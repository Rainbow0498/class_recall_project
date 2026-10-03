import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = "使用服务器环境首次创建老师账号；不修改已有账号密码"
    def handle(self, *args, **options):
        username = os.environ.get("TEACHER_USERNAME", "").strip()
        password = os.environ.get("TEACHER_PASSWORD", "")
        if not username or len(password) < 12 or password.startswith("REPLACE_"):
            raise CommandError("请配置 TEACHER_USERNAME 和至少 12 字符的 TEACHER_PASSWORD")
        User = get_user_model()
        if not User.objects.filter(username=username).exists():
            User.objects.create_user(username=username, password=password)
            self.stdout.write("老师账号已创建")
        else:
            self.stdout.write("老师账号已存在，保留原密码")
