# effort-router 게이트 검증 원장

r22~r28 게이트·선택 계층 과업의 원 요구·계약 요지·검증 기록 원장이다. r29에서 TESTS.md가 800줄 하드캡에 도달해 내용 무변경 순수 이동으로 분리했다(이동 무변경 입증 = C16 — 이동 전후 블록 `diff` 무차이). 방법론·프로토콜 원장은 TESTS.md에 잔존하며, 신규 게이트 과업 절은 본 파일 말미에 추가한다.

## r22 Stagehand 게이트 선택 실행 계층 등재 (2026-09-23)

원 요구 "jev 처럼 옵션으로 제공해" — 스킬 옵션 문서화로 확정. r21 게이트 래퍼(scripts/stagehand_gate.py 5종)를 SKILL.md 선택 계층으로 등재했다. 신규 절 '## 실행 계층(Stagehand 게이트) — 선택 실행 계층'(L107~148, 42줄) — jev 절 평행 볼드 라벨 구조, 필수 항목 8종 + 실경로 미검증 캐베. README r21 섹션 보강(venv 인터프리터·STAGEHAND_MODEL env·mock 키 조건·실경로 캐베·유출 면 확장).

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| 사용 시점 | 유료 계층 — 사용자 명시 기본, 메인 자율 활성화 시 고지 의무 |
| 폴백 | exit 2 = bypass · exit 3 = 상향 신호(최빈 원인 TYPESAFE 부재 — escalation_reason 먼저 확인) |
| 경제성 | 총 비용 상한 = (1+max_retries) × 스텝 수, 최악 6×50 = LLM 호출 300회 — 토큰 단위 제공자 청구 |
| 유출 면 | extract 수집 내용·act/observe 페이지 문맥 전부 외부 전송 — 태스크 제외가 유일 대체 경로(러너 env 삽입 미지원) |
| 실경로 | 미검증 캐베 — 러너 표면 vs SDK 4.1.0 공식 표면(Stagehand.create·model_api_key) 불일치 가능, 첫 실실행 소규모 수동 확인 |

검증 기록: ④리뷰(review-pr-xhigh 1스폰) **승인** — claims C1·C2·C5·C7·C8 verified, C6 부분(대조 반영 4건 확인 — 기록 매체 부재·404 URL은 LOW로 축소 수용), C3·C4 Phase 2 메인 검증(미러 6/6 diff 0·'## r22' 1매치). ② 라운드1 반려(HIGH 4: exit3 오라우팅·비용 상한 스텝 수 탈락·extract 유출면·실경로 무경고) → 수정 라운드(초안 작성 재호출·반려 근거 주입) → 재② 3렌즈 전부 approve → M1·M2(act/observe 유출 면·env 삽입 미지원) 메인 직접 보강 — ④ 실측 정합 확인. round 1/0, spawns 9. 커밋 위경: r21 스크립트 선커밋 후 문서 3파일 스테이징(plan §6 제약6)

## r23 검증 핀 게이트 — SHA 핀·검증 입력 분리·증거 기록 (2026-09-25)

원 요구 "우리프로젝트로 검증하고 모자라다 생각한거 가져와서 필요한거 구현해" — todo-flow 비교·적대검토에서 도출된 갭 3종(검증 자기참조 구멍 — 약화·삭제·untracked 신규 무력화 테스트가 재실행에 그대로 통과 / SHA 핀 부재 — 옛 검증으로 새 코드 통과 / 외부 효과 멱등 부재)의 대응. `scripts/verify_pin.py`·`scripts/test_verify_pin.py`(신규 2파일 — T1~T16 임시 git 저장소 fixture 전수) + SKILL.md 신규 절 '검증 핀 게이트(verify_pin)' + README '검증 핀 게이트 (r23)' 섹션.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| 핀 | 실행 시점 HEAD SHA 기록·`--expect-sha` 불일치 시 `sha_mismatch` — "옛 검증으로 새 코드" 기계 검출 |
| 검증 입력 분리 | diff(tracked — 커밋·staged·unstaged·삭제) ∪ untracked 패턴 통과분 → `verification_input_modified`, 다목적 설정(pyproject.toml·setup.cfg)은 `multipurpose_config_modified` 별도 발행(신호 순도 유지). 은닉 지정(`assume-unchanged`·`skip-worktree` — diff·status 마비 우회)은 `ls-files -v` 태그(h·S) 스캔으로 `verification_input_hidden` + `hidden_files` 발행 |
| 증거 기록 | `--save DIR` 결과 JSON(jev --save 계약 평행)·`--verify-cmd` exit code 동봉(재실행과 게이트 1호출 통합) |
| 플래그 2계층 | 재검증(sha_mismatch·verify_cmd_failed·verify_cmd_timeout — 게이트 재실행으로 소멸 확인) / 정당화(verification_input_modified·multipurpose_config_modified·verification_input_hidden — diff·은닉 확인+사유 기재, 은닉은 해제 후 재실행 권장) |
| 결정론 | git 호출 `-c core.autocrlf=false -c core.quotePath=false` 고정 — CRLF 정규화 위플래그·비ASCII 경로 C-인용(fnmatch 무력화) 경로 차단 |
| 종료코드 | exit 1 = 확인 의무 잔존(jev exit 1 폴백=진행과 정반대)·exit 2 = bypass(저장 실패만 stdout JSON 유지·`saved_to: null`)·exit 3 미사용(판단 계층이 없어 상향 경로 부재) |

검증 기록 (③구현 실측 — 명령 원문·exit code):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C1~C15 (T1~T15)·C16 (T1~T19 전 분기) | `python3 scripts/test_verify_pin.py` | exit 0 — Ran 19 tests, OK |
| C21 (T17 — ④ HIGH-2) | `python3 scripts/test_verify_pin.py VerifyPinCliTests.test_t17_non_ascii_paths_detected` | exit 0 — 비ASCII untracked 신규·tracked 수정 양쪽 modified_files 포함(quotePath 인용 우회 차단) |
| C22 (T18 — ④ HIGH-1) | `python3 scripts/test_verify_pin.py VerifyPinCliTests.test_t18_hidden_verification_input_flagged` | exit 0 — assume-unchanged·skip-worktree 은닉 시 `verification_input_hidden` ∧ hidden_files 포함 ∧ modified_files 비움(마비 실증) |
| C23 (T19 — ④ 재리뷰 HIGH) | `python3 scripts/test_verify_pin.py VerifyPinCliTests.test_t19_hidden_multipurpose_flagged` | exit 0 — skip-worktree + pyproject addopts 무력화 → `verification_input_hidden` 단독 플래그 ∧ hidden_files 포함 ∧ multipurpose_files 비움(라운드1의 완전 clean 우회 차단 실증) |
| C17 (H2) | `python3 docs/task-id/r23-verify-pin/check_structure.py` | exit 0 — PASS (SKILL 순수 삽입 +25줄·5단편 verbatim·README/TESTS 헤더) |
| C18 | `git diff --name-only 6674612 -- scripts/jev_judge.py scripts/jev_modes.py scripts/stagehand_gate.py scripts/stagehand_gate_policy.py scripts/stagehand_runner.py` | 빈 출력, exit 0 — 기존 스크립트 무변경 |
| C19 | `wc -l scripts/verify_pin.py scripts/test_verify_pin.py` | verify_pin.py 291·test_verify_pin.py 360 — 각 ≤650 ∧ README '### 검증 핀 게이트 (r23)'·TESTS '## r23' 헤더 존재(위 check_structure.py 동일 실행) |
| C20 | (메인 verify 단계) 설치본 2곳 `diff -q` | 메인 수행 — 미러 diff 0 목표 |

④리뷰 gap 2건(HIGH) 재구현 기록: G1 quotePath 비ASCII 인용 우회 → git 고정 플래그에 `-c core.quotePath=false` 추가(T17 실측 — 미적용 시 C-인용 출력이 fnmatch를 무력화해 clean 오판)·G2 assume-unchanged/skip-worktree 은닉 우회 → `git ls-files -v`(read-only) 태그 스캔 신규 플래그 `verification_input_hidden`(T18 실측 — diff·status 마비 상태에서도 검출. 앵커 시점에 테스트가 커밋돼 있어 인덱스==base인 실제 워크플로 기준 재현).

④ 재리뷰 라운드2 재구현 기록: G3 multipurpose 그룹 은닉 우회 → 은닉 매칭을 양 그룹 패턴 통합으로 확장(플래그 종수 불변 6종·hidden_files는 통합 목록. T19 실측 — skip-worktree + addopts 무력화가 라운드1에서 exit 0·완전 clean이던 것을 `verification_input_hidden` 단독 플래그로 검출)·G4 비UTF-8 파일명 디코드 → git·verify-cmd subprocess에 `errors='replace'`(엄격 디코드 크래시가 JSON 없는 exit 1 오분류되는 경로 수선). G3의 원인은 v3 계약 구멍이었다 — 은닉 매칭이 그룹 1 패턴에만 적용된 것은 구현이 v3 계약을 문자대로 준수한 결과며 번들 v4가 양 그룹 통합으로 계약을 수정했다.

구조 증명: SKILL.md +25/−0 순수 삽입(`git diff --numstat -- SKILL.md`) — check_structure.py가 기준선(git HEAD) 전 라인 보존까지 대조한다. SKILL §5 verify 정의("검증 전용 에이전트는 없다")는 유지 — verify_pin은 대체가 아니라 보강이다.

## r24 워크트리 수명주기 게이트 — 강제 제거·salvage 보존 (2026-09-25)

