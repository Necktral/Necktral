from __future__ import annotations

import os

import pytest
from django.conf import settings
from django.core.cache import caches

collect_ignore = ["src/tests/test_auth_throttling.py"]


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        default_cache = settings.CACHES.get("default", {})
        settings.CACHES = {
            **settings.CACHES,
            "default": {
                **default_cache,
                "KEY_PREFIX": f"throttle:{worker}",
            },
        }
        try:
            caches._caches = {}
        except Exception:
            pass

    cache = caches["default"]
    try:
        cache.clear()
    except Exception:
        pass
    yield
    try:
        cache.clear()
    except Exception:
        pass
