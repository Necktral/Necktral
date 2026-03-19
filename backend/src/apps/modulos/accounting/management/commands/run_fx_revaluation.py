from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.accounting.phase7 import Phase7ValidationError, run_fx_revaluation


class Command(BaseCommand):
    help = "Ejecuta revaluación FX contable para un periodo (Fase 7A)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--account-code", action="append", dest="account_codes", default=[])
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        year = int(options["year"])
        month = int(options["month"])
        strict = not bool(options.get("no_strict", False))
        account_codes = [str(x).strip().upper() for x in (options.get("account_codes") or []) if str(x).strip()]

        try:
            result = run_fx_revaluation(
                company_id=company_id,
                year=year,
                month=month,
                strict=strict,
                scope_account_codes=account_codes,
            )
        except Phase7ValidationError as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        payload = {
            "run_id": str(result.run_id),
            "status": str(result.status),
            "idempotent": bool(result.idempotent),
            "entries_created": int(result.entries_created),
            "issues_count": int(result.issues_count),
            "summary": result.summary_json,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))
        if strict and str(result.status) == "BLOCKED":
            raise CommandError("FX revaluation blocked.")
