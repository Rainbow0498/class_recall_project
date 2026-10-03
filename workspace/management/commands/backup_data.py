import os
import sqlite3
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

class Command(BaseCommand):
    help="通过 SQLite 在线备份保存完整数据库"
    def add_arguments(self,parser):
        parser.add_argument("--output")
    def handle(self,*args,**options):
        output=Path(options["output"]) if options["output"] else settings.DATA_DIR/"backups"/("workspace-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".sqlite3")
        output.parent.mkdir(parents=True,exist_ok=True)
        try:
            descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            raise CommandError("目标备份已存在，请使用新的文件名。") from None
        os.close(descriptor)
        try:
            connection.ensure_connection()
            with sqlite3.connect(output) as target:
                connection.connection.backup(target)
        except (sqlite3.Error,OSError):
            output.unlink(missing_ok=True)
            raise CommandError("备份失败，当前数据库未修改。") from None
        self.stdout.write(str(output))
