from __future__ import annotations

from typing import Any

from .execution import execute_dataset, normalize_filters_for_dataset, serialize_filters_for_storage
from .exports import create_export_from_run, export_to_dict
from .exceptions import DatasetScopeError, ReportingValidationError
from .models import SavedReportView
from .permissions import ensure_permissions
from .registry import get_dataset_spec, list_dataset_specs
from .selectors import (
    get_definition_map,
    get_export_for_scope,
    get_run_for_scope,
    get_saved_view_for_scope,
    list_saved_views_for_scope,
    list_snapshots_for_scope,
)


def list_catalog() -> list[dict[str, Any]]:
    definitions = get_definition_map()
    rows: list[dict[str, Any]] = []
    for spec in list_dataset_specs():
        db_row = definitions.get(spec.dataset_key)
        rows.append(
            {
                "dataset_key": spec.dataset_key,
                "title": spec.title,
                "description": spec.description,
                "domain_owner": spec.domain_owner,
                "scope_level": spec.scope_level,
                "schema_version": spec.schema_version,
                "semantic_version": spec.semantic_version,
                "freshness_mode": spec.freshness_mode,
                "materialization_policy": spec.materialization_policy,
                "required_permissions": spec.required_permissions,
                "filters_schema": spec.filters_schema,
                "dimensions": spec.dimensions,
                "measures": spec.measures,
                "render_hints": spec.render_hints,
                "drill_metadata": spec.drill_metadata,
                "quality_policy": (dict(db_row.quality_policy_json) if db_row is not None else spec.quality_policy),
                "export_capabilities": spec.export_capabilities,
                "status": (db_row.status if db_row is not None else spec.status),
                "is_certified": (bool(db_row.is_certified) if db_row is not None else spec.is_certified),
                "is_enabled": (bool(db_row.is_enabled) if db_row is not None else spec.is_enabled),
            }
        )
    return rows


def get_catalog_entry(dataset_key: str) -> dict[str, Any]:
    key = str(dataset_key or "").strip()
    for row in list_catalog():
        if row["dataset_key"] == key:
            return row
    raise KeyError(key)


def run_dataset_from_request(
    *,
    request,
    dataset_key: str,
    filters: dict[str, Any] | None = None,
    consumer_ref: str = "",
    enforce_kernel_permission: bool = True,
    force_refresh: bool = False,
) -> tuple[dict[str, Any], str]:
    _ = get_dataset_spec(dataset_key)  # fail fast con DatasetNotFoundError
    effective_consumer_ref = str(consumer_ref or "").strip()
    if not effective_consumer_ref:
        effective_consumer_ref = str(getattr(request, "reporting_consumer_ref", "") or "").strip()
    cleaned_filters = {
        key: value
        for key, value in (filters or {}).items()
        if value is not None and value != ""
    }
    envelope, run = execute_dataset(
        dataset_key=dataset_key,
        request=request,
        filters=cleaned_filters,
        consumer_type=str(getattr(request, "reporting_consumer_type", "API") or "API"),
        consumer_ref=effective_consumer_ref,
        enforce_kernel_permission=enforce_kernel_permission,
        force_refresh=force_refresh,
    )
    envelope = dict(envelope)
    envelope.setdefault("quality_status", str(run.quality_status or ""))
    envelope.setdefault("quality_checks", list(run.quality_checks_json or []))
    return envelope, str(run.run_id)


def create_run_export_from_request(*, request, run_id, export_format: str) -> dict[str, Any]:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    run = get_run_for_scope(run_id=run_id, company=company, branch=branch)
    if run is None:
        raise KeyError(str(run_id))
    export = create_export_from_run(
        run=run,
        requested_by=getattr(request, "user", None),
        export_format=export_format,
    )
    return export_to_dict(export)


def get_export_detail_from_request(*, request, export_id) -> dict[str, Any]:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    export = get_export_for_scope(export_id=export_id, company=company, branch=branch)
    if export is None:
        raise KeyError(str(export_id))
    return export_to_dict(export)


def list_snapshots_from_request(*, request, dataset_key: str = "", status: str = ""):
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    qs = list_snapshots_for_scope(company=company, branch=branch)
    key = str(dataset_key or "").strip()
    snapshot_status = str(status or "").strip().upper()
    if key:
        qs = qs.filter(dataset_key=key)
    if snapshot_status:
        qs = qs.filter(status=snapshot_status)
    return qs


