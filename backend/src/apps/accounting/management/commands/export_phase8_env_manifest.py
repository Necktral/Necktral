from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.phase8 import build_phase8_evidence, collect_phase8_env_manifest


class Command(BaseCommand):
    help = "Exporta manifiesto de paridad F8 (go-live producción) agregando F6/F7/F7B scope."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        parent_company_id = int(options["parent_company_id"])
        company_ids = [int(x) for x in (options.get("company_ids") or [])]
        output = str(options.get("output") or "").strip()

        try:
            payload = collect_phase8_env_manifest(
                company_id=company_id,
                branch_id=branch_id,
                parent_company_id=parent_company_id,
                company_ids=company_ids,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed_payload = build_phase8_evidence(payload=payload, secret=secret)
        raw = json.dumps(signed_payload, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase8 env manifest exported: {path}"))
        else:
            self.stdout.write(raw)
