# 분봉 토너먼트 Smoke 진단 리포트

- 작성일: 2026-05-16
- 대상: tournament_smoke/20260516_031150 (5거래일, 60 시나리오)
- 작성자: Debugger Agent

---

## 1. 결과 요약

60개 시나리오 전원 합격 0건 (일승률 0% -- 모든 시나리오). screener universe 30건은 거래 자체가 0건이며, dynamic universe 30건 중 절반은 거래 0건, 나머지는 -10~-24% 일평균 손실로 폭주. 4개 독립적 버그가 결과를 왜곡했으며, 버그 수정 없이 임계값 튜닝을 해봐야 의미가 없다.

---

## 2. 근본 원인 분석

### BUG-1 (Critical) -- screener universe 전체 trade_count = 0
**증거**: 실측

```
scan_date='2026-05-11' -> 10건 확인됨 (scan_date 컬럼으로 쿼리 시)
snapshot_date 쿼리 -> psycopg2.errors.UndefinedColumn 예외
```

**위치**: `scripts/run_intraday_tournament.py:111`

```python
sql = (
    "SELECT DISTINCT stock_code "
    "FROM screener_snapshots "
    "WHERE snapshot_date = %s"   # <-- 버그: 실제 컬럼명은 scan_date
)
```

**메커니즘**: `snapshot_date` 컬럼 없음 -> psycopg2 예외 -> `except` 분기 -> `codes = []` -> `day_candidates = []` -> 매수 스킵 -> trade_count = 0. screener_snapshots 테이블에는 5/11~5/15 각 10건(bb_reversion)이 실제로 존재하는데 쿼리 자체가 실패하므로 30개 시나리오가 전부 빈 결과를 받음.

**영향**: 30 시나리오 (screener x 10전략 x 3포지션) 전체 무효화

---

### BUG-2 (Critical) -- vwap_trade / reversal_vwap 동적 universe에서 0건
**증거**: 실측

```
000720 첫봉: amount/volume = 163,115원 (close 163,800 -- 정상)
000720 둘째봉: amount/volume = 553,645원 (close 163,700 -- 비정상, 3.4배)
000720 마지막봉: VWAP = 42,993,803원 (close 165,900 -- 259배)
-> close > VWAP 충족 봉 수: 1 / 389 (사실상 0)
```

**위치**: `utils/intraday_indicators.py:29-49` (vwap 함수)

```python
# amount 있으면 amount/volume으로 tp 계산
valid_vol = df["volume"].replace(0, np.nan)
tp = df["amount"] / valid_vol
```

**메커니즘**: `minute_candles.amount`는 **당일 누적 거래대금**이다. 분봉 단위 거래대금이 아님. vwap() 함수는 이를 분봉 단위로 착각해 `누적대금 / 분봉거래량`으로 tp를 계산 -> 첫봉 이후 tp가 실제 주가의 수백~수천 배 -> VWAP이 비정상 폭등 -> `close > VWAP` 조건 항상 False -> vwap_trade 0건, reversal_vwap 0건.

**영향**: vwap_trade 6건 (dynamic 3 + screener 3) + reversal_vwap 3건 (dynamic) = 9건 무효화. screener 3건은 BUG-1과 중복.

**수정 방향**: `amount` 컬럼의 의미를 DB에서 확인 후 `vwap()` 함수에서 분봉 단위인지 누적인지 분기 처리. 또는 fallback인 `(H+L+C)/3` 방식으로 강제 전환 (`amount` 컬럼 무시).

---

### BUG-3 (High) -- support_resistance / red_to_green 모든 universe에서 0건
**증거**: 코드 분석

`support_resistance/strategy.py:57`:
```python
prev = data.attrs.get("prev_day_ohlc") if hasattr(data, "attrs") else None
if not prev:
    return None  # attrs 없으면 즉시 종료
```

`red_to_green/strategy.py:52`:
```python
prev_close = data.attrs.get("prev_close") if hasattr(data, "attrs") else None
if prev_close is None:
    return None  # attrs 없으면 즉시 종료
```

**위치**: `backtest/engine.py` `_simulate_day_minute()` 메서드 (line 866-873)

```python
df_slice = df_up_to[df_up_to["datetime"] <= ts].copy()
if not df_slice.empty:
    sig = strategy.generate_signal(code, df_slice, timeframe="minute")
```

`run_minute()` 전체 (line 982-1172)에서 `minute_data` 로드 후 `prev_close` 또는 `prev_day_ohlc`를 `df.attrs`에 주입하는 코드가 전혀 없음. Grep 확인: `engine.py` 내 `prev_close`, `prev_day`, `attrs` 언급 0건.

**메커니즘**: 엔진이 전일 OHLC 데이터를 로드하거나 attrs에 주입하지 않으므로 두 전략은 항상 `return None`. 6건 (SR 3 + R2G 3, dynamic 기준) 모두 무효화.

