RESTORE-ON-MAC — cerberus-gate v3.0.0b4 "the honest check"
==========================================================

Your Mac was wiped. This zip IS the project: the complete, fixed,
re-verified v3.0.0b4 (package, build config, license, changelog,
release notes, the built wheel, and the proof transcripts). Everything
below was run against THIS wheel in a clean environment before the zip
was made:

  selftest   40/40  ("CERBERUS WORKS ON THIS MACHINE.")
  verify     17/17  honest check, law status, perf, tamper evidence
  e2e        cold stdio MCP: law_status INTACT (latency_ms 0.4),
             egress_check -> VETO L1_UNNAMED_HOST
  attackme   5 attacks -> 2 redirected + 3 refused, memory INTACT
  perf       20k-entry mind boots in 0.19 s; WAL append O(1) (0.04 ms)
  b3 baseline (recorded the same day): 45 MB mind booted 9.97 s per
             client, one _append 0.09 s, watchdog 1.0 s every 20 s

WHAT IS IN THE ZIP
------------------
  cerberus_gate/                          the full package, b4 fixes
  pyproject.toml                          build config (3.0.0b4)
  cerberus_gate-3.0.0b4-py3-none-any.whl  THE BUILT, VERIFIED WHEEL
  README.md                               vault rules + release rules
  LICENSE                                 the proprietary CERBERUS LICENSE
                                          TERMS - the same text the public
                                          repo ships, and now the wheel
                                          bundles it too. GOVERNING LAW is
                                          still the author's placeholder:
                                          set the jurisdiction before
                                          charging money.
  CHANGELOG.md                            full history + the b4 entry
  RELEASE-NOTES-v3.0.0b4.md               the exact notes file your gh
                                          command wants
  law.example.json                        the law template
  .gitignore                              the vault rules as ignore rules
  proof/                                  selftest, verify, e2e cold MCP,
                                          attackme (+ verdicts), ledger
                                          concurrency
  tools/                                  verify_b4.py, e2e_cold.py,
                                          attackme-b4.jsonl - rerun the
                                          whole proof yourself
  RESTORE-ON-MAC.md                       this file
  VERIFICATION.txt                        the proof numbers

STEP 1 - create the release (your original command, two fixes)
--------------------------------------------------------------
Unzip somewhere, open Terminal IN the unzipped folder, then:

  gh release create v3.0.0b4 cerberus_gate-3.0.0b4-py3-none-any.whl \
    --repo Yashas-K-Gangatkar/cerberus-gate \
    --title "3.0.0b4 - the honest check" \
    --notes-file RELEASE-NOTES-v3.0.0b4.md

(Your original command failed twice: the wheel was not in the folder
you ran it from - and even with the file present, gh needs --repo
because your home folder is not a git checkout. Both handled above.)

STEP 2 - verify the release the way a customer would
----------------------------------------------------
  pip install https://github.com/Yashas-K-Gangatkar/cerberus-gate/releases/download/v3.0.0b4/cerberus_gate-3.0.0b4-py3-none-any.whl
  python3 -m cerberus_gate selftest          # expect 40/40
  python3 -m cerberus_gate attackme          # red team, optional
  python3 -m cerberus_gate mcp-config gemini # the one block for all 20 clients

STEP 3 - sync this source back to the private vault
---------------------------------------------------
The build sandbox held no GitHub credentials, so the vault was NOT
pushed from there - do it from your Mac (vault rule 1: check git
status before every commit):

  gh repo clone Yashas-K-Gangatkar/cerberus-gate-source vault
  cd vault
  cp -R ../<unzipped-folder>/cerberus_gate .
  cp ../<unzipped-folder>/{pyproject.toml,README.md,LICENSE,CHANGELOG.md,RELEASE-NOTES-v3.0.0b4.md,.gitignore,law.example.json} .
  git add -A
  git status
  git commit -m "3.0.0b4 - the honest check (selftest 40/40, verify 17/17)"
  git push

STEP 4 - reconnect the 20 AI clients
------------------------------------
Unchanged from b3: generate once, paste everywhere.

  python3 -m cerberus_gate mcp-config gemini

The printed mcpServers block is identical for every client - paste the
same block into claude / cursor / windsurf / vscode / cline / continue /
gemini / the rest. Idempotent, no per-client rerun needed.

THE THREE BUGS THIS BUILD FIXES (one line each)
-----------------------------------------------
1. egress_check said ALLOW for packets egress_send would seal+strike
   (owner-unnamed host, or shield ABSENT) -> b4: the check IS the
   send, minus the wire, fail-closed.
2. law_status lied by omission from a cold process ("ABSENT" with a
   full chain on disk) and timed out on grown minds (O(n) WAL writes,
   O(n) boots, a loud watchdog) -> b4: armed on demand, guarded parts,
   latency_ms on the record, tail reads, string boot scan, quiet
   watch. Measured: 20k entries boot 0.19 s, append 0.04 ms.
3. the wheel bundled MIT text while its metadata said proprietary ->
   b4 bundles the real CERBERUS LICENSE TERMS.
