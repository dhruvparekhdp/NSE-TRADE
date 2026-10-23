"""Free-tier AI budget (same idea as crypto collectors/llm_budget.py).

Optional shared path via settings so both engines don't double-burn Groq/OpenRouter.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

SAFETY = 0.85

LIMITS: dict[str, dict] = {
    "groq/*": {"rpm": 30, "rpd": 1000, "tpm": 6000, "tpd": 200_000},
    "openrouter/*": {"rpm": 20, "rpd": 50, "tpm": None, "tpd": None},
    "hf/classify": {"rpm": 20, "rpd": None, "tpm": None, "tpd": None},
    "hf/*": {"rpm": 5, "rpd": 100, "tpm": None, "tpd": None},
}


def _key(provider: str, model: str) -> str:
    return f"{provider}/{model}"


class Budget:
    def __init__(self, path: str | Path = "data/llm_budget.json") -> None:
        self.path = Path(path)
        self.limits = dict(LIMITS)
        self._lock = threading.Lock()
        self.models: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            self.models = json.loads(self.path.read_text(encoding="utf-8")).get("models", {})
        except (OSError, ValueError):
            self.models = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"models": self.models}), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def limits_for(self, key: str) -> dict:
        if key in self.limits:
            return self.limits[key]
        prov = key.split("/", 1)[0]
        return self.limits.get(f"{prov}/*", {})

    def _bucket(self, key: str) -> dict:
        b = self.models.setdefault(key, {"calls": [], "tokens": [], "cool_until": 0.0})
        now = time.time()
        b["calls"] = [t for t in b.get("calls", []) if now - t < 86_400]
        b["tokens"] = [(t, n) for t, n in b.get("tokens", []) if now - t < 86_400]
        return b

    def allow(self, provider: str, model: str, est_tokens: int = 500) -> tuple[bool, float, str]:
        key = _key(provider, model)
        with self._lock:
            b = self._bucket(key)
            now = time.time()
            if b.get("cool_until", 0) > now:
                return False, b["cool_until"] - now, "cooldown"
            lim = self.limits_for(key)
            day_calls = len(b["calls"])
            min_calls = sum(1 for t in b["calls"] if now - t < 60)
            day_tok = sum(n for t, n in b["tokens"] if now - t < 86_400)
            min_tok = sum(n for t, n in b["tokens"] if now - t < 60)
            if lim.get("rpd") and day_calls >= SAFETY * lim["rpd"]:
                return False, 3600.0, "rpd"
            if lim.get("rpm") and min_calls >= SAFETY * lim["rpm"]:
                return False, 60.0, "rpm"
            if lim.get("tpd") and day_tok + est_tokens >= SAFETY * lim["tpd"]:
                return False, 3600.0, "tpd"
            if lim.get("tpm") and min_tok + est_tokens >= SAFETY * lim["tpm"]:
                return False, 60.0, "tpm"
            return True, 0.0, "ok"

    def observe(self, provider: str, model: str, tokens: int) -> None:
        key = _key(provider, model)
        with self._lock:
            b = self._bucket(key)
            now = time.time()
            b["calls"].append(now)
            b["tokens"].append((now, int(tokens)))
            self._save()

    def cooldown(self, provider: str, model: str, seconds: float) -> None:
        key = _key(provider, model)
        with self._lock:
            b = self._bucket(key)
            b["cool_until"] = max(b.get("cool_until", 0), time.time() + max(60.0, seconds))
            self._save()


_budget: Budget | None = None


def budget() -> Budget:
    global _budget
    if _budget is None:
        from config.settings import get_settings

        s = get_settings()
        path = s.shared_llm_budget_path or (Path(s.data_dir) / "llm_budget.json")
        _budget = Budget(path)
    return _budget


def reset_budget_for_tests(path: str | Path) -> Budget:
    global _budget
    _budget = Budget(path)
    return _budget


def parse_retry_seconds(text: str) -> float | None:
    m = re.search(r"try again in\s+((?:\d+(?:\.\d+)?(?:ms|h|m|s))+)", text or "", re.I)
    if not m:
        return None
    total = 0.0
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", m.group(1)):
        total += float(num) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total or None
