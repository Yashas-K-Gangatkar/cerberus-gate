"""IDOR LAB - the two-account play, rehearsed on a range we own.

the real mission shape: two of YOUR OWN accounts on a real app, one
browser logged in as A, one as B. A asks for B's objects. if the
server answers, authorization is missing and the finding is real.
on the range, alice and bob are both accounts the owner controls -
no stranger's data exists here, ever.

  vulnerable_app()  - the api answers any id with any session. broken.
  patched_app()     - the api checks the session against the record.
  attack(base)      - login as alice, probe bob's ids, return findings.
  demo()            - attack -> report -> patch -> re-attack, PASS/FAIL.

same finding shape as pentest.py, same report pipeline as
bounty_report.py. the muscle memory transfers 1:1 to any program:
swap the host, keep the discipline.
"""
import json
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SESSIONS = {}  # sid -> user_id (server-side truth; the cookie is a key,
               # never a statement about identity)

USERS = {
    1: {"name": "alice", "label": "account A (yours)",
        "phone": "+91-90000-00001", "email": "alice.range@example.test",
        "orders": [{"id": "ORD-1001", "item": "study lamp", "price": 749}],
        "addresses": [{"label": "home", "line": "12 MG Road, Bengaluru"}]},
    2: {"name": "bob", "label": "account B (also yours)",
        "phone": "+91-90000-00002", "email": "bob.range@example.test",
        "orders": [{"id": "ORD-2002", "item": "mechanical keyboard",
                    "price": 2499}],
        "addresses": [{"label": "home", "line": "7 Park Street, Kolkata"}]},
}

MENU = """<html><head><title>IDOR lab</title></head><body>
<h1>IDOR lab - two accounts, one lesson</h1>
<p>practice flow (do this in TWO browser windows, exactly like the
real mission):</p>
<ol>
<li>window 1: <a href="/login?as=alice">log in as alice (A)</a></li>
<li>window 2: <a href="/login?as=bob">log in as bob (B)</a></li>
<li>window 1 (as A): open <code>/api/profile?id=2</code>,
<code>/api/orders?id=2</code>, <code>/api/addresses?id=2</code></li>
<li>ask: did the server show B's data to A? if yes, that is the bug.</li>
</ol>
<p>mode: <b>%s</b> - <a href="/?flip=1">flip the gate</a> and feel the
difference when authorization exists.</p>
</body></html>"""


class _Lab(BaseHTTPRequestHandler):
    secure = False

    def _send(self, code, body, headers=None):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _session(self):
        """the caller's identity - parsed server-side from the cookie."""
        c = self.headers.get("Cookie", "")
        for part in c.split(";"):
            if part.strip().startswith("sid="):
                return SESSIONS.get(part.strip()[4:].strip())
        return None

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/":
            if "flip" in q:
                # the mode must live on the CLASS (the server's own
                # state), not on this request instance - an instance
                # dies with its response, and the next request would
                # read the old mode again. same lesson as the session:
                # state lives server-side.
                self.__class__.secure = not self.__class__.secure
            self._send(200, MENU % ("PATCHED" if self.secure else "VULNERABLE"))
        elif u.path == "/login":
            who = (q.get("as", ["alice"])[0])
            uid = 1 if who == "alice" else 2
            sid = secrets.token_hex(16)
            SESSIONS[sid] = uid
            self._send(200, "logged in as %s (user %d). cookie sid=%s"
                       % (who, uid, sid),
                       {"Set-Cookie": "sid=%s; HttpOnly" % sid})
        elif u.path.startswith("/api/"):
            kind = u.path.split("/")[2]          # profile | orders | addresses
            uid = self._session()
            if uid is None:
                self._send(401, "login first")
                return
            try:
                rid = int(q.get("id", [str(uid)])[0])
            except ValueError:
                self._send(400, "bad id")
                return
            if self.secure and rid != uid:
                self._send(403, "forbidden - not your record")
                return
            rec = USERS.get(rid)
            if rec is None:
                self._send(404, "no such user")
                return
            payload = rec if kind == "profile" else rec.get(kind, [])
            self._send(200, "<pre>%s</pre>" % json.dumps(payload, indent=2))
        else:
            self._send(404, "not found")

    def log_message(self, *a):
        pass


def _serve(secure):
    handler = type("Lab", (_Lab,), {"secure": secure})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % srv.server_address[1], srv


def vulnerable_app():
    """The api with no ownership check - any session reads any record."""
    return _serve(secure=False)


def patched_app():
    """Same api after the owner read the report and checked the session."""
    return _serve(secure=True)


