"""Check static role routing, preservation, backups, and idempotence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/configure_codex_plan.py'
EXPECTED = {
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


class FixedRoutingTests(unittest.TestCase):
    def run_cli(self, *args, env_extra=None):
        env = dict(os.environ, **(env_extra or {}))
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)

    @staticmethod
    def _stale_plan_high(agents):
        stale = agents / 'plan-high.toml'
        stale.write_text(stale.read_text().replace('model = "gpt-6.1-sol"', 'model = "gpt-6-luna"', 1))
        return stale.read_text()

    def test_apply_preserves_custom_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            # 커스텀 보존·백업 단언은 변경 대상 역할에 붙인다 — review-pr-high 템플릿이
            # 기대값과 일치한 뒤(커밋 73d3712)로는 변경 대상에서 제외돼 백업이 안 생긴다.
            stale = agents / 'plan-high.toml'
            stale.write_text(self._stale_plan_high(agents))
            stale.write_text(stale.read_text() + '\nsandbox_mode = "read-only"\n')
            original = stale.read_text()
            backup_env = {'EFFORT_ROUTER_BACKUP_ROOT': str(home / 'backups')}

            preview = self.run_cli('--agents-dir', str(agents), env_extra=backup_env)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            preview_report = json.loads(preview.stdout)
            self.assertIn('plan-high', preview_report['changed_roles'])
            self.assertIn('gpt-6-luna', stale.read_text())

            result = self.run_cli('--agents-dir', str(agents), '--apply', env_extra=backup_env)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['restart_required'])
            self.assertTrue(report['backup_dir'])
            self.assertEqual((Path(report['backup_dir']) / stale.name).read_text(), original)

            for name, (model, effort) in EXPECTED.items():
                data = tomllib.loads((agents / f'{name}.toml').read_text())
                self.assertEqual((data['model'], data['model_reasoning_effort']), (model, effort))
            self.assertEqual(tomllib.loads(stale.read_text())['sandbox_mode'], 'read-only')

            result = self.run_cli('--agents-dir', str(agents), '--apply', env_extra=backup_env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['restart_required'])

    def test_backup_root_outside_scan_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            backup_root = home / 'backups'
            original = self._stale_plan_high(agents)

            result = self.run_cli(
                '--agents-dir', str(agents), '--apply',
                env_extra={'EFFORT_ROUTER_BACKUP_ROOT': str(backup_root)})
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            # LOW-9 안내 키 — 기존 키 불변·추가만.
            self.assertIn('scripts/deploy_global.py', report['hint'])
            # (1) 백업이 임시 백업 루트 하위에 생성된다.
            self.assertTrue(Path(report['backup_dir']).is_relative_to(backup_root))
            # (2) 역할 스캔 루트(agents 트리)에 도트 백업 디렉터리가 생기지 않는다.
            self.assertFalse((agents / '.effort-router-backups').exists())
            # (3) 백업 사본 내용이 원본과 일치한다.
            self.assertEqual((Path(report['backup_dir']) / 'plan-high.toml').read_text(), original)

    def test_backup_root_inside_agents_tree_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory) / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            self._stale_plan_high(agents)
            before = {p.name: p.read_bytes() for p in agents.glob('*.toml')}

            result = self.run_cli(
                '--agents-dir', str(agents), '--apply',
                env_extra={'EFFORT_ROUTER_BACKUP_ROOT': str(agents / 'nested')})
            self.assertEqual(result.returncode, 1)
            # RISK-5c — 거부 시 라이브 미변경.
            self.assertEqual(before, {p.name: p.read_bytes() for p in agents.glob('*.toml')})

    def test_stale_backups_reported_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            backup_root = home / 'backups'
            configure_root = backup_root / 'configure'
            configure_root.mkdir(parents=True)
            for index in range(11):
                (configure_root / f'snap-{index:03d}').mkdir()
            self._stale_plan_high(agents)

            result = self.run_cli(
                '--agents-dir', str(agents), '--apply',
                env_extra={'EFFORT_ROUTER_BACKUP_ROOT': str(backup_root)})
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            stale = report['stale_backups']
            self.assertEqual(len(stale), 1)
            self.assertTrue(stale[0].endswith('snap-000'))
            # 자동 삭제 금지 — 보고만.
            self.assertTrue((configure_root / 'snap-000').exists())

    def test_invalid_role_prevents_partial_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory) / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            (agents / 'security-audit.toml').write_text('invalid TOML !')
            before = {p.name: p.read_bytes() for p in agents.glob('*.toml')}
            result = self.run_cli('--agents-dir', str(agents), '--apply')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in agents.glob('*.toml')})


if __name__ == '__main__':
    unittest.main()
