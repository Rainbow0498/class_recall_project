import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from django.core.management.base import CommandError

REQUIRED_TABLES={"auth_user","workspace_student","workspace_examrecord","workspace_lesson","workspace_lessonfeedback","django_migrations"}

def restore_database(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source==target or not source.is_file():
        raise CommandError("请指定与当前数据库不同的有效备份文件。")
    try:
        with sqlite3.connect(source.as_uri()+"?mode=ro",uri=True) as backup:
            integrity=backup.execute("PRAGMA integrity_check").fetchall()
            tables={row[0] for row in backup.execute("select name from sqlite_master where type='table'")}
            if integrity != [("ok",)] or not REQUIRED_TABLES.issubset(tables):
                raise CommandError("备份不是完整的教学工作台数据库。")
            if backup.execute("PRAGMA foreign_key_check").fetchone():
                raise CommandError("备份中的关联数据校验未通过。")
    except sqlite3.Error:
        raise CommandError("备份文件无效，原数据库保持原样。") from None
    target.parent.mkdir(parents=True,exist_ok=True)
    previous=target.with_name(target.name+".before-restore-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")) if target.exists() else None
    if previous:
        shutil.copy2(target,previous);previous.chmod(0o600)
    descriptor,temp=tempfile.mkstemp(dir=target.parent,prefix="restore-")
    os.close(descriptor)
    try:
        shutil.copyfile(source,temp);os.chmod(temp,0o600);os.replace(temp,target)
    finally:
        Path(temp).unlink(missing_ok=True)
    return previous
