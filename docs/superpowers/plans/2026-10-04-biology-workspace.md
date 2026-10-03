# 生物教学工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 完成老师单人使用的学生管理、排课与 AI 反馈应用，并提供 Ubuntu 容器部署材料。

**Architecture:** Django 服务端页面与后端统一部署，SQLite 持久保存数据。原生 JavaScript 增强反馈生成和复制，Caddy 提供 HTTPS，Docker Compose 管理应用与代理。

**Tech Stack:** Python 3.12、Django 5.2 LTS、Gunicorn、WhiteNoise、SQLite、原生 CSS/JavaScript、Caddy 2、Docker Compose。

**Spec:** `docs/superpowers/specs/2026-10-03-biology-teaching-workspace-design.md`

## Global Constraints

- 一对一，只有老师本人登录使用，电脑和手机共用服务器数据。
- 所有排课日期和显示统一使用北京时间。
- 时间冲突仅提示，用户确认后仍可添加。
- 重复课程调课、取消支持“仅本次”和“本次及之后”；已完成课程保持原样。
- 长期保留每节课的最终反馈；原始生成输入不建立单独的历史笔记库。
- 下次课目标为可选的内部备课内容，家长反馈不包含这一项。
- 目标分默认使用赋分口径。
- 密钥只在服务器私有环境配置，不写入日志、仓库或网页。
- 正式域名 `www.gyloveyyb.site`；没有服务器连接信息不声称已部署。
- 每个完成模块提交并推送 `origin codex/biology-workspace`，提交标题为“完成XX模块”，不强制推送。

## Review Focus

- 未登录访问任何学生或 AI 端点：重定向登录，生成端点不泄露配置。
- 跨周、月末与同日边界排课：有限日期范围，端点相接不视为冲突。
- 批量课程混有完成或取消记录：完成记录不变，恢复需重新确认冲突。
- 重新生成反馈失败或编辑旧课：已保存文本和当前进度不被隐式覆盖。
- 部署更新和恢复：启动不重置密码或数据，备份可恢复关联记录。

## File Structure

- `config/`：Django 环境、路由与 WSGI。
- `workspace/models.py`、`migrations/`：学生、成绩、课程系列、课程、最终反馈与设置。
- `workspace/forms.py`：中文表单及日期、成绩校验。
- `workspace/students.py`：学生档案和考试记录页面。
- `workspace/scheduling.py`：批量排课预览、冲突、系列变更与日历布局。
- `workspace/feedback.py`、`ai.py`：反馈事务保存和受限模型调用。
- `workspace/management/commands/`：初始化老师账号、备份与恢复。
- `templates/`、`static/`：响应式页面与渐进交互。
- `workspace/tests/`：真实 SQLite/HTTP 功能测试及模型服务边界测试。
- `Dockerfile`、`compose.yaml`、`deploy/`：容器、代理、初始化说明。

### Task 1: 登录与基础界面模块

**Files:** `manage.py`, `config/*`, `workspace/urls.py`, `workspace/views.py`, `workspace/management/commands/init_teacher.py`, `templates/base.html`, `templates/registration/login.html`, `static/app.css`, `workspace/tests/test_auth.py`, `requirements.txt`。

**Interfaces:** Django `login_required` 为后续页面保护入口；`init_teacher` 从 `TEACHER_USERNAME`、`TEACHER_PASSWORD` 创建首次账号，已存在账号不重置密码；`GET /health/` 只显示运行状态。

- [x] 写测试：未登录首页跳转；登录后首页可访问；退出仅允许 POST；初始化命令不重置已有账号。
- [x] 运行 `.venv/bin/python manage.py test workspace.tests.test_auth`，观察缺失路由产生失败。
- [x] 实现环境配置、认证、基础页面及中文响应式导航。生产环境缺少密钥必须拒绝启动。
- [x] 运行全套测试及 `manage.py check`，期望成功。
- [x] 提交“完成登录与基础界面模块”并推送远程分支。

### Task 2: 学生档案与成绩模块

**Files:** `workspace/models.py`, `workspace/forms.py`, `workspace/students.py`, `workspace/migrations/*`, `templates/students/*`, `workspace/tests/test_students.py`。

**Interfaces:** `Student` 保存姓名、年级、教材、章节、内容、平时裸分/赋分、赋分目标、学校、归档状态；`ExamRecord(student, date, raw_score, scaled_score)`；`Student.latest_exam` 根据日期和创建时间取最近记录。

- [x] 写测试：新建修改学生、归档恢复、彻底删除确认、考试日期排序、仅一种成绩合法、负分/超过 100/空白姓名拒绝。
- [x] 运行模块测试，期望失败于尚未实现的学生页面。
- [x] 实现列表搜索/年级筛选、档案表单、成绩增删和归档删除确认页。
- [x] 运行全套测试和迁移一致性检查，期望通过。
- [x] 提交“完成学生档案与成绩模块”并推送。

