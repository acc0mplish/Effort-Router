#!/usr/bin/env python3
"""r44 스폰 워치독 CLI — 장기·비동기 스폰의 진행 신호 무진행 판정(보고만).

진행 신호는 전부 호출자가 지정한다(하니스별 경로 탐색 규칙 미내장): 감시 대상
파일(--watch-file, `*.jsonl` 접미는 세션 jsonl — tool-age 신호원, 그 외 일반
파일 — file-write 신호원)의 mtime과 git 저장소(--repo)의 HEAD sha(신호 시각 =
committer 시각)다. 판정(plan §1.2·§3.2): last_progress = 전 신호 시각 최댓값,
age = max(0, now − ts)(음수 클램프 — 시계 스큐 방어) → age < threshold면
progressing(exit 0) → 이상이면 버스트(burst_interval_s 간격 burst_count회
재스냅샷, 변화 = 기존 신호 mtime 갱신·HEAD sha 변화·신규 경로 등장 한정 —
신호 소실은 회복으로 산입하지 않는다) → 변화 1건이면 recovered(exit 0 —
오탐 0 계약), 연속 무변화면 dead_confirmed(exit 1 — 응답은 무활동 확정 판정 시각 confirmed_at을
동반하며 스냅샷 timestamp와 독립이다). 버스트 재스냅 중 감시 신호가 전량 소실하면
회복으로 산입하지 않고 burst.signals_lost로 병기한다.

**자동 정지 없음 — 보고만이다.** 감시 대상 프로세스·파일에 어떤 시그널·종료·
쓰기도 하지 않는다(--save 감사 파일이 유일한 쓰기). 판정·정지·재스폰 권한은
메인 세션·사용자다(jev·r24 권한 계약 준용). dead_confirmed = 무활동 확정이지
사망 확정이 아니다 — 정상 종료(완료 보고 후 종료)를 포함하므로 수신 주체는
재스폰 판정 전 상태 파일 phase 대조와 마지막 산출 열람을 수행해야 한다.

모드: 1회 판정(기본 — 무상태, 타이머 리셋은 최신 신호 시각부터 재산정의 자연
귀결)과 --watch 루프(사이클마다 판정 JSON 1줄 jsonl 스트림, dead_confirmed
사이클에서 exit 1 종료, SIGINT/SIGTERM은 운영자 정지로 exit 0). watch에서 감시
신호 전부 소실(세션 종료로 jsonl 이동 등 — 가장 흔한 운영 이벤트)은 즉시
종료하지 않고 status:"signals_lost"·lost_cycles warn 보고로 poll을 지속하다
연속 --lost-exit-cycles(기본 3) 도달 시 exit 2로 종료한다(영구 warn 방지
상한). git 실패는 watch에서도 즉시 exit 2다(저장소 붕괴 = 재기동 대상).

종료코드(게이트 관습): 0 progressing·recovered · 1 dead_confirmed(ok:true ∧
flags:["dead_confirmed"] — 확인 의무) · 2 config/env 오류(감시 대상 0개·최초
스냅샷 전량 부재(단발)·비git repo·git 실패·무효 인자·watch 소실 상한 도달 —
stderr `FAIL spawn watchdog: <사유>`, stdout 없음. --save 실패만 판정 exit
유지 + saved_to:null + stderr 경고 — intake 계약 준용) · 3 미사용(상향 경로
없음). 표준 라이브러리만으로 자기완결한다(결정론 관습 — jev·API 무의존).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

GATE = 'spawn-watchdog'
EXIT_PASS = 0
EXIT_DEAD = 1
EXIT_CONFIG = 2
GIT_TIMEOUT_S = 5


class GateConfigError(Exception):
    """무효 입력·환경 오류 — exit 2(이유가 붙은 bypass)로 변환한다."""


class WatchStopped(Exception):
    """운영자 시그널(SIGINT/SIGTERM) — 보고 아닌 정지, exit 0."""


def fail_config(reason: str) -> None:
    print(f'FAIL spawn watchdog: {reason}', file=sys.stderr)
    raise SystemExit(EXIT_CONFIG)


# ---------------------------------------------------------------- 신호 스냅샷

def classify(path: str) -> str:
    """`*.jsonl` 접미 = 세션 jsonl(tool-age), 그 외 = 일반 파일(file-write)."""
    return 'jsonl' if path.endswith('.jsonl') else 'file'


def iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace(
        '+00:00', 'Z')


def git_head(repo: str) -> tuple[str, str, float]:
    """HEAD sha·committer ISO·epoch — 실패는 exit 2(watch에서도 즉시)."""
    try:
        proc = subprocess.run(
            ['git', '-C', repo, 'log', '-1', '--format=%H%n%cI'],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as error:
        raise GateConfigError(f'git 호출 실패({repo}): {error}') from error
    if proc.returncode != 0:
        raise GateConfigError(
            f'git 호출 실패({repo}): {proc.stderr.strip() or proc.returncode}')
    lines = proc.stdout.strip().splitlines()
    if len(lines) < 2 or not lines[0].strip():
        raise GateConfigError(f'git HEAD 출력 해석 실패({repo})')
    sha, committed = lines[0].strip(), lines[-1].strip()
    try:
        ts = datetime.fromisoformat(committed).timestamp()
    except ValueError as error:
        raise GateConfigError(
            f'git 커밋 시각 해석 실패({repo}): {committed}') from error
    return sha, committed, ts


def real_snapshot(config: dict, now: float) -> dict:
    """파일 mtime + git HEAD 스냅샷 — 부재 신호는 skipped 투명 표기."""
    entries = []
    live = {}
    for path in config['watch_files']:
        kind = classify(path)
        try:
            stat = os.stat(path)
        except OSError as error:
            entries.append({'path': path, 'kind': kind, 'mtime_utc': None,
                            'reason': f'stat 실패: {error}', 'skipped': True})
            continue
        mtime = stat.st_mtime
        live[path] = mtime
        entries.append({'path': path, 'kind': kind, 'mtime_utc': iso_utc(mtime),
                        'age_s': round(max(0.0, now - mtime), 1),
                        'skipped': False})
    git = None
    git_ts = None
    if config['repo'] is not None:
        sha, committed, git_ts = git_head(config['repo'])
        git = {'repo': config['repo'], 'head_sha': sha,
               'head_committer_utc': committed,
               'age_s': round(max(0.0, now - git_ts), 1)}
    return {'files': entries, 'live': live, 'git': git, 'git_ts': git_ts}


def detect_change(base: dict, new: dict) -> bool:
    """변화의 정의(r2 M4): mtime 갱신·HEAD sha 변화·신규 등장 — 소실 불산입."""
    old = base['live']
    for path, mtime in new['live'].items():
        if path not in old or old[path] != mtime:
            return True
    old_sha = base['git']['head_sha'] if base['git'] else None
    new_sha = new['git']['head_sha'] if new['git'] else None
    return old_sha != new_sha


# ---------------------------------------------------------------- 판정 코어

def progress_candidates(snap: dict) -> list[tuple[float, str]]:
    candidates = [(mtime, f'{classify(path)}:{path}')
                  for path, mtime in snap['live'].items()]
    if snap['git'] is not None:
        candidates.append((snap['git_ts'], 'git:head'))
    return candidates


def build_stall_input(snap: dict, now: float) -> dict | None:
    """jev stall 입력 조립 — jsonl 신호 ≥1일 때만(조건부 필드). 주장 2종 null."""
    ages = [max(0.0, now - m) for p, m in snap['live'].items()
            if classify(p) == 'jsonl']
    if not ages:
        return None
    others = [max(0.0, now - m) for p, m in snap['live'].items()
              if classify(p) != 'jsonl']
    if snap['git'] is not None:
        others.append(max(0.0, now - snap['git_ts']))
    return {'last_tool_age_s': round(min(ages), 1),
            'last_file_write_age_s': round(min(others), 1) if others else None,
            'last_assistant_text': None, 'declared_state': None}


def build_report(config: dict, snap: dict, now: float, status: str, burst: dict,
                 mode: str = 'single', cycle: int | None = None,
                 lost_cycles: int | None = None,
                 confirmed_at: float | None = None) -> dict:
    report = {'ok': True, 'gate': GATE, 'mode': mode}
    if mode == 'watch':
        report['cycle'] = cycle
    report['timestamp_utc'] = iso_utc(now)
    report['config'] = {'threshold_s': config['threshold_s'],
                        'burst_interval_s': config['burst_interval_s'],
                        'burst_count': config['burst_count']}
    report['signals'] = {'files': snap['files'], 'git': snap['git']}
    if status == 'signals_lost':
        report['last_progress_age_s'] = None
        report['last_progress_source'] = None
        report['lost_cycles'] = lost_cycles
    else:
        top_ts, top_source = max(progress_candidates(snap))
        report['last_progress_age_s'] = round(max(0.0, now - top_ts), 1)
        report['last_progress_source'] = top_source
    report['burst'] = dict(burst)
    report['status'] = status
    report['flags'] = ['dead_confirmed'] if status == 'dead_confirmed' else []
    if status == 'dead_confirmed' and confirmed_at is not None:
        report['confirmed_at'] = iso_utc(confirmed_at)
    stall = build_stall_input(snap, now)
    if stall is not None:
        report['stall_input'] = stall
    report['saved_to'] = None
    return report


def judge_once(config: dict, now_fn=time.time, sleep_fn=time.sleep,
               snapshot_fn=None, mode: str = 'single',
               cycle: int | None = None) -> dict:
    """1 사이클 판정 — now/sleep/snapshot 주입형(테스트는 초 단위 인자화)."""
    if snapshot_fn is None:
        snapshot_fn = real_snapshot
    now = now_fn()
    snap = snapshot_fn(config, now)
    burst = {'triggered': False, 'checks': 0, 'changed': False,
             'signals_lost': False}
    if not snap['live'] and snap['git'] is None:
        return build_report(config, snap, now, 'signals_lost', burst,
                            mode=mode, cycle=cycle)
    status = 'progressing'
    confirmed_at = None
    top_ts = max(ts for ts, _ in progress_candidates(snap))
    if max(0.0, now - top_ts) >= config['threshold_s']:
        burst['triggered'] = True
        status = 'dead_confirmed'
        for _ in range(config['burst_count']):
            sleep_fn(config['burst_interval_s'])
            burst['checks'] += 1
            now2 = now_fn()
            resnap = snapshot_fn(config, now2)
            if detect_change(snap, resnap):
                burst['changed'] = True
                status = 'recovered'
                snap, now = resnap, now2
                break
            if not resnap['live'] and resnap['git'] is None:
                burst['signals_lost'] = True
        if status == 'dead_confirmed':
            confirmed_at = now_fn()
    return build_report(config, snap, now, status, burst, mode=mode, cycle=cycle,
                        confirmed_at=confirmed_at)


def map_exit(status: str, mode: str = 'single') -> int:
    if status == 'dead_confirmed':
        return EXIT_DEAD
    if status == 'signals_lost':
        return EXIT_CONFIG if mode == 'single' else EXIT_PASS
    return EXIT_PASS


# ---------------------------------------------------------------- 감사 저장

def save_report(save_dir: str, report: dict) -> tuple[str | None, str | None]:
    """단발 감사 저장 — (경로, None) 또는 (None, 사유). jev·r24 계약 평행."""
    try:
        directory = Path(save_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = directory / f'{GATE}-{stamp}.json'
        payload = {**report, 'saved_to': str(path)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    except OSError as error:
        return None, str(error)
    return str(path), None


def open_watch_audit(save_dir: str) -> Path | None:
    """watch 감사 jsonl 파일 1개 생성(사이클별 append) — 실패 시 warn 후 계속."""
    try:
        directory = Path(save_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        return directory / f'{GATE}-{stamp}.json'
    except OSError as error:
        print(f'WARN spawn watchdog: --save 실패 — 감사 없이 계속한다: {error}',
              file=sys.stderr)
        return None


def append_audit(save_dir: str | None, audit_path: Path | None,
                 report: dict) -> str | None:
    if save_dir is None or audit_path is None:
        return None
    try:
        with open(audit_path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps({**report, 'saved_to': str(audit_path)},
                                    ensure_ascii=False) + '\n')
    except OSError as error:
        print(f'WARN spawn watchdog: --save 실패 — 감사 없이 계속한다: {error}',
              file=sys.stderr)
        return None
    return str(audit_path)


# ---------------------------------------------------------------- CLI·루프

def check_finite(name: str, value) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        raise GateConfigError(f'{name}은 유한 수여야 한다: {value!r}')


def validate_config(args: argparse.Namespace) -> dict:
    watch_files = args.watch_file or []
    if not watch_files and args.repo is None:
        raise GateConfigError(
            '감시 대상이 0개다 — --watch-file 또는 --repo 지정이 필요하다')
    check_finite('--threshold-s', args.threshold_s)
    if args.threshold_s <= 0:
        raise GateConfigError(
            f'--threshold-s는 양수여야 한다: {args.threshold_s!r}')
    check_finite('--burst-interval-s', args.burst_interval_s)
    if args.burst_interval_s < 0:
        raise GateConfigError(
            f'--burst-interval-s는 0 이상이어야 한다: {args.burst_interval_s!r}')
    if args.burst_count < 1:
        raise GateConfigError(
            f'--burst-count는 1 이상 정수여야 한다: {args.burst_count!r}')
    poll, max_cycles, lost_exit = (
        args.poll_interval_s, args.max_cycles, args.lost_exit_cycles)
    if args.watch:
        check_finite('--poll-interval-s', poll)
        if poll <= 0:
            raise GateConfigError(
                f'--poll-interval-s는 양수여야 한다: {poll!r}')
        if max_cycles < 0:
            raise GateConfigError(
                f'--max-cycles는 0 이상 정수여야 한다: {max_cycles!r}')
        if lost_exit < 0:
            raise GateConfigError(
                f'--lost-exit-cycles는 0 이상 정수여야 한다: {lost_exit!r}')
    return {'watch_files': [os.path.abspath(os.path.expanduser(p))
                            for p in watch_files],
            'repo': (os.path.abspath(os.path.expanduser(args.repo))
                     if args.repo else None),
            'threshold_s': args.threshold_s,
            'burst_interval_s': args.burst_interval_s,
            'burst_count': args.burst_count,
            'poll_interval_s': poll,
            'max_cycles': max_cycles,
            'lost_exit_cycles': lost_exit}


class GateArgumentParser(argparse.ArgumentParser):
    """argparse 오류도 게이트 계약 어휘로 통일 — FAIL 접두 + exit 2."""

    def error(self, message: str) -> None:
        fail_config(message)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = GateArgumentParser(
        prog='spawn_watchdog.py',
        description='r44 스폰 워치독 — 진행 신호 무진행 판정(보고만)')
    parser.add_argument('--watch-file', action='append', default=None,
                        metavar='경로', help='감시 대상 파일(반복 가능 — '
                        '*.jsonl은 세션 jsonl 분류)')
    parser.add_argument('--repo', default=None,
                        help='git 저장소 경로(진행 신호 = HEAD sha 변화)')
    parser.add_argument('--threshold-s', type=float, default=600.0,
                        help='무진행 판정 임계(초, 기본 600)')
    parser.add_argument('--burst-interval-s', type=float, default=60.0,
                        help='버스트 확인 간격(초, 기본 60)')
    parser.add_argument('--burst-count', type=int, default=3,
                        help='버스트 확인 횟수(기본 3)')
    parser.add_argument('--watch', action='store_true',
                        help='루프 모드 — 사이클마다 판정 JSON 1줄(jsonl 스트림)')
    parser.add_argument('--poll-interval-s', type=float, default=60.0,
                        help='watch 사이클 간격(초, 기본 60 — watch 전용)')
    parser.add_argument('--max-cycles', type=int, default=0,
                        help='watch 사이클 상한(0=무한 — watch 전용)')
    parser.add_argument('--lost-exit-cycles', type=int, default=3,
                        help='신호 전부 소실 warn 연속 상한(기본 3 — watch 전용)')
    parser.add_argument('--save', default=None, metavar='DIR',
                        help='감사 저장 디렉터리(단발 JSON·watch 사이클별 append)')
    return parser.parse_args(argv)


def _install_signal_handlers() -> None:
    def handler(_signum, _frame):
        raise WatchStopped()
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def run_watch(config: dict, save_dir: str | None) -> None:
    """루프 모드 — dead_confirmed exit 1·소실 상한 exit 2·운영자 정지 exit 0."""
    audit_path = open_watch_audit(save_dir) if save_dir is not None else None
    lost = 0
    cycle = 0
    try:
        while config['max_cycles'] == 0 or cycle < config['max_cycles']:
            cycle += 1
            report = judge_once(config, mode='watch', cycle=cycle)
            if report['status'] == 'signals_lost':
                lost += 1
                report['lost_cycles'] = lost
            else:
                lost = 0
            report['saved_to'] = append_audit(save_dir, audit_path, report)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            if report['status'] == 'dead_confirmed':
                raise SystemExit(EXIT_DEAD)
            if (report['status'] == 'signals_lost'
                    and lost >= config['lost_exit_cycles']):
                raise SystemExit(EXIT_CONFIG)
            time.sleep(config['poll_interval_s'])
    except WatchStopped:
        raise SystemExit(EXIT_PASS)
    except GateConfigError as error:
        fail_config(str(error))
    raise SystemExit(EXIT_PASS)


def emit_single(report: dict, save_dir: str | None) -> None:
    """단발 출력 — 저장 실패만 판정 stdout 보존 후 판정 exit 유지(intake 계약)."""
    exit_code = map_exit(report['status'])
    if save_dir is not None:
        saved, save_error = save_report(save_dir, report)
        if saved is None:
            print(json.dumps(report, ensure_ascii=False), flush=True)
            print(f'WARN spawn watchdog: --save 실패 — 판정 결과는 위 stdout '
                  f'JSON에 보존됐다: {save_error}', file=sys.stderr)
            raise SystemExit(exit_code)
        report['saved_to'] = saved
    print(json.dumps(report, ensure_ascii=False), flush=True)
    raise SystemExit(exit_code)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        config = validate_config(args)
        if args.watch:
            _install_signal_handlers()
            run_watch(config, args.save)
            raise SystemExit(EXIT_PASS)  # run_watch는 전 경로 SystemExit — 단발 블록은 watch에서 도달 불가(흐름 명시)
        report = judge_once(config)
        if report['status'] == 'signals_lost':
            raise GateConfigError(
                '최초 스냅샷에서 감시 신호가 전량 부재하다 — 감시 대상 경로 확인')
    except WatchStopped:
        # 핸들러 등록~run_watch 진입 경합 창의 SIGINT/SIGTERM도 운영자 정지 exit 0으로 흡수
        raise SystemExit(EXIT_PASS)
    except GateConfigError as error:
        fail_config(str(error))
    emit_single(report, args.save)


if __name__ == '__main__':
    main()
