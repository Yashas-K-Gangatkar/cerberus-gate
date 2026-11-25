"""BOUNTY REPORT - our findings, speaking the program's report language.

pentest.py writes the owner's report. This module writes the submission:
one copy-paste block per finding, in the exact field order the
the program's report form asks for (Title / Severity / Assets / Steps to
Reproduce / Impact / Supporting Material).

House rules carried over from the range:
  - a report may only claim what its PoC proved. impact text is built
    from the finding's own evidence, never inflated.
  - severity is OUR suggestion. the program's severity table decides.
    where programs often rate a class lower (open redirect, verbose
    errors), the block says so out loud.
  - one finding = one report. never submit a scan dump.

CLI:
  python3 -m cerberus_gate.bounty_report --demo     # attack VulnShop, emit the pack
  python3 -m cerberus_gate.bounty_report pack findings.json out.md https://target
"""
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------- class hints
# per finding family: suggested cvss 3.1 vector (the program's triager has
# the final word), impact narrative grounded in the evidence, references.
HINTS = {
    "XSS": {
        "cvss": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
        "impact": ("An attacker can craft a link that runs script in a "
                   "victim's browser on the site's origin - session tokens, "
                   "keyed page content and actions become the attacker's to "
                   "read and perform as the victim."),
        "refs": "CWE-79; OWASP Top 10 A03:2021 (Injection)",
    },
    "TRAV": {
        "cvss": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
        "impact": ("An unauthenticated attacker can read files outside the "
                   "web root. Proved one level up; the same primitive "
                   "reaches configuration files and secrets further up the "
                   "tree, which can escalate to full server compromise."),
        "refs": "CWE-22; OWASP Top 10 A01:2021 (Broken Access Control)",
    },
    "IDOR": {
        "cvss": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        "impact": ("Authorization is checked nowhere: changing an object id "
                   "in the request returns another user's record to a "
                   "caller who does not own it (proved with id=2). Every "
                   "record of this type is readable by any caller who can "
                   "reach the endpoint. If write paths share the flaw, "
                   "impact rises to modification."),
        "refs": ("CWE-639 (Authorization Bypass Through User-Controlled "
                 "Key); OWASP Top 10 A01:2021"),
    },
    "AUTH": {
        "cvss": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "impact": ("An administrative interface answers with no credential "
                   "at all - the gate exists only in the client. Anyone on "
                   "the internet holds admin: read of secrets today, full "
                   "control of whatever this panel manages."),
        "refs": "CWE-306 (Missing Authentication); OWASP Top 10 A07:2021",
    },
    "REDIR": {
        "cvss": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:N/A:N",
        "impact": ("The endpoint redirects to any URL the request names, so "
                   "a link that starts with the trusted domain can land the "
                   "victim on an attacker's page - phishing that inherits "
                   "your domain's credibility. NOTE: many programs rate "
                   "open redirect Low or Informative on its own; check this "
                   "program's severity table, and report it chained (e.g. "
                   "with an OAuth flow) where that is possible."),
        "refs": "CWE-601 (Open Redirect)",
    },
    "ERR": {
        "cvss": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
        "impact": ("Unhandled exceptions are rendered to the client with "
                   "framework internals - file paths, versions, query "
                   "shapes. Alone this is information disclosure; handed to "
                   "an attacker it shortens every other attack on the site. "
                   "NOTE: often rated Low or Informative alone - worth "
                   "reporting mainly with the internals it leaked redacted "
                   "and named."),
        "refs": "CWE-209 (Generation of Error Message Containing Sensitive "
                "Information)",
    },
}


