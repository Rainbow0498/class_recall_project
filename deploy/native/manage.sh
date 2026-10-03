#!/usr/bin/env bash
set -euo pipefail
if [[ "${EUID}" != 0 ]]; then
    echo "请通过 sudo bash deploy/native/manage.sh 命令 参数 运行。" >&2
    exit 1
fi
if [[ "$#" == 0 ]]; then
    echo "例如：sudo bash deploy/native/manage.sh backup_data" >&2
    exit 1
fi
# systemd reads the private configuration; never source it as shell code.
exec systemd-run --quiet --wait --collect --pty --service-type=exec \
    --uid=biology --gid=biology \
    --property=WorkingDirectory=/opt/biology-workspace \
    --property=EnvironmentFile=/etc/biology-workspace.env \
    --property=UMask=0077 \
    /bin/bash /opt/biology-workspace/deploy/native/run.sh "$@"
