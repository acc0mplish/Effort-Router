# effort-router

작업의 규모·위험도를 티어(S/M/L/XL)로 판정하고 단계별 모델·에포트를 배정하는 Codex·ChatGPT Skill. 일반 작업은 GPT-6-Luna max, 계획·고난도 추론은 GPT-6.1-Sol high를 사용한다.

```text
Decision(티어 판정) → Requirement → Acceptance → Task → Evidence → Learning
```

## 왜 필요한가

- 단일 모델·단일 에포트로 모든 과업을 처리하면 단순 수정에 과투자, 대형 변경에 과소검증이 된다
- 자기 산출물 검토는 검토가 아니다 — 검토는 역할과 산출물이 분리된 별도 에이전트가 해야 한다
- 서브에이전트 호출은 무상태다 — 단계 사이를 잇는 상태 계약(state.json·증거번들)이 없으면 인계가 산문 재구성에 의존해 무너진다

## 변경 이력

최근 주요 변경 3건 — 전체 기록(r1~r38·jev)은 [CHANGELOG.md](CHANGELOG.md) 참조.

- **r38** (2026-10-06) — S티어 최소 기록 계약: S 과업도 완료 시 `state.json` 1회 생성 → 대시보드에 전 과업 표시
- **r37** (2026-10-06) — 대시보드 시각 재구성: 3뷰 해시 라우팅·번들 마크다운 뷰어·탑바 시계·필터·정렬
- **r36** (2026-10-06) — **HTML 대시보드 신설** — `python3 scripts/dashboard_server.py` 기동 → **http://localhost:5777** ([상세 계약](#html-대시보드-r37))

## 구조

| 경로 | 내용 |
|------|------|
| `SKILL.md` | 스킬 본체 — 티어 판정(§1)·라우팅 테이블(§2)·실행 제약(§3)·merge 권한(§4)·상태·인계 계약(§5)·타 하니스 매핑(§6)·Output Contract |
| `AGENTS.md` | 저장소 작업의 모델·에포트 정책과 역할 템플릿 오류 예방 규칙 |
| `agents/` | Claude Code 역할 정의 10종 + ChatGPT 데스크톱 UI 메타데이터 `openai.yaml` |
| `platforms/` | Codex·ChatGPT 실행 어댑터와 기타 하니스 파생 문서 |
| `scripts/` | 전역 Codex 역할 라우팅·설치 검증 스크립트 + jev 판단 계층 CLI(jev_judge.py·jev_modes.py — CLI 12종: tier·prune·escalation·memory-gate·stall·done·dup·loop·verify-run·watch·route·guard) + Stagehand 게이트 CLI(stagehand_gate.py 3종) + 검증 핀 게이트 CLI(verify_pin.py + 실행 엔진 verify_exec.py) + 워크트리 수명주기 게이트 CLI(worktree_gate.py 4종: create·done·list·sweep) + 트리 소유 게이트 CLI(tree_gate.py 5종: claim·release·check·status·prune) + 루프 탈출 게이트 CLI(neverstuck_gate.py — 결정론 무장 판정: 무브류 3회 게이트·S7 하드 시그널·선언탐색·취향 면제) |
| `TESTS.md` | 검증 프로토콜·측정 결과·라운드별 개정 이력·재현 절차(방법론 원장 — r29 하드캡 분할 이후 게이트 과업 절은 TESTS-GATES.md로, r33 분할 이후 과거 라운드 r4~r17 기록은 TESTS-ARCHIVE.md로 이동) |
| `TESTS-ARCHIVE.md` | 과거 라운드(r4~r17) 기록 아카이브(r33 내용 불변 순수 이동) |
| `TESTS-GATES.md` | 게이트 과업별 검증 원장(r22~r28·r29) — 원 요구·계약 요지·RED/GREEN·회귀 증거 표 |
| `CHANGELOG.md` | 라운드별 변경 이력(r1~r38·jev) 전량 |

## 설치 (Codex + ChatGPT 데스크톱 앱)

### 1. Skill·custom agents 설치 — `deploy_global.py` 공식 경로

전역 설치·재설치는 통합 배포 스크립트 1회 실행이 공식 경로다. 사전 검사(신선도·중복 역할·미러 드리프트) → 스냅샷 → 역할 TOML 배포 → `config.toml`·`AGENTS.md` 결합형 치환 → 미러 2곳 동기 → 게이트 G1–G4 → JSON 리포트가 한 파이프라인으로 진행된다.

```bash
python3 scripts/deploy_global.py --dry-run   # 사전 시뮬레이션 — 라이브·백업 루트 무변경
python3 scripts/deploy_global.py             # 실배포 — 게이트 전부 PASS면 exit 0
```

- 백업 스냅샷은 `~/.effort-router-backups/<ts>-deploy/`에 생성된다(환경변수 `EFFORT_ROUTER_BACKUP_ROOT`로 최상위 루트 변경 가능 — 역할 스캔 루트 내부 경로는 거부된다). 배포 후 Codex를 재시작한다.
- 재실행은 멱등 — `changes_total: 0`이면 repo↔미러↔라이브 3점 드리프트 부재의 대용 지표다.
- 폴백(스크립트 사용 불가 환경 한정): 수동 cp는 다음과 같이 하되, 백업 루트를 `~/.codex/agents` 안에 만들지 않는다 — 역할 스캔 루트 안의 백업 사본은 중복 역할로 오인된다.

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
코딩 작업 착수 전 설치된 `effort-router`를 사용한다. 일반 작업은 GPT-6-Luna max, 계획·고난도 추론은 GPT-6.1-Sol high를 사용한다. Terra는 사용하지 않는다. native spawn/fan-out은 사용하지 않는다.
`configure_codex_plan.py --apply`는 고정 전역 role 매핑만 적용하고, 변경 후 Codex를 재시작한다. 동일 접근 2회 실패 시 GPT-6.1-Sol high로 검토하고 확정된 구현은 GPT-6-Luna max로 진행한다.

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

