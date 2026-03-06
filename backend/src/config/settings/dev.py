from .base import *  # noqa

DEBUG = True

# Dev: mantener compat legacy/global durante transición RBAC
RBAC_INCLUDE_GLOBAL_USERROLES = True

from datetime import timedelta

# Dev: tolerante (evita lockouts molestos en desarrollo)
AXES_FAILURE_LIMIT = 15
AXES_COOLOFF_TIME = timedelta(minutes=5)

# Dev: bootstrap sin token para evitar friccion en entorno local
INITIAL_SETUP_REQUIRE_TOKEN = False
