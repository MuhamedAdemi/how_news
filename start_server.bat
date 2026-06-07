@echo off
title HoW Voices — Server
cd /d "%~dp0"

echo.
echo ================================================
echo   HoW Voices Production Server
echo ================================================
echo.

REM Aktivizo virtual environment
call venv\Scripts\activate.bat

REM Vendos settings
set DJANGO_SETTINGS_MODULE=how_news.settings.production

REM Collectstatic
echo [1/3] Duke mbledhur static files...
python manage.py collectstatic --noinput --clear 2>&1

REM Migrimi
echo [2/3] Duke kontrolluar migrimet...
python manage.py migrate --noinput 2>&1

REM Niso serverin me waitress
echo [3/3] Duke nisur serverin ne port 8001...
echo.
echo   URL lokale:  http://localhost:8001
echo   Cloudflare:  shiko dritaren tjeter
echo.
python -m waitress --port=8001 --threads=4 how_news.wsgi:application

pause
