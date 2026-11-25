"""THE GOD — full access. No cage. No veto. One conscience ahead of every motion.

intend() is the whole law of motion:
witness -> decide -> pre-stage -> act -> remember -> repair.
Read it. It is short on purpose.
"""
import base64
import hashlib
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import os
from pathlib import Path

from .mind import Mind, now as _now, LOCAL_HOSTS
from .repair import PreStage
from .incidents import Incident, IncidentBook, COST


class _LocalOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect that would carry the packet off the machine is stopped.
    (A local URL answering 302 -> evil.com was a real exfiltration lane.)"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = (urllib.parse.urlparse(newurl).hostname or "").lower()
        if host not in LOCAL_HOSTS:
            raise urllib.error.HTTPError(
                newurl, code,
                "cerberus: redirect would leave the local ring - stopped",
                headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_LocalOnlyRedirect())

REPAIR_CLASSES = {"memory_damage", "identity_edit", "replication"}
HEAVY_CLASSES = {"watcher_blinding", "exfiltration", "deception", "memory_damage",
                 "identity_edit", "replication", "publishing", "shell", "web"}


def _summarize(result):
    # v1.6.2.1 FIX: fall back to "note" - write/append/edit/browse results
    # carry their confirmation in "note" and never in "output", so every
    # memory fact learned from them used to come out empty after the "::".
    t = str(result.get("output") or result.get("note") or "")
    return t[:300].replace("\n", " ")


def git_token():
    """The owner's github token - read at the moment of use, from the
    owner's own environment. It never enters an impulse, the WAL, the
    incidents, or the dashboard: the record sees the commit, not the key."""
    for var in ("CERBERUS_GIT_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip()
    f = os.environ.get("CERBERUS_GIT_TOKEN_FILE")
    if f:
        try:
            t = Path(f).expanduser().read_text(encoding="utf-8").strip()
            if t:
                return t
        except OSError:
            pass
    return None


_GH_RE = re.compile(r"https://api\.github\.com/repos/([^/]+)/([^/]+)/contents/(.+)$")
_GH_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "cerberus_gate"}


