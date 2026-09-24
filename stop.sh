#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ -f config.env ] || exit 0
docker compose --env-file config.env down
