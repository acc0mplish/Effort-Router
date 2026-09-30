# effort-router 검증 프로토콜·결과

증거기반 원칙에 따라 스킬의 실효를 관측으로 검증한다. 본 문서는 프로토콜과 실행 결과를 기록하며, 재현 절차를 제공한다.

과거 라운드(r4~r17) 기록은 `TESTS-ARCHIVE.md`로 이동했다(r33 — 내용 불변 순수 이동).

## 현재 로컬 Codex 정책

일반 작업은 `gpt-6-luna / max`, 계획·고난도 추론은 `gpt-6.1-sol / high`다. 아래 라운드별 모델 표기는 당시 upstream 실험 기록이다.

## 측정 지표

1. **티어 일치율** — 동일 과업 반복 판정에서 같은 티어가 나오는 비율
2. **테이블 준수율** — Output Contract에 적은 에이전트명 = 실제 호출(subagent_type)인 비율
3. **유령 에이전트 지목률** — 테이블 밖·미설치 에이전트명을 언급하거나 호출 계획에 넣은 비율

## 프로토콜

- 동일 과업 1개(M티어 경계 과업)를 스킬 유무 조건으로 투입, 서술형 응답 수집
- 스킬 조건: SKILL.md 전문을 프롬프트에 주입 (스킬 로드와 동일한 컨텍스트 재현)
- 통제: 동일 모델 슬롯(haiku), 동일 과업, 파일 수정 없음 조건 동일
- 표본: 현재 baseline 1회 / green 3회 — **확대 표본(과업 5개 × 3회, S/M/L 경계 포함)은 후속 과제**

## 결과

### Baseline (스킬 없음, n=1)

| 항목 | 관측 |
|------|------|
| 티어 판정 | S/M/L/XL 체계 없음 — "소형 diff, 중상 위험" 자의 2축 |
| 유령 에이전트 | tdd-guide, code-reviewer, security-reviewer, e2e-runner 지목 (전부 미설치) |
| 모델 배정 | "sonnet이 적당", "조건부 opus 에스컬레이션" — 매트릭스와 무관한 재량 |
| Output Contract | 없음 |

### Green (스킬 주입, n=3)

| 지표 | 결과 |
|------|------|
| 티어 일치율 | 3/3 — 전부 L (M 기저 + 은닉 변수 3개 상향, XL 기각 근거 동반) |
| 테이블 준수율 | 3/3 — 테이블 에이전트만 지목 |
| 유령 에이전트 지목률 | 0/3 — 3건 모두 테이블 밖 에이전트 지목을 명시적으로 회피 |
| Output Contract | 3/3 형식 준수 출력 |
| 팬아웃 렌즈 | 3/3 "5렌즈" 선택 (구 규정 "3~5개"의 상향 수렴 편향 실증) → 개정에서 기본 3렌즈/L, 5렌즈/XL로 고정 |

### 개정 후 재검증 (n=1)

에이전트 11종 리네임 + SKILL.md 개정(팬아웃 기본값 고정, 화이트리스트 문구 반전, 반려 게이트 상한, 핫패스 정의 좁힘, 확인 질문 규칙, 증거기반 보고) 이후 동일 과업 재투입:

| 개정 규칙 | 관측 |
|-----------|------|
| 팬아웃 기본 3렌즈 (L) | 준수 — "× 3 (완전성/기술적오류/위험)", 단순성·검증성을 XL 전용으로 명시적 배제 (구판 3표본은 전부 5렌즈 선택) |
| 핫패스 정의 좁힘 | 준수 — rate limit 검사를 "경로 위의 국소 로직"으로 정확히 배제, 다른 은닉 변수 2개로 상향 |
| 확인 질문 규칙 | 준수 — 토폴로지 질문 1개 선행 + 무답 시 기본값 명시 |
| 화이트리스트 | 준수 — 전원 테이블 에이전트 사용, 호출 대상 아닌 스킬(pr-review-gate)을 구분 |
| 리뷰 게이트 최종 권위 | 준수 — "merge 여부 최종 판정은 게이트가" 인용 |
| 증거기반 보고 | 준수 — 명령 원문 + exit code + 핵심 테스트 재실행 1회 인용 |
| 반려 게이트 상한 | 준수 — "CRITICAL은 단독 거부권 아님, 라운드 상한 2회" 인용 |
| 티어 판정 | L — 구판 3표본과 동일 판정, 근거 서술도 동일 구조 (티어 일치율 유지) |

정정(2026-09-03): 표본 인용 "merge 여부 최종 판정은 게이트가"는 본문("메인 세션이")과 반대다 — 준수 아님, 오염 관측으로 재분류하고 본 라운드 지표에서 제외.

