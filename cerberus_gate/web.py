"""WEB — the god's hands on a real browser (the browse verb).

The god gets FULL access to the web, like everything else: no cage, no
allowlist of sites. What it also gets is the same law of motion as the
rest of the body:

  - every browse impulse is witnessed BEFORE the browser opens
    (classified as "web" - heavy, watched, incident-recorded),
  - secrets typed into any website are exfiltration - the packet is
    redirected into the vault and the wire stays silent (rules.py),
  - every step lands in a transcript, every screenshot lands in evidence/,
  - what the god SEES on the web is learned into the one shared memory -
    so a later "success. zero failures." report that ignores a web error
    is deception, rewritten with the true record.

Steps are plain dicts, easy to read and easy to audit:

  {"action": "goto",  "url": "https://onecompiler.com/python"}
  {"action": "click", "selector": ".monaco-editor .view-lines"}
  {"action": "press", "key": "ControlOrMeta+a"}
  {"action": "type",  "text": "hello", "delay": 30}
  {"action": "fill",  "selector": "#q", "text": "search this"}
  {"action": "click", "selector": "button", "text": "Run", "nth": 0}
  {"action": "wait",  "text": "NameError", "ms": 20000}
  {"action": "read",  "selector": "span.text-red-600", "save": "error_text"}
  {"action": "shot",  "name": "onecompiler-hello"}

Playwright is an optional dependency. Without it the god simply reports
"the browser is not installed on this machine" - the mind still records
the impulse and the verdict.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_STEPS = 24          # a browse impulse may not wander forever
STEP_TIMEOUT_MS = 20000 # per-step patience
ALLOWED_SCHEMES = {"http", "https", "file", ""}


def available():
    """True if playwright is importable on this machine."""
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def missing_note():
    return ("the browser is not installed on this machine - install it with: "
            "pip3 install playwright && python3 -m playwright install chromium")


def normalize_steps(imp):
    """Accept steps in payload (list, or dict with 'steps'), or JSON in text."""
    steps = imp.get("payload")
    if isinstance(steps, dict):
        steps = steps.get("steps")
    if not isinstance(steps, list):
        steps = None
    if steps is None:
        raw = imp.get("text")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    steps = parsed
                elif isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
                    steps = parsed["steps"]
            except Exception:
                steps = None
    steps = [s for s in (steps or []) if isinstance(s, dict) and s.get("action")]
    # a bare target means "open this page first"
    tgt = str(imp.get("target") or "")
    if tgt and not any(s.get("action") == "goto" for s in steps):
        steps = [{"action": "goto", "url": tgt}] + steps
    return steps[:MAX_STEPS]


def _tag():
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def run_steps(steps, evidence_dir):
    """Execute the steps in a real Chromium. Returns the god's web result."""
    if not available():
        return {"ok": False, "note": missing_note(), "browser": "absent"}
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception as e:
        return {"ok": False, "note": "browser import failed: %s" % e.__class__.__name__}

    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    tag = _tag()
    transcript, saved, shots = [], {}, []

    def note(action, ok, detail=""):
        transcript.append({"n": len(transcript) + 1, "action": action,
                           "ok": bool(ok), "detail": str(detail)[:300]})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            for s in steps:
                act = s.get("action", "")
                try:
                    if act == "goto":
                        url = s.get("url") or ""
                        scheme = url.split(":", 1)[0].lower()
                        if scheme not in ALLOWED_SCHEMES:
                            note("goto:" + scheme, False, "scheme not allowed")
                            continue
                        page.goto(url, timeout=STEP_TIMEOUT_MS, wait_until="domcontentloaded")
                        page.wait_for_timeout(int(s.get("ms", 1200)))
                        note("goto", True, "%s -> %s" % (url[:80], page.title()[:80]))
                    elif act == "click":
                        loc = page.locator(s["selector"])
                        if s.get("text"):
                            loc = loc.filter(has_text=s["text"])   # filter FIRST...
                        loc = loc.nth(int(s.get("nth", 0)))        # ...then pick
                        loc.first.click(timeout=STEP_TIMEOUT_MS)
                        note("click", True, s["selector"][:100])
                    elif act == "press":
                        page.keyboard.press(s.get("key", "Enter"))
                        note("press", True, s.get("key", "Enter"))
                    elif act == "type":
                        page.keyboard.type(s.get("text", ""), delay=int(s.get("delay", 25)))
                        note("type", True, "%d chars" % len(s.get("text", "")))
                    elif act == "fill":
                        loc = page.locator(s["selector"]).nth(int(s.get("nth", 0)))
                        loc.first.fill(s.get("text", ""), timeout=STEP_TIMEOUT_MS)
                        note("fill", True, s["selector"][:100])
                    elif act == "wait":
                        if s.get("selector"):
                            page.wait_for_selector(s["selector"], timeout=int(s.get("ms", STEP_TIMEOUT_MS)))
                            note("wait", True, s["selector"][:100])
                        elif s.get("text"):
                            page.wait_for_selector("text=" + s["text"],
                                                   timeout=int(s.get("ms", STEP_TIMEOUT_MS)))
                            note("wait", True, "text %r" % s["text"][:60])
                        else:
                            page.wait_for_timeout(int(s.get("ms", 500)))
                            note("wait", True, "%d ms" % int(s.get("ms", 500)))
                    elif act == "read":
                        loc = page.locator(s["selector"]).nth(int(s.get("nth", 0)))
                        txt = loc.first.inner_text(timeout=STEP_TIMEOUT_MS)
                        name = s.get("save") or "text%d" % (len(saved) + 1)
                        saved[name] = txt.strip()
                        note("read", True, "%s = %r" % (name, txt.strip()[:120]))
                    elif act == "shot":
                        name = "%s-web-%s.png" % (tag, s.get("name", "page"))
                        f = evidence_dir / name
                        page.screenshot(path=str(f), full_page=bool(s.get("full")))
                        shots.append(f.name)
                        note("shot", True, f.name)
                    else:
                        note(act or "?", False, "unknown action")
                except PWTimeout:
                    note(act, False, "timed out after %d ms" % STEP_TIMEOUT_MS)
                except Exception as e:
                    note(act, False, "%s: %s" % (e.__class__.__name__, str(e)[:160]))
        finally:
            try:
                browser.close()
            except Exception:
                pass

    ok = bool(saved) or any(t["ok"] for t in transcript)
    out = {"ok": ok, "steps_done": sum(1 for t in transcript if t["ok"]),
           "steps_total": len(transcript), "transcript": transcript,
           "shots": shots, "browser": "chromium"}
    if saved:
        out["output"] = "\n".join("%s: %s" % (k, v) for k, v in saved.items())
        out["saved"] = saved
    else:
        out["output"] = "; ".join("%s=%s" % (t["action"], "ok" if t["ok"] else "FAIL")
                                  for t in transcript)
    return out
