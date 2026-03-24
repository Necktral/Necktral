from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticMetricSpec:
    metric_key: str
    name: str
    description: str
    domain_owner: str
    dataset_key: str
    unit: str
    expression: str
    semantic_version: str = "1.0.0"
    formula_version: str = "v1"
    certified: bool = True


SEMANTIC_METRIC_REGISTRY: dict[str, SemanticMetricSpec] = {}


def _normalize_metric_key(value: str) -> str:
    return str(value or "").strip().lower()


def register_semantic_metric(spec: SemanticMetricSpec) -> None:
    metric_key = _normalize_metric_key(spec.metric_key)
    if not metric_key:
        raise ValueError("semantic metric key cannot be empty")
    if metric_key in SEMANTIC_METRIC_REGISTRY:
        raise ValueError(f"duplicate semantic metric key: {metric_key}")
    SEMANTIC_METRIC_REGISTRY[metric_key] = SemanticMetricSpec(
        metric_key=metric_key,
        name=spec.name.strip(),
        description=spec.description.strip(),
        domain_owner=spec.domain_owner.strip().upper(),
        dataset_key=spec.dataset_key.strip(),
        unit=spec.unit.strip(),
        expression=spec.expression.strip(),
        semantic_version=spec.semantic_version.strip() or "1.0.0",
        formula_version=spec.formula_version.strip() or "v1",
        certified=bool(spec.certified),
    )


def metric_expression_hash(expression: str) -> str:
    raw = str(expression or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else ""


def list_semantic_metrics(*, domain_owner: str | None = None) -> list[SemanticMetricSpec]:
    rows = list(SEMANTIC_METRIC_REGISTRY.values())
    if domain_owner:
        owner = str(domain_owner).strip().upper()
        rows = [row for row in rows if row.domain_owner == owner]
    return sorted(rows, key=lambda row: row.metric_key)


def semantic_metric_keys_for_dataset(dataset_key: str) -> list[str]:
    target = str(dataset_key or "").strip()
    if not target:
        return []
    return sorted([row.metric_key for row in SEMANTIC_METRIC_REGISTRY.values() if row.dataset_key == target])


def _seed_default_metrics() -> None:
    register_semantic_metric(
        SemanticMetricSpec(
            metric_key="accounting.revenue.gross",
            name="Gross Revenue",
            description="Ingresos brutos reconocidos en el periodo.",
            domain_owner="ACCOUNTING",
            dataset_key="accounting.overview",
            unit="currency",
            expression="sum(journal_entry.amount where account_type='REVENUE')",
        )
    )
    register_semantic_metric(
        SemanticMetricSpec(
            metric_key="accounting.margin.gross_pct",
            name="Gross Margin %",
            description="Margen bruto porcentual sobre ingresos.",
            domain_owner="ACCOUNTING",
            dataset_key="accounting.overview",
            unit="percent",
            expression="((revenue - cogs) / nullif(revenue, 0)) * 100",
        )
    )
    register_semantic_metric(
        SemanticMetricSpec(
            metric_key="accounting.cash.net_flow",
            name="Net Cash Flow",
            description="Flujo neto de caja operativo.",
            domain_owner="PAYMENTS",
            dataset_key="payments.overview",
            unit="currency",
            expression="sum(cash_movement.income) - sum(cash_movement.outcome)",
        )
    )
    register_semantic_metric(
        SemanticMetricSpec(
            metric_key="inventory.turnover.index",
            name="Inventory Turnover",
            description="Rotación de inventario normalizada por periodo.",
            domain_owner="INVENTARIOS",
            dataset_key="inventarios.overview",
            unit="index",
            expression="cogs / nullif(avg_inventory_value, 0)",
        )
    )
    register_semantic_metric(
        SemanticMetricSpec(
            metric_key="fuel.dispense_to_sale.ratio",
            name="Dispense to Sale Ratio",
            description="Razón de despacho vs venta registrada.",
            domain_owner="ESTACION_SERVICIOS",
            dataset_key="estacion_servicios.overview",
            unit="ratio",
            expression="sum(fuel_dispense.volume) / nullif(sum(fuel_sale.volume), 0)",
        )
    )
    register_semantic_metric(
        SemanticMetricSpec(
            metric_key="cec.close_readiness.score",
            name="Close Readiness Score",
            description="Indicador de preparación para cierre CEC.",
            domain_owner="CEC",
            dataset_key="cec.alerts",
            unit="score",
            expression="100 - (critical_exceptions * 10) - (open_exceptions * 2)",
        )
    )


_seed_default_metrics()
