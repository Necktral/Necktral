"""API REST de contabilidad (GL, FX e intercompany) con contratos de respuesta estables."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api_exceptions import ConflictError
from apps.common.pagination import get_limit_offset, paginate_queryset
from apps.common.permissions import rbac_permission
from apps.integration.services import publish_outbox_event
from apps.rbac.selectors import get_effective_permissions_for_scope
from config.error_envelope import build_error_envelope

from .models import (
    ChartOfAccount,
    ConsolidationRun,
    FiscalPeriod,
    FxRate,
    IntercompanyDisputeCase,
    IntercompanyDisputeReason,
    IntercompanyTransaction,
    JournalDraft,
    JournalEntry,
)
from .phase7 import (
    Phase7ValidationError,
    balance_sheet_report,
    general_ledger_queryset,
    get_or_create_accounting_config,
    is_phase7_enabled_for_company,
    pnl_report,
    resolve_period_range,
    run_fx_revaluation,
    trial_balance_queryset,
    upsert_chart_of_accounts,
)
from .phase7b import (
    Phase7BValidationError,
    close_intercompany_transaction,
    confirm_intercompany_transaction,
    create_intercompany_transaction,
    dispute_intercompany_transaction,
    review_intercompany_dispute_case,
    get_consolidation_run_summary,
    reconcile_intercompany_transaction,
    run_consolidation,
    settle_intercompany_transaction,
)
from .serializers import (
    ChartOfAccountUpsertIn,
    ConsolidationReportIn,
    ConsolidationRunIn,
    FxRateUpsertIn,
    FxRevaluationRunIn,
    FiscalPeriodCloseIn,
    GeneralLedgerRangeIn,
    IntercompanyCloseIn,
    IntercompanyConfirmIn,
    IntercompanyCreateIn,
    IntercompanyDisputeCaseReviewIn,
    IntercompanyDisputeIn,
    IntercompanyReconcileIn,
    IntercompanySettleIn,
    JournalDraftApproveIn,
    JournalDraftPostIn,
    JournalEntryReverseBatchIn,
    JournalEntryReverseIn,
    ReportRangeIn,
    OperationalReconciliationIn,
)
from .services import (
    AccountingConflictError,
    approve_journal_drafts,
    close_fiscal_period,
    post_journal_drafts,
    reconcile_operational_vs_accounting,
    reverse_journal_entries_batch,
    reverse_journal_entry,
)


class HealthView(APIView):
    """Healthcheck del módulo contable sin autenticación para observabilidad técnica."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "accounting"}, status=status.HTTP_200_OK)


def _resolve_range_payload(validated: dict):
    """Resuelve rango por período (`year/month`) o por fechas explícitas, con prioridad a período."""
    period_range = resolve_period_range(
        year=validated.get("year"),
        month=validated.get("month"),
    )
    if period_range is not None:
        return period_range[0], period_range[1]
    return validated.get("date_from"), validated.get("date_to")


def _serialize_intercompany(tx: IntercompanyTransaction) -> dict:
    """Serializa transacción intercompany con contexto de disputa activa para UI/reportes."""
    dispute_case = (
        tx.dispute_cases.filter(status__in=["OPEN", "UNDER_REVIEW", "APPROVED"])
        .select_related("reason")
        .order_by("-updated_at", "-id")
        .first()
    )
    dispute_payload = {
        "case_id": str(dispute_case.case_id) if dispute_case else "",
        "reason_code": str(dispute_case.reason.code) if dispute_case and dispute_case.reason_id else "",
        "status": str(dispute_case.status) if dispute_case else "",
        "sla_due_at": dispute_case.sla_due_at if dispute_case else None,
    }
    return {
        "tx_id": str(tx.tx_id),
        "status": tx.status,
        "source_company_id": int(tx.source_company_id),
        "target_company_id": int(tx.target_company_id),
        "source_journal_entry_id": tx.source_journal_entry_id,
        "target_journal_entry_id": tx.target_journal_entry_id,
        "reference_code": tx.reference_code,
        "currency": tx.currency,
        "amount": str(tx.amount),
        "source_account_code": tx.source_account_code,
        "target_account_code": tx.target_account_code,
        "source_side": tx.source_side,
        "target_side": tx.target_side,
        "matched_amount_source": str(tx.matched_amount_source),
        "matched_amount_target": str(tx.matched_amount_target),
        "difference_amount": str(tx.difference_amount),
        "description": tx.description,
        "created_by_id": tx.created_by_id,
        "confirmed_by_id": tx.confirmed_by_id,
        "closed_by_id": tx.closed_by_id,
        "created_at": tx.created_at,
        "confirmed_at": tx.confirmed_at,
        "closed_at": tx.closed_at,
        "dispute": dispute_payload,
    }


