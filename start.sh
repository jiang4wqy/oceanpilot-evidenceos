#!/bin/sh
set -eu
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 Docker。请先安装并启动 Docker Desktop。" >&2
  exit 1
fi

if [ ! -f config.env ]; then
  password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
  sed "s/__POSTGRES_PASSWORD__/$password/g" config.env.example > config.env
  chmod 600 config.env
  echo "已创建本机配置 config.env。"
fi

docker compose --env-file config.env up --build -d
container_id=$(docker compose --env-file config.env ps -q oceanpilot)
attempt=0
while [ "$attempt" -lt 90 ]; do
  health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)
  [ "$health" = "healthy" ] && break
  [ "$health" = "unhealthy" ] && { docker compose --env-file config.env logs --tail=80 oceanpilot; exit 1; }
  attempt=$((attempt + 1))
  sleep 1
done
[ "${health:-}" = "healthy" ] || { echo "启动超时，请运行 ./status.sh 查看状态。" >&2; exit 1; }
port=$(sed -n 's/^OCEANPILOT_HOST_PORT=//p' config.env)
echo "OceanPilot 已启动：http://localhost:${port:-8000}/v2/login"
echo "首次启动后，账号密码可通过 ./show-accounts.sh 查看。"
