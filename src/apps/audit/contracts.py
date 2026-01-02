from __future__ import annotations

ALLOWED_EVENT_TYPES: set[str] = {
    # AUTH
    "AUTH_LOGIN_SUCCESS",
    "AUTH_LOGIN_FAILURE",
    "AUTH_TOKEN_REFRESH",
    "AUTH_TOKEN_REFRESH_FAILURE",
    "AUTH_LOGOUT",
    "AUTH_LOGOUT_FAILURE",
    "AUTH_LOCKOUT_TRIGGERED",
    "AUTH_ACCESS_DENIED",

    # SYNC
    "SYNC_ENROLL_CHALLENGE_CREATED",
    "SYNC_DEVICE_ENROLLED",
    "SYNC_DEVICE_REVOKED",
    "SYNC_BATCH_RECEIVED",
    "SYNC_COMMAND_APPLIED",
    "SYNC_COMMAND_REJECTED",
    "SYNC_COMMAND_DUPLICATE",

    # RBAC
    "RBAC_SEEDED_V01",

    # ORG
    "ORG_BRANCH_CREATED",
    "ORG_BRANCH_UPDATED",
    "ORG_COMPANY_PROFILE_UPDATED",

    # HR
    "HR_POSITION_CREATED",
    "HR_POSITION_UPDATED",
    "HR_POSITION_ROLEMAP_UPDATED",
    "HR_EMPLOYEE_CREATED",
    "HR_EMPLOYEE_UPDATED",
    "HR_ASSIGNMENT_CREATED",
    "HR_ASSIGNMENT_ENDED",
    "HR_RECONCILE_APPLIED",
}

ALLOWED_REASON_CODES: set[str] = {
    # Legacy / compat (mucho código actual usa "OK")
    "OK",

    # OK por módulo (Opción B)
    "AUTH_OK",
    "RBAC_OK",
    "SYNC_OK",
    "ORG_OK",
    "HR_OK",
    "AUDIT_OK",
    "REPORTS_OK",

    # Auth/login
    "INVALID_CREDENTIALS",
    "USER_DISABLED",
    # Tokens
    "TOKEN_INVALID",
    "TOKEN_EXPIRED",
    # Seguridad
    "RATE_LIMITED",

    # Authorization / policy
    "POLICY_PERMISSION_DENIED",
    "POLICY_SCOPE_DENIED",

    # Sync outcomes/errors
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
    "",
    "USER",
    "SESSION",
    "DEVICE",
    "COMPANY",
    "BRANCH",
    "POSITION",
    "EMPLOYEE",
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
