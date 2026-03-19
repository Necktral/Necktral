from __future__ import annotations

import csv
import json
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.accounting.phase7 import (
    Phase7ValidationError,
    balance_sheet_report,
    general_ledger_queryset,
    pnl_report,
    resolve_period_range,
    trial_balance_queryset,
)
from apps.modulos.iam.models import OrgUnit


def _parse_date(val: str) -> date | None:
    raw = str(val or "").strip()
    if not raw:
        return None
    return date.fromisoformat(raw)


class Command(BaseCommand):
    help = "Exporta reportes GL Fase 7A en JSON/CSV."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument(
            "--report",
            type=str,
            required=True,
            choices=["trial_balance", "general_ledger", "pnl", "balance_sheet"],
        )
        parser.add_argument("--account-code", type=str, default="")
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument("--date-from", type=str, default="")
        parser.add_argument("--date-to", type=str, default="")
        parser.add_argument("--as-of", type=str, default="")
        parser.add_argument("--format", type=str, default="json", choices=["json", "csv"])
        parser.add_argument("--output", type=str, default="")

    def _resolve_company(self, company_id: int) -> OrgUnit:
        company = OrgUnit.objects.filter(
            id=int(company_id),
            unit_type=OrgUnit.UnitType.COMPANY,
            is_active=True,
        ).first()
        if company is None:
            raise CommandError(f"company inválida o inactiva: {company_id}")
        return company

    def _to_csv(self, report_type: str, payload: dict) -> str:
        buf = StringIO()
        writer = csv.writer(buf)
        if report_type == "trial_balance":
            writer.writerow(["account_code", "account_name", "account_type", "debit_total", "credit_total"])
            for row in payload["rows"]:
                writer.writerow(
                    [row["account_code"], row["account_name"], row["account_type"], row["debit_total"], row["credit_total"]]
                )
        elif report_type == "general_ledger":
            writer.writerow(
                ["journal_entry_id", "entry_date", "description", "line_no", "currency", "fx_rate", "amount_tx", "debit_base", "credit_base"]
            )
            for row in payload["rows"]:
                writer.writerow(
                    [
                        row["journal_entry_id"],
                        row["entry_date"],
                        row["description"],
                        row["line_no"],
                        row["currency"],
                        row["fx_rate"],
                        row["amount_tx"],
                        row["debit_base"],
                        row["credit_base"],
                    ]
                )
        elif report_type == "pnl":
            writer.writerow(["account_code", "account_name", "account_type", "debit_total", "credit_total", "balance"])
            for row in payload["rows"]:
                writer.writerow(
                    [
                        row["account_code"],
                        row["account_name"],
                        row["account_type"],
                        row["debit_total"],
                        row["credit_total"],
                        row["balance"],
                    ]
                )
            writer.writerow([])
            writer.writerow(["total_revenue", payload["totals"]["revenue"]])
            writer.writerow(["total_expense", payload["totals"]["expense"]])
            writer.writerow(["net_income", payload["totals"]["net_income"]])
        else:
            writer.writerow(["section", "account_code", "account_name", "debit_total", "credit_total", "balance"])
            for section in ("assets", "liabilities", "equity"):
                for row in payload[section]["rows"]:
                    writer.writerow(
                        [
                            section,
                            row["account_code"],
                            row["account_name"],
                            row["debit_total"],
                            row["credit_total"],
                            row["balance"],
                        ]
                    )
                writer.writerow([f"{section}_total", "", "", "", "", payload[section]["total"]])
        return buf.getvalue()

    def handle(self, *args, **options):
        company = self._resolve_company(company_id=int(options["company_id"]))
        report_type = str(options["report"])
        output_format = str(options["format"])
        account_code = str(options.get("account_code") or "").strip().upper()

        try:
            period = resolve_period_range(year=options.get("year"), month=options.get("month"))
            date_from = _parse_date(options.get("date_from") or "")
            date_to = _parse_date(options.get("date_to") or "")
            if period is not None:
                date_from, date_to = period
        except (ValueError, Phase7ValidationError) as exc:
            raise CommandError(str(exc)) from exc

        payload: dict
        try:
            if report_type == "trial_balance":
                qs = trial_balance_queryset(company=company, date_from=date_from, date_to=date_to)
                payload = {
                    "rows": [
                        {
                            "account_code": row["account__code"],
                            "account_name": row["account__name"],
                            "account_type": row["account__account_type"],
                            "debit_total": str(row["debit_total"]),
                            "credit_total": str(row["credit_total"]),
                        }
                        for row in qs
                    ],
                    "filters": {"date_from": str(date_from) if date_from else "", "date_to": str(date_to) if date_to else ""},
                }
            elif report_type == "general_ledger":
                if not account_code:
                    raise CommandError("--account-code es requerido para general_ledger.")
                qs = general_ledger_queryset(company=company, account_code=account_code, date_from=date_from, date_to=date_to)
                payload = {
                    "rows": [
                        {
                            "journal_entry_id": int(row.journal_entry_id),
                            "entry_date": str(row.journal_entry.entry_date),
                            "description": row.journal_entry.description,
                            "line_no": int(row.line_no),
                            "currency": row.currency,
                            "fx_rate": str(row.fx_rate),
                            "amount_tx": str(row.amount_tx),
                            "debit_base": str(row.debit_base),
                            "credit_base": str(row.credit_base),
                        }
                        for row in qs
                    ],
                    "filters": {
                        "account_code": account_code,
                        "date_from": str(date_from) if date_from else "",
                        "date_to": str(date_to) if date_to else "",
                    },
                }
            elif report_type == "pnl":
                payload = pnl_report(company=company, date_from=date_from, date_to=date_to)
            else:
                as_of = _parse_date(options.get("as_of") or "") or date_to or date.today()
                payload = balance_sheet_report(company=company, as_of=as_of)
        except Phase7ValidationError as exc:
            raise CommandError(str(exc)) from exc

        if output_format == "json":
            raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            raw = self._to_csv(report_type, payload)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"report exported: {path}"))
        else:
            self.stdout.write(raw)
