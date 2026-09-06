#!/usr/bin/env python3
"""Resolve Codex subscription routing; optionally update role TOMLs with backups."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib

EXECUTION_ROLES = ('coder-medium', 'implement-med', 'implement-xhigh', 'core-xhigh')
PLANNING_ROLES = ('plan-high', 'plan-xhigh')
REVIEW_ROLES = ('plan-adversary-xhigh', 'review-pr-high', 'review-pr-xhigh', 'security-audit')


def expected_agents(plan: str) -> dict[str, tuple[str, str]]:
    if plan not in ('plus', 'pro'):
        raise ValueError('Unsupported or unknown plan; specify --plan plus or --plan pro explicitly.')
    return {
        **{name: ('gpt-5.6-luna', 'max') for name in EXECUTION_ROLES},
        **{name: ('gpt-6-astra', 'medium') for name in PLANNING_ROLES},
        **{name: ('gpt-6-astra', 'medium' if plan == 'plus' else 'high') for name in REVIEW_ROLES},
    }


async def _detect_plan(command: str, timeout: float) -> str:
    process = await asyncio.create_subprocess_exec(
        command, 'app-server', stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)

    async def send(message):
        process.stdin.write((json.dumps(message) + '\n').encode())
        await process.stdin.drain()

    async def receive(request_id):
        while True:
            line = await process.stdout.readline()
            if not line:
                raise ValueError('Codex app-server closed before account/read completed.')
            message = json.loads(line)
            if message.get('id') == request_id:
                if 'error' in message or not isinstance(message.get('result'), dict):
                    # Never include raw account/auth responses in errors.
                    raise ValueError('Codex app-server rejected the account lookup.')
                return message['result']

    async def lookup():
        await send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'effort_router_plan_check', 'version': '1.0'}}})
        await receive(1)
        await send({'method': 'initialized', 'params': {}})
        await send({'id': 2, 'method': 'account/read', 'params': {'refreshToken': False}})
        result = await receive(2)
        account = result.get('account')
        if not isinstance(account, dict) or account.get('type') != 'chatgpt':
            raise ValueError('ChatGPT subscription unavailable; specify --plan plus or --plan pro explicitly.')
        plan = account.get('planType')
        expected_agents(plan)
        return plan

    try:
        return await asyncio.wait_for(lookup(), timeout)
    except asyncio.TimeoutError:
        raise ValueError('Codex account lookup timed out; no routing changes applied.') from None
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


def resolve_plan(plan='auto', command='codex', timeout=15.0):
    if plan != 'auto':
        expected_agents(plan)
        return plan
    return asyncio.run(_detect_plan(command, timeout))


def render_agent(text: str, model: str, effort: str) -> str:
    """Change only bare root routing keys; retain all other TOML contents."""
    tomllib.loads(text)
    # Role templates use bare root keys. Fail rather than rewrite unfamiliar TOML.
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


def configure(plan: str, agents_dir: Path, apply: bool) -> dict:
    templates = Path(__file__).resolve().parents[1] / 'platforms' / 'codex-agents'
    changes = []
    for name, (model, effort) in expected_agents(plan).items():
        target = agents_dir / f'{name}.toml'
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink role: {target.name}')
        original = target.read_text() if target.exists() else None
        source = original if original is not None else (templates / target.name).read_text()
        updated = render_agent(source, model, effort)
        if updated != original:
            changes.append((target, original, updated))
    report = {'plan': plan, 'review_effort': 'medium' if plan == 'plus' else 'high',
              'changed_roles': [p.stem for p, _, _ in changes], 'applied': apply,
              'restart_required': bool(apply and changes), 'backup_dir': None}
    if not apply or not changes:
        return report
    agents_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')
    backup = Path(tempfile.mkdtemp(prefix=stamp, dir=_backup_root(agents_dir)))
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


def _backup_root(agents_dir):
    path = agents_dir / '.effort-router-backups'
    path.mkdir(exist_ok=True)
    return path


def _atomic_write(target, text):
    descriptor, temporary = tempfile.mkstemp(prefix='.' + target.name, dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(text)
        if target.exists():
            shutil.copymode(target, temporary)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', choices=('auto', 'plus', 'pro'), default='auto')
    parser.add_argument('--codex-bin', default='codex')
    parser.add_argument('--timeout', type=float, default=15.0)
    parser.add_argument('--agents-dir', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'agents')
    parser.add_argument('--apply', action='store_true', help='Write role changes with backups; restart Codex afterward.')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    try:
        plan = resolve_plan(args.plan, args.codex_bin, args.timeout)
        report = configure(plan, args.agents_dir.expanduser(), args.apply)
        report['source'] = 'account/read' if args.plan == 'auto' else 'explicit'
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as error:
        print(f'FAIL plan routing: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
