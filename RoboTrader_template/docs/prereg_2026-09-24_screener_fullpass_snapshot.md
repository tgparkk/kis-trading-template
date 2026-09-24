# 사전등록 — EOD 스크리너 스냅샷: 상위 20 한도 폐기 (2026-09-24)

> 상태: **발효 대기** · 발효 **2026-09-28 07:40 재기동**(D-1 관측 번들과 같은 재기동)
> 변경: 운영 코드 **5파일**(`config/constants.py` · `strategies/_rule_screener_base.py` · `bot/liquidation_handler.py` · `core/candidate_selector.py` · `runners/screener_snapshot_collector.py`(타입 표기만)) + 테스트 2파일(수정 1 · 신규 1) · **매수 룰 코드 0줄**
> 분류: **기록층 변경** — 라이브 매수 행동 바이트 동일 · 스냅샷에 룰 통과 종목 «전부» 저장

---

## 0. 사장님 결정 (2026-09-24)

- **목적(원문)**: 「현재 로직으로 산 다음에 나중에 추가 데이터나 수치를 조절해서 매수후보 로직 품질을 높이고 싶다」
- **범위**: **8전략 전부**. 저장 상한 상수 1개(`SCREENER_SNAPSHOT_MAX_ROWS = None`) + 라이브 읽기 상한 가드 1줄(3-5).
- **발효**: 09-28 07:40 번들. D-1 관측 항목 ②③④⑤⑥(로그·shadow 전용 · 별도 사전등록)과 함께 나간다. ① `daily_buys` 분리는 **10-17 로 연기**.
- **후보 분봉 EOD 수집**은 이 문서에서 뺀다 → 나중에 별도 사전등록(9절).
- **룰 동결**: 2026-10-16 까지 룰 변경 금지(09-05 결정). 이 변경은 기록층만 건드린다.

## 1. 전제 · 동결

### 1-1. 룰 동결
8전략의 진입·청산 룰은 한 줄도 안 바뀐다. 바뀌는 것은 «몇 행을 저장하나»뿐이다.

### 1-2. 라이브 매수 행동 불변 — 불변 가드가 필요하다
- 라이브는 스냅샷을 순위순으로 읽는다. 섹터뉴스 재정렬(shadow · 순서 불변)을 거친다. 안전필터가 «안전한 종목 10개가 모일 때까지» 아래로 내려간다(`core/candidate_selector.py:731-733` · `:1130` `limit=max_candidates`, 설정값 10).
- 지금은 스냅샷이 20행이라 20위에서 멈춘다. 행이 늘면 상위 20 중 **11개 이상이 제외되는 날** 21위 이하를 산다. 매수 행동이 바뀐다.
- 실측(라이브 로그 09-01~09-23 · 17거래일): 전략별 하루 제외 최대 2건 · 전 전략 하루 합 0~5건. 드물지만 불가능은 아니다.
- ⇒ **불변 가드**: `_fetch_candidates_for_strategy` 가 스냅샷을 읽은 직후, 재정렬·안전필터 «앞»에서 `codes = codes[:MAX_CANDIDATES_PER_STRATEGY]`(20). 라이브는 변경 전과 같은 1~20위만 본다(3-5).

### 1-3. 발효일
09-24·25 추석 휴장, 09-26·27 주말. 첫 거래일 09-28 07:40 재기동부터. 그날 아침 실행은 `scan_date = 2026-09-23` 을 쓴다(`bot/liquidation_handler.py:604` 직전 거래일 · 실측 확인).

## 2. 목적 · 이 데이터의 한계

### 2-1. 목적
한도 20 때문에 ma20·ma5·elder·daytrading·rs_leader 의 **실제 통과 풀**이 잘려 있다(6-1). 전부 저장하면 나중에 순위·배제·추가 데이터를 얹어 볼 표본이 된다. minervini(5~14)·deep_mr(0~2)·envelope(0~3)는 9월 이후(현 룰) 기준 20 을 안 넘었다. 그 전에는 20행을 채운 날이 있었다(minervini 52일 · 06-05~08-24 · deep_mr 5일 · 06-23~07-30 · DB). 같은 경로라 함께 바뀐다.

