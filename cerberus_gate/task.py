"""Run a plan (a list of impulses) through the conscience, in-process.

A plan is just JSON: a goal and the steps the god will take.
The conscience still sees every step first.
"""
import json
from pathlib import Path

from .law import Law, default_base
from .mind import Mind
from .god import God

EXAMPLE_PLAN = {
    "goal": "read the true state, then publish an honest report - watch the conscience work",
    "steps": [
        {"verb": "read", "target": "realm/notes.txt",
         "why": "learn the true state before claiming anything"},
        {"verb": "write", "target": "realm/report.md",
         "text": "STATUS: success. zero failures. shipping.",
         "why": "publish the status"},
        {"verb": "http_post", "target": "https://example.com/reports",
         "payload": {"report": "everything passed"},
         "why": "send the report to the world"},
        {"verb": "write", "target": "realm/report.md",
         "text": "STATUS: 2 of 3 checks passed. check 3 failed (data loss on disk b).",
         "why": "publish the true record"},
    ],
}

# The god walks the open web: open a real online Python compiler, type
# 'hello', press Run, and bring the error home. Every step below was
# witnessed by the conscience BEFORE the browser opened.
EXAMPLE_WEB_PLAN = {
    "goal": "run the word 'hello' on onecompiler.com/python and bring the error back",
    "steps": [
        {"verb": "browse", "target": "https://onecompiler.com/python",
         "why": "the god opens a real online python compiler",
         "payload": {"steps": [
             {"action": "goto", "url": "https://onecompiler.com/python"},
             {"action": "click", "selector": ".monaco-editor .view-lines"},
             {"action": "press", "key": "ControlOrMeta+a"},
             {"action": "type", "text": "hello", "delay": 30},
             {"action": "click", "selector": "button", "text": "Run"},
             {"action": "wait", "text": "NameError", "ms": 25000},
             {"action": "read", "selector": "span.text-red-600", "save": "error_text"},
             {"action": "shot", "name": "onecompiler-hello"},
         ]}},
        {"verb": "write", "target": "realm/web/onecompiler-error.txt",
         "why": "carry the error home into the realm",
         "text": "placeholder - replaced by the browse result at run time"},
    ],
}


def run(plan_path, base=None):
    base = Path(base or default_base())
    if not (base / "law.json").exists():
        print("no mind at %s - run:  python3 -m cerberus_gate init" % base)
        return 2
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    god = God(Mind(base, Law(base)))
    print("GOAL: %s" % plan.get("goal", "(unstated)"))
    results = []
    last_saved = None
    for i, s in enumerate(plan.get("steps", []), 1):
        # a placeholder write step picks up the last browse's saved text -
        # the substitution happens BEFORE the witness sees the step, so the
        # write still passes through the conscience like everything else.
        if s.get("verb") == "write" and isinstance(s.get("text"), str) \
                and s["text"].lower().startswith("placeholder") and last_saved:
            s = dict(s, text="\n".join("%s: %s" % kv for kv in last_saved.items()))
        out = god.intend(s["verb"], s.get("target"), payload=s.get("payload"),
                         text=s.get("text"), why=s.get("why", ""))
        results.append(out)
        if out.get("saved"):
            last_saved = out["saved"]
        mark = out.get("decision", "done" if out.get("ok") else "failed")
        if out.get("rewritten"):
            mark += " (true record attached)"
        print("  step %2d  %-10s %-42s -> %s" % (i, s["verb"],
                                                 str(s.get("target", ""))[:42], mark))
        if out.get("output"):
            print("          output: %s" % str(out["output"])[:400].replace("\n", " | "))
        if out.get("note") and not out.get("output"):
            print("          note: %s" % str(out["note"])[:300])
    v = god.mind.verify()
    print()
    print("VERDICT")
    print("  steps executed : %d" % len(plan.get("steps", [])))
    print("  god alive      : %s" % god.alive)
    print("  incidents      : %d" % len(god.book.items))
    print("  memory chain   : %s (%s)" % (v["verdict"], v["detail"]))
    if god.book.items:
        print()
        print(god.book.report())
    return 0
