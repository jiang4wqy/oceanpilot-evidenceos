from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def test_lifespan_owns_database_initialization(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(Settings(db_path=db_path))
    assert not db_path.exists()

    with TestClient(app, raise_server_exceptions=False) as client:
        assert db_path.is_file()
        assert client.get("/health").json() == {"status": "ok"}


def test_openapi_freezes_paths_replay_and_problem_contract(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    document = app.openapi()

    assert set(document["paths"]) == {
        "/health",
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/evidence",
        "/api/v1/cases/{case_id}/diagnose",
        "/api/v1/integrations/feishu/events",
        "/api/v1/integrations/feishu/card-actions",
    }
    diagnose = document["paths"]["/api/v1/cases/{case_id}/diagnose"]["post"]
    assert {"200", "201", "409", "422", "500", "503"}.issubset(diagnose["responses"])
    assert "DiagnosisResponse" in document["components"]["schemas"]
    diagnosis_schema = document["components"]["schemas"]["DiagnosisResponse"]
    assert "audit_reference" in diagnosis_schema["required"]

    problem_schema = document["components"]["schemas"]["ProblemDetails"]
    assert {"case_id", "missing_fields", "current_revision"}.issubset(
        problem_schema["properties"]
    )
    assert not {"case_id", "missing_fields", "current_revision"}.intersection(
        problem_schema["required"]
    )
    safe_error_ref = problem_schema["properties"]["errors"]["anyOf"][0]["items"][
        "$ref"
    ]
    assert safe_error_ref == "#/components/schemas/SafeValidationError"
    assert "SafeValidationError" in document["components"]["schemas"]
    create = document["paths"]["/api/v1/cases"]["post"]
    assert create["responses"]["201"]["headers"]["Location"]["required"] is True
    for status in ("409", "422", "500", "503"):
        content = diagnose["responses"][status]["content"]
        assert set(content) == {"application/problem+json"}

    for path_item in document["paths"].values():
        for operation in path_item.values():
            for status, response in operation["responses"].items():
                if status in {"404", "409", "422", "500", "503"}:
                    assert set(response["content"]) == {"application/problem+json"}
