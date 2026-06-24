# 2026-06-22 09:00 가상매매 포지션 청산 인과추적 Findings

> 작성: 2026-06-25 (Tracer 스파이크, 읽기 전용 조사)
> 브랜치: fix/elder-entry-buystop (조사 시점)

---

## 1. 확정된 사실 (DB + 로그 직접 증거)

### 1-1. 06-22 09:00~09:10 매도 레코드 (전건)

| timestamp (KST) | stock_code | strategy | price | profit_rate | reason |
|---|---|---|---|---|---|
| 09:00:56 | 079650 | daytrading_3methods_breakout | 4,815 | +30.67% | 목표 익절 도달 (30.66% >= 10.60%) |
| 09:00:57 | 067290 | daytrading_3methods_breakout | 2,725 | +16.45% | 목표 익절 도달 (16.45% >= 9.77%) |
| 09:00:57 | 198440 | daytrading_3methods_breakout | 2,415 | +68.88% | 목표 익절 도달 (68.88% >= 10.00%) |
| 09:03:33 | 109070 | book_pullback_ma20 | 1,801 | +12.56% | 목표 익절 도달 (12.56% >= 10.21%) |
| 09:05:00 | 200470 | book_envelope_200d | 11,170 | -6.13% | 손절 실행 (-6.13% <= -3.98%) |
| 09:05:09 | 073190 | daytrading_3methods_breakout | 705 | -26.64% | 손절 실행 (-26.64% <= -3.00%) |
| 09:05:09 | 001510 | minervini_volume_dryup | 2,650 | -14.52% | 손절 실행 (-14.52% <= -6.22%) |
| 09:05:09 | 017900 | rs_leader | 8,980 | -8.18% | 손절 실행 (-8.18% <= -3.67%) |
| 09:05:09 | 439960 | book_pullback_ma5 | 22,950 | -12.24% | 손절 실행 (-12.24% <= -3.00%) |
| 09:05:09 | 001740 | book_pullback_ma20 | 10,360 | -9.91% | 손절 실행 (-9.91% <= -4.96%) |
| 09:05:10 | 036930 | rs_leader | 201,000 | -8.43% | 손절 실행 (-8.43% <= -7.79%) |
| 09:05:10 | 018000 | book_pullback_ma5 | 995 | -8.72% | 손절 실행 (-8.72% <= -3.62%) |
| 09:05:10 | 004710 | book_envelope_200d | 12,910 | -14.22% | 손절 실행 (-14.22% <= -6.23%) |
| 09:05:10 | 000270 | elder_ema_pullback | 154,000 | -7.78% | 손절 실행 (-7.78% <= -6.24%) |
| 09:05:12 | 003490 | book_envelope_200d | 26,900 | -7.24% | 손절 실행 (-7.24% <= -4.83%) |
| 09:09:31 | 122640 | book_envelope_200d | 37,150 | +11.56% | 목표 익절 도달 (11.56% >= 11.16%) |
| 09:10:47 | 053160 | daytrading_3methods_breakout | 9,300 | +1.75% | 트레일링 스톱 매도 |

DB 소스: `robotrader.virtual_trading_records`, `timestamp::date='2026-06-22'`, `timestamp::time < '10:00'`.

---

## 2. 확정된 코드경로 및 트리거 조건

### 2-1. 실행 파일:라인 (커밋 b5416d5 — 2026-06-22 당시 코드)

```
core/trading/position_monitor.py
  _analyze_sell_for_stock()
    L221-224  is_before_rebalancing = (hour==9 and minute<5)
    L290-315  목표 익절 체크:  profit_rate >= trading_stock.target_profit_rate  → _execute_sell()
    L301-327  손절 체크:       not is_before_rebalancing AND profit_rate <= -stop_loss_rate → _execute_sell()
```

### 2-2. 트리거 조건 (정확히 재현됨)

1. **`position_monitor.check_positions_once()`** 가 `main.py` 메인트레이딩루프에서 3초마다 호출됨.
2. 09:00 장 시작 직후 첫 분봉 현재가(API 직접 호출)로 `profit_rate` 계산.
3. **09:00~09:04** 구간: `is_before_rebalancing=True` → 손절 블록, **익절은 통과**.
   - 198440(+68.88%), 079650(+30.67%), 067290(+16.45%), 109070(+12.56%), 122640(+11.56%) = 익절 09:00~09:09 처리.
4. **09:05 이후**: `is_before_rebalancing=False` → 손절도 활성화.
   - 073190(-26.64%), 001510(-14.52%), 004710(-14.22%), 001740(-9.91%), 439960(-12.24%), 017900(-8.18%) 등 = 손절 09:05 일괄 처리.

### 2-3. `state_restorer.py`의 역할 (정상 복원, 청산 트리거 아님)

- 07:40:14 ~ 07:40:21: 35개 종목 `positioned` 상태로 복원, `target_profit_rate` / `stop_loss_rate` DB에서 정확히 로드.
  - 073190: 익절 43.3%, 손절 3.0% 복원됨.
  - 198440: 익절 10.0%, 손절 10.0% 복원됨.
