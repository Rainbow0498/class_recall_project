import base64
import io
import json
import threading
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from workspace.models import CourseSeries, Lesson, Student


ROWS = [
    {'name':'示例甲','grade':'高三','date':'2026-09-22','start_time':'13:30'},
    {'name':'示例乙','grade':'其他','date':'2026-09-25','start_time':'19:30'},
    {'name':'示例丙','grade':'高二','date':'2026-09-26','start_time':'10:30'},
    {'name':'示例丁','grade':'高三','date':'2026-09-26','start_time':'13:30'},
    {'name':'示例甲','grade':'高三','date':'2026-09-26','start_time':'15:30'},
    {'name':'示例甲','grade':'高三','date':'2026-09-27','start_time':'15:30'},
]


def image_file():
    data=io.BytesIO(); Image.new('RGB',(64,64),'white').save(data,format='PNG')
    return SimpleUploadedFile('schedule.png',data.getvalue(),content_type='image/png')


@contextmanager
def vision_server(rows=None, content=None, status=200, finish='stop'):
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            text=content if content is not None else json.dumps({'lessons':rows if rows is not None else ROWS,'warnings':[]},ensure_ascii=False)
            body=json.dumps({'choices':[{'message':{'content':text},'finish_reason':finish}]}).encode()
            self.send_response(status); self.end_headers(); self.wfile.write(body)
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        with override_settings(BAILIAN_API_KEY='fake-vision-key',BAILIAN_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1'):
            yield received
    finally:
        server.shutdown(); server.server_close(); thread.join()


class ImageImportTests(TestCase):
    url='/lessons/import/'
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)
        self.client.force_login(get_user_model().objects.create_user('teacher'))
        self.student=Student.objects.create(name='示例丙',grade='高一',usual_raw=80,content='保留进度',school='不应发送的学校')
        self.today=patch('django.utils.timezone.localdate',return_value=date(2026,10,4)); self.today.start(); self.addCleanup(self.today.stop)

    def recognize(self,rows=None,**kwargs):
        with vision_server(rows,**kwargs) as received:
            response=self.client.post(self.url,{'action':'recognize','image':image_file()})
        self.assertEqual(response.status_code,200)
        self.assertIn('draft_token',response.context)
        return response,received

    def preview(self,response,edits=None):
        forms=response.context['formset']
        data={'action':'preview','draft_token':response.context['draft_token'],'rows-TOTAL_FORMS':len(forms),'rows-INITIAL_FORMS':len(forms),'rows-MIN_NUM_FORMS':1,'rows-MAX_NUM_FORMS':100}
        for index,form in enumerate(forms):
            for field in ('name','grade','date','start_time','student'):
                value=form.initial.get(field,'')
                data[f'rows-{index}-{field}']=value.pk if hasattr(value,'pk') else value
            data[f'rows-{index}-include']='on'
        data.update(edits or {})
        return self.client.post(self.url,data)

    def confirm(self,response,accept=False):
        self.assertIn('confirm_token',response.context)
        return self.client.post(self.url,{'action':'confirm','confirm_token':response.context['confirm_token'],'accept_conflicts':'on' if accept else ''})

    def test_upload_recognizes_real_image_contract_without_creating_records(self):
        response,received=self.recognize()
        self.assertEqual(len(response.context['formset']),6)
        self.assertEqual(Student.objects.count(),1); self.assertEqual(Lesson.objects.count(),0)
        payload=received[0]
        self.assertEqual(payload['model'],'qwen3-vl-flash')
        self.assertFalse(payload['enable_thinking'])
        image=payload['messages'][1]['content'][0]['image_url']['url']
        self.assertTrue(image.startswith('data:image/png;base64,'))
        self.assertEqual(base64.b64decode(image.split(',',1)[1]),image_file().read())
        prompt=json.dumps(payload,ensure_ascii=False)
        self.assertIn('2026',prompt); self.assertNotIn('不应发送的学校',prompt)
        self.assertContains(response,'核对识别结果')

    def test_confirm_creates_only_missing_students_and_two_hour_lessons_once(self):
        response,_=self.recognize(); preview=self.preview(response)
        self.assertEqual(Student.objects.count(),1); self.assertEqual(Lesson.objects.count(),0)
        self.assertEqual(self.confirm(preview).status_code,302)
        self.assertEqual(self.confirm(preview).status_code,302)
        self.assertEqual(Student.objects.count(),4); self.assertEqual(Lesson.objects.count(),6)
        self.assertEqual(Student.objects.get(name='示例甲').lessons.count(),3)
        lesson=Lesson.objects.get(student__name='示例甲',date='2026-09-27')
        self.assertEqual(str(lesson.start_time),'15:30:00'); self.assertEqual(str(lesson.end_time),'17:30:00')
        self.student.refresh_from_db(); self.assertEqual(self.student.grade,'高一'); self.assertEqual(self.student.usual_raw,80); self.assertEqual(self.student.content,'保留进度')
        self.assertIsNone(Student.objects.get(name='示例丁').usual_raw)

    def test_repeat_upload_skips_existing_same_student_date_and_time(self):
        response,_=self.recognize(); self.confirm(self.preview(response))
        response,_=self.recognize(); preview=self.preview(response)
        self.assertEqual(preview.context['plan']['duplicate_count'],6)
        self.assertEqual(preview.context['plan']['lesson_count'],0)
        self.assertEqual(self.confirm(preview).status_code,302)
        self.assertEqual(Student.objects.count(),4); self.assertEqual(Lesson.objects.count(),6)

    def test_editable_rows_can_be_corrected_and_unchecked(self):
        response,_=self.recognize(rows=ROWS[:2])
        preview=self.preview(response,{'rows-0-name':'改正后的姓名','rows-0-grade':'高二','rows-0-date':'2026-10-05','rows-0-start_time':'15:30','rows-1-include':''})
        self.assertEqual(self.confirm(preview).status_code,302)
        lesson=Lesson.objects.get(); self.assertEqual(lesson.student.name,'改正后的姓名'); self.assertEqual(lesson.student.grade,'高二'); self.assertEqual(str(lesson.date),'2026-10-05')
        self.assertFalse(Student.objects.filter(name='示例乙').exists())

    def test_overlap_requires_confirmation_and_changed_conflicts_require_new_preview(self):
        Lesson.objects.create(student=self.student,date='2026-09-22',start_time='14:00',end_time='16:00')
        response,_=self.recognize(rows=ROWS[:1]); preview=self.preview(response)
        self.assertTrue(preview.context['plan']['has_conflicts'])
        rejected=self.confirm(preview)
        self.assertEqual(rejected.status_code,200); self.assertEqual(Lesson.objects.count(),1)
        Lesson.objects.create(student=self.student,date='2026-09-22',start_time='15:00',end_time='17:00')
        changed=self.confirm(preview,accept=True)
        self.assertEqual(changed.status_code,200); self.assertContains(changed,'课表已更新'); self.assertEqual(Lesson.objects.count(),2)
        self.assertEqual(self.confirm(changed,accept=True).status_code,302)
        self.assertEqual(Lesson.objects.count(),3)

    def test_same_name_ambiguity_and_archived_students_require_resolution(self):
        Student.objects.create(name='示例丙',grade='高三')
        response,_=self.recognize(rows=[ROWS[2]]); preview=self.preview(response)
        self.assertContains(response,f'示例丙 · 高一 · #{self.student.pk}')
        self.assertContains(response,'data-name="示例丙"')
        self.assertContains(preview,'同名'); self.assertNotIn('confirm_token',preview.context)
        preview=self.preview(response,{'rows-0-student':self.student.pk})
        self.assertEqual(self.confirm(preview).status_code,302)
        self.assertEqual(Lesson.objects.get().student_id,self.student.pk)
        archived=Student.objects.create(name='示例甲',grade='高三',archived=True)
        response,_=self.recognize(rows=ROWS[:1]); preview=self.preview(response)
        self.assertContains(preview,'已归档'); self.assertEqual(Student.objects.filter(name=archived.name).count(),1)

    def test_image_and_model_errors_do_not_write_students_or_lessons(self):
        for content in ('not json',json.dumps({'lessons':[dict(ROWS[0],date='2025-09-22')]}),json.dumps({'lessons':[dict(ROWS[0],start_time='23:30')]})):
            with self.subTest(content=content), vision_server(content=content):
                response=self.client.post(self.url,{'action':'recognize','image':image_file()})
                self.assertEqual(response.status_code,200); self.assertNotIn('draft_token',response.context)
        with override_settings(BAILIAN_API_KEY=''):
            response=self.client.post(self.url,{'action':'recognize','image':image_file()})
            self.assertContains(response,'密钥')
        response=self.client.post(self.url,{'action':'recognize','image':SimpleUploadedFile('fake.png',b'not an image',content_type='image/png')})
        self.assertContains(response,'图片')
        self.assertEqual(Student.objects.count(),1); self.assertEqual(Lesson.objects.count(),0)

    def test_duplicate_rows_in_image_collapse_to_one_course(self):
        response,_=self.recognize(rows=[ROWS[0],ROWS[0]])
        preview=self.preview(response); self.confirm(preview)
        self.assertEqual(Lesson.objects.count(),1); self.assertEqual(Student.objects.filter(name='示例甲').count(),1)

    def test_import_requires_login_csrf_and_valid_signed_preview(self):
        response=self.client.post(self.url,{'action':'confirm','confirm_token':'tampered'})
        self.assertEqual(response.status_code,400)
        csrf_client=Client(enforce_csrf_checks=True)
        csrf_client.force_login(get_user_model().objects.get(username='teacher'))
        self.assertEqual(csrf_client.post(self.url,{'action':'recognize','image':image_file()}).status_code,403)
        self.client.logout(); self.assertEqual(self.client.get(self.url).status_code,302)

    def test_student_archived_after_preview_can_be_corrected_without_partial_import(self):
        response,_=self.recognize(rows=[ROWS[2]]); preview=self.preview(response)
        self.student.archived=True; self.student.save()
        rejected=self.confirm(preview)
        self.assertEqual(rejected.status_code,409)
        self.assertContains(rejected,'已归档',status_code=409)
        self.assertEqual(Lesson.objects.count(),0); self.assertEqual(CourseSeries.objects.count(),0)

    def test_batch_internal_overlap_is_shown_before_import(self):
        response,_=self.recognize(rows=[ROWS[0],dict(ROWS[0],name='另一位学生',start_time='14:00')])
        preview=self.preview(response)
        self.assertTrue(preview.context['plan']['has_conflicts'])
        self.assertEqual(self.confirm(preview).status_code,200); self.assertEqual(Lesson.objects.count(),0)
        self.assertEqual(self.confirm(preview,accept=True).status_code,302); self.assertEqual(Lesson.objects.count(),2)

    def test_imported_lessons_do_not_move_other_students_when_editing_future_scope(self):
        response,_=self.recognize(rows=ROWS[:2]); self.confirm(self.preview(response))
        first=Lesson.objects.get(student__name='示例甲')
        other=Lesson.objects.get(student__name='示例乙')
        data={'date':'2026-09-23','start_time':'15:30','end_time':'17:30','scope':'future'}
        preview=self.client.post(f'/lessons/{first.pk}/edit/',data)
        self.assertEqual(len(preview.context['occurrences']),1)
        self.client.post(f'/lessons/{first.pk}/edit/',dict(data,confirm='on'))
        other.refresh_from_db(); self.assertEqual(str(other.date),'2026-09-25'); self.assertEqual(str(other.start_time),'19:30:00')

    def test_imported_lessons_do_not_cancel_other_students_in_future_scope(self):
        response,_=self.recognize(rows=ROWS[:2]); self.confirm(self.preview(response))
        first=Lesson.objects.get(student__name='示例甲')
        url=f'/lessons/{first.pk}/cancel/'
        preview=self.client.post(url,{'scope':'future'})
        self.assertEqual(len(preview.context['targets']),1)
        self.client.post(url,{'confirm':'on','preview_token':preview.context['preview_token']})
        self.assertEqual(Lesson.objects.get(student__name='示例乙').status,'scheduled')

    def test_preview_token_cannot_be_used_by_another_account(self):
        response,_=self.recognize(rows=ROWS[:1]); preview=self.preview(response)
        self.client.force_login(get_user_model().objects.create_user('another'))
        self.assertEqual(self.confirm(preview).status_code,400)
        self.assertEqual(Lesson.objects.count(),0)

    def test_original_image_remains_available_when_correcting_and_clears_after_import(self):
        response,_=self.recognize(rows=ROWS[:1])
        original=response.context['image_url']
        invalid=self.preview(response,{'rows-0-date':'2025-09-22'})
        self.assertEqual(invalid.context.get('image_url'),original)
        preview=self.preview(response)
        edit=self.client.post(self.url,{'action':'edit','confirm_token':preview.context['confirm_token']})
        self.assertEqual(edit.context.get('image_url'),original)
        self.confirm(preview)
        self.assertIsNone(cache.get(f"image-preview:{get_user_model().objects.get(username='teacher').pk}"))

    def test_import_transaction_rolls_back_new_students_on_failure(self):
        response,_=self.recognize(rows=ROWS[:1]); preview=self.preview(response)
        from django.db import OperationalError
        with patch('workspace.image_import.Lesson.objects.bulk_create',side_effect=OperationalError('database is locked')):
            failed=self.confirm(preview)
        self.assertEqual(failed.status_code,409)
        self.assertEqual(Student.objects.count(),1); self.assertEqual(Lesson.objects.count(),0); self.assertEqual(CourseSeries.objects.count(),0)

    def test_inconsistent_grades_for_new_same_name_are_not_silently_imported(self):
        response,_=self.recognize(rows=[ROWS[0],dict(ROWS[0],date='2026-09-23',grade='高二')])
        preview=self.preview(response)
        self.assertContains(preview,'年级'); self.assertNotIn('confirm_token',preview.context)
