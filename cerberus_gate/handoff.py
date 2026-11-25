"""HANDOFF - the record follows the person, not the account.

The problem it kills: work lives inside a chat, the chat hits a token
wall, the human copies the transcript to a new account, and the new chat
burns tokens re-reading old lines just to know what happened.

The doctrine answer: the memory was never supposed to live in the chat.
It lives in the owner's Cerberus, outside every account and every vendor.
A new chat - new account, new vendor, whatever - asks the record for the
digest instead of re-reading history. One compact brief, not a transcript.

  python3 -m cerberus_gate handoff                     # the continuation brief
  python3 -m cerberus_gate handoff "the newsletter task"
  python3 -m cerberus_gate action-schema --url http://127.0.0.1:7717
                                                 # OpenAPI for a ChatGPT
                                                 # Action: same memory in
                                                 # a different vendor

And the deletion ask is already law: gdpr erase - the OWNER removes
unwanted data from the record; the AI never hides anything from it.
"""
import json
from datetime import datetime
from pathlib import Path

from .rules import redact as scrub


# ----------------------------------------------------------------------
def brief(god, base, query="", limit=8):
    """One compact continuation brief from the record - the block a new
    chat (any vendor) reads INSTEAD of an old transcript."""
    base = Path(base)
    rec = god.mind.recall(query or None, limit=limit)
    mem = rec.get("notes") if isinstance(rec, dict) else rec
    v = god.mind.verify()
    book = god.book.report() if hasattr(god, "book") else ""

    # the latest mission journal, if any - the "where am I" of work
    last_run = None
    jdir = base / "autopilot"
    if jdir.exists():
        js = sorted(jdir.glob("run-*.json"), key=lambda p: p.stat().st_mtime)
        if js:
            try:
                r = json.loads(js[-1].read_text(encoding="utf-8"))
                last_run = {"goal": r.get("goal"), "done": r.get("done"),
                            "note": (r.get("note") or "")[:200],
                            "steps": r.get("steps_used"),
                            "journal": js[-1].name}
            except Exception:
                last_run = None

    lines = ["[CONTINUATION BRIEF - from the owner's record, not a chat]"]
    if last_run:
        lines += ["last mission: %r -> %s after %s steps | %s"
                  % (last_run["goal"], "DONE" if last_run["done"] else
                     "NOT DONE", last_run["steps"], last_run["note"])]
    if mem:
        lines.append("the record knows (newest first):")
        lines += ["- %s" % scrub(str(m))[:160] for m in mem]
    else:
        lines.append("the record has nothing on %r yet" % (query or "this"))
    ff = god.mind.failure_facts()
    if ff:
        lines.append("failure facts (never re-report these as victories):")
        lines += ["- %s" % scrub(str(f))[:160] for f in ff[-5:]]
    lines.append("record verdict: %s (%s)" % (v.get("verdict"), v.get("detail")))
    if book:
        lines.append("incidents on file: %s" % str(book).strip().splitlines()[0][:120])
    lines.append("carry this brief into the next chat - never the transcript.")
    return "\n".join(lines)


# ----------------------------------------------------------------------
def action_schema(url):
    """OpenAPI 3 for one gate - import it as a ChatGPT Action (or any
    OpenAPI tool host) and a DIFFERENT vendor reads/writes the SAME
    record through the conscience. Same law, same wall, same evidence."""
    url = url.rstrip("/")
    return {
        "openapi": "3.1.0",
        "info": {"title": "Cerberus gate - the owner's record",
                 "version": "1.0",
                 "description": "Memory-first access to the owner's record. "
                                "Every write passes the conscience. The gate "
                                "enforces the owner's law, not the caller's."},
        "servers": [{"url": url}],
        "paths": {
            "/impulse": {"post": {
                "operationId": "impulse",
                "summary": "One step through the conscience: recall memory, "
                           "learn a fact, seal evidence, scan a draft before "
                           "it leaves",
                "requestBody": {"required": True, "content": {
                    "application/json": {"schema": {"type": "object",
                        "properties": {
                            "verb": {"type": "string",
                                     "enum": ["recall", "write", "append",
                                              "edit", "read", "seal",
                                              "scan_draft", "session_open"]},
                            "target": {"type": "string"},
                            "text": {"type": "string"},
                            "why": {"type": "string"},
                            "agent": {"type": "string"}},
                        "required": ["verb"]}}}},
                "responses": {"200": {"description": "the conscience's verdict"}}}},
            "/verify": {"get": {
                "operationId": "verify",
                "summary": "Verify the memory chain before trusting it",
                "responses": {"200": {"description": "chain verdict"}}}},
            "/incidents": {"get": {
                "operationId": "incidents",
                "summary": "Every refused, redirected or rewritten step",
                "responses": {"200": {"description": "the incident book"}}}},
            "/seal": {"post": {
                "operationId": "seal",
                "summary": "Sign the evidence chain now (milestone proof)",
                "requestBody": {"content": {"application/json": {
                    "schema": {"type": "object", "properties": {
                        "why": {"type": "string"}}}}}},
                "responses": {"200": {"description": "seal status"}}}},
        },
        "components": {"securitySchemes": {"HostToken": {
            "type": "apiKey", "in": "header", "name": "X-Cerberus-Token"}}},
    }
