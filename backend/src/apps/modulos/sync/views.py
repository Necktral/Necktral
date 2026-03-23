from __future__ import annotations

import secrets
import time
import uuid
from datetime import timezone as dt_timezone

from apps.modulos.iam.models import OrgUnit
from apps.modulos.sync_engine.models import Device as CoreSyncDevice
from apps.modulos.sync_engine.services import (
    RequestAuthError,
    process_batch,
    validate_request_level_auth,
)
from config.metrics import increment_counter, record_custom_latency
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.error_envelope import build_error_envelope
from .models import DeviceEnrollment
from .serializers import SyncBatchSerializer
from .signing import canonical_string, verify_hmac_signature

SYNC_HMAC_DEPRECATION_LINK = "</docs/CONTRACT_PACK_v2.0.md>; rel=\"deprecation\""
SYNC_HMAC_DEPRECATION_NOTICE = "Use /api/sync/batch/ (sync-hmac legacy se mantiene por compatibilidad)."

LEGACY_SYNC_HOLDING_CODE = "SYNC_HMAC_LEGACY_HOLDING"
LEGACY_SYNC_COMPANY_CODE = "SYNC_HMAC_LEGACY_COMPANY"


class SyncBatchView(APIView):
    authentication_classes = []  # autenticación propia por firma
    permission_classes = []
    throttle_scope = "sync_batch"

    @staticmethod
    def _metric_request() -> None:
        increment_counter("metrics:sync_legacy:requests")

    @staticmethod
    def _metric_error(reason: str) -> None:
        reason_code = str(reason or "UNKNOWN").upper()
        increment_counter(f"metrics:sync_legacy:errors:{reason_code}")
        if reason_code in {"BAD_SIGNATURE", "REPLAY_DETECTED", "TS_OUT_OF_WINDOW"}:
            increment_counter(f"metrics:sync_legacy:security:{reason_code.lower()}")

    @staticmethod
    def _metric_result(status_value: str) -> None:
        normalized = str(status_value or "UNKNOWN").upper()
        increment_counter(f"metrics:sync_legacy:results:{normalized.lower()}")

    @staticmethod
    def _metric_latency(duration_ms: int) -> None:
        record_custom_latency("sync_legacy", duration_ms=max(0, int(duration_ms)))

    @staticmethod
    def _legacy_sunset() -> str:
        return str(getattr(settings, "SYNC_HMAC_LEGACY_SUNSET", "") or "").strip()

    @classmethod
    def _with_deprecation_headers(cls, response: Response) -> Response:
        response["Deprecation"] = "true"
        response["Link"] = SYNC_HMAC_DEPRECATION_LINK
        response["X-Deprecated"] = "true"
        response["X-Deprecation-Notice"] = SYNC_HMAC_DEPRECATION_NOTICE
        sunset = cls._legacy_sunset()
        if sunset:
            response["Sunset"] = sunset
        return response

    def _error_response(self, request, *, status_code: int, reason: str, details: dict | None = None) -> Response:
        self._metric_error(reason)
        payload = build_error_envelope(
            request=request,
            status_code=status_code,
            exc=None,
            details={"detail": reason, **(details or {})},
        )
        return self._with_deprecation_headers(Response(payload, status=status_code))

    @staticmethod
    def _legacy_scope_company() -> OrgUnit:
        holding, _ = OrgUnit.objects.get_or_create(
            unit_type=OrgUnit.UnitType.HOLDING,
            code=LEGACY_SYNC_HOLDING_CODE,
            defaults={"name": "Sync Legacy Holding", "is_active": True},
        )
        company, _ = OrgUnit.objects.get_or_create(
            unit_type=OrgUnit.UnitType.COMPANY,
            code=LEGACY_SYNC_COMPANY_CODE,
            defaults={"name": "Sync Legacy Company", "is_active": True, "parent": holding},
        )
        if company.parent_id != holding.id:
            company.parent = holding
            company.save(update_fields=["parent"])
        return company

    @classmethod
    def _resolve_or_create_core_device(cls, *, device: DeviceEnrollment) -> CoreSyncDevice:
        if device.core_device_id:
            core_device = device.core_device
            if core_device is None:
                device.core_device_id = None
                device.save(update_fields=["core_device"])
            else:
                update_fields: list[str] = []
                if core_device.hmac_secret_b64 != device.secret_b64:
                    core_device.hmac_secret_b64 = device.secret_b64
                    update_fields.append("hmac_secret_b64")
                if core_device.status != CoreSyncDevice.Status.ACTIVE:
                    core_device.status = CoreSyncDevice.Status.ACTIVE
                    update_fields.append("status")
                if update_fields:
                    core_device.save(update_fields=update_fields)
                return core_device

        if not bool(getattr(settings, "SYNC_HMAC_LEGACY_ALLOW_BRIDGE_CREATE", True)):
            raise RequestAuthError(status_code=410, reason="LEGACY_DEVICE_ENROLL_DISABLED")

        company = cls._legacy_scope_company()
        core_device = CoreSyncDevice.objects.create(
            company=company,
            branch=None,
            label=f"legacy-hmac:{device.id}",
            status=CoreSyncDevice.Status.ACTIVE,
            public_key=secrets.token_bytes(32),
            hmac_secret_b64=device.secret_b64,
            meta={"legacy_hmac_enrollment_id": str(device.id)},
        )
        device.core_device = core_device
        device.save(update_fields=["core_device"])
        return core_device

    @staticmethod
    def _legacy_command_result_from_core(core_result: dict) -> dict:
        status_value = str(core_result.get("status") or "")
        if status_value in {"APPLIED", "DUPLICATE"}:
            return {"status": "OK", "data": core_result.get("refs") or {}}
        return {"status": "ERROR", "error": core_result.get("reason", "SYNC_INTERNAL_ERROR")}

    def post(self, request):
        started_at = time.monotonic()
        try:
            if not bool(getattr(settings, "SYNC_HMAC_LEGACY_ENABLED", True)):
                return self._error_response(
                    request,
                    status_code=status.HTTP_410_GONE,
                    reason="LEGACY_ENDPOINT_DISABLED",
                )

            self._metric_request()

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

            # 2) Device
            device = DeviceEnrollment.objects.select_related("core_device").filter(id=device_id, is_active=True).first()
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

            try:
                core_device = self._resolve_or_create_core_device(device=device)
            except RequestAuthError as exc:
                return self._error_response(
                    request,
                    status_code=exc.status_code,
                    reason=exc.reason,
                    details=exc.details,
                )

            # 4) Parse legacy payload y delegar a core sync_engine
            serializer = SyncBatchSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            occurred_at = timezone.datetime.fromtimestamp(ts, tz=dt_timezone.utc)
            commands = []
            for cmd in serializer.validated_data["commands"]:
                commands.append(
                    {
                        "command_id": cmd["command_id"],
                        "command_type": cmd["type"],
                        "company_id": core_device.company_id,
                        "branch_id": core_device.branch_id,
                        "occurred_at": occurred_at,
                        "sequence": None,
                        "payload": cmd.get("payload") or {},
                        "payload_hash": "",
                        "prev_hash": "",
                        "signature": "",
                    }
                )

            try:
                # En legacy ya validamos firma HMAC sobre raw-body. El core aplica skew + nonce.
                validate_request_level_auth(
                    device=core_device,
                    ts=ts,
                    nonce=str(nonce),
                    auth_scheme="hmac",
                    auth_signature_b64="",
                    body_without_signature={},
                    verify_signature=False,
                )
            except RequestAuthError as exc:
                return self._error_response(
                    request,
                    status_code=exc.status_code,
                    reason=exc.reason,
                    details=exc.details,
                )

            core_out = process_batch(
                request=request._request if hasattr(request, "_request") else request,
                actor_user=getattr(request, "user", None),
                device=core_device,
                batch_id=uuid.uuid4(),
                sent_at=occurred_at,
                commands=commands,
                require_command_signature=False,
            )

            results = []
            for core_result in core_out.get("results", []):
                legacy_result = self._legacy_command_result_from_core(core_result)
                self._metric_result(legacy_result.get("status", "UNKNOWN"))
                results.append(
                    {
                        "command_id": str(core_result.get("command_id")),
                        "result": legacy_result,
                    }
                )

            return self._with_deprecation_headers(
                Response({"device_id": str(device.id), "results": results}, status=status.HTTP_200_OK)
            )
        finally:
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            self._metric_latency(elapsed_ms)