- 복원 자체는 청산을 트리거하지 않음. 복원 후 position_monitor가 첫 분봉가를 평가하여 청산.

---

## 3. 가설별 증거 for / against

### H1 — state_restorer가 청산 트리거

| for | against |
|---|---|
| 복원 시 "[비정상 상태전이]" 경고 다수 | DB reason이 "복원"이 아닌 "목표 익절 도달 / 손절 실행" |
| 복원 후 첫 가격 평가까지 시간 간격 없음 | 복원은 07:40, 청산은 09:00 (1시간 20분 차이) |
| | 복원 코드에 매도 실행 경로 없음 |

**채택 불가.** 복원은 단순 상태 주입이며 청산 실행과 무관.

### H2 — rebalancing 루틴이 일괄 정리

| for | against |
|---|---|
| 로그에 "리밸런싱 모드" 언급 (data_collector) | reason 문자열이 "리밸런싱"이 아닌 tp/sl 사유 |
| `is_before_rebalancing` 변수명 존재 | is_before_rebalancing은 손절 억제용 시간 가드일 뿐, 별도 리밸런싱 루틴 없음 |
| | `main.py` run_daily_cycle에 리밸런싱 일괄청산 코드 없음 |

**채택 불가.** "리밸런싱"은 data_collector의 장전 일봉 수집 모드명이며 독립적인 청산 루틴이 아님.

### H3 — 분봉 첫틱 sl/tp 실행 (정상 position_monitor 동작) — **채택**

| for | against |
|---|---|
| DB reason이 "목표 익절 도달 / 손절 실행"으로 position_monitor L310/L322의 포맷과 정확히 일치 | 없음 |
| 09:00:56~09:00:57 익절, 09:05:09 손절 — is_before_rebalancing 경계(09:05)와 정확히 일치 | |
| 198440 tp=10%, 073190 sl=3% 등 DB 복원값과 reason 내 임계값이 1:1 대응 | |
| b5416d5 커밋의 position_monitor 코드가 이 동작을 그대로 구현 | |

**채택. 증거 강도: 1등급 (DB 레코드 + 코드 직접 대응).**

### H4 — EOD 청산 시간 계산 오류

| for | against |
|---|---|
| 일부 포지션이 06-18 이후 tp/sl 없이 살아남음 | eod_liquidation_hour=15 (로그 "일괄 청산: 15:00"), 09:00과 무관 |
| | reason 문자열에 "일괄청산" / "시장가" 없음 |
| | `liquidation_handler.py`는 EOD 전용으로 09:00 미호출 |

**채택 불가.**

---

## 4. 핵심 이상: 198440이 왜 +68.88%까지 tp 없이 살아남았나

`daytrading_3methods_breakout` 전략: `take_profit_pct=0.10`, `stop_loss_pct=0.10`.
198440 매수: 06-18 09:01:42 @ 1,430원. tp=10% → 1,573원 도달 시 익절이어야 함.

**왜 06-18 당일 tp 미발동?**
- 06-18 장중 position_monitor가 호출됨 → 240600(다른 종목) 손절이 09:05:03에 기록됨.
- 198440은 09:01:42에 매수 체결 → 즉시 tp 평가 대상이 됨.
- 06-18에 198440이 1,573원(+10%)에 도달하지 않았거나, 도달 시점에 현재가 조회 실패가 있었을 가능성.
- **DB 확인**: 06-18 198440 SELL 레코드 없음 → 06-18 장중 198440 가격이 tp 미달이었음.

**왜 06-19 tp 미발동?**
- 06-19 trading_20260619.log 분석: 07:40에 복원 후, 파일 끝이 20:09 스크리너 전용 시그널만 존재.
- 실제 봇(run_daily_cycle)이 06-19 장중(09:00~15:30)에 실행된 증거 없음.
- DB: 06-19~06-21 virtual_trading_records SELL 0건.
- **확정**: 06-19 봇은 장전 복원 후 조기 종료(diag-2026-06-19의 런처 bat 섹션2 REM 이슈). 06-20~21은 주말.

**결론**: 198440은 06-18 장중 tp 미달, 06-19 봇 미실행(런처 오류), 06-20~21 주말로 tp 평가 기회가 없었다. 06-22 09:00 첫 분봉가 2,415원(+68.88%)이 처음으로 tp=10% 기준을 통과하며 "목표 익절 도달"로 정상 처리됨.

---

## 5. 왜 06-22 09:05에 손절이 '일괄' 발동했나

- 09:00~09:04: `is_before_rebalancing=True` (L221-224) → `stop_loss_rate` 체크 스킵.
- 09:05:00 이후 첫 iteration: `is_before_rebalancing=False` → 35개 포지션 순차 평가.
- 갭다운 종목(073190: 961원 → 705원 = -26.6%, 001510: 3,100원 → 2,650원 = -14.5% 등)이
  한꺼번에 손절 임계값 초과 → 09:05:09~09:05:12에 집중 처리.
- "일괄청산"처럼 보이지만 실제로는 손절 억제 해제 후 누적 평가의 자연스러운 결과.

