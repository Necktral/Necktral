from __future__ import annotations

ALLOWED_EVENT_TYPES: set[str] = {
    "AUTH_LOGIN_SUCCESS",
    "AUTH_LOGIN_FAILURE",
    "AUTH_TOKEN_REFRESH",
    "AUTH_TOKEN_REFRESH_FAILURE",
    "AUTH_LOGOUT",
    "AUTH_LOGOUT_FAILURE",
    "AUTH_LOCKOUT_TRIGGERED",
    # Fase 2.2 (Ruta A):
    "AUTH_ACCESS_DENIED",

    # Bloque 2 (Offline-first Sync)
    "SYNC_ENROLL_CHALLENGE_CREATED",
    "SYNC_DEVICE_ENROLLED",
    "SYNC_DEVICE_REVOKED",
    "SYNC_BATCH_RECEIVED",
    "SYNC_COMMAND_APPLIED",
    "SYNC_COMMAND_REJECTED",
    "SYNC_COMMAND_DUPLICATE",
}

ALLOWED_REASON_CODES: set[str] = {
    # Auth/login
    "INVALID_CREDENTIALS",
    "USER_DISABLED",
    # Tokens
    "TOKEN_INVALID",
    "TOKEN_EXPIRED",
    # Seguridad
    "RATE_LIMITED",
    # Authorization (Fase 2.2)
    "POLICY_PERMISSION_DENIED",
    "POLICY_SCOPE_DENIED",

    # Bloque 2 (Sync)
    "SYNC_OK",
    "SYNC_DUPLICATE",
    "SYNC_INVALID_SIGNATURE",
    "SYNC_FORBIDDEN_SCOPE",
    "SYNC_SCHEMA_INVALID",
    "SYNC_DEVICE_REVOKED",
    "SYNC_DEVICE_QUARANTINED",
    "SYNC_PAYLOAD_MISMATCH",
    "SYNC_LIMIT_EXCEEDED",
    "SYNC_TIME_SKEW",
    "SYNC_INTERNAL_ERROR",
}

ALLOWED_SUBJECT_TYPES: set[str] = {
    "USER",
    "SESSION",
    "DEVICE",
    "",
}


def validate_event_type(event_type: str) -> None:
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"event_type no permitido: {event_type}")


def validate_reason_code(reason_code: str) -> None:
    if reason_code == "":
        return
    if reason_code not in ALLOWED_REASON_CODES:
        raise ValueError(f"reason_code no permitido: {reason_code}")


def validate_subject(subject_type: str, subject_id: str) -> None:
    if subject_type not in ALLOWED_SUBJECT_TYPES:
        raise ValueError(f"subject_type no permitido: {subject_type}")
    # subject_id puede ser "" en algunos eventos (por ejemplo cuando no existe info suficiente).
    # Para USER/SESSION/DEVICE normalmente conviene que venga lleno, pero no forzamos en DB.
