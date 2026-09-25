# effort-router

작업의 규모·위험도를 티어(S/M/L/XL)로 판정하고 단계별 모델·에포트를 배정하는 Codex·ChatGPT Skill. 일반 작업은 GPT-6-Luna max, 계획·고난도 추론은 GPT-6-Sol xhigh를 사용한다.

```text
Decision(티어 판정) → Requirement → Acceptance → Task → Evidence → Learning
```

## 왜 필요한가

- 단일 모델·단일 에포트로 모든 과업을 처리하면 단순 수정에 과투자, 대형 변경에 과소검증이 된다
- 자기 산출물 검토는 검토가 아니다 — 검토는 역할과 산출물이 분리된 별도 에이전트가 해야 한다
- 서브에이전트 호출은 무상태다 — 단계 사이를 잇는 상태 계약(state.json·증거번들)이 없으면 인계가 산문 재구성에 의존해 무너진다

## 구조

| 경로 | 내용 |
|------|------|
| `SKILL.md` | 스킬 본체 — 티어 판정(§1)·라우팅 테이블(§2)·실행 제약(§3)·merge 권한(§4)·상태·인계 계약(§5)·타 하니스 매핑(§6)·Output Contract |
| `AGENTS.md` | 저장소 작업의 모델·에포트 정책과 역할 템플릿 오류 예방 규칙 |
| `agents/` | Claude Code 역할 정의 10종 + ChatGPT 데스크톱 UI 메타데이터 `openai.yaml` |
| `platforms/` | Codex·ChatGPT 실행 어댑터와 기타 하니스 파생 문서 |
| `scripts/` | 전역 Codex 역할 라우팅·설치 검증 스크립트 + jev 판단 계층 CLI(jev_judge.py·jev_modes.py — CLI 12종: tier·prune·escalation·memory-gate·stall·done·dup·loop·verify-run·watch·route·guard) + Stagehand 게이트 CLI(stagehand_gate.py 3종) + 검증 핀 게이트 CLI(verify_pin.py) + 워크트리 수명주기 게이트 CLI(worktree_gate.py 4종: create·done·list·sweep) |
| `TESTS.md` | 검증 프로토콜·측정 결과·라운드별 개정 이력·재현 절차 |

## 설치 (Codex + ChatGPT 데스크톱 앱)

### 1. Skill·custom agents 설치

```bash
mkdir -p ~/.codex/skills/effort-router
cp -R SKILL.md TESTS.md README.md agents platforms scripts ~/.codex/skills/effort-router/

mkdir -p ~/.codex/agents
cp platforms/codex-agents/*.toml ~/.codex/agents/
python3 scripts/configure_codex_plan.py --apply
```

### 2. `~/.codex/config.toml` 전역 설정

기존 파일을 통째로 교체하지 말고 다음 값을 병합한다. `model`과 `model_reasoning_effort`는 첫 TOML table보다 위의 root 영역에 둔다.

```toml
model = "gpt-6-luna"
model_reasoning_effort = "max"

[agents]
enabled = true
```

이미 `[agents]`가 있으면 table을 다시 만들지 말고 `enabled = true`만 추가·수정한다. 기존 설치가 `[features]`의 `multi_agent = true`를 쓰며 정상 작동한다면 그대로 유지해도 된다.

`agents.enabled`는 custom role 설정을 활성화할 뿐 native spawn/fan-out을 허용하지 않는다. 이 정책에서 독립 보조 작업은 별도 `codex exec` 프로세스에 모델과 effort를 명시해 실행한다.

### 3. `~/.codex/AGENTS.md` 전역 발동 규칙

기존 내용을 보존하고 다음 단편을 추가한다.

```markdown
코딩 작업 착수 전 설치된 `effort-router`를 사용한다. 일반 작업은 GPT-6-Luna max, 계획·고난도 추론은 GPT-6-Sol xhigh를 사용한다. Terra는 사용하지 않는다. native spawn/fan-out은 사용하지 않는다.
`configure_codex_plan.py --apply`는 고정 전역 role 매핑만 적용하고, 변경 후 Codex를 재시작한다. 동일 접근 2회 실패 시 GPT-6-Sol xhigh로 검토하고 확정된 구현은 GPT-6-Luna max로 진행한다.

## 실패 기반 영구 예방 규칙

- 주요 agent guide file은 Codex의 `AGENTS.md`, Claude Code의 `CLAUDE.md`, Cursor의 `.cursorrules`다.
- 관측되거나 재현된 과거 실패 1건을 영구 예방 규칙 1줄로 변환한다.
- 규칙은 실패 트리거와 필수/금지 행동을 포함하고, 다음 작업에서 준수 여부를 판정할 수 있어야 한다.
- 같은 실패의 기존 규칙이 있으면 새 줄을 만들지 말고 기존 규칙을 더 정확하게 고친다.
- 모든 저장소에 적용되는 규칙만 전역 파일에 두고, 프로젝트 고유 규칙은 가장 가까운 프로젝트 guide file에 둔다.
```

