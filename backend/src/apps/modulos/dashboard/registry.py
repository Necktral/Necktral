from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WidgetSpec:
    widget_code: str
    title: str
    report_code: str
    domain: str
    visual: str
    description: str
    default_metrics: tuple[str, ...] = ()
    default_group_by: tuple[str, ...] = ()
    allowed_drill_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceSpec:
    code: str
    title: str
    description: str
    widget_codes: tuple[str, ...]
    intercompany_enabled: bool = False


WIDGET_REGISTRY: dict[str, WidgetSpec] = {
    "exec_revenue_velocity": WidgetSpec(
        widget_code="exec_revenue_velocity",
        title="Revenue Velocity",
        report_code="DOMAIN_FACTURACION_OVERVIEW_V1",
        domain="facturacion",
        visual="stacked_bar",
        description="Volumen y continuidad de emisión por contexto operativo.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("series", "doc_type", "branch"),
    ),
    "exec_margin_watch": WidgetSpec(
        widget_code="exec_margin_watch",
        title="Margin Watch",
        report_code="DOMAIN_ACCOUNTING_OVERVIEW_V1",
        domain="accounting",
        visual="line",
        description="Salud contable y estabilidad de posting para gestión ejecutiva.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("account", "branch", "period"),
    ),
    "exec_inventory_turn": WidgetSpec(
        widget_code="exec_inventory_turn",
        title="Inventory Turn",
        report_code="DOMAIN_INVENTARIOS_OVERVIEW_V1",
        domain="inventarios",
        visual="heatmap",
        description="Pulso de inventario y movimientos críticos por sucursal.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("warehouse", "item", "branch"),
    ),
    "exec_cash_health": WidgetSpec(
        widget_code="exec_cash_health",
        title="Cash Health",
        report_code="DOMAIN_PAYMENTS_OVERVIEW_V1",
        domain="payments",
        visual="area",
        description="Estado de sesiones y movimientos de caja/pagos.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("cash_session", "branch", "method"),
    ),
    "exec_procurement_cycle": WidgetSpec(
        widget_code="exec_procurement_cycle",
        title="Procurement Cycle",
        report_code="DOMAIN_COMPRAS_OVERVIEW_V1",
        domain="compras",
        visual="bar",
        description="Eficiencia documental y ciclo operativo de compras.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("supplier", "doc", "branch"),
    ),
    "exec_fuel_operations": WidgetSpec(
        widget_code="exec_fuel_operations",
        title="Fuel Operations",
        report_code="DOMAIN_ESTACION_SERVICIOS_OVERVIEW_V1",
        domain="estacion_servicios",
        visual="waterfall",
        description="Indicadores operativos de estación de servicios.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("shift", "product", "branch"),
    ),
    "fin_close_readiness": WidgetSpec(
        widget_code="fin_close_readiness",
        title="Close Readiness",
        report_code="DOMAIN_CEC_ALERTS_V1",
        domain="cec",
        visual="table",
        description="Alertas y bloqueos de corridas de cierre.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("close_run", "exception"),
    ),
    "fin_posting_backlog": WidgetSpec(
        widget_code="fin_posting_backlog",
        title="Posting Backlog",
        report_code="DOMAIN_ACCOUNTING_ALERTS_V1",
        domain="accounting",
        visual="table",
        description="Riesgos de posting y pendientes de conciliación.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("journal_draft", "period", "branch"),
    ),
    "fin_revenue_vs_cash": WidgetSpec(
        widget_code="fin_revenue_vs_cash",
        title="Revenue vs Cash Risk",
        report_code="DOMAIN_PAYMENTS_ALERTS_V1",
        domain="payments",
        visual="line",
        description="Brechas entre eventos de pagos y control financiero operativo.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("cash_movement", "intent", "branch"),
    ),
    "ops_fulfillment_flow": WidgetSpec(
        widget_code="ops_fulfillment_flow",
        title="Fulfillment Flow",
        report_code="DOMAIN_INTEGRATION_OVERVIEW_V1",
        domain="integration",
        visual="sankey",
        description="Flujo entre módulos por backbone de integración.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("event_type", "source_module", "status"),
    ),
    "ops_inventory_alerts": WidgetSpec(
        widget_code="ops_inventory_alerts",
        title="Inventory Alerts",
        report_code="DOMAIN_INVENTARIOS_ALERTS_V1",
        domain="inventarios",
        visual="table",
        description="Eventos de riesgo operativo de inventario.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("warehouse", "item", "movement"),
    ),
    "ops_billing_alerts": WidgetSpec(
        widget_code="ops_billing_alerts",
        title="Billing Alerts",
        report_code="DOMAIN_FACTURACION_ALERTS_V1",
        domain="facturacion",
        visual="table",
        description="Riesgos operativos y de numeración fiscal.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("doc", "series", "branch"),
    ),
    "ops_fuel_alerts": WidgetSpec(
        widget_code="ops_fuel_alerts",
        title="Fuel Alerts",
        report_code="DOMAIN_ESTACION_SERVICIOS_ALERTS_V1",
        domain="estacion_servicios",
        visual="table",
        description="Desviaciones operativas de shift/dispense/sale.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("shift", "dispense", "sale"),
    ),
    "sec_identity_surface": WidgetSpec(
        widget_code="sec_identity_surface",
        title="Identity Surface",
        report_code="DOMAIN_IAM_OVERVIEW_V1",
        domain="iam",
        visual="radar",
        description="Exposición de identidades y superficie de acceso.",
        default_metrics=("entity_count", "health_score"),
        default_group_by=("domain",),
        allowed_drill_paths=("user", "membership", "company"),
    ),
    "sec_access_drift": WidgetSpec(
        widget_code="sec_access_drift",
        title="Access Drift",
        report_code="DOMAIN_RBAC_ALERTS_V1",
        domain="rbac",
        visual="table",
        description="Deriva de permisos/roles y riesgo de sobreasignación.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("role", "permission", "assignment"),
    ),
    "sec_audit_anomalies": WidgetSpec(
        widget_code="sec_audit_anomalies",
        title="Audit Anomalies",
        report_code="DOMAIN_AUDIT_ALERTS_V1",
        domain="audit",
        visual="table",
        description="Eventos de auditoría con señal de riesgo.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("event_type", "reason_code", "request_id"),
    ),
    "plat_sync_latency": WidgetSpec(
        widget_code="plat_sync_latency",
        title="Sync Latency",
        report_code="DOMAIN_SYNC_ENGINE_ALERTS_V1",
        domain="sync_engine",
        visual="line",
        description="Señales de latencia y backlog de sincronización.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("device", "batch", "status"),
    ),
    "plat_integration_failures": WidgetSpec(
        widget_code="plat_integration_failures",
        title="Integration Failures",
        report_code="DOMAIN_INTEGRATION_ALERTS_V1",
        domain="integration",
        visual="table",
        description="Fallos críticos en outbox/inbox y cadena de eventos.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("event", "source_module", "status"),
    ),
    "plat_reports_integrity": WidgetSpec(
        widget_code="plat_reports_integrity",
        title="Reports Integrity",
        report_code="DOMAIN_REPORTS_ALERTS_V1",
        domain="reports",
        visual="table",
        description="Integridad de corridas/exportes y reproducibilidad.",
        default_metrics=("alert_count", "critical_count"),
        default_group_by=("severity",),
        allowed_drill_paths=("execution", "export", "report_code"),
    ),
}


