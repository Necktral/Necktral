from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _parse_iso_datetime(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_iso_date(raw: str) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Verifica go-live operacional de Fase 5 (estabilidad diaria + performance gate)."
    VALID_REVIEW_STATUS = {"OBSERVED", "APPROVED", "FINAL_APPROVED"}
    REQUIRED_OWNER_ROLES = ("FUNCTIONAL", "TECHNICAL")
    OWNER_APPROVAL_STATUS = {"APPROVED", "FINAL_APPROVED"}
    VALID_EXCEPTION_TYPE = {"FORCE_MAJEURE"}
    VALID_EXCEPTION_STATUS = {"APPROVED", "FINAL_APPROVED"}

    def add_arguments(self, parser):
        parser.add_argument("--evidence-dir", type=str, required=True)
        parser.add_argument("--pilot-pattern", type=str, default="**/pilot_stage3*.json")
        parser.add_argument("--gate-pattern", type=str, default="**/gate_report.json")
        parser.add_argument("--review-pattern", type=str, default="**/operational_go_live_review_*.json")
        parser.add_argument("--final-signoff-pattern", type=str, default="**/operational_go_live_final_signoff.json")
        parser.add_argument("--excused-day-pattern", type=str, default="**/operational_go_live_excused_day_*.json")
        parser.add_argument("--required-days", type=int, default=7)
        parser.add_argument("--max-failed-outbox", type=int, default=0)
        parser.add_argument("--max-reconciliation-mismatch", type=int, default=0)
        parser.add_argument("--max-draft-exception", type=int, default=0)
        parser.add_argument("--max-pending-operational", type=int, default=0)
        parser.add_argument("--max-fuel-pending", type=int, default=0)
        parser.add_argument("--max-fuel-failed", type=int, default=0)
        parser.add_argument("--allow-excused-days", action="store_true", default=False)
        parser.add_argument("--max-excused-days", type=int, default=0)
        parser.add_argument("--max-calendar-days", type=int, default=0)
        parser.add_argument("--require-performance-pass", dest="require_performance_pass", action="store_true", default=True)
        parser.add_argument("--no-require-performance-pass", dest="require_performance_pass", action="store_false")
        parser.add_argument("--require-close-ok", action="store_true", default=False)
        parser.add_argument("--require-owner-approvals", dest="require_owner_approvals", action="store_true", default=True)
        parser.add_argument("--no-require-owner-approvals", dest="require_owner_approvals", action="store_false")
        parser.add_argument("--require-final-signoff", dest="require_final_signoff", action="store_true", default=True)
        parser.add_argument("--no-require-final-signoff", dest="require_final_signoff", action="store_false")
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"JSON inválido en {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise CommandError(f"JSON inválido en {path}: se esperaba objeto")
        return payload

    @staticmethod
    def _reconciliation_mismatch_count(snapshot: dict[str, Any]) -> int:
        reconciliation = snapshot.get("reconciliation", {}) if isinstance(snapshot, dict) else {}
        rows = reconciliation.get("by_event_type", []) if isinstance(reconciliation, dict) else []
        if not isinstance(rows, list):
            return 0
        mismatches = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            operational_count = int(row.get("operational_count") or 0)
            linked_count = int(row.get("linked_count") or 0)
            operational_amount = _to_decimal(row.get("operational_amount"))
            draft_amount = _to_decimal(row.get("draft_amount"))
            if operational_count != linked_count or operational_amount != draft_amount:
                mismatches += 1
        return int(mismatches)

    @staticmethod
    def _is_day_stable(*, row: dict[str, Any], options: dict[str, Any]) -> bool:
        return bool(
            int(row["failed_outbox_total"]) <= int(options["max_failed_outbox"])
            and int(row["reconciliation_mismatch_count"]) <= int(options["max_reconciliation_mismatch"])
            and int(row["draft_exception_count"]) <= int(options["max_draft_exception"])
            and int(row["pending_operational_events_count"]) <= int(options["max_pending_operational"])
            and int(row["fuel_pending_count"]) <= int(options["max_fuel_pending"])
            and int(row["fuel_failed_count"]) <= int(options["max_fuel_failed"])
            and (not bool(options["require_close_ok"]) or bool(row["close_ok"]))
        )

    @staticmethod
    def _stable_streak_days(*, rows_desc: list[dict[str, Any]]) -> int:
        if not rows_desc:
            return 0
        expected_day = rows_desc[0]["day"]
        streak = 0
        for row in rows_desc:
            if row["day"] != expected_day:
                break
            if not bool(row["stable"]):
                break
            streak += 1
            expected_day = expected_day - timedelta(days=1)
        return int(streak)

    def _collect_excused_rows(
        self,
        *,
        evidence_dir: Path,
        excused_day_pattern: str,
    ) -> tuple[dict[date, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        excused_files = sorted(evidence_dir.glob(excused_day_pattern))
        excused_by_day: dict[date, dict[str, Any]] = {}
        rows: list[dict[str, Any]] = []
        invalid_rows: list[dict[str, Any]] = []

        for path in excused_files:
            payload = self._read_json(path)
            generated_at = _parse_iso_datetime(str(payload.get("generated_at") or ""))
            if generated_at is None:
                generated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.get_current_timezone())

            exception_date = _parse_iso_date(
                str(payload.get("exception_date") or payload.get("excused_date") or payload.get("date") or "")
            )
            exception_type = str(payload.get("exception_type") or payload.get("type") or "").strip().upper()
            status = str(payload.get("status") or "").strip().upper()
            if exception_date is None or exception_type not in self.VALID_EXCEPTION_TYPE or status not in self.VALID_EXCEPTION_STATUS:
                invalid_rows.append(
                    {
                        "path": str(path),
                        "exception_date": str(exception_date.isoformat()) if exception_date else "",
                        "exception_type": exception_type,
                        "status": status,
                    }
                )
                continue

            linked_evidence_raw = payload.get("linked_evidence")
            if isinstance(linked_evidence_raw, list):
                linked_evidence = [str(x).strip() for x in linked_evidence_raw if str(x).strip()]
            elif str(linked_evidence_raw or "").strip():
                linked_evidence = [str(linked_evidence_raw).strip()]
            else:
                linked_evidence = []

            row = {
                "path": str(path),
                "file": str(path.name),
                "day": exception_date,
                "generated_at": generated_at,
                "exception_type": exception_type,
                "status": status,
                "reported_by": str(payload.get("reported_by") or payload.get("reviewer") or "").strip(),
                "approved_by": str(payload.get("approved_by") or "").strip(),
                "summary": str(payload.get("summary") or payload.get("reason") or "").strip(),
                "impact": str(payload.get("impact") or "").strip(),
                "linked_evidence": linked_evidence,
            }
            rows.append(row)
            current = excused_by_day.get(exception_date)
            if current is None or row["generated_at"] > current["generated_at"]:
                excused_by_day[exception_date] = row

        rows.sort(key=lambda row: (row["day"], row["generated_at"], row["file"]))
        return excused_by_day, rows, invalid_rows

    @staticmethod
    def _stable_streak_with_excused(
        *,
        day_rows: dict[date, dict[str, Any]],
        excused_by_day: dict[date, dict[str, Any]],
        required_days: int,
    ) -> dict[str, Any]:
        all_days = set(day_rows.keys()) | set(excused_by_day.keys())
        if not all_days:
            return {
                "effective_streak_days": 0,
                "calendar_span_days": 0,
                "excused_days_used": 0,
                "trace": [],
            }

        current_day = max(all_days)
        effective_streak = 0
        calendar_span = 0
        excused_used = 0
        trace: list[dict[str, Any]] = []

        for _ in range(730):
            row = day_rows.get(current_day)
            excused = excused_by_day.get(current_day)
            if row is None and excused is None:
                break

            calendar_span += 1
            if row is not None and bool(row.get("stable")):
                effective_streak += 1
                trace.append(
                    {
                        "day": current_day.isoformat(),
                        "state": "STABLE",
                        "path": str(row.get("path") or ""),
                    }
                )
            elif excused is not None:
                excused_used += 1
                effective_streak += 1
                trace.append(
                    {
                        "day": current_day.isoformat(),
                        "state": "EXCUSED_FORCE_MAJEURE",
                        "path": str(excused.get("path") or ""),
                        "exception_type": str(excused.get("exception_type") or ""),
                    }
                )
            else:
                trace.append(
                    {
                        "day": current_day.isoformat(),
                        "state": "UNSTABLE",
                        "path": str((row or {}).get("path") or ""),
                    }
                )
                break

            if effective_streak >= required_days:
                break

            current_day = current_day - timedelta(days=1)

        return {
            "effective_streak_days": int(effective_streak),
            "calendar_span_days": int(calendar_span),
            "excused_days_used": int(excused_used),
            "trace": trace,
        }

    def _collect_review_rows(
        self,
        *,
        evidence_dir: Path,
        review_pattern: str,
        final_signoff_pattern: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        review_files = set(evidence_dir.glob(review_pattern))
        review_files.update(evidence_dir.glob(final_signoff_pattern))

        rows: list[dict[str, Any]] = []
        invalid_rows: list[dict[str, Any]] = []
        for path in sorted(review_files):
            payload = self._read_json(path)
            generated_at = _parse_iso_datetime(str(payload.get("generated_at") or ""))
            if generated_at is None:
                generated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.get_current_timezone())

            review_date = _parse_iso_date(str(payload.get("review_date") or ""))
            if review_date is None:
                review_date = generated_at.date()

            role = str(payload.get("role") or "").strip().upper()
            status = str(payload.get("status") or "").strip().upper()
            linked_evidence_raw = payload.get("linked_evidence")
            if isinstance(linked_evidence_raw, list):
                linked_evidence = [str(x).strip() for x in linked_evidence_raw if str(x).strip()]
            elif str(linked_evidence_raw or "").strip():
                linked_evidence = [str(linked_evidence_raw).strip()]
            else:
                linked_evidence = []

            row = {
                "path": str(path),
                "file": str(path.name),
                "review_date": str(review_date.isoformat()),
                "generated_at": generated_at,
                "reviewer": str(payload.get("reviewer") or "").strip(),
                "role": role,
                "status": status,
                "summary": str(payload.get("summary") or "").strip(),
                "linked_evidence": linked_evidence,
                "final_signoff": bool(payload.get("final_signoff")) or status == "FINAL_APPROVED",
            }
            if role not in self.REQUIRED_OWNER_ROLES or status not in self.VALID_REVIEW_STATUS:
                invalid_rows.append({"path": row["path"], "role": role, "status": status})
                continue
            rows.append(row)

        rows.sort(key=lambda row: (str(row["review_date"]), row["generated_at"], str(row["file"])))
        return rows, invalid_rows

    @staticmethod
    def _review_row_for_report(row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        return {
            "file": str(row["file"]),
            "path": str(row["path"]),
            "review_date": str(row["review_date"]),
            "generated_at": row["generated_at"].isoformat(),
            "reviewer": str(row["reviewer"]),
            "role": str(row["role"]),
            "status": str(row["status"]),
            "summary": str(row["summary"]),
            "linked_evidence": list(row["linked_evidence"]),
            "final_signoff": bool(row["final_signoff"]),
        }

    @staticmethod
    def _excused_row_for_report(row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        day = row.get("day")
        generated_at_raw = row.get("generated_at")
        generated_at = generated_at_raw.isoformat() if isinstance(generated_at_raw, datetime) else str(generated_at_raw or "")
        return {
            "file": str(row.get("file") or ""),
            "path": str(row.get("path") or ""),
            "day": str(day.isoformat()) if isinstance(day, date) else "",
            "generated_at": generated_at,
            "exception_type": str(row.get("exception_type") or ""),
            "status": str(row.get("status") or ""),
            "reported_by": str(row.get("reported_by") or ""),
            "approved_by": str(row.get("approved_by") or ""),
            "summary": str(row.get("summary") or ""),
            "impact": str(row.get("impact") or ""),
            "linked_evidence": list(row.get("linked_evidence") or []),
        }

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        required_days = max(1, int(options.get("required_days") or 7))
        max_excused_days = max(0, int(options.get("max_excused_days") or 0))
        max_calendar_days = max(0, int(options.get("max_calendar_days") or 0))
        allow_excused_days = bool(options.get("allow_excused_days", False))
        evidence_dir = Path(str(options["evidence_dir"]))
        pilot_pattern = str(options.get("pilot_pattern") or "**/pilot_stage3*.json")
        gate_pattern = str(options.get("gate_pattern") or "**/gate_report.json")
        review_pattern = str(options.get("review_pattern") or "**/operational_go_live_review_*.json")
        final_signoff_pattern = str(options.get("final_signoff_pattern") or "**/operational_go_live_final_signoff.json")
        excused_day_pattern = str(options.get("excused_day_pattern") or "**/operational_go_live_excused_day_*.json")
        output = str(options.get("output") or "").strip()

        if not evidence_dir.exists():
            raise CommandError(f"evidence-dir no existe: {evidence_dir}")

        pilot_files = sorted(evidence_dir.glob(pilot_pattern))
        if not pilot_files:
            raise CommandError(f"no se encontraron evidencias de piloto con patrón {pilot_pattern} en {evidence_dir}")

        day_rows: dict[date, dict[str, Any]] = {}
        for path in pilot_files:
            payload = self._read_json(path)
            snapshot = payload.get("snapshot", {}) if isinstance(payload, dict) else {}
            if not isinstance(snapshot, dict):
                snapshot = {}
            generated_at = _parse_iso_datetime(str(payload.get("generated_at") or snapshot.get("generated_at") or ""))
            if generated_at is None:
                generated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.get_current_timezone())

            rec_summary = (
                snapshot.get("reconciliation", {}).get("summary", {})
                if isinstance(snapshot.get("reconciliation"), dict)
                else {}
            )
            failed_outbox = snapshot.get("failed_outbox", {}) if isinstance(snapshot.get("failed_outbox"), dict) else {}
            fuel = snapshot.get("fuel_compensation", {}) if isinstance(snapshot.get("fuel_compensation"), dict) else {}
            close_attempt = payload.get("close_attempt", {}) if isinstance(payload.get("close_attempt"), dict) else {}

            row = {
                "path": str(path),
                "generated_at": generated_at,
                "day": generated_at.date(),
                "failed_outbox_total": int(failed_outbox.get("total") or 0),
                "failed_outbox_by_module": dict(failed_outbox.get("by_module") or {}),
                "reconciliation_mismatch_count": self._reconciliation_mismatch_count(snapshot),
                "draft_exception_count": int(rec_summary.get("drafts_exception") or 0),
                "pending_operational_events_count": int(rec_summary.get("pending_operational_events") or 0),
                "fuel_pending_count": int(fuel.get("pending_count") or 0),
                "fuel_failed_count": int(fuel.get("failed_count") or 0),
                "close_ok": bool(close_attempt.get("ok")) if close_attempt else False,
            }
            row["stable"] = self._is_day_stable(row=row, options=options)

            current = day_rows.get(row["day"])
            if current is None or row["generated_at"] > current["generated_at"]:
                day_rows[row["day"]] = row

        rows_desc = sorted(day_rows.values(), key=lambda x: x["day"], reverse=True)
        rows_asc = sorted(day_rows.values(), key=lambda x: x["day"])
        excused_by_day, excused_rows, invalid_excused_rows = self._collect_excused_rows(
            evidence_dir=evidence_dir,
            excused_day_pattern=excused_day_pattern,
        )

        strict_stable_streak_days = self._stable_streak_days(rows_desc=rows_desc)
        stable_streak_days = strict_stable_streak_days
        available_days = int(len(rows_desc))
        calendar_span_days = int(strict_stable_streak_days)
        excused_days_used = 0
        streak_trace: list[dict[str, Any]] = []

        if allow_excused_days:
            effective = self._stable_streak_with_excused(
                day_rows=day_rows,
                excused_by_day=excused_by_day,
                required_days=required_days,
            )
            stable_streak_days = int(effective["effective_streak_days"])
            calendar_span_days = int(effective["calendar_span_days"])
            excused_days_used = int(effective["excused_days_used"])
            streak_trace = list(effective.get("trace") or [])
            available_days = int(len(set(day_rows.keys()) | set(excused_by_day.keys())))

        gate_files = sorted(evidence_dir.glob(gate_pattern))
        latest_gate = None
        performance_passed = False
        if gate_files:
            latest_gate_path = max(gate_files, key=lambda p: p.stat().st_mtime)
            latest_gate = self._read_json(latest_gate_path)
            performance_passed = bool(latest_gate.get("passed"))

        review_rows, invalid_review_rows = self._collect_review_rows(
            evidence_dir=evidence_dir,
            review_pattern=review_pattern,
            final_signoff_pattern=final_signoff_pattern,
        )
        latest_review_by_role: dict[str, dict[str, Any]] = {}
        for row in review_rows:
            latest_review_by_role[str(row["role"])] = row

        latest_status_by_role = {
            role: str((latest_review_by_role.get(role) or {}).get("status") or "")
            for role in self.REQUIRED_OWNER_ROLES
        }
        missing_or_unapproved_roles = sorted(
            [
                role
                for role in self.REQUIRED_OWNER_ROLES
                if latest_status_by_role.get(role) not in self.OWNER_APPROVAL_STATUS
            ]
        )
        open_observation_roles = sorted(
            [role for role in self.REQUIRED_OWNER_ROLES if latest_status_by_role.get(role) == "OBSERVED"]
        )
        final_signoff_rows = [row for row in review_rows if bool(row["final_signoff"])]
        latest_final_signoff = final_signoff_rows[-1] if final_signoff_rows else None

        checks = [
            {
                "name": "pilot_days_available",
                "passed": available_days >= required_days,
                "detail": {
                    "available_days": int(available_days),
                    "required_days": int(required_days),
                },
            },
            {
                "name": "stable_streak_days",
                "passed": stable_streak_days >= required_days,
                "detail": {
                    "stable_streak_days": int(stable_streak_days),
                    "strict_stable_streak_days": int(strict_stable_streak_days),
                    "required_days": int(required_days),
                },
            },
            {
                "name": "excused_days_within_limit",
                "passed": (not allow_excused_days) or (excused_days_used <= max_excused_days),
                "detail": {
                    "enabled": bool(allow_excused_days),
                    "excused_days_used": int(excused_days_used),
                    "max_excused_days": int(max_excused_days),
                },
            },
            {
                "name": "calendar_window_within_limit",
                "passed": (not allow_excused_days) or (max_calendar_days <= 0) or (calendar_span_days <= max_calendar_days),
                "detail": {
                    "enabled": bool(allow_excused_days),
                    "calendar_span_days": int(calendar_span_days),
                    "max_calendar_days": int(max_calendar_days),
                },
            },
            {
                "name": "performance_gate_passed",
                "passed": (not bool(options.get("require_performance_pass", True))) or bool(performance_passed),
                "detail": {
                    "required": bool(options.get("require_performance_pass", True)),
                    "gate_found": bool(latest_gate is not None),
                    "gate_passed": bool(performance_passed),
                },
            },
            {
                "name": "owner_approvals_present",
                "passed": (not bool(options.get("require_owner_approvals", True)))
                or len(missing_or_unapproved_roles) == 0,
                "detail": {
                    "required": bool(options.get("require_owner_approvals", True)),
                    "required_roles": list(self.REQUIRED_OWNER_ROLES),
                    "latest_status_by_role": latest_status_by_role,
                    "missing_or_unapproved_roles": missing_or_unapproved_roles,
                },
            },
            {
                "name": "open_observations_resolved",
                "passed": len(open_observation_roles) == 0,
                "detail": {
                    "open_observations_roles": open_observation_roles,
                },
            },
            {
                "name": "final_signoff_present",
                "passed": (not bool(options.get("require_final_signoff", True))) or bool(latest_final_signoff),
                "detail": {
                    "required": bool(options.get("require_final_signoff", True)),
                    "final_signoff_present": bool(latest_final_signoff),
                    "final_signoff_file": str(latest_final_signoff.get("file") or "") if latest_final_signoff else "",
                },
            },
        ]
        go_live_passed = all(bool(x["passed"]) for x in checks)

        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "go_live_passed": bool(go_live_passed),
            "risk_level": "LOW" if go_live_passed else "HIGH",
            "evidence_dir": str(evidence_dir),
            "required_days": int(required_days),
            "excused_day_policy": {
                "allow_excused_days": bool(allow_excused_days),
                "max_excused_days": int(max_excused_days),
                "max_calendar_days": int(max_calendar_days),
                "excused_day_pattern": str(excused_day_pattern),
            },
            "stability_thresholds": {
                "max_failed_outbox": int(options.get("max_failed_outbox") or 0),
                "max_reconciliation_mismatch": int(options.get("max_reconciliation_mismatch") or 0),
                "max_draft_exception": int(options.get("max_draft_exception") or 0),
                "max_pending_operational": int(options.get("max_pending_operational") or 0),
                "max_fuel_pending": int(options.get("max_fuel_pending") or 0),
                "max_fuel_failed": int(options.get("max_fuel_failed") or 0),
                "require_close_ok": bool(options.get("require_close_ok", False)),
            },
            "stability_summary": {
                "available_days": int(available_days),
                "required_days": int(required_days),
                "stable_streak_days": int(stable_streak_days),
                "strict_stable_streak_days": int(strict_stable_streak_days),
                "excused_days_used": int(excused_days_used),
                "calendar_span_days": int(calendar_span_days),
            },
            "checks": checks,
            "stability": [
                {
                    "day": str(row["day"]),
                    "stable": bool(row["stable"]),
                    "path": row["path"],
                    "failed_outbox_total": int(row["failed_outbox_total"]),
                    "reconciliation_mismatch_count": int(row["reconciliation_mismatch_count"]),
                    "draft_exception_count": int(row["draft_exception_count"]),
                    "pending_operational_events_count": int(row["pending_operational_events_count"]),
                    "fuel_pending_count": int(row["fuel_pending_count"]),
                    "fuel_failed_count": int(row["fuel_failed_count"]),
                    "close_ok": bool(row["close_ok"]),
                }
                for row in rows_asc
            ],
            "excused_days_summary": {
                "enabled": bool(allow_excused_days),
                "excused_rows_count": int(len(excused_rows)),
                "excused_days_count": int(len(excused_by_day)),
                "excused_days_used": int(excused_days_used),
                "invalid_excused_rows_count": int(len(invalid_excused_rows)),
                "invalid_excused_rows_sample": invalid_excused_rows[:10],
                "latest_excused_by_day": {
                    str(day.isoformat()): self._excused_row_for_report(excused_by_day.get(day))
                    for day in sorted(excused_by_day.keys())
                },
            },
            "streak_trace": streak_trace,
            "latest_performance_gate": latest_gate or {},
            "review_summary": {
                "required_roles": list(self.REQUIRED_OWNER_ROLES),
                "require_owner_approvals": bool(options.get("require_owner_approvals", True)),
                "require_final_signoff": bool(options.get("require_final_signoff", True)),
                "review_rows_count": int(len(review_rows)),
                "invalid_review_rows_count": int(len(invalid_review_rows)),
                "invalid_review_rows_sample": invalid_review_rows[:10],
                "latest_status_by_role": latest_status_by_role,
                "latest_review_by_role": {
                    role: self._review_row_for_report(latest_review_by_role.get(role))
                    for role in self.REQUIRED_OWNER_ROLES
                },
                "missing_or_unapproved_roles": missing_or_unapproved_roles,
                "open_observations_roles": open_observation_roles,
                "final_signoff_present": bool(latest_final_signoff),
                "final_signoff": self._review_row_for_report(latest_final_signoff),
            },
        }
        raw = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"operational pilot go-live report exported: {out_path}"))
        else:
            self.stdout.write(raw)

        if strict and not go_live_passed:
            raise CommandError("operational pilot go-live gate failed.")
