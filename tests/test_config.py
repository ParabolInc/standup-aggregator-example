import pytest

from standup_aggregator.config import Config, ConfigError, load_config


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    """Prevent .env files in the working directory from leaking into tests."""
    monkeypatch.setattr("standup_aggregator.config.load_dotenv", lambda *a, **kw: False)


def test_load_config_returns_config_when_pat_present(monkeypatch):
    monkeypatch.setenv("PARABOL_PAT", "pat_abc123")
    monkeypatch.delenv("PARABOL_BASE_URL", raising=False)
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.pat == "pat_abc123"
    assert cfg.base_url == "https://action.parabol.co"
    assert cfg.graphql_url == "https://action.parabol.co/graphql"


def test_load_config_uses_custom_base_url(monkeypatch):
    monkeypatch.setenv("PARABOL_PAT", "pat_abc")
    monkeypatch.setenv("PARABOL_BASE_URL", "https://parabol.example.com")
    cfg = load_config()
    assert cfg.base_url == "https://parabol.example.com"
    assert cfg.graphql_url == "https://parabol.example.com/graphql"


def test_load_config_strips_trailing_slash_from_base_url(monkeypatch):
    monkeypatch.setenv("PARABOL_PAT", "pat_abc")
    monkeypatch.setenv("PARABOL_BASE_URL", "https://parabol.example.com/")
    cfg = load_config()
    assert cfg.graphql_url == "https://parabol.example.com/graphql"


def test_load_config_raises_when_pat_missing(monkeypatch):
    monkeypatch.delenv("PARABOL_PAT", raising=False)
    with pytest.raises(ConfigError) as excinfo:
        load_config()
    assert "PARABOL_PAT" in str(excinfo.value)


def test_load_config_raises_when_pat_has_wrong_prefix(monkeypatch):
    monkeypatch.setenv("PARABOL_PAT", "abc123")
    with pytest.raises(ConfigError) as excinfo:
        load_config()
    assert "pat_" in str(excinfo.value)
