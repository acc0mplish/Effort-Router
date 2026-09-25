#!/usr/bin/env python3
"""r23 검증 핀 게이트 CLI — SHA 핀·검증 입력 분리·증거 기록(결정론·jev/LLM 무관).

검증의 자기참조 구멍(검증 대상 테스트를 약화·삭제·신규 무력화해도 재실행은 같은
약화본을 통과시킨다)과 핀 부재(옛 검증으로 새 코드가 통과한다)를 기계 노출로 전환하는
게이트다(완전 차단이 아니다 — 검증 입력 변경은 정당화 계층 사유 기재로 해제되고
감시 자동화 없이 호출 시점 1회 판정이다). 감지는 git(커밋·staged·unstaged·삭제
diff + untracked 신규 + ignore 제외 untracked 스캔[r25] + 은닉 지정
ls-files -v 스캔)과 검증명령 subprocess[r26: 프로세스 그룹 제어·실행창 전후
클린 검사 — verify_exec.py 실행 엔진]뿐이며 외부 전송·과금이 없다. 기본 모드는
읽기 전용이다. --fresh-checkout 모드(--verify-cmd 필수)는 저장소 밖 컨테이너
(r24 명명 관례)와 `.git/worktrees/verify-pin-fresh` 관리 메타데이터만 쓰며 —
후자는 종료 전 remove --force+prune으로 소멸한다. 메인 워크스페이스 tracked·
인덱스·HEAD는 어떤 모드에서도 기록하지 않는다. git 호출은
`-c core.autocrlf=false -c core.quotePath=false` 고정 — CRLF 정규화 위플래그와
비ASCII 경로 C-인용(fnmatch 무력화)을 경로 자체에서 차단한다.
종료코드: 0 pass · 1 attention(확인 의무 플래그 — jev의 exit 1 폴백과 정반대다,
확인 없이 진행하면 계약 위반) · 2 config/env/git 오류(이유가 붙은 bypass — 저장
실패만 검사 결과 stdout JSON을 유지한다). exit 3은 미사용 — 판단 계층이 없어
상향(escalation) 경로 자체가 없다.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import verify_exec  # scripts/ 동일 디렉터리 국소 의존(§3-6 — r24 lib 패턴 준용)

GATE = 'verify-pin'
EXIT_PASS = 0
EXIT_ATTENTION = 1
EXIT_CONFIG = 2
DEFAULT_TIMEOUT = 600.0
GIT_FIXED = ('-c', 'core.autocrlf=false', '-c', 'core.quotePath=false')

# 그룹 1 — 검증 입력(기본 8종, --pattern은 여기에만 append된다)
VERIFICATION_PATTERNS = ('tests/*', 'test/*', 'test_*.py', '*_test.py',
                         'conftest.py', 'pytest.ini', 'tox.ini', '.github/workflows/*')
# 그룹 2 — 다목적 설정(별도 플래그 — 검증 입력 신호 순도 유지, H5)
MULTIPURPOSE_PATTERNS = ('pyproject.toml', 'setup.cfg')

FLAG_SHA = 'sha_mismatch'
FLAG_INPUT = 'verification_input_modified'
FLAG_MULTIPURPOSE = 'multipurpose_config_modified'
FLAG_INPUT_HIDDEN = 'verification_input_hidden'
FLAG_INPUT_IGNORE_HIDDEN = 'verification_input_ignore_hidden'
FLAG_CMD_FAILED = 'verify_cmd_failed'
FLAG_CMD_TIMEOUT = 'verify_cmd_timeout'
# r26 신규 3종 — survivors는 재검증 계층(프로세스 정지 후 재실행으로 소멸 확인),
# head_moved·workspace_mutated는 정당화 계층(1회성 사건 — 재실행 소멸≠해제, M16)
FLAG_SURVIVORS = 'verify_cmd_survivors'
FLAG_HEAD_MOVED = 'head_moved_during_verify'
FLAG_WORKSPACE_MUTATED = 'verify_workspace_mutated'


class GateConfigError(Exception):
    """인자·env·git 오류 — exit 2(이유가 붙은 bypass)로 변환한다."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='검증 핀 게이트 — SHA 핀·검증 입력 분리·증거 기록(읽기 전용 결정론 게이트)')
    parser.add_argument('--base',
                        help='diff 기준 커밋(앵커 = 구현 착수 전 커밋) — 미지정 시 not_evaluated')
    parser.add_argument('--expect-sha',
                        help='직전 검증 실행이 기록한 HEAD SHA — 불일치 시 sha_mismatch')
    parser.add_argument('--verify-cmd',
                        help='재실행 검증명령(shlex 분할 — 셸 미경유, 필요 시 bash -c 전달)')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT,
                        help=f'verify-cmd 타임아웃 초(기본 {DEFAULT_TIMEOUT:.0f}, 양수 유한)')
    parser.add_argument('--pattern', action='append',
                        help='검증 입력 패턴 추가(반복 가능 — 기본 패턴에 append, '
                             'multipurpose 그룹 미적용)')
    parser.add_argument('--save',
                        help='결과 JSON 저장 디렉터리(verify-pin-<UTC타임스탬프>.json)')
    parser.add_argument('--fresh-checkout', action='store_true',
                        help='핀 SHA의 detached 클린 체크아웃에서 검증(r26 — 워크스페이스 '
                             '오염 클래스 전멸. --verify-cmd 필수, 단독 지정은 exit 2)')
    return parser.parse_args(argv)


