from __future__ import annotations

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounting.services import reverse_journal_entry

User = get_user_model()


class Command(BaseCommand):
    help = "Genera reversa contable de JournalEntry (sin editar histórico)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--entry-id", type=int, required=True)
        parser.add_argument("--reason", type=str, required=True)
        parser.add_argument("--reversal-date", type=str, default="")
        parser.add_argument("--allow-same-poster", action="store_true", default=False)
        parser.add_argument("--actor-user-id", type=int, default=None)

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        entry_id = int(options["entry_id"])
        reason = str(options["reason"] or "").strip()
        reversal_date_raw = str(options.get("reversal_date") or "").strip()
        allow_same_poster = bool(options.get("allow_same_poster", False))
        actor_user_id = options.get("actor_user_id")

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
            result = reverse_journal_entry(
                company_id=company_id,
                journal_entry_id=entry_id,
                reason=reason,
                reversal_date=reversal_date,
                allow_same_poster=allow_same_poster,
                actor_user=actor_user,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "original_entry_id": int(result.original_entry_id),
            "reversal_entry_id": int(result.reversal_entry_id),
            "period_id": int(result.period_id),
            "period_year": int(result.period_year),
            "period_month": int(result.period_month),
            "idempotent": bool(result.idempotent),
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))

