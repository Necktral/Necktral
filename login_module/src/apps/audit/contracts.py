from __future__ import annotations

ALLOWED_EVENT_TYPES: set[str] = {
    # AUTH
    "AUTH_LOGIN_SUCCESS",
    "AUTH_LOGIN_FAILURE",
    "AUTH_BOOTSTRAP_ADMIN_CREATED",
    "IAM_BOOTSTRAP_ORG_CREATED",
    "AUTH_PASSWORD_CHANGED",
    "AUTH_PASSWORD_CHANGE_FAILURE",
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
    "ORG_COMPANY_CREATED",
    "ORG_COMPANY_PROFILE_UPDATED",
    # HR
    "HR_POSITION_CREATED",
    "HR_POSITION_UPDATED",
    "HR_POSITION_ROLEMAP_UPDATED",
    "HR_EMPLOYEE_CREATED",
    "HR_EMPLOYEE_UPDATED",
    "HR_EMPLOYEE_USER_PROVISIONED",
    "HR_EMPLOYEE_TEMP_PASSWORD_RESET",
    "HR_EMPLOYEE_ACCESS_REVOKED",
    "HR_ASSIGNMENT_CREATED",
    "HR_ASSIGNMENT_ENDED",
    "HR_RECONCILE_APPLIED",

    # FUEL (Estación de Servicios)
    "FUEL_SHIFT_OPENED",
    "FUEL_SHIFT_CLOSED",
    "FUEL_PRICE_SET",
    "FUEL_DISPENSE_RECORDED",
    "FUEL_DISPENSE_VOIDED",
    "FUEL_SALE_CREATED",
    "FUEL_SALE_VOIDED",
    "FUEL_TANK_RECEIPT_POSTED",
    "FUEL_TANK_ADJUSTMENT_POSTED",
    "FUEL_RECONCILIATION_POSTED",
    "FUEL_INTERCOMPANY_OUTBOX_ENQUEUED",
    "FUEL_INTERCOMPANY_OUTBOX_APPLIED",
    "FUEL_INTERCOMPANY_OUTBOX_FAILED",

    # INVENTORY
    "INVENTORY_ITEM_CREATED",
    "INVENTORY_ITEM_UPDATED",

    # BILLING
    "BILLING_CUSTOMER_CREATED",
    "BILLING_CUSTOMER_UPDATED",
    "BILLING_INVOICE_CREATED",
    "BILLING_INVOICE_ISSUED",
    "BILLING_INVOICE_VOIDED",
}

# Event Types (añadir)
ALLOWED_EVENT_TYPES.update(
    {
        "INVENTORY_MOVEMENT_POSTED",
        "INVENTORY_ADJUSTMENT_POSTED",
        "INVENTORY_TRANSFER_POSTED",
        "BILLING_DOC_CREATED",
        "BILLING_DOC_ISSUED",
        "BILLING_DOC_VOIDED",
    }
)

ALLOWED_REASON_CODES: set[str] = {
    # Legacy / compat (mucho código actual usa "OK")
    "OK",
    # OK por módulo (Opción B)
    "AUTH_OK",
    "RBAC_OK",
    "SYNC_OK",
    "ORG_OK",
    "HR_OK",
    "FUEL_OK",
    "AUDIT_OK",
    "REPORTS_OK",

    # OK por módulo (futuros kernels)

    # Auth/login
    "INVALID_CREDENTIALS",
    "USER_DISABLED",
    # Tokens
    "TOKEN_INVALID",
    "TOKEN_EXPIRED",
    # Contrato de errores API (auth)
    "AUTH_UNAUTHENTICATED",
    "AUTH_INVALID_TOKEN",
    "AUTH_TOKEN_EXPIRED",
    # Seguridad
    "RATE_LIMITED",
    # Authorization / policy
    "POLICY_PERMISSION_DENIED",
    "POLICY_SCOPE_DENIED",
    # Contrato de errores API (authz)
    "RBAC_FORBIDDEN",
    "SCOPE_FORBIDDEN",

    # Contrato de errores API (genéricos)
    "BAD_REQUEST",
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "CONFLICT",
    "INTERNAL_ERROR",
    "SERVICE_UNAVAILABLE",

    # FUEL (operación)
    "SHIFT_CLOSED",
    "VOID_NOT_ALLOWED",
    "METER_READING_MISMATCH",
    "INTERNAL_CREDIT_LIMIT",
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

    # INVENTORY (reglas)
    "NEGATIVE_STOCK_BLOCKED",
    "INVENTORY_INVALID_SCOPE",
    "INVENTORY_INSUFFICIENT_STOCK",
    "INVENTORY_IDEMPOTENCY_CONFLICT",
    "INVENTORY_SCHEMA_INVALID",

    # BILLING (reglas)
    "INVOICE_NOT_DRAFT",
    "SERIES_EXHAUSTED",
}

# Reason Codes (añadir)
ALLOWED_REASON_CODES.update(
    {
        "INVENTORY_OK",
        "BILLING_OK",
        "BILLING_VOID",
    }
)

ALLOWED_SUBJECT_TYPES: set[str] = {
    "",
    "USER",
    "SESSION",
    "DEVICE",
    "COMPANY",
    "BRANCH",
    "POSITION",
    "EMPLOYEE",

    # FUEL (Estación de Servicios)
    "FUEL_SHIFT",
    "FUEL_DISPENSE",
    "FUEL_SALE",
    "FUEL_TANK",
    "FUEL_NOZZLE",
    "FUEL_PRICE",
    "FUEL_OUTBOX",
    "FUEL_LIQUIDATION",

    # INVENTORY
    "INVENTORY_ITEM",
    "STOCK_MOVEMENT",

    # BILLING
    "CUSTOMER",
    "INVOICE",
    "PAYMENT",
}

# Subject Types (añadir)
ALLOWED_SUBJECT_TYPES.update(
    {
        "INVENTORY_MOVEMENT",
        "INVENTORY_TRANSFER",
        "BILLING_DOC",
    }
)


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
