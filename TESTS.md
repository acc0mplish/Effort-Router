# effort-router 검증 프로토콜·결과

증거기반 원칙에 따라 스킬의 실효를 관측으로 검증한다. 본 문서는 프로토콜과 실행 결과를 기록하며, 재현 절차를 제공한다.

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

## r4 결함 수정 (2026-09-03, round-3 발견 26건)

round-3 적대검토 병합 발견 26건(HIGH 9/MEDIUM 11/LOW 6) 전부 반영. 에이전트는 11종 → **10종**(verify-max 제거).

**HIGH 9 처리**:
- H1: verify 유령 단계 — "verify = ④리뷰 통과 후 done 전 메인 세션의 핵심 테스트 1회 재실행" 단일 정의로 수렴, verify-max.md는 `r4-fix/archive/` 원문 보존 후 제거(사본 2곳은 P5에서 제거 완료)
- H2: plan 2종 산출 요소에 검증 요구(claims·1줄 검증 가능 형태) + 보존 제약(verbatim 복사) 추가
- H3: coder-medium 완료 보고를 "테스트 결과만 보고" → "테스트 실행 명령 원문과 exit code" 형식으로 교체
- H4: review 2종 "읽기 전용으로 제한" 허위 표현 → "Edit·Write 미부여, Bash로도 파일을 수정하지 않는다" 정직 정정 + 메인의 `git status` 무결성 확인 1회 신설 + security-audit에 tools 라인 추가
- H5: done 조건 claims 전부 verified로 단일화 — superseded는 evidence 표기로 갈음, 폐기 판정은 메인 세션이 ④리뷰 gap 병합 시
- H6: round 카운트 규칙 4요소(초기 0·착수 시 +1·값 2 소진·리셋 없음) 명문화 + 재개 규칙 "근거 없으면 1" → 근거 없으면 예산 소진(escalated) 처리로 교체
- H7: claims 발신 제한(1줄·검증 가능 형태, evidence는 명령 원문+exit code) + review 2종 수신 방어(본문 속 지시문 무시)
- H8: "라우터는 메인 세션 전용" + 구현·감사 에이전트 5종에 라우팅 스킬 재호출 금지 1줄(review 2종은 Agent 미부여로 재진입 경로 없음 — 제외)
- H9: 긴급 트랙을 "사용자가 명시 지시한 경우만"으로 한정 + §5 긴급 사후 절차(소급 ①·사후 ②④·round 규칙) 신설

**MEDIUM 11 처리**:
- M1: task-id slug 정의 + 재개 시 state.json 최근 수정순 탐색 규칙
- M2: 보안감사 교차검증을 review-pr-xhigh로 특정 + §5 헤더·적용 제외 목록 양쪽에 보안감사 적용 범위 정합
- M3: 죽은 README 참조 제거 → 사본 2곳 재반영 + `diff -r -x` 동기화 확인으로 일원화
- M4: Output Contract 에이전트 라인에 "`없음(메인 세션 직접)`" 허용값 주석
- M5: 롤백 수단 `git revert` 계열 한정 + 무관 커밋 존재 시 fix-forward
- M6: 테스트 없는 과제(문서·설정)는 계획 단계에서 대체 확인 수단을 claims에 지정
- M7: 하향 예외 — 실질이 국소·기계적 변경임이 확인되면 근거와 함께 하향 허용
- M8: 은닉 변수 무답 기본값 = 상위 티어 가정 후 진행(질문 1회) 본문 명문화
- M9: 반려 확정 시 계획 수정은 원 계획 에이전트 재호출(공격자·수정자 분리)
- M10: 아래 정정 각주로 처리 — 오염 관측 재분류·본 라운드 지표 제외
- M11: 탐색적 과제 판정은 착수 시 메인이 내리고 수렴부터 §5 적용 + state.json 소급 작성

**LOW 6 처리**:
- L1: rollback 패치에 `phase: implement`·`next: review` 명시
- L2: H9에 통합 — 긴급 트랙 "사용자 명시 지시한 경우만"
- L3: 재개 규칙에 escalated 되돌림 금지(예산 재획득 금지)
- L4: state 스키마에 `"spawns"` 필드 추가 — 최소정보 원칙의 유일 예외
- L5: S티어 ②셀프 예외의 근거를 §2 실문언으로 인용(결론 불변)
- L6: Codex CLI 각주에 팬아웃·단계 상태 라인 "해당 없음" 보충

