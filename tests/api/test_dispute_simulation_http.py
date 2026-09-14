from uuid import uuid4

from tests.api.test_dispute_intake_http import stack  # noqa: F401
from tests.application.test_dispute_simulation import request


def test_simulation_http_requires_scope_confirmation_and_valid_preview(stack):  # noqa: F811
    app, sessions = stack
    operator = sessions["operator-a"]
    data = request()
    endpoint = "/api/v2/intake/simulations"
    assert sessions["merchant-a"].post(endpoint + "/preview", json=data).status_code == 403
    assert sessions["operator-b"].post(endpoint + "/preview", json=data).status_code == 403
    preview = operator.post(endpoint + "/preview", json=data)
    assert preview.status_code == 200, preview.text
    body = dict(
        input=data,
        confirmed=True,
        request_id=str(uuid4()),
        confirmation_token=preview.json()["confirmation_token"],
    )
    assert operator.post(endpoint, json=body | {"confirmed": False}).status_code == 422
    assert operator.post(endpoint, json=body | {"confirmation_token": "x" * 64}).status_code == 409
    response = operator.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["case"]["merchant_decision"] == "NONE"
    again = operator.post(endpoint, json=body)
    assert again.status_code == 200
    assert again.json()["case_id"] == response.json()["case_id"]
    assert (
        sessions["merchant-a"].get("/api/v2/cases/" + response.json()["case_id"]).status_code == 200
    )
