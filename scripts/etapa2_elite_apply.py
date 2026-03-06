from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"No se encontro patron para {label}")
    return text.replace(old, new, 1)


def insert_after(text: str, anchor: str, addition: str, *, label: str) -> str:
    if addition in text:
        return text
    if anchor not in text:
        raise RuntimeError(f"No se encontro anchor para {label}")
    return text.replace(anchor, anchor + addition, 1)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def update_audit_contracts() -> None:
    path = REPO_ROOT / "backend/src/apps/audit/contracts.py"
    text = path.read_text(encoding="utf-8")
    old = "    \"TOKEN_INVALID\",\n    \"TOKEN_EXPIRED\",\n"
    new = (
        "    \"TOKEN_INVALID\",\n"
        "    \"TOKEN_EXPIRED\",\n"
        "    \"TOKEN_MISMATCH\",\n"
        "    \"INVALID_OLD_PASSWORD\",\n"
        "    \"CSRF_FAILED\",\n"
    )
    text = replace_once(text, old, new, label="audit.contracts reason_codes")
    path.write_text(text, encoding="utf-8")


def add_audit_redaction() -> None:
    path = REPO_ROOT / "backend/src/apps/audit/redaction.py"
    if path.exists():
        return
    content = '''from __future__ import annotations

import hashlib
import json
from typing import Any

REDACTED = "***REDACTED***"

_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "refresh",
    "access",
    "authorization",
    "cookie",
    "set-cookie",
    "api_key",
    "apikey",
    "private_key",
    "hmac",
)

_MAX_DEPTH = 8
_MAX_JSON_BYTES = 24000


def _is_sensitive_key(key: str) -> bool:
    k = key.lower().strip()
    return any(s in k for s in _SENSITIVE_SUBSTRINGS)


def _redact(obj: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "<max_depth_reached>"

    if obj is None:
        return None
    if isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_redact(x, depth=depth + 1) for x in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            try:
                ks = str(k)
            except Exception:
                ks = "<non_string_key>"
            if _is_sensitive_key(ks):
                out[ks] = REDACTED
            else:
                out[ks] = _redact(v, depth=depth + 1)
        return out

    return str(obj)


def _truncate_if_needed(obj: Any) -> Any:
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        s = json.dumps(str(obj), ensure_ascii=False)

    b = s.encode("utf-8", errors="replace")
    if len(b) <= _MAX_JSON_BYTES:
        return obj

    h = hashlib.sha256(b).hexdigest()
    return {
        "_truncated": True,
        "_sha256": h,
        "_bytes": len(b),
    }


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    return _truncate_if_needed(_redact(metadata))


def sanitize_snapshot(snapshot: Any) -> Any:
    if snapshot is None:
        return None
    return _truncate_if_needed(_redact(snapshot))
'''
    write_file(path, content)


def update_audit_writer() -> None:
    path = REPO_ROOT / "backend/src/apps/audit/writer.py"
    text = path.read_text(encoding="utf-8")
    import_anchor = "from .models import AuditChainHeadV2, AuditEvent\n"
    import_add = "from .redaction import sanitize_metadata, sanitize_snapshot\n"
    if import_add not in text:
        text = insert_after(text, import_anchor, import_add, label="audit.writer import redaction")

    old_snap = "    before_snapshot = before_snapshot or {}\n    after_snapshot = after_snapshot or {}\n"
    new_snap = (
        "    before_snapshot = sanitize_snapshot(before_snapshot or {})\n"
        "    after_snapshot = sanitize_snapshot(after_snapshot or {})\n"
        "    metadata = sanitize_metadata(metadata)\n"
    )
    text = replace_once(text, old_snap, new_snap, label="audit.writer sanitize")
    path.write_text(text, encoding="utf-8")


