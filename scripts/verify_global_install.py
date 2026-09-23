#!/usr/bin/env python3
"""Verify the global Codex Effort Router installation without mutating it."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from configure_codex_plan import expected_agents


def load_toml(path: Path) -> dict:
    with path.open('rb') as handle:
        return tomllib.load(handle)


def main() -> int:
    codex_home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')).expanduser()
    failures: list[str] = []
    skill_dir = codex_home / 'skills' / 'effort-router'
    for relative in ('SKILL.md', 'agents/openai.yaml', 'platforms/codex.md'):
        if not (skill_dir / relative).is_file():
            failures.append(f'missing {skill_dir / relative}')

    config_path = codex_home / 'config.toml'
    if not config_path.is_file():
        failures.append(f'missing {config_path}')
        config = {}
    else:
        try:
            config = load_toml(config_path)
        except (OSError, tomllib.TOMLDecodeError) as error:
            failures.append(f'invalid {config_path}: {error}')
            config = {}

    if config.get('model') != 'gpt-6-luna':
        failures.append('config model must be gpt-6-luna')
    if config.get('model_reasoning_effort') != 'max':
        failures.append('config model_reasoning_effort must be max')

    agents_enabled = config.get('agents', {}).get('enabled') is True
    if not agents_enabled:
        failures.append('custom agents are not enabled ([agents].enabled)')

    global_agents = codex_home / 'AGENTS.md'
    if not global_agents.is_file():
        failures.append(f'missing {global_agents}')
    else:
        text = global_agents.read_text(encoding='utf-8')
        for marker in (
            'effort-router',
            'GPT-6-Luna',
            'GPT-6-Sol',
            'max',
            '실패 기반 영구 예방 규칙',
            '과거 실패 1건',
            'CLAUDE.md',
            '.cursorrules',
        ):
            if marker not in text:
                failures.append(f'AGENTS.md missing marker: {marker}')

    agent_dir = codex_home / 'agents'
    for name, (model, effort) in expected_agents().items():
        path = agent_dir / f'{name}.toml'
        if not path.is_file():
            failures.append(f'missing agent {path}')
            continue
        try:
            agent = load_toml(path)
        except (OSError, tomllib.TOMLDecodeError) as error:
            failures.append(f'invalid agent {path}: {error}')
            continue
        if agent.get('model') != model or agent.get('model_reasoning_effort') != effort:
            failures.append(
                f'agent {name} expected {model}/{effort}, got '
                f'{agent.get("model")}/{agent.get("model_reasoning_effort")}'
            )

    if failures:
        print('FAIL global effort-router installation')
        for failure in failures:
            print(f'- {failure}')
        return 1

    print('PASS global effort-router installation')
    print(f'- CODEX_HOME: {codex_home}')
    print('- default: gpt-6-luna/max')
    print(f'- custom agents: {len(expected_agents())}/{len(expected_agents())}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
