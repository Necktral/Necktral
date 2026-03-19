from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.iam.models import OrgUnit
from modulos.facturacion.models import FiscalMode
from modulos.facturacion.services import get_or_update_branch_fiscal_config


class Command(BaseCommand):
    help = "Configura modo fiscal por sucursal (A/B/NOOP)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--mode", type=str, required=True, choices=[FiscalMode.A, FiscalMode.B, FiscalMode.NOOP])
        parser.add_argument("--adapter-code", type=str, default="")
        parser.add_argument("--print-required", type=str, default="true")
        parser.add_argument("--strict-integrity", type=str, default="true")
        parser.add_argument("--contingency-max-attempts", type=int, default=5)
        parser.add_argument("--is-active", type=str, default="true")

    def _as_bool(self, value: str) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        mode = str(options["mode"]).upper()

        try:
            company = OrgUnit.objects.get(id=company_id, unit_type=OrgUnit.UnitType.COMPANY)
        except OrgUnit.DoesNotExist as exc:
            raise CommandError(f"company {company_id} not found") from exc
        try:
            branch = OrgUnit.objects.get(id=branch_id, unit_type=OrgUnit.UnitType.BRANCH, parent=company)
        except OrgUnit.DoesNotExist as exc:
            raise CommandError(f"branch {branch_id} not found under company {company_id}") from exc

        cfg = get_or_update_branch_fiscal_config(
            company=company,
            branch=branch,
            data={
                "fiscal_mode": mode,
                "adapter_code": str(options.get("adapter_code") or ""),
                "print_required": self._as_bool(str(options.get("print_required") or "true")),
                "strict_integrity": self._as_bool(str(options.get("strict_integrity") or "true")),
                "contingency_max_attempts": int(options.get("contingency_max_attempts") or 5),
                "is_active": self._as_bool(str(options.get("is_active") or "true")),
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"branch fiscal config updated: company={company.id} branch={branch.id} "
                f"mode={cfg.fiscal_mode} adapter={cfg.adapter_code or 'NOOP'} "
                f"print_required={cfg.print_required} max_attempts={cfg.contingency_max_attempts}"
            )
        )
