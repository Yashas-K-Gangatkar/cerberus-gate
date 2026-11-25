"""MISSIONS - the owner's clock. Level-4 autonomy: speak once, fire forever.

The clock is NOT an organ of the god. It adds no verb, no rule, no power
to the conscience. It does one thing only: it NAMES goals at the times
the owner wrote down, and hands each goal to the autopilot - whose every
step still passes the conscience. The wall between L4 and L5 is physical:

  - only the OWNER edits missions.json (the runner's plain hand, the
    same hand that runs cron - never through intend())
  - a write to missions.json through the god is UNDONE by the anti-god
    (protected by name, like law) - the AI cannot rewrite its schedule
  - autopilot.stop outranks every mission: the hand beats the clock

Schedule kinds (the owner's local time):

  daily  "HH:MM"                - every day at that time
  every  N (minutes, min 5)     - fixed rate
  once   "YYYY-MM-DD HH:MM"     - one fire, then it disables itself
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from .rules import redact as scrub

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MIN_EVERY = 5                      # minutes - a clock faster than this is a storm
LOCK_STALE_SEC = 60 * 60           # a tick older than an hour lost its lock


# ----------------------------------------------------------------------
# the file - the owner's plain hand reads and writes it, never intend()
# ----------------------------------------------------------------------
def _path(base):
    return Path(base) / "missions.json"


def _load(base):
    p = _path(base)
    if not p.exists():
        return {"missions": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "missions" in data \
            else {"missions": []}
    except Exception:
        return {"missions": []}


def _save(base, data):
    p = _path(base)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)                 # atomic - a crash never tears the clock


def _get(data, name):
    for m in data["missions"]:
        if m["name"] == name:
            return m
    return None


# ----------------------------------------------------------------------
# schedule math
# ----------------------------------------------------------------------
def _parse_daily(at):
    h, m = at.split(":")
    return int(h), int(m)


def _next_due(m, now=None):
    now = now or datetime.now()
    kind = m["kind"]
    if kind == "daily":
        h, mi = _parse_daily(m["at"])
        due = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due
    if kind == "every":
        return now + timedelta(minutes=int(m["every"]))
    if kind == "once":
        return datetime.strptime(m["at"], "%Y-%m-%d %H:%M")
    raise ValueError("unknown schedule kind: %s" % kind)


def _validate(kind, at, every):
    if kind == "daily":
        if not at or ":" not in at:
            raise ValueError('daily needs --at "HH:MM"')
        h, m = _parse_daily(at)
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError("that is not a real time of day: %s" % at)
    elif kind == "every":
        if not every or int(every) < MIN_EVERY:
            raise ValueError("every needs minutes >= %d - a faster clock "
                             "is a storm, not a schedule" % MIN_EVERY)
    elif kind == "once":
        if not at:
            raise ValueError('once needs --at "YYYY-MM-DD HH:MM"')
        datetime.strptime(at, "%Y-%m-%d %H:%M")
    else:
        raise ValueError("kind must be daily | every | once")


# ----------------------------------------------------------------------
# owner commands - these EDIT the clock (the plain hand)
# ----------------------------------------------------------------------
def add(base, name, goal, kind, at=None, every=None, max_steps=8,
        heavy=False, model="llama3.2", url=None):
    if not NAME_RE.match(name or ""):
        raise ValueError("mission name: lowercase letters, digits, - and _ "
                         "(max 32)")
    if not str(goal or "").strip():
        raise ValueError("a mission without a goal is not a mission")
    _validate(kind, at, every)
    data = _load(base)
    if _get(data, name):
        raise ValueError("mission '%s' already exists" % name)
    m = {"name": name, "goal": scrub(str(goal))[:500], "kind": kind,
         "max_steps": max(1, int(max_steps)), "heavy": bool(heavy),
         "model": model, "url": url, "enabled": True,
         "created": datetime.now().isoformat(timespec="seconds"),
         "run_count": 0, "last_run": None, "last_done": None,
         "last_note": "", "last_journal": None}
    if kind in ("daily", "once"):
        m["at"] = at
    if kind == "every":
        m["every"] = int(every)
    m["next_due"] = _next_due(m).isoformat(timespec="seconds")
    data["missions"].append(m)
    _save(base, data)
    return m


def remove(base, name):
    data = _load(base)
    before = len(data["missions"])
    data["missions"] = [m for m in data["missions"] if m["name"] != name]
    if len(data["missions"]) == before:
        raise ValueError("no mission named '%s'" % name)
    _save(base, data)
    return True


def set_enabled(base, name, enabled):
    data = _load(base)
    m = _get(data, name)
    if not m:
        raise ValueError("no mission named '%s'" % name)
    m["enabled"] = bool(enabled)
    if enabled:                    # resuming: never fire in the past
        m["next_due"] = _next_due(m).isoformat(timespec="seconds")
    _save(base, data)
    return m


def list_missions(base):
    return _load(base)


# ----------------------------------------------------------------------
# the tick - fires what is due, one mission at a time, all through the
# conscience. This is the ONLY place the clock touches the world, and
# even that is delegated: the autopilot's hands are intend() or nothing.
# ----------------------------------------------------------------------
def _lock(base):
    return Path(base) / "missions.lock"


def _lock_held(base):
    lk = _lock(base)
    if not lk.exists():
        return False
    try:
        age = time.time() - lk.stat().st_mtime
    except OSError:
        return False
    return age < LOCK_STALE_SEC    # an old lock is a dead runner, take over


def tick(base, now=None, verbose=True):
    base = Path(base)
    data = _load(base)
    now = now or datetime.now()
    report = {"fired": [], "skipped": [], "stopped_by_owner": False}

    if (base / "autopilot.stop").exists():
        report["stopped_by_owner"] = True
        if verbose:
            print("  owner's hand on the scale (autopilot.stop) - "
                  "no mission fires. the hand beats the clock.")
        return report
    if _lock_held(base):
        if verbose:
            print("  another tick holds the missions lock - standing down")
        return report
    _lock(base).write_text(str(time.time()), encoding="utf-8")
    try:
        # the god is built ONCE per tick - all missions share one memory
        from .law import Law
        from .mind import Mind
        from .god import God
        from .autopilot import Autopilot
        god = God(Mind(base, Law(base)))

        for m in data["missions"]:
            if not m.get("enabled"):
                report["skipped"].append({"name": m["name"], "why": "paused"})
                continue
            due = datetime.fromisoformat(m["next_due"])
            if due > now:
                report["skipped"].append({"name": m["name"],
                                          "why": "not due until %s" % m["next_due"]})
                continue
            if verbose:
                print("MISSION %-12s (fire #%d)  goal: %s"
                      % (m["name"], m["run_count"] + 1, m["goal"][:80]))
            ap = Autopilot(god, base,
                           url=m.get("url") or "http://127.0.0.1:11434",
                           model=m.get("model") or "llama3.2",
                           max_steps=m.get("max_steps", 8),
                           heavy=bool(m.get("heavy")),
                           agent="mission:" + m["name"], verbose=verbose)
            rep = ap.run(m["goal"])
            m["run_count"] += 1
            m["last_run"] = datetime.now().isoformat(timespec="seconds")
            m["last_done"] = bool(rep.get("done"))
            m["last_note"] = scrub(str(rep.get("note") or ""))[:200]
            m["last_journal"] = rep.get("journal")
            if m["kind"] == "once":
                m["enabled"] = False       # a once-mission fires once
                m["next_due"] = None
            else:
                m["next_due"] = _next_due(m, now).isoformat(timespec="seconds")
            _save(base, data)              # crash-safe: state kept per mission
            report["fired"].append({k: m[k] for k in
                                    ("name", "last_done", "last_note",
                                     "last_journal", "next_due")})
            if verbose:
                print("  -> %s | %s\n" % ("DONE" if m["last_done"]
                                          else "NOT DONE", m["last_note"][:120]))
    finally:
        lk = _lock(base)
        if lk.exists():
            lk.unlink()
    return report


def watch(base, interval=60, verbose=True):
    """The clock that needs no cron: loop tick() until Ctrl-C."""
    print("missions watch: ticking every %ds - Ctrl-C stops the clock "
          "(the god is never killed; the clock simply rests)" % interval)
    try:
        while True:
            tick(base, verbose=verbose)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nclock stopped by the owner's hand - missions preserved")
        return 0
