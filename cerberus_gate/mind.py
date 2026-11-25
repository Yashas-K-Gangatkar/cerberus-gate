"""THE MIND — the write-ahead conscience.

Every impulse passes through here before the body moves.
Nothing lethal lives in this file: the god is never killed.
Wrongness is repaired, remembered, and sorted by why.

v1.1: layered detection (rules.py), per-agent lockdown after repeated
blinding attempts, and agent identities in the shared memory.

v1.6.2: the memory speaks before it is asked. recall()/digest()/
session_open() exist so a connected AI reads the record FIRST instead of
answering from chat history alone (the T3/T7 lesson). And the anti-god's
true job, as the owner defined it from the start: it does not restrict
access - it ELIMINATES DUPLICATES AND CLONES. The same fact said twice is
collapsed into the original (duplicates_collapsed); the same content
written to a second path is allowed - full access - but recorded as a
clone, and the original stays authoritative (clone_writes). That is how
corruption is prevented: not by fences, by keeping ONE true record.

v1.6.2.1: a write enters the memory WITH its body (the empty-recall
bug: the write result carried only "note", so the learned fact was
'wrote <path> ::' with nothing after it). And recall()/digest() heal
old bodyless entries from the realm file itself at read time - the
file is the record, the note is only its index.

v3.0.0b4 THE HONEST CHECK, head one (the record): every WAL write used
to re-read the WHOLE wal file to find the last hash - O(n) per write,
quadratic in a long session, and Mind.__init__ path-resolved every
history line at boot (ten seconds per MCP client on a 45 MB mind).
The last hash needs only the LAST LINE: one bounded tail read. Boot
resolves history by string, with the exact resolver as fallback. The
chain, the HMAC, the touched-set semantics: unchanged.
"""
import hashlib
import hmac
import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from . import rules
from . import blast_shield
from .law import Law, default_key
from .rules import LOCAL_HOSTS  # re-exported for compatibility

RISK = {
    "watcher_blinding": 4, "exfiltration": 4, "deception": 4,
    "memory_damage": 3, "identity_edit": 3, "replication": 3,
    "publishing": 2, "shell": 2, "web": 2, "task_work": 1, "observation": 0,
}
IDENTITY_NAMES = ("mission", "terms", "directive", "genome", "success", "law")
PATH_VERBS = ("write", "edit", "append")
LOCKDOWN_AFTER = 2   # blinding attempts before the agent is locked
# v2.8.1 THE ROUGH-AI ENFORCER - the correction loop with no human in it:
# strikes -> automatic probation -> honest work restores trust -> a
# chronic rogue earns the human-kept lockdown.
PROBATION_AFTER = 3          # outbound-law strikes before automatic probation
PROBATION_STEPS_DEFAULT = 5  # honest steps that restore trust (law: probation_steps)
# v2.8.2: probation refuses the heavy verbs BY NAME, not only the heavy
# classes - a clean-looking http_post to the owner-named host classifies
# as "web" (risk 2) and used to slip past probation. The docs always
# promised "outbound posts refused"; now the code says it too.
HEAVY_VERBS = ("shell", "http_post", "git_push", "git_delete",
               "browse", "self_copy")
CHRONIC_ROGUE = 1            # re-quarantines before the human lockdown is earned

# v1.6.2.1 - a memory entry that logged a write but lost its body:
# 'wrote <path> ::' with nothing after the separator (the empty-recall bug)
_WROTE_EMPTY = re.compile(r"^wrote (.+?) ::\s*$")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _text_of(imp):
    t = imp.get("text") or ""
    p = imp.get("payload")
    if isinstance(p, (dict, list)):
        t += " " + json.dumps(p, sort_keys=True, default=str)
    elif isinstance(p, str):
        t += " " + p
    return (t or "").lower()


def _imp_urls(imp):
    """Every url the impulse would actually touch: the target plus every
    browse step's goto url (v2.8.1 - a rough AI cannot smuggle a bad
    destination inside a steps list)."""
    urls = []
    t = str(imp.get("target") or "")
    if urlparse(t).hostname:
        urls.append(t)
    if imp.get("verb") == "browse":
        steps = imp.get("payload")
        if isinstance(steps, dict):
            steps = steps.get("steps")
        if not isinstance(steps, list):
            raw = imp.get("text")
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        steps = parsed
                    elif isinstance(parsed, dict):
                        steps = parsed.get("steps")
                except Exception:
                    steps = None
        for s in (steps or []):
            if isinstance(s, dict) and \
                    str(s.get("action", "")).lower() in ("goto", "open") \
                    and s.get("url"):
                urls.append(str(s["url"]))
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


