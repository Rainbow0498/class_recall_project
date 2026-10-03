# Ubuntu 部署说明（Docker 方案）

**Docker 不是必须的。** 若想在已有 Ubuntu 服务器上直接运行，使用 [不依赖 Docker 的部署说明](native/README.md)，包含 Python 环境、后台服务、HTTPS、升级与备份步骤。下面保留可选的 Docker 方案；在同一服务器上选择一种方式即可。

应用目标地址：`https://www.gyloveyyb.site`，用户提供的服务器 IP 为 `140.143.124.16`。这份说明不代表服务器已经完成部署。本机没有 Docker，容器构建与证书签发必须在服务器或 CI 中验证。

## 1. 服务器和域名准备

使用服务器的 SSH 账号登录，先查看 Ubuntu 版本、内存、磁盘及 80/443 端口是否已有服务。不要直接替换已有网站。

- 域名管理平台将 `www` 的 A 记录指向 `140.143.124.16`。
- 若有 AAAA 记录，必须指向这台服务器可用的 IPv6；没有可用 IPv6 时不要留下错误记录。
- 腾讯云安全组允许 TCP 80、443，并保留你当前使用的 SSH 端口。
- 核对服务器防火墙及云平台对域名启用的要求。域名注册完成与国内服务器可对外提供网站是不同步骤，相关条件以腾讯云实际状态为准。
- `www.gyloveyyb.site` 为正式入口；不自动为裸域名 `gyloveyyb.site` 签发证书。

