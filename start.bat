@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>nul || (echo Docker not found. Install and start Docker Desktop. & exit /b 1)
if not exist config.env (
  for /f %%P in ('powershell -NoProfile -Command "([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))"') do set "DBPASS=%%P"
  powershell -NoProfile -Command "(Get-Content -Raw 'config.env.example').Replace('__POSTGRES_PASSWORD__',$env:DBPASS) | Set-Content -NoNewline -Encoding utf8 'config.env'"
  echo Created local config.env.
)
docker compose --env-file config.env up --build -d
if errorlevel 1 exit /b 1
call :waithealthy
if errorlevel 1 exit /b 1
set "PORT=8000"
for /f "tokens=1,* delims==" %%A in ('findstr /b "OCEANPILOT_HOST_PORT=" config.env') do set "PORT=%%B"
echo OceanPilot: http://localhost:%PORT%/v2/login
echo Run show-accounts.bat after startup to view demo credentials.
exit /b 0

:waithealthy
for /f %%I in ('docker compose --env-file config.env ps -q oceanpilot') do set "CONTAINER=%%I"
for /l %%N in (1,1,90) do (
  for /f %%H in ('docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" %CONTAINER% 2^>nul') do set "HEALTH=%%H"
  call if "%%HEALTH%%"=="healthy" exit /b 0
  call if "%%HEALTH%%"=="unhealthy" exit /b 1
  timeout /t 1 /nobreak >nul
)
echo Startup timed out. Run status.bat for details.
exit /b 1
