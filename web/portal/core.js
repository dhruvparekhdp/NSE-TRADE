/* Portal core: shared store, component kit, widget runtime and the app shell.
   Ported from the crypto engine's micro-UI (PLAN_V2 D7, §8). NSE differences: hash routing under
   <base href="/nse/">, ₹ and IST formatting, NSE endpoints, and one rule above all:
   NOTHING IS SIMULATED. A widget with no data shows an empty state, never a made-up number.

   Micro UI model
   - Store: one entry per endpoint. Widgets subscribe; an endpoint polls only while something is
     subscribed, every subscriber shares one request, and polling pauses while the tab is hidden.
   - Widgets: self-contained units registered by the hub modules (hubs/*.js), each declaring the
     store keys it uses. The shell mounts the widgets of the open page and unmounts the rest.
   - Components (UI.C): pure functions returning HTML for the pieces every page repeats
     (panel, tiles, table, bars, tags, meters, flags, link grids…). All text goes through esc().
   - Hub modules load on first visit to their hub, never before. */
(function () {
  "use strict";
  var Nav = window.PortalNav;
  var ASSETS = window.PORTAL_ASSETS || {};
  var IST_MS = 5.5 * 3600e3;                                   // India has no daylight saving

  // ---------------------------------------------------------------- utilities
  var U = {};
  U.$ = function (sel, root) { return (root || document).querySelector(sel); };
  U.esc = function (v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  U.reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  U.pad = function (n) { return String(n).padStart(2, "0"); };
  // All stored times are UTC epoch ms; the browser shows IST (AGENTS rule 7).
  U.ist = function (ms) { return new Date(ms + IST_MS); };
  U.hms = function (ms) { var d = U.ist(ms); return U.pad(d.getUTCHours()) + ":" + U.pad(d.getUTCMinutes()) + ":" + U.pad(d.getUTCSeconds()); };
  U.hm = function (ms) { var d = U.ist(ms); return U.pad(d.getUTCHours()) + ":" + U.pad(d.getUTCMinutes()); };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  U.day = function (ms) { var d = U.ist(ms); return U.pad(d.getUTCDate()) + " " + MONTHS[d.getUTCMonth()]; };
  U.stamp = function (ms) { return U.num(ms) ? U.day(ms) + " " + U.hm(ms) : "—"; };
  U.dur = function (ms) { var s = Math.max(0, Math.floor(ms / 1000)); return U.pad(Math.floor(s / 3600)) + ":" + U.pad(Math.floor(s / 60) % 60) + ":" + U.pad(s % 60); };
  U.num = function (x) { return x != null && x !== "" && isFinite(x); };
  U.px = function (p) { return U.num(p) ? Number(p).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"; };
  U.pct = function (x, d) { return U.num(x) ? (x >= 0 ? "+" : "−") + Math.abs(Number(x)).toFixed(d == null ? 2 : d) + "%" : "—"; };
  U.rr = function (x) { return U.num(x) ? (x >= 0 ? "+" : "−") + Math.abs(Number(x)).toFixed(2) + "R" : "—"; };
  U.inr = function (x, signed) {
    if (!U.num(x)) return "—";
    var s = "₹" + Math.abs(x).toLocaleString("en-IN", { maximumFractionDigits: Math.abs(x) < 100 ? 2 : 0 });
    return (x < 0 ? "−" : signed ? "+" : "") + s;
  };
  U.cr = function (x) { return U.num(x) ? (x < 0 ? "−" : "") + "₹" + Math.abs(x).toLocaleString("en-IN", { maximumFractionDigits: 0 }) + " cr" : "—"; };
  U.compact = function (n) {
    if (!U.num(n)) return "—";
    var a = Math.abs(n);
    return a >= 1e7 ? (n / 1e7).toFixed(2) + " cr" : a >= 1e5 ? (n / 1e5).toFixed(1) + " L" : a >= 1e3 ? (n / 1e3).toFixed(0) + "K" : String(Math.round(n));
  };
  U.ago = function (ms) {
    if (!U.num(ms)) return "—";
    var m = Math.round((Date.now() - ms) / 60000);
    return m < 1 ? "just now" : m < 60 ? m + "m ago" : m < 2880 ? Math.round(m / 60) + "h ago" : Math.round(m / 1440) + "d ago";
  };
  U.secs = function (s) { return !U.num(s) ? "—" : s < 120 ? Math.round(s) + "s" : s < 7200 ? Math.round(s / 60) + "m" : Math.round(s / 3600) + "h"; };
  U.name = function (s) { return String(s || "").replace(/[_@:]/g, " "); };
  U.median = function (xs) { var v = xs.filter(U.num).sort(function (a, b) { return a - b; }); return v.length ? v[Math.floor(v.length / 2)] : null; };
  U.mean = function (xs) { var v = xs.filter(U.num); return v.length ? v.reduce(function (a, b) { return a + b; }, 0) / v.length : null; };
  U.sum = function (xs) { return xs.filter(U.num).reduce(function (a, b) { return a + b; }, 0); };
  U.sideName = function (s) { return s === -1 || String(s).toLowerCase() === "short" ? "short" : "long"; };

  // ---------------------------------------------------------------- network
  var Net = {};
  Net.get = function (url) {
    return fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" }).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) { var b = {}; try { b = JSON.parse(t); } catch (x) { b = { error: t }; } return b; }).then(function (b) {
          var e = new Error(b.error || b.reason || ("HTTP " + r.status)); e.status = r.status; throw e;
        });
      }
      return r.json();
    });
  };
  // Admin actions ride on the signed login cookie (POST api/login). A 401 means "log in on Settings".
  Net.post = function (url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}), credentials: "same-origin" })
      .then(function (r) {
        return r.text().then(function (t) { var b = {}; try { b = JSON.parse(t); } catch (x) { b = { error: t }; } return b; }).then(function (b) {
          if (!r.ok) { var e = new Error(b.error || b.reason || ("HTTP " + r.status)); e.status = r.status; throw e; }
          return b;
        });
      });
  };

  // ---------------------------------------------------------------- store
  var Store = { src: {} };
  Store.def = function (key, url, every) { Store.src[key] = Store.src[key] || { key: key, url: url, every: every || 0, subs: [], data: undefined, err: "", at: 0 }; return Store.src[key]; };
  Store.get = function (key) { var s = Store.src[key]; return s ? s.data : undefined; };
  Store.fetch = function (key) {
    var s = Store.src[key]; if (!s || s.inflight) return s && s.inflight;
    s.inflight = Net.get(s.url).then(function (d) { s.data = d; s.err = ""; }).catch(function (e) { s.err = e.message || "failed"; s.status = e.status; })
      .then(function () { s.at = Date.now(); s.inflight = null; s.subs.slice().forEach(function (fn) { fn(key); }); });
    return s.inflight;
  };
  Store.use = function (key, fn) {
    var s = Store.src[key]; if (!s) throw new Error("unknown store key " + key);
    s.subs.push(fn);
    if (s.subs.length === 1) {
      if (!s.at || (s.every && Date.now() - s.at > s.every)) Store.fetch(key); else setTimeout(function () { fn(key); }, 0);
      if (s.every) s.timer = setInterval(function () { if (!document.hidden) Store.fetch(key); }, s.every);
    } else if (s.at) setTimeout(function () { fn(key); }, 0);
    return function () {
      var i = s.subs.indexOf(fn); if (i >= 0) s.subs.splice(i, 1);
      if (!s.subs.length && s.timer) { clearInterval(s.timer); s.timer = null; }
    };
  };
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) return;
    Object.keys(Store.src).forEach(function (k) { var s = Store.src[k]; if (s.subs.length && s.every && Date.now() - s.at > s.every) Store.fetch(k); });
  });
  // The shared endpoints (PLAN_V2 §7). URLs are relative: <base href="/nse/"> puts them under /nse/.
  Store.def("meta", "api/portal/meta", 30000);
  Store.def("quotes", "api/quotes", 30000);
  Store.def("market", "api/market", 60000);
  Store.def("swing", "api/swing", 30000);
  Store.def("paper", "api/paper", 20000);
  Store.def("signals", "api/portal/signals?days=14", 30000);
  Store.def("signals60", "api/portal/signals?days=60", 60000);
  Store.def("lab", "api/lab", 300000);
  Store.def("golive", "api/golive", 20000);
  Store.def("guard", "api/guard", 20000);
  Store.def("datahealth", "api/data-health", 60000);
  Store.def("opening", "api/opening", 30000);
  Store.def("sentiment", "api/sentiment", 60000);
  Store.def("headlines", "api/headlines?hours=24", 120000);
  Store.def("health", "api/health", 15000);
  Store.def("events", "api/events?limit=30", 60000);
  Store.def("keys", "api/keys", 0);

  // ---------------------------------------------------------------- components
  var e = U.esc, C = {};
  C.empty = function (msg) { return '<div class="empty">' + e(msg) + "</div>"; };
  C.loading = function () { return '<div class="empty">Loading…</div>'; };
  C.state = function (D, key, emptyMsg) {   // standard loading / error line for one store key
    var s = Store.src[key];
    if (s && s.err && D[key] === undefined) return '<div class="empty err">' + (s.status === 401 || s.status === 403 ? "Admin login needed: sign in on Settings." : "Unavailable: " + e(s.err)) + "</div>";
    if (D[key] === undefined) return C.loading();
    return emptyMsg ? C.empty(emptyMsg) : "";
  };
  C.locked = function (title, why) { return '<div class="locked"><b>🔒 ' + e(title) + "</b><span>" + e(why) + "</span></div>"; };
  C.tiles = function (items) {     // [[label, value, sub, cls]]
    return '<div class="kv">' + items.map(function (t) {
      return "<div" + (t[3] ? ' class="' + e(t[3]) + '"' : "") + "><small>" + e(t[0]) + "</small><b>" + e(t[1]) + "</b>" + (t[2] ? "<span>" + e(t[2]) + "</span>" : "") + "</div>";
    }).join("") + "</div>";
  };
  C.tag = function (text, kind) { return '<span class="st-tag' + (kind ? " " + kind : "") + '">' + e(text) + "</span>"; };
  C.side = function (dir) { var s = U.sideName(dir) === "short"; return '<span class="side-tag' + (s ? " short" : "") + '">' + (s ? "SHORT" : "LONG") + "</span>"; };
  C.signed = function (x, fmt) { return '<b class="' + (x >= 0 ? "up" : "dn") + '">' + e((fmt || U.pct)(x)) + "</b>"; };
  C.meter = function (share, hot) {
    var w = U.num(share) ? Math.max(0, Math.min(100, share * 100)) : 0;
    return '<div class="meter"><i class="' + (hot || share >= 0.75 ? "hot" : "") + '" style="width:' + w.toFixed(1) + '%"></i></div>';
  };
  C.rbar = function (R) {
    var prog = U.num(R) ? (Math.max(-1, Math.min(3, R)) + 1) / 4 * 100 : 25;
    return '<div class="rbar"><div class="rbar-fill' + (R < 0 ? " dn" : "") + '" style="width:' + prog.toFixed(1) + '%"></div><div class="rbar-zero"></div></div>';
  };
  C.bars = function (rows, opts) {   // [[label, value, note, cls]] horizontal bars, scaled to the max
    opts = opts || {};
    var mx = Math.max.apply(null, rows.map(function (r) { return r[1] || 0; }).concat([opts.max || 1e-9]));
    return '<div class="bars">' + rows.map(function (r) {
      return '<div class="bar-row"><div class="bar-top"><span>' + e(r[0]) + "</span><em>" + e(r[2]) + '</em></div><div class="bar-track"><i class="' + (r[3] || "") + '" style="width:' + ((r[1] || 0) / mx * 100).toFixed(1) + '%"></i></div></div>';
    }).join("") + "</div>";
  };
  C.hist = function (buckets, opts) {   // [{label, n, cls}] vertical histogram
    opts = opts || {};
    var mx = Math.max.apply(null, buckets.map(function (b) { return b.n; }).concat([1]));
    return '<div class="hist">' + buckets.map(function (b) {
      return '<div class="hist-col" title="' + e(b.n + " " + (opts.unit || "")) + '"><i class="' + (b.cls || "") + '" style="height:' + (b.n / mx * 100).toFixed(1) + '%"></i><span>' + e(b.label) + "</span></div>";
    }).join("") + "</div>";
  };
  C.flag = function (level, title, desc, extra) {
    return '<div class="flag ' + e(level) + '"><b>' + e(title) + "</b><p>" + e(desc) + "</p>" + (extra ? '<span class="mono tiny">' + e(extra) + "</span>" : "") + "</div>";
  };
  C.links = function (list) {        // [[href, title, sub]]
    return '<div class="links">' + list.map(function (l) { return '<a href="' + e(l[0]) + '"><b>' + e(l[1]) + "</b><span>" + e(l[2]) + "</span></a>"; }).join("") + "</div>";
  };
  C.pre = function (text) { return '<pre class="pre">' + e(text) + "</pre>"; };
  /* A thin line chart as inline SVG. points: [{x, y}] with numeric x/y. No axes, one baseline. */
  C.spark = function (points, opts) {
    opts = opts || {};
    var pts = (points || []).filter(function (p) { return U.num(p.x) && U.num(p.y); });
    if (pts.length < 2) return C.empty(opts.empty || "Not enough points to draw a curve yet.");
    var xs = pts.map(function (p) { return p.x; }), ys = pts.map(function (p) { return p.y; }).concat(opts.base != null ? [opts.base] : []);
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    var dx = x1 - x0 || 1, dy = y1 - y0 || 1;
    function X(v) { return ((v - x0) / dx * 1000).toFixed(1); }
    function Y(v) { return (160 - (v - y0) / dy * 150 - 5).toFixed(1); }
    var line = pts.map(function (p) { return X(p.x) + "," + Y(p.y); }).join(" ");
    return '<div class="spark"><svg viewBox="0 0 1000 160" preserveAspectRatio="none" aria-hidden="true">' +
      (opts.base != null ? '<line class="spark-base" x1="0" x2="1000" y1="' + Y(opts.base) + '" y2="' + Y(opts.base) + '"></line>' : "") +
      '<polyline class="spark-line" points="' + line + '"></polyline></svg></div>';
  };
  /* Data table. cols: [{label, w, cell(row) -> html, sort(row) -> value, cls}]. Sorting is driven by
     the widget's own state ({sort, dir}); headers carry data-act="sort" data-k=<index>. */
  C.table = function (cols, rows, opts) {
    opts = opts || {};
    if (!rows.length) return C.empty(opts.empty || "Nothing to show.");
    var st = opts.state || {};
    if (st.sort != null && cols[st.sort] && cols[st.sort].sort) {
      var f = cols[st.sort].sort, dir = st.dir || -1;
      rows = rows.slice().sort(function (a, b) { var x = f(a), y = f(b); return (x > y ? 1 : x < y ? -1 : 0) * dir; });
    }
    var tpl = "grid-template-columns:" + cols.map(function (c) { return c.w || "minmax(0,1fr)"; }).join(" ");
    var max = opts.limit || 400;
    return '<div class="scroll-x"><div class="table" style="min-width:' + (opts.minWidth || 620) + 'px"><div class="trow head" style="' + tpl + '">' +
      cols.map(function (c, i) {
        var on = st.sort === i ? (st.dir > 0 ? " ▲" : " ▼") : "";
        return c.sort ? '<button class="th" data-act="sort" data-k="' + i + '">' + e(c.label) + on + "</button>" : "<span>" + e(c.label) + "</span>";
      }).join("") + "</div>" +
      rows.slice(0, max).map(function (r) {
        return '<div class="trow' + (opts.rowCls ? " " + opts.rowCls(r) : "") + '" style="' + tpl + '">' + cols.map(function (c) { return "<span" + (c.cls ? ' class="' + c.cls + '"' : "") + ">" + c.cell(r) + "</span>"; }).join("") + "</div>";
      }).join("") + "</div></div>" +
      (rows.length > max ? '<p class="mono tiny dim">showing ' + max + " of " + rows.length + "</p>" : "");
  };
  C.sortState = function (st, k) {   // toggle helper for data-act="sort"
    k = +k; if (st.sort === k) st.dir = -(st.dir || -1); else { st.sort = k; st.dir = -1; }
  };
  C.select = function (act, label, options, value) {
    return '<label class="fld"><span>' + e(label) + '</span><select data-act="' + e(act) + '">' + options.map(function (o) {
      var v = Array.isArray(o) ? o[0] : o, t = Array.isArray(o) ? o[1] : o;
      return '<option value="' + e(v) + '"' + (String(v) === String(value) ? " selected" : "") + ">" + e(t) + "</option>";
    }).join("") + "</select></label>";
  };
  C.search = function (act, placeholder, value) {
    return '<label class="fld grow"><span class="sr">' + e(placeholder) + '</span><input type="search" data-act="' + e(act) + '" placeholder="' + e(placeholder) + '" value="' + e(value || "") + '" autocomplete="off"></label>';
  };
  C.chip = function (act, label, on) { return '<button class="chipbtn' + (on ? " on" : "") + '" data-act="' + e(act) + '" aria-pressed="' + !!on + '">' + e(label) + "</button>"; };

  // ---------------------------------------------------------------- derived facts (shared by hubs)
  var F = {};
  F.session = function (D) { return (D.meta && D.meta.session) || {}; };
  F.live = function (D) { return !!(D.meta && D.meta.mode === "live" && D.meta.live_orders); };
  F.openPositions = function (D) { return (D.swing && D.swing.open) || []; };
  F.filter = function (D) {
    var m = D.meta || {}, mk = D.market || {}, rules = (D.swing && D.swing.rules) || {};
    var rank = mk.nifty_vol_rank, max = rules.vol_rank_max != null ? rules.vol_rank_max : null;
    var mode = m.market_filter || rules.market_filter || "on";
    return { rank: rank, max: max, mode: mode, off: mode === "off", shadow: mode === "shadow", on: mode === "on",
             closed: mode === "on" && U.num(rank) && U.num(max) && rank >= max, known: U.num(rank) };
  };
  // Worst case = what every stop filling now would cost; a trailed stop above entry adds nothing.
  F.worstCaseInr = function (open) {
    return open.reduce(function (m, p) { return m + Math.max(0, p.qty * (p.entry - p.stop_now)); }, 0);
  };
  F.eqClass = function (x) { return U.num(x) ? (x >= 0 ? "up" : "dn") : ""; };

  // ---------------------------------------------------------------- widget runtime
  var W = { defs: {}, views: {}, mounted: [] };
  W.widget = function (name, def) { W.defs[name] = def; };
  W.view = function (key, rows) { W.views[key] = rows; };
  function snapshot() { var D = {}; Object.keys(Store.src).forEach(function (k) { D[k] = Store.src[k].data; }); return D; }

  function mountWidget(name, host) {
    var def = W.defs[name]; if (!def) { host.innerHTML = C.empty("Missing widget " + name); return null; }
    var el = document.createElement("div");
    el.className = def.bare ? "w-bare" : "panel" + (def.shadow === false ? "" : " shadow") + (def.cls ? " " + def.cls : "");
    el.dataset.w = name;
    var body = el;
    if (def.title && !def.bare) {
      el.innerHTML = '<div class="ph"><h2>' + e(def.title) + '</h2><span class="mono dim small ph-r"></span></div><div class="w-body"></div>';
      body = el.querySelector(".w-body");
    }
    host.appendChild(el);
    var inst = { name: name, def: def, el: el, body: body, s: {}, timers: [], unsub: [], pending: false };
    inst.ctx = {
      s: inst.s, el: el, body: body,
      right: function (t) { var r = el.querySelector(".ph-r"); if (r) r.textContent = t || ""; },
      every: function (fn, ms) { inst.timers.push(setInterval(fn, ms)); },
      render: function () { schedule(inst); },
      D: snapshot
    };
    if (def.mount) def.mount(body, inst.ctx);
    (def.uses || []).forEach(function (k) { inst.unsub.push(Store.use(k, function () { schedule(inst); })); });
    if (!(def.uses || []).length) schedule(inst);
    return inst;
  }
  function schedule(inst) {
    if (inst.pending || inst.dead) return;
    inst.pending = true;
    requestAnimationFrame(function () {
      inst.pending = false; if (inst.dead) return;
      try { inst.def.render(inst.body, snapshot(), inst.ctx); }
      catch (err) { inst.body.innerHTML = C.empty("This panel failed to draw: " + err.message); if (window.console) console.error(err); }
    });
  }
  function unmountAll() {
    W.mounted.forEach(function (inst) {
      inst.dead = true; inst.unsub.forEach(function (u) { u(); }); inst.timers.forEach(clearInterval);
      if (inst.def.unmount) inst.def.unmount(inst.body, inst.ctx);
    });
    W.mounted = [];
  }
  /* A view is rows of cells. A cell is "name", {w: name, size: "grow"|"side"|"full"} or
     {stack: [cells], size}. */
  function buildView(rows, host) {
    rows.forEach(function (row) {
      var r = document.createElement("div"); r.className = "row"; host.appendChild(r);
      row.forEach(function (cell) { buildCell(cell, r, row.length === 1); });
    });
  }
  function buildCell(cell, parent, alone) {
    if (typeof cell === "string") cell = { w: cell };
    var box = document.createElement("div");
    box.className = "cell " + (cell.size || (alone ? "full" : "grow"));
    parent.appendChild(box);
    if (cell.stack) cell.stack.forEach(function (c) { buildCell(c, box, true); });
    else { var inst = mountWidget(cell.w, box); if (inst) W.mounted.push(inst); }
  }
  // Delegated events: any [data-act] inside a widget calls def.on[act](body, event, target, ctx).
  function delegate(type) {
    document.addEventListener(type, function (ev) {
      var t = ev.target.closest && ev.target.closest("[data-act]"); if (!t) return;
      if (type === "click" && (t.tagName === "SELECT" || t.tagName === "INPUT")) return;
      var host = t.closest("[data-w]"); if (!host) return;
      var inst = W.mounted.filter(function (i) { return i.el === host; })[0];
      var fn = inst && inst.def.on && inst.def.on[t.dataset.act];
      if (fn) { if (type === "click") ev.preventDefault(); fn(inst.body, ev, t, inst.ctx); }
    });
  }
  ["click", "input", "change"].forEach(delegate);

  // ---------------------------------------------------------------- shell
  var Shell = { hub: null, tab: null, loaded: {} };
  function loadHub(id) {
    if (Shell.loaded[id]) return Shell.loaded[id];
    Shell.loaded[id] = new Promise(function (ok, fail) {
      var s = document.createElement("script");
      s.src = ASSETS["hubs/" + id + ".js"] || "portal/static/hubs/" + id + ".js";
      s.onload = ok; s.onerror = function () { Shell.loaded[id] = null; fail(new Error("could not load " + id)); };
      document.head.appendChild(s);
    });
    return Shell.loaded[id];
  }
  function drawNav(h, t) {
    U.$("#hubTabs").innerHTML = Nav.NAV.map(function (x, i) {
      return '<a class="tab' + (x === h ? " on" : "") + '"' + (x === h ? ' aria-current="page"' : "") + ' href="' + Nav.href(x, x.tabs[0]) + '">0' + (i + 1) + " " + e(x.label.toUpperCase()) + "</a>";
    }).join("");
    // a hub with one page needs no second row of tabs
    U.$("#subTabs").hidden = h.tabs.length < 2;
    U.$("#subTabs").innerHTML = h.tabs.map(function (x) {
      return '<a class="sub' + (x === t ? " on" : "") + '"' + (x === t ? ' aria-current="page"' : "") + ' href="' + e(Nav.href(h, x)) + '">' + e(x.label) + "</a>";
    }).join("");
    var word = h.label.toUpperCase();
    U.$("#logoWord").textContent = word; U.$("#logoWord").setAttribute("data-text", word);
    document.title = "NSE Engine · " + h.label + (t !== h.tabs[0] ? " · " + t.label : "");
  }
  function scrollToSection(name) {
    var el = name && document.querySelector('[data-w="' + name + '"]');
    if (el && el.scrollIntoView) { el.scrollIntoView({ behavior: U.reduced ? "auto" : "smooth", block: "start" }); return true; }
    return false;
  }
  function route() {
    var loc = Nav.locate(location.hash);
    if (!loc) loc = { hub: Nav.NAV[0], tab: Nav.NAV[0].tabs[0], native: true, known: false };
    if (!loc.known) {                     // old crypto-style address or non-canonical form → the page that holds it
      Shell.section = loc.section || null;
      var to = Nav.href(loc.hub, loc.tab);
      if (location.hash !== to) { history.replaceState({}, "", location.pathname + location.search + to); }
    }
    var h = loc.hub, t = loc.tab;
    drawNav(h, t);
    if (Shell.hub === h.id && Shell.tab === t.id) { if (Shell.section) { scrollToSection(Shell.section); Shell.section = null; } return; }
    Shell.hub = h.id; Shell.tab = t.id;
    unmountAll();
    var host = U.$("#view"); host.innerHTML = C.loading();
    loadHub(h.id).then(function () {
      if (Shell.hub !== h.id || Shell.tab !== t.id) return;
      host.innerHTML = "";
      var rows = W.views[h.id + "/" + t.id];
      if (!rows) { host.innerHTML = C.empty("This view is not built yet."); return; }
      buildView(rows, host);
      window.scrollTo(0, 0);
      if (Shell.section) { var s = Shell.section; Shell.section = null; setTimeout(function () { scrollToSection(s); }, 60); }
    }).catch(function (err) { host.innerHTML = C.empty("Could not load this hub: " + err.message); });
  }
  window.addEventListener("hashchange", route);

  // status strip + ticker + toast: shell-level, always subscribed
  function drawStrip() {
    var D = snapshot(), g = F.filter(D), open = F.openPositions(D), m = D.meta || {};
    var gate = U.$("#stripGate");
    gate.textContent = !D.meta ? "FILTER …" : g.shadow ? "FILTER SHADOW" : g.off ? "FILTER OFF"
      : !g.known ? "FILTER · NO READING YET" : g.closed ? "FILTER CLOSED" : "FILTER OPEN";
    gate.classList.toggle("closed", g.closed);
    U.$("#stripOpen").textContent = "OPEN POSITIONS " + (D.swing ? open.length : "…");
    var cap = m.capital_inr, worst = F.worstCaseInr(open);
    U.$("#stripRisk").textContent = !D.swing || !U.num(cap) || cap <= 0 ? "WORST CASE …"
      : worst <= 0 ? "WORST CASE 0%" + (open.length ? " · PROFIT LOCKED" : "")
      : "WORST CASE −" + (100 * worst / cap).toFixed(1) + "% CAPITAL";
    var q = (D.quotes && D.quotes.quotes) || [];
    U.$("#stripFeed").textContent = !D.quotes ? "FEED …" : q.length ? "FEED " + q.length + " QUOTES · " + U.ago(D.quotes.ts_ms) : "FEED · NO QUOTES YET";
    U.$("#stripMode").textContent = !D.meta ? "PAPER ONLY"
      : F.live(D) ? (m.kill_switch ? "LIVE ₹ · KILL SWITCH ON" : "LIVE ₹ ORDERS ON")
      : "LIVE ORDERS OFF · PAPER ONLY" + (m.kill_switch ? " · KILL SWITCH ON" : "");
    var s = F.session(D);
    U.$("#sessChip").textContent = s.label || s.state || "—";
  }
  var tapeKey = "";
  function drawTape() {
    var q = (Store.get("quotes") || {}).quotes || [], key = q.map(function (c) { return c.symbol; }).join();
    var track = U.$("#tape");
    if (!q.length) { if (tapeKey) { tapeKey = ""; track.innerHTML = '<span class="dim">no quotes yet</span>'; } return; }
    if (key !== tapeKey) {
      tapeKey = key;
      var html = q.map(function (c) { return '<span data-t="' + e(c.symbol) + '"><b>' + e(c.symbol) + "</b><em></em><b></b></span>"; }).join("");
      track.innerHTML = html + html;
    }
    track.querySelectorAll("[data-t]").forEach(function (s) {
      var c = null; for (var i = 0; i < q.length; i++) if (q[i].symbol === s.dataset.t) c = q[i];
      if (!c) return;
      s.children[1].textContent = U.px(c.ltp);
      s.children[2].textContent = U.num(c.chg_pct) ? (c.chg_pct >= 0 ? "▲ " : "▼ ") + U.pct(c.chg_pct) : "—";
    });
  }
  var seen = null;
  function watchSignals() {
    var list = (Store.get("signals") || {}).rows || [];
    if (seen && list.length && !seen[list[0].id]) toast(list[0]);
    seen = {}; list.forEach(function (x) { seen[x.id] = 1; });
  }
  function toast(s) {
    var t = U.$("#toast"), taken = s.decision === "taken";
    t.className = "toast" + (taken ? "" : s.decision === "skipped" ? " skip" : " neutral");
    t.innerHTML = "<small>" + (taken ? "SIGNAL TAKEN" : e(String(s.decision || "signal").toUpperCase())) + "</small><b>" + e(s.symbol + " " + U.sideName(s.side).toUpperCase() + " · " + U.name(s.strategy)) + "</b>";
    t.hidden = false; t.style.animation = "none"; void t.offsetWidth; t.style.animation = "";
    clearTimeout(toast.h); toast.h = setTimeout(function () { t.hidden = true; }, 3200);
  }
  function setPalette(p) {
    document.documentElement.setAttribute("data-palette", p);
    try { localStorage.setItem("nse-palette", p); } catch (err) { /* private mode */ }
    document.querySelectorAll(".sw").forEach(function (b) { var on = b.dataset.p === p; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
  }
  document.addEventListener("click", function (ev) { var sw = ev.target.closest && ev.target.closest(".sw"); if (sw) setPalette(sw.dataset.p); });
  function tickClock() { U.$("#clock").textContent = U.hms(Date.now()); }

  window.UI = { U: U, C: C, F: F, Net: Net, Store: Store, widget: W.widget, view: W.view, toast: toast, _W: W };

  // start
  setPalette(document.documentElement.getAttribute("data-palette") || "sage");
  tickClock(); setInterval(tickClock, 1000);
  Store.use("quotes", function () { drawStrip(); drawTape(); });
  Store.use("swing", drawStrip);
  Store.use("meta", drawStrip);
  Store.use("market", drawStrip);
  Store.use("signals", watchSignals);
  route();
})();