`scripts/verify_pin.py`(+실행 엔진 `scripts/verify_exec.py`, r26)는 검증의 자기참조 구멍(검증 대상인 테스트를 약화·삭제·신규 무력화 파일로 우회해도 재실행은 같은 약화본을 통과시킨다)과 핀 부재(옛 검증으로 새 코드가 통과한다)를 메우는 결정론 게이트다. 읽기 전용 git과 검증명령 subprocess만 쓰며 jev·LLM·외부 전송·과금이 없다 — 저장소 국소 의존(venv·fixtures)이 없어 **미러 동봉 대상**이다(Stagehand 게이트의 저장소 루트 상대·미동봉과 다르다). r26에서 todo-flow 적대검토에서 도출된 결함 4종(프로세스 그룹 제어 부재·실행창 전후 클린 검사 부재·fresh-checkout 부재·증분 영수증 부재)을 수선했다.

```bash
# M+ 코드 과업 verify 단계 — 앵커(구현 착수 전 커밋) 지정이 원칙
python3 scripts/verify_pin.py --base <앵커> \
  --expect-sha <직전 검증 HEAD> \
  --verify-cmd 'python3 scripts/test_verify_pin.py' \
  --save docs/task-id/<task-id>/
# 워크스페이스 오염 클래스 전멸이 필요하면 — 핀 SHA의 detached 클린 체크아웃에서 검증
python3 scripts/verify_pin.py --base <앵커> \
  --verify-cmd 'python3 scripts/test_verify_pin.py' --fresh-checkout
```

| 플래그 | 기본 | 설명 |
|---|---|---|
| `--base REF` | 없음 | diff 기준 커밋(앵커 = 구현 착수 전 커밋). 미지정 시 검증 입력 검사 `not_evaluated` — **미검사 ≠ 변경 없음** |
| `--expect-sha SHA` | 없음 | 직전 검증 실행이 기록한 HEAD SHA — 불일치 시 `sha_mismatch` |
| `--verify-cmd CMD` | 없음 | 재실행 검증명령(shlex 분할 — 셸 미경유, 파이프·리다이렉션 불가, 필요 시 `bash -c "..."` 전달) |
| `--timeout SEC` | 600 | verify-cmd 타임아웃(양수 유한 — 위반 시 exit 2) |
| `--pattern PAT` | 없음(반복 가능) | 검증 입력 패턴 추가(기본 패턴에 append — multipurpose 그룹 미적용) |
| `--save DIR` | 없음 | 결과 JSON 저장 디렉터리(`verify-pin-<UTC타임스탬프>.json` — jev --save 계약 평행). r26부터 **증분 영수증** — 단계(init→inspected→fresh_checkout→verify_cmd→complete)마다 원자 기록, 크래시 시 마지막 성공 단계까지 보존 |
| `--fresh-checkout` | off | 핀 SHA의 detached 클린 체크아웃에서 검증(r26). **`--verify-cmd` 필수 — 단독 지정은 exit 2**(verify-cmd 없는 fresh는 검증 부재) |

| 계층 | 플래그 | 해제 조건 |
|---|---|---|
| 재검증 | `sha_mismatch`·`verify_cmd_failed`·`verify_cmd_timeout`·`verify_cmd_survivors`(r26) | 확인 대화만으로 done 불가 — 게이트 재실행으로 플래그 소멸 확인(예: `--expect-sha`를 현재 HEAD로 갱신 후 재실행, survivors는 프로세스 정지 후 재실행) |
| 정당화 | `verification_input_modified`·`multipurpose_config_modified`·`verification_input_hidden`·`verification_input_ignore_hidden`·`head_moved_during_verify`(r26)·`verify_workspace_mutated`(r26) | 해당 diff·은닉 확인 + 사유 기재(은닉은 `git update-index --no-assume-unchanged`/`--no-skip-worktree` 해제, ignore는 .gitignore·.git/info/exclude 제외 해제 후 재실행으로 소멸 확인 권장). r26 신규 2종은 1회성 사건 — **재실행 소멸≠해제**, 사건 원인 기재로 해제 |

| 종료코드 | 의미 |
|---|---|
| 0 | pass — 플래그 0건(수행한 검사 전부 통과, 미지정 검사는 평가 제외) |
| 1 | attention — 확인 의무 플래그 1건 이상. **jev의 exit 1(폴백=진행)과 정반대** — 확인 없이 진행하면 계약 위반 |
| 2 | config·env·git 오류 — 즉시 종료, stderr `FAIL verify pin: <사유>`, stdout 없음. **저장(--save) 실패·fresh remove 실패는 예외**: 검사 결과 stdout JSON(`saved_to: null`·remove 실패는 `fresh.removed: false`+`incomplete_step`) 출력 후 exit 2 |
| 3 | 미사용 — 판단 계층(jev)이 없어 상향(escalation) 경로 자체가 없다(번호 재용 않음) |

검증 입력 패턴 — `fnmatchcase`(경로 전체 또는 basename, 플랫폼 대소문자 무관. Python fnmatch의 `*`는 `/`를 관통하므로 `tests/*`가 `tests/unit/x.py`까지 덮는다):

| 그룹 | 기본 패턴 | 플래그 |
|---|---|---|
| 검증 입력(기본 8종 + `--pattern` 확장) | `tests/*` · `test/*` · `test_*.py` · `*_test.py` · `conftest.py` · `pytest.ini` · `tox.ini` · `.github/workflows/*` | `verification_input_modified` |
| 다목적 설정 | `pyproject.toml` · `setup.cfg` | `multipurpose_config_modified` |

