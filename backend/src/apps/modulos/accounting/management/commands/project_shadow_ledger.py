from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.accounting.services import project_pending_shadow_ledger_triggers, project_shadow_ledger_for_run


class Command(BaseCommand):
    help = "Proyecta Shadow Ledger Fase 4A desde triggers CEC.CloseRunPackaged."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=str, default="")
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        run_id = str(options.get("run_id") or "").strip()
        company_id = options.get("company_id")
        limit = int(options.get("limit") or 100)

        if run_id:
            try:
                result = project_shadow_ledger_for_run(run_id=run_id, company_id=company_id)
            except Exception as exc:  # noqa: BLE001
                raise CommandError(str(exc)) from exc
            self.stdout.write(
                self.style.SUCCESS(
                    "shadow_ledger projected: "
                    f"run_id={result.run_id} status={result.close_run_status} "
                    f"events={result.economic_events_created} drafts={result.journal_drafts_generated} "
                    f"exceptions_opened={result.exceptions_opened} blocked={int(result.blocked)} "
                    f"manifest_hash={result.manifest_hash}"
                )
            )
            return

        try:
            summary = project_pending_shadow_ledger_triggers(limit=limit, company_id=company_id)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "shadow_ledger batch: "
                f"attempted={summary.attempted} processed={summary.processed} "
                f"blocked={summary.blocked} skipped={summary.skipped} failed={summary.failed}"
            )
        )
