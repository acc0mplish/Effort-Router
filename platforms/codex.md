# effort-router — Codex adapter

Applies to Codex CLI, the IDE extension, and the Codex view in the ChatGPT desktop app. They share the local Skill, `config.toml`, and custom-agent TOMLs.

## Install and update locations

- Skill: `~/.codex/skills/effort-router/`
- Custom-agent TOMLs: `~/.codex/agents/`
- Global model defaults: `~/.codex/config.toml`
- Global instructions: `~/.codex/AGENTS.md`

Copy the upstream Skill content into the Skill directory, then apply this Codex adapter's fixed role map. Preserve unrelated files and settings, and keep local Codex routing aligned with the global `AGENTS.md`.

## Global model defaults

Merge these root values above the first TOML table; do not replace the file:

```toml
model = "gpt-6-luna"
model_reasoning_effort = "max"

[agents]
enabled = true
```

If `[agents]` already exists, update its `enabled` value instead of adding a duplicate table. Preserve profiles, MCP, sandbox, and project settings. `agents.enabled` makes custom-role configuration available; it does not authorize native agent spawning or fan-out.

## Fixed Codex role map

| Role | Model | Effort |
|---|---|---|
| `coder-medium` | `gpt-6-luna` | `max` |
| `implement-med` | `gpt-6-luna` | `max` |
| `implement-xhigh` | `gpt-6-luna` | `max` |
| `core-xhigh` | `gpt-6-luna` | `max` |
| `plan-high` | `gpt-6-sol` | `xhigh` |
| `plan-xhigh` | `gpt-6-sol` | `xhigh` |
| `plan-adversary-xhigh` | `gpt-6-sol` | `xhigh` |
| `review-pr-high` | `gpt-6-sol` | `xhigh` |
| `review-pr-xhigh` | `gpt-6-sol` | `xhigh` |
| `security-audit` | `gpt-6-sol` | `xhigh` |

Use `gpt-6-luna / max` for general work and `gpt-6-sol / xhigh` for planning or high-reasoning work. Terra is not used. Custom-agent files record the mapping; their presence does not authorize a spawn.

The updater changes only the bare `model` and `model_reasoning_effort` keys in role TOMLs, preserves other content, and backs up changed files:

```bash
python3 ~/.codex/skills/effort-router/scripts/configure_codex_plan.py
python3 ~/.codex/skills/effort-router/scripts/configure_codex_plan.py --apply
```

## Global instructions and verification

Keep the existing `~/.codex/AGENTS.md` content. It must activate effort-router before coding and describe the model/effort rules and failure-ledger policy. In this installation, native spawn/fan-out is disabled by instruction; use a separate `codex exec` process for an explicitly authorized independent helper only.

Verify the local skill, global defaults, instructions, and all ten role TOMLs:

```bash
python3 ~/.codex/skills/effort-router/scripts/verify_global_install.py
```

Success prints `PASS global effort-router installation`. Restart Codex after changing global configuration or role TOMLs so the next session loads the updated values.
