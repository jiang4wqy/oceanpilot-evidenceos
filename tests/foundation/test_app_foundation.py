from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.main import create_app


def test_lifespan_initializes_real_file_and_health_is_ok(tmp_path):
    db_path = tmp_path / "foundation.db"
    app = create_app(Settings(db_path=db_path))
    assert not db_path.exists()
    with TestClient(app) as client:
        assert db_path.is_file()
        assert client.get("/health").json() == {"status": "ok"}


def test_unknown_path_uses_fixed_safe_error(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path / "foundation.db"))) as client:
        response = client.get("/unknown")
    assert response.status_code == 404
    assert response.json() == {
        "status": 404,
        "code": "HTTP_ERROR",
        "detail": "request could not be completed",
    }


def test_wrong_health_method_uses_fixed_safe_error(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path / "foundation.db"))) as client:
        response = client.post("/health")
    assert response.status_code == 405
    assert response.json() == {
        "status": 405,
        "code": "HTTP_ERROR",
        "detail": "request could not be completed",
    }


def test_unexpected_exception_does_not_echo_sentinel(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "foundation.db"))
    app.get("/boom")(lambda: (_ for _ in ()).throw(RuntimeError("SECRET-SENTINEL")))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert "SECRET-SENTINEL" not in response.text
    assert response.json() == {
        "status": 500,
        "code": "INTERNAL_ERROR",
        "detail": "internal server error",
    }


def test_sensitive_error_has_priority_over_value_error(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "foundation.db"))
    app.get("/sensitive")(lambda: (_ for _ in ()).throw(SensitiveDataRejected()))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/sensitive")
    assert response.status_code == 422
    assert response.json() == {
        "status": 422,
        "code": "SENSITIVE_DATA_REJECTED",
        "detail": "request contains disallowed sensitive data",
    }