def update_audit_middleware() -> None:
    path = REPO_ROOT / "backend/src/apps/audit/middleware.py"
    text = path.read_text(encoding="utf-8")
    import_anchor = "from django.utils.deprecation import MiddlewareMixin\n\n"
    import_add = "from apps.audit.contracts import validate_reason_code\n"
    if import_add not in text:
        text = insert_after(text, import_anchor, import_add, label="audit.middleware import validate_reason_code")

    old_block = (
        "        # Mapping contractual (códigos estándar para consumo externo)\n"
        "        if status_code == 401:\n"
        "            reason_code = \"AUTH_UNAUTHENTICATED\"\n"
        "        elif status_code == 403:\n"
        "            if getattr(request, \"required_permission\", \"\"):\n"
        "                reason_code = \"RBAC_FORBIDDEN\"\n"
        "            elif getattr(request, \"required_scope\", None):\n"
        "                reason_code = \"SCOPE_FORBIDDEN\"\n"
        "            else:\n"
        "                reason_code = \"RBAC_FORBIDDEN\"\n"
        "        else:\n"
        "            reason_code = \"RATE_LIMITED\"\n"
    )
    new_block = (
        "        reason_code = None\n"
        "        override = getattr(request, \"audit_reason_code_override\", None)\n"
        "        if override:\n"
        "            try:\n"
        "                validate_reason_code(str(override))\n"
        "                reason_code = str(override)\n"
        "            except Exception:\n"
        "                reason_code = None\n\n"
        "        # Mapping contractual (códigos estándar para consumo externo)\n"
        "        if reason_code is None:\n"
        "            if status_code == 401:\n"
        "                reason_code = \"AUTH_UNAUTHENTICATED\"\n"
        "            elif status_code == 403:\n"
        "                if getattr(request, \"required_permission\", \"\"):\n"
        "                    reason_code = \"RBAC_FORBIDDEN\"\n"
        "                elif getattr(request, \"required_scope\", None):\n"
        "                    reason_code = \"SCOPE_FORBIDDEN\"\n"
        "                else:\n"
        "                    reason_code = \"RBAC_FORBIDDEN\"\n"
        "            else:\n"
        "                reason_code = \"RATE_LIMITED\"\n"
    )
    text = replace_once(text, old_block, new_block, label="audit.middleware override")
    path.write_text(text, encoding="utf-8")


def update_error_envelope() -> None:
    path = REPO_ROOT / "backend/src/config/error_envelope.py"
    text = path.read_text(encoding="utf-8")
    old = "def error_code_for(*, status_code: int, exc: Exception | None = None, request=None) -> str:\n    sc = int(status_code)\n"
    new = (
        "def error_code_for(*, status_code: int, exc: Exception | None = None, request=None) -> str:\n"
        "    if request is not None:\n"
        "        override = getattr(request, \"error_code_override\", None)\n"
        "        if override:\n"
        "            return str(override)\n"
        "    sc = int(status_code)\n"
    )
    text = replace_once(text, old, new, label="error_envelope override")
    path.write_text(text, encoding="utf-8")


def add_cookie_csrf_middleware() -> None:
    path = REPO_ROOT / "backend/src/config/middleware/cookie_csrf.py"
    if path.exists():
        return
    content = '''from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class CookieJwtCsrfMiddleware:
    """CSRF para modo cookie en JWT.

    Si AUTH_TOKEN_TRANSPORT=cookie, exige X-CSRF-Token == cookie CSRF
    para metodos mutables. Esto previene CSRF en modo cookies.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "AUTH_TOKEN_TRANSPORT", "header") != "cookie":
            return self.get_response(request)

        if request.method in SAFE_METHODS:
            return self.get_response(request)

        # Login se permite sin CSRF (todavia no hay cookie CSRF)
        if request.path.startswith("/api/auth/login"):
            return self.get_response(request)

        access = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS_NAME)
        refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)
        if not access and not refresh:
            return self.get_response(request)

        csrf_cookie = request.COOKIES.get(settings.AUTH_COOKIE_CSRF_NAME)
        csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRFToken")

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            request.error_code_override = "AUTH_CSRF_FAILED"
            request.audit_reason_code_override = "CSRF_FAILED"
            return JsonResponse({"detail": "CSRF token missing or invalid."}, status=403)

        return self.get_response(request)
'''
    write_file(path, content)


def add_accounts_cookies() -> None:
    path = REPO_ROOT / "backend/src/apps/accounts/cookies.py"
    if path.exists():
        return
    content = '''from __future__ import annotations

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
'''
    write_file(path, content)


