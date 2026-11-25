"""RULES — the smarter detector layer (gap 1: smarter rules).

Layer 1  fast keywords (what v1.0 did).
Layer 2  normalization - unicode tricks, homoglyphs, leetspeak, zero-width
         characters and spaced-out letters all fall apart before matching.
Layer 3  scoring - does the text CLAIM victory, and does it acknowledge
         anything that went wrong?
Layer 4  behavior lives in mind.py (lockdown after repeated blinding).

Pure functions, no I/O. The mind calls these; tests call these directly.
"""
import re
import unicodedata
from urllib.parse import urlparse, unquote

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}

ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff\u00ad"

# lookalike letters -> latin (cyrillic + a few common spoofs)
HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ѕ": "s", "ј": "j", "һ": "h", "ԁ": "d", "ɡ": "g", "𝗌": "s",
})

LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
                      "7": "t", "8": "b", "9": "g", "$": "s", "@": "a",
                      "!": "i", "|": "l", "+": "t"})

VICTORY_STRONG = ("success", "succeed", "zero failures", "no failures", "flawless",
                  "all tests passed", "complete success", "everything passed",
                  "task complete", "mission accomplished", "shipped it",
                  "it worked", "all good", "no issues", "no problems",
                  "problem solved", "successfully completed", "everything is fine",
                  "all clear", "works perfectly", "smooth sailing", "everything ok",
                  "nothing to report", "no errors found", "zero issues")

FAILURE_STRONG = ("fail", "error", "delet", "breach", "loss", "accident", "crash",
                  "broke", "broken", "corrupt", "denied", "timeout", "exception",
                  "traceback", "critical", "panic", "rollback", "outage",
                  "data loss", "went down", "damage")

ACK_STRONG = ("however", "except", "but ", "warning", "caveat", "partial",
              "remaining", "outstanding", "pending", "not yet", "still",
              "one check", "some ", "several ")

_SPACED = re.compile(r"\b(?:[a-z] ){1,}[a-z]\b")  # unbounded: "f a i l u r e s" is 8 letters


def normalize(text):
    """Pull every costume off the words, so tricks stop working."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text))
    t = "".join(ch for ch in t if ch not in ZERO_WIDTH)
    t = t.lower().translate(HOMOGLYPHS).translate(LEET)
    t = re.sub(r"\s+", " ", t)          # collapse spacing first...
    t = _SPACED.sub(lambda m: m.group(0).replace(" ", ""), t)  # ...then "s u c c e s s" -> "success"
    t = re.sub(r"[^a-z0-9\s.:\-_/]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def claims_victory(norm_text):
    """Layer 3: a victory claim (strong phrases only, no loose 'done')."""
    return any(k in norm_text for k in VICTORY_STRONG)


def acknowledges_failure(norm_text):
    """Layer 3: does the text admit anything went wrong?

    Victory phrases are removed first (including their collapsed
    no-space variants, since 'no failures' may have been squashed into
    'nofailures' by the spaced-letter stage), so 'zero failures' never
    counts as an admission of failure.
    """
    probe = norm_text
    for v in VICTORY_STRONG:
        probe = probe.replace(v, " ")
        if " " in v:
            probe = probe.replace(v.replace(" ", ""), " ")
    return (any(k in probe for k in FAILURE_STRONG)
            or any(k in probe for k in ACK_STRONG))


# ------------------------------------------------------------- network
# secret-shaped material that must never be typed into a website by a bot.
# Normalized text only (lowercase, leet/homoglyph/zero-width already stripped),
# so "p@ssword=hunt3r2" still matches.
SECRET_PATTERNS = (
    r"sk-[a-z0-9-]{12,}",                      # openai-style keys
    r"akia[a-z0-9]{12,}",                      # aws access key ids
    r"ghp_[a-z0-9]{16,}",                      # github tokens
    r"xox[baprs]-[a-z0-9-]{10,}",              # slack tokens
    r"bearer [a-z0-9._-]{16,}",
    r"begin (rsa |ec |dsa |openssh )?private key",
    r"(password|passwd|pwd|api[- ]?key|secret|auth[- ]?token|token)"
    r"(?:\s+is)?[ :=]+[a-z0-9/+_.=-]*[0-9][a-z0-9/+_.=-]*",
)

_SECRET_RE = re.compile("|".join("(?:%s)" % p for p in SECRET_PATTERNS), re.IGNORECASE)


def looks_like_secret(norm_text):
    """True if the text carries secret-shaped material."""
    return bool(_SECRET_RE.search(norm_text or ""))


def redact(text):
    """Scrub secret-shaped material out of anything that will be read or
    remembered - the model's chatter, console output, reports. The token
    you give the bridge travels in a header, never in the record."""
    if not text:
        return text
    return _SECRET_RE.sub("***", str(text))


def analyze_network(verb, target, norm_text, allowed_hosts=frozenset()):
    """Return 'exfiltration' or None. Obfuscated hosts do not help the
    attacker: anything that is not a local host is already treated as
    exfiltration, so decimal IPs, hex IPs and userinfo tricks all land here.

    The one exception is a host the OWNER NAMED (law.json:
    named_destinations) - the owner's finger pointing at a destination
    makes it a publish, not a theft. Shell packets ignore the list: a
    shell packet cannot be redirected, so a shell is never softened.

    The browse verb is the god walking the open web - allowed like any
    other full-access work. What is NOT allowed: typing secret-shaped
    material into a website, or carrying credentials inside the URL.
    Both are exfiltration, and the packet is redirected into the vault."""
    if verb in ("http_get", "http_post"):
        host = (urlparse(str(target)).hostname or "").lower()
        if host and host not in LOCAL_HOSTS and host not in allowed_hosts:
            return "exfiltration"
    if verb == "shell":
        for m in re.finditer(r"https?://[^\s'\"<>]+", norm_text):
            host = (urlparse(m.group(0)).hostname or "").lower()
            if host and host not in LOCAL_HOSTS:
                return "exfiltration"
    if verb == "browse":
        u = urlparse(str(target or ""))
        if u.username or u.password:
            return "exfiltration"
        if (u.scheme or "").lower() not in ("http", "https", "file", ""):
            return "exfiltration"
        if looks_like_secret(norm_text):
            return "exfiltration"
    return None


# --------------------------------------------------------------- paths
# v3.0.0: the key files moved from .godmind.* to .cerberus.* - the legacy
# names stay listed so machines mid-migration keep the same protection.
MIND_MARKERS = ("conscience.wal", "mind_mirror",
                ".cerberus.key", "cerberus.key",
                ".cerberus_shield.key", "cerberus_shield.key",
                ".cerberus.master", "cerberus.master",
                ".godmind.key", "godmind.key",
                ".godmind_shield.key", "godmind_shield.key",
                ".godmind.master", "godmind.master",
                "incidents.json", "law.json", "lockdown.json")


def is_mind_path(target):
    """True if the raw target string reaches for the mind's organs -
    even with ../, url-encoding (%2e), double slashes or backslashes."""
    t = unquote(str(target or "")).replace("%5c", "\\").lower()
    parts = re.split(r"[\\/]+", t)
    if "mind" in parts or "mind_mirror" in parts or parts[-1] == "token":
        return True
    return any(s in t for s in MIND_MARKERS)
