"""V5-1: the portal shell loads at /nse/, assets are versioned, four palettes, hash navigation."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.settings import reset_settings_cache
from web import portal_shell
from web.app import create_app

PORTAL = portal_shell.PORTAL_DIR
NODE = shutil.which("node")


@pytest.fixture
async def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_SECRET", "unit-test-session-secret")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_settings_cache()
    cli = TestClient(TestServer(create_app()))
    await cli.start_server()
    yield cli
    await cli.close()


@pytest.mark.parametrize("path", ["/", "/nse/", "/command/anything", "/nse/book/signals"])
async def test_shell_serves_at_root_and_under_nse(client, path):
    resp = await client.get(path)
    assert resp.status == 200
    body = await resp.text()
    assert 'id="view"' in body
    assert '<base href="/nse/">' in body
    assert "{{" not in body  # every placeholder filled
    assert re.search(r"portal/static/core\.js\?v=[0-9a-f]{10}", body)
    assert re.search(r"portal/static/portal\.css\?v=[0-9a-f]{10}", body)
    assert "PAPER ONLY" in body


async def test_bare_nse_redirects_to_trailing_slash(client):
    resp = await client.get("/nse", allow_redirects=False)
    assert resp.status == 302
    assert resp.headers["Location"] == "/nse/"


async def test_assets_are_a_fixed_list_with_versioned_caching(client):
    names = portal_shell.assets()
    assert {"core.js", "nav.js", "portal.css", "chrome.js", "chrome.css"} <= set(names)
    for name, ctype in names.items():
        digest = portal_shell.read_asset(name)[1]
        resp = await client.get(f"/portal/static/{name}?v={digest}")
        assert resp.status == 200, name
        assert resp.headers["Content-Type"].startswith(ctype.split(";")[0])
        assert "immutable" in resp.headers["Cache-Control"]
        stale = await client.get(f"/portal/static/{name}?v=old")
        assert stale.headers["Cache-Control"] == "no-cache"
    for bad in ("portal.html", "..%2Fportal_shell.py", "nope.js", "hubs/../portal.html", "hubs/nope.js"):
        assert (await client.get(f"/portal/static/{bad}")).status == 404, bad


async def test_assets_also_reachable_under_the_base_path(client):
    digest = portal_shell.read_asset("core.js")[1]
    resp = await client.get(f"/nse/portal/static/core.js?v={digest}")
    assert resp.status == 200
    assert "immutable" in resp.headers["Cache-Control"]  # the ?v= query survives the prefix strip


async def test_api_is_reachable_under_the_base_path_and_typos_are_404(client):
    assert (await client.get("/nse/api/health")).status == 200
    assert (await client.get("/api/not-an-endpoint")).status == 404
    assert (await client.get("/nse/api/not-an-endpoint")).status == 404
    assert (await client.post("/nse/api/login", json={})).status in (400, 401, 503)  # routed, not a 404/405


async def test_keys_page_carries_the_portal_header(client):
    body = await (await client.get("/keys")).text()
    assert "portal/static/chrome.js" in body
    assert "portal/static/nav.js" in body


def test_four_palettes_in_html_and_css_and_they_persist():
    html = (PORTAL / "portal.html").read_text()
    css = (PORTAL / "portal.css").read_text()
    core = (PORTAL / "core.js").read_text()
    chrome = (PORTAL / "chrome.js").read_text()
    for palette in ("sage", "champagne", "ice", "lime"):
        assert f'data-p="{palette}"' in html
        assert f'data-palette="{palette}"' in css
        assert f'["{palette}"' in chrome
    # the palette is restored before first paint, saved on click, under one key
    assert 'localStorage.getItem("nse-palette")' in html
    assert 'localStorage.setItem("nse-palette"' in core
    assert 'localStorage.setItem("nse-palette"' in chrome
    assert 'data-palette="sage"' in html  # default: Sage & Lilac


def test_shell_has_the_hooks_core_js_draws_into():
    html = (PORTAL / "portal.html").read_text()
    core = (PORTAL / "core.js").read_text()
    for hook in re.findall(r'U\.\$\("#(\w+)"\)', core):
        assert f'id="{hook}"' in html, hook
    assert "<nav" in html and 'id="hubTabs"' in html and 'id="subTabs"' in html


def test_prefers_reduced_motion_is_honoured_in_css():
    css = (PORTAL / "portal.css").read_text()
    assert "prefers-reduced-motion: reduce" in css
    assert "animation-duration:.001s" in css.replace(" ", "")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_nav_is_hash_based_and_old_crypto_addresses_redirect():
    script = """
    global.window = {};
    require(process.argv[1]);
    const N = window.PortalNav;
    const out = {};
    const pairs = [
      "#/command", "#/command/today", "#/book/paper", "#/book/signals", "#/evidence", "#/system", "#/system/settings",
      "#/command/signals", "#/book/swing", "#/book/live", "#/book/guard", "#/system/golive", "#/system/keys",
      "#/evidence/accuracy", "#/nonsense", "", "#/book"
    ];
    for (const p of pairs) {
      const l = N.locate(p);
      out[p] = l && { hub: l.hub.id, tab: l.tab.id, known: l.known, section: l.section || null,
                      to: N.href(l.hub, l.tab) };
    }
    out.hubs = N.NAV.map(h => h.id);
    out.pages = N.NAV.map(h => h.tabs.map(t => t.id));
    console.log(JSON.stringify(out));
    """
    res = subprocess.run([NODE, "-e", script, str(PORTAL / "nav.js")], capture_output=True, text=True, check=True)
    out = json.loads(res.stdout)
    assert out["hubs"] == ["command", "book", "evidence", "system"]
    assert out["pages"] == [["today", "mood", "watchlist"], ["paper", "signals"], ["evidence"], ["health", "settings"]]
    # canonical hash addresses are recognised as they are
    assert out["#/command"]["known"] and out["#/command"]["tab"] == "today"
    assert out["#/book/signals"]["known"] and out["#/book/signals"]["to"] == "#/book/signals"
    assert out["#/system/settings"]["known"]
    # non-canonical forms and retired crypto addresses redirect to the page (and section) that holds them
    assert out["#/book/paper"] == {"hub": "book", "tab": "paper", "known": False, "section": None, "to": "#/book"}
    assert out["#/command/signals"]["to"] == "#/book/signals"
    assert out["#/book/swing"]["to"] == "#/book"
    assert out["#/book/live"]["section"] == "live"
    assert out["#/book/guard"]["to"] == "#/command" and out["#/book/guard"]["section"] == "guard"
    assert out["#/system/golive"]["to"] == "#/system" and out["#/system/golive"]["section"] == "golive"
    assert out["#/system/keys"]["to"] == "#/system/settings" and out["#/system/keys"]["section"] == "keys"
    assert out["#/evidence/accuracy"]["to"] == "#/evidence"
    # unknown pages inside a known hub fall back to the hub's first page; unknown hubs return null
    assert out["#/nonsense"] is None
    assert out[""]["to"] == "#/command" and not out[""]["known"]