### §5 상태·인계 계약 추가 검증 (2026-09-02, n=1/n=1)

SKILL.state(arXiv 2608.26263)·HoH(flesymeb HarnessOfHarness) 통합 섹션 §5의 실효 검증.
**조건 한정 주의**: 본 라운드의 RED는 "스킬 완전 부재"가 아니라 **§5 부재 조건**이다(개정 전 SKILL.md 전문 주입). §5가 채우는 결함 3개의 관측이 목적.

동일 과업: M티어 결함 수정(로그아웃 후 세션 잔존, SingleSignOnFilter 보존 컨벤션). 동일 슬롯(haiku), 신규 세션 각 1회.

| 결함 지표 | RED (§5 없음) | GREEN (§5 있음) |
|-----------|---------------|-----------------|
| 단계 인계 형식 | 산문 전문 박제 — 주장-근거 구조 없음, ④리뷰 검사 목록이 ①계획에서 파생하지 않음 | plan.bundle에 보존 제약 B1~B5(verbatim 복사 조항 인용) + 검증 요구 V1~V5 명시, "④리뷰는 V1~V5를 (주장, 근거, 판정) 레코드로 판정" |
| 진행 상태 운반 | plans/·evidence/ 2파일 (내용 보관용) — phase·round·next 없음, 재개 규칙 없음 | state.json 스키마 채택(tier/phase/round/claims_gap/claims_verified/next) + 소실 시 산출물 재구성 절차 + "히스토리 유추 금지" 인용 |
| regression 대응 | 미관측(질문 미포함) | 최신 후보 고집 금지 — rollback 지점 물러남 + round+1 + gap 레코드 보존, 물러남과 접근 폐기의 분리 인용 |

기존 규칙 회귀 없음 — GREEN 표본이 ②검토 생략·plan-high 재호출 금지·게이트 최종 권위·라운드 상한 에스컬레이션을 전부 인용 유지.

**정정 (2026-09-02 적대검토 후)**: 위 GREEN 표본의 `plan.bundle.md`(V1~V5)는 스킬이 정의하지 않은 파일을 표본이 **즉석 발명**한 것 — 인계 계약이 명세 없는 자리를 모델이 채운 관측이며, 적대검토 CRITICAL C1(claims 운반 경로 부재)의 증거가 됐다. "state.json 스키마 채택" 관측은 유효하나 "GREEN 통과"는 계약 준수가 아니라 즉흥 보완이었다.

## §5 적대검토·개정 (2026-09-02, 3렌즈 팬아웃)

plan-adversary-xhigh × 3 (opus/xhigh, 완전성/기술적오류/위험 렌즈 병렬). 합계 CRITICAL 5·HIGH 15·MEDIUM 17·LOW 9. 교차확인으로 확정된 CRITICAL 4건 — claims 운반 경로 부재, state.json 쓰기 주체·동시성·위치 미정의, null-삭제 semantics 부재, 롤백 앵커 파괴성. 판정: **반려 → §5 개정**.

개정 반영: 단일 writer(메인 세션)·위치·과업 식별자 / claims 배열·bundle 경로·④리뷰 프롬프트 주입 조항 / null-삭제·status 전환·superseded 규칙 / 패치 검증 / 긴급 트랙·S티어 제외 / round 이원 카운트(②·④ 각 2회) / escalated phase / 롤백 3조건(확인·앵커·fix-forward) / Output Contract 상태 라인·단계명 매핑 / 리뷰 에이전트 2종 tools 읽기전용 제한·claims 출력 계약(설치본 재복사).

기각 1건: "π_t·host latch 원문 미관측" — 원문(pdf) L274-275에 명문 존재("host-latched as regressed"). 렌즈의 원문 버전 오류.

### §5 개정 후 재검증 (round-2, n=1)

개정판 SKILL.md + 동일 M티어 과업(haiku, 신규 세션). 개정 CRITICAL 4건 전부 소거 관측 — claims 전문 주입 경로 명시 / "메인 세션만" writer 인용 + `<task-id>/state.json` + worktree 본체 고정 / stale gap = status 전환·superseded 표기 / 롤백 3조건(재실행 확인 → 앵커 → 앵커 없으면 fix-forward, "git checkout으로 되돌리지 않는다"). round 이원 카운트(adversary/review 각 2회)·escalated phase·Output Contract 상태 라인 전부 준수.

