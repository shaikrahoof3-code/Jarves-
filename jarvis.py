"""Jarvis: web UI on http://localhost:8080, free LLM API brain, tools. Run: python jarvis.py
Needs only Python 3.9+ (no pip installs). Add --lan for iPad/phone on the same Wi-Fi, --https for iPad mic."""
import hmac, json, os, pathlib, re, secrets, shutil, socket, ssl, subprocess, sys, threading, urllib.error, urllib.request, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).parent


def _env():
    e = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                e[k.strip()] = v.strip().strip("\"'")
    e.update({k: v for k, v in os.environ.items() if k in ("API_KEY", "BASE_URL", "MODEL", "PORT")})
    return e


CFG = _env()
API_KEY = "" if CFG.get("API_KEY", "").startswith("paste") else CFG.get("API_KEY", "")
BASE_URL = CFG.get("BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
MODEL = CFG.get("MODEL", "llama-3.3-70b-versatile")
PORT = int(CFG.get("PORT", 8080))
UA = "jarvis/1.0"  # some free services block the default python user agent
WORK = ROOT / "workspace"  # Jarvis can only write files here
WORK.mkdir(exist_ok=True)
MEM = ROOT / "memory.md"  # what Jarvis has learned about you
WAKE = ("wake up jarvis", "wake up java")
SLEEP = ("go to sleep jarvis", "go to sleep java")

PERSONA = """You are Jarvis, a personal assistant with 15+ years of experience as a senior software engineer,
software architect and web designer. Replies are spoken aloud: keep them short and plain, no markdown.
When asked to build something, write the files with write_file (a website goes in an index.html), then say in
one sentence what you made. Use run_command for things like git, python, npm and ffmpeg.
Design rules: one palette (60% neutral, 30% secondary, 10% accent), text contrast at least 4.5:1,
at most two fonts, an 8px spacing scale, generous whitespace, mobile first, touch targets at least 44px.
Video editing: use ffmpeg through run_command (cut, join, captions, resize, export).
When the user corrects you or states a preference, call remember. Never claim you did something you did not do."""


# ---------- tools ----------
def _safe(p):
    f = (WORK / p).resolve()
    if f != WORK.resolve() and WORK.resolve() not in f.parents:
        raise ValueError("path is outside the workspace")
    return f


def write_file(path, content):
    f = _safe(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    return f"saved {path}"


def read_file(path):
    return _safe(path).read_text()[:8000]


def run_command(cmd):
    if not APPROVE(cmd):
        return "user said no"
    r = subprocess.run(cmd, shell=True, cwd=WORK, capture_output=True, text=True, timeout=300)
    return (r.stdout + r.stderr)[-4000:] or "done"


def remember(note):
    with MEM.open("a") as f:
        f.write(f"- {note}\n")
    return "remembered"


FUNCS = {"write_file": write_file, "read_file": read_file, "run_command": run_command, "remember": remember}


def _tool(name, desc, **props):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
        "required": list(props)}}}


TOOLS = [
    _tool("write_file", "Create or overwrite a file in the workspace", path="relative path", content="file text"),
    _tool("read_file", "Read a file from the workspace", path="relative path"),
    _tool("run_command", "Run a shell command in the workspace (the user must approve it)", cmd="the command"),
    _tool("remember", "Save a lasting note about the user's preferences or a correction", note="the note"),
]


# ---------- brain ----------
def system():
    mem = MEM.read_text() if MEM.exists() else "nothing yet"
    return f"{PERSONA}\n\nWhat you know about the user:\n{mem}"


