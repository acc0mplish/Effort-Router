#!/usr/bin/env python3
"""r47 대시보드 자동 기동 멱등 래퍼 단위테스트 — 임시 포트·fixture로 계약 전수.

테스트는 subprocess로 CLI를 실행한다(test_dashboard_server.py 관습).
실제 dashboard_server.py를 에페메럴 포트에 띄우고 프로브·멱등성을 관측한다.

claims 대응:
- T1 = 사중 포트 기동(started 수취 + HTTP 200 + pid 정합),
- T2 = 멱등성(기동 중 포트 재호출 → already · 2중 미기동),
- T3 = 무효 --workspace 스킵(항상 exit 0 · 미기동),
- T4 = 무효 포트 스킵(항상 exit 0),
- T5 = 로그 파일 기록(spawn 시 생성),
- T6 = 비-HTTP 리스너 보수 판정(가비지 응답 → already · exit 0),
- T7 = argparse 인자 오류(조기 종료 흡수 · exit 0),
- C1 = 본 파일 전체 exit 0.
"""
from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSTART = ROOT / 'scripts/dashboard_autostart.py'
SERVER = ROOT / 'scripts/dashboard_server.py'

CLI_TIMEOUT_SEC = 30.0
KILL_WAIT_SEC = 10.0


def free_port() -> int:
    """OS에서 미사용 포트 1개 확보(소켓 즉시 반납 — 희박한 재점유 경합 감수)."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def http_ok(port: int) -> bool:
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2).close()
        return True
    except OSError:
        return False


def run_cli(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AUTOSTART), *extra],
        capture_output=True, text=True, timeout=CLI_TIMEOUT_SEC)


class AutostartTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.log = self.root / 'autostart.log'
        self.port = free_port()
        self._pids: list[int] = []
        self.addCleanup(self._kill_recorded)

    def _kill_recorded(self) -> None:
        for pid in self._pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        deadline = time.monotonic() + KILL_WAIT_SEC
        for pid in list(self._pids):
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(0.1)
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass

    def _record_pid_from_receipt(self, proc: subprocess.CompletedProcess) -> None:
        match = re.search(r'pid=(\d+)', proc.stdout + proc.stderr)
        if match:
            self._pids.append(int(match.group(1)))

    def test_t1_dead_port_starts_and_serves(self) -> None:
        proc = run_cli('--port', str(self.port), '--root', self.root,
                       '--log', self.log, '--timeout', '8')
        self._record_pid_from_receipt(proc)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertRegex(proc.stdout, r'^AUTOSTART started\s+http://127\.0\.0\.1:\d+ '
                                     r'pid=\d+ ready=\d+(\.\d+)?s\n?$')
        self.assertTrue(http_ok(self.port))

    def test_t2_live_port_idempotent_no_second_spawn(self) -> None:
        server = subprocess.Popen(
            [sys.executable, str(SERVER), '--port', str(self.port),
             '--root', self.root],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        self._pids.append(server.pid)
        deadline = time.monotonic() + KILL_WAIT_SEC
        while not http_ok(self.port) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(http_ok(self.port), msg='fixture 서버 미기동')
        proc = run_cli('--port', str(self.port), '--root', self.root,
                       '--log', self.log)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertRegex(proc.stdout, r'^AUTOSTART already\s+http://127\.0\.0\.1:\d+\n?$')
        self.assertTrue(http_ok(self.port))  # 기존 서버 생존 유지

    def test_t3_invalid_workspace_skips_spawn(self) -> None:
        proc = run_cli('--port', str(self.port), '--root', self.root,
                       '--workspace', str(self.root / '없는-디렉터리'),
                       '--log', self.log)
        self.assertEqual(proc.returncode, 0, msg='항상 exit 0 계약')
        self.assertIn('skip', proc.stderr)
        self.assertFalse(http_ok(self.port))  # 기동하지 않았다

    def test_t4_invalid_port_always_exit_zero(self) -> None:
        proc = run_cli('--port', '0', '--log', self.log)
        self.assertEqual(proc.returncode, 0, msg='항상 exit 0 계약')
        self.assertIn('skip', proc.stderr)

    def test_t5_log_file_written_on_spawn(self) -> None:
        proc = run_cli('--port', str(self.port), '--root', self.root,
                       '--log', self.log, '--timeout', '8')
        self._record_pid_from_receipt(proc)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        deadline = time.monotonic() + KILL_WAIT_SEC
        while not self.log.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(self.log.exists(), msg='로그 파일 미생성')

    def test_t6_non_http_listener_conservative_already(self) -> None:
        listener = socket.socket()
        listener.bind(('127.0.0.1', self.port))
        listener.listen(4)
        self.addCleanup(listener.close)

        def serve_garbage() -> None:
            while True:
                try:
                    conn, _ = listener.accept()
                except OSError:
                    return  # cleanup close — 스레드 탈출
                with conn:
                    try:
                        conn.sendall(b'not-http garbage\r\n')
                    except OSError:
                        pass

        threading.Thread(target=serve_garbage, daemon=True).start()
        proc = run_cli('--port', str(self.port), '--log', self.log)
        self._record_pid_from_receipt(proc)  # 보수 판정 회귀 시 고아 서버 방어
        self.assertEqual(proc.returncode, 0, msg='항상 exit 0 계약(리스너 미기동)')
        self.assertRegex(proc.stdout, r'^AUTOSTART already')

    def test_t7_argparse_error_absorbed_exit_zero(self) -> None:
        proc = run_cli('--port', 'abc')
        self.assertEqual(proc.returncode, 0, msg='항상 exit 0 계약(파싱 오류)')
        self.assertIn('skip', proc.stderr)


if __name__ == '__main__':
    unittest.main()