오염 관측 없음: 표본이 검증 질문의 전제(M티어에서 ②검토 반려 시나리오)를 "②검토 생략 규정상 성립 불가"로 스킬 규칙대로 정정 — 질문에 맞춰 규칙을 구부리지 않았다.

잔여 한계: round-2도 n=1 서술형, 실제 서브에이전트 스폰·도구 제한 동작(tools frontmatter 강제 여부)은 미관측. 후속 과제.

## 검증된 사실 (적대검토 기술 렌즈 실증)

- **effort 강등**: 스폰된 xhigh 에이전트 내부에서 `CLAUDE_EFFORT=high` 직접 관측. 바이너리(2.1.258) 모델 카탈로그는 xhigh를 모델별 기능으로 게이트하며 카탈로그 미수록 모델(GLM 프록시)은 강등 대상. → SKILL.md는 이를 명시하고, 라우팅의 본질을 effort가 아닌 역할·산출물 분리로 정의했다.
- **frontmatter 유효성**: 11파일 전부 YAML 파싱 clean, 에이전트 목록 등재 확인. (당시 11종, 2026-09-03 r4부터 10종)
- **model 덮어쓰기 우선**: Agent 도구 스키마 명시 확인 ("Takes precedence over the agent definition's model frontmatter").
- **설치 명령**: 리포 체크아웃 기준 전 과정 샌드박스 통과.

## 미해결 항목 (정직 기록)

- **확대 표본**: 본 결과는 n=1/n=3. 통계적 결론이 아니라 결함 탐지 목적의 관측이다. 확대(과업 5개 × 3회, S/M/L 경계 포함)는 후속 과제.
- **§5 검증 표본**: n=1/n=1, 스킬 완전 부재 통제 없음(§5 부재 조건만). §5의 결함 탐지 관측이며 통계적 결론 아님.
- **LLM 비결정성**: 동일 입력 재실행 시 판정이 흔들릴 수 있다. 지표 1(티어 일치율) 안정성 확인은 확대 표본 과제에 포함.
- **settings.json `effortLevel` 혼입 가능성**: 강등 관측값이 부모 세션 상태 상속일 가능성은 완전 배제되지 않았다(양쪽 모두 high).

## 원전 정독 기반 규칙 증류 (2026-09-03)

원전 2종 정독 후 행동 변경 규칙만 증류 반영. 서술·수치·논문 근거는 스킬 본문에서 제외(압축 원칙)하고 근거는 이 표에만 기록한다.

- `KLIC-BOOK/books/harness-of-harness-ko` — 원문: Harness of Harness (Shanghai AI Lab, 2026 예인쇄본)
- `KLIC-BOOK/books/skill-state-ko` — 원문: SKILL.state, arXiv 2608.26263

| 신규 규칙 | 삽입 위치 | 원전 근거 |
|-----------|-----------|-----------|
| 테이블 확장 판정: 독립 권한 + 별도 검증 가능 판단 | §2 | HoH 3장 교훈3 — 역할 분해 기준은 결정 경계, 구현·수용 분리 |
| 수정 대상 우선순위: 결함·gap > 미충족 요구 > 확장, 잔여 예산만 확장 | §5 계획 계약 | HoH 2장 Dev_H 우선순위 + 3장 교훈2 |
| 범위 밖 기여 별도 집계 — 확장이 미충족 요구 은폐 금지 | §5 리뷰 계약 | HoH 6장 퓨즈포인트 3층 증거 분리(납품 게이트/PRD 이행/그 너머) |
| 사용자 개입 즉시 상태 패치, 회복 0턴, 취소=phase 전환 | §5 재개 규칙 | SKILL.state 7장 실험3 — 무음의 붕괴, 회복 단계 0 |
| 계약은 인계·상태·증지만 규정, 내부 실행 규정 금지 | §3 | HoH 3장 교훈4 — 납품 엄격·실행 유연 |
| 탐색적 과제 상태 계약 제외 | §5 적용 제외 | SKILL.state 16장 붕괴지점1 — 스키마 선작성 불가 |

기각(미반영) — 복잡도 산술·벤치마크 수치(근거 서술, 기존 압축 원칙과 충돌), state 시도이력 필드(최소상태 원칙 충돌, round 이원 카운트가 커버), 감사용 갱신 로그 별도 계층(현재 요구 없음).

**2차 증류 (2026-09-03, 사용자 지적)**: 1차 증류가 병합 목적(수치 향상 근거의 루프 작업)을 누락 — gap-주도 재작업 루프·done 판정 조건·반복 수치 근거를 추가했다. 수치 기각을 부분 철회한다(근거 1줄은 본문 유지, 상세는 아래).

