import pytest

from bcrm_mcp.config import HTTP, STDIO, Settings

_KEYS = ("BCRM_BASE_URL", "BCRM_TOKEN", "BCRM_TRANSPORT",
         "BCRM_HOST", "BCRM_PORT", "BCRM_PATH")


def _clear(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)


def test_missing_base_url_exits(monkeypatch):
    _clear(monkeypatch)
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_stdio_requires_token(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BCRM_BASE_URL", "http://localhost:8000")
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_stdio_with_token_ok_and_strips_trailing_slash(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BCRM_BASE_URL", "http://localhost:8000/")
    monkeypatch.setenv("BCRM_TOKEN", "bcrm_pat_x")
    s = Settings.from_env()
    assert s.transport == STDIO
    assert s.base_url == "http://localhost:8000"
    assert s.token == "bcrm_pat_x"


def test_http_rejects_server_side_token(monkeypatch):
    # A server-side token in http mode would make every caller one identity.
    _clear(monkeypatch)
    monkeypatch.setenv("BCRM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("BCRM_TRANSPORT", "http")
    monkeypatch.setenv("BCRM_TOKEN", "bcrm_pat_x")
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_http_without_token_ok_and_transport_case_insensitive(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BCRM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("BCRM_TRANSPORT", "HTTP")
    monkeypatch.setenv("BCRM_PORT", "9001")
    s = Settings.from_env()
    assert s.transport == HTTP
    assert s.token is None
    assert s.port == 9001


def test_invalid_transport_exits(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BCRM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("BCRM_TRANSPORT", "websocket")
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_non_integer_port_exits(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BCRM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("BCRM_TRANSPORT", "http")
    monkeypatch.setenv("BCRM_PORT", "not-a-number")
    with pytest.raises(SystemExit):
        Settings.from_env()
