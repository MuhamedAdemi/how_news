FROM python:3.12-slim-bookworm

RUN useradd wagtail

EXPOSE 8000

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DJANGO_SETTINGS_MODULE=how_news.settings.production

# System packages for Pillow + psycopg2
RUN apt-get update --yes --quiet && apt-get install --yes --quiet --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libwebp-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

WORKDIR /app
RUN chown wagtail:wagtail /app

COPY --chown=wagtail:wagtail . .

USER wagtail

# Collect static files at build time (dummy key — never used at runtime)
RUN SECRET_KEY=collectstatic-build-placeholder python manage.py collectstatic --noinput --clear

# Migrate + start Gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn how_news.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 120"]