def validate_timeout(timeout: float) -> float:
    if not math.isfinite(timeout) or timeout <= 0:
        raise GateConfigError(f'--timeout은 양수 유한 값이어야 한다: {timeout!r}')
    return timeout


def run_git(*args: str) -> subprocess.CompletedProcess:
    """읽기 전용 git 호출 — autocrlf·quotePath 고정(CRLF 정규화·비ASCII 인용 위플래그 차단).

    errors='replace' — 비UTF-8 파일명 바이트의 UnicodeDecodeError를 트레이스백 없이
    치환 문자로 흘려보낸다(④ 재리뷰 LOW: 엄격 디코드 실패는 JSON 없는 exit 1 오분류).
    """
    return subprocess.run(['git', *GIT_FIXED, *args], capture_output=True, text=True,
                          errors='replace')


def fail_config(reason: str) -> None:
    print(f'FAIL verify pin: {reason}', file=sys.stderr)
    raise SystemExit(EXIT_CONFIG)


def git_stderr_reason(completed: subprocess.CompletedProcess) -> str:
    lines = completed.stderr.strip().splitlines()
    return lines[-1].strip() if lines else '(git 출력 없음)'


def resolve_head() -> str:
    completed = run_git('rev-parse', 'HEAD')
    if completed.returncode != 0:
        raise GateConfigError('git 저장소가 아니거나 커밋이 없다 — '
                              + git_stderr_reason(completed))
    return completed.stdout.strip()


def resolve_base(ref: str) -> str:
    completed = run_git('rev-parse', '--verify', ref)
    if completed.returncode != 0:
        raise GateConfigError(f'--base를 커밋으로 해석할 수 없다: {ref!r} — '
                              + git_stderr_reason(completed))
    return completed.stdout.strip()


def git_lines(*args: str) -> list[str]:
    completed = run_git(*args)
    if completed.returncode != 0:
        raise GateConfigError(f'git {args[0]} 실패 — {git_stderr_reason(completed)}')
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def collect_candidates(base_sha: str) -> list[str]:
    """앵커→작업 트리 후보 수집 — tracked diff(커밋·staged·unstaged·삭제) ∪ untracked 신규."""
    tracked = git_lines('diff', '--name-only', base_sha)
    untracked = git_lines('ls-files', '--others', '--exclude-standard')
    return sorted(set(tracked) | set(untracked))


def hidden_candidates() -> list[str]:
    """은닉 지정 경로 수집 — ls-files -v 태그 'h'(assume-unchanged)·'S'(skip-worktree).

    은닉 지정은 diff·status 양쪽에서 파일을 감춰 증거 워크플로 동반 마비시키는
    우회다(④ HIGH-1) — 후보 수집과 무관하게 항상 스캔한다.
    """
    paths = []
    for line in git_lines('ls-files', '-v'):
        tag, _, path = line.partition(' ')
        if tag in ('h', 'S') and path:
            paths.append(path)
    return paths


