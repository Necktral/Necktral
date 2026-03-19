from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.test import RequestFactory

from apps.modulos.audit.integrity import verify_queryset
from apps.modulos.audit.models import AuditEvent
from apps.modulos.audit.writer import write_event


class Command(BaseCommand):
    help = "Verifica integridad de auditoría (hash/prev_hash/firma) por partición."

    def _seed_minimal_system_chain(self) -> None:
        rf = RequestFactory()
        req = rf.get("/qa/audit-seed-minimal", HTTP_USER_AGENT="qa")
        req.META["REMOTE_ADDR"] = "127.0.0.1"

        # Usamos un event_type permitido y sujeto vacío (válido por contrato).
        write_event(
            request=req,
            event_type="RBAC_SEEDED_V01",
            reason_code="OK",
            actor_user=None,
            subject_type="",
            subject_id="",
            module="AUDIT",
        )
        write_event(
            request=req,
            event_type="RBAC_SEEDED_V01",
            reason_code="OK",
            actor_user=None,
            subject_type="",
            subject_id="",
            module="AUDIT",
        )

    def add_arguments(self, parser):
        parser.add_argument(
            "--partition-key",
            dest="partition_key",
            default=None,
            help="Partición específica (por ejemplo SYSTEM o COMPANY:123).",
        )
        parser.add_argument(
            "--format",
            dest="format",
            choices=["json", "text"],
            default="json",
            help="Formato de salida.",
        )
        parser.add_argument(
            "--output",
            dest="output",
            default=None,
            help="Ruta de archivo donde escribir el reporte.",
        )
        parser.add_argument(
            "--no-fail",
            action="store_true",
            help="No retornar exit code != 0 aunque existan errores.",
        )
        parser.add_argument(
            "--seed-minimal",
            action="store_true",
            help="Si no hay eventos, siembra una cadena mínima en SYSTEM antes de verificar.",
        )

    def handle(self, *args, **options):
        partition_key = options.get("partition_key")
        fmt = options.get("format")
        output = options.get("output")
        no_fail = bool(options.get("no_fail"))
        seed_minimal = bool(options.get("seed_minimal"))

        if seed_minimal and partition_key not in (None, "SYSTEM"):
            self.stderr.write("--seed-minimal solo soporta partition_key SYSTEM (o sin filtro).")
            raise SystemExit(2)

        if seed_minimal and not AuditEvent.objects.filter(partition_key="SYSTEM").exists():
            self._seed_minimal_system_chain()

        qs = AuditEvent.objects.all()
        if partition_key:
            qs = qs.filter(partition_key=partition_key)

        report = verify_queryset(qs)
        payload = report.to_dict()

        if fmt == "json":
            rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
        else:
            lines = [
                f"ok={payload['ok']} partitions={payload['partitions_scanned']} events={payload['events_scanned']}",
                f"errors={len(payload['errors'])}",
            ]
            for e in payload["errors"]:
                lines.append(
                    f"- {e['partition_key']} {e['event_id']} {e['code']}: {e['message']} (expected={e.get('expected')}, got={e.get('got')})"
                )
            rendered = "\n".join(lines)

        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered + "\n", encoding="utf-8")
        else:
            self.stdout.write(rendered)

        if (not payload["ok"]) and (not no_fail):
            raise SystemExit(2)