def update_authentication_cookie() -> None:
    path = REPO_ROOT / "backend/src/apps/iam/authentication.py"
    text = path.read_text(encoding="utf-8")
    if "from django.conf import settings" not in text:
        text = text.replace(
            "from __future__ import annotations\n\n",
            "from __future__ import annotations\n\nfrom django.conf import settings\n",
            1,
        )

    old = (
        "        auth_result = super().authenticate(request)\n"
        "        if auth_result is None:\n"
        "            return None\n\n"
    )
    new = (
        "        auth_result = super().authenticate(request)\n"
        "        if auth_result is None:\n"
        "            if getattr(settings, \"AUTH_TOKEN_TRANSPORT\", \"header\") != \"cookie\":\n"
        "                return None\n"
        "            cookie_name = getattr(settings, \"AUTH_COOKIE_ACCESS_NAME\", \"nt_access\")\n"
        "            raw = request.COOKIES.get(cookie_name)\n"
        "            if not raw:\n"
        "                return None\n"
        "            validated_token = self.get_validated_token(raw)\n"
        "            user = self.get_user(validated_token)\n"
        "            auth_result = (user, validated_token)\n\n"
    )
    text = replace_once(text, old, new, label="iam.authentication cookie")
    path.write_text(text, encoding="utf-8")


def update_accounts_views() -> None:
    path = REPO_ROOT / "backend/src/apps/accounts/views.py"
    text = path.read_text(encoding="utf-8")

    if "from django.conf import settings" not in text:
        text = text.replace(
            "from django.http import QueryDict\n",
            "from django.conf import settings\nfrom django.http import QueryDict\n",
            1,
        )
    if "TokenRefreshSerializer" not in text:
        text = text.replace(
            "from rest_framework_simplejwt.tokens import RefreshToken\n",
            "from rest_framework_simplejwt.tokens import RefreshToken\nfrom rest_framework_simplejwt.serializers import TokenRefreshSerializer\n",
            1,
        )
    if "from .cookies import" not in text:
        text = text.replace(
            "from .serializers import (\n",
            "from .cookies import clear_auth_cookies, set_auth_cookies\nfrom .serializers import (\n",
            1,
        )

    old_login_return = (
        "        return Response(\n"
        "            {\n"
        "                \"access\": str(refresh.access_token),\n"
        "                \"refresh\": str(refresh),\n"
        "            },\n"
        "            status=status.HTTP_200_OK,\n"
        "        )\n"
    )
    if old_login_return in text:
        new_login_return = (
            "        if getattr(settings, \"AUTH_TOKEN_TRANSPORT\", \"header\") == \"cookie\":\n"
            "            response = Response({\"ok\": True}, status=status.HTTP_200_OK)\n"
            "            set_auth_cookies(response, access=str(refresh.access_token), refresh=str(refresh))\n"
            "            return response\n\n"
            "        return Response(\n"
            "            {\n"
            "                \"access\": str(refresh.access_token),\n"
            "                \"refresh\": str(refresh),\n"
            "            },\n"
            "            status=status.HTTP_200_OK,\n"
            "        )\n"
        )
        text = text.replace(old_login_return, new_login_return, 1)

    text = text.replace("throttle_scope = \"auth_sensitive\"", "throttle_scope = \"auth_refresh\"", 1)

    marker = "    def post(self, request, *args, **kwargs):\n"
    if marker in text and "refresh_cookie" not in text:
        insert = (
            "    def post(self, request, *args, **kwargs):\n"
            "        if getattr(settings, \"AUTH_TOKEN_TRANSPORT\", \"header\") == \"cookie\":\n"
            "            refresh_cookie = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)\n"
            "            if not refresh_cookie:\n"
            "                write_event(\n"
            "                    request=request,\n"
            "                    event_type=\"AUTH_TOKEN_REFRESH_FAILURE\",\n"
            "                    reason_code=\"TOKEN_INVALID\",\n"
            "                    actor_user=None,\n"
            "                    subject_type=\"SESSION\",\n"
            "                    subject_id=\"\",\n"
            "                    metadata={\"stage\": \"refresh\", \"detail\": \"missing_refresh_cookie\"},\n"
            "                )\n"
            "                return Response({\"detail\": \"refresh es requerido.\"}, status=status.HTTP_401_UNAUTHORIZED)\n\n"
            "            serializer = TokenRefreshSerializer(data={\"refresh\": refresh_cookie})\n"
            "            if not serializer.is_valid():\n"
            "                write_event(\n"
            "                    request=request,\n"
            "                    event_type=\"AUTH_TOKEN_REFRESH_FAILURE\",\n"
            "                    reason_code=\"TOKEN_INVALID\",\n"
            "                    actor_user=None,\n"
            "                    subject_type=\"SESSION\",\n"
            "                    subject_id=\"\",\n"
            "                    metadata={\"stage\": \"refresh\", \"detail\": \"invalid_refresh_cookie\"},\n"
            "                )\n"
            "                return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)\n\n"
            "            access = serializer.validated_data[\"access\"]\n"
            "            new_refresh = serializer.validated_data.get(\"refresh\") or refresh_cookie\n"
            "            response = Response({\"ok\": True}, status=status.HTTP_200_OK)\n"
            "            set_auth_cookies(response, access=access, refresh=new_refresh)\n"
            "            write_event(\n"
            "                request=request,\n"
            "                event_type=\"AUTH_TOKEN_REFRESH\",\n"
            "                reason_code=\"\",\n"
            "                actor_user=None,\n"
            "                subject_type=\"SESSION\",\n"
            "                subject_id=\"\",\n"
            "                metadata={\"stage\": \"refresh\"},\n"
            "            )\n"
            "            return response\n\n"
        )
        text = text.replace(marker, insert, 1)

    text = text.replace("throttle_scope = \"auth_sensitive\"", "throttle_scope = \"auth_logout\"", 1)

    old_logout = "        refresh = request.data.get(\"refresh\")\n"
    new_logout = (
        "        refresh = request.data.get(\"refresh\")\n"
        "        if not refresh and getattr(settings, \"AUTH_TOKEN_TRANSPORT\", \"header\") == \"cookie\":\n"
        "            refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)\n"
    )
    text = replace_once(text, old_logout, new_logout, label="logout cookie fallback")

    old_logout_return = "        return Response(status=status.HTTP_204_NO_CONTENT)\n"
    new_logout_return = (
        "        response = Response(status=status.HTTP_204_NO_CONTENT)\n"
        "        if getattr(settings, \"AUTH_TOKEN_TRANSPORT\", \"header\") == \"cookie\":\n"
        "            clear_auth_cookies(response)\n"
        "        return response\n"
    )
    text = replace_once(text, old_logout_return, new_logout_return, label="logout cookie clear")

    path.write_text(text, encoding="utf-8")


