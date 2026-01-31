from __future__ import annotations

from django.utils import timezone
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .handlers import Command, CommandError, apply_command_idempotent
from .models import DeviceEnrollment, DeviceRequestNonce
from .serializers import SyncBatchSerializer
from .signing import canonical_string, verify_hmac_signature

MAX_SKEW_SECONDS = 300  # 5 minutos


class SyncBatchView(APIView):
    authentication_classes = []  # autenticación propia por firma
    permission_classes = []

    def post(self, request):
        # 1) Headers
        device_id = request.headers.get("X-Device-Id")
        ts_raw = request.headers.get("X-Device-Ts")
        nonce = request.headers.get("X-Device-Nonce")
        sig = request.headers.get("X-Device-Signature")

        if not (device_id and ts_raw and nonce and sig):
            return Response({"error": "MISSING_HEADERS"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ts = int(ts_raw)
        except ValueError:
            return Response({"error": "INVALID_TS"}, status=status.HTTP_400_BAD_REQUEST)

        now = int(timezone.now().timestamp())
        if abs(now - ts) > MAX_SKEW_SECONDS:
            return Response({"error": "TS_OUT_OF_WINDOW"}, status=status.HTTP_401_UNAUTHORIZED)

        # 2) Device
        device = DeviceEnrollment.objects.filter(id=device_id, is_active=True).first()
        if not device:
            return Response({"error": "UNKNOWN_OR_INACTIVE_DEVICE"}, status=status.HTTP_401_UNAUTHORIZED)

        # 3) Firma
        raw_body = request.body or b""
        canonical = canonical_string(ts=ts, nonce=nonce, raw_body=raw_body)
        if not verify_hmac_signature(device.secret_b64, canonical, sig):
            return Response({"error": "BAD_SIGNATURE"}, status=status.HTTP_401_UNAUTHORIZED)

        # 4) Anti-replay nonce (solo si la firma es válida)
        try:
            with transaction.atomic():
                DeviceRequestNonce.objects.create(device=device, nonce=nonce, ts=ts)
        except IntegrityError:
            # unique constraint => replay
            return Response({"error": "REPLAY_DETECTED"}, status=status.HTTP_401_UNAUTHORIZED)

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
