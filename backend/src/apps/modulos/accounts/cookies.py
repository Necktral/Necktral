from __future__ import annotations

import secrets

from django.conf import settings


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _cookie_kwargs(*, httponly: bool, max_age: int) -> dict:
    return {
        "max_age": max_age,
        "httponly": httponly,
        "secure": getattr(settings, "AUTH_COOKIE_SECURE", False),
        "samesite": getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax"),
        "domain": getattr(settings, "AUTH_COOKIE_DOMAIN", None),
        "path": getattr(settings, "AUTH_COOKIE_PATH", "/"),
    }


def set_auth_cookies(response, *, access: str, refresh: str, csrf: str | None = None) -> str:
    csrf = csrf or issue_csrf_token()

    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS_NAME,
        access,
        **_cookie_kwargs(httponly=True, max_age=int(settings.AUTH_COOKIE_ACCESS_MAX_AGE)),
    )
    response.set_cookie(
        settings.AUTH_COOKIE_REFRESH_NAME,
        refresh,
        **_cookie_kwargs(httponly=True, max_age=int(settings.AUTH_COOKIE_REFRESH_MAX_AGE)),
    )
    response.set_cookie(
        settings.AUTH_COOKIE_CSRF_NAME,
        csrf,
        **_cookie_kwargs(httponly=False, max_age=int(settings.AUTH_COOKIE_CSRF_MAX_AGE)),
    )
    return csrf


def clear_auth_cookies(response) -> None:
    for name in (
        settings.AUTH_COOKIE_ACCESS_NAME,
        settings.AUTH_COOKIE_REFRESH_NAME,
        settings.AUTH_COOKIE_CSRF_NAME,
    ):
        response.delete_cookie(
            name,
            path=getattr(settings, "AUTH_COOKIE_PATH", "/"),
            domain=getattr(settings, "AUTH_COOKIE_DOMAIN", None),
        )
