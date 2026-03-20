from __future__ import annotations

import hashlib
import json
from typing import Any


def build_dashboard_cache_key(
    *,
    metric: str,
    company_id: int | None,
    branch_id: int | None,
    validated: dict[str, Any],
) -> str:
    payload = {
        "metric": metric,
        "company_id": company_id,
        "branch_id": branch_id,
        "filters": {k: str(v) for k, v in sorted(validated.items()) if k != "refresh"},
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"acc.dashboard:{metric}:{digest}"

