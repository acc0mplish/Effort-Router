"""Exercise the fixed global routing verifier in an isolated Codex home."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CodexRoutingTests(unittest.TestCase):
    def test_current_install_and_stale_role_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            skill = home / 'skills' / 'effort-router'
            (skill / 'agents').mkdir(parents=True)
            (skill / 'platforms').mkdir()
            shutil.copy(ROOT / 'SKILL.md', skill)
            shutil.copy(ROOT / 'agents/openai.yaml', skill / 'agents')
            shutil.copy(ROOT / 'platforms/codex.md', skill / 'platforms')
            shutil.copytree(ROOT / 'platforms/codex-agents', home / 'agents')
            (home / 'config.toml').write_text(
                'model = "gpt-6-luna"\nmodel_reasoning_effort = "max"\n'
                '[agents]\nenabled = true\n')
            (home / 'AGENTS.md').write_text(
                'effort-router GPT-6-Luna GPT-6-Sol max 실패 기반 영구 예방 규칙 '
                '과거 실패 1건 CLAUDE.md .cursorrules')

            def verify():
                return subprocess.run(
                    [sys.executable, str(ROOT / 'scripts/verify_global_install.py')],
                    env=dict(os.environ, CODEX_HOME=str(home)),
                    capture_output=True, text=True)

            result = verify()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('custom agents: 10/10', result.stdout)

            path = home / 'agents' / 'review-pr-high.toml'
            original = path.read_text()
            path.write_text(original.replace('model = "gpt-6-sol"', 'model = "gpt-6-luna"', 1))
            result = verify()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('agent review-pr-high expected', result.stdout)

            path.write_text(original)
            path = home / 'agents' / 'plan-high.toml'
            original = path.read_text()
            path.write_text(original.replace('model = "gpt-6-sol"', 'model = "gpt-6-luna"', 1))
            update = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/configure_codex_plan.py'),
                 '--agents-dir', str(home / 'agents'), '--apply'],
                capture_output=True, text=True)
            self.assertEqual(update.returncode, 0, update.stderr)
            self.assertIn('plan-high', update.stdout)
            self.assertEqual(verify().returncode, 0)


if __name__ == '__main__':
    unittest.main()