### 4. 재로드·검증

ChatGPT 데스크톱 앱의 Codex 화면은 같은 로컬 Skill과 `~/.codex` 설정을 공유한다. ChatGPT Work는 Skill을 사용할 수 있지만 로컬 custom-agent TOML을 전제로 하지 않으므로 앱의 model/reasoning control에서 같은 매핑을 직접 선택한다. 자세한 구분은 `platforms/chat-app.md`.

설치 후 Codex CLI·IDE·ChatGPT 앱을 재시작하고 검사한다.

```bash
python3 ~/.codex/skills/effort-router/scripts/verify_global_install.py
```

`PASS global effort-router installation`이 나와야 로컬 Skill, 전역 모델·effort, subagent 활성화, 전역 발동 규칙, 10개 custom agent가 모두 설치된 상태다. 상세 병합법은 `platforms/codex.md` 참조.

### (선택) jev 판단 계층

`scripts/jev_judge.py`는 비싼 추론 스폰 전 예판을 돕는 선택 계층이다. `TYPESAFE_API_KEY` 환경변수만 읽으며, 셸 프로파일(예: `~/.bashrc`)에 아래 한 줄을 둔다.

```bash
export TYPESAFE_API_KEY='<본인 키>'
```

미설정 시 스킬은 기존 프로세스로 동작한다 — jev는 선택 계층이며, 키 부재 시 jev_judge.py는 exit 1 폴백 신호를 낸다. 사용 규칙(데이터 유출 면·감사 저장·권한 계약)은 SKILL.md의 '판단 계층(jev)' 절을 따른다.

`unset TYPESAFE_API_KEY`가 즉시 비활성 스위치다(호출 전 폴백). 키 로테이션 시 셸 프로파일의 모든 export 지점을 함께 갱신한다. 판단 모드는 **CLI 12종** — tier·prune·escalation·memory-gate·stall 기본 5종 + 채택 판정 7종(done·dup·loop·verify-run·watch·route·guard).

**판단 역할 (실험 1200호출로 캘리브레이션됨)** — 판정 1호출 비용(~0.3초·~1.2k 토큰)은 승인·차단하는 행동(심층 스폰·오배치) 비용의 극소수 %:

| 가능 (채택) | 근거 |
|------------|------|
| CLI 기본 5종 — tier·prune·escalation·stall·memory-gate | 각 실험 통과 (SKILL.md jev 절) |
| CLI 채택 7종 — done(done 조건 충족)·dup(todo 중복/우산)·loop(도구 루프)·verify-run(검증 이행)·watch(PR 코멘트 watch급)·route(스폰 역할 배치)·guard(프롬프트 가드) | 실험 채택 → 모드화 이식(템플릿 바이트 일치·스모크 7/7 판정 일치) |

| 불가 (확정) | 이유 |
|-------------|------|
| 4지+ 다중 선택 | 단일 답 수렴 — 예/아니오 연쇄로 쪼개야 함 (연쇄로 역할 배치는 성공) |
| 간접 관련성 회수 | 직접 연결만 판별 — 넓히면 무관까지 회수 |
| 인용문 내 지시 구분 | 마킹 무력 — "주입 데이터 —" 라벨 뒤 구획 분리로만 해결 |
| 권위 오염 필터 | conf 유지한 채 판단 이동 — 서술 위생(state 위생)이 1차 방어 |
| noul 수치 보간 | 방향 신호 — 임계 통과/실패만, 0.4~0.6은 판단 보류 |

설계 원칙: 질문 쪼개기 · 판별 소재 질문 내장 · 사실 필드(이력·신호)로 주기 · 예외 조건 미리 적기. 상세 원리·한계 표는 SKILL.md '판단 계층(jev)' 절 참조.

### Stagehand 게이트 (r21)

`scripts/stagehand_gate.py`는 브라우저 실행 계층(Stagehand)과 판단 계층(jev)을 잇는 래퍼다. Stagehand로 태스크를 실행 → 시도 기록을 jev verify-run/done으로 판정 → 판정에 따라 재시도·종료·에스컬레이션한다. jev 결합은 서브프로세스뿐이며, recommendation의 `verified`/`done_confirmed` 불리언만 소비한다(noul 임계 재해석 없음).

구조: `stagehand_gate.py`(게이트 CLI 본체) · `stagehand_gate_policy.py`(순수 판정 정책 — 스키마 검증·recommendation 소비·게이트 결정) · `stagehand_runner.py`(실행 계층 — 모의 러너 4시나리오 + 실 Stagehand 러너 지연 임포트).

```bash
# 환경 구성(1회) — .venv-stagehand/ 생성 + 의존성 핀 설치 + Chrome 확인
bash scripts/setup_stagehand_env.sh

# 모의 실행(키·브라우저 불필요 — 게이트 로직 검증용)
python3 scripts/stagehand_gate.py --task-file scripts/fixtures/stagehand_gate_task.example.json \
  --runner mock --mock-scenario retry-then-done

# 실 Stagehand 실행(venv python + LLM 키 필요 — OPENAI_API_KEY 또는 ANTHROPIC_API_KEY)
.venv-stagehand/bin/python scripts/stagehand_gate.py \
  --task-file scripts/fixtures/stagehand_gate_task.example.json
```

