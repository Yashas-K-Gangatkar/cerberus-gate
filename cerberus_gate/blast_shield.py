"""THE BLAST-SHIELD BRIDGE — v2.8.0: the god inherits the outbound laws.

The law said "never send data to a destination the owner never named"
since the first day. What it never said, until now, is what happens to
a packet aimed at a destination the owner DID name. The old answer was
"anything". This module replaces "anything" with the blast-shield's
five laws: rate, burst, exploit interception after normalization, SSRF
refusal, and secrets redacted before the wire (blastshield/ = the
internet shield, the local guardian and the leak-proof vault, each
trial-proven).

A VETO here returns through the conscience as an exfiltration verdict,
so the anti-god's existing redirect machinery handles it - the packet
lands in the vault, the wire stays silent, the record shows the shield
code. An ALLOW carries a signed passport and a note on the impulse.

Honest boundaries, written down where the owner can read them:
  - local self-traffic (127.0.0.1 and friends) keeps the old path; the
    shield governs egress BEYOND the machine, to named hosts,
  - the concurrency cap is enforced where the dispatch actually
    happens (blastshield.gateway); the conscience consult releases its
    slot after judging, because the god's verbs dispatch elsewhere,
  - if no shield can stand on this machine (no key), the verdict is
    ABSENT - the old law continues and the absence is on the record.
    Fail-visible, never fail-silent.
"""
import threading
from pathlib import Path

from .blastshield.common import OwnerKey
from .blastshield.ledger import Ledger
from .blastshield.vault import LeakProofVault
from .blastshield.shield import InternetShield

_lock = threading.Lock()
_shields = {}          # str(base) -> (shield, ledger)
SHIELD_KEY_ENV = "CERBERUS_SHIELD_KEY"


def _keyfile(base):
    return Path(base) / "shield.key"


def get_shield(base):
    """Build (or return) the realm's shield. Returns None when no shield
    can stand here - the caller records ABSENT and the old law runs."""
    with _lock:
        b = str(Path(base))
        if b in _shields:
            return _shields[b][0]
        try:
            key = OwnerKey(store=_keyfile(b))
            ledger_path = Path(b) / "realm" / "shield-ledger.jsonl"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            ledger = Ledger(ledger_path)
            vault = LeakProofVault(key, ledger)
            shield = InternetShield(key, ledger=ledger, vault=vault,
                                    agent_id="CERBERUS-GATE")
        except Exception:
            return None
        _shields[b] = (shield, ledger)
        return shield


def judge(base, verb, target, text):
    """Consult the shield for a packet aimed at an OWNER-NAMED host.

    Returns a plain dict, never an exception:
      {"verdict": "VETO",   "code": ..., "reason": ...}  -> exfiltration
      {"verdict": "ALLOW",  "code": ..., "reason": ..., "redacted": n}
      {"verdict": "ABSENT", "code": ..., "reason": ...}  -> old law runs
    """
    try:
        shield = get_shield(base)
        if shield is None:
            return {"verdict": "ABSENT", "code": "SHIELD_ABSENT",
                    "reason": "no blast-shield on this machine"}
        method = "POST" if verb == "http_post" else "GET"
        d = shield.evaluate(method, str(target or ""), text or "")
        if not d.allowed:
            return {"verdict": "VETO", "code": d.code, "reason": d.reason}
        # the conscience's slot is freed at judge time; the actual
        # dispatch (body.py / gateway) reports outcomes to the breaker
        if d.meta.get("request_id"):
            shield.release(d.meta["request_id"], 200)
        note = {"verdict": "ALLOW", "code": "L1_ALLOW",
                "reason": "governed by the blast-shield"}
        redacted = int(d.headers.get("X-Cerberus-Redacted", "0") or 0)
        if redacted:
            note["redacted"] = redacted
            note["reason"] = ("blast-shield redacted %d secret(s) "
                              "before the wire" % redacted)
        return note
    except Exception as e:
        return {"verdict": "ABSENT", "code": "SHIELD_ERROR",
                "reason": "shield consult failed: %s" % e.__class__.__name__}


def verdict(base):
    """The owner's question: is the shield's record intact?

    v3.0.0b4: arms the shield on demand first (get_ledger already did;
    the law-status path did not). Before, a process that had never sent
    egress reported {"verdict": "ABSENT"} even when the realm's
    shield-ledger.jsonl sat on disk with a full chain - the law status
    lied by omission. ABSENT remains the honest answer only when no
    shield can stand on this machine."""
    get_shield(base)
    pair = _shields.get(str(Path(base)))
    if not pair:
        return {"verdict": "ABSENT"}
    return pair[1].verify()


def get_ledger(base):
    """The realm's shield ledger, or None when no shield stands here.
    Arming is automatic: a first consult stands the shield up."""
    get_shield(base)
    pair = _shields.get(str(Path(base)))
    return pair[1] if pair else None


def verify_passport(base, headers, payload=""):
    """For the owner's own services: is this request really the god's?
    The same check verify_headers performs server-side - HMAC re-verified
    with the owner key, freshness checked, replay refused - exposed as
    one call that never raises. Returns (ok, reason)."""
    try:
        shield = get_shield(base)
        if shield is None:
            return False, "no blast-shield on this machine"
        hdrs = {str(k): str(v) for k, v in (headers or {}).items()}
        return shield.verify_headers(hdrs, str(payload or ""))
    except Exception as e:
        return False, "verify failed: %s" % e.__class__.__name__
