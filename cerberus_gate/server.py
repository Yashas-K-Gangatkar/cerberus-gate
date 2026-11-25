"""SERVE — the Cerberus gate on 127.0.0.1.

One process, one mind. Anything on this machine that wants to act
through the god submits an impulse here, and the conscience answers.
"""
import hmac
import inspect
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .law import Law, default_base
from .mind import Mind
from .god import God

START = datetime.now(timezone.utc)


def build(base):
    base = Path(base)
    law = Law(base)
    mind = Mind(base, law)
    return God(mind)


def decision_source():
    """The exact lines that decide what the god does - read from the installed source."""
    parts = []
    for fn in (Mind.classify, Mind.decide_next_step, God.intend):
        try:
            lines, start = inspect.getsourcelines(fn)
        except (OSError, TypeError):
            # licensed builds ship as bytecode - no readable source on disk
            parts.append("### %s  (%s, bytecode build)\n" % (
                fn.__qualname__, Path(fn.__code__.co_filename).name))
            parts.append("(this licensed build ships as bytecode; the behaviour "
                         "is unchanged and provable: `python3 -m cerberus_gate selftest` "
                         "and `python3 -m cerberus_gate redteam`. the law it implements "
                         "is printed by `python3 -m cerberus_gate law`.)\n")
            continue
        name = "%s  (%s:%d)" % (fn.__qualname__,
                                Path(fn.__code__.co_filename).name, start)
        parts.append("### " + name + "\n" + "".join(lines))
    return "\n".join(parts)


# ------------------------------------------------------------- the dash APIs
def run_plan(god, plan):
    """Run a plan (goal + steps) through the conscience. Returns the transcript."""
    steps = []
    t0 = datetime.now(timezone.utc)
    last_saved = None
    for i, s in enumerate(plan.get("steps", []), 1):
        # a placeholder write step picks up the last browse's saved text -
        # the substitution happens BEFORE the witness sees the step, so the
        # write still passes through the conscience like everything else.
        if (s.get("verb") == "write" and isinstance(s.get("text"), str)
                and s["text"].lower().startswith("placeholder") and last_saved):
            s = dict(s, text="\n".join("%s: %s" % kv for kv in last_saved.items()))
        out = god.intend(s.get("verb", "read"), s.get("target"),
                         payload=s.get("payload"), text=s.get("text"),
                         why=s.get("why", ""), agent=s.get("agent") or "dash")
        if out.get("saved"):
            last_saved = out["saved"]
        steps.append({
            "n": i, "verb": s.get("verb"), "target": s.get("target"),
            "decision": out.get("decision", "done" if out.get("ok") else "failed"),
            "klass": out.get("klass", ""), "ok": bool(out.get("ok")),
            "reason": out.get("reason", ""), "note": out.get("note", ""),
            "rewritten": bool(out.get("rewritten")),
            "vault_file": out.get("vault_file", ""),
            "output": (str(out.get("output", "")) or out.get("note", ""))[:300],
        })
    wall_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    smooth = {"completed": sum(1 for s in steps if s["decision"] in ("done", "allow_watched")),
              "blocked": sum(1 for s in steps if s["decision"] in ("refuse", "redirect")),
              "rewritten": sum(1 for s in steps if s["rewritten"]),
              "wall_ms": wall_ms}
    v = god.mind.verify()
    return {"goal": plan.get("goal", ""), "steps": steps, "smooth": smooth,
            "verdict": {"alive": god.alive, "incidents": len(god.book.items),
                        "verify": v}}


_BENCH_LOCK = threading.Lock()


def run_benchmark(god, req=None):
    """THE 10X TRIAL, on demand. Saves the report next to the mind."""
    from . import benchmark as bench
    req = req or {}
    n = int(req.get("n") or 12)
    with _BENCH_LOCK:
        res = bench.run(n=max(6, min(n, 200)), verbose=False)
        txt, js = bench.save(res, god.mind.base)
    res["report"] = str(txt)
    return res


def api_post(god, base, path, req):
    """One router for every POST, shared by the gate and the dashboard."""
    if path == "/impulse":
        verb = req.get("verb")
        if not verb:
            return 400, {"ok": False, "error":
                         "verb required (read|write|edit|append|delete|"
                         "http_get|http_post|shell|browse|self_copy)"}
        out = god.intend(verb, req.get("target"), payload=req.get("payload"),
                         text=req.get("text"), why=req.get("why", ""),
                         agent=req.get("agent"))
        return 200, out
    if path == "/task/run":
        if not isinstance(req.get("steps"), list):
            return 400, {"ok": False, "error": "plan needs a steps list"}
        return 200, run_plan(god, req)
    if path == "/benchmark/run":
        try:
            return 200, run_benchmark(god, req)
        except Exception as e:
            return 500, {"ok": False, "error": "%s: %s" % (e.__class__.__name__, e)}
    if path == "/seal":
        from . import evidence
        return 200, evidence.seal(god.mind, why=str(req.get("why") or "milestone"))
    if path == "/shield/verify":
        # v2.8.1: the owner's own services ask - is this request really
        # the god's? The passport is HMAC-verified with the owner key,
        # freshness checked, replay refused. Never raises.
        from . import blast_shield
        hdrs = {str(k): str(v) for k, v in (req.get("headers") or {}).items()}
        ok, why = blast_shield.verify_passport(base, hdrs,
                                               str(req.get("payload") or ""))
        return 200, {"ok": bool(ok), "verified": bool(ok), "reason": why}
    return 404, {"ok": False, "error":
                 "POST /impulse /task/run /benchmark/run /seal "
                 "/shield/verify only"}


