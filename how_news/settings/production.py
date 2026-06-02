import environ

from .base import *

env = environ.Env()
import os
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG = False

SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{os.path.join(BASE_DIR, 'db.sqlite3')}")
}

try:
    from .local import *
except ImportError:
    pass
