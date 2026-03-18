from __future__ import annotations

import json
import re
from datetime import datetime, time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.accounting.models import ChartOfAccount, IntercompanyTransaction
from apps.accounting.phase7 import (
    Phase7ValidationError,
    general_ledger_queryset,
    resolve_period_range,
    trial_balance_queryset,
)
from apps.iam.models import OrgUnit

SEQ_SCAN_PATTERNS = (
    re.compile(r"\bSeq Scan\b", re.IGNORECASE),
    re.compile(r"\bSCAN\b", re.IGNORECASE),
    re.compile(r"\bTABLE SCAN\b", re.IGNORECASE),
)
INDEX_HINT_PATTERNS = (
    re.compile(r"\bIndex Scan\b", re.IGNORECASE),
    re.compile(r"\bUSING INDEX\b", re.IGNORECASE),
    re.compile(r"\bINDEXED BY\b", re.IGNORECASE),
)


def _contains_seq_scan(plan: str) -> bool:
    upper_plan = str(plan or "")
    has_seq = any(pattern.search(upper_plan) for pattern in SEQ_SCAN_PATTERNS)
    if not has_seq:
        return False
    has_index = any(pattern.search(upper_plan) for pattern in INDEX_HINT_PATTERNS)
    return not has_index


class Command(BaseCommand):
    help = "Genera EXPLAIN de queries financieras/intercompany para hardening de performance."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, default=None)
        parser.add_argument("--account-code", type=str, default="")
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument("--company-ids", type=int, nargs="*", default=[])
        parser.add_argument("--max-critical-scans", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def _resolve_company_branch(self, *, company_id: int, branch_id: int | None) -> tuple[OrgUnit, OrgUnit | None]:
        company = OrgUnit.objects.filter(
            id=int(company_id),
            unit_type=OrgUnit.UnitType.COMPANY,
            is_active=True,
        ).first()
        if company is None:
            raise Phase7ValidationError(f"company inválida o inactiva: {company_id}")
        if branch_id is None:
            return company, None
        branch = OrgUnit.objects.filter(
            id=int(branch_id),
            unit_type=OrgUnit.UnitType.BRANCH,
            parent=company,
            is_active=True,
        ).first()
        if branch is None:
            raise Phase7ValidationError(f"branch inválida o fuera de company={company.id}: {branch_id}")
        return company, branch

    @staticmethod
    def _explain_query(*, name: str, queryset) -> dict:
        sql = str(queryset.query)
        try:
            plan = queryset.explain()
        except Exception as exc:  # noqa: BLE001
            return {
                "name": name,
                "ok": False,
                "sql": sql,
                "plan": "",
                "critical_seq_scan": False,
                "error": str(exc),
            }
        return {
            "name": name,
            "ok": True,
            "sql": sql,
            "plan": plan,
            "critical_seq_scan": _contains_seq_scan(plan),
            "error": "",
        }

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company, branch = self._resolve_company_branch(
            company_id=int(options["company_id"]),
            branch_id=options.get("branch_id"),
        )
        account_code = str(options.get("account_code") or "").strip().upper()
        if not account_code:
            account_code = (
                ChartOfAccount.objects.filter(company=company, is_active=True, is_postable=True)
                .order_by("code")
                .values_list("code", flat=True)
                .first()
                or ""
            )
        if not account_code:
            raise CommandError("No hay account_code disponible para general_ledger explain.")

        period = resolve_period_range(year=options.get("year"), month=options.get("month"))
        if period is None:
            today = timezone.localdate()
            period = resolve_period_range(year=today.year, month=today.month)
        if period is None:
            raise CommandError("No fue posible resolver periodo para explain.")
        date_from, date_to = period

        scope_company_ids = [int(x) for x in (options.get("company_ids") or []) if int(x) > 0]
        if not scope_company_ids:
            scope_company_ids = [int(company.id)]

        start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
        end_dt = timezone.make_aware(datetime.combine(date_to, time.max))
        intercompany_cycle_qs = (
            IntercompanyTransaction.objects.filter(Q(source_company=company) | Q(target_company=company))
            .filter(
                status__in=[
                    IntercompanyTransaction.Status.PENDING,
                    IntercompanyTransaction.Status.DIFFERENCE,
                    IntercompanyTransaction.Status.DISPUTED,
                ]
            )
            .order_by("created_at", "id")
        )
        consolidation_qs = (
            IntercompanyTransaction.objects.filter(
                source_company_id__in=scope_company_ids,
                target_company_id__in=scope_company_ids,
                status__in=[IntercompanyTransaction.Status.CONFIRMED, IntercompanyTransaction.Status.CLOSED],
                created_at__gte=start_dt,
                created_at__lte=end_dt,
            )
            .order_by("created_at", "id")
        )

        explain_rows = [
            self._explain_query(
                name="trial_balance",
                queryset=trial_balance_queryset(
                    company=company,
                    branch=branch,
                    date_from=date_from,
                    date_to=date_to,
                ),
            ),
            self._explain_query(
                name="general_ledger",
                queryset=general_ledger_queryset(
                    company=company,
                    branch=branch,
                    account_code=account_code,
                    date_from=date_from,
                    date_to=date_to,
                ),
            ),
            self._explain_query(name="intercompany_cycle", queryset=intercompany_cycle_qs),
            self._explain_query(name="consolidation_scope", queryset=consolidation_qs),
        ]
        critical_scan_count = int(sum(1 for row in explain_rows if bool(row.get("critical_seq_scan"))))
        failed_explains_count = int(sum(1 for row in explain_rows if not bool(row.get("ok"))))
        max_critical_scans = int(options.get("max_critical_scans") or 0)

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "scope": {
                "company_id": int(company.id),
                "branch_id": int(branch.id) if branch is not None else None,
                "period": {
                    "date_from": str(date_from),
                    "date_to": str(date_to),
                },
                "account_code": account_code,
                "company_ids": scope_company_ids,
            },
            "results": explain_rows,
            "summary": {
                "queries": int(len(explain_rows)),
                "failed_explains": failed_explains_count,
                "critical_seq_scans": critical_scan_count,
                "max_critical_scans": max_critical_scans,
                "passed": bool(
                    failed_explains_count == 0 and critical_scan_count <= max_critical_scans
                ),
            },
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"financial explain report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(payload["summary"]["passed"]):
            raise CommandError("financial explain gate failed.")
