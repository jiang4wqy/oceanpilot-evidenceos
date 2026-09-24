#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ -f config.env ] || { echo "请先运行 ./start.sh" >&2; exit 1; }
docker compose --env-file config.env up --build -d --force-recreate
container_id=$(docker compose --env-file config.env ps -q oceanpilot)
attempt=0
while [ "$attempt" -lt 90 ]; do
  health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)
  [ "$health" = "healthy" ] && { echo "OceanPilot 已重启。"; exit 0; }
  [ "$health" = "unhealthy" ] && { docker compose --env-file config.env logs --tail=80 oceanpilot; exit 1; }
  attempt=$((attempt + 1))
  sleep 1
done
echo "重启超时，请运行 ./status.sh 查看状态。" >&2
exit 1
