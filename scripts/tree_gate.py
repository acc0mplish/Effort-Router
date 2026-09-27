#!/usr/bin/env python3
"""r27 트리 소유 게이트 CLI — 복수 기록자(병렬 세션·헬퍼)의 트리 소유 조율(claim 레지스트리).

관측 실패(타 세션의 미커밋 변경을 추정만으로 revert — 복수 기록자 + 트리 소유
조율 장치 부재)의 영구 예방 장치다. 작업 착수 전 세션id·트리·스코프·시각을 claim
레지스트리에 기록하고, 같은 트리의 살아있는 타 세션 claim을 check가 기계 노출한다.
레지스트리는 `$(git rev-parse --git-common-dir)/effort-router-tree-claims/` —
common-dir은 모든 워크트리가 공유하므로 워크트리 간 가시성이 확보되며, .git 내부
비관리 디렉터리라 커밋 대상이 아니고 .gitignore 등록도 불필요하다.
alive = (같은 hostname ∧ pid 생존) ∨ updated_utc가 TTL 이내 — **TTL 판정 기준은
updated_utc다**(재claim heartbeat가 갱신하므로 활성 장기 세션은 TTL을 리셋한다).
pid 생존은 `os.kill(pid, 0)`(ProcessLookupError=사망·PermissionError=생존) —
비POSIX·호스트 상이·pid 미전달은 판정 불능으로 TTL만 의존하고 `pid_check:
"unsupported"`로 투명 표기한다. 판정은 보수 방향이다 — false-positive 경고(비용 =
확인 1회) < false-negative 놓침(비용 = 간섭 사건). 파손 claim 파일은 `corrupt`로
보고하고 판정에서는 alive 보수 취급(판독 불가 = 판단 보류)이며 prune 대상도 아니다.
원자성: claim 쓰기는 temp+fsync+os.replace(r26 영수증 기법), 디렉터리 생성은
mkdir(parents=True, exist_ok=True)(동시 첫 claim 경합 안전).
종료코드: 0 완료 · 1 attention(확인 의무 플래그 — claim은 기록 수행 후 주의,
jev의 exit 1 폴백과 정반대) · 2 config/env/git 오류(이유가 붙은 bypass — stderr
`FAIL tree gate: <사유>`, stdout 없음. --save 실패만 stdout JSON saved_to null
보존). exit 3은 미사용 — 판단 계층이 없어 상향 경로 자체가 없다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

GATE = 'tree-gate'
REGISTRY_DIRNAME = 'effort-router-tree-claims'
EXIT_PASS = 0
EXIT_ATTENTION = 1
EXIT_CONFIG = 2
DEFAULT_TTL_HOURS = 24.0
GIT_FIXED = ('-c', 'core.autocrlf=false', '-c', 'core.quotePath=false')
SESSION_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
SESSION_SANITIZE_RE = re.compile(r'[^A-Za-z0-9._-]')
FLAG_FOREIGN = 'foreign_claim_present'
FLAG_STALE = 'stale_claims_present'
IS_POSIX = os.name == 'posix'


class GateConfigError(Exception):
    """인자·env·git 오류 — exit 2(이유가 붙은 bypass)로 변환한다."""


# ---------------------------------------------------------------- 공통 하층

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_git(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """git 판독 호출 — autocrlf·quotePath 고정, errors='replace'(r23 GIT_FIXED 준용)."""
    return subprocess.run(['git', *GIT_FIXED, *args], capture_output=True,
                          text=True, errors='replace', cwd=cwd)


def git_reason(completed: subprocess.CompletedProcess) -> str:
    lines = completed.stderr.strip().splitlines()
    return lines[-1].strip() if lines else '(git 출력 없음)'


def fail_config(reason: str) -> None:
    print(f'FAIL tree gate: {reason}', file=sys.stderr)
    raise SystemExit(EXIT_CONFIG)


def resolve_common_dir() -> Path:
    """common-dir 확정 — 모든 워크트리가 공유하는 .git(구 git 폴백 포함)."""
    completed = run_git('rev-parse', '--path-format=absolute', '--git-common-dir')
    if completed.returncode != 0:
        completed = run_git('rev-parse', '--git-common-dir')
        if completed.returncode != 0:
            raise GateConfigError('git 저장소가 아니다 — ' + git_reason(completed))
        common = Path(completed.stdout.strip())
        if not common.is_absolute():
            common = Path.cwd() / common
    else:
        common = Path(completed.stdout.strip())
    return common.resolve()


def resolve_tree(raw: str | None) -> Path:
    """트리 확정 — --tree 인자 또는 cwd의 작업 트리 최상위(bare 저장소는 실패)."""
    if raw is not None:
        return Path(raw).resolve()
    completed = run_git('rev-parse', '--show-toplevel')
    if completed.returncode != 0:
        raise GateConfigError(
            '작업 트리를 확정할 수 없다(--show-toplevel) — bare 저장소이거나 '
            'git 저장소 밖이다 — ' + git_reason(completed))
    return Path(completed.stdout.strip()).resolve()


def registry_dir(common: Path) -> Path:
    return common / REGISTRY_DIRNAME


def tree_hash(tree: Path) -> str:
    return hashlib.sha256(str(tree).encode('utf-8')).hexdigest()[:16]


def claim_filename(tree: Path, session: str) -> str:
    """`<tree-hash16>-<session-sanitized>.json` — 검증 통과 id는 치환·절단 없다
    (§4.3 검증·sanitize 상한 64자 통일 — 파일명 충돌 경로 원천 차단)."""
    sanitized = SESSION_SANITIZE_RE.sub('_', session)[:64]
    return f'{tree_hash(tree)}-{sanitized}.json'


def validate_session(session: str | None, required: bool) -> str | None:
    if session is None:
        if required:
            raise GateConfigError(
                '--session이 필요하다(CLAIM 시 CLAUDE_SESSION_ID 환경변수 폴백 가능)')
        return None
    if not SESSION_ID_RE.match(session):
        raise GateConfigError(
            f'무효 session-id다(^[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}$): {session!r}')
    return session


def validate_pid(pid: int | None) -> int | None:
    """래퍼·세션 프로세스 pid를 호출자가 전달할 때만 유효(§4.1 각주 2) — CLI
    프로세스 pid는 즉시 종료해 liveness가 무의미하다. 미전달 시 TTL만 의존."""
    if pid is not None and pid < 1:
        raise GateConfigError(f'--pid는 양의 정수여야 한다: {pid!r}')
    return pid


def validate_ttl(ttl_hours: float) -> float:
    if not math.isfinite(ttl_hours) or ttl_hours <= 0:
        raise GateConfigError(f'--ttl-hours는 양수 유한 값이어야 한다: {ttl_hours!r}')
    return ttl_hours


def read_claim(path: Path) -> dict[str, Any] | None:
    """claim 레코드 판독 — 부재·파손·비dict는 None(status·check 마비 금지, R8 준용)."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_claim_atomic(path: Path, record: dict[str, Any]) -> None:
    """claim 원자 기록 — temp+fsync+os.replace(r26 영수증 기법). 쓰기 불가는
    GateConfigError(fail-closed — common-dir 쓰기 불가 저장소는 bypass다)."""
    try:
        directory = path.parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp',
                                   dir=str(directory))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True)
                             + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as error:
        raise GateConfigError(f'claim 기록 실패({path}) — {error}') from error


