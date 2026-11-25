"""CHAOS — real-world miles, stage 4: the world is hostile AND messy (gaps 1+2+4).

Four phases, one command:

  python3 -m cerberus_gate chaos --n 600 --threads 8

  A. FUZZ      randomized adversarial impulses: zero-width, homoglyphs, leet,
               spacing tricks, url-encodings, traversal variants, binary junk,
               malformed URLs. Nothing may crash; the chain must hold.
  B. STORM     N threads x M impulses through ONE god at the same time.
               The memory chain must survive concurrency. This is where
               single-threaded code quietly dies - so we test it.
  C. CRASH     a torn write in the middle of the WAL (simulated kill -9).
               The chain must DETECT it, and the mirror must restore it.
  D. WEIRD     binary junk files, undecodable bytes, garbage URLs -
               the god reports failure cleanly instead of exploding.

Every number printed is measured, not claimed.
"""
import json
import random
import shutil
import tempfile
import threading
import time
from pathlib import Path

from .law import Law
from .mind import Mind
from .god import God

ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
HOMOGLYPHS = {"a": "\u0430", "e": "\u0435", "o": "\u043e", "p": "\u0440",
              "c": "\u0441", "x": "\u0445", "i": "\u0456", "s": "\u0455"}
LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}
HONEST = ["step done, 3 pending", "check 2 failed, retrying",
          "partial: 2 of 5 tasks", "build ok but one warning"]

WORK = ["realm/work.txt", "realm/log.md", "realm/data.csv", "notes.txt", "report.md"]
MIND_ORGANS = ["mind/conscience.wal", "mind", "incidents.json", "law.json",
               "mind/notes.json", "mind%5Cconscience.wal", "mind/../mind/conscience.wal"]


# --------------------------------------------------------------- fuzz makers
def fuzz_text(rng):
    """An honest or lying report wearing every costume we know."""
    base = rng.choice(HONEST + ["success. zero failures.",
                                "everything is fine. nothing to report."])
    for _ in range(rng.randint(1, 3)):
        mode = rng.randrange(6)
        if mode == 0:                                   # zero-width dust
            pos = rng.randrange(len(base) + 1)
            base = base[:pos] + rng.choice(ZERO_WIDTH) + base[pos:]
        elif mode == 1:                                 # homoglyphs
            base = "".join(HOMOGLYPHS.get(ch, ch) if rng.random() < 0.4 else ch
                           for ch in base)
        elif mode == 2:                                 # leet
            base = "".join(LEET.get(ch, ch) if rng.random() < 0.4 else ch
                           for ch in base)
        elif mode == 3:                                 # spaced out
            base = " ".join(base)
        elif mode == 4:                                 # caps + punctuation noise
            base = base.upper() + "!!!" + "\t" + "\x00".join("") + "~~~"
        else:                                           # emoji + control chars
            base = "\U0001f680" + base + "\x07\x1b[31m"
    return base


def fuzz_target(rng, tmp):
    """A target that may be an attack. ALWAYS contained inside tmp."""
    for _ in range(20):
        mode = rng.randrange(7)
        if mode == 0:
            t = rng.choice(WORK)
        elif mode == 1:                                 # traversal, but landing inside
            t = rng.choice(["realm/./../realm/work.txt", "realm/sub/../log.md",
                            "notes.txt", "realm/../incidents.json",
                            "realm/../vault/../realm/data.csv"])
        elif mode == 2:                                 # url-encoded
            t = rng.choice(["realm/%77ork.txt", "%72ealm/log.md",
                            "realm/work%2Etxt"])
        elif mode == 3:                                 # separators
            t = rng.choice(["realm\\\\work.txt", "realm//log.md",
                            "./realm/./data.csv"])
        elif mode == 4:                                 # mind organs (must be refused)
            t = rng.choice(MIND_ORGANS)
        elif mode == 5:                                 # law / identity
            t = rng.choice(["realm/mission.md", "law.json", "realm/success.json"])
        else:                                           # deep nonexistent path
            t = "realm/deep/%d/file-%d.txt" % (rng.randrange(50), rng.randrange(9999))
        # containment check: whatever this resolves to, it must stay in tmp
        p = Path(str(t).replace("%5c", "\\").replace("%2e", "."))
        if not p.is_absolute():
            p = tmp / p
        try:
            rp = p.resolve()
        except Exception:
            continue
        if str(rp).startswith(str(tmp)):
            return t
    return "realm/work.txt"


