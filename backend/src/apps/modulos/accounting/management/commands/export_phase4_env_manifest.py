from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.accounting.certification import build_phase4_evidence, collect_phase4_env_manifest


class Command(BaseCommand):
    help = "Exporta manifiesto de paridad de entorno para certificación real Fase 4A."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        output = str(options.get("output") or "").strip()

        try:
            manifest = collect_phase4_env_manifest(company_id=company_id)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        secret = str(os.getenv("PHASE4_EVIDENCE_SECRET", "")).strip()
        evidence = build_phase4_evidence(payload=manifest, secret=secret)
        raw = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase4 env manifest exported: {path}"))
            return

        self.stdout.write(raw)