**수정 방향**: `run_minute()` 내 일별 루프에서 `trade_date` 직전 거래일의 일봉 close/OHLC를 조회해 `minute_data[code].attrs['prev_close']`, `minute_data[code].attrs['prev_day_ohlc']`에 주입.

---

### BUG-4 (High) -- ORB / BullFlag 동적 universe에서 과잉 거래 (2800건)
**증거**: 실측

```
000250 (20260511): ORB 신호 99건 / 381봉
000250: 09:30~10:00 구간만 0건이지만 전체 구간 99번 신호
BullFlag 000990: 하루 7번 신호 / 389봉
ORB dynamic/pos5: 2770건 거래, total_pnl = -70.66%
```

**메커니즘**: 

ORB 전략 -- `or_high`는 09:00~09:30 고가로 당일 고정된다. 상승 추세 종목에서는 09:30 이후 매 분봉마다 `close > or_high`가 True. 엔진(`_simulate_day_minute`)은 포지션 보유 중에는 재매수를 막지만, SL/TP/EOD로 청산된 즉시 다음 분봉에서 다시 같은 종목 매수 시도. 282 dynamic 종목 x 99신호 x 5일이 max_positions cap에 걸려 결국 2770건.

BullFlag -- `flag_pattern()`이 매분 슬라이딩 윈도우 탐지로 누적 데이터에서 반복 True. 마찬가지로 청산 후 즉시 재진입.

**비용 계산**: 왕복 거래 비용 = 슬리피지(5bp) x2 + 수수료(0.015%) x2 + 거래세(0.18%) = 약 0.22% per trade. 2770건 x 0.22% = 609.4% 비용 (자본 대비). MDD -64%는 비용 누적의 직접 결과.

**수정 방향**: `_simulate_day_minute()`에 종목별 당일 최대 진입 횟수 제한 (예: `max_entries_per_code_per_day=1`). 또는 전략 레벨에서 "이미 오늘 진입했던 종목" 세트를 유지해 재진입 차단.

---

### 가설 A 검증 -- SL 1% / TP 2%가 분봉 ATR 대비 너무 좁은가?
**실측**: ATR(14분봉) 평균 0.202%, 일중 변동폭 평균 9.38%.

SL 1% = ATR의 5배 -> SL 자체는 오히려 **넓다**. 분봉 단위에서 -1%가 트리거되려면 ATR 기준 5배 움직임이 필요하므로 SL은 잘 터지지 않는다. TP 2%는 일중 변동폭 9.38% 대비 충분히 달성 가능한 수준. **SL/TP 자체는 1차 원인이 아님**.

단, BUG-4(과잉 거래)로 인해 매분 진입/EOD 청산이 반복되면 SL/TP 무관하게 비용만 누적된다는 점은 사실.

---

### 가설 D 검증 -- screener_snapshots 커버리지 4.8%
**실측**: 5/11~5/15 각 10건/일, 전략 = bb_reversion 단일. smoke 기간 5거래일 x 10건 = 50건. 전체 1347종목 대비 커버리지 = 10/1347 = 0.74%/일.

그러나 BUG-1(SQL 컬럼명 오류)로 인해 10건조차 전달되지 않았으므로, 커버리지 부족은 **이차적 문제**다. BUG-1 수정 후에도 screener는 bb_reversion 10종목만 후보로 공급되어 분봉 데이트레이딩 전략에는 부적합할 수 있다.

---

## 3. 권고 수정안

### P0 -- 필수 (재smoke 전에 반드시 수정)

**P0-1: screener provider SQL 컬럼명 수정**
- 파일: `scripts/run_intraday_tournament.py:111`
- 변경 전: `"WHERE snapshot_date = %s"`
- 변경 후: `"WHERE scan_date = %s"`
- 소요: 5분

**P0-2: vwap() 함수 amount 누적값 대응**
- 파일: `utils/intraday_indicators.py:29-35`
- 원인: `minute_candles.amount`는 당일 누적 거래대금
- 수정: `amount` 컬럼 분기에서 분봉 단위 여부 검증. 가장 빠른 수정은 fallback 조건 강화 -- 첫봉 기준으로 `amount[0]/volume[0]`이 `close[0]`의 2배를 초과하면 amount를 누적값으로 판정해 `(H+L+C)/3` fallback 사용.
- 또는: `vwap()` 함수에서 `amount` 컬럼을 항상 무시하고 `(H+L+C)/3` 방식만 사용 (단순, 안전).
- 소요: 30분

**P0-3: run_minute에서 prev_close / prev_day_ohlc attrs 주입**
- 파일: `backtest/engine.py` `run_minute()` 내 일별 루프 (line 1070 부근)
- 수정: 각 trade_date 처리 전, 직전 거래일의 일봉 close를 `daily_prices` 또는 `get_minute_prices_bulk` 첫봉 open 등으로 근사해 `minute_data[code].attrs['prev_close'] = prev_close_val` 및 `minute_data[code].attrs['prev_day_ohlc'] = {'high':..,'low':..,'close':..}` 주입.
- 소요: 2시간 (전일 일봉 로드 쿼리 추가 포함)

