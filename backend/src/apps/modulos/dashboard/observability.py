from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from apps.kernels.reporting.models import ReportRun

from .models import DashboardEmbedGrant


def build_dashboard_observability(*, window_hours: int = 24) -> dict[str, Any]:
    hours = max(int(window_hours or 24), 1)
    since = timezone.now() - timedelta(hours=hours)

    grants = DashboardEmbedGrant.objects.filter(created_at__gte=since)
    issued = int(grants.count())
    redeemed = int(grants.filter(status=DashboardEmbedGrant.Status.REDEEMED).count())
    expired = int(grants.filter(status=DashboardEmbedGrant.Status.EXPIRED).count())
    redeemed_rate_pct = round((redeemed / issued * 100.0), 2) if issued else 0.0

    # Django doesn't support nested Count(filter=...) with dynamic expression in older versions,
    # so we compute redeemed per workspace in a second query deterministically.
    redeemed_by_workspace = {
        str(row["workspace_key"]): int(row["total"] or 0)
        for row in grants.filter(status=DashboardEmbedGrant.Status.REDEEMED)
        .values("workspace_key")
        .annotate(total=Count("id"))
    }
    issued_by_workspace = {
        str(row["workspace_key"]): int(row["total"] or 0)
        for row in grants.values("workspace_key").annotate(total=Count("id")).order_by("-total", "workspace_key")
    }

    top_workspace_rows = []
    workspace_redeem_rate = []
    for workspace_key, total in list(issued_by_workspace.items())[:10]:
        redeemed_count = int(redeemed_by_workspace.get(workspace_key, 0))
        top_workspace_rows.append(
            {
                "workspace_key": workspace_key,
                "issued": int(total),
                "redeemed": redeemed_count,
            }
        )
        workspace_redeem_rate.append(
            {
                "workspace_key": workspace_key,
                "issued": int(total),
                "redeemed": redeemed_count,
                "redeem_rate_pct": round((redeemed_count / int(total) * 100.0), 2) if int(total) > 0 else 0.0,
            }
        )

    dash_runs = ReportRun.objects.filter(created_at__gte=since, consumer_type="DASHBOARD")
    runs_total = int(dash_runs.count())
    top_datasets = list(
        dash_runs.values("dataset_key").annotate(total=Count("id")).order_by("-total", "dataset_key")[:10]
    )

    return {
        "window_hours": hours,
        "embed_issued": issued,
        "embed_redeemed": redeemed,
        "embed_expired": expired,
        "embed_redeem_rate_pct": redeemed_rate_pct,
        "top_workspaces": top_workspace_rows,
        "workspace_redeem_rate": workspace_redeem_rate,
        "dash_runs_total": runs_total,
        "top_dash_datasets": [
            {"dataset_key": str(row["dataset_key"]), "runs": int(row["total"] or 0)}
            for row in top_datasets
        ],
    }
