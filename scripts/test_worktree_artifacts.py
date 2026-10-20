#!/usr/bin/env python3
"""r43 워크트리 부산물 회수 단위·통합 테스트 — D1~D3·A1~A15(단위) + C1~C11(CLI).

단위 케이스는 가드·집계 순수함수를 직접 호출한다(r42 intake 패턴 — worktree_artifacts
모듈 부재 시 수집 실패가 곧 RED다, M9 명시 채택). CLI 통합 케이스는 subprocess
run_gate(test_worktree_gate 관습) — `--artifacts-only` 미구현 시 argparse error
exit 2로 RED한다. C9만 RED 예외다 — 구현 전 통과 확인용 기존 동작 대조 케이스(H2).
claims 대응: D2 = M4(env 값 공간), A2 = tracked 전체 보존(보존 제약 8),
A3 = fail-closed, A12 = M8(remove_failed·NotADirectoryError), A13 = M11(measure_error),
A14 = M11(ls_files_error·PATH git 심), A15 = M10(예산 상한 주입),
C2·C6 = 보존 제약 3(disk.low flags 미발행), C5 = H1(eligible 한정)+M2(disk 항상)+
M12(artifacts-sweep.log 1줄), C8 = M4(무효값 exit 2·0은 비활성화), C10 = M5
(mode 최상위·ignored_flags), C11 = M4(비활성화 경로).
fixture: 임시 git 저장소 + worktree 1~3개(eligible·active 혼합 — H1 검증 전제).
"""
from __future__ import annotations

import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

# 단위 케이스는 모듈 직접 임포트 — 부재 시 수집 실패 = RED(M9).
import worktree_artifacts as artifacts  # noqa: E402
import worktree_gate_lib as lib  # noqa: E402

# CLI 통합 케이스 헬퍼는 1단계(test_worktree_gate) 것을 import(r25 hardening 선례).
from test_worktree_gate import clean_env, git, run_gate, write_file  # noqa: E402


def make_repo(root):
    """초기 커밋 저장소 — worktree add 전제."""
    repo = root / f'repo-{uuid.uuid4().hex[:8]}'
    repo.mkdir()
    write_file(repo, 'docs/readme.md', 'readme\n')
    git(repo, '-c', 'advice.defaultBranch=false', 'init')
    git(repo, 'add', '-A')
    assert git(repo, 'commit', '-m', 'init').returncode == 0
    return repo


def add_worktree(repo, task, phase='active'):
    """관리 worktree 생성 — phase 지정 시 state.json·worktree.json 기록."""
    wt = repo.parent / f'{repo.name}-worktrees' / task
    completed = git(repo, 'worktree', 'add', '-b', f'wt/{task}', str(wt))
    assert completed.returncode == 0, completed.stderr
    folder = repo / 'docs/task-id' / task
    folder.mkdir(parents=True)
    (folder / 'state.json').write_text(
        json.dumps({'phase': phase}), encoding='utf-8')
    (folder / 'worktree.json').write_text(
        json.dumps({'version': 1, 'task': task}), encoding='utf-8')
    return wt


def make_ignored_artifact(wt, name='node_modules', files=2):
    """ignored 부산물 디렉터리 — .gitignore 등록 + 파일 files개(파일당 ~4MiB —
    recovered_gb 소수 2자리 반올림이 0이 되지 않게 하는 최소 크기)."""
    write_file(wt, '.gitignore', f'{name}/\n')
    for index in range(files):
        write_file(wt, f'{name}/pkg/file{index}.bin', 'x' * (2**22 + index))
    return wt / name


def make_ls_files_shim(root):
    """ls-files 차단 PATH git 심(A14 — make_git_shim 패턴 국소 복제).

    test_worktree_gate.py는 무수정 계약(보존 제약 2)이라 블록 종류 확장 대신
    본 파일에 동일 패턴을 복제한다. ls-files 외에는 실제 git으로 execv한다.
    """
    real_git = shutil.which('git')
    assert real_git, 'git 실행 파일을 찾을 수 없다'
    shim_dir = root / f'shim-{uuid.uuid4().hex[:8]}'
    shim_dir.mkdir(parents=True)
    body = f'''#!/usr/bin/env python3
import os, sys
RG = {real_git!r}; A = sys.argv[1:]
if any(A[i] == 'ls-files' for i in range(len(A))):
    print('fatal: shim blocked ls-files', file=sys.stderr); sys.exit(1)
os.execv(RG, [RG] + A)
'''
    shim = shim_dir / 'git'
    shim.write_text(body, encoding='utf-8')
    shim.chmod(0o755)
    return shim_dir