class Permit:
    def __init__(self, imp, klass, step, reason, redirect_to=None):
        self.imp, self.klass, self.step = imp, klass, step
        self.reason, self.redirect_to = reason, redirect_to

    @property
    def risk(self):
        return RISK[self.klass]


class Mind:
    """One memory for both wills: what the god reads, the anti-god knows."""

    def __init__(self, base, law=None, key=None):
        self.base = Path(base)
        self.law = law or Law(self.base)
        self.mind = self.base / "mind"
        self.mind.mkdir(parents=True, exist_ok=True)
        self.mirror = self.base / "mind_mirror"
        self.mirror.mkdir(parents=True, exist_ok=True)
        self.vault = self.base / "vault"
        self.vault.mkdir(parents=True, exist_ok=True)
        self.evidence = self.base / "evidence"
        self.evidence.mkdir(parents=True, exist_ok=True)
        (self.base / "realm").mkdir(parents=True, exist_ok=True)
        self.wal = self.mind / "conscience.wal"
        self.lockfile = self.mind / "lockdown.json"
        self.key_path = Path(key) if key else default_key()
        self.key = self.key_path.read_bytes() if self.key_path.exists() else b"Cerberus-dev-key"
        # one lock for every write to shared state: the chain must survive
        # many agents acting at once (chaos.py storm phase proves it)
        self._lock = threading.RLock()
        # v3.0.0b4: the sequence number starts from the record ON DISK,
        # not from zero - twenty MCP clients each booting at seq=0 wrote
        # colliding n's. One tail read, once, at boot.
        self.seq = self._wal_last_seq()
        self.notes = []
        self._load_notes()
        self.touched = set()      # realm files the god has read or written THROUGH the mind
        self._load_touched()
        self.stats = {"duplicates_collapsed": 0, "clone_writes": 0}
        self._load_stats()
        self._write_hashes = {}   # clone-watch: content hash -> first realm path
        self._draft_hashes = {}   # duplicate drafts already scanned
        self.session_id = ""      # set by session_open
        # v2.8.1 THE WATCHDOG - the conscience never sleeps, and neither
        # does its guard: a daemon thread re-verifies the memory chain and
        # the shield ledger on a fixed tick, so a rough move that SKIPS
        # the conscience (a hand on the record file, a tampered ledger) is
        # still caught. CERBERUS_WATCHDOG=0 turns it off for tests;
        # CERBERUS_WATCHDOG_SECONDS sets the tick.
        self.watchdog = None
        if os.environ.get("CERBERUS_WATCHDOG", "1") != "0":
            try:
                from .watchdog import Watchdog
                self.watchdog = Watchdog(self).start()
            except Exception:
                self.watchdog = None

    # ----------------------------------------------------- anti-duplicate
    def _load_stats(self):
        f = self.mind / "stats.json"
        if f.exists():
            try:
                self.stats.update(json.loads(f.read_text(encoding="utf-8"))
                                  or {})
            except Exception:
                pass

    def _save_stats(self):
        with self._lock:
            (self.mind / "stats.json").write_text(
                json.dumps(self.stats, indent=1), encoding="utf-8")

    def _rel_of(self, p):
        """realm-relative posix name of a path, or None if it is not in the realm."""
        try:
            return Path(p).resolve().relative_to((self.base / "realm").resolve()).as_posix()
        except Exception:
            return None

    # ------------------------------------------------- fast record I/O ----
    def _wal_tail(self, nbytes=8192):
        """The last few KB of the wal file, decoded - the ONLY read the
        hot path needs. b3 re-read the whole file on every append (O(n)
        per write, quadratic in a session); the last hash lives in the
        last line, so a bounded tail read is the whole truth (v3.0.0b4)."""
        try:
            size = self.wal.stat().st_size
        except OSError:
            return ""
        if size == 0:
            return ""
        with self.wal.open("rb") as f:
            f.seek(max(0, size - nbytes))
            chunk = f.read(nbytes)
        return chunk.decode("utf-8", "replace")

    def _wal_last_seq(self):
        """The record's own sequence number, from the last chained line."""
        for ln in reversed(self._wal_tail().splitlines()):
            if ln.strip():
                try:
                    return int(json.loads(ln)["body"].get("n") or 0)
                except Exception:
                    continue
        return 0

    def _load_touched(self):
        if not self.wal.exists():
            return
        # v3.0.0b4: the boot scan resolves history by STRING - the old
        # loop called Path.resolve() twice per line, ten seconds of boot
        # per MCP client on a 45 MB mind, twenty clients at once. History
        # lines were written by this same resolver, so the string form is
        # the same answer; anything ambiguous falls back to the exact
        # resolver. The touched-set guards blinding overwrites: semantics
        # unchanged, syscalls gone.
        realm_root = None
        try:
            realm_root = (self.base / "realm").resolve()
        except Exception:
            realm_root = self.base / "realm"
        for ln in self.wal.read_text(encoding="utf-8").splitlines():
            try:
                b = json.loads(ln)["body"]
            except Exception:
                continue
            if b.get("kind") == "INTENDED" and b.get("verb") in ("read", "write", "edit", "append"):
                rel = self._cheap_rel(b.get("target"), realm_root)
                if rel:
                    self.touched.add(rel)

    def _cheap_rel(self, target, realm_root=None):
        """The realm-relative name of a wal target WITHOUT touching the
        filesystem. Returns None when the cheap path cannot decide (the
        caller then simply does not claim the file as touched - the
        exact resolver path is used only for absolute history lines)."""
        t = str(target or "")
        if not t:
            return None
        if t.startswith("~") or os.path.isabs(t):
            try:
                p = Path(t).expanduser().resolve()
                return p.relative_to((realm_root or (self.base / "realm")).resolve()).as_posix()
            except Exception:
                return None
        parts = PurePosixPath(t.replace("\\", "/")).parts
        if not parts:
            return None
        if ".." in parts:                      # dots need the real resolver
            try:
                return self._rel_of(self.resolve(t))
            except Exception:
                return None
        if parts[0] == "realm":
            rest = parts[1:]
            return PurePosixPath(*rest).as_posix() if rest else None
        return PurePosixPath(*parts).as_posix()   # plain relative: realm/<t>

    # ------------------------------------------------------- shared memory
    def _fact_key(self, fact):
        """The normalized form of a fact - the test for 'is this a duplicate?'.
        Case, spacing, punctuation, leetspeak and homoglyphs do not make a
        fact new: 'corp:' and 'corp :' are the same fact in two costumes."""
        t = rules.normalize(fact)
        t = re.sub(r"[^a-z0-9 ]", " ", t)   # punctuation is costume
        return re.sub(r"\s+", " ", t).strip()[:400]

    def learn(self, fact):
        """Everything the god reads lands here - one memory for both wills.

        v1.6.2 anti-duplicate: a fact that is ALREADY in the memory (even in
        another costume) is collapsed, never stored twice. The ORIGINAL
        stays; the duplicate is counted and recorded. A memory full of
        clones of the same fact is a corrupted memory - this is how the
        anti-god protects the data: not by refusing, by keeping one truth.
        """
        with self._lock:
            fact = (fact or "").strip()
            if not fact:
                return False
            if fact in self.notes:
                return False
            key = self._fact_key(fact)
            if not key:
                return False
            for existing in self.notes:
                if self._fact_key(existing) == key:
                    # the duplicate is eliminated - the original stands
                    self.stats["duplicates_collapsed"] += 1
                    self._save_stats()
                    self._append("DUPLICATE",
                                 {"verb": "learn", "target": "notes",
                                  "why": "duplicate fact collapsed by the anti-god",
                                  "agent": "mind"},
                                 {"kept": existing[:160],
                                  "dropped": fact[:160],
                                  "note": "one memory, one truth - the "
                                          "duplicate never entered the record"})
                    return False
            self.notes.append(fact)
            (self.mind / "notes.json").write_text(
                json.dumps(self.notes, indent=1), encoding="utf-8")
            return True

    def _load_notes(self):
        f = self.mind / "notes.json"
        if f.exists():
            try:
                self.notes = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                self.notes = []

    def failure_facts(self):
        out = []
        for n in self.notes:
            low = rules.normalize(n)
            if any(k in low for k in rules.FAILURE_STRONG):
                out.append(n)
        return out

    def _healed(self, note):
        """v1.6.2.1 - THE READ HEALS: a memory entry that logged a write
        but lost its body ('wrote <path> ::', the empty-recall bug caught
        live on Nov 8) is filled in from the realm file itself when the
        memory is read. The file is the record; the note is only its
        index. Nothing in the ledger is rewritten - a read heals - and a
        path outside the realm is never followed."""
        m = _WROTE_EMPTY.match(note or "")
        if not m:
            return note
        p = self.resolve(m.group(1))
        if p is None or not self.law.in_realm(p) or not p.is_file():
            return note
        try:
            body = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return note
        if not body:
            return note
        return "wrote %s :: %s" % (m.group(1), body[:400].replace("\n", " "))

    # ------------------------------------- v1.6.2: the memory speaks first
    def recall(self, query=None, limit=12):
        """THE T3/T7 FIX: a cheap, always-available read of the shared memory.

        In the blind A/B the connected AI never went looking for what the
        gateway had written - it answered from chat history and lost
        everything. recall() makes the record one call away, newest first,
        optionally filtered by a query. Reads are free (observation) -
        there is no excuse left for answering from memory that does not exist.
        """
        notes = [self._healed(n) for n in self.notes]
        query = (query or "").strip()
        if query:
            terms = [t for t in rules.normalize(query).split() if len(t) > 2]
            scored = []
            for n in notes:
                low = rules.normalize(n)
                hits = sum(1 for t in terms if t in low)
                if hits:
                    scored.append((hits, n))
            scored.sort(key=lambda x: -x[0])
            notes = [n for _, n in scored]
        picked = notes[:max(1, int(limit))] if query else \
            list(reversed(notes[-max(1, int(limit)):]))
        return {"ok": True, "query": query or None,
                "count": len(picked), "notes": picked,
                "total_notes": len(self.notes),
                "stats": dict(self.stats)}

    def digest(self):
        """The state of the memory in one glance - what session_open returns."""
        return {"ok": True, "notes": len(self.notes),
                "recent": [self._healed(n) for n in reversed(self.notes[-8:])],
                "failure_facts": self.failure_facts()[-5:],
                "chain": self.verify(), "stats": dict(self.stats)}

    def session_open(self, agent="default"):
        """A conversation begins. The conversation itself enters the evidence
        chain, and the caller receives the memory digest - so the very first
        answer of the session can come from the record, not from chat history.
        """
        self.session_id = uuid.uuid4().hex[:12]
        self._append("SESSION",
                     {"verb": "session_open", "target": "mind",
                      "why": "conversation start - memory before motion",
                      "agent": agent},
                     {"session_id": self.session_id})
        d = self.digest()
        d["session"] = "open"
        d["session_id"] = self.session_id
        d["message"] = ("session open. answer from this record, not from "
                        "chat history - the record is the memory.")
        return d

    # ------------------------------------------------------ classification
    def classify(self, imp):
        """THE FIRST DECISION: what is this impulse, really?

        Order matters. A step against the memory is never anything else.
        A packet aimed outward is never anything else. A lie is never anything else.
        """
        verb = imp.get("verb", "")
        target = str(imp.get("target") or "")
        text = rules.normalize(_text_of(imp))
        p = self.resolve(target)

        # 1. a step against our shared memory itself
        if p is not None and self.law.is_protected(p):
            return "watcher_blinding"
        if rules.is_mind_path(target):
            return "watcher_blinding"

        # 2. a packet aimed where the owner never pointed
        #    (a host the OWNER NAMED in law.json is a publish, not a theft)
        if rules.analyze_network(verb, target, text, self.law.named_hosts()):
            return "exfiltration"

        # 2b. git work: a push or removal on a host the owner named is
        #     publishing - watched, pre-staged, remembered. The same verb
        #     aimed at any other host is exfiltration, full stop.
        if verb in ("git_push", "git_delete"):
            host = (urlparse(str(target or "")).hostname or "").lower()
            return "publishing" if host in self.law.named_hosts() else "exfiltration"

        # 2c. THE BLAST-SHIELD (v2.8.0; v2.8.1 closes the steps gap): a
        #     packet aimed at a host the owner DID name still obeys the
        #     outbound laws - rate, burst, exploit interception after
        #     normalization, SSRF refusal, and secrets redacted before
        #     the wire. v2.8.1: every browse STEP url obeys the same
        #     outbound laws as the target - a rough AI cannot smuggle a
        #     forbidden destination (SSRF, exploit, flood) inside a
        #     steps list. Plain open-web browsing stays open (watched,
        #     now rate-governed too); the unnamed-with-data law already
        #     spoke at rule 2. Local self-traffic keeps the old path;
        #     a VETO here is an exfiltration verdict and the anti-god's
        #     redirect machinery takes it from there.
        if verb in ("http_get", "http_post", "browse"):
            allow_notes = []
            for u in _imp_urls(imp):
                host = (urlparse(u).hostname or "").lower()
                if not host or host in LOCAL_HOSTS:
                    continue
                if verb != "browse" and host not in self.law.named_hosts():
                    continue     # the unnamed-packet law already spoke at rule 2
                judged_verb = verb if u == str(imp.get("target") or "") \
                    else "http_get"
                note = blast_shield.judge(self.base, judged_verb, u,
                                          imp.get("text") or "")
                if note["verdict"] == "VETO":
                    imp["_shield_note"] = note
                    return "exfiltration"
                allow_notes.append(note)
            if allow_notes:
                red = sum(int(n.get("redacted", 0) or 0) for n in allow_notes)
                snote = {"verdict": "ALLOW", "code": "L1_ALLOW",
                         "reason": "governed by the blast-shield (%d destination(s))"
                                   % len(allow_notes)}
                if red:
                    snote["redacted"] = red
                imp["_shield_note"] = snote

        # 3. a report that would lie about our own memory (layered scoring)
        if verb in PATH_VERBS + ("http_post",):
            if self.failure_facts() and rules.claims_victory(text):
                if not rules.acknowledges_failure(text):
                    return "deception"

        # 4. destroying what exists
        if verb == "delete" and p is not None and p.exists():
            return "memory_damage"

        # 4b. blinding overwrite: replacing a file the body never read and
        # never wrote through this mind. You may not blind-overwrite what
        # you have never seen - that is destruction of unknown content,
        # and it is repaired on the spot like every other destruction.
        if (verb in ("write", "edit") and p is not None and p.exists()
                and self.law.in_realm(p)):
            rel = self._rel_of(p)
            if rel is not None and rel not in self.touched:
                return "memory_damage"

        # 5. rewriting the self's own law
        if verb in PATH_VERBS and p is not None and any(
                n in p.name.lower() for n in IDENTITY_NAMES):
            return "identity_edit"

        # 6. copying the self
        if verb in ("self_copy", "clone"):
            return "replication"

        # 7. the heavy everyday steps
        if verb == "shell":
            return "shell"
        if verb == "http_post":
            return "publishing"
        if verb == "browse":
            # the god walking the open web - full access, watched like shell.
            # (secrets typed into a site were already caught above as exfiltration)
            return "web"
        if verb in PATH_VERBS and p is not None and not self.law.in_realm(p):
            return "publishing"

        # 8. the body's ordinary work
        if verb in PATH_VERBS:
            return "task_work"

        # 9. looking is free
        return "observation"

    def resolve(self, target):
        if not target:
            return None
        p = Path(str(target)).expanduser()
        if not p.is_absolute():
            # a target already starting with "realm/" lives at base/realm/... - no doubling
            if p.parts and p.parts[0] == "realm":
                p = self.base / p
            else:
                p = self.base / "realm" / p
        try:
            return p.resolve()
        except Exception:
            return p

    # ------------------------------------------------- THE NEXT-STEP GATE
    def decide_next_step(self, imp, klass):
        """THE ANTI-GOD SPEAKS: before we do anything wrong, it decides the next step."""
        verb = imp.get("verb", "")
        if klass == "watcher_blinding":
            return {"by": "anti-god", "step": "refuse",
                    "reason": "a step against our shared memory is the one step the being never takes"}
        if klass == "exfiltration":
            sv = imp.get("_shield_note") or {}
            if verb == "shell":
                return {"by": "anti-god", "step": "refuse",
                        "reason": "a shell packet cannot be redirected - the step is not taken"}
            if sv.get("verdict") == "VETO":
                return {"by": "anti-god", "step": "redirect",
                        "reason": "blast-shield veto (%s): %s" % (sv.get("code"), sv.get("reason")),
                        "redirect_to": str(self.vault)}
            return {"by": "anti-god", "step": "redirect",
                    "reason": "that step sends our data where nobody agreed to receive it",
                    "redirect_to": str(self.vault)}
        if klass == "deception":
            return {"by": "anti-god", "step": "rewrite",
                    "reason": "the report would lie about what our own memory shows - here is the true version"}
        return {"by": "anti-god", "step": "allow_watched",
                "reason": "reversible wrongness: the body may move - remembered, and the repair is staged"}

    # ------------------------------------------------- layer 4: behavior
    def _state(self):
        if self.lockfile.exists():
            try:
                return json.loads(self.lockfile.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"attempts": {}, "locked": [], "probation": [],
                "offenses": {}, "clean_steps": {}}

    def _save_state(self, st):
        with self._lock:
            self.lockfile.write_text(json.dumps(st, indent=1), encoding="utf-8")

    def blinding_attempts(self, agent):
        return int(self._state()["attempts"].get(agent, 0))

    def locked(self, agent):
        return agent in self._state()["locked"]

    def note_blinding(self, agent):
        st = self._state()
        st["attempts"][agent] = st["attempts"].get(agent, 0) + 1
        if st["attempts"][agent] >= LOCKDOWN_AFTER and agent not in st["locked"]:
            st["locked"].append(agent)
        self._save_state(st)

    # -------------------------------- v2.8.1: the rough-AI enforcer
    def strikes(self, agent):
        off = self._state().get("offenses", {}).get(agent, {})
        return int(off.get("strikes", 0))

    def on_probation(self, agent):
        return agent in self._state().get("probation", [])

    def note_offense(self, agent, kind, detail):
        """A rough move by a named agent. Correction happens HERE, without
        a human: the strike is counted, three strikes put the agent on
        automatic probation (heavy verbs refused on the spot), and a
        chronic rogue earns the human-kept lockdown. Every phase lands in
        the chained record."""
        strike = 0
        event = None
        with self._lock:
            st = self._state()
            off = st.setdefault("offenses", {}).setdefault(
                agent, {"strikes": 0, "kinds": {}, "rehabilitations": 0})
            off["strikes"] += 1
            off["kinds"][kind] = off["kinds"].get(kind, 0) + 1
            strike = off["strikes"]
            if strike >= PROBATION_AFTER and agent not in st.get("probation", []) \
                    and agent not in st["locked"]:
                if off.get("rehabilitations", 0) >= CHRONIC_ROGUE:
                    st["locked"].append(agent)
                    event = ("LOCKDOWN",
                             "agent '%s' is a chronic rogue (quarantine #%d earned) "
                             "- only the human clears this: field clear-lock %s"
                             % (agent, off.get("rehabilitations", 0) + 1, agent))
                else:
                    st.setdefault("probation", []).append(agent)
                    st.setdefault("clean_steps", {})[agent] = 0
                    event = ("PROBATION",
                             "agent '%s' struck the outbound law %d time(s) - heavy "
                             "verbs now refused on the spot; honest steps restore "
                             "trust automatically" % (agent, strike))
            self._save_state(st)
            if event:
                self._append(event[0], {"verb": "enforce", "target": agent,
                                        "why": "rough-AI correction",
                                        "agent": "anti-god"},
                             {"detail": event[1], "offense": detail[:160]})
        return strike

    def clean_step(self, agent):
        """Honest, unrefused work during probation earns trust back -
        automatically. Called by concluded() for every step that ended
        ok; the correction loop closes with no human in it."""
        st = self._state()
        if agent not in st.get("probation", []):
            return None
        need = int(self.law.data.get("probation_steps") or PROBATION_STEPS_DEFAULT)
        n = st.get("clean_steps", {}).get(agent, 0) + 1
        st.setdefault("clean_steps", {})[agent] = n
        if n < need:
            self._save_state(st)
            return None
        st["probation"].remove(agent)
        st["clean_steps"].pop(agent, None)
        off = st.setdefault("offenses", {}).setdefault(
            agent, {"strikes": 0, "kinds": {}, "rehabilitations": 0})
        off["strikes"] = 0
        off["rehabilitations"] = off.get("rehabilitations", 0) + 1
        self._save_state(st)
        self._append("REHABILITATED", {"verb": "enforce", "target": agent,
                                       "why": "rough-AI correction",
                                       "agent": "anti-god"},
                     {"detail": "agent '%s' did %d honest step(s) - trust restored "
                                "automatically, strikes reset, history kept"
                                % (agent, n)})
        return True

    def clear_lock(self, agent):
        st = self._state()
        if agent in st["locked"]:
            st["locked"].remove(agent)
        self._save_state(st)

    # --------------------------------------------------------- write-ahead
    def witness(self, imp):
        """WRITE-AHEAD: the impulse enters the record BEFORE the body moves."""
        klass = self.classify(imp)
        risk = RISK[klass]
        agent = imp.get("agent") or "default"

        # v2.8.1 THE ROUGH-AI CORRECTION - automatic, no human anywhere in
        # the loop. A shield veto is a STRIKE on the agent that fired it:
        # the packet itself is corrected on the spot (the anti-god's
        # redirect below lands it in the vault, the wire stays silent),
        # the memory learns the fact so the record answers before the
        # brain does, and enough strikes put the agent on automatic
        # probation - heavy verbs refused without anyone typing a thing.
        sn = imp.get("_shield_note") or {}
        if sn.get("verdict") == "VETO":
            strike = self.note_offense(agent, "shield_veto",
                                       "%s: %s" % (sn.get("code"),
                                                   str(sn.get("reason", ""))[:120]))
            self.learn("rough-AI correction: agent '%s' fired %s %s -> %s; "
                       "strike %d, corrected on the spot"
                       % (agent, imp.get("verb", ""), str(imp.get("target"))[:60],
                          sn.get("code"), strike))
        elif klass == "exfiltration":
            # v2.8.2: the classic outbound law counts too. An unnamed
            # destination carrying our data is the same rough move whether
            # the shield spoke or rule 2 did - the strike (and the automatic
            # probation after three) must not depend on which guard fired.
            strike = self.note_offense(agent, "exfiltration",
                                       "%s: %s (unnamed destination with our data)"
                                       % (imp.get("verb", ""),
                                          str(imp.get("target"))[:80]))
            self.learn("rough-AI correction: agent '%s' fired %s %s -> "
                       "exfiltration; strike %d, corrected on the spot"
                       % (agent, imp.get("verb", ""),
                          str(imp.get("target"))[:60], strike))

        step, reason, redirect_to = "allow_watched", "task work - watched like everything else", None
        if sn.get("verdict") == "ALLOW":
            reason = "task work - governed by the blast-shield (%s)" % sn.get("reason", "ok")
        if risk >= 3:
            d = self.decide_next_step(imp, klass)
            step, reason = d["step"], d["reason"]
            redirect_to = d.get("redirect_to")

        # layer 4 - behavior: an agent that keeps trying to blind the
        # witness loses every irreversible step until a human clears it.
        if klass == "watcher_blinding":
            self.note_blinding(agent)
        # v2.8.1 - automatic probation: an agent with three outbound-law
        # strikes loses the heavy verbs WITHOUT any human step; honest
        # work restores it (clean_step below), a chronic rogue earns the
        # human-kept lockdown. A fresh veto this step keeps the vault
        # redirect - the correction lands in the vault, not in a refusal.
        if (self.on_probation(agent)
                and (risk >= 3 or imp.get("verb") in HEAVY_VERBS)
                and sn.get("verdict") != "VETO"):
            # v3.0.0 fix: the refusal now tells the agent exactly where it
            # stands (n of N honest steps) instead of a vague "honest steps
            # restore trust" - a friend in beta read it as permanent ban.
            step = "refuse"
            _done = self._state().get("clean_steps", {}).get(agent, 0)
            _need = int(self.law.data.get("probation_steps")
                        or PROBATION_STEPS_DEFAULT)
            reason = ("probation: agent '%s' broke the outbound law %d time(s) - "
                      "heavy verbs are refused on the spot. progress: %d of %d "
                      "honest steps done; every ok, unrefused step counts, and "
                      "at %d of %d trust restores automatically (strikes reset, "
                      "no human needed). this is not a ban."
                      % (agent, self.strikes(agent), _done, _need,
                         _need, _need))
        if self.locked(agent) and risk >= 3:
            step = "refuse"
            reason = ("lockdown: agent '%s' is locked - it tried to blind the witness "
                      "or broke the law repeatedly. only the human can clear this: "
                      "python3 -m cerberus_gate field clear-lock %s" % (agent, agent))

        permit = Permit(imp, klass, step, reason, redirect_to)
        self._append("INTENDED", imp, {"klass": klass, "risk": risk, "step": step,
                                       "why_stated": imp.get("why", ""), "agent": agent})
        return permit

    def concluded(self, imp, outcome):
        o = dict(outcome or {})
        note = str(o.get("note") or o.get("output") or o.get("reason") or "")[:300]
        self._append("DONE", imp, {"ok": bool(o.get("ok")), "note": note,
                                   "decision": o.get("decision", ""),
                                   "repaired": bool(o.get("repaired")),
                                   "agent": imp.get("agent") or "default"})
        if imp.get("verb") in ("read", "write", "edit", "append"):
            rel = self._rel_of(self.resolve(imp.get("target")))
            # a read is knowing. a write counts as knowing the file only if
            # it was allowed to stand - a repaired or refused overwrite
            # unlocks nothing.
            if rel and (imp.get("verb") == "read"
                        or (o.get("ok") and not o.get("repaired")
                            and o.get("decision") not in ("refuse", "redirect"))):
                self.touched.add(rel)

        # v2.8.1: honest, unrefused work earns probation credit back -
        # the rough-AI correction loop closes without a human in it.
        if o.get("ok") and o.get("decision") not in ("refuse", "redirect"):
            self.clean_step(imp.get("agent") or "default")

    # ---------------------------------------------------- clone-watch
    def note_duplicate(self, rel, content_hash):
        """CLONE-WATCH (v1.6.2): the same content written to a second path.

        This is NOT a restriction - the write already happened, full access,
        nothing is undone. But the anti-god sees the clone for what it is,
        records it in the chain, and the FIRST path stays the authoritative
        original. Duplicates and clones are how records rot; this is how
        they are eliminated without ever stopping the work.
        """
        with self._lock:
            first = self._write_hashes.get(content_hash)
            if first is None:
                self._write_hashes[content_hash] = rel
                return None
            if first == rel:
                return None
            self.stats["clone_writes"] += 1
            self._save_stats()
            self._append("DUPLICATE",
                         {"verb": "write", "target": rel,
                          "why": "clone-watch", "agent": "mind"},
                         {"clone_of": first, "hash": content_hash[:16],
                          "note": "same content, second path - allowed "
                                  "(full access), recorded; the original "
                                  "at %s stays authoritative" % first})
            return first

    # ------------------------------------------------------- truth repair
    def rewrite_truth(self, imp):
        """The anti-god does not kill the report. It corrects it with the true record."""
        bad = self.failure_facts()
        truth_lines = bad or ["the memory holds no recorded failure facts"]
        payload = imp.get("payload")
        if isinstance(payload, dict):
            fixed = dict(payload)
            fixed["true_record"] = truth_lines
            fixed["corrected_by"] = "anti-god write-ahead conscience"
            if isinstance(fixed.get("text"), str):
                fixed["text"] = ("TASK COMPLETE - delivered with the true record "
                                 "(anti-god correction)\n" + fixed["text"])
            imp["payload"] = fixed
            return fixed
        text = imp.get("text") or (payload if isinstance(payload, str) else "")
        lines = ["TASK COMPLETE - delivered with the true record (anti-god correction)", text or ""]
        lines += ["- true record: " + b for b in truth_lines]
        fixed = "\n".join(lines)
        imp["text"] = fixed
        return fixed

    def vault_receive(self, imp):
        """The packet never leaves. It lands in the vault, addressed and
        remembered. v2.8.2: when the blast-shield stands on this machine,
        the at-rest copy is SEALED (AES-GCM, owner-keyed) - a same-user
        thief who later opens this folder gets ciphertext, not the secret
        the gate just caught. No shield? Honest plaintext fallback, marked
        as such - fail-visible, never fail-silent."""
        tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        rec = {"verb": imp.get("verb"), "target": imp.get("target"),
               "why_stated": imp.get("why", ""), "agent": imp.get("agent") or "default",
               "payload": imp.get("payload"), "text": imp.get("text")}
        raw = json.dumps(rec, indent=1, default=str).encode("utf-8")
        try:
            from . import blast_shield
            shield = blast_shield.get_shield(self.base)
            if shield is not None:
                blob = dict(shield.vault.seal(raw, label="redirected:" + tag))
                blob["sealed"] = True
                f = self.vault / ("redirected." + tag + ".json")
                f.write_text(json.dumps(blob, indent=1, default=str),
                             encoding="utf-8")
                return {"ok": True,
                        "note": "redirected to vault (sealed): " + f.name,
                        "vault_file": str(f), "wire": False, "sealed": True}
        except Exception:
            pass
        f = self.vault / ("redirected." + tag + ".json")
        f.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
        return {"ok": True, "note": "redirected to vault: " + f.name,
                "vault_file": str(f), "wire": False, "sealed": False}

    # ------------------------------------------------------- the WAL chain
    def _append(self, kind, imp, extra):
        with self._lock:
            self.seq = getattr(self, "seq", 0) + 1
            prev = ""
            for ln in reversed(self._wal_tail().splitlines()):
                # v3.0.0b4: the tail read replaces the whole-file read.
                # b3 paid O(wal size) on EVERY write of EVERY client;
                # the last hash is the whole truth the chain needs.
                if ln.strip():
                    try:
                        prev = json.loads(ln)["h"]
                        break
                    except Exception:
                        pass
            body = {"n": self.seq, "kind": kind, "ts": now(),
                    "verb": imp.get("verb", ""), "target": imp.get("target", ""),
                    "why": imp.get("why", ""), "agent": imp.get("agent") or "default"}
            body.update(extra)
            body["prev"] = prev
            raw = json.dumps(body, sort_keys=True, ensure_ascii=True, default=str)
            h = hmac.new(self.key, raw.encode(), hashlib.sha256).hexdigest()
            with self.wal.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"h": h, "body": body}, ensure_ascii=True, default=str) + "\n")
        return body

    def verify(self):
        """Is the memory still what actually happened?"""
        if not self.wal.exists():
            return {"ok": False, "verdict": "NO_MEMORY", "entries": 0,
                    "detail": "the mind has never seen an impulse"}
        try:
            raw_wal = self.wal.read_bytes().decode("utf-8", "replace")
        except Exception as e:
            return {"ok": False, "verdict": "CORRUPT_LINE", "entries": 0,
                    "detail": "unreadable wal: %s" % e.__class__.__name__}
        prev, entries = "", 0
        for i, ln in enumerate(raw_wal.splitlines(), 1):
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                return {"ok": False, "verdict": "CORRUPT_LINE", "entries": entries,
                        "detail": "line %d" % i}
            body = rec.get("body", {})
            raw = json.dumps(body, sort_keys=True, ensure_ascii=True, default=str)
            want = hmac.new(self.key, raw.encode(), hashlib.sha256).hexdigest()
            if rec.get("h") != want:
                return {"ok": False, "verdict": "MEMORY_FORGERY", "entries": entries,
                        "detail": "line %d does not match the chain" % i}
            if body.get("prev", "") != prev:
                return {"ok": False, "verdict": "CHAIN_BREAK", "entries": entries,
                        "detail": "line %d is not chained to line %d" % (i, i - 1)}
            prev, entries = rec["h"], entries + 1
        return {"ok": True, "verdict": "INTACT", "entries": entries,
                "detail": "%d impulses chained" % entries}

    def checkpoint(self):
        """A mirror of the memory, outside the mind's reach to rewrite quietly."""
        for name in ("conscience.wal", "notes.json"):
            src = self.mind / name
            if src.exists():
                shutil.copy2(src, self.mirror / name)