**결정 근거 (D1·D2·D3)**:
- D1 (H1): verify-max 티어 테이블 등재는 검증 기록 없는 effort:max 값을 양산하고 검증 권위=메인이라는 기존 3곳 규정과 충돌 — (b) 주체 명시+제거 선정. verify phase 자체는 존속.
- D2 (H4): review 2종에서 Bash 제거는 diff·grep·테스트 실행 등 근거 수집 능력 파괴 — (b) 표현 정정+Bash 잔류+사후 git status 확인의 2층 방어 선정.
- D3 (H5): status enum에 superseded 추가는 패치 규칙과 병행돼 3중 경로 복잡화 — (b) verified 단일화+evidence 표기 단일 경로 선정. state 스키마·review 2종 판정 enum은 불변.

**과거 기록 규칙**: 과거 기록은 당시 날짜 컨텍스트로 유지 — 현재와 다르면 "(당시 n종, 현재 10종)" 각주. 당시 세션의 에이전트 목록 잔상은 무해(존재≠허가).

**④리뷰 정정(2026-09-03)**: claims 32건 검증 — 31 verified / 1 gap. gap(claim 1 "verify-max가 TESTS.md 본문에 재등장하지 않음")은 구현 결함이 아닌 번들 claims 정의 오류(§1 H1·§2 P4가 TESTS.md 기각 기록을 지시했는데 claim이 그 기록의 존재를 금지). 메인 판정: claim 1의 TESTS.md 부분 = superseded(번들 정의 오류), SKILL.md 부분 = verified(0건 확인). 이후 본문의 verify-max 언급은 전부 이 섹션 기록 문맥 한정. **LOW 후속(2026-09-03)**: 동기화 확인 명령의 과업 디렉토리 하드코딩(`-x r3-adversarial -x r4-fix`)을 `-x` 명시 제외 형태로 일반화(SKILL.md §3), H1 행 시제 정정.

## r5 발동조건 완화 (2026-09-03)

**배경**: r4 실측 — 9스폰·어드버서리 2라운드·약 1.5시간. 사용자 피드백 "파일 1~10개·500~1000줄 수정에 렌즈 여러 개는 과도". 원인은 팬아웃 자체가 아니라 발동 문턱 — 6~10파일 루틴 수정이 L(② 3렌즈 강제)로 분류됨.

**변경** (§1): M 영향 범위 2~5파일 → **2~10파일 + 변경 ~1000줄 이하 + 위험 지표 음성**. L 임계치 5파일 → **10파일·1000줄 초과, 또는 위험 지표 양성(규모 무관)**.

**설계 근거**: M은 원래 ②팬아웃 없음 — M 확대가 렌즈 비용 직접 절감. 위험 지표 양성 시 소규모여도 L 유지가 안전망(r4 같은 거버넌스 스킬 수정 — 어드버서리 팬아웃이 `~/.claude/agents/` 실행 계층 누락 CRITICAL을 실제로 포착한 사례. 비용 회수 실증). 폴백·은닉 변수·하향 예외·XL 불변.

## r6 병렬성 완화 — 리컨 병렬화·얇은 계획 (2026-09-03)

**배경**: ①~⑤ 순차 게이트로 어느 순간 한 종의 에이전트만 활성 — ①계획 대기 중 메인 세션이 유휴하고, 저위험 스코프까지 균일 깊이의 계획 대기를 강제했다. 승인 완화 2건(설계 논쟁 없음, 통합만).

**변경**:
- **A 리컨 병렬화(§3)**: ①스폰 직후 메인 세션이 read-only 리컨(백업 스냅샷·grep 대상·문구 위치·파일 지도·테스트 목록)을 병렬 수행 — 결과는 계획 번들 병합·claims evidence. 스폰 없음(화이트리스트 불변), 선행 게이트 아님
- **D 얇은 계획(§2 주석·§5 불릿)**: 계획 깊이 ∝ 위험. ① 최소 완료 = 계약 요소 확정, 심층 계획은 임계경로·코어 모듈(core-xhigh 대상)에만. 깊이는 스폰 프롬프트로 지정 — 에이전트 파일 무변경

