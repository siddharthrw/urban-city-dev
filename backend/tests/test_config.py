import pytest

from core import config


def test_missing_data_dir(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    with pytest.raises(config.ConfigError, match="DATA_DIR is not set"):
        config.load_settings()


def test_data_dir_inside_repo_is_refused(monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(config.REPO_ROOT / "data"))
    with pytest.raises(config.ConfigError, match="outside the repo"):
        config.load_settings()


def test_unknown_llm_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(config.ConfigError, match="LLM_PROVIDER"):
        config.load_settings()


@pytest.mark.parametrize("host, external", [
    ("http://localhost:11434", False),
    ("http://127.0.0.1:11434", False),
    ("https://tuner-slip-arm-nathan.trycloudflare.com", True),   # a tunnel to another machine
    ("http://192.168.1.20:11434", True),
])
def test_remote_ollama_counts_as_external(monkeypatch, tmp_path, host, external):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", host)
    assert config.load_settings().llm_is_external is external


def test_nim_is_always_external(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "nim")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    assert config.load_settings().llm_is_external is True


def test_defaults_are_local(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    s = config.load_settings()
    assert s.data_dir == tmp_path.resolve() and s.catalog_path == tmp_path.resolve() / "catalog.duckdb"
    assert s.llm_provider == "ollama" and not s.llm_is_external
    assert s.ollama_model == "qwen2.5:7b" and s.nvidia_max_tokens >= 4096
