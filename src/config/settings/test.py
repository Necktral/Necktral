from .base import *  # noqa

# Tests: deterministas y rápidos
DEBUG = False

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
