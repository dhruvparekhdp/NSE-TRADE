"""APScheduler wiring + graceful shutdown (plan A12 / P0-7). Jobs are stubs in P0."""

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

from config.settings import get_settings
from data.calendar import CalendarMissing, job_should_run, load_default_calendar
from engine.state import init_db
from notify.telegram import TelegramClient
from web.app import create_app

log = logging.getLogger(__name__)
IST = "Asia/Kolkata"


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

    async def job_refresh_instruments(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: refresh instruments (08:30 IST)")

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

    async def job_square_off(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: square off MIS (15:05 IST)")

    async def job_stop_feed(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: stop websocket (15:35 IST)")

    async def job_eod(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("stub job: end-of-day summary (15:45 IST)")

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

    def _schedule(self) -> None:
        # Trading-day filter is applied inside jobs later; P0 only registers the clock times.
        jobs = [
            ("30 8 * * mon-fri", self.job_refresh_instruments, "refresh_instruments"),
            ("45 8 * * mon-fri", self.job_login, "login"),
            ("0 9 * * mon-fri", self.job_start_feed, "start_feed"),
            ("45 14 * * mon-fri", self.job_no_new_entries, "no_new_entries"),
            ("5 15 * * mon-fri", self.job_square_off, "square_off"),
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
            "nse-engine listening on http://%s:%s status=%s",
            self.settings.web_host,
            self.settings.web_port,
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