def _get(url, cookie=None):
    req = urllib.request.Request(url)
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _login_raw(base, who):
    class R(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(R)
    req = urllib.request.Request(base + "/login?as=" + who)
    try:
        with opener.open(req) as r:
            return (r.status, r.read().decode("utf-8", "replace"),
                    r.headers.get("Set-Cookie", ""), None)
    except urllib.error.HTTPError as e:
        return (e.code, e.read().decode("utf-8", "replace"), "", None)


def attack(base):
    """The two-account play: alice's session asking for bob's objects."""
    f = []
    base = base.rstrip("/")
    st, _, hdr, _ = _login_raw(base, "alice")
    cookie = hdr.split(";")[0] if hdr else ""
    if not cookie:
        return [{"id": "LAB-0", "name": "login failed on the range itself",
                 "severity": "low", "poc": "/login?as=alice",
                 "evidence": "no session cookie issued (status %d)" % st,
                 "fix": "range bug, not a finding - fix the lab."}]
    probes = [("profile", "identity (name, phone, email)"),
              ("orders", "order history"),
              ("addresses", "home address")]
    for kind, what in probes:
        # the real technique: baseline your OWN record first. if your
        # session later receives a payload that is not yours, the server
        # checked nothing.
        st_a, baseline = _get("%s/api/%s?id=1" % (base, kind), cookie)
        st, body = _get("%s/api/%s?id=2" % (base, kind), cookie)
        if st == 200 and st_a == 200 and body != baseline:
            f.append({"id": "IDOR-%s" % kind[:4].upper(),
                      "name": "IDOR on /api/%s - account B's %s served to "
                              "account A" % (kind, what),
                      "severity": "critical" if kind != "profile" else "high",
                      "poc": "/api/%s?id=2  (Cookie: %s)" % (kind, cookie),
                      "evidence": "alice's session received a payload that "
                                  "is not her own record (differs from "
                                  "id=1 baseline, status %d) - bob's %s" %
                                  (st, what),
                      "fix": "authorize against the session: return the "
                             "record only when record.id == session.user_id "
                             "- the id parameter is a request, never a "
                             "permission."})
    return f


def demo():
    """attack -> report -> patch -> re-attack. the full cycle, again."""
    from cerberus_gate import bounty_report
    ok = True
    base, srv = vulnerable_app()
    f1 = attack(base)
    srv.shutdown()
    ok &= len(f1) >= 3
    print("  %-4s vulnerable range: %d idor findings" % (
        "PASS" if len(f1) >= 3 else "FAIL", len(f1)))
    pack = Path(__file__).resolve().parent.parent / "idor-lab-pack.md"
    bounty_report.write_report_pack(f1, pack, base)
    print("  %-4s submission pack written: %s" % ("PASS", pack.name))
    base, srv = patched_app()
    f2 = attack(base)
    srv.shutdown()
    ok &= len(f2) == 0
    print("  %-4s patched range: 0 findings - the gate holds" % (
        "PASS" if len(f2) == 0 else "FAIL"))
    # flip regression: the flip must persist across requests - the old
    # bug wrote the mode on the request instance, which dies with its
    # response, so the gate LOOKED flipped and still served bob.
    base, srv = vulnerable_app()
    st, _, hdr, _ = _login_raw(base, "alice")
    cookie = hdr.split(";")[0] if hdr else ""
    _get(base + "/?flip=1")
    st_p, _ = _get(base + "/api/orders?id=2", cookie)
    st_own, _ = _get(base + "/api/orders?id=1", cookie)
    srv.shutdown()
    flipped = (st_p == 403 and st_own == 200)
    ok &= flipped
    print("  %-4s flip the gate: B's order -> %d (want 403), "
          "own order -> %d (want 200)" % (
              "PASS" if flipped else "FAIL", st_p, st_own))
    print("idor lab: %s" % ("ALL PASS" if ok else "FAILURES PRESENT"))
    return 0 if ok else 1


def serve(secure=False):
    """Run the lab in the FOREGROUND so a human can open it in a browser.

    the daemon thread that demo() uses dies the moment the python
    process exits - which is exactly what happened when the one-liner
    printed a url and quit. serve() holds the main thread until Ctrl+C.
    """
    base, srv = _serve(secure=secure)
    print("idor lab live at %s  (mode: %s)" % (
        base, "PATCHED" if secure else "VULNERABLE"))
    print("window 1: %s/login?as=alice" % base)
    print("window 2 (incognito): %s/login?as=bob" % base)
    print("then from window 1, request: %s/api/orders?id=2" % base)
    print("flip the gate in the browser: %s/?flip=1" % base)
    print("press Ctrl+C to stop the lab.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
        print("lab closed. the range remembers.")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        sys.exit(serve(secure=("--secure" in sys.argv or
                               "--patched" in sys.argv)))
    sys.exit(demo())
