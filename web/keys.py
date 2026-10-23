"""Phone-friendly /keys page — encrypted Postgres store (crypto pattern)."""

from __future__ import annotations

import time
from typing import Any

import bcrypt
from aiohttp import web

from config import secret_box
from config.key_display import fingerprint, first_diff_at, mask_value
from config.key_fields import KEY_FIELDS
from config.secrets_loader import clear_key, save_key
from config.settings import get_settings
from web.auth import require_admin as _require_admin
from web.secure_channel import is_secure_channel, require_secure_channel

_reveal_times: list[float] = []
_REVEAL_WINDOW_S = 600.0
_REVEAL_MAX = 5


def reset_reveal_rate_for_tests() -> None:
    _reveal_times.clear()

PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>NSE Keys</title>
<base href="/nse/"/>
<link rel="stylesheet" href="static/style.css"/>
<style>
.keys-list{display:flex;flex-direction:column;gap:1rem;margin-top:1rem}
.key-card{background:var(--card);padding:1rem;border-radius:8px}
.key-card label{display:block;font-weight:600;margin-bottom:.25rem}
.key-card .help{color:var(--muted);font-size:.85rem;margin-bottom:.5rem}
.key-card .where{font-size:.8rem;color:#8ab4f8}
.key-card input{width:100%;padding:.6rem;border-radius:6px;border:1px solid #333;background:#0b1016;color:var(--fg)}
.key-card .row{display:flex;gap:.5rem;margin-top:.5rem;flex-wrap:wrap}
.key-card button{padding:.5rem .8rem;border:0;border-radius:6px;background:#2a5a8c;color:#fff;font-weight:600}
.key-card button.danger{background:#6b2a2a}
.login-box{max-width:20rem;margin:2rem auto;background:var(--card);padding:1rem;border-radius:8px}
</style></head>
<body>
<header class="banner paper">KEYS · DB encrypted</header>
<main>
  <p><a href="./#/system/keys" style="color:#8ab4f8">← Portal</a></p>
  <div id="login" class="login-box">
    <label>Admin password</label>
    <input id="pw" type="password" autocomplete="current-password"/>
    <button id="login-btn" style="margin-top:.5rem;width:100%;padding:.6rem;border:0;border-radius:6px;background:#1a5f3a;color:#fff">Log in</button>
    <p id="login-err" style="color:#f88"></p>
  </div>
  <div id="keys" class="keys-list" hidden></div>
  <p id="angel-tools" hidden style="margin-top:1.5rem">
    <button id="test-angel" style="padding:.6rem 1rem;border:0;border-radius:6px;background:#2a5a8c;color:#fff;font-weight:700">Test Angel (read-only)</button>
    <span id="angel-result" class="help" style="display:block;margin-top:.5rem;color:var(--muted)"></span>
  </p>
</main>
<script>
async function api(path, body){
  const opts = body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {};
  const r = await fetch(path, opts);
  if(r.status===401){ document.getElementById('login').hidden=false; document.getElementById('keys').hidden=true; throw new Error('login'); }
  if(r.status===429){ throw new Error('rate limited — wait 2 minutes'); }
  if(!r.ok){ throw new Error('HTTP '+r.status); }
  return r.json();
}
document.getElementById('login-btn').onclick = async ()=>{
  const password = document.getElementById('pw').value;
  const r = await fetch('api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
  if(!r.ok){ document.getElementById('login-err').textContent='bad password'; return; }
  document.getElementById('login').hidden=true;
  await render();
};
document.getElementById('test-angel').onclick = async ()=>{
  const el = document.getElementById('angel-result');
  el.textContent = 'testing…';
  try{
    const d = await api('api/keys/test-angel',{});
    el.textContent = d.ok
      ? ('OK · cash ₹'+(d.available_cash??'—')+' · holdings '+d.holdings_count+' · '+d.hint)
      : ('FAIL '+ (d.error_code||'') +' — '+ (d.hint||''));
  }catch(e){ el.textContent = String(e.message||e); }
};
async function render(){
  const data = await api('api/keys');
  const root = document.getElementById('keys');
  root.hidden=false; root.innerHTML='';
  document.getElementById('angel-tools').hidden=false;
  for(const row of data.rows){
    const el = document.createElement('div'); el.className='key-card';
    const fp = row.fingerprint ? (' · fp '+row.fingerprint) : '';
    const masked = row.masked ? (' · '+row.masked+' ('+row.length+')') : '';
    el.innerHTML = `<label>${row.label}</label><div class="help">${row.help}</div>
      <div class="where">${row.where}${masked}${fp}</div>
      <input data-key="${row.key}" type="${row.kind==='secret'?'password':'text'}" placeholder="${row.is_set?'•••• (leave blank to keep)':''}" />
      <div class="row">
        <button data-act="save" data-key="${row.key}">Save</button>
        <button data-act="compare" data-key="${row.key}">Compare</button>
        <button data-act="reveal" data-key="${row.key}">Reveal</button>
        <button class="danger" data-act="clear" data-key="${row.key}">Clear</button>
      </div>`;
    root.appendChild(el);
  }
  const secure = !!data.secure_channel;
  if(!secure){
    root.insertAdjacentHTML('afterbegin','<p class="help" style="color:#f88">Compare / Reveal / Save need HTTPS, localhost or Tailscale</p>');
  }
  root.onclick = async (ev)=>{
    const btn = ev.target.closest('button'); if(!btn) return;
    const key = btn.dataset.key; const act = btn.dataset.act;
    const input = root.querySelector(`input[data-key="${key}"]`);
    if(act==='save'){
      const value = input.value;
      if(!value){ alert('type a value (blank keeps existing)'); return; }
      await api('api/keys/save',{key,value}); input.value=''; await render();
    }
    if(act==='compare'){
      const value = input.value; if(!value){ alert('type a value to compare'); return; }
      const d = await api('api/keys/compare',{key,value});
      alert(d.match ? 'matches the saved value' : ('differs'+(d.first_diff_at!=null?(' at character '+(d.first_diff_at+1)):'')));
    }
    if(act==='reveal'){
      const password = prompt('Re-type admin password to reveal');
      if(!password) return;
      const d = await api('api/keys/reveal',{key,password});
      alert('Value (copied to field for 30s):\\n'+d.value);
      input.type='text'; input.value=d.value;
      setTimeout(()=>{ input.type='password'; input.value=''; }, 30000);
    }
    if(act==='clear'){ if(!confirm('Clear stored value?')) return; await api('api/keys/clear',{key}); await render(); }
  };
}
render().catch(()=>{});
</script>
</body></html>
"""


def _plain(settings, key: str) -> str:
    v = getattr(settings, key, None)
    if v is None:
        return ""
    return v.get_secret_value() if hasattr(v, "get_secret_value") else str(v)


def status_rows() -> list[dict[str, Any]]:
    from storage.pg import database_url, get_app_settings

    settings = get_settings()
    stored: dict = {}
    if database_url():
        try:
            stored = get_app_settings()
        except Exception:  # noqa: BLE001
            stored = {}
    rows = []
    for f in KEY_FIELDS:
        s = stored.get(f.key)
        live = _plain(settings, f.key)
        if secret_box.is_sealed(s):
            where = (
                "database (encrypted)"
                if secret_box.open_(s) is not None
                else "database (cannot decrypt)"
            )
        elif isinstance(s, str) and s:
            where = "database"
        elif live:
            where = ".env / process only"
        else:
            where = "not set"
        history: list = []
        if database_url() and live:
            try:
                from storage.pg import recent_settings_history

                history = recent_settings_history(f.key, limit=5)
            except Exception:  # noqa: BLE001
                history = []
        rows.append(
            {
                "key": f.key,
                "label": f.label,
                "help": f.help,
                "kind": f.kind,
                "where": where,
                "is_set": bool(live),
                "masked": mask_value(live, kind=f.kind, key=f.key) if live else "",
                "length": len(live) if live else 0,
                "fingerprint": fingerprint(live, key=f.key) if live else None,
                "saved_ms": None,
                "history": history,
            }
        )
    return rows


def _admin_password_ok(password: str) -> bool:
    settings = get_settings()
    if settings.portal_admin_hash:
        return bcrypt.checkpw(password.encode(), settings.portal_admin_hash.encode())
    plain = settings.admin_password.get_secret_value() if settings.admin_password else None
    return bool(plain) and password == plain


async def handle_keys_page(_request: web.Request) -> web.Response:
    return web.Response(text=PAGE, content_type="text/html")


async def handle_keys_api(request: web.Request) -> web.Response:
    _require_admin(request)
    return web.json_response(
        {
            "rows": status_rows(),
            "encryption": secret_box.available(),
            "master_key": bool(secret_box.available()),
            "secure_channel": is_secure_channel(request),
        }
    )


async def handle_keys_compare(request: web.Request) -> web.Response:
    _require_admin(request)
    require_secure_channel(request)
    data = await request.json()
    key = data.get("key") or ""
    value = data.get("value") or ""
    if key not in {f.key for f in KEY_FIELDS}:
        raise web.HTTPBadRequest(text="unknown key")
    live = _plain(get_settings(), key)
    match = live == value and bool(live)
    return web.json_response(
        {
            "match": match,
            "first_diff_at": None if match else first_diff_at(live, value),
        }
    )


async def handle_keys_reveal(request: web.Request) -> web.Response:
    _require_admin(request)
    require_secure_channel(request)
    now = time.monotonic()
    _reveal_times[:] = [t for t in _reveal_times if now - t < _REVEAL_WINDOW_S]
    if len(_reveal_times) >= _REVEAL_MAX:
        raise web.HTTPTooManyRequests(text="reveal rate limit (5 per 10 min)")
    data = await request.json()
    key = data.get("key") or ""
    password = data.get("password") or ""
    if key not in {f.key for f in KEY_FIELDS}:
        raise web.HTTPBadRequest(text="unknown key")
    if not _admin_password_ok(password):
        raise web.HTTPForbidden(text="bad password")
    live = _plain(get_settings(), key)
    if not live:
        raise web.HTTPNotFound(text="not set")
    _reveal_times.append(now)
    try:
        from storage.pg import audit_event, database_url

        if database_url():
            audit_event("key_revealed", key)
    except Exception:  # noqa: BLE001
        pass
    resp = web.json_response({"value": live})
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def handle_keys_save(request: web.Request) -> web.Response:
    _require_admin(request)
    require_secure_channel(request)
    data = await request.json()
    key = data.get("key") or ""
    value = data.get("value") or ""
    try:
        save_key(key, value)
    except KeyError:
        raise web.HTTPBadRequest(text="unknown key") from None
    return web.json_response({"ok": True})


async def handle_keys_clear(request: web.Request) -> web.Response:
    _require_admin(request)
    require_secure_channel(request)
    data = await request.json()
    key = data.get("key") or ""
    try:
        clear_key(key)
    except KeyError:
        raise web.HTTPBadRequest(text="unknown key") from None
    return web.json_response({"ok": True})


def register_keys_routes(app: web.Application) -> None:
    from web.test_angel import handle_test_angel

    app.router.add_get("/keys", handle_keys_page)
    app.router.add_get("/api/keys", handle_keys_api)
    app.router.add_post("/api/keys/save", handle_keys_save)
    app.router.add_post("/api/keys/clear", handle_keys_clear)
    app.router.add_post("/api/keys/compare", handle_keys_compare)
    app.router.add_post("/api/keys/reveal", handle_keys_reveal)
    app.router.add_post("/api/keys/test-angel", handle_test_angel)
