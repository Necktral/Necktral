from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounting.models import OperationalPostingConfig
from apps.accounting.services import (
    AccountingConflictError,
    build_operational_monitor_snapshot,
    close_fiscal_period,
)
from apps.iam.models import OrgUnit
from apps.integration.services import dispatch_outbox_events


@dataclass(frozen=True)
class _ConfigState:
    posting_mode: str
    enable_billing: bool
    enable_inventory: bool
    auto_post_on_write: bool
    is_active: bool


class Command(BaseCommand):
    help = "Gestiona rollout piloto de posting operacional (stage1/stage2/stage3/status/rollback) por sucursal."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument(
            "--action",
            type=str,
            required=True,
            choices=["status", "stage1", "stage2", "stage3", "rollback"],
        )
        parser.add_argument("--date-from", type=str, default="")
        parser.add_argument("--date-to", type=str, default="")
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument("--attempt-close", action="store_true", default=False)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--cycles", type=int, default=1)
        parser.add_argument("--fuel-limit", type=int, default=200)
        parser.add_argument("--output", type=str, default="")

    @staticmethod
    def _resolve_scope(*, company_id: int, branch_id: int):
        company = OrgUnit.objects.filter(
            id=int(company_id),
            unit_type=OrgUnit.UnitType.COMPANY,
            is_active=True,
        ).first()
        if company is None:
            raise CommandError(f"company inválida o inactiva: {company_id}")

        branch = OrgUnit.objects.filter(
            id=int(branch_id),
            unit_type=OrgUnit.UnitType.BRANCH,
            parent=company,
            is_active=True,
        ).first()
        if branch is None:
            raise CommandError(f"branch inválida o fuera de company={company.id}: {branch_id}")
        return company, branch

    @staticmethod
    def _target_state_for_action(action: str) -> _ConfigState | None:
        if action == "status":
            return None
        if action == "stage1":
            return _ConfigState(
                posting_mode=OperationalPostingConfig.PostingMode.HYBRID,
                enable_billing=False,
                enable_inventory=False,
                auto_post_on_write=False,
                is_active=True,
            )
        if action in {"stage2", "stage3"}:
            return _ConfigState(
                posting_mode=OperationalPostingConfig.PostingMode.HYBRID,
                enable_billing=True,
                enable_inventory=True,
                auto_post_on_write=False,
                is_active=True,
            )
        if action == "rollback":
            return _ConfigState(
                posting_mode=OperationalPostingConfig.PostingMode.DISABLED,
                enable_billing=False,
                enable_inventory=False,
                auto_post_on_write=False,
                is_active=True,
            )
        raise CommandError(f"acción no soportada: {action}")

    @staticmethod
    def _date_range_from_options(*, date_from_raw: str, date_to_raw: str):
        df = str(date_from_raw or "").strip()
        dt = str(date_to_raw or "").strip()
        if not df and not dt:
            return None, None
        if not df or not dt:
            raise CommandError("Debe enviar ambos --date-from y --date-to, o ninguno.")
        date_from = datetime.fromisoformat(df).date()
        date_to = datetime.fromisoformat(dt).date()
        if date_from > date_to:
            raise CommandError("--date-from no puede ser mayor que --date-to.")
        return date_from, date_to

    @staticmethod
    def _config_payload(row: OperationalPostingConfig | None) -> dict:
        if row is None:
            return {}
        return {
            "posting_mode": str(row.posting_mode),
            "enable_billing": bool(row.enable_billing),
            "enable_inventory": bool(row.enable_inventory),
            "auto_post_on_write": bool(row.auto_post_on_write),
            "is_active": bool(row.is_active),
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    @staticmethod
    def _json_default(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return str(value)

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        action = str(options["action"]).strip().lower()
        attempt_close = bool(options.get("attempt_close", False))

        company, branch = self._resolve_scope(company_id=company_id, branch_id=branch_id)
        date_from, date_to = self._date_range_from_options(
            date_from_raw=str(options.get("date_from") or ""),
            date_to_raw=str(options.get("date_to") or ""),
        )

        cfg_before = OperationalPostingConfig.objects.filter(company=company, branch=branch).first()
        cfg_after = cfg_before
        target = self._target_state_for_action(action=action)
        if target is not None:
            with transaction.atomic():
                cfg_after, _ = OperationalPostingConfig.objects.select_for_update().get_or_create(
                    company=company,
                    branch=branch,
                    defaults=asdict(target),
                )
                cfg_after.posting_mode = target.posting_mode
                cfg_after.enable_billing = bool(target.enable_billing)
                cfg_after.enable_inventory = bool(target.enable_inventory)
                cfg_after.auto_post_on_write = bool(target.auto_post_on_write)
                cfg_after.is_active = bool(target.is_active)
                cfg_after.save(
                    update_fields=[
                        "posting_mode",
                        "enable_billing",
                        "enable_inventory",
                        "auto_post_on_write",
                        "is_active",
                        "updated_at",
                    ]
                )

        rollback_cycle = {}
        if action == "rollback":
            try:
                from modulos.estacion_servicios.services import run_fuel_compensation_cycle
            except Exception as exc:  # noqa: BLE001
                raise CommandError(f"No fue posible importar run_fuel_compensation_cycle: {exc}") from exc

            cycles = max(1, int(options.get("cycles") or 1))
            dispatch_limit = max(1, int(options.get("dispatch_limit") or 200))
            fuel_limit = max(1, int(options.get("fuel_limit") or 200))
            cycle_rows: list[dict] = []
            for cycle in range(cycles):
                dispatch_rows = {}
                for module in ("BILLING", "INVENTORY", "ACCOUNTING"):
                    dispatch = dispatch_outbox_events(
                        limit=dispatch_limit,
                        source_module=module,
                    )
                    dispatch_rows[module] = {
                        "attempted": int(dispatch.attempted),
                        "sent": int(dispatch.sent),
                        "retried": int(dispatch.retried),
                        "failed": int(dispatch.failed),
                    }
                fuel = run_fuel_compensation_cycle(
                    company=company,
                    branch=branch,
                    limit=fuel_limit,
                    include_failed=True,
                    actor_user=None,
                )
                cycle_rows.append(
                    {
                        "cycle": int(cycle + 1),
                        "dispatch": dispatch_rows,
                        "fuel_compensation": {
                            "attempted": int(fuel.attempted),
                            "succeeded": int(fuel.succeeded),
                            "failed": int(fuel.failed),
                            "still_pending": int(fuel.still_pending),
                            "errors": fuel.errors,
                        },
                    }
                )
            rollback_cycle = {
                "cycles": int(cycles),
                "dispatch_limit": int(dispatch_limit),
                "fuel_limit": int(fuel_limit),
                "results": cycle_rows,
            }

        close_payload = {}
        if attempt_close:
            year = options.get("year")
            month = options.get("month")
            today = timezone.localdate()
            close_year = int(year or today.year)
            close_month = int(month or today.month)
            try:
                result = close_fiscal_period(
                    company_id=int(company.id),
                    year=close_year,
                    month=close_month,
                    force=bool(options.get("force", False)),
                    actor_user=None,
                )
                close_payload = {
                    "ok": True,
                    "year": int(close_year),
                    "month": int(close_month),
                    "status": str(result.status),
                    "period_id": int(result.period_id),
                    "pending_drafts": int(result.pending_drafts),
                    "was_already_closed": bool(result.was_already_closed),
                    "force_applied": bool(result.force_applied),
                    "gate_summary": result.gate_summary,
                }
            except AccountingConflictError as exc:
                close_payload = {
                    "ok": False,
                    "year": int(close_year),
                    "month": int(close_month),
                    "error": str(exc),
                    "gate_summary": getattr(exc, "gate_summary", None),
                }

        snapshot = build_operational_monitor_snapshot(
            company=company,
            branch=branch,
            date_from=date_from,
            date_to=date_to,
        )
        payload = {
            "generated_at": timezone.now().isoformat(),
            "action": action,
            "company_id": int(company.id),
            "branch_id": int(branch.id),
            "config_before": self._config_payload(cfg_before),
            "config_after": self._config_payload(cfg_after),
            "rollback_cycle": rollback_cycle,
            "close_attempt": close_payload,
            "snapshot": snapshot,
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=self._json_default)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"operational pilot payload exported: {path}"))
            return
        self.stdout.write(raw)
