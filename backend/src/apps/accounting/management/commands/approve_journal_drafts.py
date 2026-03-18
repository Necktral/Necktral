from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.services import approve_journal_drafts


class Command(BaseCommand):
    help = "Aprueba JournalDraft VALIDATED -> APPROVED_FOR_POSTING (Fase 5)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--run-id", type=str, default="")
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--allow-unvalidated", action="store_true", default=False)
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = options.get("company_id")
        run_id = str(options.get("run_id") or "").strip()
        limit = int(options.get("limit") or 200)
        require_passed_validation = not bool(options.get("allow_unvalidated", False))

        try:
            result = approve_journal_drafts(
                company_id=company_id,
                run_id=run_id,
                limit=limit,
                require_passed_validation=require_passed_validation,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "attempted": int(result.attempted),
            "approved": int(result.approved),
            "skipped": int(result.skipped),
            "failed": int(result.failed),
            "errors": result.errors,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))
        if strict and result.failed > 0:
            raise CommandError("Approval batch con errores.")

