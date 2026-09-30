#!/usr/bin/env python3
"""r29 루프 탈출 게이트(neverstuck) CLI — 반복 실패 루프의 결정론 '무장 판정'.

증상 패치 루프(같은 수정 무브류의 반복 실패 — 이슈 5개 처리가 10개로 증식)의
영구 예방 장치다. 시도 이력 JSON을 받아 무장(armed — neverstuck 프로토콜 진입
의무: 소급 예측·Stuck Packet·메커니즘 가설·판별 실험 1개 계약) 여부를 판정하고,
무장 시 contract_reminder(③재구현 프롬프트 주입용 고정 계약 요약)를 노출한다.
판정은 결정론이다 — jev·API·git·환경·외부 파일(PROTOCOL.md 포함) 무의존,
표준 라이브러리만으로 자기완결한다. 훅이 없다 — 무장은 사건 기반(동일 무브류
3회 실패·S7 관측 시점)이라 SessionStart/PreToolUse 같은 시점 트리거가 없으며,
호출 주체는 이력을 관측한 실행 주체다(이력 파일은 즉석 JSON — state.json 신규
필드 0, 감사는 --save 과업 폴더).

입력(--history FILE 또는 - = stdin): {"goal"(선택), "preference_domain"(bool,
선택), "attempts":[{move_class(필수 str), outcome("worked"|"failed" 필수),
knob/value/context(선택 스칼라 str|int|float|bool), declared_search(bool 선택),
note(선택)}]}. **null은 결손이다** — knob·value·context의 null은 키 부재와
동등 취급(D6). 비스칼라(배열·객체) 기재·필수 누락·outcome 이형값·비bool
플래그(declared_search:1·preference_domain:"true" — 참/거짓은 JSON bool
리터럴만 허용)·NaN/Infinity 리터럴(parse_constant 거부 — 유한 스칼라만 값이다)·
비UTF-8 바이트(UnicodeDecodeError도 무효 입력 — exit 1 armed 어휘 오염 방지,
GAP-1)는 전체 거부 — 부분 판정의 모호성 제거.

판정(plan §1.4): (1) preference_domain=true → 면제 not-armed(s7_evaluable:
false — 1단계 단락, S7을 평가하지 않는다) (2) effective = declared_search:true
제외(자동 판정은 면제만 가능 — 단죄 불가) (3) S7 — effective 중 knob·value·
context 완비 worked를 knob별 그룹핑, 같은 그룹에 값·맥락이 모두 상이한 쌍 →
즉시 무장(s7_hard_signal, failed 유무 무관) (4) 같은 무브류 failed ≥3 → 무장
(three_attempt_gate, S7도 성립 시 s7 우선 보고) (5) 아니면 not-armed(Never
원칙 — 1~2회 실패 미발동, failed 3 엄격 카운트). 값 상이 판정은 타입 클래스
D1: bool⊥수치(int·float 통합)⊥str⊥기타 — 같은 클래스 안에서만 ==(30 vs 30.0
동일), 클래스가 다르면 항상 상이(True vs 1·30 vs "30" 상이). 값과 맥락 비교에
동일 규칙을 적용하며 knob 그룹핑 키도 동일 클래스로 분리한다. s7_evaluable
(전역 스코프, D3): 완비 worked 그룹이 1개라도 있으면 true, 0이면 false(판정
불능 투명 표기 — 미감지 방향 한계). trigger=s7_hard_signal ⇒ s7_evaluable:true
(삼중 게이트 무장과는 독립 — F1).

종료코드: 0 not-armed(정상 진행, 추가 시도 허용) · 1 armed(ok:true ∧
flags:["armed"] — 프로토콜 진입 의무, jev의 exit 1 폴백과 정반대, verify_pin·
worktree_gate·tree_gate와 동일 어휘) · 2 무효 입력(stderr `FAIL neverstuck
gate: <사유>`, stdout 없음 — --save 실패만 stdout JSON saved_to:null 보존 후
exit 2, 검사 결과를 버리지 않는다) · 3 미사용(결정론 게이트 — 판단 계층 상향
경로 없음). 응답은 stdout 단일 JSON — attempts 원본 배열을 항상 포함(R3-H2 —
--save 감사 파일이 세션 경계를 넘는 이력 원본이 된다), not-armed도 --save 동일
기록(armed:false 감사 — 면제·미달 근거 보존).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATE = 'neverstuck-gate'
EXIT_PASS = 0
EXIT_ARMED = 1
EXIT_CONFIG = 2
TRIGGER_S7 = 's7_hard_signal'
TRIGGER_THREE = 'three_attempt_gate'
SCALAR_TYPES = (str, int, float, bool)
OUTCOMES = ('worked', 'failed')

CONTRACT_REMINDER_TEMPLATE = (
    'neverstuck 무장: {target}은 전부 밴한다(근접 변형 포함 — 맥락별 룩업테이블·과거값 평균·보정항·시작시 자동피팅). '
    '다음 시도 전 의무: (1) 과거 각 시도가 정확히 그렇게 작동한 이유를 전부 설명하는 소급 예측 — 못 하면 기각 '
    '(2) Stuck Packet 6필드 작성(GOAL/ATTEMPT LOG/OBSERVATIONS/VARIABLES/CONSTRAINTS/ACCESS INVENTORY) '
    '(3) 메커니즘 가설 2–3개(값 아님·서명사실 S-a~S-d를 전부 동시 설명하는 모델만) '
    '(4) 판별 실험 정확히 1개 + 판정규칙("결과 X⇒H1") 사전 선언. '
    '수렴 계약: C1(모든 상수 출처 명시) ∧ C2(이력 소급 예측) — 둘 다 아니면 기각, 2차 튜닝 패스 금지. '
    '회피값은 [loop-bait — D 실험 게이트] 태그 없이 제출 금지(삭제는 금지, 사용자 재량). '
    '예산: 보고서 2라운드 상한 후 강제 에스컬레이션(계측 → 서드파티 소스 정돈·grep 문자열 제공 → 통제 프로빙 → 인간 질문 초안).')


class GateConfigError(Exception):
    """무효 입력 — exit 2(이유가 붙은 bypass)로 변환한다."""


def fail_config(reason: str) -> None:
    print(f'FAIL neverstuck gate: {reason}', file=sys.stderr)
    raise SystemExit(EXIT_CONFIG)


# ---------------------------------------------------------------- 값 비교 (D1)

def type_class(value: Any) -> str:
    """D1 타입 클래스 — bool⊥수치(int·float 통합)⊥str⊥기타."""
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, (int, float)):
        return 'number'
    if isinstance(value, str):
        return 'str'
    return 'other'


def values_same(left: Any, right: Any) -> bool:
    """같은 클래스 안에서만 ==(30 vs 30.0 동일), 클래스가 다르면 항상 상이."""
    if type_class(left) != type_class(right):
        return False
    return left == right


def values_differ(left: Any, right: Any) -> bool:
    return not values_same(left, right)


# ---------------------------------------------------------------- 입력·검증

def reject_constant(name: str) -> float:
    """json parse_constant 거부 — NaN/Infinity는 스키마 위반(F3)."""
    raise ValueError(f'비표준 수 리터럴 {name}은 허용되지 않는다(유한 스칼라만 값이다)')


def load_history(source: str) -> dict[str, Any]:
    """--history FILE|- 로드 — 파일 오류·비UTF-8·파손 JSON·비객체는 전부 exit 2."""
    if source == '-':
        origin = 'stdin'
        try:
            text = sys.stdin.read()
        except UnicodeDecodeError as error:
            raise GateConfigError(f'이력 입력({origin})이 UTF-8 텍스트가 아니다: {error}') from error
    else:
        origin = source
        try:
            text = Path(source).read_text(encoding='utf-8')
        except OSError as error:
            raise GateConfigError(f'이력 파일을 읽을 수 없다: {error}') from error
        except UnicodeDecodeError as error:
            raise GateConfigError(f'이력 파일({origin})이 UTF-8 텍스트가 아니다: {error}') from error
    try:
        data = json.loads(text, parse_constant=reject_constant)
    except ValueError as error:
        raise GateConfigError(f'이력 JSON 파싱 실패({origin}): {error}') from error
    except RecursionError as error:
        # 심층 중첩 JSON — RecursionError도 무효 입력(GAP-5 — exit 1 어휘 오염 방지).
        raise GateConfigError(f'이력 JSON 중첩이 너무 깊다({origin}): {error}') from error
    if not isinstance(data, dict):
        raise GateConfigError('이력 최상위는 JSON 객체여야 한다')
    return data


def validate_scalar(entry: dict[str, Any], field: str, where: str) -> None:
    """knob/value/context — null은 결손(D6), 비스칼라는 exit 2."""
    raw = entry.get(field)
    if raw is None:
        return
    if not isinstance(raw, SCALAR_TYPES):
        raise GateConfigError(
            f'{where} — {field}는 스칼라(str|int|float|bool)여야 한다: {type(raw).__name__}')


def validate_history(data: dict[str, Any]) -> list[dict[str, Any]]:
    """스키마 검증 — 위반은 전체 거부(부분 판정 없음). 통과하면 attempts를 돌려준다."""
    preference = data.get('preference_domain')
    if preference is not None and not isinstance(preference, bool):
        raise GateConfigError(
            f"'preference_domain'은 bool이어야 한다(참/거짓은 JSON bool 리터럴만): {preference!r}")
    if 'attempts' not in data:
        raise GateConfigError("'attempts' 키가 없다 — 스키마 위반")
    attempts = data['attempts']
    if not isinstance(attempts, list):
        raise GateConfigError("'attempts'는 배열이어야 한다")
    for index, entry in enumerate(attempts):
        where = f'attempts[{index}]'
        if not isinstance(entry, dict):
            raise GateConfigError(f'{where} — 시도는 객체여야 한다')
        move_class = entry.get('move_class')
        if move_class is None:
            raise GateConfigError(f'{where} — move_class 누락(필수)')
        if not isinstance(move_class, str):
            raise GateConfigError(f'{where} — move_class는 문자열이어야 한다: {move_class!r}')
        outcome = entry.get('outcome')
        if outcome not in OUTCOMES:
            raise GateConfigError(f'{where} — outcome은 worked|failed여야 한다: {outcome!r}')
        for field in ('knob', 'value', 'context'):
            validate_scalar(entry, field, where)
        declared = entry.get('declared_search')
        if declared is not None and not isinstance(declared, bool):
            raise GateConfigError(
                f"{where} — 'declared_search'는 bool이어야 한다(참/거짓은 JSON bool 리터럴만): {declared!r}")
    return attempts


# ---------------------------------------------------------------- 판정 (§1.4)

def aggregate_move_classes(effective: list[dict[str, Any]]) -> list[dict[str, int]]:
    """effective 한정 집계(F5 — declared 전용 무브류 미표시), 첫 등장 순."""
    order: list[str] = []
    failed: dict[str, int] = {}
    worked: dict[str, int] = {}
    for entry in effective:
        move_class = entry['move_class']
        if move_class not in failed:
            order.append(move_class)
            failed[move_class] = 0
            worked[move_class] = 0
        if entry['outcome'] == 'failed':
            failed[move_class] += 1
        else:
            worked[move_class] += 1
    return [{'move_class': move_class, 'failed': failed[move_class],
             'worked': worked[move_class]} for move_class in order]


def dedup_pairs(entries: list[tuple[Any, Any]]) -> list[tuple[Any, Any]]:
    """(value, context) 중복 제거 — D1 동등 기준, 입력순 유지(F5)."""
    deduped: list[tuple[Any, Any]] = []
    for pair in entries:
        if not any(values_same(pair[0], kept[0]) and values_same(pair[1], kept[1])
                   for kept in deduped):
            deduped.append(pair)
    return deduped


def evaluate_s7(effective: list[dict[str, Any]]) -> tuple[bool, tuple[Any, list[dict[str, Any]]] | None]:
    """S7 판정 — (s7_evaluable, 무장 시 (knob, working_values)·비무장 None).

    완비 = worked ∧ knob·value·context 전부 결손 아님. 그룹핑 키는
    (타입클래스, knob) — D1과 동일 기준으로 knob을 분리한다. 전역 스코프(D3):
    완비 그룹 ≥1이면 evaluable, 상이쌍 발견 무장 시 그 knob의 완비 worked 전체를
    중복 제거·입력순으로 열거한다(F5).
    """
    groups: dict[tuple[str, Any], list[tuple[Any, Any]]] = {}
    order: list[tuple[str, Any]] = []
    for entry in effective:
        if entry.get('outcome') != 'worked':
            continue
        knob, value, context = entry.get('knob'), entry.get('value'), entry.get('context')
        if knob is None or value is None or context is None:
            continue  # 미완비 — knob 결손 worked도 미완비 취급
        key = (type_class(knob), knob)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((value, context))
    if not order:
        return False, None
    for key in order:
        entries = dedup_pairs(groups[key])
        for index in range(len(entries)):
            for prior in entries[:index]:
                if (values_differ(entries[index][0], prior[0])
                        and values_differ(entries[index][1], prior[1])):
                    knob = key[1]
                    return True, (knob, [{'value': value, 'context': context}
                                         for value, context in entries])
    return True, None


def json_scalar(value: Any) -> str:
    """contract_reminder 내 값 직렬화 — JSON 규칙 그대로(F5: str 따옴표·수치 그대로)."""
    return json.dumps(value, ensure_ascii=False)


def build_contract_reminder(trigger: str, armed_on: dict[str, Any]) -> str:
    """치환 템플릿 — three_attempt는 무브류 쉼표 열거, s7은 knob 값@맥락·상이쌍 전부."""
    if trigger == TRIGGER_S7:
        pairs = '·'.join(f"{json_scalar(item['value'])}@{item['context']}"
                         for item in armed_on['working_values'])
        target = f"knob {armed_on['knob']}의 값 {pairs}"
    else:
        target = '무브류 ' + ', '.join(armed_on['move_classes'])
    return CONTRACT_REMINDER_TEMPLATE.format(target=target)


def judge(data: dict[str, Any], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """§1.4 의사코드 그대로 — 1단계 면제 → S7 우선 → 3회 게이트 → not-armed."""
    preference = data.get('preference_domain', False)
    total = len(attempts)
    effective = [entry for entry in attempts
                 if entry.get('declared_search') is not True]
    skipped = total - len(effective)
    exemptions = ['preference_domain'] if preference else []
    per_move_class = aggregate_move_classes(effective)

    armed = False
    trigger = None
    armed_on = None
    s7_evaluable = False
    if not preference:
        # 1단계 최우선 — 취향 바운더리는 S7·3회 게이트를 평가하지 않는다(단락).
        s7_evaluable, s7_hit = evaluate_s7(effective)
        if s7_hit is not None:
            knob, working_values = s7_hit
            armed = True
            trigger = TRIGGER_S7
            armed_on = {'knob': knob, 'working_values': working_values}
        else:
            banned = [row['move_class'] for row in per_move_class if row['failed'] >= 3]
            if banned:
                armed = True
                trigger = TRIGGER_THREE
                armed_on = {'move_classes': banned}

    return {
        'ok': True,
        'gate': GATE,
        'armed': armed,
        'trigger': trigger,
        'goal': data.get('goal'),
        'attempts_total': total,
        'attempts_considered': len(effective),
        'declared_search_skipped': skipped,
        'preference_domain': bool(preference),
        'exemptions': exemptions,
        'per_move_class': per_move_class,
        'armed_on': armed_on,
        's7_evaluable': s7_evaluable,
        'flags': ['armed'] if armed else [],
        'contract_reminder': build_contract_reminder(trigger, armed_on) if armed else None,
        'attempts': attempts,
        'saved_to': None,
    }


# ---------------------------------------------------------------- 출력·감사

def save_result(save_dir: str, result: dict[str, Any]) -> tuple[str | None, str | None]:
    """판정 JSON 저장 — (경로, None) 또는 (None, 사유). r23·r24·r27 계약 평행."""
    try:
        directory = Path(save_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = directory / f'{GATE}-{stamp}.json'
        payload = {**result, 'saved_to': str(path)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    except OSError as error:
        return None, str(error)
    return str(path), None


def emit(result: dict[str, Any], save_dir: str | None) -> None:
    """stdout 단일 JSON + armed 기반 종료 — 저장 실패만 stdout 보존 후 exit 2
    (tree_gate 전례 정합 — 검사 결과를 버리지 않는다)."""
    if save_dir is not None:
        saved, save_error = save_result(save_dir, result)
        if saved is None:
            print(json.dumps(result, ensure_ascii=False))
            fail_config(f'--save 실패 — 판정 결과는 위 stdout JSON에 보존됐다: {save_error}')
        result = {**result, 'saved_to': saved}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(EXIT_ARMED if result['armed'] else EXIT_PASS)


class GateArgumentParser(argparse.ArgumentParser):
    """argparse 오류도 게이트 계약 어휘로 통일 — FAIL 접두 + exit 2."""

    def error(self, message: str) -> None:
        fail_config(message)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = GateArgumentParser(
        prog='neverstuck_gate.py',
        description='r29 루프 탈출 게이트(neverstuck) — 시도 이력 JSON의 무장 판정')
    parser.add_argument('--history', required=True,
                        help='시도 이력 JSON 파일 경로, 또는 - (stdin)')
    parser.add_argument('--save', default=None,
                        help='감사 JSON 저장 디렉터리(not-armed도 기록)')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        data = load_history(args.history)
        attempts = validate_history(data)
        result = judge(data, attempts)
    except GateConfigError as error:
        fail_config(str(error))
    emit(result, args.save)


if __name__ == '__main__':
    main()