### Task 3: 排课与周课表模块

**Files:** `workspace/scheduling.py`, `workspace/models.py`, `workspace/forms.py`, `templates/schedule/*`, `templates/students/detail.html`, `workspace/tests/test_scheduling.py`。

**Interfaces:** `Lesson(student, date, start_time, end_time, series, status, next_goal)`；`CourseSeries`；`preview_occurrences(cleaned: dict) -> list[dict]`；`find_conflicts(date, start, end, exclude_ids=()) -> QuerySet`；`layout_day(lessons: list) -> list[dict]`；事务保存与批量变更。

- [x] 写测试：有限范围的指定星期生成、单次排课、冲突需确认、相接课程不冲突、非法日期和反向时间拒绝、已完成记录不可批量修改、取消恢复、单学生筛选和重叠布局。
- [x] 运行模块测试，期望缺失排课入口的失败。
- [x] 实现批量预览与二次确认；确认时再次计算冲突；只修改选定系列和范围。电脑按周时间格，手机按天列表。
- [x] 运行全套测试，期望通过；检查日历深链接和归档学生规则。
- [x] 提交“完成排课与周课表模块”并推送。

### Task 4: AI 反馈与教学进度模块

**Files:** `workspace/ai.py`, `workspace/feedback.py`, `workspace/models.py`, `workspace/forms.py`, `templates/feedback/*`, `templates/settings.html`, `static/app.js`, `workspace/tests/test_feedback.py`。

**Interfaces:** `generate_feedback(lesson, notes: dict, preferences) -> str`；`POST /lessons/<id>/generate/` 返回候选文本，不保存；`POST /lessons/<id>/` 校验版本，原子保存最终反馈及可选进度；`GET/POST /settings/` 保存模板和非敏感模型参数。

- [x] 写测试：模型请求无成绩/学校/内部目标；服务错误不覆盖反馈；保存与进度事务；旧课只在勾选时更新进度；文本转义；模板变更不改历史；并发旧版本拒绝覆盖。
- [x] 运行模块测试，期望未实现反馈与模型边界的失败。
- [x] 实现 OpenAI 兼容 HTTP 调用、非思考模式、30 秒超时、输出限制与安全错误提示。三项课堂输入不持久保存；姓名时间由应用组装。生成按钮禁止重复点击，候选明确由老师采用后再保存。
- [x] 实现设置页配置状态与试生成入口、复制与保存、课程备课目标独立保存。
- [x] 运行全套测试，期望通过；使用本地假模型服务检验真实 HTTP 契约，不消耗用户密钥。
- [x] 提交“完成AI反馈与教学进度模块”并推送。

### Task 5: 部署与备份模块

**Files:** `Dockerfile`, `.dockerignore`, `compose.yaml`, `.env.example`, `deploy/Caddyfile`, `deploy/README.md`, `workspace/management/commands/backup_data.py`, `workspace/management/commands/restore_data.py`, `workspace/tests/test_operations.py`, `README.md`。

**Interfaces:** `/app/data/db.sqlite3` 为持久存储；容器启动迁移及首次账号创建后运行 Gunicorn；备份使用 SQLite 在线备份，恢复仅在应用停止时执行并校验备份与保留原数据库。

- [x] 写测试：首次初始化幂等、真实备份恢复关联记录、无效备份不覆盖原数据、生产配置不使用开发密钥。
- [x] 运行模块测试，期望缺失操作命令的失败。
- [x] 编写容器与 HTTPS 配置、Ubuntu 初始化步骤、域名/防火墙核对、私有环境配置、升级、备份恢复说明和 CI 测试。
- [x] 运行全套测试、生产 `check --deploy`、迁移检查、浏览器桌面/手机功能验证。若本机无 Docker，报告容器构建未验证而非声称通过。
- [x] 提交“完成部署与备份模块”并推送。

## Execution Record

用户于 2026-10-04 确认设计并明确要求现在开始代码、逐模块提交推送。按此直接执行，无需再次审批计划。使用当前专用项目的功能分支，保留未跟踪的用户图片，不把它加入提交。首次最终复核采用独立审查代理，模块之间由执行者验证。

参考：[Django 部署要求](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)、[百炼 API](https://help.aliyun.com/zh/model-studio/qwen-api-reference/)。

最终复核：修复排课并发覆盖、批次内部冲突漏报和取消范围预览；手机可从反馈设置退出。补充完整关联数据与登录密码的恢复验证。Docker 本机不可用，实际容器构建与线上部署未验证。
