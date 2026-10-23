/* NSE portal nav — same hub shape as crypto (Command / Book / Lab / System). */
(function () {
  "use strict";
  var NAV = [
    { id: "command", label: "Command", tabs: [
      { id: "overview", label: "Overview" },
      { id: "watchlist", label: "Watchlist" },
      { id: "pipeline", label: "Pipeline" }
    ]},
    { id: "book", label: "Book", tabs: [
      { id: "paper", label: "Paper" },
      { id: "books", label: "A / B books" },
      { id: "live", label: "Live ₹" }
    ]},
    { id: "lab", label: "Lab", tabs: [
      { id: "strategies", label: "Strategies" },
      { id: "trials", label: "Trials" }
    ]},
    { id: "system", label: "System", tabs: [
      { id: "health", label: "Health" },
      { id: "data", label: "Data" },
      { id: "keys", label: "Keys", url: "keys" },
      { id: "golive", label: "Go-live" }
    ]}
  ];

  function hub(id) {
    for (var i = 0; i < NAV.length; i++) if (NAV[i].id === id) return NAV[i];
    return null;
  }
  function tab(h, id) {
    if (!h) return null;
    for (var i = 0; i < h.tabs.length; i++) if (h.tabs[i].id === id) return h.tabs[i];
    return null;
  }
  function href(h, t) {
    if (t.url) return t.url;
    return t === h.tabs[0] ? "#/" + h.id : "#/" + h.id + "/" + t.id;
  }
  function locate(hash) {
    var path = (hash || "#/command").replace(/^#/, "") || "/command";
    var parts = path.split("/").filter(Boolean);
    var h = hub(parts[0] || "command") || hub("command");
    var t = parts[1] ? tab(h, parts[1]) : h.tabs[0];
    return { hub: h, tab: t || h.tabs[0] };
  }

  window.PortalNav = { NAV: NAV, hub: hub, tab: tab, href: href, locate: locate };
})();
