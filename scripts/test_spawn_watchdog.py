#!/usr/bin/env python3
"""r44 스폰 워치독 단위테스트 — 진행 신호 스냅샷·버스트 판정 상태 기계·watch 루프 전수(W1~W11·C1~C14).

시간 주입 이원화: 단위(W)는 판정 코어 순수 함수에 now·sleep_fn·snapshot_fn을
주입해 실대기 0으로 판정 분기를 검증하고, CLI(C)는 subprocess 실행 + 임계 인자화
(--threshold-s 2 --burst-interval-s 0.4)로 실측 수 초 내 종료를 검증한다
(subprocess 관습 — import 방식은 CLI RED가 성립하지 않는다, test_neverstuck_gate
docstring 근거; 단위는 import 방식 — 모듈 부재 수집 실패 = RED, r43 M9 선례).
mtime 모의는 os.utime으로 과거 시각을 설정해 실대기 없이 무진행 상태를 조성한다.

claims 대응(r44 plan §5): W3=C-progressing 분기, W4=C2, W5=C3(오탐 0 — 본 과업
핵심), W6/W7=claim 10(stall_input 조건부), W8=C5(결손·전량 부재), W9=C11(무효
구성), W10=r2 M4(소실 불산입), W11=r2 L6(음수 클램프), C12/C13=claim 12,
C14=r2 H6(watch 소실 warn → --lost-exit-cycles 후 exit 2).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import spawn_watchdog as wd

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/spawn_watchdog.py'

REPORT_KEYS = {'ok', 'gate', 'mode', 'timestamp_utc', 'config', 'signals',
               'last_progress_age_s', 'last_progress_source', 'burst',
               'status', 'flags', 'saved_to'}
STALL_KEYS = {'last_tool_age_s', 'last_file_write_age_s',
              'last_assistant_text', 'declared_state'}


def cfg(files=(), repo=None, threshold=600.0, interval=60.0, count=3):
    """판정 코어 최소 구성 — validate_config 산출 dict와 동일 키."""
    return {'watch_files': [str(f) for f in files], 'repo': repo,
            'threshold_s': float(threshold), 'burst_interval_s': float(interval),
            'burst_count': count}


def fake_snap(files, git_ts=None, now=0.0, sha='s1', extra_skipped=()):
    """스냅샷 모형 — files: {경로: mtime}, extra_skipped: skipped 엔트리 첨가."""
    live = dict(files)
    entries = [{'path': p, 'kind': wd.classify(p), 'mtime_utc': wd.iso_utc(m),
                'age_s': round(max(0.0, now - m), 1), 'skipped': False}
               for p, m in files.items()]
    entries.extend(extra_skipped)
    git = None
    if git_ts is not None:
        git = {'repo': '/repo', 'head_sha': sha,
               'head_committer_utc': wd.iso_utc(git_ts),
               'age_s': round(max(0.0, now - git_ts), 1)}
    return {'files': entries, 'live': live, 'git': git, 'git_ts': git_ts}


def run_gate(*args, timeout=30):
    return subprocess.run([sys.executable, str(GATE), *args],
                          stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout)


def git_cmd(*args):
    proc = subprocess.run(['git', *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc


def make_git_repo(path):
    git_cmd('init', '-q', str(path))
    git_cmd('-C', str(path), 'config', 'user.email', 't@example.com')
    git_cmd('-C', str(path), 'config', 'user.name', 't')
    (path / 'f.txt').write_text('v1\n', encoding='utf-8')
    git_cmd('-C', str(path), 'add', '.')
    git_cmd('-C', str(path), 'commit', '-q', '-m', 'c1')


def age_file(path, seconds):
    past = time.time() - seconds
    os.utime(path, (past, past))


def delayed(delay, action):
    timer = threading.Timer(delay, action)
    timer.start()
    return timer


class SpawnWatchdogUnitTests(unittest.TestCase):
    """W1~W11 — import 방식, now/sleep_fn/snapshot_fn 주입(실대기 0)."""

    maxDiff = None

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.now = 1_000_000.0

    def path(self, name):
        return self.root / name

    # --- W1 스냅샷 --------------------------------------------------------

    def test_w1_snapshot_collects_two_file_mtimes(self):
        a, b = self.path('a.jsonl'), self.path('b.md')
        a.write_text('x', encoding='utf-8')
        b.write_text('y', encoding='utf-8')
        os.utime(a, (self.now - 10, self.now - 10))
        os.utime(b, (self.now - 5, self.now - 5))
        snap = wd.real_snapshot(cfg([a, b]), self.now)
        self.assertEqual({e['path'] for e in snap['files']},
                         {str(a), str(b)})
        by_path = {e['path']: e for e in snap['files']}
        self.assertEqual(by_path[str(a)]['age_s'], 10.0)
        self.assertEqual(by_path[str(b)]['age_s'], 5.0)
        self.assertEqual(by_path[str(a)]['mtime_utc'], wd.iso_utc(self.now - 10))
        self.assertFalse(by_path[str(a)]['skipped'])
        self.assertEqual(snap['live'], {str(a): self.now - 10, str(b): self.now - 5})

    # --- W2 분류 ----------------------------------------------------------

    def test_w2_kind_classification(self):
        self.assertEqual(wd.classify('/x/a.jsonl'), 'jsonl')
        self.assertEqual(wd.classify('/x/state.json'), 'file')
        self.assertEqual(wd.classify('/x/bundle.md'), 'file')

    # --- W3/W4/W5 판정 상태 기계 -----------------------------------------

    def test_w3_progressing_below_threshold(self):
        snap = fake_snap({'/w/a.jsonl': self.now - 10}, now=self.now)
        report = wd.judge_once(cfg(threshold=600), now_fn=lambda: self.now,
                               sleep_fn=lambda _s: None,
                               snapshot_fn=lambda _c, _n: snap)
        self.assertEqual(report['status'], 'progressing')
        self.assertFalse(report['burst']['triggered'])
        self.assertEqual(wd.map_exit('progressing'), 0)

    def test_w4_dead_confirmed_after_full_burst_without_change(self):
        snap = fake_snap({'/w/a.jsonl': self.now - 900}, now=self.now)
        report = wd.judge_once(cfg(threshold=10, interval=5, count=3),
                               now_fn=lambda: self.now,
                               sleep_fn=lambda _s: None,
                               snapshot_fn=lambda _c, _n: snap)
        self.assertEqual(report['status'], 'dead_confirmed')
        self.assertEqual(report['burst']['checks'], 3)
        self.assertFalse(report['burst']['changed'])
        self.assertEqual(report['flags'], ['dead_confirmed'])
        self.assertEqual(wd.map_exit('dead_confirmed'), 1)

    def test_w5_burst_reset_on_change(self):
        before = fake_snap({'/w/a.jsonl': self.now - 900}, now=self.now)
        after = fake_snap({'/w/a.jsonl': self.now - 2}, now=self.now + 1)
        calls = []

        def snapshot_fn(_c, _n):
            calls.append(1)
            return before if len(calls) == 1 else after

        report = wd.judge_once(cfg(threshold=10, interval=5, count=3),
                               now_fn=lambda: self.now,
                               sleep_fn=lambda _s: None,
                               snapshot_fn=snapshot_fn)
        self.assertEqual(report['status'], 'recovered')
        self.assertTrue(report['burst']['changed'])
        self.assertGreaterEqual(report['burst']['checks'], 1)
        self.assertEqual(wd.map_exit('recovered'), 0)

    # --- W6/W7 stall_input ------------------------------------------------

    def test_w6_stall_input_mixed_signals(self):
        snap = fake_snap({'/w/a.jsonl': self.now - 10, '/w/b.md': self.now - 5},
                         git_ts=self.now - 3, now=self.now)
        stall = wd.build_stall_input(snap, self.now)
        self.assertEqual(STALL_KEYS <= set(stall), True)
        self.assertEqual(stall['last_tool_age_s'], 10.0)
        self.assertEqual(stall['last_file_write_age_s'], 3.0)
        self.assertIsNone(stall['last_assistant_text'])
        self.assertIsNone(stall['declared_state'])

    def test_w7_stall_input_absent_without_jsonl(self):
        snap = fake_snap({'/w/b.md': self.now - 5}, now=self.now)
        self.assertIsNone(wd.build_stall_input(snap, self.now))
        report = wd.judge_once(cfg(threshold=600), now_fn=lambda: self.now,
                               sleep_fn=lambda _s: None,
                               snapshot_fn=lambda _c, _n: snap)
        self.assertNotIn('stall_input', report)

    # --- W8 결손 ----------------------------------------------------------

    def test_w8_missing_signal_skipped_and_single_all_missing_maps_exit2(self):
        alive, gone = self.path('alive.md'), self.path('gone.md')
        alive.write_text('x', encoding='utf-8')
        gone.write_text('x', encoding='utf-8')
        snap = wd.real_snapshot(cfg([alive, gone]), self.now)
        gone.unlink()
        snap = wd.real_snapshot(cfg([alive, gone]), self.now)
        skipped = [e for e in snap['files'] if e['skipped']]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]['path'], str(gone))
        self.assertIn('reason', skipped[0])
        self.assertIsNone(skipped[0]['mtime_utc'])
        report = wd.judge_once(cfg([alive], threshold=600),
                               now_fn=lambda: self.now,
                               sleep_fn=lambda _s: None,
                               snapshot_fn=lambda _c, _n: snap)
        self.assertEqual(report['status'], 'progressing')
        self.assertEqual(wd.map_exit('signals_lost', 'single'), 2)

    # --- W9 무효 구성 -----------------------------------------------------

    def test_w9_invalid_config_rejected(self):
        import argparse
        base = {'watch_file': ['/tmp/x.jsonl'], 'repo': None,
                'threshold_s': 600.0, 'burst_interval_s': 60.0,
                'burst_count': 3, 'watch': False,
                'poll_interval_s': 60.0, 'max_cycles': 0,
                'lost_exit_cycles': 3}
        cases = [
            {**base, 'threshold_s': 0.0},
            {**base, 'threshold_s': -1.0},
            {**base, 'threshold_s': float('nan')},
            {**base, 'threshold_s': float('inf')},
            {**base, 'burst_count': 0},
            {**base, 'burst_interval_s': -0.5},
            {**base, 'watch_file': [], 'repo': None},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(wd.GateConfigError):
                    wd.validate_config(argparse.Namespace(**payload))
        self.assertEqual(wd.map_exit('signals_lost', 'single'), 2)

    # --- W10 소실 불산입 --------------------------------------------------

    def test_w10_signal_disappearance_is_not_recovery(self):
        before = fake_snap({'/w/a.jsonl': self.now - 900,
                            '/w/b.jsonl': self.now - 900}, now=self.now)
        skipped = {'path': '/w/a.jsonl', 'kind': 'jsonl', 'mtime_utc': None,
                   'reason': '소실', 'skipped': True}
        after = fake_snap({'/w/b.jsonl': self.now - 900}, now=self.now,
                          extra_skipped=[skipped])
        self.assertFalse(wd.detect_change(before, after))
        report = wd.judge_once(cfg(threshold=10, interval=1, count=2),
                               now_fn=lambda: self.now,
                               sleep_fn=lambda _s: None,
                               snapshot_fn=lambda _c, _n: after)
        self.assertEqual(report['status'], 'dead_confirmed')

    # --- W11 음수 클램프 --------------------------------------------------

    def test_w11_negative_age_clamped_to_zero(self):
        future = self.path('future.md')
        future.write_text('x', encoding='utf-8')
        os.utime(future, (self.now + 100, self.now + 100))
        snap = wd.real_snapshot(cfg([future]), self.now)
        self.assertEqual(snap['files'][0]['age_s'], 0.0)
        report = wd.judge_once(cfg([future], threshold=600),
                               now_fn=lambda: self.now,
                               sleep_fn=lambda _s: None,
                               snapshot_fn=lambda _c, _n: snap)
        self.assertEqual(report['last_progress_age_s'], 0.0)


class SpawnWatchdogCliTests(unittest.TestCase):
    """C1~C14 — subprocess 실행, 임계 인자화로 실측 수 초 내 종료."""

    maxDiff = None

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def fresh(self, name):
        path = self.root / name
        path.write_text('line\n', encoding='utf-8')
        return path

    def aged(self, name, seconds):
        path = self.fresh(name)
        age_file(path, seconds)
        return path

    def assert_fail(self, result):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(result.stderr.startswith('FAIL spawn watchdog:'),
                        result.stderr)
        self.assertEqual(result.stdout, '')

    # --- C1 progressing ---------------------------------------------------

    def test_c1_fresh_signals_progressing_full_schema(self):
        session, note = self.fresh('session.jsonl'), self.fresh('bundle.md')
        result = run_gate('--watch-file', str(session), '--watch-file', str(note))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'progressing')
        self.assertFalse(report['burst']['triggered'])
        self.assertEqual(report['mode'], 'single')
        self.assertEqual(report['gate'], 'spawn-watchdog')
        self.assertEqual(set(report), REPORT_KEYS | {'stall_input'})
        self.assertEqual(STALL_KEYS <= set(report['stall_input']), True)
        self.assertEqual(report['config'], {'threshold_s': 600.0,
                                            'burst_interval_s': 60.0,
                                            'burst_count': 3})

    # --- C2 dead_confirmed ------------------------------------------------

    def test_c2_dead_confirmed_within_seconds(self):
        target = self.aged('dead.jsonl', 700)
        started = time.monotonic()
        result = run_gate('--watch-file', str(target),
                          '--threshold-s', '2', '--burst-interval-s', '0.4',
                          timeout=20)
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['ok'])
        self.assertEqual(report['flags'], ['dead_confirmed'])
        self.assertEqual(report['burst']['checks'], 3)
        self.assertFalse(report['burst']['changed'])
        self.assertLess(elapsed, 3.0)

    # --- C3 recovered(오탐 0 — 본 과업 핵심) ------------------------------

    def test_c3_burst_change_recovers(self):
        target = self.aged('burst.jsonl', 700)
        delayed(1.0, lambda: os.utime(target))
        result = run_gate('--watch-file', str(target),
                          '--threshold-s', '2', '--burst-interval-s', '0.4',
                          timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'recovered')
        self.assertTrue(report['burst']['changed'])

    # --- C4~C6·C11 config/env 오류 ---------------------------------------

    def test_c4_no_targets_exit2(self):
        self.assert_fail(run_gate())

    def test_c5_missing_path_only_exit2(self):
        self.assert_fail(run_gate('--watch-file', str(self.root / 'nope.jsonl')))

    def test_c6_non_git_repo_exit2(self):
        plain = self.root / 'plain'
        plain.mkdir()
        self.assert_fail(run_gate('--repo', str(plain)))

    def test_c9_save_writes_audit(self):
        target = self.fresh('saved.jsonl')
        out = self.root / 'audit'
        result = run_gate('--watch-file', str(target), '--save', str(out))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertIsNotNone(report['saved_to'])
        audit_files = list(out.glob('spawn-watchdog-*.json'))
        self.assertEqual(len(audit_files), 1)
        stored = json.loads(audit_files[0].read_text(encoding='utf-8'))
        self.assertEqual(stored['status'], report['status'])

    def test_c10_save_failure_keeps_judgment_exit(self):
        target = self.fresh('c10.jsonl')
        blocker = self.root / 'blocker'
        blocker.write_text('not a dir', encoding='utf-8')
        result = run_gate('--watch-file', str(target), '--save', str(blocker))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertIsNone(report['saved_to'])
        self.assertIn('--save 실패', result.stderr)

    def test_c11_invalid_args_exit2(self):
        target = self.fresh('c11.jsonl')
        for flag, value in (('--threshold-s', '-1'), ('--threshold-s', 'nan'),
                            ('--burst-count', '0'), ('--burst-interval-s', '-1')):
            with self.subTest(flag=flag, value=value):
                self.assert_fail(run_gate('--watch-file', str(target),
                                          flag, value))

    # --- C7/C8 git 신호 ---------------------------------------------------

    def test_c7_git_repo_head_signal(self):
        repo = self.root / 'repo'
        make_git_repo(repo)
        result = run_gate('--repo', str(repo))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'progressing')
        self.assertEqual(report['last_progress_source'], 'git:head')
        self.assertTrue(report['signals']['git']['head_sha'])
        self.assertEqual(report['signals']['files'], [])

    def test_c8_new_commit_counts_as_progress(self):
        repo = self.root / 'repo'
        make_git_repo(repo)
        first = json.loads(run_gate('--repo', str(repo)).stdout)
        time.sleep(0.05)
        (repo / 'f.txt').write_text('v2\n', encoding='utf-8')
        git_cmd('-C', str(repo), 'add', '.')
        git_cmd('-C', str(repo), 'commit', '-q', '-m', 'c2')
        second = json.loads(run_gate('--repo', str(repo),
                                     '--threshold-s', '2').stdout)
        self.assertEqual(second['status'], 'progressing')
        self.assertNotEqual(first['signals']['git']['head_sha'],
                            second['signals']['git']['head_sha'])

    # --- C12~C14 watch 루프 ----------------------------------------------

    def watch_run(self, *extra, timeout=20):
        return run_gate('--watch', '--poll-interval-s', '0.2', *extra,
                        timeout=timeout)

    def test_c12_watch_two_cycles_exit0(self):
        target = self.fresh('watch.jsonl')
        result = self.watch_run('--watch-file', str(target),
                                '--max-cycles', '2')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        reports = [json.loads(line) for line in lines]
        self.assertTrue(all(r['mode'] == 'watch' for r in reports))
        self.assertEqual([r['cycle'] for r in reports], [1, 2])
        self.assertTrue(all(r['status'] == 'progressing' for r in reports))

    def test_c13_watch_dead_exits1(self):
        target = self.aged('watch-dead.jsonl', 700)
        result = self.watch_run('--watch-file', str(target),
                                '--threshold-s', '1',
                                '--burst-interval-s', '0.2',
                                '--burst-count', '2',
                                '--max-cycles', '5')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        last = json.loads(lines[-1])
        self.assertEqual(last['status'], 'dead_confirmed')
        self.assertEqual(last['flags'], ['dead_confirmed'])

    def test_c14_watch_signals_lost_then_exit2(self):
        target = self.fresh('watch-lost.jsonl')
        timer = delayed(1.0, target.unlink)
        self.addCleanup(timer.cancel)
        result = self.watch_run('--watch-file', str(target),
                                '--threshold-s', '600',
                                '--lost-exit-cycles', '2',
                                '--max-cycles', '15')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        reports = [json.loads(line) for line in lines]
        lost = [r for r in reports if r['status'] == 'signals_lost']
        self.assertEqual([r['lost_cycles'] for r in lost], [1, 2])
        self.assertTrue(all(r['mode'] == 'watch' for r in lost))


if __name__ == '__main__':
    unittest.main()