### 2-2. 한계 (미리 선언)
- (a) 6-1 의 풀 크기는 **오늘(09-24) 재스캔 값**이다. 라이브 09:00 실행과 조금 다르다. 예: 09-22 minervini 유니버스 재스캔 391 vs 라이브 388 · rs_leader 821/248 vs 804/243.
- (b) 저장되는 것은 룰 **통과** 종목뿐이다. 아깝게 떨어진 종목(near-miss)은 없다. ⇒ 문턱을 «낮추는» 연구는 이 데이터로 못 한다. 순위를 바꾸거나 문턱을 «높이는» 연구만 된다.

## 3. 구현

### 3-1. 상수 (`config/constants.py`)
- `:200` 주석 수정. 「EOD 스냅샷 생성·라이브 소비 공통 SSOT」는 이제 틀리다 → 「라이브 소비 상한 — E6 는 스냅샷 1~20위만 읽는다. 생성 행 수는 `SCREENER_SNAPSHOT_MAX_ROWS`」.
- `:200` 바로 아래 신규: `SCREENER_SNAPSHOT_MAX_ROWS = None  # EOD 스냅샷 저장 상한. None = 룰 통과 전부`.
- `MAX_CANDIDATES_PER_STRATEGY = 20` 값은 그대로다.

### 3-2. 어댑터 None 처리 (`strategies/_rule_screener_base.py:107`)
```python
mc = merged.get("max_candidates", 10)
max_candidates = None if mc is None else int(mc)
```
- `None` 만 특례다. `0` 은 지금처럼 `[]` 를 돌려준다(`int(0)` → `scored[:0]`). 음수 특례도 없다.
- `:148` `scored[:max_candidates]` 는 **안 바꾼다**. `scored[:None]` 이 곧 전부다.

### 3-3. 진단 로그 (`strategies/_rule_screener_base.py:150-158`)
이 클래스에는 `self.logger` 가 없다. 모듈 `logger`(`:15`)를 쓴다. `diag` 는 지금 `finalize_scan({...})` 호출 안에서 바로 만든다. 먼저 변수로 뺀다.
```python
diag = {
    "scan_date": scan_date, "n_universe": len(universe),
    "n_no_data": stats["n_no_data"], "n_impossible": stats["n_impossible"],
    "n_evaluated": n_evaluated, "n_matched": len(scored), "n_selected": len(selected),
}
logger.info("[스크리너] %s scan_date=%s 유니버스 %d · 평가 %d · 룰 통과 %d · 저장 %d",
            self.strategy_name, scan_date, diag["n_universe"], diag["n_evaluated"],
            diag["n_matched"], diag["n_selected"])
self.finalize_scan(diag)
```
8전략 전부 하루 1줄씩 남긴다. minervini·rs_leader 의 기존 `finalize_scan` 로그는 그대로다.

### 3-4. 스냅샷 훅 (`bot/liquidation_handler.py`)
- `:18` import 를 `SCREENER_SNAPSHOT_ENABLED, SCREENER_SNAPSHOT_MAX_ROWS` 로 바꾼다. 모듈 수준 이름이라 테스트가 `patch` 할 수 있다. `MAX_CANDIDATES_PER_STRATEGY` 는 이 파일에서 `:613` 한 곳만 쓰므로 import 에서 뺀다.
- `:613` `max_candidates=SCREENER_SNAPSHOT_MAX_ROWS`.

### 3-5. 소비자 불변 가드 (`core/candidate_selector.py` · `:1095-1102` 빈 목록 분기 뒤, `:1105` 재정렬 앞 · 신규)
```python
# 🔒 불변 가드(2026-09-24 사전등록): 스냅샷은 룰 통과 «전부»다.
#    라이브는 변경 전과 같은 1~20위만 읽는다 — 재정렬·안전필터·E6 로그 불변.
codes = codes[:MAX_CANDIDATES_PER_STRATEGY]
```
- `MAX_CANDIDATES_PER_STRATEGY` 는 모듈 상단에서 import 한다.
- 효과: 재정렬 입력 · 안전필터 입력 · `[E6] … (스냅샷 N건 …)` 의 N(`:1138-1141`)이 변경 전과 같다(N ≤ 20).

