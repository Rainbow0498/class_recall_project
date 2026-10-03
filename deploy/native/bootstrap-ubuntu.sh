#!/usr/bin/env bash
set -euo pipefail
if [[ "${EUID}" != 0 ]]; then
    echo "请通过 sudo bash deploy/native/bootstrap-ubuntu.sh 运行。" >&2
    exit 1
fi
source /etc/os-release
if [[ "$ID" != ubuntu ]]; then
    echo "本脚本只适用于 Ubuntu。" >&2
    exit 1
fi
case "$VERSION_ID" in
    22.04|24.04|26.04) ;;
    *) echo "请使用 Ubuntu 22.04、24.04 或 26.04。" >&2; exit 1 ;;
esac
app_dir=/opt/biology-workspace
if [[ ! -f "$app_dir/manage.py" || ! -f "$app_dir/config/settings.py" || ! -f "$app_dir/deploy/native/biology-workspace.service" ]]; then
    echo "请先将本仓库克隆到 $app_dir。" >&2
    exit 1
fi
if systemctl is-active --quiet biology-workspace; then
    echo "应用正在运行。升级前请先备份并停止 biology-workspace 服务。" >&2
    exit 1
fi
apt-get update
apt-get install -y python3 python3-venv python3-pip ca-certificates
python3 -c 'import sys; assert sys.version_info >= (3, 10), "需要 Python 3.10 或以上版本"'
if ! id biology >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/biology-workspace --shell /usr/sbin/nologin biology
fi
install -d -o biology -g biology -m 0700 /var/lib/biology-workspace
install -d -o biology -g biology -m 0750 "$app_dir/staticfiles"
python3 -m venv "$app_dir/.venv"
"$app_dir/.venv/bin/python" -m pip install -r "$app_dir/requirements.txt"
install -m 0644 "$app_dir/deploy/native/biology-workspace.service" /etc/systemd/system/biology-workspace.service
systemctl daemon-reload
echo "环境已安装。接下来填写 /etc/biology-workspace.env，配置 Caddy，再启动服务。"
echo "完整步骤见 deploy/native/README.md。"
