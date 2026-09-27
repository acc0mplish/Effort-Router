#!/usr/bin/env python3
"""r27 트리 소유 게이트 SessionStart 훅 — 세션 시작 시 타 세션 claim 경고(선택 어댑터).

게이트 본체(scripts/tree_gate.py)는 하니스 무관 subprocess CLI이고 본 훅은 이
저장소의 Claude Code SessionStart 어댑터다. stdin JSON의 session_id로
`tree_gate.py check --session <id>`를 실행해 foreign claim 존재 시
additionalContext로 경고를 띄운다(상대 session_id·scope·alive 근거 포함).
결정론 — jev·TYPESAFE_API_KEY 무의존(tree_gate subprocess만 호출).
폴백 계약: 게이트 부재·비저장소·subprocess 오류·timeout 시 무작동·무경고(bypass,
never an error — jev 후크 폴백 계약 준용). 경고만 하며 세션 시작을 차단하지
않는다 — 훅 exit code는 항상 0이고 판정 권한은 메인 세션에 있다(읽기전용 전환
또는 신규 worktree 스폰).
"""
import json
import os
import subprocess
import sys

CHECK_TIMEOUT_S = 4  # settings.json 훅 timeout 5초 — 본체 여유


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
    return "\n".join(lines)


def main():
    session_id = read_stdin().get("session_id")
    if not session_id:
        return  # 무작동 — 출력 없음
    result, warn = run_check(session_id)
    if not warn or not result:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": warning_context(result)}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 폴백 계약 — never an error
    sys.exit(0)
