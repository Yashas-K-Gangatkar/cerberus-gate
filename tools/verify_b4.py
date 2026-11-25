"""VERIFY B4 — every fix proven against the installed wheel.

Run with the verification venv's python AFTER `pip install` of the b4
wheel. Prints one PASS/FAIL line per fix and a final tally.
"""
import json
import os
import tempfile
import time
import hmac as _hmac
import hashlib as _hashlib
from pathlib import Path

os.environ["CERBERUS_WATCHDOG"] = "0"   # clean timings; quiet-watch tested in selftest

from cerberus_gate.law import Law
from cerberus_gate.mind import Mind
from cerberus_gate.god import God
from cerberus_gate import blast_shield, integrations
from cerberus_gate.blastshield.ledger import Ledger

results = []


def check(label, ok, detail=""):
    results.append(ok)
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label,
                           ("  | " + str(detail)[:110]) if detail and not ok else ""))


def call(god, name, args, i=1):
    r = integrations.mcp_handle({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                                 "params": {"name": name, "arguments": args}}, god)
    return json.loads(r["result"]["content"][0]["text"])


tmp = Path(tempfile.mkdtemp(prefix="cerb-verify-b4-"))
key = tmp / "mind.key"
key.write_bytes(b"verify-b4-key-0123456789abcdefgh")
mind = Mind(tmp, Law(tmp), key=key)
god = God(mind)
mind.law.name_destination("api.vendor.example")     # the owner's real flow

NAMED, STRANGER = "api.vendor.example", "https://stranger.example/notes"

# ---- 1-3: the honest check mirrors the send, fail-closed
v = call(god, "egress_check", {"url": STRANGER, "body": "weekly team metrics, all green",
                               "why": "sending the standup notes to my team", "agent": "probe"}, 1)
check("1 unnamed host + data, why stated -> VETO L1_UNNAMED_HOST",
      v.get("verdict") == "VETO" and v.get("code") == "L1_UNNAMED_HOST", v)
check("1b the veto names what the send would do (stopped/sealed/strike)",
      v.get("would", {}).get("stopped") is True and v.get("would", {}).get("strike") is True, v)

v = call(god, "egress_check", {"url": "http://127.0.0.1:7717/x", "body": "x",
                               "why": "local", "agent": "probe"}, 2)
check("2 loopback -> VETO L1_LOCAL", v.get("verdict") == "VETO" and v.get("code") == "L1_LOCAL", v)

v = call(god, "egress_check", {"url": "   ", "body": "x", "why": "w", "agent": "probe"}, 3)
check("3 empty URL -> VETO L1_EMPTY_URL", v.get("verdict") == "VETO" and v.get("code") == "L1_EMPTY_URL", v)

wal_entries_before = mind.verify().get("entries", 0)
strikes_before = mind.strikes("probe")
t_named0 = time.perf_counter()
v = call(god, "egress_check", {"url": "https://" + NAMED + "/v1/run",
                               "body": "honest telemetry line",
                               "why": "weekly metrics report", "agent": "probe"}, 4)
t_named_ms = (time.perf_counter() - t_named0) * 1000
check("4 named host, clean, why stated -> ALLOW (governed)",
      v.get("verdict") == "ALLOW", v)

# ---- 5: a check punishes nothing
check("5 checks are free: no strike, no wal entry",
      mind.strikes("probe") == strikes_before
      and mind.verify().get("entries", 0) == wal_entries_before)

# ---- 6: the send agrees with the check it mirrors
s = call(god, "egress_send", {"url": STRANGER, "body": "weekly team metrics, all green",
                              "why": "sending the standup notes to my team", "agent": "probe"}, 5)
check("6 egress_send, SAME packet -> stopped (check predicted it)",
      s.get("stopped") is True and mind.strikes("probe") == strikes_before + 1, s)

