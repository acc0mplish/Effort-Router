#!/usr/bin/env python3
"""r39/r58 — 허용 모델·effort(및 Gemini 목표 슬러그·서브에이전트 티어) 조합 계약 테스트.

허용 조합 밖(xhigh·low 등 임의 조합)이 역할 파일에 남으면 실패한다.
- Claude Code: agents/*.md 의 model(alias)·effort frontmatter
- Codex: platforms/codex-agents/*.toml 의 model·model_reasoning_effort
- Gemini / Antigravity: platforms/gemini-agents/*.md · platforms/gemini.md 의 (target_slug, subagent_tier)
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))

import verify_gemini_install  # noqa: E402

ALLOWED_CLAUDE = {('opus', 'high'), ('sonnet', 'high'), ('haiku', 'high')}
ALLOWED_CODEX = {('gpt-6-luna', 'max'), ('gpt-6.2-sol', 'high'), ('gpt-6.2-sol', 'low')}
ALLOWED_GLM = {('glm-5.4', 'max'), ('glm-5.4', 'high'), ('glm-5.3-flash', 'max')}
# 주의: Gemini 쌍은 Claude/Codex/GLM의 (model, effort)가 아니라
# 확정 목표 모델 슬러그와 Antigravity 서브에이전트 로더 티어의 (target_slug, subagent_tier) 쌍이다.
ALLOWED_GEMINI = {
    ('gemini-4-argon-medium', 'inherit'),
    ('gemini-4-hydrogen-high', 'pro'),
    ('gemini-4-argon-high', 'pro'),
    ('gemini-4-carbon-high', 'pro'),
}

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
        self.assertEqual(len(ALLOWED_CLAUDE | ALLOWED_CODEX | ALLOWED_GLM | ALLOWED_GEMINI), 13)


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
    'plan-high.toml': ('gpt-6.2-sol', 'high'),
    'plan-xhigh.toml': ('gpt-6.2-sol', 'high'),
    'plan-adversary-xhigh.toml': ('gpt-6.2-sol', 'high'),
    'review-pr-high.toml': ('gpt-6.2-sol', 'low'),
    'review-pr-xhigh.toml': ('gpt-6.2-sol', 'high'),
    'security-audit.toml': ('gpt-6.2-sol', 'high'),
}
EXPECTED_GLM_ROLE = {
    'coder-medium': ('glm-5.3-flash', 'max'),
    'implement-med': ('glm-5.3-flash', 'max'),
    'implement-xhigh': ('glm-5.4', 'max'),
    'core-xhigh': ('glm-5.4', 'max'),
    'plan-high': ('glm-5.4', 'high'),
    'plan-xhigh': ('glm-5.4', 'high'),
    'plan-adversary-xhigh': ('glm-5.4', 'max'),
    'review-pr-high': ('glm-5.4', 'high'),
    'review-pr-xhigh': ('glm-5.4', 'max'),
    'security-audit': ('glm-5.4', 'max'),
}
# 역할 배분 (사용자 확정 2026-11-18): 값 쌍은 (target_slug, subagent_tier)
EXPECTED_GEMINI_ROLE = {
    'coder-medium': ('gemini-4-hydrogen-high', 'pro'),
    'implement-med': ('gemini-4-hydrogen-high', 'pro'),
    'implement-xhigh': ('gemini-4-argon-high', 'pro'),
    'core-xhigh': ('gemini-4-argon-high', 'pro'),
    'ops-supervisor': ('gemini-4-argon-medium', 'inherit'),
    'plan-high': ('gemini-4-carbon-high', 'pro'),
    'plan-xhigh': ('gemini-4-carbon-high', 'pro'),
    'plan-adversary-xhigh': ('gemini-4-carbon-high', 'pro'),
    'review-pr-high': ('gemini-4-argon-high', 'pro'),
    'review-pr-xhigh': ('gemini-4-carbon-high', 'pro'),
    'security-audit': ('gemini-4-carbon-high', 'pro'),
}
READONLY_GEMINI_ROLES = {
    'plan-adversary-xhigh',
    'review-pr-high',
    'review-pr-xhigh',
    'security-audit',
}
GEMINI_DISPLAY_BY_SLUG = {
    'gemini-4-argon-medium': 'Gemini 4 Argon (Medium)',
    'gemini-4-hydrogen-high': 'Gemini 4 Hydrogen (High)',
    'gemini-4-argon-high': 'Gemini 4 Argon (High)',
    'gemini-4-carbon-high': 'Gemini 4 Carbon (High)',
}
GEMINI_TIER_PHRASE = {
    'inherit': 'inherit 티어',
    'pro': 'pro 티어',
    'flash': 'flash 티어',
}
GLM_ROLE_ROW = re.compile(r'^\|\s*`([\w-]+)`\s*\|\s*`([\w.\-]+)\s*/\s*(\w+)`\s*\|', re.MULTILINE)
GEMINI_ROLE_ROW = re.compile(
    r'^\|\s*`([\w-]+)`\s*\|\s*`([\w.\-]+)`\s*\(`([^`]+)`\)\s*\|\s*`(\w+)`\s*\|\s*([^|]+?)\s*\|$',
    re.MULTILINE,
)


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

    def test_gemini_agents_schema_tools_and_descriptions_match_distribution(self):
        agent_paths = sorted((ROOT / 'platforms' / 'gemini-agents').glob('*.md'))
        self.assertEqual(
            {p.stem for p in agent_paths},
            set(EXPECTED_GEMINI_ROLE),
            'platforms/gemini-agents/*.md 역할 집합 불일치',
        )
        for path in agent_paths:
            role = path.stem
            target_slug, expected_tier = EXPECTED_GEMINI_ROLE[role]
            fm = verify_gemini_install.parse_frontmatter(path.read_text(encoding='utf-8'))
            with self.subTest(role=role):
                self.assertIn((target_slug, fm.get('model')), ALLOWED_GEMINI)
                self.assertEqual(fm.get('name'), role)
                self.assertEqual(fm.get('model'), expected_tier)
                self.assertEqual(fm.get('subagent'), 'true')
                self.assertEqual(fm.get('mainAgent'), 'false')
                self.assertEqual(fm.get('inheritCustomizations'), 'false')

                tools = verify_gemini_install.parse_tools_list(fm.get('tools'))
                self.assertIsNotNone(tools, f'{role}: tools 리스트 파싱 실패')
                self.assertEqual(len(tools), len(set(tools)), f'{role}: tools 중복 항목 존재')
                expected_tools = (
                    verify_gemini_install.READONLY_TOOLS
                    if role in READONLY_GEMINI_ROLES
                    else verify_gemini_install.WRITABLE_TOOLS
                )
                self.assertEqual(frozenset(tools), expected_tools)

                desc = fm.get('description', '')
                expected_display = GEMINI_DISPLAY_BY_SLUG[target_slug]
                self.assertIn(expected_display, desc)
                for other_slug, other_display in GEMINI_DISPLAY_BY_SLUG.items():
                    if other_slug != target_slug:
                        self.assertNotIn(other_display, desc)
                self.assertIn(GEMINI_TIER_PHRASE[expected_tier], desc)
                if role in READONLY_GEMINI_ROLES:
                    self.assertIn('읽기 전용', desc)

    def test_gemini_role_table_in_adapter_matches_distribution(self):
        text = (ROOT / 'platforms' / 'gemini.md').read_text(encoding='utf-8')
        matches = GEMINI_ROLE_ROW.findall(text)
        self.assertEqual(len(matches), len(EXPECTED_GEMINI_ROLE))
        rows = {role: (slug, tier) for role, slug, _disp, tier, _tools in matches}
        self.assertEqual(rows, EXPECTED_GEMINI_ROLE)
        readonly_in_table = set()
        for role, slug, display, tier, tools_col in matches:
            with self.subTest(role=role):
                self.assertIn((slug, tier), ALLOWED_GEMINI)
                self.assertEqual(display, GEMINI_DISPLAY_BY_SLUG[slug])
                if '읽기 전용' in tools_col:
                    readonly_in_table.add(role)
        self.assertEqual(readonly_in_table, READONLY_GEMINI_ROLES)

    def test_verify_gemini_install_expected_roles_match_distribution(self):
        verifier_pairs = {
            role: (slug, tier)
            for role, (slug, tier, _ro) in verify_gemini_install.EXPECTED_ROLES.items()
        }
        verifier_readonly = {
            role for role, (_slug, _tier, ro) in verify_gemini_install.EXPECTED_ROLES.items() if ro
        }
        self.assertEqual(verifier_pairs, EXPECTED_GEMINI_ROLE)
        self.assertEqual(verifier_readonly, READONLY_GEMINI_ROLES)
        self.assertEqual(
            verify_gemini_install.READONLY_TOOLS,
            frozenset({'read_file', 'run_command', 'manage_task', 'search_web'}),
        )
        self.assertEqual(
            verify_gemini_install.WRITABLE_TOOLS,
            frozenset(
                {'read_file', 'edit_file', 'write_file', 'run_command', 'manage_task', 'search_web'}
            ),
        )


if __name__ == '__main__':
    unittest.main()
