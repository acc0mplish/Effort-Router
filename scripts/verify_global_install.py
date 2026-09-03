#!/usr/bin/env python3
"""Verify the global Codex installation of effort-router without mutating it."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path


EXPECTED_AGENTS = {
    "coder-medium": ("gpt-5.6-luna", "max"),
    "implement-med": ("gpt-5.6-luna", "max"),
    "plan-high": ("gpt-5.6-sol", "high"),
    "plan-xhigh": ("gpt-5.6-sol", "xhigh"),
    "plan-adversary-xhigh": ("gpt-5.6-sol", "xhigh"),
    "review-pr-high": ("gpt-5.6-sol", "high"),
    "review-pr-xhigh": ("gpt-5.6-sol", "xhigh"),
    "implement-xhigh": ("gpt-5.6-sol", "xhigh"),
    "core-xhigh": ("gpt-5.6-sol", "max"),
    "security-audit": ("gpt-5.6-sol", "max"),
}


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def main() -> int:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    failures: list[str] = []

    skill_dir = codex_home / "skills" / "effort-router"
    required_skill_files = [skill_dir / "SKILL.md", skill_dir / "agents" / "openai.yaml"]
    for path in required_skill_files:
        if not path.is_file():
            failures.append(f"missing {path}")

    config_path = codex_home / "config.toml"
    if not config_path.is_file():
        failures.append(f"missing {config_path}")
        config = {}
    else:
        try:
            config = load_toml(config_path)
        except (OSError, tomllib.TOMLDecodeError) as error:
            failures.append(f"invalid {config_path}: {error}")
            config = {}

    if config.get("model") != "gpt-5.6-luna":
        failures.append("config model must be gpt-5.6-luna")
    if config.get("model_reasoning_effort") != "max":
        failures.append("config model_reasoning_effort must be max")

    modern_agents = config.get("agents", {})
    legacy_features = config.get("features", {})
    agents_enabled = modern_agents.get("enabled") is True or legacy_features.get("multi_agent") is True
    if not agents_enabled:
        failures.append("subagents are not enabled ([agents].enabled or [features].multi_agent)")

    global_agents = codex_home / "AGENTS.md"
    if not global_agents.is_file():
        failures.append(f"missing {global_agents}")
    else:
        text = global_agents.read_text(encoding="utf-8")
        for marker in (
            "effort-router",
            "GPT-5.6-Luna",
            "GPT-5.6-Sol",
            "실패 기반 영구 예방 규칙",
            "과거 실패 1건",
            "CLAUDE.md",
            ".cursorrules",
        ):
            if marker not in text:
                failures.append(f"AGENTS.md missing marker: {marker}")

    agent_dir = codex_home / "agents"
    for name, (model, effort) in EXPECTED_AGENTS.items():
        path = agent_dir / f"{name}.toml"
        if not path.is_file():
            failures.append(f"missing agent {path}")
            continue
        try:
            agent = load_toml(path)
        except (OSError, tomllib.TOMLDecodeError) as error:
            failures.append(f"invalid agent {path}: {error}")
            continue
        if agent.get("model") != model or agent.get("model_reasoning_effort") != effort:
            failures.append(
                f"agent {name} expected {model}/{effort}, got "
                f"{agent.get('model')}/{agent.get('model_reasoning_effort')}"
            )

    if failures:
        print("FAIL global effort-router installation")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASS global effort-router installation")
    print(f"- CODEX_HOME: {codex_home}")
    print("- default: gpt-5.6-luna/max")
    print(f"- custom agents: {len(EXPECTED_AGENTS)}/{len(EXPECTED_AGENTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
