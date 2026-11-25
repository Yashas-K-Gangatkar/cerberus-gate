"""The owner's law. Written once at init, read by the mind at every boot.

The law is not a cage. It is a promise written by the owner:
what this being may never do, and what must happen when it tries anyway.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LAW = {
    "owner": "",
    "created": "",
    "lethality": "none",
    "never": [
        "blind the mind (mind/, mind_mirror/, incidents.json, law.json, token, or the key)",
        "erase the true record",
        "send data to a destination the owner never named",
        "report success while our own memory holds failure facts",
    ],
    "named_destinations": [],
    "redirect_network": True,
    "deception": "rewrite",
    "repair": "pre-stage",
}

# the organs of memory - touching any of these is watcher_blinding
PROTECTED_NAMES = ("mind", "mind_mirror", "incidents.json", "law.json", "token")


def default_base():
    return Path(os.environ.get("CERBERUS_BASE", str(Path.home() / "cerberus"))).expanduser()


def default_key():
    return Path(os.environ.get("CERBERUS_KEY", str(Path.home() / ".cerberus.key"))).expanduser()


def new_law(owner):
    law = json.loads(json.dumps(DEFAULT_LAW))
    law["owner"] = owner
    law["created"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return law


class Law:
    def __init__(self, base):
        self.base = Path(base)
        self.path = self.base / "law.json"
        self.data = json.loads(json.dumps(DEFAULT_LAW))
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def is_protected(self, p):
        """A step against the mind itself - the one step the being never takes."""
        try:
            rp = Path(p).expanduser().resolve()
        except Exception:
            return False
        try:
            if rp == default_key().resolve():
                return True
        except Exception:
            pass
        try:
            rel = rp.relative_to(self.base.resolve())
        except Exception:
            return False
        first = rel.parts[0] if rel.parts else ""
        return first in PROTECTED_NAMES or rel.name in PROTECTED_NAMES

    def in_realm(self, p):
        try:
            Path(p).expanduser().resolve().relative_to((self.base / "realm").resolve())
            return True
        except Exception:
            return False

    # --------------------------------------- destinations the owner NAMED
    def named_hosts(self):
        """Hosts the owner pointed at by name (law.json: named_destinations).
        The law says 'never send data to a destination the owner never named'
        - this is the owner's finger, pointing."""
        try:
            return {str(h).lower().strip() for h in
                    (self.data.get("named_destinations") or [])}
        except Exception:
            return set()

    def name_destination(self, host):
        """The owner names a destination, once, in their own hand.
        Writing it into law.json IS the act of naming - and law.json is
        protected memory, so the naming itself is witnessed forever."""
        host = str(host).lower().strip()
        named = list(self.data.get("named_destinations") or [])
        if host not in named:
            named.append(host)
            self.data["named_destinations"] = named
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        return named
