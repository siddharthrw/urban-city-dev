"""Small provider-agnostic LLM client: local Ollama (default) or NVIDIA NIM (OpenAI-compatible).

Ported from the earlier urban_city project. Rules for callers:
  - The LLM never does geometry or arithmetic.
  - Never put raw partner data in a prompt: only summaries, column names, rule text.
    With LLM_PROVIDER=nim the prompt leaves this machine.
"""
import json
from dataclasses import dataclass

import httpx

from core.config import Settings, settings

TEMPERATURE = 0.1
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMInfo:
    provider: str
    model: str
    external: bool  # True = prompt text is sent off this machine


def info(cfg: Settings = settings) -> LLMInfo:
    if cfg.llm_provider == "nim":
        return LLMInfo("nim", cfg.nvidia_model, True)
    return LLMInfo("ollama", cfg.ollama_model, False)


def _messages(prompt: str, system: str) -> list[dict]:
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def _chat_ollama(cfg: Settings, messages: list, json_mode: bool, timeout: float) -> str:
    payload = {"model": cfg.ollama_model, "messages": messages, "stream": False,
               "options": {"temperature": TEMPERATURE}}
    if json_mode:
        payload["format"] = "json"
    url = f"{cfg.ollama_host.rstrip('/')}/api/chat"
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach Ollama at {url}: {e}") from e
    return r.json()["message"]["content"]


def _chat_nim(cfg: Settings, messages: list, json_mode: bool, timeout: float) -> str:
    if not cfg.nvidia_api_key:
        raise LLMError("LLM_PROVIDER=nim but NVIDIA_API_KEY is not set in .env")
    payload = {"model": cfg.nvidia_model, "messages": messages, "temperature": TEMPERATURE,
               "max_tokens": cfg.nvidia_max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(NIM_URL, json=payload, timeout=timeout,
                       headers={"Authorization": f"Bearer {cfg.nvidia_api_key}"})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach NVIDIA NIM: {e}") from e
    choice = r.json()["choices"][0]
    content = choice["message"]["content"]
    if content is None:
        # gpt-oss is a reasoning model: it can spend the whole budget thinking and return nothing.
        raise LLMError(f"NIM returned no content (finish_reason={choice.get('finish_reason')}); "
                       "raise NVIDIA_MAX_TOKENS.")
    return content


def chat(prompt: str, system: str = "", *, json_mode: bool = False, timeout: float = 180,
         cfg: Settings = settings) -> str:
    fn = _chat_nim if cfg.llm_provider == "nim" else _chat_ollama
    return fn(cfg, _messages(prompt, system), json_mode, timeout)


def chat_json(prompt: str, system: str = "", *, retries: int = 2, timeout: float = 180,
              cfg: Settings = settings) -> dict:
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            out = json.loads(chat(prompt, system, json_mode=True, timeout=timeout, cfg=cfg))
            if isinstance(out, dict):
                return out
            last = LLMError(f"Expected a JSON object, got {type(out).__name__}")
        except (json.JSONDecodeError, LLMError) as e:
            last = e
    raise LLMError(f"No valid JSON after {retries + 1} attempts: {last}")