원 요구 "워크트리격리 작업완료시 제거를 강제해야될꺼 같은데 맨날 용량없음 씨발" — 반복 관측 실패(완료 후 worktree 잔존 → 디스크 고갈)의 영구 예방 장치. 기술적 원인 실측: 미포스 `git worktree remove`는 dirty(tracked 수정·staged)·untracked 존재 시 거부 — 수동 제거 반복 실패 경로. `scripts/worktree_gate.py`·`scripts/worktree_gate_lib.py`(공용 git 계층 — 650줄 분할)·`scripts/test_worktree_gate.py`(신규 3파일 — T1~T34 임시 git 저장소 fixture 전수) + SKILL.md 신규 절 '워크트리 수명주기 게이트(worktree_gate)' + README '워크트리 수명주기 게이트 (r24)' 섹션.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| 강제 제거 | done 7단계 기계 절차 — salvage(필요 시) → `remove --force` → prune → 기록. 판정 없음, done 판정 권한은 메인(state.json phase=done 패치 후 호출); phase≠done 활성 과업 done은 exit 2 차단(r25) |
| salvage 무손실 | 미커밋분(tracked 수정·staged·untracked 비ignored)만 `add -A` + 커밋 보존 — porcelain은 ignored를 제외하므로 공백 ⇔ salvage 불필요가 정확히 일치(빈 salvage 커밋 미생성). ignored는 폐기 대상. `--no-salvage`는 폐기 수 기록의 명시 옵션(done 전용). done은 salvage 후 재판정 3라운드로 동시 작성을 감지한다(지속 시 salvage 현황 부분 JSON 후 exit 2 보존 — 극소 경합 창 잔존, r25 정정) |
| 실행 환경 독립성 | identity 폴백 `-c user.name=worktree-gate -c user.email=worktree-gate@local`(미정의 환경 fatal 차단)·`commit --no-verify`(pre-commit hook 차단 차단) — 어떤 로컬 환경에서도 salvage 성립 |
| 브랜치 보존 | 제거 후에도 커밋 도달 가능(오브젝트 공유 실측) — 기본 보존, `--drop-branch`는 tip SHA 기록 후 삭제하는 명시 옵션 |
| --unmanaged 명시 | 미관리(수동·기존 잔존분) 제거는 명시 옵션뿐(기본 off·자동 금지) — salvage는 `salvage/unmanaged-*` 브랜치에 적립, 원본 브랜치 포인터 무변경 |
| sweep 자격 | managed 전제로 `phase=="done"` 리터럴 ∨ 고아(과업 폴더 소실 — 명명규칙 재구성). 폴더 존재·state.json 파손은 고아 아님 → 보존. 활성·불일치·미관리는 보고만. 본체 작업 트리 상시 제외. 자동(비dry) sweep은 사용자 명시 시만 |
| exit 1 attention | `salvage_committed`·`removable_worktrees_present`·`worktree_missing` — 확인 의무(jev exit 1 폴백=진행과 정반대, verify_pin과 동일 어휘). 셸 체인은 rc 확인 패턴(README) |
| 폴백 exit 2 | 비저장소·무효 task-id·무효 ref·중복 create·잔존 브랜치·대상 전부 부재 done·locked·remove 실패 — stderr `FAIL worktree gate: <사유>`. exit 3 미사용(판단 계층 부재) |

검증 기록 (③구현 실측 — 명령 원문·exit code. 기입 시점: ③ = C1~C23·C25~C36, 메인 verify = C24 미러):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C1~C19·C25~C36 (T1~T31)·C20 (전체) | `python3 scripts/test_worktree_gate.py` | exit 0 — Ran 34 tests, OK(T32~T33 라운드1 가드·T34 라운드2 M1). RED 선실증: worktree_gate.py 부재 시점 동일 스위트 34 failures(r25 M5 정정 — 오기) |
| 라운드2 M1 (T34) | `python3 scripts/test_worktree_gate.py WorktreeGateTests.test_t34_done_drop_branch_on_leftover_keeps_tip` | exit 0 — 잔존 경로 done --drop-branch에서 tip을 삭제 전 판독: JSON branch.tip_sha·레지스트리 dropped_branch_tip non-null ∧ 브랜치 소멸(C10 순서 계약과 정합) |
| 라운드1 G1·G2 (T32·T33) | `python3 scripts/test_worktree_gate.py WorktreeGateTests.test_t32_done_after_completion_ignores_reappeared_dir` / `...test_t33_done_no_salvage_on_leftover` | 둘 다 exit 0 — 완료 과업 재등장 디렉터리는 멱등 유지·미삭제 ∧ 잔존 경로 --no-salvage는 신규 파일 미커밋·폐기 수 기록·1차 salvage SHA 레지스트리 기록 |
| C7 (T7 대표) | `python3 scripts/test_worktree_gate.py WorktreeGateTests.test_t7_done_salvage_tracked` | exit 0 — tracked 수정 salvage 커밋·`salvage.files` 포함·`git show wt/t-a:<파일>` 내용 일치·디렉터리 소멸 |
| C26 (T21 — H2) | `python3 scripts/test_worktree_gate.py WorktreeGateTests.test_t21_done_identity_fallback` | exit 0 — identity 미정의 환경에서 salvage 커밋 author/committer = `worktree-gate <worktree-gate@local>` |
| C29 (T24 — R2 수렴) | `python3 scripts/test_worktree_gate.py WorktreeGateTests.test_t24_done_remove_failure_converges` | exit 0 — remove 실패(쓰기금지 chmod) exit 2 → 권한 회복 후 재 done exit 0 ∧ salvage 커밋 정확히 1개(2중 커밋 없음) |
| C31 (T26) | `python3 scripts/test_worktree_gate.py WorktreeGateTests.test_t26_sweep_drop_branch` | exit 0 — swept 브랜치 소멸 ∧ JSON tip SHA 기록 |
| C35 (T30 — H1) | `python3 scripts/test_worktree_gate.py WorktreeGateTests.test_t30_sweep_unmanaged_salvage_branch` | exit 0 — 수동 worktree 제거 ∧ `salvage/unmanaged-*` 브랜치에 미커밋분 적립 ∧ 원본 브랜치 포인터 무변경 |
| C21 | `python3 docs/task-id/r24-worktree-gate/check_structure.py` | exit 0 — PASS (SKILL 순수 삽입 +28줄·3단편 verbatim·README/TESTS 헤더) |
| C22 | `git diff --name-only 3a12a43 -- scripts/jev_judge.py scripts/jev_modes.py scripts/stagehand_gate.py scripts/stagehand_gate_policy.py scripts/stagehand_runner.py scripts/verify_pin.py` | 빈 출력, exit 0 — 기존 스크립트 무변경 |
| C23 | `wc -l scripts/worktree_gate.py scripts/worktree_gate_lib.py scripts/test_worktree_gate.py` | 374·404·605(r25 M5 정정 — 오기) — 각 ≤650 ∧ README '### 워크트리 수명주기 게이트 (r24)'·TESTS '## r24' 헤더 존재(위 check_structure.py 동일 실행) |
| C24 | (메인 verify 단계) 설치본 2곳 `diff -q` | 메인 수행 — 게이트 3파일 미러 diff 0 목표 |

구현 실측 정정(번들 가정 대비): `git worktree remove --force` 실패 시(실측 — 임시 저장소 chmod 555, remove rc 255) git은 **admin 메타데이터를 제거하고 디렉터리만 남긴다** — 번들 §5 done 2단계의 "재판정 후 재 remove" 가정과 달라진다. 이에 잔존 수렴 경로를 구현했다: porcelain 부재 ∧ 레지스트리 활성 ∧ 브랜치 앵커 존재 ∧ 레지스트리 path 디렉터리 잔존이면, 임시 인덱스(read-tree tip → add -A → diff-index --cached — oid 비교라 stat 오탐 없음, 본체 인덱스 비접촉)로 미커밋분 재판정 후 commit-tree·update-ref로 salvage 적립하고 잔존 디렉터리를 rmtree로 마무리한다(C29 exit 0 수렴 — T24 실측). 브랜치 앵커가 없으면 진입하지 않는다(attention 보존 — fail-closed). rmtree·update-ref는 이 수렴 경로 한정이며 게이트의 일상 파기 수단이 아니다.

구조 증명: SKILL.md +28/−0 순수 삽입(기준선 3a12a43) — check_structure.py가 기준선 전 라인 보존까지 대조한다. SKILL §5 worktree 경로 고정·state writer 원칙은 유지 — 게이트는 state.json을 읽기만 하고 레지스트리 worktree.json만 쓴다.

