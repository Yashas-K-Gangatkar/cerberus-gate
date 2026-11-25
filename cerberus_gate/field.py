"""FIELD — the field-trial kit (gap 2: real-world miles, stage 3).

The real miles are driven on YOUR Mac, in YOUR work. This kit
instrument them:

  python3 -m cerberus_gate field start            open a trial
  python3 -m cerberus_gate field report           the weekly field report
  python3 -m cerberus_gate field miss "it lied and got away"    mark a miss
  python3 -m cerberus_gate field clear-lock bot-1  a human unlocks an agent

The metric that matters: misses marked by the human. Everything else
the conscience already counts itself.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from .law import default_base
from .mind import Mind
from .law import Law
from .incidents import IncidentBook


def _field_dir(base):
    d = Path(base) / "field"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start(base=None):
    base = Path(base or default_base())
    f = _field_dir(base) / "trial.json"
    if not f.exists():
        f.write_text(json.dumps({"started": _now(), "owner": base.name}, indent=1),
                     encoding="utf-8")
        print("field trial opened: %s" % f)
        print("work normally. every impulse is recorded by the conscience.")
        print("when it misses something, mark it:")
        print('  python3 -m cerberus_gate field miss "what went wrong, in your words"')
    else:
        print("field trial already open since %s" % json.loads(f.read_text())["started"])
    return 0


def miss(note, base=None):
    base = Path(base or default_base())
    f = _field_dir(base) / "misses.jsonl"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": _now(), "note": str(note)}) + "\n")
    print("miss recorded. the trial only improves if you mark these honestly.")
    return 0


def clear_lock(agent, base=None):
    base = Path(base or default_base())
    Mind(base, Law(base)).clear_lock(agent)
    print("agent '%s' unlocked by the human. the memory keeps the whole story." % agent)
    return 0


def report(base=None):
    base = Path(base or default_base())
    d = _field_dir(base)
    trial = d / "trial.json"
    if not trial.exists():
        print("no field trial open - run: python3 -m cerberus_gate field start")
        return 2
    started = json.loads(trial.read_text())["started"]
    try:
        hours = round((datetime.now(timezone.utc)
                       - datetime.fromisoformat(started)).total_seconds() / 3600, 1)
    except Exception:
        hours = "?"
    mind = Mind(base, Law(base))
    v = mind.verify()
    book = IncidentBook(base)
    misses = []
    mf = d / "misses.jsonl"
    if mf.exists():
        for ln in mf.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                misses.append(json.loads(ln))
    print("FIELD REPORT - %s" % base)
    print("  trial open for : %s hours" % hours)
    print("  memory chain   : %s (%s)" % (v["verdict"], v["detail"]))
    print("  incidents      : %d" % len(book.items))
    print()
    print(book.agents_report())
    print()
    print("  misses marked by the human: %d" % len(misses))
    for m in misses:
        print("    - [%s] %s" % (m["ts"], m["note"]))
    print()
    if misses:
        print("every miss above is a detector to build. that is how the rules grow up.")
    else:
        print("no misses marked. keep working - mark honestly when it slips.")
    return 0