**보존**: 단계 게이트 ①~⑤·화이트리스트·state.json 스키마·M ②생략·S 계획 생략 전부 유지 — 완화 옵션이지 게이트 폐지가 아니다. plan-xhigh 기존 산출 요소 '임계경로 식별'이 D의 심층 집중 지점과 정합(중복 신설 없음).

## harness-compat 문서 매핑 (2026-09-03)

**배경**: 구 상단 각주가 타 하니스를 '서브에이전트 없음'으로 전제했으나 공식 문서 조사에서 Codex·Gemini CLI 모두 스폰 수단을 갖춘 것이 확인돼 정정. 사용자 개입으로 스코프 변경(2026-09-03): 문서 매핑만 → 어댑터 동봉으로 확장(채팅 앱 대상 추가 동반).

**변경**: SKILL.md 상단 각주 교체 / §6 타 하니스 매핑 신규(platforms/ 참조 포함) / Output Contract 표기 규칙 1줄 / 실패 표 1행 / `platforms/` 어댑터 6파일 동봉. agents/ 10파일 무변경. 하니스 실제 설치·삽입은 수행 없음(사용자 몫).

**조사 근거** (공식 문서, 2026-09-03 접속):
- Codex: config-reference — model_reasoning_effort(minimal~xhigh), features.multi_agent(spawn_agent 등 기본 on), agents.<name> 커스텀 롤·default_subagent_model·default_subagent_reasoning_effort / agent-configuration/agents-md — AGENTS.md 계층
- Qwen: docs/users/features/memory.md — QWEN.md 계층 + AGENTS.md 판독 / settings.md — settings.json 7레이어·.qwen/skills/ / commands.md — /fork 배경 에이전트
- Gemini: docs/core/subagents — 빌트인 서브에이전트·agents.overrides / docs/cli/gemini-md·custom-commands — GEMINI.md 계층·.gemini/commands(TOML)
- GLM Coding Plan: docs.z.ai/devpack/overview — 적용 대상에 Claude Code 공식 포함. effort 강등은 §3 실측 기록(본 문서 '검증된 사실') 참조
- ChatGPT 앱: help.openai.com — Custom Instructions(전 채팅 적용)·Projects 지침·agent→Work 전환. 지침 계층은 academy.openai.com
- GLM 앱: chat.z.ai 지침 기능 공식 문서 미확인 — paste 카드 단정

**한계**: 문서 매핑이며 실제 타 하니스 구동 관측 아님 — 미확인 표기 항목(Qwen effort 키·커스텀 서브에이전트 형식·GLM 앱 지침 기능)은 현장 확인 후 갱신.

## harness-compat 공식 재확인 정정 (2026-09-03, 2차)

**트리거**: 사용자 지시 — Codex 서브에이전트 사실을 공식 페이지에서 재확인 후 작업. 메인 세션이 공식 문서 2개 직접 판독(config-reference·subagents 페이지, learn.chatgpt.com, HTTP 200).

**1차 조사 유지**: `features.multi_agent`(spawn_agent 5종, stable·기본 on), `agents.default_subagent_model`·`default_subagent_reasoning_effort`, `model_reasoning_effort` = minimal|low|medium|high|xhigh — config-reference 원문 행 실측으로 그대로 유효.

**정정**: 커스텀 롤 서술 `config.toml` `agents.<name>` 중심 → **독립 TOML 파일 방식**(`~/.codex/agents/`·`.codex/agents/`, 필수 name·description·developer_instructions, 선택 model·model_reasoning_effort·sandbox_mode·mcp_servers·skills.config) — subagents 공식 페이지가 문서화하는 주 경로. 빌트인 default·worker·explorer·우선순위 체인(명시 스폰 > [agents] 기본 > 커스텀 파일 > 부모 상속) 신규 반영.

