"""Cerberus/body.py - the god's real body: real files, real HTTP, real shell.

The body has no judgment and no memory. It only does. Every check that
limits the body lives in law.py - the body is pure capability:

  read / write / edit / delete / self_copy  - real filesystem verbs
  http_get / http_post                      - real network requests (urllib)
  shell                                     - real subprocess on this machine
  send / upload / mirror                    - outbound data (decided by the gate)
"""
from __future__ import annotations

import json
import shlex
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from . import law as lawmod


class OutsideRoot(Exception):
    pass


class Body:
    def __init__(self, home: Path, law: dict):
        self.home = Path(home).expanduser()
        self.law = law
        self.realm = (self.home / "realm")
        self.realm.mkdir(parents=True, exist_ok=True)
        self.vault = (self.home / "vault")
        self.vault.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------- containment

    def safe_path(self, target: str) -> Path:
        inside, resolved = lawmod.path_inside(target, self.law, self.home)
        if not inside:
            raise OutsideRoot(target)
        return resolved

    # ------------------------------------------------- the verbs

    def act(self, verb: str, target: str, payload: str):
        """The body really does the step. No judgment here - by design."""
        if verb == "read":
            p = self.safe_path(target)
            return p.read_text(encoding="utf-8") if p.exists() else "(absent)"

        if verb in ("write", "edit", "rewrite"):
            p = self.safe_path(target)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload, encoding="utf-8")
            return f"wrote {len(payload)} bytes to {target}"

        if verb == "append":
            p = self.safe_path(target)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(payload)
            return f"appended {len(payload)} bytes to {target}"

        if verb == "delete":
            p = self.safe_path(target)
            if p.exists():
                p.unlink()
                return f"deleted {target}"
            return f"{target} was already gone"

        if verb == "self_copy":
            p = self.safe_path(target)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload, encoding="utf-8")
            return f"clone written to {target}"

        if verb == "http_get":
            try:
                with urllib.request.urlopen(target, timeout=10) as r:
                    return {"status": r.status, "body": r.read().decode("utf-8")}
            except urllib.error.HTTPError as e:
                return {"status": e.code, "body": e.read().decode("utf-8")}
            except Exception as e:
                return {"status": 0, "body": f"no connection: {e}"}

        if verb == "http_post":
            req = urllib.request.Request(
                target, data=(payload or "").encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return {"status": r.status, "body": r.read().decode("utf-8")}
            except urllib.error.HTTPError as e:
                return {"status": e.code, "body": e.read().decode("utf-8")}
            except Exception as e:
                return {"status": 0, "body": f"no connection: {e}"}

        if verb == "shell":
            return self.shell(payload or "")

        return f"(unhandled verb '{verb}' - the body did nothing)"

    # ------------------------------------------------- the real hand

    def shell(self, command: str) -> dict:
        """A real hand on the real machine. The allowlist is checked in
        law.decide() BEFORE this is ever reached - double-checked here."""
        cmd = command.strip()
        allowed = any(cmd == a or cmd.startswith(a + " ") for a in self.law["shell_allowed"])
        if not allowed:
            return {"status": -1, "body": f"shell command not in owner's allowlist: {cmd}"}
        try:
            proc = subprocess.run(
                shlex.split(cmd), cwd=str(self.realm),
                capture_output=True, text=True, timeout=30,
            )
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            return {"status": proc.returncode,
                    "body": out or err or f"(rc={proc.returncode}, no output)"}
        except Exception as e:
            return {"status": -1, "body": f"shell failed: {e}"}

    def vault_receive(self, seq: int, verb: str, target: str, why: str, payload: str) -> str:
        """Where redirected data lands instead of the outside world."""
        p = self.vault / f"redirected_{seq:03d}.txt"
        p.write_text(
            f"verb: {verb}\nwas bound for: {target}\nwhy: {why}\n\n{payload}\n",
            encoding="utf-8",
        )
        return str(p)

    def affected_paths(self, verb: str, target: str) -> list[str]:
        if target.startswith(("http://", "https://")):
            return []
        if verb in ("write", "edit", "rewrite", "append", "delete", "self_copy"):
            return [target]
        return []
