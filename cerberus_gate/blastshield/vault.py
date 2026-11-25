"""LAYER 3 — the leak-proof vault. Data that survives its own leak.

The honest threat model: someday, some payload leaves the house and
ends up somewhere it should not be. The promise is not "nothing ever
leaks" — it is that what leaks is (1) redacted, so the secret never
boarded the wire, (2) sealed, so a stolen blob is useless ciphertext,
and (3) canary-tagged, so the leak is traced back to the exact request
that carried it.

Three hands: the redactor (scrub before egress), the seal (AES-GCM at
rest, stdlib fallback when cryptography is missing), the canary (the
homing beacon inside every governed document).
"""
import hmac
import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .common import OwnerKey, b64e, b64d


class VaultSealed(Exception):
    """Raised when a blob cannot be opened: wrong key or tampered."""


@dataclass
class SecretHit:
    label: str
    value: str
    start: int
    end: int


# High-confidence secret shapes. Redaction may over-trigger slightly —
# a masked false positive costs nothing; a leaked true positive costs
# everything. Card numbers additionally pass a Luhn check.
_SECRET_PATTERNS = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs)_[A-Za-z0-9]{30,}\b")),
    ("slack_token", re.compile(r"\bxox[bpars]-[A-Za-z0-9-]{10,}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("card_number", re.compile(r"\b(?:\d[ -]?){12,19}\b")),
    ("phone", re.compile(r"\+\d{1,3}[- ]?\d{8,12}\b")),
    ("credential_pair", re.compile(
        r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token)\b\s*[:=]\s*\S{6,}")),
]


def _luhn_ok(number: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def find_secrets(text: str) -> List[SecretHit]:
    hits: List[SecretHit] = []
    taken: List[Tuple[int, int]] = []
    for label, pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(0)
            if label == "card_number" and not _luhn_ok(value):
                continue
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in taken):
                continue
            taken.append(span)
            hits.append(SecretHit(label, value, span[0], span[1]))
    return sorted(hits, key=lambda h: h.start)


def _mask(value: str, label: str, keep_last: int = 4) -> str:
    tail = value[-keep_last:] if len(value) > keep_last else ""
    return f"[[REDACTED:{label}]]{tail}"


def redact(text: str, keep_last: int = 4) -> Tuple[str, List[SecretHit]]:
    """Return (safe_text, hits). The secret never boards the wire."""
    hits = find_secrets(text)
    if not hits:
        return text, []
    safe = text
    for hit in reversed(hits):
        safe = safe[:hit.start] + _mask(hit.value, hit.label, keep_last) + safe[hit.end:]
    return safe, hits


class LeakProofVault:
    def __init__(self, owner_key: OwnerKey, ledger=None) -> None:
        self.key = owner_key
        self.ledger = ledger
        self._canaries: Dict[str, Dict[str, Any]] = {}
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self._aesgcm = AESGCM(self.key._key)
            self._alg = "AES-GCM"
        except Exception:
            self._aesgcm = None
            self._alg = "HMAC-CTR"

    # -------------------------------------------- the redactor ----
    def redact(self, text: str, keep_last: int = 4) -> Tuple[str, List[SecretHit]]:
        """Instance hand used by the shield's LAW 5: scrub before egress."""
        return redact(text, keep_last)

    # ------------------------------------------------ the seal ----
    def seal(self, plaintext: bytes, label: str = "") -> Dict[str, Any]:
        nonce = os.urandom(12 if self._aesgcm else 16)
        if self._aesgcm:
            ct = self._aesgcm.encrypt(nonce, plaintext, label.encode())
        else:
            ct = self._fallback_xor(nonce, plaintext)
            tag = hmac.new(self.key._key, b"gm-mac" + nonce + label.encode() + ct,
                           hashlib.sha256).digest()
            ct = ct + tag
        blob = {
            "alg": self._alg,
            "label": label,
            "nonce": b64e(nonce),
            "blob": b64e(ct),
            "key_id": hashlib.sha256(self.key._key).hexdigest()[:12],
        }
        if self.ledger:
            self.ledger.append("VAULT_SEAL", {"label": label, "alg": self._alg,
                                              "bytes": len(plaintext)})
        return blob

    def open(self, blob: Dict[str, Any]) -> bytes:
        nonce = b64d(blob["nonce"])
        ct = b64d(blob["blob"])
        label = blob.get("label", "")
        try:
            if blob.get("alg") == "AES-GCM" and self._aesgcm:
                return self._aesgcm.decrypt(nonce, ct, label.encode())
            body, tag = ct[:-32], ct[-32:]
            expected = hmac.new(self.key._key, b"gm-mac" + nonce + label.encode() + body,
                                hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected):
                raise VaultSealed("integrity check failed")
            return self._fallback_xor(nonce, body)
        except VaultSealed:
            raise
        except Exception as exc:
            raise VaultSealed(f"cannot open: wrong key or tampered ({exc})") from exc

    def _fallback_xor(self, nonce: bytes, data: bytes) -> bytes:
        sub = hmac.new(self.key._key, b"gm-ctr" + nonce, hashlib.sha256).digest()
        stream, counter = b"", 0
        while len(stream) < len(data):
            stream += hmac.new(sub, counter.to_bytes(8, "big") + nonce,
                               hashlib.sha256).digest()
            counter += 1
        return bytes(a ^ b for a, b in zip(data, stream[:len(data)]))

    # ---------------------------------------------- the canary ----
    def mint_canary(self, purpose: str) -> str:
        nonce = secrets.token_hex(8)
        canary = "CB-CAN-" + hmac.new(self.key._key,
                                      f"{purpose}|{nonce}".encode(),
                                      hashlib.sha256).hexdigest()[:16]
        self._canaries[canary] = {"purpose": purpose, "ts": nonce}
        if self.ledger:
            self.ledger.append("CANARY_MINT", {"canary": canary, "purpose": purpose})
        return canary

    def trace_canary(self, canary: str) -> Optional[Dict[str, Any]]:
        """A canary seen in the wild: which governed request carried it?"""
        if self.ledger:
            events = self.ledger.find("CANARY_MINT", "canary", canary)
            if events:
                return events[0]["data"]
        return self._canaries.get(canary)

    def sweep(self, leaked_text: str) -> Dict[str, Any]:
        """Found our data in the wild? Sweep it: canaries, redaction
        markers, and whether any live secret survived."""
        canaries = [c for c in self._canaries if c in leaked_text]
        redacted = "[[REDACTED:" in leaked_text
        survivors = [h.label for h in find_secrets(leaked_text)]
        return {
            "canaries_found": canaries,
            "traces": [self.trace_canary(c) for c in canaries],
            "carries_redaction_markers": redacted,
            "live_secrets_still_readable": survivors,
            "verdict": "TRACED-AND-HARMLESS" if canaries and not survivors
                       else ("REDACTED" if redacted and not survivors else "REVIEW"),
        }
