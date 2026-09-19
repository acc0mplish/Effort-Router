#!/usr/bin/env python3
"""jev 판단 계층 CLI — TypeSafe 판단형 LLM 예판 클라이언트(선택 가속기).

스키마 출처(가정 A1): https://docs.typesafe.ai/api (2026-09-18 조회, 계획 §0 확정 사실)
- 엔드포인트: POST {endpoint} · Authorization: Bearer $TYPESAFE_API_KEY · JSON
- 요청 body: state(작업 서술 원문) + model + questions(map — 응답도 같은 키로 돌아온다)
- choice 답 = {type, choice, probabilities(전 옵션, 합 1), confidence}
- score 답 = {type, score, confidence, legend(레벨→문구), probabilities(레벨 인덱스 문자열 키, 합 1)}
- noul 답 = {type, noul(0~1)} — noul 답에는 confidence 필드가 없다
- 에러 401·422·429·529 — 재시도 없음(결정 D1): 실패는 즉시 폴백 신호다

엔드포인트 루프백 가드(결정 D5): 비기본 --endpoint는 127.0.0.1·localhost·[::1] 호스트만
허용하고, 위반 시 HTTP 호출 없이 exit 1 한다. CLI 플래그는 작업 서술 인젝션이 도달할 수
있는 표면이므로 Bearer 키의 제3자 호스트 전송 경로를 코드 레벨에서 원천 차단한다.
리다이렉트 추적도 금지한다(gap F1 — urllib 기본 처리는 Authorization 헤더를 Location
대상에 재전송하므로, 3xx는 전부 폴백 신호로 처리하고 추적하지 않는다).
--endpoint는 테스트 전용 플래그다(127.0.0.1 mock 주입용).

성공은 stdout JSON(ensure_ascii=False) + exit 0. 실패는 stderr 'FAIL jev judge: <사유>'
+ exit 1 — 호출자는 exit 1을 기존 프로세스 폴백 신호로 해석한다(jev는 선택 계층).

noul 해석(gap G2): noul 원시값은 recommendation.risk_values(tier)·recommendation.safe_noul
(prune)로 그대로 노출한다 — boolean만으로는 판단 정보가 손실된다. dead zone(0.4≤v<0.6)은
임계 인접 응답의 신뢰가 불가하다(실측 오탐 0.64·정탐 0.57 공존) — tier 위험은 양성 처리
(하향 기각 방향), prune safe는 축소 불허 처리한다.

확장 모드 3종(escalation·memory-gate·stall)의 질문 상수·입력 파싱·recommendation 합성은
jev_modes.py가 담당한다 — 의존 방향은 jev_judge → jev_modes 단방향(계획 §2.1)이며 신규
분기도 기존 call_api→validate_response→audit 파이프라인을 그대로 경유한다.
"""
from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

import jev_modes

DEFAULT_ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
DEFAULT_MODEL = 'jev-latest'
DEFAULT_TIMEOUT = 8.0
LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}
# noul 해석 dead zone(0.4≤v<0.6) — 임계 인접 응답은 신뢰 불가(실측 오탐 0.64·정탐 0.57 공존).
# 보수 처리: tier 위험은 양성(하향 기각 방향), prune safe는 축소 불허(gap G2 — 2렌즈 독립 확인).
NOUL_DEAD_ZONE = (0.4, 0.6)
PROB_SUM_TOLERANCE = 0.05

RISK_KEYS = ('request_path', 'security_control', 'topology_unknown', 'output_document', 'gate_preset')

# fanout 복합 점수(계획 §2.2) — 복잡도 Score 5레벨. 레벨 문구는 after/ 감사 질문 맵과
# 바이트 동일해야 한다(재판정 재사용 전제 A4). 렌즈 임계는 이 상수 1곳에 격리한다.
COMPLEXITY_LEVELS = (
    '단일 파일의 국소 변경이다 — 텍스트·스타일·상수 수준이고 분기 로직과 파급이 없다',
    '동일 치환의 기계적 반복이다 — 여러 파일이지만 각 변경은 동일하고 새 분기가 없다',
    '통상의 기능 과업이다 — 분기 로직 추가·수정과 2~10파일 파급, 위험 지표는 음성이다',
    '구조·통제에 닿는 변경이다 — 아키텍처·요청 경로·보안 통제·산출 문서 중 하나에 해당한다',
    '시스템 전체를 움직리는 변경이다 — 코어 재구현·전면 리팩터링, 결함이 되돌릴 수 없다',
)
LENS_THRESHOLDS = (2.5, 1.5)   # score ≥2.5 → 3렌즈, ≥1.5 → 2렌즈, 미만 → 1렌즈

