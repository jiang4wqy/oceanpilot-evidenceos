#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ -f config.env ] || { echo "请先运行 ./start.sh" >&2; exit 1; }
docker compose --env-file config.env exec -T oceanpilot \
  sh -c 'test -f /app/data/demo-accounts.json && cat /app/data/demo-accounts.json'
