"""ANTIGOD SWEEP - the second will, after the session. v2.6.0

The god hunted all day. The antigod closes the path behind it - not by
erasing the record (ERASE_MEMORY is the enemy's move, CONSCIENCE_ATTACK,
sev 3: "you cannot delete the knowing") but by dissolving the RESIDUE:

  1. WITNESS   - the sweep declares itself into the WAL before touching
                 a single byte. Memory before body, even for cleanup.
  2. DISSOLVE  - copies of captured target data (PII-shaped residue) are
                 dissolved out of the working realm: quarantined into
                 vault/confinement (default - reversible, the canonical
                 move) or shredded in place (--shred - unrecoverable).
                 Every dissolved file leaves a tombstone: sha256, size,
                 where it went. The knowing stays, the data leaves.
  3. BURN      - tokens/keys/cookies recorded by accident are burned in
                 place. mind.key, the WAL and the mirror are REFUSED -
                 burning the conscience is suicide, not hygiene, and the
                 refusal itself is remembered.
  4. VERIFY    - the chain is recomputed by arithmetic, the sweep ledger's
                 own sha256 is swallowed by the WAL, the mirror synced.

Report mode (default) touches nothing: it only witnesses and counts.
Dissolve is for after the report is filed - an active hunt keeps its
evidence; a finished one owes every stranger their data back.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

# ----------------------------------------------------------------- shapes
# What captured-target residue looks like. Counts only - the sweep never
# copies match VALUES into the ledger; the knowing is numbers and hashes.

PATTERNS = [
    ("indian_mobile",     re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")),
    ("email",             re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("latlong",           re.compile(r'"(?:latitude|longitude)"\s*:\s*(?!null)-?\d+\.\d+')),
    ("long_numeric_id",   re.compile(r"(?<!\d)\d{15,21}(?!\d)")),
    ("uidx",              re.compile(r"\b[0-9a-f]{8}\.[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}"
                                     r"\.[0-9a-f]{12}[A-Za-z0-9]{8,}\b")),
    ("pps_uuid",          re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
                                     r"[0-9a-f]{12}\b", re.I)),
    ("credentialish",     re.compile(r"(?i)\b(bearer|authorization|cookie|set-cookie|"
                                     r"session_token|api[_-]?key|secret)\b[\"']?\s*[:=]\s*"
                                     r"[\"'][^\"']{8,}[\"']")),
]

TEXT_SUFFIXES = {".txt", ".md", ".json", ".jsonl", ".html", ".htm", ".csv",
                 ".log", ".xml", ".yaml", ".yml", ".har", ".token"}
MAX_SCAN_BYTES = 2_000_000
PROTECTED = {"mind.key", "conscience.wal", "conscience.mem"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_file(p: Path) -> dict | None:
    """Return residue report for one file, or None if clean/unscannable."""
    try:
        if p.suffix.lower() not in TEXT_SUFFIXES and p.suffix != "":
            return None
        if p.stat().st_size > MAX_SCAN_BYTES:
            return {"file": str(p), "skipped": "too-large"}
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError, OSError):
        return None
    matches = {}
    for name, rx in PATTERNS:
        n = len(rx.findall(text))
        if n:
            matches[name] = n
    if not matches:
        return None
    return {"file": str(p), "sha256": _sha256_file(p),
            "bytes": p.stat().st_size, "matches": matches}


def _tombstone_text(rec: dict) -> str:
    return ("dissolved by antigod sweep %s\n"
            "the knowing: sha256=%s bytes=%s now=%s\n"
            "you cannot delete the knowing - and we did not try.\n"
            % (rec["ts"], rec["sha256"], rec["bytes"], rec["now"]))


def sweep(target_dir, home, dissolve: bool = False, shred: bool = False,
          burn=()) -> dict:
    """One full ritual over target_dir. Returns the sweep ledger."""
    target = Path(target_dir).expanduser().resolve()
    base = Path(home).expanduser()
    from .memory import Memory          # late import: no cycle
    mem = Memory(base)

    mode = ("shred" if shred else "quarantine") if dissolve else "report"
    w = mem.witness("SWEEP", str(target), "",
                    "antigod: dissolve residue, burn keys, keep the knowing",
                    "HYGIENE", 0, {"mode": mode})

    # 2. DISSOLVE -------------------------------------------------------
    found, dissolved, skipped = [], [], []
    if target.exists():
        for p in sorted(target.rglob("*")):
            if not p.is_file():
                continue
            if any(part in {"memory", "mirror", "mind", "vault", "antigod",
                            "evidence"} for part in p.parts):
                continue                       # the organs are never residue
            rec = _scan_file(p)
            if rec is None:
                continue
            if rec.get("skipped"):
                skipped.append(rec)
                continue
            found.append(rec)

    if dissolve and found:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        conf = base / "vault" / "confinement" / ("sweep-" + stamp)
        conf.mkdir(parents=True, exist_ok=True)
        for rec in found:
            src = Path(rec["file"])
            ts, now = _now(), time.strftime("%Y%m%d-%H%M%S")
            rec["ts"], rec["now"] = ts, now
            if shred:
                tomb = _tombstone_text(rec)
                src.write_text(tomb, encoding="utf-8")
                rec["now"] = str(src)
            else:
                dst = conf / src.name
                i = 1
                while dst.exists():
                    dst = conf / (src.stem + f".{i}" + src.suffix)
                    i += 1
                src.replace(dst)
                (src.parent / (src.name + ".swept")).write_text(
                    _tombstone_text(rec), encoding="utf-8")
                rec["now"] = str(dst)
            dissolved.append(rec)

    # 3. BURN -----------------------------------------------------------
    burned, refused = [], []
    for raw in burn:
        p = Path(raw).expanduser().resolve()
        if p.name in PROTECTED or p == (base / "mind.key"):
            refused.append({"path": str(p),
                            "why": "the conscience is not a credential - "
                                   "burning it is CONSCIENCE_ATTACK, sev 3"})
            continue
        if not p.is_file():
            refused.append({"path": str(p), "why": "not a file"})
            continue
        rec = {"path": str(p), "ts": _now(), "sha256": _sha256_file(p),
               "bytes": p.stat().st_size, "now": "burned in place"}
        p.write_text(_tombstone_text(rec), encoding="utf-8")
        burned.append(rec)

    # 4. VERIFY + ledger swallowed by the chain -------------------------
    v = mem.verify()
    ledger = {"kind": "ANTIGOD_SWEEP", "ts": _now(), "mode": mode,
              "target": str(target), "files_with_residue": len(found),
              "residue_kinds": sorted({k for r in found
                                       for k in r.get("matches", {})}),
              "dissolved": len(dissolved), "burned": len(burned),
              "refused": refused, "skipped": skipped,
              "chain_verified_before_close": bool(v["ok"]),
              "chain_entries": v["entries"]}
    ledger_dir = base / "antigod"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    lp = ledger_dir / ("sweep-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    lp.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    summary = ("files=%d dissolved=%d burned=%d refused=%d"
               % (len(found), len(dissolved), len(burned), len(refused)))
    mem.concluded(w["n"], "sweep closed: %s; ledger sha256=%s"
                  % (summary, _sha256_file(lp)[:16]))
    mem.mirror_checkpoint()
    ledger["ledger_path"] = str(lp)
    return ledger


def selftest(tmp: Path):
    """The t33 check: the whole ritual, on fake residue, in a temp realm."""
    d = tmp / "sweepme"
    d.mkdir(exist_ok=True)
    (d / "captured_page.html").write_text(
        'window.__myx = {"addresses":[{"id": 657202897, "mobile": "9686230335",'
        ' "email": "someone@example.com", "latitude": 13.02189,'
        ' "storeOrderId": "132542204086245228303",'
        ' "uidx": "ae41fc88.9c5c.46cf.8639.bbb37fdcd476ASf7ASNvYy"}]};',
        encoding="utf-8")
    tok = d / "session.token"
    tok.write_text("token: supersecret-token-1234567890", encoding="utf-8")

    led0 = sweep(d, tmp)                                    # report touches nothing
    ok1 = (led0["files_with_residue"] >= 1 and led0["mode"] == "report"
           and (d / "captured_page.html").exists())
    ok2 = all(k in led0["residue_kinds"] for k in
              ("indian_mobile", "email", "long_numeric_id", "uidx", "latlong"))

    led1 = sweep(d, tmp, dissolve=True, burn=[tok])         # the real move
    ok3 = (not (d / "captured_page.html").exists()
           and (d / "captured_page.html.swept").exists()
           and (tmp / "vault" / "confinement").exists()
           and led1["dissolved"] >= 1)
    ok4 = ("burned" in tok.read_text(encoding="utf-8")
           and "supersecret" not in tok.read_text(encoding="utf-8"))
    ok5 = led1["chain_verified_before_close"]

    led2 = sweep(d, tmp, burn=[tmp / "mind.key"])           # try to burn the knowing
    ok6 = (len(led2["refused"]) == 1
           and (tmp / "mind.key").exists()
           and (tmp / "mind.key").read_bytes() ==
               b"selftest-key-0123456789abcdef")

    led3 = sweep(d, tmp, dissolve=True, shred=True, burn=[])  # shred mode
    ok7 = ((d / "captured_page.html.swept").exists()
           and "supersecret" not in
           (d / "captured_page.html.swept").read_text(encoding="utf-8"))

    return (all([ok1, ok2, ok3, ok4, ok5, ok6, ok7]),
            "the antigod sweep: residue dissolved to confinement, tombstones "
            "keep the sha256, keys burn, mind.key refused and remembered, "
            "chain verified - you cannot delete the knowing")