검출 파이프라인: `git diff --name-only <base>`(tracked — 커밋·staged·unstaged·삭제) ∪ `git ls-files --others --exclude-standard`(untracked 신규 — **패턴 통과분만 반영**, 신규 conftest·테스트 우회 차단) ∪ `git ls-files -v` 은닉 스캔(`h` assume-unchanged·`S` skip-worktree 태그 — diff·status 양쪽에서 파일을 감춰 증거 워크플로 동반 마비시키는 우회를 검증 입력·다목적 설정 파일에 그룹 구분 없이 `verification_input_hidden` + `hidden_files`(양 그룹 통합 목록)로 드러낸다 — 그룹 2 은닉은 pyproject 무력화 직통 우회다). `--exclude-standard`라 제외된 untracked는 diff·untracked 검출 밖이다 — 검증 파일을 ignore하는 구성 자체가 저장소 위생 이상 신호다. 이 구멍은 `git ls-files --others`(제외 없음) 대조로 메운다: 제외된 untracked 검증 입력·다목적 파일은 `verification_input_ignore_hidden` + `ignore_hidden_files`로 드러난다(.gitignore·.git/info/exclude·전역 excludesFile 전부 — 원인은 `git check-ignore -v`로 확인, 매칭은 전체경로 한정·의존성 트리 test 파일 오탐 방지, r25). **완전 차단이 아니다** — 공모 약화는 노출되나 해제는 사유 기재고 감시 자동화 없이 호출 시점 1회 판정이다(r25). git 호출은 `-c core.autocrlf=false -c core.quotePath=false` 고정(CRLF 정규화 위플래그·비ASCII 경로 C-인용 fnmatch 무력화 차단), subprocess 디코드는 `errors='replace'`(비UTF-8 파일명 크래시 방지).

r26 실행창·프로세스 그룹: `--verify-cmd` 지정 시 실행 직전 HEAD·`git status --porcelain -z -uall`·`.git/info/exclude` 내용을 스냅샷하고 직후 재판정한다(실행 창 전후 델타 — 게이트 시작 아님, 사전 dirty는 대상 아니다). HEAD 불일치는 `head_moved_during_verify`, tracked 레코드 변화·exclude 변화·검증입력 패턴 매칭 untracked 신규·소실은 `verify_workspace_mutated`다(패턴 밖 untracked — .pytest_cache·__pycache__ 등 산출물 — 는 `window_delta` 상세에만 기록되고 플래그 없다: 오탐 경보 피로 방지, 메인 승인 트레이드오프). 검증명령은 `start_new_session` 프로세스 그룹으로 실행된다 — 타임아웃·정상 종료 뒤 SIGTERM→폴링→SIGKILL로 그룹 전멸시키고 잔존 관측 시 `verify_cmd_survivors`(비POSIX 환경은 legacy 폴백·`process_group: false` 투명 표기). **한계**: 같은 pgid에 머무는 자손 한정 — setsid 등 신규 pgid 이탈 자손은 범위 밖이다. 실행 중 ps 실패는 생존자 판정 불능으로 exit 2다(조용한 통과 금지). `--fresh-checkout`은 r24 이름 충돌 가드(`wt/verify-pin-fresh` 브랜치·`docs/task-id/verify-pin-fresh/` 존재 시 exit 2)→잔존 복구→`worktree add --detach <시작 시점 HEAD>`→cwd=fresh 검증→`remove --force`+`prune` 순서며, **fresh 잔존은 fresh 모드 재실행으로만 정리된다** — r24 sweep은 detached를 스킵해 fresh 잔존을 못 치운다. fresh 검증은 커밋 트리 한정(untracked·unstaged는 기본 모드 영역)이며 은닉 플래그는 메인 스캔에서 여전히 발행된다.

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
                "stdout_tail": "<말미 500자>", "stderr_tail": "<말미 500자>",
                "process_group": true, "survivors": false, "group_killed": false,
                "window_delta": {"head_moved": false, "tracked_changed": [],
                                 "untracked_new": [], "untracked_gone": [],
                                 "exclude_changed": false, "untracked_matched": []}},
 "fresh": null,
 "flags": ["verification_input_modified"], "saved_to": null}
```

`verify_cmd`는 미지정 시 `null`. `fresh`는 `--fresh-checkout` 미사용 시 `null`, 사용 시 `{"used": true, "checkout_sha": ..., "worktree_path": ..., "removed": true, "leftovers_cleaned": []}`. `survivors`는 legacy 폴백 시 `null`. `saved_to`는 --save 미지정·실패 모두 `null`. 타임아웃 시 `verify_cmd_timeout`만 발행하고 `verify_cmd_failed`를 병기하지 않는다(배타성 — `verify_cmd_survivors`는 독립 축으로 병기 가능). `ok` = `len(flags)==0`. 게이트 분기 전수는 임시 git 저장소 fixture로 `python3 scripts/test_verify_pin.py`(T1~T23 — r25 경화)와 `python3 scripts/test_verify_exec.py`(T24~T42 — r26 실행 엔진·fresh·영수증)에서 결정적으로 검증한다. 사용 시점·플래그 2계층·호출·감사·폴백 계약은 SKILL.md의 '검증 핀 게이트(verify_pin)' 절을 따른다.

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

### 트리 소유 게이트 (r27)

`scripts/tree_gate.py`는 복수 기록자(병렬 세션·헬퍼)가 같은 저장소를 다룰 때의 트리 소유 조율 게이트다(배경: 타 세션의 미커밋 변경을 추정만으로 revert한 사건 — 복수 기록자 + 트리 소유 조율 장치 부재). 작업 착수 전 세션id·트리·스코프·시각을 claim 레지스트리에 기록하고, 같은 트리의 살아있는 타 세션 claim을 check가 기계 노출한다. 레지스트리는 `$(git rev-parse --git-common-dir)/effort-router-tree-claims/` — common-dir은 모든 워크트리가 공유하므로 워크트리 간 가시성이 확보된다. `.git` 내부 비관리 디렉터리라 git이 무시하며 커밋 대상이 아니고 `.gitignore` 등록도 불필요하다. stdlib만 사용하며 저장소 국소 의존이 없어 **미러 동봉 대상**이다(verify_pin·worktree_gate와 동일, Stagehand 게이트의 미동봉과 다름).

```bash
# claim — 작업 착수 전 자기 세션 기록(타 alive claim 존재 시에도 기록은 되고 exit 1)
python3 scripts/tree_gate.py claim --session <id> [--scope <텍스트>] [--pid N] [--tree <경로>]

