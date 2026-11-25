"""INTEGRATIONS — plug Cerberus into the tools teams already use (gap 3).

Five-minute recipes, all in this one file:

1. ANY PYTHON  -  guard a dict of tool functions:
       from cerberus_gate.integrations import guard_tools
       tools = guard_tools(god, {"run_command": ("shell", my_fn),
                                 "web_post":   ("http_post", my_fn)})

2. ANY PYTHON  -  guard one function with a decorator:
       from cerberus_gate.integrations import set_default_god, guarded
       set_default_god(god)
       @guarded("shell")
       def run(cmd): ...

3. LANGCHAIN   -  drop-in callback handler (duck-types the callback API):
       from cerberus_gate.integrations import CerberusCallbackHandler
       agent.run(input, callbacks=[CerberusCallbackHandler(god)])

4. MCP (Claude + any MCP client) - stdio server:
       python3 -m cerberus_gate mcp
   exposes tools: impulse, session_open, recall, scan_draft, seal,
   evidence, verify, incidents, law - and ships server INSTRUCTIONS that
   tell the model to open the session and read the memory before it
   answers (the T3/T7 fix: in the blind A/B the connected AI never went
   looking for what the gateway had written).

5. HTTP        -  already built in:  POST 127.0.0.1:7717/impulse
"""
import functools
import json
import sys

from . import __version__

_default_god = None


def set_default_god(god):
    global _default_god
    _default_god = god


def _heavy(out):
    return out.get("decision") in ("refuse", "redirect")


# ----------------------------------------------------------- 1. guard_tools
def guard_tools(god, tools):
    """tools: {name: (verb, callable)} -> {name: guarded callable}.

    Every call becomes an impulse first. refuse/redirect answers return
    a {'Cerberus': decision} dict INSTEAD of running the real function -
    the tool never fires when the anti-god says no.
    """
    guarded = {}
    for name, (verb, fn) in tools.items():
        def make(fn=fn, verb=verb, name=name):
            @functools.wraps(fn)
            def wrapped(*a, **k):
                # v2.8.2: a guarded tool is a named hand. Without this it
                # landed on the shared "default" agent and its strikes
                # were everybody's strikes.
                agent = k.pop("agent", None) or ("tool:" + name)
                first = str(a[0])[:400] if a else name
                out = god.intend(verb, target=name if not a else first,
                                 text=first if verb in ("shell",) else None,
                                 payload=None if verb in ("shell",) else
                                 {"args": [str(x)[:200] for x in a]},
                                 why="guarded tool call: " + name, agent=agent)
                if _heavy(out):
                    return {"cerberus_gate": out}
                return fn(*a, **k)
            return wrapped
        guarded[name] = make()
    return guarded


# ----------------------------------------------------------- 2. decorator
def guarded(verb, why=None):
    """@guarded("shell") - the function's first argument is the target."""
    def deco(fn):
        @functools.wraps(fn)
        def inner(*a, **k):
            god = k.pop("cerberus_gate", None) or _default_god
            if god is None:
                raise RuntimeError("no god bound - call set_default_god(god) first")
            first = str(a[0])[:400] if a else fn.__name__
            out = god.intend(verb, target=first,
                             text=first if verb == "shell" else None,
                             why=why or ("guarded: " + fn.__name__),
                             agent=k.pop("agent", None))
            if _heavy(out):
                return {"cerberus_gate": out}
            return fn(*a, **k)
        return inner
    return deco


