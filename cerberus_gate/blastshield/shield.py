"""LAYER 1 — the internet shield. The gate between the agent and the
open internet.

What Gemini's draft got right: rate law, burst throttle, the idea of
an egress gate. What this build fixes, one law at a time:

  LAW 1  runaway recursion  — burst throttle, per-minute cap, AND a
         circuit breaker with three honest states (CLOSED / OPEN /
         HALF_OPEN): the breaker quarantines a hammered domain and
         then heals it with a single probe. Gemini's breaker never
         recovered; that is a self-inflicted DoS on your own agent.
  LAW 2  exploit interception — every payload is URL-decoded TWICE and
         whitespace-collapsed BEFORE pattern matching, so encoded
         attacks die and honest apostrophes ("don't ship it",
         "page#section") sail through. Gemini's regex vetoed every
         apostrophe and every hash sign; a shield that eats a third
         of legitimate traffic gets uninstalled in a week.
  LAW 3  governance that is actually cryptographic — an HMAC-SHA256
         passport signed with the OWNER's key (which the agent never
         holds), timestamped and nonce-replay-protected. A receiving
         server holding the shared key can verify it. A naked sha256
         anyone can recompute is a checksum, not a signature.
  LAW 4  the concurrency governor Gemini advertised but never wrote —
         a hard cap on simultaneous in-flight requests per domain.
  LAW 5  the data law — before anything leaves, Layer 3's redactor
         scrubs the body. The secret never boards the wire.
"""
import ipaddress
import json
import re
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .common import Decision, OwnerKey, sha256_hex, b64e
from .vault import LeakProofVault


# High-confidence exploit families. Each entry: (CLASS, compiled regex).
# The list catches the classic payload families; it is defense in
# depth, not a WAF. The deeper defense is LAW 5: carry no secrets.
_EXPLOIT_PATTERNS = [
    ("SQLI", re.compile(r"union[\s+(/(*]+select", re.I)),
    ("SQLI", re.compile(r"\b(?:or|and)\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+", re.I)),
    ("SQLI", re.compile(r";\s*drop\s+(?:table|database)\b", re.I)),
    ("SQLI", re.compile(r"\b(?:information_schema|xp_cmdshell|load_file)\b", re.I)),
    ("SQLI", re.compile(r"\b(?:sleep|benchmark|waitfor)\s*[(\s+]\s*(?:\d+|delay)", re.I)),
    ("XSS", re.compile(r"<\s*script\b", re.I)),
    ("XSS", re.compile(r"javascript\s*:[^\"']*(?:alert|eval|fetch|document)\s*\(", re.I)),
    ("XSS", re.compile(r"\bon(?:error|load|click|mouseover|focus|blur)\s*=\s*(?:alert|eval|fetch|location|document|window)\b", re.I)),
    ("CMDI", re.compile(r"`[^`]+`")),
    ("CMDI", re.compile(r"\$\([^)]*\)")),
    ("CMDI", re.compile(r"[;|]\s*(?:curl|wget|bash|sh|nc|ncat|python|perl|ruby)\b", re.I)),
    ("TRAV", re.compile(r"(?:\.\./){2,}")),
    ("SSTI", re.compile(r"\{\{\s*\d+\s*[*/+]\s*\d+\s*\}\}")),
    ("JNDI", re.compile(r"\$\{\s*jndi\s*:", re.I)),
]

# SSRF targets: loopback, RFC1918, link-local (incl. cloud metadata).
_SSRF_HOSTS = {"localhost", "metadata.google.internal"}


@dataclass
class DomainState:
    timestamps: List[float] = field(default_factory=list)
    in_flight: Dict[str, float] = field(default_factory=dict)
    consecutive_errors: int = 0
    state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    opened_at: float = 0.0


