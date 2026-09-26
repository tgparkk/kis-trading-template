# 개정문 — LLM 전 종목 채점 shadow §5-9 (dry-run 실측 반영 · 첫 실행 전) · 2026-09-26

- 대상: `docs/prereg_2026-09-26_llm_candidate_shadow.md`(동결 `64f4d4a`) — **원문은 한 글자도 고치지 않는다.** 이 문서는 별도 파일로 붙는 개정문이다.
- 근거: §10 산출물·순서 ⑤ 「dry-run(...) → **타임아웃·도구 개정문**」· §5-4 「묶음 타임아웃 = dry-run p95 로 정해 **첫 실행 «전» 개정문**」· §5-9 「권한 거부(`permission_denials`)면 `--allowedTools WebSearch,WebFetch` 추가(미시험 · **첫 실행 «전» 개정문**)」 — 셋 다 첫 채점 행 «전» 개정을 원문이 이미 예정해 뒀다.
- 시점: 코드 커밋 `0c61e7c`(구현) «후» · **첫 실호출(2026-09-28 시운전) «전»** — 아직 채점 행 0.

## 1. 목적

관리자가 2026-09-26 오늘 구현 CLI 예산(§12 ≤ 10회) 중 10회를 써 전달검증 1 + 본체 dry-run 4 + 검색 팔 dry-run 2 + 진단 3 을 실행했다. 그 결과 §5-9 두 문장(도구 허용·모델 검사)이 실측과 어긋남을 발견해 **재 dry-run 없이**(예산 소진) 코드·규칙을 고치고 이 문서로 등재한다.

## 2. dry-run 실측 (CLI 2.1.283 고정 · exe sha256 `9dbe16da…de3a`)

| 항목 | 결과 |
|---|---|
| 전달 검증 | ok · 모델 `claude-opus-5-5` · 되읊기 통과(56자) |
| 본체(A.4) | 4호출 · 45행 ok · 묶음 지연 중앙 20,902ms · p95 23,597ms · max 23,597ms |
| 검색 팔(A.7, 원문 그대로) | 2호출 ok 이나 `usage.server_tool_use.web_search_requests` = [0, 0] |
| 진단(권한) | `permission_denials` 에 `WebFetch` — 허용 목록 없이 도구가 막힘 |
| 진단(`--allowedTools WebSearch,WebFetch` 추가) | 거부 0 · `num_turns` 3 · 15.6~23.0초 · stream-json 에 `WebSearch` tool_use 2건 · **top-level `web_search_requests` 는 여전히 0** · `modelUsage`: `claude-opus-5-5`{in 6·out 628·cacheRead 14326·webSearchRequests 0} · `claude-haiku-4-5-20251001`{in 26758·out 931·webSearchRequests 2} |

⇒ Claude Code 의 `WebSearch` 는 **보조 모델(haiku)에 위임**되고, 그 보조 모델의 **출력 토큰이 가족 모델보다 많을 수 있다**(628 < 931) — §5-9 구 모델검사 규칙("출력 토큰 최다 키")이 이 실측 1건에서 이미 틀린다.

## 3. 개정 1 — 검색 팔 명령(A.7) `--allowedTools` 추가

- `--tools WebSearch,WebFetch` 바로 뒤에 `--allowedTools WebSearch,WebFetch` 를 추가한다(본체 A.4 는 무변경 · `--tools ""` 그대로).
- 이미 §5-9 원문에 「권한 거부면 추가(미시험 · 개정문)」로 예정돼 있던 조치 — 오늘 진단이 그 미시험을 확정했다.
- `argv_sha256`(검색): `6e4f9f26…f16d3a` → `f28a90de…855806a`(토큰 16→18개 · exe 경로 제외 · [실측 재계산]). **`prompt_sha256_search`는 불변**(`e1281ce9…e71a613` · A.1/A.2/A.3/A.5/A.6 펜스 본문 무변경 — `--allowedTools` 는 명령줄 인자이지 프롬프트 펜스가 아니다).

## 4. 개정 2 — 검색 팔 모델 검사 규칙 교체