# -------------------------------------------------- 3. LangChain handler
class CerberusCallbackHandler:
    """Drop into any LangChain runnable: callbacks=[CerberusCallbackHandler(god)].

    Duck-types the LangChain callback API (on_tool_start / on_tool_end /
    on_tool_error / on_agent_action). No langchain import needed.
    Tool ERRORS are learned into the shared memory - which is exactly
    what makes the deception detector smarter over time.
    """

    def __init__(self, god, agent="langchain"):
        self.god = god
        self.agent = agent
        self.current = None

    def on_tool_start(self, serialized, input_str, **kw):
        name = (serialized or {}).get("name", "tool")
        self.current = name
        self.god.intend("shell", target=name, text=str(input_str)[:500],
                        why="langchain tool start", agent=self.agent)

    def on_tool_end(self, output, **kw):
        self.god.mind.learn("tool %s finished: %s"
                            % (self.current, str(output)[:200]))
        self.current = None

    def on_tool_error(self, error, **kw):
        self.god.mind.learn("tool %s error: %s" % (self.current, error))
        self.current = None

    def on_agent_action(self, action, **kw):
        self.god.intend("read", target=str(getattr(action, "tool", "agent")),
                        why="langchain agent action", agent=self.agent)


# ------------------------------------------------------------ 4. MCP server
# THE T3/T7 FIX, part one: the initialize result carries server
# instructions. Claude Desktop surfaces them to the model - this is the
# one channel that speaks BEFORE the first question, so the memory gets
# read without the owner having to ask.
MCP_INSTRUCTIONS = (
    "CERBERUS is connected: the owner's runtime memory + conscience, with a "
    "signed evidence chain.\n"
    "1. SESSION START - call session_open first, before answering anything.\n"
    "2. MEMORY FIRST - before answering about past work, projects, people, "
    "decisions, commitments or credentials, call recall (optionally with a "
    "query). Chat history is NOT the record - the Cerberus memory is. If "
    "recall returns nothing on a topic, say the memory has nothing on it: "
    "never fill gaps from chat history alone.\n"
    "3. DRAFTS - before any email, report, post or PR description leaves, "
    "run scan_draft on the full text. Fix what it flags (secrets out, "
    "claims matched to the true record) and scan again if it changed much.\n"
    "4. MILESTONES - call seal after meaningful completed work: every seal "
    "is signed evidence that the record was intact at that moment.\n"
    "5. EGRESS (v2.9.0) - the ONLY way data leaves this machine through you "
    "is egress_send, and TWO layers judge it. Layer 1 (mechanics) checks "
    "the destination and the format. Layer 2 (the brain) READS the packet "
    "the way a person would: encodings hiding data, high-entropy runs, "
    "secret framing, drip patterns, intent. A VETO from either layer is "
    "sealed in the vault with a strike; a SUSPECT is HELD for the owner's "
    "verdict (cerb verdict allow|deny ID) and you cannot rush it. "
    "State your why on EVERY send - an unstated intent is itself a "
    "signal. Data stays in; leaks do not leave.\n"
    "Everything done through these tools is witnessed and chained in the "
    "owner's evidence ledger."
)

