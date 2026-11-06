"""NSE-004: live SmartAPI orders stay impossible unless both new flags are on."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
from aiohttp import web

from broker.angel import AngelBroker
from broker.errors import Rejected
from broker.live_guard import (
    ORDER_METHODS,
    flags_allow_live,
    live_orders_allowed,
    startup_banner,
)
from broker.paper import PaperBroker
from config.settings import get_settings, reset_settings_cache
from core.orders import OrderManager
from core.types import Bar, Signal
from engine.book_a_shadow import shadow_outcomes, shadow_scan
from engine.paper_engine import eod_fill_pending, resolve_outcomes
from strategies.orb import ORB

ROOT = Path(__file__).resolve().parents[1]
GUARDED = ROOT / "broker" / "live_guard.py"


class BoomAPI:
    """Fails the test if a SmartAPI order method actually runs."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def placeOrder(self, *_a, **_k):  # noqa: N802
        self.calls.append("placeOrder")
        raise AssertionError("SmartAPI placeOrder was called")

    def modifyOrder(self, *_a, **_k):  # noqa: N802
        self.calls.append("modifyOrder")
        raise AssertionError("SmartAPI modifyOrder was called")

    def cancelOrder(self, *_a, **_k):  # noqa: N802
        self.calls.append("cancelOrder")
        raise AssertionError("SmartAPI cancelOrder was called")


def test_flags_allow_live_needs_both_env_vars_and_the_dual_gate():
    assert flags_allow_live(enabled=True, confirmed=True, mode="live", live_orders=True) is True
    assert flags_allow_live(enabled=False, confirmed=True, mode="live", live_orders=True) is False
    assert flags_allow_live(enabled=True, confirmed=False, mode="live", live_orders=True) is False
    assert flags_allow_live(enabled=True, confirmed=True, mode="paper", live_orders=True) is False
    assert flags_allow_live(enabled=True, confirmed=True, mode="live", live_orders=False) is False


def test_defaults_keep_live_off():
    assert live_orders_allowed() is False
    banner = startup_banner()
    assert "mode=paper" in banner
    assert "live=OFF" in banner


def test_every_angel_order_path_raises_and_does_not_call_the_sdk():
    api = BoomAPI()
    broker = AngelBroker(api=api, sleep=lambda _s: None)
    with pytest.raises(Rejected):
        broker.place_order({"tradingsymbol": "SBIN-EQ", "transactiontype": "BUY"})
    with pytest.raises(Rejected):
        broker.modify_order({"orderid": "1", "tradingsymbol": "SBIN-EQ"})
    with pytest.raises(Rejected):
        broker.cancel_order("1", "NORMAL")
    assert api.calls == []


def test_env_flags_cannot_arm_live_orders_under_pytest(monkeypatch):
    """Pytest forces the new flags off, same as live_orders (plan A15)."""
    monkeypatch.setenv("LIVE_ORDERS_ENABLED", "true")
    monkeypatch.setenv("LIVE_ORDERS_CONFIRM", "true")
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("LIVE_ORDERS", "true")
    reset_settings_cache()
    settings = get_settings()
    assert settings.live_orders_enabled is False
    assert settings.live_orders_confirm is False
    assert settings.live_orders is False
    assert live_orders_allowed() is False
    api = BoomAPI()
    with pytest.raises(Rejected):
        AngelBroker(api=api, sleep=lambda _s: None).place_order({"tradingsymbol": "SBIN-EQ"})
    assert api.calls == []


