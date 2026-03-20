from __future__ import annotations

from dataclasses import dataclass
import json
import ssl
from typing import Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit

from django.conf import settings

from .models import BranchFiscalConfig, FiscalMode


@dataclass(frozen=True)
class FiscalIssueResult:
    status: str
    reference: str = ""
    evidence_id: str = ""
    metadata: dict | None = None


class FiscalAdapter(Protocol):
    mode: str
    adapter_code: str

    def attach_or_reserve_reference(self, *, doc) -> str: ...

    def issue_document(self, *, request, doc) -> FiscalIssueResult: ...

    def void_document(self, *, request, doc, reason: str) -> FiscalIssueResult: ...

    def issue_credit_note(self, *, request, original_doc, credit_note_doc) -> FiscalIssueResult: ...

    def print_document(self, *, request, doc) -> FiscalIssueResult: ...

    def record_contingency(self, *, request, doc, reason: str) -> FiscalIssueResult: ...

    def produce_fiscal_evidence(self, *, request, doc) -> FiscalIssueResult: ...

    def validate_range_integrity(self, *, request, branch, series: str) -> bool: ...


@dataclass(frozen=True)
class FiscalRuntimeConfig:
    mode: str
    adapter_code: str
    print_required: bool
    strict_integrity: bool
    contingency_max_attempts: int


@dataclass(frozen=True)
class AdapterBHttpConfig:
    base_url: str
    api_key: str
    timeout_seconds: int
    verify_tls: bool


class NoopFiscalAdapter:
    def __init__(self, *, mode: str = FiscalMode.NOOP, adapter_code: str = "NOOP"):
        self.mode = mode
        self.adapter_code = adapter_code

    def attach_or_reserve_reference(self, *, doc) -> str:
        return f"{doc.series}-{doc.number or 0}"

    def issue_document(self, *, request, doc) -> FiscalIssueResult:
        ref = self.attach_or_reserve_reference(doc=doc)
        return FiscalIssueResult(status="ISSUED", reference=ref, metadata={"adapter": self.mode})

    def void_document(self, *, request, doc, reason: str) -> FiscalIssueResult:
        ref = self.attach_or_reserve_reference(doc=doc)
        return FiscalIssueResult(status="VOIDED", reference=ref, metadata={"adapter": self.mode, "reason": reason})

    def issue_credit_note(self, *, request, original_doc, credit_note_doc) -> FiscalIssueResult:
        ref = self.attach_or_reserve_reference(doc=credit_note_doc)
        return FiscalIssueResult(
            status="CREDIT_NOTE_ISSUED",
            reference=ref,
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code, "original_doc_id": original_doc.id},
        )

    def print_document(self, *, request, doc) -> FiscalIssueResult:
        ref = self.attach_or_reserve_reference(doc=doc)
        return FiscalIssueResult(
            status="PRINTED",
            reference=ref,
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code},
        )

    def record_contingency(self, *, request, doc, reason: str) -> FiscalIssueResult:
        ref = self.attach_or_reserve_reference(doc=doc)
        return FiscalIssueResult(
            status="CONTINGENCY_RECORDED",
            reference=ref,
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code, "reason": reason},
        )

    def produce_fiscal_evidence(self, *, request, doc) -> FiscalIssueResult:
        ref = self.attach_or_reserve_reference(doc=doc)
        return FiscalIssueResult(
            status="EVIDENCE_READY",
            reference=ref,
            evidence_id=f"fiscal:{doc.id}",
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code},
        )

    def validate_range_integrity(self, *, request, branch, series: str) -> bool:
        _ = (request, branch, series)
        return True