# ── 질문 설계(계획 §2.3) — 이 상수 블록 1곳에 격리한다 ──────────────────────────
TIER_CRITERIA = {
    'S': '단순 버그 수정, 텍스트/스타일, 단일 파일 변경 (테스트 로직 변경 없음)',
    'M': '기능 추가, 리팩터링, 분기 로직 수정, 영향 2~10파일, 위험 지표 음성',
    'L': '대형 모듈, 아키텍처 변경, 고위험 핵심 모듈, 10파일 초과 또는 1000줄 초과, 위험 지표 양성',
    'XL': '코어 엔진 구현, 전체 시스템 리팩터링 (프로토타입 포함)',
}
RISK_DESCRIPTIONS = {
    'request_path': '모든 요청이 지나는 경로(필터·인터셉터·인증·라우팅)의 동작 자체를 바꾸는 변경이다',
    'security_control': '보안 통제 자체가 변경 대상이다',
    'topology_unknown': '작업 서술이 배포 토폴로지·프록시·게이트웨이 경계를 명시적으로 언급한다. 언급이 없으면 false다',
    'output_document': '작업 서술이 다른 구현을 지시할 산출 문서(설계서·계획서·명세 등)의 신규 작성 또는 중대 개정을 명시한다. 문서 산출 언급이 없으면 false다',
    'gate_preset': '게이트 신설·변경, 보안·무결성 통제 변경, 기준선 봉인 문서에 해당한다',
}
STAGE_OPTIONS = {
    'plan': ('keep_full', 'thin_plan'),
    'review': ('full_scope', 'narrow_scope'),
}
STAGE_CHOICE_DESCRIPTIONS = {
    'plan': {'keep_full': '심층 계획 스폰을 유지한다', 'thin_plan': '얇은 계획으로 축소한다'},
    'review': {'full_scope': '리뷰 전체 스코프를 유지한다', 'narrow_scope': '리뷰 스코프를 축소한다'},
}


def noul_question(description: str) -> dict[str, str]:
    return {'type': 'noul',
            'instructions': f'다음 진술이 해당하면 true, 아니면 false로 판단한다: {description}',
            'criteria': {'true': '해당한다', 'false': '해당하지 않는다'}}


def build_questions(mode: str, stage: str | None) -> dict[str, Any]:
    """호출 질문 맵을 만든다 — tier 1+은닉변수 5종 / fanout score+Noul safe / plan·review choice+Noul safe."""
    if mode == 'tier':
        questions: dict[str, Any] = {
            'tier': {'type': 'choice',
                     'instructions': '작업 서술을 S/M/L/XL 작업 티어로 분류한다',
                     'criteria': dict(TIER_CRITERIA)}}
        questions.update({f'risk_{key}': noul_question(RISK_DESCRIPTIONS[key])
                          for key in RISK_KEYS})
        return questions
    if stage == 'fanout':
        # 복합 점수(계획 P3-D1) — 렌즈 수 3단계는 Score 영역이고 choice 병설은 이중 질의다
        return {'complexity': {'type': 'score',
                               'instructions': '작업 서술의 변경 규모와 파급 수준을 판단한다',
                               'criteria': list(COMPLEXITY_LEVELS)},
                'safe': noul_question('이 축소로도 과업 계약(요구·검증 커버리지)이 훼손되지 않는다')}
    options = STAGE_OPTIONS[stage or '']
    return {stage: {'type': 'choice',
                    'instructions': f'{stage} 단계의 실행 범위를 판단한다',
                    'criteria': {option: STAGE_CHOICE_DESCRIPTIONS[stage][option]
                                 for option in options}},
            'safe': noul_question('이 축소로도 과업 계약(요구·검증 커버리지)이 훼손되지 않는다')}


