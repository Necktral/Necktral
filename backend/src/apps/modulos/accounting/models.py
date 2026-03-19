from __future__ import annotations

import uuid
from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class FiscalPeriod(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="acc_periods_company")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    opened_at = models.DateTimeField(default=timezone.now, editable=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_periods_closed",
    )

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(fields=["company", "year", "month"], name="uq_acc_period_company_year_month"),
            models.CheckConstraint(condition=models.Q(month__gte=1, month__lte=12), name="ck_acc_period_month_range"),
        ]
        indexes = [
            models.Index(fields=["company", "year", "month"]),
            models.Index(fields=["company", "status"]),
        ]


class EconomicEvent(models.Model):
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source_module = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128)

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="acc_events_company")
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acc_events_branch",
    )

    occurred_at = models.DateTimeField(default=timezone.now)
    contract_version = models.CharField(max_length=16, default="1.0")
    schema_version = models.PositiveSmallIntegerField(default=1)
    correlation_id = models.CharField(max_length=96, blank=True, default="")
    causation_id = models.CharField(max_length=96, blank=True, default="")

    payload = models.JSONField(default=dict)
    input_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    source_outbox_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    close_run_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_outbox_event_id"],
                condition=models.Q(source_outbox_event_id__isnull=False),
                name="uq_acc_event_company_source_outbox",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "occurred_at"]),
            models.Index(fields=["source_module", "event_type", "occurred_at"]),
            models.Index(fields=["company", "close_run_id", "occurred_at"]),
        ]


class PostingRuleSet(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        DEPRECATED = "DEPRECATED", "Deprecated"

    class FiscalMode(models.TextChoices):
        A = "A", "Fiscal A"
        B = "B", "Fiscal B"
        BOTH = "BOTH", "Both"

    code = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    fiscal_mode = models.CharField(max_length=8, choices=FiscalMode.choices, default=FiscalMode.BOTH)

    scope_company = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acc_posting_rules_company",
    )
    jurisdiction = models.CharField(max_length=32, blank=True, default="")

    effective_from = models.DateTimeField(null=True, blank=True)
    effective_to = models.DateTimeField(null=True, blank=True)

    rules_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="uq_acc_posting_rule_code_version"),
        ]
        indexes = [
            models.Index(fields=["status", "fiscal_mode"]),
            models.Index(fields=["scope_company", "status"]),
        ]


class JournalDraft(models.Model):
    class State(models.TextChoices):
        GENERATED = "GENERATED", "Generated"
        VALIDATED = "VALIDATED", "Validated"
        EXCEPTION = "EXCEPTION", "Exception"
        APPROVED_FOR_POSTING = "APPROVED_FOR_POSTING", "Approved for posting"
        POSTED = "POSTED", "Posted"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    economic_event = models.ForeignKey(EconomicEvent, on_delete=models.PROTECT, related_name="journal_drafts")
    rule_set = models.ForeignKey(PostingRuleSet, on_delete=models.PROTECT, related_name="journal_drafts")

    state = models.CharField(max_length=24, choices=State.choices, default=State.GENERATED)
    contract_version = models.CharField(max_length=16, default="1.0")
    schema_version = models.PositiveSmallIntegerField(default=1)
    close_run_id = models.CharField(max_length=64, blank=True, default="")
    input_manifest_hash = models.CharField(max_length=64, blank=True, default="")

    lines_json = models.JSONField(default=list)
    total_debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    generated_at = models.DateTimeField(default=timezone.now, editable=False)
    validated_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_journal_drafts_approved",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
    )
    metadata = models.JSONField(default=dict)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.CheckConstraint(condition=models.Q(total_debit__gte=0), name="ck_acc_jdraft_debit_non_negative"),
            models.CheckConstraint(condition=models.Q(total_credit__gte=0), name="ck_acc_jdraft_credit_non_negative"),
            models.UniqueConstraint(fields=["economic_event", "rule_set"], name="uq_acc_jdraft_event_rule_set"),
        ]
        indexes = [
            models.Index(fields=["state", "generated_at"]),
            models.Index(fields=["economic_event", "state"]),
        ]

    def clean(self):
        if self.total_debit != self.total_credit:
            raise ValidationError("JournalDraft requiere debit_total == credit_total.")


