@echo off
cd /d "%~dp0"
if not exist config.env exit /b 0
docker compose --env-file config.env down
