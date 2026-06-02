@echo off
:: Ekzekuto fetch_feeds automatikisht
:: Shto ne Windows Task Scheduler per te marre lajme cdo ore
cd /d "%~dp0"
call venv\Scripts\activate.bat
python manage.py fetch_feeds --limit 20
