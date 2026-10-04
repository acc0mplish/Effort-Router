"""Check policy refusal and retained legacy helpers in isolated home trees."""
import contextlib
import io
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


sys.path.insert(0, str(ROOT / "scripts"))
import deploy_global


class DeployGlobalTests(unittest.TestCase):
    def _tree_bytes(self, home):
        return {str(p.relative_to(home)): p.read_bytes()
                for p in home.rglob('*') if p.is_file()}

    def _assert_cli_blocked_without_changes(self, *extra):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            before = self._tree_bytes(home)
            result = _run(home, home / 'claude-mirror/effort-router', *extra)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['dry_run'], '--dry-run' in extra)
            self.assertIn('Astra local policy', report['error'])
            self.assertIn('LOCAL-INSTALL.md', report['error'])
            self.assertIn('configure_codex_plan.py', report['error'])
            self.assertIsNone(report['backup_dir'])
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(self._tree_bytes(home), before)
            self.assertFalse((home / 'backups').exists())

    def test_a_dry_run_is_blocked_without_changes(self):
        self._assert_cli_blocked_without_changes('--dry-run')

    def test_b_full_deploy_is_blocked_without_changes(self):
        self._assert_cli_blocked_without_changes()

    def test_policy_guard_does_not_invoke_legacy_pipeline(self):
        for extra in ([], ['--dry-run']):
            with self.subTest(extra=extra), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(sys, 'argv', [str(SCRIPT), *extra]))
                for name in ('_guard_paths', '_precheck', '_expected_content', '_snapshot',
                             '_deploy_roles', '_sync_mirrors'):
                    function = stack.enter_context(mock.patch.object(deploy_global, name))
                    stack.callback(function.assert_not_called)
                output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                self.assertEqual(deploy_global.main(), 1)
                self.assertIn('Astra local policy', json.loads(output.getvalue())['error'])

    # Retain legacy helper coverage; the guarded CLI no longer reaches these helpers.
    def test_c_legacy_replacements_preserve_root_and_are_idempotent(self):
        config, counts = deploy_global._replace_config(CONFIG_OLD)
        agents, agent_counts = deploy_global._replace_agents_md(AGENTS_OLD)
        deploy_global._validate_replacements(config, agents)
        before, after = tomllib.loads(CONFIG_OLD), tomllib.loads(config)
        self.assertEqual(deploy_global._top_level_state(before), deploy_global._top_level_state(after))
        self.assertEqual(set(before), set(after))
        self.assertEqual(after['profiles']['planning']['model_reasoning_effort'], 'high')
        self.assertGreater(sum(counts.values()) + sum(agent_counts.values()), 0)
        for stale in ('xhigh`를', 'Sol·xhigh', 'model_reasoning_effort="xhigh"',
                      '| high | 별도 지시'):
            self.assertNotIn(stale, agents)
        self.assertIn('| high | 계획 및 고난도 추론의', agents)
        self.assertIn('| xhigh | 별도 지시', agents)
        next_config, counts = deploy_global._replace_config(config)
        next_agents, agent_counts = deploy_global._replace_agents_md(agents)
        self.assertEqual((next_config, next_agents), (config, agents))
        self.assertEqual(sum(counts.values()) + sum(agent_counts.values()), 0)

    def test_d_legacy_precheck_rejects_dot_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            duplicate = home / 'agents/.effort-router-backups/20261001T000000Z'
            duplicate.mkdir(parents=True)
            (duplicate / 'plan-high.toml').write_bytes((home / 'agents/plan-high.toml').read_bytes())
            before = self._tree_bytes(home)
            mirrors = deploy_global._mirror_roots(home, home / 'claude-mirror/effort-router')
            with self.assertRaisesRegex(ValueError, 'duplicate roles'):
                deploy_global._precheck(home, mirrors)
            self.assertEqual(self._tree_bytes(home), before)

    def test_e_legacy_validation_rejects_unknown_residue_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            agents = home / 'AGENTS.md'
            agents.write_text(agents.read_text() + '변형형 잔존: GPT-6.1-SOL / XHIGH\n')
            before = self._tree_bytes(home)
            config_new, agents_new, _, _ = deploy_global._expected_content(home)
            with self.assertRaisesRegex(ValueError, 'Unknown legacy pattern'):
                deploy_global._validate_replacements(config_new, agents_new)
            self.assertEqual(self._tree_bytes(home), before)

    def test_f_legacy_mirror_helpers_preserve_snapshot_and_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            mirrors = deploy_global._mirror_roots(home, home / 'claude-mirror/effort-router')
            drifted = mirrors['codex'] / 'SKILL.md'
            drifted.write_text('user edited drift\n')
            self.assertIn({'mirror': 'codex', 'path': 'SKILL.md'}, deploy_global._mirror_drift(mirrors))
            snapshot, count = deploy_global._snapshot(home / 'backups', home, mirrors)
            self.assertGreater(count, 0)
            self.assertEqual((snapshot / 'mirrors/codex/SKILL.md').read_text(), 'user edited drift\n')
            synced = deploy_global._sync_mirrors(mirrors)
            self.assertEqual(synced, len(mirrors) * len(deploy_global.MIRROR_MANIFEST))
            self.assertEqual(drifted.read_bytes(), (ROOT / 'SKILL.md').read_bytes())
            self.assertEqual(deploy_global._mirror_drift(mirrors), [])

    def test_g_legacy_path_guards_reject_unfamiliar_mirror_and_nested_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            empty = home / 'empty-mirror'
            empty.mkdir()
            with self.assertRaisesRegex(ValueError, 'unfamiliar mirror'):
                deploy_global._guard_paths((home / 'backups').resolve(), empty, home)
            with self.assertRaisesRegex(ValueError, 'role scan tree'):
                deploy_global._guard_paths((home / 'agents/nested').resolve(), home / 'claude-mirror/effort-router', home)
            self.assertFalse((home / 'backups').exists())

    def test_h_legacy_reader_rejects_non_utf8_agents_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            (home / 'AGENTS.md').write_bytes(b'\xff\xfeinvalid utf-8\n')
            before = self._tree_bytes(home)
            with self.assertRaises(UnicodeDecodeError):
                deploy_global._expected_content(home)
            self.assertEqual(self._tree_bytes(home), before)
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

    def test_j_legacy_top_level_diagnostic_names_region(self):
        config, _ = deploy_global._replace_config(CONFIG_ROOT_OVERRIDE)
        agents, _ = deploy_global._replace_agents_md(AGENTS_OLD)
        self.assertEqual(config, CONFIG_ROOT_OVERRIDE)
        with self.assertRaisesRegex(ValueError, 'top-level') as error:
            deploy_global._validate_replacements(config, agents)
        self.assertNotIn('RISK-3', str(error.exception))

    def test_k_legacy_reader_rejects_non_utf8_config_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            (home / 'config.toml').write_bytes(b'\xff\xfeinvalid\n[agents]\n')
            before = self._tree_bytes(home)
            with self.assertRaises(UnicodeDecodeError):
                deploy_global._expected_content(home)
            self.assertEqual(self._tree_bytes(home), before)
            self.assertFalse((home / 'backups').exists())


if __name__ == '__main__':
    unittest.main()
