import os
import sqlite3
import tempfile
from pathlib import Path
from io import StringIO
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase, TestCase

class BackupTests(TransactionTestCase):
    def test_online_backup_contains_related_data(self):
        student=apps.get_model('workspace','Student').objects.create(name='备份学生',grade='高三')
        apps.get_model('workspace','ExamRecord').objects.create(student=student,date='2026-10-04',scaled_score=88)
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'backup.sqlite3'
            call_command('backup_data',output=str(output),stdout=StringIO())
            with sqlite3.connect(output) as db:
                self.assertEqual(db.execute('select name from workspace_student').fetchone()[0],'备份学生')
                self.assertEqual(db.execute('select scaled_score from workspace_examrecord').fetchone()[0],88)
            self.assertEqual(output.stat().st_mode & 0o777,0o600)

    def test_restore_validates_before_replacing_and_keeps_previous(self):
        from workspace.operations import restore_database
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'current.sqlite3'
            source=Path(folder)/'source.sqlite3'
            bad=Path(folder)/'invalid.sqlite3'
            bad.write_text('invalid')
            target.write_text('previous data')
            with self.assertRaises(CommandError):restore_database(bad,target)
            self.assertEqual(target.read_text(),'previous data')
            call_command('backup_data',output=str(source),stdout=StringIO())
            previous=restore_database(source,target)
            self.assertEqual(previous.read_text(),'previous data')
            with sqlite3.connect(target) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_restore_requires_explicit_stopped_confirmation(self):
        with self.assertRaises(CommandError):
            call_command('restore_data',input='not-used.sqlite3')

class LoginGuardTests(TestCase):
    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user('teacher',password='correct-password')

    def test_repeated_failed_login_temporarily_blocks_attempts(self):
        for _ in range(5): self.client.post('/login/',{'username':'teacher','password':'wrong'})
        response=self.client.post('/login/',{'username':'teacher','password':'correct-password'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'尝试次数过多')
        cache.clear()
        self.assertEqual(self.client.post('/login/',{'username':'teacher','password':'correct-password'}).status_code,302)