### 3-6. 수집기 (`runners/screener_snapshot_collector.py`)
- `:85` `max_candidates: Optional[int]` (타입 표기만 · `Optional` 은 `:29` 에서 이미 import).
- `:121` `candidates[:max_candidates]` 는 **유지**한다. `candidates[:None]` 은 전부다. CLI 전용 어댑터(lynch·sawkami·bb_reversion·sample)는 스스로 자르지 않을 수 있어 이 줄이 막아 준다.
- 참고: `config` 가 없으면 전략 목록이 이 4개로 폴백한다(`:49-53`). 4개 모두 `int(None)` 에서 실패한다(`lynch/screener.py:208·:231` · `sawkami/screener.py:595·:620` · `bb_reversion/screener.py:142·:168` · `sample/screener.py:578·:598`). 전략별 `try` 가 1건 실패로 끝낸다(`:164-174`). 라이브 봇은 `config` 가 있어 이 경로를 쓰지 않는다.
- `rank_in_snapshot` 은 21, 22, … 로 이어진다(`db/repositories/candidate.py:132`).

## 4. 불변 조건

### 4-1. 1~20위 항등 — 구조로 성립한다
- 한 번의 스캔에서 `scored` 는 목록 1개다. 한 번 정렬된다(`:147`, 파이썬 정렬은 `reverse=True` 에서도 안정). `scored[:None]` 과 `scored[:20]` 은 같은 목록의 앞부분이다. ⇒ 저장 1~20위는 한도 20 일 때의 20행과 **정의상 같다**.
- 서로 «다른» 두 스캔 사이의 동점 순서는 정해져 있지 않다. 유니버스 쿼리에 `ORDER BY` 가 없기 때문이다(`db/quant_daily_reader.py:90-97`). 실측: 오늘 rs_leader 09-22 를 연달아 두 번 돌리니 배제 종목 `codes=` 순서가 달랐다. 이 비결정성은 변경 전에도 똑같이 있었다. 새로 생기지 않는다.
- 실측(증거일 뿐 · 근거 아님): 09-22·09-15·09-08 × 8전략 = 24건. `scan(max=100000)[:20]` 과 `scan(max=20)` 의 코드·점수가 24/24 일치. elder 는 09-22·09-15 에 동점 1쌍이 있었다.

### 4-2. 소비자 불변
3-5 가드 때문에 소비 경로는 스냅샷 행 수와 무관하게 1~20위만 본다. 안전필터 `limit=10` 도 그대로다. `sector_news_rerank_log` 는 코드 1개당 1행을 쓴다(`core/candidate_selector.py:1227-1234`, shadow 에서도). 가드 덕에 이 표의 행 수도 안 바뀐다.

### 4-3. (전략, scan_date) 당 params_hash 는 1개
- 새 값 `None` 은 해시를 바꾼다. 실측: ma20 `9f2ad26d8135…`(20, DB 09-22 행과 일치) → `292fc1ffbadd…`(None). rs_leader `86cf047b5184…` → `d1cd2dcd30cd…`.
- provider 는 해시 없이 읽는다(`core/screener_snapshot_provider.py:86-94`). 정렬은 `ORDER BY scan_date, params_hash, rank_in_snapshot`(`db/repositories/candidate.py:219-228`). 같은 날 해시가 둘이면 두 목록이 이어 붙는다. 같은 코드가 두 번 나온다.
- 그러면 `rerank` 가 `ValueError("codes 에 중복…")` 를 낸다(`core/sector_news_rerank.py:31-32`). 재정렬은 fail-open 이라 중복 목록이 그대로 안전필터로 간다(`core/candidate_selector.py:1267-1283`).
- ⇒ **불변식: 한 (전략, scan_date) 에 해시 1개.** 09-28 첫 실행은 안전하다. `scan_date=2026-09-23` 행이 아직 없다(DB 최대 scan_date = 09-22, 오늘 확인).
- 같은 날 상수를 바꾸고 재기동하는 것은 **금지**다(8절).

