# Repository agent guide

Use `gpt-6-luna / max` for general work and `gpt-6-sol / xhigh` for planning or high-reasoning work. Do not route Terra. Do not use native spawn or fan-out; independent helpers require a separate `codex exec` with explicit model, effort, and working directory (implicit cwd inheritance has caused cross-worktree interference).

## Failure-based permanent prevention rules

- Before publishing a Codex role-template routing change, inspect the full instruction text for duplicated model-family prefixes such as `GPT-6-GPT-6-Luna`.
- On finding file changes you did not make in a worktree (e.g. rustfmt-only edits of unknown origin), do not revert or commit them — run `scripts/tree_gate.py check` to identify the owning session's claim first (an unverified assumption revert destroyed another writer's uncommitted changes, 2026-09).