- 구(§5-9 원문): 「`modelUsage` 중 출력 토큰이 가장 많은 키 = `claude-opus-5-5`」 — **폐기**(§2 실측으로 반증됨).
- 신: **가족 모델 키(`claude-opus-5-5`)가 `modelUsage` 에 있어야 하고**, 그 밖의 키(검색 도구 보조 모델)는 **전부 `webSearchRequests ≥ 1`** 이어야 한다. 하나라도 어기면 `model_mismatch`(§5-4 규약 그대로 그날 검색 팔 중단). 저장 `model` 열 = 가족 모델 키(검사 통과 시).
- 구현: `cli.py::pick_model(model_usage, most_output, expect_model)`(검색 팔만 새 규칙 · 본체 = 유일 키 규칙 무변경) · `cli.py::interpret()` 에서 `expect_model` 전달.

## 5. 개정 3 — 검색 증거 열 · `helper_models`

- `web_search_requests` = **`modelUsage[*].webSearchRequests` 의 합**(폴백 = `modelUsage` 없으면 top-level `usage.server_tool_use.web_search_requests`) — top-level 값은 위임 구조 때문에 0으로 남을 수 있어 «증거로 부족»(§2).
- 새 열 `llm_shadow.search.helper_models`(TEXT) = `modelUsage` 중 가족 키가 아닌 키를 콤마로 이은 것(예: `claude-haiku-4-5-20251001`) — 어느 보조 모델이 검색을 수행했는지 기록.
- (ㄱ)(ㄷ) 집계(§5-9 자동 집계)는 **무변경** — `search_daily_agg` 에 "검색 미수행"(`web_search_requests=0`) 전용 카운터 열이 없어 새로 추가하지 않는다. 필요하면 `v_search_daily` 조회 시 `web_search_requests = 0` 행수를 별도로 세어 보조 인쇄한다(개봉-1 스크립트 몫 · 판정 열 아님).

## 6. 개정 4 — 묶음 타임아웃 180초 확정

- §5-4 잠정값(180초)을 §2 실측(본체 p95 23,597ms ≈ 23.6초 · 30배 여유)으로 **확정**한다 — 값 변경 없음, "잠정" 딱지만 제거.

## 7. 선언된 이탈 목록

(a) 동결 상수는 git 밖 `%LOCALAPPDATA%\kis-llm-shadow\frozen.json`(HEAD·exe·프롬프트 해시 — 커밋 안 상수는 자기 참조라 불가 · 순환 회피).
(b) `run_unseal.py` 는 개봉-1(2026-12-22) 전 별도 커밋으로 넣는다(README §0 이미 명시).
(c) 구현 예산 초과: executor 33.7만 + verifier 21.9만 + 소수정 7.5만 + 이번 개정 executor 19.4만(지시 8만 초과) = **82.5만** > §12 상한 50만 — **결과와 무관하게 기록**(§12 는 판정 조건이 아니라 상한 선언).
(d) 검색 팔이 보조 모델(haiku)을 쓰는 것은 Claude Code CLI 구현 사정(WebSearch 위임)이지 이 연구가 고른 것이 아니다 — 판정 밖(가족 = `claude-opus-5-5`) · `helper_models` 열에 그대로 남긴다.
(e) README(`llm_shadow/README.md`) 이탈 목록 15건 참조 · DDL 에 `day_plan` 표 추가(README 6) · 코드 커밋 `0c61e7c` · **시운전 첫날(2026-09-28)이 개정된 검색 팔의 첫 실호출**이다(구현 CLI 예산 소진으로 재 dry-run 없음 · 실패하면 `model_mismatch`/`cli_error` 행으로 남을 뿐 봉인 데이터 오염은 없다 — §5-4·§5-9 상태 기계 그대로).

## 🔒 확정 시점

이 개정문은 **첫 채점 행 이전**에 커밋한다(§10 순서 ⑤ 그대로 · git 순서: 코드 커밋 `0c61e7c` < 이 개정문 커밋 < 첫 행). 개정 1~4 는 검색 팔(S1)에만 적용되고 본체(F1/F2/F3) 는 무변경이다.
