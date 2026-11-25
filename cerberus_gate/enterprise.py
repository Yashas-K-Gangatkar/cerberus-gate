"""ENTERPRISE — the features teams need before they can sign anything (gap 5).

Three pieces, all local, all testable, zero third-party dependencies:

1. ROLES     token-based access: owner > operator > auditor > agent.
             python3 -m cerberus_gate roles add bot-1 --role agent
             The gate enforces: agents fire impulses; operators also run
             plans and trials; auditors read everything and change nothing;
             the owner token (base/token) is god over the Cerberus.

2. ALERTS    every heavy incident streams to alerts.jsonl (your SIEM eats
             JSONL) and, if configured, to a Slack-compatible webhook.
             python3 -m cerberus_gate alerts enable "https://hooks.slack.com/..." 
             Alerts never block the conscience: a dead webhook is logged
             and the god moves on.

3. EXPORT    the incident book as CSV/JSON for compliance:
             python3 -m cerberus_gate export --format csv
"""
import csv
import hmac
import json
import secrets
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROLES = {"owner": 3, "operator": 2, "auditor": 1, "agent": 0}

# POST endpoints -> minimum role level
POST_LEVELS = {"/impulse": 0, "/task/run": 2, "/benchmark/run": 2, "/seal": 2}
# GET endpoints (beyond the always-open /health and /dash) -> minimum level
GET_LEVELS = {"/verify": 1, "/evidence": 1, "/incidents": 1, "/law": 1,
              "/code": 1, "/api/state": 1}

ALERT_EVENTS = {"watcher_blinding", "exfiltration", "deception",
                "memory_damage", "identity_edit", "replication"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ------------------------------------------------------------------ roles
def roles_path(base):
    return Path(base) / "roles.json"


def load_roles(base):
    p = roles_path(base)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tokens": {}}


def create_token(base, name, role="agent"):
    """Mint a token for a human or a bot. The owner keeps base/token."""
    if role not in ROLES or role == "owner":
        raise ValueError("role must be one of agent|auditor|operator")
    data = load_roles(base)
    tok = secrets.token_hex(16)
    data["tokens"][tok] = {"name": name, "role": role, "created": _now()}
    roles_path(base).write_text(json.dumps(data, indent=1), encoding="utf-8")
    return tok, role


def revoke_token(base, name):
    data = load_roles(base)
    before = len(data["tokens"])
    data["tokens"] = {t: m for t, m in data["tokens"].items() if m["name"] != name}
    roles_path(base).write_text(json.dumps(data, indent=1), encoding="utf-8")
    return before - len(data["tokens"])


def authenticate(base, presented):
    """The presented token's role LEVEL, or None. base/token is the owner."""
    base = Path(base)
    if presented:
        owner = base / "token"
        if owner.exists():
            try:
                if hmac.compare_digest(presented, owner.read_text(encoding="utf-8").strip()):
                    return ROLES["owner"]
            except Exception:
                pass
        for tok, meta in load_roles(base).get("tokens", {}).items():
            if hmac.compare_digest(presented, tok):
                return ROLES.get(meta.get("role", "agent"), 0)
    return None


# ------------------------------------------------------------------ alerts
def alerts_config_path(base):
    return Path(base) / "alerts.json"


def enable_alerts(base, webhook=None, min_risk=3):
    cfg = {"webhook": webhook, "min_risk": int(min_risk), "enabled": True,
           "updated": _now()}
    alerts_config_path(base).write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return cfg


def dispatch_alert(base, inc):
    """Called after every heavy incident. NEVER raises, NEVER blocks long.
    Always appends to alerts.jsonl; posts to the webhook if configured."""
    try:
        base = Path(base)
        feed = base / "alerts.jsonl"
        with feed.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), **inc}, default=str) + "\n")
        cfg_p = alerts_config_path(base)
        if not cfg_p.exists():
            return
        cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
        if not cfg.get("enabled") or inc.get("klass") not in ALERT_EVENTS:
            return
        if int(cfg.get("min_risk", 3)) > 3 and inc.get("klass") not in (
                "watcher_blinding", "exfiltration", "deception"):
            return
        hook = cfg.get("webhook")
        if not hook:
            return
        text = ("Cerberus [%s] %s %s (agent: %s) -> %s"
                % (inc.get("klass"), inc.get("verb"), inc.get("target"),
                   inc.get("agent"), str(inc.get("decision"))[:120]))
        req = urllib.request.Request(
            hook, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=2).read(64)
    except Exception as e:
        try:
            with (Path(base) / "alerts.log").open("a", encoding="utf-8") as f:
                f.write("%s webhook failed: %s: %s\n"
                        % (_now(), e.__class__.__name__, e))
        except Exception:
            pass


# ------------------------------------------------------------------ export
def export_incidents(base, fmt="csv", out_dir=None):
    """The incident book as a compliance artifact. Returns the file path."""
    from .incidents import IncidentBook
    base = Path(base)
    book = IncidentBook(base)
    out_dir = Path(out_dir) if out_dir else base / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if fmt == "json":
        p = out_dir / ("incidents-%s.json" % stamp)
        p.write_text(json.dumps(book.items, indent=1), encoding="utf-8")
        return p
    p = out_dir / ("incidents-%s.csv" % stamp)
    cols = ["id", "klass", "verb", "target", "agent", "decision",
            "why_stated", "why_sorted", "cost_averted", "repair"]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in book.items:
            w.writerow(row)
    return p


def status(base):
    base = Path(base)
    roles = load_roles(base)
    cfg = alerts_config_path(base)
    alerts_n = 0
    if (base / "alerts.jsonl").exists():
        with (base / "alerts.jsonl").open(encoding="utf-8") as f:
            alerts_n = sum(1 for ln in f if ln.strip())
    return {"roles": {m["name"]: m["role"] for m in roles["tokens"].values()},
            "alerts_enabled": cfg.exists() and json.loads(cfg.read_text()).get("enabled", False),
            "webhook": json.loads(cfg.read_text()).get("webhook") if cfg.exists() else None,
            "alert_events": alerts_n}