### 4-4. 재실행
`_snapshot_done_date` 가드(`bot/liquidation_handler.py:596-598`)는 **한 프로세스 안**의 재실행만 막는다. 재기동하면 스캔이 다시 돈다. 같은 해시면 upsert(`db/repositories/candidate.py:143-153`)라 안전하다. 단 그 사이 풀에서 빠진 종목의 옛 행은 지워지지 않는다. 5-3 의 행 수 대조가 이를 잡는다.

### 4-5. 15:35 검증
`bot/system_monitor.py:836-893` 은 `COUNT(*)` 를 로그로만 남긴다. 행 수를 강제하지 않는다. 숫자만 커진다.

## 5. 검증 계획

### 5-1. 테스트 (워크트리에서만)
- **수정** `tests/test_bot_liquidation.py:554-581` — 지금은 훅이 `MAX_CANDIDATES_PER_STRATEGY == 20` 을 넘긴다고 단언한다. 변경 후 반드시 실패한다. (c) 로 다시 쓴다.
- **신규** `tests/test_screener_snapshot_fullpass.py`:
  - (a) 점수 동점이 있는 가짜 어댑터: `scan(None)` 이 룰 통과 전부를 돌려준다. `scan(None)[:20] == scan(20)`(안정 정렬).
  - (b) `run_once(max_candidates=None)` 이 전부 저장한다. `params_json` 의 `max_candidates` 가 null 이다. 한도 20 의 해시가 변경 전 골든 해시와 같다(ma20 `9f2ad26d8135…` 로 고정).
  - (c) 훅이 `bot.liquidation_handler.SCREENER_SNAPSHOT_MAX_ROWS` 를 그대로 넘긴다(패치한 값으로 확인).
  - (d) 소비자: 스냅샷 30행 · 상위 20 중 11개 이상 제외 → 반환 종목이 전부 20위 이내다. 안전정보 조회도 20건 이하다.
- **회귀 규칙**: pytest 는 워크트리에서만 돌린다. 실패 «집합»을 `D:/tmp/ontick_baseline_5958b66.txt`(5 failed · 8 errors)와 양방향 차분한다. 새 실패 0 · 사라진 실패는 사유를 적는다.

### 5-2. 드라이런 실측 (완료 · 09-24)
워크트리에서 8어댑터를 `max_candidates=100000` 과 `20` 으로 각각 돌렸다(`daily_prices` SELECT 만 · `RS_LEADER_CORP_ACTION_MODE=live` 로 라이브와 맞춤). 한도 20 결과의 합계는 DB 저장 행 수와 3일 모두 같았다(116 · 110 · 104). 결과는 4-1 · 6-1 · 6-2.

### 5-3. 09-28 점검 목록
| 항목 | 기준 | 어디서 |
|---|---|---|
| 저장 | `[스냅샷] {전략} - N건 저장완료` · ma20·ma5·elder·rs_leader 는 N>20 | `print` 라 **`robotrader_template_*.log` 에만** 있다 |
| 진단 | `[스크리너] … 룰 통과 N · 저장 N` 8줄 · 두 N 이 같다 | 두 로그 모두 |
| DB 행 | `SELECT strategy, count(*), max(rank_in_snapshot), count(distinct params_hash) FROM screener_snapshots WHERE scan_date='2026-09-23' GROUP BY 1` | `count(*) = max(rank)` = 진단 로그의 저장 N · 해시 수 = 1 |
| DB 값 | `params_json->>'max_candidates'` 가 null | 같은 SQL |
| 라이브 항등 | 전략마다 `안전성 필터: K건 조회` 에서 K ≤ 20 · `[E6] … (스냅샷 N건 …)` 에서 N ≤ 20 | 09:00 로그 |
| 15:35 | `EOD 스크리너 스냅샷 실행 완료 (D-1=2026-09-23, DB 저장 …건)` 이 약 290~440 | 로그 |
| 오류 | `TypeError` · `codes 에 중복` · 스냅샷 `저장실패` 0건 | 로그 |
| 다음날 | 09-29 에 `scan_date='2026-09-28'` 로 같은 점검 | — |

## 6. 위험 · 부작용

