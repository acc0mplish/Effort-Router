# effort-router — ChatGPT 앱 어댑터

ChatGPT 앱에는 두 실행면이 있다. 혼동하지 않는다.

## 1. 데스크톱 앱의 Codex 화면

로컬 Codex 클라이언트다. 설치된 `effort-router` Skill, `~/.codex/config.toml`, `~/.codex/agents/*.toml`을 Codex CLI와 공유한다. 모델·effort·역할 매핑은 [codex.md](codex.md)를 그대로 적용한다.

Skill 목록 노출은 `agents/openai.yaml`의 UI 메타데이터를 사용한다. 변경이 보이지 않으면 앱에서 Skills를 새로고침하거나 앱을 재시작한다.

## 2. ChatGPT Work

ChatGPT Work에서도 Skill을 사용할 수 있지만, 로컬 Codex custom-agent TOML을 전제로 하지 않는다. 작업 시작 전에 에디터의 model/reasoning control에서 다음을 고른다.

| 작업 | 선택 |
|---|---|
| 요구가 확정된 일반 실행·변환·반복 작업 | `GPT-5.6 Luna / Max` |
| 명세 작성·계획·스펙 검토·문제 분석·해결안 판정·고난도 작업 | `GPT-5.6 Sol / High~XHigh` |
| 동일 접근 2회 실패·보안/고위험 판정·최난도 단발 문제 | `GPT-5.6 Sol / Max` |

`Max`는 한 문제를 깊게 푸는 모드다. `Ultra`는 독립 하위 작업이 있어 호스팅 subagent 병렬화가 유효할 때만 선택한다.

ChatGPT Work Output Contract의 에이전트 줄은 다음처럼 쓴다.

```text
[Effort Router]
- 판정 티어: M
- 작업 단계: 계획
- 적용 에이전트·모델·에포트: 없음(ChatGPT Work 단일 세션) (gpt-5.6-sol / high)
- 팬아웃: OFF
- 실행 지침 요약: 명세 작성은 Sol, 구현 전 검증 가능한 claims 확정
```

## 3. 일반 Chat

파일·실행 증거가 없는 일반 Chat에서는 모델 선택 조언만 적용한다. `state.json`, custom-agent role, 테스트 실행을 했다고 주장하지 않는다.
