# 青禾 · 生物教学工作台

给一位高中生物老师使用的课程管理网页，支持电脑和手机。

- 学生档案、教学进度、裸分/赋分记录、目标分和学校，停课归档与恢复。
- 所有学生与个人的日历网格课表、点击时段选择起止时间排课、单次与有限范围批量排课、冲突确认和系列调课/取消。
- 图片导入课表：按当前年份识别日期和开始时间，每节课 2 小时；核对修改后新增姓名/年级档案和独立课次，跳过重复课程，重叠需确认。
- 课堂笔记生成可修改的反馈候选、保存最终反馈、复制给家长、明确选择是否更新教学进度。
- 自定义正文模板、生成要求和模型；AI 密钥仅由后端从私有环境读取。
- 单老师登录、CSRF 保护、登录限流、编辑版本冲突保护、SQLite 在线备份与离线恢复。

## 本地运行

需要 Python 3.10 或以上版本，本地验证使用 Python 3.12。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
TEACHER_USERNAME=teacher TEACHER_PASSWORD=your-local-password .venv/bin/python manage.py init_teacher
.venv/bin/python manage.py runserver
```

访问 `http://127.0.0.1:8000`。替换示例密码为你自己的至少 12 字符密码。本地模式默认开启调试；正式容器强制 `DEBUG=0`，必须提供有效的私有配置。

可在启动前设置 `BAILIAN_API_KEY` 环境变量启用 AI，模型服务默认北京地域兼容地址。没有密钥时可以使用手动编辑反馈及其他功能。原始课堂输入只在当前页面临时保留，保存后长期保留最终反馈。

图片导入入口在课程日历右上方。沿用上述密钥，图片识别模型单独在反馈设置中配置，默认 `qwen3-vl-flash`。支持 JPG、PNG、WebP，最大 6 MB、2000 万像素；每次最多 100 节课。图片发送到百炼识别，确认导入前不会写入档案或课程。原图仅在当前服务内存中短期保留用于核对，最长 15 分钟，每位老师仅保留最新一张，导入完成即清除。

## 验证

```bash
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py test
.venv/bin/python manage.py makemigrations --check --dry-run
```

模型契约测试使用本地假 HTTP 服务，不消耗真实密钥或 API 额度。持续集成会运行测试并构建容器。

在已有 Ubuntu 服务器部署，推荐按 [直接部署说明（无需 Docker）](deploy/native/README.md) 操作；也保留 [Docker 方案](deploy/README.md)。两种方案均包含域名、HTTPS、升级和备份恢复。功能设计与实施计划见 `docs/superpowers/`。正式域名为 `www.gyloveyyb.site`；仓库代码完成不代表服务器已经上线。