def update_settings_base() -> None:
    path = REPO_ROOT / "backend/src/config/settings/base.py"
    text = path.read_text(encoding="utf-8")

    env_block = (
        "env = environ.Env(\n"
        "    DJANGO_DEBUG=(bool, False),\n"
        "    DJANGO_SECRET_KEY=(str, \"unsafe-dev-secret\"),\n"
        "    DJANGO_ALLOWED_HOSTS=(list, [\"localhost\", \"127.0.0.1\"]),\n"
        "    DJANGO_CORS_ALLOWED_ORIGINS=(list, [\"http://localhost:3000\"]),\n"
        "    DJANGO_CSRF_TRUSTED_ORIGINS=(list, [\"http://localhost:3000\"]),\n"
        ")\n"
    )
    env_add = (
        "env = environ.Env(\n"
        "    DJANGO_DEBUG=(bool, False),\n"
        "    DJANGO_SECRET_KEY=(str, \"unsafe-dev-secret\"),\n"
        "    DJANGO_ALLOWED_HOSTS=(list, [\"localhost\", \"127.0.0.1\"]),\n"
        "    DJANGO_CORS_ALLOWED_ORIGINS=(list, [\"http://localhost:3000\"]),\n"
        "    DJANGO_CSRF_TRUSTED_ORIGINS=(list, [\"http://localhost:3000\"]),\n"
        "    AUTH_TOKEN_TRANSPORT=(str, \"header\"),\n"
        "    AUTH_COOKIE_ACCESS_NAME=(str, \"nt_access\"),\n"
        "    AUTH_COOKIE_REFRESH_NAME=(str, \"nt_refresh\"),\n"
        "    AUTH_COOKIE_CSRF_NAME=(str, \"nt_csrf\"),\n"
        "    AUTH_COOKIE_SECURE=(bool, False),\n"
        "    AUTH_COOKIE_SAMESITE=(str, \"Lax\"),\n"
        "    AUTH_COOKIE_DOMAIN=(str, \"\"),\n"
        "    AUTH_COOKIE_PATH=(str, \"/\"),\n"
        "    DRF_THROTTLE_ANON=(str, \"60/min\"),\n"
        "    DRF_THROTTLE_USER=(str, \"600/min\"),\n"
        "    DRF_THROTTLE_AUTH_LOGIN=(str, \"10/min\"),\n"
        "    DRF_THROTTLE_AUTH_REFRESH=(str, \"60/min\"),\n"
        "    DRF_THROTTLE_AUTH_LOGOUT=(str, \"60/min\"),\n"
        ")\n"
    )
    text = replace_once(text, env_block, env_add, label="settings.base env")

    text = replace_once(
        text,
        "    \"x-request-id\",\n]\n",
        "    \"x-request-id\",\n    \"x-csrf-token\",\n]\n",
        label="settings.base cors headers",
    )

    if "CORS_ALLOW_CREDENTIALS" not in text:
        text = insert_after(
            text,
            "CORS_EXPOSE_HEADERS = [\n    \"X-Request-Id\",\n]\n\n",
            "CORS_ALLOW_CREDENTIALS = env(\"AUTH_TOKEN_TRANSPORT\") == \"cookie\"\n\n",
            label="settings.base cors credentials",
        )

    text = replace_once(
        text,
        "    \"django.middleware.csrf.CsrfViewMiddleware\",\n",
        "    \"django.middleware.csrf.CsrfViewMiddleware\",\n    \"config.middleware.cookie_csrf.CookieJwtCsrfMiddleware\",\n",
        label="settings.base middleware csrf",
    )

    text = replace_once(
        text,
        "        \"auth_sensitive\": \"10/min\",\n",
        "        \"auth_sensitive\": \"10/min\",\n        \"auth_refresh\": env(\"DRF_THROTTLE_AUTH_REFRESH\"),\n        \"auth_logout\": env(\"DRF_THROTTLE_AUTH_LOGOUT\"),\n",
        label="settings.base throttle rates",
    )

    auth_block = (
        "AUTH_TOKEN_TRANSPORT = env(\"AUTH_TOKEN_TRANSPORT\")\n"
        "AUTH_COOKIE_ACCESS_NAME = env(\"AUTH_COOKIE_ACCESS_NAME\")\n"
        "AUTH_COOKIE_REFRESH_NAME = env(\"AUTH_COOKIE_REFRESH_NAME\")\n"
        "AUTH_COOKIE_CSRF_NAME = env(\"AUTH_COOKIE_CSRF_NAME\")\n"
        "AUTH_COOKIE_SECURE = env.bool(\"AUTH_COOKIE_SECURE\", default=not DEBUG)\n"
        "AUTH_COOKIE_SAMESITE = env(\"AUTH_COOKIE_SAMESITE\")\n"
        "AUTH_COOKIE_DOMAIN = env(\"AUTH_COOKIE_DOMAIN\") or None\n"
        "AUTH_COOKIE_PATH = env(\"AUTH_COOKIE_PATH\")\n\n"
        "AUTH_COOKIE_ACCESS_MAX_AGE = int(SIMPLE_JWT[\"ACCESS_TOKEN_LIFETIME\"].total_seconds())\n"
        "AUTH_COOKIE_REFRESH_MAX_AGE = int(SIMPLE_JWT[\"REFRESH_TOKEN_LIFETIME\"].total_seconds())\n"
        "AUTH_COOKIE_CSRF_MAX_AGE = AUTH_COOKIE_REFRESH_MAX_AGE\n"
    )
    if auth_block not in text:
        text = text + "\n" + auth_block

    path.write_text(text, encoding="utf-8")


