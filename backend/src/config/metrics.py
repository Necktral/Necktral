from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any


_start_time = time.time()
_lock = threading.Lock()
_status_counts: Counter[str] = Counter()
_method_counts: Counter[str] = Counter()
_path_counts: Counter[str] = Counter()
_latency_sum_ms = 0
_latency_max_ms = 0
_total_requests = 0


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    if path.startswith("/api/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return f"/api/{parts[1]}"
        return "/api"
    return path


def record_request(request, *, status_code: int | None, duration_ms: int) -> None:
    global _latency_sum_ms
    global _latency_max_ms
    global _total_requests

    code = int(status_code or 0)
    family = f"{code // 100}xx" if code else "0xx"
    method = (getattr(request, "method", "") or "").upper()
    path = _normalize_path(getattr(request, "path", "") or "")

    with _lock:
        _total_requests += 1
        _latency_sum_ms += int(duration_ms)
        _latency_max_ms = max(_latency_max_ms, int(duration_ms))
        _status_counts[family] += 1
        _status_counts[str(code)] += 1
        if method:
            _method_counts[method] += 1
        if path:
            _path_counts[path] += 1


def _top(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"key": k, "count": v} for k, v in counter.most_common(limit)]


def snapshot() -> dict:
    with _lock:
        total = _total_requests
        avg_ms = int(_latency_sum_ms / total) if total else 0
        return {
            "uptime_seconds": int(time.time() - _start_time),
            "total_requests": total,
            "latency_ms_avg": avg_ms,
            "latency_ms_max": int(_latency_max_ms),
            "status_counts": dict(_status_counts),
            "method_counts": dict(_method_counts),
            "top_paths": _top(_path_counts, limit=15),
        }