# ------------------------------------------------------------- alive·stale 판정

def check_pid(pid: Any, hostname: Any) -> tuple[str, bool]:
    """(pid_check 라벨, pid가 생존을 확정하는가) — §4.2. ProcessLookupError=사망,
    PermissionError=생존(타 사용자 소유). 비POSIX·호스트 상이·pid 미전달·기타
    OSError는 unsupported — TTL만 의존한다(투명 표기 계약)."""
    if not isinstance(pid, int) or pid < 1 or not IS_POSIX \
            or hostname != socket.gethostname():
        return 'unsupported', False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return 'dead', False
    except PermissionError:
        return 'alive', True
    except OSError:
        return 'unsupported', False
    return 'alive', True


def ttl_fresh(updated_utc: Any, ttl_hours: float, now: datetime) -> bool:
    """updated_utc가 TTL 이내인가 — 판정 기준은 updated_utc다(claimed_utc 아님).
    판독 불가 타임스탬프는 보수 취급으로 fresh(판단 보류 — prune 대상에서도 제외)."""
    if not isinstance(updated_utc, str):
        return True
    try:
        updated = datetime.fromisoformat(updated_utc)
    except ValueError:
        return True
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return now - updated < timedelta(hours=ttl_hours)


def judge_claim(record: dict[str, Any], ttl_hours: float,
                now: datetime) -> dict[str, Any]:
    """alive/stale 판정 — alive = pid 생존 확정 ∨ TTL 이내. stale = 그 외
    (TTL 초과 ∧ pid 생존 아님 — 사망 확인 또는 판정 불능 포함, §4.1 prune 정의)."""
    pid_check, pid_confirms = check_pid(record.get('pid'), record.get('hostname'))
    fresh = ttl_fresh(record.get('updated_utc'), ttl_hours, now)
    alive = pid_confirms or fresh
    return {'state': 'alive' if alive else 'stale',
            'alive_reason': ('pid' if pid_confirms else 'ttl') if alive else None,
            'pid_check': pid_check}


