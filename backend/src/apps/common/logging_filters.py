from __future__ import annotations

import logging
import re

SENSITIVE_KEYS = (
    "authorization",
    "x-setup-token",
    "password",
    "refresh",
    "access",
    "token",
)

TOKEN_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9\-\._~\+\/=]+)", re.IGNORECASE)


class RedactSensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        msg = TOKEN_RE.sub(r"\1[REDACTED]", msg)
        for key in SENSITIVE_KEYS:
            msg = re.sub(rf"({key}\s*[:=]\s*)([^,\s]+)", r"\1[REDACTED]", msg, flags=re.IGNORECASE)

        record.msg = msg
        record.args = ()
        return True
