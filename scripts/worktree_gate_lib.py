#!/usr/bin/env python3
"""r24 워크트리 수명주기 게이트 공용 계층 — git 데이터 판독·salvage·분류(650줄 분할).

worktree_gate.py(CLI)가 임포트하는 git helper·salvage 엔진·entry 분류다. 설계
계약 전문은 worktree_gate.py 모듈 독스트링과 SKILL.md '워크트리 수명주기 게이트'
절에 있다 — 본 파일은 계약을 반복하지 않는다.
salvage 세 경로: 관리 worktree는 status --porcelain 판정 후 add -A + commit
(--no-verify·identity 폴백), 미관리는 plumbing(write-tree·commit-tree·branch 생성)
으로 원본 브랜치 무변경, remove 실패 잔존 디렉터리는 임시 인덱스 판독
(read-tree→add→diff-index --cached) 후 commit-tree·update-ref로 수렴한다(C29).
"""
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATE = 'worktree-gate'
EXIT_PASS = 0
EXIT_ATTENTION = 1
EXIT_CONFIG = 2
GIT_FIXED = ('-c', 'core.autocrlf=false', '-c', 'core.quotePath=false')
GATE_IDENTITY = ('-c', 'user.name=worktree-gate', '-c', 'user.email=worktree-gate@local')
TASK_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
BRANCH_PREFIX = 'wt/'
SALVAGE_MESSAGE = 'salvage({task}): worktree 제거 전 미커밋 변경분 보존'
UNMANAGED_SALVAGE_MESSAGE = 'salvage(unmanaged): 미관리 worktree 제거 전 미커밋 변경분 보존'
FLAG_SALVAGE = 'salvage_committed'
FLAG_REMOVABLE = 'removable_worktrees_present'
FLAG_MISSING = 'worktree_missing'


class GateConfigError(Exception):
    """인자·env·git 오류 — exit 2(이유가 붙은 bypass)로 변환한다."""


# ---------------------------------------------------------------- 공통 하층

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


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


def fail_config(reason: str) -> None:
    print(f'FAIL worktree gate: {reason}', file=sys.stderr)
    raise SystemExit(EXIT_CONFIG)


# ------------------------------------------------- 본체 식별·경로 파생(M-c)

def resolve_main_repo() -> Path:
    """본체 .git 확정(--git-common-dir) → 본체 루트는 그 부모. cwd 무관."""
    completed = run_git('rev-parse', '--path-format=absolute', '--git-common-dir')
    if completed.returncode != 0:
        completed = run_git('rev-parse', '--git-common-dir')  # 구 git 폴백
        if completed.returncode != 0:
            raise GateConfigError('git 저장소가 아니다 — ' + git_reason(completed))
        common = Path(completed.stdout.strip())
        if not common.is_absolute():
            common = Path.cwd() / common
    else:
        common = Path(completed.stdout.strip())
    return common.resolve().parent


def validate_task(task: str) -> str:
    if not TASK_ID_RE.match(task):
        raise GateConfigError(
            f'무효 task-id다(^[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}$): {task!r}')
    return task


def container_dir(repo: Path) -> Path:
    return repo.parent / f'{repo.name}-worktrees'


def wt_path(repo: Path, task: str) -> Path:
    return container_dir(repo) / task


def registry_path(repo: Path, task: str) -> Path:
    return repo / 'docs/task-id' / task / 'worktree.json'


def registry_field(repo: Path, task: str, updated: bool) -> dict[str, Any]:
    return {'path': str(registry_path(repo, task).relative_to(repo)),
            'updated': updated}


# ------------------------------------------------------------- git 데이터 판독