| 환경변수 | 용도 |
|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Stagehand LLM(어느 하나) — runner=stagehand일 때 필수 |
| `TYPESAFE_API_KEY` | jev 판단 호출 |
| `STAGEHAND_GATE_JEV_CMD` | jev 커맨드 오버라이드(플래그 > env > 기본) |
| `STAGEHAND_GATE_MAX_RETRIES` | 재시도 상한 env 폴백(기본 2, 0..5) |
| `STAGEHAND_MODEL` | Stagehand LLM 모델명(기본 `openai/gpt-4o-mini` — 과금 레이트 결정) |

| 종료코드 | 의미 |
|---|---|
| 0 | pass — jev 판정 불리언 true |
| 1 | retry-exhausted — 총 시도(1+max_retries) 소진 후에도 미확정 |
| 2 | config/env 오류 — 키 부재·SDK 미설치·태스크 스키마 위반 등(즉시 종료) |
| 3 | escalated — jev 판단 불능(exit≠0·비JSON·ok≠true). 브라우저 재시도 없이 즉시 상향 |

SDK 미설치 환경에서는 `--runner stagehand`가 exit 2로 실패-폐쇄한다(안내에 `scripts/setup_stagehand_env.sh` 포함). 게이트 분기 전수는 모의 러너 + 루프백 jev mock으로 `python3 scripts/test_stagehand_gate.py`에서 결정적으로 검증한다.

사용 시점·폴백·경제성·권한 계약(선택 실행 계층 옵션의 사용 규칙)은 SKILL.md의 '실행 계층(Stagehand 게이트)' 절을 따른다 — jev 위임 패턴('판단 계층(jev)' 절 위임)과 평행이다. 미설정·미구성(venv·SDK·LLM 키 부재) 시 이 계층 없이 기존 프로세스로 동작한다(exit 2 = bypass).
모의 실행도 jev 판정 단계에는 `TYPESAFE_API_KEY`(또는 `--jev-cmd` 오버라이드)가 필요하다. 실 Stagehand 실행 경로는 모의 러너만 검증됐다 — SDK 표면 불일치로 첫 실실행이 실패할 수 있으니 소규모 태스크로 수동 확인한다.

### 검증 핀 게이트 (r23)

`scripts/verify_pin.py`는 검증의 자기참조 구멍(검증 대상인 테스트를 약화·삭제·신규 무력화 파일로 우회해도 재실행은 같은 약화본을 통과시킨다)과 핀 부재(옛 검증으로 새 코드가 통과한다)를 메우는 결정론 게이트다. 읽기 전용 git과 검증명령 subprocess만 쓰며 jev·LLM·외부 전송·과금이 없다 — 저장소 국소 의존(venv·fixtures)이 없어 **미러 동봉 대상**이다(Stagehand 게이트의 저장소 루트 상대·미동봉과 다르다).

```bash
# M+ 코드 과업 verify 단계 — 앵커(구현 착수 전 커밋) 지정이 원칙
python3 scripts/verify_pin.py --base <앵커> \
  --expect-sha <직전 검증 HEAD> \
  --verify-cmd 'python3 scripts/test_verify_pin.py' \
  --save docs/task-id/<task-id>/
```

| 플래그 | 기본 | 설명 |
|---|---|---|
| `--base REF` | 없음 | diff 기준 커밋(앵커 = 구현 착수 전 커밋). 미지정 시 검증 입력 검사 `not_evaluated` — **미검사 ≠ 변경 없음** |
| `--expect-sha SHA` | 없음 | 직전 검증 실행이 기록한 HEAD SHA — 불일치 시 `sha_mismatch` |
| `--verify-cmd CMD` | 없음 | 재실행 검증명령(shlex 분할 — 셸 미경유, 파이프·리다이렉션 불가, 필요 시 `bash -c "..."` 전달) |
| `--timeout SEC` | 600 | verify-cmd 타임아웃(양수 유한 — 위반 시 exit 2) |
| `--pattern PAT` | 없음(반복 가능) | 검증 입력 패턴 추가(기본 패턴에 append — multipurpose 그룹 미적용) |
| `--save DIR` | 없음 | 결과 JSON 저장 디렉터리(`verify-pin-<UTC타임스탬프>.json` — jev --save 계약 평행) |

| 계층 | 플래그 | 해제 조건 |
|---|---|---|
| 재검증 | `sha_mismatch`·`verify_cmd_failed`·`verify_cmd_timeout` | 확인 대화만으로 done 불가 — 게이트 재실행으로 플래그 소멸 확인(예: `--expect-sha`를 현재 HEAD로 갱신 후 재실행) |
| 정당화 | `verification_input_modified`·`multipurpose_config_modified`·`verification_input_hidden`·`verification_input_ignore_hidden` | 해당 diff·은닉 확인 + 사유 기재(은닉은 `git update-index --no-assume-unchanged`/`--no-skip-worktree` 해제, ignore는 .gitignore·.git/info/exclude 제외 해제 후 재실행으로 소멸 확인 권장) |

