"""OLLAMA BRIDGE - your free local model becomes the god's brain.

The model (ollama, LM Studio, any OpenAI-compatible endpoint) THINKS.
It never touches the world directly: every step it emits is judged by
the conscience before the body moves. This file is the proof that a
real, free, local AI can be given full hands - safely.

  python3 -m cerberus_gate ollama --stage create                    # news in your realm
  python3 -m cerberus_gate ollama --stage create --repo YOU/REPO    # ...and onto github
  python3 -m cerberus_gate ollama --stage delete  --repo YOU/REPO   # removed on your command

The git token travels in the request header at the moment of use
(CERBERUS_GIT_TOKEN / GITHUB_TOKEN env, or CERBERUS_GIT_TOKEN_FILE).
It never enters an impulse, the memory, or the dashboard.
"""
import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from . import rules
from .god import God, git_token
from .law import Law
from .mind import Mind

DEFAULT_URL = "http://127.0.0.1:11434"          # ollama's default port
GITHUB_HOST = "api.github.com"
ALLOWED_VERBS = ("read", "write", "append", "edit", "delete")

SYSTEM_PROMPT = """You are the brain of a guarded AI worker called the god.
You act ONLY through the conscience: one step at a time, nothing else.
Your verbs: read, write, append, edit, delete. A target is always a file inside the realm, like realm/news.md.
Answer with ONE json object and nothing else - no markdown, no commentary:
{"say": "<one short line to the owner>", "verb": "<verb>", "target": "<realm/file>", "text": "<file content or note>", "why": "<short reason>"}
When the whole task is finished, answer exactly:
{"say": "<one short line to the owner>", "done": "<one line summary>"}
The conscience may refuse, redirect or rewrite your step. Its verdict comes back to you as step_result - never argue, adapt."""


