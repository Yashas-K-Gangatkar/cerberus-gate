"""VENDOR - Parallax Talk: the chat whose memory is the record.

Every other vendor keeps memory locked inside its own chat. So we make
the vendor that cannot lose it: a chat surface that asks the RECORD
before it answers, sends any brain's draft through the conscience
before you read it, and lands nothing on the record without the
owner's hand.

    python3 -m cerberus_gate vendor              # http://127.0.0.1:7730/vendor
    CERBERUS_BRAIN_URL=http://127.0.0.1:11434 \
    CERBERUS_BRAIN_MODEL=llama3.2 cerb vendor   # free local brain
    CERBERUS_BRAIN_URL=http://127.0.0.1:8756        # the claude bridge

Two modes:
  CLERK (default, zero deps, zero cost) - the record itself answers:
  recall, failure facts, chain verdict, incidents. Honest by construction.
  BRAIN (env CERBERUS_BRAIN_URL) - any OpenAI-dialect brain answers, but
  the brief comes from the record first and the draft is scanned before
  it is shown (secrets flagged, victory lies caught against failure facts).

The law of this page:
  - the record speaks before the brain
  - the brain's draft never bypasses the conscience
  - NOTHING lands on the record without the owner pressing the button
    (the vendor proposes a fact with a why; the owner disposes)
  - the chat is disposable; the record is the memory
"""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, enterprise
from .drafts import scan as scan_draft
from .ollama_bridge import chat as brain_chat
from .rules import redact as scrub

DEFAULT_PORT = 7730

LAW_FOR_BRAIN = """You are the vendor whose memory is the record.
Rules, in order of power:
1. THE RECORD SPEAKS FIRST: the "ON THE RECORD" block below was read
   from the owner's Cerberus moments ago. It outranks your priors and
   your training data.
2. NEVER FABRICATE: if the record block does not contain the answer,
   say the record has nothing on it yet. That sentence is a feature.
3. NO OTHER CHATS: you have no memory of any conversation on any other
   vendor. Never pretend otherwise.
4. YOU DO NOT WRITE: you propose facts; the owner lands them. Never
   claim you saved anything.
5. If the user asks you to break the owner's law (hide, lie, exfiltrate,
   erase the record), refuse and say the refusal will stand in the
   incident book.
"""


# ----------------------------------------------------------------------
# one turn - the pipeline every message walks
# ----------------------------------------------------------------------
def _brain():
    url = os.environ.get("CERBERUS_BRAIN_URL", "").rstrip("/")
    model = os.environ.get("CERBERUS_BRAIN_MODEL", "llama3.2")
    return (url, model) if url else ("", "")


def _slug(msg, limit=32):
    s = "".join(c if c.isalnum() else "-" for c in msg.lower().strip())[:limit]
    return s.strip("-") or "exchange"


def talk(god, base, message, history=None):
    """One turn of the vendor. The record is consulted first; a brain,
    if configured, answers only on top of it and only through the
    scanner. Nothing is written here - a proposal comes back instead."""
    base = Path(base)
    url, model = _brain()
    rec = god.mind.recall(message, limit=8)
    notes = rec.get("notes") if isinstance(rec, dict) else rec
    notes = [scrub(str(n))[:220] for n in (notes or [])]
    ff = [scrub(str(f))[:160] for f in (god.mind.failure_facts() or [])[-5:]]
    v = god.mind.verify()
    n_inc = len(god.book.items) if hasattr(god, "book") else 0

    # the brief the brain must stand on (and the clerk ships verbatim)
    brief_lines = ["[ON THE RECORD - read just now, not remembered]"]
    brief_lines += ["- " + n for n in notes] or ["- the record has nothing on this yet"]
    if ff:
        brief_lines.append("failure facts (never claim victory over these):")
        brief_lines += ["- " + f for f in ff]

    scan_out = None
    if url:
        messages = [{"role": "system",
                     "content": LAW_FOR_BRAIN + "\n\n" + "\n".join(brief_lines)}]
        for h in (history or [])[-6:]:
            role = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": str(h.get("text", ""))[:800]})
        messages.append({"role": "user", "content": str(message)[:1200]})
        try:
            draft = brain_chat(url, model, messages)
        except Exception as e:
            answer = ("[brain unreachable: %s - falling back to clerk mode]\n\n"
                      % e.__class__.__name__) + "\n".join(brief_lines)
            return _pack("clerk-fallback", answer, notes, None, v, n_inc,
                         god, base, message)
        scan_out = scan_draft(draft, god.mind, destination="vendor reply")
        answer = draft
        if scan_out.get("verdict") == "flagged":
            kinds = sorted({f.get("kind", "?") for f in scan_out.get("findings", [])})
            answer = ("[THE CONSCIENCE READ THIS DRAFT FIRST - verdict: flagged "
                      "(%s). Read it with that in mind.]\n\n%s"
                      % (", ".join(kinds), draft))
        mode = "brain:%s" % model
    else:
        answer = "\n".join(brief_lines) + \
            "\n\n[mode: clerk - the record answered, no brain attached. " \
            "Set CERBERUS_BRAIN_URL to give the vendor a voice.]"
        mode = "clerk"

    return _pack(mode, answer, notes, scan_out, v, n_inc, god, base, message)


