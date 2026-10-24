from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import vault

app = FastAPI(title="shad.bpda.site")

COOKIE = "shad_session"
PROVIDERS = ["elevenlabs"]


def _authed(request: Request) -> bool:
    return auth.check_session(request.cookies.get(COOKIE))


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if not _authed(request):
        return LOGIN_HTML
    return DASHBOARD_HTML


@app.post("/login")
def login(request: Request, password: str = Form(...)):
    if not auth.verify_password(password):
        return HTMLResponse(LOGIN_HTML.replace("<!--ERR-->", '<p class="err">Wrong password.</p>'), status_code=401)
    token = auth.create_session()
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE, token, httponly=True, secure=True, samesite="lax")
    return resp


@app.post("/logout")
def logout(request: Request):
    auth.destroy_session(request.cookies.get(COOKIE))
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


def _require(request: Request):
    if not _authed(request):
        raise HTTPException(401, "not logged in")


@app.get("/api/keys")
def api_list_keys(request: Request, provider: str = "elevenlabs"):
    _require(request)
    if provider not in PROVIDERS:
        raise HTTPException(400, "unknown provider")
    return vault.list_keys(provider)


@app.post("/api/keys")
async def api_add_key(request: Request):
    _require(request)
    body = await request.json()
    provider = body.get("provider", "elevenlabs")
    label = (body.get("label") or "").strip()
    value = (body.get("value") or "").strip()
    if provider not in PROVIDERS or not label or not value:
        raise HTTPException(400, "provider, label and value are required")
    kid = vault.add_key(provider, label, value)
    return {"id": kid}


@app.put("/api/keys/{kid}")
async def api_edit_key(request: Request, kid: str):
    _require(request)
    body = await request.json()
    vault.edit_key(kid, label=body.get("label"), value=body.get("value") or None)
    return {"ok": True}


@app.delete("/api/keys/{kid}")
def api_delete_key(request: Request, kid: str):
    _require(request)
    vault.delete_key(kid)
    return {"ok": True}


@app.post("/api/keys/{kid}/activate")
def api_activate_key(request: Request, kid: str):
    _require(request)
    try:
        return vault.activate_key(kid)
    except KeyError:
        raise HTTPException(404, "no such key")


LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>shad.bpda.site</title>
<style>body{font-family:system-ui;background:#0f1726;color:#e8eef7;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0}
form{background:#182238;padding:32px;border-radius:12px;width:280px}
input{width:100%;padding:10px;margin:8px 0;border-radius:6px;border:1px solid #2b3a55;
background:#0f1726;color:#e8eef7;box-sizing:border-box}
button{width:100%;padding:10px;border:0;border-radius:6px;background:#19c2d6;color:#04202a;
font-weight:600;cursor:pointer}
.err{color:#ff8787}h1{font-size:18px;margin:0 0 12px}</style></head><body>
<form method="post" action="/login">
<h1>shad.bpda.site</h1><!--ERR-->
<input type="password" name="password" placeholder="Master password" autofocus required>
<button type="submit">Login</button>
</form></body></html>"""

DASHBOARD_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>shad.bpda.site — vault</title>
<style>
body{font-family:system-ui;background:#0f1726;color:#e8eef7;margin:0;padding:24px}
h1{font-size:20px}
.card{background:#182238;border-radius:10px;padding:16px;margin:10px 0;display:flex;
justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.card.active{outline:2px solid #19c2d6}
.label{font-weight:600}
.tail{color:#8fa3c0;font-size:13px}
button{border:0;border-radius:6px;padding:8px 12px;cursor:pointer;font-weight:600}
.activate{background:#19c2d6;color:#04202a}
.danger{background:#39240f;color:#ffb787}
.ghost{background:transparent;color:#8fa3c0;border:1px solid #2b3a55}
input{padding:8px;border-radius:6px;border:1px solid #2b3a55;background:#0f1726;color:#e8eef7}
.addrow{display:flex;gap:8px;margin:16px 0;flex-wrap:wrap}
.pill{font-size:11px;padding:2px 8px;border-radius:10px;background:#0f1726;color:#19c2d6}
</style></head><body>
<h1>🔑 ElevenLabs Key Vault</h1>
<p style="color:#8fa3c0">Manual switch only — click Activate to make a key live. No rotation, no failover.</p>
<div class="addrow">
  <input id="label" placeholder="Label, e.g. Voice 1 - Brian">
  <input id="value" placeholder="API key" type="password" style="min-width:280px">
  <button class="activate" onclick="addKey()">+ Add key</button>
</div>
<div id="list"></div>
<form method="post" action="/logout" style="margin-top:24px"><button class="ghost">Log out</button></form>
<script>
async function load(){
  const r = await fetch('/api/keys'); const keys = await r.json();
  const el = document.getElementById('list');
  el.innerHTML = keys.length ? '' : '<p style="color:#8fa3c0">No keys yet.</p>';
  for (const k of keys){
    const div = document.createElement('div');
    div.className = 'card' + (k.active ? ' active' : '');
    div.innerHTML = `<div><span class="label">${k.label}</span> <span class="tail">…${k.tail}</span>
      ${k.active ? '<span class="pill">ACTIVE</span>' : ''}</div>
      <div>
        ${k.active ? '' : `<button class="activate" onclick="activate('${k.id}')">Activate</button>`}
        <button class="danger" onclick="del('${k.id}')">Delete</button>
      </div>`;
    el.appendChild(div);
  }
}
async function addKey(){
  const label = document.getElementById('label').value.trim();
  const value = document.getElementById('value').value.trim();
  if(!label || !value) return;
  await fetch('/api/keys', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({provider:'elevenlabs', label, value})});
  document.getElementById('label').value=''; document.getElementById('value').value='';
  load();
}
async function activate(id){ await fetch(`/api/keys/${id}/activate`, {method:'POST'}); load(); }
async function del(id){ if(!confirm('Delete this key?')) return;
  await fetch(`/api/keys/${id}`, {method:'DELETE'}); load(); }
load();
</script></body></html>"""
