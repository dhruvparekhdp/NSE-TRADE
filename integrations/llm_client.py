"""Slim ask_json — same role idea as crypto, NSE-sized (news_score / research only)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from config.settings import get_settings
from integrations.llm_budget import budget, parse_retry_seconds


@dataclass
class LLMReply:
    data: dict[str, Any]
    served_by: str
    raw: str


def _log_call(role: str, served_by: str, prompt: str, raw: str) -> None:
    s = get_settings()
    if not s.llm_log_calls:
        return
    d = Path(s.data_dir) / "llm_calls"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{int(time.time() * 1000)}_{role}.json"
    path.write_text(
        json.dumps({"role": role, "served_by": served_by, "prompt": prompt[:4000], "raw": raw[:8000]}, indent=2),
        encoding="utf-8",
    )


def _openai_chat(base: str, key: str, model: str, system: str, user: str, timeout: float = 60.0) -> str:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.1,
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{base.rstrip('/')}/chat/completions", headers=headers, json=body)
        if r.status_code == 429:
            wait = parse_retry_seconds(r.text) or float(r.headers.get("retry-after") or 60)
            budget().cooldown("groq" if "groq" in base else "openrouter", model, wait)
            r.raise_for_status()
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no json object in reply")
    return json.loads(text[start : end + 1])


def ask_json(role: str, system: str, user: str) -> LLMReply | None:
    """Try Groq → OpenRouter → skip. Honours budget. Returns None if all fail / unconfigured."""
    s = get_settings()
    chain: list[tuple[str, str, str, str]] = []
    if s.groq_api_key:
        chain.append(
            (
                "groq",
                "https://api.groq.com/openai/v1",
                s.groq_api_key.get_secret_value(),
                s.groq_model,
            )
        )
    if s.openrouter_api_key:
        chain.append(
            (
                "openrouter",
                "https://openrouter.ai/api/v1",
                s.openrouter_api_key.get_secret_value(),
                s.openrouter_model,
            )
        )
    for provider, base, key, model in chain:
        ok, _wait, why = budget().allow(provider, model, est_tokens=800)
        if not ok:
            continue
        try:
            raw = _openai_chat(base, key, model, system, user)
            data = _extract_json(raw)
            budget().observe(provider, model, tokens=800)
            served = f"{provider}/{model}"
            _log_call(role, served, user, raw)
            return LLMReply(data=data, served_by=served, raw=raw)
        except Exception:
            continue
    return None
