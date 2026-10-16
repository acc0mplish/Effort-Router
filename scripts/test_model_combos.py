#!/usr/bin/env python3
"""r39 — 허용 모델·effort 조합 계약 테스트 (사용자 확정 2026-10-12).

허용 조합 밖(xhigh·low 등 임의 조합)이 역할 파일에 남으면 실패한다.
- Claude Code: agents/*.md 의 model(alias)·effort frontmatter
- Codex: platforms/codex-agents/*.toml 의 model·model_reasoning_effort
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_CLAUDE = {('opus', 'high'), ('sonnet', 'high'), ('haiku', 'high')}
ALLOWED_CODEX = {('gpt-6-luna', 'max'), ('gpt-6.1-sol', 'high'), ('gpt-6.1-sol', 'low')}
ALLOWED_GLM = {('glm-5.3', 'max'), ('glm-5.3', 'high'), ('glm-5.3-flash', 'max')}

FRONTMATTER_FIELD = re.compile(r'^(model|effort):\s*(\S+)\s*$', re.MULTILINE)
TOML_FIELD = re.compile(r'^(model|model_reasoning_effort)\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def read_claude_pairs():
    pairs = {}
    for path in sorted((ROOT / 'agents').glob('*.md')):
        fields = dict(FRONTMATTER_FIELD.findall(path.read_text(encoding='utf-8')))
        pairs[path.name] = (fields.get('model'), fields.get('effort'))
    return pairs


def read_codex_pairs():
    pairs = {}
    for path in sorted((ROOT / 'platforms' / 'codex-agents').glob('*.toml')):
        found = dict(TOML_FIELD.findall(path.read_text(encoding='utf-8')))
        pairs[path.name] = (found.get('model'), found.get('model_reasoning_effort'))
    return pairs


class ClaudeCombosTests(unittest.TestCase):
    def test_every_agent_uses_allowed_claude_combo(self):
        pairs = read_claude_pairs()
        self.assertTrue(pairs, 'agents/*.md 가 없다')
        for name, pair in pairs.items():
            with self.subTest(agent=name):
                self.assertIn(pair, ALLOWED_CLAUDE, f'{name}: {pair} 는 허용 조합 밖')


class CodexCombosTests(unittest.TestCase):
    def test_every_codex_role_uses_allowed_codex_combo(self):
        pairs = read_codex_pairs()
        self.assertTrue(pairs, 'platforms/codex-agents/*.toml 이 없다')
        for name, pair in pairs.items():
            with self.subTest(role=name):
                self.assertIn(pair, ALLOWED_CODEX, f'{name}: {pair} 는 허용 조합 밖')

    def test_general_work_defaults_to_luna_max(self):
        pairs = read_codex_pairs()
        for role in ('coder-medium.toml', 'implement-med.toml'):
            with self.subTest(role=role):
                self.assertEqual(pairs[role], ('gpt-6-luna', 'max'))


class ComboSetTests(unittest.TestCase):
    def test_allowed_sets_match_user_decision(self):
        self.assertEqual(len(ALLOWED_CLAUDE | ALLOWED_CODEX | ALLOWED_GLM), 9)


# 역할 배분 (사용자 지시 2026-10-12): haiku = 코드 구현 전용, sol low = S/M 간이 리뷰
EXPECTED_CLAUDE_ROLE = {
    'coder-medium.md': ('haiku', 'high'),
    'implement-med.md': ('haiku', 'high'),
    'implement-xhigh.md': ('sonnet', 'high'),
    'core-xhigh.md': ('sonnet', 'high'),
    'ops-supervisor.md': ('sonnet', 'high'),
    'plan-high.md': ('opus', 'high'),
    'plan-xhigh.md': ('opus', 'high'),
    'plan-adversary-xhigh.md': ('opus', 'high'),
    'review-pr-high.md': ('opus', 'high'),
    'review-pr-xhigh.md': ('opus', 'high'),
    'security-audit.md': ('opus', 'high'),
}
EXPECTED_CODEX_ROLE = {
    'coder-medium.toml': ('gpt-6-luna', 'max'),
    'implement-med.toml': ('gpt-6-luna', 'max'),
    'implement-xhigh.toml': ('gpt-6-luna', 'max'),
    'core-xhigh.toml': ('gpt-6-luna', 'max'),
    'plan-high.toml': ('gpt-6.1-sol', 'high'),
    'plan-xhigh.toml': ('gpt-6.1-sol', 'high'),
    'plan-adversary-xhigh.toml': ('gpt-6.1-sol', 'high'),
    'review-pr-high.toml': ('gpt-6.1-sol', 'low'),
    'review-pr-xhigh.toml': ('gpt-6.1-sol', 'high'),
    'security-audit.toml': ('gpt-6.1-sol', 'high'),
}
EXPECTED_GLM_ROLE = {
    'coder-medium': ('glm-5.3-flash', 'max'),
    'implement-med': ('glm-5.3-flash', 'max'),
    'implement-xhigh': ('glm-5.3', 'max'),
    'core-xhigh': ('glm-5.3', 'max'),
    'plan-high': ('glm-5.3', 'high'),
    'plan-xhigh': ('glm-5.3', 'high'),
    'plan-adversary-xhigh': ('glm-5.3', 'max'),
    'review-pr-high': ('glm-5.3', 'high'),
    'review-pr-xhigh': ('glm-5.3', 'max'),
    'security-audit': ('glm-5.3', 'max'),
}
GLM_ROLE_ROW = re.compile(r'^\|\s*`([\w-]+)`\s*\|\s*`([\w.\-]+)\s*/\s*(\w+)`\s*\|', re.MULTILINE)


class RoleDistributionTests(unittest.TestCase):
    def test_claude_roles_match_distribution(self):
        self.assertEqual(read_claude_pairs(), EXPECTED_CLAUDE_ROLE)

    def test_codex_roles_match_distribution(self):
        self.assertEqual(read_codex_pairs(), EXPECTED_CODEX_ROLE)

    def test_haiku_only_on_implementation_roles(self):
        haiku = {name for name, (model, _) in read_claude_pairs().items() if model == 'haiku'}
        self.assertEqual(haiku, {'coder-medium.md', 'implement-med.md'})

    def test_claude_descriptions_match_frontmatter(self):
        # fd9da16이 frontmatter만 조합표로 갱신하고 설명을 안 고쳐 5개 역할의
        # 설명이 낡은 슬롯(소넷 low/medium·하이쿠 medium)을 언급했다(2026-10-17
        # 지적). 설명의 슬롯 문구는 frontmatter 배분과 일치해야 한다.
        slot_ko = {'opus': '오푸스(5.5)', 'sonnet': '소넷(5.5)', 'haiku': '하이쿠(5.5)'}
        for path in sorted((ROOT / 'agents').glob('*.md')):
            text = path.read_text(encoding='utf-8')
            fields = dict(FRONTMATTER_FIELD.findall(text))
            model, effort = fields.get('model'), fields.get('effort')
            with self.subTest(role=path.name):
                self.assertIn(f'{slot_ko[model]}', text.split('---')[1])
                self.assertIn(f'{effort} effort', text.split('---')[1])

    def test_glm_role_table_in_adapter_matches_distribution(self):
        text = (ROOT / 'platforms' / 'glm.md').read_text(encoding='utf-8')
        rows = {role: (model, effort) for role, model, effort in GLM_ROLE_ROW.findall(text)}
        self.assertEqual(rows, EXPECTED_GLM_ROLE)
        for role, pair in rows.items():
            with self.subTest(role=role):
                self.assertIn(pair, ALLOWED_GLM)


if __name__ == '__main__':
    unittest.main()