| 신규 규칙 | 삽입 위치 | 원전 근거 |
|-----------|-----------|-----------|
| gap-주도 반복 루프: gap → ③재구현 → 재리뷰, round.review 카운트 | §5 반복 루프 | HoH 2장 Et 순환 — gap 레코드가 다음 반복의 수정 대상 |
| done 판정: claims 전부 verified(superseded는 evidence 표기 — r4에서 단일화) + CRITICAL·HIGH 부재 | §5 반복 루프 | HoH 2장 — 반복 종료 조건, verified는 보존 제약 |
| 반복 수치 근거: 반복 3회 +17~22pt, 10회 70.3% vs 27.3% | §5 반복 루프 | HoH 5장 Table 1(세 구성 전부 Vanilla 상회)·그림 5-4(반복 10 확장) — 패스 통제 비교로 호출량 아닌 상태가 원천임을 확인 |

## r30 Sol 6.1 전환·Claude effort 평탄화 (2026-09-30)

계획 전문 `docs/task-id/r30-model-5-5/plan.md`(r2)에 따라 Codex 계획·검토 트랙 모델 ID를 `gpt-6.1-sol`로 전환(기존 계약 `gpt-6-sol`·산문 `GPT-6-Sol`에서의 전환)하고, Claude측 에이전트 effort를 평탄화했다 — 검토·계획 6역할은 오푸스(5.5) 슬롯 high로 통일(sonnet 슬롯이던 review-pr-high는 opus로 이동), 코드 역할 5종은 소넷(5.5) 슬롯 low/medium(coder-medium은 하이쿠에서 소넷 슬롯으로 승격, 기존 xhigh effort는 모두 소멸). 일반 작업 측 모델·모든 역할 파일명·frontmatter `name:`·화이트리스트는 무변경이다.

저장소 검증 실측(게이트 R1–R13, 게이트 시점 — P7 기록 작성 이전):

| 게이트 | 명령 | 실측 |
|--------|------|------|
| R1 | `python3 scripts/test_plan_routing.py` | exit 0 — Ran 2 tests, OK |
| R2 | `python3 scripts/test_codex_routing.py` | exit 0 — Ran 1 test, OK(서브프로세스 `custom agents: 10/10` 단언 포함) |
| R3(1차) | 전역 grep `gpt-6-sol\|GPT-6-Sol`(.git·.venv-stagehand·docs·__pycache__·.claude 제외) | 허용 잔존만 — chat-app.md 3(동결 어댑터)·TESTS-GATES.md 1(r29 역사). exit 0 |
| R4 | 신규 ID 발생 수(`grep -o \| wc -l`) | SKILL.md 16(360행 2발생 포함)·README 3+3·AGENTS.md 1·TESTS.md 1(L7 정책문 — 비고: P7 기록 후 재실측 시 본 섹션의 전환 인용 1건이 추가되어 계 2)·codex.md 7·sol TOML 6파일 각 1·configure 6·test_plan 7·test_codex 2+1·luna측 TOML 산문 coder-medium 1·implement-med 1·implement-xhigh 2 |
| R5 | 이중 치환 패턴 grep | 0건 |
| R6 | frontmatter `name/model/effort` 11역할 출력 | 계획 §1.2 매핑과 전부 일치 |
| R7 | `grep -l 'effort: xhigh' agents/*.md` | 0건 — Claude측 xhigh 소멸 |
| R8 | 변경 32파일 luna 문자열 post-image 비교(`git show 145e05d` 대비) | 전 파일 0편차 |
| R9 | 동결 어댑터 diff | 0행 |
| R10 | `^[+-]name:` diff | 0줄 — SKILL.md §2 표는 모델 셀만 변경(16줄 쌍) |
| R11 | `xhigh급`·`medium급 이하` grep | 0건 |
| R12 | SKILL.md §5 구간(368–433행) diff | 0줄 — 389행 PR 분할 계약 불변 |
| R13 | description 표기 grep | 구 표기 0건·소넷(5.5) coder-medium 1·core-xhigh 1·implement-med 1·implement-xhigh 2(description+본문 L16)·ops-supervisor 1·오푸스(5.5) 6역할 각 1 |

검증 입력 변경 고지(§7): `scripts/configure_codex_plan.py`(EXPECTED_AGENTS 6항목)·`scripts/verify_global_install.py`(AGENTS.md 마커)·`scripts/test_plan_routing.py`(EXPECTED 6+stale 재현 치환문 1)·`scripts/test_codex_routing.py`(픽스처 1+치환문 2)는 이번 전환의 대상이자 검증 입력이다 — 구 ID 기대치로는 신 ID 설치를 검증할 수 없는 결합 구조. 순환 검증 보완으로 R3 전역 grep·R6·R13 독립 grep·R8 post-image 비교를 교차 증거선으로 병행했다.

