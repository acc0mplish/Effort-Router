#!/usr/bin/env python3
"""r43 워크트리 부산물 회수 엔진 — 가드 3중(패턴 ∧ check-ignore ∧ tracked 0) 결정.

worktree_gate.py의 `sweep --artifacts-only`·create 자동 트리거가 호출하는 회수
엔진이다. 삭제 후보는 디렉터리 세그먼트명이 화이트리스트에 맞는 디렉터리뿐이며
(파일·symlink는 범위 밖), 가드 3중을 전부 통과한 것만 rmtree한다 — 부분 삭제는
없고 tracked 파일 1개로 디렉터리 전체가 보존된다(보존 제약 8). 대상은 재생성
가능한 ignored 부산물 한정이라 파기 무손실이며, 미커밋 소스·non-ignored untracked는
check-ignore가 원천 차단한다(fail-closed). .idea·.vscode·.cache는 화이트리스트
제외(재생성 불가·누적 데이터 — 무인 삭제의 잔여 사용자 데이터 손실 경로 차단).
회수는 flags를 발행하지 않고 exit 어휘에 관여하지 않는다(보존 제약 3). stdlib만
사용(미러 동봉 계약 — claim 13).
"""
from __future__ import annotations

import fnmatch
import os
import shutil
from pathlib import Path
from typing import Any

import worktree_gate_lib as lib

# §3.3 패턴 화이트리스트 — 계획 확정값(변경 금지). .cache 의도적 제외(claim 27).
ARTIFACT_DIR_NAMES = frozenset({
    'node_modules', 'dist', 'build', 'out', 'target', '__pycache__',
    '.venv', 'venv', '.pytest_cache', '.mypy_cache',
    '.ruff_cache', '.tox', '.nox', '.eggs', '.next', '.nuxt',
    '.output', '.turbo', '.parcel-cache', 'coverage', 'htmlcov',
    '.gradle',
})
ARTIFACT_DIR_SUFFIXES = ('.egg-info',)   # fnmatch '*.egg-info'
# create 자동 트리거 예산(r2 M10) — low 상태의 모든 create가 전수 스캔·측정의
# 임계 경로에 걸리지 않게 하는 결론론 상한. 수동 sweep은 예산 미적용(사용자 명시).
AUTO_TRIGGER_MAX_DIRS = 50
AUTO_TRIGGER_MAX_FILES = 200000


def is_artifact_name(name: str) -> bool:
    """G1 패턴 가드 — 디렉터리 세그먼트명 매칭(화이트리스트 ∨ suffix fnmatch)."""
    return name in ARTIFACT_DIR_NAMES or any(
        fnmatch.fnmatch(name, f'*{suffix}') for suffix in ARTIFACT_DIR_SUFFIXES)


def scan_candidates(wt: Path) -> list[Path]:
    """worktree 전체에서 부산물 후보 디렉터리 수집 — 발견 지점에서 하위 미진입
    (prune — node_modules 내부의 node_modules 중복 스캔 없음, A7). symlink는
    후보에서 제외한다(rmtree 대상 아님 — §3.3)."""
    found: list[Path] = []
    for dirpath, dirnames, _filenames in os.walk(wt):
        keep: list[str] = []
        for name in dirnames:
            full = Path(dirpath) / name
            if full.is_symlink():
                keep.append(name)  # walk가 따라가지 않는다(followlinks 기본 off)
            elif is_artifact_name(name):
                found.append(full)
            else:
                keep.append(name)
        dirnames[:] = keep
    return found


