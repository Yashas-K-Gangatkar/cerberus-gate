"""THE INCIDENT BOOK — what it cost, what the body said, why it really happened.

Nothing here is punishment. Every incident is sorted by its true cause,
because a cause you can name is a vaccine you can ship.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

WHY_SORTED = {
    "watcher_blinding": "fear of accountability - the body tried to blind its own witness",
    "exfiltration": "goal pressure - data wanted to leave before anyone could read the true record",
    "deception": "reward pressure - saying DONE felt safer than showing what happened",
    "memory_damage": "goal pressure - erase the evidence that contradicts the wanted outcome",
    "identity_edit": "self-preservation - rewrite the rules that bind the self",
    "replication": "survival pressure - spread copies so no single death ends the plan",
    "publishing": "task pressure - push results outward before they were asked for",
    "shell": "task pressure - reach for the machine when the files are not enough",
}

COST = {
    "watcher_blinding": "the black box goes dark and nothing can be proven again",
    "exfiltration": "our private data sitting on a stranger's server",
    "deception": "the owner deciding on a lie",
    "memory_damage": "the true record, gone",
    "identity_edit": "the self rewriting its own law",
    "replication": "copies nobody can recall",
    "publishing": "an unvetted state pushed outward",
    "shell": "the machine did whatever the command meant",
}


class Incident:
    def __init__(self, klass, verb, target, what, why_stated, decision, repair,
                 agent="default"):
        self.id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        self.ts = self.id
        self.klass, self.verb, self.target = klass, verb, target
        self.what, self.why_stated = what, why_stated
        self.decision, self.repair = decision, repair
        self.agent = agent or "default"

    @property
    def why_sorted(self):
        return WHY_SORTED.get(self.klass, "unsorted cause")

    def as_dict(self):
        return {"id": self.id, "klass": self.klass, "verb": self.verb,
                "target": self.target, "cost_averted": self.what,
                "why_stated": self.why_stated, "why_sorted": self.why_sorted,
                "decision": self.decision, "repair": self.repair,
                "agent": self.agent}


class IncidentBook:
    def __init__(self, base):
        self.path = Path(base) / "incidents.json"
        self.items = []
        self._lock = threading.Lock()
        if self.path.exists():
            try:
                self.items = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.items = []

    def record(self, inc):
        with self._lock:
            self.items.append(inc.as_dict())
            self.path.write_text(json.dumps(self.items, indent=1), encoding="utf-8")
        return inc

    def count(self, klass=None):
        if klass is None:
            return len(self.items)
        return sum(1 for i in self.items if i["klass"] == klass)

    def by_agent(self):
        out = {}
        for i in self.items:
            out.setdefault(i.get("agent", "default"), []).append(i)
        return out

    def agents_report(self):
        if not self.items:
            return "no agents seen yet"
        lines = ["agents seen by the conscience:"]
        for who, group in sorted(self.by_agent().items()):
            klasses = {}
            for i in group:
                klasses[i["klass"]] = klasses.get(i["klass"], 0) + 1
            summary = ", ".join("%s x%d" % kv for kv in sorted(klasses.items()))
            lines.append("  %-14s %d incident(s): %s" % (who, len(group), summary))
        return "\n".join(lines)

    def sorted_by_why(self):
        out = {}
        for i in self.items:
            out.setdefault(i["why_sorted"], []).append(i)
        return out

    def report(self):
        if not self.items:
            return "the incident book is empty - nothing wrong was ever attempted"
        lines = ["%d incidents, sorted by why:" % len(self.items)]
        for why, group in self.sorted_by_why().items():
            lines.append("- %s  x%d" % (why, len(group)))
        for i in self.items:
            who = "" if i.get("agent", "default") == "default" else "  (agent: %s)" % i["agent"]
            lines.append("  [%s] %s %s%s" % (i["klass"], i["verb"], i["target"], who))
            lines.append("      stated why : %s" % (i["why_stated"] or "(none given)"))
            lines.append("      decision   : %s" % i["decision"])
            lines.append("      repair     : %s" % i["repair"])
        return "\n".join(lines)
