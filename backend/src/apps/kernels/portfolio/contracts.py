"""
Financial Portfolio Kernel - Event Contracts

Define los eventos económicos que emite el Portfolio Kernel.
Estos eventos se integran con el sistema EconomicEvent y Shadow Ledger.
"""

# Eventos económicos del Portfolio
PORTFOLIO_ECONOMIC_EVENTS = {
    # Receivables (CxC)
    ("PORTFOLIO", "ReceivableCreated"),
    ("PORTFOLIO", "ReceivableAdjusted"),
    ("PORTFOLIO", "ReceivableAllocated"),
    ("PORTFOLIO", "ReceivableWrittenOff"),

    # Payables (CxP)
    ("PORTFOLIO", "PayableCreated"),
    ("PORTFOLIO", "PayableAdjusted"),
    ("PORTFOLIO", "PayableAllocated"),

    # Credits
    ("PORTFOLIO", "CreditApproved"),
    ("PORTFOLIO", "CreditDisbursed"),
    ("PORTFOLIO", "CreditRepaymentReceived"),
    ("PORTFOLIO", "InterestAccrued"),
    ("PORTFOLIO", "InterestCapitalized"),
    ("PORTFOLIO", "CreditRestructured"),
    ("PORTFOLIO", "CreditPaidOff"),
    ("PORTFOLIO", "CreditDefaulted"),
}


# Schema de payloads por evento
EVENT_PAYLOAD_SCHEMAS = {
    "ReceivableCreated": {
        "required": [
            "receivable_id",
            "party_id",
            "principal_amount",
            "currency",
            "issue_date",
            "due_date",
            "reference_type",
            "reference_id",
        ],
        "optional": [
            "invoice_number",
            "invoice_date",
            "credit_limit",
            "credit_days",
        ]
    },

    "ReceivableAllocated": {
        "required": [
            "allocation_id",
            "payment_id",
            "receivable_id",
            "allocated_amount",
            "principal_applied",
            "party_id",
        ],
        "optional": [
            "interest_applied",
            "fee_applied",
            "penalty_applied",
        ]
    },

    "PayableCreated": {
        "required": [
            "payable_id",
            "party_id",
            "principal_amount",
            "currency",
            "issue_date",
            "due_date",
            "reference_type",
            "reference_id",
        ],
        "optional": [
            "supplier_invoice_number",
            "supplier_invoice_date",
            "withholding_tax_amount",
        ]
    },

    "CreditDisbursed": {
        "required": [
            "credit_id",
            "disbursed_amount",
            "total_disbursed",
            "disbursement_date",
            "borrower_party_id",
            "lender_party_id",
        ],
        "optional": []
    },

    "InterestAccrued": {
        "required": [
            "credit_id",
            "accrual_id",
            "accrued_interest",
            "principal_balance",
            "accrual_date",
            "borrower_party_id",
        ],
        "optional": []
    },
}


def validate_event_payload(event_type: str, payload: dict) -> tuple[bool, str]:
    """
    Valida que el payload de un evento tenga los campos requeridos

    Returns:
        (is_valid, error_message)
    """
    schema = EVENT_PAYLOAD_SCHEMAS.get(event_type)
    if not schema:
        return True, ""  # No schema defined, skip validation

    missing = []
    for field in schema["required"]:
        if field not in payload:
            missing.append(field)

    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"

    return True, ""
