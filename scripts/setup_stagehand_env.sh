#!/usr/bin/env bash
# r18 Stagehand 게이트 환경 구성 — .venv-stagehand 생성 + 의존성 설치 + Chrome 사전검증.
# pip 설치는 venv 내부에서만 수행한다(시스템 pip 금지 — 보존 제약 6).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv-stagehand"
CHROME_CANDIDATES=(/usr/bin/google-chrome /usr/bin/google-chrome-stable)

find_chrome() {
  for candidate in "${CHROME_CANDIDATES[@]}"; do
    if [ -x "$candidate" ]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  echo "FAIL stagehand setup: Chrome을 찾을 수 없다 — ${CHROME_CANDIDATES[*]} 중 하나가 필요하다" >&2
  return 1
}

main() {
  local chrome
  chrome="$(find_chrome)"
  echo "[setup] Chrome 확인: $chrome"

  if [ ! -x "$VENV/bin/python" ]; then
    echo "[setup] venv 생성: $VENV"
    python3 -m venv "$VENV"
  fi

  echo "[setup] 의존성 설치(venv 내부 pip만 사용)"
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV/bin/python" -m pip install -r "$ROOT/requirements-stagehand.txt"

  "$VENV/bin/python" -c 'import stagehand' \
    || { echo 'FAIL stagehand setup: import stagehand 실패' >&2; exit 1; }
  echo "[setup] import stagehand OK"
  echo "[setup] 완료 — 실행 예: $VENV/bin/python $ROOT/scripts/stagehand_gate.py --task-file <task.json>"
}

main "$@"
