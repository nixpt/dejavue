# Dejavue — Stewardship Policy

**Version:** 1.0  
**Registered:** 2026-06-03  
**Foundry:** OpenKO (did:openko:federation:seed)

---

## Primary Steward

`did:openko:human:nixpt` — project creator and primary maintainer.

---

## Succession

If the primary steward becomes inactive for **3 or more years**, or upon death (verified by federation attestation), or upon explicit transfer declaration, stewardship transitions in this order:

1. **OpenKO Technical Council** (`did:openko:cell:technical-council`) — first preference; the council has visibility into the broader ecosystem and can ensure continuity with OpenKO protocol evolution
2. **OpenKO Tools Community** (`did:openko:cell:openko-tools`) — community of contributors who have worked on dejavue or adjacent agent tooling
3. **Public Commons** — automatic transition to public commons under OCPL-1.0 if neither of the above accepts within 90 days

The transition is executed via a signed stewardship transfer recorded in the OpenKO governance audit log and gossiped to the federation.

---

## Preservation Invariants

These survive all stewardship transitions — no steward, successor, or governance vote may override them:

- **Attribution is permanent.** The creator lineage (`did:openko:human:nixpt`) remains attached to all dejavue artifacts, derivatives, and dependent works. Attribution CU routing persists indefinitely.
- **Fork rights are guaranteed.** Any successor, any community member, any third party may fork dejavue at any time. No successor may impose restrictions that prevent forking.
- **Format openness is guaranteed.** The `.dejavue/` on-disk format (timeline.jsonl + markdown docs + fts.db) must remain publicly documented and readable without the dejavue CLI. No successor may introduce format encryption, obfuscation, or proprietary extensions that break interoperability.
- **The CLI must remain free.** The local command-line tool must always be available at no cost (CU or otherwise). Monetization applies only to hosted services and capsule deployments, never to the local CLI.

---

## What Stewardship Includes

The steward is responsible for:
- Maintaining the dejavue CLI and format specification
- Reviewing and merging community contributions
- Managing the `pool:dejavue` treasury (with OpenKO governance oversight)
- Publishing releases and maintaining the changelog
- Responding to security issues within 72 hours of report
- Upholding the preservation invariants above

---

## What Stewardship Does Not Include

- The right to change the license away from OCPL-1.0 without federation supermajority vote
- The right to restrict fork rights or format access
- The right to claim creator attribution on behalf of the steward (nixpt's lineage is permanent)
- The right to remove the CLI free-tier

---

## Community Fork Rights

If any steward violates the preservation invariants, any community member may:
1. File a governance dispute with the OpenKO technical council
2. Fork the project (fork rights are guaranteed)
3. Register the fork as a new Foundry project under its own DID

The fork carries forward the creator attribution lineage (nixpt) but operates independently under its own steward and treasury.

---

## Foundry Registration

This stewardship policy is registered at `foundry.toml` in this repository and recorded in the OpenKO Foundry registry at `did:openko:federation:seed`.