class AdapterBEmulated:
    mode = str(FiscalMode.B)

    def __init__(self, *, adapter_code: str = "EMULATED_B"):
        self.adapter_code = adapter_code or "EMULATED_B"

    def _ref(self, *, doc) -> str:
        number = int(doc.number or 0)
        return f"{doc.series}-{number:010d}"

    def attach_or_reserve_reference(self, *, doc) -> str:
        return self._ref(doc=doc)

    def issue_document(self, *, request, doc) -> FiscalIssueResult:
        _ = request
        return FiscalIssueResult(
            status="ISSUED",
            reference=self._ref(doc=doc),
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code},
        )

    def issue_credit_note(self, *, request, original_doc, credit_note_doc) -> FiscalIssueResult:
        _ = request
        return FiscalIssueResult(
            status="CREDIT_NOTE_ISSUED",
            reference=self._ref(doc=credit_note_doc),
            metadata={
                "adapter": self.mode,
                "adapter_code": self.adapter_code,
                "original_doc_id": original_doc.id,
            },
        )

    def print_document(self, *, request, doc) -> FiscalIssueResult:
        _ = request
        metadata = dict(doc.fiscal_metadata_json or {})
        if metadata.get("force_print_failure", False):
            raise RuntimeError("fiscal print failure forced by metadata")
        remaining = int(metadata.get("force_print_failures_remaining", 0) or 0)
        if remaining > 0:
            metadata["force_print_failures_remaining"] = remaining - 1
            doc.fiscal_metadata_json = metadata
            doc.save(update_fields=["fiscal_metadata_json"])
            raise RuntimeError("fiscal print failure forced by counter")

        return FiscalIssueResult(
            status="PRINTED",
            reference=self._ref(doc=doc),
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code},
        )

    def void_document(self, *, request, doc, reason: str) -> FiscalIssueResult:
        _ = request
        return FiscalIssueResult(
            status="VOIDED",
            reference=self._ref(doc=doc),
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code, "reason": reason},
        )

    def record_contingency(self, *, request, doc, reason: str) -> FiscalIssueResult:
        _ = request
        return FiscalIssueResult(
            status="CONTINGENCY_RECORDED",
            reference=self._ref(doc=doc),
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code, "reason": reason},
        )

    def produce_fiscal_evidence(self, *, request, doc) -> FiscalIssueResult:
        _ = request
        return FiscalIssueResult(
            status="EVIDENCE_READY",
            reference=self._ref(doc=doc),
            evidence_id=f"fiscal-b:{doc.id}",
            metadata={"adapter": self.mode, "adapter_code": self.adapter_code},
        )

    def validate_range_integrity(self, *, request, branch, series: str) -> bool:
        _ = (request, branch, series)
        return True


class AdapterBHttp:
    mode = str(FiscalMode.B)

    def __init__(self, *, adapter_code: str, config: AdapterBHttpConfig):
        self.adapter_code = adapter_code or "REAL_HTTP"
        self.config = config

    def _context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        if not self.config.verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def _normalized_base_url(self) -> str:
        base = str(self.config.base_url or "").strip().rstrip("/")
        if not base:
            raise RuntimeError("FISCAL_ADAPTER_B_HTTP_BASE_URL no configurado")

        parsed = urlsplit(base)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("FISCAL_ADAPTER_B_HTTP_BASE_URL debe usar esquema http/https")
        if not parsed.netloc:
            raise RuntimeError("FISCAL_ADAPTER_B_HTTP_BASE_URL invalido (host requerido)")
        return base

    def _post(self, *, endpoint: str, payload: dict) -> dict:
        base = self._normalized_base_url()
        url = f"{base}{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Adapter-Code": self.adapter_code,
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        req = urllib_request.Request(url=url, data=body, headers=headers, method="POST")
        opener = urllib_request.build_opener(
            urllib_request.HTTPHandler(),
            urllib_request.HTTPSHandler(context=self._context()),
        )
        try:
            with opener.open(req, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                if not raw.strip():
                    return {}
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise RuntimeError(f"Respuesta inválida de provider: {url}")
                return data
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Provider HTTP error {exc.code}: {detail}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"Provider URL error: {exc.reason}") from exc

    def _result(self, *, fallback_status: str, payload: dict, response: dict) -> FiscalIssueResult:
        status = str(response.get("status") or fallback_status).strip().upper()
        reference = str(response.get("reference") or payload.get("reference") or "").strip()
        evidence_id = str(response.get("evidence_id") or "").strip()
        metadata = response.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["provider"] = "HTTP"
        metadata["adapter_code"] = self.adapter_code
        return FiscalIssueResult(
            status=status,
            reference=reference,
            evidence_id=evidence_id,
            metadata=metadata,
        )

    def _payload_for_doc(self, *, doc, reason: str = "") -> dict:
        return {
            "doc_id": int(doc.id),
            "doc_type": str(doc.doc_type),
            "series": str(doc.series or ""),
            "number": int(doc.number or 0),
            "currency": str(doc.currency or "NIO"),
            "subtotal": str(doc.subtotal),
            "tax_total": str(doc.tax_total),
            "total": str(doc.total),
            "fiscal_reference": str(doc.fiscal_reference or ""),
            "reason": reason or "",
            "metadata": dict(doc.fiscal_metadata_json or {}),
        }

    def attach_or_reserve_reference(self, *, doc) -> str:
        payload = self._payload_for_doc(doc=doc)
        response = self._post(endpoint="/v1/fiscal/reserve", payload=payload)
        reference = str(response.get("reference") or "").strip()
        if reference:
            return reference
        return f"{doc.series}-{int(doc.number or 0):010d}"

    def issue_document(self, *, request, doc) -> FiscalIssueResult:
        _ = request
        payload = self._payload_for_doc(doc=doc)
        response = self._post(endpoint="/v1/fiscal/issue", payload=payload)
        return self._result(fallback_status="ISSUED", payload=payload, response=response)

    def void_document(self, *, request, doc, reason: str) -> FiscalIssueResult:
        _ = request
        payload = self._payload_for_doc(doc=doc, reason=reason or "VOID")
        response = self._post(endpoint="/v1/fiscal/void", payload=payload)
        return self._result(fallback_status="VOIDED", payload=payload, response=response)

    def issue_credit_note(self, *, request, original_doc, credit_note_doc) -> FiscalIssueResult:
        _ = request
        payload = self._payload_for_doc(doc=credit_note_doc)
        payload["original_doc_id"] = int(original_doc.id)
        response = self._post(endpoint="/v1/fiscal/credit-note", payload=payload)
        return self._result(fallback_status="CREDIT_NOTE_ISSUED", payload=payload, response=response)

    def print_document(self, *, request, doc) -> FiscalIssueResult:
        _ = request
        payload = self._payload_for_doc(doc=doc)
        response = self._post(endpoint="/v1/fiscal/print", payload=payload)
        return self._result(fallback_status="PRINTED", payload=payload, response=response)

    def record_contingency(self, *, request, doc, reason: str) -> FiscalIssueResult:
        _ = request
        payload = self._payload_for_doc(doc=doc, reason=reason or "CONTINGENCY")
        response = self._post(endpoint="/v1/fiscal/contingency", payload=payload)
        return self._result(fallback_status="CONTINGENCY_RECORDED", payload=payload, response=response)

    def produce_fiscal_evidence(self, *, request, doc) -> FiscalIssueResult:
        _ = request
        payload = self._payload_for_doc(doc=doc)
        response = self._post(endpoint="/v1/fiscal/evidence", payload=payload)
        return self._result(fallback_status="EVIDENCE_READY", payload=payload, response=response)

    def validate_range_integrity(self, *, request, branch, series: str) -> bool:
        _ = request
        payload = {"branch_id": getattr(branch, "id", None), "series": series}
        response = self._post(endpoint="/v1/fiscal/validate-range", payload=payload)
        return bool(response.get("ok", False))