def _load_intercompany(tx_id: str) -> IntercompanyTransaction | None:
    """Carga transacción intercompany por identificador de negocio (`tx_id`)."""
    return IntercompanyTransaction.objects.filter(tx_id=tx_id).first()


class ChartOfAccountView(APIView):
    """Consulta y actualización de COA/config de Fase 7 con publicación de evento de integración."""

    permission_classes = [rbac_permission("accounting.coa.read")]

    def get(self, request):
        company = request.company
        qs = ChartOfAccount.objects.filter(company=company).select_related("parent").order_by("code", "id")
        active = str(request.query_params.get("active") or "").strip().lower()
        if active in ("1", "true", "yes"):
            qs = qs.filter(is_active=True)
        elif active in ("0", "false", "no"):
            qs = qs.filter(is_active=False)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        cfg = get_or_create_accounting_config(company=company)
        results = [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "account_type": row.account_type,
                "parent_code": row.parent.code if row.parent_id else "",
                "is_postable": bool(row.is_postable),
                "is_active": bool(row.is_active),
                "is_revaluable": bool(row.is_revaluable),
            }
            for row in rows
        ]
        return Response(
            {
                "count": int(total),
                "limit": int(limit),
                "offset": int(offset),
                "results": results,
                "config": {
                    "functional_currency": cfg.functional_currency,
                    "phase7_enabled": bool(cfg.phase7_enabled),
                    "fx_gain_account_code": cfg.fx_gain_account.code if cfg.fx_gain_account_id else "",
                    "fx_loss_account_code": cfg.fx_loss_account.code if cfg.fx_loss_account_id else "",
                    "retained_earnings_account_code": (
                        cfg.retained_earnings_account.code if cfg.retained_earnings_account_id else ""
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        if not rbac_permission("accounting.coa.update")().has_permission(request, self):
            return Response({"detail": "Permiso requerido: accounting.coa.update"}, status=status.HTTP_403_FORBIDDEN)

        s = ChartOfAccountUpsertIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        company = request.company

        try:
            result = upsert_chart_of_accounts(
                company=company,
                rows=v.get("rows", []),
                sync_deactivate=bool(v.get("sync_deactivate", False)),
            )
            cfg = get_or_create_accounting_config(company=company)
            changed_config = False

            if "functional_currency" in v:
                cfg.functional_currency = str(v["functional_currency"]).strip().upper()
                changed_config = True
            if "phase7_enabled" in v:
                cfg.phase7_enabled = bool(v["phase7_enabled"])
                changed_config = True

            def _resolve_account(code_field: str):
                code = str(v.get(code_field) or "").strip().upper()
                if not code:
                    return None
                # Regla fuerte: las cuentas técnicas deben existir activas en el mismo scope de empresa.
                row = ChartOfAccount.objects.filter(company=company, code=code, is_active=True).first()
                if row is None:
                    raise Phase7ValidationError(f"Cuenta no encontrada para {code_field}: {code}")
                return row

            if "fx_gain_account_code" in v:
                cfg.fx_gain_account = _resolve_account("fx_gain_account_code")
                changed_config = True
            if "fx_loss_account_code" in v:
                cfg.fx_loss_account = _resolve_account("fx_loss_account_code")
                changed_config = True
            if "retained_earnings_account_code" in v:
                cfg.retained_earnings_account = _resolve_account("retained_earnings_account_code")
                changed_config = True

            if changed_config:
                cfg.full_clean()
                cfg.save()
        except Phase7ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="ChartOfAccountsUpserted",
            payload={
                "company_id": int(company.id),
                "created": int(result.created),
                "updated": int(result.updated),
                "deactivated": int(result.deactivated),
                "total_active": int(result.total_active),
                "phase7_enabled": bool(is_phase7_enabled_for_company(company=company)),
            },
            company=company,
            actor_user=request.user,
            request=request,
        )

        payload = {
            "created": int(result.created),
            "updated": int(result.updated),
            "deactivated": int(result.deactivated),
            "total_active": int(result.total_active),
            "phase7_enabled": bool(get_or_create_accounting_config(company=company).phase7_enabled),
        }
        return Response(payload, status=status.HTTP_200_OK)


class TrialBalanceReportView(APIView):
    """Reporte de balance de comprobación con filtros por periodo y paginación estándar."""

    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = ReportRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            date_from, date_to = _resolve_range_payload(v)
        except Phase7ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        qs = trial_balance_queryset(
            company=request.company,
            branch=getattr(request, "branch", None),
            date_from=date_from,
            date_to=date_to,
        )
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = []
        for row in rows:
            debit = row["debit_total"]
            credit = row["credit_total"]
            results.append(
                {
                    "account_code": str(row["account__code"]),
                    "account_name": str(row["account__name"]),
                    "account_type": str(row["account__account_type"]),
                    "debit_total": str(debit),
                    "credit_total": str(credit),
                    "net_balance": str(debit - credit),
                }
            )
        return Response(
            {
                "count": int(total),
                "limit": int(limit),
                "offset": int(offset),
                "filters": {
                    "date_from": str(date_from) if date_from else "",
                    "date_to": str(date_to) if date_to else "",
                },
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class GeneralLedgerReportView(APIView):
    """Reporte de mayor general por cuenta contable en orden cronológico estable."""

    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = GeneralLedgerRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            date_from, date_to = _resolve_range_payload(v)
            qs = general_ledger_queryset(
                company=request.company,
                branch=getattr(request, "branch", None),
                account_code=str(v["account_code"]),
                date_from=date_from,
                date_to=date_to,
            )
        except Phase7ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "journal_entry_id": int(row.journal_entry_id),
                "entry_date": row.journal_entry.entry_date,
                "description": row.journal_entry.description,
                "line_no": int(row.line_no),
                "account_code": row.account_code_snapshot,
                "currency": row.currency,
                "fx_rate": str(row.fx_rate),
                "amount_tx": str(row.amount_tx),
                "debit_base": str(row.debit_base),
                "credit_base": str(row.credit_base),
                "posted_at": row.journal_entry.posted_at,
            }
            for row in rows
        ]
        return Response(
            {
                "count": int(total),
                "limit": int(limit),
                "offset": int(offset),
                "filters": {
                    "account_code": str(v["account_code"]).strip().upper(),
                    "date_from": str(date_from) if date_from else "",
                    "date_to": str(date_to) if date_to else "",
                },
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class PnLReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = ReportRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            date_from, date_to = _resolve_range_payload(v)
            report = pnl_report(
                company=request.company,
                branch=getattr(request, "branch", None),
                date_from=date_from,
                date_to=date_to,
            )
        except Phase7ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "filters": {
                    "date_from": str(date_from) if date_from else "",
                    "date_to": str(date_to) if date_to else "",
                },
                **report,
            },
            status=status.HTTP_200_OK,
        )


class BalanceSheetReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = ReportRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        as_of = v.get("as_of")
        if as_of is None:
            period = resolve_period_range(year=v.get("year"), month=v.get("month"))
            if period is not None:
                as_of = period[1]
            else:
                as_of = v.get("date_to") or timezone.localdate()
        try:
            report = balance_sheet_report(
                company=request.company,
                branch=getattr(request, "branch", None),
                as_of=as_of,
            )
        except Phase7ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(report, status=status.HTTP_200_OK)


class OperationalReconciliationReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = OperationalReconciliationIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        payload = reconcile_operational_vs_accounting(
            company=request.company,
            branch=getattr(request, "branch", None),
            date_from=v.get("date_from"),
            date_to=v.get("date_to"),
        )
        payload["filters"] = {
            "date_from": str(v.get("date_from") or ""),
            "date_to": str(v.get("date_to") or ""),
            "branch_id": getattr(getattr(request, "branch", None), "id", None),
        }
        return Response(payload, status=status.HTTP_200_OK)


class FxRateUpsertView(APIView):
    permission_classes = [rbac_permission("accounting.fx_rate.read")]

    def get(self, request):
        company = request.company
        qs = FxRate.objects.filter(company=company).order_by("-rate_date", "-id")
        rate_type = str(request.query_params.get("rate_type") or "").strip().upper()
        from_currency = str(request.query_params.get("from_currency") or "").strip().upper()
        to_currency = str(request.query_params.get("to_currency") or "").strip().upper()
        if rate_type:
            qs = qs.filter(rate_type=rate_type)
        if from_currency:
            qs = qs.filter(from_currency=from_currency)
        if to_currency:
            qs = qs.filter(to_currency=to_currency)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        return Response(
            {
                "count": int(total),
                "limit": int(limit),
                "offset": int(offset),
                "results": [
                    {
                        "id": int(row.id),
                        "rate_date": str(row.rate_date),
                        "from_currency": row.from_currency,
                        "to_currency": row.to_currency,
                        "rate_type": row.rate_type,
                        "rate": str(row.rate),
                    }
                    for row in rows
                ],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if not rbac_permission("accounting.fx_rate.update")().has_permission(request, self):
            return Response({"detail": "Permiso requerido: accounting.fx_rate.update"}, status=status.HTTP_403_FORBIDDEN)

        s = FxRateUpsertIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        company = request.company

        row, created = FxRate.objects.update_or_create(
            company=company,
            rate_date=v["rate_date"],
            from_currency=str(v["from_currency"]).upper(),
            to_currency=str(v["to_currency"]).upper(),
            rate_type=str(v.get("rate_type") or "CLOSING").upper(),
            defaults={
                "rate": v["rate"],
            },
        )

        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="FxRateUpserted",
            payload={
                "company_id": int(company.id),
                "rate_id": int(row.id),
                "rate_date": str(row.rate_date),
                "from_currency": row.from_currency,
                "to_currency": row.to_currency,
                "rate_type": row.rate_type,
                "rate": str(row.rate),
                "created": bool(created),
            },
            company=company,
            actor_user=request.user,
            request=request,
        )
        return Response(
            {
                "id": int(row.id),
                "created": bool(created),
                "rate_date": str(row.rate_date),
                "from_currency": row.from_currency,
                "to_currency": row.to_currency,
                "rate_type": row.rate_type,
                "rate": str(row.rate),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class FxRevaluationRunView(APIView):
    """Ejecuta revaluación FX y expone resultado idempotente/bloqueado en contrato REST."""

    permission_classes = [rbac_permission("accounting.revaluation.run")]

    def post(self, request):
        s = FxRevaluationRunIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            result = run_fx_revaluation(
                company_id=request.company.id,
                year=int(v["year"]),
                month=int(v["month"]),
                strict=bool(v.get("strict", True)),
                scope_account_codes=v.get("scope_account_codes") or [],
                actor_user=request.user,
            )
        except Phase7ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "run_id": str(result.run_id),
            "status": str(result.status),
            "idempotent": bool(result.idempotent),
            "entries_created": int(result.entries_created),
            "issues_count": int(result.issues_count),
            "summary": result.summary_json,
        }
        if str(result.status) == "BLOCKED":
            return Response(payload, status=status.HTTP_409_CONFLICT)
        return Response(payload, status=status.HTTP_200_OK if result.idempotent else status.HTTP_201_CREATED)


class IntercompanyTransactionListCreateView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.read")]

    def get(self, request):
        company = request.company
        qs = (
            IntercompanyTransaction.objects.select_related("source_company", "target_company")
            .filter(Q(source_company=company) | Q(target_company=company))
            .order_by("-created_at", "-id")
        )
        status_filter = str(request.query_params.get("status") or "").strip().upper()
        if status_filter:
            qs = qs.filter(status=status_filter)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        return Response(
            {
                "count": int(total),
                "limit": int(limit),
                "offset": int(offset),
                "results": [_serialize_intercompany(row) for row in rows],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if not rbac_permission("accounting.intercompany.write")().has_permission(request, self):
            return Response(
                {"detail": "Permiso requerido: accounting.intercompany.write"},
                status=status.HTTP_403_FORBIDDEN,
            )
        s = IntercompanyCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            tx = create_intercompany_transaction(
                source_company_id=int(request.company.id),
                target_company_id=int(v["target_company_id"]),
                amount=v["amount"],
                currency=str(v.get("currency") or "NIO"),
                source_account_code=str(v.get("source_account_code") or ""),
                target_account_code=str(v.get("target_account_code") or ""),
                source_side=str(v.get("source_side") or "CREDIT"),
                target_side=str(v.get("target_side") or "DEBIT"),
                description=str(v.get("description") or ""),
                reference_code=str(v.get("reference_code") or ""),
                source_journal_entry_id=v.get("source_journal_entry_id"),
                target_journal_entry_id=v.get("target_journal_entry_id"),
                actor_user=request.user,
                effective_company_id=int(request.company.id),
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_intercompany(tx), status=status.HTTP_201_CREATED)


class IntercompanyTransactionConfirmView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.write")]

    def post(self, request, tx_id: str):
        s = IntercompanyConfirmIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            result = confirm_intercompany_transaction(
                tx_id=tx_id,
                actor_user=request.user,
                target_journal_entry_id=v.get("target_journal_entry_id"),
                allow_same_actor=bool(v.get("allow_same_actor", False)),
                effective_company_id=int(request.company.id),
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        tx = _load_intercompany(result.tx_id)
        if tx is None:
            return Response({"detail": "Intercompany transaction not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_intercompany(tx), status=status.HTTP_200_OK)


class IntercompanyTransactionReconcileView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.reconcile")]

    def post(self, request, tx_id: str):
        s = IntercompanyReconcileIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            result = reconcile_intercompany_transaction(
                tx_id=tx_id,
                source_amount=v["source_amount"],
                target_amount=v["target_amount"],
                actor_user=request.user,
                mark_dispute=bool(v.get("mark_dispute", False)),
                note=str(v.get("note") or ""),
                effective_company_id=int(request.company.id),
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        tx = _load_intercompany(result.tx_id)
        if tx is None:
            return Response({"detail": "Intercompany transaction not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_intercompany(tx), status=status.HTTP_200_OK)


class IntercompanyTransactionDisputeView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.dispute")]

    def post(self, request, tx_id: str):
        s = IntercompanyDisputeIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            result = dispute_intercompany_transaction(
                tx_id=tx_id,
                source_amount=v["source_amount"],
                target_amount=v["target_amount"],
                reason_code=str(v.get("reason_code") or ""),
                evidence_refs=[str(x) for x in (v.get("evidence_refs") or [])],
                actor_user=request.user,
                note=str(v.get("note") or ""),
                effective_company_id=int(request.company.id),
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        tx = _load_intercompany(result.tx_id)
        if tx is None:
            return Response({"detail": "Intercompany transaction not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_intercompany(tx), status=status.HTTP_200_OK)


class IntercompanyTransactionSettleView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.settle")]

    def post(self, request, tx_id: str):
        s = IntercompanySettleIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            result = settle_intercompany_transaction(
                tx_id=tx_id,
                source_amount=v["source_amount"],
                target_amount=v["target_amount"],
                actor_user=request.user,
                note=str(v.get("resolution_note") or v.get("note") or ""),
                close_when_confirmed=bool(v.get("close_when_confirmed", True)),
                allow_difference=bool(v.get("allow_difference", False)),
                effective_company_id=int(request.company.id),
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        tx = _load_intercompany(result.tx_id)
        if tx is None:
            return Response({"detail": "Intercompany transaction not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_intercompany(tx), status=status.HTTP_200_OK)


class IntercompanyTransactionCloseView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.write")]

    def post(self, request, tx_id: str):
        s = IntercompanyCloseIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            result = close_intercompany_transaction(
                tx_id=tx_id,
                actor_user=request.user,
                allow_difference=bool(v.get("allow_difference", False)),
                effective_company_id=int(request.company.id),
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        tx = _load_intercompany(result.tx_id)
        if tx is None:
            return Response({"detail": "Intercompany transaction not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_intercompany(tx), status=status.HTTP_200_OK)


class IntercompanyDisputeReasonListView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.read")]

    def get(self, request):
        company = request.company
        qs = IntercompanyDisputeReason.objects.filter(company=company, is_active=True).order_by("code", "-version")
        out = []
        for row in qs:
            out.append(
                {
                    "id": int(row.id),
                    "code": str(row.code),
                    "version": int(row.version),
                    "title": str(row.title),
                    "description": str(row.description or ""),
                    "severity": str(row.severity),
                    "requires_evidence": bool(row.requires_evidence),
                    "is_active": bool(row.is_active),
                }
            )
        return Response({"count": int(len(out)), "results": out}, status=status.HTTP_200_OK)


class IntercompanyDisputeCaseListView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.read")]

    def get(self, request):
        company = request.company
        qs = (
            IntercompanyDisputeCase.objects.select_related("reason", "transaction")
            .filter(transaction__source_company=company)
            .order_by("-updated_at", "-id")
        )
        status_filter = str(request.query_params.get("status") or "").strip().upper()
        if status_filter:
            qs = qs.filter(status=status_filter)
        tx_id_filter = str(request.query_params.get("tx_id") or "").strip()
        if tx_id_filter:
            qs = qs.filter(transaction__tx_id=tx_id_filter)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = []
        for row in rows:
            results.append(
                {
                    "case_id": str(row.case_id),
                    "tx_id": str(row.transaction.tx_id),
                    "status": str(row.status),
                    "reason_code": str(row.reason.code),
                    "summary": str(row.summary or ""),
                    "resolution_note": str(row.resolution_note or ""),
                    "evidence_count": int(row.evidences.count()),
                    "sla_due_at": row.sla_due_at,
                    "opened_at": row.opened_at,
                    "updated_at": row.updated_at,
                }
            )
        return Response(
            {
                "count": int(total),
                "limit": int(limit),
                "offset": int(offset),
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class IntercompanyDisputeCaseReviewView(APIView):
    permission_classes = [rbac_permission("accounting.intercompany.dispute")]

    def post(self, request, case_id: str):
        s = IntercompanyDisputeCaseReviewIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            row = review_intercompany_dispute_case(
                case_id=case_id,
                action=str(v.get("action") or ""),
                note=str(v.get("note") or ""),
                actor_user=request.user,
                effective_company_id=int(request.company.id),
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                "case_id": str(row.case_id),
                "status": str(row.status),
                "resolution_note": str(row.resolution_note or ""),
                "reviewed_at": row.reviewed_at,
                "updated_at": row.updated_at,
            },
            status=status.HTTP_200_OK,
        )


class ConsolidationRunView(APIView):
    permission_classes = [rbac_permission("accounting.consolidation.run")]

    def post(self, request):
        s = ConsolidationRunIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            result = run_consolidation(
                parent_company_id=int(request.company.id),
                year=int(v["year"]),
                month=int(v["month"]),
                company_ids=[int(x) for x in v["company_ids"]],
                strict=bool(v.get("strict", True)),
                actor_user=request.user,
            )
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "run_id": str(result.run_id),
            "status": str(result.status),
            "idempotent": bool(result.idempotent),
            "issues_count": int(result.issues_count),
            "manifest_hash": str(result.manifest_hash),
            "summary": result.summary_json,
        }
        if str(result.status) == ConsolidationRun.Status.BLOCKED:
            return Response(payload, status=status.HTTP_409_CONFLICT)
        return Response(payload, status=status.HTTP_200_OK if result.idempotent else status.HTTP_201_CREATED)


class ConsolidationRunSummaryView(APIView):
    permission_classes = [rbac_permission("accounting.consolidation.read")]

    def get(self, request, run_id: str):
        try:
            payload = get_consolidation_run_summary(run_id=run_id)
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload, status=status.HTTP_200_OK)


class ConsolidationTrialBalanceReportView(APIView):
    permission_classes = [rbac_permission("accounting.consolidation.read")]

    def get(self, request):
        s = ConsolidationReportIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        run_id = str(s.validated_data["run_id"])
        try:
            summary = get_consolidation_run_summary(run_id=run_id)
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        rows = (summary.get("summary") or {}).get("trial_balance", {}).get("rows", [])
        return Response({"run_id": run_id, "count": len(rows), "results": rows}, status=status.HTTP_200_OK)


class ConsolidationPnLReportView(APIView):
    permission_classes = [rbac_permission("accounting.consolidation.read")]

    def get(self, request):
        s = ConsolidationReportIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        run_id = str(s.validated_data["run_id"])
        try:
            summary = get_consolidation_run_summary(run_id=run_id)
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        payload = (summary.get("summary") or {}).get("pnl", {})
        return Response({"run_id": run_id, **payload}, status=status.HTTP_200_OK)


class ConsolidationBalanceSheetReportView(APIView):
    permission_classes = [rbac_permission("accounting.consolidation.read")]

    def get(self, request):
        s = ConsolidationReportIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        run_id = str(s.validated_data["run_id"])
        try:
            summary = get_consolidation_run_summary(run_id=run_id)
        except Phase7BValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        payload = (summary.get("summary") or {}).get("balance_sheet", {})
        return Response({"run_id": run_id, **payload}, status=status.HTTP_200_OK)


class JournalDraftListView(APIView):
    permission_classes = [rbac_permission("accounting.journal_draft.read")]

    def get(self, request):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = (
            JournalDraft.objects.select_related("economic_event", "rule_set", "validation_result")
            .filter(economic_event__company=company)
            .order_by("-generated_at", "-id")
        )
        if branch is not None:
            qs = qs.filter(economic_event__branch=branch)

        run_id = str(request.query_params.get("run_id") or "").strip()
        state = str(request.query_params.get("state") or "").strip()
        if run_id:
            qs = qs.filter(close_run_id=run_id)
        if state:
            qs = qs.filter(state=state)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": r.id,
                "state": r.state,
                "close_run_id": r.close_run_id,
                "economic_event_id": r.economic_event_id,
                "rule_set_id": r.rule_set_id,
                "total_debit": str(r.total_debit),
                "total_credit": str(r.total_credit),
                "generated_at": r.generated_at,
                "validated_at": r.validated_at,
                "approved_at": r.approved_at,
                "approved_by_id": r.approved_by_id,
                "posted_at": r.posted_at,
                "validation_passed": (
                    bool(r.validation_result.passed)
                    if hasattr(r, "validation_result")
                    else None
                ),
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class JournalEntryListView(APIView):
    permission_classes = [rbac_permission("accounting.journal_entry.read")]

    def get(self, request):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = JournalEntry.objects.select_related("period", "draft").filter(company=company).order_by("-posted_at", "-id")
        if branch is not None:
            qs = qs.filter(branch=branch)

        year = request.query_params.get("year")
        month = request.query_params.get("month")
        if year:
            qs = qs.filter(period__year=int(year))
        if month:
            qs = qs.filter(period__month=int(month))

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": r.id,
                "draft_id": r.draft_id,
                "period_id": r.period_id,
                "year": int(r.period.year),
                "month": int(r.period.month),
                "entry_date": r.entry_date,
                "description": r.description,
                "debit_total": str(r.debit_total),
                "credit_total": str(r.credit_total),
                "is_posted": bool(r.is_posted),
                "posted_at": r.posted_at,
                "posted_by_id": r.posted_by_id,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class FiscalPeriodListView(APIView):
    permission_classes = [rbac_permission("accounting.period.read")]

    def get(self, request):
        company = request.company
        qs = FiscalPeriod.objects.filter(company=company).order_by("-year", "-month", "-id")
        status_filter = str(request.query_params.get("status") or "").strip()
        year = request.query_params.get("year")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if year:
            qs = qs.filter(year=int(year))

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": r.id,
                "year": int(r.year),
                "month": int(r.month),
                "status": r.status,
                "opened_at": r.opened_at,
                "closed_at": r.closed_at,
                "closed_by_id": r.closed_by_id,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class JournalDraftApproveView(APIView):
    permission_classes = [rbac_permission("accounting.journal_draft.approve")]

    def post(self, request):
        s = JournalDraftApproveIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        result = approve_journal_drafts(
            company_id=request.company.id,
            run_id=str(v.get("run_id") or "").strip(),
            limit=int(v.get("limit") or 200),
            require_passed_validation=bool(v.get("require_passed_validation", True)),
            actor_user=request.user,
        )
        payload = {
            "attempted": int(result.attempted),
            "approved": int(result.approved),
            "skipped": int(result.skipped),
            "failed": int(result.failed),
            "errors": result.errors,
        }
        if bool(v.get("strict", True)) and result.failed > 0:
            return Response(payload, status=status.HTTP_409_CONFLICT)
        return Response(payload, status=status.HTTP_200_OK)


class JournalDraftPostView(APIView):
    permission_classes = [rbac_permission("accounting.journal_draft.post")]

    @staticmethod
    def _can_override_sod(request) -> bool:
        perms = get_effective_permissions_for_scope(
            request.user,
            company=request.company,
            branch=getattr(request, "branch", None),
            include_global=True,
        )
        return "accounting.sod.override" in perms or "*" in perms

    def post(self, request):
        s = JournalDraftPostIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        allow_same_approver = bool(v.get("allow_same_approver", False))
        if allow_same_approver and not self._can_override_sod(request):
            return Response(
                {"detail": "Permiso requerido: accounting.sod.override"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            result = post_journal_drafts(
                company_id=request.company.id,
                run_id=str(v.get("run_id") or "").strip(),
                limit=int(v.get("limit") or 200),
                require_approved=bool(v.get("require_approved", True)),
                auto_approve=bool(v.get("auto_approve", False)),
                allow_same_approver=allow_same_approver,
                actor_user=request.user,
            )
        except AccountingConflictError as exc:
            raise ConflictError(str(exc)) from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "attempted": int(result.attempted),
            "approved": int(result.approved),
            "posted": int(result.posted),
            "skipped": int(result.skipped),
            "failed": int(result.failed),
            "errors": result.errors,
        }
        if bool(v.get("strict", True)) and result.failed > 0:
            return Response(payload, status=status.HTTP_409_CONFLICT)
        return Response(payload, status=status.HTTP_200_OK)


class FiscalPeriodCloseView(APIView):
    permission_classes = [rbac_permission("accounting.period.close")]

    @staticmethod
    def _can_override_sod(request) -> bool:
        perms = get_effective_permissions_for_scope(
            request.user,
            company=request.company,
            branch=getattr(request, "branch", None),
            include_global=True,
        )
        return "accounting.sod.override" in perms or "*" in perms

    def post(self, request):
        s = FiscalPeriodCloseIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        allow_same_poster = bool(v.get("allow_same_poster", False))
        if allow_same_poster and not self._can_override_sod(request):
            return Response(
                {"detail": "Permiso requerido: accounting.sod.override"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            result = close_fiscal_period(
                company_id=request.company.id,
                year=int(v["year"]),
                month=int(v["month"]),
                force=bool(v.get("force", False)),
                allow_same_poster=allow_same_poster,
                actor_user=request.user,
            )
        except AccountingConflictError as exc:
            gate_summary = getattr(exc, "gate_summary", None)
            if isinstance(gate_summary, dict):
                envelope = build_error_envelope(
                    request=request,
                    status_code=status.HTTP_409_CONFLICT,
                    exc=exc,
                    details={"detail": str(exc), "gate_summary": gate_summary},
                )
                return Response(envelope, status=status.HTTP_409_CONFLICT)
            raise ConflictError(str(exc)) from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "company_id": int(result.company_id),
            "year": int(result.year),
            "month": int(result.month),
            "status": result.status,
            "period_id": int(result.period_id),
            "pending_drafts": int(result.pending_drafts),
            "was_already_closed": bool(result.was_already_closed),
            "force_applied": bool(result.force_applied),
            "gate_summary": result.gate_summary,
        }
        return Response(payload, status=status.HTTP_200_OK)


class JournalEntryReverseView(APIView):
    permission_classes = [rbac_permission("accounting.journal_entry.reverse")]

    @staticmethod
    def _can_override_sod(request) -> bool:
        perms = get_effective_permissions_for_scope(
            request.user,
            company=request.company,
            branch=getattr(request, "branch", None),
            include_global=True,
        )
        return "accounting.sod.override" in perms or "*" in perms

    def post(self, request, entry_id: int):
        s = JournalEntryReverseIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        allow_same_poster = bool(v.get("allow_same_poster", False))
        if allow_same_poster and not self._can_override_sod(request):
            return Response(
                {"detail": "Permiso requerido: accounting.sod.override"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            result = reverse_journal_entry(
                company_id=request.company.id,
                journal_entry_id=int(entry_id),
                reason=str(v["reason"]),
                reversal_date=v.get("reversal_date"),
                allow_same_poster=allow_same_poster,
                actor_user=request.user,
            )
        except AccountingConflictError as exc:
            raise ConflictError(str(exc)) from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "original_entry_id": int(result.original_entry_id),
            "reversal_entry_id": int(result.reversal_entry_id),
            "period_id": int(result.period_id),
            "period_year": int(result.period_year),
            "period_month": int(result.period_month),
            "idempotent": bool(result.idempotent),
        }
        return Response(payload, status=status.HTTP_200_OK if result.idempotent else status.HTTP_201_CREATED)


class JournalEntryReverseBatchView(APIView):
    permission_classes = [rbac_permission("accounting.journal_entry.reverse_batch")]

    @staticmethod
    def _can_override_sod(request) -> bool:
        perms = get_effective_permissions_for_scope(
            request.user,
            company=request.company,
            branch=getattr(request, "branch", None),
            include_global=True,
        )
        return "accounting.sod.override" in perms or "*" in perms

    def post(self, request):
        s = JournalEntryReverseBatchIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        allow_same_poster = bool(v.get("allow_same_poster", False))
        if allow_same_poster and not self._can_override_sod(request):
            return Response(
                {"detail": "Permiso requerido: accounting.sod.override"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            result = reverse_journal_entries_batch(
                company_id=request.company.id,
                reason=str(v["reason"]),
                run_id=str(v.get("run_id") or "").strip(),
                year=v.get("year"),
                month=v.get("month"),
                entry_ids=v.get("entry_ids"),
                limit=int(v.get("limit") or 200),
                reversal_date=v.get("reversal_date"),
                allow_same_poster=allow_same_poster,
                actor_user=request.user,
            )
        except AccountingConflictError as exc:
            raise ConflictError(str(exc)) from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "attempted": int(result.attempted),
            "reversed": int(result.reversed),
            "idempotent": int(result.idempotent),
            "failed": int(result.failed),
            "errors": result.errors,
        }
        if bool(v.get("strict", True)) and result.failed > 0:
            return Response(payload, status=status.HTTP_409_CONFLICT)
        return Response(payload, status=status.HTTP_200_OK)
