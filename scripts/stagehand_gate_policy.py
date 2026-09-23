#!/usr/bin/env python3
"""r18 Stagehand 게이트 정책 — 순수 판정 계층(I/O 없음, 전 함수 불변 반환).

jev recommendation 소비 계약(plan.md §4.5):
- `ok is True` + recommendation.<verified|done_confirmed> 불리언만 소비
- noul 값은 기록용(last_noul) 수집 — 임계(≥0.6·dead zone 0.4~0.6) 재해석 금지(보존 제약 4)
- jev 판단 불능은 JevViolationError로 보고하고 게이트가 에스컬레이션(exit 3)한다
"""
from __future__ import annotations

import json
from typing import Any

BOOL_FIELD = {'verify-run': 'verified', 'done': 'done_confirmed'}
ACTIONS = ('act', 'observe', 'extract')
MAX_STEPS = 50


class TaskValidationError(ValueError):
    """태스크 스키마 위반 — 위반 사유 전량을 errors 목록으로 보유한다(§4.4)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__('; '.join(self.errors))


class JevViolationError(ValueError):
    """jev 판정 결과 위반 — exit 3 에스컬레이션 조건이다(§4.3)."""


def validate_task(data: Any) -> dict[str, Any]:
    """태스크 파일 스키마 검증 — 위반 사유를 전량 나열해 TaskValidationError로 보고한다.

    반환값은 정규화된 신규 딕셔너리다(입력 수정 없음).
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        raise TaskValidationError(['태스크 파일이 JSON 객체가 아니다'])
    task_id = data.get('task_id')
    if not isinstance(task_id, str) or not task_id:
        errors.append("task_id는 비빈 문자열이어야 한다")
    url = data.get('url')
    if not isinstance(url, str) or not (url.startswith('http://')
                                        or url.startswith('https://')):
        errors.append("url은 http/https URL 문자열이어야 한다")
    steps = _validate_steps(data.get('steps'), errors)
    criteria = data.get('success_criteria')
    if not isinstance(criteria, str) or not criteria:
        errors.append('success_criteria는 비빈 문자열이어야 한다')
    if errors:
        raise TaskValidationError(errors)
    return {'task_id': task_id, 'url': url, 'steps': steps, 'success_criteria': criteria}


def _validate_steps(value: Any, errors: list[str]) -> tuple[dict[str, Any], ...]:
    steps = value
    if not isinstance(steps, list) or not (1 <= len(steps) <= MAX_STEPS):
        errors.append(f'steps는 1~{MAX_STEPS}개의 목록이어야 한다')
        return ()
    normalized: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        problems = _step_problems(step)
        if problems:
            errors.append(f'steps[{index}]: {", ".join(problems)}')
            continue
        normalized.append({'action': step['action'], 'instruction': step['instruction'],
                           'target': step.get('target')})
    return tuple(normalized)


def _step_problems(step: Any) -> list[str]:
    if not isinstance(step, dict):
        return ['객체가 아니다']
    problems: list[str] = []
    if step.get('action') not in ACTIONS:
        problems.append(f"action은 {'|'.join(ACTIONS)} 중 하나여야 한다")
    instruction = step.get('instruction')
    if not isinstance(instruction, str) or not instruction:
        problems.append('instruction은 비빈 문자열이어야 한다')
    target = step.get('target')
    if target is not None and not isinstance(target, str):
        problems.append('target은 문자열이어야 한다')
    return problems


def consume_recommendation(mode: str, parsed: Any) -> dict[str, Any]:
    """jev stdout 파싱 결과에서 불리언만 소비한다 — 위반은 JevViolationError.

    noul은 기록용으로만 수집하고 임계 재해석은 하지 않는다(보존 제약 4).
    """
    field = BOOL_FIELD[mode]
    if not isinstance(parsed, dict):
        raise JevViolationError('jev stdout이 JSON 객체가 아니다')
    if parsed.get('ok') is not True:
        raise JevViolationError('jev 응답 ok가 true가 아니다')
    recommendation = parsed.get('recommendation')
    if not isinstance(recommendation, dict):
        raise JevViolationError('jev 응답에 recommendation 객체가 없다')
    confirmed = recommendation.get(field)
    if not isinstance(confirmed, bool):
        raise JevViolationError(f'recommendation.{field} 불리언이 없다')
    noul = recommendation.get('noul')
    if isinstance(noul, bool) or not isinstance(noul, (int, float)):
        noul = None
    return {'confirmed': confirmed, 'noul': noul}


def gate_decision(confirmed: bool, attempts_used: int, max_attempts: int) -> str:
    """게이트 결정 — pass / retry / retry-exhausted(총 시도 상한 = 1 + max_retries)."""
    if confirmed:
        return 'pass'
    if attempts_used < max_attempts:
        return 'retry'
    return 'retry-exhausted'


def build_statement(spec: dict[str, Any], attempt: int, max_attempts: int,
                    runner_kind: str, outcome: dict[str, Any]) -> str:
    """시도 기록을 jev statement로 직렬화한다(§4.6 — 필드 최소 계약)."""
    header = (f"[stagehand-gate] task_id={spec['task_id']} attempt={attempt}/{max_attempts} "
              f"runner={runner_kind}")
    return '\n'.join((header,
                      f"url={spec['url']}",
                      f"success_criteria={spec['success_criteria']}",
                      f"status={outcome['status']}",
                      f"result={json.dumps(outcome['result'], ensure_ascii=False)}"))