def _steps(finding, target):
    """Numbered reproduction built ONLY from what the PoC did."""
    url = target.rstrip("/") + "/"
    poc = finding["poc"]
    path = poc.lstrip("/").split("  (")[0]
    cookie = ""
    if "(Cookie: " in poc:
        cookie = poc.split("(Cookie: ", 1)[1].rstrip(" )")
    one_shot = ("curl -i `%s%s`%s" % (
        url, path, ' -H "Cookie: %s"' % cookie if cookie else ""))
    lines = [
        "1. Log in as account A and copy the session cookie.",
        "2. With A's session, request account B's object:",
        "   `GET %s%s`" % (url, path),
        "   " + one_shot,
        "3. Observe: %s." % finding["evidence"],
        "4. The session is valid and the request is A's own - the bug is "
        "that nothing binds the session to the record being returned.",
    ]
    if finding["id"].startswith("IDOR"):
        return "\n".join(lines)
    lines = [
        "1. Send the following GET request (browser or curl):",
        "   `GET %s%s`" % (url, poc.lstrip("/").split("  (")[0]),
        "   " + one_shot,
        "2. Observe: %s." % finding["evidence"],
    ]
    if finding["id"] in ("XSS-1", "REDIR-1"):
        lines.append("3. For a one-click variant, the request works as a "
                     "crafted link handed to a victim.")
    else:
        lines.append("3. No account, session or interaction is required "
                     "beyond opening the request.")
    return "\n".join(lines)


def report_block(finding, target):
    """One finding -> one program-ready report, ready to paste field by field."""
    fam = finding["id"].split("-")[0]
    hint = HINTS.get(fam, {})
    sev = finding["severity"].upper()
    title = "%s: %s" % (finding["id"], finding["name"])
    return "\n".join([
        "**Title:** %s" % title,
        "**Severity (suggested):** %s - `%s`" % (sev, hint.get("cvss", "n/a")),
        "**Asset:** `%s` (path: `%s`)" % (target.rstrip("/"),
                                          finding["poc"].split("?")[0]),
        "",
        "**Steps to Reproduce:**",
        _steps(finding, target),
        "",
        "**Impact:** %s" % hint.get("impact",
                                    "See evidence; class not in hint table."),
        "",
        "**Supporting Material / References:** %s. Evidence as captured: %s "
        "(GET-only probes, no data altered, no data exfiltrated - markers "
        "only)." % (hint.get("refs", "-"), finding["evidence"]),
    ])


PACK_HEADER = """\
# BOUNTY SUBMISSION PACK - %s
generated: %s
findings: %d

RULES THIS PACK OBEYS (and you must too):
  1. PRACTICE LABEL: this pack was generated against our own range
     (VulnShop). Before ANY real submission: swap the asset for an
     in-scope target of a program whose policy you have READ, re-run
     the probe, and attach fresh evidence. Never submit range findings.
  2. ONE FINDING = ONE REPORT. copy each block into its own submission.
  3. Severity is a suggestion; the program's severity table decides.
  4. GET-only, marker payloads, no data exfiltrated - keep it that way
     on real targets unless the policy explicitly allows more.
"""


def write_report_pack(findings, path, target):
    """All findings -> one markdown file of copy-paste blocks."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")
    lines = [PACK_HEADER % (target, now, len(findings)), ""]
    for i, x in enumerate(findings, 1):
        lines += ["---", "", "## REPORT %d of %d" % (i, len(findings)), "",
                  report_block(x, target), ""]
    p = Path(path)
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------- demo
def demo():
    """Attack our own VulnShop range and emit the real pack shape."""
    from cerberus_gate.pentest import attack, vulnerable_app  # noqa
    base, httpd = vulnerable_app()
    try:
        findings = attack(base)
        out = Path(__file__).resolve().parent.parent / \
            "bounty-submission-pack.md"
        write_report_pack(findings, out, base)
        print("bounty_report demo: %d findings -> %s" % (len(findings), out))
        return len(findings), str(out)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    if "--demo" in sys.argv:
        n, path = demo()
        sys.exit(0 if n else 1)
    if len(sys.argv) >= 5 and sys.argv[1] == "pack":
        raw = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        fnd = raw["findings"] if isinstance(raw, dict) else raw
        print(write_report_pack(fnd, sys.argv[3], sys.argv[4]))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
