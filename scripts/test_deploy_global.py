"""Exercise the integrated global deployment pipeline in an isolated home tree."""
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/deploy_global.py'

AGENTS_OLD = (
    'effort-router GPT-6-Luna GPT-6.1-Sol max 실패 기반 영구 예방 규칙 '
    '과거 실패 1건 CLAUDE.md .cursorrules\n'
    '\n'
    '일반 작업은 `gpt-6-luna / max`, 계획과 고난도 추론은 `gpt-6.1-sol / xhigh`를 사용한다.\n'
    '| Level | Meaning |\n'
    '|---|---|\n'
    '| high | 별도 지시가 있을 때만 사용 |\n'
    '| xhigh | 계획 및 고난도 추론의 `gpt-6.1-sol` |\n'
    "고난도 설정: `-m gpt-6.1-sol -c 'model_reasoning_effort=\"xhigh\"'`\n"
    '계획과 리뷰는 **GPT-6.1-Sol·xhigh**\n'
)

CONFIG_OLD = (
    'model = "gpt-6.1-sol"\n'
    'model_reasoning_effort = "low"\n'
    '[agents]\n'
    'enabled = true\n'
    '\n'
    '[profiles.planning]\n'
    'model = "gpt-6.1-sol"\n'
    'model_reasoning_effort = "xhigh"\n'
)

CONFIG_ROOT_OVERRIDE = (
    'model = "gpt-6.1-sol"\n'
    'model_reasoning_effort = "xhigh"\n'
    '[agents]\n'
    'enabled = true\n'
)


def _live_bytes(home: Path) -> dict[str, bytes]:
    return {
        'config.toml': (home / 'config.toml').read_bytes(),
        'AGENTS.md': (home / 'AGENTS.md').read_bytes(),
        **{
            path.name: path.read_bytes()
            for path in sorted((home / 'agents').glob('*.toml'))
        },
    }


def _fixture(home: Path) -> None:
    """Synthetic pre-deploy home (TECH-4) — never touches the live install."""
    (home / 'agents').mkdir(parents=True)
    (home / 'config.toml').write_text(CONFIG_OLD)
    (home / 'AGENTS.md').write_text(AGENTS_OLD)
    for source in (ROOT / 'platforms/codex-agents').glob('*.toml'):
        (home / 'agents' / source.name).write_bytes(source.read_bytes())

    codex_mirror = home / 'skills' / 'effort-router'
    (codex_mirror / 'agents').mkdir(parents=True)
    (codex_mirror / 'platforms').mkdir()
    for relative in ('SKILL.md', 'README.md', 'TESTS.md', 'TESTS-GATES.md'):
        (codex_mirror / relative).write_text(f'stale {relative}\n')
    (codex_mirror / 'agents/openai.yaml').write_text('stale yaml\n')
    (codex_mirror / 'platforms/codex.md').write_text('stale codex.md\n')

    claude_mirror = home / 'claude-mirror' / 'effort-router'
    (claude_mirror / 'agents').mkdir(parents=True)
    (claude_mirror / 'platforms').mkdir()
    for relative in ('SKILL.md', 'README.md', 'TESTS.md', 'TESTS-GATES.md'):
        (claude_mirror / relative).write_text(f'stale {relative}\n')
    (claude_mirror / 'agents/openai.yaml').write_text('stale yaml\n')
    (claude_mirror / 'platforms/codex.md').write_text('stale codex.md\n')


def _run(home: Path, claude_mirror: Path, *extra, env_extra=None):
    env = dict(os.environ, EFFORT_ROUTER_BACKUP_ROOT=str(home / 'backups'))
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), '--codex-home', str(home),
         '--claude-mirror', str(claude_mirror), *extra],
        capture_output=True, text=True, env=env)


