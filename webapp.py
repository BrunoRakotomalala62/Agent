#!/usr/bin/env python3
"""Agent Computer — portail web v2 (FastAPI) avec TERMINAL INTÉGRÉ.

Un seul port = tout : tableau de bord + terminal + fichiers.
Le terminal (xterm.js + pty) vit DANS la page → plus besoin de ttyd ni de
quitter le site pour coder.

Sécurité : si TERM_PASS est défini, le terminal demande le mot de passe
avant de s'ouvrir (jeton à durée limitée). Si TERM_PASS est vide → terminal
ouvert (mode dev uniquement !).

Usage :
    TERM_PASS=... uvicorn webapp:app --host 0.0.0.0 --port 3000
"""
import asyncio
import io
import json
import os
import pty
import secrets
import select
import signal
import socket
import struct
import subprocess
import time
import urllib.parse
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

ROOT = Path(__file__).parent
MACHINE = ROOT / "machine"
HOME_DIR = MACHINE / "home" / "agent"
VAR = ROOT / "var"
START = time.time()

TERM_PASS = os.environ.get("TERM_PASS", "").strip()
PORT = int(os.environ.get("PORT", "3000"))

app = FastAPI(title="Agent Computer", docs_url=None, redoc_url=None)
_tokens: dict[str, float] = {}  # jeton -> expiration


# ------------------------------------------------------------------ helpers

def uptime() -> str:
    s = int(time.time() - START)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}h{m:02d}min{sec:02d}s"


def service_ok() -> dict:
    return {
        "machine": socket.gethostname(),
        "status": "ACTIVE",
        "uptime": uptime(),
        "load": [round(float(x), 2) for x in open("/proc/loadavg").read().split()[:3]],
        "disk": disk_usage(),
        "opencode": os.system("command -v opencode >/dev/null 2>&1") == 0,
        "terminal": "intégré (xterm.js)",
        "terminal_protected": bool(TERM_PASS),
        "workspace": str(HOME_DIR),
    }


def disk_usage() -> dict:
    st = os.statvfs(MACHINE)
    return {
        "total_gb": round(st.f_blocks * st.f_frsize / 1e9, 1),
        "free_gb": round(st.f_bavail * st.f_frsize / 1e9, 1),
    }


def safe_path(rel: str) -> Path | None:
    base = HOME_DIR.resolve()
    target = (base / rel.lstrip("/")).resolve()
    if target == base or base in target.parents:
        return target
    return None


# ------------------------------------------------------------------ routes

@app.get("/health")
async def health():
    return service_ok()


@app.get("/api/files")
async def api_files(path: str = ""):
    target = safe_path(path)
    if not target or not target.is_dir():
        return JSONResponse({"error": "chemin refusé"}, status_code=400)
    out = []
    for name in sorted(os.listdir(target)):
        full = target / name
        st = full.stat()
        out.append({
            "name": name,
            "type": "dir" if full.is_dir() else "file",
            "size": st.st_size if full.is_file() else None,
            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
        })
    return out


@app.get("/raw")
async def raw(path: str = ""):
    target = safe_path(path)
    if not target or not target.is_file():
        return Response("fichier introuvable", status_code=404)
    data = target.read_bytes()[:300_000]
    page = (f"<meta charset='utf-8'><style>body{{background:#0a0d13;color:#d7dde8;"
            f"font:12.5px Consolas,monospace;padding:16px;white-space:pre-wrap;"
            f"word-break:break-all}}</style><!-- {path} -->").encode() + data
    return Response(page, media_type="text/html")


@app.get("/watchdog.log")
async def watchdog_log():
    for cand in (VAR / "log" / "watchdog.log", VAR / "watchdog.log"):
        if cand.exists():
            return Response(cand.read_text(errors="replace"), media_type="text/plain")
    return Response("pas encore de journal", status_code=404)


class LoginBody(BaseModel):
    password: str


@app.get("/api/term-required")
async def term_required():
    return {"required": bool(TERM_PASS)}