# release — 작업 종료 시 자기 claim 제거(멱등 — 소유 대조 후 제거)
python3 scripts/tree_gate.py release --session <id> [--tree <경로>]

# check — 같은 트리의 살아있는 타 세션 claim 탐색(1건 이상 시 exit 1)
python3 scripts/tree_gate.py check [--session <id>] [--tree <경로>]

# status — claim 전체 보고(stale 1건 이상 시 exit 1)
python3 scripts/tree_gate.py status [--tree <경로>]

# prune — stale(죽은) claim만 제거(alive 불가침) — 보고 먼저
python3 scripts/tree_gate.py prune --dry-run
python3 scripts/tree_gate.py prune
```

| 서브커맨드 | 인자 | 동작 |
|---|---|---|
| `claim` | `--session`(필수¹) `--scope`(선택) `--tree`(기본: cwd toplevel) `--pid N`(선택²) `--ttl-hours N`(기본 24) | claim 파일 원자 생성(temp+fsync+os.replace). 동일 (tree, session) 재claim은 updated_utc만 갱신 멱등 = heartbeat(claimed_utc 최초 고정). 타 alive claim 존재 시 **기록은 수행** + `foreign_claim_present` |
| `release` | `--session`(필수) `--tree`(기본 동일) | 자기 (tree, session) claim 제거. **제거 전 레코드 session_id 대조** — 불일치·파손은 제거 거부 exit 2(파일명 충돌 방어). 부재 시 멱등 `already_released: true` |
| `check` | `--session`(선택³) `--tree`(기본 동일) `--ttl-hours N` | 같은 트리의 살아있는 **타 세션** claim 탐색 — 상대 session_id·scope·claimed_utc·alive 근거(pid∨TTL) 보고 |
| `status` | `--tree`(선택 — 미지정 시 레지스트리 전체) `--ttl-hours N` | 전체 claim 보고(alive·stale 판정 포함). stale 1건 이상 시 exit 1 + `stale_claims_present` |
| `prune` | `--dry-run` `--ttl-hours N` | **stale 판정 claim만 제거**(alive 절대 불가침). stale = updated_utc TTL 초과 ∧ pid 생존 아님(사망 확인 또는 판정 불능 — pid 미전달·호스트 상이·비POSIX 포함). `--dry-run`은 보고만(무변경) |

¹ `CLAUDE_SESSION_ID` 환경변수 폴백(있으면 인자 생략). ² 래퍼·세션 프로세스 pid를 호출자가 전달할 때만 유효 — 미전달 시 TTL만 의존(정직한 기본). ³ 미지정 시 자기 claim 없음 전제 전수 탐색(claim 전 사전 확인 용도).

| 종료코드 | 의미 |
|---|---|
| 0 | 정상 — claim 성공(타 claim 없음)·release 완료(멱등 포함)·check 간섭 없음·status stale 0건·prune 완료(--dry-run 포함 — 보고는 확인 의무가 아니다, JSON 기록으로 남는다) |
| 1 | attention — 확인 의무 플래그 1건 이상. **claim 서브커맨드의 경우 기록은 수행된 상태다**(`set -e` 셸에서 exit 1로 중단돼도 claim 파일은 이미 존재한다 — 재실행은 heartbeat 멱등). **jev의 exit 1(폴백=진행)과 정반대** — verify_pin·worktree_gate와 동일 어휘. 확인 없이 진행하면 계약 위반 |
| 2 | config·env·git 오류 — 즉시 종료, stderr `FAIL tree gate: <사유>`, stdout 없음. 비저장소 cwd·bare 저장소·common-dir 쓰기 불가·무효 session-id·release 레코드 불일치 제거 거부. **저장(--save) 실패만 예외**: 결과 stdout JSON(`saved_to: null`) 출력 후 exit 2 |
| 3 | 미사용 — 판단 계층(jev)이 없어 상향(escalation) 경로 자체가 없다(번호 재용 않음) |

| 플래그 | 발행 조건 | 확인 절차 |
|---|---|---|
| `foreign_claim_present` | claim·check에서 같은 트리의 살아있는 타 세션 claim 탐색(파손 claim도 보수 alive 취급 대상) | 보고된 상대 session_id·scope·alive 근거 확인 → 읽기전용 전환 또는 신규 worktree 스폰 — 판정 권한은 메인 |
| `stale_claims_present` | status에서 stale claim 잔존 | `prune --dry-run` 열람 후 `prune`(죽은 것만 지운다 — alive 불가침) |

**명명·레지스트리** — 파일명 `<tree-hash16>-<session-sanitized>.json`(tree-hash = sha256(작업 트리 절대경로 resolved) 앞 16자, session sanitize는 `[^A-Za-z0-9._-]`→`_`). session-id 검증 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` — **검증 상한과 sanitize 절단 상한을 64자로 통일**해 검증 통과 id의 파일명 충돌·타 세션 파일 오제거 경로를 원천 차단했다. 모든 경로 파생은 `git rev-parse --git-common-dir` 기준 — worktree 내부에서 실행해도 본체 .git 기준 레지스트리를 본다. `git worktree prune`·`verify_pin --fresh-checkout`의 `remove --force`도 이 디렉터리를 건드리지 않는다(worktree admin 메타데이터 아님).

```json
{"version": 1, "gate": "tree-gate", "session_id": "<호출자 id>",
 "tree": "<작업 트리 절대경로>", "tree_hash": "<sha256 앞 16자>",
 "scope": "<선택 텍스트|null>", "hostname": "<socket.gethostname()>",
 "pid": "<전달 시 정수, 아니면 null>",
 "claimed_utc": "<최초 claim 시각 ISO8601 UTC — 고정>",
 "updated_utc": "<마지막 갱신 시각 — TTL 판정 기준>"}
```

응답 JSON — 모든 서브커맨드의 정상 출력(exit 0·1)은 단일 JSON 객체다(exit 2 = stdout 없음):

