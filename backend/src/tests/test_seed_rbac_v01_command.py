import pytest
from django.core.management import call_command

from apps.audit.models import AuditEvent
from apps.rbac.models import Permission, Role, RolePermission


@pytest.mark.django_db
def test_seed_rbac_v01_command_creates_role_permissions_and_audit():
    call_command("seed_rbac_v01")

    role = Role.objects.get(name="company_admin")
    perm = Permission.objects.get(code="hr.position.create")
    assert RolePermission.objects.filter(role=role, permission=perm).exists()
    assert Permission.objects.filter(code="payments.intent.create").exists()
    assert Permission.objects.filter(code="integration.outbox.read").exists()
    assert Permission.objects.filter(code="cec.close_run.create").exists()
    assert Permission.objects.filter(code="accounting.journal_draft.post").exists()
    assert Permission.objects.filter(code="accounting.journal_entry.reverse").exists()
    assert Permission.objects.filter(code="accounting.journal_entry.reverse_batch").exists()
    assert Permission.objects.filter(code="accounting.sod.override").exists()
    assert Permission.objects.filter(code="accounting.coa.read").exists()
    assert Permission.objects.filter(code="accounting.coa.update").exists()
    assert Permission.objects.filter(code="accounting.fx_rate.read").exists()
    assert Permission.objects.filter(code="accounting.fx_rate.update").exists()
    assert Permission.objects.filter(code="accounting.report.read").exists()
    assert Permission.objects.filter(code="accounting.revaluation.run").exists()
    assert Permission.objects.filter(code="accounting.intercompany.read").exists()
    assert Permission.objects.filter(code="accounting.intercompany.write").exists()
    assert Permission.objects.filter(code="accounting.intercompany.reconcile").exists()
    assert Permission.objects.filter(code="accounting.intercompany.dispute").exists()
    assert Permission.objects.filter(code="accounting.intercompany.settle").exists()
    assert Permission.objects.filter(code="accounting.consolidation.read").exists()
    assert Permission.objects.filter(code="accounting.consolidation.run").exists()
    assert Permission.objects.filter(code="billing.doc.print").exists()
    assert Permission.objects.filter(code="billing.doc.contingency").exists()
    assert Permission.objects.filter(code="billing.doc.contingency.resolve").exists()
    assert Permission.objects.filter(code="fuel.uom_preferences.manage").exists()

    assert AuditEvent.objects.filter(event_type="RBAC_SEEDED_V01").exists()
