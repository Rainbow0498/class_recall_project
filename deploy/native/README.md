# Ubuntu 直接部署（无需 Docker）

这套网页可以直接运行在你已有的腾讯云 Ubuntu 服务器上。Python 虚拟环境安装依赖，Gunicorn 提供应用服务，systemd 负责后台运行和开机启动，Caddy 提供域名与自动 HTTPS。安装 Docker 是另一种可选部署方式。

适用于 Ubuntu 22.04、24.04、26.04 的默认 Python 3.10 或以上版本；应用本地测试使用 Python 3.12。[Django 5.2 支持的 Python 版本](https://docs.djangoproject.com/en/5.2/faq/install/)

这些文件已完成本地语法和应用验证；尚未连接你的服务器，systemd 启动和公网 HTTPS 需在服务器按下面步骤验收。

## 1. 登录服务器并准备域名

通过腾讯云控制台或自己的 SSH 客户端登录服务器（`140.143.124.16`）。下面命令都在服务器终端执行。

- 将域名 `www.gyloveyyb.site` 的 `www` A 记录指向 `140.143.124.16`；没有可用 IPv6 时不要留下错误的 AAAA 记录。
- 腾讯云安全组及服务器防火墙允许 TCP 80、443，保留已有 SSH 端口。8000 只供本机代理访问，不需要对公网开放。
- 查看已有网站和端口占用，避免覆盖正在运行的服务：`sudo ss -ltnp`。若已有 Nginx/Apache 占用 80、443，应在现有代理中接入此应用，或先安排替换；不要直接停止其他网站。
- 域名启用条件以腾讯云控制台实际状态为准。解析和端口连通后 Caddy 自动申请 HTTPS 证书。[Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)

## 2. 获取代码并安装 Python 环境

首次部署到固定目录 `/opt/biology-workspace`。若仓库为私有，先配置服务器自己的 GitHub 拉取凭据。目录已有代码时进入现有仓库，不要重复克隆。

```bash
sudo apt-get update
sudo apt-get install -y git
sudo mkdir -p /opt/biology-workspace
sudo chown "$USER":"$(id -gn)" /opt/biology-workspace
git clone --branch codex/biology-workspace https://github.com/Rainbow0498/class_recall_project.git /opt/biology-workspace
cd /opt/biology-workspace
sudo bash deploy/native/bootstrap-ubuntu.sh
```

脚本安装 Python 依赖、创建专用服务账号并注册系统服务，暂不启动网页。应用数据在 `/var/lib/biology-workspace`，与代码目录分开，更新代码不会删除学生和课程。代码目录及其父目录必须允许 `biology` 服务账号读取和进入；上述默认目录权限满足此要求。

## 3. 配置账号和密钥

```bash
sudo install -m 600 .env.example /etc/biology-workspace.env
sudo nano /etc/biology-workspace.env
```

这份配置由系统服务读取，不需要放在仓库中。修改以下值：

- `SECRET_KEY`：运行 `openssl rand -hex 32`，将生成的随机值填入。
- `TEACHER_USERNAME`：老师登录账号。
- `TEACHER_PASSWORD`：自行设置至少 12 字符的独立密码。首次启动创建账号，后续不自动重置已有密码。
- `BAILIAN_API_KEY`：百炼北京地域的 API Key；可以先留空，手动写反馈仍可用。

保持域名和其他字段不变。配置使用 `变量名=值`，复杂密码可以用双引号包住，双引号和反斜杠按 systemd 环境文件规则转义；不要写 `export`，不要把整行命令粘进配置。程序强制关闭生产调试，数据目录固定为 `/var/lib/biology-workspace`。

不要把实际配置或密钥提交到仓库。已有账号需要改密码时，使用第 6 步的密码命令。[百炼密钥配置](https://help.aliyun.com/zh/model-studio/get-api-key)

## 4. 安装 Caddy 并接入域名

如果已有 Caddy，可跳过安装，直接添加站点。新服务器可按照 [Caddy 官方 Ubuntu 安装方式](https://caddyserver.com/docs/install#debian-ubuntu-raspbian) 安装：

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy
```

以下步骤给已有主配置增加一份站点配置，保留其他站点。首次执行一次；重复操作不要重复添加同一域名。

```bash
sudo mkdir -p /etc/caddy/sites-enabled
sudo install -m 644 deploy/native/Caddyfile /etc/caddy/sites-enabled/biology-workspace.caddy
sudo nano /etc/caddy/Caddyfile
```

在主配置的**最外层**（所有站点大括号之外）加入下面一行；如果已经存在这行，不要重复添加：

```caddyfile
import /etc/caddy/sites-enabled/*.caddy
```

## 5. 启动并验收

```bash
sudo systemctl enable --now biology-workspace
sudo systemctl status biology-workspace --no-pager
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl enable caddy
sudo systemctl reload-or-restart caddy
curl -fsS https://www.gyloveyyb.site/health/
```

服务启动会依次执行数据库迁移、首次账号创建、静态资源收集及生产配置检查；失败时不会进入应用服务。最后一条命令成功后，浏览器打开 `https://www.gyloveyyb.site`，使用配置的账号登录。电脑和手机都访问这个地址。

确认学生添加、日历点击时段排课、重叠课程确认、反馈编辑保存和复制均正常，再用实际数据。API 生成需要有效密钥和额度。

故障日志：

```bash
sudo journalctl -u biology-workspace -n 80 --no-pager
sudo journalctl -u caddy -n 80 --no-pager
```

应用启动失败先核对环境文件、密码长度和依赖；HTTPS 失败核对域名、80/443 和代理日志。应用已运行而网页打不开时，不要开放 8000 到公网，应检查代理配置。

## 6. 备份、升级和改密码

在线备份（命令会输出实际备份路径）：

```bash
cd /opt/biology-workspace
sudo bash deploy/native/manage.sh backup_data
```

备份默认保存到 `/var/lib/biology-workspace/backups`。将实际备份复制到服务器之外的安全存储，单机故障时才能恢复。

升级先完成备份，再停止服务、拉取代码并重新安装依赖：

```bash
sudo systemctl stop biology-workspace
git pull --ff-only origin codex/biology-workspace
sudo bash deploy/native/bootstrap-ubuntu.sh
sudo systemctl start biology-workspace
sudo systemctl status biology-workspace --no-pager
curl -fsS https://www.gyloveyyb.site/health/
```

改密码（把 `teacher` 换为实际账号，命令会交互要求新密码）：

```bash
sudo bash deploy/native/manage.sh changepassword teacher
```

维护工具使用 systemd 读取私有配置，以应用账号运行命令；无需向终端输出密钥，也不需要将环境文件当作脚本执行。

## 7. 恢复数据库

先选择正确备份，并停止应用。外部备份先复制到 `/var/lib/biology-workspace/backups`，给 `biology:biology` 所有权及 `600` 权限。

```bash
sudo systemctl stop biology-workspace
sudo bash deploy/native/manage.sh restore_data --input /var/lib/biology-workspace/backups/实际备份文件名.sqlite3 --confirm-stopped
sudo systemctl start biology-workspace
```

恢复会替换数据库，并保留恢复前的副本。检查学生、课程、成绩、反馈和设置；登录密码使用备份时的密码。恢复成功后正常启动不会改回环境文件中的初始密码。