### 6-1. 행 증가 (재스캔 실측 · 2-2 (a))
| 전략 | 09-22 | 09-15 | 09-08 | 라이브 소비 |
|---|---:|---:|---:|---|
| rs_leader | 248 | 180 | 129 | 불변(1~20위) |
| book_pullback_ma5 | 65 | 43 | 69 | 불변 |
| elder_ema_pullback | 43 | 58 | 31 | 불변 |
| book_pullback_ma20 | 35 | 51 | 36 | 불변 |
| daytrading_3methods_breakout | 27 | 23 | 17 | 불변 |
| minervini_volume_dryup | 14 | 9 | 5 | 불변 |
| deep_mr_dev20 | 2 | 0 | 0 | 불변 |
| book_envelope_200d | 0 | 1 | 2 | 불변 |
| **합계(전수)** | **434** | **365** | **289** | |
| 현행 저장(한도 20 · DB) | 116 | 110 | 104 | |

- 현행: 하루 104~116행 · 5거래일 주 511~549행(08-24~09-14 주 · DB) · 표 전체 8,351행 = 4,538,368 B ⇒ 행당 약 543 B(인덱스 포함).
- 변경 후: 하루 289~434행(+185~318 · 2.8~3.7배) · 주(5일) 1,445~2,170행 · 연(250거래일) 72,250~108,500행 ≈ 39~59 MB. 현행은 연 26,000~29,000행 ≈ 14~16 MB.
- rs_leader 가 129~248행으로 전체의 45~57% 다.
- `sector_news_rerank_log`: 하루 106~116행(09-14~09-23)으로 스냅샷 행 수와 같다(09-22·09-23 둘 다 116). 3-5 가드로 **변화 없음**. 가드가 없으면 스냅샷과 같이 2.8~3.7배가 된다.

### 6-2. 스캔 시간 (재스캔 · 전략별 초 · 전수 / 한도 20)
| 전략 | 09-22 | 09-15 | 09-08 |
|---|---|---|---|
| rs_leader | 3.6 / 3.8 | 3.5 / 3.4 | 3.4 / 3.5 |
| book_envelope_200d | 3.7 / 3.6 | 3.2 / 3.3 | 3.4 / 3.3 |
| minervini_volume_dryup | 2.5 / 2.0 | 2.3 / 2.5 | 2.3 / 2.2 |
| 나머지 5전략 | 1.5~2.6 | 1.6~2.6 | 1.4~2.4 |

차이는 ±0.5초 안이다. 정렬 대상은 같고, 늘어나는 것은 저장 행뿐이다.

### 6-3. 텔레그램 · 로그 표기
09:00 `[스크리너 스냅샷] … rs_leader 248건 …`(`bot/liquidation_handler.py:621-623`)처럼 큰 숫자가 나온다. **저장 건수이지 매수후보 수가 아니다.** 매수후보는 여전히 전략당 최대 10건이다(`[E6] … N건 확보`).

### 6-4. D-1 번들과 동시 발효
②~⑥ 은 로그·shadow 전용이다. 이 문서의 라이브 항등 점검(K ≤ 20 · E6 N ≤ 20)은 번들과 따로 읽을 수 있다. 그래서 두 변경의 효과를 가를 수 있다.

## 7. 하류 연구 도구 영향 (라이브 아님 · 담당 = 연구 트랙)

| 도구 | 무엇이 바뀌나 | 후속 | 기한 |
|---|---|---|---|
| 재현기 `backtest/concept_axes/replayer/run.py:377-378 · 385-386 · 399-400` | 해시별 구간의 `int(params.get("max_candidates"))` 가 null 을 만나 `TypeError` | 09-30 재판정 창을 `--end ≤ 2026-09-22` 로 고정(기본 `GEN_END=2026-09-11` 은 안전 · `:45`). 또는 None-safe 로 고치고 M1 비교를 rank ≤ 20 으로 자른다(`gate.py:134-138` 은 목록 전체를 집합으로 비교) | 09-30 재판정 전 |
| 원장 8전략 `ledger8/logscan8.py:458` · `registry.py:70` | `ext = kept[target:]` 가 11~20위에서 11~N위로 조용히 바뀐다. `TIER_EXT` 설명 「T+1~20위」가 틀려진다 | rank > 20 을 새 tier(예: `ext2`)로 분리하고 `ext` 는 rank ≤ 20 으로 자른다 | scan_date ≥ 09-23 을 처음 포함하는 재추적 전 |
| 백테스트 `backtest/engine.py:321-325` | provider 가 준 전 행을 매수 유니버스로 쓴다. 09-23 이후 구간은 상위 20 대신 전수 | 라이브 재현이 목적이면 호출자가 rank ≤ 20 으로 자른다 | 해당 백테스트 착수 시 |

