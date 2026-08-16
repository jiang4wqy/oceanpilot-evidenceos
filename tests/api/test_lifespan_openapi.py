from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def test_lifespan_owns_database_initialization(tmp_path):
    db_path = tmp_path / "api.db"
    rules_db_path = tmp_path / "rules.db"
    app = create_app(Settings(db_path=db_path, rules_db_path=rules_db_path))
    assert not db_path.exists()
    assert not rules_db_path.exists()

    with TestClient(app, raise_server_exceptions=False) as client:
        assert db_path.is_file()
        assert rules_db_path.is_file()
        assert client.get("/health").json() == {"status": "ok"}


def test_openapi_freezes_paths_replay_and_problem_contract(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    document = app.openapi()

    assert set(document["paths"]) == {
        "/health",
        "/api/v1/admin/overview",
        "/api/v1/agent/turns",
        "/api/v1/agent/cases/{case_id}/review-decisions",
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/evidence",
        "/api/v1/cases/{case_id}/diagnose",
        "/api/v1/integrations/feishu/events",
        "/api/v1/integrations/feishu/card-actions",
        "/api/v1/chargeback/catalog",
        "/api/v1/chargeback/cases",
        "/api/v1/chargeback/cases/{case_id}",
        "/api/v1/chargeback/cases/{case_id}/appeal",
        "/api/v1/chargeback/cases/{case_id}/audit",
        "/api/v1/chargeback/cases/{case_id}/card-network",
        "/api/v1/chargeback/cases/{case_id}/confirm",
        "/api/v1/chargeback/cases/{case_id}/evidence",
        "/api/v1/chargeback/cases/{case_id}/evidence/withdraw-latest",
        "/api/v1/chargeback/cases/{case_id}/finalize",
        "/api/v1/chargeback/cases/{case_id}/package",
        "/api/v1/chargeback/cases/{case_id}/rule-reference",
        "/api/v1/chargeback/metrics",
        "/api/v1/chargeback/prevention/assess",
        "/api/v1/chargeback/rules",
        "/api/v1/chargeback/rules/{rule_version_id}",
        "/api/v1/chargeback/safety/scan",
    }
    diagnose = document["paths"]["/api/v1/cases/{case_id}/diagnose"]["post"]
    assert {"200", "201", "409", "422", "500", "503"}.issubset(diagnose["responses"])
    assert "DiagnosisResponse" in document["components"]["schemas"]
    diagnosis_schema = document["components"]["schemas"]["DiagnosisResponse"]
    assert "audit_reference" in diagnosis_schema["required"]

    assessment_schema = document["components"]["schemas"]["ChargebackAssessmentDTO"]
    legacy_readiness = assessment_schema["properties"]["win_likelihood"]
    assert legacy_readiness["deprecated"] is True
    assert legacy_readiness["description"] == (
        "Deprecated compatibility alias for evidence_readiness. This deterministic value "
        "measures evidence readiness, not predicted chargeback win probability."
    )

    appeal_schema = document["components"]["schemas"]["ChargebackAppealResponse"]
    assert {"synthetic", "connector_kind"}.issubset(appeal_schema["required"])
    assert appeal_schema["properties"]["synthetic"]["const"] is True
    assert appeal_schema["properties"]["connector_kind"]["const"] == "IN_PROCESS_MOCK"

    problem_schema = document["components"]["schemas"]["ProblemDetails"]
    assert {"case_id", "missing_fields", "current_revision"}.issubset(problem_schema["properties"])
    assert not {"case_id", "missing_fields", "current_revision"}.intersection(
        problem_schema["required"]
    )
    safe_error_ref = problem_schema["properties"]["errors"]["anyOf"][0]["items"]["$ref"]
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