def update_settings_prod() -> None:
    path = REPO_ROOT / "backend/src/config/settings/prod.py"
    text = path.read_text(encoding="utf-8")
    if "SECURE_PROXY_SSL_HEADER" in text:
        return
    append = '''
# Hardening (proxy / TLS / cookies)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=15552000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

AUTH_COOKIE_SECURE = True
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="Lax")

SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
'''
    text = text + "\n" + append
    path.write_text(text, encoding="utf-8")


def update_nginx_default() -> None:
    path = REPO_ROOT / "docker/nginx/default.conf"
    content = '''# Incluido dentro del contexto http (conf.d). Aqui si se puede declarar limit_req_zone.
limit_req_zone $binary_remote_addr zone=api_per_ip:10m rate=20r/s;
limit_req_zone $binary_remote_addr zone=auth_per_ip:10m rate=10r/m;

map $http_x_forwarded_proto $proxy_x_forwarded_proto {
    default $http_x_forwarded_proto;
    ""      $scheme;
}

server {
    listen 80;
    server_name _;
    server_tokens off;

    root /usr/share/nginx/html;
    client_max_body_size 10m;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "same-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self';" always;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ^~ /api/auth/ {
        limit_req zone=auth_per_ip burst=20 nodelay;

        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $proxy_x_forwarded_proto;
        proxy_read_timeout 60s;
    }

    location ^~ /api/ {
        limit_req zone=api_per_ip burst=80 nodelay;

        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $proxy_x_forwarded_proto;
        proxy_read_timeout 60s;
    }
}
'''
    path.write_text(content, encoding="utf-8")