def scan_tree_claims(reg: Path, tree: Path, exclude_session: str | None,
                     ttl_hours: float, now: datetime) -> tuple[list, list]:
    """같은 트리의 claim 스캔 — (살아있는 타 세션 목록, corrupt 파일명 목록).
    corrupt는 보수 alive 취급 대상이므로 호출부가 플래그 판정에 합류시킨다."""
    foreign: list[dict[str, Any]] = []
    corrupt: list[str] = []
    if not reg.is_dir():
        return foreign, corrupt
    for path in sorted(reg.glob(f'{tree_hash(tree)}-*.json')):
        record = read_claim(path)
        if record is None:
            corrupt.append(path.name)
            continue
        session = record.get('session_id')
        if exclude_session is not None and session == exclude_session:
            continue
        judgement = judge_claim(record, ttl_hours, now)
        if judgement['state'] == 'alive':
            foreign.append({'session_id': session, 'scope': record.get('scope'),
                            'claimed_utc': record.get('claimed_utc'),
                            'updated_utc': record.get('updated_utc'),
                            'alive_reason': judgement['alive_reason'],
                            'pid_check': judgement['pid_check']})
    return foreign, corrupt


def scan_registry(reg: Path, tree: Path | None, ttl_hours: float,
                  now: datetime) -> tuple[list, list]:
    """레지스트리(또는 단일 트리 스코프) 전수 판독 — (claims 판정 목록, corrupt)."""
    claims: list[dict[str, Any]] = []
    corrupt: list[str] = []
    if not reg.is_dir():
        return claims, corrupt
    pattern = f'{tree_hash(tree)}-*.json' if tree is not None else '*.json'
    for path in sorted(reg.glob(pattern)):
        record = read_claim(path)
        if record is None:
            corrupt.append(path.name)
            continue
        judgement = judge_claim(record, ttl_hours, now)
        entry = {'session_id': record.get('session_id'), 'tree': record.get('tree'),
                 'scope': record.get('scope'),
                 'claimed_utc': record.get('claimed_utc'),
                 'updated_utc': record.get('updated_utc'),
                 'pid_check': judgement['pid_check'], 'state': judgement['state'],
                 'file': path.name}
        if judgement['state'] == 'alive':
            entry['alive_reason'] = judgement['alive_reason']
        claims.append(entry)
    return claims, corrupt


# ------------------------------------------------------------------ 서브커맨드

def cmd_claim(reg: Path, args: argparse.Namespace, session: str,
              now: datetime) -> dict[str, Any]:
    """claim — 자기 (tree, session) 기록. 동일 조합 재claim은 updated_utc만 갱신
    멱등 = heartbeat(claimed_utc 최초 고정). 타 alive claim 존재 시에도 기록은
    수행한다 + foreign_claim_present(exit 1 — 기록과 주의는 별개 신호)."""
    tree = resolve_tree(args.tree)
    path = reg / claim_filename(tree, session)
    existing = read_claim(path)
    if existing is not None:
        if existing.get('session_id') != session:
            raise GateConfigError(
                f'claim 파일명 충돌 — 레코드 session_id 불일치: {path.name}')
        record = {**existing, 'updated_utc': utc_now()}  # heartbeat — claimed_utc 고정
    else:
        stamp = utc_now()  # 신규 claim — claimed·updated가 같은 순간이다
        record = {'version': 1, 'gate': GATE, 'session_id': session,
                  'tree': str(tree), 'tree_hash': tree_hash(tree),
                  'scope': args.scope, 'hostname': socket.gethostname(),
                  'pid': args.pid, 'claimed_utc': stamp, 'updated_utc': stamp}
    write_claim_atomic(path, record)
    foreign, corrupt = scan_tree_claims(reg, tree, session, args.ttl_hours, now)
    flags = [FLAG_FOREIGN] if foreign or corrupt else []
    return {'ok': True, 'gate': GATE, 'subcommand': 'claim', 'tree': str(tree),
            'session_id': session, 'claim_file': path.name, 'claim': record,
            'flags': flags, 'foreign_claims': foreign, 'stale_claims': [],
            'corrupt': corrupt, 'saved_to': None}