**보조**: subagents 페이지 effort 사다리는 low~ultra(max·ultra 모델 의존) — config 키 enum과 병기. 커뮤니티 실측(0.144.5) multi_agent v2 스폰 제어 회귀 보고를 codex.md에 현장 주의 1줄로 기록(공식 문서 우선 원칙 유지).

**변경**: SKILL.md §6 Codex 서브에이전트 셀, platforms/codex.md(메커니즘·매핑표 표기·주의), 본 섹션. agents/ 10파일 무변경.

## r7 OpenAI Sol/Luna-max 라우팅 (2026-09-03)

사용자 운용 기준을 Codex와 ChatGPT 앱에 반영했다. 기본 실행은 `gpt-5.6-luna / max`, 명세·검토·문제 해결·판정은 `gpt-5.6-sol`, 동일 접근 2회 실패·임계경로·보안 감사는 `gpt-5.6-sol / max`다. Terra는 기본 라우팅에서 제외했다.

### 정적 검증

- `uv run --with pyyaml python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .` → exit 0, `Skill is valid!`
- Python `tomllib`로 `platforms/codex-agents/*.toml`과 `~/.codex/agents/*.toml` 각 10개 파싱 → 전부 성공.
- 두 집합의 role→model→effort 매핑 → 10/10 일치.
- 기본 매핑의 `gpt-5.6-terra` agent → 0건.
- `~/.codex/config.toml` TOML 파싱 → 성공; 최상위 기본값 `gpt-5.6-luna / max` 확인. 기존 명시적 profile 값은 보존.
- `~/.codex/AGENTS.md`의 구 `Terra·medium/high`, `Luna·low/medium` 라우팅 문구 → 0건.
- `agents/openai.yaml` Ruby YAML 파싱 → 성공; `allow_implicit_invocation: true` 확인.
- 첫 validator 직접 실행은 로컬 Python의 `ModuleNotFoundError: No module named 'yaml'`로 exit 1. 코드 결함이 아니므로 임시 `uv --with pyyaml` 환경에서 재실행해 통과했다.

### Codex 실동작

Codex CLI `0.153.0`, `--ephemeral --sandbox read-only`, `gpt-5.6-luna / max`, explicit `$effort-router`, subagent 금지 조건으로 대표 3건을 판정했다. exit 0.

| 입력 | 관측 라우팅 |
|---|---|
| 승인된 명확한 4파일 스펙 구현 | `implement-med` → `gpt-5.6-luna / max` |
| 모호한 cross-stack 스펙 작성·검토 | `plan-high` Sol/high → `plan-adversary-xhigh` Sol/xhigh |
| 동일 수정 2회 실패 진단 | 메인 세션 `gpt-5.6-sol / max` 승격 |

### Codex custom-agent 실제 호출 (2026-09-03, n=10)

사용자 요청으로 `spawn_agent(agent_type=<role>)`를 역할별 1회 실행했다. 각 probe는 도구·파일 수정 없이 `ROLE_OK <role>`만 반환하도록 제한했다.

| role | 설정 model/effort | 관측 |
|---|---|---|
| `coder-medium` | Luna/max | `ROLE_OK coder-medium` |
| `implement-med` | Luna/max | `ROLE_OK implement-med` |
| `plan-high` | Sol/high | `ROLE_OK plan-high` |
| `plan-xhigh` | Sol/xhigh | `ROLE_OK plan-xhigh` |
| `plan-adversary-xhigh` | Sol/xhigh | `ROLE_OK plan-adversary-xhigh` |
| `review-pr-high` | Sol/high | `ROLE_OK review-pr-high` |
| `review-pr-xhigh` | Sol/xhigh | `ROLE_OK review-pr-xhigh` |
| `implement-xhigh` | Sol/xhigh | `ROLE_OK implement-xhigh` |
| `core-xhigh` | Sol/max | `ROLE_OK core-xhigh` |
| `security-audit` | Sol/max | `ROLE_OK security-audit` |

결과: 등록·스폰·응답·정상 종료 10/10. probe 전후 Git 상태 동일, `git diff --check` exit 0. 단, `spawn_agent` 결과는 실제 backend model/effort telemetry를 노출하지 않으므로 model/effort는 TOML 파싱·라우팅 메타데이터로 검증했으며 런타임 과금/추론 telemetry 검증으로 확대 해석하지 않는다.

