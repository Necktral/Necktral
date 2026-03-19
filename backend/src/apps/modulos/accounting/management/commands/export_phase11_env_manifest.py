from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.accounting.certification_phase11 import collect_phase11_env_manifest


class Command(BaseCommand):
    help = "Exporta manifiesto de entorno Fase 11 (intercompany avanzado)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        output = str(options.get("output") or "").strip()
        try:
            manifest = collect_phase11_env_manifest(company_id=company_id, branch_id=branch_id)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        raw = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase11 env manifest exported: {path}"))
            return
        self.stdout.write(raw)
