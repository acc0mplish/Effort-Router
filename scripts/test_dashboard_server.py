#!/usr/bin/env python3
"""r36 HTML 대시보드 서버 단위테스트 — 임시 fixture 루트로 계약 전수(T1~T15).

테스트는 subprocess로 CLI를 실행한다(test_verify_pin.py 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다. RED 단계(dashboard_server.py·
dashboard_assets 부재)에서는 해당 케이스가 실패한다.
fixture는 --root(tempfile)로 주입한다 — 실 docs/task-id 의존 0(재현성).

claims 대응: T1~T12 = P1 서버·API·보안 계약(번들 §5 Phase 1 표),
T13~T15 = P2 프론트엔드 계약(자산 서빙·외부 스킴 부재·배선 정적 단정),
C1 = 본 파일 전체 exit 0.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'scripts/dashboard_server.py'
ASSETS = ROOT / 'scripts/dashboard_assets'

READY_TIMEOUT_SEC = 10.0
EXIT_TIMEOUT_SEC = 10.0
HTTP_TIMEOUT_SEC = 10.0

# fixture 상태 데이터 — done(claims 4상태 전수)·plan(빈 claims)·malformed 3종 + state.json 없는 폴더
ALPHA_STATE = {
    'task': 'alpha-done', 'tier': 'M', 'phase': 'done',
    'round': {'adversary': 2, 'review': 1}, 'spawns': 14,
    'claims': [
        {'claim': 'c-verified', 'status': 'verified', 'evidence': 'ev-1'},
        {'claim': 'c-pending', 'status': 'pending', 'evidence': ''},
        {'claim': 'c-gap', 'status': 'gap', 'evidence': 'ev-3'},
        {'claim': 'c-unknown', 'status': 'mystery', 'evidence': ''},
    ],
    'bundle': 'docs/task-id/alpha-done/bundle.md', 'next': 'review',
}
BETA_STATE = {
    'task': 'beta-plan', 'tier': 'S', 'phase': 'plan',
    'round': {'adversary': 0, 'review': 0}, 'spawns': 1,
    'claims': [],
    'bundle': 'docs/task-id/beta-plan/bundle.md', 'next': 'adversary',
}
MALFORMED_TEXT = '{ 이것은 json이 아니다'

_FIXTURE_TMP = tempfile.TemporaryDirectory()
FIXTURE_ROOT = Path(_FIXTURE_TMP.name)
_SHARED = {}  # setUpModule이 채운다: proc·base_url·snap0


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def make_fixture(root: Path) -> None:
    """번들 §5 Phase 1 fixture — 과업 3종 + state.json 없는 폴더."""
    base = root / 'docs/task-id'
    write_text(base / 'alpha-done/state.json', json.dumps(ALPHA_STATE, ensure_ascii=False))
    write_text(base / 'alpha-done/bundle.md', '# alpha 번들')
    write_text(base / 'beta-plan/state.json', json.dumps(BETA_STATE, ensure_ascii=False))
    write_text(base / 'gamma-malformed/state.json', MALFORMED_TEXT)
    (base / 'empty-folder').mkdir(parents=True, exist_ok=True)


def tree_snapshot(root: Path) -> list:
    """읽기 전용 실측용 트리 스냅샷 — (상대경로, 파일 해시|디렉터리 마커) 정렬 목록."""
    entries = []
    for path in sorted(root.rglob('*')):
        rel = str(path.relative_to(root))
        if path.is_file():
            entries.append((rel, hashlib.sha256(path.read_bytes()).hexdigest()))
        else:
            entries.append((rel, '<dir>'))
    return entries


def spawn_server(root: Path, port: int = 0, extra_args: tuple = ()) -> subprocess.Popen:
    cmd = [sys.executable, str(SERVER), '--root', str(root),
           '--port', str(port), *extra_args]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def read_ready(proc: subprocess.Popen) -> str:
    """stdout 첫 행을 READY 계약으로 파싱해 base URL을 반환한다."""
    line = proc.stdout.readline().strip()
    if not line.startswith('READY '):
        raise AssertionError(f'READY 라인 계약 위반: {line!r} (stderr 대기 아님 — 즉시 실패)')
    return line[len('READY '):]


def spawn_and_ready(root: Path, port: int = 0, extra_args: tuple = ()):
    proc = spawn_server(root, port, extra_args)
    try:
        base_url = read_ready(proc)
    except Exception:
        proc.kill()
        proc.wait()
        raise
    return proc, base_url


def stop_process(proc: subprocess.Popen, close_streams: bool = True) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=EXIT_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    if close_streams:
        for stream in (proc.stdout, proc.stderr):
            if stream and not stream.closed:
                stream.close()


def http_request(base_url: str, path: str, method: str = 'GET'):
    """http.client 원시 요청 — path-as-is(traversal 원문 경로) 검증에 필요."""
    parts = urlsplit(base_url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=HTTP_TIMEOUT_SEC)
    try:
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')
        return resp.status, dict(resp.getheaders()), body
    finally:
        conn.close()


def get_json(base_url: str) -> dict:
    status, headers, body = http_request(base_url, '/api/tasks')
    assert status == 200, f'/api/tasks 상태 {status}'
    return json.loads(body)


def find_task(payload: dict, name: str) -> dict:
    matches = [t for t in payload['tasks'] if t['task'] == name]
    assert len(matches) == 1, f'{name} 항목 유일성 실패: {len(matches)}건'
    return matches[0]


def wait_exit(proc: subprocess.Popen) -> int:
    try:
        return proc.wait(timeout=EXIT_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise AssertionError('프로세스가 종료하지 않았다 — exit 코드 계약 실패')


def setUpModule():
    make_fixture(FIXTURE_ROOT)
    _SHARED['snap0'] = tree_snapshot(FIXTURE_ROOT)
    # 내결함 기동 — RED 단계(서버 부재)에도 수집·케이스 실행은 성립해야 한다
    # (test_verify_pin.py 헤더 계약: 수집 성공 + 케이스 단위 실패).
    try:
        _SHARED['proc'], _SHARED['base_url'] = spawn_and_ready(FIXTURE_ROOT)
    except Exception as exc:  # noqa: BLE001 — 기동 실패 자체가 RED 증거다
        _SHARED['proc'] = None
        _SHARED['base_url'] = None
        _SHARED['setup_error'] = str(exc)


def tearDownModule():
    stop_process(_SHARED.get('proc'))


class DashboardServerTests(unittest.TestCase):
    """P1 서버·API·보안(T1~T12) + P2 프론트엔드(T13~T15)."""

    @property
    def base_url(self) -> str:
        base = _SHARED['base_url']
        if base is None:
            self.fail(f'공유 서버 미기동(서버 부재 = RED): {_SHARED.get("setup_error")}')
        return base

    # --- P1: 서버·API·보안 -------------------------------------------------

    def test_t01_ready_line_and_survival(self):
        """T1 — --port 0 기동: stdout READY 1행·URL 파싱·프로세스 생존."""
        proc, base_url = spawn_and_ready(FIXTURE_ROOT)
        try:
            parts = urlsplit(base_url)
            self.assertEqual(parts.scheme, 'http')
            self.assertEqual(parts.hostname, '127.0.0.1')
            self.assertIsInstance(parts.port, int)
            status, _, _ = http_request(base_url, '/api/tasks')
            self.assertEqual(status, 200)
            self.assertIsNone(proc.poll(), '요청 응답 후 프로세스가 사망했다')
        finally:
            stop_process(proc, close_streams=False)
        rest = proc.stdout.read()
        stop_process(proc)  # 파이프 닫기 — ResourceWarning 정리
        self.assertEqual(rest, '', 'READY 이후 stdout 추가 출력 존재 — stdout 1행 계약 위반')

    def test_t02_api_full_fields(self):
        """T2 — /api/tasks fixture 파싱 전수: 필드별 값 일치."""
        payload = get_json(self.base_url)
        task = find_task(payload, 'alpha-done')
        self.assertEqual(task['folder'], 'alpha-done')
        self.assertEqual(task['tier'], 'M')
        self.assertEqual(task['phase'], 'done')
        self.assertEqual(task['round'], {'adversary': 2, 'review': 1})
        self.assertEqual(task['spawns'], 14)
        self.assertEqual(task['claims_total'], 4)
        self.assertEqual(task['claims'], {'verified': 1, 'pending': 1, 'gap': 1, 'other': 1})
        self.assertEqual(task['bundle'], 'docs/task-id/alpha-done/bundle.md')
        self.assertEqual(task['next'], 'review')
        self.assertIsNone(task['parse_error'])
        self.assertEqual(len(task['claim_details']), 4)
        self.assertEqual(task['claim_details'][0],
                         {'claim': 'c-verified', 'status': 'verified', 'evidence': 'ev-1'})

    def test_t03_bundle_exists_both_sides(self):
        """T3 — bundle_exists 존재(alpha)/부재(beta) 양상."""
        payload = get_json(self.base_url)
        self.assertTrue(find_task(payload, 'alpha-done')['bundle_exists'])
        beta = find_task(payload, 'beta-plan')
        self.assertFalse(beta['bundle_exists'])
        self.assertEqual(beta['bundle'], 'docs/task-id/beta-plan/bundle.md')

    def test_t04_malformed_isolated(self):
        """T4 — malformed state.json: parse_error 비null ∧ HTTP 200 ∧ 타 과업 무영향."""
        payload = get_json(self.base_url)
        gamma = find_task(payload, 'gamma-malformed')
        self.assertIsInstance(gamma['parse_error'], str)
        self.assertGreater(len(gamma['parse_error']), 0)
        self.assertNotIn(str(FIXTURE_ROOT), gamma['parse_error'],
                         'parse_error에 절대경로 유출')
        alpha = find_task(payload, 'alpha-done')
        self.assertIsNone(alpha['parse_error'])
        self.assertEqual(alpha['phase'], 'done')

    def test_t05_folder_without_state_excluded(self):
        """T5 — state.json 없는 폴더(empty-folder)는 tasks에서 제외."""
        payload = get_json(self.base_url)
        names = [t['task'] for t in payload['tasks']]
        self.assertNotIn('empty-folder', names)

    def test_t06_response_contract(self):
        """T6 — count 일치·task 이름 오름차순·generated_at ISO8601."""
        payload = get_json(self.base_url)
        names = [t['task'] for t in payload['tasks']]
        self.assertEqual(payload['count'], len(payload['tasks']))
        self.assertEqual(payload['count'], 3)
        self.assertEqual(names, sorted(names))
        generated = payload['generated_at'].replace('Z', '+00:00')
        parsed = datetime.fromisoformat(generated)
        self.assertIsNotNone(parsed.tzinfo)

    def test_t07_traversal_blocked(self):
        """T7 — 원시·인코딩 traversal 경로 전부 404 ∧ 본문에 서버 소스 문자열 미포함."""
        attempts = [
            '/../scripts/dashboard_server.py',
            '/%2e%2e/scripts/dashboard_server.py',
            '/..%2fscripts/dashboard_server.py',
            '/dashboard_assets/../../scripts/dashboard_server.py',
        ]
        for path in attempts:
            status, _, body = http_request(self.base_url, path)
            self.assertEqual(status, 404, f'{path} → {status}')
            self.assertNotIn('argparse', body, f'{path} 응답에 서버 소스 유출')

    def test_t08_non_get_rejected(self):
        """T8 — 전 비-GET(POST·PUT·DELETE·HEAD·OPTIONS·PATCH·TRACE·CONNECT) → 405
        ∧ 본문에 stdlib HTML 에러 페이지 미포함(고정 text/plain 단문 계약)."""
        methods = ('POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH',
                   'TRACE', 'CONNECT')
        for method in methods:
            status, _, body = http_request(self.base_url, '/api/tasks', method=method)
            self.assertEqual(status, 405, f'{method} /api/tasks → {status}')
            self.assertNotIn('<!DOCTYPE', body,
                             f'{method} 응답이 stdlib HTML 에러 페이지다')

    def test_t09_unknown_paths_404(self):
        """T9 — 미지정 경로(/foo·/api/unknown) → 404."""
        for path in ('/foo', '/api/unknown'):
            status, _, _ = http_request(self.base_url, path)
            self.assertEqual(status, 404, f'{path} → {status}')

    def test_t10_read_only(self):
        """T10 — 전 시나리오 후 fixture 트리 스냅샷(setUpModule 직후)과 동일."""
        # 공유 서버 수명 전체에 걸친 쓰기 부재 — 선행 테스트의 모든 요청 포함
        status, _, _ = http_request(self.base_url, '/api/tasks')
        self.assertEqual(status, 200)
        self.assertEqual(tree_snapshot(FIXTURE_ROOT), _SHARED['snap0'])

    def test_t11_help_defaults(self):
        """T11 — --help exit 0 ∧ 기본값 5777·127.0.0.1 표시."""
        completed = subprocess.run([sys.executable, str(SERVER), '--help'],
                                   capture_output=True, text=True, timeout=EXIT_TIMEOUT_SEC)
        self.assertEqual(completed.returncode, 0)
        self.assertIn('5777', completed.stdout)
        self.assertIn('127.0.0.1', completed.stdout)

    def test_t12_port_conflict_exit_2(self):
        """T12 — 점유 포트(T1 서버) 재기동 → exit 2 ∧ stderr 사유."""
        occupied = urlsplit(self.base_url).port
        proc = spawn_server(FIXTURE_ROOT, port=occupied)
        code = wait_exit(proc)
        self.assertEqual(code, 2, f'점유 포트 기동 종료코드: {code}')
        stderr = proc.stderr.read()
        self.assertGreater(len(stderr.strip()), 0, 'stderr 사유 메시지 부재')

    # --- P2: 프론트엔드 -----------------------------------------------------

    def test_t13_static_assets_served(self):
        """T13 — 정적 3종 200 ∧ Content-Type 계약 ∧ / 본문 DOCTYPE·타이틀 마커."""
        contract = {
            '/': ('text/html; charset=utf-8', ['<!DOCTYPE html>', '<title>']),
            '/app.js': ('text/javascript; charset=utf-8', []),
            '/style.css': ('text/css; charset=utf-8', []),
        }
        for path, (ctype, markers) in contract.items():
            status, headers, body = http_request(self.base_url, path)
            self.assertEqual(status, 200, f'{path} → {status}')
            self.assertEqual(headers.get('Content-Type'), ctype, f'{path} Content-Type')
            for marker in markers:
                self.assertIn(marker, body, f'{path} 마커 {marker!r} 부재')

    def test_t14_no_external_scheme(self):
        """T14 — 자산 3파일 전수 https?:// 매치 0(오프라인·CDN 금지 계약)."""
        pattern = re.compile(r'https?://')
        for name in ('index.html', 'app.js', 'style.css'):
            path = ASSETS / name
            self.assertTrue(path.is_file(), f'자산 부재: {path}')
            matches = pattern.findall(path.read_text(encoding='utf-8'))
            self.assertEqual(matches, [], f'{name}에 외부 스킴 {len(matches)}건')

    def test_t15_frontend_wiring(self):
        """T15 — 프론트 배선 정적 단정: (a) app.js id 참조 ⊆ index.html id 집합
        (b) fetch('/api/tasks' 리터럴 (c) 갱신 주기 옵션 5000/15000/60000/0 ∧ 기본 5000."""
        html = (ASSETS / 'index.html').read_text(encoding='utf-8')
        js = (ASSETS / 'app.js').read_text(encoding='utf-8')
        ids_html = set(re.findall(r'id="([A-Za-z][\w-]*)"', html))
        ids_js = set(re.findall(r"getElementById\('([\w-]+)'\)", js))
        ids_js |= set(re.findall(r"querySelector(?:All)?\('#([\w-]+)'\)", js))
        self.assertTrue(ids_js, 'app.js에서 DOM id 참조를 추출하지 못했다')
        self.assertFalse(ids_js - ids_html,
                         f'app.js가 참조하는 미정의 id: {sorted(ids_js - ids_html)}')
        self.assertIn("fetch('/api/tasks'", js, '동일 origin API 배선 리터럴 부재')
        options = set(re.findall(r'<option value="([\w-]+)"', html))
        self.assertTrue({'5000', '15000', '60000', '0'} <= options,
                        f'갱신 주기 옵션 부족: {sorted(options)}')
        self.assertIn('5000', js, 'app.js 기본 갱신 주기 5000 리터럴 부재')


if __name__ == '__main__':
    unittest.main()