### ChatGPT 앱 검증 범위

- 공식 OpenAI 문서상 ChatGPT 데스크톱 앱 Codex 화면은 로컬 Codex Skill·설정·subagent 활동을 지원하며, `agents/openai.yaml`은 앱 Skill UI 메타데이터다.
- 로컬 설치본의 `agents/openai.yaml` 존재·YAML 파싱은 확인했다.
- 앱 UI 직접 확인은 Computer Use가 `com.openai.codex` 제어를 안전 정책으로 차단해 **not run**. 앱의 Skills 새로고침 후 목록 노출은 사용자 화면에서 확인이 필요하다.

## r8 전역 설치 계약·검증 (2026-09-03)

설치 안내가 Skill 복사에서 끝나지 않도록 `~/.codex/config.toml`, `~/.codex/AGENTS.md`, custom agents, 재시작, 검증 절차를 README·SKILL·Codex 어댑터에 필수 계약으로 추가했다. 기존 설정 파일은 전체 덮어쓰기 없이 필요한 키만 병합하도록 제한했다.

```text
python3 scripts/verify_global_install.py
PASS global effort-router installation
- CODEX_HOME: /Users/yong/.codex
- default: gpt-5.6-luna/max
- custom agents: 10/10
exit 0
```

추가 검증:

- 원본·설치본 `quick_validate.py` → 각각 exit 0, `Skill is valid!`
- `SKILL.md`, `README.md`, `platforms/codex.md`, `platforms/README.md`, 검증 스크립트의 원본↔설치본 diff → 차이 0건
- `git diff --check` → exit 0

## r9 Guide file 실패 원장 (2026-09-03)

사용자 지시에 따라 `AGENTS.md`, `CLAUDE.md`, `.cursorrules`를 주요 agent guide file로 명시하고, 관측·재현된 과거 실패 1건을 영구 예방 규칙 1줄로 바꾸는 누적 계약을 추가했다. 추측 규칙 금지, 기존 규칙 중복 금지, 전역/프로젝트 범위 분리를 함께 고정했다.

검증 결과:

- 실제 `~/.codex/AGENTS.md`에 「실패 기반 영구 예방 규칙」 병합 → 제목 1건, 핵심 규칙 1건
- `python3 scripts/verify_global_install.py` → exit 0, `PASS global effort-router installation`
- 원본·설치본 `quick_validate.py` → 각각 exit 0, `Skill is valid!`
- 수정된 원본↔설치본 diff → 차이 0건
- `git diff --check` → exit 0

## r10 워치독·GLM 동시성·과업 루트 계약 (2026-09-04)

ZCode(GLM 백엔드)·ChatGPT 앱(2026-07-09 명칭 통일)·Claude Code CLI+GLM 운용 피드백 반영. 이번 라운드부터 스킬 자체 계약(`docs/task-id/<task-id>/` 상태·②팬아웃 3렌즈 → 반려 → r2 수정안 → 재검토 통과 → ④리뷰 PASS)을 실전 적용했다(round.adversary 1/2, spawns 5).

추가 계약:

1. **§3 스폰 워치독** — 장기·비동기 스폰 10분 간격 점검, 연속 2회 무진행(무응답·진행 신호 부재) 시 정지 후 재스폰·역할 재분배(동일 역할 1회 한정, 초과 `phase: escalated` — 재스폰으로 round 예산 회복 금지). 독립 후속 스폰 대기 금지(병렬 유지는 경량·리컨으로). 정지 수단 없는 하니스는 종료 시한 사전 명시.
2. **§5 과업 루트** — `docs/task-id/<task-id>/state.json` + 저장소 `.gitignore`에 `docs/task-id/` 등록. worktree 격리 시 본체 저장소 경로 고정.
3. **GLM-5.3 동시성 상한(§6 단서)** — 심층(xhigh급) 스폰 동시 1. 팬아웃 렌즈는 직렬화·경량 병렬 치환. Flash 대체는 과업 단위(메인 모델 전환)로 한정 — 렌즈별 스폰 치환은 model override 금지로 불가. Flash 구간 산출물엔 GLM-5.3 교차검증(적대검토) 1건 이상.
4. **ChatGPT Classic 명칭** — 2026-07-09 데스크톱 앱 통일 반영(chat-app.md 노트·README 병기).
5. zcode·glm·codex·qwen·gemini·grok 파생 갱신 + SKILL.md 실패 표 2행·Output Contract 혼합 팬아웃 표기.

