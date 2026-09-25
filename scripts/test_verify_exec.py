#!/usr/bin/env python3
"""r26 검증 실행 엔진 단위테스트 — 프로세스 그룹·verify-window·fresh·영수증 전수.

테스트는 subprocess로 CLI를 실행한다(test_verify_pin 관습 — import 방식이면 수집
단계 ImportError로 RED가 성립하지 않는다). 모듈레벨 헬퍼는 test_verify_pin.py
패턴 복제(import 결합 없는 자족형 — r25 test_worktree_gate_hardening 선례 준용).
claims 대응: T24 = C3(생존자 감지·비파이프 orphan), T25 = C2(타임아웃 손자 종료),
T26 = C2b(파이프 상속 orphan — 유한 종료·분류 정확), T27 = C14(비POSIX 폴백),
T28 = C4(HEAD 이동), T29 = C5(tracked 변형), T30 = C6(untracked 검증입력 신규),
T31 = C7(산출물 무오탐), T32 = 불변 시 무플래그, T33 = C2c(실행 중 ps 실패 H2),
T34 = C8(fresh 기본 흐름), T35 = C9(fresh 은닉 무력화), T36 = C10(잔존 복구),
T37 = C11(remove 실패 부분 결과), T38 = C8b(fresh 단독 exit 2), T39 = C5b(fresh
실행 중 메인 tracked 변형), T40 = C10b(r24 이름 충돌 가드 H4), T41 = C12(증분
영수증 중간 보존), T42 = C13(최종 영수증 complete).
RED 근거: verify_exec.py 부재·신규 플래그 부재 단계에서 전패한다(리컨 P5·P6·H2
시나리오 — 현행 게이트는 생존자 무검출·파이프 행업·ps 실패 조용한 통과).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PIN = ROOT / 'scripts/verify_pin.py'

# 부모 환경 오염 차단(test_verify_pin fixture 계약) — fixture git과 게이트 subprocess
# 모두 적용. 파일 기반 전역 config 격리(RH-1)까지 동일 패턴.
FIXTURE_ENV_KEYS = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_GLOBAL')
GIT_IDENTITY = ('-c', 'user.email=verify-pin-test@example.com',
                '-c', 'user.name=verify-pin-test')

_ISOLATION_TMP = tempfile.TemporaryDirectory()
XDG_ISOLATION_DIR = os.path.join(_ISOLATION_TMP.name, 'xdg')
os.makedirs(XDG_ISOLATION_DIR, exist_ok=True)


def clean_env():
    env = dict(os.environ)
    for key in FIXTURE_ENV_KEYS:
        env.pop(key, None)
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    env['XDG_CONFIG_HOME'] = XDG_ISOLATION_DIR
    return env


def git(repo, *args):
    return subprocess.run(['git', '-c', 'core.autocrlf=false', *GIT_IDENTITY, *args],
                          cwd=repo, capture_output=True, text=True, env=clean_env())


def head_sha(repo):
    completed = git(repo, 'rev-parse', 'HEAD')
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def write_file(base, name, content):
    path = Path(base) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def run_pin(repo, *args, env_extra=None, path_prefix=None):
    """게이트 subprocess 호출 — path_prefix 지정 시 PATH 앞에 심 디렉터리(r25 패턴),
    env_extra['PATH']로 치환(T27 — ps 부재 환경)."""
    env = clean_env()
    if env_extra:
        env.update(env_extra)
    if path_prefix is not None:
        env['PATH'] = f'{path_prefix}:{env.get("PATH", "")}'
    return subprocess.run([sys.executable, str(VERIFY_PIN), *args],
                          cwd=str(repo), capture_output=True, text=True, env=env)


class VerifyExecEngineTests(unittest.TestCase):
    """T24~T42 — r26 실행 엔진 분기 전수(fixture는 test_verify_pin과 자체 중복)."""

    maxDiff = None

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        # r25 H2 가드 패턴 — 루트가 git 저장소 내부면 fail로 요란하게(skip 은닉 금지)
        inside = git(self.root, 'rev-parse', '--is-inside-work-tree')
        if inside.returncode == 0 and inside.stdout.strip() == 'true':
            self.fail(f'fixture 루트가 git 저장소 내부다({self.root}) — 호스트 오염 방지')

    def make_repo(self, name='repo'):
        """패턴 비통과 파일 3종뿐인 초기 커밋 저장소(test_verify_pin.make_repo 준용)."""
        repo = self.root / name
        repo.mkdir()
        write_file(repo, 'docs/readme.md', 'readme\n')
        write_file(repo, 'src/main.py', 'print("main")\n')
        write_file(repo, 'pyproject.toml', '[project]\nname = "fixture"\n')
        self.assertEqual(git(repo, '-c', 'advice.defaultBranch=false',
                             'init').returncode, 0)
        self.assertEqual(git(repo, 'add', '-A').returncode, 0)
        self.assertEqual(git(repo, 'commit', '-m', 'init').returncode, 0)
        return repo

    def make_ps_shim(self, exit_code):
        """PATH 선두 ps 심 — 실행 중 ps 실패(H2) 유도. shim 디렉터리 반환."""
        shim_dir = self.root / 'ps-shim'
        shim_dir.mkdir()
        ps = shim_dir / 'ps'
        ps.write_text(f'#!/bin/sh\nexit {exit_code}\n', encoding='utf-8')
        ps.chmod(0o755)
        return shim_dir

    # --- T24 — C3: 정상 종료 후 백그라운드 라이터 생존 감지(비파이프 orphan) ---

    def test_t24_background_writer_survivors_detected(self):
        # 직속 bash 즉시 종료(exit 0)·손자 서브셸은 /dev/null 리다이렉트로 파이프를
        # 잡지 않는다 — communicate는 정상 반환, 그룹 폴링이 생존자를 잡는다(P5 시나리오).
        repo = self.make_repo()
        marker = self.root / 'late-marker-t24'
        cmd = f"bash -c '( sleep 1.2; touch {marker} ) >/dev/null 2>&1 & echo started'"
        result = run_pin(repo, '--verify-cmd', cmd)
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn('verify_cmd_survivors', output['flags'])
        verify = output['verify_cmd']
        self.assertTrue(verify['survivors'])
        self.assertFalse(verify['timed_out'])
        self.assertEqual(verify['exit_code'], 0)
        self.assertTrue(verify['process_group'])
        # M11 — 게이트가 그룹 소멸 확인 후 종료 + 1.5s 고정 대기(late-write 1.2s + 여유)
        time.sleep(1.5)
        self.assertFalse(marker.exists(),
                         '생존자가 종료되지 않아 late-write 마커가 쓰였다')

    # --- T25 — C2: 타임아웃 시 SIGTERM 무시 손자까지 종료 ---

    def test_t25_timeout_kills_sigterm_ignoring_grandchild(self):
        # 직속 bash는 sleep 300(진성 타임아웃)·손자 서브셸은 trap "" TERM으로 SIGTERM
        # 무시 + 5s 뒤 late-write. 같은 pgid 잔류 — SIGKILL 폴링이 종료시킨다(H3 범위 내).
        repo = self.make_repo()
        marker = self.root / 'late-marker-t25'
        cmd = (f"bash -c '( trap \"\" TERM; sleep 5; touch {marker} ) >/dev/null 2>&1"
               f" & sleep 300'")
        result = run_pin(repo, '--verify-cmd', cmd, '--timeout', '1')
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn('verify_cmd_timeout', output['flags'])
        self.assertNotIn('verify_cmd_failed', output['flags'])
        verify = output['verify_cmd']
        self.assertIsNone(verify['exit_code'])
        self.assertTrue(verify['timed_out'])
        self.assertTrue(verify['process_group'])
        self.assertTrue(verify['group_killed'])
        self.assertFalse(verify['survivors'],
                         'SIGKILL 후 그룹은 소멸 — survivors는 독립 축(잔존 아님)')
        # M11 — 예정 write 시점(5s)을 넘긴 뒤 부재 검사(거짓 GREEN 방지)
        time.sleep(5.5)
        self.assertFalse(marker.exists(),
                         'SIGTERM 무시 손자가 종료되지 않아 마커가 쓰였다')

    # --- T26 — C2b: 파이프 상속 orphan — 유한 종료·정확 분류(리컨 P6) ---

    def test_t26_pipe_holding_orphan_finite_exit_and_classification(self):
        # 손자 sleep이 stdout 파이프를 상속(리다이렉트 없음) → 직속 bash 종료 후에도
        # communicate가 EOF를 못 받아 TimeoutExpired — poll() 판별로 (b) 경로 분류.
        # 현행 게이트는 이 앞에서 사실상 무한 대기한다(행업 결함).
        repo = self.make_repo()
        cmd = "bash -c 'sleep 30 & echo started'"
        result = run_pin(repo, '--verify-cmd', cmd, '--timeout', '2')
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        verify = output['verify_cmd']
        # 직속 자식은 정상 종료(0) — 성공한 검증의 타임아웃 오분류 금지(판별 규칙 b)
        self.assertEqual(verify['exit_code'], 0)
        self.assertFalse(verify['timed_out'])
        self.assertNotIn('verify_cmd_timeout', output['flags'])
        self.assertIn('verify_cmd_survivors', output['flags'])
        self.assertTrue(verify['survivors'])
        self.assertTrue(verify['group_killed'])
        # 유한 종료 증명 — 행업 시 unittest 자체가 시간 초과로 RED
        self.assertLess(verify['duration_s'], 15)

    # --- T27 — C14: 비POSIX 폴백 투명성(PATH에서 ps 제거) ---

    def test_t27_no_ps_fallback_transparent(self):
        # PATH를 git 심림크 하나뿐인 디렉터리로 치환 — shutil.which('ps') 실패 →
        # legacy 경로(process_group false)·기존 동작(성공·타임아웃 플래그) 불변.
        repo = self.make_repo()
        shim_dir = self.root / 'path-no-ps'
        shim_dir.mkdir()
        os.symlink(shutil.which('git'), shim_dir / 'git')
        env = clean_env()
        env['PATH'] = str(shim_dir)
        ok = run_pin(repo, '--verify-cmd', '/bin/echo ok', env_extra={'PATH': env['PATH']})
        self.assertEqual(ok.returncode, 0, ok.stderr)
        output = json.loads(ok.stdout)
        self.assertFalse(output['verify_cmd']['process_group'])
        self.assertIsNone(output['verify_cmd']['survivors'])
        self.assertIsNone(output['verify_cmd']['group_killed'])
        self.assertEqual(output['flags'], [])
        slow = run_pin(repo, '--verify-cmd', '/bin/sleep 5', '--timeout', '1',
                       env_extra={'PATH': env['PATH']})
        self.assertEqual(slow.returncode, 1)
        slow_output = json.loads(slow.stdout)
        self.assertIn('verify_cmd_timeout', slow_output['flags'])
        self.assertFalse(slow_output['verify_cmd']['process_group'])

    # --- T28~T32 — verify-window 전후 클린 검사 ---

    def test_t28_head_moved_during_verify(self):
        # C4 — verify-cmd가 empty commit으로 HEAD 이동 → head_moved_during_verify
        repo = self.make_repo()
        cmd = ("bash -c 'git -c user.email=t@t -c user.name=t "
               "commit --allow-empty -m move'")
        result = run_pin(repo, '--verify-cmd', cmd)
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn('head_moved_during_verify', output['flags'])
        self.assertTrue(output['verify_cmd']['window_delta']['head_moved'])

    def test_t29_tracked_mutation_during_verify(self):
        # C5 — verify-cmd가 tracked 파일 수정(unstaged) → verify_workspace_mutated
        repo = self.make_repo()
        result = run_pin(repo, '--verify-cmd', "bash -c 'echo appended >> src/main.py'")
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn('verify_workspace_mutated', output['flags'])
        self.assertTrue(any(record.endswith('src/main.py') for record
                            in output['verify_cmd']['window_delta']['tracked_changed']),
                        output['verify_cmd']['window_delta']['tracked_changed'])

    def test_t30_untracked_verification_input_new_during_verify(self):
        # C6 — 실행창 내 conftest.py 신규 생성 → 검증입력 패턴 매칭으로 변형 검출
        repo = self.make_repo()
        result = run_pin(repo, '--verify-cmd', "bash -c 'echo import pytest > conftest.py'")
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn('verify_workspace_mutated', output['flags'])
        self.assertIn('conftest.py',
                      output['verify_cmd']['window_delta']['untracked_new'])

    def test_t31_non_pattern_artifacts_no_false_flag(self):
        # C7 — 실행창 내 패턴 밖 untracked(캐시 등) 생성은 무플래그·exit 0 유지.
        # 델타 상세에는 기록된다(투명성) — 패턴 필터만 플래그를 막는다.
        repo = self.make_repo()
        result = run_pin(repo, '--verify-cmd',
                         "bash -c 'mkdir -p .pytest_cache && echo x > .pytest_cache/foo.txt'")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['flags'], [])
        self.assertEqual(output['verify_cmd']['window_delta']['untracked_new'],
                         ['.pytest_cache/foo.txt'])

    def test_t32_clean_verify_window_no_flags(self):
        # 불변 시 무플래그 — verify-cmd 성공 + 실행창 무변형 → 기존 clean 케이스 동일
        repo = self.make_repo()
        result = run_pin(repo, '--verify-cmd', '/bin/true')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['flags'], [])
        delta = output['verify_cmd']['window_delta']
        self.assertFalse(delta['head_moved'])
        self.assertEqual(delta['tracked_changed'], [])
        self.assertEqual(delta['untracked_new'], [])
        self.assertFalse(delta['exclude_changed'])

    # --- T33 — C2c: 실행 중 ps 실패(H2) — 조용한 통과 금지 ---

    def test_t33_ps_failure_midrun_exit2(self):
        # exit 1 ps 심이 PATH 선두 — probe는 which('ps') 성공으로 posix 경로 진입 후
        # 그룹 폴링 중 ps 실패 → exit 2(사유: 생존자 판정 불능)·stdout JSON 없음
        repo = self.make_repo()
        shim_dir = self.make_ps_shim(1)
        result = run_pin(repo, '--verify-cmd', '/bin/echo ok', path_prefix=shim_dir)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('FAIL verify pin', result.stderr)
        self.assertIn('생존자', result.stderr)
        self.assertFalse(result.stdout.strip())

    # --- T34~T40 — fresh-checkout 검증 모드 ---

    def make_git_shim_block_worktree_remove(self):
        """r25 PATH git 심 패턴 — worktree remove만 exit 1 실패 유도(자체 중복)."""
        real_git = shutil.which('git')
        assert real_git, 'git 실행 파일을 찾을 수 없다'
        shim_dir = self.root / 'git-shim-remove'
        shim_dir.mkdir()
        body = f'''#!/usr/bin/env python3
import subprocess, sys
RG = {real_git!r}; A = sys.argv[1:]
if any(A[i] == 'worktree' and A[i + 1] == 'remove' for i in range(len(A) - 1)):
    sys.stderr.write('fatal: shim blocked worktree remove\\n'); sys.exit(1)
sys.exit(subprocess.run([RG, *A]).returncode)
'''
        shim = shim_dir / 'git'
        shim.write_text(body, encoding='utf-8')
        shim.chmod(0o755)
        return shim_dir

    def container(self, repo):
        return repo.parent / f'{repo.name}-worktrees'

    def fresh_wt(self, repo):
        return self.container(repo) / 'verify-pin-fresh'

    def test_t34_fresh_basic_flow_reflects_commit_only(self):
        # C8 — dirty 메인 + --fresh-checkout: fresh는 커밋 내용만 반영(grep은 커밋
        # 버전의 print를 요구 — dirty 본문이면 실패할 명령) ∧ 종료 후 worktree·
        # .git/worktrees 소멸 ∧ 빈 컨테이너 rmdir(best-effort 성공) ∧ exit 0
        repo = self.make_repo()
        write_file(repo, 'src/main.py', 'DIRTY without print\n')  # 미커밋 dirty
        cmd = "bash -c 'grep -q print src/main.py'"
        result = run_pin(repo, '--verify-cmd', cmd, '--fresh-checkout')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['flags'], [])
        fresh = output['fresh']
        self.assertTrue(fresh['used'])
        self.assertEqual(fresh['checkout_sha'], head_sha(repo))
        self.assertTrue(fresh['worktree_path'].endswith('verify-pin-fresh'))
        self.assertTrue(fresh['removed'])
        self.assertEqual(fresh['leftovers_cleaned'], [])
        self.assertFalse(self.container(repo).exists())
        self.assertFalse((repo / '.git' / 'worktrees').exists())
        # 메인 워크스페이스는 게이트가 건드리지 않는다 — dirty 본문 유지(§3-8)
        self.assertEqual((repo / 'src/main.py').read_text(encoding='utf-8'),
                         'DIRTY without print\n')

    def test_t35_fresh_neutralizes_hidden_untracked(self):
        # C9 — info/exclude 은닉 untracked conftest.py: fresh 검증은 그 파일 없이
        # 실행(cwd conftest 존재 시 fail하는 명령의 exit_code 0)·은닉 플래그는
        # 메인 스캔에서 여전히 발행(투명성 — 검증된 것과 워크스페이스의 괴리)
        repo = self.make_repo()
        init = head_sha(repo)
        exclude_path = repo / '.git' / 'info' / 'exclude'
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        exclude_path.write_text('conftest.py\n', encoding='utf-8')
        write_file(repo, 'conftest.py', 'import pytest\n')
        cmd = "bash -c 'test ! -f conftest.py'"
        result = run_pin(repo, '--verify-cmd', cmd, '--fresh-checkout', '--base', init)
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn('verification_input_ignore_hidden', output['flags'])
        self.assertEqual(output['verify_cmd']['exit_code'], 0)
        self.assertNotIn('verify_cmd_failed', output['flags'])
        self.assertNotIn('verify_workspace_mutated', output['flags'])
        self.assertTrue(output['fresh']['removed'])

    def test_t36_fresh_leftover_recovery(self):
        # C10 — 더미 잔존 양변형: 등록 worktree(detached)·미등록 디렉터리 — 정리 후
        # 정상 완료(leftovers_cleaned 기록)
        repo = self.make_repo()
        # 변형 1 — 등록 worktree 잔존
        self.assertEqual(git(repo, 'worktree', 'add', '--detach',
                             str(self.fresh_wt(repo)), 'HEAD').returncode, 0)
        result = run_pin(repo, '--verify-cmd', '/bin/true', '--fresh-checkout')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['fresh']['leftovers_cleaned'],
                         [str(self.fresh_wt(repo))])
        self.assertTrue(output['fresh']['removed'])
        self.assertFalse((repo / '.git' / 'worktrees').exists())
        # 변형 2 — 미등록 디렉터리 잔존(등록 해제 후 디렉터리만 남은 형태)
        self.fresh_wt(repo).mkdir(parents=True)
        write_file(self.fresh_wt(repo), 'junk.txt', 'leftover\n')
        result2 = run_pin(repo, '--verify-cmd', '/bin/true', '--fresh-checkout')
        self.assertEqual(result2.returncode, 0, result2.stderr)
        output2 = json.loads(result2.stdout)
        self.assertEqual(output2['fresh']['leftovers_cleaned'],
                         [str(self.fresh_wt(repo))])
        self.assertFalse(self.container(repo).exists())

    def test_t37_fresh_remove_failure_partial_result(self):
        # C11(r24 M3 패턴) — worktree remove 심 실패: stdout JSON(fresh.removed
        # false·incomplete_step worktree_remove) 출력 후 exit 2 — 검사 결과 폐기 금지
        repo = self.make_repo()
        shim_dir = self.make_git_shim_block_worktree_remove()
        result = run_pin(repo, '--verify-cmd', '/bin/true', '--fresh-checkout',
                         path_prefix=shim_dir)
        self.assertEqual(result.returncode, 2, result.stderr)
        output = json.loads(result.stdout)  # 부분 결과 — stdout에 정확 1회
        self.assertFalse(output['fresh']['removed'])
        self.assertEqual(output['incomplete_step'], 'worktree_remove')
        self.assertTrue(output['error'])
        self.assertEqual(output['verify_cmd']['exit_code'], 0)
        self.assertIsNone(output['saved_to'])
        self.assertIn('FAIL verify pin', result.stderr)

    def test_t38_fresh_without_verify_cmd_exit2(self):
        # C8b(M3) — --fresh-checkout 단독(verify-cmd 미지정) exit 2 — 검증 부재
        repo = self.make_repo()
        result = run_pin(repo, '--fresh-checkout')
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('FAIL verify pin', result.stderr)
        self.assertFalse(result.stdout.strip())

    def test_t39_fresh_main_tracked_mutation_detected(self):
        # C5b(M4) — verify-cmd cwd=fresh여도 실행 중 메인 tracked 변형은 검출
        repo = self.make_repo()
        cmd = f"bash -c 'echo x >> {repo}/src/main.py'"
        result = run_pin(repo, '--verify-cmd', cmd, '--fresh-checkout')
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn('verify_workspace_mutated', output['flags'])
        self.assertTrue(any(record.endswith('src/main.py') for record
                            in output['verify_cmd']['window_delta']['tracked_changed']))
        self.assertTrue(output['fresh']['removed'])

    def test_t40_fresh_name_collision_guard(self):
        # C10b(H4) — wt/verify-pin-fresh 브랜치 ∨ docs/task-id/verify-pin-fresh/
        # 존재 시 잔존 복구 진입 없이 exit 2 거부(양변형) — r24 관리 대상 데이터 소실 차단
        repo = self.make_repo()
        # 변형 1 — 브랜치 존재 + 잔존 디렉터리 병치(진입 없음의 증명: 잔존 미정리)
        self.assertEqual(git(repo, 'branch', 'wt/verify-pin-fresh').returncode, 0)
        self.fresh_wt(repo).mkdir(parents=True)
        result = run_pin(repo, '--verify-cmd', '/bin/true', '--fresh-checkout')
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('충돌', result.stderr)
        self.assertFalse(result.stdout.strip())
        self.assertTrue(self.fresh_wt(repo).exists(), '잔존 복구가 진입해선 안 된다')
        self.assertTrue(self.container(repo).exists())
        # 변형 2 — task-id 디렉터리 존재
        repo2 = self.make_repo('repo-collision-dir')
        (repo2 / 'docs/task-id/verify-pin-fresh').mkdir(parents=True)
        result2 = run_pin(repo2, '--verify-cmd', '/bin/true', '--fresh-checkout')
        self.assertEqual(result2.returncode, 2, result2.stdout)
        self.assertIn('충돌', result2.stderr)

    # --- T41~T42 — 증분 영수증 ---

    def poll_receipt(self, save_dir, stage, deadline_s=15.0):
        """영수증 파일이 지정 stage에 도달할 때까지 폴링 — (경로, 데이터) 반환."""
        deadline = time.monotonic() + deadline_s
        last = None
        while time.monotonic() < deadline:
            files = list(Path(save_dir).glob('verify-pin-*.json'))
            if files:
                try:
                    last = json.loads(files[0].read_text(encoding='utf-8'))
                    if last.get('stage') == stage:
                        return files[0], last
                except (OSError, ValueError):
                    pass  # 원자 replace 중 읽기 — 다음 폴링에서 재시도
            time.sleep(0.05)
        self.fail(f'{stage!r} 단계 영수증이 {deadline_s}s 내에 나타나지 않았다: {last}')

    def test_t41_receipt_survives_sigkill_midrun(self):
        # C12 — 게이트 SIGKILL 후 영수증 잔존·파싱 가능·stage·head_sha 보존.
        # fresh 조합 변형: stage fresh_checkout에서 크래시 시 잔여 worktree 시사
        # (M12 — fresh 잔존은 fresh 모드 재실행으로만 정리).
        repo = self.make_repo()
        save_dir = self.root / 'audit-t41'
        proc = subprocess.Popen(
            [sys.executable, str(VERIFY_PIN), '--verify-cmd', 'sleep 5',
             '--save', str(save_dir)],
            cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=clean_env())
        try:
            path, saved = self.poll_receipt(save_dir, 'inspected')
        finally:
            proc.kill()
            proc.wait()
        self.assertEqual(saved['stage'], 'inspected')
        self.assertEqual(saved['head_sha'], head_sha(repo))
        self.assertEqual(saved['saved_to'], str(path))
        # fresh 변형 — fresh_checkout 단계 크래시
        save_dir_f = self.root / 'audit-t41-fresh'
        proc_f = subprocess.Popen(
            [sys.executable, str(VERIFY_PIN), '--verify-cmd', 'sleep 5',
             '--fresh-checkout', '--save', str(save_dir_f)],
            cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=clean_env())
        try:
            _, saved_f = self.poll_receipt(save_dir_f, 'fresh_checkout')
        finally:
            proc_f.kill()
            proc_f.wait()
        self.assertEqual(saved_f['stage'], 'fresh_checkout')
        # 크래시 시점에 worktree가 아직 제거 전 — 잔존(재실행 정리 대상) 시사
        self.assertTrue(self.fresh_wt(repo).exists(),
                        'fresh_checkout 단계 크래시인데 worktree가 없다')

    def test_t42_receipt_complete_matches_stdout(self):
        # C13 — 정상 종료: 파일 stage complete ∧ stdout JSON과 키 일치(stage 제외)
        repo = self.make_repo()
        save_dir = self.root / 'audit-t42'
        result = run_pin(repo, '--verify-cmd', '/bin/true', '--save', str(save_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        files = list(save_dir.glob('verify-pin-*.json'))
        self.assertEqual(len(files), 1)
        saved = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertEqual(saved['stage'], 'complete')
        without_stage = {key: value for key, value in saved.items() if key != 'stage'}
        self.assertEqual(without_stage, output)
        # stdout 최종 JSON은 stage 키 없다(기존 모양 보존 — §3-4)
        self.assertNotIn('stage', output)


if __name__ == '__main__':
    unittest.main()