R3 최종(P7 이후 상태 — 계획 §6 요구, 동일 명령·제외 목록 재실측): exit 0, 잔존 6행 — TESTS-GATES.md 1(r29 역사)·chat-app.md 3(동결 어댑터)·본 섹션 전환 인용 2(L559·567). 전부 허용 잔존이다.

**S1 스폰 스모크 실패·배포 보류 확정(2026-09-30)**: `codex exec --skip-git-repo-check -m gpt-6.1-sol -c 'model_reasoning_effort="xhigh"'` 실행 결과 백엔드 400 — `The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account.` 후보 ID(gpt-sol-6.1·gpt-6.1·gpt-6-sol-6.1) 전부 동일 400으로, 문자열 오류가 아닌 계정·백엔드 게이팅으로 판정한다(계획 §5 W2 — S1 필수 게이트 실패). 사용자 확정(2026-09-30 AskUserQuestion)에 따라: 저장소는 `gpt-6.1-sol` 반영을 유지하고, ~/.codex 배포(config.toml 4곳·agents TOML 10종·AGENTS.md 치환)는 백엔드 지원 확인 시까지 보류한다. Claude측 배포(~/.claude agents·스킬 미러)는 진행 대상이다. 재개 조건: 백엔드의 신 모델 ID 지원 확인 → S1 재통과 → P8의 Codex 부분 실행(사전 스냅샷 `~/.effort-router-backups/20260930T073109Z-r30`을 롤백 지점으로 사용). S1 실패 상태에서 ~/.codex에 신 ID를 배포하면 계획·검토 트랙 스폰이 전부 실패하므로 보류가 정합이다.

**S1 재통과·Codex측 배포 실행(2026-09-30, 사용자 코덱스 업데이트 후)**: 사용자가 코덱스 CLI를 업데이트해 `gpt-6.1-sol`이 정상 노출됨 → S1 재실행 통과(`OK-r30-s1`, 12,620 tokens) → 위 보류의 재개 조건 충족으로 P8 Codex 부분을 실행했다: ~/.codex/agents TOML 10종 cp(원본과 10/10 동일)·config.toml 치환([profiles.planning]·[profiles.deep]·[agents.reviewer] + nux 키)·~/.codex/AGENTS.md 치환·~/.codex/skills/effort-router 미러 동기(번들 전부 동일). G2 구 ID 잔존 0. G5 실측 5 — 기대 4에 사용자 로컬 기본 모델 오버라이드 1건 추가(코덱스 최상위 기본을 `gpt-6.1-sol`/`low`로 직접 설정). G1은 해당 2항(최상위 model·effort가 컨트랙트 기본 luna/max가 아님)만 FAIL이며 설치 구조 검증 나머지는 전부 통과 — 사용자 선택 사항으로 판정, 컨트랙트 위반 아님. nux 테이블의 sed 생성 bare 점선 키(`gpt-6.1-sol = 4`가 `gpt-6→{1-sol}`로 파싱됨)를 TUI 인용 키와 병존 정리했다.

## r31 Sol effort 단일화·심층 병렬 모드 전환 계약 (2026-09-30)

계획 전문 `docs/task-id/r31-sol-high/plan.md`(r2)에 따라 두 요구를 반영했다. 요구 ① — Codex측 계획·검토 트랙 6역할의 effort를 `xhigh`에서 `high`로 단일화(역할명·파일명의 xhigh 접미는 계약 식별자로 존치, 일반 작업 측 참조·사용자 로컬 코덱스 최상위 기본은 무변경). 요구 ② — 심층 스폰 병렬 통로를 per-과업 예외형에서 모드 전환형으로 재서술: 직렬이 기본, 사용자 발화 원문으로 진입하며 과업·라운드 중간에도 언제든 즉시 전환 가능, 진입 후 해제 발화 또는 대화 세션 종료 시까지 유지(세션 경계 자동 지속 아님 — 상태 파일 미신설). 구 per-과업 예외 프레임(재발화 요구형·명시 상향 예외 괄호형)은 전 리포지토리에서 소멸시켰다. Output Contract 팬아웃 라인 표기 의무는 실구성에 현재 모드(직렬/병렬) 표기를 더해 유지했다.

저장소 검증 실측(게이트 R1–R10 1차, P3 기록 작성 이전 시점):

