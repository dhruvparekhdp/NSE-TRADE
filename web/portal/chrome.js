/* Portal chrome for the server-rendered tool pages (today only /keys, reached from Settings).
   Draws the same header as the portal from nav.js so the page is never a dead end, and applies
   the shared palette. Ported from the crypto engine's chrome.js (PLAN_V2 V5-1): links are hash
   routes under <base href="/nse/">. */
(function () {
  "use strict";
  var Nav = window.PortalNav;
  if (!Nav) return;

  var root = document.documentElement;
  root.setAttribute("data-theme", "brutal");
  try { root.setAttribute("data-palette", localStorage.getItem("nse-palette") || "sage"); } catch (e) { root.setAttribute("data-palette", "sage"); }

  function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var PALETTES = [["sage", "#A9D3B6", "#B9AAF2", "Sage & Lilac"], ["champagne", "#E3C58D", "#6CC9AE", "Champagne & Teal"], ["ice", "#94C5F5", "#EDA982", "Ice & Peach"], ["lime", "#C6F432", "#9B8CFF", "Classic lime"]];

  // The tool pages live under System › Settings.
  function here() { var h = Nav.hub("system"); return { hub: h, tab: Nav.tab(h, "settings") }; }

  function draw() {
    var loc = here(), h = loc.hub, t = loc.tab;
    var bar = document.getElementById("pc-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "pc-bar"; bar.className = "pc-bar"; bar.setAttribute("role", "banner");
      document.body.insertBefore(bar, document.body.firstChild);
    }
    var pal = root.getAttribute("data-palette") || "sage";
    bar.innerHTML =
      '<div class="pc-row">' +
        '<a class="pc-logo" href="#/command"><span class="pc-logo-a">NSE/</span><span class="pc-logo-b">' + esc(h.label.toUpperCase()) + "</span></a>" +
        '<nav class="pc-tabs" aria-label="Hubs">' + Nav.NAV.map(function (x, i) {
          return '<a class="pc-tab' + (x === h ? " on" : "") + '"' + (x === h ? ' aria-current="true"' : "") + ' href="' + Nav.href(x, x.tabs[0]) + '">0' + (i + 1) + " " + esc(x.label.toUpperCase()) + "</a>";
        }).join("") + "</nav>" +
        '<div class="pc-right"><span class="pc-mode" id="pc-mode">PAPER ONLY</span><div class="pc-sw" role="group" aria-label="Colour theme">' + PALETTES.map(function (p) {
          return '<button type="button" class="pc-swb' + (p[0] === pal ? " on" : "") + '" data-p="' + p[0] + '" title="' + esc(p[3]) + '" aria-label="' + esc(p[3]) + ' theme" aria-pressed="' + (p[0] === pal) + '"><i style="background:' + p[1] + '"></i><i style="background:' + p[2] + '"></i></button>';
        }).join("") + "</div></div>" +
      "</div>" +
      '<nav class="pc-subs" aria-label="Pages in ' + esc(h.label) + '">' + h.tabs.map(function (x) {
        var on = x === t;
        return '<a class="pc-sub' + (on ? " on" : "") + '"' + (on ? ' aria-current="page"' : "") + ' href="' + esc(Nav.href(h, x)) + '">' + esc(x.label) + "</a>";
      }).join("") + "</nav>";
  }

  function setPalette(p) {
    root.setAttribute("data-palette", p);
    try { localStorage.setItem("nse-palette", p); } catch (e) { /* private mode */ }
    draw();
  }

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest(".pc-swb");
    if (b) setPalette(b.dataset.p);
  });

  function start() {
    root.classList.add("pc-on");
    draw();
    fetch("api/portal/meta", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (m) {
      var el = document.getElementById("pc-mode"); if (!el || !m) return;
      var live = m.mode === "live" && m.live_orders;
      el.textContent = live ? "LIVE ORDERS ON" : "PAPER ONLY";
      el.classList.toggle("live", !!live);
    }).catch(function () { /* the badge stays at its default */ });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