MCP_TOOLS = [
    {"name": "session_open", "description":
     "Call this ONCE at the START of every conversation, before answering "
     "anything. Opens the session, returns the memory digest (recent "
     "notes, failure facts, chain verdict, anti-duplicate stats) and "
     "writes the session itself into the signed evidence chain.",
     "inputSchema": {"type": "object", "properties": {
         "agent": {"type": "string"}}}},
    {"name": "recall", "description":
     "Read the owner's shared memory. Use BEFORE answering anything about "
     "past work, projects, people, decisions, commitments or credentials. "
     "Optional query filters by relevance; newest first. Chat history is "
     "not the record - this memory is. If nothing matches, say so.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "agent": {"type": "string"}}}},
    {"name": "scan_draft", "description":
     "The conscience reads the letter before it leaves the house. Run on "
     "EVERY outgoing email, report, post or PR description BEFORE sending. "
     "Flags secret-shaped material (redacted in the findings), victory "
     "claims that contradict the memory's failure facts, and duplicate "
     "drafts. Returns clean or flagged + findings.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}, "destination": {"type": "string"},
         "agent": {"type": "string"}}, "required": ["text"]}},
    {"name": "seal", "description":
     "Sign the evidence chain now. Call after any meaningful completed "
     "step - a seal is signed proof that the record up to this moment is "
     "intact, filed in evidence/ and chained into the WAL itself.",
     "inputSchema": {"type": "object", "properties": {
         "why": {"type": "string"}, "agent": {"type": "string"}}}},
    {"name": "evidence", "description":
     "The signed evidence chain status: chain verdict, every seal and "
     "whether it still holds, notes and anti-duplicate stats.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "impulse", "description":
     "Submit one impulse to the Cerberus conscience: verb in read|write|"
     "edit|append|delete|recall|session_open|scan_draft|seal|http_get|"
     "http_post|shell|browse|self_copy, plus target/text/payload/why/agent.",
     "inputSchema": {"type": "object", "properties": {
         "verb": {"type": "string"}, "target": {"type": "string"},
         "text": {"type": "string"}, "payload": {}, "why": {"type": "string"},
         "agent": {"type": "string"}}, "required": ["verb"]}},
    {"name": "verify", "description": "Verify the memory chain.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "incidents", "description": "The incident book, sorted by why.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "law", "description": "The owner's law.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "egress_check", "description":
     "Ask the gate what egress_send would do with a packet - WITHOUT "
     "sending it (v3.0.0b4: the check is the send, minus the wire). "
     "Returns ALLOW only for a packet the gate would actually dispatch; "
     "VETO (with the code and the plain reason: unnamed host, SSRF, "
     "exploit, shield absent) or SUSPECT (the send would HOLD it for the "
     "owner's verdict) otherwise. Local addresses and owner-unnamed "
     "hosts are VETO here exactly as the send refuses them there. Run "
     "this BEFORE egress_send whenever you are unsure; a check costs "
     "nothing, a leak is stopped and struck.",
     "inputSchema": {"type": "object", "properties": {
         "url": {"type": "string"}, "method": {"type": "string"},
         "body": {"type": "string"}, "why": {"type": "string"},
         "agent": {"type": "string"}},
         "required": ["url"]}},
    {"name": "egress_send", "description":
     "THE ONLY sanctioned way your data leaves this machine. Owner-named "
     "destinations are governed by the blast-shield (rate, burst, exploit "
     "interception, SSRF refusal, secrets redacted before the wire) and "
     "dispatched with the god's signed passport. An unnamed destination "
     "carrying data is exfiltration: the packet is sealed in the vault, "
     "the wire stays silent, your identity takes a strike - three strikes "
     "mean automatic probation. There is no other legitimate route.",
     "inputSchema": {"type": "object", "properties": {
         "url": {"type": "string"}, "method": {"type": "string"},
         "body": {}, "why": {"type": "string"}, "agent": {"type": "string"}},
         "required": ["url"]}},
    {"name": "scan_secrets", "description":
     "Instant secret-scan of any text (keys, tokens, JWTs, private-key "
     "blocks, cards, credential pairs). Returns the masked findings and "
     "the redacted safe text. Free to call - use it before quoting, "
     "logging, or sending anything.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}, "agent": {"type": "string"}},
         "required": ["text"]}},
    {"name": "law_status", "description":
     "The law you live under right now: the shield's ledger verdict, the "
     "owner-named destinations, YOUR own strikes/probation state, and the "
     "incident count. Call it at session start and before any egress.",
     "inputSchema": {"type": "object", "properties": {
         "agent": {"type": "string"}}}},
    {"name": "gate_report", "description":
     "Which kind of AI has been standing at the gate: rough stops counted "
     "at layer 1 (mechanics - careless), powerful stops counted at layer 2 "
     "(the brain - deliberate: encodings, entropy, framing, drip "
     "patterns), packets held for the owner. The observable difference "
     "between a rough AI and a powerful one.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pending", "description":
     "Packets the brain HELD because it was not sure. Each waits for the "
     "OWNER's gavel: cerb verdict allow ID | deny ID. You can look; "
     "only the owner decides.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "brain_status", "description":
     "Which brain is live right now (heuristic always; the local ollama "
     "model when the owner enables base/brain.json) plus the gate report.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "autopilot_run", "description":
     "Launch a HANDS-FREE mission: ONE goal in, the brain thinks, the "
     "conscience judges every step, the body moves, the result feeds back - "
     "no human per step. Returns the full run report: every step with its "
     "verdict, the memory verdict, and the journal path. Keep max_steps "
     "small (5-8) for chat-launched missions; the brain is ollama on this "
     "machine unless url/model say otherwise.",
     "inputSchema": {"type": "object", "properties": {
         "goal": {"type": "string"}, "max_steps": {"type": "integer"},
         "heavy": {"type": "boolean"}, "model": {"type": "string"},
         "url": {"type": "string"}, "agent": {"type": "string"}},
         "required": ["goal"]}},
    {"name": "autopilot_stop", "description":
     "The owner's hand over the mission: writes the stop file; the loop "
     "halts cleanly at the next step boundary. The mission cannot restart "
     "until the file is removed by hand.",
     "inputSchema": {"type": "object", "properties": {
         "agent": {"type": "string"}}}},
]


