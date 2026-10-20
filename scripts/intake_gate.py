#!/usr/bin/env python3
"""인테이크 게이트(① 기본 엔진) — 발화 6항목 신호 점검·결정적 분류.

모든 코딩 착수 전 항상 발동하는 필수 계층(SKILL.md §0)이다. 사용자 발화를 재작성하지
않는다(원문 보존 계약) — 출력은 병렬 신호 블록(6항목 충족/누락·모호도·action 분류)이고
utterance는 입력 원문이 바이트 그대로 감사·stdout에 실린다. 키워드 사전 기반의 결정론
판정기로 stdlib만 사용하며(jev·API·네트워크 무의존) 미러 동봉 대상이다.

action 규칙의 단일 소스(§3.5 우선순위 — compute_action)이며, ② 옵션 엔진(jev intake)도
이 모듈의 compute_action·감지기를 import해 ①② 판정 정합을 유지한다. 우선순위:
  0 --urgent(§1 긴급 트랙 — 메인 판정 전달) → advisory 강하(질문 0)
  1 --task-active ∧ 루프 동사 → loop_pass(질문 0 — 티어 승계는 메인 영역)
  2 지시 대명사·직전 참조 → context_dep(누락 항목을 맥락 기준 충족으로 간주)
  3 target 또는 task_type 누락 → hard(질문 1개 의무)
  4 잔여 4항목 누락 ≥3 → soft(질문 min(누락수, 3))
  5 그 외 → advisory(질문 0)

exit 코드(게이트 어휘): 0=판정 성공(action 무관 — hard 제외·--save 저장 실패 포함) /
1=hard(질문 1개 의무 — 질문 없이 진행 금지) / 2=무효 입력 전용(빈 발화·인자 위반 —
stderr 'FAIL intake gate: <사유>'·이유 붙은 bypass). --save 저장 실패는 판정 폐기가
아니라 감사 누락이다 — exit 0(또는 hard면 1) 유지·saved_to:null·stderr 경고.

--save DIR 감사(jev --save 계약 평행): 모든 action에서 기록하며 감사 파일은 과업 폴더
(docs/task-id/<task-id>/)와 수명을 같이한다. 문맥상 한 줄 표기(advisory 누락 목록·
컨텍스트 의존)는 stdout JSON의 note 필드로 전달한다 — stdout은 단일 JSON 1줄 원칙.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

ITEM_KEYS = ('target', 'task_type', 'scope', 'risk', 'verification', 'pattern_ref')
REMAINING_KEYS = ('scope', 'risk', 'verification', 'pattern_ref')
SOFT_QUESTION_CAP = 3   # 연질 질문 상한(§3.3 — min(누락 잔여항목 수, 3))

# 항목별 판정 기준 문구 — ② 옵션 엔진(jev_intake.py)의 noul 질문과 바이트 수준 동일 관리.
ITEM_DESCRIPTIONS = {
    'target': '발화가 작업 대상을 지칭한다 — 파일·모듈·경로·컴포넌트 등 구체적 대상이 명시돼 있다',
    'task_type': '발화가 작업 유형 동사를 포함한다 — 수정(fix)·추가(add)·리팩터링(refactor)·리뷰(review)·계획(plan)',
    'scope': '발화가 범위 경계를 정한다 — 무엇을 하지 않는지(제외·금지·한정)가 명시돼 있다',
    'risk': '발화가 위험 단서를 언급한다 — 보안·인증·게이트·요청 경로·스키마·산출 문서',
    'verification': '발화가 검증 기준을 제시한다 — 테스트·빌드·통과·확인 조건',
    'pattern_ref': '발화가 기존 패턴을 참조한다 — 기존 코드·컨벤션·관례 따르기',
}

# 키워드 사전(한·영 혼용·부분 문자열 매칭) — 1곳 격리. 350줄 초과 예상 시
# intake_lexicon.py 분할 seam(§11). 영어 키는 소문자 비교 대상이다.
_ITEM_KEYWORDS = {
    'target': ('파일', '모듈', '스크립트', '컴포넌트', '함수', '클래스', '테이블',
               '엔드포인트', 'readme', 'docs/', 'src/', 'agents/'),
    'task_type': ('고쳐', '수정', 'fix', '버그', '추가', 'add', 'append', '리팩터',
                  '리팩토링', 'refactor', '리뷰', 'review', '계획', 'plan', '작성',
                  '생성', 'create', '구현', 'implement', '삭제', 'remove', '정리'),
    'scope': ('제외', '금지', '안 함', '안함', '하지 않', '범위', '한정', '제한',
              'skip', 'exclude', 'except', 'only'),
    'risk': ('보안', '인증', '게이트', '요청 경로', '요청경로', '라우팅', '필터',
             '인터셉터', '스키마', '산출 문서', '산출문서', '설계서', '계획서',
             'security', 'auth', 'schema', '권한'),
    'verification': ('테스트', '검증', '확인', '통과', '빌드', '기준', 'verify',
                     'test', '체크', 'check', '커버리지', '재현'),
    'pattern_ref': ('기존', '컨벤션', '관례', '패턴', '참조', '참고', '따라', '따름',
                    'convention', 'pattern', 'existing'),
}
# 파일 확장자·경로 형태 — target 추가 판정기("main.py 고쳐줘"류 지칭).
_TARGET_FILE_PATTERN = re.compile(r'\.\w{1,5}\b|\w+/\w+')

# 규칙 A — 지시 대명사·직전 결과 참조 감지어(확정 설계 6).
PRONOUN_KEYWORDS = ('이거', '그거', '저거', '방금', '결과 보고', '이대로', '위에서',
                    '그 파일', '그 코드', '그 부분', '이 파일', '아까', '직전', '바로 위')
# 규칙 B — 이터레이션 루프 동사(확정 설계 7).
LOOP_KEYWORDS = ('고쳐', '다시', '아직 안 돼', '여전히', '또', '재시도')


def fail(reason: str) -> NoReturn:
    print(f'FAIL intake gate: {reason}', file=sys.stderr)
    raise SystemExit(2)


def detect_item(key: str, text: str) -> bool:
    """항목 1개 판정기 — 키워드 부분 문자열 매칭(target은 파일형 정규식 병용)."""
    lowered = text.lower()
    if any(keyword in lowered for keyword in _ITEM_KEYWORDS[key]):
        return True
    return key == 'target' and _TARGET_FILE_PATTERN.search(text) is not None


def detect_items(text: str) -> dict[str, str]:
    """6항목 원문 판정 — present|missing."""
    return {key: ('present' if detect_item(key, text) else 'missing')
            for key in ITEM_KEYS}


def detect_pronoun(text: str) -> bool:
    """규칙 A 감지기 — 지시 대명사·직전 결과 참조."""
    return any(keyword in text for keyword in PRONOUN_KEYWORDS)


def detect_loop_verb(text: str) -> bool:
    """규칙 B 감지기 — 수정-재검증 루프 동사."""
    return any(keyword in text for keyword in LOOP_KEYWORDS)


def mark_context_satisfied(items: dict[str, str]) -> dict[str, str]:
    """규칙 A — 원문 기준 missing 항목을 전부 맥락 기준 충족으로 마킹(신규 dict — 불변)."""
    return {key: ('context_satisfied' if status == 'missing' else status)
            for key, status in items.items()}


def recheck_with_context(items: dict[str, str], context_text: str) -> dict[str, str]:
    """--context 경로(규칙 A 비발동 시) — 맥락에서 발견된 항목만 context_satisfied."""
    return {key: ('context_satisfied' if status == 'missing'
                  and detect_item(key, context_text) else status)
            for key, status in items.items()}


def compute_action(items: dict[str, str], context_dep_signal: bool, task_active: bool,
                   urgent: bool, loop_signal: bool = False) -> tuple[str, int]:
    """§3.5 우선순위 — action·questions_max의 단일 소스(① 공유, ② import)."""
    if urgent:                                   # 규칙 0 — 긴급 면제(강하)
        return 'advisory', 0
    if task_active and loop_signal:              # 규칙 1 — 루프 프리패스
        return 'loop_pass', 0
    if context_dep_signal:                       # 규칙 2 — 맥락 의존
        return 'context_dep', 0
    if items['target'] == 'missing' or items['task_type'] == 'missing':
        return 'hard', 1                         # 규칙 3 — 경질(질문 1개 의무)
    remaining_missing = sum(1 for key in REMAINING_KEYS if items[key] == 'missing')
    if remaining_missing >= SOFT_QUESTION_CAP:
        return 'soft', min(remaining_missing, SOFT_QUESTION_CAP)   # 규칙 4 — 연질
    return 'advisory', 0                         # 규칙 5 — advisory 주석만


def build_note(items: dict[str, str], action: str, context_dep: bool) -> str | None:
    """표기(L4) — 컨텍스트 의존·advisory 누락 주석. ①② 공통 단일 소스(④리뷰 N1)."""
    if context_dep:
        return '컨텍스트 의존 — 원문+맥락 판정'
    if action == 'advisory':
        missing = [key for key, status in items.items() if status == 'missing']
        if missing:
            return f'인테이크 advisory: 누락 {", ".join(missing)} — 티어 판정 진행'
    return None


def classify(utterance: str, context_text: str, task_active: bool, urgent: bool,
             source: str = 'user') -> dict:
    """발화+맥락+플래그 → 감사 JSON 본체(--save 전 saved_to:null 상태)."""
    items = detect_items(utterance)
    context_dep = detect_pronoun(utterance)
    if context_dep:                              # 규칙 A — 전항목 충족 간주(§3.3)
        items = mark_context_satisfied(items)
    elif context_text:                           # --context 항목 단위 재검색
        items = recheck_with_context(items, context_text)
    loop_signal = detect_loop_verb(utterance)
    action, questions_max = compute_action(items, context_dep, task_active, urgent,
                                           loop_signal)
    missing = [key for key, status in items.items() if status == 'missing']
    missing_count = len(missing)
    result = {'ok': True, 'gate': 'intake', 'mode': 'basic', 'source': source,
              'items': items, 'missing_count': missing_count,
              'ambiguity_score': missing_count / len(ITEM_KEYS),
              'action': action, 'questions_max': questions_max,
              'context_dep': context_dep, 'task_active': task_active,
              'urgent': urgent, 'utterance': utterance, 'saved_to': None}
    note = build_note(items, action, context_dep)
    if note is not None:
        result['note'] = note
    return result


def read_stdin_text() -> str:
    """stdin 바이트 읽기 — UTF-8 엄격 디코드(jev read_stdin_text 계약 평행)."""
    try:
        return sys.stdin.buffer.read().decode('utf-8')
    except UnicodeDecodeError as error:
        fail(f'input is not valid UTF-8: {error}')
    except OSError as error:
        fail(f'input read failed: {error}')


def resolve_statement(spec: str) -> str:
    return read_stdin_text() if spec == '-' else spec


def resolve_context(spec: str) -> str:
    """--context — 맥락 요약 원문(인자·파일경로·stdin '-')."""
    if spec == '-':
        return read_stdin_text()
    path = Path(spec)
    if path.is_file():
        try:
            return path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as error:
            fail(f'context file read failed: {error}')
    return spec


def save_audit(save: str, result: dict) -> str | None:
    """감사 저장 — 모든 action 기록. 실패는 판정 폐기가 아니라 감사 누락(H3)."""
    path = Path(save)
    if path.suffix != '.json':
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = path / f'intake-{stamp}.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(result, saved_to=str(path)),
                                   ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError as error:
        print(f'경고: intake 감사 저장 실패 — 판정은 보존됐다: {error}', file=sys.stderr)
        return None
    return str(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='인테이크 게이트 — 발화 6항목 신호 점검·결정적 분류(항상 켬)')
    parser.add_argument('statement',
                        help="발화 원문('-'는 stdin에서 읽는다 — 재작성 없이 그대로 감사)")
    parser.add_argument('--context',
                        help="맥락 요약 원문·경로('-'는 stdin) — 누락 항목 항목 단위 재검색")
    parser.add_argument('--task-active', action='store_true',
                        help='진행 중 과업의 수정-재검증 턴(메인 세션 판정 전달 — 규칙 B)')
    parser.add_argument('--urgent', action='store_true',
                        help='§1 긴급 트랙 발화(메인 판정) — advisory 강하(규칙 0)')
    parser.add_argument('--source', choices=('user', 'auto'), default='user',
                        help='발화 기원 — 자율 착수 과업은 auto(기원 투명 표기)')
    parser.add_argument('--save', help='감사 저장 경로(디렉터리 또는 .json 파일)')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    utterance = resolve_statement(args.statement)
    if not utterance.strip():
        fail('빈 발화 — 유효한 발화 원문이 필요하다')
    context_text = resolve_context(args.context) if args.context is not None else ''
    result = classify(utterance, context_text, args.task_active, args.urgent,
                      args.source)
    if args.save:
        result['saved_to'] = save_audit(args.save, result)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(1 if result['action'] == 'hard' else 0)


if __name__ == '__main__':
    main()