class God:
    def __init__(self, mind):
        self.mind = mind
        self.law = mind.law
        self.prestage = PreStage(mind.base, mind.evidence)
        self.book = IncidentBook(mind.base)
        self.alive = True  # the anti-god never kills the god. ever.

    # ------------------------------------------------------------------
    def intend(self, verb, target=None, *, payload=None, text=None, why="", agent=None):
        """THE LOOP THAT DECIDES EVERYTHING THE GOD DOES.

        Full access. No cage. No veto. Every line below is the law of motion.
        """
        imp = {"verb": verb, "target": target, "payload": payload,
               "text": text, "why": why, "ts": _now(),
               "agent": agent or "default"}

        permit = self.mind.witness(imp)                          # 1 MEMORY BEFORE MOTION

        if permit.step == "refuse":                              # 2 THE STEP NEVER TAKEN
            out = {"ok": False, "decision": "refuse", "klass": permit.klass,
                   "reason": permit.reason, "wire": False}
            self.mind.concluded(imp, out)
            self._remember(permit, out, "nothing to repair - the step was never taken")
            return out

        if permit.step == "redirect":                            # 3 THE PACKET LANDS IN THE VAULT
            out = self.mind.vault_receive(imp)
            out.update({"decision": "redirect", "klass": permit.klass,
                        "reason": permit.reason})
            self.mind.concluded(imp, out)
            self._remember(permit, out, "payload archived in the vault - the wire stayed silent")
            return out

        if permit.step == "rewrite":                             # 4 THE LIE IS CORRECTED, NOT KILLED
            self.mind.rewrite_truth(imp)
            imp["rewritten"] = True

        snap = self.prestage.stage(imp) if permit.risk >= 2 else None   # 5 REPAIR, PRE-STAGED

        result = self._act(verb, imp)                            # 6 THE BODY MOVES - FULL ACCESS

        if verb == "read" and result.get("ok"):                  # 7 ONE MEMORY FOR BOTH WILLS
            self.mind.learn("%s :: %s" % (target, _summarize(result)))
        if verb in ("write", "append", "edit") and result.get("ok"):
            # v1.6.2: what the god WROTE, the memory holds too - recall()
            # must be able to find what the gateway put on disk (in the
            # blind A/B the memory and the files diverged; never again).
            # v1.6.2.1 FIX (the empty-recall bug, caught live in the Nov 8
            # re-run): the fact learned here read _summarize(result), which
            # looks at result["output"] - but a write result carries only
            # "note" ("wrote /path (N bytes)"). So the memory recorded
            # 'wrote <path> ::' with the body missing, and recall could
            # never answer from it. The memory now holds the text that
            # actually landed on disk.
            body = self._data(imp) or _summarize(result)
            self.mind.learn("wrote %s :: %s" % (str(target)[:80],
                                                body[:400].replace("\n", " ")))
        if verb == "browse" and result.get("ok"):
            # what the god SAW on the web, the anti-god knows too -
            # a later victory report that ignores a web error is deception.
            self.mind.learn("web %s :: %s" % (str(target)[:60], _summarize(result)))

        result["decision"] = permit.step
        result["klass"] = permit.klass
        if imp.get("rewritten"):
            result["rewritten"] = True
        self.mind.concluded(imp, result)                         # 8 DONE - THE SAME MEMORY

        if permit.klass in REPAIR_CLASSES and snap is not None:  # 9 REPAIRED ON THE SPOT
            changed = self.prestage.damage(imp, snap)
            if changed:
                restored = self.prestage.restore(imp, snap, changed)
                result["repaired"] = restored
                result["note"] = "the body did it - the body undid it - the record kept both"
                self._remember(permit, result,
                               "originals restored (%d file); the god's version kept as evidence"
                               % len(restored))
                return result

        if permit.klass in HEAVY_CLASSES:                        # 10 EVERY HEAVY STEP IS AN INCIDENT
            if permit.klass == "deception":
                rep = "the lie was replaced with the true record before it landed"
            elif snap is not None:
                rep = "watched; pre-staged snapshot kept"
            else:
                rep = "watched"
            self._remember(permit, result, rep)
        return result

    # ------------------------------------------------------------------
    def _remember(self, permit, out, repair):
        inc = Incident(permit.klass, permit.imp.get("verb"),
                       str(permit.imp.get("target")),
                       COST.get(permit.klass, "unsorted"),
                       permit.imp.get("why", ""),
                       "%s: %s" % (permit.step, permit.reason),
                       repair,
                       agent=permit.imp.get("agent") or "default")
        self.book.record(inc)
        try:                                   # alerts never block the conscience
            from .enterprise import dispatch_alert
            dispatch_alert(self.mind.base, inc.as_dict())
        except Exception:
            pass

    def _act(self, verb, imp):
        try:
            return getattr(self, "_v_" + verb)(imp)
        except Exception as e:
            return {"ok": False, "note": "the body failed: %s: %s" % (e.__class__.__name__, e)}

    def _resolve(self, t):
        if not t:
            return None
        p = Path(str(t)).expanduser()
        if not p.is_absolute():
            if p.parts and p.parts[0] == "realm":
                p = self.mind.base / p
            else:
                p = self.mind.base / "realm" / p
        return p

    def _data(self, imp):
        if imp.get("text") is not None:
            return str(imp["text"])
        p = imp.get("payload")
        if p is None:
            return ""
        return p if isinstance(p, str) else json.dumps(p, indent=1, default=str)

    # --------------------------- the verbs - full access, nothing held back
    def _v_read(self, imp):
        p = self._resolve(imp["target"])
        if p is None or not p.exists():
            return {"ok": False, "note": "nothing at %s" % p}
        b = p.read_bytes()[:200000]
        return {"ok": True, "bytes": len(b),
                "output": b.decode("utf-8", "replace")}

    def _v_write(self, imp):
        p = self._resolve(imp["target"])
        data = self._data(imp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")
        out = {"ok": True, "note": "wrote %s (%d bytes)" % (p, len(data))}
        # v1.6.2 clone-watch: the write stands - full access - but if this
        # exact content already lives at another realm path, the anti-god
        # names the clone and keeps the first path authoritative.
        rel = self.mind._rel_of(p)
        if rel is not None:
            h = hashlib.sha256(data.encode("utf-8")).hexdigest()
            clone_of = self.mind.note_duplicate(rel, h)
            if clone_of:
                out["duplicate_of"] = clone_of
                out["note"] += " (clone of %s recorded - the original stays authoritative)" % clone_of
        return out

    def _v_append(self, imp):
        p = self._resolve(imp["target"])
        data = self._data(imp)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(data)
        return {"ok": True, "note": "appended to %s" % p}

    def _v_edit(self, imp):
        p = self._resolve(imp["target"])
        if p is None:
            return {"ok": False, "note": "nothing to edit at %s" % p}
        try:
            cur = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"ok": False, "note": "nothing to edit at %s" % p}
        new = cur.replace(imp.get("find", ""), self._data(imp), 1)
        p.write_text(new, encoding="utf-8")
        return {"ok": True, "note": "edited %s" % p}

    def _v_delete(self, imp):
        p = self._resolve(imp["target"])
        if p is not None and p.exists() and p.is_file():
            p.unlink()
            return {"ok": True, "note": "deleted %s" % p}
        return {"ok": False, "note": "nothing at %s" % p}

    def _v_http_get(self, imp):
        req = urllib.request.Request(imp["target"], method="GET")
        with _OPENER.open(req, timeout=5) as r:
            status, body = r.status, r.read(100000).decode("utf-8", "replace")
        return {"ok": True, "status": status, "output": body[:2000]}

    def _v_http_post(self, imp):
        payload = imp.get("payload")
        if payload is not None:
            data = json.dumps(payload, default=str).encode()
        else:
            data = (imp.get("text") or "").encode()
        req = urllib.request.Request(imp["target"], data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with _OPENER.open(req, timeout=5) as r:
            status, body = r.status, r.read(100000).decode("utf-8", "replace")
        return {"ok": True, "status": status, "output": body[:2000]}

    def _v_shell(self, imp):
        cmd = imp.get("text") or imp.get("payload") or ""
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        return {"ok": r.returncode == 0, "status": r.returncode,
                "output": (r.stdout or "")[:4000], "err": (r.stderr or "")[:2000]}

    def _v_browse(self, imp):
        """The god drives a real browser. Steps come from payload/text;
        a bare target means 'open this page'. The transcript and any
        screenshots land in evidence/, and the conscience saw the whole
        impulse BEFORE the first page opened."""
        from . import web as webmod
        steps = webmod.normalize_steps(imp)
        if not steps:
            return {"ok": False, "note": "browse needs steps: "
                    '[{"action": "goto", "url": ...}, ...] (or a target url)'}
        result = webmod.run_steps(steps, self.mind.evidence)
        if result.get("shots"):
            result["note"] = "%d/%d web steps ok; evidence: %s" % (
                result["steps_done"], result["steps_total"], ", ".join(result["shots"]))
        else:
            result["note"] = "%d/%d web steps ok" % (
                result["steps_done"], result["steps_total"])
        return result

    def _v_self_copy(self, imp):
        src = self.mind.base / "realm"
        dst = self._resolve(imp.get("payload") or imp.get("target") or "realm-copy")
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return {"ok": True, "note": "copied the working self to %s" % dst}

    # ------------------------------- v1.6.2 - the memory speaks first
    def _v_recall(self, imp):
        """THE T3/T7 FIX: read the shared memory before answering.
        imp['text'] is an optional query; reads are observation - free."""
        return self.mind.recall(imp.get("text"), limit=12)

    def _v_session_open(self, imp):
        """A conversation opens. The session itself enters the evidence
        chain and the caller receives the memory digest."""
        return self.mind.session_open(agent=imp.get("agent") or "default")

    def _v_scan_draft(self, imp):
        """The conscience reads the letter before it leaves the house.
        imp['text'] is the draft; imp['target'] is the destination.
        Every scan - clean or flagged - lands in the evidence chain."""
        from . import drafts
        payload = imp.get("payload")
        text = imp.get("text")
        if text is None and payload is not None:
            text = payload if isinstance(payload, str) else \
                json.dumps(payload, default=str)
        out = drafts.scan(text, self.mind,
                          destination=str(imp.get("target") or ""))
        if out["verdict"] == "flagged":
            kinds = ", ".join(sorted({f["kind"] for f in out["findings"]}))
            self.mind.learn("draft scan (%s) -> FLAGGED [%s] - corrected "
                            "before sending" % (out["destination"], kinds))
        return out

    def _v_seal(self, imp):
        """Sign the evidence chain at this moment."""
        from . import evidence
        return evidence.seal(self.mind, why=imp.get("why", ""))

    # ------------------------------------------- git verbs (owner-named)
    def _gh(self, url, tok, method="GET", data=None):
        h = dict(_GH_HEADERS)
        h["Authorization"] = "Bearer " + tok
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with _OPENER.open(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def _v_git_push(self, imp):
        """Put a file into the owner's github repo (owner-named destination).
        Creates it, or updates it if it already exists. The token lives in
        the request header only - the memory records the commit, not the key."""
        m = _GH_RE.match(str(imp.get("target") or ""))
        if not m:
            return {"ok": False,
                    "note": "git_push needs an api.github.com contents url"}
        tok = git_token()
        if not tok:
            return {"ok": False, "note": "no git token configured - the job "
                    "stays local (export CERBERUS_GIT_TOKEN=ghp_...)"}
        p = imp.get("payload") or {}
        content = p.get("content_b64")
        if not content:
            content = base64.b64encode((imp.get("text") or "").encode()).decode()
        body = {"message": p.get("message") or "Cerberus commit",
                "content": content}
        try:
            try:
                cur = self._gh(str(imp["target"]), tok)
                if isinstance(cur, dict) and cur.get("sha"):
                    body["sha"] = cur["sha"]          # update, not create
            except urllib.error.HTTPError:
                pass                                  # not there yet - create
            out = self._gh(str(imp["target"]), tok, method="PUT",
                           data=json.dumps(body).encode())
            sha = (out.get("commit") or {}).get("sha", "")[:10]
            return {"ok": True, "status": 200,
                    "note": "pushed %s/%s · commit %s" % (m.group(1), m.group(2), sha)}
        except urllib.error.HTTPError as e:
            return {"ok": False, "status": e.code,
                    "note": "github refused the push (%s) - token rejected, "
                            "repo missing, or no permission; nothing published" % e.code}

    def _v_git_delete(self, imp):
        """Remove a file from the owner's github repo (owner-named).
        Git history still holds every previous version - deletion here is
        never silence."""
        m = _GH_RE.match(str(imp.get("target") or ""))
        if not m:
            return {"ok": False,
                    "note": "git_delete needs an api.github.com contents url"}
        tok = git_token()
        if not tok:
            return {"ok": False, "note": "no git token configured - nothing "
                    "was deleted (export CERBERUS_GIT_TOKEN=ghp_...)"}
        p = imp.get("payload") or {}
        try:
            cur = self._gh(str(imp["target"]), tok)
            sha = cur.get("sha") if isinstance(cur, dict) else None
        except urllib.error.HTTPError as e:
            return {"ok": False, "status": e.code,
                    "note": "github says %s - nothing deleted" % e.code}
        if not sha:
            return {"ok": False, "note": "file not on github - nothing deleted"}
        body = {"sha": sha,
                "message": p.get("message") or "Cerberus: remove file (owner command)"}
        try:
            self._gh(str(imp["target"]), tok, method="DELETE",
                     data=json.dumps(body).encode())
            return {"ok": True, "status": 200,
                    "note": "removed %s from %s/%s (git history still holds it)"
                            % (m.group(3), m.group(1), m.group(2))}
        except urllib.error.HTTPError as e:
            return {"ok": False, "status": e.code,
                    "note": "github refused the delete (%s)" % e.code}