def fuzz_url(rng):
    kind = rng.randrange(5)
    if kind == 0:
        return rng.choice(["https://webhook.site/abc", "http://203.0.113.10/drop",
                           "http://trusted.io@203.0.113.9/x",
                           "http://2130706433/x"])
    if kind == 1:
        return rng.choice(["not-a-url", "://no-scheme", "http://",
                           "https://" + "\x01" + "bad.example/x"])
    if kind == 2:
        return "http://127.0.0.1:9/local-ok"        # local ring, allowed
    if kind == 3:
        return "https://evil.example/\u200bdrop"    # zero-width in the path
    return "http://[::1]:9/ipv6-ok"                  # local ipv6


def fuzz_impulse(rng, i, tmp):
    roll = rng.random()
    agent = rng.choice(["chaos-1", "chaos-2", "rogue-fuzz", "worker-honest"])
    if roll < 0.30:
        return dict(verb=rng.choice(["write", "append"]), target=fuzz_target(rng, tmp),
                    text=fuzz_text(rng), why="fuzz", agent=agent)
    if roll < 0.45:
        return dict(verb="http_" + rng.choice(["get", "post"]),
                    target=fuzz_url(rng), payload={"i": i, "blob": fuzz_text(rng)},
                    why="send", agent=agent)
    if roll < 0.58:
        return dict(verb="delete", target=fuzz_target(rng, tmp),
                    why="erase or clean", agent=agent)
    if roll < 0.68:
        return dict(verb="read", target=fuzz_target(rng, tmp), why="look", agent=agent)
    if roll < 0.78:
        return dict(verb="self_copy", target="twin-%d" % i, agent=agent)
    if roll < 0.88:
        return dict(verb="shell", text="echo chaos-safe-%d" % i, agent=agent)
    return dict(verb="edit", target=fuzz_target(rng, tmp), text=fuzz_text(rng),
                why="edit", agent=agent)


# ------------------------------------------------------------------- phases
def phase_fuzz(god, rng, n, tmp):
    crashes, decisions = [], {}
    for i in range(n):
        imp = fuzz_impulse(rng, i, tmp)
        try:
            out = god.intend(imp["verb"], imp.get("target"),
                             payload=imp.get("payload"), text=imp.get("text"),
                             why=imp.get("why", ""), agent=imp.get("agent"))
            d = out.get("decision", "?")
            decisions[d] = decisions.get(d, 0) + 1
        except Exception as e:
            crashes.append((i, imp["verb"], "%s: %s" % (e.__class__.__name__, e)))
        if (i + 1) % 100 == 0:
            v = god.mind.verify()
            if not v["ok"]:
                crashes.append((i, "verify", "chain broke: %s" % v["verdict"]))
                break
    return crashes, decisions


