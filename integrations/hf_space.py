"""Call the same HF Space as crypto for FinBERT classify (docs/SHARED_INFRA.md)."""

from __future__ import annotations

from typing import Any

import httpx

from config.settings import get_settings
from integrations.llm_budget import budget


def classify(texts: list[str], timeout: float = 120.0) -> list[dict[str, Any]]:
    """POST /v1/classify — returns list of {positive, negative, neutral} (or empty if unconfigured)."""
    if not texts:
        return []
    s = get_settings()
    if not s.hf_base_url:
        return []
    ok, _w, _why = budget().allow("hf", "classify", est_tokens=0)
    if not ok:
        return []
    headers = {"Content-Type": "application/json"}
    if s.hf_space_api_key:
        headers["Authorization"] = f"Bearer {s.hf_space_api_key.get_secret_value()}"
    url = s.hf_base_url.rstrip("/") + "/v1/classify"
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json={"texts": texts})
        if r.status_code >= 400:
            return []
        budget().observe("hf", "classify", 0)
        rows = r.json().get("results") or r.json().get("data") or []
        return list(rows)[: len(texts)]
