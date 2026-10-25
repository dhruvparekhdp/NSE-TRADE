/* Command hub: Today · Market mood · Watchlist (PLAN_V2 §8; Watchlist restored as its own page, owner 24 Oct 2026). */
(function () {
  "use strict";
  var U = UI.U, C = UI.C, F = UI.F, e = U.esc;
  UI.Store.def("universe", "api/universe", 300000);

  function cls(x) { return U.num(x) ? (x >= 0 ? "up" : "dn") : ""; }
  function yes(b) { return b ? "yes" : "no"; }

  // ------------------------------------------------------------------ Today
  UI.widget("today-hero", {
    bare: true, uses: ["meta", "guard"],
    mount: function (el, ctx) { ctx.every(ctx.render, 1000); },
    render: function (el, D) {
      if (!D.meta) { el.innerHTML = C.state(D, "meta"); return; }
      var s = F.session(D), m = D.meta, left = U.num(s.next_change_ms) ? s.next_change_ms - Date.now() : null;
      el.innerHTML = '<div class="hero-band"><b>' + e(String(s.label || s.state || "—").toUpperCase()) + "</b><span>" +
        (s.next_label ? e(s.next_label) + (left != null && left > 0 ? " in " + U.dur(left) : "") + " · " : "") +
        "square-off " + e(m.squareoff_at || "—") + " · no new entries after " + e(m.no_entry_after || "—") +
        " · mode " + e(String(m.mode || "").toUpperCase()) + " · live orders " + (m.live_orders ? "ON" : "off") +
        " · kill switch " + (m.kill_switch ? "ON" : "off") + "</span></div>";
    }
  });
  UI.widget("today-market", {
    title: "MARKET", uses: ["market"],
    render: function (el, D, ctx) {
      var m = D.market; if (!m) { el.innerHTML = C.state(D, "market"); return; }
      var n = m.nifty || {};
      el.innerHTML = C.tiles([
        ["NIFTY 50", U.px(n.ltp), U.pct(n.chg_pct), cls(n.chg_pct)],
        ["INDIA VIX", U.num(m.india_vix) ? Number(m.india_vix).toFixed(2) : "—", ""],
        ["VOL RANK (1Y)", U.num(m.nifty_vol_rank) ? Number(m.nifty_vol_rank).toFixed(2) : "—", m.nifty_vol_rank > 0.667 ? "top third: risk-off" : ""],
        ["ABOVE 200 DMA", m.nifty_above_200dma == null ? "—" : yes(m.nifty_above_200dma), ""],
        ["FII / DII", (U.num(m.fii_net_cr) ? U.cr(m.fii_net_cr) : "—") + " / " + (U.num(m.dii_net_cr) ? U.cr(m.dii_net_cr) : "—"), "net cash, last session"],
        ["GIFT NIFTY", U.pct(m.gift_nifty_chg_pct), U.num(m.gift_nifty_chg_pct) ? "" : "no source yet", cls(m.gift_nifty_chg_pct)]
      ]) + ((m.next_events || []).length ? '<p class="small dim" style="margin-top:8px">Next: ' +
        m.next_events.slice(0, 4).map(function (x) { return e(x.date + " " + x.label); }).join(" · ") + "</p>" : "");
    }
  });
  UI.widget("today-wallet", {
    title: "PAPER WALLET", uses: ["paper"],
    render: function (el, D) {
      var p = D.paper; if (!p) { el.innerHTML = C.state(D, "paper"); return; }
      if (!p.cycle || p.cycle.id == null) { el.innerHTML = C.empty("No paper cycle yet. It starts with the first scan on a trading day (16:20 IST)."); return; }
      var s = p.summary || {};
      el.innerHTML = C.tiles([
        ["EQUITY", U.inr(p.equity), "start " + U.inr(p.cycle.starting_wallet), cls(p.equity - p.cycle.starting_wallet)],
        ["OPEN", String((p.positions || []).length), "unrealised " + U.inr(p.unrealised, true), cls(p.unrealised)],
        ["NET P&L", U.inr(s.net_pnl, true), (s.trades || 0) + " closed", cls(s.net_pnl)]
      ]);
    }
  });
  UI.widget("today-guard", {
    title: "GUARD", uses: ["guard"],
    render: function (el, D) {
      var g = D.guard; if (!g) { el.innerHTML = C.state(D, "guard"); return; }
      var rows = [["Kill switch", g.kill_switch ? "ON" : "off", g.kill_switch ? "dn" : ""],
        ["Daily loss", U.pct(g.daily_loss_pct), ""], ["Capital floor", g.floor_ok ? "ok" : "BREACHED", g.floor_ok ? "" : "dn"],
        ["Quotes age", g.feed ? U.secs(g.feed.quotes_age_s) : "—", g.feed && g.feed.stale ? "dn" : ""],
        ["Reconcile", (g.reconcile_faults || []).length ? (g.reconcile_faults.length + " fault(s)") : "clean", (g.reconcile_faults || []).length ? "dn" : ""]];
      (g.flags || []).forEach(function (f) { rows.push([f.text || f.id, f.on ? "ON" : "off", f.on ? "dn" : ""]); });
      el.innerHTML = rows.map(function (r) {
        return '<div class="trow" style="grid-template-columns:minmax(0,1fr) auto"><span>' + e(r[0]) + '</span><b class="' + r[2] + '">' + e(r[1]) + "</b></div>";
      }).join("");
    }
  });
  UI.widget("today-feed", {
    title: "LATEST SIGNALS", uses: ["signals"],
    render: function (el, D, ctx) {
      var s = D.signals; if (!s) { el.innerHTML = C.state(D, "signals"); return; }
      var rows = (s.rows || []).filter(function (r) { return r.role === "pick"; }).slice(0, 12);
      ctx.right((s.rows || []).length + " rows · 14 days");
      el.innerHTML = C.table([
        { label: "TIME", w: "110px", cell: function (r) { return e(U.stamp(r.ts_ms)); } },
        { label: "SYMBOL", w: "110px", cell: function (r) { return "<b>" + e(r.symbol) + "</b>"; } },
        { label: "STRATEGY", w: "120px", cell: function (r) { return e(U.name(r.strategy)); } },
        { label: "DECISION", w: "90px", cell: function (r) { return C.tag(r.decision, r.decision === "taken" ? "up" : r.decision === "skipped" ? "dn" : ""); } },
        { label: "WHY", cell: function (r) { return '<span class="dim">' + e(r.reason_text || r.skip_reason || "") + "</span>"; } }
      ], rows, { empty: "No signals yet. The first scan runs at 16:20 IST on a trading day.", minWidth: 560 });
    }
  });
  UI.widget("today-jobs", {
    title: "TODAY'S JOBS", uses: ["health"],
    render: function (el, D, ctx) {
      var h = D.health; if (!h) { el.innerHTML = C.state(D, "health"); return; }
      var jobs = (h.jobs || []).slice().sort(function (a, b) { return (a.next_run_ms || 9e15) - (b.next_run_ms || 9e15); });
      ctx.right(jobs.length + " jobs · Angel " + (h.login_ok ? "logged in" : "not logged in"));
      el.innerHTML = C.table([
        { label: "JOB", cell: function (j) { return "<b>" + e(U.name(j.id)) + "</b>"; } },
        { label: "LAST RUN", w: "120px", cell: function (j) { return e(U.stamp(j.last_run_ms)); } },
        { label: "RESULT", cell: function (j) { return '<span class="' + (j.last_ok === false ? "dn" : "dim") + '">' + e(j.result || (j.last_run_ms ? "ok" : "not run yet")) + "</span>"; } },
        { label: "NEXT", w: "120px", cell: function (j) { return e(U.stamp(j.next_run_ms)); } }
      ], jobs, { empty: "No jobs reported.", minWidth: 560, limit: 40 });
    }
  });
  UI.view("command/today", [["today-hero"], [{ w: "today-market", size: "grow" }, { w: "today-wallet", size: "side" }],
    [{ w: "today-feed", size: "grow" }, { w: "today-guard", size: "side" }], ["today-jobs"]]);

  // ------------------------------------------------------------------ Market mood
  function cueRows(list) {
    return (list || []).map(function (r) {
      return [r.label || r.key, U.pct(r.chg_pct), r.stale ? "stale" : (r.ts_ms ? U.ago(r.ts_ms) : ""), r.stale ? "" : cls(r.chg_pct)];
    });
  }
  UI.widget("mood-brief", {
    title: "MORNING BRIEF · FROZEN 08:45", uses: ["opening"],
    render: function (el, D, ctx) {
      var o = D.opening; if (!o) { el.innerHTML = C.state(D, "opening"); return; }
      var b = o.brief;
      if (!b || !b.built_ms) { el.innerHTML = C.empty("No brief for " + (o.trade_date || "today") + " yet. It is built at 08:45 IST on trading days."); return; }
      ctx.right("built " + U.stamp(b.built_ms));
      var cues = cueRows(b.us).concat(cueRows(b.europe), cueRows(b.asia), cueRows(b.fx_commod));
      el.innerHTML = C.tiles([
        ["GIFT NIFTY", U.pct(b.gift_nifty && b.gift_nifty.chg_pct), b.gift_nifty && b.gift_nifty.chg_pct != null ? "" : "proxy: US futures + Asia"],
        ["FII / DII", (U.num(b.fii_net_cr) ? U.cr(b.fii_net_cr) : "—") + " / " + (U.num(b.dii_net_cr) ? U.cr(b.dii_net_cr) : "—"), "previous session"],
        ["INDIA VIX", U.num(b.india_vix) ? Number(b.india_vix).toFixed(2) : "—", ""],
        ["MOOD", U.num(b.composite) ? Number(b.composite).toFixed(2) : "—", "−1 risk-off … +1 risk-on", cls(b.composite)]
      ]) + (cues.length ? C.tiles(cues) : C.empty("Global cues unavailable (no working source from the server yet)."));
    }
  });
  UI.widget("mood-preopen", {
    title: "PRE-OPEN 09:00–09:15", uses: ["opening"],
    render: function (el, D, ctx) {
      var o = D.opening; if (!o) { el.innerHTML = C.state(D, "opening"); return; }
      var p = o.preopen || {}, n = p.nifty;
      ctx.right((p.snapshots_n || 0) + " snapshots");
      if (!n) { el.innerHTML = C.empty("No pre-open data for " + (o.trade_date || "today") + ". Recorded every 30 s from 09:00 on trading days."); return; }
      el.innerHTML = C.tiles([["NIFTY IEP", U.px(n.iep), U.pct(n.chg_pct), cls(n.chg_pct)],
        ["IMBALANCE", U.num(n.imbalance) ? Number(n.imbalance).toFixed(2) : "—", "−1 sell-heavy … +1 buy-heavy", cls(n.imbalance)]]) +
        C.table([{ label: "SYMBOL", cell: function (r) { return "<b>" + e(r.symbol) + "</b>"; } },
          { label: "IEP CHG", w: "90px", cell: function (r) { return C.signed(r.chg_pct); } },
          { label: "IMBALANCE", w: "90px", cell: function (r) { return U.num(r.imbalance) ? Number(r.imbalance).toFixed(2) : "—"; } }],
          p.movers || [], { empty: "No movers.", minWidth: 300 });
    }
  });
  UI.widget("mood-scorecard", {
    title: "OPENING SCORECARD", uses: ["opening"],
    render: function (el, D) {
      var o = D.opening; if (!o) { el.innerHTML = C.state(D, "opening"); return; }
      var s = o.scorecard;
      if (!s) { el.innerHTML = C.empty("Filled from 09:15 on trading days; the opening type is labelled at 15:45."); return; }
      var br = s.breadth || {};
      el.innerHTML = C.tiles([["NIFTY GAP", U.pct(s.nifty_gap_pct), "", cls(s.nifty_gap_pct)],
        ["GAP FILLED", s.gap_filled_ms ? "at " + U.hm(s.gap_filled_ms) : "no", ""],
        ["OR 15 MIN", s.or15 && s.or15.length === 2 ? U.px(s.or15[0]) + " – " + U.px(s.or15[1]) : "—", ""],
        ["BREADTH", U.num(br.adv) ? br.adv + " / " + br.dec : "—", "advancers / decliners"],
        ["FIRST 5 MIN VOL", U.num(s.first5_vol_x) ? Number(s.first5_vol_x).toFixed(1) + "×" : "—", "vs 20-day avg"],
        ["OPEN TYPE", s.open_type || "—", "labelled 15:45"]]);
    }
  });
  UI.widget("mood-sentiment", {
    title: "SENTIMENT", uses: ["sentiment"],
    render: function (el, D) {
      var s = D.sentiment; if (!s) { el.innerHTML = C.state(D, "sentiment"); return; }
      var alarm = s.risk_off_alarm && s.risk_off_alarm.on ? C.flag("high", "RISK-OFF ALARM", "information only, no trades changed", (s.risk_off_alarm.reasons || []).join(" · ")) : "";
      el.innerHTML = alarm + C.tiles([["COMPOSITE", U.num(s.composite) ? Number(s.composite).toFixed(2) : "—", s.label || "", cls(s.composite)]]) +
        C.table([{ label: "PART", cell: function (p) { return e(p.label || p.key); } },
          { label: "VALUE", w: "90px", cell: function (p) { return U.num(p.value) ? e(Number(p.value).toFixed(2)) : "no data"; } },
          { label: "WEIGHT", w: "70px", cell: function (p) { return e(p.weight); } },
          { label: "→", w: "70px", cell: function (p) { return U.num(p.contribution) ? C.signed(p.contribution, function (x) { return (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2); }) : "—"; } }],
          s.parts || [], { empty: "No sentiment computed yet (after the 08:45 brief).", minWidth: 320 });
    }
  });
  UI.widget("mood-markets", {
    title: "MARKETS", uses: ["sentiment"],
    render: function (el, D) {
      var s = D.sentiment; if (!s) { el.innerHTML = C.state(D, "sentiment"); return; }
      el.innerHTML = C.table([{ label: "REGION", w: "80px", cell: function (r) { return e(r.region || ""); } },
        { label: "INSTRUMENT", cell: function (r) { return "<b>" + e(r.label || r.key) + "</b>"; } },
        { label: "LAST", w: "100px", cell: function (r) { return U.px(r.last); } },
        { label: "CHG", w: "80px", cell: function (r) { return r.stale ? '<span class="dim">' + e(U.pct(r.chg_pct)) + "</span>" : C.signed(r.chg_pct); } },
        { label: "AS OF", w: "90px", cell: function (r) { return r.stale ? "stale " + e(U.ago(r.ts_ms)) : e(U.ago(r.ts_ms)); } }],
        s.markets || [], { empty: "No global market data yet (Yahoo blocks the server; a new source is being added).", minWidth: 460 });
    }
  });
  UI.widget("mood-headlines", {
    title: "HEADLINES · 24 H", uses: ["headlines"],
    mount: function (el, ctx) { ctx.s.tag = ""; },
    on: { tag: function (el, ev, t, ctx) { ctx.s.tag = t.dataset.v === ctx.s.tag ? "" : t.dataset.v; ctx.render(); } },
    render: function (el, D, ctx) {
      var h = D.headlines; if (!h) { el.innerHTML = C.state(D, "headlines"); return; }
      var rows = (h.rows || []).filter(function (r) { return !ctx.s.tag || r.event_type === ctx.s.tag; });
      ctx.right((h.rows || []).length + " headlines");
      el.innerHTML = '<div class="chipset">' + (h.tags || []).map(function (t) {
        return '<button class="chipbtn' + (ctx.s.tag === t.event_type ? " on" : "") + '" data-act="tag" data-v="' + e(t.event_type) + '">' + e(t.event_type + " · " + t.n) + "</button>";
      }).join("") + "</div>" + C.table([
        { label: "TIME", w: "100px", cell: function (r) { return e(U.stamp(r.ts_ms)); } },
        { label: "TAG", w: "120px", cell: function (r) { return C.tag(r.event_type || "other"); } },
        { label: "HEADLINE", cell: function (r) { return r.link ? '<a href="' + e(r.link) + '" target="_blank" rel="noopener">' + e(r.title) + "</a>" : e(r.title); } },
        { label: "SCORE", w: "70px", cell: function (r) { return U.num(r.score) ? C.signed(r.score, function (x) { return (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2); }) : "—"; } },
        { label: "NIFTY +60M", w: "90px", cell: function (r) { return U.num(r.nifty_move_next_60m) ? C.signed(r.nifty_move_next_60m) : "—"; } }],
        rows, { empty: "No headlines in the last 24 hours. Fetched every 15 min from 08:00 on trading days.", minWidth: 640 });
    }
  });
  UI.widget("mood-history", {
    title: "OPENING HISTORY · 60 DAYS", uses: ["opening"],
    render: function (el, D) {
      var o = D.opening; if (!o) { el.innerHTML = C.state(D, "opening"); return; }
      el.innerHTML = C.table([{ label: "DAY", cell: function (r) { return e(r.trade_date); } },
        { label: "GAP", w: "80px", cell: function (r) { return C.signed(r.nifty_gap_pct); } },
        { label: "IMB", w: "70px", cell: function (r) { return U.num(r.imbalance) ? Number(r.imbalance).toFixed(2) : "—"; } },
        { label: "TYPE", cell: function (r) { return e(r.open_type || "—"); } },
        { label: "O→C", w: "80px", cell: function (r) { return C.signed(r.open_to_close_pct); } }],
        o.history || [], { empty: "Builds up from the first recorded trading day.", minWidth: 380 });
    }
  });
  UI.view("command/mood", [["mood-brief"], [{ w: "mood-preopen", size: "half" }, { w: "mood-scorecard", size: "half" }],
    [{ w: "mood-markets", size: "grow" }, { w: "mood-sentiment", size: "side" }], ["mood-headlines"], ["mood-history"]]);

  // ------------------------------------------------------------------ Watchlist
  UI.widget("watchlist", {
    title: "WATCHLIST · NIFTY 100", uses: ["universe", "quotes", "signals"],
    mount: function (el, ctx) { ctx.s.q = ""; ctx.s.t = { sort: null }; },
    on: {
      q: function (el, ev, t, ctx) { ctx.s.q = t.value.toUpperCase(); ctx.render(); },
      sort: function (el, ev, t, ctx) { C.sortState(ctx.s.t, +t.dataset.k); ctx.render(); }
    },
    render: function (el, D, ctx) {
      if (!D.universe && !D.quotes) { el.innerHTML = C.state(D, "universe"); return; }
      var quotes = {}; ((D.quotes && D.quotes.quotes) || []).forEach(function (q) { quotes[q.symbol] = q; });
      var last = {}; ((D.signals && D.signals.rows) || []).forEach(function (r) { if (r.role === "pick" && (!last[r.symbol] || r.ts_ms > last[r.symbol].ts_ms)) last[r.symbol] = r; });
      var syms = ((D.universe && D.universe.rows) || []).map(function (r) { return r; });
      if (!syms.length) syms = Object.keys(quotes).map(function (s) { return { symbol: s, excluded: false }; });
      var rows = syms.filter(function (r) { return !ctx.s.q || r.symbol.indexOf(ctx.s.q) >= 0; }).map(function (r) {
        var q = quotes[r.symbol] || {}; return { symbol: r.symbol, excluded: r.excluded, ltp: q.ltp, chg: q.chg_pct, sig: last[r.symbol] };
      });
      var qa = D.quotes && D.quotes.ts_ms ? U.ago(D.quotes.ts_ms) : "no quotes";
      ctx.right(syms.length + " symbols · quotes " + qa + (D.quotes && D.quotes.source ? " (" + D.quotes.source + ")" : ""));
      var search = '<input class="search" data-act="q" placeholder="search symbol…" value="' + e(ctx.s.q) + '" style="margin-bottom:8px">';
      el.innerHTML = search + C.table([
        { label: "SYMBOL", w: "130px", cell: function (r) { return "<b>" + e(r.symbol) + "</b>" + (r.excluded ? ' <span class="dim tiny">excluded</span>' : ""); }, sort: function (r) { return r.symbol; } },
        { label: "LTP", w: "100px", cell: function (r) { return U.px(r.ltp); }, sort: function (r) { return r.ltp || 0; } },
        { label: "CHG", w: "90px", cell: function (r) { return U.num(r.chg) ? C.signed(r.chg) : "—"; }, sort: function (r) { return U.num(r.chg) ? r.chg : -999; } },
        { label: "LAST SIGNAL", w: "200px", cell: function (r) { return r.sig ? e(U.day(r.sig.ts_ms) + " " + U.name(r.sig.strategy)) : '<span class="dim">—</span>'; }, sort: function (r) { return r.sig ? r.sig.ts_ms : 0; } },
        { label: "DECISION / WHY", cell: function (r) { return r.sig ? C.tag(r.sig.decision) + ' <span class="dim">' + e(r.sig.reason_text || "") + "</span>" : ""; } }
      ], rows, { state: ctx.s.t, empty: "No symbols match.", minWidth: 700, limit: 120 });
    }
  });
  UI.view("command/watchlist", [["watchlist"]]);
})();
