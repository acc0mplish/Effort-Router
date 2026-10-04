"""Exercise layered duplicate role detection in an isolated Codex home."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _fixture(home: Path) -> None:
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


def _verify(home: Path):
    return subprocess.run(
        [sys.executable, str(ROOT / 'scripts/verify_global_install.py')],
        env=dict(os.environ, CODEX_HOME=str(home)),
        capture_output=True, text=True)


def _failure_lines(result) -> list[str]:
    # exit 1 경로에서만 `- ` 접두 라인이 failure다 — PASS 경로의 `- ` 라인은 정보성.
    if result.returncode == 0:
        return []
    return [line for line in result.stdout.splitlines() if line.startswith('- ')]


class DuplicateDetectionTests(unittest.TestCase):
    def _clean_baseline(self, home: Path):
        result = _verify(home)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.returncode, len(_failure_lines(result))

    def test_dot_directory_duplicate_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            clean_exit, clean_failures = self._clean_baseline(home)
            self.assertEqual((clean_exit, clean_failures), (0, 0))

            copy = home / 'agents' / '.effort-router-backups' / '20260930T000000Z'
            copy.mkdir(parents=True)
            shutil.copy(home / 'agents' / 'plan-high.toml', copy)

            result = _verify(home)
            self.assertEqual(result.returncode, 1)
            self.assertIn('duplicate role plan-high: 2 files', result.stdout)
            # 중복 1항 + fixture config 기대항(0) — 총수 정확 일치.
            self.assertEqual(len(_failure_lines(result)), 1)

    def test_non_dot_subdirectory_copy_is_warning_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            clean_exit, clean_failures = self._clean_baseline(home)

            copy = home / 'agents' / 'user-backup'
            copy.mkdir()
            shutil.copy(home / 'agents' / 'plan-high.toml', copy)

            result = _verify(home)
            # RISK-6 — 비도트 하위 디렉터리는 failure로 승격되지 않는다.
            self.assertEqual(result.returncode, clean_exit)
            self.assertEqual(len(_failure_lines(result)), clean_failures)
            self.assertIn('unexpected role file (warning)', result.stdout)

    def test_unknown_standalone_stem_is_warning_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _fixture(home)
            clean_exit, clean_failures = self._clean_baseline(home)

            custom = home / 'agents' / 'user-backup'
            custom.mkdir()
            (custom / 'custom-role.toml').write_text('model = "gpt-6-luna"\n')

            result = _verify(home)
            self.assertEqual(result.returncode, clean_exit)
            self.assertEqual(len(_failure_lines(result)), clean_failures)
            self.assertIn('unexpected role file (warning)', result.stdout)


if __name__ == '__main__':
    unittest.main()
