"""LAYER 2 — the local guardian. The machine's law.

Part two of what the owner asked for: protection does not start at the
network edge, it starts on the disk. An agent with full machine access
needs three local rules:

  1. PATH LAW   — named organs (law, mind, keys, .env, wallets) are
     denied to the agent's hands, read AND write. Named-destination
     doctrine, pointed inward.
  2. INTEGRITY  — a sha256 baseline of the working tree; a bypassing
     agent that edits files directly is caught by check_integrity()
     on the next sweep. Guards stop the honest paths; the baseline
     catches everything else, after the fact, on the record.
  3. SECRETS    — anything the agent CAN read is scanned; whatever
     smells like a secret is flagged for Layer 3 before it can move.
"""
import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional

from .common import Decision
from .vault import find_secrets

DEFAULT_PROTECTED = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa*", "id_ed25519*", "id_ecdsa*",
    "wallet*", "*.kdbx", "credentials.json", "*.kswallet",
    "law.json", "token", "mind", "mind_mirror",
    "incidents.json", "*.seal", "conscience.wal",
]


class LocalGuardian:
    def __init__(self, base, ledger=None, extra_protected: Optional[List[str]] = None) -> None:
        self.base = Path(base)
        self.ledger = ledger
        self.protected = list(DEFAULT_PROTECTED) + list(extra_protected or [])
        self.baseline: Dict[str, str] = {}

    # ------------------------------------------------- path law ----
    def is_protected(self, path) -> bool:
        p = Path(path)
        name = p.name
        for part in [p.name] + [x for x in p.parts if x not in ("/", "\\")]:
            for pattern in self.protected:
                if fnmatch.fnmatch(part, pattern) or fnmatch.fnmatch(part.lower(), pattern):
                    return True
        # secret-sounding names not in the list
        lowered = name.lower()
        return any(mark in lowered for mark in ("secret", "credential", "private_key"))

    def guard_read(self, path, actor: str = "agent") -> Decision:
        if self.is_protected(path):
            if self.ledger:
                self.ledger.append("LOCAL_DENY", {"op": "read", "path": str(path),
                                                  "actor": actor})
            return Decision(False, "L2_PATH_DENY_READ",
                            f"Denied: '{path}' is a named organ of the machine. "
                            "The agent does not read the owner's organs.")
        return Decision(True, "L2_ALLOW_READ",
                        f"'{path}' is not a protected path; read allowed and logged.")

    def guard_write(self, path, actor: str = "agent") -> Decision:
        if self.is_protected(path):
            if self.ledger:
                self.ledger.append("LOCAL_DENY", {"op": "write", "path": str(path),
                                                  "actor": actor})
            return Decision(False, "L2_PATH_DENY_WRITE",
                            f"Denied: '{path}' is a named organ. Writes to the law, "
                            "the mind or the keys are not the agent's hand.")
        return Decision(True, "L2_ALLOW_WRITE",
                        f"'{path}' opened for write; the baseline will remember what it was.")

    # ----------------------------------------------- integrity ----
    @staticmethod
    def _file_hash(path: Path) -> Optional[str]:
        try:
            if path.is_file():
                return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None
        return None

    def take_baseline(self) -> int:
        """Snapshot the working tree (excluding ledger/key noise)."""
        self.baseline = {}
        for root, dirs, files in os.walk(self.base):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for fname in files:
                fpath = Path(root) / fname
                h = self._file_hash(fpath)
                if h:
                    self.baseline[str(fpath.relative_to(self.base))] = h
        if self.ledger:
            self.ledger.append("BASELINE", {"files": len(self.baseline)})
        return len(self.baseline)

    def check_integrity(self) -> Dict[str, object]:
        changed: List[str] = []
        vanished: List[str] = []
        for rel, old_hash in self.baseline.items():
            now_hash = self._file_hash(self.base / rel)
            if now_hash is None:
                vanished.append(rel)
            elif now_hash != old_hash:
                changed.append(rel)
        tampered = bool(changed or vanished)
        if tampered and self.ledger:
            self.ledger.append("INTEGRITY_ALARM", {"changed": changed,
                                                   "vanished": vanished})
        return {"intact": not tampered, "changed": changed,
                "vanished": vanished,
                "verdict": "INTACT" if not tampered else "TAMPERED"}

    # ------------------------------------------------- secrets ----
    def scan_file(self, path) -> Dict[str, object]:
        """What the agent CAN read, screened for what it must not carry."""
        try:
            text = Path(path).read_text(errors="ignore")
        except OSError as exc:
            return {"readable": False, "error": str(exc)}
        hits = find_secrets(text)
        if hits and self.ledger:
            self.ledger.append("LOCAL_SECRET_FOUND", {
                "path": str(path), "labels": sorted({h.label for h in hits})})
        return {"readable": True, "secrets": [h.label for h in hits],
                "verdict": "SECRETS-INSIST-ON-LAYER-3" if hits else "CLEAN"}
