#!/bin/sh
# Update the Docker Compose service with backup, health check, and rollback.

set -eu

check_only=0
if [ "${1:-}" = "--check" ]; then
    check_only=1
elif [ "$#" -ne 0 ]; then
    echo "usage: $0 [--check]" >&2
    exit 2
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

if [ ! -f .env ]; then
    echo "missing $project_dir/.env" >&2
    exit 1
fi
command -v docker >/dev/null 2>&1 || {
    echo "docker is required" >&2
    exit 1
}
command -v curl >/dev/null 2>&1 || {
    echo "curl is required" >&2
    exit 1
}
docker compose version >/dev/null
docker compose config -q

if [ "$check_only" -eq 1 ]; then
    echo "server update prerequisites: OK"
    exit 0
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_host="$project_dir/backups/$stamp"
previous_image=$(docker compose images -q oceanpilot 2>/dev/null | head -n 1 || true)
rollback_tag="oceanpilot-rollback:$stamp"

if [ -n "$previous_image" ]; then
    docker image tag "$previous_image" "$rollback_tag"
fi

if docker compose ps --status running --services | grep -qx oceanpilot; then
    docker compose exec -T oceanpilot python - "$stamp" <<'PY'
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

stamp = sys.argv[1]
root = Path("/app/work")
destination = root / "backups" / stamp
destination.mkdir(parents=True, exist_ok=False)
manifest = []
for source in sorted(root.glob("*.db")):
    target = destination / source.name
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)
        integrity = target_db.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"backup integrity check failed: {source.name}")
    manifest.append(
        {
            "file": source.name,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "size": target.stat().st_size,
        }
    )
(destination / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY
    mkdir -p "$backup_host"
    docker compose cp "oceanpilot:/app/work/backups/$stamp/." "$backup_host"
    chmod -R go-rwx "$backup_host"
    echo "database backup: $backup_host"
else
    echo "service is not running; no live database backup was created"
fi

docker compose build oceanpilot
docker compose up -d --force-recreate oceanpilot

health_url=${OCEANPILOT_HEALTH_URL:-http://127.0.0.1:8000/health}
healthy=0
attempt=1
while [ "$attempt" -le 30 ]; do
    if curl --fail --silent --show-error --max-time 5 "$health_url" >/dev/null 2>&1; then
        healthy=1
        break
    fi
    sleep 2
    attempt=$((attempt + 1))
done

if [ "$healthy" -eq 1 ]; then
    echo "deployment healthy: $health_url"
    exit 0
fi

echo "deployment health check failed: $health_url" >&2
docker compose logs --tail 100 oceanpilot >&2 || true
if [ -n "$previous_image" ]; then
    docker image tag "$rollback_tag" oceanpilot:local
    docker compose up -d --no-build --force-recreate oceanpilot
    echo "previous image restored; verify service health manually" >&2
else
    echo "no previous image was available for rollback" >&2
fi
exit 1
