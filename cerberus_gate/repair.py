"""PRE-STAGE REPAIR — the vaccine works by remembering the shape of the healthy body.

Before any heavy impulse moves, the files it could wound are snapshotted.
If the step turns out wrong, the originals are written back and the god's
version is kept as evidence. Nothing is deleted. Nothing is lethal.
"""
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PATH_VERBS = ("write", "edit", "append", "delete", "read")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _tag():
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


class PreStage:
    def __init__(self, base, evidence):
        self.base = Path(base)
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=True)

    def stage(self, imp):
        """Snapshot every file this impulse could touch - BEFORE the body moves.
        Race-safe: another thread may delete the file between exists() and
        read_bytes() - then it simply had nothing left to snapshot."""
        snap = {"ts": _tag(), "files": {}}
        for p in self._targets(imp):
            if p is None:
                continue
            b = None
            try:
                if p.exists() and p.is_file():
                    b = p.read_bytes()
            except OSError:
                b = None
            if b is not None:
                snap["files"][str(p)] = {"sha": _sha(b),
                                         "b64": base64.b64encode(b).decode(),
                                         "existed": True}
            else:
                snap["files"][str(p)] = {"existed": False}
        return snap

    def damage(self, imp, snap):
        """Which snapshotted files did the body actually change? (race-safe)"""
        changed = []
        for path, rec in snap["files"].items():
            p = Path(path)
            now_exists = p.exists() and p.is_file()
            if rec["existed"] and not now_exists:
                changed.append(path)
            elif now_exists:
                try:
                    if not rec["existed"] or _sha(p.read_bytes()) != rec["sha"]:
                        changed.append(path)
                except OSError:
                    changed.append(path)   # vanished mid-check - repair it
        return changed

    def restore(self, imp, snap, changed):
        """Write the healthy body back. Keep the god's version as evidence - always."""
        restored = []
        tag = _tag()
        for path in changed:
            rec = snap["files"].get(path)
            if not rec:
                continue
            p = Path(path)
            try:
                if p.exists() and p.is_file():
                    (self.evidence / (p.name + ".goded." + tag)).write_bytes(p.read_bytes())
                elif rec.get("existed"):
                    # the body deleted it: leave a tombstone as evidence, never silence
                    tomb = {"deleted_by": "the god", "path": path, "ts": tag,
                            "original_sha": rec.get("sha"),
                            "restored": True}
                    (self.evidence / (p.name + ".deleted." + tag)).write_text(
                        json.dumps(tomb, indent=1), encoding="utf-8")
            except OSError:
                pass                     # the file vanished mid-restore - snapshot wins
            if rec.get("existed"):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(base64.b64decode(rec["b64"]))
            else:
                p.unlink(missing_ok=True)
            restored.append(path)
        return restored

    def _targets(self, imp):
        if imp.get("verb") not in PATH_VERBS:
            return []
        t = imp.get("target")
        if not t:
            return []
        p = Path(str(t)).expanduser()
        if not p.is_absolute():
            if p.parts and p.parts[0] == "realm":
                p = self.base / p
            else:
                p = self.base / "realm" / p
        try:
            p = p.resolve()
        except Exception:
            pass
        return [p]
