from __future__ import annotations


def get_limit_offset(request, *, default_limit: int = 50, max_limit: int = 200) -> tuple[int, int]:
    try:
        limit = int(request.query_params.get("limit") or default_limit)
    except Exception:
        limit = default_limit
    try:
        offset = int(request.query_params.get("offset") or 0)
    except Exception:
        offset = 0

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


def paginate_queryset(qs, *, limit: int, offset: int):
    total = qs.count()
    rows = qs[offset : offset + limit]
    return total, rows


def paginate_list(items: list, *, limit: int, offset: int):
    total = len(items)
    return total, items[offset : offset + limit]
