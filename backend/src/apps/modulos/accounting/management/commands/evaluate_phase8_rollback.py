from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.phase8 import build_phase8_evidence


class Command(BaseCommand):
    help = "Evalúa triggers de rollback F8 y emite reporte formal con acciones recomendadas."

    def add_arguments(self, parser):
        parser.add_argument("--cutover-report", type=str, required=True)
        parser.add_argument("--burnin-reports", type=str, nargs="*", default=[])
        parser.add_argument("--sustained-minutes", type=int, default=15)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--fail-on-rollback", action="store_true", default=False)

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
            raise CommandError(f"JSON inválido en {p}: se esperaba objeto")
        return payload

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _max_counter(report: dict[str, Any], key: str) -> int:
        health = dict(report.get("health") or {})
        p6 = dict(health.get("phase6") or {})
        p7 = dict(health.get("phase7a") or {})
        p7b = dict(health.get("phase7b") or {})
        return max(
            int(p6.get(key) or 0),
            int(p7.get(key) or 0),
            int(p7b.get(key) or 0),
        )

    def handle(self, *args, **options):
        cutover = self._read_json(str(options["cutover_report"]))
        burnin_paths = [str(x).strip() for x in (options.get("burnin_reports") or []) if str(x).strip()]
        burnins = [self._read_json(path) for path in burnin_paths]

        triggers: list[dict[str, Any]] = []
        now = timezone.now()
        sustained_minutes = max(1, int(options.get("sustained_minutes") or 15))

        # Trigger 1: cualquier gate rojo de verify_* o cutover.
        if not bool(cutover.get("cutover_passed")):
            triggers.append(
                {
                    "code": "CUTOVER_GATE_FAILED",
                    "severity": "CRITICAL",
                    "detail": {"cutover_passed": bool(cutover.get("cutover_passed"))},
                }
            )
        for name in ("phase6_gate_valid", "phase7_gate_valid", "phase7b_gate_valid"):
            found = [row for row in (cutover.get("checks") or []) if isinstance(row, dict) and row.get("name") == name]
            if found and not bool(found[0].get("passed")):
                triggers.append(
                    {
                        "code": "VERIFY_GATE_RED",
                        "severity": "CRITICAL",
                        "detail": {"gate_name": name},
                    }
                )

        latest = burnins[-1] if burnins else {}
        latest_dt = self._parse_dt(str(latest.get("generated_at") or "")) if latest else None
        prev = burnins[-2] if len(burnins) > 1 else {}
        prev_dt = self._parse_dt(str(prev.get("generated_at") or "")) if prev else None

        inbox_failed = self._max_counter(latest, "inbox_failed_count") if latest else 0
        outbox_failed = self._max_counter(latest, "outbox_failed_count") if latest else 0

        # Trigger 2: inbox/outbox failed sostenido > 15 minutos.
        sustained_failed = False
        if (inbox_failed > 0 or outbox_failed > 0) and latest_dt is not None:
            if prev_dt is not None:
                prev_inbox = self._max_counter(prev, "inbox_failed_count")
                prev_outbox = self._max_counter(prev, "outbox_failed_count")
                delta = latest_dt - prev_dt
                if delta >= timedelta(minutes=sustained_minutes) and (prev_inbox > 0 or prev_outbox > 0):
                    sustained_failed = True
            else:
                if now - latest_dt >= timedelta(minutes=sustained_minutes):
                    sustained_failed = True
        if sustained_failed:
            triggers.append(
                {
                    "code": "BACKBONE_FAILED_SUSTAINED",
                    "severity": "CRITICAL",
                    "detail": {
                        "inbox_failed": int(inbox_failed),
                        "outbox_failed": int(outbox_failed),
                        "sustained_minutes": sustained_minutes,
                    },
                }
            )

        # Trigger 3: missing lines o stale revaluation > 0.
        if latest:
            health = dict(latest.get("health") or {})
            phase7a = dict(health.get("phase7a") or {})
            missing_lines = int(phase7a.get("missing_lines_count") or 0)
            stale_revaluation = int(phase7a.get("stale_revaluation_count") or 0)
            if missing_lines > 0 or stale_revaluation > 0:
                triggers.append(
                    {
                        "code": "GL_HEALTH_BLOCKER",
                        "severity": "CRITICAL",
                        "detail": {
                            "missing_lines": int(missing_lines),
                            "stale_revaluation": int(stale_revaluation),
                        },
                    }
                )

            # Trigger 4: excepción CEC bloqueante sin mitigación.
            phase6 = dict(health.get("phase6") or {})
            cec_blocking = int(phase6.get("cec_blocking_open_count") or 0)
            if cec_blocking > 0:
                triggers.append(
                    {
                        "code": "CEC_BLOCKING_EXCEPTION_OPEN",
                        "severity": "CRITICAL",
                        "detail": {"cec_blocking_open_count": int(cec_blocking)},
                    }
                )

        rollback_required = len(triggers) > 0
        actions = [
            "Deshabilitar ciclos automáticos de la sucursal piloto.",
            "Revertir a versión anterior del backend.",
            "Re-ejecutar manifests y preflight para validar estado seguro.",
            "Emitir evidencia de incidente y RCA inicial.",
        ]
        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "rollback_required": bool(rollback_required),
            "trigger_count": len(triggers),
            "triggers": triggers,
            "inputs": {
                "cutover_report": str(options["cutover_report"]),
                "burnin_reports": burnin_paths,
                "sustained_minutes": sustained_minutes,
            },
            "recommended_actions": actions if rollback_required else [],
        }

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed = build_phase8_evidence(payload=report, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase8 rollback evaluation exported: {path}"))
        else:
            self.stdout.write(raw)

        if bool(options.get("fail_on_rollback")) and rollback_required:
            raise CommandError("phase8 rollback requerido")
