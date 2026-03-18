from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.services import build_operational_monitor_snapshot
from apps.iam.models import OrgUnit


class Command(BaseCommand):
    help = "Exporta snapshot operacional para performance/piloto (outbox, reconciliación, compensaciones Fuel)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, default=None)
        parser.add_argument("--date-from", type=str, default="")
        parser.add_argument("--date-to", type=str, default="")
        parser.add_argument("--output", type=str, default="")

    @staticmethod
    def _resolve_company_branch(*, company_id: int, branch_id: int | None):
        company = OrgUnit.objects.filter(
            id=int(company_id),
            unit_type=OrgUnit.UnitType.COMPANY,
            is_active=True,
        ).first()
        if company is None:
            raise CommandError(f"company inválida o inactiva: {company_id}")

        if branch_id is None:
            return company, None

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
        branch_id = options.get("branch_id")
        date_from_raw = str(options.get("date_from") or "").strip()
        date_to_raw = str(options.get("date_to") or "").strip()

        date_from = timezone.datetime.fromisoformat(date_from_raw).date() if date_from_raw else None
        date_to = timezone.datetime.fromisoformat(date_to_raw).date() if date_to_raw else None
        if (date_from is None) ^ (date_to is None):
            raise CommandError("Debe enviar ambos --date-from y --date-to, o ninguno.")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise CommandError("--date-from no puede ser mayor que --date-to.")

        company, branch = self._resolve_company_branch(company_id=company_id, branch_id=branch_id)
        payload = build_operational_monitor_snapshot(
            company=company,
            branch=branch,
            date_from=date_from,
            date_to=date_to,
        )
        raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=self._json_default)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"operational snapshot exported: {path}"))
            return

        self.stdout.write(raw)
