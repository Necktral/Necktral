from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.certification_phase7 import compare_phase7_env_manifests


class Command(BaseCommand):
    help = "Compara manifiestos de paridad Fase 7A."

    def add_arguments(self, parser):
        parser.add_argument("--left", type=str, required=True)
        parser.add_argument("--right", type=str, required=True)
        parser.add_argument("--no-strict", action="store_true", default=False)

    @staticmethod
    def _read_json(path: str) -> dict:
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
        strict = not bool(options.get("no_strict", False))
        left = self._read_json(options["left"])
        right = self._read_json(options["right"])
        mismatches = compare_phase7_env_manifests(left=left, right=right)
        payload = {"passed": len(mismatches) == 0, "mismatches": mismatches}
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if strict and mismatches:
            raise CommandError("phase7 env parity failed.")
