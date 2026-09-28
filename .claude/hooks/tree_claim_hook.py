#!/usr/bin/env python3
"""r27 트리 소유 게이트 SessionStart 훅 + r28 격리 가드 PreToolUse 훅(선택 어댑터).

게이트 본체(scripts/tree_gate.py)는 하니스 무관 subprocess CLI이고 본 훅은 이
저장소의 Claude Code 어댑터다(서브커맨드 확장 — jev_hooks 단일 파일 패턴 준용).
argv 무인자·`start` = SessionStart 어댑터(r27 로직 보존): stdin JSON의 session_id로
`tree_gate.py check --session <id>`를 실행해 foreign claim 존재 시
additionalContext로 경고를 띄운다(상대 session_id·scope·alive 근거 포함).
argv `prebash` = PreToolUse(Bash) 격리 가드(r28): git 쓰기 서브커맨드 감지 시
check를 캐시(TMPDIR·TTL 60초)와 함께 재실행해 신규 침입자를 경고하고, foreign
claim 존재 시 전체 스테이징 패턴(add -A/-u/./commit -a)을 deny로 차단한다.
결정론 — jev·TYPESAFE_API_KEY 무의존(tree_gate subprocess만 호출).
폴백 계약: 게이트 부재·비저장소·subprocess 오류·timeout·stdin 파싱 실패 시
무작동·무출력(bypass, never an error — jev 후크 폴백 계약 준용). 경고·deny 모두
훅 exit code는 항상 0이고 판정 권한은 메인 세션에 있다(읽기전용 전환 또는 신규
worktree 스폰). 오프 스위치: env `TREE_GATE_HOOKS=0`이면 prebash 전체 무작동.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

CHECK_TIMEOUT_S = 4  # settings.json 훅 timeout 5초 — 본체 여유

# --- r28 prebash 상수 ---------------------------------------------------------
CACHE_DIRNAME = 'effort-router-tree-gate-hook'
CACHE_VERSION = 1
DEFAULT_CACHE_TTL_S = 60  # 원문 "예: 60초" — TREE_GATE_HOOK_CACHE_TTL_S env로 폴백
SESSION_SANITIZE_RE = re.compile(r'[^A-Za-z0-9._-]')  # tree_gate SESSION_SANITIZE_RE 준용
# 레벨 1 쓰기 서브커맨드(§4.2 — branch·tag 포함 보수. status·log 등 read-only 제외)
GIT_WRITE_SUBCOMMANDS = frozenset((
    'add', 'commit', 'rm', 'mv', 'checkout', 'switch', 'restore', 'stash',
    'reset', 'rebase', 'merge', 'cherry-pick', 'revert', 'clean', 'push',
    'pull', 'tag', 'apply', 'am', 'worktree', 'branch', 'submodule',
    'sparse-checkout'))
# 단독형(인자 1개 소비) 글로벌 옵션 — 이 트리 귀속 불확실(§4.2 — deny 제외·트리거 유효)
TREE_UNCERTAIN_GLOBAL_OPTS = frozenset(
    ('-C', '--git-dir', '--work-tree', '--namespace'))
CONSUMING_GLOBAL_OPTS = frozenset(('-c',))  # 소비형 스킵 잔류 목록
FLAG_GLOBAL_OPTS = frozenset(('-p', '--paginate', '--no-pager', '--no-optional-locks',
                              '--literal-pathspecs', '--no-replace-objects'))
GIT_FALLBACK_RE = re.compile(
    r'(?:^|\s)git\s+(?:' + '|'.join(
        re.escape(s) for s in sorted(GIT_WRITE_SUBCOMMANDS, key=len,
                                     reverse=True)) + r')\b')
COMMIT_VALUE_SHORTS = ('m', 'F', 'C', 'c')  # commit 인자 소비 옵션 — 값 1개 스킵


def read_stdin():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def run_check(session_id):
    """tree_gate check 실행 — (stdout JSON, warning 여부). 오류 시 (None, False)."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    gate = os.path.join(root, "scripts", "tree_gate.py") if root else None
    if not gate or not os.path.isfile(gate):
        return None, False  # 게이트 부재 — 무작동
    try:
        proc = subprocess.run(
            [sys.executable, gate, "check", "--session", str(session_id)],
            capture_output=True, text=True, timeout=CHECK_TIMEOUT_S)
    except Exception:
        return None, False  # subprocess 오류·timeout — 무작동
    if proc.returncode != 1:
        return None, False  # 0(간섭 없음)·2(오류) 모두 무경고
    try:
        return json.loads(proc.stdout), True
    except ValueError:
        return None, False


