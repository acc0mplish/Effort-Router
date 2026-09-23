#!/usr/bin/env python3
"""r18 Stagehand 게이트 래퍼 CLI — 브라우저 실행 → 결과 기록 → jev 판정 → 게이트.

실행 계층(stagehand_runner)과 판단 계층(jev_judge.py 서브프로세스)을 잇는다.
종료코드(§4.3): 0 pass · 1 retry-exhausted · 2 config/env 오류 · 3 escalated.
jev 결합은 subprocess 전용이며 recommendation 불리언만 소비한다(보존 제약 1·4).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import stagehand_gate_policy as policy
import stagehand_runner as runner

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JEV_CMD = f'python3 {ROOT}/scripts/jev_judge.py'
EXIT_EXHAUSTED = 1
EXIT_CONFIG = 2
EXIT_ESCALATED = 3
MAX_RETRIES_BOUNDS = (0, 5)
DEFAULT_MAX_RETRIES = 2
DEFAULT_TIMEOUT = 30.0


class GateConfigError(Exception):
    """인자·env 범위 위반 — exit 2로 변환한다(§4.3)."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Stagehand 실행 결과를 jev로 게이트하는 래퍼 — 재시도·종료·에스컬레이션')
    parser.add_argument('--task-file', required=True, help='태스크 JSON 파일 경로(§4.4)')
    parser.add_argument('--runner', choices=('stagehand', 'mock'), default='stagehand',
                        help='실행 계층 선택(기본 stagehand)')
    parser.add_argument('--mock-scenario', choices=runner.MOCK_SCENARIOS,
                        help='runner=mock 전용 결정적 시나리오(기본 done-first)')
    parser.add_argument('--jev-mode', choices=('verify-run', 'done'), default='verify-run',
                        help='jev 판단 모드(기본 verify-run)')
    parser.add_argument('--jev-cmd',
                        help='shlex 커맨드 prefix — 플래그 > env STAGEHAND_GATE_JEV_CMD > 기본')
    parser.add_argument('--max-retries', type=int,
                        help=f'재시도 상한 {MAX_RETRIES_BOUNDS[0]}..{MAX_RETRIES_BOUNDS[1]}'
                             f'(기본 {DEFAULT_MAX_RETRIES}, env STAGEHAND_GATE_MAX_RETRIES)')
    parser.add_argument('--save-dir', help='jev --save 전달(시도별 감사 로그)')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT,
                        help=f'jev 서브프로세스 타임아웃 초(기본 {DEFAULT_TIMEOUT}, 양수 유한)')
    return parser.parse_args(argv)


