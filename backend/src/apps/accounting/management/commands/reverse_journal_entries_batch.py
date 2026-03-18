from __future__ import annotations

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounting.services import reverse_journal_entries_batch

User = get_user_model()


class Command(BaseCommand):
    help = "Ejecuta reversa contable masiva por run, periodo o lista explícita de JournalEntry IDs."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--reason", type=str, required=True)
        parser.add_argument("--run-id", type=str, default="")
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument("--entry-id", type=int, action="append", default=[])
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--reversal-date", type=str, default="")
        parser.add_argument("--allow-same-poster", action="store_true", default=False)
        parser.add_argument("--actor-user-id", type=int, default=None)
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        reason = str(options["reason"] or "").strip()
        run_id = str(options.get("run_id") or "").strip()
        year = options.get("year")
        month = options.get("month")
        entry_ids = [int(x) for x in (options.get("entry_id") or []) if int(x) > 0]
        limit = int(options.get("limit") or 200)
        allow_same_poster = bool(options.get("allow_same_poster", False))
        actor_user_id = options.get("actor_user_id")
        reversal_date_raw = str(options.get("reversal_date") or "").strip()

        actor_user = None
        if actor_user_id is not None:
            actor_user = User.objects.filter(id=int(actor_user_id), is_active=True).first()
            if actor_user is None:
                raise CommandError(f"actor-user-id inválido o inactivo: {actor_user_id}")

        reversal_date = None
        if reversal_date_raw:
            try:
                reversal_date = date.fromisoformat(reversal_date_raw)
            except ValueError as exc:
                raise CommandError("reversal-date debe ser YYYY-MM-DD.") from exc

        try:
            result = reverse_journal_entries_batch(
                company_id=company_id,
                reason=reason,
                run_id=run_id,
                year=year,
                month=month,
                entry_ids=entry_ids,
                limit=limit,
                reversal_date=reversal_date,
                allow_same_poster=allow_same_poster,
                actor_user=actor_user,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "attempted": int(result.attempted),
            "reversed": int(result.reversed),
            "idempotent": int(result.idempotent),
            "failed": int(result.failed),
            "errors": result.errors,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))
        if strict and result.failed > 0:
            raise CommandError("Batch reversal con errores.")