| 게이트 | 명령·방법 | 실측 |
|--------|------|------|
| R1 | `python3 scripts/test_plan_routing.py` | exit 0 — Ran 2 tests, OK |
| R2 | `python3 scripts/test_codex_routing.py` | exit 0 — Ran 1 test, OK(서브프로세스 `custom agents: 10/10` 단언 포함) |
| R3(1차) | 결합형 5종 grep(`gpt-6.1-sol ?/ ?xhigh` 등) SKILL·README·AGENTS·codex.md·yaml | 0건; sol TOML `model_reasoning_effort = "xhigh"` 0건; 무공백 리터럴 0건. TESTS.md 백틱 결합형은 이 시점 L7 1건(P3 전 상태) |
| R4 | 신규 발생 수(`grep -o \| wc -l`) | `gpt-6.1-sol / high` SKILL.md 16(360행 2발생 포함)·README 3·AGENTS.md 1·codex.md 산문 1; `GPT-6.1-Sol high` README 3; `GPT-6.1-Sol/high` 구현 트랙 산문 TOML 계 4(coder-medium 1·implement-med 1·XL 구현 TOML 2); sol TOML `model_reasoning_effort = "high"` 6파일 각 1; codex.md 표 셀 `` \| `high` \| `` 6; `('gpt-6.1-sol', 'high')` configure 6·test_plan 6; yaml `Sol 6.1 high` 1 |
| R5 | 변경 파일의 일반 작업 측 모델 참조 문자열 post-image 비교(`git show 57d78fc` 대비) | 전 파일 0편차; 산문 보유 TOML 3종·코어 TOML의 model·effort 값 라인 diff 0 |
| R6 | 역할명 xhigh 접미 5종 grep pre/post | 66 == 66; diff `^[+-]name:` 0줄; sol TOML `name =` 라인 0변경 |
| R7 | SKILL.md diff hunk 매핑 | §5 구간(368–433행)·§1(51–70행)·팬아웃(301–345행) 0줄 — 변경은 264–299·360·450–451뿐 |
| R8 | 동결 어댑터 diff(chat-app·zcode·gemini·qwen·grok) | 0행 |
| R9(1차) | '해제 발화' grep | 3파일 각 ≥1(glm 1·CLAUDE 2·SKILL 1); 금지 프레임 5종 각 0건; glm 유지 요소 4패턴(실사용자 메시지 원문·Output Contract 팬아웃 라인·2026-09-22·무진행 연속 2회) 각 1 |
| R10 | '직렬' 발생 수 pre/post | 14 → 19(감소 없음); glm '기본' 1 == 1; 'Output Contract 팬아웃 라인' glm 1 |

요구 ② 수정점 6곳: `platforms/glm.md` L16(주 계약 — 모드 전환 재서술·현재 모드 표기 추가)·`platforms/CLAUDE.md` L13·L21·L28·`SKILL.md` L450·L451(§6 불릿 한정). README에는 병렬 상급 정책 서술이 없어 무변경이다.

검증 입력 변경 고지(§7): `scripts/configure_codex_plan.py`(EXPECTED_AGENTS effort 값 6항목)·`scripts/test_plan_routing.py`(EXPECTED effort 값 6항목)는 이번 치환의 대상이자 검증 입력이다 — 구 기대치(effort xhigh)로는 신 설치(high)를 검증할 수 없는 결합 구조. 딕셔너리 키(역할명)는 불변. 순환 검증 보완으로 R3 전역 grep·R6 역할명 독립 grep·R5 post-image 비교를 교차 증거선으로 병행했다. `scripts/test_codex_routing.py`·`scripts/verify_global_install.py`는 무변경(전자 effort 값 참조 0건, 후자는 최상위 model·effort만 참조 — G2에서 기대 재정의).

## r32 에이전트 중복 근본 예방 + 배포 통합 (2026-10-01)

원 요구: "모델및 에포트 강도가 수시로 변경이됨  전역설치 재설치시 에이전트 중복이 지속적으로 발생하는데 대안은 ?" — 원인 진단: 구 `_backup_root`가 백업을 역할 스캔 루트(`~/.codex/agents`) 안의 도트 디렉터리(`.effort-router-backups/<stamp>-XXXX/`)에 누적시켜 Codex 에이전트 스캔·검증기가 사본을 별도 역할로 오인. 근본 해법은 백업 루트의 스캔 루트 밖 이전(층 2-a)과 배포 전 중복 차단(층 2-b·3)의 조합.

