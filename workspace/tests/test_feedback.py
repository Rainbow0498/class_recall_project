import json
import threading
from datetime import date, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.apps import apps

class FeedbackTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('teacher'))
        self.student=apps.get_model('workspace','Student').objects.create(name='崔子一',grade='高一',curriculum='必修1',content='旧进度',school='不应发送的学校',target_score=99)
        self.lesson=apps.get_model('workspace','Lesson').objects.create(student=self.student,date=date(2026,9,27),start_time=time(17,30),end_time=time(19,30),next_goal='不应发送的内部目标')
        self.url=f'/lessons/{self.lesson.pk}/'
        self.notes={'lesson_contents':'拉马克学说、达尔文学说','performance':'12题对11题','homework':'我发的练习'}

    def test_final_save_progress_and_stale_editor_guard(self):
        response=self.client.post(self.url,{'text':'最终反馈','version':0,'curriculum':'必修2','chapter':'第6章','content':'自然选择','update_progress':'on','next_goal':'下次复习'})
        self.assertEqual(response.status_code,302)
        self.student.refresh_from_db();self.lesson.refresh_from_db()
        self.assertEqual(self.student.content,'自然选择')
        self.assertEqual(self.lesson.status,'completed')
        self.assertEqual(self.lesson.progress_snapshot['curriculum'],'必修2')
        self.assertEqual(self.lesson.feedback.text,'最终反馈')
        response=self.client.post(self.url,{'text':'过期编辑','version':0})
        self.assertEqual(response.status_code,409)
        self.lesson.feedback.refresh_from_db();self.assertEqual(self.lesson.feedback.text,'最终反馈')

    def test_save_only_leaves_current_progress_and_escapes_text(self):
        self.client.post(self.url,{'text':'<script>alert(1)</script>','version':0,'content':'不应更新'})
        self.student.refresh_from_db();self.assertEqual(self.student.content,'旧进度')
        response=self.client.get(self.url)
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')

    def test_service_failure_does_not_change_saved_feedback(self):
        self.client.post(self.url,{'text':'保留文本','version':0})
        with override_settings(BAILIAN_API_KEY=''):
            response=self.client.post(self.url+'generate/',self.notes)
        self.assertEqual(response.status_code,503)
        self.lesson.feedback.refresh_from_db();self.assertEqual(self.lesson.feedback.text,'保留文本')

    def test_real_http_generation_contract_keeps_private_profile_out(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                received.append(json.loads(inner.rfile.read(int(inner.headers['Content-Length']))))
                body=json.dumps({'choices':[{'message':{'role':'assistant','content':'一、上课内容\n1.拉马克与达尔文\n二、学生情况\n1.12题对11题\n三、课后作业\n我发的练习'},'finish_reason':'stop'}]}).encode()
                inner.send_response(200);inner.end_headers();inner.wfile.write(body)
            def log_message(inner,*args):pass
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with override_settings(BAILIAN_API_KEY='fake-test-key',BAILIAN_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1'):
                response=self.client.post(self.url+'generate/',self.notes)
            self.assertEqual(response.status_code,200)
            text=response.json()['text']
            self.assertTrue(text.startswith('崔子一9.27生物课程情况反馈：\n17:30-19:30\n'))
            self.assertIn('12题对11题',text)
            request=json.dumps(received[0],ensure_ascii=False)
            self.assertNotIn('不应发送',request)
            self.assertNotIn('99',request)
            self.assertFalse(received[0]['enable_thinking'])
            self.assertFalse(hasattr(self.lesson,'feedback'))
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_settings_apply_only_to_future_generation(self):
        self.client.post(self.url,{'text':'旧反馈','version':0})
        response=self.client.post('/settings/',{'body_template':'三段反馈','instructions':'保留事实','model':'qwen3.7-flash'})
        self.assertEqual(response.status_code,302)
        self.lesson.feedback.refresh_from_db();self.assertEqual(self.lesson.feedback.text,'旧反馈')
        self.assertContains(self.client.get('/settings/'),'三段反馈')

    def test_generation_requires_login_and_notes(self):
        response=self.client.post(self.url+'generate/',{})
        self.assertEqual(response.status_code,400)
        self.client.logout()
        self.assertEqual(self.client.post(self.url+'generate/',self.notes).status_code,302)
