#!/usr/bin/env python3
"""Agent Computer — portail web (stdlib uniquement).

Sert :
  /            page d'accueil (état de la machine, terminal, fichiers, aide)
  /health      JSON de santé (uptime, services, heartbeat du watchdog)
  /api/files   JSON : contenu du dossier de travail (machine/home)
  /raw         contenu texte d'un fichier du dossier de travail
  /term        redirection vers le terminal web (ttyd, port 7681)

Usage :  python3 portal.py [--port 8125]
"""
import argparse
import json
import os
import socket
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
MACHINE = os.path.join(ROOT, "machine")
HOME = os.path.join(MACHINE, "home", "agent")
VAR = os.path.join(ROOT, "var")
LOG = os.path.join(VAR, "log")
TTYD_PORT = int(os.environ.get("TTYD_PORT", "7681"))
PID = os.getpid()
START = time.time()


def uptime() -> str:
    s = int(time.time() - START)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}h{m:02d}min{sec:02d}s"


def service_alive(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def watchdog_beat() -> str | None:
    f = os.path.join(VAR, "watchdog.heartbeat")
    try:
        return open(f).read().strip()
    except OSError:
        return None


def load_avg() -> list:
    try:
        return [round(float(x), 2) for x in open("/proc/loadavg").read().split()[:3]]
    except OSError:
        return []


def disk_usage() -> dict:
    st = os.statvfs(MACHINE)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return {"total_gb": round(total / 1e9, 1), "free_gb": round(free / 1e9, 1)}


def list_dir(path: str) -> list:
    base = os.path.realpath(HOME)
    target = os.path.realpath(os.path.join(base, path.lstrip("/")))
    if not (target == base or target.startswith(base + os.sep)):
        return {"error": "chemin refusé"}
    out = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        st = os.stat(full)
        out.append({
            "name": name,
            "type": "dir" if os.path.isdir(full) else "file",
            "size": st.st_size if os.path.isfile(full) else None,
            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
        })
    return out


def health() -> dict:
    return {
        "machine": socket.gethostname(),
        "status": "ACTIVE",
        "uptime": uptime(),
        "load": load_avg(),
        "disk": disk_usage(),
        "services": {
            "portal": True,
            "terminal_ttyd": service_alive(TTYD_PORT),
            "watchdog": watchdog_beat() is not None,
            "opencode": os.system("command -v opencode >/dev/null 2>&1") == 0,
        },
        "watchdog_last_beat": watchdog_beat(),
        "workspace": HOME,
    }


PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Computer — ma machine</title>
<style>
:root{--bg:#0b0e14;--bg2:#10141d;--line:#232b3a;--txt:#d7dde8;--mut:#7d8aa0;
--acc:#4f8cff;--ok:#23d18b;--warn:#e5c07b;--err:#f47067;--mono:Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif}
header{padding:14px 22px;background:var(--bg2);border-bottom:1px solid var(--line);
display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.badge{border:1px solid var(--ok);color:var(--ok);border-radius:20px;padding:2px 12px;font-size:12px}
main{padding:20px 22px;max-width:1100px;margin:0 auto}
h1{font-size:20px;margin:4px 0}h2{font-size:15px;margin:22px 0 8px;color:#fff}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.card{border:1px solid var(--line);background:var(--bg2);border-radius:10px;padding:12px 14px}
.card .k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.card .v{font-size:18px;font-weight:700;margin-top:4px;font-family:var(--mono)}
.card .v.small{font-size:13px;font-weight:400}
.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
a.btn{text-decoration:none;border:1px solid var(--line);background:var(--bg2);color:var(--txt);
padding:10px 16px;border-radius:9px;font-weight:600}
a.btn.p{background:var(--acc);border-color:var(--acc);color:#fff}
a.btn:hover{border-color:var(--acc)}
#files{list-style:none;padding:0;margin:0;border:1px solid var(--line);border-radius:10px;
background:var(--bg2);max-height:340px;overflow:auto}
#files li{padding:7px 12px;border-bottom:1px solid var(--line);display:flex;gap:10px;font-family:var(--mono);font-size:12.5px}
#files li:last-child{border-bottom:none}
#files .d{color:var(--acc)} #files .sz{color:var(--mut);margin-left:auto}
pre{border:1px solid var(--line);background:#0a0d13;border-radius:10px;padding:12px;overflow:auto;font-family:var(--mono);font-size:12.5px;max-height:300px}
code{background:#161c28;padding:1px 6px;border-radius:5px;font-family:var(--mono)}
</style></head><body>
<header><div><strong>🖥️ Agent Computer</strong> <span class="warn" id="statusPill">…</span></div>
<div class="badge" id="upBadge">connexion…</div></header>
<main>
<h1>Ma machine virtuelle — toujours active</h1>
<p style="color:var(--mut)">Le code vit sur <b>mon</b> disque. Les services se réparent tout seuls (watchdog).</p>
<div class="cards" id="cards"></div>
<div class="actions">
  <a class="btn p" href="/term" target="_blank">🖥️ Ouvrir le terminal</a>
  <a class="btn" href="#" onclick="toggleFiles();return false">📁 Code stocké</a>
  <a class="btn" href="#" onclick="toggleLog();return false">📜 Journal watchdog</a>
</div>
<div id="filebox" style="display:none">
  <h2>📁 Dossier de travail (machine/home/agent)</h2>
  <ul id="files"><li>chargement…</li></ul>
</div>
<div id="logbox" style="display:none">
  <h2>📜 Journal watchdog (auto-réparation)</h2>
  <pre id="logpre"></pre>
</div>
</main>
<script>
async function j(u){const r=await fetch(u);return r.json()}
function card(k,v,cls){return `<div class="card"><div class="k">${k}</div><div class="v ${cls||''}">${v}</div></div>`}
async function load(){
  try{
    const h=await j('/health');
    document.getElementById('statusPill').textContent='● MACHINE ACTIVE';
    document.getElementById('upBadge').textContent='démarrage '+h.uptime;
    const svc=h.services;
    const t=svc.terminal_ttyd?`<span class="ok">actif</span>`:`<span class="err">ARRÊTÉ (watchdog va relancer)</span>`;
    const w=svc.watchdog?`<span class="ok">actif</span>`:`<span class="err">inactif</span>`;
    const o=svc.opencode?`<span class="ok">installé</span>`:`<span class="warn">non installé</span>`;
    document.getElementById('cards').innerHTML=
      card('Statut','● ACTIVE','ok')+card('Uptime machine',h.uptime,'small')+
      card('Charge CPU',h.load.join(' '),'small')+card('Disque',h.disk.free_gb+' Go libres / '+h.disk.total_gb+' Go','small')+
      card('Terminal web',t,'small')+card('Watchdog',w,'small')+
      card('Agent opencode',o,'small')+card('Dernier battement watchdog',(h.watchdog_last_beat||'—'),'small');
  }catch(e){document.getElementById('statusPill').textContent='● hors ligne';}
}
async function toggleFiles(){
  const box=document.getElementById('filebox');box.style.display=box.style.display==='none'?'block':'none';
  if(box.style.display==='block'){
    const ul=document.getElementById('files');ul.innerHTML='<li>chargement…</li>';
    try{
      const items=await j('/api/files');
      if(items.error){ul.innerHTML='<li>'+items.error+'</li>';return}
      ul.innerHTML=items.map(f=>`<li><span class="${f.type}">${f.type==='dir'?'📁':'📄'}</span> <a href="/raw?path=${encodeURIComponent(f.name)}" style="color:var(--txt)">${f.name}</a> <span class="sz">${f.type==='file'?(f.size||0)+' o':'—'}</span></li>`).join('');
    }catch(e){ul.innerHTML='<li>erreur chargement</li>'}
  }
}
async function toggleLog(){
  const box=document.getElementById('logbox');box.style.display=box.style.display==='none'?'block':'none';
  if(box.style.display==='block'){
    const r=await fetch('/watchdog.log');document.getElementById('logpre').textContent=await r.text();
  }
}
load();setInterval(load,5000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencieux
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path in ("/", "/index.html"):
                self._send(200, PAGE.encode())
            elif parsed.path == "/term":
                self.send_response(302)
                self.send_header("Location", f"http://{self.headers.get('Host','localhost').split(':')[0]}:{TTYD_PORT}/")
                self.end_headers()
            elif parsed.path == "/health":
                self._send(200, json.dumps(health()).encode(), "application/json")
            elif parsed.path == "/api/files":
                self._send(200, json.dumps(list_dir(q.get("path", [""])[0])).encode(), "application/json")
            elif parsed.path == "/raw":
                self._serve_raw(q.get("path", [""])[0])
            elif parsed.path == "/watchdog.log":
                body = None
                for cand in (os.path.join(VAR, "log", "watchdog.log"),
                             os.path.join(VAR, "watchdog.log")):
                    try:
                        body = open(cand).read().encode()
                        break
                    except OSError:
                        continue
                if body is None:
                    self._send(404, b"pas encore de journal")
                else:
                    self._send(200, body, "text/plain; charset=utf-8")
            else:
                self._send(404, b"404")
        except BrokenPipeError:
            pass

    def _serve_raw(self, rel):
        base = os.path.realpath(HOME)
        target = os.path.realpath(os.path.join(base, rel.lstrip("/")))
        if not (target == base or target.startswith(base + os.sep)) or not os.path.isfile(target):
            self._send(404, b"fichier introuvable")
            return
        try:
            data = open(target, "rb").read(200_000)
        except OSError:
            self._send(500, b"erreur de lecture")
            return
        page = (f"<meta charset='utf-8'><style>body{{background:#0a0d13;color:#d7dde8;"
                f"font:12.5px Consolas,monospace;padding:16px;white-space:pre-wrap;word-break:break-all}}</style>"
                f"<!-- {rel} -->").encode() + data
        self._send(200, page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8125")))
    args = ap.parse_args()
    os.makedirs(HOME, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Agent Computer portal → http://127.0.0.1:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