def resolve_config(args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    """인자·env를 단일 설정으로 합성한다 — 범위 위반은 GateConfigError(전부 exit 2)."""
    timeout = validate_timeout(args.timeout)
    max_retries = resolve_max_retries(args.max_retries, env)
    scenario = resolve_scenario(args.runner, args.mock_scenario)
    return {'task_file': args.task_file,
            'runner': args.runner,
            'mock_scenario': scenario,
            'jev_mode': args.jev_mode,
            'jev_cmd': args.jev_cmd or env.get('STAGEHAND_GATE_JEV_CMD') or DEFAULT_JEV_CMD,
            'max_retries': max_retries,
            'save_dir': args.save_dir,
            'timeout': timeout}


def validate_timeout(timeout: float) -> float:
    if not math.isfinite(timeout) or timeout <= 0:
        raise GateConfigError(f'--timeout은 양수 유한 값이어야 한다: {timeout!r}')
    return timeout


def resolve_max_retries(flag: int | None, env: dict[str, str]) -> int:
    if flag is None:
        raw = env.get('STAGEHAND_GATE_MAX_RETRIES')
        if raw is None:
            return DEFAULT_MAX_RETRIES
        try:
            flag = int(raw)
        except ValueError as error:
            raise GateConfigError(f'STAGEHAND_GATE_MAX_RETRIES가 정수가 아니다: {raw!r}') \
                from error
    low, high = MAX_RETRIES_BOUNDS
    if not low <= flag <= high:
        raise GateConfigError(f'--max-retries는 {low}..{high} 범위여야 한다: {flag}')
    return flag


def resolve_scenario(runner_kind: str, scenario: str | None) -> str:
    if runner_kind == 'mock':
        return scenario or 'done-first'
    if scenario is not None:
        raise GateConfigError('--mock-scenario은 runner=mock 전용이다(config error)')
    return ''


def runner_preflight(config: dict[str, Any]) -> str | None:
    """runner=stagehand 사전검증 — LLM 키 → SDK 임포트 순(브라우저 호출 전 종료)."""
    if config['runner'] != 'stagehand':
        return None
    key_var = runner.require_llm_key(os.environ)
    runner.ensure_sdk_available()
    return key_var


def call_jev(config: dict[str, Any], statement: str) -> dict[str, Any]:
    """jev CLI 서브프로세스 호출(stdin 전달) — 판단 불능은 unavailable 근거로 보고한다.

    성공 해석은 recommendation 불리언 소비만이다. noul은 기록용 수집(§4.5).
    """
    command = (shlex.split(config['jev_cmd'])
               + [config['jev_mode'], '-', '--timeout', str(config['timeout'])])
    if config['save_dir']:
        command += ['--save', config['save_dir']]
    try:
        completed = subprocess.run(command, input=statement, capture_output=True,
                                   text=True, timeout=config['timeout'])
    except subprocess.TimeoutExpired:
        return {'unavailable': True,
                'reason': f'jev 서브프로세스 타임아웃({config["timeout"]}초)'}
    except OSError as error:
        return {'unavailable': True, 'reason': f'jev 서브프로세스 실행 실패: {error}'}
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        reason = detail[-1][:200] if detail else '(출력 없음)'
        return {'unavailable': True,
                'reason': f'jev 판단 불능(exit {completed.returncode}): {reason}'}
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return {'unavailable': True, 'reason': f'jev stdout이 JSON이 아니다: {error}'}
    try:
        return {'unavailable': False,
                'consumed': policy.consume_recommendation(config['jev_mode'], parsed)}
    except policy.JevViolationError as error:
        return {'unavailable': True, 'reason': str(error)}


def execute_attempt(config: dict[str, Any], spec: dict[str, Any],
                    attempt: int) -> dict[str, Any]:
    """러너 1회 실행 — 러너 예외도 error 기록으로 변환해 게이트를 계속한다(§4.7)."""
    try:
        return runner.run_task(spec, config['runner'], config['mock_scenario'], attempt)
    except Exception as error:  # noqa: BLE001 — 게이트 계속이 계약이다
        return {'status': 'error', 'result': {'reason': str(error)}, 'error': str(error)}


def run_gate_loop(config: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """게이트 루프 — 판정 미확정 재시도, 판단 불능 즉시 에스컬레이션(§2c)."""
    max_attempts = 1 + config['max_retries']
    log: list[dict[str, Any]] = []
    last_noul: float | None = None
    for attempt in range(1, max_attempts + 1):
        outcome = execute_attempt(config, spec, attempt)
        log.append({'attempt': attempt, 'status': outcome['status'],
                    'error': outcome.get('error')})
        statement = policy.build_statement(spec, attempt, max_attempts,
                                           config['runner'], outcome)
        call = call_jev(config, statement)
        if call['unavailable']:
            return final_result(spec, config, 'escalated', attempt, max_attempts,
                                log, None, escalation_reason=call['reason'])
        consumed = call['consumed']
        last_noul = consumed['noul']
        decision = policy.gate_decision(consumed['confirmed'], attempt, max_attempts)
        if decision != 'retry':
            return final_result(spec, config, decision, attempt, max_attempts,
                                log, last_noul)
    return final_result(spec, config, 'retry-exhausted', max_attempts, max_attempts,
                        log, last_noul)


def final_result(spec: dict[str, Any], config: dict[str, Any], decision: str,
                 attempts: int, max_attempts: int, log: list[dict[str, Any]],
                 last_noul: float | None,
                 escalation_reason: str | None = None) -> dict[str, Any]:
    """최종 결과 JSON — stdout 1줄(기존 jev CLI 출력 관습 계승)."""
    result = {'ok': decision == 'pass',
              'task_id': spec['task_id'],
              'runner': config['runner'],
              'jev_mode': config['jev_mode'],
              'decision': decision,
              'attempts': attempts,
              'max_attempts': max_attempts,
              'last_noul': last_noul,
              'attempts_log': log}
    if escalation_reason is not None:
        result['escalation_reason'] = escalation_reason
    return result


def fail_config(error: Exception) -> None:
    print(f'FAIL stagehand gate: config error: {error}', file=sys.stderr)
    raise SystemExit(EXIT_CONFIG)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        config = resolve_config(args, os.environ)
        spec = runner.load_task(config['task_file'])
        runner_preflight(config)
    except (GateConfigError, runner.RunnerConfigError) as error:
        fail_config(error)
    result = run_gate_loop(config, spec)
    print(json.dumps(result, ensure_ascii=False))
    if result['decision'] == 'pass':
        return
    raise SystemExit(EXIT_ESCALATED if result['decision'] == 'escalated'
                     else EXIT_EXHAUSTED)


if __name__ == '__main__':
    main()
