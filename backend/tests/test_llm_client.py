"""LLM client with the network replaced: no Ollama or NVIDIA needed to run these."""
import dataclasses
import json

import httpx
import pytest

from core.config import settings
from core.llm import client as llm


class FakeResponse:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=httpx.Request("POST", "http://x"), response=httpx.Response(self.status_code))

    def json(self):
        return self._body


def test_ollama_payload_is_local_low_temperature_json(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        sent.update(url=url, json=json)
        return FakeResponse({"message": {"content": '{"ok": true}'}})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.chat_json("hi", "sys") == {"ok": True}
    assert sent["url"].endswith("/api/chat") and "localhost" in sent["url"]
    assert sent["json"]["format"] == "json" and sent["json"]["options"]["temperature"] <= 0.2
    assert sent["json"]["messages"][0] == {"role": "system", "content": "sys"}


def test_info_reports_local_by_default():
    i = llm.info()
    assert i.provider == "ollama" and not i.external


def test_nim_needs_a_key_and_is_external():
    cfg = dataclasses.replace(settings, llm_provider="nim", nvidia_api_key="")
    assert llm.info(cfg).external
    with pytest.raises(llm.LLMError, match="NVIDIA_API_KEY"):
        llm.chat("hi", cfg=cfg)


def test_nim_payload_and_empty_reasoning_output(monkeypatch):
    cfg = dataclasses.replace(settings, llm_provider="nim", nvidia_api_key="k", nvidia_max_tokens=4096)
    sent = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        sent.update(json=json, headers=headers)
        return FakeResponse({"choices": [{"message": {"content": None}, "finish_reason": "length"}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(llm.LLMError, match="NVIDIA_MAX_TOKENS"):
        llm.chat("hi", json_mode=True, cfg=cfg)
    assert sent["json"]["max_tokens"] == 4096 and sent["json"]["response_format"] == {"type": "json_object"}
    assert sent["headers"]["Authorization"] == "Bearer k"


def test_chat_json_retries_then_gives_up(monkeypatch):
    replies = iter(["not json", '["a list"]', json.dumps({"fine": 1})])
    monkeypatch.setattr(llm, "chat", lambda *a, **k: next(replies))
    assert llm.chat_json("q") == {"fine": 1}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "never json")
    with pytest.raises(llm.LLMError, match="No valid JSON"):
        llm.chat_json("q", retries=1)


def test_unreachable_ollama_is_a_clear_error(monkeypatch):
    def fake_post(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(llm.LLMError, match="Could not reach Ollama"):
        llm.chat("hi")