def ignored_untracked_candidates() -> list[str]:
    """ignore 은닉 스캔(r25 H4) 모수 — untracked∧ignored 차집합.

    `git ls-files --others`(제외 없음) ∖ `--exclude-standard` = .gitignore·
    .git/info/exclude·전역 excludesFile 제외 untracked — diff·untracked 검출이
    모두 놓치는 우회 모수다. 무제외 스캔은 venv·node_modules 규모(수만 파일)에서
    수백 ms~수 초(V10·A14) — verify-cmd 경로와 합산해 상한 없이 수용한다.
    """
    all_others = git_lines('ls-files', '--others')
    standard = git_lines('ls-files', '--others', '--exclude-standard')
    return sorted(set(all_others) - set(standard))


def match_full_paths(candidates: list[str], patterns: tuple[str, ...]) -> list[str]:
    """전체경로 fnmatchcase 한정 매칭 — basename 매칭 금지(RC-1).

    차집합 모수는 의존성 트리(.venv*/.../site-packages/tests/test_*.py)를 포함해
    basename 매칭이면 관행 패턴과 결합해 의존성 테스트를 오탐한다(본 저장소 실측
    18힛) — 패턴은 경로 선두부터 fnmatch로 판정한다. 임의 깊이 무력화 파일 보완은
    --pattern 확장 계약(A15).
    """
    return sorted(path for path in candidates
                  if any(fnmatchcase(path, pattern) for pattern in patterns))


def hidden_patterns(extra_patterns: list[str]) -> tuple[str, ...]:
    """은닉 매칭 패턴 — 검증 입력(기본+추가)과 multipurpose 양 그룹 통합(④ 재리뷰 HIGH).

    그룹 2 은닉은 pyproject 무력화 직통 우회다 — 은닉은 어느 그룹이든 즉시 의심 신호이므로
    그룹 구분 없이 단일 플래그로 발행한다.
    """
    return (*VERIFICATION_PATTERNS, *extra_patterns, *MULTIPURPOSE_PATTERNS)


def match_candidates(candidates: list[str], patterns: tuple[str, ...]) -> list[str]:
    """fnmatchcase(경로 전체) 또는 fnmatchcase(basename) — 플랫폼 대소문자 무관 결정론."""
    return sorted(path for path in candidates
                  if any(fnmatchcase(path, pattern) or fnmatchcase(Path(path).name, pattern)
                         for pattern in patterns))


