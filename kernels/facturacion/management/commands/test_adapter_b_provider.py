from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.iam.models import OrgUnit
from kernels.facturacion.fiscal_adapters import FiscalMode, get_fiscal_adapter, resolve_fiscal_runtime_config


class Command(BaseCommand):
    help = "Prueba conectividad/contrato del provider Adapter B configurado para sucursal."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--series", type=str, default="B")

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        series = str(options.get("series") or "B").strip().upper() or "B"

        company = OrgUnit.objects.filter(id=company_id, unit_type=OrgUnit.UnitType.COMPANY).first()
        if company is None:
            raise CommandError(f"company inválida: {company_id}")
        branch = OrgUnit.objects.filter(id=branch_id, unit_type=OrgUnit.UnitType.BRANCH, parent=company).first()
        if branch is None:
            raise CommandError(f"branch inválida para company={company_id}: {branch_id}")

        cfg = resolve_fiscal_runtime_config(company=company, branch=branch)
        if cfg.mode != FiscalMode.B:
            raise CommandError(f"modo fiscal actual no es B (mode={cfg.mode})")

        adapter = get_fiscal_adapter(company=company, branch=branch)
        try:
            ok = bool(adapter.validate_range_integrity(request=None, branch=branch, series=series))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"provider test failed: {exc}") from exc

        if not ok:
            raise CommandError("provider respondió ok=false en validate_range_integrity")

        self.stdout.write(
            self.style.SUCCESS(
                f"adapter_b provider ok: mode={cfg.mode} adapter_code={cfg.adapter_code} series={series}"
            )
        )