Caddy 在域名解析和端口连通后自动申请 HTTPS 证书。该方案仅公开代理的 80/443 端口，应用的 8000 端口不映射到公网。[Caddy 自动 HTTPS 说明](https://caddyserver.com/docs/automatic-https)

## 2. 获取代码并安装环境

仓库当前实现位于 `codex/biology-workspace` 分支。若仓库为私有，先在服务器配置你自己的 GitHub 只读拉取凭据。

```bash
sudo apt-get update
sudo apt-get install -y git
sudo mkdir -p /opt/biology-workspace
sudo chown "$USER":"$(id -gn)" /opt/biology-workspace
git clone --branch codex/biology-workspace https://github.com/Rainbow0498/class_recall_project.git /opt/biology-workspace
cd /opt/biology-workspace
sudo bash deploy/bootstrap-ubuntu.sh
```

环境初始化脚本依据 [Docker 官方 Ubuntu 安装方法](https://docs.docker.com/engine/install/ubuntu/)，安装 Docker 与 Compose。检测到现有 Docker 时保留现有安装；检测到可能冲突的容器组件时停止，不自动卸载。它不修改 SSH 或防火墙配置。服务器访问 Docker 软件源和镜像源失败时，先解决网络或配置可信的镜像源。

## 3. 填写私有配置

```bash
umask 077
cp .env.example .env
chmod 600 .env
nano .env
```

需要自行替换的字段：

- `SECRET_KEY`：至少 50 字符的随机字符串。可运行 `openssl rand -hex 32`，将结果只填入服务器 `.env`。
- `TEACHER_USERNAME`：老师登录账号。
- `TEACHER_PASSWORD`：独立的至少 12 字符密码，不要使用示例占位内容。首次启动创建账号，后续启动不会重置已有密码。
- `BAILIAN_API_KEY`：百炼北京地域的普通按量付费 API Key，直接填入 `.env`；无需发到聊天或提交到仓库。可以先留空，手动反馈和其他功能仍可使用。
- `BAILIAN_BASE_URL`：默认北京地域 OpenAI 兼容服务地址。使用工作空间专属地址时，替换为对应北京工作空间地址。

其余域名字段保持示例中的 `www.gyloveyyb.site` 即可。配置中不要放真实学生资料。[百炼密钥配置](https://help.aliyun.com/zh/model-studio/get-api-key)

模型默认 `qwen3.7-flash`，可在登录后的反馈设置页面修改；那里只显示密钥配置状态，无法查看密钥。

图片课表导入沿用同一个 `BAILIAN_API_KEY`，但使用单独的视觉模型，默认 `qwen3-vl-flash`，可在反馈设置中的“图片课表识别模型”修改。所用模型需支持图片输入，密钥需有对应模型权限和可用额度。[百炼视觉理解接口说明](https://help.aliyun.com/zh/model-studio/vision)

## 4. 首次启动

```bash
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose logs --tail=80 app caddy
```

应用启动时执行数据库迁移、首次账号初始化和生产环境检查；任一步失败会停止启动。Caddy 等应用健康检查通过后再启动代理。浏览器访问正式 HTTPS 域名，使用配置的老师账号登录。

依次验证：添加学生、录入成绩、预览重复排课、确认重叠课程、生成候选反馈、采用修改保存、重新打开历史反馈、复制文本。手机使用同一地址与账号。

若 HTTPS 无法签发，检查 A/AAAA 记录、80/443 连通性、已有端口占用及 Caddy 日志。AI 无法生成时检查密钥地域、余额、模型权限和服务器到百炼的连通性；页面已有输入和保存的反馈会保留。

## 5. 备份与升级

数据库保存在名为 `biology-workspace_app_data` 的持久卷中。普通容器更新保留它。**不要运行 `docker compose down -v`，该命令会删除持久卷。**

应用运行期间可在线备份：

```bash
sudo docker compose exec app python manage.py backup_data
```

命令输出容器内备份路径 `/app/data/backups/workspace-日期时间.sqlite3`。将实际文件名替换到下面的路径，并复制到服务器之外的安全存储；只留在同一台服务器上不能防止整台服务器故障。

```bash
mkdir -p backups
sudo docker compose cp app:/app/data/backups/实际备份文件名.sqlite3 ./backups/
```

升级前先备份，再执行：

```bash
git pull --ff-only origin codex/biology-workspace
sudo docker compose up -d --build
sudo docker compose ps
```

图片导入版本同样按上述方式升级，需要重新构建以安装图片读取依赖。启动时自动执行新增的模型设置迁移，保留现有数据库、老师密码及私有配置。你当前的服务器项目目录为 `/dev/biology-workspace`，执行升级前先进入该目录。

升级后打开“课程日历 → 图片导入”，选择课表图，核对姓名、年级、日期和时段，再确认新增。日期使用当前年份，每节课固定 2 小时；已有档案不会修改，缺失档案只创建姓名和年级，已有同一学生同一时段课程会跳过。重叠课程需勾选确认。同一次图片导入的课程是独立课次，后续调整或取消不会连带其他学生。

修改老师密码：

```bash
sudo docker compose exec app python manage.py changepassword teacher
```

将 `teacher` 换为实际账号。修改 `.env` 中的初始密码不会修改数据库里的已有密码。

## 6. 恢复数据

恢复会替换当前数据库。先确认应用停止，选择正确备份文件；命令会校验完整性及必要的数据表，并保留恢复前数据库副本。

```bash
sudo docker compose stop app
sudo docker compose run --rm --no-deps app python manage.py restore_data --input /app/data/backups/实际备份文件名.sqlite3 --confirm-stopped
sudo docker compose up -d app
```

如果备份来自服务器之外，先在应用运行时导入，并给容器中的应用账号读取权限，再停止应用并恢复：

```bash
sudo docker compose exec app mkdir -p /app/data/backups
sudo docker compose cp ./backups/实际备份文件名.sqlite3 app:/app/data/backups/imported.sqlite3
sudo docker compose exec --user root app chown teacher:teacher /app/data/backups/imported.sqlite3
sudo docker compose exec --user root app chmod 600 /app/data/backups/imported.sqlite3
```

然后在恢复命令中使用 `/app/data/backups/imported.sqlite3`。恢复后检查学生数量、课程、反馈和成绩；备份包含老师账号及反馈设置，应使用备份时的登录密码。

## 7. 日常维护

定期在线备份并复制到其他安全存储，升级前也备份；定期检查磁盘空间与证书/服务状态。生产环境关闭调试；单 worker 加 4 个线程适合这一版单老师使用，也保证登录限流与重复生成保护共用同一进程缓存。