**P0-4: 종목별 당일 재진입 차단**
- 파일: `backtest/engine.py` `_simulate_day_minute()` (line 746~980)
- 수정: 메서드 시작 시 `entered_today: set = set()` 선언. 매수 성공 시 `entered_today.add(code)`. 매수 판단부에서 `if code in entered_today: continue` 추가.
- 소요: 30분

---

### P1 -- 권장 (P0 이후 2차 smoke)

**P1-1: SL/TP 그리드 확대**
현재 고정값 SL=1%, TP=2%를 그리드로 변환:
- SL: [0.5%, 1.0%, 2.0%, 3.0%]
- TP: [1.0%, 2.0%, 4.0%, 6.0%]
- trail: [None, 0.3%, 0.5%, 1.0%]
smoke에서는 중간값(SL 1%, TP 2%)부터 시작하되 P0 수정 후 ATR 대비 적정 비율 재측정 후 결정.

**P1-2: screener universe 범위 확대**
현재 `bb_reversion` 단일 전략 10종목/일은 데이트레이딩 후보풀로 부족. smoke 기간 커버리지: 10/1347 = 0.74%. dynamic universe(282종목)와 비교하면 3.5% 수준. 개선 방안:
- ATR 3%+ / 거래대금 100억+ 필터를 screener_snapshots에 bb_reversion 외 전략도 등록, 또는
- screener 후보가 5종목 미만인 날은 dynamic universe로 fallback.

**P1-3: vwap_trade / reversal_vwap 임계값 재검토**
BUG-2 수정 후 VWAP이 정상화되면 신호 발생 여부 재확인. `vol_zscore_threshold=1.0`이 너무 엄격하면 0.5로 완화, `deviation_pct=0.01`(1%)이 너무 좁으면 0.005로 완화.

---

### P2 -- 선택

**P2-1: tournament_results CSV 인코딩**
summary.md에 em dash(--) 문자가 있을 경우 일부 환경에서 깨짐. `_write_report_md()` 호출 시 `encoding='utf-8-sig'` 또는 대시 문자를 ASCII `-`로 치환.

**P2-2: screener_snapshots 전략별 토너먼트 매핑**
현재 `_make_screener_provider`는 전략명 무관하게 모든 `scan_date` 행을 반환. 인트라데이 10전략 각각에 맞는 screener snapshot이 없으므로 `bb_reversion` 후보를 공유하는 구조. 장기적으로는 데이트레이딩 전용 screener(거래대금/ATR 필터)를 별도 구축.

---

## 4. 재smoke 실행 명령

P0 4건 수정 완료 후:

```powershell
cd D:\GIT\kis-trading-template\RoboTrader_template
python scripts/run_intraday_tournament.py `
    --start 20260511 --end 20260515 `
    --capital 10000000 `
    --max-positions 3 4 5 `
    --universe screener,dynamic `
    --strategies all `
    --eod 15:20 `
    --slip-bps 5 `
    --out reports/tournament_smoke
```

예상 소요: 5거래일 x 282종목 x 60시나리오 = 약 20~40분 (Parquet 캐시 적중 시).

검증 기준:
- screener 30건: trade_count > 0 (bb_reversion 10종목 기준, 최소 1~5건/시나리오 예상)
- vwap_trade/reversal_vwap dynamic: trade_count > 0
- SR/R2G: trade_count > 0
- ORB/BullFlag dynamic: trade_count < 200/시나리오 (재진입 차단 효과)

---

## 5. 풀 토너먼트 일정 재추정

| 단계 | 현황 | 재추정 |
|------|------|--------|
| P0 버그 수정 | 0% | 3~4시간 (수정 + 단위 테스트) |
| 재smoke (5거래일) | 완료(오염) | 20~40분 |
| 풀 토너먼트 168거래일 | 미실행 | 4~12시간 (캐시 콜드스타트 포함) |
| P1 임계값 그리드 smoke | 미계획 | 1~2시간 (5거래일 x P1 그리드) |
| **합계** | | **8~18시간** |

현 페이스 기준 88시간 추정은 버그 미수정 상태의 반복 실행을 포함한 것. P0 수정 후에는 풀 토너먼트 단일 실행 4~12시간으로 단축 가능. 단, `daily_prices` 조회 API 추가(P0-3)로 인해 런타임이 10~20% 증가할 수 있음.

---

## 6. 참조 파일 및 라인

| 버그 | 파일 | 라인 |
|------|------|------|
| BUG-1 SQL | `scripts/run_intraday_tournament.py` | 111 |
| BUG-2 VWAP | `utils/intraday_indicators.py` | 29-35 |
| BUG-3 attrs 미주입 | `backtest/engine.py` | run_minute() (1070~) |
| BUG-4 재진입 | `backtest/engine.py` | _simulate_day_minute() (913~) |
| screener 스키마 | DB: `robotrader.screener_snapshots` | 컬럼: scan_date |
| dynamic universe | `utils/intraday_universe.py` | build_universe_for_date() |
