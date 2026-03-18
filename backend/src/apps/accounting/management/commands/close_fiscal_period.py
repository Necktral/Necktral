from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.services import close_fiscal_period


class Command(BaseCommand):
    help = "Cierra periodo fiscal contable con gates operativos-contables de reconciliación."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--force", action="store_true", default=False)

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        year = int(options["year"])
        month = int(options["month"])
        force = bool(options.get("force", False))

        try:
            result = close_fiscal_period(
                company_id=company_id,
                year=year,
                month=month,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "company_id": int(result.company_id),
            "year": int(result.year),
            "month": int(result.month),
            "status": result.status,
            "period_id": int(result.period_id),
            "pending_drafts": int(result.pending_drafts),
            "was_already_closed": bool(result.was_already_closed),
            "force_applied": bool(result.force_applied),
            "gate_summary": result.gate_summary,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))
