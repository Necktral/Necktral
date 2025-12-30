from django.http import QueryDict
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit.writer import write_event

from .serializers import LoginSerializer, MeSerializer


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


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Axes usa request.POST para extraer el username. En JSON, request.POST viene vacío.
        qd = QueryDict("", mutable=True)
        qd.update({"username": request.data.get("username", "")})
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
        refresh = RefreshToken.for_user(user)

        write_event(
            request=request,
            event_type="AUTH_LOGIN_SUCCESS",
            reason_code="",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"username": user.username},
        )

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH",
                reason_code="",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh"},
            )
        else:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh"},
            )
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
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
            return Response({"detail": "refresh es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh)
            token.blacklist()
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
            return Response({"detail": "refresh inválido."}, status=status.HTTP_400_BAD_REQUEST)

        write_event(
            request=request,
            event_type="AUTH_LOGOUT",
            reason_code="",
            actor_user=request.user,
            subject_type="USER",
            subject_id=str(request.user.id),
            metadata={"stage": "logout"},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)



class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = MeSerializer.from_user(request.user)
        return Response(payload, status=status.HTTP_200_OK)


# --- ACL Snapshot endpoint ---
from rest_framework.permissions import IsAuthenticated

from apps.iam.selectors import build_acl_snapshot


class MeACLView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_acl_snapshot(request.user), status=status.HTTP_200_OK)