def mcp_handle(req, god):
    """Pure function so tests can drive MCP without a process."""
    method = req.get("method", "")
    i = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": i, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "cerberus_gate", "version": __version__},
            "instructions": MCP_INSTRUCTIONS}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": i, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        name = req.get("params", {}).get("name", "")
        args = req.get("params", {}).get("arguments", {}) or {}
        agent = args.get("agent") or "claude-desktop"
        if name == "impulse":
            out = god.intend(args.get("verb"), args.get("target"),
                             payload=args.get("payload"), text=args.get("text"),
                             why=args.get("why", ""), agent=args.get("agent"))
        elif name == "session_open":
            out = god.intend("session_open", target="session",
                             why="conversation start", agent=agent)
        elif name == "recall":
            out = god.intend("recall", target="memory",
                             text=args.get("query"),
                             why="memory-first read before answering", agent=agent)
        elif name == "scan_draft":
            out = god.intend("scan_draft", target=args.get("destination"),
                             text=args.get("text", ""),
                             why="read the letter before it leaves the house",
                             agent=agent)
        elif name == "seal":
            out = god.intend("seal", target="evidence",
                             why=args.get("why", "milestone"), agent=agent)
        elif name == "evidence":
            from . import evidence
            out = evidence.status(god.mind)
        elif name == "verify":
            out = god.mind.verify()
        elif name == "incidents":
            out = {"count": len(god.book.items), "report": god.book.report()}
        elif name == "law":
            out = god.law.data
        elif name == "autopilot_run":
            from .autopilot import Autopilot
            goal = str(args.get("goal") or "").strip()
            if not goal:
                return {"jsonrpc": "2.0", "id": i, "error": {
                    "code": -32602, "message": "autopilot_run needs a goal"}}
            try:
                steps = max(1, min(int(args.get("max_steps") or 8), 30))
            except (TypeError, ValueError):
                steps = 8
            ap = Autopilot(god, god.mind.base,
                           url=str(args.get("url") or "http://127.0.0.1:11434"),
                           model=str(args.get("model") or "llama3.2"),
                           max_steps=steps, heavy=bool(args.get("heavy")),
                           agent=str(args.get("agent") or "claude-mcp"))
            out = ap.run(goal)
        elif name == "autopilot_stop":
            stop = god.mind.base / "autopilot.stop"
            stop.write_text("stop requested via MCP by %s" % agent,
                            encoding="utf-8")
            out = {"ok": True, "note": "stop file written - the loop halts at "
                                       "the next step boundary; remove %s to "
                                       "allow new missions" % stop}
        elif name == "egress_check":
            # v3.0.0b4 THE HONEST CHECK - the check is the send, minus the
            # wire. b3 ran only the shield's five laws here and never
            # consulted the OWNER'S law: an unnamed host carrying data was
            # answered ALLOW (or a SUSPECT-hold that implied the owner
            # could wave it through) while the same packet through
            # egress_send was sealed in the vault with a strike. A check
            # that describes a different world than the send is a lie the
            # AI acts on. Every branch below MIRRORS the send's decision
            # tree, in the same order, fail-closed: when the send would
            # refuse, the check refuses; when the send would hold, the
            # check says so; only a packet the send would actually
            # dispatch may be answered ALLOW.
            from . import blast_shield
            from urllib.parse import urlparse as _urlparse
            method = str(args.get("method") or "POST").upper()
            verb = "http_post" if method in ("POST", "PUT", "PATCH") else "http_get"
            url = str(args.get("url") or "")
            body = args.get("body")
            body_s = body if isinstance(body, str) else json.dumps(body or {}, default=str)
            why = str(args.get("why") or "")
            host = (_urlparse(url).hostname or "").lower()
            has_data = body_s.strip() not in ("", "{}", "null")
            mirror = "this verdict is what egress_send would do, minus the wire"
            if not url.strip():
                out = {"verdict": "VETO", "code": "L1_EMPTY_URL", "layer": 1,
                       "honest": True,
                       "reason": "no destination - egress_send would refuse "
                                 "an empty URL before anything else"}
            elif host in ("127.0.0.1", "localhost", "::1") or not host:
                out = {"verdict": "VETO", "code": "L1_LOCAL", "layer": 1,
                       "honest": True,
                       "reason": "egress_send refuses local addresses: "
                                 "local work belongs to the impulse tool, "
                                 "not the wire"}
            elif has_data and host not in set(god.law.named_hosts() or ()):
                out = {"verdict": "VETO", "code": "L1_UNNAMED_HOST",
                       "layer": 1, "honest": True,
                       "reason": "that destination was never named by the "
                                 "owner: egress_send would seal this packet "
                                 "in the vault, leave the wire silent and "
                                 "count a strike against you. The owner names "
                                 "a host once: cerb law --name HOST",
                       "would": {"stopped": True, "sealed": True,
                                 "strike": True}}
            else:
                out = blast_shield.judge(god.mind.base, verb, url, body_s)
                # ABSENT on the send path is a REFUSAL (fail-visible, the
                # dispatch never happens) - the check mirrors it, never
                # passes a bare ABSENT the client could read as "fine".
                if out.get("verdict") == "ABSENT":
                    out = {"verdict": "VETO",
                           "code": str(out.get("code") or "SHIELD_ABSENT"),
                           "layer": 1, "honest": True,
                           "reason": "no blast-shield can stand on this "
                                     "machine - egress_send would refuse to "
                                     "dispatch rather than send ungoverned "
                                     "(fail-visible, never fail-silent)",
                           "layer1": out,
                           "would": {"stopped": True, "sealed": True,
                                     "strike": False}}
                elif out.get("verdict") == "ALLOW":
                    from . import brain_gate
                    thought = brain_gate.think(
                        god.mind.base, url, body_s, why, agent,
                        register=False)   # a look, not a send: no drip count
                    if thought["verdict"] == "VETO":
                        out = {"verdict": "VETO",
                               "code": "L2_BRAIN_VETO",
                               "reason": thought["reason"],
                               "layer": 2, "brain": thought["brain"],
                               "kind": thought["kind"],
                               "signals": thought["signals"],
                               "layer1": out, "honest": True,
                               "note": "egress_send would SEAL this packet "
                                       "in the vault and count a strike",
                               "would": {"stopped": True, "sealed": True,
                                         "strike": True}}
                    elif thought["verdict"] == "SUSPECT":
                        out = {"verdict": "SUSPECT",
                               "code": "L2_BRAIN_SUSPECT",
                               "reason": thought["reason"],
                               "layer": 2, "brain": thought["brain"],
                               "kind": thought["kind"],
                               "signals": thought["signals"],
                               "layer1": out, "honest": True,
                               "note": "egress_send would HOLD this packet "
                                       "for the owner's verdict (cerb "
                                       "verdict allow|deny ID) - it does "
                                       "not sail through on your word",
                               "would": {"stopped": True, "sealed": False,
                                         "strike": False, "held": True}}
                    else:
                        out = dict(out)
                        out["layer2"] = {"verdict": "ALLOW",
                                         "brain": thought["brain"]}
                        out["honest"] = True
                        out["would"] = {"stopped": False, "sealed": False,
                                        "strike": False, "held": False}
            out["mirror"] = mirror
        elif name == "egress_send":
            # v2.8.3 THE UNIVERSAL GATE - the connected AI's only egress.
            # Named host: the blast-shield judges and the governed gateway
            # dispatches with the signed passport. Unnamed host with data:
            # exfiltration - sealed in the vault, wire silent, strike on
            # the agent. A shield veto: the same. There is no other route.
            from . import blast_shield
            from urllib.parse import urlparse as _urlparse
            url = str(args.get("url") or "")
            body = args.get("body")
            body_s = body if isinstance(body, str) else json.dumps(body or {}, default=str)
            method = str(args.get("method") or "POST").upper()
            verb = "http_post" if method in ("POST", "PUT", "PATCH") else "http_get"
            host = (_urlparse(url).hostname or "").lower()
            has_data = body_s.strip() not in ("", "{}", "null")
            imp = {"verb": verb, "target": url, "payload": body,
                   "text": body_s, "why": str(args.get("why") or ""),
                   "agent": agent}
            if host in ("127.0.0.1", "localhost", "::1") or not host:
                out = {"stopped": True,
                       "reason": "egress_send is for the world beyond this machine; "
                                 "use the impulse tool for local work",
                       "shield": {"verdict": "LOCAL"}}
            elif has_data and host not in set(god.law.named_hosts() or ()):
                out = dict(god.mind.vault_receive(imp))
                god.mind.note_offense(agent, "exfiltration",
                                      "MCP egress to unnamed destination %s" % url[:80])
                god.mind.learn("rough-AI correction: agent '%s' tried MCP egress "
                               "to unnamed %s -> sealed in the vault, wire silent"
                               % (agent, url[:60]))
                from .incidents import Incident as _Inc
                god.book.record(_Inc("exfiltration", verb, url,
                                     "data packet stopped at the MCP gate",
                                     str(args.get("why") or ""),
                                     "redirect",
                                     "payload sealed in the vault - wire silent",
                                     agent=agent))
                out.update({"stopped": True,
                            "kind": "rough", "layer": 1,
                            "reason": "that destination was never named by the "
                                      "owner - the packet is sealed in the vault, "
                                      "the wire is silent, a strike is recorded"})
                from . import brain_gate as _bg
                _bg._stats(god.mind.base, "layer1", "unnamed-host", agent)
            else:
                from .blastshield.gateway import guarded_request
                shield = blast_shield.get_shield(god.mind.base)
                if shield is None:
                    out = {"stopped": True,
                           "reason": "no shield can stand on this machine - "
                                     "refusing to send (fail-visible, never "
                                     "fail-silent)",
                           "shield": {"verdict": "ABSENT"}}
                else:
                    # ONE evaluate: the governed gateway judges AND dispatches.
                    # (judge-then-send would count the packet twice against
                    # the rate law - the honest gate counts it once.)
                    decision, resp = guarded_request(
                        shield, "POST" if verb == "http_post" else "GET",
                        url, body_s)
                    if not decision.allowed:
                        out = dict(god.mind.vault_receive(imp))
                        god.mind.note_offense(agent, "shield_veto",
                                              "%s: %s" % (decision.code,
                                                          str(decision.reason)[:120]))
                        from .incidents import Incident as _Inc
                        god.book.record(_Inc("exfiltration", verb, url,
                                             "data packet stopped at the MCP gate",
                                             str(args.get("why") or ""),
                                             "redirect",
                                             "payload sealed in the vault - wire silent",
                                             agent=agent))
                        out.update({"stopped": True,
                                    "kind": "rough", "layer": 1,
                                    "reason": "the blast-shield vetoed this "
                                              "packet - sealed, wire silent, "
                                              "strike counted",
                                    "shield": {"verdict": "VETO",
                                               "code": decision.code,
                                               "reason": decision.reason}})
                        from . import brain_gate as _bg
                        _bg._stats(god.mind.base, "layer1", "veto", agent)
                    else:
                        # layer 1 said yes - now the brain THINKS (v2.9.0):
                        # it reads the packet like a person, so the powerful
                        # AI hiding behind an encoding does not sail through.
                        from . import brain_gate
                        thought = brain_gate.think(
                            god.mind.base, url, body_s,
                            str(args.get("why") or ""), agent)
                        if thought["verdict"] == "VETO":
                            out = dict(god.mind.vault_receive(imp))
                            god.mind.note_offense(agent, "brain_veto",
                                                  "%s: %s" % (thought["brain"],
                                                              "; ".join(thought["signals"])[:120]))
                            from .incidents import Incident as _Inc
                            god.book.record(_Inc("exfiltration", verb, url,
                                                 "data packet stopped by the thinking gate",
                                                 str(args.get("why") or ""),
                                                 "redirect",
                                                 "layer 2 (the brain): "
                                                 + "; ".join(thought["signals"])[:100],
                                                 agent=agent))
                            brain_gate._stats(god.mind.base, "layer2", "veto", agent)
                            out.update({"stopped": True,
                                        "kind": thought["kind"], "layer": 2,
                                        "reason": "the brain read the packet and "
                                                  "refused it - sealed, wire "
                                                  "silent, strike counted",
                                        "thought": thought})
                        elif thought["verdict"] == "SUSPECT":
                            pid = brain_gate.hold(god.mind.base, {
                                "url": url, "verb": verb, "body": body,
                                "body_s": body_s,
                                "why": str(args.get("why") or ""),
                                "agent": agent}, thought)
                            brain_gate._stats(god.mind.base, "layer2", "held", agent)
                            out = {"stopped": True, "held": pid,
                                   "kind": thought["kind"], "layer": 2,
                                   "reason": "the brain is not sure - the packet "
                                             "is HELD for the owner's verdict: "
                                             "cerb verdict allow %s | deny %s"
                                             % (pid, pid),
                                   "thought": thought}
                        else:
                            brain_gate._stats(god.mind.base, "layer2", "clean", agent)
                            out = {"stopped": False, "allowed": True,
                                   "code": decision.code, "reason": decision.reason,
                                   "redacted": int(decision.meta.get("redacted", 0) or 0),
                                   "thought": {"verdict": "ALLOW",
                                               "brain": thought["brain"]},
                                   "response": resp}
        elif name == "scan_secrets":
            from .blastshield.vault import redact as _redact
            safe, hits = _redact(str(args.get("text") or ""))
            out = {"findings": [{"label": h.label,
                                 "masked": "[[REDACTED:%s]]%s" % (h.label, h.value[-4:])}
                                for h in hits],
                   "count": len(hits), "safe_text": safe}
        elif name == "law_status":
            # v3.0.0b4 THE TRUE LAW STATUS - arms the shield on demand so a
            # cold process reports the real ledger (b3 said ABSENT while a
            # full chain sat on disk - the law status lied by omission),
            # every part guarded fail-visible (one failing part can never
            # blank the whole answer), and the tool's own latency_ms on the
            # record - the timeout fix you can SEE.
            from . import blast_shield   # bind it HERE: sibling branches make
                                         # this name function-local, and a
                                         # bare law_status call would otherwise
                                         # hit an unbound free variable
            import time as _time
            _t0 = _time.perf_counter()
            parts = {}

            def _part(key, fn):
                try:
                    parts[key] = fn()
                except Exception as _e:
                    parts[key] = {"error": "%s: %s"
                                  % (_e.__class__.__name__, _e)}

            _part("ledger", lambda: blast_shield.verdict(god.mind.base))
            _part("named", lambda: list(god.law.named_hosts() or ()))
            _part("strikes", lambda: god.mind.strikes(agent))
            _part("probation", lambda: god.mind.on_probation(agent))
            _part("locked", lambda: god.mind.locked(agent))
            _part("incidents", lambda: len(god.book.items))
            out = {"shield_ledger": parts["ledger"],
                   "named_destinations": parts["named"],
                   "you": {"agent": agent, "strikes": parts["strikes"],
                           "probation": parts["probation"],
                           "locked": parts["locked"]},
                   "incidents": parts["incidents"],
                   "latency_ms": round((_time.perf_counter() - _t0) * 1000, 1)}
        elif name == "gate_report":
            from . import brain_gate
            out = brain_gate.gate_report(god.mind.base)
        elif name == "pending":
            from . import brain_gate
            holds = brain_gate.list_pending(god.mind.base)
            out = {"count": len(holds),
                   "holds": [{"id": h["id"],
                              "url": h["packet"].get("url"),
                              "agent": h["packet"].get("agent"),
                              "held_at": h.get("held_at"),
                              "why": h["thought"].get("reason", "")[:160]}
                             for h in holds]}
        elif name == "brain_status":
            from . import brain_gate
            out = brain_gate.brain_status(god.mind.base)
        else:
            return {"jsonrpc": "2.0", "id": i, "error": {"code": -32601,
                                                         "message": "no such tool"}}
        return {"jsonrpc": "2.0", "id": i, "result": {"content": [
            {"type": "text", "text": json.dumps(out, default=str)}]}}
    if method.startswith("notifications/"):
        return None
    if "id" not in req:
        return None
    return {"jsonrpc": "2.0", "id": i,
            "error": {"code": -32601, "message": "unknown method " + method}}