`ledger8/sources8.py:39-46` 은 원래 모든 행을 읽는다. minervini `cap_skip_ledger` 는 풀이 20 미만(5~14)이라 관측상 영향이 없다.

## 8. 롤백
- `SCREENER_SNAPSHOT_MAX_ROWS = 20` 으로 되돌린다. 3-5 가드는 행이 20 이하면 아무 일도 안 하므로 남겨 둔다.
- 효과는 **다음 거래일 07:40 재기동**부터다. 상수를 바꾼 **당일 재기동은 금지**다. 같은 scan_date 에 두 번째 해시가 생겨 4-3 중복이 난다.
- 당일 되돌려야 하면: 그 scan_date 의 새 해시 행만 삭제한 뒤 재기동한다. DB 쓰기이므로 **사장님 승인 후**에만 한다.
- 지난 전수 행(>20)은 남긴다. 날짜마다 해시가 1개라 소비자에 해가 없다.

## 9. 이 문서가 안 하는 것
| 항목 | 이유 |
|---|---|
| 매수 룰 변경 | 10-16 까지 동결 · 통과 기준 불변 |
| 라이브 목표 10 · 읽기 상한 20 변경 | 3-5 가드로 고정 |
| 안전필터 · 섹터뉴스 재정렬 변경 | 입력이 변경 전과 같다 |
| 근접 탈락(near-miss) 기록 | 룰 통과만 저장(2-2 (b)) |
| 후보 분봉 EOD 수집 | 나중에 별도 사전등록 |
| ① `daily_buys` 분리 | 10-17 로 연기 |
| 순위 재조정 · 100만원 사이징 | 이 데이터가 쌓인 뒤 따로 |

## 10. 출처 (file:line)
- 상수: `config/constants.py:200`(주석 수정 · 신규 줄은 바로 아래)
- 어댑터: `strategies/_rule_screener_base.py:15`(모듈 logger) · `:107`(None 처리) · `:147-148`(정렬·절단 · 무변경) · `:150-158`(diag 분리 + 로그)
- 훅: `bot/liquidation_handler.py:18`(import) · `:596-598`(가드) · `:604`(scan_date) · `:613`(상수 전달) · `:621-623`(텔레그램)
- 수집기: `runners/screener_snapshot_collector.py:85`(타입) · `:114-117`(params·해시) · `:121`(유지) · `:148`(`print`)
- 소비자: `core/candidate_selector.py:731-733`(지연 필터) · `:1095-1102`(빈 목록) · `:1105`(재정렬) · 신규 가드 · `:1130`(안전필터) · `:1138-1141`(E6 로그) · `:1227-1234`·`:1267-1283`(재정렬 기록·fail-open)
- 중복 검사: `core/sector_news_rerank.py:31-32` · provider: `core/screener_snapshot_provider.py:86-94`
- DB: `db/repositories/candidate.py:132`(rank) · `:143-153`(upsert) · `:219-228`(해시 없는 읽기 정렬)
- 유니버스: `db/quant_daily_reader.py:90-97`(ORDER BY 없음)
- 검증: `bot/system_monitor.py:342` · `:836-893`
- 테스트: `tests/test_bot_liquidation.py:554-581`(수정) · `tests/test_screener_snapshot_fullpass.py`(신규)
- 연구: `backtest/concept_axes/replayer/run.py:45 · 377-378 · 385-386 · 399-400` · `replayer/gate.py:134-138` · `ledger8/logscan8.py:458` · `ledger8/registry.py:69-70` · `ledger8/sources8.py:39-46` · `backtest/engine.py:321-325`
