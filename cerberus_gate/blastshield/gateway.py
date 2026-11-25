"""The guarded dispatcher — the part Gemini's code never had.

A shield that only judges payloads but never carries them is a
lecture, not a firewall. guarded_request() is the real hand: it asks
the gate, and ONLY on an ALLOW does anything touch the wire — with
the signed passport attached. Vetoed requests cost zero bytes.
"""
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Tuple

from .common import Decision


def guarded_request(shield, method: str, url: str, payload: str = "",
                    timeout: float = 15.0,
                    embed_canary: bool = False) -> Tuple[Decision, Optional[Dict[str, Any]]]:
    """Evaluate, dispatch, report. Returns (decision, response_or_None).

    The decision is authoritative even when response is None: a veto
    never leaves the house, and the caller gets the reason on the
    record instead of a socket error."""
    decision = shield.evaluate(method, url, payload, embed_canary=embed_canary)
    if not decision.allowed:
        return decision, None

    wire_payload = decision.meta.get("wire_payload", payload)
    body = wire_payload.encode("utf-8") if method.upper() in ("POST", "PUT", "PATCH") else None
    req = urllib.request.Request(url, data=body, method=method.upper())
    for name, value in decision.headers.items():
        req.add_header(name, value)
    if body is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

    status = None
    response: Optional[Dict[str, Any]] = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            response = {"status": status,
                        "headers": dict(resp.headers.items()),
                        "body": resp.read(65536).decode("utf-8", "replace")}
    except urllib.error.HTTPError as exc:
        status = exc.code
        response = {"status": status, "error": f"HTTP {exc.code}",
                    "body": exc.read(65536).decode("utf-8", "replace")[:2000]}
    except Exception as exc:  # DNS failure, timeout, refused...
        response = {"status": 0, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        # Always report back to the breaker; free the concurrency slot.
        shield.release(decision.meta.get("request_id", ""), status)
    return decision, response