def inspect_verification(base_sha: str | None,
                         extra_patterns: list[str]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """검증 입력 그룹(기본+추가)과 multipurpose 그룹을 분리 발행한다(H5).

    base 미지정은 not_evaluated — 미검사 ≠ 변경 없음(M-d). 패턴 비통과 후보는 폐기한다
    (untracked 오탐 폭주 방지 — H1 LOW). 은닉 지정 검출(파이프라인 4단계)과 ignore
    은닉 검출(r25)은 base와 무관하게 항상 수행하며 양 그룹 패턴을 통합 적용한다
    (④ 재리뷰 HIGH·r25 H4).
    """
    patterns = (*VERIFICATION_PATTERNS, *extra_patterns)
    hidden = match_candidates(hidden_candidates(), hidden_patterns(extra_patterns))
    ignore_hidden = match_full_paths(ignored_untracked_candidates(),
                                     hidden_patterns(extra_patterns))
    if base_sha is None:
        return {'status': 'not_evaluated', 'patterns': list(patterns),
                'modified_files': [], 'multipurpose_files': [],
                'hidden_files': hidden, 'ignore_hidden_files': ignore_hidden}, \
            ((FLAG_INPUT_HIDDEN,) if hidden else ()) \
            + ((FLAG_INPUT_IGNORE_HIDDEN,) if ignore_hidden else ())
    candidates = collect_candidates(base_sha)
    modified = match_candidates(candidates, patterns)
    multipurpose = match_candidates(candidates, MULTIPURPOSE_PATTERNS)
    verification = {'status': 'modified' if modified else 'clean',
                    'patterns': list(patterns),
                    'modified_files': modified,
                    'multipurpose_files': multipurpose,
                    'hidden_files': hidden,
                    'ignore_hidden_files': ignore_hidden}
    flags = ((FLAG_INPUT,) if modified else ()) \
        + ((FLAG_MULTIPURPOSE,) if multipurpose else ()) \
        + ((FLAG_INPUT_HIDDEN,) if hidden else ()) \
        + ((FLAG_INPUT_IGNORE_HIDDEN,) if ignore_hidden else ())
    return verification, flags


def run_verify_window(command: str, timeout: float, process_group: bool,
                      patterns: tuple[str, ...],
                      cwd: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """verify-cmd 실행창 — 직전 스냅샷 → 실행 → 직후 재판정 델타(r26 §5.1).

    기준은 실행 창 전후 델타(게이트 시작 아님) — 선행 inspect_verification과
    무관하다. 사전 dirty는 플래그 대상 아니다(게이트의 검증입력 검사 영역).
    untracked 신규·소실은 검증입력 패턴 매칭 한정 검출(.pytest_cache 등 산출물
    오탐 방지 — §12-3 승인 트레이드오프), exclude 내용 변화는 무조건 변형이다(M8).
    ps 실패 등 엔진 오류는 verify_exec.GateConfigError — 호출부가 exit 2로
    변환한다(H2)."""
    before = verify_exec.window_snapshot()  # 메인 워크스페이스 기준(fresh여도 동일, M4)
    verify_cmd = verify_exec.run_verify_cmd(command, timeout,
                                            cwd or Path.cwd(), process_group)
    delta = verify_exec.window_delta(before, verify_exec.window_snapshot())
    untracked_matched = match_candidates(
        delta['untracked_new'] + delta['untracked_gone'], patterns)
    detail = {**delta, 'untracked_matched': untracked_matched}
    return {**verify_cmd, 'window_delta': detail}, untracked_matched


def verify_window_flags(delta: dict[str, Any]) -> tuple[str, ...]:
    """실행창 델타 플래그 — HEAD 이동은 head_moved_during_verify(정당화 계층),
    tracked 변형·exclude 변화·패턴 매칭 untracked는 verify_workspace_mutated
    (정당화 계층 — 1회성 사건, 재실행 소멸≠해제, M16)."""
    flags = ()
    if delta['head_moved']:
        flags += (FLAG_HEAD_MOVED,)
    if delta['tracked_changed'] or delta['exclude_changed'] \
            or delta['untracked_matched']:
        flags += (FLAG_WORKSPACE_MUTATED,)
    return flags


def verify_cmd_flags(verify: dict[str, Any]) -> tuple[str, ...]:
    flags = ()
    if verify['timed_out']:
        flags += (FLAG_CMD_TIMEOUT,)  # 타임아웃이 원인 — failed 병기 금지(배타성, LOW)
    elif verify['exit_code'] != 0:
        flags += (FLAG_CMD_FAILED,)
    if verify.get('survivors'):
        flags += (FLAG_SURVIVORS,)  # 독립 축(프로세스 잔존) — timeout과 병기 가능(r26)
    return flags


def assemble_result(head_sha: str, expect_sha: str | None, base_ref: str | None,
                    base_sha: str | None, sha_matched: bool | None,
                    verification: dict[str, Any], verify_cmd: dict[str, Any] | None,
                    flags: list[str],
                    fresh: dict[str, Any] | None = None) -> dict[str, Any]:
    """결과 dict 새 조립 — 돌연변이 없다(번들 §5 구현 노트)."""
    return {'ok': len(flags) == 0,
            'gate': GATE,
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'head_sha': head_sha,
            'pin': {'expect_sha': expect_sha, 'base_ref': base_ref,
                    'base_sha': base_sha, 'sha_matched': sha_matched},
            'verification_input': verification,
            'verify_cmd': verify_cmd,
            'fresh': fresh,
            'flags': list(flags),
            'saved_to': None}


def save_result(save_dir: str, result: dict[str, Any]) -> tuple[str | None, str | None]:
    """결과 JSON 저장 — (경로, None) 또는 (None, 사유). 검사 결과는 폐기하지 않는다(M-f)."""
    try:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        directory = Path(save_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{GATE}-{stamp}.json'
        payload = {**result, 'saved_to': str(path)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    except OSError as error:
        return None, str(error)
    return str(path), None


def fresh_prologue(head: str) -> tuple[Path, dict[str, Any]]:
    """fresh 절차 전반 — 가드(H4)→잔존 복구→worktree add --detach(§5.2 순서).

    가드·잔존 복구·add 실패는 GateConfigError — 호출부가 exit 2로 변환한다.
    잔존 복구는 r24 sweep이 detached를 스킵해 fresh 잔존을 못 치우므로(M12)
    fresh 모드 재실행으로만 정리된다."""
    repo = verify_exec.main_toplevel()
    verify_exec.fresh_guard(repo)
    leftovers = verify_exec.fresh_leftover_cleanup(repo)
    worktree = verify_exec.fresh_checkout(repo, head)
    fresh = {'used': True, 'checkout_sha': head, 'worktree_path': str(worktree),
             'removed': False, 'leftovers_cleaned': leftovers}
    return worktree, fresh


def fresh_epilogue(repo: Path, worktree: Path, fresh: dict[str, Any],
                   result: dict[str, Any]) -> dict[str, Any]:
    """fresh 절차 후반 — remove --force + prune + 빈 컨테이너 rmdir.

    remove 실패는 부분 결과 JSON을 stdout에 정확 1회 출력한 뒤 exit 2(r24 M3
    패턴 — 검사 결과 폐기 금지, §3-2 대칭). 오염 있어도 --force로 제거된다(P2)."""
    try:
        verify_exec.fresh_remove(repo, worktree)
    except (GateConfigError, verify_exec.GateConfigError) as error:
        partial = {**result, 'fresh': {**fresh, 'removed': False},
                   'incomplete_step': 'worktree_remove', 'error': str(error)}
        print(json.dumps(partial, ensure_ascii=False))
        fail_config(f'fresh worktree remove 실패 — {error}')
    return {**fresh, 'removed': True}


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        timeout = validate_timeout(args.timeout)
        if args.fresh_checkout and args.verify_cmd is None:
            raise GateConfigError('--fresh-checkout은 --verify-cmd와 함께 사용해야 한다'
                                  ' — verify-cmd 없는 fresh는 검증 부재다')
        head = resolve_head()
        base_sha = resolve_base(args.base) if args.base is not None else None
        worktree, fresh = (None, None)
        if args.fresh_checkout:
            worktree, fresh = fresh_prologue(head)
    except (GateConfigError, verify_exec.GateConfigError) as error:
        fail_config(str(error))
    verification, verification_flags = inspect_verification(base_sha, args.pattern or [])
    sha_matched = None if args.expect_sha is None else head == args.expect_sha
    sha_flags = (FLAG_SHA,) if sha_matched is False else ()
    verify_cmd = None
    window_flags: tuple[str, ...] = ()
    if args.verify_cmd is not None:
        patterns = (*VERIFICATION_PATTERNS, *(args.pattern or []))
        cwd = worktree if worktree is not None else None
        try:
            verify_cmd, _ = run_verify_window(args.verify_cmd, timeout,
                                              verify_exec.capability(), patterns, cwd)
        except (GateConfigError, verify_exec.GateConfigError) as error:
            fail_config(str(error))
        window_flags = verify_window_flags(verify_cmd['window_delta'])
    cmd_flags = verify_cmd_flags(verify_cmd) if verify_cmd is not None else ()
    flags = [*sha_flags, *verification_flags, *cmd_flags, *window_flags]
    result = assemble_result(head, args.expect_sha, args.base, base_sha,
                             sha_matched, verification, verify_cmd, flags, fresh)
    if worktree is not None:
        fresh = fresh_epilogue(verify_exec.main_toplevel(), worktree, fresh, result)
        result = {**result, 'fresh': fresh}
    if args.save is not None:
        saved, save_error = save_result(args.save, result)
        if saved is None:
            print(json.dumps(result, ensure_ascii=False))
            fail_config(f'--save 실패 — 검사 결과는 위 stdout JSON에 보존됐다: {save_error}')
        result = {**result, 'saved_to': saved}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(EXIT_PASS if not result['flags'] else EXIT_ATTENTION)


if __name__ == '__main__':
    main()
