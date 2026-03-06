from __future__ import annotations

from django.utils import timezone
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.error_envelope import build_error_envelope
from .handlers import Command, CommandError, apply_command_idempotent
from .models import DeviceEnrollment, DeviceRequestNonce
from .serializers import SyncBatchSerializer
from .signing import canonical_string, verify_hmac_signature

MAX_SKEW_SECONDS = 300  # 5 minutos


class SyncBatchView(APIView):
    authentication_classes = []  # autenticación propia por firma
    permission_classes = []
    throttle_scope = "sync_batch"

    def _error_response(self, request, *, status_code: int, reason: str, details: dict | None = None) -> Response:
        payload = build_error_envelope(
            request=request,
            status_code=status_code,
            exc=None,
            details={"detail": reason, **(details or {})},
        )
        return Response(payload, status=status_code)

    def post(self, request):
        # 1) Headers
        device_id = request.headers.get("X-Device-Id")
        ts_raw = request.headers.get("X-Device-Ts")
        nonce = request.headers.get("X-Device-Nonce")
        sig = request.headers.get("X-Device-Signature")

        if not (device_id and ts_raw and nonce and sig):
            return self._error_response(
                request,
                status_code=status.HTTP_400_BAD_REQUEST,
                reason="MISSING_HEADERS",
                details={
                    "required": [
                        "X-Device-Id",
                        "X-Device-Ts",
                        "X-Device-Nonce",
                        "X-Device-Signature",
                    ]
                },
            )

        try:
            ts = int(ts_raw)
        except ValueError:
            return self._error_response(
                request,
                status_code=status.HTTP_400_BAD_REQUEST,
                reason="INVALID_TS",
            )

        now = int(timezone.now().timestamp())
        if abs(now - ts) > MAX_SKEW_SECONDS:
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="TS_OUT_OF_WINDOW",
            )

        # 2) Device
        device = DeviceEnrollment.objects.filter(id=device_id, is_active=True).first()
        if not device:
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="UNKNOWN_OR_INACTIVE_DEVICE",
            )

        # 3) Firma
        raw_body = request.body or b""
        canonical = canonical_string(ts=ts, nonce=nonce, raw_body=raw_body)
        if not verify_hmac_signature(device.secret_b64, canonical, sig):
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="BAD_SIGNATURE",
            )

        # 4) Anti-replay nonce
        try:
            # Usamos savepoint para que un nonce duplicado no rompa la transacción del request.
            with transaction.atomic():
                DeviceRequestNonce.objects.create(device=device, nonce=nonce, ts=ts)
        except IntegrityError:
            # unique constraint => replay
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="REPLAY_DETECTED",
            )

        # 5) Parse + apply
        serializer = SyncBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        for c in serializer.validated_data["commands"]:
            cmd = Command(
                command_id=str(c["command_id"]),
                type=c["type"],
                payload=c.get("payload") or {},
            )
            try:
                r = apply_command_idempotent(device, cmd)
                results.append({"command_id": cmd.command_id, "result": r})
            except CommandError as e:
                results.append({"command_id": cmd.command_id, "result": {"status": "ERROR", "error": str(e)}})

        return Response({"device_id": str(device.id), "results": results}, status=status.HTTP_200_OK)
