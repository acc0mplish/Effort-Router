#!/usr/bin/env python3
"""r23 검증 핀 게이트 단위테스트 — 임시 git 저장소 fixture로 분기 전수(T1~T18).

테스트는 subprocess로 CLI를 실행한다(test_jev_judge 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다. RED 단계(verify_pin.py 부재·신규
분기 미구현)에서는 해당 테스트가 실패한다.
claims 대응: T1~T15 = 번들 §4 C1~C15, T16 = R3 fnmatch 경계, T17 = C21(비ASCII
quotePath 우회), T18 = C22(은닉 우회), T19 = C23(multipurpose 은닉),
C16 = 본 파일 전체 exit 0.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PIN = ROOT / 'scripts/verify_pin.py'

# 부모 환경 오염 차단(번들 §5 fixture 계약) — fixture git과 게이트 subprocess 모두 적용
FIXTURE_ENV_KEYS = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_GLOBAL')
GIT_IDENTITY = ('-c', 'user.email=verify-pin-test@example.com',
                '-c', 'user.name=verify-pin-test')


def clean_env():
    env = dict(os.environ)
    for key in FIXTURE_ENV_KEYS:
        env.pop(key, None)
    return env


def git(repo, *args):
    return subprocess.run(['git', '-c', 'core.autocrlf=false', *GIT_IDENTITY, *args],
                          cwd=repo, capture_output=True, text=True, env=clean_env())


def head_sha(repo):
    completed = git(repo, 'rev-parse', 'HEAD')
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def write_file(repo, name, content):
    path = Path(repo) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def run_pin(repo, *args):
    return subprocess.run([sys.executable, str(VERIFY_PIN), *args],
                          cwd=repo, capture_output=True, text=True, env=clean_env())


class VerifyPinCliTests(unittest.TestCase):
    """T1~T16 — claims 대응표(번들 §4 (Tn) 표기) 그대로."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def make_repo(self):
        """패턴 비통과 파일 3종뿐인 초기 커밋 저장소 — src 전용 변경이 clean 기준선."""
        repo = self.root / 'repo'
        repo.mkdir()
        write_file(repo, 'docs/readme.md', 'readme\n')
        write_file(repo, 'src/main.py', 'print("main")\n')
        write_file(repo, 'pyproject.toml', '[project]\nname = "fixture"\n')
        self.assertEqual(git(repo, '-c', 'advice.defaultBranch=false',
                             'init').returncode, 0)
        self.assertEqual(git(repo, 'add', '-A').returncode, 0)
        self.assertEqual(git(repo, 'commit', '-m', 'init').returncode, 0)
        return repo

    def commit_all(self, repo, message):
        self.assertEqual(git(repo, 'add', '-A').returncode, 0)
        self.assertEqual(git(repo, 'commit', '-m', message).returncode, 0)

    def test_t1_clean_src_commit_passes(self):
        # C1 — 초기 커밋 + src 전용 변경 커밋: exit 0 ∧ ok ∧ flags [] ∧ head_sha 일치
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'src/main.py', 'print("changed")\n')
        self.commit_all(repo, 'src change')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['ok'])
        self.assertEqual(output['flags'], [])
        self.assertEqual(output['gate'], 'verify-pin')
        self.assertEqual(output['head_sha'], head_sha(repo))

    def test_t2_committed_test_file_flagged(self):
        # C2 — tests/test_a.py 추가 커밋: exit 1 ∧ modified ∧ verification_input_modified
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'tests/test_a.py', 'def test_a():\n    assert True\n')
        self.commit_all(repo, 'add test')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['verification_input']['status'], 'modified')
        self.assertIn('verification_input_modified', output['flags'])
        self.assertIn('tests/test_a.py', output['verification_input']['modified_files'])

    def test_t3_untracked_new_verification_inputs_flagged(self):
        # C3(H1) — untracked 신규 2종(tests/test_new.py·conftest.py): 둘 다 검출
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'tests/test_new.py', 'def test_new():\n    assert True\n')
        write_file(repo, 'conftest.py', 'import pytest\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        modified = output['verification_input']['modified_files']
        self.assertIn('tests/test_new.py', modified)
        self.assertIn('conftest.py', modified)
        self.assertIn('verification_input_modified', output['flags'])

    def test_t4_staged_only_flagged(self):
        # C4(H1) — staged 전용(git add 후 미커밋): 검출
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'tests/test_b.py', 'def test_b():\n    assert True\n')
        self.assertEqual(git(repo, 'add', 'tests/test_b.py').returncode, 0)
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        self.assertIn('verification_input_modified', json.loads(result.stdout)['flags'])

    def test_t5_non_matching_changes_stay_clean(self):
        # C5(H1 LOW) — 패턴 비통과 untracked·변경(notes.txt·docs/readme.md): 오탐 없음
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'notes.txt', 'memo\n')
        write_file(repo, 'docs/readme.md', 'changed\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['verification_input']['status'], 'clean')
        self.assertEqual(output['verification_input']['modified_files'], [])

    def test_t6_worktree_modified_test_flagged(self):
        # C6 — 커밋 없이 기존 테스트 파일 작업 트리 수정(약화): 검출
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'tests/test_a.py', 'def test_a():\n    assert True\n')
        self.commit_all(repo, 'add test')
        write_file(repo, 'tests/test_a.py', 'def test_a():\n    assert False\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        self.assertIn('verification_input_modified', json.loads(result.stdout)['flags'])

    def test_t7_extra_pattern_two_way(self):
        # C7 — --pattern 'e2e/*' 추가 시 e2e/spec.yaml 검출, 미지정 시 미검출(양방향)
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'e2e/spec.yaml', 'step: open\n')
        without = run_pin(repo, '--base', init)
        self.assertEqual(without.returncode, 0, without.stderr)
        self.assertEqual(
            json.loads(without.stdout)['verification_input']['modified_files'], [])
        with_pattern = run_pin(repo, '--base', init, '--pattern', 'e2e/*')
        self.assertEqual(with_pattern.returncode, 1)
        output = json.loads(with_pattern.stdout)
        self.assertIn('e2e/spec.yaml', output['verification_input']['modified_files'])
        self.assertIn('e2e/*', output['verification_input']['patterns'])

    def test_t8_multipurpose_separate_flag(self):
        # C8(H5) — pyproject.toml: multipurpose 플래그 ∧ verification_input은 clean(분리 실증)
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'pyproject.toml',
                   '[project]\nname = "fixture"\n\n'
                   '[tool.pytest.ini_options]\naddopts = "-p no:cacheprovider"\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('multipurpose_config_modified', output['flags'])
        self.assertNotIn('verification_input_modified', output['flags'])
        self.assertEqual(output['verification_input']['status'], 'clean')
        self.assertIn('pyproject.toml', output['verification_input']['multipurpose_files'])

    def test_t9_expect_sha_two_way(self):
        # C9 — --expect-sha 정답: sha_matched true·플래그 없음 / 오답: exit 1 ∧ sha_mismatch
        repo = self.make_repo()
        current = head_sha(repo)
        good = run_pin(repo, '--expect-sha', current)
        self.assertEqual(good.returncode, 0, good.stderr)
        good_output = json.loads(good.stdout)
        self.assertTrue(good_output['pin']['sha_matched'])
        self.assertEqual(good_output['flags'], [])
        bad = run_pin(repo, '--expect-sha', '0' * 40)
        self.assertEqual(bad.returncode, 1)
        bad_output = json.loads(bad.stdout)
        self.assertFalse(bad_output['pin']['sha_matched'])
        self.assertIn('sha_mismatch', bad_output['flags'])

    def test_t10_no_base_not_evaluated(self):
        # C10(M-d) — --base 미지정: not_evaluated(미검사 ≠ 변경 없음) ∧ exit 0
        repo = self.make_repo()
        result = run_pin(repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['verification_input']['status'], 'not_evaluated')
        self.assertIsNone(output['pin']['base_ref'])
        self.assertIsNone(output['pin']['base_sha'])
        self.assertIsNone(output['pin']['sha_matched'])
        self.assertIsNone(output['verify_cmd'])

    def test_t11_verify_cmd_success(self):
        # C11 — exit 0 명령: verify_cmd.exit_code==0 ∧ 게이트 exit 0
        repo = self.make_repo()
        result = run_pin(repo, '--verify-cmd', f'{sys.executable} -c pass')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['verify_cmd']['exit_code'], 0)
        self.assertFalse(output['verify_cmd']['timed_out'])
        self.assertEqual(output['flags'], [])

    def test_t12_verify_cmd_failure_flag(self):
        # C12 — exit 3 명령: verify_cmd_failed ∧ 게이트 exit 1
        repo = self.make_repo()
        result = run_pin(repo, '--verify-cmd',
                         f'{sys.executable} -c "raise SystemExit(3)"')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('verify_cmd_failed', output['flags'])
        self.assertEqual(output['verify_cmd']['exit_code'], 3)

    def test_t13_verify_cmd_timeout_exclusive(self):
        # C13(LOW) — 타임아웃: verify_cmd_timeout 단독(failed 배타) ∧ exit_code null ∧ exit 1
        repo = self.make_repo()
        result = run_pin(repo, '--verify-cmd', 'sleep 5', '--timeout', '1')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('verify_cmd_timeout', output['flags'])
        self.assertNotIn('verify_cmd_failed', output['flags'])
        self.assertIsNone(output['verify_cmd']['exit_code'])
        self.assertTrue(output['verify_cmd']['timed_out'])

    def test_t14_save_audit_file(self):
        # C14 — --save DIR: verify-pin-*.json 1개 ∧ 파일 head_sha == stdout head_sha
        repo = self.make_repo()
        save_dir = self.root / 'audit'
        result = run_pin(repo, '--save', str(save_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIsNotNone(output['saved_to'])
        files = list(save_dir.glob('verify-pin-*.json'))
        self.assertEqual(len(files), 1)
        saved = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertEqual(saved['head_sha'], output['head_sha'])

    def test_t15_config_error_quadruple(self):
        # C15(M-f·M-i) — 오류 4종 전부 exit 2 ∧ stderr FAIL. save 실패만 stdout JSON 유지
        repo = self.make_repo()
        non_repo = self.root / 'plain'
        non_repo.mkdir()
        cases = (
            ('non git directory', run_pin(non_repo)),
            ('invalid base ref', run_pin(repo, '--base', 'no-such-ref')),
            ('negative timeout', run_pin(repo, '--timeout', '-1')),
        )
        for name, result in cases:
            self.assertEqual(result.returncode, 2, name)
            self.assertIn('FAIL', result.stderr, name)
            self.assertFalse(result.stdout.strip(), name)
        existing = write_file(repo, 'not-a-dir', 'blocked\n')
        failed_save = run_pin(repo, '--save', str(existing))
        self.assertEqual(failed_save.returncode, 2)
        self.assertIn('FAIL', failed_save.stderr)
        output = json.loads(failed_save.stdout)
        self.assertIsNone(output['saved_to'])

    def test_t16_fnmatch_nested_and_case(self):
        # C16/R3 — fnmatchcase 결정론: 중첩 경로 검출(*의 / 관통) ∧ 대소문자 비일치 미검출
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'tests/unit/test_x.py', 'def test_x():\n    assert True\n')
        write_file(repo, 'TESTS/unit_x.yaml', 'not: matching\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        modified = output['verification_input']['modified_files']
        self.assertIn('tests/unit/test_x.py', modified)
        self.assertNotIn('TESTS/unit_x.yaml', modified)
        self.assertNotIn('TESTS/unit_x.yaml',
                         output['verification_input']['multipurpose_files'])

    def test_t17_non_ascii_paths_detected(self):
        # C21(④ HIGH-2) — quotePath 인용 우회 차단: 비ASCII untracked 신규 ∧ tracked 수정
        # 양쪽 검출. quotePath 기본값은 비ASCII 경로를 C-인용해 fnmatch를 무력화한다.
        repo = self.make_repo()
        init = head_sha(repo)
        write_file(repo, 'tests/test_가나다.py', 'def test_a():\n    assert True\n')
        self.commit_all(repo, 'add non-ascii test')
        write_file(repo, 'tests/test_가나다.py', 'def test_a():\n    assert False\n')
        write_file(repo, 'tests/test_한글.py', 'def test_h():\n    assert True\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        modified = output['verification_input']['modified_files']
        self.assertIn('tests/test_가나다.py', modified)
        self.assertIn('tests/test_한글.py', modified)
        self.assertIn('verification_input_modified', output['flags'])

    def test_t18_hidden_verification_input_flagged(self):
        # C22(④ HIGH-1) — assume-unchanged·skip-worktree 은닉(④리뷰 재현 순서 그대로):
        # 앵커 시점에 테스트가 이미 커밋돼 있고(인덱스==base), update-index 후 worktree
        # 약화하면 diff·status가 모두 마비된다 — ls-files -v 태그(h·S)로 검출한다.
        repo = self.make_repo()
        write_file(repo, 'tests/test_a.py', 'def test_a():\n    assert True\n')
        write_file(repo, 'tests/test_b.py', 'def test_b():\n    assert True\n')
        self.commit_all(repo, 'add tests')
        init = head_sha(repo)
        self.assertEqual(git(repo, 'update-index', '--assume-unchanged',
                             'tests/test_a.py').returncode, 0)
        self.assertEqual(git(repo, 'update-index', '--skip-worktree',
                             'tests/test_b.py').returncode, 0)
        write_file(repo, 'tests/test_a.py', 'def test_a():\n    assert False\n')
        write_file(repo, 'tests/test_b.py', 'def test_b():\n    assert False\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('verification_input_hidden', output['flags'])
        hidden = output['verification_input']['hidden_files']
        self.assertIn('tests/test_a.py', hidden)
        self.assertIn('tests/test_b.py', hidden)
        # 은닉이 diff·status를 마비시켰음의 증명 — modified는 비어 있고 은닉만이 신호다
        self.assertEqual(output['verification_input']['modified_files'], [])
        self.assertEqual(output['verification_input']['status'], 'clean')

    def test_t19_hidden_multipurpose_flagged(self):
        # C23(④ 재리뷰 HIGH) — multipurpose 그룹 은닉: 그룹 구분 없이 검출한다.
        # skip-worktree + addopts 무력화 수정 → 라운드1 게이트는 완전 clean 우회다.
        repo = self.make_repo()
        init = head_sha(repo)
        self.assertEqual(git(repo, 'update-index', '--skip-worktree',
                             'pyproject.toml').returncode, 0)
        write_file(repo, 'pyproject.toml',
                   '[project]\nname = "fixture"\n\n'
                   '[tool.pytest.ini_options]\naddopts = "-p no:cacheprovider"\n')
        result = run_pin(repo, '--base', init)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['flags'], ['verification_input_hidden'])
        self.assertIn('pyproject.toml', output['verification_input']['hidden_files'])
        # 완전 clean 우회 실증 — diff·multipurpose 스캔은 모두 마비되고 은닉만이 신호다
        self.assertEqual(output['verification_input']['multipurpose_files'], [])
        self.assertEqual(output['verification_input']['status'], 'clean')


if __name__ == '__main__':
    unittest.main()
