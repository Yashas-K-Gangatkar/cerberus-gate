"""CLAUDE BRIDGE - Claude itself becomes the god's brain.

Anthropic's API does not speak the OpenAI dialect the autopilot uses,
so this file is the translator: a tiny local endpoint that speaks
OpenAI on the near side and Anthropic on the far side.

    near side   POST /v1/chat/completions   (what Autopilot speaks)
    far side    POST /v1/messages           (what Claude speaks)

The API key travels from the environment to the wire at the moment of
use (ANTHROPIC_API_KEY). It is never written to disk, never enters an
impulse, the memory, or the record - the same rule as the git token.

Two ways to run it:

    python3 -m cerberus_gate claude                       # a long-lived local
                                                    # bridge on 127.0.0.1:8756
    python3 -m cerberus_gate autopilot "GOAL" --brain claude
                                                    # the loop spawns its
                                                    # own bridge in-process

Cost honesty: the bridge is free; talking to Claude costs Anthropic
tokens. Point --brain at ollama and the whole loop is free instead.

For tests the far side is movable: set ANTHROPIC_BASE_URL (default
https://api.anthropic.com) - never store that override anywhere.
"""
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_PORT = 8756
DEFAULT_MAX_TOKENS = 2048


def api_key():
    """Read at request time - the key never rests anywhere."""
    return os.environ.get("ANTHROPIC_API_KEY", "")


def base_url():
    return (os.environ.get("ANTHROPIC_BASE_URL")
            or "https://api.anthropic.com").rstrip("/")


# ----------------------------------------------------------------------
# the translation, pure and testable
# ----------------------------------------------------------------------
def translate_request(openai_req):
    """OpenAI dialect -> Anthropic dialect.

    system role moves to the top-level `system` field (Anthropic's rule);
    everything else keeps its order - the conversation's shape matters.
    """
    system = "\n".join(m.get("content", "") for m in
                       openai_req.get("messages", [])
                       if m.get("role") == "system")
    messages = [{"role": m["role"], "content": m.get("content", "")}
                for m in openai_req.get("messages", [])
                if m.get("role") in ("user", "assistant")]
    return {"model": openai_req.get("model", "claude-haiku-4-5"),
            "system": system or None,
            "messages": messages,
            "max_tokens": int(os.environ.get("ANTHROPIC_MAX_TOKENS")
                              or DEFAULT_MAX_TOKENS),
            "stream": False}


def translate_response(anthropic_resp):
    """Anthropic dialect -> OpenAI dialect (the part chat() reads)."""
    text = "".join(b.get("text", "") for b in anthropic_resp.get("content", [])
                   if b.get("type") == "text")
    return {"choices": [{"message": {"role": "assistant", "content": text},
                         "finish_reason": anthropic_resp.get("stop_reason")}],
            "usage": anthropic_resp.get("usage", {}),
            "model": anthropic_resp.get("model")}


def far_post(body, timeout=120):
    """One round-trip to Anthropic. The key touches the header here -
    at the moment of use - and is dropped when the call returns."""
    key = api_key()
    if not key:
        raise RuntimeError(
            "no ANTHROPIC_API_KEY in the environment - the bridge refuses "
            "to guess; export it or run --brain ollama (free)")
    req = urllib.request.Request(
        base_url() + "/v1/messages",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "x-api-key": key,
                 "anthropic-version": ANTHROPIC_VERSION},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ----------------------------------------------------------------------
# the local endpoint
# ----------------------------------------------------------------------
def make_handler():
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            if not self.path.rstrip("/").endswith("/v1/chat/completions"):
                self.send_response(404)
                self.end_headers()
                return
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                openai_req = json.loads(self.rfile.read(n) or b"{}")
                out = far_post(translate_request(openai_req))
                body = json.dumps(translate_response(out)).encode()
                self.send_response(200)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                body = json.dumps({"error": {"message": detail,
                                             "status": e.code}}).encode()
                self.send_response(e.code)
            except Exception as e:            # key missing, network down...
                body = json.dumps({"error": {"message": str(e),
                                             "status": 502}}).encode()
                self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):   # silence - the record lives in Cerberus
            pass

    return H


def serve(port=DEFAULT_PORT):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler())
    print("Cerberus claude bridge on http://127.0.0.1:%d  (Anthropic: %s)"
          % (port, base_url()))
    print("the autopilot speaks here; Claude speaks behind it")
    print("stop: Ctrl-C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def spawn(port=0):
    """An in-process bridge for one autopilot run - port 0 = the OS picks."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % srv.server_address[1], srv
