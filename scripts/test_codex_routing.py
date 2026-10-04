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
                'model = "gpt-6-astra"\nmodel_reasoning_effort = "medium"\n'
                '[agents]\nenabled = true\n')
            (home / 'AGENTS.md').write_text(
                'effort-router GPT-6-Astra medium max 실패 기반 영구 예방 규칙 '
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
            path.write_text(original.replace('model = "gpt-6-astra"', 'model = "stale-model"', 1))
            result = verify()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('agent review-pr-high expected', result.stdout)

            path.write_text(original)
            path = home / 'agents' / 'plan-high.toml'
            original = path.read_text()
            path.write_text(original.replace('model = "gpt-6-astra"', 'model = "stale-model"', 1))
            update = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/configure_codex_plan.py'),
                 '--agents-dir', str(home / 'agents'), '--apply'],
                env=dict(os.environ, EFFORT_ROUTER_BACKUP_ROOT=str(home / 'backups')),
                capture_output=True, text=True)
            self.assertEqual(update.returncode, 0, update.stderr)
            self.assertIn('plan-high', update.stdout)
            self.assertEqual(verify().returncode, 0)

            config = home / 'config.toml'
            original = config.read_text()
            for model, effort, provider in (
                ('stale-model', 'medium', None),
                ('gpt-6-astra', 'ultra', None),
                ('gpt-6-astra', 'medium', 'different-provider'),
            ):
                with self.subTest(model=model, effort=effort, provider=provider):
                    profile = f'\n[profiles.fast]\nmodel = "{model}"\nmodel_reasoning_effort = "{effort}"\n'
                    if provider:
                        profile += f'model_provider = "{provider}"\n'
                    config.write_text(original + profile)
                    result = verify()
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('profile fast must', result.stdout)
            config.write_text(original)
            self.assertEqual(verify().returncode, 0)


if __name__ == '__main__':
    unittest.main()
