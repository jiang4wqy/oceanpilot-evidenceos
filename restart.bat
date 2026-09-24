@echo off
cd /d "%~dp0"
if not exist config.env (echo Run start.bat first. & exit /b 1)
docker compose --env-file config.env up --build -d --force-recreate
if errorlevel 1 exit /b 1
for /f %%I in ('docker compose --env-file config.env ps -q oceanpilot') do set "CONTAINER=%%I"
for /l %%N in (1,1,90) do (
  for /f %%H in ('docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" %CONTAINER% 2^>nul') do set "HEALTH=%%H"
  call if "%%HEALTH%%"=="healthy" (echo OceanPilot restarted. & exit /b 0)
  call if "%%HEALTH%%"=="unhealthy" exit /b 1
  timeout /t 1 /nobreak >nul
)
echo Restart timed out. Run status.bat for details.
exit /b 1
