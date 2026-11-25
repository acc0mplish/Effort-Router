---
name: effort-router
description: Use when starting any coding task in Devin. Classifies scope and risk as S/M/L/XL and picks model and effort per stage before planning, implementation, review, or audit.
triggers:
  - user
  - model
allowed-tools:
  - read
  - grep
  - glob
---

# effort-router (Devin draft)

Source: Effort-Router SKILL.md. Full tier and gate rules live upstream. This file is the Devin-facing subset. If they conflict, upstream wins.

## Step 1 — Tier
- S: single-file bug fix, text or style, no test logic change.
- M: feature add, refactor, branch logic change, 2-10 files, about 1000 lines or less, no risk triggers.
- L: large module, architecture change, risk triggers present (auth, request path, security control, shared core, design docs). Design or spec documents are always L or higher.
- XL: core engine, full-system refactor.
- If tier signals conflict, choose the higher tier.
- Emergency hotfix only when the user explicitly says so: implement first, review after.

## Step 2 — Stage and model (Devin)
Confirmed slug: `devin/swe-2` (effort suffix `:low|:high|:max`).
- Routine implementation (S/M): devin/swe-2, high. Writes code.
- Critical path or core (L/XL): devin/swe-2, max. Writes code.
- Planning: devin/swe-2, high. Read-only. Writes the plan only.
- Adversarial plan review: devin/swe-2, high. Read-only.
- Light review (S/M): devin/swe-2, low. Read-only.
- Deep review or security audit: devin/swe-2, high. Read-only.
Current harness routes every stage to `devin/swe-2:max` (OMP config.yml modelRoles) — flat routing is the fallback until per-role subagent profiles exist.
Do not use names outside Devin's list. Confirm with /model. Adaptive or Fusion overrides this table only if the user chose them.

## Step 3 — Evidence contract
- A completion claim needs the exact test or build command and its exit code, copied from output.
- The reviewer is a different stage from the implementer. Self-review does not count.
- Record a state file per task: tier, model per stage, claims, verified or not.

## Step 4 — Failure ledger
- When a failure is observed and reproduced, add one line to the guide file of the project where it happened (AGENTS.md). Trigger, required action, forbidden action. Do not add duplicates; sharpen the existing line.

## Step 5 — Output
- Report: tier with reason, model per stage, evidence, open risks.
- Plain text. No secrets, keys, or sensitive paths in task descriptions.