| 종료코드 | 의미 |
|---|---|
| 0 | pass — 플래그 0건(수행한 검사 전부 통과, 미지정 검사는 평가 제외) |
| 1 | attention — 확인 의무 플래그 1건 이상. **jev의 exit 1(폴백=진행)과 정반대** — 확인 없이 진행하면 계약 위반 |
| 2 | config·env·git 오류 — 즉시 종료, stderr `FAIL verify pin: <사유>`, stdout 없음. **저장(--save) 실패만 예외**: 검사 결과 stdout JSON(`saved_to: null`) 출력 후 exit 2 |
| 3 | 미사용 — 판단 계층(jev)이 없어 상향(escalation) 경로 자체가 없다(번호 재용 않음) |

검증 입력 패턴 — `fnmatchcase`(경로 전체 또는 basename, 플랫폼 대소문자 무관. Python fnmatch의 `*`는 `/`를 관통하므로 `tests/*`가 `tests/unit/x.py`까지 덮는다):

| 그룹 | 기본 패턴 | 플래그 |
|---|---|---|
| 검증 입력(기본 8종 + `--pattern` 확장) | `tests/*` · `test/*` · `test_*.py` · `*_test.py` · `conftest.py` · `pytest.ini` · `tox.ini` · `.github/workflows/*` | `verification_input_modified` |
| 다목적 설정 | `pyproject.toml` · `setup.cfg` | `multipurpose_config_modified` |

검출 파이프라인: `git diff --name-only <base>`(tracked — 커밋·staged·unstaged·삭제) ∪ `git ls-files --others --exclude-standard`(untracked 신규 — **패턴 통과분만 반영**, 신규 conftest·테스트 우회 차단) ∪ `git ls-files -v` 은닉 스캔(`h` assume-unchanged·`S` skip-worktree 태그 — diff·status 양쪽에서 파일을 감춰 증거 워크플로 동반 마비시키는 우회를 검증 입력·다목적 설정 파일에 그룹 구분 없이 `verification_input_hidden` + `hidden_files`(양 그룹 통합 목록)로 드러낸다 — 그룹 2 은닉은 pyproject 무력화 직통 우회다). `--exclude-standard`라 제외된 untracked는 diff·untracked 검출 밖이다 — 검증 파일을 ignore하는 구성 자체가 저장소 위생 이상 신호다. 이 구멍은 `git ls-files --others`(제외 없음) 대조로 메운다: 제외된 untracked 검증 입력·다목적 파일은 `verification_input_ignore_hidden` + `ignore_hidden_files`로 드러난다(.gitignore·.git/info/exclude·전역 excludesFile 전부 — 원인은 `git check-ignore -v`로 확인, 매칭은 전체경로 한정·의존성 트리 test 파일 오탐 방지, r25). **완전 차단이 아니다** — 공모 약화는 노출되나 해제는 사유 기재고 감시 자동화 없이 호출 시점 1회 판정이다(r25). git 호출은 `-c core.autocrlf=false -c core.quotePath=false` 고정(CRLF 정규화 위플래그·비ASCII 경로 C-인용 fnmatch 무력화 차단), subprocess 디코드는 `errors='replace'`(비UTF-8 파일명 크래시 방지).

```json
{"ok": false, "gate": "verify-pin", "timestamp_utc": "...", "head_sha": "<HEAD 전체 SHA>",
 "pin": {"expect_sha": null, "base_ref": "<인자 원문|null>", "base_sha": "<resolve된 SHA|null>",
         "sha_matched": null},
 "verification_input": {"status": "clean|modified|not_evaluated",
                        "patterns": ["<검증 입력 그룹 패턴 전체>"],
                        "modified_files": ["tests/test_a.py"],
                        "multipurpose_files": ["pyproject.toml"],
                        "hidden_files": [],
                        "ignore_hidden_files": []},
 "verify_cmd": {"command": "<원문>", "exit_code": 0, "timed_out": false, "duration_s": 1.2,
                "stdout_tail": "<말미 500자>", "stderr_tail": "<말미 500자>"},
 "flags": ["verification_input_modified"], "saved_to": null}
```

`verify_cmd`는 미지정 시 `null`. `saved_to`는 --save 미지정·실패 모두 `null`. 타임아웃 시 `verify_cmd_timeout`만 발행하고 `verify_cmd_failed`를 병기하지 않는다(배타성). `ok` = `len(flags)==0`. 게이트 분기 전수는 임시 git 저장소 fixture로 `python3 scripts/test_verify_pin.py`에서 결정적으로 검증한다(T1~T16). 사용 시점·플래그 2계층·호출·감사·폴백 계약은 SKILL.md의 '검증 핀 게이트(verify_pin)' 절을 따른다.

