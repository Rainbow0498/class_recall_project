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
        self.client.post(f'/lessons/{lessons[0].pk}/cancel/',{'scope':'future','confirm':'on'})
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
