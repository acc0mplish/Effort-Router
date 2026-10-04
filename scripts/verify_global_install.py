#!/usr/bin/env python3
"""Verify the global Codex Effort Router installation without mutating it."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from configure_codex_plan import default_routing, expected_agents, routing_policy


def load_toml(path: Path) -> dict:
    with path.open('rb') as handle:
        return tomllib.load(handle)


def find_duplicate_roles(agent_dir: Path) -> tuple[dict[str, list[Path]], list[Path]]:
    """Layered duplicate detection (RISK-6): a stem is a duplicate failure only
    when 2+ same-stem TOMLs exist and at least one sits in a dot directory;
    non-dot subdirectory TOMLs are reported as warnings only."""
    dot_files: list[Path] = []
    warning_files: list[Path] = []
    groups: dict[str, list[Path]] = {}
    for path in sorted(agent_dir.rglob('*.toml')):
        relative_parts = path.relative_to(agent_dir).parts[:-1]
        groups.setdefault(path.stem, []).append(path)
        if any(part.startswith('.') for part in relative_parts):
            dot_files.append(path)
        elif path.parent != agent_dir:
            warning_files.append(path)
    duplicates = {
        stem: paths for stem, paths in groups.items()
        if len(paths) > 1 and any(path in dot_files for path in paths)
    }
    return duplicates, warning_files


def main() -> int:
    codex_home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')).expanduser()
    failures: list[str] = []
    try:
        policy = routing_policy()
        default_model, default_effort = default_routing()
        roles = expected_agents()
    except (OSError, ValueError, TypeError) as error:
        print(f'FAIL local routing policy: {error}')
        return 1
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

    if config.get('model') != default_model:
        failures.append(f'config model must be {default_model}')
    if config.get('model_reasoning_effort') != default_effort:
        failures.append(f'config model_reasoning_effort must be {default_effort}')
    for name, effort in policy.get('profiles', {}).items():
        profile = config.get('profiles', {}).get(name)
        if profile is not None:
            if profile.get('model') != default_model or profile.get('model_reasoning_effort') != effort:
                failures.append(f'profile {name} must be {default_model}/{effort}')
            if profile.get('model_provider', config.get('model_provider', 'openai')) != config.get('model_provider', 'openai'):
                failures.append(f'profile {name} must use the default Astra provider')

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
            'GPT-6-Astra',
            'medium',
            'max',
            '실패 기반 영구 예방 규칙',
            '과거 실패 1건',
            'CLAUDE.md',
            '.cursorrules',
        ):
            if marker not in text:
                failures.append(f'AGENTS.md missing marker: {marker}')

    agent_dir = codex_home / 'agents'
    for name, (model, effort) in roles.items():
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

    if agent_dir.is_dir():
        duplicates, warning_files = find_duplicate_roles(agent_dir)
        for stem, paths in duplicates.items():
            listed = ', '.join(str(path) for path in paths)
            failures.append(f'duplicate role {stem}: {len(paths)} files: {listed}')
        for path in warning_files:
            print(f'unexpected role file (warning): {path}')

    if failures:
        print('FAIL global effort-router installation')
        for failure in failures:
            print(f'- {failure}')
        return 1

    print('PASS global effort-router installation')
    print(f'- CODEX_HOME: {codex_home}')
    print(f'- default: {default_model}/{default_effort}')
    print(f'- custom agents: {len(roles)}/{len(roles)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