def read_state_phase(repo: Path, task: str) -> str | None:
    """state.json은 phase 키만 판독 — 파손·부재 시 None(list·sweep 마비 방지 R8)."""
    try:
        data = json.loads(
            (repo / 'docs/task-id' / task / 'state.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data.get('phase') if isinstance(data, dict) else None


def read_registry(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_registry(path: Path, data: dict[str, Any]) -> None:
    """레지스트리 기록 — 갱신은 기존 dict를 읽어 새 dict 조립(돌연변이 금지)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    except OSError as error:
        raise GateConfigError(f'레지스트리 기록 실패({path}) — {error}') from error


def branch_exists(branch: str) -> bool:
    return run_git('show-ref', '--verify', '--quiet',
                   f'refs/heads/{branch}').returncode == 0


def branch_tip(branch: str) -> str | None:
    completed = run_git('rev-parse', '--verify', f'refs/heads/{branch}')
    return completed.stdout.strip() if completed.returncode == 0 else None


def parse_worktree_list(stdout: str) -> list[dict[str, Any]]:
    """porcelain 파서(M-d) — branch는 refs/heads/ 접두 제거, detached·파서 실패
    항목은 branch None으로 내려보낸다(분류 단계에서 unmanaged — 목록 마비 금지)."""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in stdout.splitlines():
        if line.startswith('worktree '):
            if current is not None:
                entries.append(current)
            current = {'path': line[len('worktree '):], 'head': None, 'branch': None,
                       'locked': False, 'bare': False, 'detached': False}
        elif current is None:
            continue  # 블럭 앞 이탈 라인 — 폐기(마비 방지)
        elif line.startswith('HEAD '):
            current['head'] = line[len('HEAD '):]
        elif line.startswith('branch '):
            ref = line[len('branch '):]
            prefix = 'refs/heads/'
            current['branch'] = ref[len(prefix):] if ref.startswith(prefix) else ref
        elif line == 'detached':
            current['detached'] = True
        elif line == 'locked' or line.startswith('locked '):
            current['locked'] = True
        elif line == 'bare':
            current['bare'] = True
    if current is not None:
        entries.append(current)
    return entries


def worktree_entries() -> list[dict[str, Any]]:
    completed = run_git('worktree', 'list', '--porcelain')
    if completed.returncode != 0:
        raise GateConfigError('git worktree list 실패 — ' + git_reason(completed))
    return parse_worktree_list(completed.stdout)


def find_worktree(entries: list[dict[str, Any]], branch: str) -> dict[str, Any] | None:
    return next((entry for entry in entries if entry.get('branch') == branch), None)


def du_bytes(path: str) -> int | None:
    """du -sb 경로별 bytes(GNU 전용 — 실패·비GNU 시 null 허용, LOW)."""
    try:
        completed = subprocess.run(['du', '-sb', path], capture_output=True,
                                   text=True, errors='replace', timeout=120)
        if completed.returncode == 0:
            return int(completed.stdout.split()[0])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


# ------------------------------------------------------------------- salvage

def salvage_none(discarded: int = 0, skipped: bool = False) -> dict[str, Any]:
    """salvage 미수행 표준 형태(null 아님 — C9 구분)."""
    return {'performed': False, 'commit': None, 'changes': 0, 'files': [],
            'skipped_by_option': skipped, 'discarded_changes': discarded}


def status_porcelain(wt: Path) -> list[str]:
    """worktree 상태 — porcelain은 ignored를 제외하므로 공백 ⇔ salvage 불필요(P1).
    -uall — untracked 디렉터리를 파일 단위로 전개(salvage.files 열람 면, H4)."""
    completed = run_git('status', '--porcelain', '-uall', cwd=str(wt))
    if completed.returncode != 0:
        raise GateConfigError('git status 실패 — ' + git_reason(completed))
    return [line for line in completed.stdout.splitlines() if line.strip()]


def porcelain_paths(lines: list[str]) -> list[str]:
    paths = []
    for line in lines:
        body = line[3:] if len(line) > 3 else line
        if ' -> ' in body:  # rename 표기 — 새 경로만 열람 대상으로 남긴다
            body = body.split(' -> ', 1)[1]
        paths.append(body)
    return paths


def perform_salvage(task: str, wt: Path) -> dict[str, Any]:
    """관리 worktree salvage — add -A + commit(--no-verify·identity 폴백, H2·H3)."""
    lines = status_porcelain(wt)
    if not lines:
        return salvage_none()
    files = porcelain_paths(lines)
    git_ok('add', '-A', cwd=str(wt))
    completed = run_git(*GATE_IDENTITY, 'commit', '--no-verify',
                        '-m', SALVAGE_MESSAGE.format(task=task), cwd=str(wt))
    if completed.returncode != 0:
        if 'nothing to commit' in completed.stdout + completed.stderr:
            # 경쟁 재판정 — 공백이면 무해 종료(salvage 미수행), 잔존이면 exit 2(LOW)
            if not status_porcelain(wt):
                return salvage_none()
        raise GateConfigError(f'salvage 커밋 실패 — {git_reason(completed)}')
    return {'performed': True, 'commit': git_ok('rev-parse', 'HEAD', cwd=str(wt)),
            'changes': len(lines), 'files': files,
            'skipped_by_option': False, 'discarded_changes': 0}


def perform_salvage_unmanaged(wt: Path) -> dict[str, Any]:
    """미관리 worktree salvage(H1) — plumbing으로 원본 브랜치 포인터 무변경:
    write-tree → commit-tree(부모 = 현 HEAD) → salvage/unmanaged-<스탬프> 브랜치 생성.
    checkout 없이 커밋을 적립한다(게이트 금지 명령 reset·checkout 회피)."""
    lines = status_porcelain(wt)
    if not lines:
        return salvage_none()
    files = porcelain_paths(lines)
    git_ok('add', '-A', cwd=str(wt))
    tree = git_ok('write-tree', cwd=str(wt))
    head = git_ok('rev-parse', 'HEAD', cwd=str(wt))
    completed = run_git(*GATE_IDENTITY, 'commit-tree', tree, '-p', head,
                        '-m', UNMANAGED_SALVAGE_MESSAGE, cwd=str(wt))
    if completed.returncode != 0:
        raise GateConfigError('salvage commit-tree 실패 — ' + git_reason(completed))
    sha = completed.stdout.strip()
    branch_name = f'salvage/unmanaged-{utc_stamp()}'
    git_ok('branch', branch_name, sha)
    return {'performed': True, 'commit': sha, 'branch': branch_name,
            'changes': len(lines), 'files': files,
            'skipped_by_option': False, 'discarded_changes': 0}


def perform_salvage_leftover(wt: Path, branch: str, commit: bool = True) -> dict[str, Any]:
    """등록 해제된 잔존 디렉터리(remove 실패 잔존물)의 salvage 재판정·적립(C29 수렴).

    remove 실패 시 admin 메타데이터는 제거되고 디렉터리만 남는다(실측) — status
    --porcelain이 불가하므로 임시 인덱스(read-tree tip → add -A → diff-index
    --cached)로 tip 기준 미커밋분을 판독한다(본체 인덱스 비접촉, oid 비교라 stat
    오탐 없음). 잔존 시 commit-tree 적립 후 update-ref로 브랜치를 선진한다 —
    salvage는 커밋 추가다. commit=False(--no-salvage)면 폐기 수만 판독해 기록하고
    커밋하지 않는다(A12·C36 — 명시 옵션은 잔존 경로에서도 유효). 브랜치 앵커가
    없으면 이 경로에 진입하지 않는다(호출부).
    """
    common = git_ok('rev-parse', '--path-format=absolute', '--git-common-dir')
    fd, index_path = tempfile.mkstemp(prefix='worktree-gate-index-')
    os.close(fd)
    try:
        env = {**os.environ, 'GIT_INDEX_FILE': index_path}
        prefix = ['git', *GIT_FIXED, f'--git-dir={common}', f'--work-tree={wt}']

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([*prefix, *args], env=env, capture_output=True,
                                  text=True, errors='replace')

        def must(completed: subprocess.CompletedProcess, label: str) -> str:
            if completed.returncode != 0:
                raise GateConfigError(f'{label} 실패 — {git_reason(completed)}')
            return completed.stdout.strip()

        must(run('read-tree', f'refs/heads/{branch}'), '잔존 디렉터리 read-tree')
        must(run('add', '-A'), '잔존 디렉터리 add')
        files = [line for line in must(run('diff-index', '--cached', '--name-only',
                                           f'refs/heads/{branch}'),
                                       '잔존 디렉터리 diff-index').splitlines()
                 if line]
        if not commit:
            # --no-salvage — skipped_by_option은 폐기 수와 무관하게 True(정상 경로 통일)
            return salvage_none(discarded=len(files), skipped=True)
        if not files:
            return salvage_none()
        tree = must(run('write-tree'), '잔존 디렉터리 write-tree')
        parent = must(run('rev-parse', f'refs/heads/{branch}'), '잔존 브랜치 판독')
        message = SALVAGE_MESSAGE.format(task=branch[len(BRANCH_PREFIX):])
        sha = must(run(*GATE_IDENTITY, 'commit-tree', tree, '-p', parent,
                       '-m', message), '잔존 디렉터리 commit-tree')
        must(run('update-ref', f'refs/heads/{branch}', sha), '잔존 브랜치 갱신')
        return {'performed': True, 'commit': sha, 'changes': len(files),
                'files': files, 'skipped_by_option': False, 'discarded_changes': 0}
    finally:
        try:
            os.unlink(index_path)
        except OSError:
            pass


def remove_worktree_force(path: str) -> None:
    completed = run_git('worktree', 'remove', '--force', path)
    if completed.returncode != 0:
        raise GateConfigError(f"worktree remove 실패({path}) — {git_reason(completed)}")


def prune_worktrees() -> bool:
    """고아 admin 메타데이터 정리 — best-effort(실패가 절차를 중단하지 않는다)."""
    return run_git('worktree', 'prune').returncode == 0


def rmdir_container_best_effort(repo: Path) -> None:
    """빈 컨테이너 정리 — 실패 무시(best-effort, LOW)."""
    try:
        container_dir(repo).rmdir()
    except OSError:
        pass


def discard_leftover_dir(leftover: Path) -> None:
    """등록 해제된 잔존 디렉터리 삭제 — remove --force 대상이 아니다(C29 수렴 한정).

    이 경로는 salvage 재판정(위 perform_salvage_leftover)과 브랜치 앵커 확인 뒤에만
    도달한다 — rmtree는 게이트의 일상 파기 수단이 아니라 잔존 수렴 전용이다.
    삭제 실패는 exit 2로 보고한다(§3 — 실패 경로의 암묵 traceback 금지)."""
    try:
        shutil.rmtree(leftover)
    except OSError as error:
        raise GateConfigError(
            f'잔존 디렉터리 삭제 실패({leftover}) — {error}') from error


def last_salvage_commit(branch: str) -> str | None:
    """브랜치에서 최근 salvage 커밋 SHA — 순수 수렴(재판정 공백) 시 1차 실패 당시
    salvage SHA를 레지스트리에 남기는 기록 보조(LOW-6). 부재 시 None."""
    completed = run_git('log', '--grep=^salvage(', '--format=%H', '-n', '1',
                        f'refs/heads/{branch}')
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


# ------------------------------------------------------- 분류(list·sweep 공용)

def classify_entries(repo: Path) -> list[dict[str, Any]]:
    """본체 첫 항목 제외한 worktree 분류 — managed(명명규칙: 컨테이너/<task-id> ∧
    브랜치 wt/<task-id>)·eligible(phase=="done" 리터럴 ∨ 고아[과업 폴더 소실]).
    폴더 존재·state.json 파손은 고아 아님(보존 — H5·R7), detached는 unmanaged."""
    infos: list[dict[str, Any]] = []
    for entry in worktree_entries()[1:]:
        branch = entry['branch']
        task = branch[len(BRANCH_PREFIX):] if branch else None
        if task is not None and (not TASK_ID_RE.match(task)
                                 or entry['path'] != str(wt_path(repo, task))):
            task = None
        if task is None:
            infos.append({'entry': entry, 'task': None, 'managed': False,
                          'classification': 'unmanaged',
                          'unmanaged_reason': 'detached' if entry['detached'] else 'manual',
                          'phase': None, 'orphan': False, 'registered': False,
                          'done_utc': None, 'eligible': False})
            continue
        registry = read_registry(registry_path(repo, task))
        phase = read_state_phase(repo, task)
        orphan = not (repo / 'docs/task-id' / task).exists()
        infos.append({'entry': entry, 'task': task, 'managed': True,
                      'classification': 'managed', 'phase': phase, 'orphan': orphan,
                      'registered': registry is not None,
                      'done_utc': registry.get('done_utc') if registry else None,
                      'eligible': orphan or phase == 'done'})
    return infos
