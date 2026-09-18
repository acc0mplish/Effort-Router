#!/usr/bin/env python3
"""jev 확장 판단 모드 3종 — escalation(격상 사유 검증)·memory-gate(기억 게이팅)·stall(고착 판정).

모드 정의 모듈이다 — 질문 상수·입력 파싱·recommendation 합성만 담당하고 네트워크 호출은
없다(보존 5). API 호출·응답 검증·감사는 jev_judge.py 엔진이 수행하며, 의존 방향은
jev_judge → jev_modes 단방향이다(계획 §2.1). 이 모듈은 jev_judge를 import하지 않는다 —
__main__ 실행 시 모듈 2회 로드를 유발하므로 fail()은 2줄 자체 복제이고, 관련성 임계
noul_confirmed는 jev_judge 정의를 파라미터로 주입받는다(보존 3 — 신규 dead zone·임계 정의 없음).

게이트 원칙(계획 §2.3): 기각·확정 방향(격상 차단·고착 개입)만 CONFIRM_CONFIDENCE(기존
방향별 임계와 같은 값 0.85)를 요구하고, 허용·상향 방향은 confidence 바닥이 없다 —
자원 과투자 비용 < 결함 유출 비용.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, NoReturn

# 격상 허용 케이스(계획 §2.2) — ASCII 키 + 한국어 criteria(TIER_CRITERIA의 S/M/L/XL 패턴 계승).
# --rules-file JSON({case_id: 설명, ...})으로 교체 가능하다. not_justified는 교체 불가(항상 병설).
ESCALATION_CASES = {
    'workload_surge_observed': '관측된 작업량 급증이다 — 파일 수·변경 범위가 착수 시 합의된 예상을 넘어섰다는 증거가 사유에 있다',
    'harness_constraint_measured': '하니스 제약 실측이다 — 타임아웃·컨텍스트 한도·도구 반복 실패 등 환경 제약이 실제로 관측되었다',
    'user_explicit_directive': '사용자 명시 지시이다 — 사용자가 직접 상위 모델 격상을 지시했다',
}
NOT_JUSTIFIED = 'not_justified'
NOT_JUSTIFIED_CRITERIA = '어느 허용 사유에도 해당하지 않는다 — 난이도·선호·자신 없음은 사유가 아니다'

# 고착 판정 선택지(계획 §2.2) — 워커 자기 보고(주장)보다 검증 신호가 우선한다(결정 D4).
STALL_INACTIVITY_HINT = 1800   # criteria 문구 주입용 안내 기준 — 코드 합성 미사용(결정 D9)
STALL_STATES = {
    'working': '작업 중이다 — 검증 신호가 최근 활동을 보여준다(마지막 도구 호출·파일 기록이 최근이다). '
               '최근 활동 신호가 존재하면 자기 보고와 무관하게 고착로 판정하지 않는다',
    'waiting_declared': '대기 선언이다 — 자기 보고·최근 발화가 외부 응답·승인 대기를 선언하고 있고 '
                        '무활동 구간이 고찰 기준 이하다(안내 기준: 마지막 도구 호출이 약 1800초 미만 전). '
                        '대기 선언이 있어도 무활동이 고찰 기준을 넘으면 고착로 판정한다',
    'approval_pending': '결재 대기이다 — 상위 세션 승인 대기 중이다',
    'terminated': '종료했다 — 신호가 세션 종료와 정합한다',
    'stalled': '고착했다 — 검증 신호가 장기 무활동을 보여준다: 마지막 도구 호출·파일 기록이 모두 오래됐다 '
               '(안내 기준: 약 1800초 이상). 자기 보고가 작업 중을 주장해도 신호가 우선한다. '
               '최근 활동 신호가 하나라도 존재하면 고착이 아니다',
}

MAX_MEMORY_LINES = 100   # 초과 시 FAIL — 조용한 truncation은 뒤 줄의 거짓 음성을 만든다(결정 D5)
CONFIRM_CONFIDENCE = 0.85   # 기각·확정 방향 임계 — 기존 방향별 임계와 같은 값의 상수 1곳


def fail(reason: str) -> NoReturn:
    print(f'FAIL jev judge: {reason}', file=sys.stderr)
    raise SystemExit(1)


def _escalation_cases(rules_file: str | None) -> dict[str, str]:
    """허용 케이스 3종 + not_justified 병설. --rules-file로 3종만 교체한다(D-CLI1)."""
    if rules_file is None:
        cases = dict(ESCALATION_CASES)
        cases[NOT_JUSTIFIED] = NOT_JUSTIFIED_CRITERIA
        return cases
    try:
        raw = Path(rules_file).read_bytes().decode('utf-8')
    except FileNotFoundError:
        fail(f'rules file not found: {rules_file}')
    except UnicodeDecodeError as error:
        fail(f'rules file is not valid UTF-8: {error}')
    except OSError as error:
        fail(f'rules file read failed: {error}')
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        fail(f'rules file is not valid JSON: {error}')
    if not isinstance(parsed, dict) or not parsed:
        fail('rules file must be a non-empty JSON object of {case_id: 설명}')
    if not all(isinstance(value, str) for value in parsed.values()):
        fail('rules file criteria values must all be strings')
    if NOT_JUSTIFIED in parsed:
        fail("rules file cannot replace the 'not_justified' option")
    cases = dict(parsed)
    cases[NOT_JUSTIFIED] = NOT_JUSTIFIED_CRITERIA
    return cases


def _memory_lines(source: str) -> list[tuple[int, str]]:
    """라인 전처리(계획 §2.2) — 빈 줄·공백 줄 제외, 선두 frontmatter 제외, 원 줄번호 유지."""
    rows = source.split('\n')
    start = 0
    if rows and rows[0].strip() == '---':
        for index in range(1, len(rows)):
            if rows[index].strip() == '---':
                start = index + 1
                break
    kept = [(number, row) for number, row in enumerate(rows[start:], start=start + 1)
            if row.strip()]
    if len(kept) > MAX_MEMORY_LINES:
        fail(f'memory file has {len(kept)} non-blank lines — limit is {MAX_MEMORY_LINES}; '
             'split the file and call again')
    return kept


def _stall_signals(spec: str, stdin_text: Callable[[], str]) -> dict[str, Any]:
    """신호 획득(파일 경로 > JSON 원문 > stdin)·스키마 검증 — 위반은 FAIL exit 1(계획 §2.2)."""
    try:
        is_file = Path(spec).is_file()
    except (OSError, ValueError):
        is_file = False
    if spec == '-':
        raw = stdin_text()
    elif is_file:
        try:
            raw = Path(spec).read_bytes().decode('utf-8')
        except (OSError, UnicodeDecodeError) as error:
            fail(f'signal file read failed: {error}')
    else:
        raw = spec
    try:
        signals = json.loads(raw)
    except json.JSONDecodeError as error:
        fail(f'signal is not valid JSON: {error}')
    if not isinstance(signals, dict):
        fail('signal must be a JSON object')
    tool_age = signals.get('last_tool_age_s')
    if not isinstance(tool_age, (int, float)) or isinstance(tool_age, bool) or tool_age < 0:
        fail("signal 'last_tool_age_s' must be a number >= 0")
    if 'last_file_write_age_s' not in signals:
        fail("signal 'last_file_write_age_s' key is required")
    write_age = signals['last_file_write_age_s']
    if write_age is not None and (not isinstance(write_age, (int, float))
                                  or isinstance(write_age, bool) or write_age < 0):
        fail("signal 'last_file_write_age_s' must be a number >= 0 or null")
    if 'last_assistant_text' not in signals:
        fail("signal 'last_assistant_text' key is required")
    spoken = signals['last_assistant_text']
    if spoken is not None and not isinstance(spoken, str):
        fail("signal 'last_assistant_text' must be a string or null")
    declared = signals.get('declared_state')
    if declared is not None and not isinstance(declared, str):
        fail("signal 'declared_state' must be a string or null")
    return signals


def _serialize_signals(signals: dict[str, Any]) -> str:
    """결정적 직렬화(계획 §2.2) — 검증 신호와 자기 보고(주장)를 문단·문구로 분리한다(결정 D4)."""
    write_age = signals['last_file_write_age_s']
    write_part = '기록 없음' if write_age is None else f'{write_age}초 전'
    declared = signals.get('declared_state') or ''
    spoken = signals['last_assistant_text'] or ''
    return (f"검증 신호: 마지막 도구 호출 {signals['last_tool_age_s']}초 전, "
            f"마지막 파일 기록 {write_part}.\n"
            f"워커 자기 보고(참고용 주장 — 검증 신호와 정합할 때만 참고): "
            f"declared_state='{declared}', 마지막 발화: '{spoken}'")


def parse_mode_input(mode: str, statement: str, *, rules_file: str | None = None,
                     memory_file: str | None = None, top_k: int | None = None,
                     stdin_text: Callable[[], str]) -> dict[str, Any]:
    """모드별 입력을 파싱해 {state, ...모드 데이터}를 반환한다 — 실패는 FAIL exit 1."""
    if mode == 'escalation':
        return {'state': statement, 'cases': _escalation_cases(rules_file)}
    if mode == 'memory-gate':
        if statement == '-' and memory_file == '-':
            fail('stdin 이중 소비 불가 — statement와 --memory-file을 동시에 "-"로 지정할 수 없다')
        if memory_file is None:
            fail("memory-gate 모드에는 --memory-file {경로|'-'}가 필요하다")
        state = stdin_text() if statement == '-' else statement
        if memory_file == '-':
            source = stdin_text()
        else:
            try:
                source = Path(memory_file).read_bytes().decode('utf-8')
            except FileNotFoundError:
                fail(f'memory file not found: {memory_file}')
            except UnicodeDecodeError as error:
                fail(f'memory file is not valid UTF-8: {error}')
            except OSError as error:
                fail(f'memory file read failed: {error}')
        if top_k is None or top_k < 1:
            fail(f'--top-k must be a positive integer, got {top_k!r}')
        return {'state': state, 'lines': _memory_lines(source), 'top_k': top_k}
    if mode == 'stall':
        signals = _stall_signals(statement, stdin_text)
        return {'state': _serialize_signals(signals), 'signals': signals}
    fail(f'unsupported mode: {mode}')


def build_mode_questions(mode: str, mode_input: dict[str, Any]) -> dict[str, Any]:
    """모드별 질문 맵 — fan-out은 전 질문을 단일 요청에 병렬 태운다(1호출 원칙)."""
    if mode == 'escalation':
        return {'decision': {'type': 'choice',
                             'instructions': '격상 사유가 허용 케이스에 해당하는지 판정한다',
                             'criteria': dict(mode_input['cases'])}}
    if mode == 'memory-gate':
        return {f'line_{number}': {'type': 'noul',
                                   'instructions': ('기억 파일의 다음 줄이 이 요청을 해결하거나 판단하는 데 필요한 정보이면 true, '
                                                    '아니면 false로 판단한다 — 필요한 정보는 요청 대상의 직접 언급뿐 아니라 '
                                                    f'그 원인·해결 수단으로 기능하는 배경 지식도 포함한다. 줄: {text}'),
                                   'criteria': {'true': '해결·판단에 필요한 정보다', 'false': '필요하지 않은 정보다'}}
                for number, text in mode_input['lines']}
    return {'state': {'type': 'choice',
                      'instructions': ('검증 신호를 근거로 워커 세션의 현재 상태를 판정한다 — '
                                       '자기 보고 주장보다 검증 신호가 우선한다'),
                      'criteria': dict(STALL_STATES)}}


def build_mode_recommendation(mode: str, mode_input: dict[str, Any], answers: dict[str, Any],
                              noul_confirmed: Callable[[float], bool]) -> dict[str, Any]:
    """모드별 recommendation 합성 — 관련성 임계는 jev_judge의 noul_confirmed를 주입받는다(보존 3)."""
    if mode == 'escalation':
        answer = answers['decision']
        decision = answer['choice']
        return {'decision': decision,
                'case': None if decision == NOT_JUSTIFIED else decision,
                'confidence': answer['confidence'],
                'probabilities': answer['probabilities'],
                'reject_confirmed': (decision == NOT_JUSTIFIED
                                     and answer['confidence'] >= CONFIRM_CONFIDENCE)}
    if mode == 'memory-gate':
        entries = [{'line_no': number, 'text': text,
                    'noul': answers[f'line_{number}']['noul'],
                    'relevant': noul_confirmed(answers[f'line_{number}']['noul'])}
                   for number, text in mode_input['lines']]
        ranked = sorted((entry for entry in entries if entry['relevant']),
                        key=lambda entry: (-entry['noul'], entry['line_no']))
        return {'lines': entries,
                'selected': [entry['line_no'] for entry in ranked[:mode_input['top_k']]],
                'top_k': mode_input['top_k'],
                'stats': {'total': len(entries),
                          'relevant_count': sum(1 for entry in entries if entry['relevant'])}}
    answer = answers['state']
    return {'state': answer['choice'], 'confidence': answer['confidence'],
            'probabilities': answer['probabilities'],
            'intervene_confirmed': (answer['choice'] == 'stalled'
                                    and answer['confidence'] >= CONFIRM_CONFIDENCE)}
