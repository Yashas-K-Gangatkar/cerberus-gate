# RELEASE NOTES - cerberus-gate 3.0.0b4 "The Honest Check" (2026-11-24)

One-command install:

```
pip install https://github.com/Yashas-K-Gangatkar/cerberus-gate/releases/download/v3.0.0b4/cerberus_gate-3.0.0b4-py3-none-any.whl
```

## Why b4 exists

Two findings from the 2026-11-24 verification pass, both reproduced in a
clean environment, both fixed, both regression-tested:

**Finding 1 - egress_check could say ALLOW for a packet egress_send would
refuse.** A connected AI that did its duty (check first, then send) got a
green light for data aimed at a destination the owner never named - and
the same packet at `egress_send` was sealed in the vault, the wire stayed
silent, and the agent earned a strike. The check tool lied by omission:
the unnamed-host law existed only on the send path.

**Finding 2 - law_status could report a misleading ABSENT.** A fresh
process (every MCP client session is a fresh process) answered
`shield_ledger: ABSENT` even when the realm's `shield-ledger.jsonl` sat
on disk with a full, intact chain - because only the send path armed the
shield in-process. The tool that reports the law told the AI there was
no record when there was one.

## What changed

1. **The honest check** (`cerberus_gate/integrations.py`, `egress_check`):
   the unnamed-host law now runs at the check too, before the shield is
   consulted. Answers exactly what `egress_send` would do:
   - unnamed destination + data -> `VETO` / `UNNAMED_DESTINATION`, with a
     plain reason and a `send_would: {stopped, sealed, strike}` truth block;
   - loopback (127.0.0.1 / localhost / ::1) -> `LOCAL`;
   - named hosts -> unchanged: layer 1 shield, then layer 2 brain.
   Read-only by design: a check never writes the vault, never strikes,
   never counts stats - a look never punishes.
2. **The true law status** (`law_status` + `blast_shield.verdict`):
   `verdict()` arms the shield on demand, so a cold process reports the
   REAL ledger verdict (`INTACT` / `TAMPERED at entry N`) from the disk
   record. Every part of the answer is guarded fail-visible (one failing
   part can never blank the whole answer), and the answer carries its own
   `latency_ms` - slowness is now visible in the answer itself.
3. `egress_check` tool description updated to promise the new contract.
4. Selftest extended **38 -> 40**:
   - test 39: the honest check (unnamed vetoed, checks never punish,
     named still governed, loopback stays local);
   - test 40: the true law status (real verdict from a cold process,
     entries counted, named destinations listed, latency on record).

## Verification record (2026-11-24, clean sandbox)

- `python -m cerberus_gate selftest` -> **SELFTEST 40/40**,
  "CERBERUS WORKS ON THIS MACHINE."
- Cold-process end-to-end through the real stdio MCP server
  (`python -m cerberus_gate mcp`, exactly how an AI client drives it):
  - `law_status` from a cold process: `shield_ledger.verdict: INTACT`,
    entries counted, named destinations listed, **latency_ms 10.5**
    (wall 10.6 ms) - no timeout, no ABSENT;
  - `egress_check` unnamed destination with a benign body:
    `VETO / UNNAMED_DESTINATION` in **0.1 ms** (before b4: ALLOW);
  - controls unchanged: named host clean -> ALLOW; SSRF target ->
    VETO `L1_SSRF_BLOCKED`; encoded secret at a named host -> VETO at
    layer 2.
- Honest wording: b4 fixes the check/status layer and its verification.
  It does not re-run the earlier network-pilot scenario (law_status
  timeout on that machine was environmental); it makes law_status
  fast, truthful and self-reporting everywhere it runs.

## Build

Wheel: `cerberus_gate-3.0.0b4-py3-none-any.whl`
sha256: `0423ed0b89b5ed606a147a4e5f5e28486995834a6afd2cc5a9849653f8f021b3`

This repository ships builds only; the source lives in the private
repository (see SECURITY.md).
