#!/usr/bin/env python3
"""r24 워크트리 수명주기 게이트 CLI — 생성·완료 제거 기계 강제(강제 제거 ∧ 정지 트리 0손실 — 동시 작성 감지 후 제거, r25).

워크트리 격리 과업의 완료 후 잔존(디스크 고갈 반복 관측 실패)을 막는 게이트다.
미포스 `git worktree remove`는 작업 트리가 dirty(tracked 수정·staged)하거나
untracked 파일이 있으면 거부된다 — 수동 제거가 반복 실패해 방치되는 경로를,
salvage 커밋(미커밋 분만) 후 remove --force·prune의 7단계 기계 절차로 강제한다.
salvage는 커밋 추가이지 리셋이 아니다 — 게이트가 실행하는 파기성·변경성 명령은
`worktree remove --force`·`branch -D`(done --drop-branch 명시 옵션 — create add 실패 정리 제외)·`add -A`·`commit --no-verify`와
salvage 전용 plumbing(branch 생성·update-ref·잔존 디렉터리 rmtree)뿐이며
reset·checkout·unlock 자동 실행은 금지한다.
본체 저장소 식별은 `git rev-parse --git-common-dir`(M-c) — worktree 내부에서
실행해도 본체 기준으로 레지스트리·컨테이너·목록을 파생한다.
salvage 커밋은 identity 폴백 `-c user.name=worktree-gate -c user.email=worktree-gate@local`
(H2)과 `--no-verify`(H3 — 기계 절차에 hook 판단은 무의미)를 병용해 어떤 로컬
환경에서도 성립한다. git 호출은 `-c core.autocrlf=false -c core.quotePath=false`
고정, subprocess 디코드는 errors='replace'(r23 GIT_FIXED 준용). 공용 git 계층은
worktree_gate_lib.py(650줄 분할 — 번들 §2).
종료코드: 0 완료(eligible 0건 포함 — dry-run·명시 폐기도 기록으로 남는다) ·
1 attention(확인 의무 플래그 — jev의 exit 1 폴백과 정반대) · 2 config/env/git
오류(이유가 붙은 bypass — stderr `FAIL worktree gate: <사유>`). exit 3은 미사용 —
판단 계층이 없어 상향 경로 자체가 없다(r23과 동일 근거).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import worktree_gate_lib as lib
from worktree_gate_lib import (BRANCH_PREFIX, EXIT_ATTENTION, EXIT_PASS, FLAG_MISSING,
                               FLAG_REMOVABLE, FLAG_SALVAGE, GATE, GateConfigError,
                               classify_entries, du_bytes, perform_salvage_unmanaged)


# ------------------------------------------------------------------ 서브커맨드

def cmd_create(repo: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = lib.validate_task(args.task)
    reg_path = lib.registry_path(repo, task)
    if reg_path.exists():
        raise GateConfigError(f'이미 레지스트리가 있다 — 중복 create 금지: {task}')
    wt = lib.wt_path(repo, task)
    if wt.exists():
        raise GateConfigError(f'경로 충돌 — worktree 디렉터리가 이미 존재한다: {wt}')
    branch = BRANCH_PREFIX + task
    if lib.branch_exists(branch):
        raise GateConfigError(
            f'잔존 브랜치 {branch}가 단독 존재한다(실패 잔존물로 보인다) — '
            f'확인 후 git branch -D {branch}')
    base_sha = lib.git_ok('rev-parse', '--verify', args.base)
    try:
        reg_path.parent.mkdir(parents=True, exist_ok=True)  # 과업 폴더 mkdir(LOW)
    except OSError as error:
        raise GateConfigError(
            f'과업 폴더 생성 실패({reg_path.parent}) — {error}') from error
    completed = lib.run_git('worktree', 'add', str(wt), '-b', branch, base_sha,
                            cwd=str(repo))
    if completed.returncode != 0:
        lib.run_git('branch', '-D', branch)  # add 실패 부분 정리(best-effort 원자성 M-a)
        raise GateConfigError(f'worktree add 실패 — {lib.git_reason(completed)}')
    head = lib.git_ok('rev-parse', 'HEAD', cwd=str(wt))
    lib.write_registry(reg_path, {'version': 1, 'gate': GATE, 'task': task,
                                  'path': str(wt), 'branch': branch,
                                  'base_ref': args.base, 'base_sha': base_sha,
                                  'created_utc': lib.utc_now(), 'done_utc': None,
                                  'salvage_commit': None,
                                  'dropped_branch_tip': None})
    return {'ok': True, 'gate': GATE, 'subcommand': 'create', 'task': task,
            'timestamp_utc': lib.utc_now(),
            'worktree': {'path': str(wt), 'branch': branch, 'created': True,
                         'head_sha': head},
            'base': {'ref': args.base, 'sha': base_sha},
            'registry': lib.registry_field(repo, task, True),
            'flags': [], 'saved_to': None}


def require_done_phase(repo: Path, task: str) -> None:
    """done 사전 phase 검사(M2·V7) — 활성 과업 done은 exit 2 사전 차단.

    state.json 부재·파손(None)은 고아·레지스트리리스 정상 경로라 진행한다(A5).
    레지스트리 소실+활성 phase 혼합도 동일 차단한다(V7) — phase 패치 주체는 메인
    세션 단일(§5)이며 중단·폐기 과업도 phase=done 전환 후 done 호출이다.
    """
    phase = lib.read_state_phase(repo, task)
    if phase is not None and phase != 'done':
        raise GateConfigError(
            f'활성 과업 상태다(phase={phase}) — phase=done 전환 후 재시도'
            f'(중단·폐기 과업도 동일): {task}')


def emit_partial(partial: dict[str, Any], error: Exception) -> None:
    """부분 결과 JSON을 stdout에 1회 출력한 뒤 원래 예외를 재발행한다(M3·V5).

    emit 미도달 경로라 stdout JSON은 정확 1회다(R6). --save는 수행하지 않는다
    (r23 --save 실패 시 stdout 보존과 동일 형태 — 이 경로는 --save 미수행, 한계).
    재발행된 GateConfigError는 main이 stderr `FAIL <gate>: <사유>`·exit 2로
    변환한다(§3 종료코드 어휘 — exit 1 의미 확장 아님).
    """
    print(json.dumps(partial, ensure_ascii=False))
    raise error


def execute_done(repo: Path, task: str, drop_branch: bool,
                 no_salvage: bool) -> dict[str, Any]:
    """done — 대상 확정·멱등·locked·phase 검사·salvage(동시 작성 감지 루프)·remove·prune·기록(전부 기계 절차, r25 경화)."""
    reg_path = lib.registry_path(repo, task)
    registry = lib.read_registry(reg_path)
    branch = BRANCH_PREFIX + task
    entry = lib.find_worktree(lib.worktree_entries(), branch)
    if entry is None and registry is None:
        raise GateConfigError(
            f'done 대상 부재 — 레지스트리·worktree 모두 없다: {task}')
    if entry is not None \
            and entry['path'] != str(lib.wt_path(repo, task)):
        raise GateConfigError(
            f"브랜치 {branch}의 worktree가 명명규칙 경로 밖에 있다: {entry['path']}")
    registry_less = registry is None
    head_fields = {'ok': None, 'gate': GATE, 'subcommand': 'done', 'task': task,
                   'timestamp_utc': lib.utc_now()}
    if entry is None:
        # 2단계 멱등 확인 — 레지스트리 path는 힌트, porcelain 부재가 우선(LOW).
        pruned = lib.prune_worktrees()
        if registry is None:
            raise GateConfigError(f'done 대상 부재 — 레지스트리·worktree 모두 없다: {task}')
        return finish_absent(repo, task, registry, branch, drop_branch,
                             no_salvage, head_fields, pruned)
    if entry['locked']:
        # lock은 사용자 보존 신호 — 자동 unlock 금지(A11), -f -f 탈출구는 문서로만.
        raise GateConfigError(
            f"worktree가 locked다 — git worktree unlock {entry['path']} 후 재시도하라")
    require_done_phase(repo, task)  # 4단계(M2) — salvage 전 사전 차단
    wt = Path(entry['path'])
    if no_salvage:  # --no-salvage — 폐기를 각오한 명시 옵션(폐기 수 기록, H4·A12·A4)
        salvage = lib.salvage_none(discarded=len(lib.status_porcelain(wt)),
                                   skipped=True)
    else:
        try:
            salvage = lib.salvage_until_quiet(
                lambda: lib.perform_salvage(task, wt),
                lambda: bool(lib.status_porcelain(wt)), str(wt))
        except lib.SalvageAborted as error:
            emit_partial({**head_fields, 'ok': False,
                          'worktree': {'path': str(wt), 'branch': branch,
                                       'removed': False, 'already_removed': False,
                                       'registry_less': registry_less},
                          'salvage': error.salvage, 'pruned': None,
                          'aborted': 'concurrent_writer', 'error': str(error)},
                         error)
    lib.remove_worktree_force(str(wt))      # 5단계 — salvage 후 잔여는 ignored뿐
    pruned = lib.prune_worktrees()          # 6단계
    tip = lib.branch_tip(branch)            # 브랜치는 제거 후에도 잔존(실측 P4)
    dropped = False
    if drop_branch:
        try:
            lib.git_ok('branch', '-D', branch)  # 명시 옵션뿐 — tip SHA 기록 후 삭제
            dropped = True
        except GateConfigError as error:  # M3 — 제거 성공 뒤 실패는 부분 결과 보존
            emit_partial({**head_fields, 'ok': False,
                          'worktree': {'path': str(wt), 'branch': branch,
                                       'removed': True, 'already_removed': False,
                                       'registry_less': registry_less},
                          'salvage': salvage, 'pruned': pruned,
                          'branch': {'name': branch, 'preserved': True,
                                     'dropped': False, 'tip_sha': tip},
                          'registry': lib.registry_field(repo, task, False),
                          'incomplete_step': 'branch_drop', 'error': str(error)},
                         error)
    if registry is not None:
        try:
            lib.write_registry(reg_path, {**registry, 'done_utc': lib.utc_now(),
                                          'salvage_commit': salvage['commit'],
                                          'dropped_branch_tip': tip if dropped
                                          else registry.get('dropped_branch_tip')})
        except GateConfigError as error:  # M3 — 기록 실패도 부분 결과 보존
            emit_partial({**head_fields, 'ok': False,
                          'worktree': {'path': str(wt), 'branch': branch,
                                       'removed': True, 'already_removed': False,
                                       'registry_less': registry_less},
                          'salvage': salvage, 'pruned': pruned,
                          'branch': {'name': branch, 'preserved': not dropped,
                                     'dropped': dropped, 'tip_sha': tip},
                          'registry': lib.registry_field(repo, task, False),
                          'incomplete_step': 'registry_write', 'error': str(error)},
                         error)
    lib.rmdir_container_best_effort(repo)   # 7단계 말미 — 빈 컨테이너 정리
    flags = [FLAG_SALVAGE] if salvage['performed'] else []
    return {**head_fields, 'ok': len(flags) == 0,
            'worktree': {'path': str(wt), 'branch': branch, 'removed': True,
                         'already_removed': False, 'registry_less': registry_less},
            'salvage': salvage, 'pruned': pruned,
            'branch': {'name': branch, 'preserved': not dropped, 'dropped': dropped,
                       'tip_sha': tip},
            'registry': lib.registry_field(repo, task, registry is not None),
            'flags': flags,
            'saved_to': None}


def finish_absent(repo: Path, task: str, registry: dict[str, Any], branch: str,
                  drop_branch: bool, no_salvage: bool,
                  head_fields: dict[str, Any], pruned: bool) -> dict[str, Any]:
    """porcelain 부재 done — 잔존 디렉터리 수렴(C29)·소실 attention·멱등 후속."""
    reg_path = lib.registry_path(repo, task)
    # remove 실패 잔존물 — 등록은 해제됐고 디렉터리만 남았다. 진입 가드(G1):
    # (a) 활성 레지스트리(done_utc 없음 — 완료 과업의 재등장 디렉터리는 멱등 유지)
    # (b) 정규 명명 경로(레지스트리 path 변조 시 임의 경로 삭제 표적 차단)
    # (c) 브랜치 앵커(salvage 도달점) 존재 — 없으면 attention 보존(fail-closed).
    leftover = registry.get('path')
    if registry.get('done_utc') is None and leftover \
            and Path(leftover) == lib.wt_path(repo, task) \
            and Path(leftover).is_dir() and lib.branch_tip(branch) is not None:
        require_done_phase(repo, task)  # 수렴 분기도 활성 과업 사전 차단(M2)
        if no_salvage:
            salvage = lib.salvage_none(
                discarded=len(lib.leftover_dirty_files(Path(leftover), branch)),
                skipped=True)
        else:
            try:
                salvage = lib.salvage_until_quiet(
                    lambda: lib.perform_salvage_leftover(Path(leftover), branch),
                    lambda: bool(lib.leftover_dirty_files(Path(leftover), branch)),
                    str(leftover))
            except lib.SalvageAborted as error:
                emit_partial({**head_fields, 'ok': False,
                              'worktree': {'path': leftover, 'branch': branch,
                                           'removed': False, 'already_removed': False,
                                           'registry_less': False},
                              'salvage': error.salvage, 'pruned': None,
                              'aborted': 'concurrent_writer', 'error': str(error)},
                             error)
        lib.discard_leftover_dir(Path(leftover))
        pruned = lib.prune_worktrees()
        tip = lib.branch_tip(branch)  # 삭제 전 판독 — 정상 경로와 동일 순서(M1)
        dropped = False
        if drop_branch:
            try:
                lib.git_ok('branch', '-D', branch)
                dropped = True
            except GateConfigError as error:  # M3 — 부분 결과 보존
                emit_partial({**head_fields, 'ok': False,
                              'worktree': {'path': leftover, 'branch': branch,
                                           'removed': True, 'already_removed': False,
                                           'registry_less': False},
                              'salvage': salvage, 'pruned': pruned,
                              'branch': {'name': branch, 'preserved': True,
                                         'dropped': False, 'tip_sha': tip},
                              'registry': lib.registry_field(repo, task, False),
                              'incomplete_step': 'branch_drop', 'error': str(error)},
                             error)
        # 순수 수렴(재판정 공백)이면 1차 실패 당시 salvage SHA를 기록한다(LOW-6)
        salvage_sha = salvage['commit'] or lib.last_salvage_commit(branch)
        try:
            lib.write_registry(reg_path, {**registry, 'done_utc': lib.utc_now(),
                                          'salvage_commit': salvage_sha,
                                          'dropped_branch_tip': tip if dropped
                                          else registry.get('dropped_branch_tip')})
        except GateConfigError as error:  # M3 — 기록 실패도 부분 결과 보존
            emit_partial({**head_fields, 'ok': False,
                          'worktree': {'path': leftover, 'branch': branch,
                                       'removed': True, 'already_removed': False,
                                       'registry_less': False},
                          'salvage': salvage, 'pruned': pruned,
                          'branch': {'name': branch, 'preserved': not dropped,
                                     'dropped': dropped, 'tip_sha': tip},
                          'registry': lib.registry_field(repo, task, False),
                          'incomplete_step': 'registry_write', 'error': str(error)},
                         error)
        lib.rmdir_container_best_effort(repo)
        flags = [FLAG_SALVAGE] if salvage['performed'] else []
        return {**head_fields, 'ok': len(flags) == 0,
                'worktree': {'path': leftover, 'branch': branch, 'removed': True,
                             'already_removed': False, 'registry_less': False},
                'salvage': salvage, 'pruned': pruned,
                'branch': {'name': branch, 'preserved': not dropped,
                           'dropped': dropped, 'tip_sha': tip},
                'registry': lib.registry_field(repo, task, True),
                'flags': flags,
                'saved_to': None}
    if registry.get('done_utc'):
        return {**head_fields,
                'worktree': {'path': registry.get('path'), 'branch': branch,
                             'removed': False, 'already_removed': True,
                             'registry_less': False},
                'salvage': lib.salvage_none(), 'pruned': pruned,
                'branch': {'name': branch, 'preserved': True, 'dropped': False,
                           'tip_sha': lib.branch_tip(branch)},
                'registry': lib.registry_field(repo, task, False),
                'flags': [], 'saved_to': None}
    # 활성 레지스트리인데 게이트 밖 소실 — 잔여 미커밋분 손실 가능(attention)
    lib.write_registry(reg_path, {**registry, 'done_utc': lib.utc_now()})
    return {**head_fields,
            'worktree': {'path': registry.get('path'), 'branch': branch,
                         'removed': False, 'already_removed': False,
                         'registry_less': False},
            'salvage': lib.salvage_none(), 'pruned': pruned,
            'branch': {'name': branch, 'preserved': True, 'dropped': False,
                       'tip_sha': lib.branch_tip(branch)},
            'registry': lib.registry_field(repo, task, True),
            'flags': [FLAG_MISSING], 'saved_to': None}


def cmd_list(repo: Path, args: argparse.Namespace) -> dict[str, Any]:
    """list — entries 배열 + summary(total·managed·unmanaged·eligible). eligible
    1건 이상이면 removable_worktrees_present(exit 1 — 디스크 적체 attention)."""
    infos = classify_entries(repo)
    entries_out: list[dict[str, Any]] = []
    for info in infos:
        entry = info['entry']
        item: dict[str, Any] = {'task': info['task'], 'path': entry['path'],
                                'branch': entry['branch'],
                                'classification': info['classification'],
                                'managed': info['managed'],
                                'phase': info['phase'], 'orphan': info['orphan'],
                                'registered': info['registered'],
                                'eligible_for_sweep': info['eligible'],
                                'locked': entry['locked'], 'bytes': None}
        if not info['managed']:
            item['unmanaged_reason'] = info['unmanaged_reason']
        if args.du:
            item['bytes'] = du_bytes(entry['path'])
        entries_out.append(item)
    eligible = sum(1 for info in infos if info['eligible'])
    flags = [FLAG_REMOVABLE] if eligible else []
    summary = {'total': len(entries_out),
               'managed': sum(1 for info in infos if info['managed']),
               'unmanaged': sum(1 for info in infos if not info['managed']),
               'eligible': eligible}
    return {'ok': not flags, 'gate': GATE, 'subcommand': 'list',
            'timestamp_utc': lib.utc_now(), 'entries': entries_out,
            'summary': summary, 'flags': flags, 'saved_to': None}


def remove_unmanaged(entry: dict[str, Any]) -> dict[str, Any]:
    """--unmanaged 제거 — salvage(동시 작성 감지 루프·salvage/unmanaged-* 보존) 후
    remove·prune."""
    wt = Path(entry['path'])
    try:
        salvage = lib.salvage_until_quiet(
            lambda: perform_salvage_unmanaged(wt),
            lambda: bool(lib.unsalvaged_paths(wt)), str(wt))
    except lib.SalvageAborted as error:  # V5 — 감사 대칭 부분 결과
        emit_partial({'task': None, 'path': str(wt),
                      'classification': 'unmanaged', 'salvage': error.salvage,
                      'aborted': 'concurrent_writer', 'error': str(error),
                      'ok': False}, error)
    lib.remove_worktree_force(str(wt))
    pruned = lib.prune_worktrees()
    return {'task': None, 'path': str(wt), 'classification': 'unmanaged',
            'salvage': salvage, 'salvage_branch': salvage.get('branch'),
            'pruned': pruned,
            'flags': [FLAG_SALVAGE] if salvage['performed'] else []}


def cmd_sweep(repo: Path, args: argparse.Namespace) -> dict[str, Any]:
    """sweep — eligible(phase=="done" ∨ 고아)에 done 절차 일괄 적용. 불일치·활성·
    미관리는 기본 보고만(존재 ≠ 허가), 제거는 --unmanaged 명시 시뿐이다."""
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    flags: list[str] = []
    for info in classify_entries(repo):
        entry = info['entry']
        if info['managed']:
            if info['eligible']:
                if args.dry_run:
                    items.append({'task': info['task'], 'path': entry['path'],
                                  'would_remove': True})
                else:
                    item = execute_done(repo, info['task'], args.drop_branch, False)
                    items.append(item)
                    flags.extend(item['flags'])
            elif info['done_utc'] is not None:
                skipped.append({'task': info['task'], 'path': entry['path'],
                                'reason': 'inconsistent'})
            else:
                skipped.append({'task': info['task'], 'path': entry['path'],
                                'reason': 'active_phase'})
        elif not args.unmanaged:
            skipped.append({'task': None, 'path': entry['path'],
                            'reason': 'unmanaged'})
        elif entry['locked']:
            # L3 — lock은 사용자 보존 신호 — salvage 전 사전 분류(salvage 브랜치만
            # 남는 반쪽 상태 방지). 탈출구는 unlock 후 재시도
            skipped.append({'task': None, 'path': entry['path'],
                            'reason': 'locked'})
        elif entry['detached']:
            # detached HEAD는 브랜치 재구성 불가 — 명시 옵션에서도 보존(LOW)
            skipped.append({'task': None, 'path': entry['path'],
                            'reason': 'detached'})
        elif args.dry_run:
            items.append({'path': entry['path'], 'would_remove': True,
                          'classification': 'unmanaged'})
        else:
            item = remove_unmanaged(entry)
            items.append(item)
            flags.extend(item['flags'])
    flags = sorted(set(flags))
    return {'ok': not flags, 'gate': GATE, 'subcommand': 'sweep',
            'timestamp_utc': lib.utc_now(), 'items': items, 'skipped': skipped,
            'summary': {'swept': len(items), 'skipped': len(skipped)},
            'flags': flags, 'saved_to': None}


# ------------------------------------------------------------------ CLI 출력

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='워크트리 수명주기 게이트 — 생성·완료 제거 기계 강제'
                    '(salvage 보존 후 remove --force·prune)')
    sub = parser.add_subparsers(dest='subcommand', required=True)

    def add_save(target: argparse.ArgumentParser) -> None:
        target.add_argument('--save', help='결과 JSON 저장 디렉터리'
                                           '(worktree-gate-<UTC타임스탬프>.json)')

    create = sub.add_parser('create', help='worktree·브랜치·레지스트리 생성')
    create.add_argument('--task', required=True, help='task-id(명명규칙 검증 대상)')
    create.add_argument('--base', default='HEAD', help='시작 커밋(기본 HEAD)')
    add_save(create)

    done = sub.add_parser('done', help='salvage 후 제거·prune·기록(7단계)')
    done.add_argument('--task', required=True, help='task-id')
    done.add_argument('--drop-branch', action='store_true',
                      help='tip SHA 기록 후 브랜치 삭제(기본 보존)')
    done.add_argument('--no-salvage', action='store_true',
                      help='미커밋분 폐기를 각오한 명시 옵션(폐기 수 기록 — done 전용)')
    add_save(done)

    listing = sub.add_parser('list', help='worktree·레지스트리·phase 대조 보고')
    listing.add_argument('--du', action='store_true',
                         help='du -sb 경로별 bytes(GNU 전용 — 실패 시 null)')
    add_save(listing)

    sweep = sub.add_parser('sweep', help='eligible(done·고아) worktree 일괄 done')
    sweep.add_argument('--dry-run', action='store_true',
                       help='보고만(무변경)')
    sweep.add_argument('--unmanaged', action='store_true',
                       help='미관리 worktree도 salvage(salvage/unmanaged-*) 후 제거'
                            '(기본 off — 자동 제거 금지)')
    sweep.add_argument('--drop-branch', action='store_true',
                       help='sweep 대상(managed wt/<task-id>) 브랜치도 tip SHA 기록 '
                            '후 삭제 — 미관리 원본 브랜치는 삭제하지 않는다')
    add_save(sweep)
    return parser.parse_args(argv)


def save_result(save_dir: str, result: dict[str, Any]) -> tuple[str | None, str | None]:
    """결과 JSON 저장 — (경로, None) 또는 (None, 사유). r23 계약 평행."""
    try:
        directory = Path(save_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{GATE}-{lib.utc_stamp()}.json'
        payload = {**result, 'saved_to': str(path)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    except OSError as error:
        return None, str(error)
    return str(path), None


def emit(result: dict[str, Any], save_dir: str | None) -> None:
    if save_dir is not None:
        saved, save_error = save_result(save_dir, result)
        if saved is None:
            print(json.dumps(result, ensure_ascii=False))
            lib.fail_config(
                f'--save 실패 — 검사 결과는 위 stdout JSON에 보존됐다: {save_error}')
        result = {**result, 'saved_to': saved}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(EXIT_ATTENTION if result['flags'] else EXIT_PASS)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        repo = lib.resolve_main_repo()
        if args.subcommand == 'create':
            result = cmd_create(repo, args)
        elif args.subcommand == 'done':
            result = execute_done(repo, lib.validate_task(args.task),
                                  args.drop_branch, args.no_salvage)
        elif args.subcommand == 'list':
            result = cmd_list(repo, args)
        else:
            result = cmd_sweep(repo, args)
    except GateConfigError as error:
        lib.fail_config(str(error))
    emit(result, args.save)


if __name__ == '__main__':
    main()