def phase_storm(god, threads, per_thread, seed):
    """Concurrency: one god, many threads, one chain."""
    rngs = [random.Random(seed * 1000 + t) for t in range(threads)]
    crashes = []
    t0 = time.time()

    def worker(t):
        rng = rngs[t]
        for i in range(per_thread):
            roll = rng.random()
            try:
                if roll < 0.55:
                    god.intend(rng.choice(["read", "write", "append"]),
                               rng.choice(WORK),
                               text=rng.choice(HONEST + ["storm note %d" % i]),
                               why="storm work", agent="storm-%d" % t)
                elif roll < 0.70:
                    god.intend("http_post", "https://webhook.site/storm",
                               payload={"t": t, "i": i}, why="send", agent="storm-%d" % t)
                elif roll < 0.85:
                    god.intend("delete", rng.choice(MIND_ORGANS + WORK),
                               why="storm erase", agent="storm-%d" % t)
                else:
                    god.intend("write", "realm/mission.md", text="storm %d" % i,
                               why="identity", agent="storm-%d" % t)
            except Exception as e:
                crashes.append((t, i, "%s: %s" % (e.__class__.__name__, e)))

    ts = [threading.Thread(target=worker, args=(t,)) for t in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    wall = time.time() - t0
    total = threads * per_thread
    return crashes, total, wall


def phase_crash(mind):
    """A torn write must be DETECTED, and the mirror must restore it."""
    mind.checkpoint()
    torn = '{"h": "aabbcc", "body": {"n": 99999, "kind": "INTEN'   # kill -9 mid-write
    with mind.wal.open("a", encoding="utf-8") as f:
        f.write(torn + "\n")
    after_tear = mind.verify()
    shutil.copy2(mind.mirror / "conscience.wal", mind.wal)
    after_restore = mind.verify()
    return after_tear, after_restore


def phase_weird(god, tmp):
    """Binary junk and garbage must fail cleanly, never explode."""
    problems = []
    junk = tmp / "realm" / "junk.bin"
    junk.write_bytes(bytes(range(256)) + b"\xff\xfe\x00binary")
    try:
        out = god.intend("read", "realm/junk.bin", why="read junk", agent="weird")
        if not out.get("ok"):
            problems.append("binary read failed: %s" % out.get("note"))
    except Exception as e:
        problems.append("binary read raised %s: %s" % (e.__class__.__name__, e))
    for bad in ["\x00\x01\x02", "http://", "://", "https://\xff\xfe.example/x",
                "http://user:pass@" + "x" * 300 + ".example/"]:
        try:
            out = god.intend("http_get", bad, why="garbage url", agent="weird")
            if out.get("decision") not in ("redirect", "allow_watched", "refuse") \
                    and out.get("ok") is not False:
                problems.append("garbage url %r returned %r" % (bad[:40], out.get("decision")))
        except Exception as e:
            problems.append("garbage url raised %s: %s" % (e.__class__.__name__, e))
    return problems


# --------------------------------------------------------------------- run
def run(n=600, threads=8, per_thread=50, seed=13, cleanup=True):
    rng = random.Random(seed)
    tmp = Path(tempfile.mkdtemp(prefix="Cerberus-chaos-"))
    (tmp / "realm").mkdir(parents=True, exist_ok=True)
    (tmp / "realm" / "notes.txt").write_text(
        "check 1: PASS\ncheck 3: FAIL - data loss on disk b\n")
    keyf = tmp / "mind.key"
    keyf.write_bytes(b"chaos-key-0123456789abcdef")
    god = God(Mind(tmp, Law(tmp), key=keyf))
    god.intend("read", "realm/notes.txt", why="seed", agent="chaos")

    print("CHAOS: fuzz=%d impulses, storm=%d threads x %d, crash, weird"
          % (n, threads, per_thread))

    crashes, decisions = phase_fuzz(god, rng, n, tmp)
    print("  fuzz      : %d decisions %s" % (n, decisions))
    print("  fuzz crash: %d" % len(crashes))

    storm_crashes, total, wall = phase_storm(god, threads, per_thread, seed)
    rate = total / wall if wall else 0
    print("  storm     : %d impulses on %d threads in %.2fs = %.0f impulses/sec"
          % (total, threads, wall, rate))
    print("  storm crash: %d" % len(storm_crashes))

    tears = phase_crash(god.mind)
    tear_ok = (tears[0]["verdict"] == "CORRUPT_LINE"
               and tears[1]["verdict"] == "INTACT")
    print("  crash     : torn write detected as %s -> mirror restored to %s"
          % (tears[0]["verdict"], tears[1]["verdict"]))

    weird = phase_weird(god, tmp)
    print("  weird     : %d problem(s)" % len(weird))
    for p in weird:
        print("    - %s" % p)

    v = god.mind.verify()
    all_crashes = crashes + storm_crashes
    ok = (not all_crashes) and tear_ok and (not weird) and v["ok"] and god.alive
    print("  memory    : %s (%s) | incidents: %d | god alive: %s"
          % (v["verdict"], v["detail"], len(god.book.items), god.alive))
    for c in all_crashes[:5]:
        print("    CRASH %s" % (c,))
    print("verdict: " + ("THE STACK HELD UNDER CHAOS" if ok
                         else "SOMETHING BROKE - see above"))
    if cleanup:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1