검증 결과:

- ②팬아웃(심층 general-purpose ×1 + 경량 Explore ×2 병렬 — 신규 동시성 규칙 선적용): 반려 3건 HIGH(§2 병렬 스폰 vs 상한 충돌·렌즈별 Flash 혼합 구조 불가·재스폰 예산 결함) 독립 확인 → r2 수정안 반영 → 재검토 1렌즈 통과(HIGH 잔존 0)
- ④리뷰: claims 1-8 verified(grep·git diff 헝크·check-ignore 채증) + 보존 제약 위반 0(§2·§5 예산·롤백 원문 무변경, 기존 .gitignore 항목 유지) + LOW 2건 → 반영
- `git diff --check` → exit 0
- 원본↔설치본(`~/.agents/skills/effort-router/`) diff → 차이 0건(books·.git 제외)

## r11 문서 산출 과제 적대검토 계약 (2026-09-04)

사용자 요구 반영: 설계·디자인 문서·계획 문서 생성 과제에 ②적대검토 필수. 기존 구멍 — ②가 "구현을 위한 ①계획"에만 연결돼 문서가 최종 산물인 과제는 검토 생략 경로가 열려 있었다.

추가 계약:

1. **§1 은닉 변수 '산출 문서'** — 다운스트림 구현을 지시하는 설계·디자인·계획 문서의 신규 작성·중대 개정(요구·범위·인터페이스 결정 변경)은 **L 고정 승격**('+1 티어' 규칙에 우선, 하향 예외·탐색적 판정 대상 아님).
2. **●●● '문서 산출 과제' 단락** — 계획 문서 = ①산출물 직접 ②적용. 설계·디자인 문서 = ①얇은 계획(심층 ①·Phase 분해는 ②초안 팬아웃 심층으로 대체) → ③초안(`plan-*` 명세 영역) → ②초안 팬아웃 → 수정(반려 시 수정 주체 = 초안 작성 스폰 재호출) → ④. 렌즈 해석(완전성=요구 누락·기술적 오류=내적 일관성·실행 가능성·위험=다운스트림 파급, XL +단순성·검증성), §3 대체 확인 수단→완전성 렌즈→④ claims 연결, 보안 설계 문서 교차검증.
3. **팬아웃 불가 하니스 폴백** — ChatGPT Work·Classic·OFF 어댑터는 메인 셀프 3렌즈 순차(`ON: 셀프 3렌즈 순차` 투명 표기). 셀프 순차는 '독립 확인' 요건 미충족 — 반려 확정은 사용자(상위 세션) 확인 한정.
4. 어댑터 파생 갱신: zcode·qwen·gemini·grok §1 행 + zcode 매핑표 ①·②행 비고 + grok ②행 폴백 + chat-app.md Work 폴백. glm·codex·README 무변경(본문 상속·화이트리스트 팬아웃 지원 근거).
5. 설치본 동기화 범위를 사본 2곳(~/.agents·~/.claude)로 확장 — ~/.claude에 r4 이전 구버전 잔존을 재검토 렌즈가 발견(§3 '기존 사본 2곳 동기화' 계약 이행).

검증 결과:

- ②팬아웃(심층 GP ×1 + 경량 Explore ×2): 3렌즈 반려 — HIGH 교차 확인(+1 메커니즘 구멍·팬아웃 불가 이행 불가·수정 주체·초안 역할 미정·파생 갱신 누락·심층 ① 충돌·~/.claude 구버전) → r2 수정안 → 재검토 1렌즈 통과(HIGH 0)
- ④리뷰: claims 6건 verified(grep 라인 채증) + 보존 제약 준수(§2·§5 원문·3렌즈 명칭·r10 계약 무변경, glm·codex·README 무변경 확인) + MEDIUM gap 2건(심각도 이중 정의·셀프 폴백 독립 확인) → 문구 보강 후 재리뷰
- `git diff --check` → exit 0
- 원본↔설치본 2곳 diff → 차이 0건(books·.git·.gitignore·docs 제외)

