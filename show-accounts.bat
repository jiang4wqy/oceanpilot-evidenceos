@echo off
cd /d "%~dp0"
if not exist config.env (echo Run start.bat first. & exit /b 1)
docker compose --env-file config.env exec -T oceanpilot sh -c "test -f /app/data/demo-accounts.json ^&^& cat /app/data/demo-accounts.json"
