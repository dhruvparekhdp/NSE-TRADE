"""APScheduler wiring + graceful shutdown (plan A12 / P0-7; review R1 job wiring)."""

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
from core.session_times import derive_engine_times
from data.calendar import CalendarMissing, job_should_run, load_default_calendar
from engine.state import init_db
from notify.telegram import TelegramClient
from web.app import create_app

log = logging.getLogger(__name__)
IST = "Asia/Kolkata"
IST_Z = ZoneInfo(IST)


class EngineRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.data_dir = Path(self.settings.data_dir)
        self.db = init_db(self.data_dir / "engine.db")
        self.scheduler = AsyncIOScheduler(timezone=IST)
        self.telegram = TelegramClient()
        self.app = create_app(db=self.db)
        self.app["scheduler"] = self.scheduler  # System > Health lists the jobs
        self.app["engine"] = self
        self._runner: web.AppRunner | None = None
        self._stopping = asyncio.Event()
        self._nse_get_json = None  # tests inject a fake

    def _trading_day_ok(self, *, allow_special_entries: bool = True) -> bool:
        """Skip holiday / weekend / missing-year jobs (PLAN_V2 V1-2)."""
        if not job_should_run():
            log.info("skip job: not a trading day (or calendar missing)")
            return False
        if not allow_special_entries and not self.settings.trade_special_sessions:
            today = datetime.now(IST_Z).date()
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
        log.info("job: refresh instruments (08:30 IST)")

    async def job_login(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("job: login (08:45 IST)")

    async def job_morning_brief(self) -> None:
        if not self._trading_day_ok():
            return
        from engine.jobs import job_morning_brief

        try:
            brief = await asyncio.to_thread(job_morning_brief, self.db)
            log.info("job: morning_brief trade_date=%s", brief.get("trade_date"))
        except Exception as exc:  # noqa: BLE001
            log.warning("morning_brief failed: %s", exc)

    async def job_cues(self) -> None:
        if not self._trading_day_ok():
            return
        from engine.jobs import job_cues

        try:
            n = await asyncio.to_thread(job_cues, self.db)
            log.info("job: cues n=%s", n)
        except Exception as exc:  # noqa: BLE001
            log.warning("cues failed: %s", exc)

    async def job_preopen(self) -> None:
        if not self._trading_day_ok():
            return
        now = datetime.now(IST_Z)
        if now.hour != 9 or now.minute > 14:
            return
        final = now.minute == 14
        from engine.jobs import job_preopen

        try:
            n = await asyncio.to_thread(
                job_preopen, self.db, get_json=self._nse_get_json, final=final
            )
            log.info("job: preopen n=%s final=%s", n, final)
        except Exception as exc:  # noqa: BLE001
            log.warning("preopen failed: %s", exc)

    async def job_opening_scorecard(self) -> None:
        if not self._trading_day_ok():
            return
        # Marks come from quotes cache when available; otherwise skip quietly.
        log.info("job: opening scorecard tick")

    async def job_open_type(self) -> None:
        if not self._trading_day_ok():
            return
        from engine.jobs import job_opening_scorecard

        today = datetime.now(IST_Z).date().isoformat()
        row = self.db.execute(
            "SELECT open, prev_close, close FROM opening_summary WHERE trade_date=? AND symbol='NIFTY'",
            (today,),
        ).fetchone()
        if not row or row["open"] is None or row["prev_close"] is None:
            log.info("job: open_type skip (no opening_summary yet)")
            return
        try:
            await asyncio.to_thread(
                job_opening_scorecard,
                self.db,
                trade_date=today,
                open_px=float(row["open"]),
                prev_close=float(row["prev_close"]),
                last_px=float(row["close"] or row["open"]),
                finalize_type=True,
            )
            log.info("job: open_type finalized")
        except Exception as exc:  # noqa: BLE001
            log.warning("open_type failed: %s", exc)

    async def job_start_feed(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("job: start websocket / Book A shadow feed (09:00 IST)")

    async def job_pending(self) -> None:
        if not self._trading_day_ok(allow_special_entries=False):
            return
        from engine.paper_jobs import job_pending

        today = datetime.now(IST_Z).date()
        n = await asyncio.to_thread(job_pending, self.db, trade_date=today)
        log.info("job: pending_orders ready n=%s", n)

    async def job_book_a_shadow(self) -> None:
        if not self._trading_day_ok(allow_special_entries=False):
            return
        if getattr(self.settings, "book_a_mode", "shadow") != "shadow":
            return
        log.info("job: Book A shadow scan (live bars when WS wired)")

    async def job_no_new_entries(self) -> None:
        if not self._trading_day_ok(allow_special_entries=False):
            return
        log.info("job: no new Book A entries")

    async def job_square_off(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("job: square off MIS")

    async def job_stop_feed(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("job: stop websocket")

    async def job_daily_bars(self) -> None:
        if not self._trading_day_ok():
            return
        from config.paths import lake_dir
        from data.angel_daily import job_daily_bars, universe_symbol_tokens
        from data.lake import Lake

        today = datetime.now(IST_Z).date()
        lake = Lake(self.data_dir / "lake" if (self.data_dir / "lake").exists() else lake_dir())
        tokens = universe_symbol_tokens(self.db)
        if not tokens:
            log.info("job: daily_bars skip (no instrument tokens)")
            return
        api = getattr(self, "_daily_candle_api", None)
        if api is None:
            log.info("job: daily_bars skip (no Angel session injected)")
            return
        try:
            stats = await asyncio.to_thread(
                job_daily_bars,
                lake,
                self.db,
                symbols=tokens,
                trade_date=today,
                api=api,
            )
            log.info("job: daily_bars %s", stats)
        except Exception as exc:  # noqa: BLE001
            log.warning("daily_bars failed: %s", exc)

    async def job_eod_fill(self) -> None:
        if not self._trading_day_ok():
            return
        from config.paths import lake_dir
        from data.lake import Lake
        from engine.paper_jobs import job_eod_fill

        today = datetime.now(IST_Z).date()
        lake = Lake(self.data_dir / "lake" if (self.data_dir / "lake").exists() else lake_dir())
        try:
            results = await asyncio.to_thread(job_eod_fill, self.db, lake, trade_date=today)
            log.info("job: eod_fill n=%s", len(results))
        except Exception as exc:  # noqa: BLE001
            log.warning("eod_fill failed: %s", exc)

    async def job_scan(self) -> None:
        if not self._trading_day_ok(allow_special_entries=False):
            return
        from config.paths import lake_dir
        from data.lake import Lake
        from engine.paper_jobs import job_scan

        today = datetime.now(IST_Z).date()
        lake = Lake(self.data_dir / "lake" if (self.data_dir / "lake").exists() else lake_dir())
        enabled = list(self.settings.strategies_enabled or [])
        try:
            rows = await asyncio.to_thread(
                job_scan,
                self.db,
                lake,
                trade_date=today,
                enabled=enabled,
                write=True,
            )
            log.info("job: Book B scan signals=%s enabled=%s", len(rows), enabled or "shadow-all")
        except Exception as exc:  # noqa: BLE001
            log.warning("scan failed: %s", exc)

    async def job_outcomes(self) -> None:
        if not self._trading_day_ok():
            return
        from config.paths import lake_dir
        from data.lake import Lake
        from engine.paper_jobs import job_outcomes

        today = datetime.now(IST_Z).date()
        lake = Lake(self.data_dir / "lake" if (self.data_dir / "lake").exists() else lake_dir())
        try:
            n = await asyncio.to_thread(job_outcomes, self.db, lake, trade_date=today)
            log.info("job: outcomes resolved n=%s", n)
        except Exception as exc:  # noqa: BLE001
            log.warning("outcomes failed: %s", exc)

    async def job_eod_report(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("job: eod report / Telegram summary")

    async def job_flows(self) -> None:
        if not self._trading_day_ok():
            return
        from engine.jobs import job_flows

        try:
            ok = await asyncio.to_thread(job_flows, self.db, self._nse_get_json)
            log.info("job: flows ok=%s", ok)
        except Exception as exc:  # noqa: BLE001
            log.warning("flows failed: %s", exc)

    async def job_bhav_check(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("job: bhav parity check")

    async def job_backfill(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("job: history backfill")

    async def job_backup(self) -> None:
        log.info("job: backups")

    async def job_news(self) -> None:
        """Headlines every 15 min (PLAN_V2 V1b)."""
        if not self._trading_day_ok():
            return
        log.info("news job: start")
        try:
            from news.pipeline import refresh_and_score
            from news.scrape import Headline

            headlines: list[Headline] = []
            summary = refresh_and_score(headlines)
            log.info(
                "news job: done india=%s macro=%s score=%.3f",
                summary.get("n_india"),
                summary.get("n_macro_shared"),
                float(summary.get("score") or 0),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("news job failed: %s", exc)

    async def job_free_quotes(self) -> None:
        if not self._trading_day_ok():
            return
        log.info("free quotes job: start")
        try:
            from data.free_quotes import refresh_default_universe

            payload = await asyncio.to_thread(refresh_default_universe, self.data_dir, n=20)
            log.info("free quotes job: n=%s", len(payload.get("quotes") or []))
        except Exception as exc:  # noqa: BLE001
            log.warning("free quotes job failed: %s", exc)

    def _hhmm_cron(self, hhmm: str) -> str:
        h, m = hhmm.split(":")
        return f"{int(m)} {int(h)} * * mon-fri"

    def _schedule(self) -> None:
        # R9: square-off / no-entry from core.session_times (defaults 14:55 / 14:35).
        sq_at, no_entry = derive_engine_times(self.settings.broker_squareoff_at)
        sq_at = getattr(self.settings, "square_off_at", None) or sq_at
        no_entry = getattr(self.settings, "no_entry_after", None) or no_entry
        jobs: list[tuple[str, object, str]] = [
            ("30 8 * * mon-fri", self.job_refresh_instruments, "refresh_instruments"),
            ("45 8 * * mon-fri", self.job_login, "login"),
            ("45 8 * * mon-fri", self.job_morning_brief, "morning_brief"),
            ("0 9 * * mon-fri", self.job_start_feed, "start_feed"),
            ("0 9 * * mon-fri", self.job_pending, "pending"),
            (self._hhmm_cron(no_entry), self.job_no_new_entries, "no_new_entries"),
            (self._hhmm_cron(sq_at), self.job_square_off, "square_off"),
            ("35 15 * * mon-fri", self.job_stop_feed, "stop_feed"),
            ("45 15 * * mon-fri", self.job_open_type, "open_type"),
            ("10 16 * * mon-fri", self.job_daily_bars, "daily_bars"),
            ("15 16 * * mon-fri", self.job_eod_fill, "eod_fill"),
            ("20 16 * * mon-fri", self.job_scan, "scan"),
            ("30 16 * * mon-fri", self.job_outcomes, "outcomes"),
            ("35 16 * * mon-fri", self.job_eod_report, "eod_report"),
            ("0 18 * * mon-fri", self.job_backfill, "backfill"),
            ("*/15 18-19 * * mon-fri", self.job_flows, "flows"),
            ("30 18 * * mon-fri", self.job_bhav_check, "bhav_check"),
            ("30 18 * * *", self.job_backup, "backup"),
            ("*/15 8-16 * * mon-fri", self.job_news, "news"),
            ("*/5 8-16 * * mon-fri", self.job_cues, "cues"),
            ("*/5 9-15 * * mon-fri", self.job_free_quotes, "free_quotes"),
            ("*/5 9-15 * * mon-fri", self.job_book_a_shadow, "book_a_shadow"),
            ("*/5 9-14 * * mon-fri", self.job_opening_scorecard, "opening_scorecard"),
            ("*/1 9 * * mon-fri", self.job_preopen, "preopen"),
        ]
        for cron, fn, name in jobs:
            self.scheduler.add_job(
                fn,
                CronTrigger.from_crontab(cron, timezone=IST),
                id=name,
                replace_existing=True,
            )

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
                pass
        await self.start()
        await self._stopping.wait()


def main() -> None:
    runner = EngineRunner()
    asyncio.run(runner.run_forever())


if __name__ == "__main__":
    main()
