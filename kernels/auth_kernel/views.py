import pyotp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.modulos.accounts.cookies import clear_auth_cookies, set_auth_cookies
from apps.modulos.audit.writer import write_event
from apps.modulos.iam.bootstrap_services import bootstrap_init_admin, get_bootstrap_status
from apps.modulos.iam.selectors import build_acl_snapshot
from apps.modulos.iam.serializers import BootstrapInitAdminSerializer
from apps.modulos.org.bootstrap_services import bootstrap_organization_for_user
from apps.modulos.org.serializers import BootstrapOrganizationSerializer
from config.throttling import AuthLoginRateThrottle

from .serializers import (
    LoginSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    TwoFactorSetupConfirmSerializer,
    TwoFactorVerifySerializer,
)
from .services import (
    consume_2fa_challenge,
    extract_login_reason_code,
    is_admin_user,
    issue_2fa_challenge,
    persist_refresh_token,
    request_auth_transport,
    revoke_refresh_session,
    token_jti,
    totp_for_user,
)

User = get_user_model()

DEPRECATION_SUNSET_AT = "Mon, 18 May 2026 00:00:00 GMT"


def _legacy_bootstrap_headers(*, successor: str) -> dict[str, str]:
    return {
        "Deprecation": "true",
        "Sunset": DEPRECATION_SUNSET_AT,
        "Link": f'<{successor}>; rel="successor-version"',
    }


def _legacy_response(payload, *, status_code: int, successor: str) -> Response:
    return Response(payload, status=status_code, headers=_legacy_bootstrap_headers(successor=successor))


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthLoginRateThrottle]

    def post(self, request):
        transport = request_auth_transport(request)
        qd = QueryDict("", mutable=True)
        qd.update({"username": request.data.get("username") or request.data.get("email") or ""})
        request._request.POST = qd

        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            reason = extract_login_reason_code(serializer.errors)
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
        if is_admin_user(user) and user.totp_enabled:
            challenge = issue_2fa_challenge(user=user, request=request)
            write_event(
                request=request,
                event_type="AUTH_2FA_CHALLENGE",
                reason_code="TOTP_REQUIRED",
                actor_user=user,
                subject_type="USER",
                subject_id=str(user.id),
                metadata={"stage": "login"},
            )
            return Response({"2fa_required": True, "challenge": challenge}, status=status.HTTP_202_ACCEPTED)

        refresh = RefreshToken.for_user(user)
        persist_refresh_token(token=refresh, user=user, request=request)
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

        return Response({"access": str(refresh.access_token), "refresh": str(refresh)}, status=status.HTTP_200_OK)


class RefreshView(TokenRefreshView):
    permission_classes = (AllowAny,)  # type: ignore[assignment]
    throttle_scope = "auth_refresh"

    def post(self, request, *args, **kwargs):
        transport = request_auth_transport(request)
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
        except TokenError:
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

        jti = token_jti(token)
        session = user.refresh_sessions.filter(jti=jti, revoked_at__isnull=True).first()
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
        persist_refresh_token(token=new_refresh, user=user, request=request)
        revoke_refresh_session(session, replaced_by_jti=token_jti(new_refresh))
        try:
            token.blacklist()
        except TokenError:
            pass

        access = new_refresh.access_token
        new_refresh_str = str(new_refresh)
        write_event(
            request=request,
            event_type="AUTH_TOKEN_REFRESH",
            reason_code="",
            actor_user=None,
            subject_type="SESSION",
            subject_id="",
            metadata={"stage": "refresh"},
        )

        if transport == "cookie":
            response = Response({"ok": True}, status=status.HTTP_200_OK)
            set_auth_cookies(response, access=str(access), refresh=new_refresh_str)
            return response

        return Response({"access": str(access), "refresh": new_refresh_str}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_logout"

    def post(self, request):
        transport = request_auth_transport(request)
        refresh = request.data.get("refresh")
        if transport == "cookie":
            refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)

        response = Response(status=status.HTTP_204_NO_CONTENT)
        if transport == "cookie":
            clear_auth_cookies(response)

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
            return response

        try:
            token = RefreshToken(refresh)
        except TokenError:
            write_event(
                request=request,
                event_type="AUTH_LOGOUT_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=request.user,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "logout", "detail": "invalid_refresh"},
            )
            return response

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
            return Response({"detail": "refresh no pertenece al usuario."}, status=status.HTTP_403_FORBIDDEN)

        jti = token_jti(token)
        session = request.user.refresh_sessions.filter(jti=jti, revoked_at__isnull=True).first()
        if session:
            revoke_refresh_session(session)

        try:
            token.blacklist()
        except TokenError:
            write_event(
                request=request,
                event_type="AUTH_LOGOUT_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=request.user,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "logout", "detail": "blacklist_failed"},
            )
            return response

        write_event(
            request=request,
            event_type="AUTH_LOGOUT",
            reason_code="",
            actor_user=request.user,
            subject_type="USER",
            subject_id=str(request.user.id),
            metadata={"stage": "logout"},
        )
        return response