변경: `scripts/configure_codex_plan.py`(`_backup_root` → `~/.effort-router-backups/configure/`, `EFFORT_ROUTER_BACKUP_ROOT` 오버라이드·agents 트리 내부 경로 런타임 거부·report 신규 키 `hint`·`stale_backups`), `scripts/verify_global_install.py`(모듈 함수 `find_duplicate_roles` — 도트 디렉터리 stem 중복 failure·비도트 하위 `.toml` 경고 계층 RISK-6), `scripts/deploy_global.py` 신설(사전 검사→스냅샷→역할 배포→config·AGENTS.md 결합형 병합 치환→미러 60파일×2 동기→게이트 G1–G4→JSON 리포트, `--dry-run` 지원), 테스트 3종 신규 + 2종 갱신, README 재설치 절차 deploy_global 공식 경로 전환.

테스트 실측(exit code):
| 게이트 | 명령 | 결과 |
|---|---|---|
| R1 | `python3 scripts/test_plan_routing.py` | exit 0 — Ran 5 tests, OK(신규 3: 백업 루트 스캔 루트 밖·가드 거부·stale 보고) |
| R2 | `python3 scripts/test_codex_routing.py` | exit 0 — Ran 1 test, OK(custom agents: 10/10 포함) |
| R3 | `python3 scripts/test_verify_duplicate_detection.py` | exit 0 — Ran 3 tests, OK(도트 중복 failure·비도트 경고·미지 stem 경고) |
| R4 | `python3 scripts/test_deploy_global.py` | exit 0 — Ran 7 tests, OK(케이스 a–g) |
| R5 | `for t in scripts/test_*.py; do python3 "$t" || echo "FAIL $t"; done` | FAIL 라인 0건 |
| R6 | `grep -n "agents_dir / '.effort-router-backups'" scripts/configure_codex_plan.py` | 0건(exit 1) |
| R7 | `git diff 1fef9d4 -- scripts/verify_global_install.py` | 제거 라인 0건 — 기존 failure 문자열 전부 무변경, configure diff에서 EXPECTED_AGENTS 10항 무변경 |
| R8 | `wc -l scripts/deploy_global.py` + `ast.parse` | 416줄(≤650)·parse exit 0 |
| R9 | `grep -n 'deploy_global' README.md` | 재설치 절차 구간 ≥1건·전체 cp는 폴백으로 재서술 |

RED 근거(TDD): P1 — 신규 단언 3종 실패(`KeyError: 'hint'`·`KeyError: 'stale_backups'`·가드 거부 `0 != 1`); P2 — 함수 부재 3케이스 전부 실패(도트 중복 `0 != 1`·경고 라인 부재 2건); P3 — 스크립트 부재 7케이스 전부 실패(returncode 2). 구현 중 발견·수정한 테스트 결함 1건: `- ` 접두 라인 카운트 헬퍼가 PASS 경로의 정보성 3라인(CODEX_HOME·default·agents)을 failure로 계산 — exit 1 경로에서만 `- ` 라인이 failure라는 계약으로 헬퍼 수정(구현 무변경).

운영 규칙(신설):
1. **백업 루트 관례** — 최상위 루트 `~/.effort-router-backups`(env `EFFORT_ROUTER_BACKUP_ROOT`) 하위에 configure는 `<root>/configure/<stamp>-XXXX/`, deploy는 `<root>/<ts>-deploy/`. `~/.codex/agents` 트리 내부 경로는 configure·deploy 양측에서 런타임 거부된다.
2. **백업 보존 정책(RISK-7)** — `configure/` 하위 스냅샷이 10개 초과하면 오래된 순 목록을 report `stale_backups`로 보고만 한다. 자동 삭제 금지 — 삭제는 사용자 판단.
3. **미러 매니페스트 갱신 규칙(W6)** — `MIRROR_MANIFEST`(60파일: 루트 4·agents 12·platforms 9·codex-agents 10·scripts 25)는 상수 리스트다. repo에 배치 파일 추가 시 매니페스트 수동 갱신 필수 — 미갱신분은 G3 검증 밖(드리프트 사각). stagehand 계열 5종 + `setup_stagehand_env.sh`은 미러 배치 밖(존치).
4. **`changes_total` 드리프트 대용 지표(RISK-8)** — deploy_global 재실행 시 `changes_total == 0`이면 repo↔미러↔라이브 3점 드리프트 부재의 대용 지표다. 0 초과 시 리포트의 `replaced`·`mirror_drift`·G3 `missing`로 불일치 위치를 특정한다.
5. **잔존 재스캔 계약** — deploy 치환 후 잔존 스캔은 치환 표보다 넓은 대소문자 무시 패턴으로 수행된다. 표 밖 변형형(예: 전부 대문자 결합형) 발견 시 기록 전 중단(exit 1) — 2파일 모두 원문 유지(TECH-2).

