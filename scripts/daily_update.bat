@echo off
:: HoW Voices — Perditesim ditor automatik
:: Vendos ne Task Scheduler te ekzekutohet cdo dite ne ora 06:00

cd /d "C:\Users\MyPC\Desktop\how_news"
call venv\Scripts\activate.bat

echo [%date% %time%] Duke filluar perditesimin ditor...

python manage.py fetch_feeds --limit 30
python manage.py translate_news --limit 50
python manage.py fetch_gov --ai --limit 10
python manage.py fetch_mls --limit 20
python manage.py fetch_agriculture --limit 15
python manage.py fetch_employment
python manage.py fetch_business
python manage.py fetch_environment
python manage.py fetch_education
python manage.py expire_gov_items

echo [%date% %time%] Perditesimi perfundoi.