class JournalEntry(models.Model):
    draft = models.OneToOneField(JournalDraft, on_delete=models.PROTECT, related_name="journal_entry")
    period = models.ForeignKey(FiscalPeriod, on_delete=models.PROTECT, related_name="journal_entries")

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="journal_entries_company")
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="journal_entries_branch",
    )

    entry_date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=255, blank=True, default="")

    debit_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    is_posted = models.BooleanField(default=True)
    posted_at = models.DateTimeField(default=timezone.now, editable=False)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_journal_entries_posted",
    )

    reversed_entry = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reverses",
    )
    metadata = models.JSONField(default=dict)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.CheckConstraint(condition=models.Q(debit_total__gte=0), name="ck_acc_jentry_debit_non_negative"),
            models.CheckConstraint(condition=models.Q(credit_total__gte=0), name="ck_acc_jentry_credit_non_negative"),
            models.CheckConstraint(
                condition=models.Q(debit_total=models.F("credit_total")),
                name="ck_acc_jentry_balanced",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "period", "entry_date"]),
            models.Index(fields=["period", "is_posted"]),
        ]

    def clean(self):
        if self.debit_total != self.credit_total:
            raise ValidationError("JournalEntry requiere debit_total == credit_total.")
        if self.is_posted and self.period.status == FiscalPeriod.Status.CLOSED:
            raise ValidationError("No se permite posting en periodo cerrado.")
        if self.company_id and self.period.company_id != self.company_id:
            raise ValidationError("JournalEntry.company debe coincidir con FiscalPeriod.company.")


class ChartOfAccount(models.Model):
    class AccountType(models.TextChoices):
        ASSET = "ASSET", "Asset"
        LIABILITY = "LIABILITY", "Liability"
        EQUITY = "EQUITY", "Equity"
        REVENUE = "REVENUE", "Revenue"
        EXPENSE = "EXPENSE", "Expense"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="acc_chart_accounts")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=128)
    account_type = models.CharField(max_length=16, choices=AccountType.choices)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_postable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_revaluable = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uq_acc_coa_company_code"),
        ]
        indexes = [
            models.Index(fields=["company", "account_type", "is_active"]),
            models.Index(fields=["company", "is_postable", "is_active"]),
        ]

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("ChartOfAccount.company debe ser COMPANY.")
        if self.parent_id and self.parent_id == self.id:
            raise ValidationError("ChartOfAccount.parent no puede referenciarse a sí misma.")
        if self.parent_id and self.parent.company_id != self.company_id:
            raise ValidationError("ChartOfAccount.parent debe pertenecer a la misma company.")


class CompanyAccountingConfig(models.Model):
    company = models.OneToOneField(OrgUnit, on_delete=models.PROTECT, related_name="accounting_config")
    functional_currency = models.CharField(max_length=8, default="NIO")
    phase7_enabled = models.BooleanField(default=False)
    fx_gain_account = models.ForeignKey(
        ChartOfAccount,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="configured_as_fx_gain",
    )
    fx_loss_account = models.ForeignKey(
        ChartOfAccount,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="configured_as_fx_loss",
    )
    retained_earnings_account = models.ForeignKey(
        ChartOfAccount,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="configured_as_retained_earnings",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        indexes = [
            models.Index(fields=["phase7_enabled"]),
        ]

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("CompanyAccountingConfig.company debe ser COMPANY.")
        account_fields = (
            ("fx_gain_account", self.fx_gain_account),
            ("fx_loss_account", self.fx_loss_account),
            ("retained_earnings_account", self.retained_earnings_account),
        )
        for field_name, account in account_fields:
            if account is None:
                continue
            if account.company_id != self.company_id:
                raise ValidationError(f"{field_name} debe pertenecer a la misma company.")


class OperationalPostingConfig(models.Model):
    class PostingMode(models.TextChoices):
        DISABLED = "DISABLED", "Disabled"
        ASYNC = "ASYNC", "Async"
        SYNC = "SYNC", "Sync"
        HYBRID = "HYBRID", "Hybrid"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="acc_operational_posting_company")
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acc_operational_posting_branch",
    )
    posting_mode = models.CharField(max_length=16, choices=PostingMode.choices, default=PostingMode.HYBRID)
    enable_billing = models.BooleanField(default=True)
    enable_inventory = models.BooleanField(default=True)
    auto_post_on_write = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(fields=["company", "branch"], name="uq_acc_operational_posting_scope"),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "is_active"]),
            models.Index(fields=["company", "posting_mode", "is_active"]),
        ]

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("OperationalPostingConfig.company debe ser COMPANY.")
        if self.branch_id:
            if self.branch.unit_type != OrgUnit.UnitType.BRANCH:
                raise ValidationError("OperationalPostingConfig.branch debe ser BRANCH.")
            if self.branch.parent_id != self.company_id:
                raise ValidationError("OperationalPostingConfig.branch debe pertenecer a la misma company.")


