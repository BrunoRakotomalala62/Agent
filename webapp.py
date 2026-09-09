#!/usr/bin/env python3
"""Agent Computer — portail web v3 : tableau de bord + 💬 CHAT avec agent autonome
+ terminal intégré + fichiers.

L'agent fait TOUT lui-même : il explore le dossier, lit/écrit les fichiers,
exécute des commandes dans le terminal, fait git add/commit/push — vous, vous
discutez. Chat alimenté par Gemini (function calling).

Sécurité : si TERM_PASS est défini, chat ET terminal demandent le mot de passe
(jeton 15 min). Sinon accès libre (mode dev uniquement !).

Usage :
    GEMINI_API_KEY=... TERM_PASS=... uvicorn webapp:app --host 0.0.0.0 --port 3000
"""
import asyncio
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

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

ROOT = Path(__file__).parent
MACHINE = ROOT / "machine"
HOME_DIR = Path(os.environ.get("WS_DIR") or (ROOT / "machine" / "home" / "agent"))
VAR = ROOT / "var"
START = time.time()

TERM_PASS = os.environ.get("TERM_PASS", "").strip()
PORT = int(os.environ.get("PORT", "3000"))
AGENT_MODEL = os.environ.get("AGENT_MODEL", "gemini-3.6-flash")
AGENT_KEY = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY") or "").strip()

app = FastAPI(title="Agent Computer", docs_url=None, redoc_url=None)
_tokens: dict[str, float] = {}
_chat_history: dict[str, list] = {}


# ------------------------------------------------------------------ helpers

def uptime() -> str:
    s = int(time.time() - START)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}h{m:02d}min{sec:02d}s"


def disk_usage() -> dict:
    st = os.statvfs(MACHINE)
    return {
        "total_gb": round(st.f_blocks * st.f_frsize / 1e9, 1),
        "free_gb": round(st.f_bavail * st.f_frsize / 1e9, 1),
    }


def service_ok() -> dict:
    return {
        "machine": socket.gethostname(),
        "status": "ACTIVE",
        "uptime": uptime(),
        "load": [round(float(x), 2) for x in open("/proc/loadavg").read().split()[:3]],
        "disk": disk_usage(),
        "opencode": os.system("command -v opencode >/dev/null 2>&1") == 0,
        "terminal": "intégré (xterm.js)",
        "chat": f"agent {AGENT_MODEL}",
        "chat_ready": bool(AGENT_KEY),
        "terminal_protected": bool(TERM_PASS),
        "workspace": str(HOME_DIR),
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


@app.get("/api/chat/status")
async def chat_status():
    return {"model": AGENT_MODEL, "ready": bool(AGENT_KEY), "workspace": str(HOME_DIR)}


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


# ------------------------------------------------------------------ terminal (pty)

class PtyShell:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.master, slave = pty.openpty()
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["HOME"] = str(HOME_DIR)
        env["TERM"] = "xterm-256color"
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
        if self.proc.poll() is not None:
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


# ------------------------------------------------------------------ chat agent autonome

TOOL_DECLS = [
    {
        "name": "run_terminal",
        "description": "Exécute une commande shell dans le terminal de la machine (dossier de travail). "
                       "Utilise-le pour TOUT ce qui touche au système : git, tests, ls, python…",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "la commande shell complète"}},
            "required": ["command"]},
    },
    {
        "name": "list_files",
        "description": "Liste le contenu d'un dossier du projet (chemin relatif, vide = racine).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "chemin relatif du dossier"}}},
    },
    {
        "name": "read_file",
        "description": "Lit le contenu d'un fichier du projet (chemin relatif).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "chemin relatif du fichier"}},
            "required": ["path"]},
    },
    {
        "name": "write_file",
        "description": "Écrit un fichier du projet (chemin relatif, contenu complet ; écrase si existe).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]},
    },
]

SYSTEM_PROMPT = f"""Tu es l'agent de codage de l'Agent Computer, une machine de travail dont
le dossier projet est : {HOME_DIR}

RÈGLES ABSOLUES :
1. Tu fais TOUT toi-même : explore le dossier (list_files), lis les fichiers
   (read_file), exécute les commandes (run_terminal) — l'utilisateur ne tape JAMAIS
   de commande, il ne fait que te parler.
2. Pour créer/modifier un fichier, utilise write_file (contenu COMPLET du fichier)
   ou des commandes shell (ex. sed, python).
3. Vérifie ton travail avant de répondre (exécute le code, lance les tests).
4. SAUVEGARDE OBLIGATOIRE : après chaque série de modifications réussies, exécute
   dans l'ordre : git add -A  puis  git commit -m "message clair en français"
   puis  git push origin HEAD  (si le dossier est un dépôt git avec un remote).
   Si ce n'est pas un dépôt ou pas de remote, signale-le simplement.
5. Réponds TOUJOURS en français, de façon concise : ce que tu as fait, le résultat,
   et la prochaine étape possible."""


