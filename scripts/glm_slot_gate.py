#!/usr/bin/env python3
"""GLM 슬롯 매핑 게이트 — GLM 백엔드 세션에서 역할 파일의 Claude 별칭이 Claude로 새는 것을 막는다.

배경(2026-10-18 사고): 역할 파일은 `model: opus|sonnet|haiku` 별칭을 쓴다. GLM 백엔드 세션에서
이 별칭은 `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` 매핑이 있어야만 GLM으로 해석된다.
매핑이 없거나 GLM이 아니면 서브에이전트가 Claude 모델로 돌아 Claude 사용량을 소모한다.

검사 계약 (환경변수 기준):
- `ANTHROPIC_BASE_URL`이 없거나 `api.anthropic.com`이면 Claude 세션 → 대상 아님(exit 2, bypass).
- GLM 세션이면 역할 파일에 쓰인 slot별 `ANTHROPIC_DEFAULT_<SLOT>_MODEL`이 SLOT_MODEL과 정확히 일치해야 한다.
  누락·불일치·Claude 모델 ID는 위반(exit 1).

종료코드: 0 통과 / 1 위반 / 2 대상 아님(bypass).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 사용자 확정 배분(2026-10-12, platforms/glm.md 이원 모델 정책).
# haiku 슬롯 = 반복 구현 경량 모델, sonnet·opus 슬롯 = GLM-5.3 고정.
SLOT_MODEL = {
    'haiku': 'glm-5.3-flash',
    'sonnet': 'glm-5.3',
    'opus': 'glm-5.3',
}
ANTHROPIC_HOST = 'api.anthropic.com'
FRONTMATTER_MODEL = re.compile(r'^model:\s*(\S+)\s*$', re.MULTILINE)


def is_glm_session(env):
    base = (env.get('ANTHROPIC_BASE_URL') or '').strip()
    return bool(base) and ANTHROPIC_HOST not in base


def role_slots(agents_dir):
    """역할 파일별 frontmatter model 별칭 → {파일명: slot}. 알 수 없는 별칭도 그대로 둔다."""
    slots = {}
    for path in sorted(Path(agents_dir).glob('*.md')):
        m = FRONTMATTER_MODEL.search(path.read_text(encoding='utf-8').split('---')[1])
        if m:
            slots[path.name] = m.group(1)
    return slots


def violations(env, agents_dir):
    """GLM 세션의 위반 목록. 대상이 아니면 빈 목록(호출자가 is_glm_session으로 먼저 판정)."""
    found = []
    used = sorted(set(role_slots(agents_dir).values()))
    for slot in used:
        if slot not in SLOT_MODEL:
            found.append(f'slot `{slot}`: 매핑 정책 밖 별칭 — GLM 세션에서 Claude로 해석될 수 있다')
            continue
        key = f'ANTHROPIC_DEFAULT_{slot.upper()}_MODEL'
        got = (env.get(key) or '').strip()
        want = SLOT_MODEL[slot]
        if not got:
            found.append(f'{key} 미설정 — `{slot}` 역할이 Claude {slot}로 스폰된다 (기대 {want})')
        elif got != want:
            found.append(f'{key}={got} — 기대값 {want}과 불일치')
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--agents-dir', default=str(ROOT / 'agents'))
    args = parser.parse_args(argv)
    env = dict(os.environ)
    if not is_glm_session(env):
        print('glm-slot-gate: bypass — GLM 세션 아님(ANTHROPIC_BASE_URL 부재 또는 Anthropic 호스트)')
        return 2
    found = violations(env, args.agents_dir)
    if found:
        print('glm-slot-gate: FAIL')
        for line in found:
            print(f'  - {line}')
        print('조치: platforms/glm.md "슬롯 매핑" 블록을 GLM 세션 env에 설정 후 세션 재시작.')
        return 1
    print('glm-slot-gate: PASS — 모든 역할 별칭이 GLM 모델로 매핑됨')
    return 0


if __name__ == '__main__':
    sys.exit(main())