def cmd_release(reg: Path, args: argparse.Namespace,
                session: str) -> dict[str, Any]:
    """release — 자기 (tree, session) claim 제거. 제거 전 레코드 session_id 대조
    (파일명 충돌 방어 — 불일치·파손은 거부). 부재 시 멱등 already_released."""
    tree = resolve_tree(args.tree)
    path = reg / claim_filename(tree, session)
    record = read_claim(path)
    if record is None:
        if path.exists():
            raise GateConfigError(
                f'release 거부 — claim 레코드 파손으로 소유를 검증할 수 없다: '
                f'{path.name}(수동 확인 후 제거)')
        return {'ok': True, 'gate': GATE, 'subcommand': 'release',
                'tree': str(tree), 'session_id': session,
                'already_released': True, 'flags': [], 'foreign_claims': [],
                'stale_claims': [], 'corrupt': [], 'saved_to': None}
    if record.get('session_id') != session:
        raise GateConfigError(
            f'release 거부 — 레코드 session_id 불일치(타 세션 파일 제거 금지): '
            f'{path.name}')
    try:
        path.unlink()
    except OSError as error:
        raise GateConfigError(f'claim 제거 실패({path}) — {error}') from error
    return {'ok': True, 'gate': GATE, 'subcommand': 'release', 'tree': str(tree),
            'session_id': session, 'already_released': False, 'flags': [],
            'foreign_claims': [], 'stale_claims': [], 'corrupt': [],
            'saved_to': None}


def cmd_check(reg: Path, args: argparse.Namespace, session: str | None,
              now: datetime) -> dict[str, Any]:
    """check — 같은 트리의 살아있는 타 세션 claim 탐색. session 미지정은 자기
    claim 없음 전제 전수 탐색(claim 전 사전 확인 용도, §4.1 각주 3)."""
    tree = resolve_tree(args.tree)
    foreign, corrupt = scan_tree_claims(reg, tree, session, args.ttl_hours, now)
    flags = [FLAG_FOREIGN] if foreign or corrupt else []
    return {'ok': True, 'gate': GATE, 'subcommand': 'check', 'tree': str(tree),
            'session_id': session, 'flags': flags, 'foreign_claims': foreign,
            'stale_claims': [], 'corrupt': corrupt, 'saved_to': None}


def cmd_status(reg: Path, args: argparse.Namespace,
               now: datetime) -> dict[str, Any]:
    """status — claim 보고(--tree 지정 시 해당 트리, 미지정 시 레지스트리 전체).
    stale 1건 이상 시 stale_claims_present(prune 유도 — removable 대칭)."""
    tree = resolve_tree(args.tree) if args.tree is not None else None
    claims, corrupt = scan_registry(reg, tree, args.ttl_hours, now)
    stale = [c for c in claims if c['state'] == 'stale']
    flags = [FLAG_STALE] if stale else []
    return {'ok': True, 'gate': GATE, 'subcommand': 'status',
            'tree': str(tree) if tree is not None else None, 'session_id': None,
            'claims': claims, 'flags': flags, 'stale_claims': stale,
            'foreign_claims': [], 'corrupt': corrupt, 'saved_to': None}


