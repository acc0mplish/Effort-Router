#!/usr/bin/env python3
"""r49 — cache_probe 단위테스트: message.id dedup·숫자 화이트리스트 6필드·exit 0/2·읽기 전용.

픽스처는 합성 JSONL이다(실 대화 원문 미사용 — usage_log 테스트 관례).
케이스: T1 dedup+sums·T2 CANARY 비유출·T3 usage 0건 exit 2·T4 부재 파일 exit 2·
T5 정상 exit 0+스키마·T6 필드 부분 누락 0채움·T7 복수 파일 합산·T8 부호화 파손 exit 2·T9 부분 부재·읽기 실패 보고·C1 읽기 전용.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import cache_probe  # noqa: E402

SCHEMA_KEYS = {'ok', 'gate', 'files', 'records', 'dropped_duplicates',
               'skipped_bad_lines', 'skipped_bad_files', 'missing_files',
               'sums', 'hit_ratio', 'max_gap_s', 'first_ts', 'last_ts'}
SUMS_KEYS = set(cache_probe.ALL_FIELDS)


def assistant_record(msg_id: str, ts: str, usage: dict | None = None,
                     content: list | None = None) -> dict:
    message: dict = {'id': msg_id, 'role': 'assistant',
                     'content': content if content is not None
                     else [{'type': 'text', 'text': 'ok'}]}
    if usage is not None:
        message['usage'] = usage
    return {'type': 'assistant', 'timestamp': ts, 'message': message}


USAGE_A = {'input_tokens': 100, 'cache_read_input_tokens': 200,
           'cache_creation_input_tokens': 0, 'output_tokens': 50}
USAGE_B = {'input_tokens': 10, 'cache_read_input_tokens': 20,
           'cache_creation_input_tokens': 30, 'output_tokens': 40,
           'cache_creation': {'ephemeral_1h_input_tokens': 5,
                              'ephemeral_5m_input_tokens': 7}}
USAGE_C = {'input_tokens': 7, 'cache_read_input_tokens': 0,
           'cache_creation_input_tokens': 0, 'output_tokens': 0}

FIXTURE_3 = [
    assistant_record('msg_1', '2026-10-22T01:00:00.000Z', USAGE_A),
    assistant_record('msg_2', '2026-10-22T01:00:10.000Z', USAGE_B),
    # 동일 message.id 재등장 2건 → dropped_duplicates
    assistant_record('msg_1', '2026-10-22T01:00:20.000Z', USAGE_A),
    {'type': 'user', 'timestamp': '2026-10-22T01:00:25.000Z',
     'message': {'role': 'user', 'content': 'USER ROW'}},
    assistant_record('msg_3', '2026-10-22T01:01:00.000Z', USAGE_C),
    assistant_record('msg_2', '2026-10-22T01:01:30.000Z', USAGE_B),
    # 파손 라인 → skipped_bad_lines
    '{"type": "assistant", broken',
]


def write_jsonl(path: Path, rows: list) -> Path:
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows),
                    encoding='utf-8')
    return path


class CollectTests(unittest.TestCase):
    """파서 직접 import 단위테스트."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_t1_dedup_and_sums(self):
        path = write_jsonl(self.dir / 'session.jsonl', FIXTURE_3)
        report = cache_probe.summarize(cache_probe.collect([str(path)]))
        self.assertEqual(report['records'], 3)
        self.assertEqual(report['dropped_duplicates'], 2)
        self.assertEqual(report['skipped_bad_lines'], 1)
        self.assertEqual(report['files'], 1)
        self.assertEqual(report['sums'], {
            'input_tokens': 117, 'cache_read_input_tokens': 220,
            'cache_creation_input_tokens': 30, 'output_tokens': 90,
            'ephemeral_1h_input_tokens': 5, 'ephemeral_5m_input_tokens': 7})
        self.assertAlmostEqual(report['hit_ratio'], 220 / 367, places=9)
        self.assertEqual(report['max_gap_s'], 50.0)

    def test_t6_partial_usage_fields_fill_zero(self):
        rows = [assistant_record('msg_1', '2026-10-22T01:00:00.000Z',
                                 {'input_tokens': 5}),
                assistant_record('msg_2', '2026-10-22T01:00:05.000Z',
                                 {'cache_read_input_tokens': 3,
                                  'cache_creation': 'not-a-dict'})]
        path = write_jsonl(self.dir / 'old-schema.jsonl', rows)
        report = cache_probe.summarize(cache_probe.collect([str(path)]))
        self.assertEqual(report['records'], 2)
        self.assertEqual(report['sums'], {
            'input_tokens': 5, 'cache_read_input_tokens': 3,
            'cache_creation_input_tokens': 0, 'output_tokens': 0,
            'ephemeral_1h_input_tokens': 0, 'ephemeral_5m_input_tokens': 0})

    def test_t7_multi_file_aggregates(self):
        first = write_jsonl(self.dir / 'a.jsonl', FIXTURE_3[:3])
        second = write_jsonl(self.dir / 'b.jsonl', FIXTURE_3[4:6])
        report = cache_probe.summarize(
            cache_probe.collect([str(first), str(second)]))
        # dedup은 파일 경계를 넘어 전역 message.id 기준 — msg_1·msg_2 재등장 전부 제거
        self.assertEqual(report['files'], 2)
        self.assertEqual(report['records'], 3)
        self.assertEqual(report['dropped_duplicates'], 2)
        self.assertEqual(report['sums']['input_tokens'], 117)
        self.assertEqual(report['sums']['output_tokens'], 90)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / 'cache_probe.py'), *args],
            capture_output=True, text=True, timeout=60)

    def test_t2_canary_text_never_leaks(self):
        path = write_jsonl(self.dir / 'canary.jsonl', [
            assistant_record('msg_1', '2026-10-22T01:00:00.000Z', USAGE_A,
                             content=[{'type': 'text',
                                       'text': 'CANARY-SECRET-TEXT'}])])
        result = self.run_cli('--jsonl', str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('CANARY-SECRET-TEXT', result.stdout)
        self.assertNotIn('CANARY-SECRET-TEXT', result.stderr)
        self.assertNotIn('USER ROW', result.stdout)

    def test_t3_zero_usage_records_exit_2(self):
        path = write_jsonl(self.dir / 'no-usage.jsonl', [
            {'type': 'user', 'timestamp': '2026-10-22T01:00:00.000Z',
             'message': {'role': 'user', 'content': 'hi'}}])
        result = self.run_cli('--jsonl', str(path))
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())

    def test_t4_missing_source_exit_2(self):
        result = self.run_cli('--jsonl', str(self.dir / 'absent.jsonl'))
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())

    def test_t5_normal_run_exit_0_full_schema(self):
        path = write_jsonl(self.dir / 'session.jsonl', FIXTURE_3)
        result = self.run_cli('--jsonl', str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        report = json.loads(lines[0])
        self.assertEqual(set(report), SCHEMA_KEYS)
        self.assertTrue(report['ok'])
        self.assertEqual(report['gate'], 'cache_probe')
        self.assertEqual(set(report['sums']), SUMS_KEYS)
        self.assertIsNotNone(report['hit_ratio'])
        self.assertIsNotNone(report['max_gap_s'])
        self.assertTrue(report['first_ts'])
        self.assertTrue(report['last_ts'])

    def test_t8_corrupt_bytes_file_exit_2(self):
        corrupt = self.dir / 'corrupt.jsonl'
        corrupt.write_bytes(b'\xff\xfe\x00\xfa not utf8 \xff')
        result = self.run_cli('--jsonl', str(corrupt))
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('FAIL cache probe', result.stderr)

    def test_t9_partial_missing_and_corrupt_reported(self):
        valid = write_jsonl(self.dir / 'ok.jsonl', FIXTURE_3)
        corrupt = self.dir / 'corrupt.jsonl'
        corrupt.write_bytes(b'\xff\xfe broken')
        result = self.run_cli('--jsonl', str(valid), str(corrupt),
                              str(self.dir / 'absent.jsonl'))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[0])
        self.assertEqual(report['skipped_bad_files'], 1)
        self.assertEqual(len(report['missing_files']), 1)
        self.assertIn('WARN cache probe', result.stderr)

    def test_c1_source_file_read_only(self):
        path = write_jsonl(self.dir / 'session.jsonl', FIXTURE_3)
        before_bytes = path.read_bytes()
        before_mtime = path.stat().st_mtime_ns
        result = self.run_cli('--jsonl', str(path), '--save', str(self.dir / 'audit'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before_bytes)
        self.assertEqual(path.stat().st_mtime_ns, before_mtime)
        self.assertEqual(len(list((self.dir / 'audit').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
