#!/usr/bin/env python3
"""r25 워크트리 게이트 경화 단위테스트 — 적대검토 결함 수선 전수(T35~T44).

테스트는 subprocess로 CLI를 실행한다(test_worktree_gate 관습). 모듈레벨 헬퍼는
1단계(test_worktree_gate) 것을 import(jev 선례), 클래스 fixture(가드 포함)는
자체 중복이다.
claims 대응: T35 = C15 인프라(H2 가드 메타 — 인프라 단계에서 이미 GREEN), T36~T38 =
H3·V5·RH-2(동시 작성 감지 루프 — 정상·잔존·미관리 경로), T39 = M1(명명경로 일치),
T40 = M2·V7(phase 사전 차단·혼합 조합), T41 = M3(제거 후 단계 실패 부분 JSON),
T42 = L1(ok 스키마 통일), T43 = L3(locked 사전 분류), T44 = L4(-z 파싱).
RED 근거: T36~T44는 salvage_until_quiet·phase·경로·부분 결과 분기가 구현되기
전까지 실패한다(T35는 제외 — setUp 가드는 인프라 단계에서 착지).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
GATE = ROOT / 'scripts/worktree_gate.py'
TEST_WORKTREE_GATE = ROOT / 'scripts/test_worktree_gate.py'

from test_worktree_gate import (clean_env, git, make_git_shim,  # noqa: E402
                                run_gate, write_file)


def churn_writer(directory, name, stop, written):
    """3ms 간격 append writer(H3 유도 — R2 마진: 중단 ~1.5s ≪ writer 수명)."""
    path = Path(directory) / name
    count = 0
    while not stop.is_set() and count < 2000:
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(f'line {count}\n')
        count += 1
        written.append(count)
        time.sleep(0.003)


class WorktreeGateHardeningTests(unittest.TestCase):
    """T35~T44 — r25 경화 분기 전수(fixture는 test_worktree_gate와 자체 중복)."""

    maxDiff = None

    def setUp(self):
        env_root = os.environ.get('WORKTREE_GATE_TEST_ROOT')
        if env_root:
            self.root = Path(env_root) / f'wgh-{uuid.uuid4().hex[:8]}'
            self.root.mkdir(parents=True)
            self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.root = Path(tmp.name)
        # H2 — 루트가 git 저장소 내부면 create가 호스트 본체에서 실행된다 — skip이
        # "10 passed"에 숨으므로 fail로 요란하게 터뜨린다(1단계와 동일 가드).
        inside = git(self.root, 'rev-parse', '--is-inside-work-tree')
        if inside.returncode == 0 and inside.stdout.strip() == 'true':
            self.fail(f'fixture 루트가 git 저장소 내부다({self.root}) — 호스트 오염 방지: '
                      'WORKTREE_GATE_TEST_ROOT를 저장소 밖으로 옮겨라')

    def make_repo(self):
        repo = self.root / f'repo-{uuid.uuid4().hex[:8]}'
        repo.mkdir()
        write_file(repo, 'docs/readme.md', 'readme\n')
        write_file(repo, 'src/main.py', 'print("main")\n')
        write_file(repo, '.gitignore', '*.log\n')
        self.assertEqual(git(repo, '-c', 'advice.defaultBranch=false',
                             'init').returncode, 0)
        self.assertEqual(git(repo, 'add', '-A').returncode, 0)
        self.assertEqual(git(repo, 'commit', '-m', 'init').returncode, 0)
        return repo

    def container(self, repo):
        return repo.parent / f'{repo.name}-worktrees'

    def set_phase(self, repo, task, phase):
        task_dir = repo / 'docs/task-id' / task
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / 'state.json').write_text(
            json.dumps({'task': task, 'phase': phase}), encoding='utf-8')

    def registry(self, repo, task):
        return json.loads((repo / 'docs/task-id' / task / 'worktree.json')
                          .read_text(encoding='utf-8'))

    def branch_exists(self, repo, branch):
        return git(repo, 'show-ref', '--verify',
                   f'refs/heads/{branch}').returncode == 0

    def salvage_branches(self, repo):
        listing = git(repo, 'for-each-ref', '--format=%(refname:short)',
                      'refs/heads/salvage/unmanaged-*')
        return [line for line in listing.stdout.splitlines() if line.strip()]

    def salvage_commit_count(self, repo, branch):
        completed = git(repo, 'rev-list', '--count', '--grep=^salvage(', branch)
        assert completed.returncode == 0, completed.stderr
        return int(completed.stdout.strip())

    # --- T35 — H2 가드 메타(인프라 착지분 — GREEN 전제, V9) ------------------

    def test_t35_h2_guard_fails_inside_repo(self):
        # 저장소 내부 경로를 WORKTREE_GATE_TEST_ROOT로 단일 테스트 subprocess 실행 →
        # rc≠0 ∧ 가드 문구(호스트 오염 방지 — skip 아닌 fail 실증)
        with tempfile.TemporaryDirectory() as tmp:
            host = Path(tmp) / 'host-repo'
            host.mkdir()
            self.assertEqual(git(host, '-c', 'advice.defaultBranch=false',
                                 'init').returncode, 0)
            env = clean_env()
            env['WORKTREE_GATE_TEST_ROOT'] = str(host)
            result = subprocess.run(
                [sys.executable, str(TEST_WORKTREE_GATE),
                 'WorktreeGateTests.test_t1_create_basics'],
                capture_output=True, text=True, env=env, cwd=str(host))
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn('git 저장소 내부', combined)
            self.assertIn('FAILED', combined)

    # --- T36~T38 — H3 동시 작성 감지 루프 + V5 부분 결과 ----------------------

    def test_t36_done_concurrent_writer_aborts_with_partial_json(self):
        # H3 정상 경로 — 3ms writer와 done 병행: exit 2 ∧ 디렉터리 잔존 ∧ stdout
        # 부분 JSON(aborted·salvage.rounds·commit — R6 정확 1객체) ∧ salvage 커밋
        # ≥1 ∧ writer 정지 후 재 done → 전 행 수 일치(0손실 실증)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-w').returncode, 0)
        wt = self.container(repo) / 't-w'
        written: list[int] = []
        stop = threading.Event()
        thread = threading.Thread(target=churn_writer,
                                  args=(wt, 'churn.txt', stop, written))
        thread.start()
        blocked = run_gate(repo, 'done', '--task', 't-w')
        stop.set()
        thread.join()
        self.assertEqual(blocked.returncode, 2)
        self.assertIn('FAIL', blocked.stderr)
        self.assertTrue(wt.exists())
        output = json.loads(blocked.stdout)
        self.assertEqual(output['aborted'], 'concurrent_writer')
        self.assertFalse(output['worktree']['removed'])
        self.assertTrue(output['salvage']['performed'])
        self.assertIsNotNone(output['salvage']['commit'])
        self.assertGreaterEqual(output['salvage']['rounds'], 1)
        self.assertFalse(output['ok'])
        self.assertGreaterEqual(len(written), 1)
        self.assertGreaterEqual(self.salvage_commit_count(repo, 'wt/t-w'), 1)
        retried = run_gate(repo, 'done', '--task', 't-w')
        self.assertEqual(retried.returncode, 1, retried.stderr)
        shown = git(repo, 'show', 'wt/t-w:churn.txt')
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(len(shown.stdout.splitlines()), len(written))
        self.assertFalse(wt.exists())

    def test_t37_leftover_concurrent_writer_aborts_then_converges(self):
        # H3 잔존 경로 — 심 1차(remove 실패) → 잔존 디렉터리 writer → done exit 2
        # 보존(부분 JSON) → 정지 후 수렴(제거 완료)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-lw').returncode, 0)
        wt = self.container(repo) / 't-lw'
        write_file(wt, 'notes.txt', 'memo\n')
        shim_dir = make_git_shim(self.root, 'worktree-remove')
        first = run_gate(repo, 'done', '--task', 't-lw', shim_dir=shim_dir)
        self.assertEqual(first.returncode, 2)  # 1차 — salvage 후 remove 실패
        self.assertTrue(wt.exists())
        written: list[int] = []
        stop = threading.Event()
        thread = threading.Thread(target=churn_writer,
                                  args=(wt, 'late.txt', stop, written))
        thread.start()
        blocked = run_gate(repo, 'done', '--task', 't-lw')
        stop.set()
        thread.join()
        self.assertEqual(blocked.returncode, 2)
        output = json.loads(blocked.stdout)
        self.assertEqual(output['aborted'], 'concurrent_writer')
        self.assertFalse(output['worktree']['removed'])
        self.assertTrue(output['salvage']['performed'])
        self.assertTrue(wt.exists())
        retried = run_gate(repo, 'done', '--task', 't-lw')
        self.assertEqual(retried.returncode, 1, retried.stderr)
        self.assertFalse(wt.exists())

    def test_t38_sweep_unmanaged_writer_aborts_then_proceeds(self):
        # H3 미관리 — sweep --unmanaged + writer: exit 2 보존(부분 JSON) → 정지 후
        # 진행(salvage/unmanaged-* 브랜치 1개)
        repo = self.make_repo()
        ext = self.root / f'ext-{uuid.uuid4().hex[:8]}'
        self.assertEqual(git(repo, 'worktree', 'add', str(ext),
                             '-b', 'manual-w').returncode, 0)
        written: list[int] = []
        stop = threading.Event()
        thread = threading.Thread(target=churn_writer,
                                  args=(ext, 'churn.txt', stop, written))
        thread.start()
        blocked = run_gate(repo, 'sweep', '--unmanaged')
        stop.set()
        thread.join()
        self.assertEqual(blocked.returncode, 2)
        self.assertIn('FAIL', blocked.stderr)
        self.assertTrue(ext.exists())
        output = json.loads(blocked.stdout)
        self.assertEqual(output['aborted'], 'concurrent_writer')
        self.assertIsNone(output['task'])
        self.assertEqual(output['classification'], 'unmanaged')
        retried = run_gate(repo, 'sweep', '--unmanaged')
        self.assertEqual(retried.returncode, 1, retried.stderr)
        self.assertFalse(ext.exists())
        # 라운드마다 salvage 커밋 추가(원칙) — 브랜치는 1개 이상
        self.assertGreaterEqual(len(self.salvage_branches(repo)), 1)

    # --- T39·T40·T41 — M1·M2·M3 done 사전 차단·부분 보존 ----------------------

    def test_t39_done_random_path_mismatch_blocked(self):
        # M1 — 활성 레지스트리 + 명명규칙 밖 경로 attach → done exit 2 ∧ 임의
        # 경로 무변경(레지스트리 유무 무관 경로 일치 검사)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-p').returncode, 0)
        canonical = self.container(repo) / 't-p'
        self.assertEqual(git(repo, 'worktree', 'remove', '--force',
                             str(canonical)).returncode, 0)
        arbitrary = self.root / f'arbitrary-{uuid.uuid4().hex[:8]}'
        self.assertEqual(git(repo, 'worktree', 'add', str(arbitrary),
                             'wt/t-p').returncode, 0)
        write_file(arbitrary, 'sentinel.txt', 'untouched\n')
        result = run_gate(repo, 'done', '--task', 't-p')
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL', result.stderr)
        self.assertTrue(arbitrary.exists())
        self.assertEqual((arbitrary / 'sentinel.txt').read_text(encoding='utf-8'),
                         'untouched\n')
        self.assertEqual(self.salvage_commit_count(repo, 'wt/t-p'), 0)

    def test_t40_done_phase_guard_blocks_active(self):
        # M2 — phase=implement done → exit 2·보존(salvage 0) → phase=done 후 진행.
        # V7 혼합 — 레지스트리 소실(worktree.json 삭제)+implement도 동일 차단
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a2').returncode, 0)
        wt = self.container(repo) / 't-a2'
        self.set_phase(repo, 't-a2', 'implement')
        write_file(wt, 'notes.txt', 'precious\n')
        blocked = run_gate(repo, 'done', '--task', 't-a2')
        self.assertEqual(blocked.returncode, 2)
        self.assertIn('phase', blocked.stderr)
        self.assertTrue(wt.exists())
        self.assertEqual(self.salvage_commit_count(repo, 'wt/t-a2'), 0)
        self.set_phase(repo, 't-a2', 'done')
        retried = run_gate(repo, 'done', '--task', 't-a2')
        self.assertEqual(retried.returncode, 1, retried.stderr)
        self.assertFalse(wt.exists())
        # V7 — 혼합 조합
        self.assertEqual(run_gate(repo, 'create', '--task', 't-mix').returncode, 0)
        self.set_phase(repo, 't-mix', 'implement')
        (repo / 'docs/task-id/t-mix/worktree.json').unlink()
        mixed = run_gate(repo, 'done', '--task', 't-mix')
        self.assertEqual(mixed.returncode, 2)
        self.assertIn('phase', mixed.stderr)
        self.assertTrue((self.container(repo) / 't-mix').exists())

    def test_t41_branch_drop_failure_partial_json(self):
        # M3 — branch-delete 심 + done --drop-branch: 제거 성공 뒤 기록 단계 실패 →
        # stdout 부분 JSON(removed true·incomplete_step)·stderr FAIL·exit 2 ∧
        # 레지스트리 done_utc 유지 null(감사 대칭 — R6 정확 1객체)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-bd').returncode, 0)
        wt = self.container(repo) / 't-bd'
        write_file(wt, 'notes.txt', 'memo\n')
        shim_dir = make_git_shim(self.root, 'branch-delete')
        blocked = run_gate(repo, 'done', '--task', 't-bd', '--drop-branch',
                           shim_dir=shim_dir)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn('FAIL', blocked.stderr)
        output = json.loads(blocked.stdout)
        self.assertTrue(output['worktree']['removed'])
        self.assertFalse(wt.exists())  # remove는 성공 — 실패는 기록 단계다
        self.assertEqual(output['incomplete_step'], 'branch_drop')
        self.assertFalse(output['registry']['updated'])
        self.assertFalse(output['ok'])
        self.assertTrue(output['branch']['preserved'])
        self.assertIsNotNone(output['salvage']['commit'])
        self.assertTrue(self.branch_exists(repo, 'wt/t-bd'))
        self.assertIsNone(self.registry(repo, 't-bd')['done_utc'])

    # --- T42·T43·T44 — L1·L3·L4 ----------------------------------------------

    def test_t42_done_ok_schema_unified(self):
        # L1 — done 결과 ok = len(flags)==0 통일: clean done ok true ∧ salvage
        # done ok false(create·list·verify_pin과 동일 스키마)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-ok').returncode, 0)
        clean_done = json.loads(run_gate(repo, 'done', '--task', 't-ok').stdout)
        self.assertTrue(clean_done['ok'])
        self.assertEqual(clean_done['flags'], [])
        self.assertEqual(run_gate(repo, 'create', '--task', 't-sv').returncode, 0)
        write_file(self.container(repo) / 't-sv', 'notes.txt', 'memo\n')
        salvage_done = json.loads(run_gate(repo, 'done', '--task', 't-sv').stdout)
        self.assertFalse(salvage_done['ok'])
        self.assertEqual(salvage_done['flags'], ['salvage_committed'])

    def test_t43_sweep_unmanaged_locked_preserved_before_salvage(self):
        # L3 — locked 수동 worktree sweep --unmanaged → salvage 전 사전 분류:
        # skipped 'locked' ∧ 디렉터리 잔존 ∧ salvage 브랜치 0(반쪽 상태 방지)
        repo = self.make_repo()
        ext = self.root / f'ext-{uuid.uuid4().hex[:8]}'
        self.assertEqual(git(repo, 'worktree', 'add', str(ext),
                             '-b', 'manual-lock').returncode, 0)
        write_file(ext, 'precious.txt', 'keep\n')
        self.assertEqual(git(repo, 'worktree', 'lock', str(ext)).returncode, 0)
        result = run_gate(repo, 'sweep', '--unmanaged')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(ext.exists())
        output = json.loads(result.stdout)
        self.assertEqual(output['skipped'][0]['reason'], 'locked')
        self.assertEqual(output['skipped'][0]['path'], str(ext))
        self.assertEqual(self.salvage_branches(repo), [])

    def test_t44_newline_filename_salvage_z(self):
        # L4 — porcelain -z 전환: 개행 파일명이 salvage.files에 정확히 기록 ∧
        # 커밋 트리 정합(linesplit 파서는 레코드를 절단한다 — P3 규격). FS 미지원
        # 시 능력 기반 skip(A7 — DrvFs)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-nl').returncode, 0)
        wt = self.container(repo) / 't-nl'
        name = 'we\nird.txt'
        try:
            write_file(wt, name, 'content\n')
        except OSError:
            self.skipTest('이 파일시스템은 개행 파일명을 지원하지 않는다(A7)')
        result = run_gate(repo, 'done', '--task', 't-nl')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn(name, output['salvage']['files'])
        shown = git(repo, 'show', f'wt/t-nl:{name}')
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(shown.stdout, 'content\n')
        self.assertFalse(wt.exists())


if __name__ == '__main__':
    unittest.main()