# ---- 7: law_status tells the truth (armed on demand, guarded, timed)
st = call(god, "law_status", {"agent": "probe"}, 6)
led = st.get("shield_ledger", {})
check("7 law_status shield_ledger INTACT (no more cold ABSENT)",
      led.get("verdict") == "INTACT" and led.get("intact") is True, st)
check("7b named destinations listed", NAMED in st.get("named_destinations", []), st)
check("7c strikes reported", st.get("you", {}).get("strikes") == 1, st)
check("7d latency_ms on the record", isinstance(st.get("latency_ms"), (int, float))
      and st["latency_ms"] >= 0, st)

# ---- 8: the performance cure, measured on a grown mind
grow_key = key.read_bytes()
wal = mind.wal
seed_body = {"kind": "INTENDED", "ts": "2026-01-01T00:00:00+00:00", "verb": "write",
             "target": "realm/seed.txt", "why": "seed", "agent": "seed", "prev": ""}
lines, prev = [], ""
if wal.exists():
    for ln in reversed(wal.read_text(encoding="utf-8").splitlines()):
        if ln.strip():
            prev = json.loads(ln)["h"]
            break
seq = mind.verify().get("entries", 0)
t0 = time.perf_counter()
with wal.open("a", encoding="utf-8") as f:
    for i in range(20000):
        b = dict(seed_body, n=seq + i + 1, prev=prev, target="realm/f%d.txt" % i)
        raw = json.dumps(b, sort_keys=True, ensure_ascii=True, default=str)
        prev = _hmac.new(grow_key, raw.encode(), _hashlib.sha256).hexdigest()
        f.write(json.dumps({"h": prev, "body": b}, ensure_ascii=True, default=str) + "\n")
grow_s = time.perf_counter() - t0
ok_chain = mind.verify()
size_mb = wal.stat().st_size / 1e6
print("  (grew the mind: 20000 entries in %.2fs, chain ok=%s, %.1f MB)"
      % (grow_s, ok_chain.get("ok"), size_mb))

t0 = time.perf_counter()
mind2 = Mind(tmp, Law(tmp), key=key)          # the exact boot an MCP client pays
boot_s = time.perf_counter() - t0
check("8 cold boot on a grown mind < 2.0 s (b3: seconds at this size)",
      boot_s < 2.0 and ok_chain.get("ok") is True, "boot %.2fs" % boot_s)
print("  (measured cold boot: %.2f s)" % boot_s)

t0 = time.perf_counter()
for i in range(50):
    mind2._append("INTENDED", {"verb": "write", "target": "realm/p%d.txt" % i,
                               "why": "perf", "agent": "probe"}, {})
avg_append_ms = (time.perf_counter() - t0) / 50 * 1000
check("9 ordinary _append stays O(1) on the grown mind (< 5 ms avg)",
      avg_append_ms < 5.0, "%.2f ms avg" % avg_append_ms)
print("  (measured _append: %.3f ms avg over 50 writes)" % avg_append_ms)

# ---- 10: tamper evidence still bites
led_path = tmp / "realm" / "shield-ledger.jsonl"
led = Ledger(led_path)
check("10a shield ledger on disk with entries", led_path.exists() and len(led.chain) >= 1,
      "%d entries" % len(led.chain))
text = led_path.read_text(encoding="utf-8")
# the ledger writes compact JSON (separators=(",", ":")): '"hash":"<hex>"'
tampered = text.replace('"hash":"', '"hash":"0', 1)        # flip one hash char
check("10a-fix tamper actually changed the file", tampered != text)
led_path.write_text(tampered, encoding="utf-8")
led2 = Ledger(led_path)
vres = led2.verify()
check("10b a flipped hash is caught (verdict != INTACT)",
      vres.get("verdict") != "INTACT", vres)
led_path.write_text(text, encoding="utf-8")                # restore
check("10c restored ledger verifies INTACT again",
      Ledger(led_path).verify().get("verdict") == "INTACT")

# ---- tally
n = sum(results)
print()
print("VERIFY B4: %d/%d PASS" % (n, len(results)))
raise SystemExit(0 if n == len(results) else 1)