def _tool_run_terminal(command: str) -> str:
    try:
        proc = subprocess.run(
            ["bash", "-lc", command], cwd=str(HOME_DIR), capture_output=True,
            text=True, timeout=90, env=dict(os.environ, HOME=str(HOME_DIR)))
        out = (proc.stdout or "")[-20000:]
        err = (proc.stderr or "")[-8000:]
        return f"[code de sortie {proc.returncode}]\nSTDOUT:\n{out}\nSTDERR:\n{err}"
    except subprocess.TimeoutExpired:
        return "ERREUR: commande interrompue (plus de 90 s)"
    except Exception as exc:
        return f"ERREUR: {exc}"


def _tool_list_files(path: str = "") -> str:
    target = safe_path(path)
    if not target or not target.is_dir():
        return "ERREUR: dossier introuvable ou refusé"
    lines = []
    for name in sorted(os.listdir(target)):
        full = target / name
        kind = "📁" if full.is_dir() else "📄"
        size = full.stat().st_size if full.is_file() else 0
        lines.append(f"{kind} {name} ({size} o)")
    return "\n".join(lines) or "(dossier vide)"


def _tool_read_file(path: str) -> str:
    target = safe_path(path)
    if not target or not target.is_file():
        return "ERREUR: fichier introuvable ou refusé"
    try:
        return target.read_text(errors="replace")[:40000]
    except Exception as exc:
        return f"ERREUR: {exc}"


def _tool_write_file(path: str, content: str) -> str:
    target = safe_path(path)
    if target is None:
        return "ERREUR: chemin refusé (hors du projet)"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"OK : {path} écrit ({len(content)} caractères)"
    except Exception as exc:
        return f"ERREUR: {exc}"


def _exec_tool(name: str, args: dict) -> tuple[str, str]:
    """Retourne (label_pour_le_chat, résultat)."""
    args = args or {}
    if name == "run_terminal":
        return f"$ {args.get('command', '')[:160]}", _tool_run_terminal(args.get("command", ""))
    if name == "list_files":
        return f"📁 liste de {args.get('path') or '.'}", _tool_list_files(args.get("path", ""))
    if name == "read_file":
        return f"📖 {args.get('path')}", _tool_read_file(args.get("path", ""))
    if name == "write_file":
        return f"✏️ écriture de {args.get('path')}", _tool_write_file(args.get("path", ""), args.get("content", ""))
    return f"? outil {name}", "ERREUR: outil inconnu"


async def _agent_call(contents: list) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{AGENT_MODEL}:generateContent"
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "tools": [{"functionDeclarations": TOOL_DECLS}],
    }
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=150) as client:
                resp = await client.post(url, params={"key": AGENT_KEY}, json=body)
            data = resp.json()
            if resp.status_code in (429, 500, 503) and attempt < 3:
                await asyncio.sleep(6 * (attempt + 1))  # reprise automatique
                continue
            if resp.status_code != 200:
                msg = data.get("error", {}).get("message", resp.text)[:400]
                raise RuntimeError(f"API Gemini ({resp.status_code}) : {msg}")
            try:
                return data["candidates"][0]["content"]
            except (KeyError, IndexError):
                raise RuntimeError("Réponse Gemini vide ou bloquée (contenu refusé ?)")
        except (httpx.TransportError, asyncio.TimeoutError) as exc:
            last_err = exc
            if attempt < 3:
                await asyncio.sleep(6 * (attempt + 1))
                continue
    if last_err:
        raise RuntimeError(f"Réseau Gemini injoignable : {last_err}")
    raise RuntimeError("API Gemini : échec après plusieurs tentatives")