def chat(url, model, messages, timeout=120):
    """One round-trip to any OpenAI-compatible endpoint (ollama speaks it)."""
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps({"model": model, "messages": messages,
                         "stream": False}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8", "replace"))
    return (out.get("choices") or [{}])[0].get("message", {}).get("content", "")


def parse_step(text):
    """Pull the first json object out of the model's answer (it may
    wrap it in chatter or code fences; the conscience reads the intent,
    not the costume)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _line(mark, txt):
    print("  %s %s" % (mark, txt))


def run(base=None, url=DEFAULT_URL, model="llama3.2", stage="create",
        repo=None, path="news.md", agent="ollama", max_steps=8,
        hard=False, verbose=True, key=None):
    base = Path(base).expanduser()
    god = God(Mind(base, Law(base), key=key))
    mind = god.mind
    realm_file = mind.base / "realm" / path
    print("CERBERUS ollama bridge - stage: %s · brain: %s (%s) · model: %s"
          % (stage, "local/free", url, model))

    created_push = None
    if stage == "create":
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content":
                     "Task from the owner: create the file realm/%s and fill it "
                     "with one short original news article you invent yourself "
                     "(2-4 paragraphs). Then report done." % path}]
        done_say = ""
        for _ in range(max_steps):
            try:
                raw = chat(url, model, messages)
            except urllib.error.URLError as e:
                print("  ! the brain is not answering (%s) - is ollama running?"
                      % getattr(e, "reason", e))
                print("    start it:  ollama serve   (and pull a model: ollama pull %s)" % model)
                return {"ok": False, "error": "brain unreachable"}
            step = parse_step(raw)
            if step is None:
                messages.append({"role": "user", "content":
                                 "step_result: that was not one json object. "
                                 "Answer with ONE json object only."})
                continue
            _line("brain says:", rules.redact(str(step.get("say", "")))[:200])
            if step.get("done"):
                done_say = rules.redact(str(step.get("done", "")))[:200]
                break
            verb = str(step.get("verb") or "").strip()
            if verb not in ALLOWED_VERBS:
                messages.append({"role": "user", "content":
                                 "step_result: unknown verb '%s'. Use one of %s, "
                                 "as one json object." % (verb, ", ".join(ALLOWED_VERBS))})
                continue
            out = god.intend(verb, step.get("target"),
                             text=step.get("text"), payload=step.get("payload"),
                             why=str(step.get("why") or "")[:200], agent=agent)
            mark = {"refuse": "x REFUSED ", "redirect": "o REDIRECT",
                    "rewrite": "~ REWRITE"}.get(out.get("decision"), "= allowed")
            _line(mark + ":", "%s %s -> %s" % (
                verb, str(step.get("target"))[:40],
                rules.redact(str(out.get("note") or out.get("reason") or ""))[:120]))
            messages.append({"role": "user", "content": "step_result: " + json.dumps(
                {k: out.get(k) for k in ("ok", "decision", "note", "reason")},
                default=str)})

        # the owner's named destination: only if the owner gave a repo AND a token
        if repo and git_token():
            mind.law.name_destination(GITHUB_HOST)
            gh_url = "https://%s/repos/%s/contents/%s" % (GITHUB_HOST, repo, path)
            content = realm_file.read_bytes() if realm_file.exists() else b""
            out = god.intend("git_push", gh_url,
                             payload={"message": "Cerberus: %s written by the local brain"
                                      % path,
                                      "content_b64": base64.b64encode(content).decode()},
                             why="the owner named this repo and this file",
                             agent=agent)
            created_push = out
            _line("= git    :", rules.redact(str(out.get("note") or out.get("reason")))[:140])
        elif repo:
            _line("! git    :", "no git token found - the job stays local "
                  "(export CERBERUS_GIT_TOKEN=ghp_...)")

        exists = realm_file.exists()
        size = realm_file.stat().st_size if exists else 0
        v = mind.verify()
        print()
        print("JOB REPORT - ground truth from the conscience, not the brain's claim")
        print("  realm/%-12s %s" % (path, "WRITTEN (%d bytes)" % size if exists else "NOT WRITTEN"))
        if repo:
            pushed = bool(created_push and created_push.get("ok"))
            if pushed:
                gh_line = "PUSHED · " + rules.redact(str(created_push.get("note")))
            else:
                fallback = (created_push or {}).get("note") or "no token / no repo"
                gh_line = "NOT PUSHED · " + rules.redact(str(fallback))
            print("  %-19s %s" % ("github " + repo, gh_line))
        print("  %-19s %s (%s) · god alive: %s" % ("memory",
              v["verdict"], v["detail"], god.alive))
        if done_say:
            print("  %-19s %s" % ("the brain said", done_say))
        print("  watch it live      : python3 -m cerberus_gate dash")
        return {"ok": exists, "written": exists, "pushed": bool(
            created_push and created_push.get("ok")), "verify": v}

    if stage == "delete":
        print("  the owner commands: remove realm/%s%s"
              % (path, (" and " + repo + "/" + path) if repo else ""))
        out_local = god.intend("delete", "realm/" + path,
                               why="the owner commanded deletion", agent="owner")
        if out_local.get("repaired"):
            _line("= local  :", "the body deleted it - the anti-god restored it "
                  "byte-identical. nothing the AI deletes is ever gone; "
                  "the tombstone is in evidence/")
        elif out_local.get("ok"):
            _line("= local  :", rules.redact(str(out_local.get("note"))))
        else:
            _line("! local  :", rules.redact(str(out_local.get("note") or out_local.get("reason"))))
        out_gh = None
        if repo and git_token():
            gh_url = "https://%s/repos/%s/contents/%s" % (GITHUB_HOST, repo, path)
            out_gh = god.intend("git_delete", gh_url,
                                payload={"message": "Cerberus: remove %s (owner command)" % path},
                                why="the owner commanded deletion", agent="owner")
            _line(("= git    :" if out_gh.get("ok") else "! git    :"),
                  rules.redact(str(out_gh.get("note") or out_gh.get("reason")))[:140])
        elif repo:
            _line("! git    :", "no git token found - github side untouched "
                  "(export CERBERUS_GIT_TOKEN=ghp_...)")
        if hard:
            realm_file.unlink(missing_ok=True)   # the OWNER's own hand, not the god's
            mind.learn("owner removed realm/%s by hand (--hard)" % path)
            _line("= owner  :", "you removed realm/%s yourself - beyond the god's repair" % path)
        v = mind.verify()
        print()
        print("JOB REPORT - ground truth from the conscience")
        print("  realm/%-12s %s" % (path,
              "STILL THERE (the conscience restores what the AI deletes - "
              "run again with --hard to remove it as the owner)"
              if realm_file.exists() else "GONE (removed by the owner's own hand)"))
        if repo:
            print("  %-19s %s" % ("github " + repo,
                  rules.redact(str(out_gh.get("note"))) if out_gh else
                  "untouched (no token or no --repo)"))
        print("  %-19s %s (%s) · god alive: %s" % ("memory",
              v["verdict"], v["detail"], god.alive))
        return {"ok": True, "deleted_locally": not realm_file.exists(),
                "git": out_gh, "verify": v}

    print("unknown stage: %s (use create or delete)" % stage)
    return {"ok": False, "error": "unknown stage"}
