#!/usr/bin/env python3
"""jev_modes.py 단위테스트 — 확장 판단 모드 3종(escalation·memory-gate·stall) T27~T36.

MockJevServer·run_cli 재사용(test_jev_judge) — 127.0.0.1 mock 기반(실 API·실 키 불필요).
테스트는 subprocess로 CLI를 실행한다(test_jev_judge 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_jev_judge import FAKE_KEY, SCRIPT, MockJevServer, noul, valid_payload

CASE_IDS = ('workload_surge_observed', 'harness_constraint_measured',
            'user_explicit_directive', 'not_justified')
STALL_IDS = ('working', 'waiting_declared', 'approval_pending', 'terminated', 'stalled')


def run_cli(*args, stdin_text=None, stdin_bytes=None):
    env = dict(os.environ)
    env['TYPESAFE_API_KEY'] = FAKE_KEY
    text = stdin_bytes is None
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=text, env=env,
                          input=stdin_bytes if stdin_bytes is not None else stdin_text)


def choice_responder(qid, choice, confidence):
    """choice 질문의 답을 특정 choice·confidence로 고정한다 — 게이트 경계 검증용."""
    def responder(request):
        response = valid_payload(request['questions'])
        options = list(request['questions'][qid]['criteria'])
        response['answers'][qid] = {'type': 'choice', 'choice': choice,
                                    'confidence': confidence,
                                    'probabilities': {option: 1.0 if option == choice else 0.0
                                                      for option in options}}
        return response
    return responder


def write_memory_file(directory, name, lines):
    path = Path(directory) / name
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(path)


class JevModeTests(unittest.TestCase):
    def test_t27_escalation_happy_path(self):
        reason = '착수 시 3파일 예상이었으나 조사 결과 14파일이 동일 결함 패턴에 걸려 있다'
        with MockJevServer() as mock:
            result = run_cli('escalation', reason, '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['ok'])
        self.assertEqual(output['mode'], 'escalation')
        recommendation = output['recommendation']
        # mock 기본 choice 답은 options[0] — 허용 방향이라 conf 바닥 없음(reject_confirmed 거짓)
        self.assertEqual(recommendation['decision'], 'workload_surge_observed')
        self.assertEqual(recommendation['case'], 'workload_surge_observed')
        self.assertEqual(recommendation['confidence'], 0.9)
        self.assertEqual(set(recommendation['probabilities']), set(CASE_IDS))
        self.assertFalse(recommendation['reject_confirmed'])
        self.assertIsInstance(output['usage']['input_tokens'], int)
        request = mock.requests[0]
        self.assertEqual(request['payload']['state'], reason)
        questions = request['payload']['questions']
        self.assertEqual(set(questions), {'decision'})
        self.assertEqual(questions['decision']['type'], 'choice')
        self.assertEqual(set(questions['decision']['criteria']), set(CASE_IDS))

    def test_t28_escalation_reject_gate(self):
        # 기각 확정은 not_justified ∧ conf≥0.85만 — 허용 방향은 conf 바닥 없음(계획 §2.3)
        cases = (('not_justified', 0.84, False), ('not_justified', 0.85, True),
                 ('workload_surge_observed', 0.95, False))
        for choice, confidence, expected in cases:
            with MockJevServer(responder=choice_responder('decision', choice, confidence)) as mock:
                result = run_cli('escalation', '사유', '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            recommendation = json.loads(result.stdout)['recommendation']
            self.assertEqual(recommendation['decision'], choice, confidence)
            self.assertEqual(recommendation['case'],
                             None if choice == 'not_justified' else choice, confidence)
            self.assertEqual(recommendation['reject_confirmed'], expected, confidence)

    def test_t29_escalation_rules_file(self):
        # 커스텀 허용 규칙 교체 — criteria가 questions에 반영되고 not_justified는 항상 병설
        with tempfile.TemporaryDirectory() as directory:
            rules_path = Path(directory) / 'rules.json'
            rules_path.write_text('{"custom_case": "커스텀 사유 설명"}', encoding='utf-8')
            with MockJevServer() as mock:
                result = run_cli('escalation', '사유', '--rules-file', str(rules_path),
                                 '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            criteria = mock.requests[0]['payload']['questions']['decision']['criteria']
            self.assertEqual(set(criteria), {'custom_case', 'not_justified'})
            self.assertEqual(criteria['custom_case'], '커스텀 사유 설명')

            violations = (('not json {{', 'non-JSON'), ('{}', 'empty object'),
                          ('{"case": 1}', 'non-string value'))
            for content, name in violations:
                broken = Path(directory) / 'broken.json'
                broken.write_text(content, encoding='utf-8')
                with MockJevServer() as mock:
                    result = run_cli('escalation', '사유', '--rules-file', str(broken),
                                     '--endpoint', mock.endpoint)
                self.assertEqual(result.returncode, 1, name)
                self.assertIn('FAIL jev judge:', result.stderr, name)
                self.assertEqual(mock.hits, 0, name)

            missing = Path(directory) / 'missing.json'
            with MockJevServer() as mock:
                result = run_cli('escalation', '사유', '--rules-file', str(missing),
                                 '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL jev judge:', result.stderr)
            self.assertEqual(mock.hits, 0)

    def test_t30_memory_gate_fanout(self):
        # 비빈 줄 수만큼 line_{n} 질문 1호출 fan-out — selected는 noul 내림차순 top-k
        request = 'OAuth 리다이렉트 루프 버그를 수정한다'
        lines = ['OAuth 토큰 갱신은 refresh 우선', '리다이렉트 URI는 콜백과 정확히 일치시킨다',
                 '세션 쿠키 갱신 시 루프가 난다', '다크 테마 선호는 토글로 저장한다']
        noul_values = {'line_1': 0.9, 'line_2': 0.7, 'line_3': 0.95, 'line_4': 0.2}
        with tempfile.TemporaryDirectory() as directory:
            memory_path = write_memory_file(directory, 'memory.md', lines)
            with MockJevServer(noul_values=noul_values) as mock:
                result = run_cli('memory-gate', request, '--memory-file', memory_path,
                                 '--top-k', '2', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['ok'])
        self.assertEqual(output['mode'], 'memory-gate')
        self.assertEqual(mock.requests[0]['payload']['state'], request)
        questions = mock.requests[0]['payload']['questions']
        self.assertEqual(set(questions), {f'line_{n}' for n in range(1, 5)})
        self.assertTrue(all(question['type'] == 'noul' for question in questions.values()))
        self.assertIn(lines[0], questions['line_1']['instructions'])
        recommendation = output['recommendation']
        self.assertEqual(recommendation['top_k'], 2)
        self.assertEqual(recommendation['selected'], [3, 1])
        self.assertEqual(recommendation['stats'], {'total': 4, 'relevant_count': 3})
        self.assertEqual([entry['line_no'] for entry in recommendation['lines']], [1, 2, 3, 4])
        self.assertEqual([entry['noul'] for entry in recommendation['lines']],
                         [0.9, 0.7, 0.95, 0.2])
        self.assertEqual([entry['relevant'] for entry in recommendation['lines']],
                         [True, True, True, False])
        self.assertEqual(recommendation['lines'][0]['text'], lines[0])

    def test_t31_memory_gate_dead_zone(self):
        # 관련성 임계는 기존 noul_confirmed(≥0.6) 재사용 — dead zone 0.4~0.6 불통과
        noul_values = {'line_1': 0.59, 'line_2': 0.60}
        with tempfile.TemporaryDirectory() as directory:
            memory_path = write_memory_file(directory, 'memory.md', ['경계 아래', '경계 위'])
            with MockJevServer(noul_values=noul_values) as mock:
                result = run_cli('memory-gate', '요청', '--memory-file', memory_path,
                                 '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        recommendation = json.loads(result.stdout)['recommendation']
        self.assertEqual([entry['relevant'] for entry in recommendation['lines']],
                         [False, True])
        self.assertEqual(recommendation['selected'], [2])
        self.assertEqual(recommendation['stats'], {'total': 2, 'relevant_count': 1})

    def test_t32_memory_gate_preprocess_and_limit(self):
        request = '요청 서술'
        with tempfile.TemporaryDirectory() as directory:
            # frontmatter(줄 1~4)·빈 줄(5·6·8·9) 제외, 원 줄번호 유지(7·10)
            lines = ['---', 'title: 기억', 'tags: x', '---', '', '  ', '일곱째 줄 내용',
                     '', '', '열째 줄 내용']
            memory_path = write_memory_file(directory, 'memory.md', lines)
            with MockJevServer() as mock:
                result = run_cli('memory-gate', request, '--memory-file', memory_path,
                                 '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            questions = mock.requests[0]['payload']['questions']
            self.assertEqual(set(questions), {'line_7', 'line_10'})
            recommendation = json.loads(result.stdout)['recommendation']
            self.assertEqual(recommendation['stats'], {'total': 2, 'relevant_count': 0})
            self.assertEqual(recommendation['lines'][0],
                             {'line_no': 7, 'text': '일곱째 줄 내용', 'noul': 0.01,
                              'relevant': False})
            # stdin 라인 소스('--memory-file -')
            with MockJevServer() as mock:
                result = run_cli('memory-gate', request, '--memory-file', '-',
                                 '--endpoint', mock.endpoint,
                                 stdin_text='stdin 첫 줄\n\nstdin 셋째 줄')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(set(mock.requests[0]['payload']['questions']),
                             {'line_1', 'line_3'})
            # 비빈 줄 101개 → FAIL(조용한 truncation 금지 — 결정 D5)
            overflow = write_memory_file(directory, 'overflow.md',
                                         [f'줄 {n}' for n in range(1, 102)])
            with MockJevServer() as mock:
                result = run_cli('memory-gate', request, '--memory-file', overflow,
                                 '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL jev judge:', result.stderr)
            self.assertEqual(mock.hits, 0)
            # statement와 --memory-file 동시 '-' → FAIL(stdin 이중 소비 불가)
            with MockJevServer() as mock:
                result = run_cli('memory-gate', '-', '--memory-file', '-',
                                 '--endpoint', mock.endpoint, stdin_text='x')
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL jev judge:', result.stderr)
            self.assertEqual(mock.hits, 0)

    def test_t33_stall_happy_path(self):
        # 신호 직렬화가 결정적 state로 전송된다 — 검증 신호 값 식자·claim 격리 문구(결정 D4)
        signals = {'last_tool_age_s': 3500, 'last_file_write_age_s': 3500,
                   'last_assistant_text': None, 'declared_state': None}
        with MockJevServer(responder=choice_responder('state', 'stalled', 0.93)) as mock:
            result = run_cli('stall', json.dumps(signals), '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['ok'])
        self.assertEqual(output['mode'], 'stall')
        recommendation = output['recommendation']
        self.assertEqual(recommendation['state'], 'stalled')
        self.assertEqual(recommendation['confidence'], 0.93)
        self.assertEqual(set(recommendation['probabilities']), set(STALL_IDS))
        self.assertTrue(recommendation['intervene_confirmed'])
        state = mock.requests[0]['payload']['state']
        self.assertIn('마지막 도구 호출 3500초 전', state)
        self.assertIn('마지막 파일 기록 3500초 전', state)
        self.assertIn('워커 자기 보고', state)
        questions = mock.requests[0]['payload']['questions']
        self.assertEqual(set(questions), {'state'})
        self.assertEqual(questions['state']['type'], 'choice')
        self.assertEqual(set(questions['state']['criteria']), set(STALL_IDS))

    def test_t34_stall_schema_violations(self):
        base = {'last_tool_age_s': 10, 'last_file_write_age_s': 20,
                'last_assistant_text': None}
        violations = (
            ('negative tool age', {**base, 'last_tool_age_s': -1}),
            ('string tool age', {**base, 'last_tool_age_s': '10'}),
            ('missing last_tool_age_s',
             {'last_file_write_age_s': 20, 'last_assistant_text': None}),
            ('negative write age', {**base, 'last_file_write_age_s': -5}),
            ('assistant text non-string', {**base, 'last_assistant_text': 3}),
        )
        for name, signals in violations:
            with MockJevServer() as mock:
                result = run_cli('stall', json.dumps(signals), '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 1, name)
            self.assertIn('FAIL jev judge:', result.stderr, name)
            self.assertNotIn('Traceback', result.stderr, name)
            self.assertEqual(mock.hits, 0, name)
        with MockJevServer() as mock:
            result = run_cli('stall', 'not-json {{', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertEqual(mock.hits, 0)

    def test_t35_stall_intervene_gate(self):
        # 개입 확정은 stalled ∧ conf≥0.85 — working은 conf와 무관하게 거짓(계획 §2.3)
        signals = json.dumps({'last_tool_age_s': 4000, 'last_file_write_age_s': 4000,
                              'last_assistant_text': '거의 다 됐습니다',
                              'declared_state': 'working'})
        cases = (('stalled', 0.85, True), ('stalled', 0.84, False),
                 ('working', 0.95, False))
        for choice, confidence, expected in cases:
            with MockJevServer(responder=choice_responder('state', choice, confidence)) as mock:
                result = run_cli('stall', signals, '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            recommendation = json.loads(result.stdout)['recommendation']
            self.assertEqual(recommendation['state'], choice, confidence)
            self.assertEqual(recommendation['intervene_confirmed'], expected, confidence)

    def test_t36_stall_file_path_input(self):
        # 신호 JSON 파일 경로 입력 — 원문 JSON과 동일 결과
        signals = {'last_tool_age_s': 900, 'last_file_write_age_s': 1200,
                   'last_assistant_text': '외부 API 응답 대기 중 — 15분 타임아웃',
                   'declared_state': 'waiting'}
        raw = json.dumps(signals, ensure_ascii=False)
        runs = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'signals.json'
            path.write_text(raw, encoding='utf-8')
            for spec in (str(path), raw):
                with MockJevServer(responder=choice_responder('state', 'waiting_declared',
                                                              0.9)) as mock:
                    result = run_cli('stall', spec, '--endpoint', mock.endpoint)
                self.assertEqual(result.returncode, 0, result.stderr)
                runs.append((mock.requests[0]['payload']['state'],
                             json.loads(result.stdout)['recommendation']))
        self.assertEqual(runs[0], runs[1])
        self.assertIn('마지막 도구 호출 900초 전', runs[0][0])
        self.assertIn("declared_state='waiting'", runs[0][0])
        self.assertIn('외부 API 응답 대기 중', runs[0][0])
        self.assertFalse(runs[0][1]['intervene_confirmed'])


if __name__ == '__main__':
    unittest.main()
