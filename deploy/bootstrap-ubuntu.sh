#!/usr/bin/env bash
set -euo pipefail
if [[ "${EUID}" != 0 ]]; then
    echo "请通过 sudo bash deploy/bootstrap-ubuntu.sh 运行。" >&2
    exit 1
fi
source /etc/os-release
if [[ "$ID" != "ubuntu" ]]; then
    echo "本脚本只适用于 Ubuntu。" >&2
    exit 1
fi
case "$VERSION_ID" in
    22.04|24.04|26.04) ;;
    *) echo "当前 Ubuntu 版本未在本部署方案中验证，请先检查 Docker 官方支持情况。" >&2; exit 1 ;;
esac
if command -v docker >/dev/null 2>&1; then
    docker --version
    docker compose version
    echo "Docker 已存在，保留现有安装。"
    exit 0
fi
for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
        echo "发现已有容器组件 $package，请人工核对后处理，脚本不会卸载。" >&2
        exit 1
    fi
done
apt-get update
apt-get install -y ca-certificates curl
install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg --output /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
arch=$(dpkg --print-architecture)
codename=${UBUNTU_CODENAME:-$VERSION_CODENAME}
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$arch" "$codename" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version
docker compose version
