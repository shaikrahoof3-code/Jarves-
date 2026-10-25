"""Offline self-check: python test_jarvis.py  (no key, microphone or internet needed)."""
import http.client, json, threading, time
from http.server import ThreadingHTTPServer

import jarvis


def tc(name, **args):
    return {"id": "c1", "function": {"name": name, "arguments": json.dumps(args)}}


# 1. tools stay inside the workspace
assert jarvis.write_file("t/a.txt", "x") == "saved t/a.txt"
try:
    jarvis.write_file("../evil.txt", "x")
    raise SystemExit("FAIL: escaped workspace")
except ValueError:
    pass

# 2. wake word / sleep, with a fake brain that writes a file then answers
replies = iter([{"content": None, "tool_calls": [tc("write_file", path="t/hi.txt", content="hello")]},
                {"content": "Saved it."}])
jarvis.llm = lambda m: next(replies)
s = {"awake": False, "history": []}
assert jarvis.step(s, "make me a website") is None
assert "awake" in jarvis.step(s, "Wake up, Jarvis!")
assert jarvis.step(s, "make a hello file") == "Saved it."
assert (jarvis.WORK / "t/hi.txt").read_text() == "hello"
assert jarvis.step(s, "Go to sleep Jarvis") == "Going to sleep." and not s["awake"]

# 3. memory is fed back into the prompt
jarvis.MEM = jarvis.WORK / "mem_test.md"
jarvis.remember("likes dark themes")
assert "dark themes" in jarvis.system()

# 4. the web server: token required, health blocks the mic, approval flow works end to end
srv = ThreadingHTTPServer(("127.0.0.1", 0), jarvis.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port, H = srv.server_address[1], {"Cookie": f"jt={jarvis.TOKEN}"}


def req(method, path, body=None, headers=H):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request(method, path, json.dumps(body) if body is not None else None, headers)
    r = c.getresponse()
    return r.status, r.read()


assert req("GET", "/", headers={})[0] == 403                       # no token, no entry
assert req("POST", "/api/say", {"text": "x"}, headers={})[0] == 403
import os
os.environ["CODESPACES"] = "true"                                   # inside Codespaces GitHub checks the login instead
assert req("GET", "/api/health", headers={})[0] == 200
del os.environ["CODESPACES"]
code, page = req("GET", "/")
assert code == 200 and b"Enable microphone" in page
jarvis.API_KEY = ""
assert json.loads(req("GET", "/api/health")[1])["ready"] is False   # mic stays locked

jarvis.STATE.update(awake=True, history=[])
replies = iter([{"content": None, "tool_calls": [tc("run_command", cmd="echo hi")]}, {"content": "All done."}])
jarvis.llm = lambda m: next(replies)
job = json.loads(req("POST", "/api/say", {"text": "run something"})[1])["job"]
for _ in range(50):
    j = json.loads(req("GET", f"/api/job?id={job}")[1])
    if j["status"] == "approval":
        break
    time.sleep(0.1)
assert j["status"] == "approval" and j["cmd"] == "echo hi"
req("POST", "/api/approve", {"id": job, "ok": True})
for _ in range(50):
    j = json.loads(req("GET", f"/api/job?id={job}")[1])
    if j["status"] == "done":
        break
    time.sleep(0.1)
assert j["reply"] == "All done."

# a denied command must not run
jarvis.STATE.update(awake=True, history=[])
replies = iter([{"content": None, "tool_calls": [tc("run_command", cmd="echo nope > denied.txt")]}, {"content": "Ok."}])
job = json.loads(req("POST", "/api/say", {"text": "again"})[1])["job"]
for _ in range(50):
    if json.loads(req("GET", f"/api/job?id={job}")[1])["status"] == "approval":
        break
    time.sleep(0.1)
req("POST", "/api/approve", {"id": job, "ok": False})
for _ in range(50):
    if json.loads(req("GET", f"/api/job?id={job}")[1])["status"] == "done":
        break
    time.sleep(0.1)
assert not (jarvis.WORK / "denied.txt").exists()
print("ALL TESTS PASSED")
