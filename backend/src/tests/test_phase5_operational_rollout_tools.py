from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.iam.models import OrgUnit


def _mk_scope():
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
    return company, branch


@pytest.mark.django_db
def test_export_operational_load_snapshot_writes_expected_shape(tmp_path: Path):
    company, branch = _mk_scope()
    output = tmp_path / "snapshot.json"

    call_command(
        "export_operational_load_snapshot",
        company_id=company.id,
        branch_id=branch.id,
        output=str(output),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["company_id"] == company.id
    assert payload["branch_id"] == branch.id
    assert "failed_outbox" in payload
    assert "reconciliation" in payload
    assert "fuel_compensation" in payload


@pytest.mark.django_db
def test_manage_operational_posting_pilot_stage_and_rollback(tmp_path: Path):
    company, branch = _mk_scope()
    stage1_output = tmp_path / "stage1.json"
    rollback_output = tmp_path / "rollback.json"

    call_command(
        "manage_operational_posting_pilot",
        company_id=company.id,
        branch_id=branch.id,
        action="stage1",
        output=str(stage1_output),
    )
    stage1 = json.loads(stage1_output.read_text(encoding="utf-8"))
    cfg_stage1 = stage1.get("config_after") or {}
    assert cfg_stage1.get("posting_mode") == "HYBRID"
    assert cfg_stage1.get("enable_billing") is False
    assert cfg_stage1.get("enable_inventory") is False

    call_command(
        "manage_operational_posting_pilot",
        company_id=company.id,
        branch_id=branch.id,
        action="rollback",
        output=str(rollback_output),
    )
    rollback = json.loads(rollback_output.read_text(encoding="utf-8"))
    cfg_rollback = rollback.get("config_after") or {}
    assert cfg_rollback.get("posting_mode") == "DISABLED"
    assert cfg_rollback.get("enable_billing") is False
    assert cfg_rollback.get("enable_inventory") is False
    rollback_cycle = rollback.get("rollback_cycle") or {}
    assert int(rollback_cycle.get("cycles") or 0) == 1
    assert isinstance(rollback_cycle.get("results"), list)