def fail(reason: str) -> NoReturn:
    print(f'FAIL jev judge: {reason}', file=sys.stderr)
    raise SystemExit(1)


def read_stdin_text() -> str:
    """stdin을 바이트로 읽어 UTF-8 엄격 디코드한다(gap F3 — surrogateescape mojibake 차단)."""
    try:
        return sys.stdin.buffer.read().decode('utf-8')
    except UnicodeDecodeError as error:
        fail(f'statement is not valid UTF-8: {error}')
    except OSError as error:
        fail(f'statement read failed: {error}')


def guard_endpoint(endpoint: str) -> None:
    """D5 — 기본 엔드포인트 또는 loopback 호스트만 허용한다(HTTP 호출 전 사전검증)."""
    if endpoint == DEFAULT_ENDPOINT:
        return
    host = (urlsplit(endpoint).hostname or '').lower()
    if host not in LOOPBACK_HOSTS:
        fail(f'non-loopback endpoint rejected: {endpoint} — Bearer 키 유출 방지 가드(결정 D5)')


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """리다이렉트 추적 금지(D5 보강) — 3xx를 추적하지 않고 HTTPError로 되돌린다.

    urllib 기본 리다이렉트 처리는 Authorization 헤더를 Location 대상에 재전송한다.
    302가 Bearer 키를 제3자 호스트로 전파하는 경로가 되므로 추적 자체를 닫는다.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call_api(endpoint: str, api_key: str, body: dict[str, Any], timeout: float) -> str:
    """단발 POST — 재시도 없음(D1). 실패는 전부 폴백 신호로 변환한다."""
    request = urllib.request.Request(
        endpoint, data=json.dumps(body).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {api_key}'})
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
    except socket.timeout:
        fail(f'request timed out after {timeout}s')
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            location = error.headers.get('Location') if error.headers else None
            fail(f'redirect is not allowed ({error.code} -> {location or "no-location"})')
        fail(f'HTTP {error.code} — 재시도 없이 폴백한다(결정 D1)')
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            fail(f'request timed out after {timeout}s')
        fail(f'request failed: {error.reason}')
    except http.client.HTTPException as error:
        # 절단 응답(IncompleteRead)·비정상 연결 종료(RemoteDisconnected) 등 스트림 결함(gap G1)
        fail(f'response stream failed: {error}')
    except OSError as error:
        fail(f'request failed: {error}')
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError as error:
        fail(f'invalid response schema: response is not valid UTF-8: {error}')


def validate_response(payload: Any, questions: dict[str, Any]
                      ) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """응답 스키마 검증 — 위반 시 exit 1. (model, answers, usage)를 반환한다."""
    if not isinstance(payload, dict):
        fail('invalid response schema: response is not a JSON object')
    model = payload.get('model')
    if not isinstance(model, str):
        fail("invalid response schema: response 'model' is not a string")
    answers = payload.get('answers')
    if not isinstance(answers, dict):
        fail("invalid response schema: response 'answers' is not an object")
    missing = [qid for qid in questions if qid not in answers]
    if missing:
        fail(f"invalid response schema: response 'answers' is missing question keys: "
             f"{', '.join(missing)}")
    for qid, question in questions.items():
        if question['type'] == 'choice':
            validate_choice_answer(qid, answers[qid], question['criteria'])
        elif question['type'] == 'score':
            validate_score_answer(qid, answers[qid], question['criteria'])
        else:
            validate_noul_answer(qid, answers[qid])
    return model, answers, validate_usage(payload.get('usage'))


def validate_choice_answer(qid: str, answer: Any, criteria: dict[str, str]) -> None:
    if not isinstance(answer, dict) or answer.get('type') != 'choice':
        fail(f"invalid response schema: answer '{qid}' is not a choice answer")
    options = set(criteria)
    if answer.get('choice') not in options:
        fail(f"invalid response schema: answer '{qid}' choice "
             f"{answer.get('choice')!r} not in options {sorted(options)}")
    probabilities = answer.get('probabilities')
    if not isinstance(probabilities, dict) or set(probabilities) != options:
        fail(f"invalid response schema: answer '{qid}' probabilities keys "
             f"!= options {sorted(options)}")
    values = list(probabilities.values())
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
               for value in values):
        fail(f"invalid response schema: answer '{qid}' probabilities has "
             f"non-numeric values {values!r}")
    total = sum(values)
    if not 1.0 - PROB_SUM_TOLERANCE <= total <= 1.0 + PROB_SUM_TOLERANCE:
        fail(f"invalid response schema: answer '{qid}' probabilities sum "
             f"{total!r} outside 1±{PROB_SUM_TOLERANCE}")
    confidence = answer.get('confidence')
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) \
            or not 0.0 <= confidence <= 1.0:
        fail(f"invalid response schema: answer '{qid}' confidence "
             f"{confidence!r} not in [0, 1]")


def validate_score_answer(qid: str, answer: Any, criteria: list[str]) -> None:
    """score 답 검증 — 레벨 인덱스 문자열 키 확률 분포·legend·confidence(스키마는 r0 실측 50회 실증)."""
    if not isinstance(answer, dict) or answer.get('type') != 'score':
        fail(f"invalid response schema: answer '{qid}' is not a score answer")
    levels = {str(index) for index in range(len(criteria))}
    score = answer.get('score')
    if not isinstance(score, (int, float)) or isinstance(score, bool) \
            or not -PROB_SUM_TOLERANCE <= score <= len(criteria) - 1 + PROB_SUM_TOLERANCE:
        fail(f"invalid response schema: answer '{qid}' score "
             f"{score!r} not in [0, {len(criteria) - 1}]")
    probabilities = answer.get('probabilities')
    if not isinstance(probabilities, dict) or set(probabilities) != levels:
        fail(f"invalid response schema: answer '{qid}' probabilities keys "
             f"!= levels {sorted(levels)}")
    values = list(probabilities.values())
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
               for value in values):
        fail(f"invalid response schema: answer '{qid}' probabilities has "
             f"non-numeric values {values!r}")
    total = sum(values)
    if not 1.0 - PROB_SUM_TOLERANCE <= total <= 1.0 + PROB_SUM_TOLERANCE:
        fail(f"invalid response schema: answer '{qid}' probabilities sum "
             f"{total!r} outside 1±{PROB_SUM_TOLERANCE}")
    legend = answer.get('legend')
    if not isinstance(legend, dict) or set(legend) != levels \
            or not all(isinstance(text, str) for text in legend.values()):
        fail(f"invalid response schema: answer '{qid}' legend keys "
             f"!= levels {sorted(levels)} or has non-string values")
    confidence = answer.get('confidence')
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) \
            or not 0.0 <= confidence <= 1.0:
        fail(f"invalid response schema: answer '{qid}' confidence "
             f"{confidence!r} not in [0, 1]")


def validate_noul_answer(qid: str, answer: Any) -> None:
    """noul 답 검증 — confidence 필드는 없다(choice와 분리 검증)."""
    if not isinstance(answer, dict) or answer.get('type') != 'noul':
        fail(f"invalid response schema: answer '{qid}' is not a noul answer")
    value = answer.get('noul')
    if not isinstance(value, (int, float)) or isinstance(value, bool) \
            or not 0.0 <= value <= 1.0:
        fail(f"invalid response schema: answer '{qid}' noul {value!r} not in [0, 1]")


def validate_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        fail("invalid response schema: response 'usage' is not an object")
    for key in ('input_tokens', 'output_tokens'):
        value = usage.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            fail(f"invalid response schema: response 'usage.{key}' is not an integer")
    return usage


def noul_risk_positive(value: float) -> bool:
    """위험 은닉 변수 — dead zone은 보수적으로 양성 처리한다(하향 기각 방향)."""
    return value >= NOUL_DEAD_ZONE[0]


def noul_confirmed(value: float) -> bool:
    """확신 판정 — dead zone은 확신으로 인정하지 않는다(축소 금지 방향)."""
    return value >= NOUL_DEAD_ZONE[1]


def build_fanout_recommendation(answers: dict[str, Any]) -> dict[str, Any]:
    """fanout 복합 점수 합성 — 임계 판정만 하고 보간하지 않는다(계획 P3-D2).

    complexity.score는 확률 분포의 기댓값(레벨 0~4)이다. 렌즈 수는 스코어 임계로만 정하고,
    safe 미확신(거짓·dead zone 포함)은 최대 렌즈 3을 강제한다(거부권 — gap G2 계승).
    """
    complexity_answer = answers['complexity']
    probabilities = complexity_answer['probabilities']
    score = sum(int(level) * value for level, value in probabilities.items())
    safe_noul = answers['safe']['noul']
    lens_forced_reason = None if noul_confirmed(safe_noul) else 'safe_not_confirmed'
    if lens_forced_reason is None:
        lens_count = (3 if score >= LENS_THRESHOLDS[0]
                      else 2 if score >= LENS_THRESHOLDS[1] else 1)
    else:
        lens_count = 3
    return {'stage': 'fanout',
            'action': {3: 'keep_all', 2: 'reduce', 1: 'minimal'}[lens_count],
            'lens_count': lens_count, 'lens_forced_reason': lens_forced_reason,
            'complexity': {'score': score, 'confidence': complexity_answer['confidence'],
                           'normalized': score / (len(COMPLEXITY_LEVELS) - 1),
                           'probabilities': probabilities},
            'safe_noul': safe_noul, 'safe_to_prune': noul_confirmed(safe_noul)}


def build_recommendation(mode: str, stage: str | None,
                         answers: dict[str, Any]) -> dict[str, Any]:
    if mode == 'tier':
        tier_answer = answers['tier']
        risk_values = {key: answers[f'risk_{key}']['noul'] for key in RISK_KEYS}
        risks = {key: noul_risk_positive(value) for key, value in risk_values.items()}
        return {'tier': tier_answer['choice'],
                'confidence': tier_answer['confidence'],
                'probabilities': tier_answer['probabilities'],
                'risks': risks, 'risk_values': risk_values,
                'any_risk': any(risks.values())}
    if stage == 'fanout':
        return build_fanout_recommendation(answers)
    choice_answer = answers[stage or '']
    safe_noul = answers['safe']['noul']
    return {'stage': stage, 'action': choice_answer['choice'],
            'confidence': choice_answer['confidence'],
            'probabilities': choice_answer['probabilities'],
            'safe_noul': safe_noul, 'safe_to_prune': noul_confirmed(safe_noul)}


def audit_target(save: str, mode: str) -> Path:
    """디렉터리(또는 .json 아닌 미존재 경로)면 <dir>/<mode>-<UTC스탬프>.json, 파일 경로면 그대로."""
    path = Path(save)
    if path.suffix == '.json' or (path.exists() and path.is_file()):
        return path
    # 마이크로초 포함 — 동일초 연속 호출이 감사 파일을 덮어쓰지 않는다(gap L1)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    return path / f'{mode}-{stamp}.json'


def write_audit_file(path: Path, mode: str, endpoint: str, model: str, state: str,
                     questions: dict[str, Any], raw: str, parsed: dict[str, Any]) -> None:
    """감사 저장 — request는 state·questions만 담는다(Authorization·API 키 미포함)."""
    timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    audit = {'timestamp': timestamp, 'mode': mode, 'endpoint': endpoint, 'model': model,
             'request': {'state': state, 'questions': questions},
             'response_raw': raw, 'parsed': parsed}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError as error:
        fail(f'audit save failed: {error}')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='jev 판단 계층 CLI — TypeSafe 판단형 LLM 예판 클라이언트')
    parser.add_argument('mode',
                        choices=('tier', 'prune', 'escalation', 'memory-gate', 'stall',
                                 *jev_modes.EXTRA_MODES),
                        help='판단 모드')
    parser.add_argument('statement',
                        help="작업 서술 원문 또는 모드 입력(stall은 신호 JSON 원문·경로, "
                             "'-'는 stdin에서 읽는다)")
    parser.add_argument('--stage', choices=('plan', 'fanout', 'review'),
                        help='prune 모드의 대상 단계')
    parser.add_argument('--rules-file',
                        help='escalation 모드 — 허용 규칙 JSON 파일({case_id: 설명})')
    parser.add_argument('--memory-file',
                        help="memory-gate 모드 — 기억 파일 경로('-'는 stdin 전체)")
    parser.add_argument('--top-k', type=int, default=5,
                        help='memory-gate 모드 — selected 상위 N줄(기본 5)')
    parser.add_argument('--tracks-file',
                        help="dup 모드 — 트랙 목록 JSON 파일({track_id: 제목}, '-'는 stdin)")
    parser.add_argument('--instructions',
                        help="guard 모드 — 지시 섹션 원문·경로('-'는 stdin 전체)")
    parser.add_argument('--roles-file',
                        help="route 모드 — 역할 프로파일 JSON 파일({'roles': [...]}, "
                             "'-'는 stdin, 미지정 시 내장 6종)")
    parser.add_argument('--save', help='감사 저장 경로(디렉터리 또는 .json 파일)')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT,
                        help=f'HTTP 타임아웃 초(기본 {DEFAULT_TIMEOUT})')
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT,
                        help='테스트 전용 — loopback 한정 가드 적용(결정 D5)')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='요청 model 이름')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        fail(f'--timeout must be a positive finite number, got {args.timeout!r}')
    mode_input = None
    if args.mode in ('escalation', 'memory-gate', 'stall'):
        # 신규 모드는 입력 파싱·질문 생성·recommendation 합성만 jev_modes에 위임하고
        # 호출·검증·감사는 기존 파이프라인을 그대로 경유한다(계획 §2.1)
        mode_input = jev_modes.parse_mode_input(
            args.mode, args.statement, rules_file=args.rules_file,
            memory_file=args.memory_file, top_k=args.top_k, stdin_text=read_stdin_text)
        state = mode_input['state']
    elif args.mode in jev_modes.EXTRA_MODES:
        # 채택 판정 7종 — 입력 파싱·질문 생성·recommendation 합성은 jev_modes 별도 함수가
        # 담당하고 호출·검증·감사는 기존 파이프라인을 그대로 경유한다(계획 jev-cli8 §2.5)
        mode_input = jev_modes.parse_extra_input(
            args.mode, args.statement, tracks_file=args.tracks_file,
            instructions=args.instructions, roles_file=args.roles_file,
            stdin_text=read_stdin_text)
        state = mode_input['state']
    elif args.statement == '-':
        state = read_stdin_text()
    else:
        state = args.statement
    guard_endpoint(args.endpoint)
    api_key = os.environ.get('TYPESAFE_API_KEY')
    if not api_key:
        fail('TYPESAFE_API_KEY is not set — HTTP 호출 없이 폴백한다(jev는 선택 계층)')
    if args.mode == 'prune' and not args.stage:
        fail('prune 모드에는 --stage {plan|fanout|review}가 필요하다')
    if args.mode in jev_modes.EXTRA_MODES:
        questions = jev_modes.build_extra_questions(args.mode, mode_input)
    else:
        questions = (jev_modes.build_mode_questions(args.mode, mode_input)
                     if mode_input is not None else build_questions(args.mode, args.stage))
    body = {'state': state, 'model': args.model, 'questions': questions}
    raw = call_api(args.endpoint, api_key, body, args.timeout)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        fail(f'response is not valid JSON: {error}')
    model, answers, usage = validate_response(payload, questions)
    audit_path = audit_target(args.save, args.mode) if args.save else None
    if args.mode in jev_modes.EXTRA_MODES:
        recommendation = jev_modes.build_extra_recommendation(
            args.mode, mode_input, answers, noul_confirmed)
    else:
        recommendation = (jev_modes.build_mode_recommendation(
            args.mode, mode_input, answers, noul_confirmed)
            if mode_input is not None else build_recommendation(args.mode, args.stage, answers))
    parsed = {'ok': True, 'mode': args.mode, 'model': model,
              'recommendation': recommendation,
              'usage': usage, 'audit': str(audit_path) if audit_path is not None else None}
    if audit_path is not None:
        write_audit_file(audit_path, args.mode, args.endpoint, model,
                         state, questions, raw, parsed)
    print(json.dumps(parsed, ensure_ascii=False))


if __name__ == '__main__':
    main()
