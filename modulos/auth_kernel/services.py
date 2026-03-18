import hashlib
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

import pyotp
from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import RefreshTokenSession, TwoFactorChallenge


def token_jti(token: RefreshToken) -> str:
    return str(token.get("jti", ""))


def token_expiry(token: RefreshToken):
    exp = token.get("exp", None)
    if exp is None:
        return None
    return datetime.fromtimestamp(int(exp), tz=dt_timezone.utc)


def persist_refresh_token(*, token: RefreshToken, user, request) -> RefreshTokenSession:
    jti = token_jti(token)
    expires_at = token_expiry(token) or timezone.now()
    ip = request.META.get("REMOTE_ADDR") if request is not None else None
    ua = (request.META.get("HTTP_USER_AGENT", "") if request is not None else "") or ""
    return RefreshTokenSession.objects.create(
        user=user,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip,
        user_agent=ua[:256],
    )


def revoke_refresh_session(session: RefreshTokenSession, *, replaced_by_jti: str | None = None) -> None:
    session.revoked_at = timezone.now()
    session.last_used_at = timezone.now()
    session.replaced_by_jti = replaced_by_jti or ""
    session.save(update_fields=["revoked_at", "last_used_at", "replaced_by_jti"])


def extract_login_reason_code(serializer_errors) -> str:
    if hasattr(serializer_errors, "get"):
        nfe = serializer_errors.get("non_field_errors", [])
        if nfe:
            code = getattr(nfe[0], "code", "")
            if code == "user_disabled":
                return "USER_DISABLED"
            if code == "invalid_credentials":
                return "INVALID_CREDENTIALS"
    return "INVALID_CREDENTIALS"


def request_auth_transport(request) -> str:
    if getattr(settings, "AUTH_ALLOW_TRANSPORT_OVERRIDE", False):
        override = request.headers.get("X-Auth-Transport") or request.query_params.get("auth_transport")
        if override in ("header", "cookie"):
            return override
    return getattr(settings, "AUTH_TOKEN_TRANSPORT", "header")


def is_admin_user(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def totp_for_user(user):
    return pyotp.TOTP(user.totp_secret)


def ua_hash(request) -> str:
    ua = (request.META.get("HTTP_USER_AGENT", "") or "").strip()
    if not ua:
        return ""
    return hashlib.sha256(ua.encode("utf-8")).hexdigest()


def issue_2fa_challenge(*, user, request) -> str:
    expires_at = timezone.now() + timedelta(seconds=int(settings.TOTP_CHALLENGE_TTL))
    challenge = TwoFactorChallenge.objects.create(
        user=user,
        expires_at=expires_at,
        ip_address=(request.META.get("REMOTE_ADDR") or None),
        user_agent_hash=ua_hash(request),
    )
    signer = signing.TimestampSigner(salt="auth-2fa")
    return signer.sign(str(challenge.id))


def consume_2fa_challenge(*, challenge_token: str, request) -> TwoFactorChallenge | None:
    signer = signing.TimestampSigner(salt="auth-2fa")
    try:
        raw = signer.unsign(challenge_token, max_age=settings.TOTP_CHALLENGE_TTL)
        challenge_id = uuid.UUID(str(raw))
    except (BadSignature, SignatureExpired, ValueError):
        return None

    now = timezone.now()
    ip = request.META.get("REMOTE_ADDR") or None
    current_ua_hash = ua_hash(request)

    with transaction.atomic():
        challenges = list(TwoFactorChallenge.objects.select_for_update().filter(id=challenge_id))
        if not challenges:
            return None

        challenge = challenges[0]
        if challenge.used_at is not None:
            return None
        if challenge.expires_at and challenge.expires_at <= now:
            return None
        if challenge.ip_address and ip and challenge.ip_address != ip:
            return None
        if challenge.user_agent_hash and current_ua_hash and challenge.user_agent_hash != current_ua_hash:
            return None

        TwoFactorChallenge.objects.filter(pk=challenge.pk).delete()

    return challenge
