from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.certification_phase12 import compare_phase12_env_manifests


class Command(BaseCommand):
    help = "Compara manifiestos Fase 12 y detecta drift de paridad."

    def add_arguments(self, parser):
        parser.add_argument("--left", type=str, required=True)
        parser.add_argument("--right", type=str, required=True)
        parser.add_argument("--strict", action="store_true", default=False)

    @staticmethod
    def _read(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            raise CommandError(f"archivo no encontrado: {p}")
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"JSON inválido en {p}: {exc}") from exc
        if not isinstance(payload, dict):
            raise CommandError(f"JSON inválido en {p}: se esperaba objeto")
        return payload

    def handle(self, *args, **options):
        left = self._read(str(options["left"]))
        right = self._read(str(options["right"]))
        mismatches = compare_phase12_env_manifests(left=left, right=right)
        payload = {
            "drift_detected": bool(len(mismatches) > 0),
            "mismatches_count": int(len(mismatches)),
            "mismatches": mismatches,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if bool(options.get("strict", False)) and mismatches:
            raise CommandError("phase12 manifest drift detected.")
