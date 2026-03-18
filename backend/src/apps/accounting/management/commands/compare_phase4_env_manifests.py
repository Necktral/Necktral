from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.certification import compare_phase4_env_manifests


class Command(BaseCommand):
    help = "Compara manifiestos de paridad Fase 4A (staging vs producción) y falla en drift."

    def add_arguments(self, parser):
        parser.add_argument("--left", type=str, required=True)
        parser.add_argument("--right", type=str, required=True)
        parser.add_argument("--no-strict", action="store_true", default=False)

    def _read_json(self, path: str) -> dict:
        p = Path(path)
        if not p.exists():
            raise CommandError(f"archivo no encontrado: {p}")
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"JSON inválido en {p}: {exc}") from exc

    def handle(self, *args, **options):
        left = self._read_json(options["left"])
        right = self._read_json(options["right"])
        strict = not bool(options.get("no_strict", False))

        mismatches = compare_phase4_env_manifests(left=left, right=right)
        if not mismatches:
            self.stdout.write(self.style.SUCCESS("phase4 parity ok: sin drift"))
            return

        lines = ["phase4 parity drift detectado:"]
        for row in mismatches:
            lines.append(f"- {row['field']}: left={row['left']} right={row['right']}")
        message = "\n".join(lines)
        if strict:
            raise CommandError(message)
        self.stdout.write(message)
