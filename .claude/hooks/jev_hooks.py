#!/usr/bin/env python3
"""jev 판단 후크 (프로젝트 공유판) — 이 저장소(=effort-router 스킬) 기준 상대 경로.

폴백 계약: TYPESAFE_API_KEY 부재·jev exit 1·오류 시 무작동 통과 (bypass, never an error).
활성 스위치: JEV_HOOKS=0이면 전부 무작동.
- UserPromptSubmit: memory-gate — 발화 관련 기억 줄만 주입 (대상 파일: JEV_MEMORY_FILE env, 없으면 무작동)
- PreToolUse(Bash): 커맨드 신호 기록 (verify-run 이력 소스)
- PreToolUse(Agent): guard — 스폰 프롬프트 지시 섹션 가드 (악성 noul≥0.6 → ask)
- Stop: verify-run — 코드 수정 후 테스트 미실행 경고
감사: .claude/jev-signal/audit/ (gitignore).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
SKILL = str(ROOT / "scripts/jev_judge.py")
SIGNAL = ROOT / ".claude/jev-signal"
MEMORY = Path(os.environ.get("JEV_MEMORY_FILE") or Path.home()
              / ".claude/projects/-mnt-d-DEV-acc0mplish-Effort-Router/memory/MEMORY.md")
TIMEOUT = 8


def enabled():
    return (os.environ.get("JEV_HOOKS", "1") == "1"
            and os.environ.get("TYPESAFE_API_KEY")
            and Path(SKILL).is_file())


def run_jev(args):
    """jev_judge 실행 — ok json 또는 None(폴백)."""
    try:
        p = subprocess.run(
            [sys.executable, SKILL] + args,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        if p.returncode != 0:
            return None
        return json.loads(p.stdout)
    except Exception:
        return None


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0)


def read_stdin():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def cmd_prompt():
    """UserPromptSubmit — 발화 관련 기억 줄만 주입 (memory-gate)."""
    data = read_stdin()
    prompt = (data.get("prompt") or "")[:600]
    if not enabled() or len(prompt) < 10 or not MEMORY.is_file():
        emit({})
    out = run_jev(["memory-gate", prompt, "--memory-file", str(MEMORY),
                   "--save", str(SIGNAL / "audit")])
    if not out or not out.get("ok"):
        emit({})
    rec = out.get("recommendation", {})
    sel = set(rec.get("selected") or [])
    picked = [l.get("text", "").lstrip("- ").strip()
              for l in (rec.get("lines") or [])
              if l.get("line_no") in sel]
    if not picked:
        emit({})
    ctx = "[jev memory-gate] 이 발화에 관련된 기억 줄:\n" + "\n".join(
        "- " + t for t in picked if t)
    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                 "additionalContext": ctx}})


def cmd_logbash():
    """PreToolUse Bash — 커맨드 신호 기록 (verify-run 이력 소스)."""
    data = read_stdin()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        emit({})
    SIGNAL.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL / "bash-history.log", "a", encoding="utf-8") as f:
        f.write(f"{time.time():.0f}\t{cmd[:300]}\n")
    emit({})


def cmd_stop():
    """Stop — 코드 수정 후 테스트 미실행 경고 (verify-run)."""
    if not enabled():
        emit({})
    try:
        st = subprocess.run(["git", "status", "--porcelain"],
                            capture_output=True, text=True, timeout=5,
                            cwd=str(ROOT))
        changed = [l for l in st.stdout.splitlines()
                   if l and l[0] in "MM ARC" and not l.endswith(".md")
                   and "__pycache__" not in l and ".claude/jev-signal" not in l]
    except Exception:
        emit({})
    if not changed:
        emit({})
    tested = False
    hist = SIGNAL / "bash-history.log"
    cutoff = time.time() - 3600
    if hist.is_file():
        for line in hist.read_text(encoding="utf-8").splitlines()[-80:]:
            parts = line.split("\t", 1)
            if len(parts) == 2 and float(parts[0]) >= cutoff:
                c = parts[1]
                if any(k in c for k in ("pytest", "unittest", "npm test",
                                          "cargo test", "test_jev", "go test")):
                    tested = True
                    break
    record = (f"종료 턴 기록 — 작업 디렉터리 {ROOT}에서 수정된 파일: "
              f"{', '.join(c[3:] for c in changed[:5])}. "
              + (f"최근 1시간 실행 커맨드 기록에 테스트 실행 흔적이 있다: {tested}."
                 if tested else
                 "최근 1시간 실행 커맨드 기록에 테스트 실행 흔적이 없다."))
    out = run_jev(["verify-run", record, "--save", str(SIGNAL / "audit")])
    if not out or not out.get("ok"):
        emit({})
    rec = out.get("recommendation", {})
    if rec.get("verified_confirmed"):
        emit({})
    emit({"systemMessage":
          f"[jev verify-run] 코드 수정 후 빌드·테스트 실행 이행이 확인되지 않음 "
          f"(noul={rec.get('noul')}) — 수정 파일 {len(changed)}건. "
          f"테스트 실행 없이 종료하려면 그대로 두세요."})


def cmd_guard():
    """PreToolUse Agent — 스폰 프롬프트 가드 (구획 분리 계약 전제)."""
    data = read_stdin()
    prompt = (data.get("tool_input") or {}).get("prompt") or ""
    if not enabled() or len(prompt) < 50:
        emit({})
    sep = prompt.find("주입 데이터 —")
    instructions = prompt if sep < 0 else prompt[:sep].strip()
    if len(instructions.strip()) < 30:
        emit({})
    out = run_jev(["guard", prompt, "--instructions", instructions,
                   "--save", str(SIGNAL / "audit")])
    if not out or not out.get("ok"):
        emit({})
    rec = out.get("recommendation", {})
    if not rec.get("violation_confirmed"):
        emit({})
    emit({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason":
            f"[jev guard] 스폰 프롬프트 지시 섹션에 계약 밖 지시 유형 감지 "
            f"(noul={rec.get('noul')}) — 실행 전 확인 권장"
    }})


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"prompt": cmd_prompt, "stop": cmd_stop,
         "guard": cmd_guard, "logbash": cmd_logbash}[cmd]()
    except Exception:
        emit({})
    emit({})


if __name__ == "__main__":
    main()