@app.post("/api/term-login")
async def term_login(body: LoginBody):
    if TERM_PASS and body.password != TERM_PASS:
        return JSONResponse({"error": "mot de passe incorrect"}, status_code=401)
    token = secrets.token_hex(16)
    _tokens[token] = time.time() + 15 * 60  # 15 min
    return {"token": token}


def _check_token(token: str) -> bool:
    exp = _tokens.get(token, 0)
    if time.time() > exp:
        _tokens.pop(token, None)
        return False
    return True


# ------------------------------------------------------------------ terminal

class PtyShell:
    """PTY bash branché sur une WebSocket FastAPI."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.master, slave = pty.openpty()
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["HOME"] = str(HOME_DIR)
        env["TERM"] = "xterm-256color"
        env["PS1"] = "agent@machine:\\w$ "
        self.proc = subprocess.Popen(
            ["bash", "-l"],
            stdin=slave, stdout=slave, stderr=slave,
            cwd=str(HOME_DIR), env=env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(slave)
        os.set_blocking(self.master, False)

    async def pump(self):
        loop = asyncio.get_event_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, self._read, 65536)
            except (OSError, ConnectionError):
                break
            if data is None:
                await asyncio.sleep(0.02)
                continue
            if not data:
                break
            try:
                await self.ws.send_text(data.decode("utf-8", "replace"))
            except Exception:
                break

    def _read(self, n: int):
        if not self.proc.poll() is None:
            try:
                return os.read(self.master, n)
            except OSError:
                return b""
        r, _, _ = select.select([self.master], [], [], 0.1)
        if not r:
            return None
        return os.read(self.master, n)

    def write(self, data: bytes):
        os.write(self.master, data)

    def resize(self, cols: int, rows: int):
        try:
            import fcntl
            import termios
            fcntl.ioctl(self.master, termios.TIOCSWINSZ,
                        struct.pack("HHHH", rows, cols, 0, 0))
        except Exception:
            pass

    def close(self):
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGHUP)
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            os.close(self.master)
        except Exception:
            pass


@app.websocket("/ws/term")
async def ws_term(ws: WebSocket):
    token = ws.query_params.get("token", "")
    if TERM_PASS and not _check_token(token):
        await ws.close(code=4001, reason="authentification requise")
        return
    await ws.accept()
    shell = PtyShell(ws)
    pump_task = asyncio.create_task(shell.pump())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                shell.write(raw.encode())
                continue
            if msg.get("type") == "resize":
                shell.resize(int(msg.get("cols", 80)), int(msg.get("rows", 24)))
            else:
                shell.write(str(msg.get("data", "")).encode())
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        pump_task.cancel()
        shell.close()


# ------------------------------------------------------------------ page

@app.get("/")
async def index():
    return Response(PAGE, media_type="text/html")


PAGE = r"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Computer — ma machine</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">
<style>
:root{--bg:#0b0e14;--bg2:#10141d;--line:#232b3a;--txt:#d7dde8;--mut:#7d8aa0;
--acc:#4f8cff;--ok:#23d18b;--warn:#e5c07b;--err:#f47067;--mono:Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif}
header{padding:12px 20px;background:var(--bg2);border-bottom:1px solid var(--line);
display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.badge{border:1px solid var(--ok);color:var(--ok);border-radius:20px;padding:2px 12px;font-size:12px}
nav{display:flex;gap:4px;padding:0 20px;background:var(--bg2);border-bottom:1px solid var(--line)}
nav button{background:none;border:none;color:var(--mut);padding:11px 16px;cursor:pointer;
font-size:13px;border-bottom:2px solid transparent}
nav button.active{color:var(--txt);border-bottom-color:var(--acc)}
.hidden{display:none!important}
main{padding:18px 20px;max-width:1150px;margin:0 auto}
h1{font-size:19px;margin:4px 0}h2{font-size:15px;margin:16px 0 8px;color:#fff}
.tab{display:none}.tab.active{display:block}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.card{border:1px solid var(--line);background:var(--bg2);border-radius:10px;padding:11px 13px}
.card .k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.card .v{font-size:17px;font-weight:700;margin-top:4px;font-family:var(--mono)}
.card .v.small{font-size:13px;font-weight:400}
.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
#term-box{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#0a0d13;height:60vh}
#files{list-style:none;padding:0;margin:0;border:1px solid var(--line);border-radius:10px;
background:var(--bg2);max-height:400px;overflow:auto}
#files li{padding:7px 12px;border-bottom:1px solid var(--line);display:flex;gap:10px;
font-family:var(--mono);font-size:12.5px;cursor:pointer}
#files li:hover{background:#182238}
#files .d{color:var(--acc)}#files .sz{color:var(--mut);margin-left:auto}
pre.viewer{border:1px solid var(--line);background:#0a0d13;border-radius:10px;padding:12px;
overflow:auto;font-family:var(--mono);font-size:12.5px;max-height:50vh;white-space:pre-wrap}
#lock{position:fixed;inset:0;background:rgba(0,0,0,.82);display:flex;align-items:center;
justify-content:center;z-index:10}
#lock .box{background:var(--bg2);border:1px solid var(--line);border-radius:14px;
padding:26px;width:340px;text-align:center}
#lock input{width:100%;margin:12px 0}
a.btn{text-decoration:none;border:1px solid var(--line);background:var(--bg2);color:var(--txt);
padding:8px 14px;border-radius:9px;font-weight:600;display:inline-block}
.btn{background:var(--acc);border:none;color:#fff;padding:9px 16px;border-radius:9px;cursor:pointer}
.hint{color:var(--mut);font-size:12px}
</style></head><body>
<header><div><strong>🖥️ Agent Computer</strong> <span class="warn" id="pill">…</span></div>
<div class="badge" id="up">connexion…</div></header>
<nav>
  <button data-tab="dash" class="active">📊 Tableau de bord</button>
  <button data-tab="term">💻 Terminal</button>
  <button data-tab="files">📁 Fichiers</button>
</nav>
<main>
  <section id="tab-dash" class="tab active">
    <h1>Ma machine de codage IA</h1>
    <p class="hint">Le terminal est intégré : ouvrez l'onglet 💻 Terminal pour lancer l'agent sans quitter le site.</p>
    <div class="cards" id="cards"></div>
    <h2>📜 Journal</h2>
    <pre id="log" class="viewer">chargement…</pre>
  </section>
  <section id="tab-term" class="tab">
    <div id="lock" class="hidden"><div class="box">
      <div style="font-size:34px">🔒</div><h2>Terminal protégé</h2>
      <p class="hint">Entrez le mot de passe (TERM_PASS) pour ouvrir le terminal.</p>
      <input type="password" id="pass" placeholder="mot de passe" />
      <button class="btn" id="unlock">Déverrouiller</button>
    </div></div>
    <div id="term-box"></div>
    <p class="hint">Astuce : tapez <code>opencode</code> pour lancer l'agent de codage dans ce terminal.</p>
  </section>
  <section id="tab-files" class="tab">
    <h2>📁 Dossier de travail <span class="hint">(machine/home/agent)</span></h2>
    <div id="crumbs" class="hint"></div>
    <ul id="files"></ul>
    <h2 id="viewer-title" class="hidden"></h2>
    <pre id="viewer" class="viewer hidden"></pre>
  </section>
</main>
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script>
const $=s=>document.querySelector(s);
/* ---- onglets ---- */
document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');$('#tab-'+b.dataset.tab).classList.add('active');
  if(b.dataset.tab==='files')loadFiles('');if(b.dataset.tab==='term')ensureTerm();
}));
/* ---- dashboard ---- */
async function j(u){const r=await fetch(u);return r.json()}
function card(k,v,cls){return `<div class="card"><div class="k">${k}</div><div class="v ${cls||''}">${v}</div></div>`}
async function dash(){
  try{
    const h=await j('/health');
    $('#pill').textContent='● MACHINE ACTIVE';$('#up').textContent='démarrage '+h.uptime;
    $('#cards').innerHTML=
      card('Statut','● ACTIVE','ok')+card('Uptime',h.uptime,'small')+
      card('Charge CPU',h.load.join(' '),'small')+
      card('Disque',h.disk.free_gb+' Go libres','small')+
      card('Terminal',h.terminal)+card('Terminal protégé',h.terminal_protected?'oui 🔒':'non ⚠️','small')+
      card('Agent opencode',h.opencode?'installé':'non installé','small')+
      card('Machine',h.machine,'small');
    const r=await fetch('/watchdog.log');$('#log').textContent=await r.text();
  }catch(e){$('#pill').textContent='● hors ligne'}
}
/* ---- fichiers ---- */
let cwd='';
async function loadFiles(path){
  cwd=path;
  $('#crumbs').textContent=path?('📂 / '+path):'📂 / (racine du dossier de travail)';
  $('#viewer').classList.add('hidden');$('#viewer-title').classList.add('hidden');
  const items=await j('/api/files?path='+encodeURIComponent(path));
  const ul=$('#files');ul.innerHTML='';
  if(path){const li=document.createElement('li');li.innerHTML='<span class="d">⬆ ..</span>';
    li.onclick=()=>loadFiles(path.split('/').slice(0,-1).join('/'));ul.appendChild(li);}
  items.forEach(f=>{const li=document.createElement('li');
    li.innerHTML=`<span class="${f.type}">${f.type==='dir'?'📁':'📄'}</span> ${esc(f.name)}<span class="sz">${f.type==='file'?(f.size||0)+' o':''}</span>`;
    li.onclick=()=>{if(f.type==='dir')loadFiles((path?path+'/':'')+f.name);else viewFile((path?path+'/':'')+f.name);};
    ul.appendChild(li);});
}
async function viewFile(p){$('#viewer-title').textContent='📄 '+p;$('#viewer-title').classList.remove('hidden');
  const r=await fetch('/raw?path='+encodeURIComponent(p));$('#viewer').textContent=await r.text();
  $('#viewer').classList.remove('hidden');}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
/* ---- terminal intégré ---- */
let term=null,ws=null,token='',termAsked=false;
async function ensureTerm(){
  if(term)return;
  const need=await j('/api/term-required');
  if(need.required){
    $('#lock').classList.remove('hidden');
    $('#unlock').onclick=unlock; $('#pass').addEventListener('keydown',e=>{if(e.key==='Enter')unlock()});
  } else { $('#lock').classList.add('hidden'); openTerm(''); }
}
async function unlock(){
  const res=await fetch('/api/term-login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({password:$('#pass').value})});
  if(res.ok){token=(await res.json()).token;$('#pass').value='';$('#lock').classList.add('hidden');openTerm(token);}
  else alert('Mot de passe incorrect');
}
function openTerm(tok){
  term=new Terminal({cursorBlink:true,fontFamily:'Consolas,monospace',fontSize:13,theme:{background:'#0a0d13'}});
  term.open($('#term-box'));
  const proto=location.protocol==='https:'?'wss':'ws';
  ws=new WebSocket(`${proto}://${location.host}/ws/term?token=${encodeURIComponent(tok)}`);
  ws.onopen=()=>{term.focus();term.writeln('\x1b[32m=== Terminal connecté — tapez opencode pour lancer l\'agent ===\x1b[0m');sendResize();};
  ws.onmessage=e=>term.write(e.data);
  ws.onclose=()=>term.writeln('\r\n\x1b[31m=== connexion fermée ===\x1b[0m');
  term.onData(d=>{if(ws&&ws.readyState===1)ws.send(d);});
  term.onResize(size=>sendResize(size));
  new ResizeObserver(()=>sendResize()).observe($('#term-box'));
}
function sendResize(sz){
  if(!ws||ws.readyState!==1)return;
  const dims=sz||{cols:term.cols,rows:term.rows};
  ws.send(JSON.stringify({type:'resize',cols:dims.cols,rows:dims.rows}));
}
/* ---- boot ---- */
dash();setInterval(dash,5000);loadFiles('');
</script></body></html>"""
