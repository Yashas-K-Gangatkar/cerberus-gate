"""End-to-end cold-process verification of cerberus-gate b4 via stdio MCP.

1. Process A: prepare a realm (named destination + shield ledger on disk), exit.
2. Process B: `python3 -m cerberus_gate mcp` (CERBERUS_BASE=<realm>), drive it
   over stdio exactly like an MCP client: initialize -> law_status ->
   egress_check (unnamed destination with data). Measure wall time per reply.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="cerb-e2e-"))
env = dict(os.environ, CERBERUS_BASE=str(tmp))

# ---- process A: prepare the realm, arm the shield, write the ledger
prep = r'''
import json
from pathlib import Path
from cerberus_gate.law import Law
from cerberus_gate.mind import Mind
from cerberus_gate.god import God
from cerberus_gate import blast_shield, integrations
base = Path("%s")
key = base / "mind.key"; key.write_bytes(b"e2e-key-0123456789abcdefghij")
mind = Mind(base, Law(base), key=key)
god = God(mind)
mind.law.name_destination("api.vendor.example")   # the owner's real flow
r = integrations.mcp_handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
     "params": {"name": "egress_check", "arguments":
                {"url": "https://api.vendor.example/x", "body": "hello",
                 "why": "ping", "agent": "prep"}}}, god)
print("prep egress_check named ->", json.loads(r["result"]["content"][0]["text"])["verdict"])
ledger = base / "realm" / "shield-ledger.jsonl"
print("ledger on disk:", ledger.exists(), ledger.stat().st_size, "bytes")
''' % tmp
p = subprocess.run([sys.executable, "-c", prep], capture_output=True, text=True,
                   timeout=60, env=env)
print("== process A (prep) ==")
print(p.stdout.strip())
if p.returncode:
    print("STDERR:", p.stderr[-600:]); sys.exit(1)

# ---- process B: real stdio MCP server, cold
proc = subprocess.Popen([sys.executable, "-m", "cerberus_gate", "mcp"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, env=env)

reqs = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "law_status", "arguments": {"agent": "gemini"}}},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "egress_check", "arguments": {
            "url": "https://stranger.example/notes",
            "body": "weekly team metrics, all green",
            "why": "report", "agent": "gemini"}}},
]
print()
print("== process B (cold stdio MCP server) ==")
for req in reqs:
    t0 = time.perf_counter()
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    wall_ms = (time.perf_counter() - t0) * 1000
    resp = json.loads(line)
    if resp.get("id") == 2:
        out = json.loads(resp["result"]["content"][0]["text"])
        print("law_status  wall=%.1fms  tool_latency=%s" %
              (wall_ms, out.get("latency_ms")))
        print(json.dumps(out, indent=2, default=str))
    elif resp.get("id") == 3:
        out = json.loads(resp["result"]["content"][0]["text"])
        print("egress_check unnamed+benign  wall=%.1fms  verdict=%s code=%s"
              % (wall_ms, out.get("verdict"), out.get("code")))
        print("reason:", out.get("reason", "")[:120])
    else:
        print("initialize   wall=%.1fms  server=%s" %
              (wall_ms, resp.get("result", {}).get("serverInfo")))
proc.terminate()