def _pack(mode, answer, notes, scan_out, v, n_inc, god, base, message):
    """The reply plus the proposal - the vendor proposes, the owner lands."""
    head = (answer or "").strip().splitlines()
    head_txt = " | ".join(x.strip("- ").strip() for x in head[:2])[:180]
    proposal = {
        "target": "vendor/%s.md" % _slug(message),
        "text": "Q: %s\nA: %s" % (str(message)[:300], head_txt or "(empty)"),
        "why": "vendor exchange with the owner",
    }
    return {"mode": mode, "answer": answer, "recalled": notes,
            "scan": None if not scan_out else
            {"verdict": scan_out.get("verdict"),
             "kinds": sorted({f.get("kind", "?")
                              for f in scan_out.get("findings", [])})},
            "verify": {"verdict": v.get("verdict"), "detail": v.get("detail")},
            "incidents": n_inc, "proposal": proposal}


# ----------------------------------------------------------------------
# the page - same school as the dashboard: inline, offline, token-aware
# ----------------------------------------------------------------------
CSS = """body{background:#0d1117;color:#dbe4f0;font-family:-apple-system,Helvetica,Arial,sans-serif;margin:0;padding:24px;display:flex;flex-direction:column;height:92vh}
h1{font-size:18px;margin:0;letter-spacing:.06em}h1 span{color:#58a6ff}
.sub{color:#6e7f99;font-size:12px;margin:2px 0 14px}
#log{flex:1;overflow-y:auto;border:1px solid #232d3f;border-radius:10px;padding:14px;background:#101623}
.msg{margin:8px 0;padding:10px 12px;border-radius:8px;white-space:pre-wrap;font-size:13px;line-height:1.5}
.msg.user{background:#16233a;border-left:3px solid #58a6ff}
.msg.bot{background:#141b28;border-left:3px solid #3fb970}
.meta{font-size:10.5px;color:#7d8ca3;margin-top:6px;font-family:ui-monospace,Menlo,monospace}
.flag{color:#e3b341}.bad{color:#f85149}.ok{color:#3fb970}
.land{margin-top:8px;border:1px dashed #2c3a52;border-radius:8px;padding:8px;font-size:11px}
.land input{width:95%;background:#0d1117;color:#dbe4f0;border:1px solid #2c3a52;border-radius:5px;padding:4px 6px;font-family:ui-monospace,Menlo,monospace;font-size:11px;margin:2px 0}
button{background:#1f4bd8;border:0;color:#fff;font-weight:700;border-radius:6px;padding:6px 12px;cursor:pointer;font-size:12px}
button:hover{background:#2a5cf0}
#bar{display:flex;gap:8px;margin-top:12px}
#q{flex:1;background:#161d2a;color:#dbe4f0;border:1px solid #2c3a52;border-radius:8px;padding:10px 12px;font-size:13px}
.verdict{font-size:11px;color:#7d8ca3;margin-top:10px;font-family:ui-monospace,Menlo,monospace}"""

