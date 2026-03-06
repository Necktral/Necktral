from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class PermissionMeta:
    owner_team: str
    risk_level: str
    default_roles: tuple[str, ...]
    expires_at: date | None = None


_PERMS: dict[str, PermissionMeta] = {}


def register(
    code: str,
    *,
    owner_team: str = "core",
    risk_level: str = "MED",
    default_roles: Iterable[str] = (),
    expires_at: date | None = None,
) -> None:
    if code in _PERMS:
        raise RuntimeError(f"permiso duplicado en registry: {code}")
    _PERMS[code] = PermissionMeta(
        owner_team=owner_team,
        risk_level=risk_level,
        default_roles=tuple(default_roles),
        expires_at=expires_at,
    )


# ORG
register("org.company.create", owner_team="org", risk_level="HIGH", default_roles=("company_admin",))
register("org.company.read", owner_team="org", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("org.company.update", owner_team="org", risk_level="HIGH", default_roles=("company_admin",))
register("org.branch.read", owner_team="org", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("org.branch.create", owner_team="org", risk_level="HIGH", default_roles=("company_admin",))
register("org.branch.update", owner_team="org", risk_level="HIGH", default_roles=("company_admin", "branch_manager"))

# IAM
register("iam.users.create", owner_team="iam", risk_level="HIGH", default_roles=("company_admin", "hr_manager"))

# HR
register("hr.position.read", owner_team="hr", risk_level="LOW", default_roles=("company_admin", "hr_manager", "hr_clerk"))
register("hr.position.create", owner_team="hr", risk_level="MED", default_roles=("company_admin", "hr_manager"))
register("hr.position.update", owner_team="hr", risk_level="MED", default_roles=("company_admin", "hr_manager"))
register("hr.position.roles.update", owner_team="hr", risk_level="HIGH", default_roles=("company_admin", "hr_manager"))
register("hr.employee.read", owner_team="hr", risk_level="LOW", default_roles=("company_admin", "hr_manager", "hr_clerk"))
register("hr.employee.create", owner_team="hr", risk_level="MED", default_roles=("company_admin", "hr_manager"))
register("hr.employee.update", owner_team="hr", risk_level="MED", default_roles=("company_admin", "hr_manager", "hr_clerk"))
register("hr.assignment.read", owner_team="hr", risk_level="LOW", default_roles=("company_admin", "hr_manager", "hr_clerk"))
register("hr.assignment.create", owner_team="hr", risk_level="MED", default_roles=("company_admin", "hr_manager"))
register("hr.assignment.end", owner_team="hr", risk_level="MED", default_roles=("company_admin", "hr_manager"))

# RBAC
register("rbac.roles.read", owner_team="rbac", risk_level="LOW", default_roles=("company_admin",))
register("rbac.roles.update", owner_team="rbac", risk_level="HIGH", default_roles=("company_admin",))
register("rbac.permissions.read", owner_team="rbac", risk_level="LOW", default_roles=("company_admin",))
register("rbac.permissions.update", owner_team="rbac", risk_level="HIGH", default_roles=("company_admin",))
register("rbac.assignments.read", owner_team="rbac", risk_level="LOW", default_roles=("company_admin",))
register("rbac.assignments.update", owner_team="rbac", risk_level="HIGH", default_roles=("company_admin",))
register(
    "auth.lockout.reset",
    owner_team="auth",
    risk_level="HIGH",
    default_roles=("company_admin",),
    expires_at=date(2030, 12, 31),
)

# Auditoria
register("audit.read", owner_team="audit", risk_level="MED", default_roles=("company_admin", "auditor"))
register("audit.export", owner_team="audit", risk_level="HIGH", default_roles=("company_admin", "auditor"))

# Sync
register("sync.device.enroll", owner_team="sync", risk_level="HIGH", default_roles=("company_admin", "sync_admin"))
register("sync.device.revoke", owner_team="sync", risk_level="HIGH", default_roles=("company_admin", "sync_admin"))
register("sync.batch.receive", owner_team="sync", risk_level="HIGH", default_roles=("company_admin", "sync_admin"))

# INVENTORY (granular + legacy)
register("inventory.item.read", owner_team="inventory", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("inventory.item.create", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.item.update", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.warehouse.create", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.balance.read", owner_team="inventory", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("inventory.movement.receive", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.movement.issue", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.movement.adjust", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.transfer.create", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.movement.post", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.adjustment.create", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("inventory.read", owner_team="inventory", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("inventory.write", owner_team="inventory", risk_level="MED", default_roles=("company_admin", "branch_manager"))

# BILLING (granular + legacy)
register("billing.customer.read", owner_team="billing", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("billing.customer.create", owner_team="billing", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("billing.customer.update", owner_team="billing", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("billing.invoice.read", owner_team="billing", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("billing.invoice.create", owner_team="billing", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("billing.invoice.issue", owner_team="billing", risk_level="HIGH", default_roles=("company_admin",))
register("billing.invoice.void", owner_team="billing", risk_level="HIGH", default_roles=("company_admin",))
register("billing.doc.read", owner_team="billing", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("billing.doc.create", owner_team="billing", risk_level="MED", default_roles=("company_admin", "branch_manager"))
register("billing.doc.issue", owner_team="billing", risk_level="HIGH", default_roles=("company_admin",))
register("billing.doc.void", owner_team="billing", risk_level="HIGH", default_roles=("company_admin",))
register("clients.read", owner_team="billing", risk_level="LOW", default_roles=("company_admin", "branch_manager"))
register("clients.write", owner_team="billing", risk_level="MED", default_roles=("company_admin", "branch_manager"))

# Reportes legacy
register("reports.view", owner_team="reports", risk_level="LOW", default_roles=("company_admin", "branch_manager", "auditor"))
register("reports.export", owner_team="reports", risk_level="MED", default_roles=("company_admin", "auditor"))

# FUEL
register("fuel.config.read", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.config.update", owner_team="fuel", risk_level="HIGH", default_roles=("fuel_admin",))
register("fuel.shift.open", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.shift.close", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.shift.read", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor", "fuel_auditor"))
register("fuel.dispense.create", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_cashier"))
register("fuel.dispense.read", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor", "fuel_auditor"))
register("fuel.dispense.void", owner_team="fuel", risk_level="HIGH", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.sale.create", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_cashier"))
register("fuel.sale.read", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor", "fuel_auditor"))
register("fuel.sale.void", owner_team="fuel", risk_level="HIGH", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.price.read", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.price.update", owner_team="fuel", risk_level="HIGH", default_roles=("fuel_admin",))
register("fuel.tank.read", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.tank.receive", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.tank.adjust", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.reconcile.view", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor", "fuel_auditor"))
register("fuel.reconcile.post", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_supervisor"))
register("fuel.outbox.read", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin",))
register("fuel.outbox.reprocess", owner_team="fuel", risk_level="HIGH", default_roles=("fuel_admin",))
register("fuel.reports.view", owner_team="fuel", risk_level="LOW", default_roles=("fuel_admin", "fuel_supervisor", "fuel_auditor"))
register("fuel.reports.export", owner_team="fuel", risk_level="MED", default_roles=("fuel_admin", "fuel_auditor"))

PERMISSIONS_REGISTRY = _PERMS


def get_permission_meta(code: str) -> PermissionMeta | None:
    return _PERMS.get(code)
