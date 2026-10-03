import os
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

class AuthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("teacher", password="test-password")

    def test_private_home_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_authenticated_home_and_post_logout(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get("/"), "生物教学工作台")
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.assertEqual(self.client.post("/logout/").status_code, 302)

    def test_credentials_initialization_is_idempotent(self):
        with patch.dict(os.environ, {"TEACHER_USERNAME": "teacher", "TEACHER_PASSWORD": "different-password"}):
            call_command("init_teacher")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("test-password"))

    def test_health_exposes_no_configuration(self):
        self.assertJSONEqual(self.client.get("/health/").content, {"status": "ok"})
