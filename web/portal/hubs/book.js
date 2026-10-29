/* Book hub: Paper book · Signals (PLAN_V2 §8). */
(function () {
  "use strict";
  var U = UI.U, C = UI.C, e = U.esc;
  function cls(x) { return U.num(x) ? (x >= 0 ? "up" : "dn") : ""; }

  // ------------------------------------------------------------------ Paper book
  UI.widget("paper-tiles", {
    bare: true, uses: ["paper"],
    render: function (el, D) {
      var p = D.paper; if (!p) { el.innerHTML = C.state(D, "paper"); return; }
      if (!p.cycle || p.cycle.id == null) {
        el.innerHTML = '<div class="hero-band"><b>NO PAPER CYCLE YET</b><span>The cycle starts with the first 16:20 IST scan on a trading day. ' +
          "Until a strategy is enabled in Settings, every signal is logged in shadow and its outcome tracked.</span></div>";
        return;
      }
      var c = p.cycle, s = p.summary || {}, k = s.costs || {};
      var costTotal = U.sum(Object.keys(k).map(function (x) { return k[x]; }));
      el.innerHTML = C.tiles([
        ["EQUITY", U.inr(p.equity), "start " + U.inr(c.starting_wallet) + " · peak " + U.inr(c.peak_wallet), cls(p.equity - c.starting_wallet)],
        ["CASH", U.inr(c.wallet), "free for new buys"],
        ["UNREALISED", U.inr(p.unrealised, true), (p.positions || []).length + " open", cls(p.unrealised)],
        ["NET P&L", U.inr(s.net_pnl, true), "after all costs", cls(s.net_pnl)],
        ["HIT RATE", s.trades ? Math.round(s.win_rate_pct) + "%" : "—", (s.trades || 0) + " closed · exp " + U.inr(s.expectancy_per_trade, true)],
        ["COSTS", U.inr(costTotal), Object.keys(k).map(function (x) { return x + " " + U.inr(k[x]); }).join(" · ")],
        ["CYCLE", "#" + c.id, "started " + U.stamp(c.started_ms)]
      ]);
    }
  });
  UI.widget("paper-positions", {
    title: "OPEN POSITIONS", uses: ["swing", "paper"],
    render: function (el, D, ctx) {
      var open = (D.paper && D.paper.positions) || (D.swing && D.swing.open);
      if (!open) { el.innerHTML = C.state(D, "paper"); return; }
      ctx.right(open.length + " open");
      if (!open.length) { el.innerHTML = C.empty("No open positions."); return; }
      el.innerHTML = '<div class="cards">' + open.map(function (p) {
        return '<div class="pos"><div class="pos-top"><b>' + e(p.symbol) + "</b>" + C.side(1) + "</div>" +
          '<div class="mono small dim">' + e(U.name(p.strategy)) + " · " + e(p.qty) + " sh</div>" +
          '<div class="pos-r ' + cls(p.r_now) + '">' + U.rr(p.r_now) + "</div>" + C.rbar(p.r_now) +
          '<div class="mono tiny dim">in ' + U.px(p.entry) + " · now " + U.px(p.mark) + " · stop " + U.px(p.stop_now) +
          (p.stop_now !== p.stop_init ? " (was " + U.px(p.stop_init) + ")" : "") + "</div>" +
          '<div class="mono tiny">' + U.inr(p.unrealised_inr, true) + " · " + e(p.sessions_left) + " sessions left</div></div>";
      }).join("") + "</div>";
    }
  });
  UI.widget("paper-history", {
    title: "CLOSED TRADES", uses: ["paper"],
    mount: function (el, ctx) { ctx.s.t = { sort: null }; },
    on: { sort: function (el, ev, t, ctx) { C.sortState(ctx.s.t, +t.dataset.k); ctx.render(); } },
    render: function (el, D, ctx) {
      var p = D.paper; if (!p) { el.innerHTML = C.state(D, "paper"); return; }
      var h = p.history || [];
      var rs = h.map(function (t) { return t.r; });
      ctx.right(h.length ? h.length + " closed · avg " + U.rr(U.mean(rs)) + " · total " + U.rr(U.sum(rs)) : "");
      el.innerHTML = C.table([
        { label: "SYMBOL", w: "110px", cell: function (t) { return "<b>" + e(t.symbol) + "</b>"; }, sort: function (t) { return t.symbol; } },
        { label: "STRATEGY", cell: function (t) { return e(U.name(t.strategy)); } },
        { label: "R", w: "80px", cell: function (t) { return C.signed(t.r, U.rr); }, sort: function (t) { return t.r; } },
        { label: "NET", w: "100px", cell: function (t) { return C.signed(t.net_inr, function (x) { return U.inr(x, true); }); }, sort: function (t) { return t.net_inr; } },
        { label: "COSTS", w: "80px", cell: function (t) { return U.inr(t.costs_inr); } },
        { label: "EXIT", cell: function (t) { return e(t.exit_reason || ""); } },
        { label: "CLOSED", w: "110px", cell: function (t) { return e(U.stamp(t.exit_ms)); }, sort: function (t) { return t.exit_ms || 0; } }
      ], h.slice().reverse(), { state: ctx.s.t, empty: "No closed trades yet.", minWidth: 640 });
    }
  });
  UI.widget("paper-takeskip", {
    title: "TAKEN vs SKIPPED", uses: ["swing"],
    render: function (el, D) {
      var s = D.swing; if (!s) { el.innerHTML = C.state(D, "swing"); return; }
      var t = (s.takeskip && s.takeskip.take) || {}, k = (s.takeskip && s.takeskip.skip) || {};
      el.innerHTML = '<p class="small dim">Every signal, traded or skipped, is resolved by the same exit engine, so the skip rules can be audited.</p>' +
        C.bars([["TAKEN", (t.n || 0) + (t.running || 0), (t.n || 0) + " resolved · avg " + U.rr(t.avg_r), "up"],
          ["SKIPPED", (k.n || 0) + (k.running || 0), (k.n || 0) + " resolved · avg " + U.rr(k.avg_r), "dn"]]);
    }
  });
  UI.widget("paper-rules", {
    title: "RULES IN FORCE", uses: ["swing", "meta"],
    render: function (el, D) {
      var r = D.swing && D.swing.rules; if (!r) { el.innerHTML = C.state(D, "swing"); return; }
      el.innerHTML = C.tiles([["TIMEFRAME", r.timeframe || "1d", "daily close"], ["STOP", r.stop || "—", r.trail || ""],
        ["TIME LIMIT", (r.time_limit_sessions || "—") + " sessions", ""], ["RISK", (r.risk_pct || "—") + "%", "of capital per trade"],
        ["MIN SIZE", U.inr(r.min_position_inr), "CNC cost floor"], ["MAX OPEN", String(r.max_open || "—"), "one per symbol, max 2 per sector"],
        ["MARKET FILTER", r.market_filter || "off", r.vol_rank_max ? "vol rank > " + r.vol_rank_max + " skips" : ""],
        ["CAPITAL", U.inr(D.meta && D.meta.capital_inr), "paper"]]);
    }
  });
  UI.widget("paper-live", {
    title: "LIVE ₹", uses: ["golive"],
    render: function (el, D) {
      var g = D.golive; if (!g) { el.innerHTML = C.state(D, "golive"); return; }
      var open = (g.gates || []).filter(function (x) { return !x.ok; }).length;
      el.innerHTML = C.locked("Live trading is locked", open + " of " + (g.gates || []).length + " go-live gates still open (System › Health). Real orders also need MODE=live and LIVE_ORDERS=true in the server .env plus the owner's written yes.");
    }
  });
  UI.view("book/paper", [["paper-tiles"], ["paper-positions"], [{ w: "paper-history", size: "grow" }, { stack: ["paper-takeskip", "paper-rules", "paper-live"], size: "side" }]]);

  // ------------------------------------------------------------------ Signals
  var ROLE = ["all", "pick", "mirror", "random"], DEC = ["all", "taken", "skipped", "shadow"];
  UI.widget("signals-table", {
    title: "EVERY SIGNAL", uses: ["signals60"],
    mount: function (el, ctx) { ctx.s.role = "pick"; ctx.s.dec = "all"; ctx.s.q = ""; ctx.s.t = { sort: null }; },
    on: {
      role: function (el, ev, t, ctx) { ctx.s.role = t.dataset.v; ctx.render(); },
      dec: function (el, ev, t, ctx) { ctx.s.dec = t.dataset.v; ctx.render(); },
      q: function (el, ev, t, ctx) { ctx.s.q = t.value.toUpperCase(); ctx.render(); },
      sort: function (el, ev, t, ctx) { C.sortState(ctx.s.t, +t.dataset.k); ctx.render(); }
    },
    render: function (el, D, ctx) {
      var s = D.signals60; if (!s) { el.innerHTML = C.state(D, "signals60"); return; }
      var all = s.rows || [];
      var rows = all.filter(function (r) {
        return (ctx.s.role === "all" || r.role === ctx.s.role) && (ctx.s.dec === "all" || r.decision === ctx.s.dec) && (!ctx.s.q || r.symbol.indexOf(ctx.s.q) >= 0);
      });
      ctx.right(rows.length + " of " + all.length + " · 60 days");
      function chips(act, list, cur) { return list.map(function (v) { return '<button class="chipbtn' + (v === cur ? " on" : "") + '" data-act="' + act + '" data-v="' + v + '">' + v + "</button>"; }).join(""); }
      el.innerHTML = '<div class="chipset">' + chips("role", ROLE, ctx.s.role) + " " + chips("dec", DEC, ctx.s.dec) +
        ' <input class="search" data-act="q" placeholder="symbol…" value="' + e(ctx.s.q) + '"></div>' + C.table([
        { label: "TIME", w: "110px", cell: function (r) { return e(U.stamp(r.ts_ms)); }, sort: function (r) { return r.ts_ms; } },
        { label: "SYMBOL", w: "110px", cell: function (r) { return "<b>" + e(r.symbol) + "</b>"; }, sort: function (r) { return r.symbol; } },
        { label: "BOOK", w: "50px", cell: function (r) { return e(r.book); } },
        { label: "STRATEGY", w: "120px", cell: function (r) { return e(U.name(r.strategy)); } },
        { label: "ROLE", w: "70px", cell: function (r) { return C.tag(r.role); } },
        { label: "SIDE", w: "70px", cell: function (r) { return C.side(r.side); } },
        { label: "PRICE", w: "90px", cell: function (r) { return U.px(r.price); } },
        { label: "STOP", w: "90px", cell: function (r) { return U.px(r.stop); } },
        { label: "DECISION", w: "80px", cell: function (r) { return C.tag(r.decision, r.decision === "taken" ? "up" : r.decision === "skipped" ? "dn" : ""); } },
        { label: "WHY", cell: function (r) { return '<span class="dim">' + e(r.reason_text || r.skip_reason || "") + "</span>"; } },
        { label: "OUTCOME", w: "90px", cell: function (r) { return e(r.virtual_status || "—"); } }
      ], rows, { state: ctx.s.t, empty: "No signals yet. The first scan runs at 16:20 IST on a trading day.", minWidth: 1000 });
    }
  });
  UI.widget("signals-refused", {
    title: "WHY REFUSED", uses: ["signals60"],
    render: function (el, D) {
      var s = D.signals60; if (!s) { el.innerHTML = C.state(D, "signals60"); return; }
      var r = (s.refused || []).slice().sort(function (a, b) { return b.n - a.n; });
      el.innerHTML = r.length ? C.bars(r.map(function (x) { return [x.reason_text || x.reason, x.n, String(x.n), "dn"]; })) : C.empty("Nothing refused yet.");
    }
  });
  UI.view("book/signals", [[{ w: "signals-table", size: "grow" }, { w: "signals-refused", size: "side" }]]);
})();