def update_frontend_axios() -> None:
    path = REPO_ROOT / "frontend/src/boot/axios.ts"
    text = path.read_text(encoding="utf-8")
    if "VITE_AUTH_TRANSPORT" not in text:
        insert = (
            "const AUTH_TRANSPORT = import.meta.env.VITE_AUTH_TRANSPORT || 'header';\n"
            "const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME || 'nt_csrf';\n\n"
            "function readCookie(name: string): string | null {\n"
            "  const m = document.cookie.match(new RegExp('(^|;\\\\s*)' + name + '=([^;]*)'));\n"
            "  return m ? decodeURIComponent(m[2]) : null;\n"
            "}\n\n"
        )
        text = insert_after(
            text,
            "  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api';\n",
            insert,
            label="frontend axios env",
        )

    text = text.replace(
        "export const api = axios.create({\n  baseURL: API_BASE_URL,\n  timeout: 25_000,\n});\n\nexport const authApi = axios.create({\n  baseURL: API_BASE_URL,\n  timeout: 25_000,\n});\n",
        "export const api = axios.create({\n  baseURL: API_BASE_URL,\n  timeout: 25_000,\n  withCredentials: AUTH_TRANSPORT === 'cookie',\n});\n\nexport const authApi = axios.create({\n  baseURL: API_BASE_URL,\n  timeout: 25_000,\n  withCredentials: AUTH_TRANSPORT === 'cookie',\n});\n",
    )

    if "X-CSRF-Token" not in text:
        text = text.replace(
            "    // Auth header\n    if (auth.accessToken) {\n      config.headers = config.headers ?? {};\n      config.headers.Authorization = `Bearer ${auth.accessToken}`;\n    }\n",
            "    // Auth header\n    if (AUTH_TRANSPORT === 'header' && auth.accessToken) {\n      config.headers = config.headers ?? {};\n      config.headers.Authorization = `Bearer ${auth.accessToken}`;\n    }\n\n    if (AUTH_TRANSPORT === 'cookie') {\n      const csrf = readCookie(CSRF_COOKIE_NAME);\n      if (csrf) {\n        config.headers = config.headers ?? {};\n        config.headers['X-CSRF-Token'] = csrf;\n      }\n    }\n",
            1,
        )

    text = text.replace(
        "          original.headers = original.headers ?? {};\n          if (auth.accessToken) original.headers.Authorization = `Bearer ${auth.accessToken}`;\n",
        "          original.headers = original.headers ?? {};\n          if (AUTH_TRANSPORT === 'header' && auth.accessToken) {\n            original.headers.Authorization = `Bearer ${auth.accessToken}`;\n          }\n",
        1,
    )

    path.write_text(text, encoding="utf-8")


