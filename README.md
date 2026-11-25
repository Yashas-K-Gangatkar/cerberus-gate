# cerberus-gate-source - PRIVATE VAULT (founder only)

This repository holds the source of cerberus-gate. The public repo
(Yashas-K-Gangatkar/cerberus-gate) ships builds only.

## Vault rules (never break these)

1. NEVER commit: the master signing key, any `*.key` file, license
   ledgers, customer bundles (they carry baked keys), `RUN-ME.command` /
   `RUN-ME-WINDOWS.bat` / `INSTALL-WINDOWS.bat` (baked keys), `evidence/`,
   `.cerberus/`, benchmark jsons with machine info. The `.gitignore`
   here blocks the known ones - check `git status` before every commit
   anyway.
2. Builds run locally on the founder machine only. CI never receives
   secrets.
3. Public releases get a GENERIC trial wheel: no watermark, no baked
   key. Customer bundles are watermarked, baked, and delivered by hand
   (WhatsApp/email) - never through Releases.
4. If a secret ever lands in git history: rotate/revoke it FIRST, then
   clean history (git filter-repo). Rotation before cleanup, always.
5. The license-mint logic and the master key stay outside this repo and
   outside every build artifact.

## Release checklist

- [x] version bumped (pyproject.toml + cerberus_gate/__init__.py) - 3.0.0b4
- [ ] CHANGELOG.md updated
- [x] selftest passes locally (40/40)
- [x] generic trial wheel built (no watermark, no key)
- [ ] generic wheel uploaded to the public repo Releases + tag
- [ ] customer bundles built per order, delivered privately

## Current build state (Nov 2026)

- Engine: 3.0.0b4 "the honest check" - egress_check is the send minus
  the wire (unnamed host vetoed where b3 said ALLOW; shield ABSENT is
  a VETO, never a quiet pass-through); the law_status timeout chain is
  cut at all three links (O(1) WAL tail writes, string boot scan, quiet
  watchdog + tailing shield ledger); WAL seq starts from disk
- Selftest 40/40 (38 inherited + 2 new: the honest check, the quiet
  record)
- Next: dashboard first-run wizard, `cerb doctor` command
