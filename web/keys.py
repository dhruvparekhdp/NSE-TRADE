"""Phone-friendly /keys page — encrypted Postgres store (crypto pattern)."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from config import secret_box
from config.key_fields import KEY_FIELDS
from config.secrets_loader import clear_key, save_key
from config.settings import get_settings
from web.auth import require_admin as _require_admin

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
</main>
<script>
async function api(path, body){
  const opts = body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {};
  const r = await fetch(path, opts);
  if(r.status===401){ document.getElementById('login').hidden=false; document.getElementById('keys').hidden=true; throw new Error('login'); }
  return r.json();
}
document.getElementById('login-btn').onclick = async ()=>{
  const password = document.getElementById('pw').value;
  const r = await fetch('api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
  if(!r.ok){ document.getElementById('login-err').textContent='bad password'; return; }
  document.getElementById('login').hidden=true;
  await render();
};
async function render(){
  const data = await api('api/keys');
  const root = document.getElementById('keys');
  root.hidden=false; root.innerHTML='';
  for(const row of data.rows){
    const el = document.createElement('div'); el.className='key-card';
    el.innerHTML = `<label>${row.label}</label><div class="help">${row.help}</div>
      <div class="where">${row.where}${row.hint?(' · '+row.hint):''}</div>
      <input data-key="${row.key}" type="${row.kind==='secret'?'password':'text'}" placeholder="${row.is_set?'•••• (leave blank to keep)':''}" />
      <div class="row">
        <button data-act="save" data-key="${row.key}">Save</button>
        <button class="danger" data-act="clear" data-key="${row.key}">Clear</button>
      </div>`;
    root.appendChild(el);
  }
  root.onclick = async (ev)=>{
    const btn = ev.target.closest('button'); if(!btn) return;
    const key = btn.dataset.key; const act = btn.dataset.act;
    if(act==='save'){
      const input = root.querySelector(`input[data-key="${key}"]`);
      const value = input.value;
      if(!value){ alert('type a value (blank keeps existing)'); return; }
      await api('api/keys/save',{key,value}); input.value=''; await render();
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
        hint = ("…" + live[-4:]) if (f.kind == "secret" and len(live) >= 8) else ""
        rows.append(
            {
                "key": f.key,
                "label": f.label,
                "help": f.help,
                "kind": f.kind,
                "where": where,
                "is_set": bool(live),
                "hint": hint,
            }
        )
    return rows


async def handle_keys_page(_request: web.Request) -> web.Response:
    return web.Response(text=PAGE, content_type="text/html")


async def handle_keys_api(request: web.Request) -> web.Response:
    _require_admin(request)
    return web.json_response(
        {"rows": status_rows(), "encryption": secret_box.available(), "master_key": bool(secret_box.available())}
    )


async def handle_keys_save(request: web.Request) -> web.Response:
    _require_admin(request)
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
    data = await request.json()
    key = data.get("key") or ""
    try:
        clear_key(key)
    except KeyError:
        raise web.HTTPBadRequest(text="unknown key") from None
    return web.json_response({"ok": True})


def register_keys_routes(app: web.Application) -> None:
    app.router.add_get("/keys", handle_keys_page)
    app.router.add_get("/api/keys", handle_keys_api)
    app.router.add_post("/api/keys/save", handle_keys_save)
    app.router.add_post("/api/keys/clear", handle_keys_clear)
