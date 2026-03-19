from types import SimpleNamespace

from apps.modulos.iam.context import RequestContext
from config.error_envelope import build_error_envelope


def test_error_envelope_includes_context():
    ctx = RequestContext(
        request_id="req-123",
        company_id=10,
        branch_id=20,
        data_company_id=11,
        data_branch_id=21,
    )
    request = SimpleNamespace(request_id="req-123", ctx=ctx)

    payload = build_error_envelope(request=request, status_code=403, exc=None, details={"detail": "x"})

    context = payload["error"]["details"].get("context")
    assert context == {
        "company_id": 10,
        "branch_id": 20,
        "data_company_id": 11,
        "data_branch_id": 21,
    }