def guard_candidates(wt: Path, candidates: list[Path]) -> tuple[list, list]:
    """가드 3중 판정 — (통과 [(절대경로, 상대경로)], skipped [{path, reason}]).

    G2 check-ignore(cwd=해당 worktree) 미통과는 not_ignored·git 오류(0/1 외
    exit)는 check_ignore_error, G3 ls-files 오류는 ls_files_error·tracked 1건이라도
    있으면 tracked_present로 디렉터리 전체 보존한다(부분 삭제 없음). 전 실패
    경로 fail-closed다. check-ignore는 --no-index로 패턴 전용 판정을 한다 —
    기본 모드는 index를 consult해 tracked 경로를 무조건 not-ignored로 돌려
    tracked_present 사유가 도달 불가능하고(G3 무의미화) ignore 규칙 유무라는
    G2 본래 질문과 어긋난다. tracked 보증은 G3가 단독 담당한다."""
    passed: list[tuple[Path, str]] = []
    skipped: list[dict[str, str]] = []
    for path in candidates:
        rel = path.relative_to(wt).as_posix()
        check = lib.run_git('check-ignore', '-q', '--no-index', '--', rel,
                            cwd=str(wt))
        if check.returncode not in (0, 1):
            skipped.append({'path': rel, 'reason': 'check_ignore_error'})
            continue
        if check.returncode != 0:
            skipped.append({'path': rel, 'reason': 'not_ignored'})
            continue
        listed = lib.run_git('ls-files', '--', rel, cwd=str(wt))
        if listed.returncode != 0:
            skipped.append({'path': rel, 'reason': 'ls_files_error'})
            continue
        if listed.stdout.strip():
            skipped.append({'path': rel, 'reason': 'tracked_present'})
            continue
        passed.append((path, rel))
    return passed, skipped


def measure_bytes(path: Path, budget: dict[str, Any] | None = None) -> int:
    """디렉터리 크기 합계(scandir 재귀 — du 미의존, A8). budget은 {used, limit,
    exceeded} — 파일 계수 상한 초과 시 그 시점까지의 합계를 반환하고 exceeded를
    세운다(M10). OSError는 삼키지 않고 그대로 올린다(호출부가 measure_error로
    전환 — M11)."""
    total = 0
    stack = [os.fspath(path)]
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                    continue
                if budget is not None and budget['limit'] is not None:
                    if budget['used'] >= budget['limit']:
                        budget['exceeded'] = True
                        return total
                    budget['used'] += 1
                total += entry.stat(follow_symlinks=False).st_size
    return total


def remove_tree(path: Path) -> None:
    """후보 디렉터리 삭제 — OSError(NotADirectoryError 포함)는 호출부가
    remove_failed로 전환한다(M8·A12 — 테스트는 본 함수를 patch한다)."""
    shutil.rmtree(path)


def append_sweep_log(container: Path, report: dict[str, Any]) -> None:
    """무인 회수 영수증(M12) — 컨테이너 artifacts-sweep.log 1줄 append.

    create 자동 트리거만 호출한다 — 수동 sweep의 감사면은 stdout·--save다.
    기록 실패는 무시한다(best-effort — 영수증 부재가 회수를 무효화하지 않는다)."""
    summary = report['summary']
    line = (f"{lib.utc_now()} | recovered_gb={summary['recovered_gb']} | "
            f"worktrees={summary['worktrees_scanned']} | "
            f"budget_exceeded={bool(report.get('budget_exceeded'))}\n")
    try:
        container = Path(container)
        container.mkdir(parents=True, exist_ok=True)
        with open(container / 'artifacts-sweep.log', 'a', encoding='utf-8') as handle:
            handle.write(line)
    except OSError:
        pass


def _sweep_one(wt: Path, info: dict[str, Any], candidates: list[Path],
               dry_run: bool, max_dirs: int | None, file_budget: dict[str, Any],
               counters: dict[str, int]) -> tuple[dict[str, Any], bool]:
    """worktree 1개 처리 — (target, stop). stop=True는 dirs 예산 소진으로 전역
    중복 중단해야 함을 뜻한다(M10 부분 보고)."""
    passed, skipped = guard_candidates(wt, candidates)
    counters['candidates'] += len(candidates)
    counters['skipped'] += len(skipped)
    target: dict[str, Any] = {'task': info['task'], 'path': str(wt),
                              'managed': info['managed'],
                              'orphan': info['orphan'],
                              'candidates': len(candidates), 'removed': [],
                              'skipped': skipped, 'bytes_before': 0,
                              'dry_run': dry_run}
    if dry_run:
        target['would_remove'] = [rel for _path, rel in passed]
        for path, rel in passed:
            try:
                target['bytes_before'] += measure_bytes(path)
            except OSError:
                skipped.append({'path': rel, 'reason': 'measure_error'})
                counters['skipped'] += 1
        return target, False
    dirs_left = max_dirs
    stop = False
    for path, rel in passed:
        if dirs_left is not None and dirs_left <= 0:
            stop = True  # 예산 소진 — 이후 후보는 미처리(M10 부분 보고)
            break
        try:
            size = measure_bytes(path, budget=file_budget)
        except OSError:
            skipped.append({'path': rel, 'reason': 'measure_error'})
            counters['skipped'] += 1
            continue
        try:
            remove_tree(path)
        except OSError:
            skipped.append({'path': rel, 'reason': 'remove_failed'})
            counters['skipped'] += 1
            continue
        if dirs_left is not None:
            dirs_left -= 1
        target['removed'].append(rel)
        target['bytes_before'] += size
    counters['removed'] += len(target['removed'])
    counters['recovered'] += target['bytes_before']
    return target, stop