class JournalEntryLine(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    line_no = models.PositiveIntegerField()
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, related_name="journal_entry_lines")
    account_code_snapshot = models.CharField(max_length=32)

    currency = models.CharField(max_length=8, default="NIO")
    fx_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1.00000000"))
    amount_tx = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    debit_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    meta_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(fields=["journal_entry", "line_no"], name="uq_acc_jentry_line_order"),
            models.CheckConstraint(condition=models.Q(fx_rate__gt=0), name="ck_acc_jline_fx_rate_positive"),
            models.CheckConstraint(condition=models.Q(debit_base__gte=0), name="ck_acc_jline_debit_non_negative"),
            models.CheckConstraint(condition=models.Q(credit_base__gte=0), name="ck_acc_jline_credit_non_negative"),
        ]
        indexes = [
            models.Index(fields=["journal_entry", "line_no"]),
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["currency", "created_at"]),
        ]

    def clean(self):
        if self.debit_base > 0 and self.credit_base > 0:
            raise ValidationError("JournalEntryLine no puede tener débito y crédito positivos simultáneamente.")
        if self.account_id and self.journal_entry_id:
            if self.account.company_id != self.journal_entry.company_id:
                raise ValidationError("JournalEntryLine.account debe pertenecer a la misma company del entry.")
        if not self.account_code_snapshot and self.account_id:
            self.account_code_snapshot = self.account.code


class FxRate(models.Model):
    class RateType(models.TextChoices):
        CLOSING = "CLOSING", "Closing"
        SPOT = "SPOT", "Spot"
        AVERAGE = "AVERAGE", "Average"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="acc_fx_rates")
    rate_date = models.DateField()
    from_currency = models.CharField(max_length=8)
    to_currency = models.CharField(max_length=8)
    rate_type = models.CharField(max_length=16, choices=RateType.choices, default=RateType.CLOSING)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "rate_date", "from_currency", "to_currency", "rate_type"],
                name="uq_acc_fx_rate_scope",
            ),
            models.CheckConstraint(condition=models.Q(rate__gt=0), name="ck_acc_fx_rate_positive"),
        ]
        indexes = [
            models.Index(fields=["company", "rate_type", "rate_date"]),
            models.Index(fields=["company", "from_currency", "to_currency", "rate_date"]),
        ]

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("FxRate.company debe ser COMPANY.")
        if self.from_currency == self.to_currency:
            raise ValidationError("FxRate.from_currency y to_currency deben ser distintos.")


class RevaluationRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        BLOCKED = "BLOCKED", "Blocked"
        FAILED = "FAILED", "Failed"

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="acc_revaluation_runs")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    scope_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    summary_json = models.JSONField(default=dict)
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_revaluation_runs_executed",
    )
    executed_at = models.DateTimeField(default=timezone.now, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "year", "month", "scope_hash"],
                name="uq_acc_revaluation_company_period_scope",
            ),
            models.CheckConstraint(condition=models.Q(month__gte=1, month__lte=12), name="ck_acc_revaluation_month_range"),
        ]
        indexes = [
            models.Index(fields=["company", "year", "month", "status"]),
            models.Index(fields=["company", "status", "executed_at"]),
        ]


class RevaluationEntryLink(models.Model):
    revaluation_run = models.ForeignKey(RevaluationRun, on_delete=models.PROTECT, related_name="entry_links")
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="revaluation_links")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["revaluation_run", "journal_entry"],
                name="uq_acc_revaluation_entry_link",
            ),
        ]
        indexes = [
            models.Index(fields=["journal_entry", "created_at"]),
        ]