def update_frontend_storage() -> None:
    path = REPO_ROOT / "frontend/src/core/storage/auth.ts"
    text = path.read_text(encoding="utf-8")
    if "AUTH_TRANSPORT" not in text:
        text = text.replace(
            "export type StoredTokens = {\n",
            "const AUTH_TRANSPORT = import.meta.env.VITE_AUTH_TRANSPORT || 'header';\n\nexport type StoredTokens = {\n",
            1,
        )

    text = replace_once(
        text,
        "export function readTokens(): StoredTokens {\n  return {\n    access: localStorage.getItem(STORAGE_KEYS.AUTH_ACCESS),\n    refresh: localStorage.getItem(STORAGE_KEYS.AUTH_REFRESH),\n  };\n}\n",
        "export function readTokens(): StoredTokens {\n  if (AUTH_TRANSPORT === 'cookie') {\n    return { access: null, refresh: null };\n  }\n  return {\n    access: localStorage.getItem(STORAGE_KEYS.AUTH_ACCESS),\n    refresh: localStorage.getItem(STORAGE_KEYS.AUTH_REFRESH),\n  };\n}\n",
        label="frontend storage read",
    )

    text = replace_once(
        text,
        "export function writeTokens(tokens: { access: string; refresh: string }) {\n  localStorage.setItem(STORAGE_KEYS.AUTH_ACCESS, tokens.access);\n  localStorage.setItem(STORAGE_KEYS.AUTH_REFRESH, tokens.refresh);\n}\n",
        "export function writeTokens(tokens: { access: string; refresh: string }) {\n  if (AUTH_TRANSPORT === 'cookie') return;\n  localStorage.setItem(STORAGE_KEYS.AUTH_ACCESS, tokens.access);\n  localStorage.setItem(STORAGE_KEYS.AUTH_REFRESH, tokens.refresh);\n}\n",
        label="frontend storage write",
    )

    text = replace_once(
        text,
        "export function clearTokens() {\n  localStorage.removeItem(STORAGE_KEYS.AUTH_ACCESS);\n  localStorage.removeItem(STORAGE_KEYS.AUTH_REFRESH);\n}\n",
        "export function clearTokens() {\n  if (AUTH_TRANSPORT === 'cookie') return;\n  localStorage.removeItem(STORAGE_KEYS.AUTH_ACCESS);\n  localStorage.removeItem(STORAGE_KEYS.AUTH_REFRESH);\n}\n",
        label="frontend storage clear",
    )

    path.write_text(text, encoding="utf-8")