WORKSPACE_REGISTRY: dict[str, WorkspaceSpec] = {
    "executive_v1": WorkspaceSpec(
        code="executive_v1",
        title="Executive v1",
        description="Workspace ejecutivo certificado (ingresos, margen, caja y riesgo operativo).",
        widget_codes=(
            "exec_revenue_velocity",
            "exec_margin_watch",
            "exec_cash_health",
            "exec_inventory_turn",
            "exec_fuel_operations",
        ),
        intercompany_enabled=True,
    ),
    "operations_fuel_accounting_v1": WorkspaceSpec(
        code="operations_fuel_accounting_v1",
        title="Operations Fuel + Accounting v1",
        description="Control operativo de fuel y contabilidad con foco en excepciones y conciliación.",
        widget_codes=(
            "ops_fuel_alerts",
            "fin_posting_backlog",
            "fin_revenue_vs_cash",
            "exec_fuel_operations",
            "exec_margin_watch",
        ),
        intercompany_enabled=False,
    ),
    "executive_cross_domain": WorkspaceSpec(
        code="executive_cross_domain",
        title="Executive Cross Domain",
        description="Vista ejecutiva transversal de negocio y operación.",
        widget_codes=(
            "exec_revenue_velocity",
            "exec_margin_watch",
            "exec_inventory_turn",
            "exec_cash_health",
            "exec_procurement_cycle",
            "exec_fuel_operations",
        ),
        intercompany_enabled=True,
    ),
    "financial_control_tower": WorkspaceSpec(
        code="financial_control_tower",
        title="Financial Control Tower",
        description="Control financiero y readiness de cierre operacional.",
        widget_codes=(
            "exec_margin_watch",
            "exec_cash_health",
            "fin_close_readiness",
            "fin_posting_backlog",
            "fin_revenue_vs_cash",
        ),
        intercompany_enabled=True,
    ),
    "operations_logistics": WorkspaceSpec(
        code="operations_logistics",
        title="Operations Logistics",
        description="Monitoreo de flujo operativo multi-kernel.",
        widget_codes=(
            "ops_fulfillment_flow",
            "ops_inventory_alerts",
            "ops_billing_alerts",
            "ops_fuel_alerts",
            "exec_procurement_cycle",
        ),
    ),
    "security_compliance": WorkspaceSpec(
        code="security_compliance",
        title="Security Compliance",
        description="Postura de seguridad, acceso y cumplimiento.",
        widget_codes=(
            "sec_identity_surface",
            "sec_access_drift",
            "sec_audit_anomalies",
        ),
    ),
    "platform_reliability": WorkspaceSpec(
        code="platform_reliability",
        title="Platform Reliability",
        description="Salud técnica de sincronización e integración.",
        widget_codes=(
            "plat_sync_latency",
            "plat_integration_failures",
            "plat_reports_integrity",
        ),
    ),
}


