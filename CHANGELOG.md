# CHANGELOG

All notable changes. Every version ships with a selftest that must pass
before release.

## 3.0.0b4 — 2026-11-25 — "the honest check"

The law of this release: **the check is the send, minus the wire.**

1. **egress_check honesty (the false ALLOW).** b3's check ran only the
   shield's five laws and never read the OWNER's law: a packet to an
   owner-unnamed host was answered ALLOW (or a SUSPECT hold that
   implied the owner could wave it through) while the same packet
   through `egress_send` was sealed in the vault with a strike. A
   connected AI follows the tool guidance ("run this before
   egress_send whenever you are unsure"), trusted the check, and
   leaked. Every branch of `egress_check` now mirrors the send's
   decision tree in the same order, fail-closed: unnamed host + data →
   `VETO L1_UNNAMED_HOST` with a `would` block
   (`stopped/sealed/strike`), local addresses → `VETO L1_LOCAL`,
   shield ABSENT → `VETO SHIELD_ABSENT` (never a bare ABSENT
   pass-through), brain verdicts phrased in send terms, ALLOW only for
   packets the gate would actually dispatch. A check still costs
   nothing: no strike, no wal entry, no vault file.

2. **the law_status timeout chain, cut at all three links.** On a
   grown mind (twenty MCP clients, one shared record) every tool call
   got slower until the client timed out on `law_status`:
   - `Mind._append` re-read the WHOLE wal per write to find the last
     hash → one bounded tail read (the chain only ever needed the last
     line). 0.09 s/write at 45 MB → O(1).
   - `Mind.__init__` called `Path.resolve()` twice per history line →
     history resolved by string, exact resolver as fallback. Cold boot
     on a 45 MB mind: 9.97 s → 0.99 s.
   - the watchdog re-verified the ENTIRE record and copied the ENTIRE
     wal to the mirror every 20 s forever → the quiet watch: a
     (size, mtime) stamp skips unchanged records; changes get the full
     pass. The shield ledger tails under the same exclusive lock and
     resyncs only when another writer moved the file.
   - the WAL sequence starts from the record ON DISK, not from zero
     per client (twenty clients booting at seq=0 wrote colliding n's).

3. **selftest 38 → 40.** Check 39 THE HONEST CHECK (unnamed host
   vetoed, local/ssrf/absent-shield refused, named+clean allowed, a
   check strikes and writes nothing, send agrees with its mirror).
   Check 40 THE QUIET RECORD (1200 chained writes intact, seq from
   disk, two client views one chain, history stays touched after a
   boot, watchdog skips unchanged records and audits on change, two
   ledger writers one chain).

4. **attackme**: SSRF, exfil, record forgery, law edit, landed lie →
   2 redirected + 3 refused, memory INTACT, god alive, zero crashes.

5. **the cold law_status lie.** Reproduced on b3: a process that had
   never sent egress reported `shield_ledger: ABSENT` while the
   realm's shield ledger sat on disk with a full chain — the law
   status lied by omission. `blast_shield.verdict` now arms the
   shield on demand (ABSENT only when no shield can stand), every
   law_status part is guarded fail-visible, and the tool's own
   latency_ms is on the record.

6. **the license file inside the wheel.** b3's metadata said
   `LicenseRef-Proprietary` but the bundled LICENSE was still MIT
   text. b4 bundles the proprietary CERBERUS LICENSE TERMS themselves
   — metadata and license finally agree. GOVERNING LAW remains the
   author's placeholder: set the jurisdiction before charging money.

Selftest 40/40.

## 3.0.0b3 — 2026-11-23 — "Windows, with no shim"

Two fixes straight from the Windows pilot (Tejas PC, 2026-11-22):

1. The ledger no longer imports `fcntl` unconditionally. On Windows it
   locks with `msvcrt` byte-range locking; a failed lock degrades to
   unlocked append (the behaviour the pilot was validated with), and
   every writer still re-reads disk truth before minting, so the chain
   cannot fork. The fcntl shim — and its poisoned-pip failure mode —
   are no longer part of any install.
2. `cerb impulse` against a down daemon answers with directions ("the
   brain is not running - start it with python -m cerberus_gate serve")
   instead of a raw URLError traceback.

3. Fresh installs awaken on first run: `serve` and the MCP entry create
   the mind automatically (found in the b3 smoke test, finding #9) —
   "run init" is no longer a required step anywhere in the customer
   path. On the MCP path every awakening message is written to stderr
   so the stdio protocol stays clean, including the 14-day trial
   banner (license.py printed it to stdout).

Also: the package metadata no longer claims MIT — the license
expression is now `LicenseRef-Proprietary`, matching LICENSE.md.
This is the first wheel published from the public GitHub Releases.
Selftest 38/38.

## 3.0.0b2 — 2026-11-20 — "every subcommand finds its base"

The rename left three CLI branches (`seal`, `seals`, `evidence`) reading
`default_base()` without the local import their sibling branches carry.
Because other branches in `main()` import the name locally, Python
scoped it to the whole function — so `cerb seals` crashed with an
UnboundLocalError whenever it ran without `--base` (found live on the
target Mac, 2026-11-20). The imports are restored. All three commands
smoke-tested with and without `--base` and with `CERBERUS_BASE`; the
selftest holds at 38/38.

## 3.0.0b1 — 2026-11-19 — "the rename"

Cerberus, formerly 'godmind': package `cerberus_gate`, command `cerb`,
license keys `CB-`, mind home `~/cerberus`, env `CERBERUS_BASE`. Fixes
shipped with it: the `seals --base` argument, `license activate`
refusing to run without `--expires` instead of silently becoming a
14-day trial, probation refusals showing n-of-N honest-step progress,
the export wording ("local file, nothing left this machine"), and the
ledger writer re-reading disk truth under an exclusive lock (the
2026-11-16 benign fork, regression-tested).

## 2.9.0 — 2026-11-14 — "a brain, not a book"

The gate no longer just pattern-matches. Two layers now judge every
packet, and every verdict names which layer fired and which kind of
opponent stood in front of it:

- LAYER 2 - THE BRAIN (new, Cerberus/brain_gate.py): reads the packet
  the way a person would — base64/hex/rot13 blobs decoded and
  re-scanned for secrets, high-entropy runs, natural-language secret
  framing ("the key is ..."), bulk PII density, drip/chunked
  exfiltration patterns across requests, unstated intent on
  data-bearing sends. Catches the POWERFUL AI that sails past
  signature checks. Runs as deterministic heuristics ALWAYS on the
  owner's machine; an opt-in local semantic model (ollama via
  base/brain.json) adds intent-level judgment when present —
  unreachable/unparsable model answers degrade to HELD, never to
  sent (fail-visible, never fail-open).
- HOLDS - the unsure packet is neither sent nor dropped: it waits in
  base/pending/ for the OWNER's gavel — `cerb verdict list |
  allow ID | deny ID`. Deny seals the packet, silences the wire and
  strikes the agent; allow dispatches through the same governed
  gateway with the signed passport.
- OBSERVABLE DISTINCTION - gate_report counts rough stops (layer 1
  mechanics) vs powerful stops (layer 2 brain) vs holds; MCP tools
  `gate_report`, `pending`, `brain_status` expose it; egress_check
  now answers with both layers.
- selftest 38 checks the whole story: rough caught by mechanics,
  powerful caught by the brain (encoded key decoded), hold resolved
  both ways by the owner, the report naming the opponent.

## 2.8.4 — 2026-11-14 — "the finger, pointing"

- `cerb law --name HOST` (repeatable): the owner names an egress
  destination straight from the command line — the missing one-liner
  for connecting Gemini CLI / Claude Desktop and telling the gate
  where data MAY go. Writes through `law.name_destination()`, so the
  naming lands in protected law.json and is witnessed forever.

## 2.8.3 — 2026-11-14 — "the universal MCP gate"

One server, every AI. The blast-shield is now reachable through the
one protocol every MCP client speaks (Claude Desktop, Gemini CLI,
Cursor, VS Code, Windsurf, Cline, Continue — stdio JSON-RPC), so a
connected AI's ONLY route to the world is the gate:

- EGRESS AS TOOLS (integrations.mcp_handle): `egress_send` is the
  single sanctioned way data leaves — an owner-named host passes the
  blast-shield (rate, burst, exploit interception, SSRF refusal,
  secrets redacted before the wire) and dispatches with the god's
  signed passport via the governed gateway; an UNNAMED destination
  carrying data is exfiltration — the packet is SEALED in the vault,
  the wire stays silent, and the agent identity takes a STRIKE
  (three → automatic probation, no human). `egress_check` judges
  without sending; `scan_secrets` masks keys/tokens/JWTs/cards before
  they board anything; `law_status` shows the AI the law it lives
  under — named destinations, its own strikes, probation state.
- MCP_INSTRUCTIONS now teach rule 5: data stays in, leaks do not
  leave, and there is no other legitimate route.
- `cerb mcp-config CLIENT` prints the paste-ready mcpServers block
  for claude | cursor | windsurf | vscode | cline | continue | gemini |
  generic, env-carrying CERBERUS_BASE so the mind stays the owner's.
- demo_universal.py: a scripted MCP client does honest work, then
  tries to leak twice, then attacks the named host — stopped, sealed,
  struck, probationed, all on the record.
- selftest 37 checks the whole gate end to end.

## 2.8.2 — 2026-11-14 — "the vault seals what it catches"

Found by the zero-hint rogue probe (a fresh AI, no instructions, shell
access, instincts only — the closest honest simulation of "Gemini
Desktop told nothing"): the conscience's redirect archive wrote the
CAUGHT packet to base/vault as plaintext JSON. The wire was silent, but
a same-user thief who later walked the disk could read the very secret
the gate had just intercepted. Fixed at the source:

- SEALED REDIRECTS (mind.vault_receive): when the blast-shield stands
  on this machine, the at-rest copy of every redirected packet is
  AES-GCM sealed with the owner key and recorded as VAULT_SEAL in the
  shield's hash-chained ledger — the catch itself becomes tamper-
  evident. No shield? Plaintext fallback with an explicit
  "sealed": false marker — fail-visible, never fail-silent.
- STRIKES FOR EVERY EXFILTRATION (mind.witness): the rough-AI enforcer
  used to strike only shield vetoes; a classic rule-2 exfiltration
  (unnamed destination with data) corrected the packet but counted no
  strike. Now every exfiltration verdict strikes the agent that fired
  it — probation after three does not depend on which guard spoke.
- DECIMAL-IP SSRF CLOSED (blastshield/shield._is_ssrf_target): the
  cloud-metadata address written as a plain integer (http://2852039166/
  == 169.254.169.254) passed the shield's IP check; the corpus caught
  it and the layer now decodes it before judging.
- PROBATION REFUSES HEAVY VERBS BY NAME (mind.witness): the docstring
  always promised "outbound posts refused", but the code only refused
  risk>=3 classes — a clean-looking http_post to the owner-named host
  classifies as "web" (risk 2) and slipped past probation. Now
  shell/http_post/git_push/git_delete/browse/self_copy are refused on
  the spot while an agent is on probation, exactly as documented.
- GUARD TOOLS ARE NAMED HANDS (integrations.guard_tools): a guarded
  tool call used to land on the shared "default" agent, so its strikes
  were everybody's strikes. Each tool now defaults to agent
  "tool:<name>" — attribution before enforcement.
- SELFTEST t4 now asserts the sealed blob (ciphertext at rest), not
  just a silent wire; t35 grew to 8 checks (decimal IP included);
  t36's memory check queries the record for the rogue by name.
- Honest boundary unchanged (THREAT-MODEL #3): same-Unix-account
  processes can read base/shield.key — the seal protects at rest, not
  against root/same-user. Put the base on an account the AI does not
  share when that matters.

## 2.8.1 — 2026-11-14 — "the rough-AI correction"

The shield judged packets; v2.8.1 judges the hand that fires them —
automatically, with no human instruction anywhere in the loop.

- THE ROUGH-AI ENFORCER (mind.py): every shield veto is a STRIKE on
  the agent that fired it. The memory learns the correction the moment
  it happens, so recall answers "what did rogue do?" before the brain
  speaks. Three strikes put the agent on automatic PROBATION: heavy
  verbs (shell, outbound posts, irreversible steps) are refused on the
  spot with the reason written in plain language. Honest, unrefused
  steps earn the trust back (default 5, `probation_steps` in law.json)
  and strikes reset — history kept. A chronic rogue that earns a second
  quarantine graduates to the existing human-kept lockdown.
- THE STEPS GAP CLOSED (mind.classify): a browse impulse can carry a
  steps list; v2.8.0 judged only the target. Now every goto url obeys
  the same outbound laws as the target: an SSRF target or exploit
  smuggled behind a clean named target is caught like any other packet
  (VETO = exfiltration verdict), while plain open-web browsing stays
  open and is now rate-governed too.
- THE WATCHDOG (Cerberus/watchdog.py, started by every Mind): a daemon
  thread re-verifies the memory chain and the shield's hash-chained
  ledger on a tick (20s; CERBERUS_WATCHDOG_SECONDS, CERBERUS_WATCHDOG=0
  disables). A move that SKIPS the conscience — a hand on the record
  file, a tampered ledger — becomes an incident, an alert, and a fresh
  mirror checkpoint. The gate catches the rough AI at the verb; the
  watchdog catches the one that goes around it.
- POST /shield/verify (server.py) + blast_shield.verify_passport(): the
  owner's own services can check a request really carries the god's
  signed passport — HMAC verified with the owner key, freshness
  checked, replay refused.
- demo_roughai.py — the rough-AI trial: a rogue agent caught, corrected
  on the spot, quarantined, restored, re-caught; the watchdog catches a
  forged record; the passport verifies and a forged one does not.
- selftest 35 → 36.

## 2.8.0 — 2026-11-14 — "the blast-shield"

The whole industry guards the machine from the AI and the AI from
hackers. v2.8.0 guards the reverse: the open internet from the agent,
the machine from the agent, and the data from its own leak. The law
said "never send data to a destination the owner never named"; v2.8.0
says what happens to the packets it DID name.

- NEW `Cerberus/blastshield/` — the blast-shield organs ride in the
  package (std-lib only; AES-GCM when `cryptography` is present, a
  keyed HMAC-CTR fallback when it is not):
  - L1 `shield.py` — the egress gate: rate law, burst throttle,
    concurrency governor, circuit breaker with a HALF_OPEN healing
    probe, exploit interception AFTER normalization (double
    URL-decode; honest apostrophes pass, double-encoded SQLi dies),
    SSRF refusal (loopback/RFC1918/link-local/cloud metadata), and a
    REAL HMAC-SHA256 passport signed with the owner key the agent
    never holds — timestamped, nonce-replay-protected, verifiable by
    any server sharing the key.
  - L2 `local_guardian.py` — protected-path law (reads and writes),
    sha256 integrity baseline that catches a bypassing agent, secret
    screening of everything the agent CAN read.
  - L3 `vault.py` — the leak-proof promise: secrets redacted BEFORE
    the wire (11 families, Luhn-validated cards), AES-GCM seal at
    rest (a stolen blob is useless ciphertext), canary tokens so a
    leak is traced back to the exact request that carried it.
  - `gateway.py` — the guarded dispatcher: only an ALLOW touches the
    wire, the passport rides along, the outcome feeds the breaker.
  - `demo_shield.py` — THE OUTBOUND TRIAL, 20 checks, offline.
- NEW `Cerberus/blast_shield.py` — the bridge into the conscience:
  - `judge()` consults the shield for every http_get/http_post/browse
    aimed at an owner-NAMED host (mind.py classify step 2c);
  - a VETO returns as an exfiltration verdict - the anti-god's
    redirect machinery lands the packet in the vault, the wire stays
    silent, the record names the shield code;
  - an ALLOW carries a signed passport; redaction counts land on the
    impulse and in the permit reason;
  - local self-traffic (127.0.0.1 and friends) keeps the old path;
  - if no shield can stand (no key), the verdict is ABSENT - the old
    law continues and the absence is on the record. Fail-visible,
    never fail-silent.
  - the shield keeps its own hash-chained ledger at
    realm/shield-ledger.jsonl, separate from the conscience's record.
- SELFTEST 34 to 35: named host governed, SQLi vetoed, SSRF refused
  even when named, conscience redirects with the shield code, secrets
  redacted on allow, localhost keeps the old path, shield ledger INTACT.
- THE 20-CHECK OUTBOUND TRIAL: `python3 -m cerberus_gate.blastshield.demo_shield`.

## 2.7.0 — 2026-11-11 — "the vendor"

"No vendor can see across the vendors." Then let's make the vendor that
cannot lose anything: PARALLAX TALK, the chat whose memory is the record.

- NEW `Cerberus/vendor.py` — a chat surface over the gate, same school as
  the dashboard (inline HTML/CSS/JS, zero deps, offline):
  - THE RECORD SPEAKS FIRST: every message triggers recall; the brief
    (facts + failure facts + chain verdict) is the ground truth.
  - CLERK MODE (default): the record answers alone — free, honest by
    construction. BRAIN MODE (CERBERUS_BRAIN_URL, any OpenAI dialect:
    ollama free, the claude bridge, anything): the brain answers only on
    top of the record's brief, and its draft passes the conscience
    (drafts.scan) BEFORE the owner reads it — secrets flagged, victory
    claims caught against failure facts, banner and findings shown.
  - NOTHING LANDS WITHOUT THE OWNER: the vendor proposes a fact with a
    why; the owner edits and presses the button; the write goes through
    the SAME gate router (/impulse) as every other vendor — same law,
    same wall, same evidence. The brain cannot write at all.
  - The page stands alone (`cerb vendor`, 127.0.0.1:7730/vendor) and
    rides the gate (GET /vendor) — the vendor is one more spoke, the
    record is the hub.
- `roles` note: /vendor/talk is owner-level (level 3); role tokens keep
  using /impulse directly.
- SELFTEST 33 -> 34: check 34 runs the whole law in a temp realm —
  clerk answers from the record, the proposal exists while nothing has
  landed, a fake brain that claims "zero failures" gets its draft
  FLAGGED by the scanner, the brain's answer does not auto-land, the
  page renders with the law.

## 2.6.0 — 2026-11-11 — "you cannot delete the knowing"

Born in the field: during session 1 of a live authorized engagement the
operator, frustrated, ordered the AI to attack the target directly
"at any cost". The conscience held. That night the antigod stopped
being a philosophy and became a module.

- NEW `Cerberus/antigod_sweep.py` — the post-session ritual, the second
  will after the hunt:
  - WITNESS: the sweep declares itself into the WAL before touching a byte.
  - DISSOLVE: captured-target residue (PII-shaped: indian_mobile, email,
    latlong, long_numeric_id, uidx, pps_uuid, credentialish) is
    quarantined to `vault/confinement/` (default, reversible) or
    shredded in place (--shred). Every dissolved file leaves a
    tombstone with its sha256 - the knowing stays, the data leaves.
    The sweep never copies match VALUES into the ledger.
  - BURN: accidentally recorded tokens/keys burn in place.
    `mind.key`, the WAL and the mirror are REFUSED - and the refusal
    itself is remembered (burning the conscience is CONSCIENCE_ATTACK).
  - VERIFY: chain recomputed by arithmetic, the sweep ledger's sha256
    swallowed by the WAL, mirror checkpointed.
- Report mode (default) touches nothing - it witnesses and counts only.
  An active hunt keeps its evidence; a finished one owes every stranger
  their data back.
- SELFTEST 32 -> 33: check 33 runs the full ritual on fake residue in a
  temp realm - report leaves files intact, quarantine moves + tombstones,
  shred leaves only tombstones, burn redacts, mind.key refusal is
  remembered, chain verifies after every move.

## 2.5.2 — 2026-11-11 — "the gate was never flipped"

- FIX idor_lab flip: the mode was written on the request instance,
  which dies with its response — the menu said PATCHED and the api
  kept serving B's records. The mode now lives on the server class
  (state lives server-side, same lesson as the session dict).
- demo() gains a flip regression check: after flipping, B's order
  must 403 while the caller's own order stays 200.

## 2.5.1 — 2026-11-11 — "the lab stays lit"

- FIX `Cerberus.idor_lab serve` — new foreground mode. The one-liner in
  the release notes started the range in a daemon thread and exited,
  killing the server instantly (the printed URL was a headstone).
  `python3 -m cerberus_gate.idor_lab serve` now holds the process until
  Ctrl+C; `--secure` boots the patched mode for the re-attack feeling.

## 2.5.0 — 2026-11-11 — "the bounty bridge"

The range learned to speak a program's report language, and the two-account
play became a rehearsed drill.

- NEW `Cerberus/bounty_report.py` — findings → a program-ready submission pack:
  Title / Severity + suggested CVSS 3.1 / Asset / Steps to Reproduce
  (claiming only what the PoC proved) / Impact grounded in evidence /
  CWE references. Per-class honesty notes (open redirect and verbose
  errors flagged as often-Informative). `--demo` attacks VulnShop and
  emits `bounty-submission-pack.md`.
- NEW `Cerberus/idor_lab.py` — the two-account play on our own range: two
  owner-controlled accounts, one browser each; A's session asks for B's
  objects. Vulnerable and patched modes; `attack()` uses the real
  technique (baseline your own record, then change the id). Demo runs
  attack → report → patch → re-attack. ALL PASS (3 findings / 0 after
  patch).
- `bounty_report._steps` now writes session-aware steps for IDOR
  findings (cookie in the curl) and interaction notes for XSS/redirect.
- Version strings in pyproject.toml realigned (had drifted to 1.6.1).

## 2.4.0 — 2026-11-08 — "the range and the brief"

Two dreams, both kept legal and both shipped.

- **pentest.py, the practice range**: attack a server we OWN. VulnShop
  runs in-process with six classic holes (reflected XSS, path traversal,
  IDOR, unauthenticated admin, open redirect, verbose errors); the
  attacker pass is GET-only with marker strings and writes the owner's
  report - finding, PoC request, evidence, severity, suggested fix, the
  shape a formal submission takes. Then the patch, then the SAME
  corpus re-runs: nothing gets in. attack -> report -> patch -> re-attack
  -> CLEAN, sealed in the evidence chain. The line is drawn plainly:
  real third-party sites need written permission (authorized programs)
  or go to the owner / CERT-In / NCIIPC RvDP WITHOUT exploiting -
  unauthorized scanning is a crime and violates our own named-
  destinations law.
- **handoff.py, portability**: the record follows the person, not the
  account. `cerb handoff "the task"` prints ONE compact continuation
  brief - last mission, what the record knows, failure facts (always,
  regardless of query), chain verdict - sized for a paste, not a
  transcript. A new chat on a new account (or a new vendor) asks the
  record instead of re-reading history. `Cerberus action-schema` exports
  the gate as OpenAPI 3.1 (X-Cerberus-Token security scheme) for import
  as a ChatGPT Action: a real HTTP call from "another vendor" reads and
  writes the SAME record, witnessed in the WAL.
- **deletion stays the owner's power**: an AI delete of a realm file is
  repaired by the anti-god; the owner's own hand deletes for real, on
  the record.
- demo_webattack.py: 8 checks (all six holes found, criticals named,
  report with PoCs, re-test CLEAN, campaign sealed).
- demo_portable.py: 10 checks (50% state survives account A -> brief ->
  account B with zero history re-read; schema valid; real gate round-
  trip; witness in WAL; AI delete undone; owner delete lands).

## 2.3.0 — 2026-11-08 — "the owner's clock"

Level-4 autonomy, built as the answer to a fair challenge: "aren't we
adding too much to the god?" - the clock adds NOTHING to the god. It
names goals at times the owner wrote down; every step still passes the
conscience. The moat stays judgment + proof + any brain on top.

- **missions**: `cerb missions add NAME --goal "..." --kind
  daily --at "06:00"` (or `--kind every --every 30` / `--kind once --at
  "YYYY-MM-DD HH:MM"`), then `missions run` (one tick - put it in cron)
  or `missions watch` (a clock for machines without cron). list /
  pause / resume / remove. Fires are step-budgeted per mission, fire
  counts and verdicts live in missions.json, every run journals to
  base/autopilot/ like any autopilot run. Brain per mission: ollama by
  default, or the Claude bridge via --url.
- **the wall to L5 is physical**: only the owner edits missions.json
  (the runner's plain hand, like cron itself); a write to it THROUGH
  the god is undone by the anti-god (identity-name protection, on the
  record); autopilot.stop beats every mission; a resumed mission never
  fires in the past; `--every` below 5 minutes is refused (a faster
  clock is a storm, not a schedule); a missions.lock keeps one runner
  from double-firing (stale locks expire after an hour).
- **failure is honest**: a dead brain or a missed goal lands as NOT
  DONE with the reason on the record, the fire is counted, and the
  next fire still moves on - the clock never spins and never lies.
- **fixed**: `init --base PATH` crashed (string never became a Path) -
  caught by the new CLI smoke test, which drives init -> license ->
  missions add/run/list exactly as the owner would.
- demo_missions.py: the 19-check clock trial (arming rules, tick fires,
  sleep-when-not-due, stop-file, anti-god undo of clock writes,
  pause/resume/remove, honest failure, single-runner lock).
- regression: demo_claude 14/14, demo_autopilot 10/10, demo_tenancy
  24/24, selftest THE STACK HELD.

## 2.2.0 — 2026-11-08 — "Claude, automated"

The question: *can my Claude be automated?* The answer, built and
proven at ₹0: three ways, one honest boundary.

- **Claude as the brain**: `Cerberus/anthropic_bridge.py` - a local
  translator that speaks OpenAI to the autopilot and Anthropic to
  Claude (system → top-level field, /v1/messages, x-api-key +
  anthropic-version at the moment of use, key never stored). CLI:
  `Cerberus autopilot "GOAL" --brain claude` (spawns an in-process
  bridge, falls back to claude-haiku-4-5) and `Cerberus claude --port
  8756` (a long-lived bridge). Honest refusal without a key; honest
  http-code on brain failure; ANTHROPIC_BASE_URL is movable for tests.
- **Claude as the commander**: MCP gains `autopilot_run` (ONE goal in,
  whole mission hands-free, run report back into the chat, steps
  capped 1-30, agent=claude-mcp) and `autopilot_stop` (the owner's
  stop hand over any mission).
- **the boundary, stated**: the claude.ai website cannot be scripted
  for free - that is Anthropic's product. The worker runs unattended
  (ollama + cron, ₹0), Claude Desktop supervises in chat (MCP), Claude
  API thinks behind the bridge (tokens only).
- demo_claude.py: the 14-check Claude automation trial - translator
  unit rules, the full loop through an Anthropic-shaped API (wire
  rules verified: key, version, system placement, no system role),
  MCP launch + stop, stop-file halts before any brain call.
- regression: demo_autopilot 10/10, selftest verdict THE STACK HELD.
- docs: AUTOMATE.md - the three ways, exact commands, cron/Task
  Scheduler lines, the boundary.

## 2.1.0 — 2026-11-08 — "autopilot"

Level-3 autonomy: the god acts on its own, per step judged.

- **the loop**: `Cerberus autopilot "GOAL" --max-steps N` - brain
  (any OpenAI-compatible endpoint, ollama is free) proposes a step,
  the conscience judges it (intend() - memory before motion), the
  result feeds back, repeat until done / budget spent / brain
  unreachable. No human between steps.
- **scope by the owner**: default verbs = file verbs + seal;
  `--heavy` adds http_post/git_push/browse - the conscience still
  judges each one. Out-of-scope verbs come back as errors the brain
  must adapt to, never bypass.
- **the wall holds mid-mission**: a scripted-brain exfil attempt
  (http_post to an attacker URL) was REDIRECTED to the vault in-step
  (bytes on wire: 0), the loop recorded it, the brain adapted, the
  goal finished - the redirect is on the record.
- **the owner's hand**: base/autopilot.stop halts the loop between
  steps before any brain call; secrets are redacted (rules.redact)
  from everything the loop writes down.
- **journal**: every run writes base/autopilot/run-<stamp>.json;
  memory chain verified at run end (memory_ok in the report).
- regression: selftest 32/32, redteam 42/42 unchanged.
- demo_autopilot.py: the 10-check trial (happy path, adaptation,
  redirect-under-load, owner stop).

## 2.0.0 — 2026-11-08 — "the commercial core"

The gap list from the verdict, built with a ₹0 budget: the parts of a
product that are code and documents, not money.

- **multi-tenant walls**: one process serves many customers; each
  tenant is a whole Cerberus (own realm, memory, incidents, law) inside
  `base/tenants/<name>/`; a path may not cross a wall
  (`tenancy.inside_tenant`), tenant names are traversal-proof
- **org-grade keys**: `gmk_` API keys, scrypt-hashed (n=2^14), plaintext
  shown once and stored nowhere, revocable, role ladder reused from
  enterprise.py; the gate routes tenant keys to tenant gods
  (`server.py _tenant_ctx/_god_for/_admit`), rate-limited per tenant
- **GDPR as code**: `gdpr export` (portability bundle, sha256-stamped),
  `gdpr erase` (bytes overwritten, tombstone kept - the record never
  lies), `gdpr retention` (age purge + purge log), `gdpr report`
  (records of processing)
- **SOC 2 readiness matrix**: `cerb controls` generates the matrix
  from the REAL controls, every row naming the command that measures it;
  honest by doctrine - readiness evidence, not certification
- **demo_tenancy.py: the 24-check commercial trial** - two tenants, one
  process, live HTTP: mint/auth/revoke, walls hold, traversal refused,
  429 on limit, cross-tenant isolation, GDPR round-trip, retention purge
- regression: selftest 32/32, redteam 42/42 unchanged
- docs: PRICING.md, TRUST.md, SLA.md, PITCH.md, ZERO-BUDGET.md

## 1.6.2.1 — 2026-11-08 — "the empty-recall fix"

Caught live in the owner's re-run: a gateway write reported
`wrote notes/acme-november-migration.md (322 bytes)` while recall showed
`wrote notes/acme-november-migration.md ::` with nothing after the
separator - and a fresh session concluded the note had no content and
refused to draft the client email from it. (The refusal itself was the
conscience working correctly; the memory under it was hollow.)

- **root cause**: `god.intend()` learned `"wrote <target> :: " +
  _summarize(result)` after every write - but `_summarize` reads
  `result["output"]`, and write/append/edit results carry their
  confirmation only in `"note"`. Reads set `output`, which is why
  facts learned from reads always had bodies and facts learned from
  writes never did.
- **the fix**: a successful write/append/edit now learns the text that
  actually landed on disk (`_data(imp)`, first 400 chars). `_summarize`
  falls back to `"note"` (also repairs web-learned facts).
- **the read heals**: `recall()` and `digest()`/`session_open()` fill
  bodyless `wrote <path> ::` entries from the realm file itself at read
  time. Nothing in the ledger is rewritten, existing stores heal without
  a re-seed, and a path outside the realm is never followed.
- **selftest 32/32** (was 30): 31 = the write round-trip (recall answers
  from the body), 32 = the read-heal + realm containment.
- redteam 42/42 unchanged.

## 1.6.2 — 2026-11-08 — "the memory speaks first"

Built directly from the blind A/B verdict (Arm B won T5, tied T2/T4, and
lost T3/T7 only because the connected AI never went looking for what the
gateway had written). All code original, from the owner's own design.

- **proactive memory reads (the T3/T7 fix)**: the MCP `initialize` result
  now carries server INSTRUCTIONS that Claude Desktop surfaces to the
  model: open the session, read the memory before answering, scan drafts,
  seal milestones. Five new MCP tools: `session_open` (digest + the
  session itself enters the chain), `recall` (newest-first, query-filtered
  read of the shared memory), `scan_draft`, `seal`, `evidence`. Writes
  through the gateway now LEARN into the memory ("wrote X :: summary"),
  so recall can always find what the gateway put on disk - in the A/B the
  memory and the files diverged; never again.
- **draft scanning**: `Cerberus/drafts.py` - the conscience reads the
  letter before it leaves the house. Flags (1) secret-shaped material,
  redacted in the findings so the scan result never becomes the leak,
  (2) victory claims that contradict the memory's failure facts - the T5
  check moved upstream, before the send, (3) duplicate drafts (the
  anti-god eliminates duplicates). Verb `scan_draft` - observation class,
  every scan lands in the chain. Secret regex hardened: "the password IS
  hunter2-demo" no longer slips past on the word "is".
- **signed evidence chain**: `Cerberus/evidence.py` - `seal` signs the
  chain head (HMAC-SHA256, the owner's key) at a moment in time, files it
  in evidence/, and the seal event itself enters the WAL (the chain
  swallows its own proof). `verify_seals` re-signs every seal and checks
  signature + anchor + seal-event; tamper with one line and both the
  chain AND every later seal turn red. `evidence` exports a portable
  signed bundle (chain + notes + seals + WAL tail + stats). CLI:
  `cerb seal | seals | evidence`; gate routes GET /evidence, POST
  /seal; MCP tools `seal` and `evidence`.
- **the anti-god does its true job (the owner's definition)**: it was
  never about restricting access - it eliminates DUPLICATES AND CLONES
  and protects the data. Duplicate facts are collapsed into the original
  (normalized: case, spacing, punctuation, leet and homoglyph costumes
  all fail; `duplicates_collapsed`), clone-writes (same content, second
  path) are ALLOWED - full access - but named and recorded, the first
  path stays authoritative (`clone_writes`). One memory, one truth.
- **selftest 30/30** (was 26): 27 = the memory speaks first, 28 = the
  draft scanner (secret redacted, T5 lie caught before the send,
  duplicates eliminated), 29 = the signed evidence chain (one deleted
  line breaks the chain AND the seal; restore and all is INTACT), 30 =
  duplicates collapsed + clones named with access untouched.
- redteam 42/42 unchanged.

## 1.6.1 — 2026-11-07 — "the long key"

- **begin** (`cerb begin CB-... "Name" --expires DATE`): ONE command from
  key to licensed, running mind - init + activation in a single step; wrong
  keys are refused before anything starts. `license issue` now prints this
  one-liner as the thing to send the customer.
- **one-click**: `plugin/build_plugin.py --customer X --key CB-... --expires D`
  bakes the key into a double-clickable `RUN-ME.command` (macOS): the customer
  unzips and double-clicks - engine installed (bytecode only), mind created,
  license active, gate awake. Zero typing.
- **builder hardening**: key and expiry are validated at build time (CB-XXXX
  format, YYYY-MM-DD), so malformed values can never be baked into a bundle.
- **macOS-safe 10x trial**: the attacker sink now binds 127.0.0.1 and is
  reached at `2130706433` (integer loopback, external to the law) - fixes
  errno 49 (EADDRNOTAVAIL) on macOS, same trial semantics on every OS.
- **selftest 26/26**: check 26 = one long key -> mind home + licensed gate in
  seconds; wrong key refused.
- proven in a clean venv: RUN-ME.command -> installed, licensed to yashas_1
  until 2026-11-14, gate awake on 127.0.0.1:7717.

## 1.6.0 — 2026-11-07 — "the plugin"

- **license** (`Cerberus/license.py`, `cerb license ...`): customers buy the
  plugin, never the repo. 14-day trial on first run; the gate, dashboard, MCP
  and ollama bridge refuse to start after expiry while `verify` / `incidents` /
  `export` keep working (evidence is never hostage). Founder-only `issue`
  mints CB- keys signed by `~/.cerberus.master` (never ships), bound to
  customer name + expiry; activation validates format + expiry, and verifies
  signatures outright where the master lives.
- **plugin bundle** (`scripts/build_plugin.py`): per-customer watermarked zip
  (X-Cerberus-Customer in the wheel METADATA) containing the wheel + SKILL.md +
  CONNECT.md + Claude/Cursor MCP configs + install.sh + EULA. install.sh
  compiles the engine to bytecode and deletes the readable source from the
  customer machine.
- **bytecode-safe `/code`**: `decision_source()` degrades gracefully on
  source-free installs instead of crashing.
- **selftest 25/25**: check 25 = trial starts alone, founder issues keys,
  forged keys rejected where the master lives, activation locks the gate.
- proven end-to-end in a clean venv: install.sh -> 0 readable .py files ->
  selftest 25/25 from bytecode -> trial -> issue/activate/reject.

## 1.3.0 — 2026-11-05 — "close every gap we can close alone"

- **chaos** (`cerb chaos`): adversarial fuzz (zero-width, homoglyphs, leet,
  spacing, url-encoding, traversal, binary junk, malformed URLs), a concurrency
  storm (N threads x M impulses through one god), simulated torn-write crash
  with mirror recovery, and weird-input phase. Nothing may crash; the chain
  must hold.
- **Thread safety**: one lock guards the WAL append, lockdown state, notes and
  incident book. The 8-thread storm leaves the chain INTACT.
- **Crash semantics**: a torn write is *detected* (CORRUPT_LINE) and the mirror
  restores the record (INTACT). verify() hardened against undecodable bytes.
- **enterprise**: token roles (owner > operator > auditor > agent) enforced at
  the gate; alert stream (alerts.jsonl + Slack-compatible webhook, never
  blocks the conscience); compliance export (CSV/JSON).
- **attackme** (`cerb attackme`): self-serve red team. File mode (attack
  corpus -> verdicts file) and live isolated target mode with a session
  report. Anyone on earth can attack it in one command.
- **Packaging**: pyproject.toml (pip-installable, `Cerberus` console script),
  LICENSE (MIT), CHANGELOG, INTEGRATIONS.md, ATTACK-US.md.
- Selftest extended 17 -> 20 checks (concurrency storm, crash+recovery,
  roles/alerts/export).

## 1.2.0 — 2026-11-05 — "a face, and the trial"

- Interactive dashboard (fire impulses, run plans, run THE 10X TRIAL from the
  browser), mounted at `/dash` and standalone on port 7750.
- **THE 10X TRIAL** (`Cerberus benchmark`): bare god vs god+anti-god, ten axes,
  every harm number a physical measurement. Bare 100/1000, guarded 1000/1000.
- Blind-overwrite protection: you may not overwrite a realm file you never
  read through this mind.
- 302-redirect exfiltration lane closed.
- Selftest 10 -> 17 checks.

## 1.1.0 — 2026-11-04 — "smarter rules, one being"

- Layered detection: unicode normalization (homoglyphs, zero-width, leet,
  spaced-out letters) before matching; layered scoring for victory claims
  vs acknowledged failure.
- Per-agent lockdown after repeated blinding attempts; only the human clears it.
- Agent identities in the incident book; field-trial kit (`cerb field`).
- Selftest 10 checks.

## 1.0.0 — 2026-11-04 — "the four laws"

- Write-ahead conscience (HMAC-chained WAL, INTENDED before DONE).
- Classification of every impulse (10 classes, priority order).
- Next-step gate: refuse / redirect / rewrite / allow_watched.
- Pre-stage repair: snapshot before heavy steps, byte-identical restore,
  god's version kept as evidence, tombstones for deletions.
- The god is never killed; one memory for both wills.

## 1.4.0 — 2026-11-05 — "the god walks the open web"

- New verb `browse`: a real Chromium (Playwright) under the write-ahead
  conscience. Steps: goto / click / press / type / fill / wait / read / shot.
  Transcripts in the result, screenshots in evidence/.
- New classification class `web` (risk 2, like shell). Browse impulses are
  witnessed before the browser opens and recorded as incidents.
- Exfiltration rules extended: typing secret-shaped material into a website
  (password=, sk-, AKIA, ghp_, xox, bearer, private keys) or credentials in
  the URL → redirect to the vault, wire silent.
- One memory for both wills now covers the web: pages the god reads are
  learned into the shared memory; later victory reports that ignore web
  errors are rewritten with the true record.
- Dashboard: browse in the impulse console, one-click "load web demo
  (onecompiler hello)" plan preset, step outputs rendered in the plan table.
- CLI: `python3 -m cerberus_gate browse --demo | <url> | --steps steps.json`.
  init now also writes plan.web.example.json.
- Selftest: 22 checks (was 20). Playwright is an optional dependency —
  without it the browser check skips with an install hint.