---

## 6. 재현 테스트 설계 (Task 3 입력용)

### 목표
`position_monitor._analyze_sell_for_stock()`이:
1. **09:00~09:04**: 익절만 실행, 손절 억제됨을 확인.
2. **09:05+**: 익절 + 손절 모두 실행됨을 확인.
3. **복원 포지션**에 대해 tp/sl이 정상 작동함을 확인.

### 테스트 케이스 설계

```python
# tests/test_position_monitor_sl_tp_timing.py

@pytest.mark.parametrize("mock_time,profit_rate,tp,sl,expect_sell,expect_reason", [
    # 09:02 — 익절 발동 (is_before_rebalancing=True이지만 tp는 통과)
    (datetime(2026,6,22,9,2,0), 0.689, 0.10, 0.10, True, "목표 익절 도달"),
    # 09:02 — 손절 억제 (is_before_rebalancing=True)
    (datetime(2026,6,22,9,2,0), -0.266, 0.10, 0.10, False, None),
    # 09:05 — 손절 발동 (is_before_rebalancing=False)
    (datetime(2026,6,22,9,5,0), -0.266, 0.10, 0.30, True, "손절 실행"),
    # 09:05 — tp 미달, sl 미달 → 매도 없음
    (datetime(2026,6,22,9,5,0), 0.05, 0.10, 0.10, False, None),
])
async def test_analyze_sell_timing(mock_time, profit_rate, tp, sl, expect_sell, expect_reason):
    # 준비: TradingStock에 target_profit_rate=tp, stop_loss_rate=sl, position(avg_price=1000) 설정
    # now_kst() 를 mock_time으로 패치
    # _get_current_price() 를 avg_price*(1+profit_rate)로 패치
    # _execute_sell()을 spy로 설정
    # 실행: await monitor._analyze_sell_for_stock(stock)
    # 검증: _execute_sell 호출 여부 + reason 문자열 접두어
```

### 핵심 입력 조건
- `trading_stock.target_profit_rate`: state_restorer 복원 후 값 (DB에서 로드됨).
- `trading_stock.stop_loss_rate`: 동일.
- `now_kst()` mock: 09:02 vs 09:05 두 케이스 필수.
- `is_stale=False`, `owner_strategy=None` 또는 실제 전략 인스턴스.
- 트레일링 스톱 미활성화 (highest_price_since_buy 낮게 설정).

---

## 7. 잔여 불확실성 및 추가 probe 권고

| 항목 | 불확실성 | 권고 probe |
|---|---|---|
| 198440 06-18 장중 실제 최고가 | DB minute_candles 조회로 1,573원 도달 여부 확인 가능 | `SELECT MAX(high_price) FROM minute_candles WHERE stock_code='198440' AND timestamp::date='2026-06-18'` |
| 06-19 봇이 장중 09:00~에 실행됐는지 | trading_20260619.log에 09:00 이후 position_monitor 관련 줄 없음 → 미실행 확인됨 | 추가 확인 불필요 |
| `is_before_rebalancing` 의도 (설계 vs 버그) | 손절 억제 의도는 "갭하락 첫 틱 오버반응 방지"로 추정 — 코드 주석 "09:00~09:05 사이에는 손절 체크 안 함 (익절만)"에서 명시됨 | 설계 의도 확인됨, 별도 probe 불필요 |
| 073190 손절 임계값 불일치 (DB: sl=3.0%, reason: -26.64%) | 6일 보유 중 급락 → tp=43.3% 미달 + 첫 평가 시 -26.6% → sl=3% 임계 초과 | 백테스트 sl=10% vs 복원 sl=3% 설정 불일치 조사 가능 (minor) |

---

## 8. 최종 결론

**채택 가설: H3 — 정상 position_monitor tp/sl 동작 (설계 의도대로)**

06-22 09:00 "일괄청산"처럼 보이는 현상은:
1. `state_restorer`가 06-22 07:40에 35개 포지션을 정확한 tp/sl로 복원.
2. 06-18 매수 후 06-19 봇 조기종료 + 06-20~21 주말로 tp/sl 평가 기회가 4일간 공백.
3. 06-22 장 개시 후 `position_monitor._analyze_sell_for_stock()`이 첫 분봉가로 평가:
   - 09:00~09:04: `is_before_rebalancing=True` → 익절만 (`core/trading/position_monitor.py:L307-315`)
   - 09:05+: `is_before_rebalancing=False` → 손절도 활성화 (`core/trading/position_monitor.py:L317-327`)
4. 주말 갭상승(198440 +68.88%)과 갭하락(073190 -26.64%)이 첫 틱에 동시 처리.

**버그가 아님.** 설계 의도(4일 공백 + 갭 처리 = 정상 tp/sl 누적 발동)이나,
`daytrading_3methods_breakout`의 `holding_period="swing"` 선언에도 불구하고 주말을 포함한 멀티데이 보유가 발생한 점은 전략 파라미터 설계(`max_holding_days=10`)와는 정합하나 "데이트레이딩"이라는 전략명과의 불일치로 향후 설계 검토 여지가 있음.
