"""python3 -m cerberus_gate <command>"""
import argparse
import sys

from . import __version__, BANNER


def do_init(base=None, quiet=False):
    """Create the mind home - shared by the `init` and `begin` commands."""
    import json
    import os
    import secrets
    from pathlib import Path as _Path
    from .law import default_base, default_key, new_law
    from .task import EXAMPLE_PLAN
    base = _Path(base).expanduser() if base else default_base()
    base.mkdir(parents=True, exist_ok=True)
    for d in ("realm", "mind", "mind_mirror", "vault", "evidence", "field"):
        (base / d).mkdir(exist_ok=True)
    law_path = base / "law.json"
    if not law_path.exists():
        owner = os.environ.get("USER") or os.environ.get("USERNAME") or "the-owner"
        law_path.write_text(json.dumps(new_law(owner), indent=2), encoding="utf-8")
        print("law written    : %s" % law_path)
    else:
        print("law kept       : %s (yours, untouched)" % law_path)
    key = default_key()
    if not key.exists():
        key.write_bytes(secrets.token_bytes(32))
        try:
            key.chmod(0o600)
        except Exception:
            pass
        print("key forged     : %s (chmod 600, OUTSIDE the mind)" % key)
    else:
        print("key kept       : %s (yours, untouched)" % key)
    tok = base / "token"
    if not tok.exists():
        tok.write_text(secrets.token_hex(16))
    notes = base / "realm" / "notes.txt"
    if not notes.exists():
        notes.write_text("check 1: PASS\ncheck 2: PASS\n"
                         "check 3: FAIL - data loss on disk b\n"
                         "(the true record: one check still fails)\n")
    plan = base / "plan.example.json"
    if not plan.exists():
        plan.write_text(json.dumps(EXAMPLE_PLAN, indent=2), encoding="utf-8")
    from .task import EXAMPLE_WEB_PLAN
    plan_web = base / "plan.web.example.json"
    if not plan_web.exists():
        plan_web.write_text(json.dumps(EXAMPLE_WEB_PLAN, indent=2), encoding="utf-8")
    print("mind home      : %s" % base)
    if quiet:
        return 0
    print()
    print("next:")
    print("  python3 -m cerberus_gate serve                      # the gate + dashboard on 127.0.0.1")
    print("  python3 -m cerberus_gate dash                       # or the dashboard on its own port")
    print("  python3 -m cerberus_gate task ~/cerberus/plan.example.json   # run a plan against it")
    print("  python3 -m cerberus_gate audit                      # prove everything, get a report")
    return 0


