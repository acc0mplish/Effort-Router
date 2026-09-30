#!/usr/bin/env python3
"""Apply the fixed global Effort Router policy to Codex role TOMLs."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib

EXPECTED_AGENTS = {
    'coder-medium': ('gpt-6-luna', 'max'),
    'implement-med': ('gpt-6-luna', 'max'),
    'implement-xhigh': ('gpt-6-luna', 'max'),
    'core-xhigh': ('gpt-6-luna', 'max'),
    'plan-high': ('gpt-6.1-sol', 'high'),
    'plan-xhigh': ('gpt-6.1-sol', 'high'),
    'plan-adversary-xhigh': ('gpt-6.1-sol', 'high'),
    'review-pr-high': ('gpt-6.1-sol', 'high'),
    'review-pr-xhigh': ('gpt-6.1-sol', 'high'),
    'security-audit': ('gpt-6.1-sol', 'high'),
}


def expected_agents() -> dict[str, tuple[str, str]]:
    return dict(EXPECTED_AGENTS)


def render_agent(text: str, model: str, effort: str) -> str:
    """Change only bare root routing keys; retain all other TOML contents."""
    tomllib.loads(text)
    root_end = re.search(r'^\s*\[', text, flags=re.M)
    root = text[:root_end.start()] if root_end else text
    tail = text[root_end.start():] if root_end else ''
    for key, value in (('model', model), ('model_reasoning_effort', effort)):
        pattern = rf'^{key}\s*=\s*"[^"\n]*"[^\n]*$'
        root, count = re.subn(pattern, f'{key} = "{value}"', root, flags=re.M)
        if count != 1:
            raise ValueError(f'Expected one bare root {key} key; refusing to rewrite unfamiliar role TOML.')
    updated = root + tail
    data = tomllib.loads(updated)
    if data.get('model') != model or data.get('model_reasoning_effort') != effort:
        raise ValueError('Role routing update validation failed.')
    return updated


def configure(agents_dir: Path, apply: bool) -> dict:
    templates = Path(__file__).resolve().parents[1] / 'platforms' / 'codex-agents'
    changes = []
    for name, (model, effort) in expected_agents().items():
        target = agents_dir / f'{name}.toml'
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink role: {target.name}')
        original = target.read_text(encoding='utf-8') if target.exists() else None
        source = original if original is not None else (templates / target.name).read_text(encoding='utf-8')
        updated = render_agent(source, model, effort)
        if updated != original:
            changes.append((target, original, updated))

    report = {
        'policy': 'global',
        'changed_roles': [path.stem for path, _, _ in changes],
        'applied': apply,
        'restart_required': bool(apply and changes),
        'backup_dir': None,
        'hint': 'run scripts/deploy_global.py for full deployment',
    }
    if not apply or not changes:
        return report

    agents_dir.mkdir(parents=True, exist_ok=True)
    backup_root = _backup_root(agents_dir)
    report['stale_backups'] = _stale_backups(backup_root)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')
    backup = Path(tempfile.mkdtemp(prefix=stamp, dir=backup_root))
    report['backup_dir'] = str(backup)
    for target, original, _ in changes:
        if original is not None:
            shutil.copy2(target, backup / target.name)

    written = []
    try:
        for target, original, updated in changes:
            _atomic_write(target, updated)
            written.append((target, original))
    except OSError:
        for target, original in reversed(written):
            if original is None:
                target.unlink()
            else:
                shutil.copy2(backup / target.name, target)
        raise
    return report


def _backup_root(agents_dir: Path) -> Path:
    root = Path(os.environ.get(
        'EFFORT_ROUTER_BACKUP_ROOT', str(Path.home() / '.effort-router-backups')))
    resolved = root.expanduser().resolve()
    scan_tree = agents_dir.resolve()
    if resolved == scan_tree or scan_tree in resolved.parents:
        raise ValueError(
            f'Refusing backup root inside the role scan tree: {resolved}')
    path = resolved / 'configure'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stale_backups(backup_root: Path, keep: int = 10) -> list[str]:
    snapshots = sorted(path for path in backup_root.iterdir() if path.is_dir())
    if len(snapshots) <= keep:
        return []
    return [str(path) for path in snapshots[:-keep]]


def _atomic_write(target: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix='.' + target.name, dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(text)
        if target.exists():
            shutil.copymode(target, temporary)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--agents-dir',
        type=Path,
        default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'agents',
    )
    parser.add_argument('--apply', action='store_true', help='Write role changes with backups; restart Codex afterward.')
    args = parser.parse_args()
    try:
        report = configure(args.agents_dir.expanduser(), args.apply)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as error:
        print(f'FAIL global routing configuration: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
