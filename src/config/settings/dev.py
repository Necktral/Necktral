
from .base import *  # noqa

DEBUG = True

from datetime import timedelta

# Dev: tolerante (evita lockouts molestos en desarrollo)
AXES_FAILURE_LIMIT = 15
AXES_COOLOFF_TIME = timedelta(minutes=5)
