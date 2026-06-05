#!/bin/bash
# HoW Voices — Perditesim ditor automatik (Linux/Server)
# Shto ne cron: 0 6 * * * /path/to/how_voices/scripts/daily_update.sh >> /var/log/how_voices.log 2>&1

cd "$(dirname "$0")/.."
source venv/bin/activate

echo "[$(date)] Duke filluar perditesimin ditor..."

python manage.py fetch_feeds --limit 30
python manage.py fetch_gov --ai --limit 10
python manage.py fetch_mls --limit 20
python manage.py fetch_agriculture --limit 15
python manage.py expire_gov_items

echo "[$(date)] Perditesimi perfundoi."