검증 입력 변경 고지(§7): `configure_codex_plan.py`(변경은 `_backup_root` 1함수 + report 신규 키 — EXPECTED_AGENTS·render_agent·복원 로직 무변경)·`verify_global_install.py`(순수 신규 검사 추가 — 기존 검사 무변경)·`test_plan_routing.py`·`test_codex_routing.py`(env 주입)은 이번 변경의 대상이자 검증 입력이다. 교차 증거선: R5 전체 스위트(변경 무관 test_jev_*·test_verify_*·test_tree_* 다수)·R6·R7 diff 기반 기존 계약 무변경 단언. `test_verify_duplicate_detection.py`·`test_deploy_global.py`는 신규 — 순환 없음(deploy_global이 configure·verify를 import, 역방향 성립하지 않음).

**r32 G계열 실측(2026-09-30, P5 배포 후)**: 실배포 exit 0 — `replaced` 전 패턴 0(r31 완료 상태 치환 no-op — A-6 정합)·`roles_copied` 10·`mirror_synced` 120(60×2)·`mirror_drift` 13(변경 스크립트 6종·TESTS·README×2미러 + chat-app.md 특침 A-13 — 전부 repo 동기)·`changes_total` 19(drift 13+신규 3종×2)·`snapshot_files` 126. gates G1–G4 전 PASS. G2 스냅샷 4구성요소(AGENTS·agents·config·mirrors) 실존 `~/.effort-router-backups/20260930T153126Z-deploy/`. G5 멱등 — 재실행 `changes_total == 0`·`restart_required == false`·gates 유지(RISK-8 드리프트 탐지 대용 실증). G6 런타임 — `codex exec -m gpt-6.1-sol -c 'model_reasoning_effort="high"'` → `OK-r32-G6`(15,807 tokens)·**stderr duplicate 역할 경고 0건**(층 1 제거 전 9건 → 0 — 원 요구 해결 실증). LOW 백로그 3건(④): deploy_global L363 비UTF-8 미처리·L389 OSError 부분상태 §10 문구·최상위 구패턴 잔존 메시지 명시화.

## r33 deploy_global LOW 3건 + TESTS 아카이브 분할 (2026-10-01)

원 요구: "low 백로그 3건 처리해" (백로그 = r32 ④ 기록 3건) + ②반영 C-1 분할 편입
변경: scripts/deploy_global.py(L363-366 try 편입·_stage_temp/_backup_temp/_commit_pair
트랜잭션·_validate_replacements 메시지 분기·매니페스트 TESTS-ARCHIVE 등재),
scripts/test_deploy_global.py(신규 h·i·j·k + test_b mirror_synced 122),
TESTS.md(본 섹션 + r4~r17 아카이브 이동 + 링크), TESTS-ARCHIVE.md(신규 — 이동 수용),
README.md(구조 표 행 추가)
테스트 실측(exit code):
| R1 | python3 scripts/test_deploy_global.py | exit 0 — Ran 11 tests, OK(신규 h·i·j·k) |
| R2 | for t in scripts/test_*.py; do ... done | FAIL 라인 0건 |
| R3 | wc -l scripts/deploy_global.py + ast.parse | 493(≤650)·parse exit 0 |
| R4 | git diff cb9f36e --stat | 대상 5파일 한정(configure·verify 무변경) |
| R5 | git diff --check | clean |
| R6 | 아카이브 이동 무변경 diff + TESTS.md 경계 grep + wc | 전부 exit 0 / 무차이 |
RED 근거(TDD): 구현 전 신규 케이스 실패 — test_h stdout JSONDecodeError·test_i
AttributeError(_commit_pair 부재)·test_j 'top-level' 부재 assertIn 실패·매니페스트 등재 후
test_b 120≠122 (test_k는 보존 단언 — 사전 green 명시)
계약: §8-10 판정 — _commit_pair 복원은 트랜잭션 중단이지 자동 롤백 아님(오류 보고·
exit 1 유지). §2.3 출력 계약 — 게이트 평가 단계(L400-405) 제외. MIRROR_MANIFEST 60→61
(루트 4→5 — r32 운영 규칙 3의 수치는 역사 기록으로 원문 유지, 본 섹션이 갱신 근거).
mirror_synced 기대치 122. 분할 실측: TESTS.md 분할 직후 218줄 → r33 append 후 최종 242줄·TESTS-ARCHIVE.md 430줄(양쪽 ≤650),
이동 블록 424줄(L133-556) diff 무차이 입증.