class TwoFactorSetupView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        user = request.user
        if not is_admin_user(user):
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
        return Response({"secret": secret, "otpauth_uri": otpauth}, status=status.HTTP_200_OK)


class TwoFactorConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        user = request.user
        if not is_admin_user(user):
            return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
        if not user.totp_secret:
            return Response({"detail": "2FA no inicializado."}, status=status.HTTP_400_BAD_REQUEST)

        s = TwoFactorSetupConfirmSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        totp = totp_for_user(user)
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
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        s = TwoFactorVerifySerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        challenge = consume_2fa_challenge(challenge_token=s.validated_data["challenge"], request=request)
        if not challenge:
            return Response({"detail": "Challenge inválido."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(id=challenge.user_id, is_active=True).first()
        if not user or not is_admin_user(user) or not user.totp_enabled:
            return Response({"detail": "Challenge inválido."}, status=status.HTTP_400_BAD_REQUEST)

        totp = totp_for_user(user)
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
        persist_refresh_token(token=refresh, user=user, request=request)
        write_event(
            request=request,
            event_type="AUTH_2FA_VERIFIED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"stage": "2fa_verify"},
        )

        transport = request_auth_transport(request)
        if transport == "cookie":
            response = Response({"ok": True}, status=status.HTTP_200_OK)
            set_auth_cookies(response, access=str(refresh.access_token), refresh=str(refresh))
            return response
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)}, status=status.HTTP_200_OK)


class TwoFactorDisableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        user = request.user
        if not is_admin_user(user):
            return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

        s = TwoFactorSetupConfirmSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        if not user.totp_enabled or not user.totp_secret:
            return Response({"detail": "2FA no habilitado."}, status=status.HTTP_400_BAD_REQUEST)

        totp = totp_for_user(user)
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
        return Response(MeSerializer.from_user(request.user), status=status.HTTP_200_OK)


class MeACLView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "me_acl_read"

    def get(self, request):
        return Response(build_acl_snapshot(request.user), status=status.HTTP_200_OK)


class LegacyBootstrapStatusView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "heavy_reads"

    def get(self, request):
        payload = get_bootstrap_status()
        return _legacy_response(payload, status_code=status.HTTP_200_OK, successor="/api/backend/iam/bootstrap/status/")


class LegacyBootstrapInitView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "admin_writes"

    def post(self, request):
        serializer = BootstrapInitAdminSerializer(data=request.data)
        if not serializer.is_valid():
            return _legacy_response(
                serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
                successor="/api/backend/iam/bootstrap/init-admin/",
            )
        try:
            user = bootstrap_init_admin(serializer.validated_data)
        except ValueError as exc:
            return _legacy_response(
                {"detail": str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST,
                successor="/api/backend/iam/bootstrap/init-admin/",
            )

        write_event(
            request=request,
            event_type="AUTH_BOOTSTRAP_ADMIN_CREATED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"username": user.username},
        )
        return _legacy_response(
            {"id": user.id},
            status_code=status.HTTP_201_CREATED,
            successor="/api/backend/iam/bootstrap/init-admin/",
        )


class LegacyBootstrapOrgView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "admin_writes"

    def post(self, request):
        serializer = BootstrapOrganizationSerializer(data=request.data)
        if not serializer.is_valid():
            return _legacy_response(
                serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
                successor="/api/backend/org/bootstrap/organization/",
            )
        try:
            ids = bootstrap_organization_for_user(request.user, serializer.validated_data)
        except ValueError as exc:
            detail = str(exc)
            status_code = status.HTTP_409_CONFLICT if "Bootstrap ya realizado" in detail else status.HTTP_400_BAD_REQUEST
            if "Falta role" in detail:
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return _legacy_response(
                {"detail": detail},
                status_code=status_code,
                successor="/api/backend/org/bootstrap/organization/",
            )

        write_event(
            request=request,
            event_type="IAM_BOOTSTRAP_ORG_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="COMPANY",
            subject_id=str(ids["company_id"]),
            metadata=ids,
        )
        return _legacy_response(
            ids,
            status_code=status.HTTP_200_OK,
            successor="/api/backend/org/bootstrap/organization/",
        )
