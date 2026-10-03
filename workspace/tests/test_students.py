from django.contrib.auth import get_user_model
from django.test import TestCase
from django.apps import apps

class StudentTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('teacher'))
        self.data = {'name': '崔子一', 'grade': '高一', 'curriculum': '必修1', 'chapter': '第2章', 'content': '细胞结构', 'target_score': '90', 'school': '目标大学'}

    def create_student(self):
        response = self.client.post('/students/new/', self.data)
        self.assertEqual(response.status_code, 302)
        return apps.get_model('workspace', 'Student').objects.get()

    def test_create_edit_and_search(self):
        student = self.create_student()
        self.assertContains(self.client.get('/students/?q=崔'), '崔子一')
        changed = dict(self.data, content='细胞膜', usual_raw='65', usual_scaled='80')
        self.assertEqual(self.client.post(f'/students/{student.pk}/edit/', changed).status_code, 302)
        student.refresh_from_db()
        self.assertEqual(student.content, '细胞膜')
        self.assertEqual(student.usual_scaled, 80)
        self.assertNotContains(self.client.get('/students/?q=不存在'), '崔子一')

    def test_archive_restore_and_confirmed_delete(self):
        student = self.create_student()
        self.client.post(f'/students/{student.pk}/archive/')
        self.assertNotContains(self.client.get('/students/'), '崔子一')
        self.assertContains(self.client.get('/students/?archived=1'), '崔子一')
        self.client.post(f'/students/{student.pk}/archive/')
        student.refresh_from_db()
        self.assertFalse(student.archived)
        self.client.post(f'/students/{student.pk}/delete/')
        self.assertTrue(type(student).objects.filter(pk=student.pk).exists())
        self.client.post(f'/students/{student.pk}/delete/', {'confirm': 'on'})
        self.assertFalse(type(student).objects.filter(pk=student.pk).exists())

    def test_exam_sorting_partial_scores_and_validation(self):
        student = self.create_student()
        url = f'/students/{student.pk}/exams/new/'
        self.client.post(url, {'date': '2026-09-30', 'scaled_score': '84'})
        self.client.post(url, {'date': '2026-09-10', 'raw_score': '70'})
        self.assertEqual(student.latest_exam.scaled_score, 84)
        self.assertEqual(self.client.post(url, {'date': '2026-10-01', 'raw_score': '-1'}).status_code, 200)
        self.assertEqual(self.client.post(url, {'date': '2026-10-01', 'raw_score': '101'}).status_code, 200)
        self.client.post(url, {'date': '2026-10-01'})
        self.assertEqual(student.exams.count(), 2)
        self.assertContains(self.client.get(f'/students/{student.pk}/'), '84')

    def test_blank_name_rejected(self):
        response = self.client.post('/students/new/', dict(self.data, name='   '))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '这个字段是必填项')

    def test_student_routes_are_private(self):
        self.client.logout()
        self.assertEqual(self.client.get('/students/').status_code, 302)
        self.assertEqual(self.client.post('/students/new/', self.data).status_code, 302)