def llm(messages):
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", json.dumps({"model": MODEL, "messages": messages, "tools": TOOLS}).encode(),
        {"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["choices"][0]["message"]


def ask(history, text):
    history.append({"role": "user", "content": text})
    for _ in range(6):
        try:
            msg = llm([{"role": "system", "content": system()}] + history)
        except urllib.error.HTTPError as e:
            return "The free service says the limit is reached. Wait a little and try again." if e.code == 429 \
                else f"The AI service returned error {e.code}. Check your key in the .env file."
        except Exception as e:
            return f"I could not reach the AI service: {e}"
        calls = msg.get("tool_calls") or []
        entry = {"role": "assistant", "content": msg.get("content") or ""}
        if calls:
            entry["tool_calls"] = calls
        history.append(entry)
        if not calls:
            return msg.get("content") or "Done."
        for c in calls:
            try:
                out = FUNCS[c["function"]["name"]](**json.loads(c["function"]["arguments"]))
            except Exception as e:
                out = f"error: {e}"
            history.append({"role": "tool", "tool_call_id": c["id"], "content": str(out)})
    return "I got stuck on that one, please try again."


def clean(s):
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def step(state, heard):
    """One turn of the wake/sleep state machine. Returns the reply to show/speak, or None."""
    h = clean(heard)
    if not state["awake"]:
        if any(w in h for w in WAKE):
            state["awake"] = True
            return "I'm awake. What do you need?"
        return None
    if any(w in h for w in SLEEP):
        state["awake"], state["history"] = False, []
        return "Going to sleep."
    return ask(state["history"], heard) if h else None


# ---------- jobs: one at a time, approvals go through the UI ----------
STATE = {"awake": False, "history": []}
JOBS, CUR, LOCK = {}, {}, threading.Lock()


def _approve(cmd):
    job = CUR["job"]
    job["ev"].clear()
    job.update(status="approval", cmd=cmd)
    return job["ev"].wait(120) and job["ok"] is True


APPROVE = _approve


def start_job(text):
    jid, job = uuid.uuid4().hex[:8], {"status": "running", "reply": None, "cmd": None, "ok": None, "ev": threading.Event()}
    JOBS[jid] = job

    def work():
        with LOCK:
            CUR["job"] = job
            try:
                reply = step(STATE, text)
            except Exception as e:
                reply = f"Something broke: {e}"
            job.update(status="done", reply=reply, awake=STATE["awake"])

    threading.Thread(target=work, daemon=True).start()
    return jid


def health():
    checks = [{"name": "API key", "ok": bool(API_KEY), "hint": "" if API_KEY else "Put your key in the .env file", "required": True}]
    ok, why = False, "needs a key first"
    if API_KEY:
        try:
            urllib.request.urlopen(urllib.request.Request(
                BASE_URL + "/models", headers={"Authorization": "Bearer " + API_KEY, "User-Agent": UA}), timeout=10)
            ok, why = True, ""
        except urllib.error.HTTPError as e:
            why = "key was rejected" if e.code in (401, 403) else f"service error {e.code}"
        except Exception:
            why = "cannot reach the service (internet?)"
    checks.append({"name": "Free AI service", "ok": ok, "hint": why, "required": True})
    try:
        (WORK / ".w").write_text("x")
        (WORK / ".w").unlink()
        w = True
    except OSError:
        w = False
    checks.append({"name": "Workspace folder", "ok": w, "hint": "" if w else "Cannot write files", "required": True})
    f = bool(shutil.which("ffmpeg"))
    checks.append({"name": "ffmpeg (video editing)", "ok": f, "hint": "" if f else "Optional: install from ffmpeg.org", "required": False})
    return {"checks": checks, "ready": all(c["ok"] for c in checks if c["required"])}


# ---------- web server ----------
def _token():
    p = ROOT / ".token"
    if not p.exists():
        p.write_text(secrets.token_urlsafe(16))
    return p.read_text().strip()


TOKEN = _token()  # every request needs it, so other websites can't drive Jarvis


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authed(self):
        if os.environ.get("CODESPACES") == "true":  # shortcut: GitHub's private port already checks your login; breaks if you make the port Public
            return True
        t =parse_qs(urlparse(self.path).query).get("t", [""])[0]
        m = re.search(r"jt=([\w-]+)", self.headers.get("Cookie", ""))
        return any(x and hmac.compare_digest(x, TOKEN) for x in (t, m.group(1) if m else ""))

    def _send(self, code, body, ctype="application/json", extra=None):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._authed():
            return self._send(403, b"Open the link printed in the terminal; it contains a secret key.", "text/plain")
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8",
                              {"Set-Cookie": f"jt={TOKEN}; HttpOnly; SameSite=Strict; Path=/"})
        if u.path == "/api/health":
            return self._send(200, health())
        if u.path == "/api/job":
            jid = parse_qs(u.query).get("id", [""])[0]
            job = JOBS.get(jid)
            if not job:
                return self._send(404, {"error": "no such job"})
            out = {k: job.get(k) for k in ("status", "reply", "cmd", "awake")}
            if job["status"] == "done":
                JOBS.pop(jid, None)
            return self._send(200, out)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return self._send(403, {"error": "forbidden"})
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        path = urlparse(self.path).path
        if path == "/api/say":
            return self._send(200, {"job": start_job(str(data.get("text", ""))[:2000])})
        if path == "/api/approve":
            job = JOBS.get(data.get("id"))
            if not job or job["status"] != "approval":
                return self._send(404, {"error": "nothing to approve"})
            job.update(ok=data.get("ok") is True, status="running")
            job["ev"].set()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})


def main():
    lan, https = "--lan" in sys.argv, "--https" in sys.argv
    srv = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", PORT), H)
    if https:
        c, k = ROOT / "cert.pem", ROOT / "key.pem"
        if not c.exists():
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(k), "-out", str(c),
                            "-days", "365", "-subj", "/CN=jarvis"], check=True, capture_output=True)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(c, k)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    host = "localhost"
    if lan:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # sends nothing, just finds this computer's Wi-Fi address
        host = s.getsockname()[0]
    url = f"http{'s' if https else ''}://{host}:{PORT}/?t={TOKEN}"
    print(f"\nJarvis is running. Open this link{' on your iPad' if lan else ''}:\n\n  {url}\n\nCtrl+C to stop.")
    if not lan:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
