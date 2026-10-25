/* Evidence hub: pre-registered trials, gate results and research reports (PLAN_V2 §8). */
(function () {
  "use strict";
  var U = UI.U, C = UI.C, e = U.esc;

  UI.widget("ev-counters", {
    bare: true, uses: ["lab", "datahealth"],
    render: function (el, D) {
      var l = D.lab; if (!l) { el.innerHTML = C.state(D, "lab"); return; }
      var st = l.strategies || [], dh = (D.datahealth && D.datahealth.lake) || {};
      el.innerHTML = C.tiles([
        ["TRIALS SO FAR", String(l.trials_total || 0), "every lab run is counted"],
        ["PASSED THE GATE", String(st.filter(function (s) { return s.passed; }).length), "of " + st.length + " strategies"],
        ["BOOK B DATA", dh.first_date ? dh.first_date + " → " + dh.last_date : "none yet", dh.symbols ? dh.symbols + " symbols" : "bhavcopy backfill pending"],
        ["SYNTHETIC FILES", String(dh.synthetic_files || 0), dh.synthetic_files ? "results on synthetic data don't count" : ""]
      ]);
    }
  });
  function fmt(v) {
    if (v == null) return "—";
    if (typeof v === "number") return Math.abs(v) < 10 && v % 1 ? v.toFixed(3) : String(v);
    if (typeof v === "boolean") return v ? "✓" : "✗";
    if (Array.isArray(v)) return v.join(", ");
    return String(v);
  }
  UI.widget("ev-gates", {
    title: "GATE TABLE (n ≥ 100 per half · avg R ≥ +0.10 both halves · beats mirror and random · R > 0 at costs ×1.5)", uses: ["lab"],
    render: function (el, D) {
      var l = D.lab; if (!l) { el.innerHTML = C.state(D, "lab"); return; }
      el.innerHTML = C.table([
        { label: "STRATEGY", w: "150px", cell: function (s) { return "<b>" + e(s.id) + "</b>"; } },
        { label: "BOOK", w: "50px", cell: function (s) { return e(s.book); } },
        { label: "PREREG", w: "130px", cell: function (s) { return e(s.prereg_id || "—"); } },
        { label: "TRIALS", w: "60px", cell: function (s) { return e(s.trials); } },
        { label: "LAST REPORT", cell: function (s) {
          var r = s.last_report || {};
          var keys = ["n_first", "n_second", "avg_r_first", "avg_r_second", "avg_r_stress", "reasons"];
          var parts = keys.filter(function (k) { return r[k] != null; }).map(function (k) { return k.replace(/_/g, " ") + " " + fmt(r[k]); });
          return '<span class="mono tiny">' + e(parts.join(" · ") || "no run yet") + "</span>";
        } },
        { label: "VERDICT", w: "80px", cell: function (s) { return s.last_report && s.last_report.passed != null ? C.tag(s.last_report.passed ? "PASS" : "FAIL", s.last_report.passed ? "up" : "dn") : C.tag("not run"); } }
      ], l.strategies || [], { empty: "No trials recorded yet. They run once the bhavcopy history is backfilled (V3).", minWidth: 820 });
    }
  });
  UI.widget("ev-note", {
    title: "HOW TO READ THIS",
    render: function (el) {
      el.innerHTML = '<p class="small">A strategy may paper trade only after it passes the gate on real history in <b>both</b> halves ' +
        "(2012–2018 and 2019–2026), beats its mirror (the opposite trade) and random entries, and stays positive when costs are 1.5× higher. " +
        "Rules are pre-registered in <code>docs/PREREG.md</code> before any run; a rule changed after seeing results counts as a new, post-hoc trial.</p>";
    }
  });
  UI.view("evidence/evidence", [["ev-counters"], ["ev-gates"], ["ev-note"]]);
})();