```json
{"ok": true, "gate": "tree-gate", "subcommand": "check", "tree": "<abs>",
 "session_id": "<id|null>", "flags": ["foreign_claim_present"],
 "foreign_claims": [{"session_id": "...", "scope": "...", "claimed_utc": "...",
                     "updated_utc": "...", "alive_reason": "pid|ttl",
                     "pid_check": "alive|dead|unsupported"}],
 "stale_claims": [], "corrupt": [], "saved_to": null}
```

`ok` = **게이트 절차 수행 성공** — **exit 1도 `ok: true`다**(경고는 flags·세부 배열로 전달 — 수행 성공과 경고 상태의 분리). 서브커맨드별 채움: claim·check → `foreign_claims` / status → `stale_claims`·`corrupt`(전체 보고는 `claims`) / prune → `stale_claims`(제거 대상 보고) / release → 최소 필드 + `already_released`(멱등 시 true). alive = (같은 hostname ∧ pid 생존) ∨ **updated_utc가 TTL 이내** — TTL 판정 기준은 updated_utc다(heartbeat가 갱신하므로 활성 장기 세션은 TTL을 계속 리셋한다. claimed_utc는 최초 기록 고정·보고용). pid 생존은 `os.kill(pid, 0)`(ProcessLookupError=사망·PermissionError=생존) — 비POSIX·호스트 상이·pid 미전달은 `pid_check: "unsupported"` 투명 표기 후 TTL만 의존한다. 파손 claim 파일은 `corrupt`로 보고하고 판정에서는 alive 보수 취급(판독 불가 = 판단 보류 — prune 대상도 아니다). **알려진 한계**: pid 재사용·컨테이너 pid-namespace에서 같은 pid가 다른 프로세스를 가리켜 alive 오판 가능(보수 방향 수용 — 오판 비용은 확인 1회), **이 게이트의 보장은 참여 세션이 모두 claim했을 때만 성립한다**(계약 밖 기록자는 감지 대상 아님).

**폴백** — 비저장소·bare·common-dir 쓰기 불가 = exit 2 = "이 게이트 없이 기존 프로세스 진행". **데이터 유출 면** — scope·session_id에 시크릿·API 키·민감 경로 기재 금지(레코드가 .git에 평문 남는다). 외부 전송은 없다(로컬 파일만). **SessionStart 훅**(`.claude/hooks/tree_claim_hook.py` + settings 엔트리, timeout 5초)은 이 저장소의 선택 어댑터다 — stdin JSON의 session_id로 `check`를 자동 수행, foreign claim 존재 시 additionalContext 경고(상대 session_id·scope·alive 근거 + "판정 권한은 메인" 안내). 훅은 항상 exit 0(세션 시작 차단 없음)이며 게이트 부재·비저장소·오류 시 무작동·무출력. jev·TYPESAFE_API_KEY 무의존(결정론). 게이트 분기 전수는 임시 git 저장소 fixture로 `python3 scripts/test_tree_gate.py`(T1~T20 — 훅 케이스 포함)에서 결정적으로 검증한다. 사용 시점·보장 성립 요건·state.json `tree_claim` 필드 계약은 SKILL.md의 '트리 소유 게이트(tree_gate)' 절을 따른다.

**격리 가드(r28) — PreToolUse(Bash) 재점검·커밋 오염 방어**: r27 SessionStart 경고가 1회성이던 구멍을 메는 계층으로, 같은 훅 파일의 `prebash` 서브커맨드가 이 저장소의 국소 선택 어댑터로 동작한다(미러 환경 미작동 — settings 엔트리도 저장소 국소). r28에서 SessionStart(start) 경고는 기존 문구 보존 하에 말미에 격리 안내 1줄(`python3 scripts/worktree_gate.py create --task <task-id>` — r24, 호출 주체는 메인 세션 단일)이 추가됐다. 동작은 3단계다. ① 레벨 1 트리거 — 명령 문자열을 셸 제어 연산자로 분할(quote 상태 추적 — 인용 내부 `&&`는 위조 세그먼트로 취급하지 않는다, `$()`·백틱 치환·히어독 본문(`<<`·`<<-` 종결자 라인까지)·괄호 그룹은 불투명·제외)해 git 쓰기 서브커맨드 감지: `add` `commit` `rm` `mv` `checkout` `switch` `restore` `stash` `reset` `rebase` `merge` `cherry-pick` `revert` `clean` `push` `pull` `tag` `apply` `am` `worktree` `branch` `submodule` `sparse-checkout`(branch·tag 포함 보수). 미감지면 무간섭·캐시 미생성. ② 재점검 — check를 캐시와 함께 재실행: 캐시는 `<TMPDIR>/effort-router-tree-gate-hook/<session-sanitized>.json`(TTL 60초 — `TREE_GATE_HOOK_CACHE_TTL_S`로 폴백, 무효값은 기본 60), TTL 내 check 스킵·returncode 0·1은 모두 유효 판정으로 기록(foreign=false도 캐시 — 60초 윈도 내 재실행 없음), 2·오류·timeout·파싱 실패는 무작동 bypass. 기준선(직전 캐시) 대비 신규 foreign claim이 처음 등장하면 additionalContext 경고(신규 분만 — SessionStart 중복 없음), corrupt 신규 등장도 1회 통보한다. ③ deny — foreign alive claim 존재(foreign_claims 배열 비빈 — corrupt-only는 deny 불발행) ∧ shlex 성공 세그먼트에서 git 명령 위치 ∧ 전체 스테이징일 때만:

| 조건 | deny | 허용 |
|---|---|---|
| `add` | `-A`·`--all`·`-u`·`--update`(묶음 `-Av` 분해 포함) ∧ pathspec 없음 / pathspec 토큰 중 `.`·`./` 존재 | `git add <경로>`·`git add -A src/`·`git add ./src` — 부분 스테이징 |
| `commit` | `-a`·`--all`(묶음 `-am` 분해 포함) ∧ 커밋 대상 pathspec 없음(`-m`·`-F`·`-C`·`-c`는 값 1개 스킵) | `git commit -m "x"`·`git commit -am "x" -- <경로>` |

