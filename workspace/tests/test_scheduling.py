from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

class SchedulingTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('teacher'))
        self.client.post('/students/new/', {'name':'崔子一','grade':'高一'})
        self.student = apps.get_model('workspace','Student').objects.get()
        self.data = {'student':self.student.pk,'start_date':'2026-10-05','end_date':'2026-10-19','weekdays':['0'],'start_time':'17:30','end_time':'19:30'}

    def book(self, data=None, accept=False):
        response = self.client.post('/lessons/new/', data or self.data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('preview_token', response.context)
        return self.client.post('/lessons/new/', {'preview_token':response.context['preview_token'], 'confirm':'on', 'accept_conflicts':'on' if accept else ''})

    def test_bulk_preview_and_idempotent_confirmation(self):
        response = self.client.post('/lessons/new/', self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([str(x['date']) for x in response.context['occurrences']], ['2026-10-05','2026-10-12','2026-10-19'])
        token = response.context['preview_token']
        for _ in range(2):
            self.client.post('/lessons/new/', {'preview_token':token,'confirm':'on'})
        self.assertEqual(apps.get_model('workspace','Lesson').objects.count(), 3)

    def test_overlap_requires_explicit_confirmation_and_adjoining_is_clear(self):
        self.assertEqual(self.book().status_code, 302)
        self.assertEqual(self.book().status_code, 200)
        self.assertEqual(self.book(accept=True).status_code, 302)
        self.assertEqual(self.book(dict(self.data,start_time='19:30',end_time='20:30')).status_code, 302)
        self.assertEqual(apps.get_model('workspace','Lesson').objects.count(), 9)

    def test_series_edit_and_cancel_protect_completed(self):
        self.book()
        Lesson=apps.get_model('workspace','Lesson')
        lessons=list(Lesson.objects.order_by('date'))
        lessons[1].status='completed'; lessons[1].save()
        response=self.client.post(f'/lessons/{lessons[0].pk}/edit/', {'date':'2026-10-06','start_time':'16:00','end_time':'17:00','scope':'future','confirm':'on'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual([str(x.date) for x in Lesson.objects.order_by('pk')],['2026-10-06','2026-10-12','2026-10-20'])
        preview=self.client.post(f'/lessons/{lessons[0].pk}/cancel/',{'scope':'future'})
        self.client.post(f'/lessons/{lessons[0].pk}/cancel/',{'preview_token':preview.context['preview_token'],'confirm':'on'})
        self.assertEqual(Lesson.objects.filter(status='cancelled').count(), 2)
        self.assertEqual(Lesson.objects.filter(status='completed').count(), 1)
        self.client.post(f'/lessons/{lessons[0].pk}/restore/',{'confirm':'on'})
        lessons[0].refresh_from_db(); self.assertEqual(lessons[0].status,'scheduled')

    def test_invalid_ranges_and_archive_block_booking(self):
        for data in [dict(self.data,end_date='2026-10-01'),dict(self.data,end_time='16:00'),dict(self.data,end_date='2028-10-01')]:
            response=self.client.post('/lessons/new/',data)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
        self.student.archived=True;self.student.save()
        response=self.client.post('/lessons/new/',self.data)
        self.assertTrue(response.context['form'].errors)

    def test_week_filter_and_overlap_layout(self):
        self.book();self.book(accept=True)
        response=self.client.get(f'/?week=2026-10-05&student={self.student.pk}')
        self.assertContains(response,'崔子一')
        self.assertEqual(response.context['lesson_count'],2)
        day=response.context['days'][0]
        self.assertEqual(len(day['layout']),2)
        self.assertNotEqual(day['layout'][0]['left'],day['layout'][1]['left'])
        self.assertContains(self.client.get(f'/students/{self.student.pk}/'),'2026')

    def test_booking_is_private(self):
        self.client.logout()
        self.assertEqual(self.client.post('/lessons/new/',self.data).status_code,302)

class SchedulingRegressionTests(TestCase):
    setUp=SchedulingTests.setUp
    book=SchedulingTests.book
    def test_edit_preserves_feedback_saved_during_conflict_check(self):
        from unittest.mock import patch
        from workspace import scheduling
        self.book();Lesson=apps.get_model('workspace','Lesson');lesson=Lesson.objects.order_by('date').first()
        original=scheduling.find_conflicts
        entered=False
        def interleave(*args,**kwargs):
            nonlocal entered
            if not entered:
                entered=True
                self.client.post(f'/lessons/{lesson.pk}/',{'text':'刚保存的反馈','version':0,'next_goal':'新目标','curriculum':'必修2','content':'新进度','update_progress':'on'})
            return original(*args,**kwargs)
        with patch('workspace.scheduling.find_conflicts',side_effect=interleave):
            response=self.client.post(f'/lessons/{lesson.pk}/edit/',{'date':'2026-10-06','start_time':'16:00','end_time':'17:00','scope':'future','confirm':'on'})
        self.assertEqual(response.status_code,409)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status,'completed')
        self.assertEqual(str(lesson.date),'2026-10-05')
        self.assertEqual(lesson.next_goal,'新目标')
        self.assertEqual(lesson.progress_snapshot['content'],'新进度')
        self.assertEqual(lesson.version,1)
        self.assertEqual(lesson.feedback.text,'刚保存的反馈')
        self.assertEqual(str(Lesson.objects.order_by('date').last().date),'2026-10-19')

    def test_proposed_batch_conflicts_require_confirmation(self):
        Lesson=apps.get_model('workspace','Lesson');Series=apps.get_model('workspace','CourseSeries')
        series=Series.objects.create(token='regression-series')
        a=Lesson.objects.create(student=self.student,series=series,date='2026-10-05',start_time='09:00',end_time='11:00')
        Lesson.objects.create(student=self.student,series=series,date='2026-10-05',start_time='17:00',end_time='19:00')
        data={'date':'2026-10-05','start_time':'16:00','end_time':'18:00','scope':'future'}
        response=self.client.post(f'/lessons/{a.pk}/edit/',data)
        self.assertTrue(response.context['has_conflicts'])
        response=self.client.post(f'/lessons/{a.pk}/edit/',dict(data,confirm='on'))
        self.assertEqual(response.status_code,200)
        response=self.client.post(f'/lessons/{a.pk}/edit/',dict(data,confirm='on',accept_conflicts='on'))
        self.assertEqual(response.status_code,302)

    def test_cancel_preview_lists_actual_range_and_protects_newly_completed(self):
        self.book();Lesson=apps.get_model('workspace','Lesson');lessons=list(Lesson.objects.order_by('date'))
        lessons[1].status='completed';lessons[1].save()
        url=f'/lessons/{lessons[0].pk}/cancel/'
        preview=self.client.post(url,{'scope':'future'})
        self.assertContains(preview,'2026.10.19')
        self.assertEqual(len(preview.context['targets']),2)
        self.assertEqual(Lesson.objects.filter(status='cancelled').count(),0)
        token=preview.context['preview_token']
        self.client.post(f'/lessons/{lessons[0].pk}/',{'text':'已完成反馈','version':0})
        response=self.client.post(url,{'confirm':'on','preview_token':token})
        self.assertEqual(response.status_code,409)
        self.assertEqual(Lesson.objects.filter(status='cancelled').count(),0)

    def test_cancel_transaction_preserves_concurrently_saved_feedback(self):
        from unittest.mock import patch
        from workspace import scheduling
        self.book();lesson=apps.get_model('workspace','Lesson').objects.order_by('date').first()
        url=f'/lessons/{lesson.pk}/cancel/'
        preview=self.client.post(url,{'scope':'future'})
        self.assertIn('preview_token',preview.context)
        token=preview.context['preview_token']
        original=scheduling.scoped_lessons
        def interleave(*args,**kwargs):
            targets=original(*args,**kwargs)
            self.client.post(f'/lessons/{lesson.pk}/',{'text':'刚完成的课','version':0})
            return targets
        with patch('workspace.scheduling.scoped_lessons',side_effect=interleave):
            response=self.client.post(url,{'confirm':'on','preview_token':token})
        self.assertEqual(response.status_code,409)
        lesson.refresh_from_db();self.assertEqual(lesson.status,'completed');self.assertEqual(lesson.version,1)

class CalendarSelectionTests(TestCase):
    setUp=SchedulingTests.setUp

    def test_clickable_calendar_slots_and_mobile_day_grid(self):
        response=self.client.get('/?week=2026-10-05&day=2026-10-07')
        self.assertEqual(response.status_code,200)
        self.assertEqual(str(response.context['selected_day']),'2026-10-07')
        self.assertEqual(response.context['days'][0]['slots'][0]['start'],'08:00')
        self.assertEqual(response.context['days'][0]['slots'][0]['end'],'10:00')
        self.assertContains(response,'id="slot-dialog"')
        self.assertContains(response,'选择时段安排课程')
        self.assertContains(response,'start=08%3A00')
        self.assertNotContains(response,'今天没有安排课程，留一点时间给备课。')

    def test_grid_link_prefills_valid_date_and_time_range(self):
        response=self.client.get(f'/lessons/new/?date=2026-10-07&start=14:30&end=16:30&student={self.student.pk}')
        initial=response.context['form'].initial
        self.assertEqual(str(initial['start_date']),'2026-10-07')
        self.assertEqual(initial['start_time'],'14:30')
        self.assertEqual(initial['end_time'],'16:30')
        self.assertEqual(int(initial['student']),self.student.pk)

    def test_invalid_slot_parameters_do_not_break_form(self):
        response=self.client.get('/lessons/new/?date=bad&start=99:99&end=01:00')
        self.assertEqual(response.status_code,200)
        self.assertNotEqual(response.context['form'].initial.get('start_date'),'bad')
        self.assertEqual(response.context['form'].initial['start_time'],'17:30')
        self.assertEqual(response.context['form'].initial['end_time'],'19:30')
        response=self.client.get('/lessons/new/',{'start':'14:30+08:00','end':'16:30'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['form'].initial['start_time'],'17:30')

    def test_late_evening_slot_stays_within_day(self):
        apps.get_model('workspace','Lesson').objects.create(student=self.student,date='2026-10-05',start_time='23:00',end_time='23:59')
        response=self.client.get('/?week=2026-10-05')
        slot=response.context['days'][0]['slots'][-1]
        self.assertEqual(slot['start'],'23:30')
        self.assertEqual(slot['end'],'23:59')