async def run_agent_turn(history: list, emit) -> str:
    """Fait tourner la boucle agent. history = contents Gemini (muté en place)."""
    steps = 0
    while steps < 20:
        steps += 1
        content = await _agent_call(history)
        parts = content.get("parts", [])
        history.append({"role": "model", "parts": parts})
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
            return "".join(p.get("text", "") for p in parts).strip()
        for fc in calls:
            name, args = fc.get("name", ""), fc.get("args", {}) or {}
            label, result = _exec_tool(name, args)
            await emit({"type": "tool", "text": label})
            if name == "run_terminal" and result:
                await emit({"type": "toolout", "text": result[:1200]})
            history.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": name, "response": {"result": result[:40000]}}}],
            })
    return "⚠️ J'ai dû m'arrêter (trop d'étapes pour cette demande). Reformulez en plus petites étapes."


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    token = ws.query_params.get("token", "")
    if TERM_PASS and not _check_token(token):
        await ws.close(code=4001, reason="authentification requise")
        return
    if not AGENT_KEY:
        await ws.accept()
        await ws.send_json({"type": "error", "text": "Clé IA absente : définissez GEMINI_API_KEY."})
        await ws.close()
        return
    await ws.accept()
    sid = uuid.uuid4().hex
    history = _chat_history.setdefault(sid, [])

    async def emit(msg: dict):
        await ws.send_json(msg)

    busy = False
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") != "chat":
                continue
            text = str(msg.get("text", "")).strip()
            if not text:
                continue
            if busy:
                await ws.send_json({"type": "error", "text": "L'agent travaille déjà — patientez."})
                continue
            busy = True
            history.append({"role": "user", "parts": [{"text": text}]})
            try:
                await emit({"type": "thinking", "text": "L'agent réfléchit et agit…"})
                answer = await run_agent_turn(history, emit)
                if answer:
                    await emit({"type": "agent", "text": answer})
            except Exception as exc:
                await emit({"type": "error", "text": f"Erreur : {exc}"})
            finally:
                busy = False
                await emit({"type": "done"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _chat_history.pop(sid, None)


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
main{padding:18px 20px;max-width:1150px;margin:0 auto}
h1{font-size:19px;margin:4px 0}h2{font-size:15px;margin:16px 0 8px;color:#fff}
.tab{display:none}.tab.active{display:block}
.hidden{display:none!important}
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
justify-content:center;z-index:50}
#lock .box{background:var(--bg2);border:1px solid var(--line);border-radius:14px;
padding:26px;width:340px;text-align:center}
#lock input{width:100%;margin:12px 0}
a.btn{text-decoration:none;border:1px solid var(--line);background:var(--bg2);color:var(--txt);
padding:8px 14px;border-radius:9px;font-weight:600;display:inline-block}
.btn{background:var(--acc);border:none;color:#fff;padding:9px 16px;border-radius:9px;cursor:pointer}
.btn:disabled{opacity:.5;cursor:wait}
.hint{color:var(--mut);font-size:12px}
/* ---- chat ---- */
#chat{display:flex;flex-direction:column;height:70vh;border:1px solid var(--line);
border-radius:12px;background:var(--bg2);overflow:hidden}
#chat-log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:82%;padding:9px 13px;border-radius:12px;font-size:13.5px;line-height:1.5;
white-space:pre-wrap;word-break:break-word}
.msg.user{align-self:flex-end;background:var(--acc);color:#fff;border-bottom-right-radius:3px}
.msg.agent{align-self:flex-start;background:#1a2332;border:1px solid var(--line);border-bottom-left-radius:3px}
.msg.err{align-self:flex-start;background:#2a1618;border:1px solid var(--err);color:var(--err)}
.toolline{align-self:flex-start;font-family:var(--mono);font-size:11.5px;color:var(--warn);
background:#161c28;border:1px solid var(--line);padding:4px 9px;border-radius:6px;max-width:100%;
overflow-x:auto;white-space:pre-wrap}
.toolout{align-self:flex-start;font-family:var(--mono);font-size:11px;color:#9db0c9;
background:#0d1117;border-left:2px solid var(--line);padding:5px 10px;max-width:100%;
white-space:pre-wrap;word-break:break-all}
.thinking{align-self:flex-start;color:var(--mut);font-size:12px;font-style:italic}
#chat-input{display:flex;gap:8px;padding:10px;border-top:1px solid var(--line)}
#chat-input textarea{flex:1;resize:none;background:var(--bg);color:var(--txt);
border:1px solid var(--line);border-radius:8px;padding:9px 11px;font-size:13.5px}
#chat-input textarea:focus{outline:none;border-color:var(--acc)}
.chip{display:inline-block;border:1px solid var(--line);background:var(--bg3,#161c28);
color:var(--txt);border-radius:16px;padding:4px 11px;font-size:12px;cursor:pointer;margin:2px 4px 0 0}
.chip:hover{border-color:var(--acc)}
</style></head><body>
<header><div><strong>🖥️ Agent Computer</strong> <span class="warn" id="pill">…</span></div>
<div class="badge" id="up">connexion…</div></header>
<nav>
  <button data-tab="dash" class="active">📊 Tableau de bord</button>
  <button data-tab="chat">💬 Chat</button>
  <button data-tab="term">💻 Terminal</button>
  <button data-tab="files">📁 Fichiers</button>
</nav>
<main>
  <section id="tab-dash" class="tab active">
    <h1>Ma machine de codage IA</h1>
    <p class="hint">Posez votre demande dans l'onglet 💬 Chat : l'agent explore, code,
      exécute le terminal et pousse sur GitHub tout seul.</p>
    <div class="cards" id="cards"></div>
    <h2>📜 Journal</h2>
    <pre id="log" class="viewer">chargement…</pre>
  </section>

  <section id="tab-chat" class="tab">
    <h1>💬 Discutez avec votre agent</h1>
    <p class="hint" id="chat-meta">L'agent fait tout : il lit le code, le modifie, lance les
      commandes et sauvegarde sur GitHub. Vous ne faites que demander.</p>
    <div id="chat">
      <div id="chat-log"></div>
      <div id="chat-input">
        <textarea id="chat-text" rows="2" placeholder="Ex. : ajoute une fonction multiplication dans calcul.py et teste-la…"></textarea>
        <button class="btn" id="chat-send">Envoyer ⏎</button>
      </div>
    </div>
    <p class="hint">Suggestions :</p>
    <div>
      <span class="chip" data-p="Corrige tous les bugs du projet, vérifie avec des tests, puis pousse sur GitHub.">🐛 Corriger les bugs du projet</span>
      <span class="chip" data-p="Crée un site web de démonstration dans un dossier demo/ (HTML+CSS+JS) puis pousse-le.">🌐 Créer un site de démo</span>
      <span class="chip" data-p="Explique-moi ce que fait ce projet et sa structure.">🔍 Expliquer le projet</span>
    </div>
  </section>

  <section id="tab-term" class="tab">
    <h1>💻 Terminal</h1>
    <p class="hint">Astuce : l'onglet 💬 Chat fait tout pour vous. Ici, vous pouvez aussi
      lancer opencode à la main : tapez <code>opencode</code>.</p>
    <div id="term-box"></div>
  </section>

  <section id="tab-files" class="tab">
    <h2>📁 Dossier de travail <span class="hint">(machine/home/agent)</span></h2>
    <div id="crumbs" class="hint"></div>
    <ul id="files"></ul>
    <h2 id="viewer-title" class="hidden"></h2>
    <pre id="viewer" class="viewer hidden"></pre>
  </section>
</main>

<div id="lock" class="hidden"><div class="box">
  <div style="font-size:34px">🔒</div><h2>Espace protégé</h2>
  <p class="hint">Entrez le mot de passe (TERM_PASS) pour ouvrir le chat / terminal.</p>
  <input type="password" id="pass" placeholder="mot de passe" />
  <button class="btn" id="unlock">Déverrouiller</button>
</div></div>

<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script>
const $=s=>document.querySelector(s);
/* ---- onglets ---- */
document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');const t=$('#tab-'+b.dataset.tab);t.classList.add('active');
  if(b.dataset.tab==='files')loadFiles('');
  if(b.dataset.tab==='term'){ensureUnlock().then(()=>{if(!term)openTerm(token);});}
  if(b.dataset.tab==='chat'){ensureUnlock().then(()=>connectChat());}
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
      card('💬 Chat',h.chat)+card('Agent prêt',h.chat_ready?'oui ✅':'NON — clé manquante',h.chat_ready?'ok':'err')+
      card('Terminal protégé',h.terminal_protected?'oui 🔒':'non ⚠️','small')+
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
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
/* ---- verrou commun (chat + terminal) ---- */
let token='',term=null,termws=null,chatws=null,chatBusy=false;
async function ensureUnlock(){
  if(token)return;
  const need=await j('/api/term-required');
  if(!need.required){token='free';return;}
  $('#lock').classList.remove('hidden');
  $('#unlock').onclick=unlock;
  $('#pass').addEventListener('keydown',e=>{if(e.key==='Enter')unlock()});
}
async function unlock(){
  const res=await fetch('/api/term-login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({password:$('#pass').value})});
  if(res.ok){token=(await res.json()).token;$('#pass').value='';$('#lock').classList.add('hidden');
    const act=document.querySelector('nav button.active').dataset.tab;
    if(act==='chat')connectChat();else if(act==='term'&&!term)openTerm(token);
  } else alert('Mot de passe incorrect');
}
/* ---- terminal xterm ---- */
function openTerm(tok){
  term=new Terminal({cursorBlink:true,fontFamily:'Consolas,monospace',fontSize:13,theme:{background:'#0a0d13'}});
  term.open($('#term-box'));
  const proto=location.protocol==='https:'?'wss':'ws';
  termws=new WebSocket(`${proto}://${location.host}/ws/term?token=${encodeURIComponent(tok)}`);
  termws.onopen=()=>{term.focus();term.writeln('\x1b[32m=== Terminal connecté — l\'agent travaille aussi depuis le 💬 Chat ===\x1b[0m');sendResize();};
  termws.onmessage=e=>term.write(e.data);
  termws.onclose=()=>term.writeln('\r\n\x1b[31m=== connexion fermée ===\x1b[0m');
  term.onData(d=>{if(termws&&termws.readyState===1)termws.send(d);});
  term.onResize(sz=>sendResize(sz));
  new ResizeObserver(()=>sendResize()).observe($('#term-box'));
}
function sendResize(sz){
  if(!termws||termws.readyState!==1)return;
  const dims=sz||{cols:term.cols,rows:term.rows};
  termws.send(JSON.stringify({type:'resize',cols:dims.cols,rows:dims.rows}));
}
/* ---- chat ---- */
function addMsg(kind,text){
  const log=$('#chat-log');
  const d=document.createElement('div');
  d.className='msg '+kind;d.textContent=text;log.appendChild(d);
  log.scrollTop=log.scrollHeight;return d;
}
function addLine(cls,text){
  const log=$('#chat-log');const d=document.createElement('div');
  d.className=cls;d.textContent=text;log.appendChild(d);
  log.scrollTop=log.scrollHeight;return d;
}
function connectChat(){
  if(chatws&&(chatws.readyState===0||chatws.readyState===1))return;
  const proto=location.protocol==='https:'?'wss':'ws';
  chatws=new WebSocket(`${proto}://${location.host}/ws/chat?token=${encodeURIComponent(token)}`);
  chatws.onopen=()=>{addLine('thinking','✅ Connecté — posez votre demande.');};
  chatws.onmessage=e=>{
    const m=JSON.parse(e.data);
    if(m.type==='tool')addLine('toolline','🔧 '+m.text);
    else if(m.type==='toolout')addLine('toolout',m.text);
    else if(m.type==='agent'){removeThinking();addMsg('agent',m.text);}
    else if(m.type==='error'){removeThinking();addMsg('err',m.text);}
    else if(m.type==='thinking'){removeThinking();addLine('thinking',m.text);chatBusy=true;}
    else if(m.type==='done'){removeThinking();chatBusy=false;}
  };
  chatws.onclose=()=>{chatws=null;if(!document.querySelector('nav button.active')||document.querySelector('nav button.active').dataset.tab==='chat')
    addLine('thinking','⚠️ connexion fermée — rechargez la page pour reparler à l\'agent.');};
}
function removeThinking(){
  document.querySelectorAll('#chat-log .thinking').forEach(n=>n.remove());
}
async function sendChat(){
  const ta=$('#chat-text');const text=ta.value.trim();
  if(!text||!chatws||chatws.readyState!==1||chatBusy){if(chatBusy)return;return;}
  ta.value='';addMsg('user',text);
  chatws.send(JSON.stringify({type:'chat',text}));
  addLine('thinking','⏳ l\'agent travaille…');
}
function bindChat(){
  $('#chat-send').addEventListener('click',sendChat);
  $('#chat-text').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat();}});
  document.querySelectorAll('.chip').forEach(c=>c.addEventListener('click',()=>{
    $('#chat-text').value=c.dataset.p;sendChat();}));
}
/* ---- boot ---- */
bindChat();dash();setInterval(dash,5000);loadFiles('');
</script></body></html>"""
