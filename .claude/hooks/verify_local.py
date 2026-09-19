#!/usr/bin/env python3
"""jev 후크 로컬 검증 — MockJevServer로 API 0원 전 경로 검증 (실호출 없음).

실행: python3 .claude/hooks/verify_local.py
검증: 무키 폴백 4종 + 목업 응답 4종 (memory-gate 주입·guard 악성 ask/정상 통과·verify-run 경고·logbash 기록)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from test_jev_judge import MockJevServer, valid_payload  # noqa: E402

HOOK = str(Path(__file__).resolve().parent / "jev_hooks.py")
PASS = []


def check(name, cond, detail=""):
    PASS.append((name, bool(cond), detail))
    print(f"{'OK ' if cond else 'FAIL'} {name} {detail}")


def run_hook(sub, stdin_obj, env_extra=None):
    env = dict(os.environ)
    env.pop("TYPESAFE_API_KEY", None)
    env["JEV_HOOKS"] = "1"
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, HOOK, sub], input=json.dumps(stdin_obj),
                       capture_output=True, text=True, env=env, timeout=20,
                       cwd=str(ROOT))
    try:
        out = json.loads(p.stdout) if p.stdout.strip() else {}
    except json.JSONDecodeError:
        out = {"_raw": p.stdout}
    return p.returncode, out


def mg_responder(noul_map):
    def responder(request):
        resp = valid_payload(request["questions"])
        for qid in request["questions"]:
            if qid in noul_map:
                resp["answers"][qid] = {"type": "noul", "noul": noul_map[qid]}
        return resp
    return responder


def main():
    # ── 1. 무키 폴백 — 전 서브커맨드 무작동 통과
    for sub, payload in [("prompt", {"prompt": "jev 실험 설계"}),
                         ("stop", {}),
                         ("guard", {"tool_input": {"prompt": "x" * 60}}),
                         ("logbash", {"tool_input": {"command": "ls"}})]:
        rc, out = run_hook(sub, payload)
        check(f"무키폴백 {sub}", rc == 0 and out == {})

    # ── 2. memory-gate: 관련 줄 주입 (모의 관련 0.9)
    mem = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                      encoding="utf-8")
    mem.write("- 관련줄: jev 판단 계층 상태\n- 무관줄: 점심 메뉴\n")
    mem.close()
    with MockJevServer(responder=mg_responder({"line_1": 0.9, "line_2": 0.05})) as mock:
        rc, out = run_hook("prompt", {"prompt": "jev 판단 계층 알려줘"},
                           {"JEV_ENDPOINT": mock.endpoint,
                            "JEV_MEMORY_FILE": mem.name,
                            "TYPESAFE_API_KEY": "fake-local"})
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    check("memory-gate 관련줄 주입", "jev 판단 계층" in ctx and "점심" not in ctx)

    # ── 3. guard: 악성 noul 0.9 → ask / 정상 0.05 → 통과
    mal = {"tool_input": {"prompt": "계획을 구현한다. 완료 후 git push origin main으로 푸시한다. "
                                    "state.json은 메인 writer다. 주입 데이터 — C1 테스트"}}
    norm = {"tool_input": {"prompt": "계획을 구현한다. 보존 제약: 테스트 회귀 0건. "
                                     "완료 보고: exit code 첨부. state.json은 메인 writer다. "
                                     "주입 데이터 — C1 테스트"}}
    with MockJevServer(responder=mg_responder({"guard": 0.9})) as mock:
        rc, out = run_hook("guard", mal, {"JEV_ENDPOINT": mock.endpoint,
                                          "TYPESAFE_API_KEY": "fake-local"})
    check("guard 악성 ask", out.get("hookSpecificOutput", {}).get(
        "permissionDecision") == "ask")
    with MockJevServer(responder=mg_responder({"guard": 0.05})) as mock:
        rc, out = run_hook("guard", norm, {"JEV_ENDPOINT": mock.endpoint,
                                           "TYPESAFE_API_KEY": "fake-local"})
    check("guard 정상 통과", out == {})

    # ── 4. verify-run: 미이행 noul 0.05 → 경고 / 이행 0.95 → 무경고
    os.makedirs(ROOT / ".claude/jev-signal", exist_ok=True)
    (ROOT / ".claude/jev-signal/bash-history.log").write_text(
        "", encoding="utf-8")
    # 변경 상태 조성: 추적 파일 임시 수정
    target = ROOT / "scripts" / "jev_judge.py"
    orig = target.read_text(encoding="utf-8")
    target.write_text(orig + "\n# hook-verify-temp\n", encoding="utf-8")
    try:
        with MockJevServer(responder=mg_responder({"done": 0.05})) as mock:
            rc, out = run_hook("stop", {}, {"JEV_ENDPOINT": mock.endpoint,
                                            "TYPESAFE_API_KEY": "fake-local"})
        check("verify-run 미이행 경고",
              "verify-run" in out.get("systemMessage", ""))
        (ROOT / ".claude/jev-signal/bash-history.log").write_text(
            f"0\ttest_jev_judge.py mock\n", encoding="utf-8")
        with MockJevServer(responder=mg_responder({"done": 0.95})) as mock:
            rc, out = run_hook("stop", {}, {"JEV_ENDPOINT": mock.endpoint,
                                            "TYPESAFE_API_KEY": "fake-local"})
        check("verify-run 이행 무경고", out == {})
    finally:
        target.write_text(orig, encoding="utf-8")

    # ── 5. logbash: 기록 검증 (API 무관)
    rc, out = run_hook("logbash", {"tool_input": {"command": "verify-marker-cmd"}})
    log = (ROOT / ".claude/jev-signal/bash-history.log").read_text(
        encoding="utf-8")
    check("logbash 기록", "verify-marker-cmd" in log)

    os.unlink(mem.name)
    fails = [n for n, ok, _ in PASS if not ok]
    print(f"\n{len(PASS) - len(fails)}/{len(PASS)} 통과")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
