#!/usr/bin/env python3
"""r24 워크트리 수명주기 게이트 단위테스트 — 임시 git 저장소 fixture로 분기 전수(T1~T34).

테스트는 subprocess로 CLI를 실행한다(test_verify_pin 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다. RED 단계(worktree_gate.py 부재·
신규 분기 미구현)에서는 해당 테스트가 실패한다.
claims 대응: T1~T19 = 번들 §4 C1~C19, T20~T31 = C25~C36(②반려 파생).
T32 = 라운드1 G1(완료 과업 재등장 디렉터리 멱등 유지), T33 = G2·LOW-6(잔존 경로
--no-salvage·1차 salvage SHA 기록), T34 = 라운드2 M1(잔존 경로 --drop-branch의
tip 삭제 전 판독). C20 = 본 파일 전체 exit 0.
C21~C24 = 문서·미러(docs/task-id 스크립트·메인).
fixture 계약: r23 준용 + identity 환경변수 제거(H2 실증 전제)·state.json 헬퍼·
WORKTREE_GATE_TEST_ROOT env로 fixture 루트 지정(M-g — /tmp ext4 vs /mnt/d DrvFs 재현).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/worktree_gate.py'

# 부모 환경 오염 차단 — fixture git과 게이트 subprocess 모두 적용.
# GIT_AUTHOR/COMMITTER 제거는 H2(identity 폴백) 실증의 전제다.
FIXTURE_ENV_KEYS = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_GLOBAL',
                    'GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL',
                    'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL')
GIT_IDENTITY = ('-c', 'user.email=worktree-gate-test@example.com',
                '-c', 'user.name=worktree-gate-test')


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


def write_file(base, name, content):
    path = Path(base) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def run_gate(cwd, *args):
    return subprocess.run([sys.executable, str(GATE), *args],
                          cwd=str(cwd), capture_output=True, text=True, env=clean_env())


class WorktreeGateTests(unittest.TestCase):
    """T1~T31 — claims 대응표(번들 §4 (Tn) 표기) 그대로."""

    maxDiff = None

    def setUp(self):
        env_root = os.environ.get('WORKTREE_GATE_TEST_ROOT')
        if env_root:
            self.root = Path(env_root) / f'wgate-{uuid.uuid4().hex[:8]}'
            self.root.mkdir(parents=True)
            self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.root = Path(tmp.name)

    def make_repo(self):
        """초기 커밋 저장소 — .gitignore 포함 커밋(T9 ignored-only 분기 전제)."""
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

    def salvage_commit_count(self, repo, branch):
        completed = git(repo, 'rev-list', '--count', '--grep=^salvage(', branch)
        assert completed.returncode == 0, completed.stderr
        return int(completed.stdout.strip())

    # --- create (T1~T5·T29) -------------------------------------------------

    def test_t1_create_basics(self):
        # C1 — create → exit 0 ∧ 디렉터리·브랜치·레지스트리 존재 ∧ JSON path·branch 정합
        repo = self.make_repo()
        result = run_gate(repo, 'create', '--task', 't-a')
        self.assertEqual(result.returncode, 0, result.stderr)
        wt = self.container(repo) / 't-a'
        self.assertTrue(wt.is_dir())
        self.assertTrue(self.branch_exists(repo, 'wt/t-a'))
        self.assertTrue((repo / 'docs/task-id/t-a/worktree.json').exists())
        output = json.loads(result.stdout)
        self.assertEqual(output['worktree']['path'], str(wt))
        self.assertEqual(output['worktree']['branch'], 'wt/t-a')
        self.assertEqual(output['flags'], [])

    def test_t2_create_base_sha(self):
        # C2 — --base <직전 커밋 SHA> → worktree HEAD가 base SHA와 일치
        repo = self.make_repo()
        base = head_sha(repo)
        result = run_gate(repo, 'create', '--task', 't-b', '--base', base)
        self.assertEqual(result.returncode, 0, result.stderr)
        wt = self.container(repo) / 't-b'
        self.assertEqual(head_sha(wt), base)

    def test_t3_create_duplicate_fails(self):
        # C3 — 동일 task-id 재 create → exit 2 ∧ stderr FAIL(중복 방어)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        again = run_gate(repo, 'create', '--task', 't-a')
        self.assertEqual(again.returncode, 2)
        self.assertIn('FAIL', again.stderr)

    def test_t4_create_invalid_task_ids(self):
        # C4 — 무효 task-id(슬래시·공백) → 전부 exit 2
        repo = self.make_repo()
        for bad in ('bad/id', 'bad id'):
            result = run_gate(repo, 'create', '--task', bad)
            self.assertEqual(result.returncode, 2, bad)
            self.assertIn('FAIL', result.stderr, bad)

    def test_t5_create_invalid_base(self):
        # C5 — --base no-such-ref → exit 2
        repo = self.make_repo()
        result = run_gate(repo, 'create', '--task', 't-b', '--base', 'no-such-ref')
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL', result.stderr)

    def test_t29_create_residual_branch_blocked(self):
        # C34(M-a) — 브랜치 wt/t-c 선행 존재(레지스트리 부재) create → exit 2 ∧
        # stderr 사유에 잔존 브랜치 명시(재시도 차단 방어)
        repo = self.make_repo()
        self.assertEqual(git(repo, 'branch', 'wt/t-c').returncode, 0)
        result = run_gate(repo, 'create', '--task', 't-c')
        self.assertEqual(result.returncode, 2)
        self.assertIn('wt/t-c', result.stderr)

    # --- done (T6~T12·T20~T22·T24·T27·T31) ----------------------------------

    def test_t6_done_clean(self):
        # C6 — 변경 없는 done → exit 0 ∧ 디렉터리 소멸 ∧ 브랜치 잔존 ∧
        # 레지스트리 done_utc non-null ∧ salvage.performed false
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        result = run_gate(repo, 'done', '--task', 't-a')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.container(repo) / 't-a').exists())
        self.assertTrue(self.branch_exists(repo, 'wt/t-a'))
        self.assertIsNotNone(self.registry(repo, 't-a')['done_utc'])
        output = json.loads(result.stdout)
        self.assertFalse(output['salvage']['performed'])

    def test_t7_done_salvage_tracked(self):
        # C7 — tracked 미커밋 수정 done → exit 1 ∧ salvage_committed ∧ wt tip에
        # salvage 커밋 ∧ 커밋 트리에 해당 내용 ∧ salvage.files 포함 ∧ 디렉터리 소멸
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        wt = self.container(repo) / 't-a'
        write_file(wt, 'src/main.py', 'modified in worktree\n')
        result = run_gate(repo, 'done', '--task', 't-a')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('salvage_committed', output['flags'])
        self.assertTrue(output['salvage']['performed'])
        self.assertIn('src/main.py', output['salvage']['files'])
        shown = git(repo, 'show', 'wt/t-a:src/main.py')
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(shown.stdout, 'modified in worktree\n')
        self.assertFalse(wt.exists())

    def test_t8_done_salvage_untracked(self):
        # C8 — untracked(비ignored) 신규 2종 done → 둘 다 salvage 커밋 트리·files 포함
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        wt = self.container(repo) / 't-a'
        write_file(wt, 'notes.txt', 'memo\n')
        write_file(wt, 'extra/data.txt', 'data\n')
        result = run_gate(repo, 'done', '--task', 't-a')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('notes.txt', output['salvage']['files'])
        self.assertIn('extra/data.txt', output['salvage']['files'])
        for name in ('notes.txt', 'extra/data.txt'):
            self.assertEqual(git(repo, 'show', f'wt/t-a:{name}').returncode, 0, name)
        self.assertFalse(wt.exists())

    def test_t9_done_ignored_only_no_salvage(self):
        # C9 — ignored 파일만 존재 done → exit 0 ∧ performed false(빈 salvage 커밋
        # 미생성) ∧ 디렉터리 소멸
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        write_file(self.container(repo) / 't-a', 'build.log', 'noise\n')
        result = run_gate(repo, 'done', '--task', 't-a')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['salvage']['performed'])
        self.assertIsNone(output['salvage']['commit'])
        self.assertFalse((self.container(repo) / 't-a').exists())

    def test_t10_done_drop_branch(self):
        # C10 — done --drop-branch → 브랜치 소멸 ∧ JSON·레지스트리 dropped_branch_tip
        # 에 tip SHA 기록
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        result = run_gate(repo, 'done', '--task', 't-a', '--drop-branch')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['branch']['dropped'])
        tip = output['branch']['tip_sha']
        self.assertIsNotNone(tip)
        self.assertFalse(self.branch_exists(repo, 'wt/t-a'))
        self.assertEqual(self.registry(repo, 't-a')['dropped_branch_tip'], tip)

    def test_t11_done_unknown_task(self):
        # C11(H5) — 레지스트리·worktree 전부 부재 task done → exit 2 ∧ stderr FAIL
        repo = self.make_repo()
        result = run_gate(repo, 'done', '--task', 'ghost')
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL', result.stderr)

    def test_t12_done_idempotent(self):
        # C12 — done 후 재 done(멱등) → exit 0 ∧ already_removed true
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        self.assertEqual(run_gate(repo, 'done', '--task', 't-a').returncode, 0)
        again = run_gate(repo, 'done', '--task', 't-a')
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(json.loads(again.stdout)['worktree']['already_removed'])

    def test_t20_done_pre_commit_hook_blocked_but_salvaged(self):
        # C25(H3) — pre-commit hook exit 1 worktree에서 done → salvage 성립
        # (--no-verify) ∧ 디렉터리 소멸 ∧ exit 1(salvage_committed)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-h').returncode, 0)
        hook = repo / '.git' / 'hooks' / 'pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
        hook.chmod(0o755)
        write_file(self.container(repo) / 't-h', 'notes.txt', 'memo\n')
        result = run_gate(repo, 'done', '--task', 't-h')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('salvage_committed', output['flags'])
        self.assertTrue(output['salvage']['performed'])
        self.assertFalse((self.container(repo) / 't-h').exists())

    def test_t21_done_identity_fallback(self):
        # C26(H2) — identity 미정의 환경에서 tracked 수정 done → salvage 성립 ∧
        # salvage 커밋 author/committer가 worktree-gate <worktree-gate@local>
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-i').returncode, 0)
        write_file(self.container(repo) / 't-i', 'src/main.py', 'changed\n')
        result = run_gate(repo, 'done', '--task', 't-i')
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        sha = output['salvage']['commit']
        self.assertIsNotNone(sha)
        shown = git(repo, 'show', '-s', '--format=%an <%ae>|%cn <%ce>', sha)
        self.assertEqual(shown.stdout.strip(),
                         'worktree-gate <worktree-gate@local>'
                         '|worktree-gate <worktree-gate@local>')

    def test_t22_done_registry_less(self):
        # C27(H5) — 고아 done(레지스트리 삭제·worktree 존재) → 레지스트리리스 경로
        # 진행(exit 2 아님) ∧ salvage·제거 ∧ JSON에 branch.tip_sha·salvage.commit
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-r').returncode, 0)
        wt = self.container(repo) / 't-r'
        write_file(wt, 'notes.txt', 'precious\n')
        shutil.rmtree(repo / 'docs/task-id/t-r')
        result = run_gate(repo, 'done', '--task', 't-r')
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['worktree']['registry_less'])
        self.assertIsNotNone(output['branch']['tip_sha'])
        self.assertIsNotNone(output['salvage']['commit'])
        self.assertFalse(wt.exists())
        self.assertFalse((repo / 'docs/task-id/t-r/worktree.json').exists())

    def test_t24_done_remove_failure_converges(self):
        # C29(M-f·R2) — remove 실패(쓰기금지 chmod) 유도 done → exit 2 ∧ 권한 회복 후
        # 재 done → 수렴 exit 0 ∧ salvage 커밋 정확히 1개(재시도 2중 커밋 없음)
        if os.geteuid() == 0:
            self.skipTest('root는 chmod 쓰기금지가 무의미하다')
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-r').returncode, 0)
        wt = self.container(repo) / 't-r'
        write_file(wt, 'notes.txt', 'memo\n')
        wt.chmod(0o555)
        blocked = run_gate(repo, 'done', '--task', 't-r')
        self.assertEqual(blocked.returncode, 2)
        self.assertIn('FAIL', blocked.stderr)
        self.assertTrue(wt.exists())
        wt.chmod(0o755)
        retried = run_gate(repo, 'done', '--task', 't-r')
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertFalse(wt.exists())
        self.assertEqual(self.salvage_commit_count(repo, 'wt/t-r'), 1)

    def test_t27_done_empty_container_rmdir(self):
        # C32(M-f) — 컨테이너 유일 worktree done 후 컨테이너 디렉터리 소멸
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-o').returncode, 0)
        self.assertEqual(run_gate(repo, 'done', '--task', 't-o').returncode, 0)
        self.assertFalse(self.container(repo).exists())

    def test_t31_done_no_salvage_discards(self):
        # C36(H4) — done --no-salvage(미커밋 2건) → salvage 커밋 부재 ∧ 디렉터리 소멸 ∧
        # discarded_changes==2 ∧ exit 0(명시 폐기)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-n').returncode, 0)
        wt = self.container(repo) / 't-n'
        write_file(wt, 'notes.txt', 'memo\n')
        write_file(wt, 'extra/data.txt', 'data\n')
        result = run_gate(repo, 'done', '--task', 't-n', '--no-salvage')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['salvage']['skipped_by_option'])
        self.assertIsNone(output['salvage']['commit'])
        self.assertEqual(output['salvage']['discarded_changes'], 2)
        self.assertFalse(wt.exists())
        self.assertEqual(self.salvage_commit_count(repo, 'wt/t-n'), 0)

    def test_t32_done_after_completion_ignores_reappeared_dir(self):
        # 라운드1 G1 — 완료 과업(done_utc 기록) 옛 경로에 임의 디렉터리 재등장 →
        # 재 done은 멱등(already_removed) 유지 ∧ 그 디렉터리를 salvage·삭제하지 않는다
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-g').returncode, 0)
        self.assertEqual(run_gate(repo, 'done', '--task', 't-g').returncode, 0)
        wt = self.container(repo) / 't-g'
        wt.mkdir(parents=True)
        write_file(wt, 'stray.txt', 'not mine\n')
        again = run_gate(repo, 'done', '--task', 't-g')
        self.assertEqual(again.returncode, 0, again.stderr)
        output = json.loads(again.stdout)
        self.assertTrue(output['worktree']['already_removed'])
        self.assertTrue(wt.exists())  # 재등장 디렉터리 무시 — salvage·rmtree 금지
        self.assertEqual(self.salvage_commit_count(repo, 'wt/t-g'), 0)

    def test_t33_done_no_salvage_on_leftover(self):
        # 라운드1 G2·LOW-6 — remove 실패 잔존 경로에서 --no-salvage → 신규 파일도
        # 커밋하지 않고 폐기 수 기록 ∧ 1차 실패 당시 salvage SHA는 레지스트리에 기록
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-l').returncode, 0)
        wt = self.container(repo) / 't-l'
        write_file(wt, 'notes.txt', 'memo\n')
        wt.chmod(0o555)
        blocked = run_gate(repo, 'done', '--task', 't-l')
        self.assertEqual(blocked.returncode, 2)  # 1차 — salvage 커밋 후 remove 실패
        wt.chmod(0o755)
        write_file(wt, 'extra.txt', 'late\n')  # 실패 이후 신규 파일
        result = run_gate(repo, 'done', '--task', 't-l', '--no-salvage')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['salvage']['performed'])
        self.assertTrue(output['salvage']['skipped_by_option'])
        self.assertEqual(output['salvage']['discarded_changes'], 1)
        self.assertFalse(wt.exists())
        self.assertEqual(self.salvage_commit_count(repo, 'wt/t-l'), 1)  # 1차분뿐
        self.assertIsNotNone(self.registry(repo, 't-l')['salvage_commit'])

    def test_t34_done_drop_branch_on_leftover_keeps_tip(self):
        # 라운드2 M1 — 잔존 경로 done --drop-branch → tip은 삭제 전 판독: JSON
        # branch.tip_sha·레지스트리 dropped_branch_tip non-null ∧ 브랜치 소멸
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-b').returncode, 0)
        wt = self.container(repo) / 't-b'
        write_file(wt, 'notes.txt', 'memo\n')
        wt.chmod(0o555)
        blocked = run_gate(repo, 'done', '--task', 't-b')
        self.assertEqual(blocked.returncode, 2)  # 1차 — salvage 후 remove 실패
        wt.chmod(0o755)
        result = run_gate(repo, 'done', '--task', 't-b', '--drop-branch')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['branch']['dropped'])
        tip = output['branch']['tip_sha']
        self.assertIsNotNone(tip)
        self.assertFalse(self.branch_exists(repo, 'wt/t-b'))
        self.assertEqual(self.registry(repo, 't-b')['dropped_branch_tip'], tip)
        self.assertFalse(wt.exists())

    # --- list (T13·T14·T23·T25·T28) -----------------------------------------

    def test_t13_list_active_phase(self):
        # C13 — list(phase=implement) → entry 1건 ∧ managed ∧ phase implement ∧
        # eligible_for_sweep false ∧ exit 0
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        self.set_phase(repo, 't-a', 'implement')
        result = run_gate(repo, 'list')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(len(output['entries']), 1)
        entry = output['entries'][0]
        self.assertTrue(entry['managed'])
        self.assertEqual(entry['phase'], 'implement')
        self.assertFalse(entry['eligible_for_sweep'])
        self.assertEqual(output['summary']['eligible'], 0)

    def test_t14_list_done_phase_attention(self):
        # C14 — phase=done 전환 후 list → eligible true ∧ exit 1 ∧
        # removable_worktrees_present 플래그
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        self.set_phase(repo, 't-a', 'done')
        result = run_gate(repo, 'list')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertTrue(output['entries'][0]['eligible_for_sweep'])
        self.assertIn('removable_worktrees_present', output['flags'])

    def test_t23_list_detached_unmanaged(self):
        # C28(M-d) — detached HEAD worktree(수동 생성) list → unmanaged 분류 ∧
        # list 정상 종료(파서 실패가 목록 전체를 마비시키지 않음)
        repo = self.make_repo()
        ext = self.root / f'ext-{uuid.uuid4().hex[:8]}'
        self.assertEqual(git(repo, 'worktree', 'add', '--detach', str(ext),
                             'HEAD').returncode, 0)
        result = run_gate(repo, 'list')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(len(output['entries']), 1)
        entry = output['entries'][0]
        self.assertEqual(entry['classification'], 'unmanaged')
        self.assertEqual(entry['unmanaged_reason'], 'detached')
        self.assertFalse(entry['eligible_for_sweep'])

    def test_t25_list_du_bytes(self):
        # C30(M-f) — list --du → 존재 worktree entry의 bytes non-null
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        result = run_gate(repo, 'list', '--du')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIsInstance(output['entries'][0]['bytes'], int)

    def test_t28_list_from_inside_worktree(self):
        # C33(M-c) — worktree 내부 디렉터리에서 list → 본체 식별(--git-common-dir)으로
        # entries 동일(경로 오작동 없음)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-a').returncode, 0)
        self.set_phase(repo, 't-a', 'implement')
        from_repo = json.loads(run_gate(repo, 'list').stdout)
        from_wt = run_gate(self.container(repo) / 't-a', 'list')
        self.assertEqual(from_wt.returncode, 0, from_wt.stderr)
        from_wt_output = json.loads(from_wt.stdout)
        self.assertEqual([e['path'] for e in from_repo['entries']],
                         [e['path'] for e in from_wt_output['entries']])
        self.assertEqual(from_repo['summary'], from_wt_output['summary'])

    # --- sweep (T15~T18·T26·T30) ---------------------------------------------

    def test_t15_sweep_dry_run_no_change(self):
        # C15 — sweep --dry-run(eligible 1건) → JSON에 eligible 보고 ∧ 디렉터리 잔존 ∧
        # 레지스트리 done_utc 여전히 null(무변경) ∧ exit 0
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-d').returncode, 0)
        self.set_phase(repo, 't-d', 'done')
        result = run_gate(repo, 'sweep', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual([item['task'] for item in output['items']], ['t-d'])
        self.assertTrue((self.container(repo) / 't-d').exists())
        self.assertIsNone(self.registry(repo, 't-d')['done_utc'])

    def test_t16_sweep_eligible_only(self):
        # C16 — sweep(eligible 1건[phase=done] + 활성 1건[implement]) → eligible
        # 디렉터리 소멸 ∧ 활성 디렉터리 잔존
        repo = self.make_repo()
        for task, phase in (('t-done', 'done'), ('t-active', 'implement')):
            self.assertEqual(run_gate(repo, 'create', '--task', task).returncode, 0)
            self.set_phase(repo, task, phase)
        result = run_gate(repo, 'sweep')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.container(repo) / 't-done').exists())
        self.assertTrue((self.container(repo) / 't-active').exists())
        output = json.loads(result.stdout)
        self.assertEqual([item['task'] for item in output['items']], ['t-done'])
        self.assertEqual(output['skipped'],
                         [{'task': 't-active',
                           'path': str(self.container(repo) / 't-active'),
                           'reason': 'active_phase'}])

    def test_t17_sweep_orphan_salvages(self):
        # C17 — 고아 sweep — create 후 과업 폴더 전체 삭제 후 sweep → 명명규칙
        # 재구성으로 제거 ∧ salvage 필요 시 C7 동일 행동
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-o').returncode, 0)
        wt = self.container(repo) / 't-o'
        write_file(wt, 'src/main.py', 'orphan work\n')
        shutil.rmtree(repo / 'docs/task-id/t-o')
        result = run_gate(repo, 'sweep')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(wt.exists())
        output = json.loads(result.stdout)
        item = output['items'][0]
        self.assertEqual(item['task'], 't-o')
        self.assertTrue(item['salvage']['performed'])
        self.assertIn('src/main.py', item['salvage']['files'])
        shown = git(repo, 'show', 'wt/t-o:src/main.py')
        self.assertEqual(shown.stdout, 'orphan work\n')

    def test_t18_sweep_leaves_unmanaged(self):
        # C18 — 게이트 밖 worktree(직접 생성, 컨테이너 밖 경로) 존재 시 기본 sweep →
        # 해당 디렉터리 잔존 ∧ JSON에 unmanaged 보고
        repo = self.make_repo()
        ext = self.root / f'ext-{uuid.uuid4().hex[:8]}'
        self.assertEqual(git(repo, 'worktree', 'add', str(ext),
                             '-b', 'manual-x').returncode, 0)
        result = run_gate(repo, 'sweep')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(ext.exists())
        output = json.loads(result.stdout)
        self.assertEqual(output['skipped'][0]['reason'], 'unmanaged')
        self.assertEqual(output['skipped'][0]['path'], str(ext))

    def test_t26_sweep_drop_branch(self):
        # C31(M-f) — sweep --drop-branch → swept 항목 브랜치 소멸 ∧ JSON에 tip SHA 기록
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'create', '--task', 't-s').returncode, 0)
        self.set_phase(repo, 't-s', 'done')
        result = run_gate(repo, 'sweep', '--drop-branch')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.branch_exists(repo, 'wt/t-s'))
        output = json.loads(result.stdout)
        self.assertIsNotNone(output['items'][0]['branch']['tip_sha'])

    def test_t30_sweep_unmanaged_salvage_branch(self):
        # C35(H1) — sweep --unmanaged → 수동 worktree(컨테이너 밖) 제거 ∧ 미커밋분은
        # salvage/unmanaged-* 브랜치에 salvage ∧ 원본 브랜치 포인터 무변경
        repo = self.make_repo()
        ext = self.root / f'ext-{uuid.uuid4().hex[:8]}'
        self.assertEqual(git(repo, 'worktree', 'add', str(ext),
                             '-b', 'manual-x').returncode, 0)
        write_file(ext, 'salvage-me.txt', 'precious\n')
        tip_before = git(repo, 'rev-parse', 'manual-x').stdout.strip()
        result = run_gate(repo, 'sweep', '--unmanaged')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(ext.exists())
        listing = git(repo, 'for-each-ref', '--format=%(refname:short)',
                      'refs/heads/salvage/unmanaged-*')
        branches = [line for line in listing.stdout.splitlines() if line.strip()]
        self.assertEqual(len(branches), 1)
        shown = git(repo, 'show', f'{branches[0]}:salvage-me.txt')
        self.assertEqual(shown.stdout, 'precious\n')
        self.assertEqual(git(repo, 'rev-parse', 'manual-x').stdout.strip(), tip_before)

    # --- 공통 (T19) -----------------------------------------------------------

    def test_t19_non_git_directory_all_subcommands(self):
        # C19 — 비 git 디렉터리에서 4 서브커맨드 전부 → exit 2 ∧ stderr FAIL
        plain = self.root / 'plain'
        plain.mkdir()
        cases = (
            run_gate(plain, 'create', '--task', 'x'),
            run_gate(plain, 'done', '--task', 'x'),
            run_gate(plain, 'list'),
            run_gate(plain, 'sweep'),
        )
        for index, result in enumerate(cases):
            self.assertEqual(result.returncode, 2, f'subcommand #{index}')
            self.assertIn('FAIL', result.stderr, f'subcommand #{index}')


if __name__ == '__main__':
    unittest.main()
