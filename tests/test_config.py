import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_settings_default_base_url_and_env_override(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("BASE_URL", "http://example.test")
    assert get_settings().base_url == "http://example.test"
    get_settings.cache_clear()


def test_settings_default_failure_policy_is_rollback(monkeypatch):
    monkeypatch.delenv("FAILURE_POLICY", raising=False)
    assert Settings().failure_policy == "rollback"


def test_settings_rejects_unknown_failure_policy():
    with pytest.raises(ValidationError):
        Settings(failure_policy="nope")
