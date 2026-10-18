#!/usr/bin/env python3
"""glm_slot_gate 계약 테스트 — GLM 세션에서 Claude 별칭 누수(2026-10-18 사고) 재발 방지."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import glm_slot_gate as gate

ROOT = Path(__file__).resolve().parents[1]
GLM_BASE = 'https://glm.example.invalid/api/anthropic'  # 호스트는 검사 대상이 아니다(비-Anthropic이면 충분)
GOOD_ENV = {
    'ANTHROPIC_BASE_URL': GLM_BASE,
    'ANTHROPIC_DEFAULT_HAIKU_MODEL': 'glm-5.3-flash',
    'ANTHROPIC_DEFAULT_SONNET_MODEL': 'glm-5.3',
    'ANTHROPIC_DEFAULT_OPUS_MODEL': 'glm-5.3',
}


def write_roles(directory, slots):
    for name, slot in slots.items():
        (Path(directory) / name).write_text(
            f'---\nname: {name}\nmodel: {slot}\neffort: high\n---\n본문\n', encoding='utf-8')


class SessionDetectionTests(unittest.TestCase):
    def test_no_base_url_is_claude_session(self):
        self.assertFalse(gate.is_glm_session({}))

    def test_anthropic_host_is_claude_session(self):
        self.assertFalse(gate.is_glm_session({'ANTHROPIC_BASE_URL': 'https://api.anthropic.com'}))

    def test_other_host_is_glm_session(self):
        self.assertTrue(gate.is_glm_session({'ANTHROPIC_BASE_URL': GLM_BASE}))


class ViolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def test_full_mapping_passes(self):
        write_roles(self.dir, {'a.md': 'haiku', 'b.md': 'sonnet', 'c.md': 'opus'})
        self.assertEqual(gate.violations(GOOD_ENV, self.dir), [])

    def test_missing_haiku_mapping_is_violation(self):
        # 사고 원인 재현: 슬롯 매핑 미설정 → haiku 역할이 Claude Haiku로 샌다.
        write_roles(self.dir, {'coder.md': 'haiku'})
        env = {k: v for k, v in GOOD_ENV.items() if k != 'ANTHROPIC_DEFAULT_HAIKU_MODEL'}
        found = gate.violations(env, self.dir)
        self.assertEqual(len(found), 1)
        self.assertIn('ANTHROPIC_DEFAULT_HAIKU_MODEL 미설정', found[0])

    def test_claude_model_id_in_mapping_is_violation(self):
        write_roles(self.dir, {'plan.md': 'opus'})
        env = dict(GOOD_ENV, ANTHROPIC_DEFAULT_OPUS_MODEL='claude-opus-5-5')
        found = gate.violations(env, self.dir)
        self.assertEqual(len(found), 1)
        self.assertIn('불일치', found[0])

    def test_unused_slot_is_not_checked(self):
        # 역할이 haiku를 쓰지 않으면 haiku 매핑 부재는 위반이 아니다.
        write_roles(self.dir, {'plan.md': 'opus'})
        env = {k: v for k, v in GOOD_ENV.items() if k != 'ANTHROPIC_DEFAULT_HAIKU_MODEL'}
        self.assertEqual(gate.violations(env, self.dir), [])

    def test_unknown_alias_is_violation(self):
        write_roles(self.dir, {'x.md': 'gpt'})
        found = gate.violations(GOOD_ENV, self.dir)
        self.assertTrue(any('정책 밖 별칭' in f for f in found))


class RealRolesTests(unittest.TestCase):
    def test_repo_roles_use_only_mapped_slots(self):
        # 역할 파일에 정책 밖 별칭이 생기면 실패 — 매핑 블록 갱신이 필요하다는 신호.
        slots = set(gate.role_slots(ROOT / 'agents').values())
        self.assertLessEqual(slots, set(gate.SLOT_MODEL))

    def test_repo_roles_pass_with_documented_mapping(self):
        self.assertEqual(gate.violations(GOOD_ENV, ROOT / 'agents'), [])


class DocumentedMappingTests(unittest.TestCase):
    """platforms/glm.md의 '슬롯 매핑' 블록이 게이트 정책과 같은 값인지 강제한다."""

    def test_glm_adapter_documents_gate_mapping(self):
        text = (ROOT / 'platforms' / 'glm.md').read_text(encoding='utf-8')
        for slot, model in gate.SLOT_MODEL.items():
            with self.subTest(slot=slot):
                self.assertIn(f'ANTHROPIC_DEFAULT_{slot.upper()}_MODEL": "{model}"', text)


if __name__ == '__main__':
    unittest.main()
