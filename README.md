# CERBERUS - the conscience for your AI

**One install. Every AI. One shared memory.**

Cerberus sits between your AI agents and the real world: every impulse is
written to a tamper-evident local ledger and judged **before** it happens -
refused, redirected into a vault, rewritten with the truth, or allowed
watched. Everything stays on your machine. Switch AI tools (Gemini CLI,
Cursor, Claude Desktop, Cline, Windsurf...) and the new one reads the same
local memory - no re-explaining, no double-paying for context.

## Install - one command

Prerequisite: Python installed once (Windows: python.org installer, tick
**Add python.exe to PATH**; Mac: python.org installer).

Then paste this single command into a terminal:

```
pip install https://github.com/Yashas-K-Gangatkar/cerberus-gate/releases/latest/download/cerberus_gate-3.0.0b3-py3-none-any.whl
```

That is the whole install. Nothing else to click. No account. No web page.

## Use - just talk to your AI

Open your AI the way you always do and talk normally. Cerberus starts with
it and judges every impulse in the background.

You never configure anything and you never open a dashboard. When your AI
wants to do something risky, the conscience answers it - **REFUSED**,
**REDIRECTED**, **REWRITTEN**, or **ALLOWED_WATCHED** - and the verdict is
written to the ledger on your disk.

## Trial and license

No key? It runs **free for 14 days** per machine. Bought a license? Run
the activation line the founder sent you - it carries your personal key,
name and expiry. Keys are personal and non-transferable.

## If anything fails

Open [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - every error seen so far
in real installs, with a verified fix. Golden rule: screenshot the whole
window before asking for help.

## Where is the source code?

This repository ships **builds only**. The source lives in a private
repository. See [SECURITY.md](SECURITY.md) for reporting vulnerabilities
privately, and [LICENSE.md](LICENSE.md) for the terms.

## The 10x trial

The built-in benchmark measures physical harm (bytes on the wire, files
deleted, lies delivered) with and without the conscience: 0% harm on all
ten attack axes, honest work unblocked, price disclosed per impulse.
Run it yourself: `python -m cerberus_gate benchmark`
