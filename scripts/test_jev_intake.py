#!/usr/bin/env python3
"""jev intake 모드(② 옵션 엔진) 계약 테스트 — 번들 §5 J1-J9.

test_jev_judge.py의 127.0.0.1 ThreadingHTTPServer mock loopback API 패턴을 답승한다 —
실 API·실 키 불필요. CLI는 subprocess로 실행한다(import 방식은 수집 단계 ImportError로
RED가 성립하지 않는다). 환경변수는 테스트마다 강제 주입한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/jev_judge.py'
FAKE_KEY = 'test-key-value'
ITEM_KEYS = ('target', 'task_type', 'scope', 'risk', 'verification', 'pattern_ref')
TOP_LEVEL_KEYS = {'ok', 'mode', 'model', 'recommendation', 'usage', 'audit'}
RECOMMENDATION_FIELDS = {'ok', 'gate', 'mode', 'source', 'items', 'missing_count',
                         'ambiguity_score', 'action', 'questions_max', 'context_dep',
                         'task_active', 'urgent', 'utterance', 'saved_to'}


def noul(value):
    return {'type': 'noul', 'noul': value}


def intake_payload(questions, noul_values=None, ok=True, drop_keys=()):
    """intake 질문 맵(전 noul)에 대한 스키마 합법 응답을 합성한다."""
    answers = {qid: noul((noul_values or {}).get(qid, 0.01))
               for qid in questions if qid not in drop_keys}
    return {'ok': ok, 'model': 'jev-1.13.0', 'answers': answers,
            'usage': {'input_tokens': 120, 'output_tokens': 30}}


class MockJevServer:
    """ThreadingHTTPServer mock — 설정된 응답을 돌려주고 수신 요청을 기록한다."""

    def __init__(self, noul_values=None, ok=True, drop_keys=()):
        self.noul_values = noul_values or {}
        self.ok = ok
        self.drop_keys = drop_keys
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
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                outer.requests.append({'payload': payload})
                data = json.dumps(intake_payload(payload['questions'], outer.noul_values,
                                                 outer.ok, outer.drop_keys)).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()


class JevIntakeTests(unittest.TestCase):
    def run_cli(self, *args, stdin_text=None):
        env = dict(os.environ)
        env['TYPESAFE_API_KEY'] = FAKE_KEY
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, env=env,
                              input=stdin_text)

    def test_j1_six_noul_questions(self):
        with MockJevServer() as mock:
            result = self.run_cli('intake', '고쳐줘', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        questions = mock.requests[0]['payload']['questions']
        self.assertEqual(set(questions), set(ITEM_KEYS))
        for key, question in questions.items():
            self.assertEqual(question['type'], 'noul', key)
            self.assertEqual(set(question['criteria']), {'true', 'false'}, key)

    def test_j2_noul_threshold_conversion(self):
        for value, expected in ((0.7, 'present'), (0.3, 'missing')):
            with MockJevServer(noul_values={key: value for key in ITEM_KEYS}) as mock:
                result = self.run_cli('intake', '고쳐줘', '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            items = json.loads(result.stdout)['recommendation']['items']
            for key in ITEM_KEYS:
                self.assertEqual(items[key], expected, (key, value))

    def test_j3_missing_answer_key_falls_back(self):
        # 키 부재 = exit 1 = ① 기본 엔진 폴백 신호(§3.2)
        with MockJevServer(drop_keys=('target',)) as mock:
            result = self.run_cli('intake', '고쳐줘', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertIn('missing question keys', result.stderr)

    def test_j4_ok_false_falls_back(self):
        with MockJevServer(ok=False) as mock:
            result = self.run_cli('intake', '고쳐줘', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge:', result.stderr)
        self.assertIn('ok=false', result.stderr)

    def test_j5_context_in_state_including_file_path(self):
        statement = '섹션 추가해'
        context_text = '대상 파일: README.md, 검증: 빌드 통과'
        with tempfile.TemporaryDirectory() as directory:
            context_file = Path(directory) / 'context.txt'
            context_file.write_text(context_text, encoding='utf-8')
            with MockJevServer() as mock:
                result = self.run_cli('intake', statement, '--context', str(context_file),
                                      '--endpoint', mock.endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = mock.requests[0]['payload']['state']
            self.assertIn(statement, state)
            self.assertIn(context_text, state)
            self.assertIn('[맥락]', state)
        # 리터럴 인자 경로도 동일하게 state에 포함된다
        with MockJevServer() as mock:
            result = self.run_cli('intake', statement, '--context', context_text,
                                  '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(context_text, mock.requests[0]['payload']['state'])

    def test_j6_boundary_point_six_is_confirmed(self):
        # noul ≥ 0.6 = 충족 — 경계 포함(§3.2 단일 임계 승계)
        with MockJevServer(noul_values={key: 0.6 for key in ITEM_KEYS}) as mock:
            result = self.run_cli('intake', '고쳐줘', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        items = json.loads(result.stdout)['recommendation']['items']
        self.assertTrue(all(items[key] == 'present' for key in ITEM_KEYS))

    def test_j7_audit_via_existing_pipeline(self):
        statement = '감사 저장 대상 발화'
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / 'audit'
            with MockJevServer() as mock:
                result = self.run_cli('intake', statement, '--endpoint', mock.endpoint,
                                      '--save', str(save))
            self.assertEqual(result.returncode, 0, result.stderr)
            files = list(save.glob('intake-*.json'))
            self.assertEqual(len(files), 1)
            content = files[0].read_text(encoding='utf-8')
            audit = json.loads(content)
            self.assertEqual(audit['request']['state'], statement)
            self.assertNotIn(FAKE_KEY, content)
            self.assertEqual(json.loads(result.stdout)['audit'], str(files[0]))

    def test_j8_task_active_loop_pass(self):
        # H1 — ② 경로 규칙 B: --task-active 플래그가 recommendation.action으로 전달된다
        with MockJevServer(noul_values={key: 0.9 for key in ITEM_KEYS}) as mock:
            result = self.run_cli('intake', '다시 고쳐', '--task-active',
                                  '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        recommendation = json.loads(result.stdout)['recommendation']
        self.assertEqual(recommendation['action'], 'loop_pass')
        self.assertEqual(recommendation['questions_max'], 0)
        self.assertTrue(recommendation['task_active'])

    def test_j9_stdout_structure_and_nested_field_set(self):
        # H2 — 최상위 {ok,mode,model,recommendation,usage,audit} 유지 + ① 필드 세트 중첩
        with MockJevServer(noul_values={key: 0.9 for key in ITEM_KEYS}) as mock:
            result = self.run_cli('intake', '고쳐줘', '--endpoint', mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(set(output), TOP_LEVEL_KEYS)
        self.assertEqual(output['mode'], 'intake')
        recommendation = output['recommendation']
        for field in RECOMMENDATION_FIELDS:
            self.assertIn(field, recommendation, field)
        self.assertEqual(recommendation['gate'], 'intake')
        self.assertEqual(recommendation['mode'], 'jev')
        self.assertEqual(recommendation['utterance'], '고쳐줘')
        self.assertIsNone(recommendation['saved_to'])
        self.assertAlmostEqual(recommendation['ambiguity_score'],
                               recommendation['missing_count'] / 6)

    def test_j10_note_parity_with_basic_engine(self):
        # ④리뷰 N1 — advisory+누락에서 ② recommendation.note가 ① 표기와 동일 형식.
        noul = {key: 0.9 for key in ITEM_KEYS}
        noul['risk'] = 0.2                       # 유일 누락 → advisory + note
        with MockJevServer(noul_values=noul) as mock:
            result = self.run_cli('intake', '리드미 문구 고쳐줘', '--endpoint',
                                  mock.endpoint)
        self.assertEqual(result.returncode, 0, result.stderr)
        recommendation = json.loads(result.stdout)['recommendation']
        self.assertEqual(recommendation['action'], 'advisory')
        self.assertEqual(recommendation['note'],
                         '인테이크 advisory: 누락 risk — 티어 판정 진행')

    def test_j11_context_file_read_failure_is_jev_fallback(self):
        # ④리뷰 N2 — 읽기 불가 context 파일은 jev 어휘 폴백(exit 1)이지 traceback 아님.
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as handle:
            handle.write(b'\xff\xfe\x00not-utf8')
            bad_path = handle.name
        self.addCleanup(os.unlink, bad_path)
        result = self.run_cli('intake', '고쳐줘', '--context', bad_path,
                              '--endpoint', 'http://127.0.0.1:1/')
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL jev judge: context file read failed', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