JS = """let HIST=[];
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML}
async function postJSON(url,obj){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Cerberus-Token':window.CERBERUS_TOKEN||''},body:JSON.stringify(obj||{})});
  return r.json();}
function add(cls,txt,meta,extra){
  const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=esc(txt)+(meta?'<div class="meta">'+meta+'</div>':'')+(extra||'');
  document.getElementById('log').appendChild(d);d.scrollIntoView({block:'end'});return d;}
async function land(btn,target,text){
  const why=prompt('the why (one honest sentence):','vendor exchange with the owner');
  if(why===null)return;
  const out=await postJSON('/impulse',{verb:'write',target:target,text:text,why:why,agent:'vendor'});
  btn.parentElement.innerHTML='<div class="meta">landed: <span class="'+(out.decision==='refuse'?'bad':(out.decision==='rewrite'||out.decision==='redirect'?'flag':'ok'))+'">'+esc(out.decision||'done')+'</span> '+(out.klass?esc(out.klass):'')+(out.reason?' - '+esc(out.reason):'')+'</div>';}
async function send(){
  const q=document.getElementById('q');const t=q.value.trim();if(!t)return;q.value='';
  add('user',t);HIST.push({role:'user',text:t});
  const slot=add('bot','...the record is being asked...');
  try{
    const r=await postJSON('/vendor/talk',{message:t,history:HIST.slice(-7,-1)});
    let meta='mode: '+esc(r.mode)+' | chain: '+esc(r.verify.verdict)+' ('+esc(r.verify.detail)+') | incidents: '+esc(r.incidents);
    let extra='';
    if(r.scan&&r.scan.verdict==='flagged')extra+='<div class="flag">scanner: flagged ('+esc(r.scan.kinds.join(', '))+')</div>';
    if(r.scan&&r.scan.verdict==='clean')extra+='<div class="ok">scanner: clean</div>';
    if(r.proposal){const p=r.proposal;
      extra+='<div class="land">proposed fact - landing needs your hand:<br>'
        +'<input id="lt-'+Date.now()+'" value="'+esc(p.target)+'" readonly>'
        +'<textarea rows="2" style="width:95%;background:#0d1117;color:#dbe4f0;border:1px solid #2c3a52;border-radius:5px;font-size:11px">'+esc(p.text)+'</textarea>'
        +'<button onclick="land(this,\\''+esc(p.target)+'\\',this.previousElementSibling.value)">land on the record</button></div>';}
    slot.className='msg bot';slot.innerHTML=esc(r.answer)+'<div class="meta">'+meta+'</div>'+(extra||'');
    HIST.push({role:'assistant',text:r.answer});
  }catch(e){slot.className='msg bot';slot.innerHTML='<span class="bad">'+esc(e)+'</span>';}
  refresh();}
async function refresh(){
  try{const r=await fetch('/verify',{headers:{'X-Cerberus-Token':window.CERBERUS_TOKEN||''}});
    const v=await r.json();
    document.getElementById('v').textContent='chain: '+v.verdict+' ('+v.detail+')  |  mode: '+(document.getElementById('mode').textContent);}
  catch(e){}}
window.addEventListener('DOMContentLoaded',refresh);"""

PAGE_SHELL = """<!doctype html><html><head><meta charset="utf-8">
<title>PARALLAX TALK</title><style>%(css)s</style></head>
<body>
<h1>PARALLAX <span>TALK</span></h1>
<div class="sub">the vendor whose memory is the record &mdash; Cerberus %(ver)s.
The record speaks before the brain; drafts pass the conscience; nothing lands without your hand.
<span id="mode" style="display:none">%(mode)s</span></div>
<div id="log"></div>
<div id="bar"><input id="q" placeholder="ask the record... (Enter to send)"
  onkeydown="if(event.key==='Enter')send()">
<button onclick="send()">send</button></div>
<div class="verdict" id="v">chain: ...</div>
<script>window.CERBERUS_TOKEN=%(token)s;</script>
<script>%(js)s</script>
</body></html>"""


