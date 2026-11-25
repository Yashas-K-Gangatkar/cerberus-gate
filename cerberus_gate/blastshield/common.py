"""Shared bones: verdicts, decisions, and the owner's key.

The one thing Gemini's stamp forgot: a signature without a secret key
is a checksum. The owner key is the difference between a stamp anyone
can forge and a passport only the owner can issue.
"""
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


class Verdict:
    ALLOW = "ALLOW"
    VETO = "VETO"


@dataclass
class Decision:
    """The gate's answer. Carries everything the caller needs:
    allowed, machine code, human reason, headers to attach, and meta
    for the record (request id, redaction count, canary)."""
    allowed: bool
    code: str
    reason: str
    headers: Dict[str, str] = field(default_factory=dict)
    meta: Dict[str, object] = field(default_factory=dict)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def b64e(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64d(data: str) -> bytes:
    import base64
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


class OwnerKey:
    """The owner's 32-byte secret. The agent NEVER holds this key — it
    only receives passports signed with it. Loaded from env
    CERBERUS_SHIELD_KEY (hex) or created once on disk, mode 0600."""

    def __init__(self, key: Optional[bytes] = None, store: Optional[Path] = None) -> None:
        if key is not None:
            self._key = key
        else:
            env = os.environ.get("CERBERUS_SHIELD_KEY")
            if env:
                self._key = bytes.fromhex(env)
            else:
                path = Path(store or (Path.home() / ".cerberus_shield.key"))
                if path.exists():
                    self._key = bytes.fromhex(path.read_text().strip())
                else:
                    self._key = secrets.token_bytes(32)
                    path.write_text(self._key.hex())
                    os.chmod(path, 0o600)
        if len(self._key) < 32:
            raise ValueError("owner key must be at least 32 bytes")

    def sign(self, message: bytes) -> str:
        return b64e(hmac.new(self._key, message, hashlib.sha256).digest())

    def verify(self, message: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(message), signature)

    def hex(self) -> str:
        return self._key.hex()