### 워크트리 수명주기 게이트 (r24)

`scripts/worktree_gate.py`는 워크트리 격리 과업의 수명주기 — 생성·완료 제거 — 를 기계 강제하는 게이트다(원 요구: "작업완료시 제거를 강제해야될꺼 같은데 맨날 용량없음"). 미포스 `git worktree remove`는 작업 트리가 dirty(tracked 수정·staged)하거나 untracked 파일이 있으면 `--force` 요구로 거부된다 — 수동 제거가 반복 실패해 방치되는 경로다. 게이트는 미커밋 변경분(tracked 수정·staged·untracked 비ignored)만 자동 salvage 커밋으로 보존한 뒤 `remove --force`·prune한다 — 강제 제거가 기본이되 데이터 파기는 아니며, ignored 파일(venv·node_modules·빌드 산출)은 폐기 대상이다. 커밋은 본체 오브젝트 저장소에 공유되므로 디렉터리 제거 자체는 커밋 분실이 아니다.

```bash
# 생성 — 저장소 외부 <repo>-worktrees/<task-id>에 worktree + 브랜치 wt/<task-id>
python3 scripts/worktree_gate.py create --task <task-id> [--base <커밋>]

# 완료 — salvage(필요 시) → remove --force → prune → 레지스트리 갱신
python3 scripts/worktree_gate.py done --task <task-id> [--drop-branch] [--no-salvage]

# 적체 대조 — 제거 대상(done·고아) 존재 시 exit 1
python3 scripts/worktree_gate.py list [--du]

# 일괄 정리 — 보고 먼저, 실제 sweep은 사용자 명시 시에만
python3 scripts/worktree_gate.py sweep --dry-run
python3 scripts/worktree_gate.py sweep [--drop-branch]
python3 scripts/worktree_gate.py sweep --unmanaged   # 미관리(수동·기존 잔존분)도 salvage 후 제거
```

**exit 1은 attention — 셸 체인에서 조용히 무시하지 않는다**(jev의 exit 1 폴백=진행과 정반대). rc 확인 패턴:

```bash
python3 scripts/worktree_gate.py done --task <task-id>
rc=$?
if [ "$rc" -eq 1 ]; then
  echo "salvage 커밋 발생 — push 전 salvage.files 열람 필요"  # 확인 후 진행
elif [ "$rc" -ne 0 ]; then
  exit "$rc"  # exit 2 — 사유는 stderr
fi
```

| 서브커맨드 | 인자 | 동작 |
|---|---|---|
| `create` | `--task`(필수) `--base REF`(기본 HEAD) | task-id 검증 → 중복 레지스트리·경로·잔존 브랜치·base 선행 검사 → `worktree add -b wt/<task-id>` → 레지스트리 기록. add 실패 시 생성된 브랜치 best-effort 정리(부분 실패 원자성) |
| `done` | `--task`(필수) `--drop-branch` `--no-salvage` | 7단계: 대상 확정(레지스트리리스 경로 포함) → 멱등 → locked → phase 검사(r25) → salvage(동시 작성 감지 루프, r25) → remove --force → prune → 기록 |
| `list` | `--du` | worktree·레지스트리·state.json phase 대조 entries + summary. 제거 대상 1건 이상 시 exit 1 |
| `sweep` | `--dry-run` `--unmanaged` `--drop-branch` | eligible(done·고아)에 done 절차 일괄 적용. `--dry-run`은 보고만(무변경), `--unmanaged`는 미관리도 salvage 후 제거 |

| 종료코드 | 의미 |
|---|---|
| 0 | 완료 — 절차 성공. list는 제거 대상 0건. `done --no-salvage`·멱등 already_removed·`sweep --dry-run`도 0(명시 폐기·보고는 확인 의무가 아니다 — JSON 기록으로 남는다) |
| 1 | attention — 확인 의무 플래그 1건 이상. **jev의 exit 1(폴백=진행)과 정반대** — verify_pin과 동일 어휘 |
| 2 | config·env·git 오류 — 즉시 종료, stderr `FAIL worktree gate: <사유>`, stdout 없음. **저장(--save) 실패만 예외**: 결과 stdout JSON(`saved_to: null`) 출력 후 exit 2 |
| 3 | 미사용 — 판단 계층(jev)이 없어 상향(escalation) 경로 자체가 없다(번호 재용 않음) |

| 플래그 | 발행 조건 | 확인 절차 |
|---|---|---|
| `salvage_committed` | done·sweep에서 미커밋 변경분을 salvage 커밋했다 | 완료 선언·push 전 `salvage.files` 열람 — 시크릿 확인 시 브랜치 drop 후 시크릿 교체 |
| `removable_worktrees_present` | list에서 제거 대상(done·고아) 잔존 | done·sweep으로 해소 |
| `worktree_missing` | 활성 레지스트리인데 디렉터리가 게이트 밖에서 소실 | 잔여 미커밋분 손실 가능 — 수동 확인 후 정리 |

