# Phase 1 분봉 데이트레이딩 인프라 완료 일지

작성일: 2026-05-16  
작성자: Phase 1E 통합 검토  
연관 계획: `C:\Users\sttgp\.claude\plans\0-5-1-5-quirky-bunny.md`

---

## 1. 개요

**Phase 1 (분봉 데이트레이딩 인프라)** 풀스택 구축 완료.

사장님 확정 사항: T+0 당일 청산, 가상자본 1,000만원, 동시 3~5종목, 포트폴리오 일 0.5~1.5% 수익률 목표.  
데이터 소스: `robotrader.minute_candles` 단일 (1,347종목 × 318일 × 5,116만행 × 10GB).  
인프라가 없는 상태(일봉 전용 백테스트)에서 출발하여 분봉 데이트레이딩 풀스택을 새로 구축.

---

## 2. 산출물 요약

| Phase | 단계 | 주요 산출물 | 신규 테스트 |
|-------|------|-------------|-------------|
| 1A | 분봉 데이터 로더 | `get_minute_prices`, `get_minute_prices_bulk`, `MinuteCache` (Parquet 디스크 캐시 + LRU 메모리 200MB) | 15 |
| 1B | BacktestEngine 분봉 모드 | `run_minute(...)` 신규 메서드, T+0/EOD/SL/TP/trail, `sells_by_reason` 4키 확장 | 23 |
| 1C | 분봉 지표 엔진 | `vwap`, `orb_levels`, `rsi_minute`, `ema_minute`, `bollinger_minute`, `volume_zscore`, `volume_surge`, `flag_pattern`, `pivot_sr_levels`, `red_to_green` 10함수 | 68 |
| 1D | 10개 전략 골격 | `IntradayBaseStrategy` + 10전략 (ABCDPattern/BullFlag/ReversalRSI/ReversalVWAP/MATrend/VWAPTrade/SupportResistance/RedToGreen/ORB/Pullback) | 59 |
| 1E | 통합 검토 | 본 changelog + screener 적합성 노트 | - |
| **합계** | | | **165개** (목표 100+ 초과 달성) |

---

## 3. 회귀 결과

| 구분 | passed | failed | 비고 |
|------|--------|--------|------|
| Phase 1 시작 전 기준선 | 1,300 | 1 (pre-existing) | test_screener_pipeline — 스크리너 JSON 만료 |
| **Phase 1 완료 후** | **1,861** | **1 (pre-existing)** | 동일 1건, 우리 변경 무관 |
| 순 증가 | **+561** | 0 신규 | |

pre-existing fail (`test_auto_resolve_latest_screener`) 은 스크리너 JSON 만료 환경 의존 이슈로 Phase 1과 무관. 건드리지 않음.

---

## 4. 변경/신규 파일 목록

### 수정 파일 (기존 파일 변경)

| 파일 절대경로 | 변경 내용 |
|---------------|-----------|
| `D:\GIT\kis-trading-template\RoboTrader_template\backtest\engine.py` | `run_minute()` 신규 메서드, T+0 EOD 청산, SL/TP/trail 분봉 트리거, `sells_by_reason` 4키 |
| `D:\GIT\kis-trading-template\RoboTrader_template\db\repositories\price.py` | `get_minute_prices()`, `get_minute_prices_bulk()` 신규, minute_candles 단일 소스 |
| `D:\GIT\kis-trading-template\RoboTrader_template\utils\unified_data_loader.py` | `load_minute_data` 스텁 → 실 구현 교체 |
| `D:\GIT\kis-trading-template\RoboTrader_template\pyproject.toml` | `slow` 마커 등록 (pytest markers) |

### 신규 모듈

