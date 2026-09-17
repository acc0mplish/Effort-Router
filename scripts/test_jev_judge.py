#!/usr/bin/env python3
"""jev_judge.py 단위테스트 — 127.0.0.1 ThreadingHTTPServer mock 기반(실 API·실 키 불필요).

테스트는 subprocess로 CLI를 실행한다(test_plan_routing.py 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다. 환경변수는 테스트마다 강제 주입해
호스트의 실제 TYPESAFE_API_KEY가 새어 들거나 실 API로 호출되는 일을 막는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/jev_judge.py'
FAKE_KEY = 'test-key-value'

# T1 픽스처 계약: tier 답은 실측 원문 그대로(스키마 근거 docs.typesafe.ai/api, 2026-09-18)
TIER_ANSWER = {'type': 'choice', 'choice': 'M', 'confidence': 0.94,
               'probabilities': {'S': 0.04, 'L': 0.0, 'M': 0.96, 'XL': 0.0}}
RISK_IDS = ('request_path', 'security_control', 'topology_unknown', 'output_document', 'gate_preset')


def noul(value):
    return {'type': 'noul', 'noul': value}


def valid_payload(questions, noul_values=None):
    """질문 맵을 받아 스키마 합법 응답을 합성한다 — tier 답은 실측 원문 그대로."""
    answers = {}
    for qid, question in questions.items():
        if qid == 'tier':
            answers[qid] = dict(TIER_ANSWER)
        elif question['type'] == 'choice':
            options = list(question['criteria'])
            answers[qid] = {'type': 'choice', 'choice': options[0], 'confidence': 0.9,
                            'probabilities': {option: 1.0 / len(options) for option in options}}
        else:
            answers[qid] = noul((noul_values or {}).get(qid, 0.01))
    return {'model': 'jev-1.13.0', 'answers': answers,
            'usage': {'input_tokens': 432, 'output_tokens': 45}}


class MockJevServer:
    """ThreadingHTTPServer mock — 설정된 응답을 돌려주고 수신 요청을 기록한다."""

    def __init__(self, status=200, sleep=0.0, responder=None, noul_values=None,
                 raw_body=None, redirect_location=None):
        self.status = status
        self.sleep = sleep
        self.responder = responder
        self.noul_values = noul_values or {}
        self.raw_body = raw_body
        self.redirect_location = redirect_location
        self.hits = 0
        self.requests = []

    @property
    def endpoint(self):
        return f'http://127.0.0.1:{self.port}/v1/systemone'

    def __enter__(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.hits += 1
                length = int(self.headers.get('Content-Length') or 0)
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = None
                outer.requests.append({'path': self.path,
                                       'headers': dict(self.headers),
                                       'payload': payload})
                if outer.sleep:
                    time.sleep(outer.sleep)
                if outer.redirect_location is not None:
                    self.send_response(302)
                    self.send_header('Location', outer.redirect_location)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if outer.status == 200:
                    if outer.raw_body is not None:
                        data = outer.raw_body
                    elif outer.responder is not None:
                        data = json.dumps(outer.responder(payload)).encode('utf-8')
                    else:
                        data = json.dumps(
                            valid_payload(payload['questions'], outer.noul_values)).encode('utf-8')
                else:
                    data = json.dumps({'error': {'message': 'mock error'}}).encode('utf-8')
                self.send_response(outer.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                # 리다이렉트 추적 회귀 검출용 — GET도 기록한다(302 추적 시 urllib가 GET /leak로 전환)
                outer.hits += 1
                outer.requests.append({'path': self.path, 'headers': dict(self.headers),
                                       'payload': None})
                self.send_response(405)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()


class JevJudgeTests(unittest.TestCase):
    def run_cli(self, *args, with_key=True, stdin_text=None, stdin_bytes=None):
        env = dict(os.environ)
        if with_key:
            env['TYPESAFE_API_KEY'] = FAKE_KEY
        else:
            env.pop('TYPESAFE_API_KEY', None)
        text = stdin_bytes is None
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=text, env=env,
                              input=stdin_bytes if stdin_bytes is not None else stdin_text)

    def test_t1_tier_happy_path(self):
        statement = '여러 모듈에 걸친 리팩터링과 테스트 보강 작업'
        with MockJevServer() as mock:
            result = self.run_cli('tier', statement, '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['ok'])
        self.assertEqual(output['mode'], 'tier')
        self.assertEqual(output['model'], 'jev-1.13.0')
        recommendation = output['recommendation']
        self.assertEqual(recommendation['tier'], 'M')
        self.assertEqual(recommendation['confidence'], 0.94)
        self.assertEqual(set(recommendation['probabilities']), {'S', 'M', 'L', 'XL'})
        self.assertEqual(set(recommendation['risks']), set(RISK_IDS))
        self.assertFalse(recommendation['any_risk'])
        self.assertIsInstance(output['usage']['input_tokens'], int)
        self.assertIsInstance(output['usage']['output_tokens'], int)
        self.assertIsNone(output['audit'])
        request = mock.requests[0]
        self.assertEqual(request['headers'].get('Authorization'), 'Bearer test-key-value')
        self.assertEqual(set(request['payload']), {'state', 'model', 'questions'})
        self.assertEqual(request['payload']['state'], statement)
        self.assertEqual(len(request['payload']['questions']), 6)

    def test_t2_risk_noul_flags(self):
        values = {f'risk_{key}': value for key, value in
                  zip(RISK_IDS, (0.01, 0.9, 0.02, 0.03, 0.04))}
        with MockJevServer(noul_values=values) as mock:
            result = self.run_cli('tier', '보안 통제 경로 변경 작업', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        recommendation = json.loads(result.stdout)['recommendation']
        self.assertTrue(recommendation['risks']['security_control'])
        self.assertFalse(recommendation['risks']['request_path'])
        self.assertTrue(recommendation['any_risk'])

    def test_t3_prune_three_stages(self):
        stages = {'plan': ('keep_full', 'thin_plan'),
                  'fanout': ('keep', 'reduce'),
                  'review': ('full_scope', 'narrow_scope')}
        for stage, options in stages.items():
            with MockJevServer(noul_values={'safe': 0.9}) as mock:
                result = self.run_cli('prune', '--stage', stage, '작업', '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output['mode'], 'prune')
            recommendation = output['recommendation']
            self.assertEqual(recommendation['stage'], stage)
            self.assertEqual(recommendation['action'], options[0])
            self.assertTrue(recommendation['safe_to_prune'])
            self.assertEqual(set(recommendation['probabilities']), set(options))
            self.assertEqual(set(mock.requests[0]['payload']['questions']), {stage, 'safe'})

    def test_t4_missing_key(self):
        with MockJevServer() as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint, with_key=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertIn('TYPESAFE_API_KEY', result.stderr)
        self.assertEqual(mock.hits, 0)

    def test_t5_http_errors(self):
        for status in (401, 500):
            with MockJevServer(status=status) as mock:
                result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL jev judge:', result.stderr)

    def test_t6_timeout(self):
        with MockJevServer(sleep=2.0) as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint, '--timeout', '0.3')
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertIn('timed out', result.stderr)

    def test_t7a_probabilities_key_mismatch(self):
        def broken_probabilities(request):
            response = valid_payload(request['questions'])
            response['answers']['tier']['probabilities'] = {'S': 1.0}
            return response

        with MockJevServer(responder=broken_probabilities) as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)

    def test_t7b_invalid_choice_value(self):
        def broken_choice(request):
            response = valid_payload(request['questions'])
            response['answers']['tier']['choice'] = 'XX'
            return response

        with MockJevServer(responder=broken_choice) as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)

    def test_t7c_noul_without_confidence_is_valid(self):
        # noul 답에 confidence 필드가 없는 것은 정상이다(docs 스키마 — 분리 검증)
        with MockJevServer() as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_t8_stdin_statement(self):
        statement = 'stdin에서 읽은 작업 서술'
        with MockJevServer() as mock:
            result = self.run_cli('tier', '-', '--endpoint', mock.endpoint, stdin_text=statement)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mock.requests[0]['payload']['state'], statement)

    def test_t9_audit_file(self):
        statement = '감사 저장 대상 작업'
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / 'audit'
            with MockJevServer() as mock:
                result = self.run_cli('tier', statement, '--endpoint', mock.endpoint,
                                      '--save', str(save))
            self.assertEqual(result.returncode, 0, result.stderr)
            files = list(save.glob('tier-*.json'))
            self.assertEqual(len(files), 1)
            content = files[0].read_text(encoding='utf-8')
            audit = json.loads(content)
            self.assertEqual(audit['request']['state'], statement)
            self.assertIn('response_raw', audit)
            self.assertNotIn(FAKE_KEY, content)
            self.assertEqual(json.loads(result.stdout)['audit'], str(files[0]))

    def test_t10_request_shape(self):
        with MockJevServer() as mock:
            self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
            self.run_cli('prune', '--stage', 'fanout', '작업', '--endpoint', mock.endpoint)
        self.assertEqual(mock.hits, 2)
        questions = mock.requests[0]['payload']['questions']
        self.assertEqual(mock.requests[0]['payload']['model'], 'jev-latest')
        self.assertEqual(len(questions), 6)
        self.assertEqual(set(questions['tier']['criteria']), {'S', 'M', 'L', 'XL'})
        for key in RISK_IDS:
            self.assertEqual(questions[f'risk_{key}']['type'], 'noul')
            self.assertEqual(set(questions[f'risk_{key}']['criteria']), {'true', 'false'})
        prune_questions = mock.requests[1]['payload']['questions']
        self.assertEqual(set(prune_questions), {'fanout', 'safe'})
        self.assertEqual(set(prune_questions['fanout']['criteria']), {'keep', 'reduce'})
        self.assertEqual(set(prune_questions['safe']['criteria']), {'true', 'false'})

    def test_t11_endpoint_guard(self):
        with MockJevServer() as mock:
            result = self.run_cli('tier', '작업',
                                  '--endpoint', 'https://evil.example/v1/systemone')
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertIn('non-loopback', result.stderr)
        self.assertEqual(mock.hits, 0)

    def test_t12_redirect_blocked(self):
        with MockJevServer() as mock:
            mock.redirect_location = f'http://127.0.0.1:{mock.port}/leak'
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertIn('redirect', result.stderr)
        leak_hits = sum(1 for request in mock.requests if request['path'] == '/leak')
        self.assertEqual(leak_hits, 0)

    def test_t13_probabilities_non_numeric(self):
        def non_numeric(request):
            response = valid_payload(request['questions'])
            response['answers']['tier']['probabilities'] = {
                'S': '0.04', 'L': 0.0, 'M': 0.96, 'XL': 0.0}
            return response

        with MockJevServer(responder=non_numeric) as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge: invalid response schema', result.stderr)

    def test_t14_response_not_utf8(self):
        with MockJevServer(raw_body=b'\xff\xfe{"model":"jev"}') as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_t15_negative_timeout(self):
        with MockJevServer() as mock:
            result = self.run_cli('tier', '작업', '--endpoint', mock.endpoint,
                                  '--timeout', '-1')
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(mock.hits, 0)

    def test_t16_stdin_not_utf8(self):
        with MockJevServer() as mock:
            result = self.run_cli('tier', '-', '--endpoint', mock.endpoint,
                                  stdin_bytes=b'\xff\xfe{"broken":"\xff"}')
        stderr = result.stderr.decode('utf-8', 'replace')
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', stderr)
        self.assertNotIn('Traceback', stderr)
        self.assertEqual(mock.hits, 0)


if __name__ == '__main__':
    unittest.main()