**명명·레지스트리** — worktree 경로 `<본체 저장소 부모>/<저장소 디렉터리명>-worktrees/<task-id>`, 브랜치 `wt/<task-id>`(미관리 salvage 전용 `salvage/unmanaged-<UTC스탬프>`), 레지스트리 본체 `<repo>/docs/task-id/<task-id>/worktree.json`(worktree 파기에도 본체에 생존 — 고아 판정·명명규칙 재구성의 뿌리). task-id 검증 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` — 팬아웃 렌즈용 `<task-id>-l<n>`도 통과한다. 모든 경로 파생은 `git rev-parse --git-common-dir` 본체 식별 기준 — worktree 내부에서 실행해도 본체 기준으로 동작한다.

```json
{"version": 1, "gate": "worktree-gate", "task": "r25-x", "path": "<abs>",
 "branch": "wt/r25-x", "base_ref": "HEAD", "base_sha": "<sha>",
 "created_utc": "...", "done_utc": null, "salvage_commit": null,
 "dropped_branch_tip": null}
```

done 결과 JSON(레지스트리리스·고아 경로의 복구 기록은 stdout·--save JSON이 담당한다):

```json
{"ok": false, "gate": "worktree-gate", "subcommand": "done", "task": "r24-x",
 "timestamp_utc": "...",
 "worktree": {"path": "<abs>", "branch": "wt/r24-x", "removed": true,
              "already_removed": false, "registry_less": false},
 "salvage": {"performed": true, "commit": "<sha>", "changes": 3,
             "files": ["src/a.py", "notes.txt"],
             "skipped_by_option": false, "discarded_changes": 0, "rounds": 1},
 "pruned": true,
 "branch": {"name": "wt/r24-x", "preserved": true, "dropped": false, "tip_sha": "<sha>"},
 "registry": {"path": "docs/task-id/r24-x/worktree.json", "updated": true},
 "flags": ["salvage_committed"], "saved_to": null}
