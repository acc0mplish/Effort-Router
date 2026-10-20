#!/usr/bin/env python3
"""intake_gate.py 계약 테스트 — 번들 §5 T1-T18.

unittest.TestCase 스타일(저장소 관례) + pytest 실행. 판정 로직은 순수함수 직접 호출,
exit 코드·stdout JSON은 subprocess 검증(test_glm_slot_gate.py·test_jev_judge.py 패턴).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import intake_gate as gate

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/intake_gate.py'

SCHEMA_FIELDS = {'ok', 'gate', 'mode', 'source', 'items', 'missing_count',
                 'ambiguity_score', 'action', 'questions_max', 'context_dep',
                 'task_active', 'urgent', 'utterance', 'saved_to'}
ITEM_KEYS = {'target', 'task_type', 'scope', 'risk', 'verification', 'pattern_ref'}


class CliHarness:
    """subprocess 실행기 — tests는 run_cli(...).dict로 stdout JSON을 받는다."""

    @staticmethod
    def run_cli(*args, stdin_text=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, input=stdin_text)


def output_of(result):
    return json.loads(result.stdout)


class ActionRuleTests(unittest.TestCase):
    """compute_action 순수함수 — §3.5 우선순위 직접 호출."""

    @staticmethod
    def items(*missing):
        return {key: ('missing' if key in missing else 'present') for key in ITEM_KEYS}

    def test_priority0_urgent_overrides_hard(self):
        action, qmax = gate.compute_action(self.items('target', 'task_type'),
                                           False, False, True)
        self.assertEqual((action, qmax), ('advisory', 0))

    def test_priority1_loop_pass_requires_flag_and_loop_verb(self):
        action, qmax = gate.compute_action(self.items('target'), False, True, False,
                                           loop_signal=True)
        self.assertEqual((action, qmax), ('loop_pass', 0))

    def test_priority1_no_flag_no_loop_pass(self):
        action, _ = gate.compute_action(self.items('target'), False, False, False,
                                        loop_signal=True)
        self.assertEqual(action, 'hard')

    def test_priority2_context_dep(self):
        action, qmax = gate.compute_action(self.items('target'), True, False, False)
        self.assertEqual((action, qmax), ('context_dep', 0))

    def test_priority1_beats_priority2(self):
        action, _ = gate.compute_action(self.items('target'), True, True, False,
                                        loop_signal=True)
        self.assertEqual(action, 'loop_pass')

    def test_priority3_hard(self):
        action, qmax = gate.compute_action(self.items('scope', 'target'), False,
                                           False, False)
        self.assertEqual((action, qmax), ('hard', 1))

    def test_priority4_soft_caps_at_three(self):
        action, qmax = gate.compute_action(self.items('scope', 'risk', 'verification',
                                                      'pattern_ref'), False, False, False)
        self.assertEqual((action, qmax), ('soft', 3))

    def test_priority5_advisory(self):
        action, qmax = gate.compute_action(self.items('scope'), False, False, False)
        self.assertEqual((action, qmax), ('advisory', 0))


class DetectorTests(unittest.TestCase):
    """항목 판정기·감지기 단위(T16 포함)."""

    def test_t16_risk_keyword_present(self):
        self.assertTrue(gate.detect_item('risk', '인증 로직 수정'))
        self.assertTrue(gate.detect_item('task_type', '인증 로직 수정'))

    def test_risk_absent_without_keyword(self):
        self.assertFalse(gate.detect_item('risk', 'README에 섹션 추가'))

    def test_target_by_extension(self):
        self.assertTrue(gate.detect_item('target', 'main.py 고쳐줘'))

    def test_pronoun_detection(self):
        for text in ('결과 보고 고쳐', '이대로 진행해', '그거 고쳐'):
            self.assertTrue(gate.detect_pronoun(text), text)
        self.assertFalse(gate.detect_pronoun('README에 섹션 추가'))

    def test_loop_verb_detection(self):
        for text in ('다시 고쳐', '아직 안 돼', '여전히 실패'):
            self.assertTrue(gate.detect_loop_verb(text), text)
        self.assertFalse(gate.detect_loop_verb('README에 섹션 추가'))


class CliJudgmentTests(unittest.TestCase):
    def run_cli(self, *args, stdin_text=None):
        return CliHarness.run_cli(*args, stdin_text=stdin_text)

    def test_t1_all_items_present_advisory(self):
        result = self.run_cli(
            'agents/coder-medium.md 파일에 리팩터 동사 추가, 테스트 통과 기준, '
            '기존 컨벤션 따름, 보안 제외')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        self.assertEqual(output['action'], 'advisory')
        self.assertEqual(output['missing_count'], 0)
        self.assertEqual(output['ambiguity_score'], 0.0)
        self.assertEqual(output['questions_max'], 0)

    def test_t2_bare_fix_is_hard(self):
        result = self.run_cli('고쳐줘')
        self.assertEqual(result.returncode, 1)
        output = output_of(result)
        self.assertEqual(output['action'], 'hard')
        self.assertEqual(output['questions_max'], 1)
        self.assertEqual(output['items']['task_type'], 'present')
        self.assertEqual(output['items']['target'], 'missing')

    def test_t3_target_type_only_is_soft(self):
        result = self.run_cli('README에 섹션 추가')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        self.assertEqual(output['action'], 'soft')
        self.assertEqual(output['questions_max'], 3)
        self.assertEqual(output['missing_count'], 4)

    def test_t4_result_reference_is_context_dep(self):
        result = self.run_cli('결과 보고 고쳐')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        self.assertEqual(output['action'], 'context_dep')
        self.assertEqual(output['questions_max'], 0)
        self.assertEqual(output['missing_count'], 0)
        self.assertEqual(output['ambiguity_score'], 0.0)
        self.assertTrue(output['context_dep'])
        self.assertEqual(output['items']['target'], 'context_satisfied')

    def test_t5_pronoun_is_context_dep(self):
        result = self.run_cli('이대로 진행해')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        self.assertEqual(output['action'], 'context_dep')
        self.assertEqual(output['missing_count'], 0)

    def test_t6_task_active_loop_pass_keeps_items(self):
        result = self.run_cli('다시 고쳐', '--task-active')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        self.assertEqual(output['action'], 'loop_pass')
        self.assertTrue(output['task_active'])
        self.assertEqual(output['questions_max'], 0)
        self.assertEqual(output['items']['target'], 'missing')
        # 원문 기준 items·missing_count는 그대로(§3.3 — loop_pass는 재계산 없음)
        self.assertEqual(output['missing_count'], 5)

    def test_t7_no_flag_means_no_loop_pass(self):
        result = self.run_cli('다시 고쳐')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(output_of(result)['action'], 'hard')

    def test_t8_task_active_beats_context_dep(self):
        result = self.run_cli('그거 다시 고쳐', '--task-active')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output_of(result)['action'], 'loop_pass')

    def test_t9_context_recheck_marks_only_found_items(self):
        result = self.run_cli('섹션 추가해', '--context', '대상 파일: README.md, 검증: 빌드 통과')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        items = output['items']
        self.assertEqual(items['target'], 'context_satisfied')
        self.assertEqual(items['verification'], 'context_satisfied')
        self.assertEqual(items['task_type'], 'present')
        self.assertEqual(items['scope'], 'missing')
        self.assertEqual(items['risk'], 'missing')
        self.assertEqual(items['pattern_ref'], 'missing')
        self.assertEqual(output['action'], 'soft')
        self.assertEqual(output['questions_max'], 3)

    def test_t10_empty_statement_is_invalid_input(self):
        for statement in ('', '   '):
            result = self.run_cli(statement)
            self.assertEqual(result.returncode, 2, repr(statement))
            self.assertIn('FAIL intake gate:', result.stderr)
            self.assertEqual(result.stdout, '')

    def test_t11_stdin_dash_input(self):
        result = self.run_cli('-', stdin_text='고쳐줘')
        self.assertEqual(result.returncode, 1)
        output = output_of(result)
        self.assertEqual(output['action'], 'hard')
        self.assertEqual(output['utterance'], '고쳐줘')

    def test_t12_save_success_records_full_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / 'intake'
            result = self.run_cli('고쳐줘', '--save', str(save))
            self.assertEqual(result.returncode, 1)
            output = output_of(result)
            self.assertIsNotNone(output['saved_to'])
            self.assertTrue(Path(output['saved_to']).is_file())
            self.assertEqual(set(output), SCHEMA_FIELDS)
            self.assertEqual(set(output['items']), ITEM_KEYS)
            self.assertEqual(output['gate'], 'intake')
            self.assertEqual(output['mode'], 'basic')

    def test_t13_save_failure_keeps_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / 'file'
            blocker.write_text('x', encoding='utf-8')
            result = self.run_cli('고쳐줘', '--save', str(blocker / 'audit'))
            self.assertEqual(result.returncode, 1)
            output = output_of(result)
            self.assertIsNone(output['saved_to'])
            self.assertEqual(output['action'], 'hard')
            self.assertIn('경고', result.stderr)

    def test_t14_utterance_is_verbatim(self):
        statement = '  agents/coder-medium.md 파일에 리팩터 동사 추가 — 원문 보존 확인용  '
        result = self.run_cli(statement)
        self.assertEqual(output_of(result)['utterance'], statement)

    def test_t15_ambiguity_equals_missing_over_six(self):
        cases = ('고쳐줘', 'README에 섹션 추가',
                 '섹션 추가해 --contextX')  # 세 번째는 개별 실행으로 대체한다
        for statement in cases[:2]:
            result = self.run_cli(statement)
            output = output_of(result)
            self.assertAlmostEqual(output['ambiguity_score'],
                                   output['missing_count'] / 6)
            self.assertGreaterEqual(output['ambiguity_score'], 0.0)
            self.assertLessEqual(output['ambiguity_score'], 1.0)
        result = self.run_cli('섹션 추가해', '--context', '대상 파일: README.md')
        output = output_of(result)
        self.assertAlmostEqual(output['ambiguity_score'], output['missing_count'] / 6)

    def test_t17_urgent_downgrades_to_advisory(self):
        result = self.run_cli('터졌어 고쳐', '--urgent')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        self.assertEqual(output['action'], 'advisory')
        self.assertEqual(output['questions_max'], 0)
        self.assertTrue(output['urgent'])
        self.assertEqual(output['items']['target'], 'missing')

    def test_t18_source_auto_records_origin(self):
        statement = 'deploy_global 매니페스트에 신규 게이트 스크립트 4종 추가 등록'
        result = self.run_cli(statement, '--source', 'auto')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = output_of(result)
        self.assertEqual(output['source'], 'auto')
        self.assertEqual(output['utterance'], statement)

    def test_source_defaults_to_user(self):
        result = self.run_cli('고쳐줘')
        self.assertEqual(output_of(result)['source'], 'user')


if __name__ == '__main__':
    unittest.main()
