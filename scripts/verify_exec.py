#!/usr/bin/env python3
"""r26 검증 실행 엔진 — 프로세스 그룹 제어·verify-window·fresh-checkout(650줄 분할).

verify_pin.py(CLI)가 임포트하는 실행 계층이다. 설계 계약 전문은 verify_pin.py
모듈 독스트링과 SKILL.md '검증 핀 게이트' 절에 있다 — 본 파일은 계약을 반복하지
않는다. 원형: todo-flow verification.py stop_group(어휘 이식 — SIGTERM→pgid 폴링
1.5s→SIGKILL→드레인→2s 폴링, ps 실패 예외 보관·재발기). 파기성·변경성 명령은
fresh 모드의 worktree add --detach·remove --force·prune·컨테이너 rmtree(잔존
복구 한정)뿐이다 — 메인 워크스페이스 tracked·인덱스·HEAD는 기록하지 않는다.
한계(계약): 프로세스 그룹 제어는 같은 pgid에 머무는 자손 한정 — setsid 등 신규
pgid 생성 이탈 자손은 killpg·ps 폴링 모두 범위 밖이다.
"""
from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

EXIT_CONFIG = 2
GIT_FIXED = ('-c', 'core.autocrlf=false', '-c', 'core.quotePath=false')
TAIL_CHARS = 500
# stop_group — SIGTERM 후 그룹 사멸 폴링(Slow teardown의 coverage flush 보호, r26 M13)
TERM_POLL_S = 1.5
# SIGKILL 후 잔존 관측 상한 — 초과 시 undead 종착지(survivors 플래그 확정 후 진행, M2)
KILL_POLL_S = 2.0
# 파이프 드레인 상한 — 파이프 잡은 생존자 잔존 시 fd close + wait 회수로 탈출(P6)
DRAIN_S = 5.0
# 정상 종료 후 생존자 판정 — 0.3s deadline 지속 관측 + 안정화 재스캔 1회(M14)
SURVIVOR_WINDOW_S = 0.3
SURVIVOR_SETTLE_S = 0.05
FRESH_NAME = 'verify-pin-fresh'
FRESH_TASK_DIR = 'docs/task-id/verify-pin-fresh'


class GateConfigError(Exception):
    """인자·env·git·ps 오류 — exit 2(이유가 붙은 bypass)로 변환한다."""


class ExecPsError(GateConfigError):
    """실행 중 ps 실패(H2) — 생존자 판정 불능. 조용한 통과 금지, exit 2로 변환."""


# ---------------------------------------------------------------- git 하층

