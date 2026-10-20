#!/usr/bin/env python3
"""jev intake 모드 정의 모듈 — ② 옵션 엔진(6항목 Noul fan-out).

인테이크 계층의 jev 옵션 엔진이다(SKILL.md §0 — 기본은 ① intake_gate, ②는 메인 명시
선택 시만). 질문 상수·입력 파싱·recommendation 합성만 담당하고 네트워크 호출이 없으며,
API 호출·응답 검증·감사는 jev_judge.py 기존 파이프라인을 그대로 경유한다(확장 모드 3종과
동일 구조). 의존 방향은 jev_judge → jev_intake → intake_gate 단방향으로, action·계산
규칙·감지기는 intake_gate 공유 함수를 import한다(①② 정합 단일 소스 — 순환 없음).

noul ≥ 0.6 = 항목 충족 — 임계 판정은 build_recommendation의 noul_confirmed 인자로
주입받는다(jev_modes 관례 평행 — 임계 상수 2곳화 금지, 기존 채택 판정 모드 단일 임계
승계). 항목 판정 기준 문구는 intake_gate.ITEM_DESCRIPTIONS와 바이트 수준 동일 관리된다.
원문 보존 계약: utterance는 어디에서도 재작성되지 않고 recommendation에 그대로 실린다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from intake_gate import (ITEM_DESCRIPTIONS, ITEM_KEYS, build_note, compute_action,
                         detect_loop_verb, detect_pronoun)


def parse_input(statement: str, context: str | None = None, *,
                task_active: bool = False, urgent: bool = False,
                source: str = 'user',
                stdin_text: Callable[[], str] | None = None) -> dict[str, Any]:
    """intake 모드 입력 파싱 — 발화·맥락·플래그를 mode_input으로 묶는다.

    context는 맥락 요약 원문(인자)·파일경로·stdin('-')을 받는다(①와 대칭 — L2).
    state는 발화+맥락을 합성해 기존 jev 파이프라인의 질문 판정 대상이 된다 — 발화 원문
    utterance는 합성과 무관하게 그대로 보존된다(원문 보존 계약).
    """
    read = stdin_text or (lambda: sys.stdin.read())
    utterance = read() if statement == '-' else statement
    context_text = ''
    if context is not None:
        if context == '-':
            context_text = read()
        else:
            path = Path(context)
            if path.is_file():
                try:
                    context_text = path.read_text(encoding='utf-8')
                except (OSError, UnicodeDecodeError) as error:
                    # jev 어휘 폴백(exit 1) — 호출 엔진 fail()과 동일 형태(④리뷰 N2).
                    print(f'FAIL jev judge: context file read failed: {error}',
                          file=sys.stderr)
                    raise SystemExit(1)
            else:
                context_text = context
    state = utterance if not context_text else f'{utterance}\n\n[맥락]\n{context_text}'
    return {'state': state, 'utterance': utterance, 'context': context_text,
            'task_active': task_active, 'urgent': urgent, 'source': source}


def build_questions(state: str) -> dict[str, Any]:
    """6항목 noul 질문 맵 — 항목 정의 문구는 intake_gate와 바이트 수준 동일 관리."""
    return {key: {'type': 'noul',
                  'instructions': (f'다음 진술이 해당하면 true, 아니면 false로 판단한다: '
                                   f'{ITEM_DESCRIPTIONS[key]}'),
                  'criteria': {'true': '해당한다', 'false': '해당하지 않는다'}}
            for key in ITEM_KEYS}


def build_recommendation(mode_input: dict[str, Any], answers: dict[str, Any],
                         noul_confirmed: Callable[[float], bool]) -> dict[str, Any]:
    """recommendation 합성 — ① 필드 세트(gate 포함)를 내부에 중첩해 반환한다(H2).

    noul_confirmed(≥0.6 주입)로 항목별 충족을 판정하고, 규칙 A·B·규칙 0은 intake_gate
    공유 함수로 ① 엔진과 동일하게 적용한다. ok·saved_to는 호출 엔진(jev_judge)이 채운다.
    """
    utterance = mode_input['utterance']
    items = {key: ('present' if noul_confirmed(answers[key]['noul']) else 'missing')
             for key in ITEM_KEYS}
    context_dep = detect_pronoun(utterance)
    if context_dep:                              # 규칙 A — 전항목 충족 간주(§3.3)
        items = {key: ('context_satisfied' if status == 'missing' else status)
                 for key, status in items.items()}
    action, questions_max = compute_action(
        items, context_dep, mode_input['task_active'], mode_input['urgent'],
        detect_loop_verb(utterance))
    missing_count = sum(1 for status in items.values() if status == 'missing')
    recommendation = {'gate': 'intake', 'mode': 'jev', 'source': mode_input['source'],
                      'items': items, 'missing_count': missing_count,
                      'ambiguity_score': missing_count / len(ITEM_KEYS),
                      'action': action, 'questions_max': questions_max,
                      'context_dep': context_dep, 'task_active': mode_input['task_active'],
                      'urgent': mode_input['urgent'], 'utterance': utterance}
    note = build_note(items, action, context_dep)   # ①② 표기 정합(④리뷰 N1)
    if note is not None:
        recommendation['note'] = note
    return recommendation
