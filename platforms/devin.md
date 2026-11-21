# effort-router — Devin / Devin Bots adapter (DRAFT)

Status: draft derived from Effort-Router SKILL.md §1 (tiers), §2 (roles), §3 (constraints), §5 (state contract). Rules conflict -> SKILL.md wins.
Verified from docs.devin.ai: Skills (SKILL.md, .devin/skills/ or ~/.config/devin/skills/), subagent profiles via `agent:`, per-skill `model:`, AGENTS.md / AGENTS.local.md / .devin/rules, Bot instructions + memory + modes.
NOT verified (confirm in the Devin app before relying on it): exact subagent profile file location and format, whether Cloud Bot sessions load repo Skills, whether Bot instructions accept a file or only pasted text, and whether the model short names below exist in your plan.

## 1. Where things go

| Devin surface | Install target | Content |
|---|---|---|
| Devin CLI, project | `.devin/skills/effort-router/SKILL.md` (committed) | Full SKILL.md body from upstream, frontmatter below |
| Devin CLI, global | `~/.config/devin/skills/effort-router/SKILL.md` | Same file, for all projects |
| Devin CLI rules | `AGENTS.md` (repo root) or `~/.config/devin/AGENTS.md` | 10-line pointer only, not the full skill (docs: keep rules small, reference skills) |
| Devin Bot | Bot General instructions | Bot block in section 4 (short) |

## 2. Skill frontmatter (replaces the Claude/Codex/Gemini frontmatter)

```yaml
---
name: effort-router
description: Use when starting any coding task in Devin. Classifies scope/risk as S/M/L/XL and picks model and effort per stage before planning, implementation, review, or audit.
triggers:
  - user
  - model
allowed-tools:
  - read
  - grep
  - glob
---
```

allowed-tools is only auto-approval, not a restriction (docs). Do not rely on it to make a reviewer read-only. Use a subagent profile with a tool list for that (section 3).

## 3. Role -> Devin mapping (proposal)

Devin's short model names from docs: opus, sonnet, swe, gpt, codex, gemini. Adaptive and Fusion are also available. Effort-Router's role model names (GPT-6-Luna, GPT-6.2-Sol, Gemini 4 Argon/Hydrogen/Carbon, Claude 5.5) are NOT Devin model names and must not be copied as-is.

| Effort-Router role | Stage | Proposed Devin model | Effort | Read-only |
|---|---|---|---|---|
| coder-medium, implement-med | routine implementation | swe | high (cycle with Alt+T) | no |
| implement-xhigh, core-xhigh | critical path / core | opus or gpt | max | no |
| plan-high, plan-xhigh | planning | opus | high | yes (planning writes docs only) |
| plan-adversary-xhigh | adversarial plan review | gpt or codex | high | yes |
| review-pr-high | S/M light review | swe | low | yes |
| review-pr-xhigh, security-audit | deep review / security | opus | high | yes |
| ops-supervisor | monitoring | sonnet | high | no |

Setting model per stage: use `model:` on a skill, or `agent:` pointing at a subagent profile whose model is set. Profile model is inherited unless the skill sets `model:` (docs). Effort is not in the skill frontmatter; set it with Alt+T or the mode picker and record it in state.json.

Bot note: a Bot's Child Capability sets the mode for child sessions. It starts on the org default and only people who can configure the Bot can change it. Set it once to the matching stage mode and ask the Bot to use a different mode per session where needed.

## 4. Bot instruction block (paste into the Bot General page)

Keep this short. Long instructions dilute the agent (docs).

```
Before any coding work, apply the effort-router skill (name: effort-router).
1. Classify the task S, M, L, or XL from the user's words (not from file count alone). Risk triggers (auth, request path, security control, shared core, design docs) raise the tier one level, and design docs are always L or higher.
2. Use the stage model table in the skill. Planning and review sessions are read-only. Implementation sessions write code.
3. Report the tier and the model used at the start of each child session.
4. Never claim done without the test command output and its exit code.
5. Record a failure as one rule line in the guide file of the project it happened in.
```

## 5. AGENTS.md pointer (repo root)

```
# Devin rules
- For coding tasks, follow .devin/skills/effort-router/SKILL.md (tier, model per stage, evidence contract).
- Planning and review stages do not edit code. Implementation stages do not approve their own work.
- Do not put secrets, API keys, or sensitive paths in task descriptions or Bot instructions.
```

## 6. Required changes to upstream Effort-Router (to make it native)

1. Add `platforms/devin.md` (this draft, after confirming the open items above).
2. Add `platforms/devin-agents/*.md`: one subagent profile per role, with allowed tools and model. Format to be confirmed from the Devin subagents doc (docs.devin.ai/cli/subagents.md, not yet read).
3. Add a Devin row to the platform table in platforms/README.md and to the case table in SKILL.md §6. The case numbering and the 13-combo rule in test_model_combos.py must add Devin combos, or the test will reject them.
4. scripts/: verify_global_install.py and deploy_global.py assume ~/.codex or ~/.gemini paths. Add a Devin install verifier. Do not reuse the Codex one.
5. jev and Stagehand gates call an external API (TYPESAFE_API_KEY, api.typesafe.ai) and an LLM. Devin cloud sessions should use the secrets store, not a plain env file. Keep both gates off by default on Devin.
6. Tier and stage logic (SKILL.md §1, §5) is harness-neutral and needs no change.

## 7. Open questions for you

1. Which Devin plan and model list do you have? Confirm swe/opus/gpt/codex names in `/model`.
2. Do you want Adaptive or Fusion instead of fixed per-stage models? Adaptive would override the role table.
3. Should the Bot run the whole pipeline, or only the planning and review stages while coding stays in CLI sessions?