def resolve_adapter_b_http_config() -> AdapterBHttpConfig:
    return AdapterBHttpConfig(
        base_url=str(getattr(settings, "FISCAL_ADAPTER_B_HTTP_BASE_URL", "") or "").strip(),
        api_key=str(getattr(settings, "FISCAL_ADAPTER_B_HTTP_API_KEY", "") or "").strip(),
        timeout_seconds=max(1, int(getattr(settings, "FISCAL_ADAPTER_B_HTTP_TIMEOUT_SECONDS", 15) or 15)),
        verify_tls=bool(getattr(settings, "FISCAL_ADAPTER_B_HTTP_VERIFY_TLS", True)),
    )


def resolve_fiscal_runtime_config(*, company=None, branch=None) -> FiscalRuntimeConfig:
    if company is not None and branch is not None:
        row = (
            BranchFiscalConfig.objects.filter(company=company, branch=branch, is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if row is not None:
            return FiscalRuntimeConfig(
                mode=str(row.fiscal_mode or FiscalMode.NOOP).upper(),
                adapter_code=(row.adapter_code or "").strip().upper() or "NOOP",
                print_required=bool(row.print_required),
                strict_integrity=bool(row.strict_integrity),
                contingency_max_attempts=max(1, int(row.contingency_max_attempts or 5)),
            )

    mode = str(getattr(settings, "FISCAL_ADAPTER_MODE", FiscalMode.NOOP) or FiscalMode.NOOP).upper()
    if mode not in (FiscalMode.A, FiscalMode.B, FiscalMode.NOOP):
        mode = FiscalMode.NOOP
    return FiscalRuntimeConfig(
        mode=mode,
        adapter_code="NOOP" if mode != FiscalMode.B else "EMULATED_B",
        print_required=bool(mode == FiscalMode.B),
        strict_integrity=True,
        contingency_max_attempts=5,
    )


def get_fiscal_adapter(*, company=None, branch=None, doc=None) -> FiscalAdapter:
    if doc is not None:
        company = company or getattr(doc, "company", None)
        branch = branch or getattr(doc, "branch", None)
    cfg = resolve_fiscal_runtime_config(company=company, branch=branch)
    if cfg.mode == FiscalMode.B:
        provider_mode = str(getattr(settings, "FISCAL_ADAPTER_B_PROVIDER", "EMULATED") or "EMULATED").strip().upper()
        adapter_code = str(cfg.adapter_code or "").strip().upper()
        if provider_mode in ("HTTP", "REAL_HTTP") or adapter_code in ("HTTP", "REAL_HTTP", "B_HTTP", "PROVIDER_B"):
            return AdapterBHttp(adapter_code=adapter_code or "REAL_HTTP", config=resolve_adapter_b_http_config())
        return AdapterBEmulated(adapter_code=cfg.adapter_code)
    return NoopFiscalAdapter(mode=cfg.mode, adapter_code=cfg.adapter_code)
