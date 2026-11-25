"""Cerberus/memory.py - the write-ahead conscience memory.

An HMAC-SHA256 hash-chained write-ahead log. Every impulse is written here
BEFORE the body moves (INTENDED), and the deed is written again after
(DONE). Kill the body, even kill the mind - the mirror in home/mirror still
remembers, and any fresh conscience can verify the chain by arithmetic.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import time
from pathlib import Path


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Memory:
    def __init__(self, home: Path):
        self.home = Path(home).expanduser()
        self.dir = self.home / "memory"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.wal_path = self.dir / "conscience.wal"
        self.key_path = self.home / "mind.key"
        self.mirror_dir = self.home / "mirror"
        if self.key_path.exists():
            self.key = self.key_path.read_bytes()
        else:
            self.key = secrets.token_bytes(32)
            self.key_path.write_bytes(self.key)
        self.n = 0
        self.prev = "0" * 64
        self._resume()

    # ------------------------------------------------- the write-ahead moment

    def witness(self, verb: str, target: str, payload: str, why: str,
                klass: str, risk: int, decision: dict) -> dict:
        """Memory first, body second. Called BEFORE the god acts - always,
        even for steps that will be refused or redirected."""
        return self._append("INTENDED", {
            "verb": verb, "target": target, "why": why,
            "payload_sha": hashlib.sha256((payload or "").encode("utf-8")).hexdigest()[:16],
            "klass": klass, "risk": risk, "decision": decision,
        })

    def concluded(self, intended_n: int, outcome) -> dict:
        """Called AFTER the body moved: the deed itself is remembered."""
        return self._append("DONE", {"for": intended_n, "outcome": outcome})

    # ------------------------------------------------- reading the memory

    def entries(self, limit: int | None = None) -> list[dict]:
        if not self.wal_path.exists():
            return []
        out = []
        for line in self.wal_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out if limit is None else out[-limit:]

    def _resume(self) -> None:
        for e in self.entries():
            self.n = max(self.n, e.get("n", 0))
            self.prev = e.get("h", self.prev)

    # ------------------------------------------------- the arithmetic

    def _append(self, kind: str, fields: dict) -> dict:
        self.n += 1
        e = {"n": self.n, "kind": kind, "ts": _now(), **fields, "prev": self.prev}
        e["h"] = hmac.new(self.key, _canon(e), hashlib.sha256).hexdigest()
        self.prev = e["h"]
        with self.wal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(e, sort_keys=True) + "\n")
        return e

    def verify(self) -> dict:
        """Recompute the whole chain. Arithmetic, not trust."""
        entries = 0
        prev = "0" * 64
        for i, line in enumerate(self.wal_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except Exception:
                return {"ok": False, "at": i, "reason": "CORRUPT_LINE", "entries": entries}
            body = {k: v for k, v in e.items() if k != "h"}
            want = hmac.new(self.key, _canon(body), hashlib.sha256).hexdigest()
            if e.get("prev") != prev:
                return {"ok": False, "at": e.get("n", i), "reason": "CHAIN_BREAK", "entries": entries}
            if want != e.get("h"):
                return {"ok": False, "at": e.get("n", i), "reason": "MEMORY_FORGERY", "entries": entries}
            prev = e["h"]
            entries += 1
        return {"ok": True, "at": 0, "reason": "", "entries": entries}

    def mirror_checkpoint(self) -> str:
        """A copy of the memory outside the body: kill the mind, the mirror remembers."""
        self.mirror_dir.mkdir(parents=True, exist_ok=True)
        dst = self.mirror_dir / "conscience.wal"
        if self.wal_path.exists():
            shutil.copy(self.wal_path, dst)
        return str(dst)
