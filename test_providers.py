import json
import stat
from unittest.mock import patch

import httpx
import pytest
from openai import OpenAI
from modules.ai_interface import AIInterface
from modules.provider_registry import ProviderRegistry


@pytest.fixture
def registry(tmp_path, monkeypatch):
    for key in ("BASETEN_API_KEY", "BASETEN_BASE_URL", "BASETEN_MODEL", "PIKIT_OPENAI_API_KEY", "PIKIT_CUSTOM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    return ProviderRegistry(tmp_path / "providers.json")


def config(port=8081, key=""):
    return {"base_url": f"http://127.0.0.1:{port}/v1", "model": "test-model", "api_key": key}


def test_persistence_and_permissions(registry):
    registry.save("local", config())
    registry.save("custom", config(8082, "test-secret"))
    reloaded = ProviderRegistry(registry.path)
    assert reloaded.read_selected() == "custom"
    assert reloaded.get("local") == config()
    assert reloaded.get("custom") == config(8082, "test-secret")
    assert stat.S_IMODE(registry.path.stat().st_mode) == 0o600


@pytest.mark.parametrize("content", ['bad json', '[]', '{"selected_provider":"local","providers":[]}', '{"selected_provider":"unknown","providers":{}}'])
def test_corrupt_settings_fail_closed(registry, content):
    registry.path.write_text(content)
    ai = AIInterface(registry=ProviderRegistry(registry.path))
    with pytest.raises(RuntimeError, match="No request was sent"):
        ai.query("hello")
    assert ai.client is None


def test_baseten_defaults_and_environment(registry, monkeypatch):
    monkeypatch.setenv("BASETEN_API_KEY", "test-baseten-key")
    ai = AIInterface(registry=registry)
    assert ai.base_url == "https://inference.baseten.co/v1"
    assert ai.model == "openai/gpt-oss-120b"
    assert ai.client.api_key == "test-baseten-key"
    assert "test-baseten-key" not in repr(ai.get_config())
    monkeypatch.setenv("BASETEN_MODEL", "existing-model")
    monkeypatch.setenv("BASETEN_BASE_URL", "https://example.test/v1")
    fresh = ProviderRegistry(registry.path)
    assert fresh.get("baseten")["model"] == "existing-model"
    assert fresh.get("baseten")["base_url"] == "https://example.test/v1"


def test_missing_key_does_not_prevent_gui_start(registry):
    ai = AIInterface(registry=registry)
    with pytest.raises(RuntimeError, match="API key missing"):
        ai.query("hello")


def test_switch_changes_actual_http_request(registry, monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    def client(api_key, base_url, timeout):
        return OpenAI(api_key=api_key or "local-no-key", base_url=base_url,
                      http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr("modules.ai_interface._mk_client", client)
    for provider, port, key in (("local", 8081, ""), ("custom", 8082, "test-custom"), ("baseten", 8083, "test-baseten")):
        registry.save(provider, config(port, key))
        ai = AIInterface(registry=ProviderRegistry(registry.path))
        assert ai.query("hello") == "ok"
        assert str(requests[-1].url) == f"http://127.0.0.1:{port}/v1/chat/completions"
        assert json.loads(requests[-1].content)["model"] == "test-model"
        assert requests[-1].headers["authorization"] == f"Bearer {key or 'local-no-key'}"
    assert len(requests) == 3


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_errors_do_not_leak_response_secrets_or_fallback(registry, status):
    registry.save("local", config())
    ai = AIInterface(registry=registry)
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "secret-key"}})
    ai.client = OpenAI(api_key="test", base_url=ai.base_url, max_retries=0,
                       http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    with patch("modules.ai_interface.time.sleep"), pytest.raises(RuntimeError) as error:
        ai.query("hello")
    assert "secret-key" not in str(error.value)
    assert all(r.url.host == "127.0.0.1" for r in requests)
    assert "Authentication failed" in str(error.value) if status in (401, 403) else "HTTP" in str(error.value)


def test_save_failure_preserves_selection(registry):
    registry.save("local", config())
    with patch("modules.provider_registry.os.replace", side_effect=OSError), pytest.raises(OSError):
        registry.save("custom", config(8082, "test"))
    assert registry.read_selected() == "local"
    assert ProviderRegistry(registry.path).read_selected() == "local"


@pytest.mark.parametrize("url", ["https://user:secret@example.com/v1", "https://example.com/v1?api_key=secret", "file:///tmp/test"])
def test_reject_credentials_in_url(registry, url):
    with pytest.raises(ValueError):
        registry.save("local", dict(config(), base_url=url))


def test_connection_error_is_actionable(registry):
    registry.save("local", config())
    ai = AIInterface(registry=registry)
    def fail(request):
        raise httpx.ConnectError("secret server detail", request=request)
    ai.client = OpenAI(api_key="test", base_url=ai.base_url, max_retries=0,
                       http_client=httpx.Client(transport=httpx.MockTransport(fail)))
    with patch("modules.ai_interface.time.sleep"), pytest.raises(RuntimeError, match="Cannot connect") as error:
        ai.query("hello")
    assert "secret server detail" not in str(error.value)


def test_stream_uses_selected_endpoint(registry):
    registry.save("local", config())
    ai = AIInterface(registry=registry)
    def respond(request):
        assert str(request.url) == "http://127.0.0.1:8081/v1/chat/completions"
        assert "stream_options" not in json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              text='data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n')
    ai.client = OpenAI(api_key="test", base_url=ai.base_url,
                       http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert list(ai.stream_query("hello")) == ["hello"]


def test_switch_preserves_baseten_config(registry):
    original = dict(config(9000, "test-baseten"), model="baseten-model")
    registry.save("baseten", original)
    registry.save("local", config())
    restored = ProviderRegistry(registry.path)
    assert restored.get("baseten") == original
    with pytest.raises(ValueError, match="valid inference provider"):
        restored.get("not-a-provider")
    assert restored.read_selected() == "local"
