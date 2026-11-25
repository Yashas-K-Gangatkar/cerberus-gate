# cerberus-gate 3.0.0b4 — "the honest check"

The one-command install:

```
pip install https://github.com/Yashas-K-Gangatkar/cerberus-gate/releases/latest/download/cerberus_gate-3.0.0b4-py3-none-any.whl
```

**The law of this release: the check is the send, minus the wire.**

b3 had a lie at its heart, and a timeout around its neck.

## 1. egress_check told the truth the send would not allow (the false ALLOW)

b3's `egress_check` ran only the shield's five laws (rate, burst,
exploit, SSRF, redaction) and never read the OWNER's law. A packet to
a destination the owner never NAMED came back ALLOW — or a SUSPECT
hold that implied the owner could wave it through — while the SAME
packet through `egress_send` was sealed in the vault, the wire stayed
silent, and the agent took a strike. A connected AI that does what the
tools tell it ("run this before egress_send whenever you are unsure")
trusted the check and leaked. A check that describes a different world
than the send is a lie the AI acts on.

b4: every branch of `egress_check` MIRRORS the send's decision tree,
in the same order, fail-closed:

- unnamed host + data → `VETO L1_UNNAMED_HOST` (b3 said ALLOW) with the
  `would` block: `{"stopped": true, "sealed": true, "strike": true}`
- local addresses (127.0.0.1, localhost, ::1) → `VETO L1_LOCAL`
- SSRF / exploit payloads → the same refusal codes the send path gives
- shield ABSENT → `VETO SHIELD_ABSENT` (b3 passed a bare ABSENT the
  client could read as "fine"; the send refuses, so the check refuses)
- brain VETO/SUSPECT → stated in send terms: "egress_send would SEAL
  this packet and count a strike" / "egress_send would HOLD this
  packet for the owner's verdict"
- ALLOW only for a packet the gate would actually dispatch
- a check still costs nothing: no strike, no wal entry, no vault file

## 2. the law_status timeout chain — cut at all three links

On a real, grown mind (twenty MCP clients writing one shared record),
b3 made every tool call slower every day, until the client gave up on
`law_status` — the session-start call:

- **O(n) WAL writes**: every `_append` re-read the WHOLE conscience.wal
  to find the last hash. The chain only ever needs the LAST line:
  one bounded tail read now (b3: 0.09 s per write at 45 MB; b4: O(1)).
- **O(n) boots**: `Mind.__init__` called `Path.resolve()` twice per
  history line — 10 s of boot per MCP client on a 45 MB mind, twenty
  clients at once. History is now resolved by string (it was written
  by the same resolver), with the exact resolver as fallback.
  Measured: 45 MB mind, cold boot 9.97 s → 0.99 s.
- **the loud watchdog**: every 20 s, forever, in the same process that
  serves MCP: re-verify the ENTIRE record + copy the ENTIRE wal to the
  mirror. The quiet watch: a (size, mtime) stamp skips the pass when
  nothing moved; anything that changes gets the full pass. The shield
  ledger gets the same cure: tail read under the same exclusive lock,
  full resync only when another writer moved the file.

Also: the WAL sequence now starts from the record ON DISK, not from
zero per client — twenty clients booting at seq=0 wrote colliding n's.

## 3. the cold law_status lie — armed on demand, latency on the record

Reproduced on b3: a process that had never sent egress answered
`shield_ledger: ABSENT` while the realm's `shield-ledger.jsonl` sat on
disk with a full chain — the law status lied by omission, to the owner
and to any AI asking on their behalf. b4:

- `blast_shield.verdict` arms the shield on demand first; ABSENT now
  means exactly one thing: no shield can stand on this machine.
- every `law_status` part is guarded fail-visible — one failing part
  can never blank the whole answer.
- the tool reports its own `latency_ms` — the timeout fix you can SEE.
  Measured on a cold stdio session: 0.4 ms.

## 4. the license file inside the wheel

b3's metadata said `LicenseRef-Proprietary` while the bundled LICENSE
was still MIT text. b4's wheel carries the proprietary CERBERUS
LICENSE TERMS themselves — metadata and license finally agree.
(GOVERNING LAW is still the author's placeholder: set the jurisdiction
before charging money.)

## Verification

- Selftest 40/40 (38 inherited + 2 new):
  - check 39 THE HONEST CHECK: unnamed host vetoed, local refused,
    ssrf refused, named+clean allowed, absent shield refused, a check
    strikes nothing and writes nothing, and the send agrees with the
    check it mirrors
  - check 40 THE QUIET RECORD: 1200 chained writes intact, WAL seq
    from disk, two client views one chain, history stays touched after
    a boot, watchdog skips unchanged records and audits on change, two
    ledger writers one chain
- attackme: 5 attacks (SSRF, exfil, record forgery, law edit, clone)
  → 2 redirected + 3 refused, memory INTACT, god alive, zero crashes
- cold stdio MCP session (the exact path Gemini/Claude drive):
  law_status answers INTACT with the real ledger head, the named
  destinations and its own latency_ms (0.4 ms measured); egress_check
  on an unnamed destination answers VETO L1_UNNAMED_HOST
- measured on a 20k-entry grown mind: cold boot 0.19 s (b3 recorded:
  9.97 s at 45 MB), one _append 0.040 ms (O(1)); a flipped hash in the
  shield ledger is caught ("TAMPERED at entry 1"); a restored ledger
  verifies INTACT; four concurrent ledger writers share one chain
  (8/8 seqs, INTACT)
- mcp-config regenerated per client unchanged (same one-block reuse
  for all 20 clients)

Generic build: no watermark, no baked key — runs free for 14 days per
machine, then activate with your personal key.