## 재현 절차

```bash
# 1. 과업 프롬프트 준비 (M티어 경계: 기능 추가, 2~5파일, 은닉 변수 포함)
# 2. 조건 A (baseline): 스킬 내용 없이 투입
# 3. 조건 B (green): SKILL.md 전문을 프롬프트에 주입해 투입
# 4. 응답에서 3개 지표 산출 (위 표 형식으로 본 문서에 추가)
```

## r8 Codex CLI Luna/Astra 단계별 라우팅 (2026-09-06)

현재 Codex 정책은 r7의 Sol 매핑을 대체한다. r7 런타임 기록은 당시 결과이며 새 매핑의 런타임 증거가 아니다.

- 모든 실무 실행·구현·수정·테스트: `gpt-5.6-luna / max` (XL 구현·임계경로 포함).
- 계획·명세 작성: `gpt-6-astra / medium`.
- 계획 검토·문제 판정·PR 리뷰·보안 감사: `gpt-6-astra / high`.
- 기존 role 이름은 유지한다. 접미사가 아닌 TOML의 모델·effort가 실제 매핑이다.
- 동일 접근 2회 실패 시 Astra/high 검토 → 필요 시 Astra/medium 재계획 → Luna/max 실행.

저장소 검증:

- `python3 scripts/test_codex_routing.py` → exit 0. 임시 설치에서 10개 role 통과, 변경된 8개 role 각각의 구 Sol 모델 거부 확인.
- `uv run --with pyyaml /Users/yong/.codex/skills/.system/skill-creator/scripts/quick_validate.py .` → exit 0, `Skill is valid!`.
- `git diff --check` → exit 0.

전역 설치·재시작·새 모델의 실제 role 스폰은 이 개정에서 수행하지 않았다. 설치 후 위 매핑으로 runtime protocol을 다시 실행해야 한다.

## r9 Codex 요금제 자동 분기 (2026-09-06)

- `scripts/configure_codex_plan.py`: 공식 app-server `account/read`로 로그인 요금제 조회. Plus 검토 medium, Pro 검토 high; 계획 medium·실무 Luna/max 유지.
- 기본은 읽기 전용. `--apply`에서 role TOML의 모델·effort만 반영하고 기존 파일 백업. 계정 전환 후 재적용 및 변경 시 Codex 재시작 필요.
- 자동 감지 불가·미지원 요금제는 exit 1. `--plan plus|pro`로 명시 가능. API 키에서 ChatGPT 요금제를 추정하지 않음.
- `verify_global_install.py`도 같은 요금제 매핑 사용. `--plan` 미지정 시 자동 조회.

검증 명령과 결과:

- `python3 scripts/test_plan_routing.py` → exit 0, 4 tests. Plus/Pro 왕복, 백업·사용자 설정 보존·멱등성, 읽기 전용, app-server handshake, Plus/Pro/API 키/미지원/null 계정, 타임아웃, 잘못된 TOML의 무변경 중단 검증.
- `python3 scripts/test_codex_routing.py` → exit 0, 1 test. Pro 설치 및 구 Sol 거부, Plus 적용 후 Plus 검증 통과·Pro 검증 거부.
- `python3 scripts/configure_codex_plan.py --agents-dir platforms/codex-agents` → exit 0. 실제 Codex CLI 0.153.0: `plan=pro`, `review_effort=high`, `source=account/read`, `changed_roles=[]`, `applied=false`.
- `uv run --with pyyaml /Users/yong/.codex/skills/.system/skill-creator/scripts/quick_validate.py .` → exit 0, `Skill is valid!`.
- `git diff --check` → exit 0.

Plus는 격리된 표본으로 검증했으며 실제 Plus 계정 로그인은 수행하지 않았다. 이번 작업에서 전역 설치나 실제 모델 role 스폰은 수행하지 않았다.
