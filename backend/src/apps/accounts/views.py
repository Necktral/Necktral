import hashlib
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
import pyotp
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit.writer import write_event
from config.throttling import AuthLoginRateThrottle

from apps.accounts.bootstrap_guard import enforce_bootstrap_guard
from apps.common.permissions import rbac_permission

from apps.iam.models import AdminGrant, OrgUnit, UserMembership
from apps.iam.selectors import build_acl_snapshot
from apps.org.models import BranchProfile, CompanyProfile
from apps.rbac.models import Role, RoleAssignment
from apps.rbac.seed_v01 import seed_rbac_v01
from modulos.estacion_servicios.services import provision_fuel_inventory_for_branch
from modulos.facturacion.services import provision_billing_sequences_for_branch

from .cookies import clear_auth_cookies, set_auth_cookies
from .models import RefreshTokenSession, TwoFactorChallenge
from .serializers import (
    LoginSerializer,
    MeSerializer,
    BootstrapInitSerializer,
    BootstrapOrgSerializer,
    PasswordChangeSerializer,
    TwoFactorSetupConfirmSerializer,
    TwoFactorVerifySerializer,
    AxesUnlockSerializer,
)

User = get_user_model()


def _token_jti(token: RefreshToken) -> str:
    return str(token.get("jti", ""))


def _token_expiry(token: RefreshToken):
    exp = token.get("exp", None)
    if exp is None:
        return None
    return datetime.fromtimestamp(int(exp), tz=dt_timezone.utc)


def _persist_refresh_token(*, token: RefreshToken, user, request) -> RefreshTokenSession:
    jti = _token_jti(token)
    expires_at = _token_expiry(token) or timezone.now()
    ip = request.META.get("REMOTE_ADDR") if request is not None else None
    ua = (request.META.get("HTTP_USER_AGENT", "") if request is not None else "") or ""
    return RefreshTokenSession.objects.create(
        user=user,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip,
        user_agent=ua[:256],
    )


def _revoke_refresh_session(session: RefreshTokenSession, *, replaced_by_jti: str | None = None) -> None:
    session.revoked_at = timezone.now()
    session.last_used_at = timezone.now()
    session.replaced_by_jti = replaced_by_jti or ""
    session.save(update_fields=["revoked_at", "last_used_at", "replaced_by_jti"])


def _extract_login_reason_code(serializer_errors) -> str:
    # serializer_errors puede contener ErrorDetail con .code
    try:
        nfe = serializer_errors.get("non_field_errors", [])
        if nfe:
            code = getattr(nfe[0], "code", "")
            if code == "user_disabled":
                return "USER_DISABLED"
            if code == "invalid_credentials":
                return "INVALID_CREDENTIALS"
    except Exception:
        pass
    return "INVALID_CREDENTIALS"


def _request_auth_transport(request) -> str:
    override = request.headers.get("X-Auth-Transport") or request.query_params.get("auth_transport")
    if override in ("header", "cookie"):
        return override
    return getattr(settings, "AUTH_TOKEN_TRANSPORT", "header")