def test_paper_and_shadow_never_call_smartapi_order_methods(monkeypatch):
    """Paper and shadow books run against a mock that fails if an order method is used."""

    def boom(*_a, **_k):
        raise AssertionError("paper/shadow called a SmartAPI order method")

    monkeypatch.setattr("broker.live_guard.place_order", boom)
    monkeypatch.setattr("broker.live_guard.modify_order", boom)
    monkeypatch.setattr("broker.live_guard.cancel_order", boom)

    bar = Bar(1_700_000_000_000, 100.0, 101.0, 99.0, 100.5, 1000)
    shadow_scan(symbol="SBIN", bars_1m=[bar], strategies=[ORB()], decision_ms=bar.ts_ms + 60_000)
    assert shadow_outcomes([], [bar]) == []

    signal = Signal(
        ts_ms=bar.ts_ms,
        symbol="SBIN",
        side=1,
        entry_ref=100.0,
        stop=95.0,
        target=110.0,
        time_exit_ms=None,
        strategy="S6_swing",
        book="B",
    )
    eod_fill_pending([signal], {})
    resolve_outcomes([signal], {"SBIN": [bar]})

    paper = PaperBroker(capital=100_000)
    paper.place_order(
        client_tag="ne261106BXX0001",
        symbol="SBIN",
        side="BUY",
        qty=1,
        order_type="LIMIT",
        product="DELIVERY",
        purpose="entry",
        price=100.0,
        trigger=None,
    )
    paper.cancel_order("ne261106BXX0001")
    OrderManager(paper).submit_bracket(
        trade_id=1,
        trade_date="2026-11-06",
        strategy_code="S6",
        symbol="SBIN",
        side=1,
        qty=1,
        book="B",
        entry_ref=100.0,
        stop=95.0,
        target=110.0,
        now_ms=bar.ts_ms,
    )


def test_smartapi_order_methods_are_called_only_inside_the_guard():
    """AST scan: placeOrder / modifyOrder / cancelOrder calls live only in broker/live_guard.py."""
    offenders: list[str] = []
    guarded_hits: dict[str, list[int]] = {name: [] for name in ORDER_METHODS}
    assert_lines: dict[str, list[int]] = {}

    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", "var", "__pycache__"} for part in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ORDER_METHODS:
                continue
            if rel != "broker/live_guard.py":
                offenders.append(f"{rel}:{node.lineno}:{node.func.attr}")
            else:
                guarded_hits[node.func.attr].append(node.lineno)

    assert offenders == []
    for name in ORDER_METHODS:
        assert guarded_hits[name], f"{name} is not called from the guarded module"

    for node in ast.walk(ast.parse(GUARDED.read_text(encoding="utf-8"), filename=str(GUARDED))):
        if not isinstance(node, ast.FunctionDef):
            continue
        asserts = [
            n.lineno
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "assert_live_orders_allowed"
        ]
        orders = [
            n.lineno
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in ORDER_METHODS
        ]
        if orders:
            assert asserts, f"{node.name} calls an order method without the guard"
            assert min(asserts) < min(orders), f"{node.name} must call the guard before the SDK"
            assert_lines[node.name] = asserts

    assert set(assert_lines) >= {"place_order", "modify_order", "cancel_order"}


@pytest.mark.asyncio
async def test_startup_log_states_mode_and_live_off(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()

    from engine.runner import EngineRunner

    runner = EngineRunner()

    class _Runner:
        async def setup(self) -> None:
            return None

    class _Site:
        async def start(self) -> None:
            return None

    monkeypatch.setattr(runner.scheduler, "start", lambda: None)
    monkeypatch.setattr(runner.scheduler, "add_job", lambda *_a, **_k: None)
    monkeypatch.setattr(web, "AppRunner", lambda _app: _Runner())
    monkeypatch.setattr(web, "TCPSite", lambda *_a, **_k: _Site())
    # runner.start imported web as a module attribute
    monkeypatch.setattr("engine.runner.web.AppRunner", lambda _app: _Runner())
    monkeypatch.setattr("engine.runner.web.TCPSite", lambda *_a, **_k: _Site())

    with caplog.at_level(logging.INFO, logger="engine.runner"):
        await runner.start()
    try:
        text = caplog.text
        assert "mode=paper" in text
        assert "live=OFF" in text
    finally:
        runner.db.close()
