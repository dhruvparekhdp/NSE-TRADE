/* The one navigation map for the NSE portal (PLAN_V2 §8). The portal shell (core.js) and the
   server-rendered tool pages (chrome.js, e.g. /keys) both draw their header from this.

   Routing is by URL hash (#/book/signals) because the portal is served under /nse/.
   Seven pages, four hubs. Pages that used to be separate in the crypto portal are sections of these
   pages now; their old addresses are `aliases` and redirect to the page that holds them.
   An alias is "/hub/tab" or ["/hub/tab", "widget"] when it should scroll to a section. */
(function () {
  "use strict";

  var NAV = [
    { id: "command", label: "Command", tabs: [
      { id: "today", label: "Today", native: true,
        aliases: ["/command/overview", ["/book/guard", "guard"], ["/command/guard", "guard"]] },
      { id: "mood", label: "Market mood", native: true,
        aliases: ["/command/opening", "/command/sentiment", "/command/market"] }
    ] },
    { id: "book", label: "Book", tabs: [
      { id: "paper", label: "Paper book", native: true,
        aliases: ["/book/swing", ["/book/cycle", "cycle"], ["/book/live", "live"], "/book/intraday"] },
      { id: "signals", label: "Signals", native: true,
        aliases: ["/command/signals", "/book/history", "/evidence/history", "/book/shadow"] }
    ] },
    { id: "evidence", label: "Evidence", tabs: [
      { id: "evidence", label: "Evidence", native: true,
        aliases: ["/evidence/strategies", "/evidence/accuracy", "/evidence/research", "/evidence/trials", "/evidence/lab"] }
    ] },
    { id: "system", label: "System", tabs: [
      { id: "health", label: "Health", native: true,
        aliases: [["/system/golive", "golive"], ["/system/data", "data"], "/system/diagnostics", "/system/jobs"] },
      { id: "settings", label: "Settings", native: true,
        aliases: [["/system/keys", "keys"], ["/system/watchlist", "universe"], "/command/watchlist", "/system/api", "/system/ai"] }
    ] }
  ];

  function hub(id) { for (var i = 0; i < NAV.length; i++) if (NAV[i].id === id) return NAV[i]; return null; }
  function tab(h, id) { if (!h) return null; for (var i = 0; i < h.tabs.length; i++) if (h.tabs[i].id === id) return h.tabs[i]; return null; }
  // The first page of a hub lives at #/<hub>; the others at #/<hub>/<page>.
  function href(h, t) { return t === h.tabs[0] ? "#/" + h.id : "#/" + h.id + "/" + t.id; }
  function norm(path) { return "/" + String(path || "").replace(/^#/, "").split("/").filter(Boolean).join("/"); }

  function viaAlias(path) {
    for (var i = 0; i < NAV.length; i++) {
      for (var j = 0; j < NAV[i].tabs.length; j++) {
        var al = NAV[i].tabs[j].aliases || [];
        for (var k = 0; k < al.length; k++) {
          var a = Array.isArray(al[k]) ? al[k][0] : al[k];
          if (a === path) return { hub: NAV[i], tab: NAV[i].tabs[j], native: true, known: false, alias: true, section: Array.isArray(al[k]) ? al[k][1] : null };
        }
      }
    }
    return null;
  }

  // Which hub/page an address (the part after '#') belongs to. `known` is false when the address
  // is an alias or not the page's canonical form, so the shell rewrites the hash to Nav.href().
  function locate(hash) {
    var path = norm(hash);
    if (path === "/") return { hub: NAV[0], tab: NAV[0].tabs[0], native: true, known: false };
    var parts = path.split("/").filter(Boolean), h = hub(parts[0]);
    var al = viaAlias(path);
    if (al) return al;
    if (!h) return null;
    var t = parts[1] ? tab(h, parts[1]) : h.tabs[0];
    if (!t) return { hub: h, tab: h.tabs[0], native: true, known: false };
    var canon = href(h, t).slice(1);
    return { hub: h, tab: t, native: !!t.native, known: path === canon };
  }

  window.PortalNav = { NAV: NAV, hub: hub, tab: tab, href: href, locate: locate };
})();