def run_git(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """git 호출 — autocrlf·quotePath 고정, errors='replace'(비UTF-8 파일명 방어)."""
    return subprocess.run(['git', *GIT_FIXED, *args], capture_output=True,
                          text=True, errors='replace', cwd=cwd)


def git_reason(completed: subprocess.CompletedProcess) -> str:
    lines = completed.stderr.strip().splitlines()
    return lines[-1].strip() if lines else '(git 출력 없음)'


def git_ok(*args: str, cwd: str | None = None) -> str:
    completed = run_git(*args, cwd=cwd)
    if completed.returncode != 0:
        raise GateConfigError(f'git {args[0]} 실패 — {git_reason(completed)}')
    return completed.stdout.strip()


# ------------------------------------------------------------ capability probe

def capability() -> bool:
    """게이트 시작 시 1회 — hasattr(killpg) ∧ which(ps) 양측 참이면 posix-killpg."""
    return hasattr(os, 'killpg') and shutil.which('ps') is not None


# ------------------------------------------------- 프로세스 그룹(todo-flow 원형)

def group_running(pgid: int) -> bool:
    """그룹 생존 판정 — ps -axo pgid=,stat= 폴링(좀비 Z 제외). ps 실패는 H2 예외."""
    try:
        result = subprocess.run(['ps', '-axo', 'pgid=,stat='], capture_output=True,
                                text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExecPsError('생존자 판정 불능 — ps 실행 실패: '
                          f'{type(error).__name__}: {error}') from error
    if result.returncode != 0:
        raise ExecPsError('생존자 판정 불능 — ps 실패: '
                          f'{(result.stderr or result.stdout).strip()[:200]}')
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == str(pgid) and not fields[1].startswith('Z'):
            return True
    return False


def await_group_death(pgid: int, timeout_s: float) -> bool:
    """그룹 사멸 폴링 — deadline 내 사멸 True·초과 False(undead). ps 실패는 재발행."""
    deadline = time.monotonic() + timeout_s
    while True:
        if not group_running(pgid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def _send_group_signal(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass  # 그룹 소멸 — 목적 달성


def _drain_after_group_death(proc: subprocess.Popen) -> tuple[str, str]:
    """그룹 사멸 후 드레인(순서 강제 — P6 교착 방지). 드레인 타임아웃 시 fd close +
    wait(5)로 직속 자식 회수 — 이 경로에서는 출력 tail이 소실될 수 있다(LOW —
    파이프를 놓는 대가)."""
    try:
        return proc.communicate(timeout=DRAIN_S)
    except subprocess.TimeoutExpired:
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
        try:
            proc.wait(timeout=DRAIN_S)
        except subprocess.TimeoutExpired:
            pass  # 직속 자식 미회수 — survivors 판정(아래)이 잔존을 보고한다
        return '', ''


def stop_group(proc: subprocess.Popen) -> tuple[str, str, bool]:
    """그룹 강제 종료 — SIGTERM→1.5s 폴링→SIGKILL→드레인→2s 폴링.

    반환 (stdout, stderr, group_dead). ps 실패는 SIGKILL 발사 후 예외 재발행한다
    (todo-flow inspection_error 패턴 — 실패를 조용히 삼키지 않는다)."""
    _send_group_signal(proc.pid, signal.SIGTERM)
    ps_error: ExecPsError | None = None
    try:
        await_group_death(proc.pid, TERM_POLL_S)
    except ExecPsError as error:
        ps_error = error
    finally:
        _send_group_signal(proc.pid, signal.SIGKILL)
    stdout, stderr = _drain_after_group_death(proc)
    if ps_error is not None:
        raise ps_error
    group_dead = await_group_death(proc.pid, KILL_POLL_S)
    return stdout, stderr, group_dead


def detect_survivors(pgid: int) -> bool:
    """정상 종료 후 생존자 판정 — 0.3s deadline 폴링에서 지속 관측될 때만 성립
    (직속 종료 레이스의 순간 오탐 방지) + 판정 전 안정화 재스캔 1회(M14)."""
    deadline = time.monotonic() + SURVIVOR_WINDOW_S
    while True:
        if not group_running(pgid):
            return False
        if time.monotonic() >= deadline:
            time.sleep(SURVIVOR_SETTLE_S)
            return group_running(pgid)
        time.sleep(0.02)


def terminate_group(pgid: int) -> bool:
    """생존 그룹 종료(파이프 이미 소비된 경로) — SIGTERM→1.5s→SIGKILL→2s 폴링.
    반환 group_dead. ps 실패는 재발행(H2 — exit 2 변환은 호출부)."""
    _send_group_signal(pgid, signal.SIGTERM)
    try:
        await_group_death(pgid, TERM_POLL_S)
    finally:
        _send_group_signal(pgid, signal.SIGKILL)
    return await_group_death(pgid, KILL_POLL_S)


# ------------------------------------------------------------ 실행 엔진 본체

def as_text(value: Any) -> str:
    """TimeoutExpired 출력은 text 모드에서도 bytes로 올 수 있다 — 방어적 복원."""
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value


def _tail(text: str, limit: int = TAIL_CHARS) -> str:
    return text[-limit:]


def _result(command: str, started: float, exit_code: int | None, timed_out: bool,
            stdout: str, stderr: str, survivors: bool | None,
            group_killed: bool | None) -> dict[str, Any]:
    return {'command': command, 'exit_code': exit_code, 'timed_out': timed_out,
            'duration_s': round(time.monotonic() - started, 3),
            'stdout_tail': _tail(as_text(stdout)),
            'stderr_tail': _tail(as_text(stderr)),
            'survivors': survivors, 'group_killed': group_killed}


def _run_legacy(argv: list[str], command: str, timeout: float,
                started: float) -> dict[str, Any]:
    """비POSIX 폴백 — 현행 subprocess.run(timeout=) 의미 이관(직속 자식만 종료).
    process_group false로 투명 표기(C14)."""
    try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return _result(command, started, None, True, as_text(error.stdout),
                       as_text(error.stderr), None, None)
    except OSError as error:
        raise GateConfigError(f'--verify-cmd 실행 불가: {error}') from error
    return _result(command, started, completed.returncode, False,
                   completed.stdout, completed.stderr, None, None)


def _run_posix(argv: list[str], command: str, timeout: float, cwd: Path,
               started: float) -> dict[str, Any]:
    """posix-killpg 실행 — start_new_session으로 pgid==자식 pid 보장(P1 실측).

    TimeoutExpired 판별 규칙(리컨 P6·M6): poll()로 직속 자식 종료 여부 확인 —
    (a) 미종료 = 진성 타임아웃, (b) 이미 종료 = 파이프 잡은 orphan(타임아웃 아님 —
    exit_code 반영·survivors로 정확 분류). 양쪽 모두 stop_group 강제. 판별 경계에는
    poll() 시점 경쟁 창이 존재한다 — 보장은 orphan 시나리오 내 정확성 한정."""
    try:
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors='replace', start_new_session=True,
                                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    except OSError as error:
        raise GateConfigError(f'--verify-cmd 실행 불가: {error}') from error
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        genuine_timeout = proc.poll() is None
        stdout, stderr, group_dead = stop_group(proc)
        survivors = (not group_dead) or (not genuine_timeout)
        return _result(command, started,
                       None if genuine_timeout else proc.returncode,
                       genuine_timeout, stdout, stderr, survivors, True)
    except BaseException:
        stop_group(proc)
        raise
    survivors = detect_survivors(proc.pid)
    group_killed = False
    if survivors:
        terminate_group(proc.pid)  # group_dead 여부와 무관하게 탐지 사실은 유지된다
        group_killed = True
    return _result(command, started, proc.returncode, False, stdout, stderr,
                   survivors, group_killed)


def split_verify_command(command: str) -> list[str]:
    argv = shlex.split(command)
    if not argv:
        raise GateConfigError('--verify-cmd가 빈 명령이다')
    return argv


def run_verify_cmd(command: str, timeout: float, cwd: Path,
                   process_group: bool) -> dict[str, Any]:
    """검증명령 1회 실행 — 타임아웃은 failed와 배타, survivors는 독립 축.

    process_group False(비POSIX 폴백)면 survivors·group_killed는 null이다."""
    argv = split_verify_command(command)
    started = time.monotonic()
    if not process_group:
        result = _run_legacy(argv, command, timeout, started)
    else:
        result = _run_posix(argv, command, timeout, cwd, started)
    return {**result, 'process_group': process_group}


# ------------------------------------------------- verify-window(전후 클린 검사)

def status_z_records(stdout: str) -> list[tuple[str, str]]:
    """porcelain -z 레코드 파서 — (XY, path) NUL 구분. R·C 레코드는 다음 필드가
    원경로다(신경로 우선). 개행 파일명 안전(r24 L4 준용)."""
    records: list[tuple[str, str]] = []
    fields = stdout.split('\0')
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if len(record) < 3:
            continue
        records.append((record[:2], record[3:]))
        if record[0] in ('R', 'C'):
            index += 1  # 다음 필드 = 원경로 — 폐기
    return records


def exclude_path() -> Path:
    """.git/info/exclude 절대경로 — rev-parse --git-path(cwd 상대 보정)."""
    completed = run_git('rev-parse', '--git-path', 'info/exclude')
    if completed.returncode != 0:
        raise GateConfigError('git 저장소가 아니다 — ' + git_reason(completed))
    path = Path(completed.stdout.strip())
    return path if path.is_absolute() else Path.cwd() / path


def _exclude_content(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def window_snapshot() -> dict[str, Any]:
    """실행 직전 스냅샷 3종 — HEAD·porcelain(-z -uall)·info/exclude 내용(M8)."""
    return {'head': git_ok('rev-parse', 'HEAD'),
            'porcelain': run_git('status', '--porcelain', '-z', '-uall').stdout,
            'exclude': _exclude_content(exclude_path())}


def window_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """실행 창 전후 델타 — 게이트 시작 아닌 실행창 기준(선행 inspect와 무관).

    tracked 레코드(XY≠'  '·'??'·staged 포함)는 집합 비교 1건 변화도 검출.
    untracked 신규·소실은 원시 경로만 반환 — 패턴 매칭은 호출부(verify_pin)가
    검증입력 패턴 어휘로 수행한다(산출물 오탐 방지 — §5.1)."""
    before_records = status_z_records(before['porcelain'])
    after_records = status_z_records(after['porcelain'])
    before_tracked = {(xy, path) for xy, path in before_records if xy != '??'}
    after_tracked = {(xy, path) for xy, path in after_records if xy != '??'}
    before_untracked = {path for xy, path in before_records if xy == '??'}
    after_untracked = {path for xy, path in after_records if xy == '??'}
    return {'head_moved': before['head'] != after['head'],
            'tracked_changed': sorted((f'{xy} {path}' for xy, path
                                       in (after_tracked - before_tracked)
                                       | (before_tracked - after_tracked))),
            'untracked_new': sorted(after_untracked - before_untracked),
            'untracked_gone': sorted(before_untracked - after_untracked),
            'exclude_changed': before['exclude'] != after['exclude']}


# ------------------------------------------------- fresh-checkout(Phase 2 이후)

def main_toplevel() -> Path:
    """메인 저장소 루트 — fresh 경로 파생 기준(verify_pin은 메인 cwd 전제)."""
    return Path(git_ok('rev-parse', '--show-toplevel'))


def fresh_container(repo: Path) -> Path:
    """컨테이너 경로 — <repo.parent>/<repo.name>-worktrees(r24 명명 관례 준용)."""
    return repo.parent / f'{repo.name}-worktrees'


def fresh_worktree_path(repo: Path) -> Path:
    return fresh_container(repo) / FRESH_NAME


def fresh_guard(repo: Path) -> None:
    """r24 이름 충돌 가드(H4) — wt/verify-pin-fresh 브랜치 ∨ docs/task-id/
    verify-pin-fresh/ 존재 시 exit 2 거부(TASK_ID_RE가 verify-pin-fresh를 task-id로
    허용해 r24 관리 worktree가 salvage 없이 remove --force되는 데이터 소실 차단)."""
    completed = run_git('show-ref', '--verify', '--quiet',
                        f'refs/heads/wt/{FRESH_NAME}')
    if completed.returncode == 0:
        raise GateConfigError(f'r24 관리 대상과 이름 충돌 — wt/{FRESH_NAME} 브랜치가 '
                              '존재해 fresh 잔존 복구에 진입할 수 없다')
    if (repo / FRESH_TASK_DIR).exists():
        raise GateConfigError(f'r24 관리 대상과 이름 충돌 — {FRESH_TASK_DIR}/가 '
                              '존재해 fresh 잔존 복구에 진입할 수 없다')


def fresh_leftover_cleanup(repo: Path) -> list[str]:
    """잔존 복구 — 고정명 verify-pin-fresh 대상만. 등록 항목이면 remove --force+
    prune, 등록 없는 디렉터리만 남으면 rmtree(fresh worktree는 기계 생성 산출물만
    담는 계약 — salvage 불필요). rmtree 실패는 exit 2(M9). 정리 목록 반환."""
    leftovers: list[str] = []
    worktree = fresh_worktree_path(repo)
    entries = git_ok('worktree', 'list', '--porcelain')
    registered = any(line.startswith('worktree ') and
                     line[len('worktree '):] == str(worktree)
                     for line in entries.splitlines())
    if registered:
        completed = run_git('worktree', 'remove', '--force', str(worktree))
        if completed.returncode != 0:
            raise GateConfigError(f"fresh 잔존 worktree remove 실패({worktree}) — "
                                  + git_reason(completed))
        run_git('worktree', 'prune')
        leftovers.append(str(worktree))
    elif worktree.exists():
        try:
            shutil.rmtree(worktree)
        except OSError as error:
            raise GateConfigError(f'fresh 잔존 디렉터리 삭제 실패({worktree}) — '
                                  f'{error}') from error
        leftovers.append(str(worktree))
    return leftovers


def fresh_checkout(repo: Path, head_sha: str) -> Path:
    """worktree add --detach — head_sha는 게이트 시작 시점 resolve 값(dirty 메인과
    무관, P3 실측). 실패는 exit 2(git 오류)."""
    worktree = fresh_worktree_path(repo)
    completed = run_git('worktree', 'add', '--detach', str(worktree), head_sha)
    if completed.returncode != 0:
        raise GateConfigError(f'fresh worktree add 실패({worktree}) — '
                              + git_reason(completed))
    return worktree


def fresh_remove(repo: Path, worktree: Path) -> None:
    """remove --force + prune + 빈 컨테이너 rmdir(best-effort). remove 실패는
    GateConfigError — 호출부가 부분 결과(stdout JSON·fresh.removed false)를
    출력한 뒤 exit 2로 변환한다(r24 M3 패턴 — 검사 결과 폐기 금지)."""
    completed = run_git('worktree', 'remove', '--force', str(worktree))
    if completed.returncode != 0:
        raise GateConfigError(f'fresh worktree remove 실패({worktree}) — '
                              + git_reason(completed))
    run_git('worktree', 'prune')
    try:
        fresh_container(repo).rmdir()
    except OSError:
        pass  # 빈 컨테이너 정리는 best-effort(LOW — 다른 worktree 잔존 시 유지)
