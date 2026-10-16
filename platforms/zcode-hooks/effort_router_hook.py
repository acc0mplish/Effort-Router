#!/usr/bin/env python3
"""effort-router 기계적 발동 훅 (ZCode 사용자 스코프) — platforms/zcode.md 어댑터.

관측 실패(2026-10-17): ZCode에는 자동 발동 트리거가 없어 모델 재량에만 의존하다
이어하기 세션에서 라우터 계약이 한 번도 출력되지 않았음. 이 훅은 매 세션 시작과
매 사용자 발화에 계약 리마인더를 기계적으로 주입한다.

관측 실패(2026-10-17, 2차): ZCode 훅 러너(zcode.cjs kma)는 '{'로 시작하지 않는
stdout을 조용히 폐기한다 — 평문 출력은 exit 0으로 성공 기록되지만 아무것도
주입되지 않는다. 주입은 hookSpecificOutput.additionalContext JSON 랩으로만 성립한다.

계약: 상시 exit 0 (절대 차단하지 않는다 — jev/트리 게이트 폴백 계약 준용),
표준 라이브러리만 사용, 키 무의존(결정론), 활성 스위치 EFFORT_ROUTER_HOOKS=0.
- session (SessionStart): 세션 컨텍스트로 전체 발동 규칙 블록 주입
- prompt  (UserPromptSubmit): 매 발화 1줄 리마인더 주입 (컨텍스트 압축에도 살음)

배포원: Effort-Router 저장소 platforms/zcode-hooks/effort_router_hook.py —
`cp platforms/zcode-hooks/effort_router_hook.py ~/.zcode/hooks/` 후
~/.zcode/cli/config.json의 hooks 항목에 절대경로로 등록한다.
"""
import json
import os
import sys

SESSION_BLOCK = """[effort-router 발동 규칙 — 기계적 주입]
이 세션에는 전역 effort-router 규칙이 적용된다: 코딩 작업 착수 전(계획·구현·리뷰·감사 각각) 티어 판정(S/M/L/XL·보안감사)과 Output Contract를 먼저 출력한다. ZCode 적용 계약(platforms/zcode.md): 스폰은 ~/.zcode/agents/*.md 역할 정의를 subagent_type으로 사용하되 라우팅 테이블 내 역할만 호출한다(존재 ≠ 허가), 심층 스폰 동시 상한 1, 증거기반 보고(실행 명령 원문+exit code). 이어하기/압축 세션에서도 이 규칙은 유효하다."""

PROMPT_LINE = "[effort-router] 신규 코딩 과제 착수 발화면 구현 전에 [Effort Router] 계약(티어 판정·적용 에이전트·팬아웃 라인)을 먼저 출력한다 — 단순 질문·이어하기는 생략."


def emit(event_name: str, text: str) -> None:
    # 평문 print는 러너가 폐기한다(kma 파서) — additionalContext JSON 랩이 계약.
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}, ensure_ascii=False))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if os.environ.get("EFFORT_ROUTER_HOOKS", "1") != "1":
        return 0
    if mode == "session":
        emit("SessionStart", SESSION_BLOCK)
    elif mode == "prompt":
        # stdin(JSON)은 읽지 않는다 — 발화 내용과 무관하게 상시 주입이 계약이다.
        try:
            sys.stdin.read()
        except Exception:
            pass
        emit("UserPromptSubmit", PROMPT_LINE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
