"""Check static role routing, preservation, backups, and idempotence."""
import json
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
    'plan-high': ('gpt-6-sol', 'xhigh'),
    'plan-xhigh': ('gpt-6-sol', 'xhigh'),
    'plan-adversary-xhigh': ('gpt-6-sol', 'xhigh'),
    'review-pr-high': ('gpt-6-sol', 'xhigh'),
    'review-pr-xhigh': ('gpt-6-sol', 'xhigh'),
    'security-audit': ('gpt-6-sol', 'xhigh'),
}


class FixedRoutingTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_apply_preserves_custom_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory) / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            custom = agents / 'review-pr-high.toml'
            custom.write_text(custom.read_text() + '\nsandbox_mode = "read-only"\n')
            original = custom.read_text()
            stale = agents / 'plan-high.toml'
            stale.write_text(stale.read_text().replace('model = "gpt-6-sol"', 'model = "gpt-6-luna"', 1))

            preview = self.run_cli('--agents-dir', str(agents))
            self.assertEqual(preview.returncode, 0, preview.stderr)
            preview_report = json.loads(preview.stdout)
            self.assertIn('plan-high', preview_report['changed_roles'])
            self.assertIn('gpt-6-luna', stale.read_text())

            result = self.run_cli('--agents-dir', str(agents), '--apply')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['restart_required'])
            self.assertTrue(report['backup_dir'])
            self.assertEqual((Path(report['backup_dir']) / custom.name).read_text(), original)

            for name, (model, effort) in EXPECTED.items():
                data = tomllib.loads((agents / f'{name}.toml').read_text())
                self.assertEqual((data['model'], data['model_reasoning_effort']), (model, effort))
            self.assertEqual(tomllib.loads(custom.read_text())['sandbox_mode'], 'read-only')

            result = self.run_cli('--agents-dir', str(agents), '--apply')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['restart_required'])

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