| 파일 절대경로 | 역할 |
|---------------|------|
| `D:\GIT\kis-trading-template\RoboTrader_template\utils\minute_cache.py` | Parquet 디스크 캐시 (`cache/minute/{date}/{code}.parquet`) + LRU 메모리 200MB |
| `D:\GIT\kis-trading-template\RoboTrader_template\utils\intraday_indicators.py` | 분봉 지표 10함수 (pure functions, pandas 기반) |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\__init__.py` | 패키지 init |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\_base_intraday.py` | `IntradayBaseStrategy` — holding_period='intraday', SL/TP/eod_cutoff 표준화 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\abcd_pattern\` | ABCD 패턴 전략 (strategy.py + config.yaml + __init__.py) |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\bull_flag\` | 강세 깃발형 모멘텀 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\reversal_rsi\` | 분봉 RSI 극단 반전 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\reversal_vwap\` | VWAP 이탈 후 회귀 반전 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\ma_trend\` | 분봉 MA 골든/데드 추세 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\vwap_trade\` | VWAP 추세 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\support_resistance\` | 피벗 지지/저항 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\red_to_green\` | 전일 종가 회복 (R2G) 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\orb\` | 개장 30분 박스 돌파 (ORB) 전략 |
| `D:\GIT\kis-trading-template\RoboTrader_template\strategies\intraday\pullback\` | 눌림목 진입 전략 |

### 신규 테스트 파일

| 파일 절대경로 | 테스트 수 |
|---------------|-----------|
| `D:\GIT\kis-trading-template\RoboTrader_template\tests\test_minute_loader.py` | 15 |
| `D:\GIT\kis-trading-template\RoboTrader_template\tests\test_intraday_indicators.py` | 68 |
| `D:\GIT\kis-trading-template\RoboTrader_template\tests\test_backtest_engine_minute.py` | 23 |
| `D:\GIT\kis-trading-template\RoboTrader_template\tests\test_intraday_strategies_part_a.py` | 34 |
| `D:\GIT\kis-trading-template\RoboTrader_template\tests\test_intraday_strategies_part_b.py` | 25 |

---

## 5. 격리 이슈 메모

**현상**: Phase 1A 초기 구현 직후 기존 테스트 일부가 PriceRepository mock 충돌로 간헐적 실패.

**원인**: `test_minute_loader.py`가 PriceRepository를 패치할 때 모듈 캐시가 다른 테스트로 누출됨.

**조치**: `test_minute_loader.py`에 `autouse` fixture로 모듈 fresh import를 강제. `importlib.reload()` 또는 `sys.modules` 키 삭제 패턴 적용. 이후 격리 정상화, 전체 회귀 안정.

---

## 6. 다음 단계 (Phase 2 — 토너먼트 1라운드)

### Phase 2 착수 전 결재 필요 사항 (아래 §7 참조)

### Phase 2 작업 내용

1. **토너먼트 러너 신규**: `scripts/run_intraday_tournament.py`
   - 168 거래일 × 10전략 × 종목풀 순회
   - 예상 실행 시간: 4~12시간 (분봉 캐시 콜드스타트 별도 30~60분)
2. **평가 지표**: 평균 일일수익률, 일승률, Calmar, Sortino, MDD, 최대 일손실, 누적 PnL, 거래수
3. **합격선**: 일일수익률 ≥ 0.3% AND 일승률 ≥ 50% AND MDD ≤ 15%
4. **종합 점수**: 0.4 × 일수익률 + 0.3 × 일승률 + 0.3 × Calmar 정규화 → 상위 2~3개 + 사장님 와일드카드 1개
5. **산출물**: `reports/tournament_round1_YYYYMMDD.md` + `.parquet`

### Phase 2 종목풀 확정 필요

screener_snapshots 적합성 검토 결과 → 현재 **부적합** (8일치/4.8% 커버리지, bb_reversion 단일).  
상세: [note-2026-05-16-screener-intraday-fitness.md](note-2026-05-16-screener-intraday-fitness.md)  
권장: 옵션 2 (분봉 동적 스크리너 신규 구축, `scripts/build_intraday_universe.py`)

---

## 7. 사장님 결재 필요 사항

| # | 항목 | 선택지 | 현재 디폴트 |
|---|------|--------|-------------|
| **A** | **screener_snapshots 적합성 결정** | 옵션 1 (현재 8일, 빠름) / **옵션 2 권장** (동적 스크리너 신규, 1~2주) / 옵션 3 (병행) | 결재 대기 |
| **B** | 동시 보유 N 확정 | **3** / 4 / **5** (plan에서 3~5 범위 결재) | 3~5 (미확정) |
| **C** | EOD 청산 시각 | **15:20** (디폴트) / 다른 시각 | 15:20 OK |
| **D** | 슬리피지 | **5bp 고정** / 정밀화 (호가스프레드 데이터 필요) | 5bp OK |

- A 결재 후 Phase 2 착수
- B는 토너먼트 파라미터에서 그리드 변수로 포함 가능 (예: max_positions=[3,4,5])