deny 출력은 단일 JSON 객체(`permissionDecision: "deny"`)며 사유에 pathspec 안내(`git add <경로>… / git commit -- <경로>…`)·격리 명령 원문·유령 탈출 안내("상대 claim이 유령(세션 종료)으로 보이면 tree_gate.py status 확인 후 레지스트리 파일 수동 삭제 — prune은 alive 불가침")를 담고, 신규 침입자·corrupt와 동시 성립 시 해당 줄을 사유 말미에 병합한다(경고를 별도 emit하지 않는다 — JSON 객체 1개 원칙). dry-run(`--dry-run`·add `-n`)은 실행 안 되는 명령으로 deny 제외하며, commit 값 결합 문자(`-ma`의 `a`)는 플래그로 오인하지 않고 `git -C../x`·`--git-dir=…` 결합형 귀속 불확실 세그먼트도 deny 대상에서 제외한다(재점검 트리거는 유효). **단독 세션(claim 부재)의 `git add -A`는 허용** — 오탐 0. 긴급 회수는 env `TREE_GATE_HOOKS=0`(prebash 전체 오프 — 재시작 불요; 경고만 남기는 분리 스위치는 없으며 settings 블록 제거도 경고를 함께 소멸시킨다). **알려진 한계**: 파일 수준 소유권 판정·index.lock 재시도 범위 밖, xargs·find -exec 뒤 git·스크립트 내부 git·별칭·`$()`/백틱 치환 내부 git·괄호 그룹 내부 git·`-C` 등 트리 귀속 불확실 세그먼트(deny 한정 — 재점검 트리거는 유효)·비Bash 쓰기 도구(Edit·Write — 감지 창은 SessionStart 1회 잔존)·SessionStart 통보~첫 캐시 기록 사이 침입자의 기준선 합류(경고 영구 누락 — deny는 유지)는 미감지이며, 하니스 밖(직접 터미널) git은 무관하다. 훅 케이스 전수는 `python3 scripts/test_tree_claim_hook.py`(T19~T35)에서 검증한다 — 저장소 국소 케이스는 `.claude/hooks` 부재 환경(미러)에서 skipTest로 자동 제외된다.

### 루프 탈출 게이트 (r29)

`scripts/neverstuck_gate.py`는 반복 실패 루프(같은 무브류의 증상 패치 반복 — 이슈 5개 처리가 10개로 증식)의 **결정론 무장 판정 게이트**다. 시도 이력 JSON을 받아 neverstuck 프로토콜(증상 패치 금지·메커니즘 진단 강제 — 원천 NeverStuck Protocol v1) 진입 의무(armed) 여부를 판정하고, 무장 시 `contract_reminder`(③재구현 프롬프트 주입용 고정 계약 요약)를 노출한다. stdlib만 사용하며 jev·API·git·환경·외부 파일(PROTOCOL.md 포함) 무의존 — **미러 동봉 대상**이다. 서브커맨드 없음·훅 없음(무장은 사건 기반 — 동일 무브류 3회 실패·S7 관측 시점에 호출 주체가 직접 실행한다). 사용 시점·배선·무장 시 행동 계약 전문은 SKILL.md '루프 탈출 게이트(neverstuck)' 절을 따른다.

```bash
# 무장 판정 — 시도 이력 JSON(파일 경로 또는 - = stdin)
python3 scripts/neverstuck_gate.py --history <이력.json>
python3 scripts/neverstuck_gate.py --history - < <이력.json>

# 판정 JSON 감사 기록(not-armed도 기록 — 과업 폴더 권장)
python3 scripts/neverstuck_gate.py --history <이력.json> --save docs/task-id/<task-id>/
```

입력 스키마 — 최상위 `{"goal"(선택), "preference_domain"(bool 선택), "attempts":[…]}`이며 시도 항목은:

| 필드 | 필수 | 규칙 |
|---|---|---|
| `move_class` | 필수 | 문자열 — 무브류 id(1개 밴으로 덮이는 변경류 단위로 정규화 기재). 누락·비문자열은 exit 2 |
| `outcome` | 필수 | `"worked"` \| `"failed"` — 이형값은 exit 2 |
| `knob`·`value`·`context` | 선택 | 스칼라(str\|int\|float\|bool). **null은 결손(키 부재와 동등 취급)** — 배열·객체 기재는 exit 2. worked 시도에도 기재 의무(미기록 = s7_evaluable:false 미감지) |
| `declared_search` | 선택 | bool — 비bool 리터럴(`1`·`"true"`)은 exit 2, null·부재는 결손(false). true는 의도적 탐색 선언(판정 대상 제외) |
| `preference_domain`(최상위) | 선택 | bool — 취향 도메인 선언(전역 면제). 비bool은 exit 2, **null·부재는 결손(false — 보수 방향)** |
| `note`·`goal` | 선택 | 자유 기록 — 판정 무관(응답에 원본 보존) |

전체 거부 규칙(부분 판정 없음 — exit 2): 위 필수·스칼라·bool 위반 + **NaN/Infinity 리터럴**(parse_constant 거부 — 유한 스칼라만 값이다) + **비UTF-8 바이트** + **심층 중첩 JSON**(RecursionError 랩) + `attempts` 키 부재·비배열. 빈 배열 `[]`는 유효 not-armed다.

판정 규칙 — 순서 고정(§1.4 의사코드):

