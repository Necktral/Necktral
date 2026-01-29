import pytest
from django.test import Client


@pytest.mark.django_db(transaction=False)
def test_api_404_is_contractual_json_and_preserves_request_id_header():
    client = Client()
    rid = "req-404"

    response = client.get(
        "/api/this-endpoint-does-not-exist/",
        HTTP_X_REQUEST_ID=rid,
    )

    assert response.status_code == 404
    assert response.headers.get("X-Request-Id") == rid

    payload = response.json()
    assert "error" in payload
    assert payload["error"]["http_status"] == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["error"]["request_id"] == rid
    assert payload["error"]["retryable"] is False
