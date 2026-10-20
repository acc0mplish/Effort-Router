# 변경 이력

새 것부터. 상세 검증 기록은 `TESTS.md`·`TESTS-GATES.md`·`TESTS-ARCHIVE.md` 원장 참조.

- **r43** (2026-10-20) — 워크트리 게이트 디스크 보고·부산물 회수: `create`·`list`·`sweep` 응답 최상위 `disk` 필드(free_gb·total_gb·low — 임계 기본 10GB·env `WORKTREE_MIN_FREE_GB`, 0=비활성화) · `sweep --artifacts-only` 배타 모드(가드 3중: 패턴 화이트리스트 ∧ check-ignore ∧ tracked 0 — tracked 1건으로 디렉터리 전체 보존) · create 자동 트리거(disk.low ∧ eligible 잔존 부산물 — active 무인 미접촉·예산 상한 후보 50/파일 200,000·컨테이너 artifacts-sweep.log 영수증)
- **r42** (2026-10-20) — 인테이크 계층(§0) 신설: 발화 6항목 신호 블록 — ① 결정론 엔진 `intake_gate.py`(hard/soft/advisory/context_dep/loop_pass 분류·규칙 0 긴급 면제·원문 보존) + ② jev 옵션 엔진 `intake` 모드(6항목 Noul fan-out·폴백) · Output Contract 인테이크 라인 · CLI 13종
- **r41** (2026-10-13) — 대시보드 프로젝트 필터 신설: `/api/projects` · `/api/tasks?project=` · 2세그먼트 번들(`/api/bundle/<project>/<folder>`) · Host·Sec-Fetch-Site 가드 · 심볼릭 링크 차단(nofollow lstat·`O_NOFOLLOW`) · `--workspace`(워크스페이스 전 프로젝트 탐색, 미지정 시 home 단일) + 사이드바 프로젝트 네비·`#/task/<project>/<folder>` 해시 라우팅 · 배포 G2 게이트 역방향 계약 수정(verify exit 0=통과 — 구 계약은 정상 설치에서 영원히 실패)
- **r39** (2026-10-12) — Asana 브라우저 에이전트 보고서 적용: Stagehand 러너 SDK 표면 수리(PR-0) · 토큰 사용량 수집기 `usage_log.py`(P1, 과업 폴더 `usage.jsonl`) · 게이트 토큰 상한 `--max-tokens`(P2) · 프리픽스 감사·모델 예산 조사 보고서(P3·P7, 정책 변경 없음). P4 실험 하네스는 예산 게이트 미충족으로 보류
- **r40** (2026-10-12) — 4케이스 재정비: 허용 조합 9개(Codex 3·Claude 3·GLM 3) 확정 · `gpt-6-luna / max` 상시 기본 · Claude `haiku` 코드 구현 전용·`sonnet` 임계경로 · Codex `review-pr-high` sol low · 전역 `config.toml` 루트 luna/max · ZCode·ChatGPT 어댑터 활성화 · 미사용 하니스 어댑터 qwen·gemini·grok 삭제 · 계약 테스트 `test_model_combos.py` · 배포 백업 스냅샷 동일 초 충돌 수정(mkdtemp, 회귀 테스트 `SnapshotCollisionTests`)
- **r39b** (2026-10-09) — 트리거 복구: description이 "Codex or ChatGPT task"로 한정돼 Claude Code 세션에서 스킬 미발동(실측 — 본문 §6은 Claude Code가 기준 하니스인데 트리거만 제한). description에 Claude Code 포함·과업 착수 전 발동 명시. 본문 계약 무변경 · 배포 samefile 가드(자기 복사 크래시 방지) · 배포 백업 스냅샷 동일 초 충돌 수정(mkdtemp 고유 디렉터리, 회귀 테스트 `SnapshotCollisionTests`)
- **r38** (2026-10-06) — S티어 최소 기록 계약: S 과업도 완료 시 `state.json` 1회 생성 → 대시보드에 전 과업 표시
- **r37** (2026-10-06) — 대시보드 시각 재구성: 원본 충실도 셸(사이드바+탑바)·3뷰 해시 라우팅(`#/` 목록 · `#/activity` 실행 현황 · `#/task/<folder>` 상세)·번들 마크다운 뷰어(`/api/bundle`)·탑바 시계·필터·정렬
- **r36** (2026-10-06) — **HTML 대시보드 신설** — `python3 scripts/dashboard_server.py` 기동 → **http://localhost:5777** 브라우저에서 과업 상태 열람 (읽기 전용·로컬 전용 바인딩·README 대시보드 절 참조)
- **r35** (2026-10-04) — 계약 개정 3건: phase `blocked`/`cancelled` 분리·착수 시 실행 상한 선언·후속 개선 채널
- **r34** (2026-10-02) — 근거 수준 분리: ①계획 번들에 확정/가정/미확정 3분 표기
- **r33** (2026-10-01) — deploy_global LOW 3건 수선 + TESTS 원장 3분할(본체/GATES/ARCHIVE)
- **r32** (2026-10-01) — `deploy_global.py` 1커맨드 통합 배포 + 역할 중복 근본 예방(백업 루트 이전·중복 탐지)
- **r31** (2026-09-30) — Codex 솔 high 단일화·심층 병렬 모드 전환 계약
- **r30** (2026-09-30) — 모델 전환: Codex GPT-6.1-Sol / Claude 역할 슬롯 소넷·오푸스(5.5) 통일
- **r29** (2026-09-30) — 루프 탈출 게이트(neverstuck): 동일 무브류 3회 실패 → 무장 판정 CLI·테스트 34케이스
- **r28** (2026-09-28) — 격리 가드: PreToolUse 훅 — 타 세션 claim 존재 시 전체 스테이징 커밋 차단
- **r27** (2026-09-28) — 트리 소유 게이트(tree_gate): 복수 세션 같은 저장소 작업 조율(claim/release/check/status/prune)
- **r26** (2026-09-25) — 검증 실행 엔진: 프로세스 그룹 제어·fresh-checkout 검증·증분 영수증
- **r25** (2026-09-25) — 게이트 경화: 워크트리 수렴 루프·phase 차단 / 검증핀 info/exclude 은닉 검출
- **r24** (2026-09-25) — 워크트리 수명주기 게이트(worktree_gate): 완료 시 강제 제거·salvage 보존·고아 sweep
- **r23** (2026-09-25) — 검증 핀 게이트(verify_pin): SHA 핀닝·검증 입력 분리·은닉 검출
- **r22** (2026-09-23) — Stagehand 게이트 계약 등재(SKILL 신규 절)
- **r21** (2026-09-23) — Stagehand 게이트 래퍼: 브라우저 실행 + jev 판정 조합 CLI
- **r20** (2026-09-22) — 잔존 후보 9건 수선
- **r19** (2026-09-22) — 심층 렌즈 병렬 상향 통로(사용자 명시 발화 트리거)
- **r18** (2026-09-22) — PR 분할 상한(직렬 체인 상한 5)·대기 시 행동 계약
- **r17** (2026-09-19) — 외부 하니스 메커니즘 차용: 무효화 전파·실행 패턴 어휘
- **jev** (2026-09-18) — 판단 계층 추가: CLI 12종(tier·prune·done·dup·loop·verify-run·watch·route·guard 등) + 프로젝트 후크 4종
- **r16** (2026-09-15) — 자율 연속 진행 개정 + 게이트·통제·기준선 L고정 프리셋·LOW 잔존 정리
- **r12~r15** (2026-09-11~13) — 원전 증류(반려 근거 주입·재스폰 진단·claim 충실성)·자기 적대검토·어댑터 동결·ops-supervisor 온디맨드
- **r7~r11** (2026-09-03~04) — Sol/Luna 라우팅·전역 설치 계약·Guide file 실패 원장·워치독·GLM 동시성 상한·문서 산출 과제 적대검토
- **r4~r6** (2026-09-03) — 결함 수정·발동조건 완화·리컨 병렬화·얇은 계획
- **r1~r3** (2026-09-03) — 스킬 착수: 티어 판정·화이트리스트 라우팅·상태계약·하니스 어댑터