def _is_admin_user(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _totp_for_user(user):
    return pyotp.TOTP(user.totp_secret)


def _ua_hash(request) -> str:
    ua = (request.META.get("HTTP_USER_AGENT", "") or "").strip()
    if not ua:
        return ""
    return hashlib.sha256(ua.encode("utf-8")).hexdigest()


def _issue_2fa_challenge(*, user, request) -> str:
    expires_at = timezone.now() + timedelta(seconds=int(settings.TOTP_CHALLENGE_TTL))
    challenge = TwoFactorChallenge.objects.create(
        user=user,
        expires_at=expires_at,
        ip_address=(request.META.get("REMOTE_ADDR") or None),
        user_agent_hash=_ua_hash(request),
    )
    signer = signing.TimestampSigner(salt="auth-2fa")
    return signer.sign(str(challenge.id))


def _consume_2fa_challenge(*, challenge_token: str, request) -> TwoFactorChallenge | None:
    signer = signing.TimestampSigner(salt="auth-2fa")
    try:
        raw = signer.unsign(challenge_token, max_age=settings.TOTP_CHALLENGE_TTL)
        challenge_id = uuid.UUID(str(raw))
    except Exception:
        return None

    now = timezone.now()
    ip = request.META.get("REMOTE_ADDR") or None
    ua_hash = _ua_hash(request)

    # Use atomic block + select_for_update to prevent replay attacks
    with transaction.atomic():
        # Force evaluation to list to ensure DB hit and locking
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

        if challenge.user_agent_hash and ua_hash and challenge.user_agent_hash != ua_hash:
            return None

        # Challenge consumed. Delete to prevent any replay possibility.
        # Use QuerySet delete to avoid clearing pk on the instance structure
        TwoFactorChallenge.objects.filter(pk=challenge.pk).delete()

    return challenge


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthLoginRateThrottle]

    def post(self, request):
        transport = _request_auth_transport(request)
        # Axes usa request.POST para extraer el username. En JSON, request.POST viene vacío.
        qd = QueryDict("", mutable=True)
        qd.update({"username": request.data.get("username") or request.data.get("email") or ""})
        request._request.POST = qd  # compatibilidad Axes

        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            reason = _extract_login_reason_code(serializer.errors)
            write_event(
                request=request,
                event_type="AUTH_LOGIN_FAILURE",
                reason_code=reason,
                actor_user=None,
                subject_type="USER",
                subject_id=str(request.data.get("username", "")),
                metadata={"stage": "login"},
            )
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data["user"]

        if _is_admin_user(user) and user.totp_enabled:
            challenge = _issue_2fa_challenge(user=user, request=request)
            write_event(
                request=request,
                event_type="AUTH_2FA_CHALLENGE",
                reason_code="TOTP_REQUIRED",
                actor_user=user,
                subject_type="USER",
                subject_id=str(user.id),
                metadata={"stage": "login"},
            )
            return Response(
                {"2fa_required": True, "challenge": challenge},
                status=status.HTTP_202_ACCEPTED,
            )

        refresh = RefreshToken.for_user(user)
        _persist_refresh_token(token=refresh, user=user, request=request)

        # Nota: must_change_password se evalúa en /me y el frontend redirige a /password-change
        # No alteramos tokens aquí.

        write_event(
            request=request,
            event_type="AUTH_LOGIN_SUCCESS",
            reason_code="",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"username": user.username},
        )

        if transport == "cookie":
            response = Response({"ok": True}, status=status.HTTP_200_OK)
            set_auth_cookies(response, access=str(refresh.access_token), refresh=str(refresh))
            return response

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class RefreshView(TokenRefreshView):
    permission_classes = (AllowAny,)  # type: ignore[assignment]
    throttle_scope = "auth_refresh"

    def post(self, request, *args, **kwargs):
        transport = _request_auth_transport(request)
        refresh_token = None
        if transport == "cookie":
            refresh_cookie = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)
            if not refresh_cookie:
                write_event(
                    request=request,
                    event_type="AUTH_TOKEN_REFRESH_FAILURE",
                    reason_code="TOKEN_INVALID",
                    actor_user=None,
                    subject_type="SESSION",
                    subject_id="",
                    metadata={"stage": "refresh", "detail": "missing_refresh_cookie"},
                )
                response = Response({"detail": "refresh es requerido."}, status=status.HTTP_401_UNAUTHORIZED)
                clear_auth_cookies(response)
                return response

            refresh_token = refresh_cookie
        else:
            refresh_token = request.data.get("refresh")

        if not refresh_token:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh", "detail": "missing_refresh"},
            )
            return Response({"detail": "refresh es requerido."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            token = RefreshToken(refresh_token)
        except Exception:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh", "detail": "invalid_refresh"},
            )
            response = Response({"detail": "refresh inválido."}, status=status.HTTP_401_UNAUTHORIZED)
            if transport == "cookie":
                clear_auth_cookies(response)
            return response

        token_user_id = token.get("user_id")
        if not token_user_id:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh", "detail": "missing_user_id"},
            )
            return Response({"detail": "refresh inválido."}, status=status.HTTP_401_UNAUTHORIZED)

        user = User.objects.filter(id=token_user_id, is_active=True).first()
        if not user:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh", "detail": "user_inactive"},
            )
            return Response({"detail": "refresh inválido."}, status=status.HTTP_401_UNAUTHORIZED)

        jti = _token_jti(token)
        session = RefreshTokenSession.objects.filter(
            jti=jti,
            user=user,
            revoked_at__isnull=True,
        ).first()
        if not session or (session.expires_at and session.expires_at <= timezone.now()):
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh", "detail": "session_revoked_or_missing"},
            )
            return Response({"detail": "refresh inválido."}, status=status.HTTP_401_UNAUTHORIZED)

        new_refresh = RefreshToken.for_user(user)
        _persist_refresh_token(token=new_refresh, user=user, request=request)
        _revoke_refresh_session(session, replaced_by_jti=_token_jti(new_refresh))
        try:
            token.blacklist()
        except Exception:
            pass

        access = new_refresh.access_token
        new_refresh_str = str(new_refresh)

        if transport == "cookie":
            response = Response({"ok": True}, status=status.HTTP_200_OK)
            set_auth_cookies(response, access=str(access), refresh=new_refresh_str)
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH",
                reason_code="",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh"},
            )
            return response

        write_event(
            request=request,
            event_type="AUTH_TOKEN_REFRESH",
            reason_code="",
            actor_user=None,
            subject_type="SESSION",
            subject_id="",
            metadata={"stage": "refresh"},
        )

        return Response(
            {
                "access": str(access),
                "refresh": new_refresh_str,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    # Seguridad: evita que un tercero pueda invalidar refresh ajenos (DoS por blacklist).
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_logout"

    def post(self, request):
        transport = _request_auth_transport(request)
        refresh = request.data.get("refresh")
        if transport == "cookie":
            refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)

        # Preparamos la respuesta base (idempotente)
        response = Response(status=status.HTTP_204_NO_CONTENT)

        # 1. Limpieza incondicional de cookies si el transporte es cookie.
        if transport == "cookie":
            clear_auth_cookies(response)

        try:
            if not refresh:
                write_event(
                    request=request,
                    event_type="AUTH_LOGOUT_FAILURE",
                    reason_code="TOKEN_INVALID",
                    actor_user=request.user,
                    subject_type="SESSION",
                    subject_id="",
                    metadata={"stage": "logout", "detail": "missing_refresh"},
                )
                # response ya es 204 y cookies limpias
                return response

            token = RefreshToken(refresh)

            token_user_id = token.get("user_id")
            if token_user_id is not None and str(token_user_id) != str(request.user.id):
                write_event(
                    request=request,
                    event_type="AUTH_LOGOUT_FAILURE",
                    reason_code="TOKEN_MISMATCH",
                    actor_user=request.user,
                    subject_type="SESSION",
                    subject_id="",
                    metadata={"stage": "logout", "detail": "refresh_owner_mismatch"},
                )
                # No blacklistear refresh ajeno; responder 403 para señalizar el riesgo.
                return Response({"detail": "refresh no pertenece al usuario."}, status=status.HTTP_403_FORBIDDEN)

            jti = _token_jti(token)

            # Revocación de sesión extendida
            session = RefreshTokenSession.objects.filter(jti=jti, user=request.user, revoked_at__isnull=True).first()
            if session:
                _revoke_refresh_session(session)

            # Revocación estándar (blacklist JWT)
            token.blacklist()

            write_event(
                request=request,
                event_type="AUTH_LOGOUT",
                reason_code="",
                actor_user=request.user,
                subject_type="USER",
                subject_id=str(request.user.id),
                metadata={"stage": "logout"},
            )

        except Exception:
            write_event(
                request=request,
                event_type="AUTH_LOGOUT_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=request.user,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "logout", "detail": "invalid_refresh"},
            )
            # Idempotente: refresh expirado/corrupto no debe bloquear el logout local.
            # response ya es 204 y cookies limpias.
            pass

        return response


class AxesUnlockView(APIView):
    permission_classes = [rbac_permission("auth.lockout.reset")]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        s = AxesUnlockSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        username = (s.validated_data.get("username") or "").strip() or None
        ip_address = (s.validated_data.get("ip_address") or "").strip() or None

        try:
            from axes.helpers import reset

            reset(username=username, ip_address=ip_address)
        except Exception:
            try:
                from axes.models import AccessAttempt

                qs = AccessAttempt.objects.all()
                if username:
                    qs = qs.filter(username=username)
                if ip_address:
                    qs = qs.filter(ip_address=ip_address)
                qs.delete()
            except Exception:
                return Response({"detail": "No se pudo desbloquear."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        write_event(
            request=request,
            event_type="AUTH_LOCKOUT_RESET",
            reason_code="AUTH_OK",
            actor_user=request.user,
            subject_type="USER",
            subject_id=str(username or ""),
            metadata={"ip_address": ip_address or ""},
        )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class TwoFactorSetupView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        user = request.user
        if not _is_admin_user(user):
            return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

        secret = pyotp.random_base32()
        user.totp_secret = secret
        user.totp_enabled = False
        user.totp_confirmed_at = None
        user.save(update_fields=["totp_secret", "totp_enabled", "totp_confirmed_at"])

        totp = pyotp.TOTP(secret)
        otpauth = totp.provisioning_uri(name=user.username, issuer_name=settings.TOTP_ISSUER)

        write_event(
            request=request,
            event_type="AUTH_2FA_SETUP_STARTED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"stage": "2fa_setup"},
        )

        return Response(
            {"secret": secret, "otpauth_uri": otpauth},
            status=status.HTTP_200_OK,
        )


class TwoFactorConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        user = request.user
        if not _is_admin_user(user):
            return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

        if not user.totp_secret:
            return Response({"detail": "2FA no inicializado."}, status=status.HTTP_400_BAD_REQUEST)

        s = TwoFactorSetupConfirmSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        totp = _totp_for_user(user)
        ok = totp.verify(s.validated_data["code"], valid_window=settings.TOTP_VALID_WINDOW)
        if not ok:
            write_event(
                request=request,
                event_type="AUTH_2FA_FAILED",
                reason_code="TOTP_INVALID",
                actor_user=user,
                subject_type="USER",
                subject_id=str(user.id),
                metadata={"stage": "2fa_confirm"},
            )
            return Response({"detail": "Código inválido."}, status=status.HTTP_400_BAD_REQUEST)

        user.totp_enabled = True
        user.totp_confirmed_at = timezone.now()
        user.save(update_fields=["totp_enabled", "totp_confirmed_at"])

        write_event(
            request=request,
            event_type="AUTH_2FA_ENABLED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"stage": "2fa_confirm"},
        )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class TwoFactorVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        s = TwoFactorVerifySerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        challenge = _consume_2fa_challenge(
            challenge_token=s.validated_data["challenge"],
            request=request,
        )
        if not challenge:
            return Response({"detail": "Challenge inválido."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(id=challenge.user_id, is_active=True).first()
        if not user or not _is_admin_user(user) or not user.totp_enabled:
            return Response({"detail": "Challenge inválido."}, status=status.HTTP_400_BAD_REQUEST)

        totp = _totp_for_user(user)
        ok = totp.verify(s.validated_data["code"], valid_window=settings.TOTP_VALID_WINDOW)
        if not ok:
            write_event(
                request=request,
                event_type="AUTH_2FA_FAILED",
                reason_code="TOTP_INVALID",
                actor_user=user,
                subject_type="USER",
                subject_id=str(user.id),
                metadata={"stage": "2fa_verify"},
            )
            return Response({"detail": "Código inválido."}, status=status.HTTP_400_BAD_REQUEST)

        refresh = RefreshToken.for_user(user)
        _persist_refresh_token(token=refresh, user=user, request=request)

        write_event(
            request=request,
            event_type="AUTH_2FA_VERIFIED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"stage": "2fa_verify"},
        )

        transport = _request_auth_transport(request)
        if transport == "cookie":
            response = Response({"ok": True}, status=status.HTTP_200_OK)
            set_auth_cookies(response, access=str(refresh.access_token), refresh=str(refresh))
            return response

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class TwoFactorDisableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        user = request.user
        if not _is_admin_user(user):
            return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

        s = TwoFactorSetupConfirmSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        if not user.totp_enabled or not user.totp_secret:
            return Response({"detail": "2FA no habilitado."}, status=status.HTTP_400_BAD_REQUEST)

        totp = _totp_for_user(user)
        ok = totp.verify(s.validated_data["code"], valid_window=settings.TOTP_VALID_WINDOW)
        if not ok:
            write_event(
                request=request,
                event_type="AUTH_2FA_FAILED",
                reason_code="TOTP_INVALID",
                actor_user=user,
                subject_type="USER",
                subject_id=str(user.id),
                metadata={"stage": "2fa_disable"},
            )
            return Response({"detail": "Código inválido."}, status=status.HTTP_400_BAD_REQUEST)

        user.totp_enabled = False
        user.totp_secret = ""
        user.totp_confirmed_at = None
        user.save(update_fields=["totp_enabled", "totp_secret", "totp_confirmed_at"])

        write_event(
            request=request,
            event_type="AUTH_2FA_DISABLED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"stage": "2fa_disable"},
        )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class BootstrapStatusView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "heavy_reads"

    def get(self, request):
        has_user = User.objects.exists()
        is_fresh = not has_user

        has_holding = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING, is_active=True).exists()
        has_company = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, is_active=True).exists()
        setup_required = (not has_holding) or (not has_company)

        return Response(
            {"is_fresh": bool(is_fresh), "setup_required": bool(setup_required)},
            status=status.HTTP_200_OK,
        )


class BootstrapInitView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "bootstrap"

    def post(self, request):
        # contrato: solo se permite cuando no hay usuarios
        if User.objects.exists():
            return Response({"detail": "Sistema ya inicializado."}, status=status.HTTP_400_BAD_REQUEST)

        enforce_bootstrap_guard(request)

        s = BootstrapInitSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data

        user = User.objects.create_user(
            username=v["username"].strip(),
            email=(v.get("email") or None),
            password=v["password"],
            first_name=v.get("first_name", ""),
            last_name=v.get("last_name", ""),
        )
        user.is_staff = True
        user.is_superuser = True
        user.must_change_password = False
        user.save(update_fields=["is_staff", "is_superuser", "must_change_password"])

        write_event(
            request=request,
            event_type="AUTH_BOOTSTRAP_ADMIN_CREATED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"username": user.username},
        )

        return Response({"id": user.id}, status=status.HTTP_201_CREATED)


class BootstrapOrgView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "admin_writes"

    def post(self, request):
        s = BootstrapOrgSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data

        # contrato inicial: solo 1 holding en bootstrap
        if OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING, is_active=True).exists():
            return Response({"detail": "Bootstrap ya realizado."}, status=status.HTTP_409_CONFLICT)

        from django.db import transaction

        with transaction.atomic():
            # 1) Seed RBAC (idempotente)
            seed_rbac_v01()

            # 2) Holding
            holding = OrgUnit.objects.create(
                unit_type=OrgUnit.UnitType.HOLDING,
                name=v["holding_name"].strip(),
                code="",
                is_active=True,
            )

            # 3) Company
            company = OrgUnit.objects.create(
                unit_type=OrgUnit.UnitType.COMPANY,
                parent=holding,
                name=v["company_name"].strip(),
                code="",
                is_active=True,
            )

            cp, _ = CompanyProfile.objects.get_or_create(company=company)
            # Completar campos pedidos por el wizard
            cp.legal_name = v["company_name"].strip()
            cp.tax_id = (v.get("company_tax_id") or "").strip()
            cp.save(update_fields=["legal_name", "tax_id"])

            # 4) Branch inicial
            branch = OrgUnit.objects.create(
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                name=v["branch_name"].strip(),
                code="",
                is_active=True,
            )

            bp, _ = BranchProfile.objects.get_or_create(branch=branch)
            bp.address = (v.get("branch_address") or "").strip()
            bp.save(update_fields=["address"])

            provision_fuel_inventory_for_branch(
                request=request,
                company=company,
                branch=branch,
                actor_user=request.user,
            )

            provision_billing_sequences_for_branch(
                request=request,
                company=company,
                branch=branch,
                actor_user=request.user,
            )

            # 5) Membership a COMPANY (esto habilita accesibilidad en ACL snapshot)
            UserMembership.objects.get_or_create(
                user=request.user,
                org_unit=company,
                defaults={"is_active": True},
            )

            # 6) RoleAssignment SYSTEM: company_admin (scope COMPANY)
            role = Role.objects.filter(name="company_admin").first()
            if not role:
                return Response(
                    {"detail": "Falta role 'company_admin'. Ejecuta seed_rbac_v01."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            RoleAssignment.objects.get_or_create(
                user=request.user,
                role=role,
                org_unit=company,
                origin=RoleAssignment.Origin.SYSTEM,
                defaults={"is_active": True, "origin_ref": "bootstrap"},
            )

            # 7) AdminGrants (scoped a COMPANY, completos)
            for cap, _ in AdminGrant.Capability.choices:
                AdminGrant.objects.get_or_create(
                    user=request.user,
                    org_unit=company,
                    capability=cap,
                    defaults={"applies_to_subtree": True, "is_active": True},
                )

        write_event(
            request=request,
            event_type="IAM_BOOTSTRAP_ORG_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="COMPANY",
            subject_id=str(company.id),
            metadata={"holding_id": holding.id, "company_id": company.id, "branch_id": branch.id},
        )

        return Response(
            {"holding_id": holding.id, "company_id": company.id, "branch_id": branch.id},
            status=status.HTTP_200_OK,
        )


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        s = PasswordChangeSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data

        user = request.user
        if not user.check_password(v["old_password"]):
            write_event(
                request=request,
                event_type="AUTH_PASSWORD_CHANGE_FAILURE",
                reason_code="INVALID_OLD_PASSWORD",
                actor_user=user,
                subject_type="USER",
                subject_id=str(user.id),
                metadata={"stage": "password_change"},
            )
            return Response({"old_password": "Incorrecta"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(v["new_password"])
        if hasattr(user, "must_change_password"):
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
        else:
            user.save(update_fields=["password"])

        write_event(
            request=request,
            event_type="AUTH_PASSWORD_CHANGED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"stage": "password_change"},
        )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "me_read"

    def get(self, request):
        payload = MeSerializer.from_user(request.user)
        return Response(payload, status=status.HTTP_200_OK)


# --- ACL Snapshot endpoint ---
class MeACLView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "me_acl_read"

    def get(self, request):
        return Response(build_acl_snapshot(request.user), status=status.HTTP_200_OK)
