from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.services import (
    OPERATIONAL_ACCOUNTING_PROJECTOR_CONSUMER,
    project_pending_operational_accounting_links,
)


class Command(BaseCommand):
    help = "Procesa eventos operacionales para enlace contable asincrono (billing/inventory/procurement)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--consumer", type=str, default=OPERATIONAL_ACCOUNTING_PROJECTOR_CONSUMER)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = options.get("company_id")
        limit = int(options.get("limit") or 200)
        consumer = str(options.get("consumer") or OPERATIONAL_ACCOUNTING_PROJECTOR_CONSUMER).strip()
        output = str(options.get("output") or "").strip()

        summary = project_pending_operational_accounting_links(
            company_id=company_id,
            limit=limit,
            actor_user=None,
            consumer=consumer or OPERATIONAL_ACCOUNTING_PROJECTOR_CONSUMER,
        )

        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "company_id": int(company_id) if company_id is not None else None,
            "consumer": consumer or OPERATIONAL_ACCOUNTING_PROJECTOR_CONSUMER,
            "attempted": int(summary.attempted),
            "processed": int(summary.processed),
            "skipped": int(summary.skipped),
            "failed": int(summary.failed),
            "passed": int(summary.failed) == 0,
        }
        raw = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"operational accounting projector report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and int(summary.failed) > 0:
            raise CommandError("operational accounting projector finished with failures.")