class DraftValidationResult(models.Model):
    draft = models.OneToOneField(JournalDraft, on_delete=models.PROTECT, related_name="validation_result")
    passed = models.BooleanField(default=False)
    errors_json = models.JSONField(default=list)
    is_blocking = models.BooleanField(default=True)
    validated_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        indexes = [
            models.Index(fields=["passed", "is_blocking", "validated_at"]),
        ]


class ExceptionLink(models.Model):
    draft = models.ForeignKey(JournalDraft, on_delete=models.PROTECT, related_name="exception_links")
    exception = models.ForeignKey("cec.CECException", on_delete=models.PROTECT, related_name="accounting_exception_links")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(fields=["draft", "exception"], name="uq_acc_exception_link_draft_exception"),
        ]
        indexes = [
            models.Index(fields=["exception", "created_at"]),
        ]


class IntercompanyTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        DIFFERENCE = "DIFFERENCE", "Difference"
        DISPUTED = "DISPUTED", "Disputed"
        CLOSED = "CLOSED", "Closed"

    class Side(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    tx_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source_company = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="acc_intercompany_source_transactions",
    )
    target_company = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="acc_intercompany_target_transactions",
    )
    source_journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acc_intercompany_source_journal_transactions",
    )
    target_journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acc_intercompany_target_journal_transactions",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reference_code = models.CharField(max_length=96, blank=True, default="")
    currency = models.CharField(max_length=8, default="NIO")
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    source_account_code = models.CharField(max_length=32, blank=True, default="")
    target_account_code = models.CharField(max_length=32, blank=True, default="")
    source_side = models.CharField(max_length=8, choices=Side.choices, default=Side.CREDIT)
    target_side = models.CharField(max_length=8, choices=Side.choices, default=Side.DEBIT)
    matched_amount_source = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    matched_amount_target = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    difference_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    description = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_transactions_created",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_transactions_confirmed",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_transactions_closed",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.CheckConstraint(condition=~models.Q(source_company=models.F("target_company")), name="ck_acc_ic_tx_company_distinct"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_acc_ic_tx_amount_positive"),
        ]
        indexes = [
            models.Index(fields=["source_company", "target_company", "status", "created_at"]),
            models.Index(fields=["source_company", "status", "created_at"]),
            models.Index(fields=["target_company", "status", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["reference_code"]),
        ]

    _ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        Status.PENDING: {Status.CONFIRMED, Status.DIFFERENCE, Status.DISPUTED, Status.CLOSED},
        Status.CONFIRMED: {Status.DIFFERENCE, Status.DISPUTED, Status.CLOSED},
        Status.DIFFERENCE: {Status.CONFIRMED, Status.DISPUTED, Status.CLOSED},
        Status.DISPUTED: {Status.CONFIRMED, Status.CLOSED},
        Status.CLOSED: set(),
    }

    def can_transition_to(self, target_status: str) -> bool:
        if target_status == self.status:
            return True
        return target_status in self._ALLOWED_TRANSITIONS.get(self.status, set())

    def clean(self):
        if self.source_company_id and self.source_company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("IntercompanyTransaction.source_company debe ser COMPANY.")
        if self.target_company_id and self.target_company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("IntercompanyTransaction.target_company debe ser COMPANY.")
        if self.source_company_id and self.target_company_id and self.source_company_id == self.target_company_id:
            raise ValidationError("source_company y target_company deben ser distintos.")
        if self.source_journal_entry_id and self.source_journal_entry.company_id != self.source_company_id:
            raise ValidationError("source_journal_entry debe pertenecer a source_company.")
        if self.target_journal_entry_id and self.target_journal_entry.company_id != self.target_company_id:
            raise ValidationError("target_journal_entry debe pertenecer a target_company.")


