from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.accounting.phase8 import compare_phase8_env_manifests


class Command(BaseCommand):
    help = "Compara manifiestos F8 y falla en drift si --strict."

    def add_arguments(self, parser):
        parser.add_argument("--left", type=str, required=True)
        parser.add_argument("--right", type=str, required=True)
        parser.add_argument("--strict", action="store_true", default=False)

    def _read_json(self, path: str) -> dict:
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
        left = self._read_json(options["left"])
        right = self._read_json(options["right"])
        mismatches = compare_phase8_env_manifests(left=left, right=right)

        if mismatches:
            self.stdout.write(json.dumps({"ok": False, "mismatches": mismatches}, ensure_ascii=False, indent=2))
            if bool(options.get("strict")):
                raise CommandError("phase8 parity drift detected")
            return

        self.stdout.write(self.style.SUCCESS("phase8 parity ok: no drift"))