라운드1 재구현 기록 (④ 수정요청 경증 — gap 4건): G1 잔존 수렴 진입 가드 보강 — 활성 레지스트리(done_utc 없음)·정규 명명 경로(레지스트리 path == 컨테이너/<task-id>)·브랜치 앵커 3중 조건으로 좁혀 완료 과업의 재등장 디렉터리는 멱등(already_removed)을 유지하고 레지스트리 path 변조의 임의 경로 rmtree를 차단(T32 실측)·G2 --no-salvage를 잔존 경로에도 전달 — 재판정은 임시 인덱스로 폐기 수만 판독(commit=False)하고 커밋하지 않는다(T33 실측)·G3 discard_leftover_dir의 rmtree OSError를 exit 2(사유)로 변환 — traceback+exit 1의 의미 충돌 제거·G4 문서 정정 — TESTS "+30→+28" 2곳·README exit 2 행에 --save 실패 예외(stdout JSON 후 exit 2) 명시·sweep --drop-branch 도움말에 "미관리 원본 브랜치는 삭제하지 않는다" 교정. LOW-6 동반 수선: 순수 수렴(재판정 공백) 시 레지스트리 salvage_commit에 1차 실패 당시 salvage SHA를 기록(log --grep=^salvage( 조회 — T33 후단 실측).

마이크로 수정 기록 (④ 재리뷰 종결 전 M1·니트 2건): M1 잔존 경로 --drop-branch의 tip 판독을 branch -D 실행 전으로 이동(정상 경로와 동일 순서 — 삭제 후 복구는 fsck --lost-found까지 단절되는 순서 위반 수선, T34 실측)·니트 잔존 경로 --no-salvage의 skipped_by_option을 폐기 수 0이어도 True로 통일(정상 경로와의 불일치 제거 — perform_salvage_leftover의 commit=False 분기를 files 공백 판정 앞으로 이동)·니트 README "기타 한정" 테스트 범위 표기 T1~T31 → T1~T34.


## r25 게이트 경화 — 적대검토 결함 수선 (2026-09-25)

원 요구 "ㄱㄱㄸ" — r23(verify_pin)·r24(worktree_gate) 사후 적대검토에서 확정된 결함 수선(HIGH 4·MEDIUM 5·LOW 판단 6·②반려 RC-1·RH 4). `scripts/verify_pin.py`(ignore 은닉 검출·기본 패턴 8종)·`scripts/worktree_gate.py`+`worktree_gate_lib.py`(동시 작성 감지 루프·phase·경로 가드·부분 결과 보존·-z 파싱)·테스트 2건 경화 + 신규 `scripts/test_worktree_gate_hardening.py`(T35~T44) + SKILL·README·TESTS 계약 정정.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| ignore 은닉 검출(H4·RC-1) | untracked∧ignored(.gitignore·.git/info/exclude·전역 excludesFile) 검증 입력·다목적 파일 → `verification_input_ignore_hidden` + `ignore_hidden_files`(무제외 스캔 차집합·base 무관 상시). 매칭은 전체경로 한정 — 의존성 트리 내부 test 파일 basename 오탐 방지(본 저장소 18파일 실측). 원인 파일은 `git check-ignore -v`로 확인 |
| 동시 작성 감지(H3·V5·RH-2) | done은 salvage 후 재판정 3라운드 — 잔존 변경이면 재 salvage, 지속 시 salvage 현황 부분 JSON(stdout) 후 exit 2 보존 중단. daemon writer는 프로세스 정지 후 재실행이 유일한 정상 탈출(`--no-salvage`는 활성 작성분 폐기 각오 비상구). '0손실'은 작성 정지 상태 전제(극소 경합 창 문서화) |
| 유도법 전환(H1) | remove 실패 유도를 chmod에서 PATH git 심으로 — FS 무관(ext4·DrvFs 동일 실측)·root 무의존. WORKTREE_GATE_TEST_ROOT DrvFs 실행으로 잔존 수렴 엔진 실증 |
| 호스트 오염 방어(H2)·머신 의존 차단(RH-1) | fixture 루트가 git 저장소 내부면 setUp에서 전 테스트 fail(오염 전 차단). fixture env는 파일 기반 전역 config도 격리(GIT_CONFIG_GLOBAL·GIT_CONFIG_SYSTEM=/dev/null·XDG_CONFIG_HOME 전환) — 테스트가 머신 gitignore와 무관 |
| done 사전 차단(M1·M2·V7) | 명명규칙 경로 일치(레지스트리 유무 무관)·state.json phase≠done → exit 2(레지스트리 소실+활성 phase 혼합 포함 — phase 패치 주체는 메인) |
| 감사 보존(M3·V5) | 제거 성공 후 기록 단계 실패·동시 작성 중단 모두 부분 결과 stdout JSON 후 exit 2 |
| 완전 차단 아님(M4) | verify_pin은 약화 가능성을 기계 노출로 전환 — 공모 약화 해제는 사유 기재, 감시 자동화 없음(호출 시점 1회) |

검증 기록 (③구현 실측 — 명령 원문·exit code):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C1 | `python3 scripts/test_verify_pin.py` | exit 0 — Ran 23 tests, OK(기존 T1~T19 무수정 통과 + 신규 T20~T23) |
| C2 | `python3 scripts/test_verify_pin.py VerifyPinCliTests.test_t20_info_exclude_ignore_hidden_flagged` | exit 0 — .git/info/exclude 등록 + untracked conftest.py 공격에서 exit 1 ∧ `verification_input_ignore_hidden` ∧ `ignore_hidden_files==['conftest.py']` ∧ base 미지정 변형도 동일 검출(not_evaluated·상시 스캔). 구 게이트는 exit 0·flags [] 무검출(H4) |
| C3 | `python3 scripts/test_verify_pin.py VerifyPinCliTests.test_t22_ignored_non_verification_stays_clean` | exit 0 — ignore된 비검증입력 untracked + venv 의존성 트리 내부 `tests/test_dep.py`(basename은 `test_*.py`와 일치) 모두 무신호 — 오탐 0(전체경로 한정 실증, RC-1) |
| C4 | `python3 scripts/test_verify_pin.py VerifyPinCliTests.test_t23_global_config_isolation_and_detection` | exit 0 — 격리 env에서 fixture 전역 config 미적용(conftest.py가 정상 modified 경로로 검출) ∧ `GIT_CONFIG_GLOBAL` 경유 전역 excludesFile 등록 시 `verification_input_ignore_hidden` 검출(RH-1 양방향) |
| C5 | `python3 scripts/test_worktree_gate.py` | exit 0 — Ran 34 tests, OK(T24·T33·T34 PATH 심 전환 포함·root skip 제거) |
| C6 | `mkdir -p /mnt/d/tmp/wgate-r25 && WORKTREE_GATE_TEST_ROOT=/mnt/d/tmp/wgate-r25 python3 scripts/test_worktree_gate.py` ∧ 동일 env `python3 scripts/test_worktree_gate_hardening.py` | 각 exit 0 — Ran 34 tests, OK(76.2s) ∧ Ran 10 tests, OK(41.6s). chmod 유도 시점 DrvFs 실패 4/34 → 0(H1 해소 — 심 유도·잔존 수렴 엔진 DrvFs 실증) |
| C7 | `python3 scripts/worktree_gate.py list`(본 저장소 cwd) | exit 0 ∧ `summary.total==0` ∧ entries [](자기적용 스모크 — 잔존 0) |
| C8 | `python3 scripts/verify_pin.py --base 0588175 --verify-cmd 'python3 scripts/test_worktree_gate.py'` | exit 1 ∧ flags `verification_input_modified`(변경 `scripts/test_verify_pin.py`) ∧ `verify_cmd.exit_code==0` ∧ `verification_input.ignore_hidden_files==[]`(RC-1 전체경로 매칭으로 venv 18파일 오탐 해소 실증) |
| C9 | `wc -l scripts/verify_pin.py scripts/test_verify_pin.py scripts/worktree_gate.py scripts/worktree_gate_lib.py scripts/test_worktree_gate.py scripts/test_worktree_gate_hardening.py` | 326·474·493·502·650·352 — 각 ≤650 |
| C10 | `git diff --name-only 0588175 -- scripts/jev_judge.py … test_plan_routing.py`(13파일) | 빈 출력, exit 0 — 기존 스크립트 무변경 |
| C11 | `git diff 0588175 -- scripts/test_verify_pin.py \| grep -c '^-.*def test_t'` | 출력 0 — 기존 테스트 메서드 정의 무삭제 |
| C16 | `git diff 0588175 -- scripts/test_worktree_gate.py \| grep -c '^-.*def test_t'` | 출력 0 — 기존 테스트 메서드 정의 무삭제·diff hunk는 §3 허용 편집 5종(심 전환·root skip 제거·setUp 가드·심 헬퍼 공개·독스트링+clean_env 격리) |
| C15 | RED 선실증: `python3 scripts/test_verify_pin.py` → exit 1 — Ran 23 tests, FAILED(failures=3, errors=1 — T20 FAIL·T21 FAIL·T22 ERROR·T23 FAIL) ∧ `python3 scripts/test_worktree_gate_hardening.py` → exit 1 — Ran 10 tests, FAILED(failures=8, errors=1 — T36~T44 전부, T35는 인프라 단계 GREEN으로 실패 목록 부재) | 기록 완료 |

L6 DrvFs 지연 기록(양측 실측 — 같은 머신 WSL2): test_worktree_gate.py ext4 10.7s vs DrvFs 76.2s(약 7배)·test_worktree_gate_hardening.py ext4 7.6s vs DrvFs 41.6s(약 5배) — 번들 R8 예상(~8배)과 정합. 일상 실행은 /tmp(ext4) 기본, DrvFs는 H1 실증용 일회 검증이다.


## r26 게이트 강화 — 실행 엔진 4기능 (2026-09-25)

원 요구 — todo-flow(JakeB-5, v0.0.4) 적대검토에서 도출된 verify_pin 게이트 결함 4종 수선: ①프로세스 그룹 제어 없음 ②verify-cmd 전후 클린 검사 없음 ③fresh-checkout 검증 모드 없음 ④증분 영수증 없음. `scripts/verify_exec.py`(신규 실행 엔진 — capability probe·프로세스 그룹·verify-window·fresh 절차)·`scripts/verify_pin.py`(리와이어 — 신규 플래그 3종·--fresh-checkout·ReceiptWriter)·`scripts/test_verify_exec.py`(신규 T24~T42) + SKILL·README·TESTS 계약 등재. 기존 플래그 7종·exit 코드·`test_verify_pin.py`(T1~T23) 무변경 보존.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| 프로세스 그룹 제어 | 검증명령은 `start_new_session` 그룹 실행 — 타임아웃·정상 종료 뒤 SIGTERM→1.5s pgid 폴링→SIGKILL→드레인→2s 폴링 전멸(todo-flow verification.py 원형 어휘 이식). 잔존 관측은 `verify_cmd_survivors`(재검증 계층 — 프로세스 정지 후 재실행으로 소멸 확인). **같은 pgid 잔류 자손 한정** — setsid 이탈은 범위 밖(계약 한계 문서화). 실행 중 ps 실패는 exit 2(생존자 판정 불능 — 조용한 통과 금지) |
| 파이프 상속 orphan 판별 | communicate 타임아웃 시 poll()로 직속 자식 종료 여부 판별 — (a) 미종료=진성 타임아웃·(b) 이미 종료=파이프 잡은 orphan(타임아웃 오분류 금지·survivors로 정확 분류). 그룹 사멸 후 드레인 순서 강제로 P6 교착 제거, 드레인 타임아웃 시 fd close+wait 회수 |
| 실행창 전후 클린 검사 | verify-cmd 실행 직전 HEAD·porcelain -z -uall·info/exclude 스냅샷→직후 재판정. HEAD 이동=`head_moved_during_verify`·tracked 변형·exclude 변화·검증입력 패턴 매칭 untracked=`verify_workspace_mutated`(정당화 계층 — 1회성 사건, 재실행 소멸≠해제). 패턴 밖 untracked(산출물)는 델타 상세에만 기록 — 오탐 없음(메인 승인 트레이드오프) |
| fresh-checkout 검증 | --fresh-checkout(--verify-cmd 필수, 단독 exit 2) — r24 이름 충돌 가드(`wt/verify-pin-fresh`·`docs/task-id/verify-pin-fresh/` 사전 거부)→잔존 복구→`worktree add --detach <시작 HEAD>`→cwd=fresh 검증→`remove --force`+`prune`. remove 실패는 부분 결과 stdout JSON 1회 후 exit 2(r24 M3 패턴). 커밋 트리 한정·은닉 플래그는 메인 스캔에서 여전히 발행·fresh 잔존은 fresh 재실행으로만 정리(r24 sweep detached 스킵) |
| 증분 영수증 | --save 시 단계(init→inspected→fresh_checkout→verify_cmd→complete)마다 tmp+fsync+os.replace 원자 재기록 — 크래시 시 마지막 성공 stage 보존. 실패 종료 시 강제 기록 없음(최종 stdout이 사유 운반), 중간 기록 실패는 검사 계속·최종 저장까지 실패 시 exit 2 합류. stdout 최종 JSON은 stage 키 없음 |

검증 기록 (③구현 실측 — 명령 원문·exit code):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C1 | `python3 scripts/test_verify_pin.py` ∧ `git diff c75dcb7 -- scripts/test_verify_pin.py` | exit 0 — Ran 23 tests, OK ∧ diff 빈 출력(무변경) |
| C2·C2b·C3 | `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t24_background_writer_survivors_detected` · `...test_t25_timeout_kills_sigterm_ignoring_grandchild` · `...test_t26_pipe_holding_orphan_finite_exit_and_classification` | 각 exit 0 — T24 생존자 감지+late-write 마커 부재·T25 타임아웃 손자(SIGTERM 무시) SIGKILL 종료+마커 부재+survivors false(독립 축)·T26 파이프 상속 orphan 유한 종료(duration<15s)+exit_code 0+타임아웃 오분류 없음 |
| C2c | `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t33_ps_failure_midrun_exit2` | exit 0 — exit 1 ps 심(PATH)에서 게이트 exit 2·stderr `FAIL verify pin`·생존자 사유·stdout 없음(조용한 통과 금지) |
| C4·C5·C6·C7 | `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t28_head_moved_during_verify` · `...test_t29_tracked_mutation_during_verify` · `...test_t30_untracked_verification_input_new_during_verify` · `...test_t31_non_pattern_artifacts_no_false_flag` | 각 exit 0 — HEAD 이동·tracked 변형·conftest 신규 검출, 패턴 밖 .pytest_cache 생성은 무플래그 exit 0(델타 상세에는 기록) |
| C5b | `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t39_fresh_main_tracked_mutation_detected` | exit 0 — verify-cmd cwd=fresh여도 실행 중 메인 tracked 변형 검출(`verify_workspace_mutated`) ∧ fresh.removed true |
| C8·C8b | `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t34_fresh_basic_flow_reflects_commit_only` · `...test_t38_fresh_without_verify_cmd_exit2` | 각 exit 0 — dirty 메인에서 fresh는 커밋 내용만 반영·종료 후 worktree·`.git/worktrees`·컨테이너 소멸·exit 0 ∧ fresh 단독 exit 2 |
| C9·C10·C10b·C11 | `...test_t35_fresh_neutralizes_hidden_untracked` · `...test_t36_fresh_leftover_recovery` · `...test_t40_fresh_name_collision_guard` · `...test_t37_fresh_remove_failure_partial_result` | 각 exit 0 — exclude 은닉 untracked가 fresh 검증에 부재(exit_code 0)·은닉 플래그는 여전히 발행 ∧ 등록·미등록 잔존 복구(leftovers_cleaned 기록) ∧ 브랜치·task-id 디렉터리 양변형 exit 2+잔존 미진입 증명 ∧ remove 심 실패 시 stdout JSON 1회(`fresh.removed` false·`incomplete_step` worktree_remove) 후 exit 2 |
| C12·C13 | `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t41_receipt_survives_sigkill_midrun` · `...test_t42_receipt_complete_matches_stdout` | 각 exit 0 — SIGKILL 후 영수증 잔존·파싱·stage(inspected/fresh_checkout)·head_sha 보존·fresh 크래시 시 잔여 worktree 시사 ∧ 정상 종료 stage complete+stdout JSON과 키 일치(stage 제외) |
| C14 | `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t27_no_ps_fallback_transparent` | exit 0 — PATH에서 ps 제거 시 `process_group: false`·`survivors` null·성공·타임아웃 플래그 기존 동작 불변 |
| C15 | `wc -l scripts/verify_pin.py scripts/verify_exec.py scripts/test_verify_exec.py scripts/test_verify_pin.py` | 444·418·508·474 — 각 ≤650 |
| C16 | `python3 scripts/test_verify_exec.py` | exit 0 — Ran 19 tests, OK(T24~T42 전수) |
| C17 | `git diff c75dcb7 -- scripts/test_verify_pin.py scripts/worktree_gate.py scripts/worktree_gate_lib.py scripts/test_worktree_gate.py scripts/test_worktree_gate_hardening.py` | 빈 출력 — 무변경 대상 5파일 보존 |
| C18 | `python3 scripts/verify_pin.py --base c75dcb7 --verify-cmd 'python3 scripts/test_verify_pin.py' --fresh-checkout` | exit 1 ∧ flags `['verification_input_modified']`(구현 산출물 — 검증 입력 변경 보고: test_verify_exec.py 신규 작성) ∧ verify_cmd.exit_code 0 ∧ fresh.removed true |
| C19 | `diff -q ~/.claude/skills/effort-router/<경로> <저장소>/<경로>` ∧ 동일 for `~/.codex/...` — 6종×2미러 | **초회 실측 불일치 — ③구현이 미러 복사를 TESTS.md r26절 작성보다 먼저 수행해 양 미러 TESTS.md가 r25 구본이었다(④리뷰 적발·메인 재실측 FAIL). 메인 재동기화 후 12/12 일치 — 리뷰 갭 수선으로 정정 기록. 복사는 저장소 변경 완료 후 마지막 1회로 순서 고정** |
| RED 선실증 | Phase 1: `python3 scripts/test_verify_exec.py` → exit 1 — Ran 10 tests, FAILED(failures=6, errors=4 — 신규 키 KeyError·플래그 부재·T33 exit 0 조용한 통과) / Phase 2: exit 1 — Ran 17 tests, FAILED(failures=6, errors=1 — --fresh-checkout unrecognized) / Phase 3: exit 1 — Ran 19 tests, FAILED(failures=1, errors=1 — stage 키 부재·폴링 타임아웃) | 기록 완료 |
| 리뷰 HIGH 수선 — legacy 폴백 cwd | 메인 재현 시나리오(ps 제거 PATH 심만 + dirty 메인 + `--verify-cmd '/bin/cat ver.txt' --fresh-checkout`)에서 `python3 scripts/test_verify_exec.py VerifyExecEngineTests.test_t27b_fresh_legacy_fallback_runs_in_fresh_checkout` → 수선 전 exit 1 — `AssertionError: 'dirty\n' != 'committed\n'` RED 재현 / 수선 후 exit 0 — stdout_tail `committed` ∧ fresh.used true ∧ process_group false ∧ 메인 ver.txt dirty 유지 | 기록 완료 |
| 리뷰 LOW 3건 수선 | `python3 scripts/test_verify_exec.py` → exit 0 — Ran 20 tests, OK(T27b 포함) ∧ `python3 scripts/test_verify_pin.py` → exit 0 — Ran 23 tests, OK. ①fresh_epilogue의 main_toplevel try 밖 평가 → prologue가 repo 루트 반환·epilogue 재평가 제거 ②TimeoutExpired 경로 group_killed 하드코딩 → 그룹 소멸 확인 시만 True(실측 group_dead) ③main() 65줄 → write_stage·execute_verify_window·finish_receipt 분해로 49줄(<50) | 기록 완료 |


## r27 트리 소유 게이트 — 병렬 세션 조율 (2026-09-28)

원 요구 — 재발 방지 프로토콜 1번 "트리 소유 claim: 작업 시작 전 세션id·경로·스코프·시각 기록… 살아있는 타 세션 claim 발견 시 → 읽기전용 or 신규 worktree 스폰". 관측 실패(타 머신 병렬 세션 워크트리 간섭 — 기록자 불명 변경을 추정만으로 revert)의 두 층위(조율 장치 부재·근거 없는 추정 행동)를 `scripts/tree_gate.py`(신규 — claim·release·check·status·prune 5서브커맨드)·`scripts/test_tree_gate.py`(신규 T1~T20+T8b)·SKILL·README·AGENTS·SessionStart 훅(`.claude/hooks/tree_claim_hook.py` + settings 엔트리)으로 봉쇄한다. 기존 4 게이트·기존 문서 절 구조 무변경 보존.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| claim 단위·레지스트리 | (트리, 세션) 조합이 claim 단위. 레지스트리 `$(git rev-parse --git-common-dir)/effort-router-tree-claims/`(워크트리 간 공유·비관리·커밋 대상 아님)·파일명 `<tree-hash16>-<session-sanitized>.json`·session-id 검증과 sanitize 절단 상한 64자 통일(파일명 충돌·타 세션 파일 오제거 경로 원천 차단)·원자 쓰기(temp+fsync+os.replace)·release는 제거 전 레코드 session_id 대조(불일치·파손 거부) |
| alive·stale 판정 | alive = (같은 hostname ∧ pid 생존) ∨ updated_utc TTL 이내 — 기준은 **updated_utc**(heartbeat가 리셋)·claimed_utc 최초 고정. pid 생존 `os.kill(pid,0)`(ProcessLookupError=사망·PermissionError=생존)·비POSIX·호스트 상이·pid 미전달은 `pid_check: "unsupported"` 표기 후 TTL 의존. 판정은 보수 방향(오판 비용 = 확인 1회)·파손 claim은 corrupt 보고 + alive 보수 취급(prune 대상 제외)·prune은 stale만 제거(stale = TTL 초과 ∧ pid 생존 아님 — alive 불가침) |
| exit 어휘·플래그 | 0 완료·1 attention(**claim은 기록 수행 후 주의** — jev exit 1 폴백과 정반대)·2 config/env/git 오류(stderr `FAIL tree gate:`·--save 실패만 stdout JSON saved_to null 보존)·3 미사용. 플래그 2종 — `foreign_claim_present`(claim·check)·`stale_claims_present`(status) |
| stdout 응답 | 단일 JSON 객체(exit 2는 stdout 없음) — `ok` = 절차 수행 성공(**exit 1도 ok: true** — 경고는 flags·세부 배열로 전달)·`alive_reason`(pid·ttl)·`pid_check` 투명 표기 |
| SessionStart 훅 | stdin JSON session_id → `tree_gate.py check --session <id>` subprocess — foreign claim 시 additionalContext 경고(상대 session_id·scope·alive 근거 + 판정 권한은 메인 안내). **항상 exit 0**(세션 시작 차단 없음)·게이트 부재·비저장소·오류 시 무작동·무출력·jev·TYPESAFE_API_KEY 무의존(결정론) |
| AGENTS 원장 1줄 | 기록자 불명 변경 revert·커밋 금지 → `scripts/tree_gate.py check`로 소유 claim 확인 먼저(추정 revert 사건의 행동 차단) |

검증 기록 (③구현 실측 — 명령 원문·exit code):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C4 RED 선실증 | `python3 scripts/test_tree_gate.py`(tree_gate.py·훅 부재) | exit 1 — Ran 21 tests, FAILED (failures=21) — subprocess CLI 실행 방식으로 수집 단계 통과 후 전량 실패 |
| C1 2단계 GREEN | Phase 1 직후 `python3 scripts/test_tree_gate.py` / Phase 2 직후 동일 | Phase 1: exit 1 — FAILED (failures=2 — T19·T20만, 훅 미구현 RED 유지) / Phase 2: exit 0 — Ran 21 tests, OK(훅 케이스 포함 전량) |
| C2 회귀 | `python3 scripts/test_worktree_gate.py` ∧ `test_worktree_gate_hardening.py` ∧ `test_verify_pin.py` ∧ `test_verify_exec.py` ∧ `test_jev_judge.py` ∧ `test_jev_modes.py` ∧ `test_jev_modes_extra.py` ∧ `test_stagehand_gate.py` | 각 exit 0 — OK(기존 4 게이트 테스트 무수정) |
| C3 scripts 무변경 | `git status --short scripts/` | `?? scripts/test_tree_gate.py`·`?? scripts/tree_gate.py` 2행만 — 기존 스크립트 무변경(커밋 후 `git diff 2fda0aa --name-only -- scripts/`로 동일 입증) |
| C5 claim | 임시 git 저장소(`mktemp -d /tmp/r27-manual-XXXX`)에서 `python3 scripts/tree_gate.py claim --session sess-A --scope "r27 수동 실측" --save <repo>/docs/task-id/r27-tree-claim/` | exit 0 ∧ `.git/effort-router-tree-claims/<hash16>-sess-A.json` 생성 ∧ 레코드 필드(session_id sess-A·tree·tree_hash 16자·scope·hostname·claimed_utc==updated_utc·pid null) 정합 ∧ 감사 JSON `docs/task-id/r27-tree-claim/tree-gate-*.json` 기록(비커밋) |
| C6 check | 동일 저장소 `check --session sess-B` | exit 1 ∧ flags `["foreign_claim_present"]` ∧ foreign_claims[0] = session_id sess-A·scope·claimed_utc·alive_reason ttl·pid_check unsupported |
| C7 release | `release --session sess-A` → `check --session sess-B` | exit 0 ∧ claim 파일 소멸 ∧ 이후 check exit 0(간섭 없음·flags []) |
| C8 release 멱등 | 재 `release --session sess-A` | exit 0 ∧ `already_released: true` |
| C9 stale·prune | `claim sess-C` ∧ `claim sess-alive --pid $$` 후 `check --ttl-hours 0.000001` → `status --ttl-hours 0.000001` → `prune --dry-run --ttl-hours 0.000001` → `prune --ttl-hours 0.000001` | check exit 1 — stale sess-C는 미보고(살아있는 sess-alive만 pid 근거 보고) / status exit 1 ∧ `stale_claims_present` ∧ sess-C state stale / prune --dry-run exit 0 ∧ removed 0·파일 2건 잔존 / prune exit 0 ∧ removed 1 ∧ sess-C 소멸 ∧ sess-alive(pid 생존·TTL 초과) 보존 |
| C10 워크트리 가시성 | `git worktree add ../demo-wt -b wt-x` → demo-wt 내부 `claim --session sess-W` → demo-wt 내부 `check --session sess-B` → 본체 cwd `check --session sess-B --tree <demo-wt 경로>` | claim exit 0 — 레지스트리는 본체 `.git/effort-router-tree-claims/`(common-dir)에 기록 ∧ worktree 내부 check exit 1 ∧ 본체 cwd check도 exit 1(동일 sess-W claim 탐색 — common-dir 공유 실증) |
| C11 폴백 | 비저장소 cwd에서 `claim --session sess-X` | exit 2 ∧ stderr `FAIL tree gate: git 저장소가 아니다 — fatal: not a git repository …` ∧ stdout 없음 |
| C14 훅 실측 | `echo '{"session_id": "sess-B"}' \| CLAUDE_PROJECT_DIR=<repo> python3 .claude/hooks/tree_claim_hook.py` / 동일·`CLAUDE_PROJECT_DIR=/nonexistent-r27` / clean 트리 cwd + sess-Z | foreign claim 존재: additionalContext JSON emit(session sess-alive·scope·claimed·alive=pid + "판정 권한은 메인" 안내) ∧ exit 0 / 게이트 부재: 출력 없음 ∧ exit 0 / 간섭 없음: 출력 없음 ∧ exit 0 |
| C12 문서 정합 | — | **PR2 완료 후 ④리뷰가 판정**(SKILL·README·TESTS·AGENTS r27 절 상호 일치 — 서브커맨드 5종·exit 체계·플래그 2종·레지스트리 경로·state 필드명 `tree_claim`·AGENTS :3 cwd 확장·원장 1줄) |
| C13 줄수 | `wc -l scripts/tree_gate.py scripts/test_tree_gate.py .claude/hooks/tree_claim_hook.py SKILL.md README.md AGENTS.md TESTS.md` | 485·489·78·466·454·8·754 — 전부 650 경고선 이내(TESTS.md는 800 하드캡 내) |
| 검증 입력 변경 보고 | test_tree_gate.py는 **신규 검증 입력**이다(T1~T20+T8b 21건 — 게이트 분기 전수). T19·T20(훅 케이스)은 Phase 2(훅 구현)에서 GREEN 전환 — 위 C1 2단계 GREEN 행 | 기록 완료 |


## r28 격리 가드 — 재점검 훅·커밋 오염 방어 (2026-09-28)

원 요구 — "같은프로젝트내의 세션이 있을시에는 격리에대한 문제점을 확실이 짚고 넘어가야할꺼같은데". r27 잔존 구멍 3종(경고 1회성·커밋 오염 무차단·격리 액션 미연결)을 `tree_claim_hook.py` `prebash` 서브커맨드(PreToolUse(Bash)) + settings 엔트리 + SKILL·README 등재로 봉쇄. 게이트 본체·기존 4 게이트·기존 문서 절 무변경.

계약 요지 (증류):

| 항목 | 계약 |
|---|---|
| 서브커맨드 확장 | argv 무인자·`start` = r27 SessionStart 로직 그대로(경고는 말미 격리 안내 1줄만 추가 — 기존 문구 보존)·`prebash` = 신규. 폴백 계약 동일 — 게이트 부재·비저장소·subprocess 오류·timeout·stdin 파싱 실패·`TREE_GATE_HOOKS=0`(오프 스위치 — prebash 전체, 분리 스위치 없음)은 무작동·무출력·exit 0 |
| 재점검(레벨 1) | git 쓰기 서브커맨드 23종 감지 시만 동작 — quote 상태 추적 분할(인용 내부 `&&` 위조 세그먼트 봉쇄)·`$()`/백틱/히어독 본문(`<<`·`<<-` 종결자 라인까지) 불투명·괄호 그룹 제외·shlex 실패는 정규식 폴백(레벨 1 한정)·`-C`·`--git-dir`·`--work-tree`·`--namespace`(결합형 `-C../x`·`--git-dir=…` 포함 — 단독형만 인자 소비)는 트리거 유효·deny 제외(귀속 불확실) |
| 캐시 | `<TMPDIR>/effort-router-tree-gate-hook/<session-sanitized>.json` — TTL 60초(`TREE_GATE_HOOK_CACHE_TTL_S` 폴백·무효값은 기본 60)·returncode 0·1은 모두 유효 판정 기록(foreign=false 포함)·temp+os.replace 원자·파손 자가치유·`corrupt_seen` 추적으로 corrupt 신규 등장 1회 통보 |
| deny(레벨 2) | foreign_claims 배열 비빈(exit code 아님 — corrupt-only deny 불발행) ∧ shlex 성공 세그먼트 git 명령 위치 ∧ 전체 스테이징(add -A/--all/-u/--update 묶음 분해·pathspec `.`·`./` / commit -a/-all ∧ pathspec 없음 — `--` 이후 전부 pathspec·`-m` 등 값 1 스킵·값 결합 문자(`-ma`의 a)는 플래그 아님). dry-run(`--dry-run`·add -n)은 실행 안 되는 명령으로 deny 제외. 단독 세션·pathspec 병존·부분 스테이징은 허용(오탐 0) |
| 경고·deny 병합 | 신규 침입자(기준선 차집합 — 첫 캐시는 기록만)·corrupt 신규는 additionalContext 경고, deny 동시 성립 시 deny 단독 emit(2개 JSON 객체 금지)·사유 말미 병합. deny 사유 = pathspec 안내 + 격리 명령 원문(`worktree_gate.py create --task <task-id>`) + 유령 탈출 안내("tree_gate.py status 확인 후 레지스트리 파일 수동 삭제 — prune은 alive 불가침") |
| skipTest 가드 | 훅 케이스 전부(T19·T20·T21~T35 — `test_tree_claim_hook.py` 분리, 파일 전체 19케이스) — `HOOK.is_file()` 부재(미러 배포 환경) 시 skip: **저장소=실행·미러=skip**. T19·T20은 전치 단정의 가드 전환만(§5 유일 예외 — 단정 축소 아님) |
| 알려진 한계 | 파일 소유권·index.lock 범위 밖·xargs/find -exec·스크립트·별칭·치환 내부·괄호 그룹 내부 git·`-C` 세그먼트(deny 한정)·비Bash 쓰기 도구(Edit·Write)·기준선 합류(경고 누락 — deny 유지)·하니스 밖 무관. R2 판명 — PreToolUse additionalContext는 공식 지원(v2.1.9 changelog 확인)·deny 스키마 문서 확인 — reason 이관 규칙 불발동 |

검증 기록 (③구현 실측 — 명령 원문·exit code):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C4 RED 선실증 | `python3 scripts/test_tree_gate.py`(훅 확장 전 — 분할 전 단일 파일 34케이스 실측) | exit 1 — Ran 34 tests, FAILED (failures=8, errors=4 — T21·T22·T23·T24·T26·T27·T28·T29·T29b·T30·T31·T31b. T25는 단독 무출력이 양 경로 동일해 우연 통과) |
| C1 저장소 | `python3 scripts/test_tree_gate.py` ∧ `python3 scripts/test_tree_claim_hook.py` | 각 exit 0 — Ran 19 tests, OK(게이트 본체 T1~T18+T8b) ∧ Ran 19 tests, OK(훅 T19·T20·T21~T35 — 분할 파일, T32~T35 갭 수선 포함) |
| C1 미러 | 스킬 형상 임시 복제(scripts 3파일 — `.claude` 부재) 후 `python3 /tmp/r28-mirror/scripts/test_tree_gate.py` ∧ `python3 /tmp/r28-mirror/scripts/test_tree_claim_hook.py` | 각 exit 0 — Ran 19, OK(19 실행·0 skip) ∧ Ran 19, OK (skipped=19) — 총 **19 실행·19 skip·0 실패** |
| C2 회귀 | `python3 scripts/test_worktree_gate.py` ∧ `_hardening` ∧ `test_verify_pin.py` ∧ `test_verify_exec.py` ∧ `test_jev_judge.py` ∧ `test_jev_modes.py` ∧ `test_jev_modes_extra.py` ∧ `test_stagehand_gate.py` | 각 exit 0 — 34·10·23·20·27·10·14·15 tests OK(분할 후 재실측) |
| C5 가드 | 임시 git 저장소 foreign claim 후 prebash — `git add -A`·`git commit -am "x"`·`git add .`·`git add ./`·`git add -u` / `git add src.txt` | 각 exit 0 ∧ deny JSON(pathspec 안내·격리 명령·유령 탈출 안내 포함) / 부분 스테이징 무출력 |
| C6 단독 | claim 부재 저장소 `git add -A` | 무출력·exit 0 ∧ 캐시 `foreign:false` 생성 |
| C7 캐시 | TTL 내 재실행 후 epoch 대조 / `TREE_GATE_HOOK_CACHE_TTL_S=1`+sleep 후 epoch 대조 | epoch 불변(same=yes) → 갱신(renewed=yes) 실측 |
| C8 신규·corrupt | 기준선 후 제2 claim → 만료 재점검 경고(신규 포함) → 재실행 무경고 / corrupt-only → deny 불발행·통보 1회 → 재실행 무통보 | 테스트 T29·T29b + 수동 실측 일치 |
| C9 오탐 | `echo git add -A`·`echo "git add -A"`·`echo "x && git add -A"`·`git -C ../x add -A`·`ls -la`·`git status`·`git log`·`X=$(git add -A); echo done`·`(cd ../x && git add -A)`·히어독 본문(`cat > s.sh <<'EOF'`+`git add -A`+`EOF`)·`git -C../other add -A`·`git --git-dir=../x add -A`·`git commit -ma`·`git add --dry-run -A`·`git add -n -A`·`git add --dry-run .` | 9종+갭 수선 7반례 전부 무간섭(deny 없음)·exit 0 |
| C10 폴백·스위치 | `CLAUDE_PROJECT_DIR=/nonexistent-r28-gate` / 비저장소 cwd / `TREE_GATE_HOOKS=0`(foreign 상태) + `git add -A` | 전부 무출력·exit 0 |
| C11 start 확장 | `git show HEAD:.claude/hooks/tree_claim_hook.py` 훅 vs 확장 훅 — 무인자·`start` 출력 diff | 무간섭 트리 바이트 동등(0바이트) / foreign 트리 기존 문구 유지 + 격리 안내 1줄만 추가(제거줄 0) |
| C11b 동시 성립 | 기준선 대비 신규 침입자 + `git add -A` | stdout JSON 1개(deny 단독)·reason에 신규 session 병합·additionalContext 없음 |
| 갭 수선 D1~D4(T32~T35) | ④리뷰 gap — D1 히어독 본문 불투명·D2 결합형 귀속 불확실(startswith 확장)·D3 commit 값 결합 문자 비플래그·D4 dry-run deny 제외. RED: `python3 scripts/test_tree_claim_hook.py` → exit 1 — Ran 19, FAILED (failures=4 — T32·T33·T34·T35) → 수선 후 exit 0 | 수 manual 실측 — foreign 캐시 상태 8반례 전부 permissionDecision=None·exit 0(D2 `-C../other`는 신규 침입자 경고만 — 비차단 재점검 신호) |
| C3 백색 | `git diff --name-only` | 예상 7파일(수정 6 — 훅·test_tree_gate·settings·SKILL·README·TESTS + 신규 test_tree_claim_hook.py — git diff는 6출력·untracked 별도) |
| C13 줄수 | `wc -l` 전체 | 훅 558·test_tree_gate 440·test_tree_claim_hook 416·settings 73·SKILL 468·README 463·TESTS 792(800 하드캡 내) — 650 경고선 이내 유지(분할 전 test 702 초과분은 팀 승인 분할로 해소) |
| 검증 입력 변경 보고 | test_tree_gate.py 확장(신규 13케이스 T21~T31b + T19·T20 skipTest 가드 전환) 후, 팀 승인으로 훅 케이스 15건(T19·T20·T21~T31b)을 `scripts/test_tree_claim_hook.py` 신규 파일로 분할 — 게이트 본체 19건은 원 파일 잔류. C1·C3 화이트리스트 갱신은 메인 소관 | 기록 완료 |



## r29 루프 탈출 게이트 — 반복 실패 루프 무장 판정 (2026-09-30)

원 요구 ① "이슈가 5개처리했는데 10개로 늘어나있음 해결못하고 삽질하는 근본적 원인을 해결해야될꺼 같음 리포지토리 검토하고 우리꺼에 적용해보자 https://github.com/chldbwnstm/NeverStuck" ② "야이씨발아 설치말고 우리 에포트라우터에 네버스턱 작업하는걸 추가하라는 소린데 이새끼가". 의도 해석 — NeverStuck 스킬 '설치'가 아니라 effort-router 계약·게이트 체계에 NeverStuck 작업방식(반복 실패 루프 탈출 — 증상 패치 금지·메커니즘 진단 강제)을 편입한다. 근본 문제 = 에이전트가 이슈를 증상 패치로 처리 → 이슈 증식(5 처리 → 10 존재)·삽질. `scripts/neverstuck_gate.py`(신규 — 단일 judge, 표준 라이브러리만)·`scripts/test_neverstuck_gate.py`(신규 34케이스)·SKILL·README·TESTS(+TESTS-GATES 분할 A안)·AGENTS로 봉쇄. 기존 게이트 5종(jev·stagehand·verify_pin·worktree·tree+r28 가드)·훅·state.json 스키마 무변경 보존.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| 게이트 본체 | 결정론 '무장 판정' CLI — `python3 scripts/neverstuck_gate.py --history FILE\|- [--save DIR]`. 서브커맨드 없음·훅 없음(무장은 사건 기반 — 동일 무브류 3회 실패·S7 관측 시점). jev·API·git·환경·외부 파일(PROTOCOL.md 포함) 무의존 — 표준 라이브러리만 자기완결(미러 동봉) |
| 판정 순서 | 1단계 preference_domain 면제(최우선 단락 — s7_evaluable:false) → effective(declared_search:true 제외 — 면제만 가능·단죄 불가) → S7(완비 worked의 knob별 값·맥락 상이쌍 = 즉시 무장, failed 유무 무관) → 3회 게이트(같은 무브류 failed ≥3 — S7 성립 시 s7 우선 보고) → not-armed(Never 원칙 — 1~2회 미발동·failed 3 엄격 카운트) |
| 값 비교 D1 | 타입 클래스 bool⊥수치(int·float 통합)⊥str⊥기타 — 같은 클래스 안에서만 ==(30 vs 30.0 동일), 클래스가 다르면 항상 상이(True vs 1·30 vs "30" 상이). 값·맥락 비교와 knob 그룹핑 키에 동일 규칙 적용 |
| s7_evaluable | 전역 스코프(D3) — 완비(knob·value·context) worked 그룹 ≥1이면 true, 0이면 false(판정 불능 투명 표기 — 미감지 방향). trigger=s7_hard_signal ⇒ true(삼중 게이트 무장과 독립 — F1: three_attempt 무장 시 완비 worked 0이면 false 가능) |
| 스키마 검증 | 필수 = move_class(문자열)·outcome(worked\|failed). knob·value·context는 선택 스칼라(str\|int\|float\|bool) — **null은 결손(키 부재 동등 취급)**. 비스칼라(배열·객체)·필수 누락·outcome 이형값·비bool 플래그(declared_search:1·preference_domain:"true" — 참/거짓은 JSON bool 리터럴만)·NaN/Infinity(parse_constant 거부)·비UTF-8 바이트·심층 중첩 JSON(RecursionError)은 전체 거부 exit 2(부분 판정 없음). preference_domain:null·declared_search:null도 결손=False 판정(GAP-4) |
| exit 어휘 | 0 not-armed(정상 진행)·1 armed(ok:true ∧ flags:["armed"] — 프로토콜 진입 의무, **jev의 exit 1 폴백과 정반대** — verify_pin·worktree_gate·tree_gate와 동일 어휘)·2 무효 입력(stderr `FAIL neverstuck gate: <사유>`·stdout 없음 — **--save 실패만 stdout JSON saved_to:null 보존 후 exit 2**, 검사 결과를 버리지 않는다)·3 미사용(결정론 게이트 — 상향 경로 없음) |
| 응답·감사 | stdout 단일 JSON — **attempts 원본 배열 항상 포함**(R3-H2 — --save 감사 파일이 세션 경계를 넘는 이력 원본이 된다)·not-armed도 --save 동일 기록(armed:false 감사)·not-armed 형태는 trigger·armed_on·contract_reminder null 명시·working_values는 상이쌍 산출 근거 완비 worked 전체(중복 제거·입력순)·per_move_class는 effective 한정 집계·contract_reminder는 무장 시 고정 계약 요약+치환 템플릿(무브류 쉼표 열거 / knob 값@맥락·상이쌍 전부, 값 직렬화는 JSON 규칙) |
| 이력 JSON 운영 | 동일 무브류 첫 실패부터 이력 파일 개시·시도마다 즉시 append·knob·value·context는 **worked 시도에도 기재**(미기록은 s7_evaluable:false로 미감지)·환경별 정상값 분기는 declared_search:true로 기록(S7 오탐 방지)·보관은 과업 폴더(감사 JSON과 구분)·과업 재개 시 직전 --save 감사·번들에서 이력 이어 조립 — 세부는 SKILL 신규 절 |
| AGENTS 원장 1줄 | 같은 수정 무브류 3회 실패 시 증상 패치 추가 금지 — `scripts/neverstuck_gate.py --history`로 무장 판정 먼저(armed면 소급 예측·노브 밴 계약 진입) |

검증 기록 (③구현 실측 — 명령 원문·exit code):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C4 RED 선실증 | `python3 scripts/test_neverstuck_gate.py`(neverstuck_gate.py 부재) | exit 1 — Ran 28 tests, FAILED (failures=27, errors=1) — subprocess CLI 방식으로 수집 단계 통과 후 전량 실패 |
| C1 GREEN | `python3 scripts/test_neverstuck_gate.py` | Phase 1 직후 exit 0 — Ran 28 tests, OK → ④ gap 5케이스 추가 후 exit 0 — Ran 33 tests, OK → GAP-5 1케이스 추가 후 exit 0 — **Ran 34 tests, OK(최종)** |
| C2 회귀 | `python3 scripts/test_worktree_gate.py` ∧ `_hardening` ∧ `test_verify_pin.py` ∧ `test_verify_exec.py` ∧ `test_jev_judge.py` ∧ `test_jev_modes.py` ∧ `test_jev_modes_extra.py` ∧ `test_stagehand_gate.py` ∧ `test_tree_gate.py` ∧ `test_tree_claim_hook.py` ∧ `test_codex_routing.py` | 각 exit 0 — 기존 11종 무수정(gap 라운드 후 12종 재실측에서도 전부 exit 0 유지) |
| C2 예외(별도 보고 확정) | `python3 scripts/test_plan_routing.py` | exit 1 — **r29 무인과 기존 결함**(3중 실측: r29 파일 grep 0건·실패 메커니즘 toml 백업 국한·untracked 제거 격리 재현 동일 실패). 근본 원인: 커밋 73d3712가 platforms/codex-agents/review-pr-high.toml을 기대값(gpt-6-sol/xhigh)과 일치시켜 configure_codex_plan.py:62 `updated != original` 분기에서 변경 대상 제외 → 백업 미생성 → test_plan_routing.py:52 FileNotFoundError. 별도 보고로 처리 확정(④·메인 판정) |
| C5 3회 게이트 | 같은 move_class failed 3 이력 JSON + `--history` | exit 1 ∧ armed:true ∧ trigger "three_attempt_gate" ∧ armed_on.move_classes ∧ **s7_evaluable:false**(완비 worked 0 — F1) |
| C6 미발동 | 같은 무브류 failed 2 | exit 0 ∧ armed:false ∧ trigger null(Never 원칙 — 1~2회 미발동) |
| C7 선언 면제 | declared_search:true failed 3 / 실 failed 1+선언 2 / 선언 worked 상이쌍만 | exit 0 ∧ declared_search_skipped 3·considered 0·클래스 미표시 / 선언만 제외 시 1 미달 not-armed / S7 대상도 effective 한정(D2 — 선언 시도 제외) |
| C8 S7 즉시 무장 | knob worked (30,sess-1)·(90,sess-2), failed 0 | exit 1 ∧ trigger "s7_hard_signal" ∧ armed_on.knob ∧ working_values 상이쌍 ∧ per_move_class worked 2(F2 정합) |
| C9 판정 불능 투명 | value·context 미전달 worked만 존재 | exit 0 ∧ s7_evaluable:false(완비 그룹 0) |
| C10 취향 면제 | preference_domain:true ∧ failed 3 | exit 0 ∧ exemptions ["preference_domain"] — 1단계 최우선(S7 비성립 병기) |
| C11 무효 입력 | outcome "maybe"·move_class 누락·attempts 키 부재·파손 JSON·value 배열·비UTF-8 바이트·NaN·Infinity·60k deep nesting | 각 exit 2 ∧ stderr `FAIL neverstuck gate:` ∧ stdout 없음 |
| C12 감사 | `--save DIR`(armed·not-armed 각) / --save 대상이 기존 파일 | neverstuck-gate-<UTC>.json 기록 ∧ saved_to 응답 ∧ 파일에 attempts 원본 포함(not-armed도 기록) / 저장 실패는 stdout JSON saved_to:null 보존 후 exit 2(F4) |
| C14 기존 절 무변경 | `git diff -U0 SKILL.md` | §3 '미해결 검토'·§5 '반복 루프' 절 본문 행 부재 — 신규 절 삽입만(문서 Phase 실측) |
| C16 A안 이동 무변경 | `git show 683a6d1:TESTS.md \| sed -n '553,792p' > /tmp/before.txt` → TESTS-GATES.md 대응 범위 추출 `> /tmp/after.txt` → `diff /tmp/before.txt /tmp/after.txt` | 무차이(출력 0) + r22~r28 절 헤더 grep 존치 — 아래 실측 기록 |
| gap 라운드(④리뷰) | GAP-1 비UTF-8(UnicodeDecodeError 랩 — exit 1 어휘 오염 차단)·GAP-2 F4 --save 실패 커버·GAP-3 커버리지 3종(S7 우선 보고·복수 무브류 쉼표 열거·비인접 상이쌍 탐지)·GAP-5 심층 중첩 JSON(RecursionError 랩) / GAP-4는 문서 메모(preference_domain:null 결손=False — SKILL 절 명시) | 수정 후 GREEN 재실행 exit 0 — Ran 34 tests, OK |
| C13·줄수 | `wc -l` 전 변경 파일 | gate 378·test 485 + 본 문서 Phase 실측치 — 650 경고선 이내(TESTS-GATES는 800 하드캡 내) |
| 검증 입력 변경 보고 | test_neverstuck_gate.py는 **신규 검증 입력**이다(T1~T24+보조 28 + gap 6 = 34케이스 — 게이트 분기 전수). 기존 테스트 무수정 | 기록 완료 |

## r34 근거 수준 분리 — ①계획 번들 가정·미확정 표기 계약 (2026-10-02)

원 요구: andrej-explains(Shawnchee/andrej-explains) 저장소 검토에서 도출한 "가정·미해결 명시" 갭의 effort-router 이식. 사용자 판정: E1(근거 수준 분리 불릿) 채택, E2(트레이스 의무) 탈락 — "E2는 안해도됨 여기 프로젝트 아님". 갭 실측 근거: TESTS.md L77 발명 사건(스킬이 정의하지 않은 자리를 모델이 즉석 발명) — 계획 번들에 불확실 전제의 행선지가 없어 암묵 가정이 ②·④ 공격 표적에서 사라지는 결함 클래스.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| 신규 불릿 | §5 증거번들 '근거 수준 분리' — 번들에 섹션 1개, 계약 요소 수준 3분 표기(확정: 근거 위치 / 가정: 확인 수단 존재 / 미확정: 확인 수단 부재) |
| 널 표기 | 3분 전부 0건이면 '없음' 1줄 기재 — 섹션 생략은 ④ gap |
| 질문 경로 | 미확정 = ①수령 후 ③착수 전 메인이 과업(task-id)당 1회 묶음 확인 질문, 무답분은 가정 전환 후 진행(§1 은닉 변수 질문 규칙 준용) |
| claims 배제 | 가정·미확정은 claims 배열 미등록(done 조건 보존 — ④는 번들 섹션 대조로 검증) |
| 전파 | 가정·미확정의 확증·반증·해소는 메인 번들 표기 갱신 — 기존 트리거 4종 그대로, 실질 변경 수반 반증은 무효화 전파 (b) 발동(v5) |
| 부속 편집 2곳 | 얇은 계획 최소 완료 기준 열거에 '근거 수준 분리' 추가·긴급 트랙 소급 ① 재구성 항목에 '근거 수준 3분' 추가 |
| 적용 제외 | §5 본칙 3개 상속(S티어·긴급 ③선행·탐색적) |

검증 기록 (verify — 메인 핵심 재실행, 계약 문서 과업 = grep 게이트 §3 대체 확인 수단):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C1 신규 불릿 | `grep -c "근거 수준 분리\*\*: ①계획은 번들에" SKILL.md` | 1건(L392) exit 0 — 문구 v4 전문 번들 대조 일치(`-F` 고정문 일치 + md5 대조) |
| C2 부속 편집·보존 제약 | `grep -c "근거 수준 분리·인터페이스" SKILL.md` ∧ `grep -c "근거 수준 3분과" SKILL.md` ∧ `git diff -U0 SKILL.md \| grep "^-" \| grep -v "^---" \| wc -l` | 각 1건(L389·L376) exit 0·마이너스 2행 = 명세 치환 원행(소급 ①·얇은 계획)뿐 — 기존 구 삭제·이동 0 |
| C3 r34 섹션 | `grep -n "^## r34" TESTS-GATES.md` | L287 exit 0 — diff `@@ -283,3 +283,30 @@` append만, r22~r29 무변경(TESTS-GATES 실재 섹션 — r30~r33은 TESTS.md 소재, r21은 본 파일 부재·산문 언급만) |
| C4 모델 리터럴 | `grep -c "gpt-6.1-sol / high\|gpt-6-sol\|opus/xhigh" SKILL.md TESTS-GATES.md` | SKILL.md 15·TESTS-GATES.md 1(기록 시점 실측) — 본 표의 명령 원문 인용으로 최종 재실측 2(자기참조 +1 — TESTS.md L146 R4 전례 동일 클래스). R4 본원장은 발생 수(`grep -o \| wc -l`) 단위, 본 기록은 줄 수(`grep -c`) 단위 — 결론 동일. 신규 발생 0 — 번들 가정 1건이 이 실측으로 확증 전환 |
| 파일 범위 | `git status -s` ∧ `wc -l` | `M SKILL.md`·`M TESTS-GATES.md` 2파일만 — SKILL.md 503→504·TESTS-GATES.md 285→312(본 검증 기록 표 8행 포함 최종) |
| 검증 입력 변경 보고 | 테스트 스크립트·게이트 무접촉 — 본 과업은 계약 문서 grep 게이트만 적용 | 기록 완료 |

### 소급 적대검토·갭 라운드 2 (2026-10-03)

소급 검토 렌즈 2종(산출물·장부 / 프로세스 준수 — plan-adversary-xhigh 직렬 2스폰): 반려·위반 확정. HIGH 5 — A-1 섹션 생략 감지 배선 부재('전달' 무채널 — 주입 계약은 claims·원요구뿐) / C-1 번들 '배포 본수' 미확정 오분류(스크립트=진실원천)·해소 후 미갱신 / F1 ① plan-high 미스폰(메인 직접 수행 — '얇은 계획'은 심층 면제지 스폰 면제 아님, Output Contract 명시-미스폰 = 라우팅 위반) / F2 문서 산출 과제 실행 계약 미적용(외부 원천 대조 0건·grep claims 사용) / F3 spawns 4≠5. MED — A-2 요소 열거 3≠7, A-3 미확정 해소 전이 미규정, B-1 'r21~r33' 허위 범위, B-2 ②·④ 실행 기록 부재, F4 round 근거 불명확, F5 반려 라벨 계약 외 어휘, F6 Contract 직렬 미표기(LOW). 갭 수정: 불릿 v5(배선·해소·열거 3치환)·장부 정정·번들 확증 전환·외부 원천 대조 추가.

| 실행 기록 | 내용 |
|---|---|
| ② | 소급 렌즈A·B 2스폰(직렬) — round.adversary 0 유지(최초 ② 실행 카운트 없음 규칙 — 소급 렌즈는 갱신된 번들에 대한 최초 ② 실행) |
| ④ | 라운드1 ④ 수정요청 3건은 gap 아닌 claims 밖 정정이므로 L427 근거상 과카운트 — round는 통계 기록이므로 소급 차감 없이 사유 기록으로 보존. 라운드2 +1은 렌즈A A-1(C1 gap) 확정 후 재구현 착수의 정규 카운트 → round.review 2 확정. 라운드3 ④ 후 round.review 3(재리뷰 수정요청 = claims 밖 정정 착수 — 과카운트 사유 기록 관례 동일) |
| spawns | 누적 5(②3+③1+④1) 중 라운드1 종료 시 4로 오기록 — 소급 정정. 소급 검토 2스폰 포함 누적 7, 라운드2 ③·④ 후 9, 라운드3 ③·④ 후 11 |
| 외부 원천 대조 | 근거 수준 3분의 원천 — Shawnchee/andrej-explains SKILL.md "Separate verified facts, inference, assumptions, and unresolved questions. Cite file paths and symbols, or authoritative sources for external claims." (raw.githubusercontent.com — 본 과업 세션 취득 캐시). 3분 체계는 해당 원문의 4분(verified/inference/assumptions/unresolved)을 effort-router 계약 요소에 맞춰 3분으로 수렴 적용한 것임을 대조 확인 |
| 프로세스 위반 기록 | F1(① 메인 직접)·F2(문서 산출 실행 계약 미적용)·F4 round 근거 불명확(라운드1 재구현 주체 메인 직접 병기)·F6(Contract 직렬 미표기) — 라운드1 실측 위반. 라운드2부터 ③ implement-med 스폰·④ 재리뷰로 시정. 이력 소급 재실행은 불가 — 기록으로 봉쇄 |
| 라운드3 | ④ 발견 4건 정정(bundle v4 superseded 주석·F4/F6 통일·round 서술·v5.1 배선 1구) — wc: SKILL.md 504·TESTS-GATES.md 325 |

## r35 계약 개정 3건 — phase blocked·cancelled·착수 상한 선언·후속 개선 채널 (2026-10-04)

원 요구: 외부 프롬프트(자율 코딩 에이전트용 시스템 프롬프트, 스몰중력 원본 수정본) 대조 검토에서 도출한 채택 후보 3건 적용("/goal 1,2,3 계획작성해서 적용해"). 채택 기각 1건: 총예산 고정·한도 도달 종료 — round 무상한·경로 전환 철학(§5 예산)과 정면 충돌. 갭 실측 근거: §5 '취소·폐기는 phase 전환'이 enum 미정의 값 암시(worktree_gate.py:85 주석과 불일치)·산재 상한 4곳 착수 시 통합 선언 부재·'범위 밖 기여 분리' 종착점 부재. 본 회차는 r34 근거 수준 분리와 외부 독립 수렴(사실·추론·미검증 3분 ≡ 확정·가정·미확정) — r34 방향 타당성 외부 확인 신호.

계약 요지 (증류):

| 항목 | 계약 |
|------|------|
| phase 2값 | state.json phase 열거 6→8(blocked·cancelled) — blocked=안전한 완료 방해 외부 조건 대기(진입 판정 메인·next 유지·해소 관측 시 재개·독립 과업 계속), cancelled=취소·폐기 확정(최종 패치 시에도 next 유지). 두 값은 완료 아님 — 미해결·차단·폐기 보고 |
| 취소 정리 3단계 | (1) phase=done 패치(게이트 입력 토큰 — done 판정 조건과 무관) → (2) 게이트 done 호출(salvage·제거) → (3) phase=cancelled 최종 패치. (2) exit 2 실패 시 (3) 유보·원인 해소 후 (2) 재실행·정리 실패 잔존은 phase=done 유지+'정리 실패 잔존' 보고 |
| 재개 가드 | 재개 규칙 — phase=blocked·cancelled면 next 진행 아님(blocked는 해소 관측, cancelled는 사용자 재개 요청 시 신규 판정이 전제) |
| 실행 상한 라인 | Output Contract 신규 라인 — 동시성·재시도 상한 착수 시 고정 선언(심층 동시 N·재스폰 M회·적용 계층, 없음 가능). 산재 4곳 무수정 통합 선언·round 무상한 유지(총예산 비채택)·하위 워크플로 공유·③④ 스폰 프롬프트 주입·상황 변화 시 재선언·불일치=라우팅 위반 |
| 상한 우회 금지 | §3 신규 불릿 — 상한은 task-id가 아니라 작업 실체 귀속·재부여·신규 번들 발급으로 초기화 금지. ①회귀·번들 갱신(경로 전환)은 우회 아님 — 카운터는 갱신 후에도 연속 |
| 후속 개선 섹션 | §5 '범위 밖 기여 분리' 확장 — 번들 '후속 개선' 선택 섹션(① 초기 배치·'없음' 표기·③④ 발견분 보고→메인 병합·writer 원칙 준용·중복 규칙 금지·state 필드 0) |

프로세스: 문서 산출 과제 흐름 준수 — ①얇은 계획(plan-high) → ③초안(plan-high, 명세 영역) → ②팬아웃 3렌즈 직렬(완전성/기술적오류/위험, plan-adversary-xhigh — GLM 심층 동시 1) → 수정 라운드(③초안 스폰 재호출, 반려 근거 주입) → ④리뷰(review-pr-xhigh). jev tier 예판 M 추천(0.65) 기각 — any_risk 양성(output_document 0.91·gate_preset 0.51, 감audits/task-id/r35-contract3/jev/). ② HIGH 2건 이결 확인(취소 3단계 실패 분기 부재 — 기술·위험 렌즈 독립 발견) → 수정 라운드 S1~S7 반영. round 0/0(반려 확정 형식 아닌 수정 라운드). 프로세스 위반 0.

검증 기록 (verify — 메인 재확인, 계약 문서 과업 = §3 대체 확인 수단):

| claims | 명령 원문 | 결과 |
|---|---|---|
| C1 phase 8값 | `grep -c 'plan\|adversary\|implement\|review\|verify\|done\|blocked\|cancelled' SKILL.md` | 1건(L414) exit 0 — ④ word-diff로 기존 6값 접두사 byte 일치·말미 삽입만 확인 |
| C2 기존 문구 보존 | ④ word-diff @@ -421,8·@@ -388,7 | 순수 삽입·appending — 실제 문구 삭제 0(라인 diff - 6행은 전부 치환 원행 라인 표시) |
| C3 게이트 무수정 | `git diff --name-only fd45770` | SKILL.md 단일 — scripts/·README·platforms 미포함(옵션 b — 게이트 스크립트 계약 require_done_phase 준수) |
| C4 상한 라인·우회 금지 | `grep -n '실행 상한' SKILL.md` ∧ `grep -c '재스폰은 동일 역할 2회까지\|GLM-5.3 상한 1' SKILL.md` | L358·L470·L479·L481 4곳·산재 상한 grep 2 — 통합 선언만·값 무수정 |
| C5 비종착 치환 | `grep -c '비종착' SKILL.md` | 0건(S3(b) 치환 잔존 없음 — '완료 아님 표시' 계열) |
| C6 파일 범위·규모 | `git status --porcelain` ∧ `wc -l SKILL.md TESTS-GATES.md` | M SKILL.md 단일(verify 시점)·SKILL.md 504→509(+5)·650 경계·800 하드캡 내 |
| 배포 | `python3 scripts/deploy_global.py` 2회 | 1회째 미러 동기·2회째 멱등(changes_total 0) — 아래 verify 기록 |
| 검증 입력 변경 보고 | 테스트 스크립트·게이트 무접촉 — grep 게이트·스키마 대조만 적용 | 기록 완료 |
