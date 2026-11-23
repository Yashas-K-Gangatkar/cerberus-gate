# Security Policy

## Reporting a vulnerability

Contact the founder privately: open a GitHub **security advisory** on
this repository (Security tab -> Report a vulnerability), or use the
support channel you received with your license.

Please include:

- what you did and what happened
- the output of `python -m cerberus_gate seals`
- your operating system and `python --version`

Please do **not** open a public issue for security problems.

## What this product is

All judging, memory and evidence stay on your machine. The gate listens
on 127.0.0.1 only. Nothing leaves the machine by design.

## In scope

- ledger tamper-evidence and forgery detection
- license bypass or key forgery
- dashboard exposure beyond localhost
- MCP transport issues

## Out of scope

- attacks that require local admin on the target machine (they own the
  machine already)

## Safe harbor

Good-faith security research is welcome and will not be pursued legally.
Coordinated disclosure window: 90 days.
