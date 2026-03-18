from __future__ import annotations

from rest_framework import serializers


class JournalDraftApproveIn(serializers.Serializer):
    run_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=2000, default=200)
    require_passed_validation = serializers.BooleanField(required=False, default=True)
    strict = serializers.BooleanField(required=False, default=True)


class JournalDraftPostIn(serializers.Serializer):
    run_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=2000, default=200)
    require_approved = serializers.BooleanField(required=False, default=True)
    auto_approve = serializers.BooleanField(required=False, default=False)
    allow_same_approver = serializers.BooleanField(required=False, default=False)
    strict = serializers.BooleanField(required=False, default=True)


class FiscalPeriodCloseIn(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    force = serializers.BooleanField(required=False, default=False)
    allow_same_poster = serializers.BooleanField(required=False, default=False)


class JournalEntryReverseIn(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    reversal_date = serializers.DateField(required=False)
    allow_same_poster = serializers.BooleanField(required=False, default=False)


class JournalEntryReverseBatchIn(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    run_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    year = serializers.IntegerField(required=False, min_value=2000, max_value=2100)
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    entry_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=False,
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=2000, default=200)
    reversal_date = serializers.DateField(required=False)
    allow_same_poster = serializers.BooleanField(required=False, default=False)
    strict = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        run_id = str(attrs.get("run_id") or "").strip()
        year = attrs.get("year")
        month = attrs.get("month")
        entry_ids = attrs.get("entry_ids") or []

        selectors = 0
        if run_id:
            selectors += 1
        if year is not None or month is not None:
            if year is None or month is None:
                raise serializers.ValidationError("year y month deben enviarse juntos.")
            selectors += 1
        if entry_ids:
            selectors += 1
        if selectors != 1:
            raise serializers.ValidationError("Debe seleccionar exactamente un scope: run_id, (year+month) o entry_ids.")
        return attrs


class CoARowIn(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=128)
    account_type = serializers.ChoiceField(choices=["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"])
    parent_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    is_postable = serializers.BooleanField(required=False, default=True)
    is_active = serializers.BooleanField(required=False, default=True)
    is_revaluable = serializers.BooleanField(required=False, default=False)


class ChartOfAccountUpsertIn(serializers.Serializer):
    rows = CoARowIn(many=True)
    sync_deactivate = serializers.BooleanField(required=False, default=False)
    functional_currency = serializers.CharField(max_length=8, required=False, allow_blank=False)
    phase7_enabled = serializers.BooleanField(required=False)
    fx_gain_account_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    fx_loss_account_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    retained_earnings_account_code = serializers.CharField(max_length=32, required=False, allow_blank=True)


class ReportRangeIn(serializers.Serializer):
    year = serializers.IntegerField(required=False, min_value=2000, max_value=2100)
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    as_of = serializers.DateField(required=False)

    def validate(self, attrs):
        year = attrs.get("year")
        month = attrs.get("month")
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        as_of = attrs.get("as_of")

        if (year is None) != (month is None):
            raise serializers.ValidationError("year y month deben enviarse juntos.")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("date_from debe ser menor o igual que date_to.")
        if as_of and (date_from or date_to):
            raise serializers.ValidationError("as_of no puede combinarse con date_from/date_to.")
        return attrs


class GeneralLedgerRangeIn(ReportRangeIn):
    account_code = serializers.CharField(max_length=32)


class OperationalReconciliationIn(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("date_from debe ser menor o igual que date_to.")
        return attrs


class FxRateUpsertIn(serializers.Serializer):
    rate_date = serializers.DateField()
    from_currency = serializers.CharField(max_length=8)
    to_currency = serializers.CharField(max_length=8)
    rate_type = serializers.ChoiceField(choices=["CLOSING", "SPOT", "AVERAGE"], required=False, default="CLOSING")
    rate = serializers.DecimalField(max_digits=18, decimal_places=8)

    def validate(self, attrs):
        if str(attrs["from_currency"]).upper() == str(attrs["to_currency"]).upper():
            raise serializers.ValidationError("from_currency y to_currency deben ser distintos.")
        if attrs["rate"] <= 0:
            raise serializers.ValidationError("rate debe ser mayor que 0.")
        return attrs


class FxRevaluationRunIn(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    strict = serializers.BooleanField(required=False, default=True)
    scope_account_codes = serializers.ListField(
        child=serializers.CharField(max_length=32),
        required=False,
        allow_empty=True,
    )


class IntercompanyCreateIn(serializers.Serializer):
    target_company_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    currency = serializers.CharField(max_length=8, required=False, default="NIO")
    source_account_code = serializers.CharField(max_length=32)
    target_account_code = serializers.CharField(max_length=32)
    source_side = serializers.ChoiceField(choices=["DEBIT", "CREDIT"], required=False, default="CREDIT")
    target_side = serializers.ChoiceField(choices=["DEBIT", "CREDIT"], required=False, default="DEBIT")
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    reference_code = serializers.CharField(max_length=96, required=False, allow_blank=True)
    source_journal_entry_id = serializers.IntegerField(min_value=1, required=False)
    target_journal_entry_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if attrs["amount"] <= 0:
            raise serializers.ValidationError("amount debe ser mayor a cero.")
        return attrs


class IntercompanyConfirmIn(serializers.Serializer):
    target_journal_entry_id = serializers.IntegerField(min_value=1, required=False)
    allow_same_actor = serializers.BooleanField(required=False, default=False)


class IntercompanyReconcileIn(serializers.Serializer):
    source_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    target_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    mark_dispute = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class IntercompanyDisputeIn(serializers.Serializer):
    source_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    target_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    reason_code = serializers.CharField(max_length=64)
    evidence_refs = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        allow_empty=True,
        default=list,
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class IntercompanySettleIn(serializers.Serializer):
    source_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    target_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    resolution_note = serializers.CharField(max_length=255, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)
    close_when_confirmed = serializers.BooleanField(required=False, default=True)
    allow_difference = serializers.BooleanField(required=False, default=False)


class IntercompanyDisputeCaseReviewIn(serializers.Serializer):
    action = serializers.ChoiceField(choices=["UNDER_REVIEW", "APPROVED", "REJECTED", "CANCELLED"])
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class IntercompanyCloseIn(serializers.Serializer):
    allow_difference = serializers.BooleanField(required=False, default=False)


class ConsolidationRunIn(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    company_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )
    strict = serializers.BooleanField(required=False, default=True)


class ConsolidationReportIn(serializers.Serializer):
    run_id = serializers.UUIDField(required=True)
