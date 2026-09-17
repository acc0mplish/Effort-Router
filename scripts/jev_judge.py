#!/usr/bin/env python3
"""jev 판단 계층 CLI — TypeSafe 판단형 LLM 예판 클라이언트(선택 가속기).

스키마 출처(가정 A1): https://docs.typesafe.ai/api (2026-09-18 조회, 계획 §0 확정 사실)
- 엔드포인트: POST {endpoint} · Authorization: Bearer $TYPESAFE_API_KEY · JSON
- 요청 body: state(작업 서술 원문) + model + questions(map — 응답도 같은 키로 돌아온다)
- choice 답 = {type, choice, probabilities(전 옵션, 합 1), confidence}
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
"""
from __future__ import annotations

import argparse
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

DEFAULT_ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
DEFAULT_MODEL = 'jev-latest'
DEFAULT_TIMEOUT = 8.0
LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}
NOUL_TRUE_THRESHOLD = 0.5  # noul ∈ [0,1] — 0.5 이상이면 true criteria 충족으로 해석한다
PROB_SUM_TOLERANCE = 0.05

RISK_KEYS = ('request_path', 'security_control', 'topology_unknown', 'output_document', 'gate_preset')

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
    'topology_unknown': '코드만으로 판별 불가한 배포 토폴로지·프록시 경계 변수가 있다',
    'output_document': '다운스트림 구현을 지시하는 산출 문서의 신규 작성·중대 개정이다',
    'gate_preset': '게이트 신설·변경, 보안·무결성 통제 변경, 기준선 봉인 문서에 해당한다',
}
STAGE_OPTIONS = {
    'plan': ('keep_full', 'thin_plan'),
    'fanout': ('keep', 'reduce'),
    'review': ('full_scope', 'narrow_scope'),
}
STAGE_CHOICE_DESCRIPTIONS = {
    'plan': {'keep_full': '심층 계획 스폰을 유지한다', 'thin_plan': '얇은 계획으로 축소한다'},
    'fanout': {'keep': '팬아웃 렌즈 구성을 유지한다', 'reduce': '팬아웃 렌즈를 축소한다'},
    'review': {'full_scope': '리뷰 전체 스코프를 유지한다', 'narrow_scope': '리뷰 스코프를 축소한다'},
}


def noul_question(description: str) -> dict[str, str]:
    return {'type': 'noul',
            'instructions': f'다음 진술이 해당하면 true, 아니면 false로 판단한다: {description}',
            'criteria': {'true': '해당한다', 'false': '해당하지 않는다'}}


def build_questions(mode: str, stage: str | None) -> dict[str, Any]:
    """호출 질문 맵을 만든다 — tier 1+은닉변수 5종 / prune 스테이지 choice+Noul safe."""
    if mode == 'tier':
        questions: dict[str, Any] = {
            'tier': {'type': 'choice',
                     'instructions': '작업 서술을 S/M/L/XL 작업 티어로 분류한다',
                     'criteria': dict(TIER_CRITERIA)}}
        questions.update({f'risk_{key}': noul_question(RISK_DESCRIPTIONS[key])
                          for key in RISK_KEYS})
        return questions
    options = STAGE_OPTIONS[stage or '']
    return {stage: {'type': 'choice',
                    'instructions': f'{stage} 단계의 실행 범위를 판단한다',
                    'criteria': {option: STAGE_CHOICE_DESCRIPTIONS[stage][option]
                                 for option in options}},
            'safe': noul_question('이 축소로도 과업 계약(요구·검증 커버리지)이 훼손되지 않는다')}


def fail(reason: str) -> NoReturn:
    print(f'FAIL jev judge: {reason}', file=sys.stderr)
    raise SystemExit(1)


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


def build_recommendation(mode: str, stage: str | None,
                         answers: dict[str, Any]) -> dict[str, Any]:
    if mode == 'tier':
        tier_answer = answers['tier']
        risks = {key: answers[f'risk_{key}']['noul'] >= NOUL_TRUE_THRESHOLD
                 for key in RISK_KEYS}
        return {'tier': tier_answer['choice'],
                'confidence': tier_answer['confidence'],
                'probabilities': tier_answer['probabilities'],
                'risks': risks, 'any_risk': any(risks.values())}
    choice_answer = answers[stage or '']
    return {'stage': stage, 'action': choice_answer['choice'],
            'confidence': choice_answer['confidence'],
            'probabilities': choice_answer['probabilities'],
            'safe_to_prune': answers['safe']['noul'] >= NOUL_TRUE_THRESHOLD}


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
    parser.add_argument('mode', choices=('tier', 'prune'), help='판단 모드')
    parser.add_argument('statement', help="작업 서술 원문 ('-'는 stdin에서 읽는다)")
    parser.add_argument('--stage', choices=('plan', 'fanout', 'review'),
                        help='prune 모드의 대상 단계')
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
    if args.statement == '-':
        # stdin은 바이트로 읽어 UTF-8 엄격 디코드한다(gap F3 확장). UTF-8 모드의
        # surrogateescape에서 sys.stdin.read()는 비UTF-8 바이트를 조용히 통과시키므로
        # — 무음 mojibake가 외부로 전송되는 경로를 환경과 무관하게 차단한다.
        try:
            state = sys.stdin.buffer.read().decode('utf-8')
        except UnicodeDecodeError as error:
            fail(f'statement is not valid UTF-8: {error}')
        except OSError as error:
            fail(f'statement read failed: {error}')
    else:
        state = args.statement
    guard_endpoint(args.endpoint)
    api_key = os.environ.get('TYPESAFE_API_KEY')
    if not api_key:
        fail('TYPESAFE_API_KEY is not set — HTTP 호출 없이 폴백한다(jev는 선택 계층)')
    if args.mode == 'prune' and not args.stage:
        fail('prune 모드에는 --stage {plan|fanout|review}가 필요하다')
    questions = build_questions(args.mode, args.stage)
    body = {'state': state, 'model': args.model, 'questions': questions}
    raw = call_api(args.endpoint, api_key, body, args.timeout)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        fail(f'response is not valid JSON: {error}')
    model, answers, usage = validate_response(payload, questions)
    audit_path = audit_target(args.save, args.mode) if args.save else None
    parsed = {'ok': True, 'mode': args.mode, 'model': model,
              'recommendation': build_recommendation(args.mode, args.stage, answers),
              'usage': usage, 'audit': str(audit_path) if audit_path is not None else None}
    if audit_path is not None:
        write_audit_file(audit_path, args.mode, args.endpoint, model,
                         state, questions, raw, parsed)
    print(json.dumps(parsed, ensure_ascii=False))


if __name__ == '__main__':
    main()
