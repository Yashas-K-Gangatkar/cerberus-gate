"""CERBERUS SHIELD — the outbound blast-shield, three layers deep.

v2.8.0: THE BLAST-SHIELD — the missing half of cybersecurity.
    The whole industry guards the machine from the AI and the AI from
    hackers. Almost nobody guards the OPEN INTERNET from the AI.
    Three layers, in order:
    L1 the internet shield  — the egress gate: rate law, burst throttle,
       concurrency governor, circuit breaker that heals, exploit
       interception after normalization, and a signature that is REAL
       (HMAC, owner-keyed, replay-protected — not a naked checksum).
    L2 the local guardian   — the machine's law: protected paths,
       integrity baselines, every event on a tamper-evident ledger.
    L3 the leak-proof vault — data that survives its own leak: secrets
       redacted before egress, vault sealed AES-GCM, canary tokens that
       trace a leak back to the exact request that carried it.
    The promise is not "nothing ever leaks". The promise is: what leaks
    is redacted, sealed, and traced.
"""
from .common import Decision, OwnerKey, Verdict
from .ledger import Ledger
from .shield import InternetShield
from .local_guardian import LocalGuardian
from .vault import LeakProofVault, VaultSealed
from .gateway import guarded_request

__version__ = "2.8.0"