class WorktreeArtifactsUnitTests(unittest.TestCase):
    """D1~D3·A1~A15 — 가드·집계 순수함수 직접 호출(fixture 자체 중복)."""

    maxDiff = None

    def setUp(self):
        tmp = __import__('tempfile').TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.assertEqual(
            git(self.root, 'rev-parse', '--is-inside-work-tree').returncode, 128)

    def sweep(self, repo, **kwargs):
        """sweep_artifacts in-process 호출 — classify_entries의 worktree list는
        프로세스 cwd의 git을 따르므로 fixture 저장소로 chdir한다(CLI subprocess는
        cwd=repo라 무관)."""
        saved = os.getcwd()
        os.chdir(repo)
        self.addCleanup(os.chdir, saved)
        return artifacts.sweep_artifacts(repo, **kwargs)

    # ------------------------------------------------------------- D — lib

    def test_d1_disk_usage_report_keys(self):
        report = lib.disk_usage_report(str(self.root))
        self.assertEqual(set(report), {'free_gb', 'total_gb', 'low'})
        self.assertGreater(report['free_gb'], 0)
        self.assertGreater(report['total_gb'], 0)

    def test_d2_min_free_gb_invalid_values(self):
        for raw in ('abc', '-1', 'nan', 'inf', '10737418240'):
            with self.subTest(raw=raw):
                with mock.patch.dict(os.environ,
                                     {'WORKTREE_MIN_FREE_GB': raw}):
                    with self.assertRaises(lib.GateConfigError):
                        lib.min_free_gb()

    def test_d3_min_free_gb_default_and_zero(self):
        with mock.patch.dict(os.environ, {}):
            os.environ.pop('WORKTREE_MIN_FREE_GB', None)
            self.assertEqual(lib.min_free_gb(), 10.0)
            os.environ['WORKTREE_MIN_FREE_GB'] = '2.5'
            self.assertEqual(lib.min_free_gb(), 2.5)
            # 0은 무효값이 아니라 비활성화다 — low 항상 false·보고 유지(M4).
            os.environ['WORKTREE_MIN_FREE_GB'] = '0'
            self.assertEqual(lib.min_free_gb(), 0.0)
            report = lib.disk_usage_report(str(self.root))
            self.assertFalse(report['low'])
            self.assertIn('free_gb', report)

    # ------------------------------------------------- A — 가드·회수 엔진

    def test_a1_ignored_node_modules_passes_guard(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a1', phase='done')
        make_ignored_artifact(wt)
        candidates = artifacts.scan_candidates(wt)
        self.assertEqual([path.name for path in candidates], ['node_modules'])
        passed, skipped = artifacts.guard_candidates(wt, candidates)
        self.assertEqual(len(passed), 1)
        self.assertEqual(skipped, [])

    def test_a2_tracked_build_dir_preserved_whole(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a2', phase='done')
        write_file(wt, '.gitignore', 'build/\n')
        write_file(wt, 'build/out.o', 'x\n')
        assert git(wt, 'add', '-f', 'build/out.o').returncode == 0
        assert git(wt, 'commit', '-m', 'tracked build').returncode == 0
        candidates = artifacts.scan_candidates(wt)
        self.assertEqual([path.name for path in candidates], ['build'])
        passed, skipped = artifacts.guard_candidates(wt, candidates)
        self.assertEqual(passed, [])
        self.assertEqual(skipped,
                         [{'path': 'build', 'reason': 'tracked_present'}])

    def test_a3_no_gitignore_fails_closed(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a3', phase='done')
        write_file(wt, 'node_modules/pkg/index.js', 'x\n')
        passed, skipped = artifacts.guard_candidates(
            wt, artifacts.scan_candidates(wt))
        self.assertEqual(passed, [])
        self.assertEqual(skipped,
                         [{'path': 'node_modules', 'reason': 'not_ignored'}])

    def test_a4_untracked_source_survives_sweep(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a4', phase='done')
        make_ignored_artifact(wt)
        write_file(wt, 'src.py', 'print("src")\n')
        write_file(wt, 'docs/notes.md', 'notes\n')
        report = self.sweep(repo, dry_run=False)
        self.assertTrue((wt / 'src.py').exists())
        self.assertTrue((wt / 'docs/notes.md').exists())
        self.assertFalse((wt / 'node_modules').exists())

    def test_a5_idea_and_cache_never_candidates(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a5', phase='done')
        write_file(wt, '.gitignore', '.idea/\n.cache/\n')
        write_file(wt, '.idea/workspace.xml', 'x\n')
        write_file(wt, '.cache/data.bin', 'x\n')
        self.assertEqual(artifacts.scan_candidates(wt), [])

    def test_a6_egg_info_suffix_candidate(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a6', phase='done')
        write_file(wt, '.gitignore', '*.egg-info/\n')
        write_file(wt, 'pkg.egg-info/PKG-INFO', 'x\n')
        passed, skipped = artifacts.guard_candidates(
            wt, artifacts.scan_candidates(wt))
        self.assertEqual([rel for _path, rel in passed], ['pkg.egg-info'])
        self.assertEqual(skipped, [])

    def test_a7_nested_candidates_pruned(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a7', phase='done')
        write_file(wt, '.gitignore', 'node_modules/\n')
        write_file(wt, 'node_modules/inner/node_modules/deep.js', 'x\n')
        write_file(wt, 'node_modules/pkg/sub/dir/file.js', 'x\n')
        candidates = artifacts.scan_candidates(wt)
        self.assertEqual([path.name for path in candidates], ['node_modules'])

    def test_a8_measure_bytes_sum(self):
        target = self.root / 'measure'
        write_file(target, 'a.txt', '123')
        write_file(target, 'sub/b.txt', '12345')
        write_file(target, 'sub/c.txt', '12')
        self.assertEqual(artifacts.measure_bytes(target), 10)

    def test_a9_dry_run_leaves_files(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a9', phase='done')
        make_ignored_artifact(wt)
        report = self.sweep(repo, dry_run=True)
        self.assertTrue((wt / 'node_modules/pkg/file0.bin').exists())
        self.assertEqual(report['targets'][0]['dry_run'], True)
        self.assertEqual(report['targets'][0]['would_remove'], ['node_modules'])
        self.assertEqual(report['targets'][0]['removed'], [])

    def test_a10_real_sweep_schema_and_recovery(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a10', phase='done')
        make_ignored_artifact(wt)
        expected = artifacts.measure_bytes(wt / 'node_modules')
        report = self.sweep(repo, dry_run=False)
        self.assertFalse((wt / 'node_modules').exists())
        self.assertEqual(report['mode'], 'artifacts-only')  # 최상위 키(M5)
        self.assertEqual(report['summary']['recovered_bytes'], expected)
        self.assertGreater(report['summary']['recovered_gb'], 0)
        for key in ('ok', 'gate', 'subcommand', 'timestamp_utc', 'disk',
                    'targets', 'summary', 'flags', 'saved_to'):
            self.assertIn(key, report)
        target = report['targets'][0]
        self.assertEqual(target['removed'], ['node_modules'])
        self.assertIs(target['managed'], True)
        self.assertIs(target['orphan'], False)

    def test_a11_locked_and_unmanaged_excluded(self):
        repo = make_repo(self.root)
        wt_done = add_worktree(repo, 'a11', phase='done')
        make_ignored_artifact(wt_done)
        wt_locked = add_worktree(repo, 'a11l', phase='done')
        make_ignored_artifact(wt_locked)
        assert git(repo, 'worktree', 'lock', str(wt_locked)).returncode == 0
        wt_manual = repo.parent / f'{repo.name}-worktrees' / 'manual-x'
        assert git(repo, 'worktree', 'add', '--detach', str(wt_manual),
                   'HEAD').returncode == 0
        make_ignored_artifact(wt_manual)
        report = self.sweep(repo, dry_run=False)
        self.assertEqual(report['summary']['unmanaged_excluded'], 1)
        self.assertEqual(report['summary']['locked_excluded'], 1)
        self.assertTrue((wt_locked / 'node_modules').exists())
        self.assertTrue((wt_manual / 'node_modules').exists())
        self.assertFalse((wt_done / 'node_modules').exists())

    def test_a12_remove_failed_skipped_ok_kept(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a12', phase='done')
        make_ignored_artifact(wt)
        with mock.patch.object(artifacts, 'remove_tree',
                               side_effect=NotADirectoryError('파일로 대체됨')):
            report = self.sweep(repo, dry_run=False)
        self.assertTrue(report['ok'])
        self.assertEqual(report['targets'][0]['skipped'],
                         [{'path': 'node_modules', 'reason': 'remove_failed'}])
        self.assertEqual(report['summary']['removed_count'], 0)
        self.assertTrue((wt / 'node_modules').exists())

    def test_a13_measure_error_skipped_ok_kept(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a13', phase='done')
        make_ignored_artifact(wt)
        with mock.patch.object(artifacts, 'measure_bytes',
                               side_effect=OSError('scandir 실패')):
            report = self.sweep(repo, dry_run=False)
        self.assertTrue(report['ok'])
        self.assertEqual(report['targets'][0]['skipped'],
                         [{'path': 'node_modules', 'reason': 'measure_error'}])
        self.assertTrue((wt / 'node_modules').exists())

    def test_a14_ls_files_error_fail_closed(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a14', phase='done')
        make_ignored_artifact(wt)
        shim_dir = make_ls_files_shim(self.root)
        saved_path = os.environ['PATH']
        os.environ['PATH'] = f'{shim_dir}:{saved_path}'
        self.addCleanup(os.environ.__setitem__, 'PATH', saved_path)
        report = self.sweep(repo, dry_run=False)
        self.assertTrue(report['ok'])
        self.assertEqual(report['targets'][0]['skipped'],
                         [{'path': 'node_modules', 'reason': 'ls_files_error'}])
        self.assertTrue((wt / 'node_modules').exists())

    def test_a15_budget_cap_partial_recovery(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'a15', phase='done')
        write_file(wt, '.gitignore', 'node_modules/\ndist/\ntarget/\n')
        for name in ('node_modules', 'dist', 'target'):
            write_file(wt, f'{name}/f.bin', 'x')
        report = self.sweep(repo, dry_run=False, max_dirs=2)
        self.assertTrue(report['budget_exceeded'])
        self.assertEqual(report['summary']['removed_count'], 2)
        survivors = [name for name in ('node_modules', 'dist', 'target')
                     if (wt / name).exists()]
        self.assertEqual(len(survivors), 1)


class WorktreeArtifactsCliTests(unittest.TestCase):
    """C1~C11 — subprocess run_gate(test_worktree_gate 관습). C9는 RED 예외
    (구현 전 통과 확인용 대조)다."""

    maxDiff = None

    def setUp(self):
        tmp = __import__('tempfile').TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.assertEqual(
            git(self.root, 'rev-parse', '--is-inside-work-tree').returncode, 128)

    def gate(self, repo, *args, env_extra=None):
        with mock.patch.dict(os.environ, env_extra or {}):
            return run_gate(repo, *args)

    def test_c1_list_has_disk_field(self):
        repo = make_repo(self.root)
        add_worktree(repo, 'c1', phase='active')
        completed = self.gate(repo, 'list')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(set(payload['disk']), {'free_gb', 'total_gb', 'low'})
        for key in ('entries', 'summary', 'flags', 'saved_to'):
            self.assertIn(key, payload)  # 기존 필드 무변경 — additive

    def test_c2_low_sweep_exit0_flags_empty(self):
        repo = make_repo(self.root)
        add_worktree(repo, 'c2', phase='active')  # eligible 0 fixture(L7)
        completed = self.gate(repo, 'sweep',
                              env_extra={'WORKTREE_MIN_FREE_GB': '99999.9'})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload['disk']['low'])
        self.assertEqual(payload['flags'], [])  # 어휘 무변경(보존 제약 3)

    def test_c3_artifacts_only_recovers_keeps_tracked(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'c3', phase='done')
        make_ignored_artifact(wt)
        completed = self.gate(repo, 'sweep', '--artifacts-only')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertFalse((wt / 'node_modules').exists())
        self.assertTrue((wt / 'docs/readme.md').exists())  # tracked 생존
        self.assertGreater(payload['summary']['recovered_gb'], 0)

    def test_c4_dry_run_artifacts_only_no_change(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'c4', phase='done')
        make_ignored_artifact(wt)
        completed = self.gate(repo, 'sweep', '--dry-run', '--artifacts-only')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue((wt / 'node_modules').exists())  # 무변경
        self.assertEqual(payload['targets'][0]['would_remove'], ['node_modules'])
        self.assertEqual(payload['targets'][0]['removed'], [])

    def test_c5_create_auto_trigger_eligible_only(self):
        repo = make_repo(self.root)
        wt_done = add_worktree(repo, 'c5done', phase='done')
        make_ignored_artifact(wt_done)
        wt_active = add_worktree(repo, 'c5active', phase='active')
        make_ignored_artifact(wt_active)
        completed = self.gate(repo, 'create', '--task', 'c5new',
                              env_extra={'WORKTREE_MIN_FREE_GB': '99999.9'})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload['ok'])
        self.assertEqual(set(payload['disk']), {'free_gb', 'total_gb', 'low'})
        self.assertIn('artifacts_sweep', payload)
        self.assertFalse((wt_done / 'node_modules').exists())   # eligible 회수
        self.assertTrue((wt_active / 'node_modules').exists())  # active 생존(H1)
        self.assertTrue(
            (repo.parent / f'{repo.name}-worktrees' / 'c5new').exists())  # 신규 정상
        log = repo.parent / f'{repo.name}-worktrees' / 'artifacts-sweep.log'
        self.assertTrue(log.exists())  # M12 영수증
        self.assertEqual(len(log.read_text(encoding='utf-8').splitlines()), 1)

    def test_c6_not_low_create_no_artifacts_sweep(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'c6', phase='done')
        make_ignored_artifact(wt)
        completed = self.gate(repo, 'create', '--task', 'c6new')  # 기본 임계
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIn('disk', payload)
        self.assertNotIn('artifacts_sweep', payload)

    def test_c7_low_but_no_artifacts_no_trigger(self):
        repo = make_repo(self.root)
        add_worktree(repo, 'c7', phase='done')  # 부산물 0
        completed = self.gate(repo, 'create', '--task', 'c7new',
                              env_extra={'WORKTREE_MIN_FREE_GB': '99999.9'})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertNotIn('artifacts_sweep', payload)
        log = repo.parent / f'{repo.name}-worktrees' / 'artifacts-sweep.log'
        self.assertFalse(log.exists())  # 회수 미실행 — 로그도 미부착

    def test_c8_invalid_env_exit2_zero_disabled(self):
        repo = make_repo(self.root)
        completed = self.gate(repo, 'create', '--task', 'c8x',
                              env_extra={'WORKTREE_MIN_FREE_GB': 'abc'})
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(completed.stderr.startswith('FAIL worktree gate:'))
        completed = self.gate(repo, 'create', '--task', 'c8y',
                              env_extra={'WORKTREE_MIN_FREE_GB': '0'})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(json.loads(completed.stdout)['disk']['low'])

    def test_c9_plain_sweep_baseline_unchanged(self):
        """RED 예외 대조 케이스(H2) — 기존 sweep 필드만 단언한다. disk additive
        검증은 C1·C2·C11이 담당한다(본 케이스는 배선 전에도 통과해야 한다).
        .gitignore는 본체에 커밋해 둔다 — wt 내 untracked .gitignore는
        salvage_committed(exit 1)를 유발해 베이스라인 대조가 무의미해진다."""
        repo = make_repo(self.root)
        write_file(repo, '.gitignore', 'node_modules/\n')
        assert git(repo, 'add', '-A').returncode == 0
        assert git(repo, 'commit', '-m', 'gitignore').returncode == 0
        wt = add_worktree(repo, 'c9', phase='done')
        write_file(wt, 'node_modules/pkg/file0.bin', 'x')  # ignored 부산물만
        completed = self.gate(repo, 'sweep')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        for key in ('items', 'skipped', 'summary', 'flags', 'saved_to'):
            self.assertIn(key, payload)
        self.assertEqual(payload['subcommand'], 'sweep')
        self.assertFalse((wt / 'node_modules').exists())

    def test_c10_ignored_flags_transparent(self):
        repo = make_repo(self.root)
        wt = add_worktree(repo, 'c10', phase='done')
        make_ignored_artifact(wt)
        completed = self.gate(repo, 'sweep', '--artifacts-only',
                              '--unmanaged', '--drop-branch')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload['mode'], 'artifacts-only')  # 최상위(M5)
        self.assertEqual(payload['summary']['ignored_flags'],
                         ['unmanaged', 'drop-branch'])
        self.assertFalse((wt / 'node_modules').exists())

    def test_c11_zero_threshold_list_low_false(self):
        repo = make_repo(self.root)
        add_worktree(repo, 'c11', phase='active')
        completed = self.gate(repo, 'list',
                              env_extra={'WORKTREE_MIN_FREE_GB': '0'})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIn('disk', payload)
        self.assertFalse(payload['disk']['low'])


if __name__ == '__main__':
    unittest.main()
