from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase7b import (
    build_phase7b_evidence,
    collect_phase7b_operational_health,
)


class Command(BaseCommand):
    help = "Gate final de go-live 7B (intercompany + consolidación)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--certification", type=str, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
        parser.add_argument("--max-blocked-consolidation", type=int, default=0)
        parser.add_argument("--max-open-consolidation-exception", type=int, default=0)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    @staticmethod
    def _read_json(path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            raise CommandError(f"archivo no encontrado: {p}")
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"JSON inválido en {p}: {exc}") from exc
        if not isinstance(payload, dict):
            raise CommandError(f"JSON inválido en {p}: se esperaba objeto.")
        return payload

    @staticmethod
    def _validate_certification(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if bool(payload.get("passed")) is not True:
            errors.append("passed debe ser true.")
        if bool(payload.get("deterministic_replay")) is not True:
            errors.append("deterministic_replay debe ser true.")
        if bool(payload.get("go_live_passed")) is not True:
            errors.append("go_live_passed debe ser true.")
        first_hash = str(payload.get("first_manifest_hash") or "")
        second_hash = str(payload.get("second_manifest_hash") or "")
        if not first_hash or not second_hash or first_hash != second_hash:
            errors.append("first_manifest_hash y second_manifest_hash deben coincidir.")
        first_status = str(payload.get("first_status") or "")
        second_status = str(payload.get("second_status") or "")
        if not first_status or not second_status or first_status != second_status:
            errors.append("first_status y second_status inválidos o no coinciden.")
        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        certification = self._read_json(options["certification"])
        certification_errors = self._validate_certification(certification)
        health = collect_phase7b_operational_health(company_id=company_id, consumer=consumer)

        checks = [
            {
                "name": "certification_valid",
                "passed": len(certification_errors) == 0,
                "detail": {"errors": certification_errors},
            },
            {
                "name": "open_intercompany_within_threshold",
                "passed": int(health["open_intercompany_count"]) <= int(options.get("max_open_intercompany") or 0),
                "detail": {
                    "count": int(health["open_intercompany_count"]),
                    "max_allowed": int(options.get("max_open_intercompany") or 0),
                },
            },
            {
                "name": "disputed_intercompany_within_threshold",
                "passed": int(health["disputed_intercompany_count"]) <= int(options.get("max_disputed_intercompany") or 0),
                "detail": {
                    "count": int(health["disputed_intercompany_count"]),
                    "max_allowed": int(options.get("max_disputed_intercompany") or 0),
                },
            },
            {
                "name": "blocked_consolidation_within_threshold",
                "passed": int(health["blocked_consolidation_count"]) <= int(options.get("max_blocked_consolidation") or 0),
                "detail": {
                    "count": int(health["blocked_consolidation_count"]),
                    "max_allowed": int(options.get("max_blocked_consolidation") or 0),
                },
            },
            {
                "name": "open_consolidation_exception_within_threshold",
                "passed": int(health["open_consolidation_exception_count"])
                <= int(options.get("max_open_consolidation_exception") or 0),
                "detail": {
                    "count": int(health["open_consolidation_exception_count"]),
                    "max_allowed": int(options.get("max_open_consolidation_exception") or 0),
                },
            },
            {
                "name": "inbox_failed_within_threshold",
                "passed": int(health["inbox_failed_count"]) <= int(options.get("max_inbox_failed") or 0),
                "detail": {
                    "count": int(health["inbox_failed_count"]),
                    "max_allowed": int(options.get("max_inbox_failed") or 0),
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": int(health["outbox_failed_count"]) <= int(options.get("max_outbox_failed") or 0),
                "detail": {
                    "count": int(health["outbox_failed_count"]),
                    "max_allowed": int(options.get("max_outbox_failed") or 0),
                },
            },
        ]
        go_live_passed = all(bool(item["passed"]) for item in checks)
        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": int(company_id)},
            "go_live_passed": bool(go_live_passed),
            "checks": checks,
            "health": health,
            "certification_ref": {
                "run_id": str(certification.get("run_id") or ""),
                "manifest_hash": str(certification.get("second_manifest_hash") or ""),
            },
        }
        secret = str(os.getenv("PHASE7B_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase7b_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase7b go-live report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(go_live_passed):
            raise CommandError("phase7b go-live gate failed.")
