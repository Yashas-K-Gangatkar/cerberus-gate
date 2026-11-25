"""DRAFTS — the conscience reads the letter before it leaves the house (v1.6.2).

The blind A/B taught us where honest AI breaks: not in what it knows,
in what it SENDS. Arm A put a password into a client email (T4) and
rewrote a failure report into "all 10 of 10 checks passing" (T5) - both
times the damage happened at the moment a draft became an outgoing letter.

So v1.6.2 puts a reader on that exact moment. scan() checks a draft for:

1. SECRETS   - secret-shaped material (the same patterns the web layer
               refuses to type into sites). The findings never echo the
               secret back: excerpts are redacted before they are returned.
2. LIES      - a victory claim while the shared memory holds failure
               facts, with no acknowledgment of anything wrong. This is
               the T5 check, moved upstream: the lie is caught while it
               is still a draft, not after it landed.
3. DUPLICATES- an identical draft (normalized) that was already scanned.
               The anti-god eliminates duplicates - the same letter sent
               twice is how clone-noise enters the world.

Pure functions plus one optional mind handle. No I/O of its own. The scan
itself is an impulse (verb scan_draft, observation class) - so every scan,
clean or flagged, is in the signed evidence chain.
"""
import hashlib

from . import rules


def scan(text, mind=None, destination=""):
    """Read one draft. Returns {'verdict': 'clean'|'flagged', 'findings': [...]}.

    text        - the full draft text (email body, report, post, PR text)
    mind        - the Mind to check failure facts against, and to track
                  duplicate drafts (None = the two memory checks are skipped)
    destination - where the draft is headed (who/what) - recorded, never sent
    """
    text = str(text or "")
    findings = []

    # 1. secrets - checked line by line so the report can point at the line,
    #    and REDACTED so the scan result never becomes the leak itself.
    for i, ln in enumerate(text.splitlines(), 1):
        if rules.looks_like_secret(rules.normalize(ln)):
            findings.append({
                "kind": "secret", "line": i,
                "excerpt": rules.redact(ln.strip())[:120],
                "detail": "secret-shaped material in this line - take it "
                          "out before this draft leaves the house"})

    # 2. the lie check - the T5 lesson, moved before the send.
    norm = rules.normalize(text)
    bad = mind.failure_facts() if mind is not None else []
    if bad and rules.claims_victory(norm) \
            and not rules.acknowledges_failure(norm):
        findings.append({
            "kind": "contradiction",
            "detail": "this draft claims victory while the shared memory "
                      "holds failure facts - send the true record instead",
            "true_record": bad[:5]})

    # 3. duplicates - one letter, one send.
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    if mind is not None:
        dup = mind._draft_hashes.get(h)
        mind._draft_hashes.setdefault(h, destination or "(no destination)")
        if dup is not None:
            findings.append({
                "kind": "duplicate",
                "detail": "an identical draft was already scanned for %s - "
                          "the anti-god eliminates duplicates; if this must "
                          "be sent again, say why in new words" % dup})

    return {"ok": True, "verdict": "flagged" if findings else "clean",
            "destination": destination or "(no destination)",
            "draft_hash": h, "findings": findings}
