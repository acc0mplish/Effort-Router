#!/usr/bin/env python3
"""대시보드 SessionStart 자동 기동 — 멱등 래퍼(r47).

이미 127.0.0.1:<포트>가 대시보드에 응답하면 아무것도 하지 않고, 응답이 없을
때만 dashboard_server.py를 기동한다(setsid nohup 상당 — start_new_session 트리,
부모 종료·세션 종료 무관 생존). Claude Code SessionStart 훅에서 호출한다.

계약:
- 종료 코드는 항상 0이다 — 훅이 세션 시작을 방해하지 않는다(실패·스킵 사유는
  stderr와 stdout 수취 라인으로만 남는다).
- 바인드를 건드리지 않는다 — 서버 기본 127.0.0.1(로컬 전용)을 그대로 쓴다.
  외부 노출 인자(--bind)는 제공하지 않는다.
- 프로브는 HTTP GET /(타임아웃 1초). 응답이면 전부(404 포함) 기동 중 판정.
  타임아웃·기타 오류는 보수적으로 기동 중으로 본다 — 이중 기동 방지가 우선이다.
- 동시 훅 경합: 두 세션이 동시에 프로브 실패 후 기동하면 늦은 쪽이 bind 오류로
  즉시 exit 2로 죽는다 — 무해하다(로그에만 남는다).
- state.json writer는 메인 세션 단일 — 본 스크립트는 서버를 띄울 뿐 상태를
  쓰지 않는다(서버 자체가 읽기 전용).

사용:
    python3 scripts/dashboard_autostart.py [--workspace DIR] [--port 5777]
                                           [--log FILE] [--root DIR] [--timeout 10]

SessionStart 훅 장착(타 서버 ~/.claude/settings.json — 병합, 기존 훅 보존):
    {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
        "command": "python3 /절대경로/Effort-Router/scripts/dashboard_autostart.py --workspace /워크스페이스/루트"}]}]}}}

stdout 수취 계약(정확히 1행):
    AUTOSTART already  http://127.0.0.1:<포트>
    AUTOSTART started  http://127.0.0.1:<포트> pid=<n> ready=<초>
    AUTOSTART already  http://127.0.0.1:<포트> — 경합: 타 기동이 승리(자체 스폰은 bind 오류로 종료)
stderr 전용(exit 0은 유지 — 세션 시작 방해 없음):
    AUTOSTART unconfirmed http://127.0.0.1:<포트> pid=<n> — 제한시간 내 미응답
    AUTOSTART skip — <사유>
"""
from __future__ import annotations

import argparse
import http.client
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 5777
DEFAULT_TIMEOUT_SEC = 10.0
PROBE_TIMEOUT_SEC = 1.0
POLL_INTERVAL_SEC = 0.2
DEFAULT_LOG = Path('~/.cache/effort-router-dashboard.log').expanduser()
SERVER = Path(__file__).resolve().parent / 'dashboard_server.py'


def port_serving(port: int) -> bool:
    """127.0.0.1:<포트>에 HTTP 응답이 오는가.

    거부(ConnectionRefused)만 미기동(False)이다. 타임아웃·비-HTTP 응답
    (HTTPException — 가비지 리스너 등)·기타 오류는 보수적으로 기동 중(True)으로
    본다 — 무언가 포트를 점유 중이므로 이중 기동보다 미기동 판정이 안전하다.
    """
    url = f'http://127.0.0.1:{port}/'
    try:
        urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_SEC).close()
        return True
    except urllib.error.HTTPError:
        return True  # 응답 자체가 기동 중 증거(404 포함)
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            return False
        return True  # 타임아웃 등 — 보수적으로 기동 중
    except (OSError, http.client.HTTPException):
        return True


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='대시보드 멱등 자동 기동 (SessionStart 훅용 — 항상 exit 0)')
    parser.add_argument('--workspace', type=Path, default=None,
                        help='dashboard_server --workspace 전달(미지정 시 home 단일)')
    parser.add_argument('--root', type=Path, default=None,
                        help='dashboard_server --root 전달(테스트 격리용)')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help=f'대상 포트 (기본 {DEFAULT_PORT})')
    parser.add_argument('--log', type=Path, default=DEFAULT_LOG,
                        help=f'기동 로그 (기본 {DEFAULT_LOG})')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_SEC,
                        help=f'기동 후 응답 대기 제한시간 초 (기본 {DEFAULT_TIMEOUT_SEC})')
    return parser.parse_args(argv)


def spawn_server(args: argparse.Namespace) -> int | None:
    """dashboard_server.py를 분리 세션으로 기동하고 pid를 돌려준다."""
    cmd = [sys.executable, str(SERVER), '--port', str(args.port)]
    if args.workspace is not None:
        cmd += ['--workspace', str(args.workspace)]
    if args.root is not None:
        cmd += ['--root', str(args.root)]
    args.log.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(args.log, 'a', encoding='utf-8')
    try:
        proc = subprocess.Popen(
            cmd, stdout=log_fh, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True)
    finally:
        log_fh.close()
    return proc.pid


def pid_alive(pid: int) -> bool:
    """스폰 pid 생존 확인 — 경합 수취 구분용(타 기동 승리 시 자체 스폰은 죽는다)."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main(argv=None) -> int:
    """항상 exit 0 — argparse 조기 종료(SystemExit)·미처리 예외도 수취로 흡수한다."""
    try:
        return _run(argv)
    except SystemExit as exc:  # argparse 인자 오류 등
        if exc.code not in (None, 0):  # --help 등 정상 종료(0)는 무음 통과
            print(f'AUTOSTART skip — 인자 파싱 조기 종료({exc.code})', file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 — 훅 세션 방해 금지 계약
        print(f'AUTOSTART skip — {type(exc).__name__}: {exc}', file=sys.stderr)
        return 0


def _run(argv=None) -> int:
    args = parse_args(argv)
    if not 1 <= args.port <= 65535:
        print(f'AUTOSTART skip — 무효 포트 {args.port}', file=sys.stderr)
        return 0
    if args.workspace is not None and not args.workspace.is_dir():
        print(f'AUTOSTART skip — --workspace {args.workspace} 은 디렉터리가 아니다',
              file=sys.stderr)
        return 0
    url = f'http://127.0.0.1:{args.port}'
    if port_serving(args.port):
        print(f'AUTOSTART already  {url}')
        return 0
    pid = spawn_server(args)
    started_at = time.monotonic()
    deadline = started_at + max(args.timeout, 0.0)
    while time.monotonic() < deadline:
        if port_serving(args.port):
            if not pid_alive(pid):
                print(f'AUTOSTART already  {url} — '
                      f'경합: 타 기동이 승리(자체 스폰은 bind 오류로 종료)')
                return 0
            elapsed = round(time.monotonic() - started_at, 1)
            print(f'AUTOSTART started  {url} pid={pid} ready={elapsed}s')
            return 0
        time.sleep(POLL_INTERVAL_SEC)
    print(f'AUTOSTART unconfirmed {url} pid={pid} — 제한시간 내 미응답(로그 확인)',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