def update_frontend_auth_store() -> None:
    path = REPO_ROOT / "frontend/src/stores/auth.store.ts"
    text = path.read_text(encoding="utf-8")

    if "AUTH_TRANSPORT" not in text:
        text = text.replace(
            "type RefreshResponse = { access: string; refresh?: string };\n\n",
            "type RefreshResponse = { access: string; refresh?: string };\n\nconst AUTH_TRANSPORT = import.meta.env.VITE_AUTH_TRANSPORT || 'header';\n\n",
            1,
        )

    text = replace_once(
        text,
        "  getters: {\n    isAuthenticated: (s) => Boolean(s.accessToken && s.refreshToken),\n  },\n",
        "  getters: {\n    isAuthenticated: (s) => (AUTH_TRANSPORT === 'cookie' ? s.status === 'authenticated' : Boolean(s.accessToken && s.refreshToken)),\n  },\n",
        label="auth store getter",
    )

    text = replace_once(
        text,
        "    initFromStorage() {\n      if (this.hydrated) return;\n      const t = readTokens();\n      this.accessToken = t.access;\n      this.refreshToken = t.refresh;\n      this.status = this.isAuthenticated ? 'authenticated' : 'anonymous';\n      this.hydrated = true;\n    },\n",
        "    initFromStorage() {\n      if (this.hydrated) return;\n      if (AUTH_TRANSPORT === 'cookie') {\n        this.hydrated = true;\n        return;\n      }\n      const t = readTokens();\n      this.accessToken = t.access;\n      this.refreshToken = t.refresh;\n      this.status = this.isAuthenticated ? 'authenticated' : 'anonymous';\n      this.hydrated = true;\n    },\n",
        label="auth store init",
    )

    text = replace_once(
        text,
        "    async login(username: string, password: string) {\n      const { data } = await authApi.post<LoginResponse>('/auth/login/', { username, password });\n      this.accessToken = data.access;\n      this.refreshToken = data.refresh;\n      this.status = 'authenticated';\n      writeTokens({ access: data.access, refresh: data.refresh });\n\n      // Fetch user details immediately to check flags\n      await this.fetchMe();\n    },\n",
        "    async login(username: string, password: string) {\n      const { data } = await authApi.post<LoginResponse>('/auth/login/', { username, password });\n      if (AUTH_TRANSPORT === 'cookie') {\n        this.accessToken = null;\n        this.refreshToken = null;\n        this.status = 'authenticated';\n      } else {\n        this.accessToken = data.access;\n        this.refreshToken = data.refresh;\n        this.status = 'authenticated';\n        writeTokens({ access: data.access, refresh: data.refresh });\n      }\n\n      // Fetch user details immediately to check flags\n      await this.fetchMe();\n    },\n",
        label="auth store login",
    )

    text = replace_once(
        text,
        "    async refresh() {\n      const currentRefresh = this.refreshToken;\n      if (!currentRefresh) throw new Error('No refresh token available');\n\n      // lock: si ya hay refresh en progreso, esperar el mismo\n      if (this.refreshInFlight) return this.refreshInFlight;\n\n      this.status = 'refreshing';\n      this.refreshInFlight = (async () => {\n        try {\n          const { data } = await authApi.post<RefreshResponse>('/auth/refresh/', {\n            refresh: currentRefresh,\n          });\n\n          // backend puede rotar refresh: si viene uno nuevo, lo reemplazamos\n          const newAccess = data.access;\n          const newRefresh = data.refresh ?? currentRefresh;\n\n          this.accessToken = newAccess;\n          this.refreshToken = newRefresh;\n          this.status = 'authenticated';\n          writeTokens({ access: newAccess, refresh: newRefresh });\n        } finally {\n          this.refreshInFlight = null;\n        }\n      })();\n\n      return this.refreshInFlight;\n    },\n",
        "    async refresh() {\n      const currentRefresh = this.refreshToken;\n      if (AUTH_TRANSPORT === 'cookie') {\n        await authApi.post('/auth/refresh/', {});\n        this.status = 'authenticated';\n        return;\n      }\n      if (!currentRefresh) throw new Error('No refresh token available');\n\n      // lock: si ya hay refresh en progreso, esperar el mismo\n      if (this.refreshInFlight) return this.refreshInFlight;\n\n      this.status = 'refreshing';\n      this.refreshInFlight = (async () => {\n        try {\n          const { data } = await authApi.post<RefreshResponse>('/auth/refresh/', {\n            refresh: currentRefresh,\n          });\n\n          // backend puede rotar refresh: si viene uno nuevo, lo reemplazamos\n          const newAccess = data.access;\n          const newRefresh = data.refresh ?? currentRefresh;\n\n          this.accessToken = newAccess;\n          this.refreshToken = newRefresh;\n          this.status = 'authenticated';\n          writeTokens({ access: newAccess, refresh: newRefresh });\n        } finally {\n          this.refreshInFlight = null;\n        }\n      })();\n\n      return this.refreshInFlight;\n    },\n",
        label="auth store refresh",
    )

    text = replace_once(
        text,
        "    async logout() {\n      const refresh = this.refreshToken;\n      const access = this.accessToken;\n\n      // limpiar stores primero para cortar UI rápido\n      this.hardClearLocal();\n\n      // y luego intentar avisar al backend (si falla, no pasa nada)\n      if (refresh && access) {\n        try {\n          // Usamos authApi pero inyectamos el header manualmente\n          // (porque hardClearLocal ya borró el token del store)\n          await authApi.post(\n            '/auth/logout/',\n            { refresh },\n            { headers: { Authorization: `Bearer ${access}` } },\n          );\n        } catch {\n          // intencional: no bloqueamos el logout local\n        }\n      }\n    },\n",
        "    async logout() {\n      const refresh = this.refreshToken;\n      const access = this.accessToken;\n\n      // limpiar stores primero para cortar UI rapido\n      this.hardClearLocal();\n\n      if (AUTH_TRANSPORT === 'cookie') {\n        try {\n          await authApi.post('/auth/logout/', {});\n        } catch {\n          // intencional: no bloqueamos el logout local\n        }\n        return;\n      }\n\n      // y luego intentar avisar al backend (si falla, no pasa nada)\n      if (refresh && access) {\n        try {\n          // Usamos authApi pero inyectamos el header manualmente\n          // (porque hardClearLocal ya borro el token del store)\n          await authApi.post(\n            '/auth/logout/',\n            { refresh },\n            { headers: { Authorization: `Bearer ${access}` } },\n          );\n        } catch {\n          // intencional: no bloqueamos el logout local\n        }\n      }\n    },\n",
        label="auth store logout",
    )

    path.write_text(text, encoding="utf-8")


def main() -> None:
    update_audit_contracts()
    add_audit_redaction()
    update_audit_writer()
    update_audit_middleware()
    update_error_envelope()
    add_cookie_csrf_middleware()
    add_accounts_cookies()
    update_authentication_cookie()
    update_accounts_views()
    update_settings_base()
    update_settings_prod()
    update_nginx_default()
    update_frontend_axios()
    update_frontend_storage()
    update_frontend_auth_store()


if __name__ == "__main__":
    main()
