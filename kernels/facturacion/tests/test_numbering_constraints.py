from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections
from django.db.models import Count

from apps.modulos.iam.models import OrgUnit
from kernels.facturacion.models import BillingDocument, BillingSequence, DocStatus
from kernels.facturacion.services import create_draft, issue_doc


def _build_scope():
    token = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding {token}",
        code=f"H-{token}",
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company {token}",
        code=f"C-{token}",
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch {token}",
        code=f"B-{token}",
    )

    User = get_user_model()
    user = User.objects.create_user(
        username=f"tester_{token}",
        email=f"tester_{token}@example.com",
        password="Secret123!",
    )
    request = SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        META={},
        headers={},
        path="/test/billing/",
        method="POST",
        request_id=f"req-{token}",
    )
    return user, request


def _write_race_report(payload: dict) -> None:
    reports_dir = Path(__file__).resolve().parents[3] / "qa" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_file = reports_dir / "facturacion_race_report.json"
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


@pytest.mark.django_db
def test_allows_multiple_drafts_with_number_zero_for_same_scope():
    user, request = _build_scope()

    draft_a = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="K6",
        currency="NIO",
        customer_name="Cliente A",
        customer_ref="A-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio A",
                "quantity": "1",
                "unit_price": "10",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )
    draft_b = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="K6",
        currency="NIO",
        customer_name="Cliente B",
        customer_ref="B-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio B",
                "quantity": "1",
                "unit_price": "20",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )

    docs = list(BillingDocument.objects.filter(id__in=[draft_a.doc_id, draft_b.doc_id]).order_by("id"))
    assert len(docs) == 2
    assert docs[0].number == 0
    assert docs[1].number == 0
    assert docs[0].status == DocStatus.DRAFT
    assert docs[1].status == DocStatus.DRAFT


@pytest.mark.django_db
def test_issue_assigns_monotonic_nonzero_numbers_for_same_series():
    user, request = _build_scope()

    draft_a = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="K6",
        currency="NIO",
        customer_name="Cliente A",
        customer_ref="A-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio A",
                "quantity": "1",
                "unit_price": "10",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )
    draft_b = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="K6",
        currency="NIO",
        customer_name="Cliente B",
        customer_ref="B-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio B",
                "quantity": "1",
                "unit_price": "20",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )

    out_a = issue_doc(
        request=request,
        actor=user,
        doc_id=draft_a.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )
    out_b = issue_doc(
        request=request,
        actor=user,
        doc_id=draft_b.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )

    assert int(out_a["number"]) == 1
    assert int(out_b["number"]) == 2

    issued_numbers = list(
        BillingDocument.objects.filter(
            id__in=[draft_a.doc_id, draft_b.doc_id],
            status=DocStatus.ISSUED,
        )
        .order_by("number")
        .values_list("number", flat=True)
    )
    assert issued_numbers == [1, 2]


@pytest.mark.django_db(transaction=True)
def test_issue_race_recovers_on_sequence_integrity_error_and_keeps_unique_numbers(monkeypatch):
    user, request = _build_scope()
    series = f"RACE-{uuid.uuid4().hex[:6]}"

    draft_a = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series=series,
        currency="NIO",
        customer_name="Cliente A",
        customer_ref="A-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio A",
                "quantity": "1",
                "unit_price": "10",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"race-draft-{uuid.uuid4().hex}",
    )
    draft_b = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series=series,
        currency="NIO",
        customer_name="Cliente B",
        customer_ref="B-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio B",
                "quantity": "1",
                "unit_price": "20",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"race-draft-{uuid.uuid4().hex}",
    )

    create_barrier = Barrier(2)
    original_create = BillingSequence.objects.create
    create_integrity_errors = 0
    capture_exceptions: list[str] = []
    captured_numbers: list[int] = []
    captured_doc_ids: list[int] = []

    def _wrapped_create(*args, **kwargs):
        nonlocal create_integrity_errors
        if kwargs.get("series") == series:
            create_barrier.wait(timeout=10)
        try:
            return original_create(*args, **kwargs)
        except IntegrityError:
            create_integrity_errors += 1
            raise

    monkeypatch.setattr(BillingSequence.objects, "create", _wrapped_create)

    issue_barrier = Barrier(2)

    def _issue(doc_id: int) -> dict:
        close_old_connections()
        issue_barrier.wait(timeout=10)
        try:
            return issue_doc(
                request=request,
                actor=user,
                doc_id=doc_id,
                apply_inventory=False,
                print_after_issue=False,
                idempotency_key=f"race-issue-{uuid.uuid4().hex}",
            )
        finally:
            close_old_connections()

    for _attempt in range(2):
        capture_exceptions.clear()
        captured_numbers.clear()
        captured_doc_ids.clear()
        issue_barrier.reset()
        create_barrier.reset()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_issue, draft_a.doc_id), pool.submit(_issue, draft_b.doc_id)]
            for fut in futures:
                try:
                    out = fut.result(timeout=30)
                    captured_numbers.append(int(out["number"]))
                    captured_doc_ids.append(int(out["doc_id"]))
                except Exception as exc:  # pragma: no cover - diagnostic capture
                    capture_exceptions.append(f"{type(exc).__name__}: {exc}")
        if not capture_exceptions:
            break

    duplicates = (
        BillingDocument.objects.filter(
            company=request.company,
            branch=request.branch,
            doc_type="INVOICE",
            series=series,
            number__gt=0,
        )
        .values("company_id", "branch_id", "doc_type", "series", "number")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
        .count()
    )

    report_payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not capture_exceptions and sorted(captured_numbers) == [1, 2] and duplicates == 0 else "FAIL",
        "series": series,
        "docs_emitted": sorted(captured_doc_ids),
        "numbers": sorted(captured_numbers),
        "duplicates_gt0": duplicates,
        "create_integrity_errors": create_integrity_errors,
        "exceptions": capture_exceptions,
    }
    _write_race_report(report_payload)

    assert not capture_exceptions, f"unexpected concurrent issue exceptions: {capture_exceptions}"
    assert "TransactionManagementError" not in " ".join(capture_exceptions)
    assert sorted(captured_numbers) == [1, 2]
    assert duplicates == 0
    assert create_integrity_errors >= 1
