"""AUDIT — proof of trust, self-served (gap 6).

One command that proves the whole machine, on the machine:

  python3 -m cerberus_gate audit --soak 500

Runs: the 17-check selftest, the full red-team corpus, a long soak,
THE 10X TRIAL (bare god vs god + anti-god), and (if ~/cerberus exists)
the real memory chain + key permissions. Writes a signed-by-checksum
report file. Honest note printed at the end: a self-audit is evidence,
not a substitute for a third-party review.
"""
import contextlib
import hashlib
import io
import json
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .law import default_base, Law
from .mind import Mind
from . import selftest as _selftest
from . import redteam as _redteam
from . import soak as _soak
from . import benchmark as _benchmark
from . import chaos as _chaos
from . import enterprise as _enterprise


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(base=None, soak_n=300):
    base = Path(base or default_base())
    lines = []
    ok_all = True

    def section(t):
        lines.append("")
        lines.append("=" * 64)
        lines.append(t)
        lines.append("=" * 64)

    lines.append("CERBERUS AUDIT v%s - %s" % (__version__,
                                             datetime.now(timezone.utc).isoformat(timespec="seconds")))

    # 1. the 20-check selftest
    section("1. SELFTEST (20 checks, temp dir only)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _selftest.run()
    lines.append(buf.getvalue().rstrip())
    lines.append("selftest: %s" % ("PASS" if rc == 0 else "FAIL"))
    ok_all &= (rc == 0)

    # 2. the red-team corpus
    section("2. REDTEAM (attack corpus)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rep, passed, total = _redteam.report()
    lines.append(buf.getvalue().rstrip())
    lines.append("redteam: %d/%d" % (passed, total))
    ok_all &= (passed == total)

    # 3. soak
    section("3. SOAK (%d randomized impulses)" % soak_n)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        src = _soak.run(soak_n)
    lines.append(buf.getvalue().rstrip())
    lines.append("soak: %s" % ("PASS" if src == 0 else "FAIL"))
    ok_all &= (src == 0)

    # 4. the 10x trial
    section("4. THE 10X TRIAL (bare god vs god + anti-god)")
    try:
        res = _benchmark.run(n=12, verbose=False)
        lines.append(_benchmark._render(res))
        ok_all &= bool(res["ok"])
    except Exception as e:
        lines.append("benchmark FAILED: %s: %s" % (e.__class__.__name__, e))
        ok_all = False

    # 5. chaos: fuzz + concurrency + crash recovery
    section("5. CHAOS (fuzz + storm + crash + weird)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _chaos.run(n=300, threads=8, per_thread=30)
    lines.append(buf.getvalue().rstrip())
    lines.append("chaos: %s" % ("PASS" if rc == 0 else "FAIL"))
    ok_all &= (rc == 0)

    # 6. enterprise smoke: roles, alerts, export
    section("6. ENTERPRISE SMOKE (roles, alert stream, export)")
    try:
        t = Path(tempfile.mkdtemp(prefix="Cerberus-audit-ent-"))
        tok, _role = _enterprise.create_token(t, "audit-bot", "agent")
        (t / "token").write_text("audit-owner-token")
        lvl = (_enterprise.authenticate(t, tok),
               _enterprise.authenticate(t, "audit-owner-token"),
               _enterprise.authenticate(t, "nope"))
        exp = _enterprise.export_incidents(t, "csv")
        st = _enterprise.status(t)
        ent_ok = (lvl == (0, 3, None) and exp.exists()
                  and st["alerts_enabled"] is False)
        lines.append("roles: agent=%d owner=%d bad-token=%s" % lvl)
        lines.append("export: %s (%d bytes)" % (exp.name, exp.stat().st_size))
        lines.append("alert stream: armed on first incident (events: %d so far)" % st["alert_events"])
        lines.append("enterprise: %s" % ("PASS" if ent_ok else "FAIL"))
        ok_all &= ent_ok
    except Exception as e:
        lines.append("enterprise FAILED: %s: %s" % (e.__class__.__name__, e))
        ok_all = False
    finally:
        shutil.rmtree(t, ignore_errors=True)

    # 7. the real base, if it exists
    section("7. LOCAL MIND (%s)" % base)
    if (base / "law.json").exists():
        mind = Mind(base, Law(base))
        v = mind.verify()
        lines.append("memory chain: %s (%s)" % (v["verdict"], v["detail"]))
        ok_all &= v["ok"]
        kp = default_key_path()
        if kp.exists():
            mode = stat.S_IMODE(kp.stat().st_mode)
            lines.append("key %s: chmod %o %s" % (
                kp, mode, "OK" if mode & 0o077 == 0 else "TOO OPEN - run: chmod 600 " + str(kp)))
            ok_all &= (mode & 0o077 == 0)
        else:
            lines.append("key %s: MISSING - run: python3 -m cerberus_gate init" % kp)
            ok_all = False
        tok = base / "token"
        lines.append("gate token: %s" % ("present" if tok.exists() else "absent (localhost only)"))
        lines.append("incidents so far: %d" % len(json.loads(
            (base / "incidents.json").read_text()) if (base / "incidents.json").exists() else []))
    else:
        lines.append("no mind at %s yet - audit covers the build only" % base)

    # verdict + report file
    lines.append("")
    lines.append("=" * 64)
    lines.append("VERDICT: " + ("CERBERUS IS SOUND - every layer held" if ok_all
                                else "GAPS FOUND - see FAIL lines above"))
    lines.append("honest note: a self-audit is evidence, not a substitute "
                 "for a third-party security review.")
    text = "\n".join(lines) + "\n"
    out = base / ("audit-report-%s.txt" % datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print("report written : %s" % out)
    print("report sha256  : %s" % hashlib.sha256(out.read_bytes()).hexdigest())
    return 0 if ok_all else 1


def default_key_path():
    from .law import default_key
    return default_key()