class IntercompanyReconciliation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        DIFFERENCE = "DIFFERENCE", "Difference"
        DISPUTED = "DISPUTED", "Disputed"
        CLOSED = "CLOSED", "Closed"

    transaction = models.ForeignKey(
        IntercompanyTransaction,
        on_delete=models.PROTECT,
        related_name="reconciliations",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    source_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    target_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    difference_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    note = models.CharField(max_length=255, blank=True, default="")
    details_json = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_reconciliations_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        indexes = [
            models.Index(fields=["transaction", "status", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class IntercompanyDisputeReason(models.Model):
    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    company = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="acc_intercompany_dispute_reasons",
    )
    code = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=128)
    description = models.CharField(max_length=255, blank=True, default="")
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.HIGH)
    requires_evidence = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code", "version"],
                name="uq_acc_ic_dispute_reason_company_code_version",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "code", "is_active"]),
            models.Index(fields=["company", "is_active", "updated_at"]),
        ]

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("IntercompanyDisputeReason.company debe ser COMPANY.")


class IntercompanyDisputeCase(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SETTLED = "SETTLED", "Settled"
        CANCELLED = "CANCELLED", "Cancelled"

    case_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    transaction = models.ForeignKey(
        IntercompanyTransaction,
        on_delete=models.PROTECT,
        related_name="dispute_cases",
    )
    reason = models.ForeignKey(
        IntercompanyDisputeReason,
        on_delete=models.PROTECT,
        related_name="dispute_cases",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    summary = models.CharField(max_length=255, blank=True, default="")
    resolution_note = models.CharField(max_length=255, blank=True, default="")
    details_json = models.JSONField(default=dict)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_disputes_opened",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_disputes_reviewed",
    )
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_disputes_settled",
    )
    opened_at = models.DateTimeField(default=timezone.now, editable=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["transaction"],
                condition=models.Q(status__in=["OPEN", "UNDER_REVIEW", "APPROVED"]),
                name="uq_acc_ic_dispute_case_active_per_tx",
            ),
        ]
        indexes = [
            models.Index(fields=["transaction", "status", "updated_at"]),
            models.Index(fields=["status", "sla_due_at"]),
            models.Index(fields=["reason", "status"]),
        ]


class IntercompanyDisputeEvidence(models.Model):
    evidence_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    dispute_case = models.ForeignKey(
        IntercompanyDisputeCase,
        on_delete=models.PROTECT,
        related_name="evidences",
    )
    reference = models.CharField(max_length=255)
    evidence_hash = models.CharField(max_length=64)
    mime_type = models.CharField(max_length=128, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_intercompany_dispute_evidences_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["dispute_case", "evidence_hash"],
                name="uq_acc_ic_dispute_evidence_case_hash",
            ),
        ]
        indexes = [
            models.Index(fields=["dispute_case", "created_at"]),
            models.Index(fields=["evidence_hash"]),
        ]


class ConsolidationRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        BLOCKED = "BLOCKED", "Blocked"
        FAILED = "FAILED", "Failed"

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    parent_company = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="acc_consolidation_runs_parent",
    )
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    scope_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    company_ids_json = models.JSONField(default=list)
    summary_json = models.JSONField(default=dict)
    input_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    output_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acc_consolidation_runs_executed",
    )
    started_at = models.DateTimeField(default=timezone.now, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["parent_company", "year", "month", "scope_hash"],
                name="uq_acc_consolidation_scope",
            ),
            models.CheckConstraint(condition=models.Q(month__gte=1, month__lte=12), name="ck_acc_consolidation_month_range"),
        ]
        indexes = [
            models.Index(fields=["parent_company", "year", "month", "status"]),
            models.Index(fields=["status", "started_at"]),
        ]

    def clean(self):
        if self.parent_company_id and self.parent_company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("ConsolidationRun.parent_company debe ser COMPANY.")


class ConsolidationEliminationLink(models.Model):
    consolidation_run = models.ForeignKey(
        ConsolidationRun,
        on_delete=models.PROTECT,
        related_name="elimination_links",
    )
    intercompany_transaction = models.ForeignKey(
        IntercompanyTransaction,
        on_delete=models.PROTECT,
        related_name="consolidation_links",
    )
    elimination_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "accounting"
        constraints = [
            models.UniqueConstraint(
                fields=["consolidation_run", "intercompany_transaction"],
                name="uq_acc_consolidation_elimination_link",
            ),
        ]
        indexes = [
            models.Index(fields=["consolidation_run", "created_at"]),
            models.Index(fields=["intercompany_transaction", "created_at"]),
        ]
