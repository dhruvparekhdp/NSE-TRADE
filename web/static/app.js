/* NSE portal shell — hash hubs, shared fetch store, crypto-like pages. */
(function () {
  "use strict";
  var Nav = window.PortalNav;
  var store = {};
  var pollers = {};

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function inr(x) {
    if (x == null || !isFinite(x)) return "—";
    return "₹" + Math.abs(x).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }
  function ago(ms) {
    if (!ms) return "—";
    var m = Math.round((Date.now() - ms) / 60000);
    return m < 1 ? "just now" : m < 60 ? m + "m ago" : Math.round(m / 60) + "h ago";
  }
  function toast(msg) {
    var el = document.getElementById("toast");
    el.hidden = false;
    el.textContent = msg;
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { el.hidden = true; }, 2800);
  }

  function get(url) {
    return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  function post(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      if (r.status === 401) throw new Error("login required — open System → Keys");
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function use(key, url, everyMs) {
    if (!store[key]) store[key] = { data: null, err: null, at: 0 };
    function pull() {
      return get(url).then(function (d) {
        store[key].data = d; store[key].err = null; store[key].at = Date.now();
        render();
      }).catch(function (e) {
        store[key].err = String(e.message || e); render();
      });
    }
    if (!pollers[key]) {
      pull();
      pollers[key] = setInterval(pull, everyMs || 20000);
    }
    return store[key];
  }

  function panel(title, body) {
    return '<section class="panel"><h2>' + esc(title) + "</h2>" + body + "</section>";
  }
  function tiles(rows) {
    return '<div class="grid">' + rows.map(function (r) {
      return '<div class="tile"><small>' + esc(r[0]) + "</small><b>" + esc(r[1]) + "</b></div>";
    }).join("") + "</div>";
  }

  var AGENTS = [
    ["Free quotes", "yfinance poll — no Angel cost"],
    ["Session clock", "IST market hours + kill switch"],
    ["Strategies", "ORB · VWAP · gap · swing …"],
    ["Paper book", "MIS/CNC fills after costs"],
    ["News / AI", "Shared crypto headlines + HF"],
    ["Angel orders", "Only when mode=live + live_orders"]
  ];
  var agentStage = 0;

  function renderCommand(tab) {
    var today = use("today", "api/today", 15000).data || {};
    var quotes = use("quotes", "api/quotes", 30000).data || {};
    var qlist = quotes.quotes || [];
    if (tab.id === "watchlist") {
      var rows = qlist.map(function (q) {
        var chg = q.prev_close ? ((q.ltp - q.prev_close) / q.prev_close * 100) : null;
        return "<tr><td>" + esc(q.symbol) + "</td><td>" + esc(q.ltp.toFixed(2)) + "</td><td>" +
          (chg == null ? "—" : (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%") + "</td><td>" + esc(q.source) + "</td></tr>";
      }).join("");
      return panel("WATCHLIST · free yfinance",
        '<p class="dim small" style="margin-bottom:10px">Delayed Yahoo NSE (.NS). Angel WS not used for watching.</p>' +
        (rows
          ? '<table class="table"><thead><tr><th>SYM</th><th>LTP</th><th>CHG</th><th>SRC</th></tr></thead><tbody>' + rows + "</tbody></table>"
          : '<p class="muted">No quotes yet. System → Data → Refresh, or wait for the poller.</p>'));
    }
    if (tab.id === "pipeline") {
      var metrics = [
        (qlist.length || 0) + " symbols",
        today.session_state || "—",
        (today.quotes_n || 0) + " cached",
        "paper book",
        "shared news",
        today.angel_configured ? "keys set" : "Angel idle"
      ];
      return panel("AGENT PIPELINE",
        '<div class="flow"><div class="flow-fill" style="width:' + (((agentStage + 1) / AGENTS.length) * 100).toFixed(1) + '%"></div></div>' +
        '<div class="agents">' + AGENTS.map(function (a, i) {
          return '<div class="agent' + (i === agentStage ? " active" : "") + '"><div class="a-top mono tiny dim">0' + (i + 1) +
            "</div><b>" + esc(a[0]) + "</b><p class=\"small dim\">" + esc(a[1]) + '</p><span class="metric">' + esc(metrics[i]) + "</span></div>";
        }).join("") + "</div>");
    }
    return panel("TODAY",
      tiles([
        ["MODE", String(today.mode || "paper").toUpperCase()],
        ["SESSION", today.session_state || "—"],
        ["CAPITAL", inr(today.capital_inr)],
        ["QUOTES", (today.quotes_n || 0) + " · " + (today.quotes_age_s != null ? today.quotes_age_s + "s" : "—")],
        ["KILL", today.kill_switch ? "ON" : "off"],
        ["LIVE ORDERS", today.live_orders ? "YES" : "no"]
      ]) +
      '<p class="dim small" style="margin-top:12px">' + esc(today.data_source || "") + "</p>");
  }

  function renderBook(tab) {
    if (tab.id === "live") {
      return panel("LIVE ₹",
        '<p class="dim">Dual gate: <b class="acc">mode=live</b> and <b class="acc">live_orders=true</b>. Until then everything is paper. Angel keys live in System → Keys.</p>');
    }
    if (tab.id === "books") {
      var books = use("books", "api/books", 30000).data || {};
      var a = books.A || {}, b = books.B || {};
      return panel("BOOK A (MIS) · BOOK B (CNC)",
        tiles([
          ["A TRADES", String(a.trades || 0)],
          ["A AVG R", a.avg_r != null ? Number(a.avg_r).toFixed(2) : "—"],
          ["B TRADES", String(b.trades || 0)],
          ["B AVG R", b.avg_r != null ? Number(b.avg_r).toFixed(2) : "—"]
        ]));
    }
    var paper = use("paper", "api/paper", 20000).data || {};
    var open = paper.open || [];
    var body = tiles([
      ["CAPITAL", inr(paper.capital_inr)],
      ["OPEN", String(open.length)],
      ["CLOSED", String(paper.closed_trades || 0)]
    ]);
    if (open.length) {
      body += '<table class="table" style="margin-top:12px"><thead><tr><th>SYM</th><th>BOOK</th><th>STRAT</th><th>QTY</th><th>ENTRY</th></tr></thead><tbody>' +
        open.map(function (t) {
          return "<tr><td>" + esc(t.symbol) + "</td><td>" + esc(t.book) + "</td><td>" + esc(t.strategy) + "</td><td>" +
            esc(t.qty) + "</td><td>" + esc(t.entry_price) + "</td></tr>";
        }).join("") + "</tbody></table>";
    } else {
      body += '<p class="muted" style="margin-top:12px">' + esc(paper.note || "No open paper trades yet.") + "</p>";
    }
    return panel("PAPER BOOK", body);
  }

  function renderLab(tab) {
    if (tab.id === "trials") {
      var lab = use("lab", "api/lab", 30000).data || {};
      var trials = lab.trials || [];
      if (!trials.length) return panel("LAB TRIALS", '<p class="muted">No trials yet. Research jobs write here.</p>');
      return panel("LAB TRIALS",
        '<table class="table"><thead><tr><th>ID</th><th>STRAT</th><th>N</th><th>AVG R</th><th>WIN%</th><th>PASS</th></tr></thead><tbody>' +
        trials.map(function (t) {
          return "<tr><td>" + esc(t.id) + "</td><td>" + esc(t.strategy) + "</td><td>" + esc(t.n) + "</td><td>" +
            esc(t.avg_r) + "</td><td>" + esc(t.win_pct) + "</td><td>" + (t.passed ? "yes" : "no") + "</td></tr>";
        }).join("") + "</tbody></table>");
    }
    var st = use("strategies", "api/strategies", 60000).data || {};
    var rows = (st.strategies || []).map(function (s) {
      return "<tr><td>" + esc(s.id) + "</td><td>" + esc(s.book) + "</td><td>" + esc(s.timeframe) +
        "</td><td>" + (s.enabled ? "on" : "off") + "</td></tr>";
    }).join("");
    return panel("STRATEGIES (crypto-shared families)",
      '<p class="dim small" style="margin-bottom:10px">ORB · VWAP revert · gap · momo · PDH/RS · Donchian · Keltner</p>' +
      (rows
        ? '<table class="table"><thead><tr><th>ID</th><th>BOOK</th><th>TF</th><th>EN</th></tr></thead><tbody>' + rows + "</tbody></table>"
        : '<p class="muted">Registry empty.</p>'));
  }

  function renderSystem(tab) {
    if (tab.id === "keys") {
      return panel("KEYS", '<p>Open the encrypted store: <a href="keys">API keys (DB)</a></p>');
    }
    if (tab.id === "golive") {
      return panel("GO-LIVE CHECKLIST",
        '<ol class="dim" style="margin:0;padding-left:1.2rem;line-height:1.7">' +
        "<li>Paper P&amp;L stable after costs</li>" +
        "<li>Strategies pass Lab gates</li>" +
        "<li>Angel keys in Postgres via Keys page</li>" +
        "<li>Set mode=live <b>and</b> live_orders (dual gate)</li>" +
        "<li>Keep free quotes for research; Angel only for orders</li>" +
        "</ol>");
    }
    if (tab.id === "data") {
      var q = use("quotes", "api/quotes", 30000).data || {};
      return panel("DATA · FREE FIRST",
        tiles([
          ["SOURCE", q.source || "—"],
          ["SYMBOLS", String((q.quotes || []).length)],
          ["UPDATED", ago(q.ts_ms)]
        ]) +
        '<p class="dim small" style="margin:12px 0">No free NSE tick socket we trust. Polling yfinance (.NS) every few minutes. Angel SmartAPI WS stays off until live orders.</p>' +
        '<button class="btn primary" id="btnRefreshQuotes" type="button">Refresh quotes now</button>');
    }
    var h = use("health", "api/health", 15000).data || {};
    return panel("HEALTH",
      '<pre class="mono small" style="white-space:pre-wrap;margin:0">' + esc(JSON.stringify(h, null, 2)) + "</pre>");
  }

  function renderView(loc) {
    var h = loc.hub.id, t = loc.tab;
    if (h === "command") return renderCommand(t);
    if (h === "book") return renderBook(t);
    if (h === "lab") return renderLab(t);
    return renderSystem(t);
  }

  function paintChrome(loc) {
    var logo = document.getElementById("logoWord");
    logo.setAttribute("data-text", loc.hub.label.toUpperCase());
    logo.textContent = loc.hub.label.toUpperCase();

    document.getElementById("hubTabs").innerHTML = Nav.NAV.map(function (h) {
      var cls = "tab" + (h.id === loc.hub.id ? " on" : "");
      return '<a class="' + cls + '" href="' + Nav.href(h, h.tabs[0]) + '">' + esc(h.label) + "</a>";
    }).join("");

    document.getElementById("subTabs").innerHTML = loc.hub.tabs.map(function (t) {
      var cls = "subtab" + (t.id === loc.tab.id ? " on" : "");
      var href = t.url || Nav.href(loc.hub, t);
      return '<a class="' + cls + '" href="' + href + '">' + esc(t.label) + "</a>";
    }).join("");
  }

  function paintStrip() {
    var today = (store.today && store.today.data) || {};
    var quotes = (store.quotes && store.quotes.data) || {};
    var live = today.mode === "live" && today.live_orders;
    document.getElementById("stripGate").textContent = "FREE DATA";
    document.getElementById("stripQuotes").textContent =
      (today.quotes_n || (quotes.quotes || []).length || 0) + " quotes · " +
      (today.quotes_age_s != null ? today.quotes_age_s + "s old" : "waiting");
    document.getElementById("stripFeed").textContent =
      today.angel_configured ? "Angel keys ok · WS idle" : "Angel not configured";
    document.getElementById("stripMode").textContent = live ? "LIVE MONEY" : "PAPER ONLY";
    var chip = document.getElementById("modeChip");
    chip.textContent = live ? "LIVE" : "PAPER";
    chip.className = "chip " + (live ? "live" : "ink");
    document.getElementById("sessChip").textContent = today.session_state || "—";

    var qlist = quotes.quotes || [];
    var tape = document.getElementById("tape");
    if (qlist.length) {
      var html = qlist.map(function (q) {
        return "<span><b>" + esc(q.symbol) + "</b> " + esc(Number(q.ltp).toFixed(2)) + "</span>";
      }).join("");
      tape.innerHTML = html + html;
    }
  }

  function render() {
    var loc = Nav.locate(location.hash);
    paintChrome(loc);
    document.getElementById("view").innerHTML = renderView(loc);
    paintStrip();
    var btn = document.getElementById("btnRefreshQuotes");
    if (btn) {
      btn.onclick = function () {
        btn.disabled = true;
        post("api/quotes/refresh", {}).then(function (r) {
          toast("Fetched " + r.n + " quotes");
          delete pollers.quotes;
          use("quotes", "api/quotes", 30000);
        }).catch(function (e) {
          toast(String(e.message || e));
        }).finally(function () { btn.disabled = false; });
      };
    }
  }

  function tickClock() {
    var d = new Date();
    var ist = new Date(d.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
    function p(n) { return String(n).padStart(2, "0"); }
    document.getElementById("clock").textContent =
      p(ist.getHours()) + ":" + p(ist.getMinutes()) + ":" + p(ist.getSeconds());
  }

  window.addEventListener("hashchange", render);
  if (!location.hash) location.hash = "#/command";
  use("today", "api/today", 15000);
  use("quotes", "api/quotes", 30000);
  setInterval(function () { agentStage = (agentStage + 1) % AGENTS.length; if ((Nav.locate(location.hash).tab || {}).id === "pipeline") render(); }, 1600);
  setInterval(tickClock, 1000);
  tickClock();
  render();
})();
