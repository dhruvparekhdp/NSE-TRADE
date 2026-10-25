/* System hub: Health (go-live, jobs, data, events) · Settings (kill switch, keys, Test Angel) (PLAN_V2 §8). */
(function () {
  "use strict";
  var U = UI.U, C = UI.C, e = U.esc;

  // ------------------------------------------------------------------ Health
  UI.widget("sys-golive", {
    title: "GO-LIVE GATES", uses: ["golive"],
    render: function (el, D, ctx) {
      var g = D.golive; if (!g) { el.innerHTML = C.state(D, "golive"); return; }
      var open = (g.gates || []).filter(function (x) { return !x.ok; }).length;
      ctx.right(g.verdict + " · " + open + " open");
      el.innerHTML = (g.gates || []).map(function (x) {
        return '<div class="trow" style="grid-template-columns:24px minmax(0,1fr) minmax(0,1.2fr)"><b class="' + (x.ok ? "up" : "dn") + '">' + (x.ok ? "✓" : "✗") +
          "</b><span>" + e(x.label) + '</span><span class="dim small">' + e(x.detail || "") + "</span></div>";
      }).join("") || C.empty("No gates reported.");
    }
  });
  UI.widget("sys-engine", {
    title: "ENGINE", uses: ["health", "meta"],
    render: function (el, D) {
      var h = D.health; if (!h) { el.innerHTML = C.state(D, "health"); return; }
      var m = D.meta || {};
      el.innerHTML = C.tiles([
        ["STATUS", h.ok ? "ok" : "problem", h.status || "", h.ok ? "up" : "dn"],
        ["MODE", String(h.mode || "").toUpperCase(), "live orders " + (h.live_orders ? "ON" : "off")],
        ["ANGEL", h.angel_configured ? (h.login_ok ? "logged in" : "keys set") : "no keys", h.ws_connected ? "feed connected" : "feed idle"],
        ["SESSION", h.session_state || "—", m.calendar_ok ? "calendar " + m.calendar_year_loaded + " ok" : "calendar missing"],
        ["COSTS", m.costs_verified ? "verified" : "not verified", "contract note pending"],
        ["VERSION", m.version || "—", ""]
      ]);
    }
  });
  UI.widget("sys-jobs", {
    title: "JOBS", uses: ["health"],
    render: function (el, D) {
      var h = D.health; if (!h) { el.innerHTML = C.state(D, "health"); return; }
      var jobs = (h.jobs || []).slice().sort(function (a, b) { return (a.next_run_ms || 9e15) - (b.next_run_ms || 9e15); });
      el.innerHTML = C.table([
        { label: "JOB", cell: function (j) { return "<b>" + e(U.name(j.id)) + "</b>"; } },
        { label: "LAST RUN", w: "120px", cell: function (j) { return e(U.stamp(j.last_run_ms)); } },
        { label: "RESULT", cell: function (j) { return '<span class="' + (j.last_ok === false ? "dn" : "dim") + '">' + e(j.result || (j.last_run_ms ? "ok" : "not run yet")) + "</span>"; } },
        { label: "NEXT RUN", w: "120px", cell: function (j) { return e(U.stamp(j.next_run_ms)); } }
      ], jobs, { empty: "No jobs reported.", minWidth: 560, limit: 50 });
    }
  });
  UI.widget("sys-data", {
    title: "DATA", uses: ["datahealth"],
    render: function (el, D) {
      var d = D.datahealth; if (!d) { el.innerHTML = C.state(D, "datahealth"); return; }
      var l = d.lake || {}, b = d.bhav || {};
      el.innerHTML = C.tiles([
        ["DAILY BARS", l.symbols ? l.symbols + " symbols" : "none yet", l.first_date ? l.first_date + " → " + l.last_date : "first fill at 16:10 on a trading day"],
        ["MISSING DAYS", String(l.missing_n || 0), (l.missing_days || []).slice(0, 4).join(", ")],
        ["BHAVCOPY", b.last_date || "—", b.format || ""],
        ["CORP ACTIONS", d.corp_actions_applied ? "applied" : "not yet", ""],
        ["1-MIN BARS TODAY", d.minutes_today ? d.minutes_today.rows + " rows" : "—", d.minutes_today ? d.minutes_today.symbols + " symbols" : ""]
      ]);
    }
  });
  UI.widget("sys-events", {
    title: "EVENTS", uses: ["events"],
    render: function (el, D) {
      var ev = D.events; if (!ev) { el.innerHTML = C.state(D, "events"); return; }
      el.innerHTML = C.table([
        { label: "TIME", w: "110px", cell: function (r) { return e(U.stamp(r.ts_ms)); } },
        { label: "KIND", w: "150px", cell: function (r) { return C.tag(r.kind); } },
        { label: "DETAIL", cell: function (r) { return '<span class="mono tiny dim">' + e(String(r.json || "").slice(0, 160)) + "</span>"; } }
      ], ev.rows || [], { empty: "No events yet.", minWidth: 560, limit: 30 });
    }
  });
  UI.view("system/health", [[{ w: "sys-golive", size: "grow" }, { w: "sys-engine", size: "side" }], [{ w: "sys-jobs", size: "grow" }, { w: "sys-data", size: "side" }], ["sys-events"]]);

  // ------------------------------------------------------------------ Settings
  UI.widget("set-login", {
    title: "ADMIN",
    on: {
      login: function (el, ev, t, ctx) {
        var pw = el.querySelector("[name=pw]").value;
        UI.Net.post("api/login", { password: pw }).then(function () { UI.toast("Signed in"); UI.Store.refresh && UI.Store.refresh("keys"); ctx.s.msg = "Signed in."; ctx.render(); })
          .catch(function (err) { ctx.s.msg = "Sign-in failed: " + err.message; ctx.render(); });
      },
      kill: function (el, ev, t, ctx) {
        var on = t.dataset.v === "on";
        if (on && !window.confirm("Stop all NEW entries? Open positions keep their stops.")) return;
        UI.Net.post("api/kill", { on: on }).then(function (r) { ctx.s.msg = "Kill switch " + (r.kill_switch ? "ON" : "off") + "."; ctx.render(); })
          .catch(function (err) { ctx.s.msg = "Failed: " + err.message; ctx.render(); });
      },
      testangel: function (el, ev, t, ctx) {
        ctx.s.msg = "Testing Angel (read-only)…"; ctx.render();
        UI.Net.post("api/keys/test-angel", {}).then(function (r) {
          ctx.s.msg = "Angel: " + (r.ok || r.login_ok ? "login OK" : "login failed") + (r.hint ? " · " + r.hint : "") +
            (r.available_cash != null ? " · cash " + U.inr(r.available_cash) : "") + (r.holdings_count != null ? " · " + r.holdings_count + " holdings" : "");
          ctx.render();
        }).catch(function (err) { ctx.s.msg = "Test failed: " + err.message; ctx.render(); });
      }
    },
    render: function (el, D, ctx) {
      el.innerHTML = '<div class="chipset"><input type="password" name="pw" placeholder="admin password" class="search">' +
        '<button class="chipbtn on" data-act="login">SIGN IN</button>' +
        '<button class="chipbtn" data-act="kill" data-v="on">KILL SWITCH ON</button>' +
        '<button class="chipbtn" data-act="kill" data-v="off">KILL SWITCH OFF</button>' +
        '<button class="chipbtn" data-act="testangel">TEST ANGEL (READ-ONLY)</button></div>' +
        (ctx.s.msg ? '<p class="small" style="margin-top:8px">' + e(ctx.s.msg) + "</p>" : "") +
        '<p class="small dim" style="margin-top:8px">Mode and live orders can only be changed in the server .env, never here.</p>';
    }
  });
  UI.widget("set-session", {
    title: "SESSION TIMES (READ-ONLY)", uses: ["meta"],
    render: function (el, D) {
      var m = D.meta; if (!m) { el.innerHTML = C.state(D, "meta"); return; }
      el.innerHTML = C.tiles([["BROKER SQUARE-OFF", m.broker_squareoff_at || "—", "confirm in the Angel app"],
        ["ENGINE SQUARE-OFF", m.squareoff_at || "—", "15 min earlier"], ["NO NEW ENTRIES", m.no_entry_after || "—", ""],
        ["CAPITAL (PAPER)", U.inr(m.capital_inr), ""], ["BOOK A", m.book_a_mode || "—", "intraday"], ["MARKET FILTER", m.market_filter || "off", ""]]);
    }
  });
  UI.widget("set-keys", {
    title: "KEYS · ENCRYPTED IN POSTGRES", uses: ["keys"],
    render: function (el, D, ctx) {
      var k = D.keys; if (!k) { el.innerHTML = C.state(D, "keys"); return; }
      ctx.right(k.secure_channel ? "secure channel" : "plain HTTP: saving and revealing keys is disabled");
      el.innerHTML = C.table([
        { label: "KEY", cell: function (r) { return "<b>" + e(r.label || r.key) + "</b>"; } },
        { label: "SAVED VALUE", w: "150px", cell: function (r) { return r.is_set ? '<span class="mono">' + e(r.masked || "set") + "</span>" : '<span class="dim">not set</span>'; } },
        { label: "LEN", w: "50px", cell: function (r) { return e(r.length || ""); } },
        { label: "WHERE", w: "70px", cell: function (r) { return e(r.where || ""); } },
        { label: "SAVED", w: "110px", cell: function (r) { return e(U.stamp(r.saved_ms)); } }
      ], k.rows || [], { empty: "No keys.", minWidth: 560 }) + '<p class="small dim" style="margin-top:8px">Edit keys on the <a href="keys">keys page</a> (needs HTTPS or Tailscale).</p>';
    }
  });
  UI.view("system/settings", [[{ w: "set-login", size: "grow" }, { w: "set-session", size: "side" }], ["set-keys"]]);
})();