def _saved_view_to_dict(row: SavedReportView, *, user) -> dict[str, Any]:
    owner_id = getattr(row.requested_by, "id", None)
    return {
        "view_id": str(row.view_id),
        "name": row.name,
        "dataset_key": row.dataset_key,
        "filters": dict(row.filters_json or {}),
        "render_state": dict(row.render_state_json or {}),
        "is_shared": bool(row.is_shared),
        "is_owner": bool(getattr(user, "is_authenticated", False) and getattr(user, "id", None) == owner_id),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_saved_views_from_request(*, request, dataset_key: str = ""):
    company = getattr(request, "company", None)
    if company is None:
        raise DatasetScopeError("Contexto company requerido para reporting.")
    branch = getattr(request, "branch", None)
    user = getattr(request, "user", None)
    qs = list_saved_views_for_scope(company=company, branch=branch, user=user)
    key = str(dataset_key or "").strip()
    if key:
        qs = qs.filter(dataset_key=key)
    return qs


def get_saved_view_detail_from_request(*, request, view_id) -> dict[str, Any]:
    company = getattr(request, "company", None)
    if company is None:
        raise DatasetScopeError("Contexto company requerido para reporting.")
    row = get_saved_view_for_scope(
        view_id=view_id,
        company=company,
        branch=getattr(request, "branch", None),
        user=getattr(request, "user", None),
    )
    if row is None:
        raise KeyError(str(view_id))
    return _saved_view_to_dict(row, user=getattr(request, "user", None))


def create_saved_view_from_request(
    *,
    request,
    name: str,
    dataset_key: str,
    filters: dict[str, Any] | None = None,
    render_state: dict[str, Any] | None = None,
    is_shared: bool = False,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ReportingValidationError("name es requerido.")

    company = getattr(request, "company", None)
    if company is None:
        raise DatasetScopeError("Contexto company requerido para reporting.")
    branch = getattr(request, "branch", None)
    user = getattr(request, "user", None)

    spec = get_dataset_spec(dataset_key)
    catalog_entry = get_catalog_entry(spec.dataset_key)
    if not bool(catalog_entry.get("is_enabled")):
        raise ReportingValidationError("Dataset deshabilitado para saved views.")

    if spec.scope_level == "BRANCH" and branch is None:
        raise DatasetScopeError("Contexto branch requerido para este dataset.")

    ensure_permissions(
        user=user,
        company=company,
        branch=branch,
        required_permissions=spec.required_permissions,
        effective_permissions_override=getattr(request, "reporting_effective_permissions", None),
    )

    normalized_filters = normalize_filters_for_dataset(dataset_key=spec.dataset_key, filters=filters or {})
    row = SavedReportView.objects.create(
        name=clean_name,
        dataset_key=spec.dataset_key,
        requested_by=user if getattr(user, "is_authenticated", False) else None,
        company=company,
        branch=branch,
        filters_json=serialize_filters_for_storage(normalized_filters),
        render_state_json=dict(render_state or {}),
        is_shared=bool(is_shared),
        is_active=True,
    )
    return _saved_view_to_dict(row, user=user)


def generate_snapshot_from_request(
    *,
    request,
    dataset_key: str,
    filters: dict[str, Any] | None = None,
    force_refresh: bool = False,
    consumer_ref: str = "",
) -> dict[str, Any]:
    spec = get_dataset_spec(dataset_key)
    if spec.materialization_policy == "LIVE_ONLY":
        raise ReportingValidationError("El dataset no soporta snapshots por política LIVE_ONLY.")

    _, run_id = run_dataset_from_request(
        request=request,
        dataset_key=dataset_key,
        filters=filters,
        consumer_ref=consumer_ref or "api:/reporting/snapshots/generate",
        force_refresh=force_refresh,
    )
    run = get_run_for_scope(
        run_id=run_id,
        company=getattr(request, "company", None),
        branch=getattr(request, "branch", None),
    )
    if run is None:
        raise KeyError(str(run_id))
    source = dict(run.source_summary_json or {})
    snapshot_id = source.get("snapshot_id")
    if snapshot_id is None:
        raise ReportingValidationError("No se pudo resolver snapshot para el run generado.")

    from .models import ReportSnapshot

    snapshot = ReportSnapshot.objects.filter(pk=snapshot_id).first()
    if snapshot is None:
        raise ReportingValidationError("Snapshot no encontrado luego de la generación.")
    return {
        "dataset_key": spec.dataset_key,
        "run_id": str(run.run_id),
        "snapshot_id": int(snapshot.id),
        "status": snapshot.status,
        "fresh_until": snapshot.fresh_until,
        "row_count": int(snapshot.row_count or 0),
        "payload_hash": snapshot.payload_hash,
        "schema_version": snapshot.schema_version,
        "semantic_version": snapshot.semantic_version,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
        "materialization_strategy": source.get("materialization"),
        "force_refresh": bool(force_refresh),
    }