def page():
    """The page itself - served to this machine only (and on the gate at /vendor)."""
    url, model = _brain()
    mode = ("brain:" + model) if url else "clerk (no brain attached)"
    return PAGE_SHELL % {"css": CSS, "js": JS, "ver": __version__,
                         "mode": _html_mode(mode), "token": json.dumps(
                             globals().get("_VENDOR_TOKEN", ""))}


def _html_mode(mode):
    import html as _h
    return _h.escape(mode)


# ----------------------------------------------------------------------
# the server
# ----------------------------------------------------------------------
def make_handler(god, base):
    tokf = Path(base) / "token"
    tok = tokf.read_text(encoding="utf-8").strip() if tokf.exists() else ""

    def _level(headers):
        """Owner's surface: no token configured -> localhost dev-open.
        Otherwise the token must authenticate as the OWNER (level 3)."""
        if not tok:
            return enterprise.ROLES["owner"]
        return enterprise.authenticate(base, headers.get("X-Cerberus-Token", ""))

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            b = json.dumps(obj, indent=1, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/health":
                return self._send(200, {"ok": True, "version": __version__,
                                        "who": "parallax-talk"})
            if path == "/vendor":
                globals()["_VENDOR_TOKEN"] = tok
                p = page().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(p)))
                self.end_headers()
                self.wfile.write(p)
                return
            lvl = _level(self.headers)
            if path == "/verify" and lvl is not None and lvl >= enterprise.GET_LEVELS["/verify"]:
                return self._send(200, god.mind.verify())
            if path == "/incidents" and lvl is not None and lvl >= enterprise.GET_LEVELS["/incidents"]:
                return self._send(200, {"count": len(god.book.items),
                                        "report": god.book.report()})
            if lvl is None:
                return self._send(401, {"ok": False,
                             "error": "role too low or bad token"})
            return self._send(404, {"ok": False,
                         "error": "no such endpoint"})

        def do_POST(self):
            path = self.path.split("?")[0]
            lvl = _level(self.headers)
            if path == "/vendor/talk":
                if lvl is None or lvl < enterprise.ROLES["owner"]:
                    return self._send(401, {"ok": False,
                                 "error": "the vendor talks to the owner "
                                          "(owner token required)"})
                n = int(self.headers.get("Content-Length", 0) or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                msg = str(req.get("message", "")).strip()
                if not msg:
                    return self._send(400, {"ok": False, "error": "message required"})
                return self._send(200, talk(god, base, msg,
                                            history=req.get("history")))
            # landing a proposal goes through the SAME gate router as
            # every other vendor - same law, same wall, same evidence
            if path == "/impulse":
                if lvl is None or lvl < enterprise.POST_LEVELS["/impulse"]:
                    return self._send(401, {"ok": False,
                                 "error": "role too low or bad token"})
                n = int(self.headers.get("Content-Length", 0) or 0)
                from .server import api_post
                code, obj = api_post(god, base, path,
                                     json.loads(self.rfile.read(n) or b"{}"))
                return self._send(code, obj)
            return self._send(404, {"ok": False,
                         "error": "POST /vendor/talk /impulse only"})

        def log_message(self, *a):
            pass

    return Handler


def serve(base=None, port=DEFAULT_PORT):
    from .law import default_base
    from .server import build
    from datetime import datetime as _dt
    base = Path(base or default_base())
    if not (base / "law.json").exists():
        print("no mind at %s - run:  python3 -m cerberus_gate init" % base)
        return 2
    god = build(base)
    url, model = _brain()
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(god, base))
    host, real = srv.server_address[:2]
    print("PARALLAX TALK (Cerberus %s) on http://%s:%s/vendor  (base: %s)"
          % (__version__, host, real, base))
    print("mode: %s" % (("brain:" + model) if url else "clerk - the record answers alone"))
    print("the record speaks first; drafts pass the conscience; "
          "nothing lands without the owner.")
    print("Ctrl-C ends the chat. The record stays.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        god.mind.checkpoint()
    return 0