def warning_context(result):
    lines = ["[tree-gate] 이 트리에 살아있는 타 세션 claim이 있다 — 쓰기 전 확인 의무:"]
    for claim in result.get("foreign_claims") or []:
        lines.append(
            f"- session {claim.get('session_id')} scope={claim.get('scope')} "
            f"claimed={claim.get('claimed_utc')} alive={claim.get('alive_reason')}")
    for name in result.get("corrupt") or []:
        lines.append(f"- (파손 claim — 판단 보류) {name}")
    lines.append("판정 권한은 메인 — 읽기전용 전환 또는 신규 worktree 스폰.")
    lines.append("격리 안내: python3 scripts/worktree_gate.py create --task <task-id> "
                 "(r24 워크트리 게이트 — 호출 주체는 메인 세션 단일)")
    return "\n".join(lines)


# ---------------------------------------------------------------- r28 prebash

def cache_ttl_s():
    """TTL 판정 — TREE_GATE_HOOK_CACHE_TTL_S env 폴백. 무효값(비수·비양수)은
    기본 60으로 폴백한다(오류 아님 — §4.4)."""
    raw = os.environ.get('TREE_GATE_HOOK_CACHE_TTL_S')
    if raw is None:
        return DEFAULT_CACHE_TTL_S
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_CACHE_TTL_S
    if value <= 0:
        return DEFAULT_CACHE_TTL_S
    return value


def cache_path(session_id):
    sanitized = SESSION_SANITIZE_RE.sub('_', session_id)[:64]
    return os.path.join(tempfile.gettempdir(), CACHE_DIRNAME, f'{sanitized}.json')


def load_cache(path, session_id):
    """캐시 판독 — 부재·파손·버전 불일치·세션 불일치는 None(무효 → 재기록 대상)."""
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get('version') != CACHE_VERSION:
        return None
    if data.get('session_id') != session_id:
        return None
    if not isinstance(data.get('last_check_epoch'), (int, float)):
        return None
    return data


