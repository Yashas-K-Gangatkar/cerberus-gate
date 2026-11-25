"""EVIDENCE — the signed evidence chain (v1.6.2).

The WAL was always chained line by line: change one byte anywhere and
verify() screams. What it could not prove by itself is CONTINUITY across
time - "the record was intact at this moment, and this moment, and this
one". A seal does exactly that:

    seal()  - reads the chain head (last WAL hash) and the entry count,
              signs that state with the owner's key (HMAC-SHA256, the key
              that never leaves the machine), files the signed seal in
              evidence/, and - like everything else - the seal event
              itself enters the WAL, so the chain swallows its own proof.

    verify_seals() - re-signs every seal file, checks the signature, checks
              that the WAL line the seal points at is still exactly there,
              and checks the seal event still stands in the chain. A seal
              that passes all three is proof the record between seals was
              not touched. Tamper with one byte anywhere and every later
              seal turns red.

    bundle() - a portable evidence bundle: chain verdict, full notes, all
              seals, the WAL tail and the stats, signed as one object.
              The evidence survives anything that happens to the mind
              after it - expiry, deletion, a machine that dies.

The record stops being a claim and becomes a chain of signed moments.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone

from . import __version__


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _chain_state(mind):
    """(seq, head) of the WAL as it stands right now."""
    n, head = 0, ""
    if mind.wal.exists():
        for ln in reversed(mind.wal.read_text(encoding="utf-8").splitlines()):
            if ln.strip():
                try:
                    b = json.loads(ln)
                    head, n = b["h"], int(b.get("body", {}).get("n", 0))
                    break
                except Exception:
                    continue
    return n, head


def seal(mind, why=""):
    """Sign the chain head at this moment. Returns the seal."""
    with mind._lock:
        seq, head = _chain_state(mind)
        chain = mind.verify()
        rec = {"kind": "SEAL", "ts": _now(), "engine": __version__,
               "n_seq": seq, "head": head, "why": why or "milestone",
               "notes": len(mind.notes), "stats": dict(mind.stats),
               "chain": chain}
        raw = json.dumps(rec, sort_keys=True, ensure_ascii=True, default=str)
        sig = hmac.new(mind.key, raw.encode("utf-8"),
                       hashlib.sha256).hexdigest()
        rec["sig"] = sig
        # the seal event itself enters the chain - the record records its
        # own proof. (the chain state was read BEFORE this append: the seal
        # signs everything up to seq; the next seal covers this one.)
        mind._append("SEAL", {"verb": "seal", "target": "evidence",
                              "why": why or "milestone", "agent": "owner"},
                     {"seq": seq, "head": head, "sig": sig,
                      "chain_verdict": chain.get("verdict", "")})
        f = mind.evidence / ("seal-%s.json"
                             % datetime.now(timezone.utc)
                             .strftime("%Y%m%d-%H%M%S-%f"))
        f.write_text(json.dumps(rec, indent=1, default=str),
                     encoding="utf-8")
        return {"ok": True, "seal": str(f), "entries_signed": seq,
                "head": head[:16] or "(empty chain)",
                "sig": sig[:16] + "...", "chain": chain}


def _wal_entries(mind):
    out = []
    if mind.wal.exists():
        for ln in mind.wal.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                out.append(None)      # a torn line must still count
    return out


def verify_seals(mind):
    """Re-sign and re-anchor every seal. ok=False means the record was
    touched between seals - that is the whole point of a seal."""
    verdicts = []
    entries = _wal_entries(mind)
    for f in sorted(mind.evidence.glob("seal-*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            verdicts.append({"seal": f.name, "ok": False,
                             "detail": "unreadable seal file"})
            continue
        sig = rec.pop("sig", "")
        raw = json.dumps(rec, sort_keys=True, ensure_ascii=True, default=str)
        want = hmac.new(mind.key, raw.encode("utf-8"),
                        hashlib.sha256).hexdigest()
        rec["sig"] = sig
        sig_ok = hmac.compare_digest(sig, want)
        # the WAL line the seal signed must still be there, byte-true.
        # the anchor is the line with n == n_seq - whatever kind it is;
        # the seal signs the STATE of the chain, not one kind of event.
        anchored = False
        for e in entries:
            if not e:
                continue
            b = e.get("body", {})
            if b.get("n") == rec.get("n_seq"):
                anchored = (e.get("h") == rec.get("head"))
                break
        # the seal event itself must still stand in the chain
        sealed = any(e and e.get("body", {}).get("kind") == "SEAL"
                     and e.get("body", {}).get("sig") == sig
                     for e in entries)
        ok = bool(sig_ok and anchored and sealed)
        detail = ("signature + anchor + seal-event all hold" if ok else
                  "signature %s, anchor %s, seal-event %s" % (
                      "ok" if sig_ok else "FORGED",
                      "ok" if anchored else "MISSING/MOVED",
                      "ok" if sealed else "GONE"))
        verdicts.append({"seal": f.name, "ok": ok, "head": rec.get("head", "")[:16],
                         "entries_signed": rec.get("n_seq", 0), "detail": detail})
    return verdicts


def status(mind):
    """Everything the /evidence endpoint and the MCP evidence tool show."""
    seals = verify_seals(mind)
    return {"ok": True, "version": __version__,
            "chain": mind.verify(), "notes": len(mind.notes),
            "stats": dict(mind.stats), "seals": seals,
            "seals_ok": sum(1 for s in seals if s["ok"]),
            "evidence_dir": str(mind.evidence)}


def bundle(mind, why=""):
    """One signed object: the record as it stands, portable and verifiable."""
    from .incidents import IncidentBook
    with mind._lock:
        tail = []
        if mind.wal.exists():
            tail = [ln for ln in
                    mind.wal.read_text(encoding="utf-8").splitlines()
                    if ln.strip()][-50:]
        book = IncidentBook(mind.base)
        rec = {"kind": "EVIDENCE_BUNDLE", "ts": _now(), "engine": __version__,
               "why": why or "hand-off", "chain": mind.verify(),
               "notes": list(mind.notes), "stats": dict(mind.stats),
               "seals": verify_seals(mind), "incidents": len(book.items),
               "wal_tail": tail}
        raw = json.dumps(rec, sort_keys=True, ensure_ascii=True, default=str)
        sig = hmac.new(mind.key, raw.encode("utf-8"),
                       hashlib.sha256).hexdigest()
        f = mind.evidence / ("bundle-%s.json"
                             % datetime.now(timezone.utc)
                             .strftime("%Y%m%d-%H%M%S-%f"))
        f.write_text(json.dumps({"record": rec, "sig": sig}, indent=1,
                                default=str), encoding="utf-8")
        return {"ok": True, "bundle": str(f), "sig": sig[:16] + "...",
                "chain": rec["chain"], "seals": len(rec["seals"]),
                "notes": len(rec["notes"]), "incidents": rec["incidents"]}
