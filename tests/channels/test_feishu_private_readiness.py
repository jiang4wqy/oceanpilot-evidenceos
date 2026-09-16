"""Configuration diagnostics must not impersonate live private-case acceptance."""

import pytest

from scripts import check_feishu_readiness as readiness


@pytest.mark.parametrize("enabled", [False, True])
def test_readiness_separates_configuration_from_live_acceptance(monkeypatch, capsys, enabled):
    values = {
        "FEISHU_APP_ID": "cli_synthetic",
        "FEISHU_APP_SECRET": "synthetic-secret-never-print",
        "FEISHU_VERIFICATION_TOKEN": "synthetic-token-never-print",
        "FEISHU_ENCRYPT_KEY": "synthetic-encryption-never-print",
        "OCEANPILOT_V2_BASE_URL": "https://synthetic.invalid",
        "OCEANPILOT_FEISHU_PRIVATE_CASES": "enabled" if enabled else "disabled",
        "OCEANPILOT_FEISHU_PRIVATE_OUTBOUND": "authorized-test",
    }
    monkeypatch.setattr(readiness, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        readiness.os, "getenv", lambda name, default=None: values.get(name, default)
    )
    monkeypatch.setattr(readiness, "_public_health", lambda _: True)
    monkeypatch.setattr(readiness.FeishuOutboundClient, "get_tenant_access_token", lambda _: "fake")
    assert readiness.main() == 0
    result = capsys.readouterr().out
    assert "private_outbound_configured=" + ("READY" if enabled else "NOT_READY") in result
    assert "running_process_configuration_verified=NOT_CHECKED" in result
    assert "private_pairing_and_access_verified=NOT_CHECKED" in result
    assert "fixed_host_hour_and_restart_acceptance=NOT_CHECKED" in result
    assert "live_delivery_verified=NOT_CHECKED" in result
    assert "legacy_case_bindings_used=NO" in result
    for name in (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_VERIFICATION_TOKEN",
        "FEISHU_ENCRYPT_KEY",
    ):
        assert values[name] not in result