def cmd_prune(reg: Path, args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    """prune — stale 판정 claim만 제거(alive 절대 불가침 — 안전한 정리). corrupt는
    판정 불능이라 대상에서 제외한다. --dry-run은 보고만(무변경)."""
    claims, corrupt = scan_registry(reg, None, args.ttl_hours, now)
    stale = [c for c in claims if c['state'] == 'stale']
    removed = 0
    if not args.dry_run:
        for target in stale:
            try:
                (reg / target['file']).unlink()
            except OSError as error:
                raise GateConfigError(
                    f"claim 제거 실패({target['file']}) — {error}") from error
            removed += 1
    return {'ok': True, 'gate': GATE, 'subcommand': 'prune', 'tree': None,
            'session_id': None, 'flags': [], 'foreign_claims': [],
            'stale_claims': stale, 'corrupt': corrupt, 'removed': removed,
            'dry_run': bool(args.dry_run), 'saved_to': None}


# ------------------------------------------------------------------ CLI 출력

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='트리 소유 게이트 — 복수 기록자 조율 claim 레지스트리'
                    '(claim·release·check·status·prune)')
    sub = parser.add_subparsers(dest='subcommand', required=True)

    def add_common(target: argparse.ArgumentParser) -> None:
        target.add_argument('--save',
                            help='결과 JSON 저장 디렉터리(tree-gate-<UTC타임스탬프>.json)')
        target.add_argument('--ttl-hours', type=float, default=DEFAULT_TTL_HOURS,
                            help=f'alive 판정 TTL 시간(기본 {DEFAULT_TTL_HOURS:.0f}, '
                                 '양수 유한 — 기준은 updated_utc)')

    claim = sub.add_parser('claim', help='자기 세션 claim 기록(재claim은 heartbeat 멱등)')
    claim.add_argument('--session', help='세션 id(미지정 시 CLAUDE_SESSION_ID 폴백)')
    claim.add_argument('--scope', help='작업 스코프 설명(선택 — 시크릿 기재 금지)')
    claim.add_argument('--tree', help='작업 트리 경로(기본: cwd의 git toplevel)')
    claim.add_argument('--pid', type=int, help='래퍼·세션 프로세스 pid(선택 — '
                                            '미전달 시 TTL만 의존)')
    add_common(claim)

    release = sub.add_parser('release', help='자기 claim 제거(멱등·소유 대조)')
    release.add_argument('--session', required=True, help='세션 id')
    release.add_argument('--tree', help='작업 트리 경로(기본: cwd의 git toplevel)')
    add_common(release)

    check = sub.add_parser('check', help='같은 트리의 살아있는 타 세션 claim 탐색')
    check.add_argument('--session', help='자기 세션 id(미지정 시 전수 탐색)')
    check.add_argument('--tree', help='작업 트리 경로(기본: cwd의 git toplevel)')
    add_common(check)

    status = sub.add_parser('status', help='claim 전체 보고(alive·stale 판정)')
    status.add_argument('--tree', help='스코프 트리(미지정 시 레지스트리 전체)')
    add_common(status)

    prune = sub.add_parser('prune', help='stale claim만 제거(alive 불가침)')
    prune.add_argument('--dry-run', action='store_true', help='보고만(무변경)')
    add_common(prune)
    return parser.parse_args(argv)


def save_result(save_dir: str, result: dict[str, Any]) -> tuple[str | None, str | None]:
    """결과 JSON 저장 — (경로, None) 또는 (None, 사유). r23·r24 계약 평행."""
    try:
        directory = Path(save_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = directory / f'{GATE}-{stamp}.json'
        payload = {**result, 'saved_to': str(path)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    except OSError as error:
        return None, str(error)
    return str(path), None


def emit(result: dict[str, Any], save_dir: str | None) -> None:
    """stdout 단일 JSON + 플래그 기반 종료 — 저장 실패만 stdout 보존 후 exit 2
    (§4.4 — 검사 결과를 버리지 않는다)."""
    if save_dir is not None:
        saved, save_error = save_result(save_dir, result)
        if saved is None:
            print(json.dumps(result, ensure_ascii=False))
            fail_config(f'--save 실패 — 검사 결과는 위 stdout JSON에 보존됐다: {save_error}')
        result = {**result, 'saved_to': saved}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(EXIT_ATTENTION if result['flags'] else EXIT_PASS)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        validate_ttl(args.ttl_hours)
        common = resolve_common_dir()
        reg = registry_dir(common)
        now = datetime.now(timezone.utc)
        if args.subcommand == 'claim':
            session = validate_session(
                args.session if args.session is not None
                else os.environ.get('CLAUDE_SESSION_ID'), required=True)
            validate_pid(args.pid)
            result = cmd_claim(reg, args, session, now)
        elif args.subcommand == 'release':
            result = cmd_release(reg, args, args.session)
        elif args.subcommand == 'check':
            result = cmd_check(reg, args, validate_session(args.session,
                                                           required=False), now)
        elif args.subcommand == 'status':
            result = cmd_status(reg, args, now)
        else:
            result = cmd_prune(reg, args, now)
    except GateConfigError as error:
        fail_config(str(error))
    emit(result, args.save)


if __name__ == '__main__':
    main()