def write_cache(path, session_id, verdict):
    """원자 캐시 기록(temp+os.replace — tree_gate 기법 준용). returncode 0·1 유효
    판정 시에만 호출된다. 실패는 무시(캐시 부재 = 다음 만료 재판정 — 폴백 계약)."""
    record = {
        'version': CACHE_VERSION,
        'session_id': session_id,
        'last_check_epoch': time.time(),
        'foreign': bool(verdict.get('foreign_claims')),
        'foreign_sessions': [claim.get('session_id')
                             for claim in verdict.get('foreign_claims') or []],
        'corrupt_seen': list(verdict.get('corrupt') or []),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f'{path}.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass  # 캐시 실패는 무작동 — 판정·출력에는 영향 없다


def run_check_full(session_id):
    """tree_gate check — returncode 0·1은 모두 유효 판정 완료(stdout JSON 반환,
    §4.2 3단계). 2·subprocess 오류·timeout·JSON 파싱 실패는 None(판정 불능 bypass)."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    gate = os.path.join(root, "scripts", "tree_gate.py") if root else None
    if not gate or not os.path.isfile(gate):
        return None  # 게이트 부재 — 무작동
    try:
        proc = subprocess.run(
            [sys.executable, gate, "check", "--session", str(session_id)],
            capture_output=True, text=True, timeout=CHECK_TIMEOUT_S)
    except Exception:
        return None  # subprocess 오류·timeout — 무작동
    if proc.returncode not in (0, 1):
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def split_segments(command):
    """셸 제어 연산자(`&&`·`||`·`;`·`|`·개행) 분할 — quote·불투명 영역 상태 추적
    (§4.2). 작은·큰따옴표 내부 제어 연산자는 분할 기준 제외(위조 세그먼트 봉쇄),
    `$()`·백틱 치환·히어독 본문(`<<`·`<<-` 종결자 라인까지)·히어스트링(`<<<`)은
    불투명 통과(미닫힘·종결자 미발견 시 이후 전체 단일 세그먼트).
    반환: [(세그먼트, 괄호 그룹 혼입 여부)] — bare `(`·`)` 세그먼트는 판정 제외(R6)."""
    segments = []
    current = []
    current_has_paren = False
    has_paren_flags = []
    index = 0
    end = len(command)
    quote = None
    unbalanced = False
    pending_heredoc = None  # (종결자 워드, <<- 여부) — 다음 개행부터 본문 불투명
    while index < end:
        ch = command[index]
        if unbalanced:
            current.append(ch)  # 미닫힌 치환 이후 — 단일 세그먼트로 흡수
            index += 1
            continue
        if pending_heredoc and ch == '\n':
            word, dash = pending_heredoc
            pending_heredoc = None
            pos = index + 1
            body_end = -1
            while pos <= end:
                nl = command.find('\n', pos)
                line = command[pos:nl if nl != -1 else end]
                if (line.lstrip('\t') if dash else line) == word:
                    body_end = end if nl == -1 else nl + 1
                    break
                if nl == -1:
                    break
                pos = nl + 1
            if body_end == -1:
                unbalanced = True  # 종결자 라인 미발견 — 이후 전체 불투명
                current.append(command[index:])
                index = end
                continue
            current.append(command[index:body_end])  # 본문~종결자 라인 불투명 통과
            index = body_end
            continue
        if quote:
            current.append(ch)
            if quote == '"' and ch == '\\' and index + 1 < end:
                current.append(command[index + 1])
                index += 2
                continue
            if ch == quote:
                quote = None
            index += 1
            continue
        if ch in ('\'', '"'):
            quote = ch
            current.append(ch)
            index += 1
            continue
        if ch == '\\' and index + 1 < end:
            current.append(ch)
            current.append(command[index + 1])
            index += 2
            continue
        if command.startswith('$(', index):
            depth = 1
            current.append('$(')
            index += 2
            inner_quote = None
            while index < end and depth > 0:
                inner = command[index]
                if inner_quote:
                    if inner == '\\' and index + 1 < end:
                        current.append(command[index + 1])
                        index += 2
                        continue
                    if inner == inner_quote:
                        inner_quote = None
                    current.append(inner)
                    index += 1
                    continue
                if inner in ('\'', '"'):
                    inner_quote = inner
                    current.append(inner)
                    index += 1
                    continue
                if command.startswith('$(', index):
                    depth += 1
                    current.append('$(')
                    index += 2
                    continue
                if inner == ')':
                    depth -= 1
                    current.append(inner)
                    index += 1
                    continue
                current.append(inner)
                index += 1
            if depth > 0:
                unbalanced = True  # 미닫힘·불균형 — 이후 전체 단일 세그먼트
            continue
        if ch == '`':
            close = command.find('`', index + 1)
            if close == -1:
                unbalanced = True
                current.append(command[index:])
                index = end
            else:
                current.append(command[index:close + 1])
                index = close + 1
            continue
        if command.startswith('<<<', index):
            nl = command.find('\n', index)
            stop = end if nl == -1 else nl
            current.append(command[index:stop])  # 히어스트링 워드 — 개행은 분할 유지
            index = stop
            continue
        if command.startswith('<<', index):
            dash = command.startswith('<<-', index)
            j = index + (3 if dash else 2)
            while j < end and command[j] in ' \t':
                j += 1
            word_start = j
            while j < end and command[j] not in ' \t\n;&|':
                j += 1
            word = command[word_start:j]
            if len(word) >= 2 and word[0] == word[-1] and word[0] in ('\'', '"'):
                word = word[1:-1]  # 인용 종결자 — 벗겨낸 워드가 라인 종결자다
            current.append(command[index:j])  # 오퍼레이터+워드는 세그먼트 본문
            index = j
            if word:
                pending_heredoc = (word, dash)  # 본문은 다음 개행 뒤에 온다
            continue
        if command[index:index + 2] in ('&&', '||'):
            segments.append(''.join(current))
            has_paren_flags.append(current_has_paren)
            current = []
            current_has_paren = False
            index += 2
            continue
        if ch in (';', '|', '\n'):
            segments.append(''.join(current))
            has_paren_flags.append(current_has_paren)
            current = []
            current_has_paren = False
            index += 1
            continue
        if ch in ('(', ')'):
            current_has_paren = True  # 괄호 그룹 — 판정 제외 대상 표식
        current.append(ch)
        index += 1
    segments.append(''.join(current))
    has_paren_flags.append(current_has_paren)
    return list(zip(segments, has_paren_flags))


def classify_segment(segment):
    """세그먼트 shlex 판정 — dict(trigger·eligible·sub·rest). shlex 실패는 None
    (레벨 2 제외 — 파싱 불확실엔 차단하지 않는다). eligible=False는 git 명령 위치
    트리 귀속 불확실(-C계열) 세그먼트 — 서브커맨드 판정(deny)에서 제외한다(§4.2)."""
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return None
    index = 0
    while index < len(tokens) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', tokens[index]):
        index += 1  # 환경변수 할당(X=y) 접두 건너뜀
    if index >= len(tokens) or tokens[index] != 'git':
        return {'trigger': False, 'eligible': False, 'sub': None, 'rest': []}
    index += 1
    uncertain = False
    while index < len(tokens):
        token = tokens[index]
        uncertain_opt = next(
            (opt for opt in TREE_UNCERTAIN_GLOBAL_OPTS if token.startswith(opt)),
            None)
        if uncertain_opt is not None:
            uncertain = True  # 결합형(-C../x·--git-dir=../x)도 귀속 불확실(D2)
            index += 2 if token == uncertain_opt else 1  # 단독형만 인자 1개 소비
            continue
        if token in CONSUMING_GLOBAL_OPTS:
            index += 2
            continue
        if token in FLAG_GLOBAL_OPTS or (token.startswith('--') and '=' in token):
            index += 1  # 플래그형·`=` 결합형 — 스킵
            continue
        if token.startswith('-') and len(token) > 1:
            index += 1  # 미상 단축 글로벌 플래그 — 무값 취급
            continue
        sub = token if token in GIT_WRITE_SUBCOMMANDS else None
        return {'trigger': sub is not None,
                'eligible': sub is not None and not uncertain,
                'sub': sub, 'rest': tokens[index + 1:]}
    return {'trigger': False, 'eligible': False, 'sub': None, 'rest': []}


def whole_staging_deny(sub, rest):
    """전체 스테이징 판정(§4.3 요건 3) — shlex 성공 세그먼트에만 호출된다.
    add: -A/--all/-u/--update(묶음 분해 포함) ∧ pathspec 없음, 또는 pathspec 중
    `.`·`./` 존재. commit: -a/--all ∧ 커밋 대상 pathspec 없음(-m·-F·-C·-c는 값
    1개 스킵 — 값 결합 문자(-ma의 a)는 플래그 아님). `--` 종결자 이후는 전부
    pathspec. dry-run(--dry-run·add -n)은 실행 안 되는 명령으로 deny 제외(D4)."""
    pathspecs = []
    all_flag = False
    dry_run = False
    after_terminator = False
    index = 0
    count = len(rest)
    while index < count:
        token = rest[index]
        if after_terminator:
            pathspecs.append(token)
            index += 1
            continue
        if token == '--':
            after_terminator = True
            index += 1
            continue
        if token.startswith('--'):
            if token == '--dry-run':
                dry_run = True
            if sub == 'add' and token in ('--all', '--update'):
                all_flag = True
            if sub == 'commit' and token == '--all':
                all_flag = True
            index += 1  # 롱폼 — 묶음 분해 대상 아님(--amend 등)
            continue
        if token.startswith('-') and len(token) > 1:
            chars = token[1:]
            if sub == 'add':
                all_flag = all_flag or 'A' in chars or 'u' in chars
                dry_run = dry_run or 'n' in chars  # add -n == --dry-run
                index += 1
                continue
            if sub == 'commit':
                consumed_next = False
                for position, char in enumerate(chars):
                    if char in COMMIT_VALUE_SHORTS:
                        # 값 소비 옵션 발견 — 이후 문자는 결합값(-ma의 a, D3)
                        consumed_next = position == len(chars) - 1
                        break
                    if char == 'a':
                        all_flag = True
                index += 2 if consumed_next else 1
                continue
        pathspecs.append(token)  # 비옵션 위치 인자 = pathspec
        index += 1
    if dry_run:
        return False  # 실행 안 되는 명령(D4)
    if sub == 'add':
        real_pathspec = [p for p in pathspecs if p not in ('.', './')]
        return (all_flag and not real_pathspec) or any(p in ('.', './')
                                                       for p in pathspecs)
    if sub == 'commit':
        return all_flag and not pathspecs
    return False


def claim_line(claim):
    return (f"- session {claim.get('session_id')} scope={claim.get('scope')} "
            f"claimed={claim.get('claimed_utc')} alive={claim.get('alive_reason')}")


def intrusion_warning(new_claims, new_corrupt):
    """신규 침입자·corrupt 신규 등장 통보 문안(§4.2 원문 골격) — 둘 다 없으면 None."""
    lines = []
    if new_claims:
        lines.append('[tree-gate] 진행 중 재점검 — 신규 타 세션 claim이 감지되었다'
                     ' — 쓰기 전 확인 의무:')
        lines.extend(claim_line(claim) for claim in new_claims)
        lines.append('판정 권한은 메인 — 읽기전용 전환 또는 신규 worktree 스폰. '
                     '격리가 필요하면: python3 scripts/worktree_gate.py create '
                     '--task <task-id> (r24 — 호출 주체는 메인 세션)')
    if new_corrupt:
        lines.append('[tree-gate] 진행 중 재점검 — 파손 claim 파일이 존재한다'
                     '(판단 보류):')
        lines.extend(f'- (파손 claim — 판단 보류) {name}' for name in new_corrupt)
    return '\n'.join(lines) if lines else None


def deny_reason(foreign_sessions, new_claims, new_corrupt):
    """deny 사유(§4.3 스키마 전문) — 신규 침입자·corrupt 줄을 말미에 병합한다
    (경고·deny 동시 성립 시 이 객체가 유일한 출력 — 2개 JSON 객체 emit 금지)."""
    reason = (
        '[tree-gate] 커밋 오염 방어 — 이 트리에 살아있는 타 세션 claim이 있다('
        + ', '.join(foreign_sessions) + '). 전체 스테이징(add -A/-u/./commit -a)은 '
        '타 세션의 변경을 흡수한다. pathspec 지정 커밋으로 변경하라(git add <경로>… / '
        'git commit -- <경로>…). 격리가 필요하면: python3 scripts/worktree_gate.py '
        'create --task <task-id> (r24 — 호출 주체는 메인 세션). 상대 claim이 유령'
        '(세션 종료)으로 보이면 tree_gate.py status 확인 후 레지스트리 파일 수동 삭제'
        ' — prune은 alive 불가침.')
    merged = [claim_line(claim) for claim in new_claims]
    merged.extend(f'- (파손 claim — 판단 보류) {name}' for name in new_corrupt)
    if merged:
        reason += '\n' + '\n'.join(merged)
    return reason


def cmd_prebash():
    data = read_stdin()
    session_id = data.get('session_id')
    command = (data.get('tool_input') or {}).get('command') or ''
    if not session_id or not command:
        return  # stdin 파싱 실패 — 무작동 exit 0
    if os.environ.get('TREE_GATE_HOOKS') == '0':
        return  # 오프 스위치 — prebash 전체 무작동(§4.1)
    classifications = []
    fallback_trigger = False
    for segment, group_ambiguous in split_segments(command):
        if group_ambiguous:
            continue  # 괄호 그룹·불균형 — 판정 제외(R6)
        info = classify_segment(segment)
        if info is None:
            # shlex 실패 — 정규식 폴백은 레벨 1(재점검 트리거)만(§4.2)
            fallback_trigger = fallback_trigger or bool(GIT_FALLBACK_RE.search(segment))
            continue
        classifications.append(info)
    if not fallback_trigger and not any(info['trigger'] for info in classifications):
        return  # 레벨 1 미발화 — read-only·비git 무간섭(캐시도 건드리지 않는다)
    path = cache_path(session_id)
    cached = load_cache(path, session_id)
    fresh = None
    if cached is None or time.time() - cached['last_check_epoch'] > cache_ttl_s():
        fresh = run_check_full(session_id)
        if fresh is None:
            return  # 판정 불능(returncode 2·오류·timeout·파싱 실패) — bypass 무출력
        write_cache(path, session_id, fresh)
    if fresh is not None:
        foreign_claims = fresh.get('foreign_claims') or []
        foreign_sessions = [claim.get('session_id') for claim in foreign_claims]
        baseline_sessions = cached.get('foreign_sessions') if cached else None
        new_claims = ([claim for claim in foreign_claims
                       if claim.get('session_id') not in set(baseline_sessions)]
                      if baseline_sessions is not None else [])  # 첫 캐시 — 기록만
        baseline_corrupt = set(cached.get('corrupt_seen') or []) if cached else set()
        new_corrupt = [name for name in fresh.get('corrupt') or []
                       if name not in baseline_corrupt]
    else:
        foreign_sessions = list(cached.get('foreign_sessions') or [])
        new_claims = []  # 캐시 히트 — 신규 판정 불가(다음 만료 재점검이 포착)
        new_corrupt = []
    deny_hit = any(
        info['eligible'] and info['sub'] in ('add', 'commit')
        and whole_staging_deny(info['sub'], info['rest'])
        for info in classifications)
    if foreign_sessions and deny_hit:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': deny_reason(
                foreign_sessions, new_claims, new_corrupt)}}, ensure_ascii=False))
        return  # deny 단독 — additionalContext 병존 emit 없음(§4.3)
    warning = intrusion_warning(new_claims, new_corrupt)
    if warning:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'additionalContext': warning}}, ensure_ascii=False))


def run_start():
    """r27 SessionStart 로직 — 무인자·`start`·알 수 없는 argv 호출(계약 보존)."""
    session_id = read_stdin().get("session_id")
    if not session_id:
        return  # 무작동 — 출력 없음
    result, warn = run_check(session_id)
    if not warn or not result:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": warning_context(result)}}, ensure_ascii=False))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'prebash':
        cmd_prebash()
        return
    run_start()  # 폴백 — never an error


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 폴백 계약 — never an error
    sys.exit(0)
