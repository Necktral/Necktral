from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.accounting.certification_phase7 import collect_phase7_env_manifest


class Command(BaseCommand):
    help = "Exporta manifiesto de entorno para paridad Fase 7A."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        output = str(options.get("output") or "").strip()
        try:
            manifest = collect_phase7_env_manifest(company_id=company_id)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        raw = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase7 env manifest exported: {path}"))
        else:
            self.stdout.write(raw)
