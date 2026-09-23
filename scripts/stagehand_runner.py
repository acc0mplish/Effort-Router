#!/usr/bin/env python3
"""r18 Stagehand 실행 계층 — 태스크 로드·모의 러너·실 Stagehand 러너.

동일 시그니처 `run_task(spec, runner_kind, scenario, attempt_index)` 프로토콜로
실행 계층을 추상화한다(plan.md §2b). Stagehand SDK는 실실행 함수 내부 지연 임포트 —
미설치 환경에서도 게이트 전체 로직·테스트가 동작한다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from stagehand_gate_policy import TaskValidationError, validate_task

MOCK_SCENARIOS = ('done-first', 'retry-then-done', 'never-done', 'runner-error')
API_KEY_VARS = ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY')
INSTALL_GUIDE = ('Stagehand SDK가 설치되어 있지 않다 — '
                 'bash scripts/setup_stagehand_env.sh 로 .venv-stagehand 를 구성한 뒤 '
                 '그 가상환경의 python으로 실행하라')


class RunnerConfigError(Exception):
    """config/env 오류 — 게이트가 exit 2로 변환한다(§4.3)."""


class RunnerUnavailableError(RunnerConfigError):
    """LLM 키·SDK 부재 — exit 2이며 설치 안내를 포함한다(§4.3)."""


def require_llm_key(env: dict[str, str]) -> str:
    """runner=stagehand에 필요한 LLM 키를 확인한다 — 어느 하나라도 있으면 통과."""
    present = [name for name in API_KEY_VARS if env.get(name)]
    if not present:
        raise RunnerConfigError(
            'LLM API 키 부재 — OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 중 하나가 '
            '필요하다(runner=stagehand)')
    return present[0]


def ensure_sdk_available() -> None:
    """SDK 임포트 사전검증 — 미설치면 설치 안내(스크립트명 포함)로 exit 2 근거를 만든다."""
    try:
        import stagehand  # noqa: F401
    except ImportError as error:
        raise RunnerUnavailableError(f'{INSTALL_GUIDE} (import stagehand 실패: {error})')


def load_task(path: str) -> dict[str, Any]:
    """태스크 파일 로드 + 스키마 검증 — 파일·JSON 오류도 config 오류(exit 2)로 보고한다."""
    try:
        raw = Path(path).read_text(encoding='utf-8')
    except OSError as error:
        raise RunnerConfigError(f'태스크 파일을 읽을 수 없다: {error}')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RunnerConfigError(f'태스크 파일이 유효한 JSON이 아니다: {error}')
    try:
        return validate_task(data)
    except TaskValidationError as error:
        raise RunnerConfigError(
            '태스크 스키마 위반:\n' + '\n'.join(f'  - {reason}' for reason in error.errors))


def run_task(spec: dict[str, Any], runner_kind: str, scenario: str,
             attempt_index: int) -> dict[str, Any]:
    """실행 계층 단일 진입 — 러너 예외는 게이트가 error 기록으로 변환해 계속한다(§4.7)."""
    if runner_kind == 'mock':
        return run_mock_task(spec, scenario, attempt_index)
    return run_stagehand_task(spec, attempt_index)


def run_mock_task(spec: dict[str, Any], scenario: str, attempt_index: int) -> dict[str, Any]:
    """내장 모의 러너 — 시나리오·시도 횟수로 결정적으로 전환한다(§4.7)."""
    if scenario not in MOCK_SCENARIOS:
        raise RunnerConfigError(
            f'무효 시나리오: {scenario!r} — {", ".join(MOCK_SCENARIOS)} 중 하나여야 한다')
    if scenario == 'runner-error':
        raise RuntimeError(f'mock runner failure: task_id={spec["task_id"]} '
                           f'attempt={attempt_index}')
    success = scenario == 'done-first' or (scenario == 'retry-then-done'
                                           and attempt_index >= 2)
    if success:
        return {'status': 'success',
                'result': {'steps_completed': len(spec['steps']),
                           'actions': [{'action': step['action'],
                                        'instruction': step['instruction'],
                                        'status': 'done'} for step in spec['steps']]}}
    return {'status': 'error',
            'result': {'reason': f'시나리오 {scenario}의 {attempt_index}차 시도 실패 — '
                                 f'{len(spec["steps"])}개 단계 중 일부가 완료되지 않았다'},
            'error': f'시나리오 {scenario} {attempt_index}차 시도 실패'}


def run_stagehand_task(spec: dict[str, Any], attempt_index: int) -> dict[str, Any]:
    """실 Stagehand 러너 — 지연 임포트 후 로컬 브라우저로 steps를 수행한다.

    SDK API 표면은 버전별로 상이하다(위험 §8) — 진입점 계약(§4.4·§4.7)만 고정하고
    세부 호출은 최소 표면만 사용한다. 실브라우저 E2E는 키 확보 후 수동 스모크(A4).
    """
    try:
        import asyncio

        from stagehand import Stagehand  # 지연 임포트(§2b)
    except ImportError as error:
        raise RunnerUnavailableError(f'{INSTALL_GUIDE} (import stagehand 실패: {error})')
    return asyncio.run(_run_steps(spec, attempt_index))


async def _run_steps(spec: dict[str, Any], attempt_index: int) -> dict[str, Any]:
    from stagehand import Stagehand

    model_name = os.environ.get('STAGEHAND_MODEL') or 'openai/gpt-4o-mini'
    stagehand = Stagehand(env='LOCAL', model_name=model_name)
    try:
        await stagehand.init()
        page = stagehand.page
        await page.goto(spec['url'])
        actions = []
        for index, step in enumerate(spec['steps']):
            actions.append(await _execute_step(page, step, index))
        return {'status': 'success',
                'result': {'steps_completed': len(spec['steps']), 'actions': actions,
                           'attempt_index': attempt_index}}
    finally:
        await stagehand.close()


async def _execute_step(page: Any, step: dict[str, Any], index: int) -> dict[str, Any]:
    action = step['action']
    if action == 'act':
        await page.act(step['instruction'])
        return {'index': index, 'action': action, 'status': 'done'}
    if action == 'observe':
        candidates = await page.observe(step['instruction'])
        return {'index': index, 'action': action, 'status': 'done',
                'candidates': len(candidates)}
    if action == 'extract':
        extracted = await page.extract(step['instruction'])
        return {'index': index, 'action': action, 'status': 'done',
                'data': extracted}
    return {'index': index, 'action': action, 'status': 'error',
            'reason': f'무효 action: {action}'}
