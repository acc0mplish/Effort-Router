#!/usr/bin/env python3
"""Deploy the Effort Router global policy to Codex in a single pipeline.

Pipeline (fixed order): precheck (freshness, duplicates, mirror diff) ->
snapshot -> role TOML deploy -> combined config.toml/AGENTS.md merge-only
replacement -> 2-way mirror sync -> gates G1-G4 -> JSON report.
stdout is a single pure-JSON report; stderr carries a human summary.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

from configure_codex_plan import _atomic_write, expected_agents
from verify_global_install import find_duplicate_roles

ROOT = Path(__file__).resolve().parents[1]

_ROOT_MIRROR_FILES = ('SKILL.md', 'README.md', 'TESTS.md', 'TESTS-GATES.md',
                      'TESTS-ARCHIVE.md')
_AGENT_MIRROR_FILES = (
    'openai.yaml',
    'coder-medium.md', 'core-xhigh.md', 'implement-med.md', 'implement-xhigh.md',
    'ops-supervisor.md', 'plan-adversary-xhigh.md', 'plan-high.md', 'plan-xhigh.md',
    'review-pr-high.md', 'review-pr-xhigh.md', 'security-audit.md',
)
_PLATFORM_MIRROR_FILES = (
    'CLAUDE.md', 'README.md', 'chat-app.md', 'codex.md', 'gemini.md',
    'glm.md', 'grok.md', 'qwen.md', 'zcode.md',
)
_SCRIPT_MIRROR_FILES = (
    'configure_codex_plan.py', 'jev_judge.py', 'jev_modes.py',
    'neverstuck_gate.py', 'tree_gate.py', 'verify_exec.py',
    'verify_global_install.py', 'verify_pin.py', 'worktree_gate.py',
    'worktree_gate_lib.py',
    'test_codex_routing.py', 'test_jev_judge.py', 'test_jev_modes.py',
    'test_jev_modes_extra.py', 'test_neverstuck_gate.py', 'test_plan_routing.py',
    'test_tree_claim_hook.py', 'test_tree_gate.py', 'test_verify_exec.py',
    'test_verify_pin.py', 'test_worktree_gate.py', 'test_worktree_gate_hardening.py',
    'deploy_global.py', 'test_deploy_global.py', 'test_verify_duplicate_detection.py',
)
MIRROR_MANIFEST = (
    _ROOT_MIRROR_FILES
    + tuple(f'agents/{name}' for name in _AGENT_MIRROR_FILES)
    + tuple(f'platforms/{name}' for name in _PLATFORM_MIRROR_FILES)
    + tuple(
        f'platforms/codex-agents/{name}.toml' for name in sorted(expected_agents()))
    + tuple(f'scripts/{name}' for name in _SCRIPT_MIRROR_FILES)
)

# r31 확정 표 + R3 정규식 변형형 (MED-6) — 발견 시에만 적용·카운트 기록.
REPLACEMENTS = (
    ('combined_lower', (r'gpt-6\.1-sol ?/ ?xhigh', 'gpt-6.1-sol / high')),
    ('combined_upper', (r'GPT-6\.1-Sol ?/ ?xhigh', 'GPT-6.1-Sol / high')),
    ('space_upper', (r'GPT-6\.1-Sol xhigh', 'GPT-6.1-Sol high')),
    ('middot_upper', (r'Sol·xhigh', 'Sol·high')),
    ('sol_61', (r'Sol 6\.1 xhigh', 'Sol 6.1 high')),
    ('effort_literal', (r'model_reasoning_effort ?= ?"xhigh"',
                        'model_reasoning_effort = "high"')),
)
# AGENTS.md 어휘 표 2행 의미 교환 — 구형 감지 시에만 (이중 교환 방지 §5-W3).
VOCAB_SWAP = (
    ('vocab_high',
     '| high | 별도 지시가 있을 때만 사용 |',
     '| high | 계획 및 고난도 추론의 `gpt-6.1-sol` |'),
    ('vocab_xhigh',
     '| xhigh | 계획 및 고난도 추론의 `gpt-6.1-sol` |',
     '| xhigh | 별도 지시가 있을 때만 사용 |'),
)
VOCAB_NEW_MARKERS = ('| high | 계획 및 고난도 추론의', '| xhigh | 별도 지시')


def _apply_replacements(text: str, table=REPLACEMENTS) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for name, (pattern, replacement) in table:
        text, count = re.subn(pattern, replacement, text)
        counts[name] = count
    return text, counts


def _residual_count(text: str) -> int:
    """Broader-than-table legacy scan (case-insensitive) so unexpected
    variant forms abort the pipeline instead of surviving silently."""
    return sum(
        len(re.findall(pattern, text, flags=re.IGNORECASE))
        for _, (pattern, _) in REPLACEMENTS)


def _split_root_tail(text: str) -> tuple[str, str]:
    match = re.search(r'^\s*\[', text, flags=re.M)
    if not match:
        return text, ''
    return text[:match.start()], text[match.start():]


def _top_level_state(data: dict) -> dict:
    return {key: value for key, value in data.items() if not isinstance(value, dict)}


def _replace_config(text: str) -> tuple[str, dict[str, int]]:
    """Merge-only replacement — the root section (before the first ``[``) is
    structurally untouched (RISK-3); replacements apply to the tail only."""
    root, tail = _split_root_tail(text)
    before = tomllib.loads(text)
    tail, counts = _apply_replacements(tail)
    updated = root + tail
    after = tomllib.loads(updated)
    if set(before) != set(after) or _top_level_state(before) != _top_level_state(after):
        raise ValueError('config.toml top-level keys would change; refusing to write.')
    return updated, counts


def _replace_agents_md(text: str) -> tuple[str, dict[str, int]]:
    updated, counts = _apply_replacements(text)
    for name, old, new in VOCAB_SWAP:
        if old in updated:
            updated, count = re.subn(re.escape(old), new, updated)
            counts[name] = count
    return updated, counts


def _expected_content(codex_home: Path) -> tuple[str, str, dict, dict]:
    """Compute both in-memory replacement results without touching disk."""
    config_text = (codex_home / 'config.toml').read_text(encoding='utf-8')
    agents_text = (codex_home / 'AGENTS.md').read_text(encoding='utf-8')
    config_new, config_counts = _replace_config(config_text)
    agents_new, agents_counts = _replace_agents_md(agents_text)
    return config_new, agents_new, config_counts, agents_counts


def _validate_replacements(config_new: str, agents_new: str) -> None:
    """TECH-2 — both files are validated in memory before either is written."""
    root, tail = _split_root_tail(config_new)
    root_residual = _residual_count(root)
    tail_residual = _residual_count(tail) + _residual_count(agents_new)
    if root_residual and not tail_residual:
        raise ValueError(
            'config.toml top-level (user override region) still holds legacy '
            f'effort literals ({root_residual}); refusing to write. The root '
            'section is structurally untouched — adjust the top-level override '
            'manually before re-running.')
    if root_residual or tail_residual:
        raise ValueError('Unknown legacy pattern residue after replacement; refusing to write.')
    for name, old, _ in VOCAB_SWAP:
        if old in agents_new:
            raise ValueError(f'Vocabulary row {name} still holds the old form; refusing to write.')


def _mirror_roots(codex_home: Path, claude_mirror: Path) -> dict[str, Path]:
    return {'codex': codex_home / 'skills' / 'effort-router', 'claude': claude_mirror}


def _mirror_drift(mirrors: dict[str, Path]) -> list[dict]:
    drift: list[dict] = []
    for label, root in mirrors.items():
        for relative in MIRROR_MANIFEST:
            path = root / relative
            if path.is_file() and path.read_bytes() != (ROOT / relative).read_bytes():
                drift.append({'mirror': label, 'path': relative})
    return drift


def _count_changes(codex_home: Path, mirrors: dict[str, Path],
                   config_new: str, agents_new: str) -> int:
    """TECH-5 — content comparison against repo/expected results, no writes."""
    templates = ROOT / 'platforms' / 'codex-agents'
    total = 0
    for name in expected_agents():
        live = codex_home / 'agents' / f'{name}.toml'
        if not live.is_file() or live.read_bytes() != (templates / f'{name}.toml').read_bytes():
            total += 1
    for path, expected in ((codex_home / 'config.toml', config_new),
                           (codex_home / 'AGENTS.md', agents_new)):
        if not path.is_file() or path.read_bytes() != expected.encode('utf-8'):
            total += 1
    for root in mirrors.values():
        for relative in MIRROR_MANIFEST:
            path = root / relative
            if not path.is_file() or path.read_bytes() != (ROOT / relative).read_bytes():
                total += 1
    return total


def _snapshot(backup_root: Path, codex_home: Path,
              mirrors: dict[str, Path]) -> tuple[Path, int]:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')
    snapshot = backup_root / f'{stamp}deploy'
    (snapshot / 'mirrors' / 'codex').mkdir(parents=True)
    (snapshot / 'mirrors' / 'claude').mkdir()
    count = 0
    for name in ('config.toml', 'AGENTS.md'):
        source = codex_home / name
        if source.is_file():
            shutil.copy2(source, snapshot / name)
            count += 1
    agents_dir = codex_home / 'agents'
    (snapshot / 'agents').mkdir(exist_ok=True)
    for path in sorted(agents_dir.glob('*.toml')) if agents_dir.is_dir() else []:
        shutil.copy2(path, snapshot / 'agents' / path.name)
        count += 1
    for label, root in mirrors.items():
        for relative in MIRROR_MANIFEST:
            source = root / relative
            if source.is_file():
                destination = snapshot / 'mirrors' / label / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                count += 1
    return snapshot, count


def _deploy_roles(codex_home: Path) -> list[str]:
    templates = ROOT / 'platforms' / 'codex-agents'
    agents_dir = codex_home / 'agents'
    agents_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in sorted(expected_agents()):
        target = agents_dir / f'{name}.toml'
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink role: {target.name}')
        _atomic_write(target, (templates / f'{name}.toml').read_text(encoding='utf-8'))
        copied.append(name)
    return copied


def _stage_temp(target: Path, text: str) -> Path:
    """Write text to a temp file beside target (mode preserved); no replace."""
    # W2 — mkstemp→fdopen 진입 실패의 fd 누수 창은 사실상 없음(동일 플래그 개방).
    descriptor, temporary = tempfile.mkstemp(prefix='.' + target.name, dir=target.parent)
    staged = Path(temporary)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(text)
        if target.exists():
            shutil.copymode(target, temporary)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def _backup_temp(target: Path) -> Path:
    """Byte-exact copy of target beside it (copy2 — content, mode, times)."""
    descriptor, temporary = tempfile.mkstemp(prefix='.' + target.name, dir=target.parent)
    os.close(descriptor)
    backup = Path(temporary)
    try:
        shutil.copy2(target, temporary)
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
    return backup


def _commit_pair(pairs: tuple[tuple[Path, str], ...], backup_dir: Path) -> None:
    """TECH-2b — stage every file first, then replace in order; on failure the
    already-replaced files are restored from byte-exact staged backups
    (transactional abort — the OSError is still reported, so this is not the
    §8-10 auto-rollback of a failed pipeline)."""
    staged_new: list[tuple[Path, Path]] = []
    staged_old: dict[Path, Path] = {}
    replaced = 0
    try:
        for target, text in pairs:
            staged_new.append((target, _stage_temp(target, text)))
        for target, _ in pairs:
            staged_old[target] = _backup_temp(target)
        for index, (target, temporary) in enumerate(staged_new):
            os.replace(temporary, target)
            replaced = index + 1
    except OSError:
        for target, _ in staged_new[:replaced]:
            try:
                os.replace(staged_old[target], target)
            except OSError:
                print(f'restore of {target} failed — manual restore point: {backup_dir}',
                      file=sys.stderr)
        raise
    finally:
        for _, temporary in staged_new:
            temporary.unlink(missing_ok=True)
        for temporary in staged_old.values():
            temporary.unlink(missing_ok=True)


def _sync_mirrors(mirrors: dict[str, Path]) -> int:
    synced = 0
    for root in mirrors.values():
        for relative in MIRROR_MANIFEST:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
            if destination.read_bytes() != (ROOT / relative).read_bytes():
                raise OSError(f'Mirror sync verification failed: {destination}')
            synced += 1
    return synced


def _gate_g1(codex_home: Path, config_pre: dict) -> dict:
    texts = [(codex_home / 'config.toml').read_text(encoding='utf-8'),
             (codex_home / 'AGENTS.md').read_text(encoding='utf-8')]
    texts.extend(
        path.read_text(encoding='utf-8')
        for path in sorted((codex_home / 'agents').glob('*.toml')))
    residual = {path: 0 for path in ('config.toml', 'AGENTS.md')}
    residual['config.toml'] = _residual_count(texts[0])
    residual['AGENTS.md'] = _residual_count(texts[1])
    roles_residual = sum(_residual_count(text) for text in texts[2:])
    config = tomllib.loads(texts[0])
    top_ok = (_top_level_state(config) == _top_level_state(config_pre)
              and set(config) == set(config_pre))
    vocab_ok = all(marker in texts[1] for marker in VOCAB_NEW_MARKERS)
    passed = sum(residual.values()) + roles_residual == 0 and top_ok and vocab_ok
    return {'pass': passed, 'residual': sum(residual.values()) + roles_residual,
            'top_level_ok': top_ok, 'vocab_table_ok': vocab_ok}


def _gate_g2(codex_home: Path) -> dict:
    expected = ['config model must be gpt-6-luna',
                'config model_reasoning_effort must be max']
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts/verify_global_install.py')],
        env=dict(os.environ, CODEX_HOME=str(codex_home)),
        capture_output=True, text=True)
    failures = [line[2:] for line in result.stdout.splitlines()
                if line.startswith('- ')]
    passed = result.returncode == 1 and failures == expected
    return {'pass': passed, 'verify_exit': result.returncode, 'failures': failures}


def _gate_g3(mirrors: dict[str, Path]) -> dict:
    missing = []
    for label, root in mirrors.items():
        for relative in MIRROR_MANIFEST:
            path = root / relative
            if not path.is_file() or path.read_bytes() != (ROOT / relative).read_bytes():
                missing.append(f'{label}:{relative}')
    return {'pass': not missing, 'missing': missing}


def _gate_g4(codex_home: Path) -> dict:
    templates = ROOT / 'platforms' / 'codex-agents'
    mismatched = []
    for name in sorted(expected_agents()):
        live = codex_home / 'agents' / f'{name}.toml'
        if not live.is_file() or live.read_bytes() != (templates / f'{name}.toml').read_bytes():
            mismatched.append(name)
    return {'pass': not mismatched, 'mismatched': mismatched}


def _guard_paths(backup_root: Path, claude_mirror: Path, codex_home: Path) -> None:
    agents_tree = (codex_home / 'agents').resolve()
    if backup_root == agents_tree or agents_tree in backup_root.parents:
        raise ValueError(f'Refusing backup root inside the role scan tree: {backup_root}')
    for marker in ('SKILL.md', 'README.md'):
        if not (claude_mirror / marker).is_file():
            raise ValueError(
                f'--claude-mirror is missing the {marker} marker; refusing an '
                'unfamiliar mirror path.')


def _precheck(codex_home: Path, mirrors: dict[str, Path]
              ) -> tuple[dict[str, list[str]], list[dict], list[str]]:
    templates = ROOT / 'platforms' / 'codex-agents'
    missing_templates = [name for name in sorted(expected_agents())
                         if not (templates / f'{name}.toml').is_file()]
    if missing_templates:
        raise ValueError(f'Repo role templates missing: {missing_templates}')
    agents_dir = codex_home / 'agents'
    duplicates: dict[str, list[str]] = {}
    warnings: list[str] = []
    if agents_dir.is_dir():
        found, warning_files = find_duplicate_roles(agents_dir)
        duplicates = {stem: [str(path) for path in paths]
                      for stem, paths in found.items()}
        warnings = [str(path) for path in warning_files]
    if duplicates:
        raise ValueError(f'Dot-directory duplicate roles present; aborting: {duplicates}')
    for name in ('config.toml', 'AGENTS.md'):
        if not (codex_home / name).is_file():
            raise ValueError(f'Missing deployment target: {codex_home / name}')
    tomllib.loads((codex_home / 'config.toml').read_text(encoding='utf-8'))
    drift = _mirror_drift(mirrors)
    return duplicates, drift, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='Simulate without touching live files or the backup root; '
                             'gates are not evaluated (informational report only).')
    parser.add_argument('--codex-home', type=Path, default=None,
                        help='Target Codex home (default $CODEX_HOME or ~/.codex)')
    parser.add_argument('--claude-mirror', type=Path, default=None,
                        help='Claude-side mirror root (default ~/.claude/skills/effort-router)')
    args = parser.parse_args()

    codex_home = (args.codex_home or Path(
        os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))).expanduser()
    claude_mirror = (args.claude_mirror or Path.home() / '.claude' / 'skills' / 'effort-router'
                     ).expanduser()
    backup_root = Path(os.environ.get(
        'EFFORT_ROUTER_BACKUP_ROOT', str(Path.home() / '.effort-router-backups'))
    ).expanduser().resolve()
    mirrors = _mirror_roots(codex_home, claude_mirror)

    report: dict = {'dry_run': args.dry_run, 'backup_dir': None}
    try:
        _guard_paths(backup_root, claude_mirror, codex_home)
        duplicates, drift, warnings = _precheck(codex_home, mirrors)
    except (OSError, ValueError) as error:
        report['error'] = str(error)
        print(json.dumps(report, ensure_ascii=False))
        print(f'FAIL deploy precheck: {error}', file=sys.stderr)
        return 1

    report['precheck'] = {
        'roles_expected': sorted(expected_agents()),
        'duplicates': duplicates,
        'role_file_warnings': warnings,
        'mirror_drift': drift,
    }
    report['mirror_drift'] = drift

    try:
        config_new, agents_new, config_counts, agents_counts = _expected_content(codex_home)
        report['replaced'] = {'config.toml': config_counts, 'AGENTS.md': agents_counts}
        report['changes_total'] = _count_changes(codex_home, mirrors, config_new, agents_new)
        report['restart_required'] = report['changes_total'] > 0
    except (OSError, ValueError) as error:
        report['error'] = str(error)
        print(json.dumps(report, ensure_ascii=False))
        print(f'FAIL deploy content stage: {error}', file=sys.stderr)
        return 1

    if args.dry_run:
        report['planned'] = {
            'roles_copied': len(expected_agents()),
            'mirror_synced': len(MIRROR_MANIFEST) * 2,
            'replacements': report['replaced'],
            'snapshot_root': str(backup_root),
        }
        report['drift_detected'] = bool(drift) or report['changes_total'] > 0
        print(json.dumps(report, ensure_ascii=False))
        print('DRY-RUN report only — live files, backup root, and gates untouched.',
              file=sys.stderr)
        return 0

    try:
        snapshot, snapshot_files = _snapshot(backup_root, codex_home, mirrors)
        report['backup_dir'] = str(snapshot)
        report['snapshot_files'] = snapshot_files
        report['roles_copied'] = _deploy_roles(codex_home)
        config_pre = tomllib.loads(
            (codex_home / 'config.toml').read_text(encoding='utf-8'))
        _validate_replacements(config_new, agents_new)
        _commit_pair(((codex_home / 'config.toml', config_new),
                      (codex_home / 'AGENTS.md', agents_new)), snapshot)
        report['mirror_synced'] = _sync_mirrors(mirrors)
    except (OSError, ValueError) as error:
        report['error'] = str(error)
        print(json.dumps(report, ensure_ascii=False))
        print(f'FAIL deploy write phase: {error}', file=sys.stderr)
        print(f'Manual restore point (no auto-rollback): {report["backup_dir"]}',
              file=sys.stderr)
        return 1

    report['gates'] = {
        'G1': _gate_g1(codex_home, config_pre),
        'G2': _gate_g2(codex_home),
        'G3': _gate_g3(mirrors),
        'G4': _gate_g4(codex_home),
    }
    passed = all(gate['pass'] for gate in report['gates'].values())
    print(json.dumps(report, ensure_ascii=False))
    for name, gate in report['gates'].items():
        print(f'{name}: {"PASS" if gate["pass"] else "FAIL"}', file=sys.stderr)
    print(f'changes_total: {report["changes_total"]}', file=sys.stderr)
    print('Restart Codex to apply role changes.', file=sys.stderr)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