| 규칙 | 내용 |
|---|---|
| 1단계 면제 | `preference_domain:true` → not-armed(`exemptions` 표기 — 최우선 단락, S7을 평가하지 않는다) |
| effective | `declared_search:true` 시도는 판정 대상 제외(자동 판정은 면제만 가능 — 단죄 불가). `declared_search_skipped` 수 투명 보고 |
| S7 하드신호 | effective 중 knob·value·context **완비 worked**를 knob별 그룹핑 — 같은 그룹에 값·맥락이 모두 상이한 쌍 → 즉시 무장(failed 유무 무관) |
| 값 비교 D1 | 타입 클래스 bool⊥수치(int·float 통합)⊥str⊥기타 — 같은 클래스 안에서만 ==(30 vs 30.0 동일), 클래스가 다르면 항상 상이(True vs 1·30 vs "30" 상이). 값·맥락 비교와 knob 그룹핑 키에 동일 적용 |
| 3회 게이트 | effective를 move_class별 그룹핑 — failed ≥3인 무브류 존재 → 무장(1~2회 미발동 — Never 원칙). S7 동시 성립 시 s7 우선 보고 |
| s7_evaluable | 전역 스코프(D3) — 완비 worked 그룹 ≥1이면 true, 0이면 false(판정 불능 투명 표기 — 미감지 방향). trigger=s7_hard_signal ⇒ true(three_attempt 무장과 독립 — 완비 worked 0이면 false 가능) |

| 종료코드 | 의미 |
|---|---|
| 0 | not-armed — 정상 진행, 추가 시도 허용 |
| 1 | **armed** — neverstuck 프로토콜 진입 의무(`ok:true` ∧ `flags:["armed"]`). **jev의 exit 1(폴백=진행)과 정반대** — verify_pin·worktree_gate·tree_gate와 동일 어휘 |
| 2 | 무효 입력 — 즉시 종료, stderr `FAIL neverstuck gate: <사유>`, stdout 없음. **저장(--save) 실패만 예외**: 결과 stdout JSON(`saved_to: null`) 출력 후 exit 2 |
| 3 | 미사용 — 결정론 게이트, 판단 계층 상향 경로 없음(번호 재용 않음) |

응답 JSON — 정상 출력(exit 0·1)은 단일 JSON 객체다(exit 2 = stdout 없음, --save 실패 제외):

```json
{"ok": true, "gate": "neverstuck-gate", "armed": true,
 "trigger": "s7_hard_signal",
 "goal": "…", "attempts_total": 7, "attempts_considered": 6,
 "declared_search_skipped": 1, "preference_domain": false, "exemptions": [],
 "per_move_class": [{"move_class": "timeout-retune", "failed": 0, "worked": 2},
                    {"move_class": "prompt-rewording", "failed": 4, "worked": 0}],
 "armed_on": {"knob": "timeout",
              "working_values": [{"value": 30, "context": "sess-1"},
                                 {"value": 90, "context": "sess-2"}]},
 "s7_evaluable": true,
 "flags": ["armed"],
 "contract_reminder": "…아래 전문…",
 "attempts": [ …입력 attempts 원본 배열 그대로… ],
 "saved_to": null}
```

`ok` = **판정 절차 수행 성공** — **exit 1도 `ok: true`다**(tree_gate 계약 평행). **attempts 원본 배열은 무장·미무장 무관 항상 포함**된다 — --save 감사 파일이 세션 경계를 넘는 이력 원본이 되며(과업 재개 시 직전 감사·번들에서 이어 조립), 응답 예의 집계도 정합이다(attempts_considered 6 = per_move_class 합 0+2+4+0). not-armed 형태는 `armed:false`·`trigger:null`·`armed_on:null`·`contract_reminder:null`로 무장 전용 필드만 null 명시된다. `working_values`는 상이쌍 산출 근거가 된 완비 worked 전체(중복 제거·입력순), `per_move_class`는 effective 한정 집계(선언 전용 무브류 미표시)다. trigger=three_attempt_gate면 `armed_on.move_classes:[…]`, s7이면 `armed_on.knob`+`working_values`.

contract_reminder 전문 — 무장 시 게이트가 노출하는 고정 문자열(`<armed_on 대상>` 치환, §1.6):

> neverstuck 무장: <armed_on 대상>은 전부 밴한다(근접 변형 포함 — 맥락별 룩업테이블·과거값 평균·보정항·시작시 자동피팅). 다음 시도 전 의무: (1) 과거 각 시도가 정확히 그렇게 작동한 이유를 전부 설명하는 소급 예측 — 못 하면 기각 (2) Stuck Packet 6필드 작성(GOAL/ATTEMPT LOG/OBSERVATIONS/VARIABLES/CONSTRAINTS/ACCESS INVENTORY) (3) 메커니즘 가설 2–3개(값 아님·서명사실 S-a~S-d를 전부 동시 설명하는 모델만) (4) 판별 실험 정확히 1개 + 판정규칙("결과 X⇒H1") 사전 선언. 수렴 계약: C1(모든 상수 출처 명시) ∧ C2(이력 소급 예측) — 둘 다 아니면 기각, 2차 튜닝 패스 금지. 회피값은 [loop-bait — D 실험 게이트] 태그 없이 제출 금지(삭제는 금지, 사용자 재량). 예산: 보고서 2라운드 상한 후 강제 에스컬레이션(계측 → 서드파티 소스 정돈·grep 문자열 제공 → 통제 프로빙 → 인간 질문 초안).

치환 규칙 — three_attempt_gate: `무브류 <무브류 쉼표 열거>` / s7_hard_signal: `knob <K>의 값 <v1>@<c1>·<v2>@<c2>`(상이쌍 전부 열거 — 값 직렬화는 JSON 규칙: str은 따옴표 포함, 수치는 그대로).

**한계** — move_class 문자열 동일성 기반(근접 변형 미감지 — 이력 기록 시 무브류 정규화 기재로 완화, 자동 유사도 판정은 단죄 위험으로 미도입)·S7은 knob·value·context 기재 의존(완비 그룹 0 = `s7_evaluable:false` 투명 표기 — 미감지 방향)·게이트는 무장 '판정'만(밴 준수·소급 예측 품질·실험 1개 규율은 SKILL 계약 텍스트 영역)·무장 후 진입·밴 해제·에스컬레이션 판정 권한은 메인(해제 시 사유+감사 1건). 분기 전수는 `python3 scripts/test_neverstuck_gate.py`(34케이스)에서 결정적으로 검증한다.

### HTML 대시보드 (r37)