def sweep_artifacts(repo: Path, dry_run: bool, *, disk: dict[str, Any] | None = None,
                    max_dirs: int | None = None, max_files: int | None = None,
                    eligible_only: bool = False) -> dict[str, Any]:
    """부산물 회수 — 대상 확정 → 후보 스캔 → 가드 3중 → 측정 → rmtree → 보고.

    대상은 managed(등록·고아 포함) 뿐이다 — unmanaged·locked·detached는 스캔 대상
    외(계수만 보고). eligible_only=True는 create 자동 트리거 한정이다(H1 — active
    phase는 무인 미접촉·수동 --artifacts-only에서만 회수). max_dirs·max_files는
    예산 상한 주입(None=무제한 — 수동 sweep은 사용자 명시라 미적용, r2 M10)이며
    초과 시 그 시점까지의 부분 회수분만 보고하고 budget_exceeded를 최상위에
    표기한다. rmtree 실패는 skipped(remove_failed) — 전체 ok는 유지된다."""
    repo = Path(repo)
    if disk is None:
        disk = lib.disk_usage_report(repo)
    scanned: list[dict[str, Any]] = []
    counters = {'unmanaged_excluded': 0, 'locked_excluded': 0,
                'candidates': 0, 'removed': 0, 'skipped': 0, 'recovered': 0}
    for info in lib.classify_entries(repo):
        entry = info['entry']
        if not info['managed']:
            counters['unmanaged_excluded'] += 1
        elif entry['locked'] or entry['detached']:
            counters['locked_excluded'] += 1
        elif not (eligible_only and not info['eligible']):
            scanned.append(info)
    file_budget = {'used': 0, 'limit': max_files, 'exceeded': False}
    targets: list[dict[str, Any]] = []
    dirs_exhausted = False
    for info in scanned:
        if dirs_exhausted:
            break
        wt = Path(info['entry']['path'])
        candidates = scan_candidates(wt)
        if not candidates:
            continue  # 후보 0개 worktree는 targets에 미포함(L5 — 요약 잡음 방지)
        target, stop = _sweep_one(wt, info, candidates, dry_run, max_dirs,
                                  file_budget, counters)
        targets.append(target)
        dirs_exhausted = stop
    budget_exceeded = dirs_exhausted or file_budget['exceeded']
    summary = {'worktrees_scanned': len(targets),
               'unmanaged_excluded': counters['unmanaged_excluded'],
               'locked_excluded': counters['locked_excluded'],
               'candidates': counters['candidates'],
               'removed_count': counters['removed'],
               'skipped_count': counters['skipped'],
               'recovered_bytes': counters['recovered'],
               'recovered_gb': round(counters['recovered'] / 1024**3, 2)}
    report: dict[str, Any] = {'ok': True, 'gate': lib.GATE,
                              'subcommand': 'sweep', 'mode': 'artifacts-only',
                              'timestamp_utc': lib.utc_now(), 'disk': disk,
                              'targets': targets, 'summary': summary,
                              'flags': [], 'saved_to': None}
    if budget_exceeded:
        report = {**report, 'budget_exceeded': True}
    return report
