from __future__ import annotations

import json
import urllib.request

from django.conf import settings

ALERT_EVENT_TYPES = {
    "AUTH_LOCKOUT_TRIGGERED",
    "RBAC_ROLE_ASSIGNED",
    "AUTH_LOCKOUT_RESET",
}

ALERT_REASON_CODES = {
    "SYNC_INTERNAL_ERROR",
}


def _send_slack(text: str) -> None:
    url = getattr(settings, "SECURITY_ALERT_SLACK_WEBHOOK", "") or ""
    if not url:
        return
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5)


def maybe_alert(event) -> None:
    try:
        intercompany = None
        try:
            intercompany = (event.metadata or {}).get("intercompany")
        except Exception:
            intercompany = None

        intercompany_denied = bool(
            intercompany
            and isinstance(intercompany, dict)
            and intercompany.get("grant_found") is False
        )

        if event.event_type in ALERT_EVENT_TYPES or event.reason_code in ALERT_REASON_CODES or intercompany_denied:
            text = (
                f"[AUDIT] {event.event_type} reason={event.reason_code} "
                f"actor={getattr(event.actor_user, 'id', '')} "
                f"subject={event.subject_type}:{event.subject_id} "
                f"request_id={event.metadata.get('request_id', '')}"
            )
            _send_slack(text)
    except Exception:
        return
