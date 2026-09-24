#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ -f config.env ] || { echo "尚未初始化；请运行 ./start.sh"; exit 0; }
docker compose --env-file config.env ps
