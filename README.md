# 青禾 · 生物教学工作台

给一位高中生物老师使用的课程管理网页，支持电脑和手机。

- 学生档案、教学进度、裸分/赋分记录、目标分和学校，停课归档与恢复。
- 所有学生周课表与个人课表、单次与有限范围批量排课、冲突确认和系列调课/取消。
- 课堂笔记生成可修改的反馈候选、保存最终反馈、复制给家长、明确选择是否更新教学进度。
- 自定义正文模板、生成要求和模型；AI 密钥仅由后端从私有环境读取。
- 单老师登录、CSRF 保护、登录限流、编辑版本冲突保护、SQLite 在线备份与离线恢复。

## 本地运行

需要 Python 3.12。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
TEACHER_USERNAME=teacher TEACHER_PASSWORD=your-local-password .venv/bin/python manage.py init_teacher
.venv/bin/python manage.py runserver
```

访问 `http://127.0.0.1:8000`。替换示例密码为你自己的至少 12 字符密码。本地模式默认开启调试；正式容器强制 `DEBUG=0`，必须提供有效的私有配置。

可在启动前设置 `BAILIAN_API_KEY` 环境变量启用 AI，模型服务默认北京地域兼容地址。没有密钥时可以使用手动编辑反馈及其他功能。原始课堂输入只在当前页面临时保留，保存后长期保留最终反馈。

## 验证

```bash
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py test
.venv/bin/python manage.py makemigrations --check --dry-run
```

模型契约测试使用本地假 HTTP 服务，不消耗真实密钥或 API 额度。持续集成会运行测试并构建容器。

正式部署、域名、HTTPS、升级和备份恢复见 [Ubuntu 部署说明](deploy/README.md)。功能设计与实施计划见 `docs/superpowers/`。正式域名为 `www.gyloveyyb.site`；仓库代码完成不代表服务器已经上线。
