"""Plan-specific routing must preserve custom settings and reject uncertainty."""
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


class PlanRoutingTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_plus_pro_roundtrip_preserves_custom_settings_and_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory) / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            custom = agents / 'review-pr-high.toml'
            custom.write_text(custom.read_text() + '\nsandbox_mode = "read-only"\n')
            original = custom.read_text()
            for plan, effort in [('plus', 'medium'), ('pro', 'high')]:
                result = self.run_cli('--plan', plan, '--agents-dir', str(agents), '--apply')
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['review_effort'], effort)
                self.assertTrue(report['restart_required'])
                for path in agents.glob('*.toml'):
                    data = tomllib.loads(path.read_text())
                    expected = 'max' if data['model'] == 'gpt-5.6-luna' else 'medium' if path.stem in ('plan-high', 'plan-xhigh') else effort
                    self.assertEqual(data['model_reasoning_effort'], expected)
                self.assertEqual(tomllib.loads(custom.read_text())['sandbox_mode'], 'read-only')
                if plan == 'plus':
                    self.assertEqual((Path(report['backup_dir']) / custom.name).read_text(), original)
            result = self.run_cli('--plan', 'pro', '--agents-dir', str(agents), '--apply')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['restart_required'])

    def test_read_only_and_unknown_do_not_mutate(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory) / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            before = {p.name: p.read_bytes() for p in agents.iterdir()}
            result = self.run_cli('--plan', 'plus', '--agents-dir', str(agents))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['review_effort'], 'medium')
            result = self.run_cli('--plan', 'unknown', '--agents-dir', str(agents), '--apply')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in agents.iterdir()})

    def test_auto_detection_protocol_and_failure_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for account, expected in [({'type': 'chatgpt', 'planType': 'plus'}, 0),
                                      ({'type': 'chatgpt', 'planType': 'pro'}, 0),
                                      ({'type': 'chatgpt', 'planType': 'business'}, 1),
                                      ({'type': 'apiKey'}, 1), (None, 1)]:
                fake = base / 'codex'
                fake.write_text('#!' + sys.executable + '\n' +
                    'import json,sys\n' +
                    'assert json.loads(input())["method"] == "initialize"\n' +
                    'print(json.dumps({"id":1,"result":{}}),flush=True)\n' +
                    'assert json.loads(input())["method"] == "initialized"\n' +
                    'request=json.loads(input())\n' +
                    'assert request["method"] == "account/read"\n' +
                    'assert request["params"] == {"refreshToken":False}\n' +
                    'print(json.dumps({"id":2,"result":{"account":' + repr(account) + '}}),flush=True)\n')
                fake.chmod(0o755)
                result = self.run_cli('--codex-bin', str(fake), '--agents-dir', str(base / 'agents'))
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected == 0:
                    report = json.loads(result.stdout)
                    self.assertEqual(report['plan'], account['planType'])
                    self.assertEqual(report['source'], 'account/read')
                self.assertFalse((base / 'agents').exists())
            fake.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(30)\n')
            result = self.run_cli('--codex-bin', str(fake), '--timeout', '0.1', '--apply', '--agents-dir', str(base / 'agents'))
            self.assertEqual(result.returncode, 1)
            self.assertIn('timed out', result.stderr)
            self.assertFalse((base / 'agents').exists())

    def test_invalid_role_prevents_partial_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory) / 'agents'
            shutil.copytree(ROOT / 'platforms/codex-agents', agents)
            (agents / 'security-audit.toml').write_text('invalid TOML !')
            before = {p.name: p.read_bytes() for p in agents.iterdir()}
            result = self.run_cli('--plan', 'plus', '--agents-dir', str(agents), '--apply')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in agents.iterdir()})


if __name__ == '__main__':
    unittest.main()
