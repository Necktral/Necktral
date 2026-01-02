from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db import transaction

from apps.rbac.models import Permission, Role, RolePermission

@dataclass(frozen=True)
class SeedResult:
    roles_created: int
    roles_updated: int
    perms_created: int
    perms_updated: int
    roleperms_created: int

def seed_rbac_v01() -> SeedResult:
    """
    Catálogo estándar v0.1 (robusto, modular, extensible).
    - Idempotente (get_or_create + updates)
    - No borra cosas existentes.
    """

    roles = {
        "company_admin": "Administrador global dentro de la empresa (RBAC + ORG + HR + reportes).",
        "branch_manager": "Administrador de sucursal.",
        "hr_manager": "Gestión completa de RRHH.",
        "hr_clerk": "Operación RRHH (altas/bajas/edición), sin RBAC.",
        "auditor": "Lectura de auditoría y reportes.",
        "warehouse_manager": "Gestión de inventario (placeholder).",
        "warehouse_operator": "Operación inventario (placeholder).",
        "sales_manager": "Gestión comercial (placeholder).",
        "sales_rep": "Operación ventas (placeholder).",
        "cashier": "Caja (placeholder).",
        "sync_admin": "Administración de Sync (enroll/revoke) (placeholder).",
    }

    permissions = {
        # ORG
        "org.company.read": "Ver datos de empresa.",
        "org.company.update": "Actualizar datos de empresa.",
        "org.branch.read": "Ver sucursales.",
        "org.branch.create": "Crear sucursales.",
        "org.branch.update": "Actualizar sucursales.",
        # HR
        "hr.position.read": "Ver puestos.",
        "hr.position.create": "Crear puestos.",
        "hr.position.update": "Actualizar puestos.",
        "hr.position.roles.update": "Actualizar mapeo Puesto->Roles.",
        "hr.employee.read": "Ver empleados.",
        "hr.employee.create": "Crear empleados.",
        "hr.employee.update": "Actualizar empleados.",
        "hr.assignment.create": "Crear asignaciones laborales.",
        "hr.assignment.end": "Finalizar asignaciones laborales.",
        # RBAC (para UI admin futura)
        "rbac.roles.read": "Ver roles.",
        "rbac.roles.update": "Actualizar roles.",
        "rbac.permissions.read": "Ver permisos.",
        "rbac.permissions.update": "Actualizar permisos.",
        "rbac.assignments.read": "Ver asignaciones de roles.",
        "rbac.assignments.update": "Actualizar asignaciones de roles.",
        # Auditoría
        "audit.read": "Leer auditoría.",
        "audit.export": "Exportar auditoría.",
        # Sync (placeholder)
        "sync.device.enroll": "Enrolar dispositivos.",
        "sync.device.revoke": "Revocar dispositivos.",
        "sync.batch.receive": "Recibir lotes de sync.",
        # Placeholders de módulos futuros ya existentes en tests
        "inventory.read": "Lectura inventario (placeholder).",
        "inventory.write": "Escritura inventario (placeholder).",
        "clients.read": "Lectura clientes (placeholder).",
        "clients.write": "Escritura clientes (placeholder).",
        "reports.view": "Ver reportes (placeholder).",
        "reports.export": "Exportar reportes (placeholder).",
    }

    role_to_perms = {
        "company_admin": [
            "org.company.read", "org.company.update",
            "org.branch.read", "org.branch.create", "org.branch.update",
            "hr.position.read", "hr.position.create", "hr.position.update", "hr.position.roles.update",
            "hr.employee.read", "hr.employee.create", "hr.employee.update",
            "hr.assignment.create", "hr.assignment.end",
            "rbac.roles.read", "rbac.roles.update",
            "rbac.permissions.read", "rbac.permissions.update",
            "rbac.assignments.read", "rbac.assignments.update",
            "audit.read", "audit.export",
            "sync.device.enroll", "sync.device.revoke", "sync.batch.receive",
            "inventory.read", "inventory.write",
            "clients.read", "clients.write",
            "reports.view", "reports.export",
        ],
        "branch_manager": [
            "org.branch.read", "org.branch.update",
            "hr.employee.read", "hr.employee.update",
            "inventory.read", "inventory.write",
            "clients.read", "clients.write",
            "reports.view",
        ],
        "hr_manager": [
            "org.company.read",
            "org.branch.read",
            "hr.position.read", "hr.position.create", "hr.position.update", "hr.position.roles.update",
            "hr.employee.read", "hr.employee.create", "hr.employee.update",
            "hr.assignment.create", "hr.assignment.end",
        ],
        "hr_clerk": [
            "org.branch.read",
            "hr.position.read",
            "hr.employee.read", "hr.employee.create", "hr.employee.update",
            "hr.assignment.create", "hr.assignment.end",
        ],
        "auditor": [
            "audit.read",
            "reports.view",
        ],
        "warehouse_manager": ["inventory.read", "inventory.write"],
        "warehouse_operator": ["inventory.read"],
        "sales_manager": ["clients.read", "clients.write", "reports.view"],
        "sales_rep": ["clients.read"],
        "cashier": ["reports.view"],
        "sync_admin": ["sync.device.enroll", "sync.device.revoke"],
    }

    roles_created = roles_updated = perms_created = perms_updated = roleperms_created = 0

    with transaction.atomic():
        role_objs: dict[str, Role] = {}
        for name, desc in roles.items():
            obj, created = Role.objects.get_or_create(name=name, defaults={"description": desc, "is_active": True})
            if created:
                roles_created += 1
            else:
                update_fields: list[str] = []
                if obj.description != desc:
                    obj.description = desc
                    update_fields.append("description")
                if not obj.is_active:
                    obj.is_active = True
                    update_fields.append("is_active")
                if update_fields:
                    obj.save(update_fields=update_fields)
                    roles_updated += 1
            role_objs[name] = obj

        perm_objs: dict[str, Permission] = {}
        for code, desc in permissions.items():
            obj, created = Permission.objects.get_or_create(code=code, defaults={"description": desc, "is_active": True})
            if created:
                perms_created += 1
            else:
                update_fields: list[str] = []
                if obj.description != desc:
                    obj.description = desc
                    update_fields.append("description")
                if not obj.is_active:
                    obj.is_active = True
                    update_fields.append("is_active")
                if update_fields:
                    obj.save(update_fields=update_fields)
                    perms_updated += 1
            perm_objs[code] = obj

        for role_name, perm_codes in role_to_perms.items():
            role = role_objs[role_name]
            for code in perm_codes:
                perm = perm_objs.get(code)
                if perm is None:
                    # Catálogo inconsistente => fallo duro
                    raise ValueError(f"Permiso no existe en seed permissions: {code}")
                _, rp_created = RolePermission.objects.get_or_create(role=role, permission=perm)
                if rp_created:
                    roleperms_created += 1
    return SeedResult(
        roles_created=roles_created,
        roles_updated=roles_updated,
        perms_created=perms_created,
        perms_updated=perms_updated,
        roleperms_created=roleperms_created,
    )