터미널 없이 브라우저에서 과업 상태를 보는 읽기 전용 로컬 대시보드다.
r36의 단일 테이블 UI를 todo-flow(JakeB-5/todo-flow, MIT) 대시보드 원본 충실도로
재구성했다(스타일 국소 재구현 — 코드 이식 없음): 웜 화이트 팔레트 ·
사이드바+탑바+배너 공통 셸 · 해시 라우팅 3뷰.

```bash
python3 scripts/dashboard_server.py            # 기동 → http://127.0.0.1:5777
python3 scripts/dashboard_server.py --port 0   # OS 할당 포트 — stdout READY 라인에서 확인
```

| 라우트 | 응답 |
|---|---|
| `/` | 대시보드 HTML |
| `/api/tasks` | 과업 상태 JSON — `docs/task-id/*/state.json` 전수 스캔 + `excerpt`(원 요구 발췌)·`mtime` 확장 |
| `/api/bundle/<folder>` | 과업 번들 원문 JSON(`{"folder", "markdown"}`) — state.json 보유 폴더 한정, 4단계 경로 검증 |
| `/app.js` · `/style.css` · `/tokens.css` · `/markdown.js` · `/views/*.js` | 정적 자원 (고정 매핑 — 이 외 경로는 전부 404) |

뷰는 해시 라우팅으로 전환한다 — `#/`(과업 목록, 기본)·`#/activity`(실행 현황)·
`#/task/<folder>`(과업 상세 — 목록·현황 행 클릭으로 진입, bundle.md 마크다운
렌더링). 폴링(기본 5초, 사이드바 푸터에서 주기 변경)은 라우트 무관 지속되며
상세 뷰의 문서 DOM은 재구성하지 않는다.

- 읽기 전용: 서버는 state.json·번들을 포함해 어떤 파일도 쓰지 않는다(GET 전용 — state.json writer는 메인 세션 단일). 상호작용(체크박스·아코디언·정렬·필터·검색·클립보드 복사)은 전부 브라우저 로컬 상태다
- 보안: 기본 `127.0.0.1` 바인딩(로컬 전용). 정적 자원은 고정 매핑 테이블뿐이고 `/api/bundle`은 `unquote` 후 `/`·`\`·`..`·NUL 차단 + state.json 보유 폴더 한정이라 트래버설은 구조적으로 불가. 마크다운 렌더러는 textContent 주입 일원화 + http:/https: 스킴 외 링크 강등
- 파손 방어: malformed state.json은 `parse_error`로 격리 표시 — 서버·타 과업 표시 무영향
- 표시 범위: `state.json`을 남기는 전 과업 — S티어(완료 시 최소 기록만 생성, r38 계약)도 포함. S 레코드는 발췌 없음(번들 부재 → 폴백 문구)·claims 칩 `–`·완료 카운트 합산
- 종료: Ctrl+C(SIGINT/SIGTERM → exit 0). 포트 점유 등 config 오류는 stderr 사유 + exit 2
- `--port 0`은 테스트 용도 — `scripts/test_dashboard_server.py`(T1~T25)가 READY 라인 파싱 계약으로 사용한다. `--root`로 탐색 루트 교체 가능(테스트 격리)

## 모델 매핑

일반 작업은 `gpt-6-luna / max`, 계획·고난도 추론은 `gpt-6.1-sol / high`다. Terra는 사용하지 않는다. 이 설치에서는 native spawn/fan-out을 사용하지 않는다.

| 작업 | 모델·effort |
|---|---|
| 구현·조사·테스트·검증 | `gpt-6-luna / max` |
| 계획·명세·아키텍처 | `gpt-6.1-sol / high` |
| 계획 검토·리뷰·보안 판정 | `gpt-6.1-sol / high` |

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

FrontierSWE·ProgramBench는 [1]의 평가 벤치마크다(개별 링크는 [1] 본문 참조). 측정·검증 기록과 개정 이력(r4 결함 수정 → r6 병렬성 완화 → r12 Procedural Graphs 증류 → harness-compat 타 하니스 지원)은 `TESTS-ARCHIVE.md` 참조.

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

## Thanks to

- **[NeverStuck](https://github.com/chldbwnstm/NeverStuck)** (chldbwnstm) — r29 루프 탈출 게이트의 프로토콜 원천이다. 핵심 원칙("맥락마다 재조정이 필요한 파라미터는 상수가 아니라, 변동하는 무언가의 미모델링 함수다")·3회 무장 게이트·S7 하드 시그널·노브 밈+소급 예측 강제·loop-bait 태깅·Honesty clause를 증류해 결정론 무장 판정 CLI(`neverstuck_gate.py`)와 SKILL 계약 절로 편입했다. 결정론 재구현 과정에서 발견한 명세 여지 3건(S7 무장 조건·값 동등성 의미론 — [#1](https://github.com/chldbwnstm/NeverStuck/issues/1), 환경별 정상값의 guard 미커버 — [#2](https://github.com/chldbwnstm/NeverStuck/issues/2), PROTOCOL.md 동반 하드 의존 — [#3](https://github.com/chldbwnstm/NeverStuck/issues/3))은 업스트림 이슈로 보고했다.
- **[TODO Flow](https://github.com/JakeB-5/todo-flow)** (JakeB-5, MIT) — r23~r26 게이트 3종의 설계 참조원이다. 정확-후보 SHA 핀닝(`verify_pin`의 핀 원형), 완료 시 체크아웃 자동 정리·salvage 브랜치 보존 원칙(`worktree_gate`의 수명주기 원형)을 가져왔고, 그들의 검증 게이트를 적대검토하며 발견한 결함들(검증 자기참조·환경 격차·은닉 우회)이 이 저장소의 동일 결함을 r25에서 스스로 수선하는 계기가 됐다. r26에서는 todo-flow의 `verification.py` stop_group(프로세스 그룹 원형)·`engine.py` require_clean(실행창 전후 클린 검사 원형)·`land()` 통합 체크아웃(fresh-checkout 원형)·`cleanup.py` write_json(증분 영수증 원형)을 어휘 이식해 검증 핀 게이트의 결함 4종을 수선했다.
