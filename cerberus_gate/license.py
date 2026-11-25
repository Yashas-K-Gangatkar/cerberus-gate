"""license - customers pay, the founder keeps the engine.

The distribution rule:
  - the customer bundle is a plugin they install and connect, never a repo;
  - the gate / dashboard / MCP / ollama bridge run in TRIAL mode for 14 days,
    then refuse to start until a license key is activated;
  - keys are issued by the founder's machine (`license issue`), signed with the
    founder's master key (~/.cerberus.master - never ships);
  - evidence stays readable even after expiry: verify / incidents / export
    always work, so compliance never loses the record.

Honesty note (documented in SELL.md): a client-side license check is a lock on
the door, not a bank vault. The real protection is the update stream, the
incident book, per-customer watermarked builds, and support. The fully sealed
option is the hosted gate (your server, their config snippet) - next rung.
"""
import datetime
import hmac
import json
import os
import re
import secrets
from pathlib import Path

TRIAL_DAYS = 14
KEY_RE = re.compile(r"^CB-[0-9A-F]{10}$")


def _home(home=None):
    return Path(home) if home else Path.home()


def license_file(home=None):
    return _home(home) / ".cerberus.license"


def trial_file(home=None):
    return _home(home) / ".cerberus.trial"


def master_file(home=None):
    return _home(home) / ".cerberus.master"


def _today():
    return datetime.date.today()


def _read_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(p, data):
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        p.chmod(0o600)
    except Exception:
        pass


def ensure_master(home=None):
    """Forge the founder's signing key once. This file NEVER ships."""
    m = master_file(home)
    if not m.exists():
        m.write_bytes(secrets.token_bytes(32))
        try:
            m.chmod(0o600)
        except Exception:
            pass
    return m


def _sign(master_path, message):
    return hmac.new(master_path.read_bytes(), message.encode("utf-8"),
                    "sha256").hexdigest()[:10].upper()


def issue(name, days=7, home=None):
    """Founder only: mint a license key bound to name + expiry date."""
    if not name or not str(name).strip():
        raise ValueError("a license needs the customer's name")
    expires = (_today() + datetime.timedelta(days=int(days))).isoformat()
    m = ensure_master(home)
    key = "CB-" + _sign(m, "%s|%s" % (str(name).strip(), expires))
    return {"name": str(name).strip(), "key": key, "expires": expires,
            "days": int(days)}


def activate(key, name, expires=None, home=None):
    """Customer only: store the key the founder sent, with its expiry."""
    key = (key or "").strip().upper()
    name = (name or "").strip()
    if not KEY_RE.match(key):
        return {"ok": False, "error": "that key does not look like a "
                "Cerberus key (expected CB-XXXXXXXXXX)"}
    if not name:
        return {"ok": False, "error": "the key was issued to a name - "
                "activate it with that exact name"}
    if not expires:
        # v3.0.0 fix: activating without --expires used to silently become a
        # 14-day trial - a customer who pasted only the key got a license
        # that died in two weeks with no warning. Refuse instead: the expiry
        # is half of the signed fact (name|expires), so demanding it here is
        # also what makes the founder-machine verification below possible.
        return {"ok": False,
                "error": "activate needs --expires YYYY-MM-DD (exactly as the "
                         "founder sent it). Without it this used to silently "
                         "become a %d-day trial - that trap is gone."
                         % TRIAL_DAYS}
    try:
        exp = datetime.date.fromisoformat(str(expires).strip())
    except ValueError:
        return {"ok": False, "error": "expiry must be YYYY-MM-DD"}
    if exp < _today():
        return {"ok": False, "error": "that key expired on %s - "
                "ask the founder for a fresh one" % exp.isoformat()}
    m = master_file(home)
    if m.exists():
        # where the master key lives (the founder's machine) a key is
        # verified for real - this is how support proves a key is genuine
        expected = "CB-" + _sign(m, "%s|%s" % (name, exp.isoformat()))
        if not hmac.compare_digest(expected, key):
            return {"ok": False, "error": "that key is not genuine for "
                    "this name and expiry"}
    _write_json(license_file(home),
                {"name": name, "key": key, "expires": exp.isoformat(),
                 "activated": datetime.datetime.now().isoformat(timespec="seconds")})
    return {"ok": True, "name": name, "expires": exp.isoformat()}


def status(home=None):
    """One dict: what mode is this machine in, and how long is left."""
    lic = _read_json(license_file(home))
    exp_s = lic.get("expires")
    if lic.get("key") and exp_s:
        try:
            exp = datetime.date.fromisoformat(exp_s)
            days = (exp - _today()).days
            if days >= 0:
                return {"mode": "licensed", "name": lic.get("name", ""),
                        "expires": exp_s, "days_left": days}
            return {"mode": "expired", "name": lic.get("name", ""),
                    "expires": exp_s, "days_left": 0}
        except ValueError:
            pass
    t = _read_json(trial_file(home))
    started = t.get("started")
    if started:
        try:
            s = datetime.date.fromisoformat(str(started)[:10])
            days = TRIAL_DAYS - (_today() - s).days
            if days > 0:
                return {"mode": "trial", "days_left": days}
            return {"mode": "trial-ended", "days_left": 0}
        except ValueError:
            pass
    _write_json(trial_file(home), {"started": _today().isoformat()})
    return {"mode": "trial", "days_left": TRIAL_DAYS}


def check(home=None):
    """(ok, message) - the gate calls this before it starts serving."""
    if os.environ.get("CERBERUS_LICENSE", "").lower() == "off":
        return True, "license check off (CERBERUS_LICENSE=off)"
    s = status(home)
    if s["mode"] == "licensed":
        return True, "licensed to %s until %s (%d days left)" % (
            s["name"], s["expires"], s["days_left"])
    if s["mode"] == "trial":
        return True, ("TRIAL: %d days left - activate with: "
                      "python3 -m cerberus_gate license activate KEY \"NAME\" "
                      "--expires YYYY-MM-DD" % s["days_left"])
    return False, ("the trial has ended. ask the founder for a key, then: "
                   "python3 -m cerberus_gate license activate KEY \"NAME\" --expires YYYY-MM-DD "
                   "(evidence stays readable: verify, incidents, export always work)")


def guard(home=None):
    """0 = start the service, 2 = refuse. Prints one honest line."""
    ok, msg = check(home)
    print(msg)
    return 0 if ok else 2
