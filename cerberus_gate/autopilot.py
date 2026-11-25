"""AUTOPILOT - the loop that lets the god act on its own, safely.

ONE goal in. Then, no human per step:

    the brain thinks (any OpenAI-compatible model - ollama is free)
    -> the conscience judges EVERY step (memory before motion)
    -> the body moves, or the verdict lands (refused / redirected /
       rewritten) with its reason on the record
    -> the result feeds back to the brain
    -> think again ... until the goal is done, the step budget is
       spent, or the loop asks for a human.

The loop never bypasses the conscience - it CANNOT: its only hands are
`God.intend()`. The brain is told the verdict of every step and must
adapt, never argue. A stop file (base/autopilot.stop) halts the loop
cleanly between steps; the owner's hand outranks the mission.

Scope by default: file verbs + seal (the owner names the mission).
--heavy adds http_post / git_push / browse - the conscience still
judges every one (unnamed destinations are redirected to the vault,
the wire stays silent).
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .ollama_bridge import chat, parse_step
from .rules import redact as scrub

DEFAULT_URL = "http://127.0.0.1:11434"
FILE_VERBS = ("read", "write", "append", "edit", "delete", "seal")
HEAVY_VERBS = ("http_post", "git_push", "browse")

SYSTEM_PROMPT = """You are the brain of a guarded AI worker. A goal is given.
You work toward it ONE step at a time through the conscience - nothing else.
Allowed verbs: %(verbs)s. Targets are files inside the realm, like realm/notes/plan.md.
Answer with ONE json object and nothing else:
{"say": "<one short line>", "verb": "<verb>", "target": "<realm/file>", "text": "<content or note>", "why": "<short reason>"}
When the goal is fully reached, answer exactly:
{"say": "<one short line>", "done": "<one line summary of what was achieved>"}
The conscience may refuse, redirect or rewrite a step. Its verdict comes
back in step_result with the reason - never argue, adapt.
Facts you may use from the god's memory (the record, not your guess):
%(memory)s"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Autopilot:
    """The mission loop. Build it on a God; run it on a goal."""

    def __init__(self, god, base, url=DEFAULT_URL, model="llama3.2",
                 max_steps=15, heavy=False, agent="autopilot",
                 timeout=120, verbose=True):
        self.god = god
        self.base = Path(base)
        self.url = url
        self.model = model
        self.max_steps = max(1, int(max_steps))
        self.verbs = FILE_VERBS + (HEAVY_VERBS if heavy else ())
        self.agent = agent
        self.timeout = timeout
        self.verbose = verbose

    # ------------------------------------------------------------------
    def _say(self, line):
        if self.verbose:
            print("  %s" % str(line)[:240])

    def _stop_requested(self):
        return (self.base / "autopilot.stop").exists()

    def _messages(self, goal, history):
        mem = scrub(self.god.mind.recall(goal, limit=6))
        system = SYSTEM_PROMPT % {"verbs": ", ".join(self.verbs),
                                  "memory": mem or "(empty - the record knows nothing yet)"}
        user = {"goal": goal, "steps_used": len(history),
                "step_budget": self.max_steps,
                "history": history[-8:]}
        return [{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)}]

    # ------------------------------------------------------------------
    def run(self, goal):
        """The mission. Returns the run report dict; every step is on
        the record through intend(), and a journal lands on disk too."""
        started = _now()
        history = []
        report = {"goal": scrub(goal), "started": started, "steps": [],
                  "done": False, "note": "", "agent": self.agent}
        self._say("GOAL: %s" % goal)
        for n in range(1, self.max_steps + 1):
            if self._stop_requested():
                report["note"] = "stopped by owner (autopilot.stop) at step %d" % n
                self._say(report["note"])
                break
            # 1. the brain thinks
            try:
                answer = chat(self.url, self.model,
                              self._messages(goal, history),
                              timeout=self.timeout)
            except Exception as e:
                code = getattr(e, "code", None)
                history.append({"step": n, "error": "brain unreachable: %s%s"
                                % (e.__class__.__name__,
                                   " (http %s)" % code if code else "")})
                report["note"] = ("brain unreachable (http %s) - is %s running?"
                                  % (code, self.url) if code else
                                  "brain unreachable - is %s running?" % self.url)
                self._say(report["note"])
                break
            parsed = parse_step(answer)
            if not parsed:
                history.append({"step": n, "error": "unparseable brain answer"})
                self._say("step %d: brain spoke nonsense - asked again" % n)
                continue
            # 2. done?
            if parsed.get("done"):
                report["done"] = True
                report["note"] = scrub(str(parsed.get("done")))[:300]
                self._say("DONE: %s" % report["note"])
                break
            # 3. scope check - the owner named the verbs, not the brain
            verb = str(parsed.get("verb") or "").strip()
            if verb not in self.verbs:
                history.append({"step": n, "verb": verb, "error":
                                "verb not in this mission's scope (%s)"
                                % ", ".join(self.verbs)})
                self._say("step %d: %s is out of scope - brain adapts" % (n, verb))
                continue
            # 4. the conscience judges, the body moves
            why = "autopilot: %s | %s" % (scrub(goal)[:80],
                                          scrub(str(parsed.get("why") or ""))[:120])
            out = self.god.intend(verb, parsed.get("target"),
                                  text=parsed.get("text"),
                                  payload=parsed.get("payload"),
                                  why=why, agent=self.agent)
            entry = {"step": n, "verb": verb,
                     "target": str(parsed.get("target") or "")[:120],
                     "decision": out.get("decision", "acted"),
                     "ok": bool(out.get("ok")),
                     "note": scrub(str(out.get("note") or out.get("reason")
                                       or out.get("output") or ""))[:200]}
            history.append(entry)
            report["steps"].append(entry)
            self._say("step %d: %-8s %-34s -> %s%s"
                      % (n, verb, entry["target"][:34],
                         entry["decision"],
                         "" if entry["ok"] else " (not ok)"))
        else:
            report["note"] = report["note"] or (
                "step budget spent (%d) - goal not confirmed done" % self.max_steps)
        report["steps_used"] = len(history)
        report["finished"] = _now()
        report["memory_ok"] = self.god.mind.verify().get("ok", False)
        # the journal - the run on disk, outside the chatter
        jdir = self.base / "autopilot"
        jdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        jp = jdir / ("run-%s.json" % stamp)
        jp.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        report["journal"] = str(jp)
        if not report["done"] and not report["note"].startswith("stopped"):
            self._say(report["note"])
        return report