class DeployGlobalTests(unittest.TestCase):
    def test_a_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            before = _live_bytes(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'

            result = _run(home, claude_mirror, '--dry-run')

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['dry_run'])
            self.assertNotIn('gates', report)
            self.assertIn('drift_detected', report)
            self.assertIn('planned', report)
            self.assertIsNone(report['backup_dir'])
            self.assertEqual(_live_bytes(home), before)
            self.assertFalse((home / 'backups').exists())

    def test_b_full_deploy_gates_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'

            result = _run(home, claude_mirror)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report['dry_run'])
            self.assertTrue(report['restart_required'])
            self.assertTrue(all(gate['pass'] for gate in report['gates'].values()),
                            report['gates'])
            self.assertEqual(len(report['roles_copied']), 10)
            self.assertEqual(report['mirror_synced'], 122)
            self.assertTrue(Path(report['backup_dir']).is_dir())
            # (iv) 최상위 무손상 — 치환은 tail 섹션에만 적용됐다.
            config = tomllib.loads((home / 'config.toml').read_text())
            self.assertEqual(config['model'], 'gpt-6.1-sol')
            self.assertEqual(config['model_reasoning_effort'], 'low')
            self.assertEqual(config['profiles']['planning']['model_reasoning_effort'], 'high')
            # AGENTS.md 구패턴 0 + 어휘 표 신형 2행.
            agents_md = (home / 'AGENTS.md').read_text()
            for stale in ('xhigh`를', 'Sol·xhigh', 'model_reasoning_effort="xhigh"',
                          '| high | 별도 지시'):
                self.assertNotIn(stale, agents_md)
            self.assertIn('| high | 계획 및 고난도 추론의', agents_md)
            self.assertIn('| xhigh | 별도 지시', agents_md)

    def test_c_rerun_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'
            first = _run(home, claude_mirror)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            second = _run(home, claude_mirror)

            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            report = json.loads(second.stdout)
            self.assertEqual(report['changes_total'], 0)
            self.assertFalse(report['restart_required'])
            self.assertTrue(all(gate['pass'] for gate in report['gates'].values()),
                            report['gates'])

    def test_d_dot_duplicate_blocks_deployment(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'
            copy = home / 'agents' / '.effort-router-backups' / '20261001T000000Z'
            copy.mkdir(parents=True)
            (copy / 'plan-high.toml').write_bytes((home / 'agents/plan-high.toml').read_bytes())
            before = _live_bytes(home)

            result = _run(home, claude_mirror)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(_live_bytes(home), before)

    def test_e_unknown_residue_aborts_before_any_config_write(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'
            agents_md = home / 'AGENTS.md'
            agents_md.write_text(agents_md.read_text() + '변형형 잔존: GPT-6.1-SOL / XHIGH\n')
            config_before = (home / 'config.toml').read_bytes()
            agents_before = agents_md.read_bytes()

            result = _run(home, claude_mirror)

            self.assertEqual(result.returncode, 1)
            # TECH-2 — 검증 실패 시 2파일 모두 원문 유지.
            self.assertEqual((home / 'config.toml').read_bytes(), config_before)
            self.assertEqual(agents_md.read_bytes(), agents_before)

    def test_f_mirror_drift_reported_snapshotted_then_synced(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'
            drifted = home / 'skills' / 'effort-router' / 'SKILL.md'
            drifted.write_text('user edited drift\n')

            result = _run(home, claude_mirror)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertIn(
                {'mirror': 'codex', 'path': 'SKILL.md'},
                report['mirror_drift'])
            # 동기 후 repo와 일치.
            self.assertEqual(
                drifted.read_bytes(), (ROOT / 'SKILL.md').read_bytes())
            # 스냅샷에 미러 기존분 보존.
            snapshot = Path(report['backup_dir'])
            self.assertEqual(
                (snapshot / 'mirrors/codex/SKILL.md').read_text(), 'user edited drift\n')

    def test_g_misuse_guards_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            empty_mirror = home / 'empty-mirror'
            empty_mirror.mkdir()

            result = _run(home, empty_mirror)

            self.assertEqual(result.returncode, 1)
            self.assertFalse((home / 'backups').exists())

            result = _run(home, home / 'claude-mirror' / 'effort-router',
                          env_extra={'EFFORT_ROUTER_BACKUP_ROOT': str(home / 'agents' / 'nested')})
            self.assertEqual(result.returncode, 1)

    def test_h_non_utf8_agents_md_reports_json_error(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            (home / 'AGENTS.md').write_bytes(b'\xff\xfeinvalid utf-8\n')
            before = _live_bytes(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'

            result = _run(home, claude_mirror)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)   # §2.3 — stdout은 JSON 1문서
            self.assertIn('error', report)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(_live_bytes(home), before)
            self.assertFalse((home / 'backups').exists())

    def test_i_commit_pair_atomic_under_second_replace_failure(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import deploy_global

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            config = work / 'config.toml'
            agents = work / 'AGENTS.md'
            # CRLF 원문 — 복원이 텍스트 왕복이 아니라 copy2 바이트 복사임을 실측(T-1).
            config.write_bytes(b'old config line1\r\nold config line2\r\n')
            agents.write_bytes(b'old agents\r\n')

            real_replace = os.replace
            calls = []
            def fail_second(src, dst):
                # 주의: 인덱스 2 주입은 _commit_pair의 교체 순서(config.toml → AGENTS.md)와
                # 결합 — 페어 구성·순서 변경 시 이 인덱스를 갱신한다(T-3).
                calls.append(Path(dst).name)
                if len(calls) == 2:
                    raise OSError('injected second-replace failure')
                return real_replace(src, dst)

            with mock.patch('deploy_global.os.replace', side_effect=fail_second):
                with self.assertRaises(OSError):
                    deploy_global._commit_pair(
                        ((config, 'new config'), (agents, 'new agents')), work)

            self.assertEqual(config.read_bytes(), b'old config line1\r\nold config line2\r\n')
            self.assertEqual(agents.read_bytes(), b'old agents\r\n')
            self.assertFalse([p for p in work.iterdir() if p.name.startswith('.')])

    def test_j_top_level_override_message_names_region(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            (home / 'config.toml').write_text(CONFIG_ROOT_OVERRIDE)
            config_before = (home / 'config.toml').read_bytes()
            agents_before = (home / 'AGENTS.md').read_bytes()
            claude_mirror = home / 'claude-mirror' / 'effort-router'

            result = _run(home, claude_mirror)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertIn('top-level', report['error'])
            self.assertNotIn('RISK-3', report['error'])   # R-2 — 내부 라벨 미노출
            self.assertEqual((home / 'config.toml').read_bytes(), config_before)
            self.assertEqual((home / 'AGENTS.md').read_bytes(), agents_before)

    def test_k_non_utf8_config_reports_json_error(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            (home / 'config.toml').write_bytes(b'\xff\xfeinvalid\n[agents]\n')
            before = _live_bytes(home)
            claude_mirror = home / 'claude-mirror' / 'effort-router'

            result = _run(home, claude_mirror)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertIn('error', report)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(_live_bytes(home), before)
            self.assertFalse((home / 'backups').exists())


if __name__ == '__main__':
    unittest.main()