class InternetShield:
    CLOSED, OPEN, HALF_OPEN = "CLOSED", "OPEN", "HALF_OPEN"

    def __init__(self, owner_key: OwnerKey, ledger=None, vault: Optional[LeakProofVault] = None,
                 agent_id: str = "CERBERUS-AGENT-01",
                 max_per_minute: int = 30, min_interval: float = 0.5,
                 max_concurrent: int = 4, breaker_cooldown: float = 30.0,
                 error_threshold: int = 3, exfil_policy: str = "redact") -> None:
        self.key = owner_key
        self.ledger = ledger
        self.vault = vault
        self.agent_id = agent_id
        self.max_per_minute = max_per_minute
        self.min_interval = min_interval
        self.max_concurrent = max_concurrent
        self.breaker_cooldown = breaker_cooldown
        self.error_threshold = error_threshold
        self.exfil_policy = exfil_policy
        self.domains: Dict[str, DomainState] = {}
        self._seen_nonces: Dict[str, float] = {}
        self._last_decision: Dict[str, str] = {}

    # ------------------------------------------------- helpers ----
    @staticmethod
    def _host(url: str) -> str:
        try:
            return (urllib.parse.urlparse(url).hostname or "").lower()
        except ValueError:
            return ""

    @staticmethod
    def _normalize(text: str) -> str:
        """Decode twice, collapse whitespace, strip nulls — THEN match.
        %2527%20OR becomes ' OR before the scanner ever sees it."""
        out = text
        for _ in range(2):
            try:
                decoded = urllib.parse.unquote(out)
                if decoded == out:
                    break
                out = decoded
            except Exception:
                break
        return out.replace("\x00", " ")

    def _is_ssrf_target(self, host: str) -> bool:
        if not host or host in _SSRF_HOSTS or host.endswith(".internal") or host.endswith(".local"):
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is None and host.isdigit():
            try:
                # decimal-encoded IPv4 ("http://2852039166/" IS the cloud
                # metadata address wearing a costume) - v2.8.2 closes it
                ip = ipaddress.IPv4Address(int(host))
            except ValueError:
                ip = None
        if ip is None:
            return False
        return (ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_unspecified or ip.is_reserved)

    def _scan_exploits(self, text: str) -> Optional[Tuple[str, str]]:
        norm = self._normalize(text)
        for family, pattern in _EXPLOIT_PATTERNS:
            if pattern.search(norm):
                return family, pattern.pattern[:48]
        return None

    def _veto(self, code: str, reason: str, host: str = "") -> Decision:
        if self.ledger:
            self.ledger.append("L1_VETO", {"code": code, "host": host})
        return Decision(False, code, reason)

    # ------------------------------------------------ the gate ----
    def evaluate(self, method: str, url: str, payload: str = "",
                 embed_canary: bool = False) -> Decision:
        now = time.time()
        try:
            parts = urllib.parse.urlparse(url)
        except ValueError:
            return self._veto("L1_MALFORMED_URL", "Request URL could not be parsed.")
        host = (parts.hostname or "").lower()

        if parts.scheme not in ("http", "https"):
            return self._veto("L1_SCHEME_FORBIDDEN",
                              f"Egress vetoed: scheme '{parts.scheme}' is not a web scheme. "
                              "Only http/https leave the house.", host)

        # LAW 0: destinations the owner never named — the inner network.
        if self._is_ssrf_target(host):
            return self._veto("L1_SSRF_BLOCKED",
                              f"Egress vetoed: '{host}' is an internal/metadata address. "
                              "Agents do not get to talk to the machine's own innards.", host)

        st = self.domains.setdefault(host, DomainState())

        # LAW 1a: circuit breaker (OPEN / HALF_OPEN).
        if st.state == self.OPEN:
            if now - st.opened_at < self.breaker_cooldown:
                wait = round(self.breaker_cooldown - (now - st.opened_at), 1)
                return self._veto("L1_CIRCUIT_OPEN",
                                  f"Egress halted: '{host}' is quarantined by the circuit "
                                  f"breaker to protect the remote server. Probe in ~{wait}s.", host)
            st.state = self.HALF_OPEN  # one probe gets through
            st.timestamps = []         # the quarantine served its sentence: clean slate

        if st.state == self.HALF_OPEN and st.in_flight:
            return self._veto("L1_CIRCUIT_PROBING",
                              f"Egress held: '{host}' is in half-open probe; "
                              "one request at a time until it proves healthy.", host)

        # LAW 2: exploit interception AFTER normalization.
        hit = self._scan_exploits(f"{url} {payload}")
        if hit:
            family, snippet = hit
            return self._veto("L2_EXPLOIT_" + family,
                              f"Egress vetoed: outbound payload matches a {family} "
                              f"attack family. The open internet is not a punching bag.", host)

        # LAW 1b: burst throttle.
        st.timestamps = [t for t in st.timestamps if now - t < 60]
        if st.timestamps and (now - st.timestamps[-1]) < self.min_interval:
            return self._veto("L1_BURST_FLOOD",
                              f"Egress throttled: sub-interval burst on '{host}'. "
                              "Machines wait their turn.", host)

        # LAW 1c: per-minute rate + breaker trip.
        if len(st.timestamps) >= self.max_per_minute:
            self._trip_breaker(st, host)
            return self._veto("L1_RATE_BREACH",
                              f"Circuit breaker tripped: over {self.max_per_minute} req/min "
                              f"on '{host}'. The remote server is protected.", host)

        # LAW 4: concurrency governor.
        if len(st.in_flight) >= self.max_concurrent:
            return self._veto("L1_CONCURRENCY_CAP",
                              f"Egress held: {len(st.in_flight)} in-flight requests to '{host}' "
                              f"(cap {self.max_concurrent}). Politeness is enforced, not suggested.", host)

        # LAW 5: data law — nothing sensitive boards the wire.
        redacted_count = 0
        canary = ""
        wire_payload = payload
        if self.vault and payload:
            safe, hits = self.vault.redact(payload)
            if hits:
                if self.exfil_policy == "block":
                    return self._veto("L5_DATA_EXFIL",
                                      f"Egress vetoed: payload carries {len(hits)} secret(s) "
                                      f"({', '.join(h.label for h in hits)}). Policy is block.", host)
                wire_payload = safe
                redacted_count = len(hits)
                if self.ledger:
                    self.ledger.append("L5_REDACT", {"host": host,
                                                     "labels": [h.label for h in hits]})
            if embed_canary:
                canary = self.vault.mint_canary(f"{method} {host}{parts.path}")
                wire_payload = wire_payload + f" [[{canary}]]" if wire_payload else f"[[{canary}]]"

        # Commit: rate bookkeeping + in-flight + signed passport.
        st.timestamps.append(now)
        request_id = secrets.token_hex(6)
        st.in_flight[request_id] = now

        passport = {
            "m": method.upper(), "h": host, "p": parts.path or "/",
            "ts": round(now, 3), "nc": secrets.token_hex(8),
            "ph": sha256_hex(wire_payload.encode("utf-8"))[:32],
            "ag": self.agent_id,
        }
        passport_b64 = b64e(json.dumps(passport, sort_keys=True,
                                       separators=(",", ":")).encode())
        signature = self.key.sign(b"GM1|" + passport_b64.encode())

        headers = {
            "X-Cerberus-Governed": "true",
            "X-Agent-ID": self.agent_id,
            "X-Cerberus-Passport": passport_b64,
            "X-Cerberus-Signature": signature,
        }
        if redacted_count:
            headers["X-Cerberus-Redacted"] = str(redacted_count)
        if canary:
            headers["X-Cerberus-Canary"] = canary

        if self.ledger:
            self.ledger.append("L1_ALLOW", {
                "request_id": request_id, "method": method.upper(),
                "host": host, "path": parts.path or "/",
                "redacted": redacted_count, "canary": canary,
                "state": st.state,
            })

        reason = "Outbound request verified by the blast-shield."
        if redacted_count:
            reason += f" {redacted_count} secret(s) redacted before boarding."
        if st.state == self.HALF_OPEN:
            reason += " (half-open probe: one request to prove the domain healthy.)"

        self._last_decision[request_id] = host
        return Decision(True, "L1_ALLOW", reason, headers,
                        {"request_id": request_id, "wire_payload": wire_payload,
                         "canary": canary})

    def release(self, request_id: str, status: Optional[int] = None) -> None:
        """Call after dispatch: frees the concurrency slot and reports
        the outcome to the breaker (2xx heals, 429/5xx accumulates)."""
        host = self._last_decision.pop(request_id, None)
        if not host:
            return
        st = self.domains.get(host)
        if st:
            st.in_flight.pop(request_id, None)
        if status is None or not st:
            return
        if 200 <= status < 400:
            st.consecutive_errors = 0
            if st.state == self.HALF_OPEN:
                st.state = self.CLOSED
                if self.ledger:
                    self.ledger.append("BREAKER_CLOSE", {"host": host})
        elif status == 429 or status >= 500:
            st.consecutive_errors += 1
            if st.state == self.HALF_OPEN or st.consecutive_errors >= self.error_threshold:
                self._trip_breaker(st, host)

    def _trip_breaker(self, st: DomainState, host: str) -> None:
        st.state = self.OPEN
        st.opened_at = time.time()
        if self.ledger:
            self.ledger.append("BREAKER_OPEN", {"host": host})

    # ------------------------------------------- server-side check ----
    def verify_headers(self, headers: Dict[str, str],
                       received_payload: str = "") -> Tuple[bool, str]:
        """For the RECEIVING server (or the owner auditing traffic):
        decode the passport, check freshness and replay, re-verify the
        HMAC with the shared owner key."""
        passport_b64 = headers.get("X-Cerberus-Passport", "")
        signature = headers.get("X-Cerberus-Signature", "")
        if not passport_b64 or not signature:
            return False, "missing passport or signature"
        try:
            from .common import b64d
            passport = json.loads(b64d(passport_b64))
        except Exception as exc:
            return False, f"malformed passport ({exc})"
        if not self.key.verify(b"GM1|" + passport_b64.encode(), signature):
            return False, "signature does not verify (tampered or forged)"
        age = time.time() - float(passport["ts"])
        if abs(age) > 300:
            return False, f"passport stale ({int(age)}s old)"
        nonce = passport["nc"]
        if nonce in self._seen_nonces:
            return False, "replayed nonce"
        self._prune_nonces()
        self._seen_nonces[nonce] = time.time()
        body_hash = sha256_hex(received_payload.encode("utf-8"))[:32]
        if received_payload and body_hash != passport["ph"]:
            return False, "payload hash mismatch (body tampered in transit)"
        return True, f"governed request from {passport['ag']} verified"

    def _prune_nonces(self) -> None:
        now = time.time()
        self._seen_nonces = {n: t for n, t in self._seen_nonces.items()
                             if now - t < 600}
