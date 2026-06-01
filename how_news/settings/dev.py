import environ

from .base import *

env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG = True

SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-)h3lyl+2^f9#7d$enffr-+^-@69t518436l9^tj@(t%yd0il^!",
)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


try:
    from .local import *
except ImportError:
    pass
