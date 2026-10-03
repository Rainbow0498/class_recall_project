from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from workspace.operations import restore_database

class Command(BaseCommand):
    help="应用停止后恢复数据库，保留恢复前副本"
    def add_arguments(self,parser):
        parser.add_argument("--input",required=True)
        parser.add_argument("--confirm-stopped",action="store_true")
    def handle(self,*args,**options):
        if not options["confirm_stopped"]:
            raise CommandError("先停止应用，再传入 --confirm-stopped 确认恢复。")
        target=Path(connections["default"].settings_dict["NAME"])
        connections.close_all()
        previous=restore_database(options["input"],target)
        self.stdout.write("恢复完成。"+("恢复前数据库保留于："+str(previous) if previous else ""))
