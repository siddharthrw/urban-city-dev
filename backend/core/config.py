"""App settings, read once from the repo's .env file (and the process environment).

Everything else asks this module for paths and switches; nothing else reads .env.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_VERSION = "0.1.0"

load_dotenv(REPO_ROOT / ".env")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    llm_provider: str
    api_port: int
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    nvidia_api_key: str = ""
    nvidia_model: str = "openai/gpt-oss-20b"
    nvidia_max_tokens: int = 4096

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.duckdb"

    @property
    def llm_is_external(self) -> bool:
        """True if prompt text leaves this machine: NIM, or an Ollama server that isn't local
        (e.g. a tunnel to another computer)."""
        if self.llm_provider != "ollama":
            return True
        host = urlparse(self.ollama_host).hostname or ""
        return host not in ("localhost", "127.0.0.1", "::1")


def load_settings() -> Settings:
    raw = os.environ.get("DATA_DIR", "").strip()
    if not raw:
        raise ConfigError(
            "DATA_DIR is not set. Copy .env.example to .env and set DATA_DIR "
            r"(e.g. DATA_DIR=D:\citydata)."
        )
    data_dir = Path(raw).expanduser().resolve()
    if data_dir == REPO_ROOT or REPO_ROOT in data_dir.parents:
        raise ConfigError(f"DATA_DIR ({data_dir}) must be outside the repo ({REPO_ROOT}).")

    provider = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
    if provider not in ("ollama", "nim"):
        raise ConfigError(f"LLM_PROVIDER must be 'ollama' or 'nim', got '{provider}'.")

    env = os.environ.get
    return Settings(
        data_dir=data_dir,
        llm_provider=provider,
        api_port=int(env("API_PORT", "8000")),
        ollama_host=env("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=env("OLLAMA_MODEL", "qwen2.5:7b"),
        nvidia_api_key=env("NVIDIA_API_KEY", ""),
        nvidia_model=env("NVIDIA_MODEL", "openai/gpt-oss-20b"),
        nvidia_max_tokens=int(env("NVIDIA_MAX_TOKENS", "4096")),
    )


settings = load_settings()