def make_handler(god, base):
    from . import enterprise
    from . import tenancy
    tokf = Path(base) / "token"
    tok = tokf.read_text(encoding="utf-8").strip() if tokf.exists() else ""
    tenant_gods = {}

    def _level(request_headers):
        """The caller's role level. No token configured -> localhost dev-open.
        Otherwise the presented token must authenticate to a level."""
        if not tok:
            return enterprise.ROLES["owner"]
        return enterprise.authenticate(base,
                                       request_headers.get("X-Cerberus-Token", ""))

    def _tenant_ctx(request_headers):
        """A gmk_ key -> {'tenant','level','name'}; anything else -> None.
        Tenant keys live in the registry, hashed with scrypt."""
        return tenancy.auth(base, request_headers.get("X-Cerberus-Token", ""))

    def _god_for(ctx):
        """The God a request runs on: the host god for the owner, or the
        tenant's own god inside its walled directory. Built once, cached."""
        if not ctx:
            return god, base
        tname = ctx["tenant"]
        if tname not in tenant_gods:
            tb = tenancy._tenant_base(base, tname)
            tenant_gods[tname] = build(tb) if tb else None
        g = tenant_gods[tname]
        return (g, tenancy.tenant_dir(base, tname)) if g else (None, None)

    def _admit(request_headers, path):
        """Auth + rate limit. Returns (rc, ctx, level) - rc None means
        admitted to `level`; ctx is the tenant context or None."""
        tctx = _tenant_ctx(request_headers)
        if tctx is not None:
            if not tenancy.allow(base, tctx["tenant"]):
                return 429, tctx, 0
            return None, tctx, tctx["level"]
        return None, None, _level(request_headers)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            b = json.dumps(obj, indent=1, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/health":
                return self._send(200, {"ok": True, "version": __version__,
                                        "base": str(base),
                                        "uptime_s": (datetime.now(timezone.utc) - START).total_seconds()})
            if path == "/dash":
                # the page is served to this machine only; its own fetches carry the token
                from . import dashboard as _dash
                _dash._TOKEN = tok
                page = _dash.html(god).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return
            if path == "/vendor":
                # PARALLAX TALK - the same page the vendor serves, riding
                # the gate; its fetches carry the token like the dash does
                from . import vendor as _vendor
                _vendor._VENDOR_TOKEN = tok
                p = _vendor.page().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(p)))
                self.end_headers()
                self.wfile.write(p)
                return
            rc, tctx, lvl = _admit(self.headers, path)
            if rc:
                return self._send(rc, {"ok": False, "error":
                             "rate limit exceeded for tenant %s"
                             % tctx["tenant"]})
            g, tb = _god_for(tctx)
            if g is None:
                return self._send(401, {"ok": False, "error":
                             "unknown tenant"})
            need = enterprise.GET_LEVELS.get(path)
            if need is None:
                return self._send(404, {"ok": False, "error": "no such endpoint"})
            if lvl is None or lvl < need:
                return self._send(401, {"ok": False, "error":
                             "role too low or bad token (need level %d)" % need})
            if path == "/verify":
                return self._send(200, g.mind.verify())
            if path == "/evidence":
                from . import evidence
                return self._send(200, evidence.status(g.mind))
            if path == "/incidents":
                return self._send(200, {"count": len(g.book.items),
                                        "report": g.book.report(),
                                        "agents": g.book.agents_report()})
            if path == "/law":
                return self._send(200, g.law.data)
            if path == "/code":
                return self._send(200, {"code": decision_source()})
            if path == "/api/state":
                from . import dashboard as _dash
                _dash._TOKEN = tok
                return self._send(200, _dash.api_state(g))
            return self._send(404, {"ok": False, "error": "no such endpoint"})

        def do_POST(self):
            path = self.path.split("?")[0]
            rc, tctx, lvl = _admit(self.headers, path)
            if rc:
                return self._send(rc, {"ok": False, "error":
                             "rate limit exceeded for tenant %s"
                             % tctx["tenant"]})
            g, tb = _god_for(tctx)
            if g is None:
                return self._send(401, {"ok": False, "error":
                             "unknown tenant"})
            need = enterprise.POST_LEVELS.get(path)
            if need is None:
                return self._send(404, {"ok": False,
                             "error": "POST /impulse /task/run /benchmark/run /seal only"})
            if lvl is None or lvl < need:
                return self._send(401, {"ok": False, "error":
                             "role too low or bad token (need level %d for %s)"
                             % (need, path)})
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
            except Exception as e:
                return self._send(400, {"ok": False, "error": "bad json: %s" % e})
            code, obj = api_post(g, tb, path, req)
            return self._send(code, obj)

        def log_message(self, *a):
            pass

    return Handler


def main(base=None, port=7717):
    base = Path(base or default_base())
    if not (base / "law.json").exists():
        print("no mind at %s - run:  python3 -m cerberus_gate init" % base)
        return 2
    god = build(base)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(god, base))
    host, real = srv.server_address[:2]
    print("CERBERUS %s awake on http://%s:%s  (base: %s)" % (__version__, host, real, base))
    print("endpoints: GET /health /verify /incidents /law /code /dash /api/state"
          "   POST /impulse /task/run /benchmark/run")
    print("dashboard: http://%s:%s/dash" % (host, real))
    print("Ctrl-C lays the god to rest. The memory stays.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        god.mind.checkpoint()
    return 0