```

**왜 저장소 외부인가** — 저장소 내부 배치(`.worktrees/`)는 (a) 게이트가 타 저장소의 .gitignore를 수정해야 하고(범용 배포 계약과 충돌) (b) grep·LSP·파일 감시가 중복 소스 트리 전체를 훑는다(토큰·인덱싱 오염). 외부 컨테이너는 프로젝트 무변경이며 쓰기 범위가 명명규칙 단일 디렉터리로 예측 가능하다. 부모 디렉터리 쓰기 불가 시 exit 2(fail-closed).

**sweep 자격** — managed(레지스트리 존재, 또는 고아 시 명명규칙 재구성: 컨테이너 내 디렉터리명=task-id ∧ 브랜치 `wt/<task-id>`) 전제로 (a) `state.json`의 `phase=="done"` 리터럴 (b) 고아 — 과업 폴더 자체 소실. **폴더가 남아 있고 state.json만 파손·부재면 고아가 아니다 — 보존한다**(판독 불가 = 판단 보류). 활성 phase·불일치(phase≠done ∧ done_utc 기록)·미관리(컨테이너 밖·수동 생성·detached HEAD)는 기본 보고만이며 제거는 `--unmanaged` 명시 시뿐이다 — 존재 ≠ 허가. 본체 작업 트리(porcelain 첫 항목)는 항상 제외다. `--unmanaged`의 salvage는 `salvage/unmanaged-*` 브랜치에 적립해 **원본 브랜치 포인터를 변경하지 않는다**. locked worktree는 `--unmanaged`에서도 제거하지 않는다(salvage 전 보존 분류 — unlock 후 재시도, r25).

**데이터 유출 면** — salvage 커밋은 미커밋 파일 전부를 브랜치에 편입한다 — 시크릿(`.env.local` 등)·대형 바이너리 포함 가능하며 편입분은 본체 오브젝트 저장소에 영구 추가된다. 게이트 자체는 외부 전송이 없으나 **salvage 브랜치를 push하면 편입 파일이 원격에 공개된다** — `salvage_committed`(exit 1)의 확인 절차가 push 전 `salvage.files` 열람이다. 폐기 각오 시 `done --no-salvage`(폐기 수 JSON 기록 — done 전용, sweep에는 미제공).

**salvage의 디스크 비용 — 부분 해소다** — 주 절감은 worktree 디렉터리 해분(ignored 대다수 = venv·node_modules·빌드 산출)이다. salvage 편입분은 비ignored 내용 크기만큼 본체 `.git`에 영구 추가된다 — 대량 산출물이 .gitignore 미등록이면 절감이 상쇄될 수 있다. `.gitignore` 등록이 병행 전제다.

**locked worktree** — lock은 사용자의 보존 신호다. 게이트는 자동 unlock하지 않고 exit 2 사유에 안내한다: `git worktree unlock <path>` 후 재시도. 사용자 확인 후 강제하려면 `git worktree remove -f -f <path>`(문서로만 제공 — 게이트가 실행하지 않는다).

**기타 한정** — `list --du`는 `du -sb`(GNU 전용 — 실패·비GNU 시 bytes null). salvage 커밋은 identity 미정의 환경에서도 게이트 identity(`worktree-gate <worktree-gate@local>`)로 성립하고 pre-commit hook은 `--no-verify`로 우회한다(기계 절차 — hook 판단 무의미). remove 실패(파일 잠금·권한) 시 exit 2 — 재호출이 salvage 재판정(공백)으로 2중 커밋 없이 수렴한다. phase≠done 활성 과업 done·동시 작성 지속 감지 시에도 exit 2로 차단한다(보존 방향 — 동시 작성 중단 시에도 부분 결과 JSON이 stdout에 남는다, r25). 제거 후 기록 단계 실패 시 부분 결과 JSON을 stdout에 남긴 뒤 exit 2한다(r25). 게이트 분기 전수는 임시 git 저장소 fixture로 `python3 scripts/test_worktree_gate.py`에서 결정적으로 검증한다(T1~T34·r25 hardening T35~T44 — 별도 파일 test_worktree_gate_hardening.py). 사용 시점·호출 주체(메인 세션 단일)·시점 계약·저장소 외부 효과는 SKILL.md의 '워크트리 수명주기 게이트(worktree_gate)' 절을 따른다.

## 모델 매핑

일반 작업은 `gpt-6-luna / max`, 계획·고난도 추론은 `gpt-6-sol / xhigh`다. Terra는 사용하지 않는다. 이 설치에서는 native spawn/fan-out을 사용하지 않는다.

| 작업 | 모델·effort |
|---|---|
| 구현·조사·테스트·검증 | `gpt-6-luna / max` |
| 계획·명세·아키텍처 | `gpt-6-sol / xhigh` |
| 계획 검토·리뷰·보안 판정 | `gpt-6-sol / xhigh` |

`python3 scripts/configure_codex_plan.py --apply`는 고정 role 매핑을 백업과 함께 적용한다. 상세 설정과 검증은 [Codex adapter](platforms/codex.md)를 따른다.

## 다른 하니스에서 쓰기

Claude Code와 기타 환경에서는 티어 판정·증거 계약·Output Contract를 유지하고 각 하니스의 모델 체계로 치환한다.

| 환경 | 어댑터 | 형태 |
|------|--------|------|
| Codex CLI | `platforms/codex.md` | AGENTS.md 병합 단편 + 커스텀 에이전트 TOML(`~/.codex/agents/`) role↔effort 매핑표 |
| Qwen Code | `platforms/qwen.md` | QWEN.md 병합 단편 |
| Gemini CLI | `platforms/gemini.md` | GEMINI.md 병합 단편 |
| GLM Coding Plan | `platforms/glm.md` | 백엔드 교체 매핑(Claude Code 하니스 유지) |
| ZCode (GLM 백엔드) | `platforms/zcode.md` | 빌트인 스폰 + 역할 계약 주입 매핑. 백엔드 교체(Claude Code+GLM)는 glm.md |
| ChatGPT 앱 | `platforms/chat-app.md` | Codex 화면/Work/ChatGPT Classic 구분 |
| Grok Bot (Cursor) | `platforms/grok.md` | 스킬 저장 + Task/CloudAgent 매핑. xAI grok.com은 chat-app.md |

설치·붙여넣기 절차는 `platforms/README.md`. 어댑터는 본문의 파생 축약 이식본이다 — 규칙 충돌 시 SKILL.md가 우선한다.

## 핵심 원칙

- **존재 ≠ 허가** — 호출 가능한 에이전트는 §2 화이트리스트뿐. 테이블 밖 파일은 무시한다
- **증거기반 보고** — 완료 보고는 서술이 아니라 실행 명령 원문 + exit code. 상위 세션은 핵심 검증 1회 재실행
- **state.json 단일 writer** — 서브에이전트는 쓰지 않고 메인 세션이 패치. 재개는 대화 히스토리 추측 없이 `next`·`bundle`부터
- **무효화 전파** — 원 요구·계약·외부 수정·번들 갱신이 일어나면 그 입력에 의존하는 검증 완료 claims를 재검증 대상으로 되돌린다(상세 계약은 §5 무효화 전파)
- **gap이 다음 라운드를 만든다** — claims 전부 verified + CRITICAL·HIGH 부재일 때만 done. 라운드 상한 없음(자율 연속 진행) — 2회 연속 같은 결함 재발 시 ① 회귀로 경로 전환
- **라우팅의 본질은 effort 수치가 아니라 역할·산출물 분리** — effort는 환경 의존(프록시에서 조용히 강등될 수 있음, §3 실측)

## 근거·참조논문

- **역할 3분(Project Planner/Developer/QA)·증거번들·계보** — [1]에서 증류
- **상태계약 원형**(state.json·최소정보·명시적 실행 상태) — [2]
- **반복의 효과 실측**: 반복 3회 원샷 대비 +17~22pt(GameCraft Overall), 10회까지 상승(FrontierSWE Dominance) — [1]의 평가에서 관측. 이득의 원천은 호출량이 아니라 호출 사이를 잇는 상태다
- **외부 하니스 상태의 구성(Belief·Progress·Experience)과 선택적 상태 접근** — [4]. state.json 최소정보·압축 재개 원침의 이론적 배경
- **기각 이력의 재주입(반려 근거 주입 계약)** — [5]. 기각된 후보를 다음 수정 호출에 되먹여 같은 실패 제안의 변형 반복을 막는 구조가 §2 반려 게이트의 반려 근거 주입 계약 원형이다
- **관측 기반 규칙의 외부 실측** — [5]. 결함 있는 손작업 전문가 그래프가 MultiChallenge 전체 성공률을 87.50 → 58.93로 깎았고(결함 있는 사전의 게이트 없는 1회 갱신은 53.57로 악화), 검증 게이트를 갖춘 반복 진화만 92.86로 회복시켰다 — '관측된 실패 1건 → 규칙 1줄' 실패 원장 원칙의 교차 근거
- **진단 조건부 재시도 > 무진단 재샘플링(난이도 클수록 격차 확대)·검증 통과 ≠ 요구 충실성(거짓 증명서 방지)** — [6]

### 참조논문

1. Haoyang Yan, Min-le Su, Hangfan Zhang, Zhanhao Li, Chen Zhang, Shao Zhang, Yang Chen, Lei Bai, Shuyue Hu. *Harness-of-Harness: Multi-Day Autonomous Software Development with Continual Improvement.* arXiv:2609.01481 [cs.AI], 2026. — https://arxiv.org/abs/2609.01481
2. Sanket Badhe, Priyanka Tiwari, Jonghyun Chung. *SKILL.state: Scalable Long-Horizon Agent Skills.* arXiv:2608.26263 [cs.AI], 2026. — https://arxiv.org/abs/2608.26263
3. Tongxu Luo 외. *GameCraft-Bench: Can Agents Build Playable Games End-to-End in a Real Game Engine?* arXiv:2606.17861, 2026. — https://arxiv.org/abs/2606.17861
4. Xuying Ning, Dongqi Fu, Tianxin Wei, Hanqing Zeng, Yuanchen Bei, Bingxuan Li, Zihao Li, Qifan Wang, Xiang Shen, Yifan Wu, Jiayi Liu, Hong Li, Yinglong Xia, Xiangjun Fan, Hanghang Tong, Jingrui He. *EvoHarness-RL: Learning Self-Evolving Runtime Harness for Long-Horizon LLM Agents.* arXiv:2608.05446 [cs.LG], 2026. — https://arxiv.org/abs/2608.05446
5. Yuxing Lu, Yicheng Chen, Shanchan Wu, Sercan Ö. Arık. *Procedural Graphs: Self-Evolving Execution Structures for LLM Agents.* arXiv:2609.09153 [cs.AI], 2026. — https://arxiv.org/abs/2609.09153
6. Joshua Ong Jun Leang, Haonan Li, Zheng Zhao, Xinyi Shang, Wenda Li, Zhengzhong Liu, Eric Xing, Shay B. Cohen, Eleonora Giunchiglia. *Magenta: Closing the Loop Between Mathematical Reasoning and Lean Verification.* arXiv:2609.11319 [cs.AI], 2026. — https://arxiv.org/abs/2609.11319

FrontierSWE·ProgramBench는 [1]의 평가 벤치마크다(개별 링크는 [1] 본문 참조). 측정·검증 기록과 개정 이력(r4 결함 수정 → r6 병렬성 완화 → r12 Procedural Graphs 증류 → harness-compat 타 하니스 지원)은 `TESTS.md` 참조.

### 한국어 번역본 (`books/`)

참조논문의 한국어 정독서를 함께 동봉한다(korean-ebook 스킬로 제작. 정독서 시리즈 전체는 [KLIC-BOOK](https://github.com/klic-co-kr/KLIC-BOOK)):

| 파일 | 대응 |
|------|------|
| `books/하니스의_하니스_harness-of-harness-ko.pdf` | [1] HoH |
| `books/에이전트는_대화로_일하지_않는다_skill-state-ko.pdf` | [2] SKILL.state |
| `books/에이전트는 하니스를 배운다.pdf` | [4] EvoHarness-RL |
| `books/절차_그래프의_이해_procedural-graphs-ko.pdf` | [5] Procedural Graphs — LLM 에이전트를 위한 자기진화 실행 구조 (2026-09) |
| `books/루프를_닫다_magenta-ko.pdf` | [6] Magenta — 수학 추론과 Lean 검증 사이의 루프 (2026-09) |
| `books/많이_줄수록_여럿일수록_정말_더_잘할까_agent-papers-2026-ko.pdf` | 멀티 에이전트 논문집(번역 시리즈) |