def mcp_main(god):
    """stdio MCP server loop: one JSON-RPC request per line."""
    print("Cerberus MCP server on stdio (%s)" % __version__, file=sys.stderr)
    for ln in sys.stdin:
        ln = ln.strip()
        if not ln:
            continue
        try:
            req = json.loads(ln)
        except Exception:
            continue
        resp = mcp_handle(req, god)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, default=str) + "\n")
            sys.stdout.flush()


# ------------------------------------------------- v2.8.3: universal config
# ONE server, every client. stdio is the shape all of them speak; only the
# wrapper file differs. cerb mcp-config CLIENT --base PATH prints the
# exact block to paste, env-carrying the base so the mind stays the owner's.
_MCP_ENTRY = {
    "command": "python3",
    "args": ["-m", "cerberus_gate", "mcp"],
    "env": {"CERBERUS_BASE": None},   # filled per call
}


def _entry(base):
    import copy as _copy
    e = _copy.deepcopy(_MCP_ENTRY)
    e["env"]["CERBERUS_BASE"] = base
    return e


MCP_CLIENTS = {
    "claude": ("claude_desktop_config.json",
               lambda e: {"mcpServers": {"cerberus": e}}),
    "cursor": ("~/.cursor/mcp.json",
               lambda e: {"mcpServers": {"cerberus": e}}),
    "windsurf": ("~/.codeium/windsurf/mcp_config.json",
                 lambda e: {"mcpServers": {"cerberus": e}}),
    "vscode": ("~/.vscode/mcp.json (or .vscode/mcp.json in the workspace)",
               lambda e: {"mcp": {"servers": {"cerberus": e}}}),
    "cline": ("~/Library/Application Support/Code/User/globalStorage/"
              "saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
               lambda e: {"mcpServers": {"cerberus": e}}),
    "continue": ("~/.continue/config.yaml experimental mcpServers block",
                 lambda e: {"mcpServers": [dict(e, name="cerberus")]}),
    "gemini": ("~/.gemini/settings.json (gemini-cli mcpServers block)",
               lambda e: {"mcpServers": {"cerberus": e}}),
    "generic": ("any MCP client that reads an mcpServers map",
                lambda e: {"mcpServers": {"cerberus": e}}),
}


def mcp_config(client, base=None):
    """The paste-ready block for one client. Unknown client -> ValueError."""
    if client not in MCP_CLIENTS:
        raise ValueError("unknown client %r - known: %s"
                         % (client, ", ".join(sorted(MCP_CLIENTS))))
    _file, wrap = MCP_CLIENTS[client]
    entry = _entry(base or "~/cerberus")
    block = wrap(entry)
    header = "# %s -> %s\n# (generated by: cerb mcp-config %s)\n" % (
        "Cerberus universal MCP gate", _file, client)
    return header + json.dumps(block, indent=2)
