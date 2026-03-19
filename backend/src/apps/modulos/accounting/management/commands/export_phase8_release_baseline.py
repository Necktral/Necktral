from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.phase8 import build_phase8_evidence, collect_phase8_env_manifest


class Command(BaseCommand):
    help = "Congela baseline de release F8 (imagen backend + hashes de migraciones/flags/permisos)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--backend-image", type=str, default="")
        parser.add_argument("--release-version", type=str, default="")
        parser.add_argument("--environment", type=str, default="")
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        parent_company_id = int(options["parent_company_id"])
        company_ids = [int(x) for x in (options.get("company_ids") or [])]
        backend_image = str(options.get("backend_image") or os.getenv("BACKEND_IMAGE", "")).strip()
        release_version = str(options.get("release_version") or os.getenv("RELEASE_VERSION", "")).strip()
        environment = str(options.get("environment") or os.getenv("APP_ENV", "")).strip()
        output = str(options.get("output") or "").strip()

        try:
            manifest = collect_phase8_env_manifest(
                company_id=company_id,
                branch_id=branch_id,
                parent_company_id=parent_company_id,
                company_ids=company_ids,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        baseline = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": dict(manifest.get("pilot_scope") or {}),
            "release": {
                "backend_image": backend_image,
                "release_version": release_version,
                "environment": environment,
                "phase6_app_version": str((manifest.get("phase6") or {}).get("app_version") or ""),
                "phase6_git_sha": str((manifest.get("phase6") or {}).get("git_commit_sha") or ""),
                "phase7_app_version": str((manifest.get("phase7") or {}).get("app_version") or ""),
                "phase7_git_sha": str((manifest.get("phase7") or {}).get("git_commit_sha") or ""),
            },
            "baseline_hashes": {
                "phase6_migrations_hash": str((manifest.get("phase6") or {}).get("migrations_hash") or ""),
                "phase6_required_permissions_hash": str((manifest.get("phase6") or {}).get("required_permissions_hash") or ""),
                "phase6_branch_fiscal_config_hash": str((manifest.get("phase6") or {}).get("branch_fiscal_config_hash") or ""),
                "phase7_migrations_hash": str((manifest.get("phase7") or {}).get("migrations_hash") or ""),
                "phase7_required_permissions_hash": str((manifest.get("phase7") or {}).get("required_permissions_hash") or ""),
                "phase7_accounting_config_hash": str((manifest.get("phase7") or {}).get("accounting_config_hash") or ""),
                "phase7_chart_of_accounts_hash": str((manifest.get("phase7") or {}).get("chart_of_accounts_hash") or ""),
                "phase8_parity_fingerprint": str(manifest.get("parity_fingerprint") or ""),
            },
        }

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed = build_phase8_evidence(payload=baseline, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase8 release baseline exported: {path}"))
        else:
            self.stdout.write(raw)
