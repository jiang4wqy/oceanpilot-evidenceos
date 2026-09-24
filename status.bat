@echo off
cd /d "%~dp0"
if not exist config.env (echo Not initialized. Run start.bat. & exit /b 0)
docker compose --env-file config.env ps
