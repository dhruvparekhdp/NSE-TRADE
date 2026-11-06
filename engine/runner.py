"""APScheduler wiring + graceful shutdown (plan A12 / P0-7).

Market refresh, signal generation, MIS square-off, and the end-of-day snapshot
run in paper/shadow and never call broker order methods. Login, the feed, and
backup are still stubs.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from broker.live_guard import startup_banner
from config.settings import get_settings
from data.calendar import CalendarMissing, job_should_run, load_default_calendar
from engine.state import init_db
from notify.telegram import TelegramClient
from web.app import create_app

log = logging.getLogger(__name__)
IST = "Asia/Kolkata"


def _clock_ms(now_ms: int | None) -> int:
    if now_ms is not None:
        return int(now_ms)
    return int(datetime.now(ZoneInfo(IST)).timestamp() * 1000)


class EngineRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.data_dir = Path(self.settings.data_dir)
        self.db = init_db(self.data_dir / "engine.db")
        self.scheduler = AsyncIOScheduler(timezone=IST)
        self.telegram = TelegramClient()
        self.app = create_app(db=self.db)
        self.app["scheduler"] = self.scheduler  # System > Health lists the jobs
        self._runner: web.AppRunner | None = None
        self._stopping = asyncio.Event()

    def _trading_day_ok(self, *, allow_special_entries: bool = True) -> bool:
        """Skip holiday / weekend / missing-year jobs (PLAN_V2 V1-2)."""
        if not job_should_run():
            log.info("skip job: not a trading day (or calendar missing)")
            return False
        if not allow_special_entries and not self.settings.trade_special_sessions:
            today = datetime.now(ZoneInfo(IST)).date()
            try:
                cal = load_default_calendar()
                if cal.special_session(today) is not None:
                    log.info("skip new-entry job: special session (Muhurat)")
                    return False
            except CalendarMissing:
                return False
        return True

    async def job_refresh_instruments(self, *, now_ms: int | None = None) -> dict | None:
        """Persist the local quote cache. Does not download the scrip master or Yahoo."""
        from data.free_quotes import read_quotes_cache
        from engine.scheduled_jobs import refresh_market_data

        ms = _clock_ms(now_ms)
        try:
            cache = read_quotes_cache(self.data_dir)
            result = await asyncio.to_thread(
                refresh_market_data,
                self.db,
                now_ms=ms,
                quotes=list(cache.get("quotes") or []),
            )
            log.info("job: market data refresh %s", result.get("status"))
            return result
        except Exception as exc:  # noqa: BLE001 — a quote job must not stop the scheduler
            log.warning("market data refresh failed: %s", exc)
            return None

    async def job_login(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: login (08:45 IST)")

    async def job_start_feed(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: start websocket (09:00 IST)")

    async def job_no_new_entries(self) -> None:
        if not self._trading_day_ok(allow_special_entries=False):
            return
        log.info("stub job: no new Book A entries (14:45 IST)")

    async def job_generate_signals(self, *, now_ms: int | None = None) -> dict | None:
        """Scan strategies into the local book. Shadow writes signals; paper writes virtual shares."""
        from engine.scheduled_jobs import generate_signals

        ms = _clock_ms(now_ms)
        try:
            result = await asyncio.to_thread(
                generate_signals,
                self.db,
                now_ms=ms,
                book_a_mode=self.settings.book_a_mode,
                enabled=list(self.settings.strategies_enabled or []),
                allow_special=bool(self.settings.trade_special_sessions),
                no_entry_after=self.settings.no_entry_after,
                square_off_at=self.settings.square_off_at,
            )
            log.info("job: signals %s", result.get("status"))
            return result
        except Exception as exc:  # noqa: BLE001
            log.warning("signal generation failed: %s", exc)
            return None

    async def job_square_off(self, *, now_ms: int | None = None) -> dict | None:
        """Square off paper MIS at settings.square_off_at, which must be before 15:30 IST."""
        from engine.scheduled_jobs import square_off_mis

        ms = _clock_ms(now_ms)
        try:
            result = await asyncio.to_thread(
                square_off_mis,
                self.db,
                now_ms=ms,
                square_off_at=self.settings.square_off_at,
            )
            log.info("job: square off %s", result.get("status"))
            return result
        except Exception as exc:  # noqa: BLE001
            log.warning("square off failed: %s", exc)
            return None

    async def job_stop_feed(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: stop websocket (15:35 IST)")

    async def job_eod(self, *, now_ms: int | None = None) -> dict | None:
        """Write the paper performance snapshot after the cash close."""
        from engine.scheduled_jobs import snapshot_performance

        ms = _clock_ms(now_ms)
        try:
            result = await asyncio.to_thread(
                snapshot_performance,
                self.db,
                now_ms=ms,
                start_inr=float(self.settings.capital_inr),
            )
            log.info("job: eod snapshot %s", result.get("status"))
            return result
        except Exception as exc:  # noqa: BLE001
            log.warning("eod snapshot failed: %s", exc)
            return None

    async def job_backfill(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: history backfill (18:00 IST)")

    async def job_backup(self) -> None:
        log.info("stub job: backups (18:30 IST)")

    async def job_news(self) -> None:
        """Pull India RSS when network allowed; score via HF Space / rules (SHARED_INFRA)."""
        if not self._trading_day_ok():
            return
        log.info("news job: start")
        try:
            from news.pipeline import refresh_and_score
            from news.scrape import Headline

            # Live fetch is optional — empty batch still merges shared crypto headlines.
            headlines: list[Headline] = []
            summary = refresh_and_score(headlines)
            log.info(
                "news job: done india=%s macro=%s score=%.3f",
                summary.get("n_india"),
                summary.get("n_macro_shared"),
                float(summary.get("score") or 0),
            )
        except Exception as exc:  # noqa: BLE001 — never kill the engine for news
            log.warning("news job failed: %s", exc)

    async def job_free_quotes(self) -> None:
        """Poll yfinance (free, delayed). Angel WS stays off until live orders."""
        if not self._trading_day_ok():
            return
        log.info("free quotes job: start")
        try:
            from data.free_quotes import refresh_default_universe

            payload = await asyncio.to_thread(refresh_default_universe, self.data_dir, n=20)
            log.info("free quotes job: n=%s", len(payload.get("quotes") or []))
        except Exception as exc:  # noqa: BLE001
            log.warning("free quotes job failed: %s", exc)

    def _square_off_cron(self) -> str:
        """settings.square_off_at, or 14:55 if that clock is not before 15:30 IST."""
        from engine.scheduled_jobs import cron_at

        try:
            return cron_at(self.settings.square_off_at)
        except ValueError:
            log.warning("square_off_at %s is not before 15:30 IST; using 14:55", self.settings.square_off_at)
            return cron_at("14:55")

    def _schedule(self) -> None:
        # Holiday and session checks live inside the jobs (IST calendar, not the host clock).
        jobs = [
            ("30 8 * * mon-fri", self.job_refresh_instruments, "refresh_instruments"),
            ("45 8 * * mon-fri", self.job_login, "login"),
            ("0 9 * * mon-fri", self.job_start_feed, "start_feed"),
            ("*/15 9-15 * * mon-fri", self.job_generate_signals, "generate_signals"),
            ("45 14 * * mon-fri", self.job_no_new_entries, "no_new_entries"),
            (self._square_off_cron(), self.job_square_off, "square_off"),
            ("35 15 * * mon-fri", self.job_stop_feed, "stop_feed"),
            ("45 15 * * mon-fri", self.job_eod, "eod"),
            ("0 18 * * mon-fri", self.job_backfill, "backfill"),
            ("30 18 * * *", self.job_backup, "backup"),
            ("*/15 8-16 * * mon-fri", self.job_news, "news"),
            # Free quote poll every 5 min during market window (no Angel)
            ("*/5 9-15 * * mon-fri", self.job_free_quotes, "free_quotes"),
        ]
        for cron, fn, name in jobs:
            minute, hour, *_rest = cron.split()
            # Use CronTrigger from full expression for clarity
            self.scheduler.add_job(fn, CronTrigger.from_crontab(cron, timezone=IST), id=name, replace_existing=True)

    async def start(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        try:
            from config.secrets_loader import apply_db_secrets

            apply_db_secrets()
            self.settings = get_settings()
        except Exception as exc:  # noqa: BLE001
            log.warning("db secrets load failed: %s", exc)
        self._schedule()
        self.scheduler.start()
        # Warm free quotes once at boot (don't wait for cron)
        self.scheduler.add_job(self.job_free_quotes, id="free_quotes_boot", replace_existing=True)
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.settings.web_host, self.settings.web_port)
        await site.start()
        log.info(
            "%s status=%s",
            startup_banner(self.settings),
            "ok" if self.settings.angel_configured else "not configured",
        )

    async def stop(self) -> None:
        log.info("shutting down")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.telegram.aclose()
        if self._runner is not None:
            await self._runner.cleanup()
        self.db.close()
        self._stopping.set()

    async def run_forever(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows / restricted loops
                pass
        await self.start()
        await self._stopping.wait()


def main() -> None:
    runner = EngineRunner()
    asyncio.run(runner.run_forever())


if __name__ == "__main__":
    main()