def get_workspace(workspace_code: str) -> WorkspaceSpec | None:
    return WORKSPACE_REGISTRY.get(str(workspace_code or "").strip())


def get_widget(widget_code: str) -> WidgetSpec | None:
    return WIDGET_REGISTRY.get(str(widget_code or "").strip())


def catalog_payload() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for workspace in WORKSPACE_REGISTRY.values():
        out.append(
            {
                "workspace_code": workspace.code,
                "title": workspace.title,
                "description": workspace.description,
                "widget_count": len(workspace.widget_codes),
                "intercompany_enabled": bool(workspace.intercompany_enabled),
                "widgets": list(workspace.widget_codes),
            }
        )
    return out


def workspace_payload(workspace_code: str) -> dict[str, object] | None:
    workspace = get_workspace(workspace_code)
    if workspace is None:
        return None
    widgets: list[dict[str, object]] = []
    for widget_code in workspace.widget_codes:
        widget = WIDGET_REGISTRY[widget_code]
        widgets.append(
            {
                "widget_code": widget.widget_code,
                "title": widget.title,
                "report_code": widget.report_code,
                "domain": widget.domain,
                "visual": widget.visual,
                "description": widget.description,
                "default_metrics": list(widget.default_metrics),
                "default_group_by": list(widget.default_group_by),
                "allowed_drill_paths": list(widget.allowed_drill_paths),
            }
        )
    return {
        "workspace_code": workspace.code,
        "title": workspace.title,
        "description": workspace.description,
        "intercompany_enabled": bool(workspace.intercompany_enabled),
        "widgets": widgets,
    }