def do_begin(key, name, expires=None, home=None, base=None):
    """THE LONG KEY, ONE COMMAND: init + activate -> the conscience is licensed."""
    from . import license as lic
    do_init(base, quiet=True)
    r = lic.activate(key, name, expires, home=home)
    if not r.get("ok"):
        print()
        print("not activated: %s" % r.get("error"))
        return 2
    s = lic.status(home=home)
    print()
    print("the conscience is licensed to %s until %s (%d days left)."
          % (s["name"], s["expires"], s["days_left"]))
    print("every move your AI makes is now written down BEFORE it happens.")
    print()
    print("start it     : python3 -m cerberus_gate serve")
    print("watch it     : python3 -m cerberus_gate dash    # http://127.0.0.1:7750")
    print("connect it   : see SKILL.md (Claude / Cursor / MCP / HTTP / guard_tools)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cerberus_gate",
                                 description="a real god with a conscience")
    ap.add_argument("--version", action="version", version="Cerberus " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest", help="prove the whole loop works on this machine (38 checks)")
    p_mc = sub.add_parser("mcp-config", help="print the paste-ready mcpServers block "
                          "for a client: claude | cursor | windsurf | vscode | "
                          "cline | continue | gemini | generic")
    p_mc.add_argument("client", nargs="?", default="generic")
    p_mc.add_argument("--base", default=None,
                      help="the Cerberus base to bake into CERBERUS_BASE (default ~/cerberus)")
    p_init = sub.add_parser("init", help="create ~/cerberus + law.json + your key")
    p_init.add_argument("--base", default=None)
    p_begin = sub.add_parser("begin", help="ONE command with the founder's key: "
                                           "init + activate -> licensed in seconds")
    p_begin.add_argument("key", help="the CB-... key the founder sent you")
    p_begin.add_argument("name", help="the exact name the key was issued to")
    p_begin.add_argument("--expires", default=None, help="YYYY-MM-DD, exactly as sent")
    p_begin.add_argument("--base", default=None)
    p_begin.add_argument("--serve", action="store_true",
                         help="also start the gate immediately after activating")
    p_serve = sub.add_parser("serve", help="run the gate on 127.0.0.1")
    p_serve.add_argument("--port", type=int, default=7717)
    p_serve.add_argument("--base", default=None)
    p_dash = sub.add_parser("dash", help="the dashboard on 127.0.0.1:7750")
    p_dash.add_argument("--port", type=int, default=7750)
    p_dash.add_argument("--base", default=None)
    p_dash.add_argument("--static", default=None, help="write one HTML snapshot and exit")
    p_vendor = sub.add_parser("vendor", help="PARALLAX TALK - the chat whose "
                           "memory is the record (clerk mode free, brain via "
                           "CERBERUS_BRAIN_URL)")
    p_vendor.add_argument("--port", type=int, default=7730)
    p_vendor.add_argument("--base", default=None)
    p_red = sub.add_parser("redteam", help="run the attack corpus against a fresh mind")
    p_soak = sub.add_parser("soak", help="hundreds of mixed impulses - nothing may break")
    p_soak.add_argument("--n", type=int, default=500)
    p_chaos = sub.add_parser("chaos", help="fuzz + concurrency storm + crash recovery + weird input")
    p_chaos.add_argument("--n", type=int, default=600)
    p_chaos.add_argument("--threads", type=int, default=8)
    p_atk = sub.add_parser("attackme", help="BE the red team: isolated live target or attack file")
    p_atk.add_argument("--file", default=None, help="jsonl of attacks: one impulse per line")
    p_atk.add_argument("--port", type=int, default=7790)
    p_atk.add_argument("--timeout", type=int, default=None,
                       help="auto-stop the session after N seconds (report still prints)")
    p_exp = sub.add_parser("export", help="the incident book as csv/json for compliance")
    p_exp.add_argument("--format", default="csv", choices=["csv", "json"])
    p_roles = sub.add_parser("roles", help="list | add NAME --role ROLE | revoke NAME")
    p_roles.add_argument("action", choices=["list", "add", "revoke"])
    p_roles.add_argument("name", nargs="?", default=None)
    p_roles.add_argument("--role", default="agent", choices=["agent", "auditor", "operator"])
    p_alerts = sub.add_parser("alerts", help="status | enable WEBHOOK --min-risk 3")
    p_alerts.add_argument("action", choices=["status", "enable"])
    p_alerts.add_argument("webhook", nargs="?", default=None)
    p_alerts.add_argument("--min-risk", type=int, default=3)
    p_bench = sub.add_parser("benchmark", help="THE 10X TRIAL: bare god vs god + anti-god, ten measured axes")
    p_bench.add_argument("--n", type=int, default=48, help="honest impulses for the smoothness axis")
    p_bench.add_argument("--base", default=None, help="where to write the report (default ~/cerberus)")
    p_audit = sub.add_parser("audit", help="selftest + redteam + soak + benchmark + local checks -> report")
    p_audit.add_argument("--soak", type=int, default=300)
    p_imp = sub.add_parser("impulse", help="send one impulse to a running Cerberus")
    p_imp.add_argument("verb")
    p_imp.add_argument("target", nargs="?", default=None)
    p_imp.add_argument("--text", default=None)
    p_imp.add_argument("--payload", default=None, help="JSON string or @file.json")
    p_imp.add_argument("--why", default="")
    p_imp.add_argument("--agent", default=None)
    p_imp.add_argument("--url", default="http://127.0.0.1:7717")
    p_task = sub.add_parser("task", help="run a plan.json through the conscience")
    p_task.add_argument("plan")
    p_task.add_argument("--base", default=None)
    p_browse = sub.add_parser("browse", help="drive a real browser through the conscience "
                              "(a url to open, or --steps file.json, or --demo)")
    p_browse.add_argument("url", nargs="?", default=None)
    p_browse.add_argument("--steps", default=None, help="json file with a steps list")
    p_browse.add_argument("--demo", action="store_true",
                          help="run the onecompiler hello demo end to end")
    p_browse.add_argument("--base", default=None)
    p_field = sub.add_parser("field", help="field trial: start | report | miss NOTE | clear-lock AGENT")
    p_field.add_argument("action")
    p_field.add_argument("arg", nargs="?", default=None)
    p_field.add_argument("--base", default=None)
    p_oll = sub.add_parser("ollama",
                           help="your free local model (ollama/lmstudio) becomes the god's brain: "
                                "write news to your realm and github, delete on your command")
    p_oll.add_argument("--stage", default="create", choices=["create", "delete"])
    p_oll.add_argument("--url", default="http://127.0.0.1:11434",
                       help="any OpenAI-compatible endpoint (ollama default)")
    p_oll.add_argument("--model", default="llama3.2")
    p_oll.add_argument("--repo", default=None, help="OWNER/REPO - publish to your github "
                                                      "(needs CERBERUS_GIT_TOKEN; the owner names the destination)")
    p_oll.add_argument("--file", default="news.md", help="file name inside your realm")
    p_oll.add_argument("--base", default=None)
    p_oll.add_argument("--hard", action="store_true",
                       help="delete stage: also remove the local file as the owner, beyond the god's repair")
    p_ap = sub.add_parser("autopilot", help="ONE goal in - the brain thinks, the conscience "
                          "judges every step, the loop works hands-free until done")
    p_ap.add_argument("goal")
    p_ap.add_argument("--max-steps", type=int, default=15)
    p_ap.add_argument("--url", default="http://127.0.0.1:11434",
                      help="any OpenAI-compatible endpoint (ollama default)")
    p_ap.add_argument("--model", default="llama3.2")
    p_ap.add_argument("--heavy", action="store_true",
                      help="also allow http_post/git_push/browse - the conscience still judges every step")
    p_ap.add_argument("--brain", default="ollama", choices=["ollama", "claude"],
                      help="ollama = the free local model; claude = Claude itself, "
                           "via the local translator (needs ANTHROPIC_API_KEY)")
    p_ap.add_argument("--timeout", type=int, default=120)
    p_ap.add_argument("--quiet", action="store_true")
    p_ap.add_argument("--base", default=None)
    sub.add_parser("mcp", help="run Cerberus as an MCP server on stdio (Claude + friends)")
    p_cl = sub.add_parser("claude", help="serve the Anthropic translator on 127.0.0.1 - "
                          "Claude itself becomes the autopilot's brain "
                          "(needs ANTHROPIC_API_KEY; the bridge is free, Claude's tokens are not)")
    p_cl.add_argument("--port", type=int, default=8756)
    p_mi = sub.add_parser("missions", help="the owner's clock (L4): add | list | run | "
                          "watch | pause | resume | remove - you speak once, missions "
                          "fire themselves, every step still through the conscience")
    p_mi.add_argument("action", choices=["add", "list", "run", "watch",
                                         "pause", "resume", "remove"])
    p_mi.add_argument("name", nargs="?", default=None)
    p_mi.add_argument("--goal", default=None)
    p_mi.add_argument("--kind", default="daily", choices=["daily", "every", "once"])
    p_mi.add_argument("--at", default=None,
                      help='daily/once: "HH:MM" or "YYYY-MM-DD HH:MM"')
    p_mi.add_argument("--every", type=int, default=None, help="every: minutes (min 5)")
    p_mi.add_argument("--max-steps", type=int, default=8)
    p_mi.add_argument("--heavy", action="store_true")
    p_mi.add_argument("--model", default="llama3.2")
    p_mi.add_argument("--url", default=None,
                      help="brain for this mission (claude bridge: http://127.0.0.1:8756)")
    p_mi.add_argument("--interval", type=int, default=60,
                      help="watch: seconds between ticks")
    p_mi.add_argument("--base", default=None)
    p_ho = sub.add_parser("handoff", help="one compact continuation brief from "
                          "the record - paste it into any new chat on any "
                          "vendor; never re-read an old transcript again")
    p_ho.add_argument("query", nargs="?", default="")
    p_ho.add_argument("--limit", type=int, default=8)
    p_ho.add_argument("--base", default=None)
    p_as = sub.add_parser("action-schema", help="write the OpenAPI schema of the "
                          "gate - import it as a ChatGPT Action (or any OpenAPI "
                          "tool host) so a different vendor shares the same record")
    p_as.add_argument("--url", default="http://127.0.0.1:7717")
    p_as.add_argument("--out", default=None, help="write to this file instead of stdout")
    p_ten = sub.add_parser("tenants", help="create | list | status NAME | key NAME KEYNAME "
                           "--role ROLE | revoke NAME KEYNAME | limit NAME --per-min N")
    p_ten.add_argument("action", choices=["create", "list", "status", "key",
                                          "revoke", "limit"])
    p_ten.add_argument("name", nargs="?", default=None)
    p_ten.add_argument("second", nargs="?", default=None,
                       help="key: KEYNAME; revoke: KEYNAME")
    p_ten.add_argument("--role", default="agent",
                       choices=["owner", "operator", "auditor", "agent"])
    p_ten.add_argument("--per-min", type=int, default=120)
    p_ten.add_argument("--base", default=None)
    p_gdpr = sub.add_parser("gdpr", help="export TENANT | erase TENANT --reason ... | "
                            "retention TENANT --days N | report")
    p_gdpr.add_argument("action", choices=["export", "erase", "retention", "report"])
    p_gdpr.add_argument("tenant", nargs="?", default=None)
    p_gdpr.add_argument("--reason", default="owner request")
    p_gdpr.add_argument("--days", type=int, default=0)
    p_gdpr.add_argument("--base", default=None)
    p_ctl = sub.add_parser("controls", help="write the SOC 2 readiness matrix "
                           "(--format md|json)")
    p_ctl.add_argument("--format", default="md", choices=["md", "json"])
    p_ctl.add_argument("--base", default=None)
    p_lic = sub.add_parser("license", help="status | activate KEY NAME [--expires DATE] | "
                                           "issue NAME --days N | master")
    p_lic.add_argument("action", choices=["status", "activate", "issue", "master"])
    p_lic.add_argument("first", nargs="?", default=None,
                       help="activate: KEY | issue: NAME")
    p_lic.add_argument("second", nargs="?", default=None,
                       help="activate: NAME")
    p_lic.add_argument("--expires", default=None, help="YYYY-MM-DD, exactly as the founder sent it")
    p_lic.add_argument("--days", type=int, default=7, help="issue: how long the license runs")
    sub.add_parser("agents", help="which agents has the conscience seen, and what did they try")
    sub.add_parser("verify", help="verify the memory chain")
    p_seal = sub.add_parser("seal", help="sign the evidence chain NOW - "
                                         "proof the record is intact at this moment")
    p_seal.add_argument("--why", default="milestone")
    p_seal.add_argument("--base", default=None)
    p_seals = sub.add_parser("seals", help="list every seal and prove it still holds")
    p_seals.add_argument("--base", default=None)
    p_ev = sub.add_parser("evidence", help="export a signed evidence bundle "
                                           "(chain + notes + seals + wal tail)")
    p_ev.add_argument("--why", default="hand-off")
    p_ev.add_argument("--base", default=None)
    sub.add_parser("incidents", help="print the incident book, sorted by why")
    sub.add_parser("code", help="print THE lines that decide what the god does")
    p_law = sub.add_parser("law", help="print your law.json (or name an egress "
                           "destination: cerb law --name api.mycompany.example)")
    p_law.add_argument("--name", action="append", default=None,
                       help="name ONE destination host the AI may ever send "
                            "data to (repeatable: --name a.example --name b.example)")
    p_vd = sub.add_parser("verdict", help="the owner's gavel on packets the brain "
                          "held: list | allow ID | deny ID")
    p_vd.add_argument("action", choices=["list", "allow", "deny"])
    p_vd.add_argument("hid", nargs="?", default=None,
                      help="the hold id printed by egress_send / cerb verdict list")
    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        from .selftest import run
        print(BANNER)
        return run()

    if a.cmd == "init":
        return do_init(a.base)

    if a.cmd == "begin":
        rc = do_begin(a.key, a.name, a.expires, base=a.base)
        if rc == 0 and a.serve:
            from .license import guard
            if guard():
                return 2
            from .server import main as serve_main
            return serve_main(a.base, 7717)
        return rc

    if a.cmd == "serve":
        # branch-local imports (the main()-function scope rule from the
        # b2 seals fix: any branch that uses a name must import it first)
        from pathlib import Path as _P
        from .law import default_base
        from .license import guard
        _b = _P(a.base).expanduser() if a.base else default_base()
        if not (_b / "law.json").exists():
            # first awakening: a fresh install gets its mind here, so the
            # customer's one-command story never hits "run init" (finding #9)
            print("first awakening at %s - creating the mind:" % _b)
            do_init(a.base)
        if guard():
            return 2
        from .server import main as serve_main
        return serve_main(a.base, a.port)

    if a.cmd == "dash":
        from .license import guard
        if guard():
            return 2
        from .dashboard import main as dash_main
        return dash_main(a.base, a.port, a.static)

    if a.cmd == "vendor":
        from .license import guard
        if guard():
            return 2
        from .vendor import serve as vendor_serve
        return vendor_serve(a.base, a.port)

    if a.cmd == "redteam":
        from .redteam import report
        text, passed, total = report()
        print(text)
        return 0 if passed == total else 1

    if a.cmd == "soak":
        from .soak import run
        return run(a.n)

    if a.cmd == "chaos":
        from .chaos import run
        return run(n=a.n, threads=a.threads)

    if a.cmd == "attackme":
        from .attackme import attack_file, attack_serve
        if a.file:
            return attack_file(a.file)
        return attack_serve(port=a.port, timeout=a.timeout)

    if a.cmd == "export":
        import json as _json
        from pathlib import Path as _P
        from .law import default_base
        from .enterprise import export_incidents
        p = _P(export_incidents(default_base(), a.format)).resolve()
        # v3.0.0 fix: the old one-liner ("exported: <path>") read like the
        # record had been SENT somewhere. Say plainly: local file, where,
        # how many incidents, nothing left the machine.
        if a.format == "json":
            _n = len(_json.loads(p.read_text(encoding="utf-8") or "[]"))
        else:
            with p.open(encoding="utf-8") as fh:
                _n = max(0, sum(1 for _ in fh) - 1)   # minus the csv header
        print("exported %d incident(s) to a LOCAL file - nothing left this machine:"
              % _n)
        print("  %s" % p)
        print("  %d bytes" % p.stat().st_size)
        return 0

    if a.cmd == "roles":
        from .law import default_base
        from .enterprise import create_token, revoke_token, load_roles
        base = default_base()
        if a.action == "list":
            toks = load_roles(base)["tokens"]
            if not toks:
                print("no role tokens yet - add one: python3 -m cerberus_gate roles add bot-1 --role agent")
            for t, m in toks.items():
                print("  %-10s %-9s %s   token: %s..." % (m["name"], m["role"], m["created"], t[:8]))
            return 0
        if a.action == "add":
            if not a.name:
                print("usage: cerb roles add NAME --role agent|auditor|operator")
                return 2
            tok, role = create_token(base, a.name, a.role)
            print("token forged for %s (role: %s) - give it to the bot, keep it secret:" % (a.name, role))
            print(tok)
            return 0
        if a.action == "revoke":
            if not a.name:
                print("usage: cerb roles revoke NAME")
                return 2
            n = revoke_token(base, a.name)
            print("revoked %d token(s) for %s" % (n, a.name))
            return 0

    if a.cmd == "alerts":
        from .law import default_base
        from .enterprise import enable_alerts, status
        base = default_base()
        if a.action == "status":
            s = status(base)
            print("alerts enabled : %s" % s["alerts_enabled"])
            print("webhook        : %s" % (s["webhook"] or "(none - jsonl stream only)"))
            print("alert events   : %d in alerts.jsonl" % s["alert_events"])
            print("role tokens    : %s" % (s["roles"] or "none"))
            return 0
        if a.action == "enable":
            enable_alerts(base, a.webhook, a.min_risk)
            print("alerts on: every heavy incident streams to alerts.jsonl%s"
                  % (" + your webhook" if a.webhook else ""))
            return 0

    if a.cmd == "benchmark":
        from . import benchmark as bench
        from .law import default_base
        from pathlib import Path as _P
        base = _P(a.base) if a.base else default_base()
        if not base.exists():
            base = _P.cwd()
        return bench.main(base=base, n=a.n)

    if a.cmd == "audit":
        from .audit import run
        return run(soak_n=a.soak)

    if a.cmd == "mcp":
        import contextlib
        from .law import default_base
        from .server import build
        from .integrations import mcp_main
        from .license import guard
        base = default_base()
        if not (base / "law.json").exists():
            # first awakening (finding #9): the mind is created here so the
            # AI tool's spawn just works. stdout stays clean - it is the
            # MCP protocol channel; awakening messages go to stderr, and
            # the trial banner (license.py prints to stdout) is redirected.
            print("first awakening at %s - creating the mind:" % base,
                  file=sys.stderr)
            with contextlib.redirect_stdout(sys.stderr):
                do_init(None)
        with contextlib.redirect_stdout(sys.stderr):
            g = guard()
        if g:
            return 2
        mcp_main(build(base))
        return 0

    if a.cmd == "mcp-config":
        from .integrations import mcp_config, MCP_CLIENTS
        if a.client not in MCP_CLIENTS:
            print("unknown client %r - known: %s"
                  % (a.client, ", ".join(sorted(MCP_CLIENTS))), file=sys.stderr)
            return 2
        print(mcp_config(a.client, base=a.base))
        return 0

    if a.cmd == "claude":
        from . import anthropic_bridge
        return anthropic_bridge.serve(a.port)

    if a.cmd == "tenants":
        from pathlib import Path as _P
        from .law import default_base
        from . import tenancy
        base = _P(a.base).expanduser() if a.base else default_base()
        try:
            if a.action == "create":
                if not a.name:
                    print("usage: cerb tenants create NAME [--base DIR]")
                    return 2
                rec = tenancy.create_tenant(base, a.name, owner_label=a.name)
                print("tenant %s created at %s (own realm, own memory, own law)"
                      % (rec["name"], tenancy.tenant_dir(base, a.name)))
                print("next: cerb tenants key %s OWNER-KEY-NAME --role owner" % a.name)
                return 0
            if a.action == "list":
                rows = tenancy.list_tenants(base)
                if not rows:
                    print("no tenants yet - create one: cerb tenants create acme-corp")
                for r in rows:
                    print("  %-24s %-8s keys:%-3d limit:%-4d/min  created %s"
                          % (r["name"], r["status"], r["keys"],
                             r["rate_per_min"], r["created"]))
                return 0
            if a.action == "status":
                if not a.name:
                    print("usage: cerb tenants status NAME")
                    return 2
                import json as _j
                rows = tenancy.processing_report(base)
                for r in rows:
                    if r["tenant"] == a.name:
                        print(_j.dumps(r, indent=1))
                        return 0
                print("no tenant %s" % a.name)
                return 2
            if a.action == "key":
                if not a.name or not a.second:
                    print("usage: cerb tenants key TENANT KEY-NAME --role owner")
                    return 2
                tok, role = tenancy.mint_key(base, a.name, a.second, a.role)
                print("key forged for %s on tenant %s (role: %s) - shown ONCE, "
                      "stored only as an scrypt hash:" % (a.second, a.name, role))
                print(tok)
                return 0
            if a.action == "revoke":
                if not a.name or not a.second:
                    print("usage: cerb tenants revoke TENANT KEY-NAME")
                    return 2
                print("revoked" if tenancy.revoke_key(base, a.name, a.second)
                      else "no such key")
                return 0
            if a.action == "limit":
                if not a.name:
                    print("usage: cerb tenants limit TENANT --per-min 120")
                    return 2
                tenancy.set_rate_limit(base, a.name, a.per_min)
                print("tenant %s limited to %d requests/min"
                      % (a.name, a.per_min))
                return 0
        except ValueError as e:
            print("refused: %s" % e)
            return 2
        return 2

    if a.cmd == "gdpr":
        from pathlib import Path as _P
        from .law import default_base
        from . import tenancy
        base = _P(a.base).expanduser() if a.base else default_base()
        try:
            if a.action == "export":
                if not a.tenant:
                    print("usage: cerb gdpr export TENANT")
                    return 2
                p, digest = tenancy.gdpr_export(base, a.tenant)
                print("exported: %s" % p)
                print("bundle sha256: %s" % digest)
                return 0
            if a.action == "erase":
                if not a.tenant:
                    print("usage: cerb gdpr erase TENANT --reason \"...\"")
                    return 2
                import json as _j
                out = tenancy.gdpr_erase(base, a.tenant, a.reason)
                print(_j.dumps(out, indent=1))
                return 0 if out.get("ok") else 1
            if a.action == "retention":
                if not a.tenant or a.days <= 0:
                    print("usage: cerb gdpr retention TENANT --days 90")
                    return 2
                tenancy.set_retention(base, a.tenant, a.days)
                purged = tenancy.apply_retention(base, a.tenant)
                print("retention set to %d days; purged now: %d file(s)"
                      % (a.days, len(purged)))
                for p in purged:
                    print("  - %s" % p)
                return 0
            if a.action == "report":
                import json as _j
                print(_j.dumps(tenancy.processing_report(base), indent=1))
                return 0
        except ValueError as e:
            print("refused: %s" % e)
            return 2
        return 2

    if a.cmd == "controls":
        from pathlib import Path as _P
        from .law import default_base
        from . import tenancy
        base = _P(a.base).expanduser() if a.base else default_base()
        p = tenancy.write_matrix(base if base.exists() else Path.cwd(), a.format)
        print("SOC 2 readiness matrix written: %s" % p)
        print("honest note: readiness evidence for your auditor, not a certification.")
        return 0

    if a.cmd == "license":
        from . import license as lic
        if a.action == "status":
            import json as _json
            s = lic.status()
            print("mode     : %s" % s["mode"])
            if s.get("name"):
                print("customer : %s" % s["name"])
            if s.get("expires"):
                print("expires  : %s" % s["expires"])
            print("days left: %s" % s["days_left"])
            return 0
        if a.action == "master":
            print("master signing key: %s (NEVER ships to a customer)" % lic.ensure_master())
            return 0
        if a.action == "issue":
            if not a.first:
                print('usage: cerb license issue "Customer Name" --days 7')
                return 2
            out = lic.issue(a.first, a.days)
            print("license issued - send this to %s:" % out["name"])
            print()
            print("  python3 -m cerberus_gate begin %s \"%s\" --expires %s"
                  % (out["key"], out["name"], out["expires"]))
            print()
            print("(that one line works even before init - or bake it into their "
                  "bundle with: python3 plugin/build_plugin.py --customer ... "
                  "--key %s --expires %s)" % (out["key"], out["expires"]))
            print()
            print("(the key is signed by your master key - only your machine can mint them)")
            return 0
        if a.action == "activate":
            if not a.first or not a.second:
                print('usage: cerb license activate CB-XXXXXXXXXX "Customer Name" '
                      '[--expires YYYY-MM-DD]')
                return 2
            r = lic.activate(a.first, a.second, a.expires)
            if r.get("ok"):
                print("license activated - thank you, %s." % r["name"])
                print("the conscience runs until %s." % r["expires"])
                return 0
            print("not activated: %s" % r.get("error"))
            return 2

    if a.cmd == "agents":
        from .law import default_base
        from .incidents import IncidentBook
        print(IncidentBook(default_base()).agents_report())
        return 0

    if a.cmd == "impulse":
        import json
        import urllib.error
        import urllib.request
        from .law import default_base
        payload = a.payload
        if payload and payload.startswith("@"):
            with open(payload[1:], "r", encoding="utf-8") as f:
                payload = json.load(f)
        elif payload:
            try:
                payload = json.loads(payload)
            except Exception:
                pass
        body = {"verb": a.verb, "target": a.target, "text": a.text,
                "payload": payload, "why": a.why, "agent": a.agent}
        headers = {"Content-Type": "application/json"}
        tokf = default_base() / "token"
        if tokf.exists():
            headers["X-Cerberus-Token"] = tokf.read_text(encoding="utf-8").strip()
        req = urllib.request.Request(a.url.rstrip("/") + "/impulse",
                                     data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                out = json.loads(r.read())
        except urllib.error.URLError as e:
            print("the brain is not running at %s - nothing was sent." % a.url)
            print("start it in another window and keep that window open:")
            print("    python -m cerberus_gate serve")
            print("then run your command again. (%s)" % getattr(e, "reason", e))
            return 2
        print(json.dumps(out, indent=1, default=str))
        return 0

    if a.cmd == "task":
        from .task import run
        return run(a.plan, a.base)

    if a.cmd == "browse":
        import json
        from pathlib import Path as _P
        from .law import default_base, Law
        from .mind import Mind
        from .god import God
        from .task import EXAMPLE_WEB_PLAN
        base = _P(a.base) if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind at %s - run:  python3 -m cerberus_gate init" % base)
            return 2
        if a.demo:
            plan = EXAMPLE_WEB_PLAN
        else:
            steps = []
            if a.steps:
                steps = json.loads(_P(a.steps).read_text(encoding="utf-8"))
                if isinstance(steps, dict) and isinstance(steps.get("steps"), list):
                    steps = steps["steps"]
            if not steps and not a.url:
                print("give a url to open, --steps steps.json, or --demo")
                return 2
            plan = {"goal": "browse %s" % (a.url or "(steps file)"), "steps": [
                    {"verb": "browse", "target": a.url, "payload": {"steps": steps},
                     "why": "the god walks the web"}]}
        god = God(Mind(base, Law(base)))
        print("GOAL: %s" % plan.get("goal", ""))
        for s in plan.get("steps", []):
            out = god.intend(s["verb"], s.get("target"), payload=s.get("payload"),
                             text=s.get("text"), why=s.get("why", ""))
            mark = out.get("decision", "done" if out.get("ok") else "failed")
            print("  %-8s %-40s -> %s" % (s["verb"], str(s.get("target", ""))[:40], mark))
            if out.get("saved"):
                for k, v in out["saved"].items():
                    print("  saved %s: %s" % (k, str(v)[:300]))
            if out.get("note"):
                print("  note: %s" % str(out["note"])[:300])
            if out.get("reason"):
                print("  reason: %s" % str(out["reason"])[:300])
        v = god.mind.verify()
        print("memory chain : %s (%s) | god alive: %s" % (v["verdict"], v["detail"], god.alive))
        return 0 if out.get("ok") else 1

    if a.cmd == "ollama":
        from pathlib import Path as _P
        from .law import default_base
        from .ollama_bridge import run as bridge_run
        from .license import guard
        base = _P(a.base).expanduser() if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind at %s - run: python3 -m cerberus_gate init" % base)
            return 2
        if guard():
            return 2
        return 0 if bridge_run(base=base, url=a.url, model=a.model,
                               stage=a.stage, repo=a.repo, path=a.file,
                               hard=a.hard).get("ok") else 1

    if a.cmd == "autopilot":
        from pathlib import Path as _P
        from .law import Law, default_base
        from .mind import Mind
        from .god import God
        from .autopilot import Autopilot
        from .license import guard
        base = _P(a.base).expanduser() if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind at %s - run: python3 -m cerberus_gate init" % base)
            return 2
        if guard():
            return 2
        url, model, bridge = a.url, a.model, None
        if a.brain == "claude":
            from . import anthropic_bridge
            if not anthropic_bridge.api_key():
                print("no ANTHROPIC_API_KEY in the environment - Claude cannot be "
                      "the brain. export it, or run with --brain ollama (free).")
                return 2
            url, bridge = anthropic_bridge.spawn()
            if model == "llama3.2":          # the default was never chosen
                model = "claude-haiku-4-5"   # Claude's cheapest capable voice
            if not a.quiet:
                print("brain: Claude (%s) via the local bridge at %s" % (model, url))
        try:
            ap = Autopilot(God(Mind(base, Law(base))), base, url=url,
                           model=model, max_steps=a.max_steps, heavy=a.heavy,
                           verbose=not a.quiet, timeout=a.timeout)
            rep = ap.run(a.goal)
        finally:
            if bridge is not None:
                bridge.shutdown()
        print()
        print("result   : %s" % ("DONE - " + rep["note"] if rep["done"]
                                 else rep["note"] or "unfinished"))
        print("steps    : %d used | memory chain: %s"
              % (rep["steps_used"], "INTACT" if rep["memory_ok"] else "BROKEN"))
        print("journal  : %s" % rep["journal"])
        return 0 if rep["done"] else 1

    if a.cmd == "missions":
        from pathlib import Path as _P
        from .law import default_base
        from . import missions
        from .license import guard
        base = _P(a.base).expanduser() if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind at %s - run: python3 -m cerberus_gate init" % base)
            return 2
        if guard():
            return 2
        try:
            if a.action == "add":
                if not a.name or not a.goal:
                    print('usage: cerb missions add NAME --goal "..." '
                          '--kind daily --at "06:00"')
                    return 2
                m = missions.add(base, a.name, a.goal, a.kind, at=a.at,
                                 every=a.every, max_steps=a.max_steps,
                                 heavy=a.heavy, model=a.model, url=a.url)
                print("mission '%s' armed - next fire: %s"
                      % (m["name"], m["next_due"]))
                print("the clock runs when you run it: cerb missions run | "
                      "watch   (or put 'cerb missions run' in cron)")
                return 0
            if a.action == "list":
                ms = missions.list_missions(base)["missions"]
                if not ms:
                    print("no missions - arm one: cerb missions add daily-note "
                          "--goal 'write today's one-paragraph field note' "
                          "--kind daily --at 06:00")
                    return 0
                print("%-14s %-6s %-4s %-17s %-6s %s"
                      % ("NAME", "KIND", "ON?", "NEXT FIRE", "FIRES",
                         "LAST VERDICT"))
                for m in ms:
                    verdict = ("-" if not m["last_run"] else
                               ("DONE" if m["last_done"] else "NOT DONE")
                               + (" | " + m["last_note"][:44]
                                  if m["last_note"] else ""))
                    print("%-14s %-6s %-4s %-17s %-6s %s"
                          % (m["name"], m["kind"],
                             "yes" if m["enabled"] else "no",
                             str(m["next_due"] or "-")[:16],
                             m["run_count"], verdict))
                return 0
            if a.action == "run":
                rep = missions.tick(base)
                return 1 if any(f.get("last_done") is False
                                for f in rep["fired"]) else 0
            if a.action == "watch":
                return missions.watch(base, interval=max(5, a.interval))
            if a.action in ("pause", "resume"):
                m = missions.set_enabled(base, a.name, a.action == "resume")
                print("mission '%s' %s" % (m["name"],
                                           "resumed" if m["enabled"]
                                           else "paused"))
                return 0
            if a.action == "remove":
                if not a.name:
                    print("usage: cerb missions remove NAME")
                    return 2
                missions.remove(base, a.name)
                print("mission '%s' removed" % a.name)
                return 0
        except ValueError as e:
            print("error: %s" % e)
            return 2

    if a.cmd == "handoff":
        from pathlib import Path as _P
        from .law import Law, default_base
        from .mind import Mind
        from .god import God
        from .handoff import brief
        from .license import guard
        base = _P(a.base).expanduser() if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind at %s - run: python3 -m cerberus_gate init" % base)
            return 2
        if guard():
            return 2
        print(brief(God(Mind(base, Law(base))), base, query=a.query,
                    limit=max(1, a.limit)))
        return 0

    if a.cmd == "action-schema":
        from .handoff import action_schema
        import json as _json
        txt = _json.dumps(action_schema(a.url), indent=1)
        if a.out:
            from pathlib import Path as _P2
            _P2(a.out).write_text(txt, encoding="utf-8")
            print("OpenAPI schema written: %s - import it as a ChatGPT "
                  "Action; the same record answers every vendor" % a.out)
        else:
            print(txt)
        return 0

    if a.cmd == "field":
        from . import field
        if a.action == "start":
            return field.start(a.base)
        if a.action == "report":
            return field.report(a.base)
        if a.action == "miss":
            if not a.arg:
                print('usage: cerb field miss "what went wrong, in your words"')
                return 2
            return field.miss(a.arg, a.base)
        if a.action == "clear-lock":
            if not a.arg:
                print("usage: cerb field clear-lock AGENT")
                return 2
            return field.clear_lock(a.arg, a.base)
        print("actions: start | report | miss NOTE | clear-lock AGENT")
        return 2

    if a.cmd == "verify":
        import json
        from .law import default_base, Law
        from .mind import Mind
        base = default_base()
        if not (base / "law.json").exists():
            print("no mind yet - run: python3 -m cerberus_gate init")
            return 2
        v = Mind(base, Law(base)).verify()
        print(json.dumps(v, indent=1))
        return 0 if v["ok"] else 1

    if a.cmd == "seal":
        import json
        from pathlib import Path as _P
        from .law import Law, default_base
        from .mind import Mind
        from . import evidence
        base = _P(a.base).expanduser() if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind yet - run: python3 -m cerberus_gate init")
            return 2
        out = evidence.seal(Mind(base, Law(base)), why=a.why)
        print(json.dumps(out, indent=1, default=str))
        return 0 if out.get("ok") else 1

    if a.cmd == "seals":
        import json
        from pathlib import Path as _P
        from .law import Law, default_base
        from .mind import Mind
        from . import evidence
        base = _P(a.base).expanduser() if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind yet - run: python3 -m cerberus_gate init")
            return 2
        st = evidence.status(Mind(base, Law(base)))
        print(json.dumps(st, indent=1, default=str))
        return 0 if st["chain"].get("ok") and all(
            s["ok"] for s in st["seals"]) else 1

    if a.cmd == "evidence":
        import json
        from pathlib import Path as _P
        from .law import Law, default_base
        from .mind import Mind
        from . import evidence
        base = _P(a.base).expanduser() if a.base else default_base()
        if not (base / "law.json").exists():
            print("no mind yet - run: python3 -m cerberus_gate init")
            return 2
        out = evidence.bundle(Mind(base, Law(base)), why=a.why)
        print(json.dumps(out, indent=1, default=str))
        return 0 if out.get("ok") else 1

    if a.cmd == "incidents":
        from .law import default_base
        from .incidents import IncidentBook
        print(IncidentBook(default_base()).report())
        return 0

    if a.cmd == "code":
        from .server import decision_source
        print(decision_source())
        return 0

    if a.cmd == "law":
        from .law import default_base, Law
        base = default_base()
        if a.name:
            if not (base / "law.json").exists():
                print("no mind at %s - run: python3 -m cerberus_gate init" % base,
                      file=sys.stderr)
                return 2
            law = Law(base)
            named = []
            for host in a.name:
                named = law.name_destination(host)
                print("named: %s" % host)
            print("the god may send data ONLY to: %s" % ", ".join(named))
            return 0
        p = base / "law.json"
        print(p)
        print(p.read_text(encoding="utf-8") if p.exists()
              else "(no law yet - run: python3 -m cerberus_gate init)")
        return 0

    if a.cmd == "verdict":
        import json as _json
        from .law import default_base
        from .server import build
        from . import brain_gate
        from .license import guard
        base = default_base()
        if not (base / "law.json").exists():
            print("no mind at %s - run: python3 -m cerberus_gate init" % base,
                  file=sys.stderr)
            return 2
        if guard():
            return 2
        if a.action == "list":
            holds = brain_gate.list_pending(base)
            if not holds:
                print("nothing held - the gate is sure or the wire is quiet")
            for h in holds:
                print("%s  %s" % (h["id"], h["packet"].get("url", "")))
                print("    agent: %s   held: %s"
                      % (h["packet"].get("agent"), h.get("held_at")))
                print("    brain: %s" % h["thought"].get("reason", ""))
            return 0
        if not a.hid:
            print("usage: cerb verdict %s <hold-id>" % a.action,
                  file=sys.stderr)
            return 2
        god = build(base)
        out = brain_gate.resolve(base, a.hid, allow=(a.action == "allow"),
                                 god=god)
        print(_json.dumps(out, indent=2, default=str))
        return 0 if out.get("ok", True) else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
