#!/usr/bin/env python3
"""r18 Stagehand 게이트 단위테스트 — 모의 러너 + 루프백 MockJevServer(실제 jev_judge.py 경유).

테스트는 subprocess로 CLI를 실행한다(test_jev_judge 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다. 브라우저·실 API 키 없이
게이트 판정 분기(pass/retry-exhausted/escalated/config)를 결정적으로 검증한다.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_jev_judge import FAKE_KEY, SCRIPT, MockJevServer

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/stagehand_gate.py'
POLICY = ROOT / 'scripts/stagehand_gate_policy.py'

LLM_KEYS = ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY')

TASK = {
    'task_id': 'cli-test-task',
    'url': 'https://example.com',
    'steps': [{'action': 'act', 'instruction': '페이지에 접속해 본문을 기다린다'}],
    'success_criteria': '본문에 Example Domain이 표시된다',
}


def attempt_responder(noul_by_request):
    """요청 순서별 noul을 다르게 응답하는 responder — retry-then-done 재현용."""
    state = {'index': 0}

    def responder(request):
        value = noul_by_request[min(state['index'], len(noul_by_request) - 1)]
        state['index'] += 1
        return {'model': 'jev-1.13.0',
                'answers': {'done': {'type': 'noul', 'noul': value}},
                'usage': {'input_tokens': 12, 'output_tokens': 4}}

    return responder


def write_task(directory, data=None):
    path = Path(directory) / 'task.json'
    path.write_text(json.dumps(data or TASK, ensure_ascii=False), encoding='utf-8')
    return str(path)


def load_policy():
    spec = importlib.util.spec_from_file_location('stagehand_gate_policy', POLICY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_gate_env(without_llm_keys=False):
    env = dict(os.environ)
    env['TYPESAFE_API_KEY'] = FAKE_KEY
    if without_llm_keys:
        for key in LLM_KEYS:
            env.pop(key, None)
    return env


def run_gate(*args, env_extra=None, without_llm_keys=False, mock_server=None):
    """stagehand_gate.py를 subprocess로 실행한다 — jev-cmd는 루프백 mock으로 주입."""
    env = build_gate_env(without_llm_keys)
    if mock_server is not None:
        args = (*args, '--jev-cmd',
                f'{sys.executable} {SCRIPT} --endpoint {mock_server.endpoint}')
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(GATE), *args],
                          capture_output=True, text=True, env=env)


class PolicyUnitTests(unittest.TestCase):
    """정책 계층 순수 함수 — import 직접 검증(I/O 없음)."""

    def test_validate_task_error_listing(self):
        module = load_policy()
        broken = {'task_id': '', 'url': 'ftp://x', 'steps': [],
                  'success_criteria': ''}
        with self.assertRaises(module.TaskValidationError) as ctx:
            module.validate_task(broken)
        messages = ctx.exception.errors
        self.assertEqual(len(messages), 4)
        for fragment in ('task_id', 'url', 'steps', 'success_criteria'):
            self.assertTrue(any(fragment in message for message in messages))
        normalized = module.validate_task(dict(TASK))
        self.assertEqual(normalized['task_id'], TASK['task_id'])
        self.assertEqual(len(normalized['steps']), 1)

    def test_consume_recommendation_violations(self):
        module = load_policy()
        violations = (
            ('not-a-dict', '문자열'),
            ('ok false', {'ok': False, 'recommendation': {'verified': True}}),
            ('ok missing', {'recommendation': {'verified': True}}),
            ('recommendation missing', {'ok': True}),
            ('field missing', {'ok': True, 'recommendation': {'noul': 0.9}}),
            ('field not bool', {'ok': True, 'recommendation': {'verified': 'true'}}),
        )
        for name, parsed in violations:
            with self.assertRaises(module.JevViolationError, msg=name):
                module.consume_recommendation('verify-run', parsed)
        consumed = module.consume_recommendation(
            'verify-run', {'ok': True, 'recommendation': {'verified': True, 'noul': 0.9}})
        self.assertEqual(consumed, {'confirmed': True, 'noul': 0.9})
        consumed_done = module.consume_recommendation(
            'done', {'ok': True, 'recommendation': {'done_confirmed': False}})
        self.assertEqual(consumed_done, {'confirmed': False, 'noul': None})


class GateCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = self._tmp.name

    def test_t1_pass_first_attempt(self):
        with MockJevServer(noul_values={'done': 0.9}) as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'done-first',
                              mock_server=mock)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['ok'])
        self.assertEqual(output['decision'], 'pass')
        self.assertEqual(output['attempts'], 1)
        self.assertEqual(output['max_attempts'], 3)
        self.assertEqual(output['last_noul'], 0.9)
        state = mock.requests[0]['payload']['state']
        for fragment in ('task_id=cli-test-task', 'attempt=1/3', 'runner=mock',
                         'url=https://example.com',
                         'success_criteria=본문에 Example Domain이 표시된다',
                         'status=success', 'result='):
            self.assertIn(fragment, state)

    def test_t2_retry_then_done(self):
        with MockJevServer(responder=attempt_responder([0.1, 0.9])) as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'retry-then-done',
                              mock_server=mock)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['decision'], 'pass')
        self.assertEqual(output['attempts'], 2)
        self.assertEqual(len(output['attempts_log']), 2)
        self.assertEqual(output['attempts_log'][0]['status'], 'error')
        self.assertEqual(output['attempts_log'][1]['status'], 'success')
        self.assertEqual(mock.hits, 2)

    def test_t3_never_done_exhausted(self):
        # claim 4 — never-done + noul 0.1: attempts == 3, exit 1
        with MockJevServer(noul_values={'done': 0.1}) as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'never-done',
                              mock_server=mock)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertFalse(output['ok'])
        self.assertEqual(output['decision'], 'retry-exhausted')
        self.assertEqual(output['attempts'], 3)
        self.assertEqual(output['max_attempts'], 3)
        self.assertEqual(mock.hits, 3)

    def test_t4_escalation_no_browser_retry(self):
        # claim 5 — jev 판단 불능(비JSON 응답 → jev FAIL exit 1): exit 3, attempts 1
        with MockJevServer(raw_body=b'not-json{{{') as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'done-first',
                              mock_server=mock)
        self.assertEqual(result.returncode, 3)
        output = json.loads(result.stdout)
        self.assertFalse(output['ok'])
        self.assertEqual(output['decision'], 'escalated')
        self.assertEqual(output['attempts'], 1)
        self.assertEqual(mock.hits, 1)

    def test_t5_runner_error_converted_to_error_record(self):
        # runner-error 예외도 게이트가 error 기록으로 변환해 재시도를 계속한다(§4.7)
        with MockJevServer(noul_values={'done': 0.1}) as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'runner-error',
                              mock_server=mock)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['decision'], 'retry-exhausted')
        self.assertEqual(output['attempts'], 3)
        for entry in output['attempts_log']:
            self.assertEqual(entry['status'], 'error')

    def test_t6_missing_llm_key_exit_2(self):
        # claim 2 — 키 부재 시 브라우저 호출 없이 즉시 exit 2
        task = write_task(self.directory)
        result = run_gate('--task-file', task, '--runner', 'stagehand',
                          without_llm_keys=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('OPENAI_API_KEY', result.stderr)
        self.assertIn('ANTHROPIC_API_KEY', result.stderr)
        self.assertFalse(result.stdout.strip())

    def test_t7_task_schema_violation_exit_2(self):
        broken = {'url': 'ftp://x', 'steps': [], 'success_criteria': ''}
        task = write_task(self.directory, broken)
        result = run_gate('--task-file', task, '--runner', 'mock')
        self.assertEqual(result.returncode, 2)
        for fragment in ('task_id', 'url', 'steps', 'success_criteria'):
            self.assertIn(fragment, result.stderr)

    def test_t8_config_ranges(self):
        task = write_task(self.directory)
        cases = (
            ('max-retries above range', ('--max-retries', '6')),
            ('max-retries negative', ('--max-retries', '-1')),
            ('invalid timeout', ('--timeout', '-1')),
            ('scenario with stagehand', ('--runner', 'stagehand',
                                         '--mock-scenario', 'done-first')),
        )
        for name, args in cases:
            result = run_gate('--task-file', task, *args)
            self.assertEqual(result.returncode, 2, name)
            self.assertIn('config error', result.stderr, name)

    def test_t8b_max_retries_zero(self):
        with MockJevServer(noul_values={'done': 0.1}) as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'never-done',
                              '--max-retries', '0', mock_server=mock)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['attempts'], 1)

    def test_t9_sdk_missing_exit_2_with_guide(self):
        # claim 8 — 가짜 키 + runner=stagehand + SDK 미설치: exit 2 + 설치 안내(스크립트명)
        task = write_task(self.directory)
        result = run_gate('--task-file', task, '--runner', 'stagehand',
                          without_llm_keys=True, env_extra={'OPENAI_API_KEY': 'fake-key'})
        self.assertEqual(result.returncode, 2)
        self.assertIn('scripts/setup_stagehand_env.sh', result.stderr)
        self.assertFalse(result.stdout.strip())

    def test_t10_done_mode_consumed(self):
        with MockJevServer(noul_values={'done': 0.9}) as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'done-first',
                              '--jev-mode', 'done', mock_server=mock)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['decision'], 'pass')
        self.assertEqual(output['jev_mode'], 'done')
        self.assertEqual(output['last_noul'], 0.9)

    def test_t11_env_fallbacks_and_flag_precedence(self):
        task = write_task(self.directory)
        # env 폴백: STAGEHAND_GATE_MAX_RETRIES=0 → 시도 1회
        with MockJevServer(noul_values={'done': 0.1}) as mock:
            result = run_gate('--task-file', task, '--runner', 'mock',
                              '--mock-scenario', 'never-done',
                              env_extra={'STAGEHAND_GATE_MAX_RETRIES': '0'},
                              mock_server=mock)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['attempts'], 1)
        # env로 죽은 endpoint 주입 → escalate. 플래그가 env를 이기면 pass(우선순위 증명)
        dead_cmd = f'{sys.executable} {SCRIPT} --endpoint http://127.0.0.1:1'
        with MockJevServer(noul_values={'done': 0.9}) as mock:
            env_result = run_gate('--task-file', task, '--runner', 'mock',
                                  '--mock-scenario', 'done-first',
                                  env_extra={'STAGEHAND_GATE_JEV_CMD': dead_cmd})
            self.assertEqual(env_result.returncode, 3)
            flag_result = run_gate('--task-file', task, '--runner', 'mock',
                                   '--mock-scenario', 'done-first',
                                   env_extra={'STAGEHAND_GATE_JEV_CMD': dead_cmd},
                                   mock_server=mock)
        self.assertEqual(flag_result.returncode, 0, flag_result.stderr)

    def test_t12_save_dir_audit(self):
        save = Path(self.directory) / 'audit'
        with MockJevServer(noul_values={'done': 0.9}) as mock:
            result = run_gate('--task-file', write_task(self.directory),
                              '--runner', 'mock', '--mock-scenario', 'done-first',
                              '--save-dir', str(save), mock_server=mock)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(save.glob('verify-run-*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
