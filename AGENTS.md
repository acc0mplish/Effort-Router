# Repository agent guide

Use `gpt-6-luna / max` for general work and `gpt-6-sol / xhigh` for planning or high-reasoning work. Do not route Terra. Do not use native spawn or fan-out; independent helpers require a separate `codex exec` with explicit model and effort.

## Failure-based permanent prevention rules

- Before publishing a Codex role-template routing change, inspect the full instruction text for duplicated model-family prefixes such as `GPT-6-GPT-6-Luna`.
