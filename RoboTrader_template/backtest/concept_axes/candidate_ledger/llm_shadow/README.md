# llm_shadow — 연구 ② LLM 전 종목 채점 shadow «전향 관측»

> 규범 = `docs/prereg_2026-09-26_llm_candidate_shadow.md`(동결 `64f4d4a`). 봇은 이 패키지를 읽지 않는다(라이브 변경 0줄).
> 🔒 **개봉 스크립트 `run_unseal.py`(§6~§8)는 이 커밋에 없다** — 개봉-1(2026-12-22) «전» 별도 커밋으로 넣는다.
> 그 전까지 LLM 출력을 결과·통계와 잇는 코드는 없다(봉인 §4 · §13-1).

| 파일 | 사전등록 |
|---|---|
| `prompt_v1.py` | 부록 A(A.1~A.3·A.5·A.6 펜스 그대로) · A.4/A.7 argv · `PROMPT_SHA256`(§5-7) · 부록 대조 |
| `inputs.py` | §2 T/D · §3-1 U(D) · §3-2 (A) 새 항목 · §3-5 컷오프 · §3-6~3-10 블록 · 12-31 휴장 로컬 보강 |
| `schedule.py` | §3-2·3-3 조각·순환·우선순위·이월·성수기(순수) |
| `state.py` | §5-3 plan→호출→shadow · 재개 · §5-4 묶음·재시도 · §5-5 한도·429/529 · §5-6 반복 · 저장소 |
| `cli.py` | §5-2 고정 exe 호출·env 가드 · 부록 B 결과 해석 · §4 사후 검사 |
| `freeze.py` | §5-1 무결성(동결 파일 · HEAD·깨끗한 워크트리·exe·CLI 버전·프롬프트) |
| `lock.py` | §3-4 OS 잠금(PID·시각 · stale 자동 해제) |
| `dart_load.py` | §3-4 전향 적재(① 스크립트 잠금만 교체 · 합산 ≤ 60회/일 · ① §2 완결 판정) |
| `search_arm.py` | §5-9 검색 팔 표본·호출·(ㄱ)(ㄷ) 집계 |
| `ledger.py` · `alerts.py` | §4 원장 해시 · §3-4 경보 |
| `ddl.sql` · `ddl.py` | 부록 C(역할·스키마·표·뷰 3개) · 쓰기 연결 |
| 런너 | `scripts/llm_candidate_shadow.py`(본체 16:10) · `scripts/llm_shadow_search.py`(검색 팔 08:30) |
| 테스트 | `tests/test_llm_shadow.py` |

## 선언된 이탈·해석(구현)

1. 동결 상수(code_sha·exe_sha256·cli_version·prompt sha·타임아웃)는 git 밖 `%LOCALAPPDATA%/kis-llm-shadow/frozen.json`(`--freeze`) — 커밋 안 상수는 자기 참조라 불가.
2. `argv_sha256` = argv[1:](exe 경로 제외 · exe 는 `exe_sha256` 로 고정)을 NUL 로 이은 UTF-8 sha256.
3. 짝 해시(§5-9) = 블록에서 `=== {i}/{k} ` 조각만 뺀 본문(종목명·시총·r20 줄은 남김) → `block_sha256`.
4. 재무 PIT: 03·06·09 외 결산월(예 202605)도 +60일 · 12월 +100일.
5. (ㄱ) 정규화: NFKC 가 `ㆍ`(U+318D)를 `ᆞ`(U+119E)로 바꾸므로 6종의 NFKC 상도 `·` 로 바꾼다. D+3 = 거래일.
6. 표 `day_plan` 추가(그날 U(D) 코드 목록·건수·성수기 — 늦은 편입·재계산용 · 모델 출력 없음).
7. (B) 가 상한에 못 들면 행을 쓰지 않는다(다음 날 계속 due) · `skipped_cap` 은 (A) 넘침에만.
8. 1차 실패 칸은 재시도 뒤 종결 행을 쓴다(INSERT-only 유지) · 재시도 묶음 ≤ 20 · 한도 오류 시 재시도·반복 생략(다음 실행이 재개).
9. 한도 오류 ⇒ `search_paused.flag`(검색 팔 중단 · 해제 수동).
10. `scripts/dart_disclosure_backfill.py` 에 `run(args, lock_fns=None)` 주입 매개변수만 추가(기본 동작 동일).

## 실행 순서(§10)

```
psql -h 127.0.0.1 -p 5433 -U postgres -d kis_template -f backtest/concept_axes/candidate_ledger/llm_shadow/ddl.sql
python scripts/llm_candidate_shadow.py --verify-appendix
python scripts/llm_candidate_shadow.py --freeze --batch-timeout 180      # 코드 커밋 뒤 · 깨끗한 워크트리
python scripts/llm_candidate_shadow.py --dry-run --transmission-check    # CLI 1회
python scripts/llm_candidate_shadow.py --dry-run --dry-codes 120         # CLI ≤ 10회 · 묶음 p95
python scripts/llm_shadow_search.py --dry-run --max-calls 2              # WebSearch 확인
```
`config/key.ini`(라이브 트리)에 `[LLM_SHADOW]` 절 `db_password = …` 추가 필요.
