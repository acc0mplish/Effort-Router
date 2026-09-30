#!/usr/bin/env python3
"""r29 루프 탈출 게이트(neverstuck) 단위테스트 — tmpdir 이력 JSON fixture로 분기 전수(T1~T24+보조).

테스트는 subprocess로 CLI를 실행한다(test_tree_gate 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다. RED 단계(neverstuck_gate.py 부재)
에서는 전 테스트가 실패한다. 게이트는 git·환경 무의존(결정론 — 표준 라이브러리만)
이라 fixture는 tmpdir의 이력 JSON뿐이다(stdin 케이스 T16 포함, git fixture 불필요).
claims 대응(r29 plan §5): T1=C6, T2=C5(+F1 s7_evaluable:false), T4/T5/T23=C7(선언
면제 — 실패·worked 양면), T7=C8, T10/T11=C9, T11b=D3 전역 스코프, T12=C10,
T13/T14/T15a/T15c(배열)/T21=C11, T15b=빈 배열 not-armed, T15c(null)=D6 결손,
T18/T18b=C12, T19=C13(주입용 문자열·치환 템플릿), T16=stdin 경로,
T17=R3-H2 attempts 원본 포함, T20=D1 타입 클래스, T24=F3 스키마 엣지,
나머지는 분기 전수(T3·T6·T8·T9·T22).
④리뷰 gap 반영(2026-09-30, 총 34케이스): GAP-1 비UTF-8 이력 exit 2(crash 방지)·
GAP-2 --save 실패 stdout saved_to:null 보존(F4)·GAP-3a S7 우선 보고·GAP-3b 복수
무브류 쉼표 열거·GAP-3c 비인접 상이쌍 탐지(회귀 방어)·GAP-5 심층 중첩 JSON
RecursionError exit 2. GAP-4(preference_domain:null 결손=False 판정)는 구현
변경 없음 — Phase 2 SKILL 문서 메모.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/neverstuck_gate.py'

RESPONSE_KEYS = sorted(('ok', 'gate', 'armed', 'trigger', 'goal', 'attempts_total',
                        'attempts_considered', 'declared_search_skipped',
                        'preference_domain', 'exemptions', 'per_move_class',
                        'armed_on', 's7_evaluable', 'flags', 'contract_reminder',
                        'attempts', 'saved_to'))


class NeverstuckGateTests(unittest.TestCase):
    """T1~T24 + T11b·T15a/b/c·T18b — 28케이스, plan §5 기대값 그대로."""

    maxDiff = None

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    # --- fixtures ---------------------------------------------------------------

    def run_gate(self, *args, stdin_text=None):
        """게이트 subprocess 호출 — stdin 미지정 시 DEVNULL(오독 방지)."""
        if stdin_text is None:
            return subprocess.run([sys.executable, str(GATE), *args],
                                  stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True)
        return subprocess.run([sys.executable, str(GATE), *args],
                              input=stdin_text, capture_output=True, text=True)

    def history(self, payload, name='history.json'):
        path = self.root / name
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        path.write_text(text, encoding='utf-8')
        return path

    def judge(self, payload, *extra_args):
        return self.run_gate('--history', str(self.history(payload)), *extra_args)

    def attempts(self, *entries):
        return {'attempts': list(entries)}

    def fail_case(self, move_class='m'):
        return {'move_class': move_class, 'outcome': 'failed'}

    def s7_pair(self, v1, v2, knob='k', c1='cA', c2='cB', declared=False):
        return {'attempts': [
            {'move_class': 'm', 'outcome': 'worked', 'knob': knob,
             'value': v1, 'context': c1, 'declared_search': declared},
            {'move_class': 'm', 'outcome': 'worked', 'knob': knob,
             'value': v2, 'context': c2, 'declared_search': declared}]}

    def assert_config_error(self, result):
        """exit 2 계약 — stderr FAIL 접두 ∧ stdout 없음(C11)."""
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('FAIL neverstuck gate:', result.stderr)
        self.assertEqual(result.stdout, '')

    # --- 3회 게이트 (T1·T2·T3·T5·T6) ---------------------------------------------

    def test_t1_two_failures_not_armed(self):
        # C6 — 같은 무브류 failed 2 → exit 0 ∧ armed:false(Never 원칙: 1~2회 미발동)
        result = self.judge(self.attempts(self.fail_case(), self.fail_case()))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertIsNone(output['trigger'])
        self.assertEqual(output['flags'], [])
        self.assertIsNone(output['contract_reminder'])

    def test_t2_three_failures_armed(self):
        # C5 — failed 3 → exit 1 ∧ three_attempt_gate ∧ s7_evaluable:false
        # (F1 — 완비 worked 0이면 삼중 게이트 무장과 무관하게 evaluable:false)
        result = self.judge(self.attempts(*[self.fail_case('timeout-retune')] * 3))
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['armed'])
        self.assertTrue(output['ok'])
        self.assertEqual(output['trigger'], 'three_attempt_gate')
        self.assertEqual(output['armed_on'], {'move_classes': ['timeout-retune']})
        self.assertFalse(output['s7_evaluable'])
        self.assertEqual(output['flags'], ['armed'])

    def test_t3_distinct_move_classes_split(self):
        # 무브류 구분 — A 2회 + B 1회 → 어느 클래스도 failed 3 미달, exit 0
        result = self.judge(self.attempts(self.fail_case('a'), self.fail_case('a'),
                                          self.fail_case('b')))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['armed'])

    def test_t5_declared_only_excluded_real_below_threshold(self):
        # C7 — 실 failed 1 + 선언 failed 2 → 선언만 제외하면 1 미달 → exit 0
        result = self.judge(self.attempts(self.fail_case('m'),
                                          {**self.fail_case('m'), 'declared_search': True},
                                          {**self.fail_case('m'), 'declared_search': True}))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertEqual(output['declared_search_skipped'], 2)
        self.assertEqual(output['attempts_considered'], 1)

    def test_t6_worked_not_counted_for_three_gate(self):
        # worked 1 + failed 2 같은 무브 → 3회 게이트는 failed만 카운트 → exit 0
        result = self.judge(self.attempts({'move_class': 'm', 'outcome': 'worked'},
                                          self.fail_case('m'), self.fail_case('m')))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['armed'])

    # --- 선언 탐색 면제 (T4·T23) ---------------------------------------------------

    def test_t4_declared_search_failures_exempt(self):
        # C7 — declared_search:true 3회 실패 → exit 0 ∧ skipped 3 ∧ 클래스 미표시(F5)
        result = self.judge(self.attempts(*[
            {**self.fail_case('probe'), 'declared_search': True}] * 3))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertEqual(output['declared_search_skipped'], 3)
        self.assertEqual(output['attempts_considered'], 0)
        self.assertEqual(output['attempts_total'], 3)
        self.assertEqual(output['per_move_class'], [])

    def test_t23_declared_search_excluded_from_s7(self):
        # D2 교차 — 선언탐색 worked 상이쌍만 존재 → S7 대상 아님(effective 한정) → exit 0
        result = self.judge(self.s7_pair(30, 90, declared=True))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertEqual(output['declared_search_skipped'], 2)
        self.assertEqual(output['attempts_considered'], 0)

    # --- S7 (T7·T8·T9·T10·T11·T11b·T22) --------------------------------------------

    def test_t7_s7_hard_signal_immediate_arm(self):
        # C8 — knob K worked (30,s1),(90,s2) 값·맥락 상이 → failed 0이어도 exit 1
        result = self.judge(self.s7_pair(30, 90, knob='timeout',
                                         c1='sess-1', c2='sess-2'))
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['armed'])
        self.assertEqual(output['trigger'], 's7_hard_signal')
        self.assertEqual(output['armed_on']['knob'], 'timeout')
        self.assertEqual(output['armed_on']['working_values'],
                         [{'value': 30, 'context': 'sess-1'},
                          {'value': 90, 'context': 'sess-2'}])
        self.assertTrue(output['s7_evaluable'])
        # per_move_class 정합(F2) — s7 무장 knob의 완비 worked 2가 그대로 보인다
        self.assertEqual(output['per_move_class'],
                         [{'move_class': 'm', 'failed': 0, 'worked': 2}])

    def test_t8_same_context_no_s7(self):
        # 값 상이·맥락 동일 → S7 불성립(맥락 상이 필요) → exit 0
        result = self.judge(self.s7_pair(30, 90, c2='cA'))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertTrue(output['s7_evaluable'])

    def test_t9_same_value_no_s7(self):
        # 값 동일·맥락 상이 → S7 불성립(값 상이 필요) → exit 0
        result = self.judge(self.s7_pair(30, 30))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertTrue(output['s7_evaluable'])

    def test_t10_missing_value_not_evaluable(self):
        # C9 — value 미전달 worked만 존재(완비 그룹 0) → exit 0 ∧ s7_evaluable:false
        result = self.judge(self.attempts(
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'timeout', 'context': 'c1'},
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'timeout', 'context': 'c2'}))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertFalse(output['s7_evaluable'])

    def test_t11_missing_context_not_evaluable(self):
        # C9 — context 미전달 worked만 존재(완비 그룹 0) → exit 0 ∧ s7_evaluable:false
        result = self.judge(self.attempts(
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'timeout', 'value': 30},
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'timeout', 'value': 90}))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertFalse(output['s7_evaluable'])

    def test_t11b_complete_group_exists_globally_evaluable(self):
        # D3 전역 스코프 — 완비 그룹 1(S7 비성립·단일 완비) + 결손 worked 1 병존
        # → s7_evaluable:true(완비 그룹 존재가 우선)
        result = self.judge(self.attempts(
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k',
             'value': 30, 'context': 'c1'},
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k'}))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertTrue(output['s7_evaluable'])

    def test_t22_different_knobs_no_cross_grouping(self):
        # knob별 그룹핑 — 그룹 간 합산 불가(서로 다른 knob 각 worked 1) → exit 0
        result = self.judge(self.attempts(
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k1',
             'value': 30, 'context': 'c1'},
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k2',
             'value': 90, 'context': 'c2'}))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertTrue(output['s7_evaluable'])

    # --- 취향 면제 (T12) ------------------------------------------------------------

    def test_t12_preference_domain_exempt(self):
        # C10 — preference_domain:true ∧ failed 3(S7 비성립 병기) → 1단계 최우선 면제
        result = self.judge({'preference_domain': True,
                             'attempts': [self.fail_case()] * 3})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertIn('preference_domain', output['exemptions'])
        self.assertEqual(output['exemptions'], ['preference_domain'])
        self.assertTrue(output['preference_domain'])
        self.assertIsNone(output['trigger'])

    # --- 스키마 검증 (T13·T14·T15a/b/c·T21·T24) --------------------------------------

    def test_t13_invalid_outcome_exit2(self):
        # C11 — outcome:"maybe" → exit 2 ∧ stderr FAIL 접두 ∧ stdout 없음
        result = self.judge(self.attempts({'move_class': 'm', 'outcome': 'maybe'}))
        self.assert_config_error(result)

    def test_t14_missing_move_class_exit2(self):
        # C11 — move_class 누락 시도 → 전체 거부 exit 2(부분 판정 없음)
        result = self.judge(self.attempts({'outcome': 'failed'}))
        self.assert_config_error(result)

    def test_t15a_missing_attempts_key_exit2(self):
        # C11 — attempts 키 부재 → exit 2
        result = self.judge({'goal': 'attempts 없는 이력'})
        self.assert_config_error(result)

    def test_t15b_empty_attempts_not_armed(self):
        # 빈 배열 [] → 유효, not-armed(exit 0)
        result = self.judge({'attempts': []})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertEqual(output['attempts_total'], 0)
        self.assertEqual(output['attempts_considered'], 0)

    def test_t15c_value_array_rejected_null_is_missing(self):
        # T15c(배열)=C11 — value 비스칼라(배열) → exit 2 /
        # T15c(null)=D6 — value:null은 결손(완비 그룹 0 → s7_evaluable:false, exit 2 아님)
        result = self.judge(self.attempts(
            {'move_class': 'm', 'outcome': 'worked', 'value': [30]}))
        self.assert_config_error(result)
        result = self.judge(self.s7_pair(None, None))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertFalse(output['s7_evaluable'])

    def test_t21_broken_json_exit2(self):
        # C11 — 파손 JSON 파일 → exit 2 ∧ stderr FAIL
        result = self.run_gate('--history', str(self.history('{not json')))
        self.assert_config_error(result)

    def test_t24_schema_edges(self):
        # F3 — knob·context null 결손 / 비bool 플래그 2종 / NaN·Infinity 리터럴 거부
        result = self.judge(self.attempts(
            {'move_class': 'm', 'outcome': 'worked', 'knob': None,
             'value': 30, 'context': None},
            {'move_class': 'm', 'outcome': 'worked', 'knob': None,
             'value': 90, 'context': None}))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['armed'])
        self.assertFalse(output['s7_evaluable'])  # null 결손 → 완비 그룹 0
        result = self.judge(self.attempts(
            {**self.fail_case(), 'declared_search': 1}))
        self.assert_config_error(result)
        result = self.judge({'preference_domain': 'true', 'attempts': [self.fail_case()]})
        self.assert_config_error(result)
        for literal in ('NaN', 'Infinity'):
            broken = self.history(
                '{"attempts": [{"move_class": "m", "outcome": "failed", "value": %s}]}' % literal)
            self.assert_config_error(self.run_gate('--history', str(broken)))

    # --- 응답·감사 (T16·T17·T18·T18b·T19·T20) -----------------------------------------

    def test_t16_stdin_history_equivalent(self):
        # stdin 경로 — `--history -`가 파일 경로와 동일 판정(전체 응답 동일)
        payload = self.attempts(*[self.fail_case('stdin-mc')] * 3)
        via_stdin = self.run_gate('--history', '-', stdin_text=json.dumps(payload))
        self.assertEqual(via_stdin.returncode, 1, via_stdin.stderr)
        self.assertTrue(json.loads(via_stdin.stdout)['armed'])
        via_file = self.judge(payload)
        self.assertEqual(json.loads(via_file.stdout), json.loads(via_stdin.stdout))

    def test_t17_armed_response_structure(self):
        # R3-H2 — ok:true ∧ flags:["armed"] ∧ exit 1 ∧ attempts 원본 포함 ∧ §1.5 키 구조
        entries = [{'move_class': 'm', 'outcome': 'failed'}] * 3
        payload = {'goal': '테스트 목표', 'attempts': entries}
        result = self.judge(payload)
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(sorted(output.keys()), RESPONSE_KEYS)
        self.assertTrue(output['ok'])
        self.assertEqual(output['gate'], 'neverstuck-gate')
        self.assertEqual(output['flags'], ['armed'])
        self.assertEqual(output['attempts'], entries)
        self.assertEqual(output['goal'], '테스트 목표')
        self.assertIsNone(output['saved_to'])
        self.assertEqual(output['attempts_total'], 3)
        self.assertEqual(output['attempts_considered'], 3)
        self.assertEqual(output['declared_search_skipped'], 0)
        self.assertFalse(output['preference_domain'])
        self.assertEqual(output['exemptions'], [])

    def test_t18_save_armed_audit(self):
        # C12 — --save DIR(armed 이력) → neverstuck-gate-<UTC>.json 기록 ∧
        # saved_to 경로 응답 ∧ 파일에 armed:true ∧ attempts 원본 포함(R3-H2)
        audit = self.root / 'audit'
        result = self.judge(self.attempts(*[self.fail_case('m')] * 3),
                            '--save', str(audit))
        self.assertEqual(result.returncode, 1, result.stderr)
        saved = json.loads(result.stdout)['saved_to']
        self.assertTrue(saved and Path(saved).is_file())
        files = list(audit.glob('neverstuck-gate-*.json'))
        self.assertEqual(len(files), 1)
        payload = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertTrue(payload['armed'])
        self.assertEqual(len(payload['attempts']), 3)

    def test_t18b_save_not_armed_audit(self):
        # C12 — not-armed도 --save 동일 기록(armed:false 감사 ∧ attempts 원본)
        audit = self.root / 'audit-quiet'
        result = self.judge(self.attempts(self.fail_case('m')),
                            '--save', str(audit))
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)['saved_to']
        self.assertTrue(saved and Path(saved).is_file())
        payload = json.loads(Path(saved).read_text(encoding='utf-8'))
        self.assertFalse(payload['armed'])
        self.assertEqual(len(payload['attempts']), 1)

    def test_t19_contract_reminder_template(self):
        # C13 — 고정 문구 4종 + 치환 템플릿(무브류 열거 / knob 값@맥락·상이쌍 전부) +
        # 값 JSON 직렬화(F5 — str 따옴표·수치 그대로) + not-armed null
        three = self.judge(self.attempts(*[self.fail_case('timeout-retune')] * 3))
        reminder = json.loads(three.stdout)['contract_reminder']
        for phrase in ('소급 예측', 'Stuck Packet', 'loop-bait', '실험 정확히 1개'):
            self.assertIn(phrase, reminder, phrase)
        self.assertIn('무브류 timeout-retune은 전부 밴한다', reminder)
        s7 = self.judge(self.s7_pair(30, 90, knob='timeout',
                                     c1='sess-1', c2='sess-2'))
        reminder = json.loads(s7.stdout)['contract_reminder']
        self.assertIn('knob timeout의 값 30@sess-1·90@sess-2은 전부 밴한다', reminder)
        str_val = self.judge(self.s7_pair('30', 'fast', knob='k', c1='c1', c2='c2'))
        reminder = json.loads(str_val.stdout)['contract_reminder']
        self.assertIn('"30"@c1·"fast"@c2', reminder)
        quiet = self.judge(self.attempts(self.fail_case('m')))
        self.assertIsNone(json.loads(quiet.stdout)['contract_reminder'])

    def test_t20_value_type_classes(self):
        # D1 — 30 vs 30.0 동일(수치 통합 ==) / 30 vs "30" 상이(str⊥수치) /
        # True vs 1 상이(bool은 수치와 별개)
        same = self.judge(self.s7_pair(30, 30.0))
        self.assertEqual(same.returncode, 0, same.stderr)
        output = json.loads(same.stdout)
        self.assertFalse(output['armed'])
        self.assertTrue(output['s7_evaluable'])
        diff_str = self.judge(self.s7_pair(30, '30'))
        self.assertEqual(diff_str.returncode, 1, diff_str.stderr)
        self.assertEqual(json.loads(diff_str.stdout)['trigger'], 's7_hard_signal')
        diff_bool = self.judge(self.s7_pair(True, 1))
        self.assertEqual(diff_bool.returncode, 1, diff_bool.stderr)
        self.assertEqual(json.loads(diff_bool.stdout)['trigger'], 's7_hard_signal')

    # --- ④리뷰 gap 커버리지 (GAP-1·2·3a/b/c — r29 ④리뷰 판정 반영) -------------------

    def test_gap1_non_utf8_history_exit2(self):
        # GAP-1 HIGH — 비UTF-8 바이너리 이력 파일 → crash(exit 1 = armed 어휘 오염)
        # 금지, exit 2 ∧ stderr FAIL ∧ stdout 없음(§1.2 무효 입력 계약)
        binary = self.root / 'binary.json'
        binary.write_bytes(b'\xff\xfe{"attempts": []}')
        self.assert_config_error(self.run_gate('--history', str(binary)))

    def test_gap2_save_failure_stdout_preserved(self):
        # F4·GAP-2 — 판정 성공·--save 실패(대상이 기존 일반 파일) → stdout JSON
        # saved_to:null 보존 ∧ exit 2(tree_gate:451 전례 정합 — 결과를 버리지 않는다)
        blocker = self.root / 'blocker.txt'
        blocker.write_text('not a directory\n', encoding='utf-8')
        result = self.judge(self.attempts(self.fail_case('m')), '--save', str(blocker))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('FAIL neverstuck gate:', result.stderr)
        output = json.loads(result.stdout)
        self.assertIsNone(output['saved_to'])
        self.assertFalse(output['armed'])

    def test_gap3a_s7_priority_over_three_gate(self):
        # GAP-3a — S7·3회 게이트 동시 성립 → s7 우선 보고(plan §1.4 4단계)
        result = self.judge({'attempts': [
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k',
             'value': 30, 'context': 'c1'},
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k',
             'value': 90, 'context': 'c2'},
            {'move_class': 'm', 'outcome': 'failed'},
            {'move_class': 'm', 'outcome': 'failed'},
            {'move_class': 'm', 'outcome': 'failed'}]})
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['trigger'], 's7_hard_signal')
        self.assertEqual(output['armed_on']['knob'], 'k')

    def test_gap3b_multi_move_class_enumeration(self):
        # GAP-3b — 복수 무브류 3회 무장 → armed_on.move_classes 전부(첫 등장 순) ∧
        # contract_reminder 쉼표 열거
        result = self.judge(self.attempts(*[self.fail_case('timeout-retune')] * 3,
                                          *[self.fail_case('prompt-rewording')] * 3))
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['armed_on'],
                         {'move_classes': ['timeout-retune', 'prompt-rewording']})
        self.assertIn('무브류 timeout-retune, prompt-rewording은 전부 밴한다',
                      output['contract_reminder'])

    def test_gap3c_nonadjacent_pair_detection(self):
        # GAP-3c — 같은 knob worked 3+ 중 비인접 상이쌍((90,cA)·(30,cA)·(30,cB) —
        # 유일 성립쌍이 0-2)도 탐지(전수 쌍 비교 회귀 방어) + working_values
        # 중복 제거·입력순(F5)
        result = self.judge(self.attempts(
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k',
             'value': 90, 'context': 'cA'},
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k',
             'value': 30, 'context': 'cA'},
            {'move_class': 'm', 'outcome': 'worked', 'knob': 'k',
             'value': 30, 'context': 'cB'}))
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['trigger'], 's7_hard_signal')
        self.assertEqual(output['armed_on']['working_values'],
                         [{'value': 90, 'context': 'cA'},
                          {'value': 30, 'context': 'cA'},
                          {'value': 30, 'context': 'cB'}])

    def test_gap5_deep_nesting_exit2(self):
        # GAP-5 LOW — 심층 중첩 JSON(60k deep array) → RecursionError도 무효 입력,
        # exit 2 ∧ stderr FAIL ∧ stdout 없음(GAP-1 동일류 — exit 1 어휘 오염 방지)
        deep = self.root / 'deep.json'
        deep.write_text('[' * 60000, encoding='utf-8')
        self.assert_config_error(self.run_gate('--history', str(deep)))


if __name__ == '__main__':
    unittest.main()
