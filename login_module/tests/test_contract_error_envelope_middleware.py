import json

import pytest
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory

from config.middleware.api_error_envelope import ApiErrorEnvelopeMiddleware


@pytest.mark.django_db(transaction=False)
def test_api_error_envelope_wraps_non_json_httpresponse_under_api_paths():
    rf = RequestFactory()
    request = rf.get("/api/_test/plain-error")
    request.request_id = "req-mw-plain"

    def get_response(_request):
        return HttpResponse("Oops", status=400, content_type="text/plain")

    mw = ApiErrorEnvelopeMiddleware(get_response)
    response = mw(request)

    assert response.status_code == 400
    assert (response.get("Content-Type") or "").lower().startswith("application/json")

    payload = json.loads(response.content.decode("utf-8"))
    assert payload["error"]["http_status"] == 400
    assert payload["error"]["code"] == "BAD_REQUEST"
    assert payload["error"]["request_id"] == "req-mw-plain"
    assert payload["error"]["message"] == "Oops"


@pytest.mark.django_db(transaction=False)
def test_api_error_envelope_does_not_double_wrap_if_already_enveloped():
    rf = RequestFactory()
    request = rf.get("/api/_test/already")
    request.request_id = "req-mw-already"

    already = {"error": {"code": "X", "http_status": 418}}

    def get_response(_request):
        return JsonResponse(already, status=418)

    mw = ApiErrorEnvelopeMiddleware(get_response)
    response = mw(request)

    assert response.status_code == 418
    payload = json.loads(response.content.decode("utf-8"))
    assert payload == already
