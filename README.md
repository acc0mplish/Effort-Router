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
| `GATES.md` | 게이트 5종 CLI 전체 참조 — 플래그·종료코드·JSON 스키마·한계 |

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

### 게이트 5종 (선택 계층)

반복 실패를 막는 결정론 스크립트들. 전부 선택 계층 — 안 쓰면 기존 프로세스 그대로 동작한다.

| 게이트 | 뭐 하는 거 | 기본 명령 |
|---|---|---|
| Stagehand (r21) | 브라우저 자동화 실행 → jev가 통과/재시도 판정 | `scripts/stagehand_gate.py --task-file <json>` |
| 검증 핀 (r23) | 검증에 HEAD를 핀 + 테스트 파일 약화·은닉 탐지 — "옛 검증으로 새 코드 통과" 차단 | `scripts/verify_pin.py --base <앵커> --verify-cmd <테스트명령>` |
| 워크트리 수명주기 (r24) | worktree 완료 시 강제 제거 — 미커밋분은 자동 커밋 보존(디스크 잔여 방지) | `scripts/worktree_gate.py create\|done\|list\|sweep --task <id>` |
| 트리 소유 (r27+r28) | 여러 세션이 같은 저장소에서 작업 중임을 서로 탐지 — 상대 claim 있으면 경고 + `git add -A`류 전체 스테이징 차단 | `scripts/tree_gate.py claim\|release\|check --session <id>` |
| 루프 탈출 (r29) | 같은 수정 3회 실패 → 증상 패치 금지·원인 진단 강제(neverstuck) | `scripts/neverstuck_gate.py --history <이력.json>` |

- 종료코드 공통: **0 통과 · 1 확인 의무(무시 금지) · 2 오류**
- CLI 플래그·JSON 스키마·한계 전문: [GATES.md](GATES.md) · 계약(사용 시점·권한·폴백): SKILL.md 각 게이트 절

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
