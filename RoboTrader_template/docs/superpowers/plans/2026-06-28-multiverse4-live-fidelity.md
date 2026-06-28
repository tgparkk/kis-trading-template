# MULTIVERSE4 라이브 정합 (유니버스 PIT + 사이징) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `multiverse4_returns_export.py`가 라이브 EOD 스크리너와 동일한 PIT 유니버스 + 라이브와 동일한 per-stock 사이징(자본÷K)으로 측정하도록 한다.

**Architecture:** 기존 검증 모듈 `backtest/screener_universe.py`(PIT 게이팅)를 `run_one`/`main`에 배선한다. 데이터 로드 유니버스를 전략별 스크리너 합집합으로 확장하고, 진입 신호캐시를 PIT 멤버십으로 게이팅하며, per-stock 매수금액을 `INITIAL/spec.K`로 산출한다. 모든 신규 seam은 reader/loader 주입형이라 DB 없이 단위테스트한다.

**Tech Stack:** Python 3.9, pytest, pandas. SSOT=robotrader_quant (측정 전용; 라이브 코드·DB 무변형).

## Global Constraints

- 라이브 매매 코드/DB/SSOT 변경 금지 — `scripts/multiverse4_returns_export.py` + `tests/test_multiverse4.py`만 수정.
- 신규 함수는 reader/loader 주입 인자를 받아 DB 없이 테스트 가능해야 한다(기존 test_multiverse4 스타일 = 토이데이터·순수함수).
- `INITIAL = 10_000_000.0` (전략당 가상자본, 기존 상수 재사용).
- scan 주기 = 월별. base_filter(시총·거래대금 플로어)까지 정합, `max_candidates=10/일`은 K+우선순위로 근사(복제 안 함).
- **git commit/push는 프로젝트 규칙상 사장님 확인 필요** — 각 Task의 commit 스텝은 실행하되, 최종 push/PR 전 관리자가 승인 취합. (커밋 메시지 끝에 Co-Authored-By 트레일러 부착)
- 미커밋 WIP(deep_mr 추가·시총백필, 브랜치 `feat/deepmr-wire-and-mcap-precision`)와 충돌 주의 — 동일 파일 수정이므로 현재 작업트리 기준으로 이어서 편집(덮어쓰기 금지).

---

### Task 1: 월별 scan_date 헬퍼

**Files:**
- Modify: `scripts/multiverse4_returns_export.py` (모듈 함수 추가, 메트릭 함수 근처)
- Test: `tests/test_multiverse4.py`

**Interfaces:**
- Produces: `_monthly_scan_dates(start: str, end: str) -> List[str]` — `[start, end]`(YYYY-MM-DD) 구간을 월별 1개 scan_date(각 월의 마지막 캘린더일, 단 end 월은 end 자신)로 반환. 정렬 오름차순. start/end 자신 포함.

- [ ] **Step 1: Write the failing test**

```python
def test_monthly_scan_dates_basic():
    from scripts.multiverse4_returns_export import _monthly_scan_dates
    out = _monthly_scan_dates("2024-01-15", "2024-04-10")
    # 시작월은 start 자신, 중간월은 말일, 종료월은 end 자신
    assert out[0] == "2024-01-15"
    assert "2024-02-29" in out          # 2024 윤년 2월 말일
    assert "2024-03-31" in out
    assert out[-1] == "2024-04-10"
    assert out == sorted(out)
    assert len(out) == len(set(out))    # 중복 없음
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multiverse4.py::test_monthly_scan_dates_basic -v`
Expected: FAIL — `ImportError: cannot import name '_monthly_scan_dates'`

- [ ] **Step 3: Write minimal implementation**

`scripts/multiverse4_returns_export.py` 의 `_maxdd` 정의 다음 줄에 추가:

```python
def _monthly_scan_dates(start: str, end: str) -> List[str]:
    """[start, end] 를 월별 scan_date 로 분해. 시작월=start, 종료월=end, 중간월=말일.

    시총/거래대금은 완만 변화 → 월별 근사로 충분(모듈 권장). get_universe_snapshot 의
    date<=scan_date 방어 폴백이 캘린더 말일/거래일 차이를 흡수한다.
    """
    s = pd.Timestamp(start[:10])
    e = pd.Timestamp(end[:10])
    if e < s:
        return [start[:10]]
    # 각 월말(MonthEnd) + 시작/종료 경계
    month_ends = pd.date_range(s, e, freq="ME")  # pandas>=2.2: 'ME'(월말)
    dates = {s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")}
    for d in month_ends:
        if s <= d <= e:
            dates.add(d.strftime("%Y-%m-%d"))
    return sorted(dates)
```

(주: pandas 버전이 'ME' 미지원이면 'M' 으로 폴백 — 실행 환경 pandas 버전 확인 후 택1.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multiverse4.py::test_monthly_scan_dates_basic -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add RoboTrader_template/scripts/multiverse4_returns_export.py RoboTrader_template/tests/test_multiverse4.py
git commit -m "feat(mv4): add _monthly_scan_dates helper for PIT screener cadence"
```

---

### Task 2: per-stock 사이징 = INITIAL/K

**Files:**
- Modify: `scripts/multiverse4_returns_export.py` — `run_one` 시그니처/본문, `MAX_PER_STOCK` 주석
- Test: `tests/test_multiverse4.py`

**Interfaces:**
- Consumes: `INITIAL`, `StrategySpec.K`.
- Produces: `run_one(spec, data, turnover, max_per_stock=None, resolver=None)` — `max_per_stock is None` 이면 `INITIAL/spec.K` 사용. (`resolver` 는 Task 3 에서 사용; 본 Task 에선 인자만 추가하고 무시 가능하나 시그니처는 최종형으로 둔다.)
- `_per_stock_amount(spec, override: Optional[float]) -> float` — `override if override is not None else INITIAL/spec.K`.

- [ ] **Step 1: Write the failing test**

```python
def test_per_stock_amount_is_capital_over_k():
    from scripts.multiverse4_returns_export import _per_stock_amount, SPECS, INITIAL
    # elder K=20 → 50만, minervini K=3 → 약 333.3만, daytrading K=5 → 200만
    assert _per_stock_amount(SPECS["elder_ema_pullback"], None) == pytest.approx(INITIAL / 20)
    assert _per_stock_amount(SPECS["minervini_volume_dryup"], None) == pytest.approx(INITIAL / 3)
    assert _per_stock_amount(SPECS["daytrading_3methods_breakout"], None) == pytest.approx(INITIAL / 5)
    # 명시 override 는 그대로
    assert _per_stock_amount(SPECS["elder_ema_pullback"], 1_000_000.0) == pytest.approx(1_000_000.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multiverse4.py::test_per_stock_amount_is_capital_over_k -v`
Expected: FAIL — `ImportError: cannot import name '_per_stock_amount'`

- [ ] **Step 3: Write minimal implementation**

`run_one` 바로 위에 추가:

```python
def _per_stock_amount(spec: StrategySpec, override: Optional[float]) -> float:
    """라이브 정합 per-stock 매수금액 = INITIAL/K (라이브 main.py allocate_strategy_capital
    → virtual_trading_manager.get_max_quantity 와 동일). override 지정 시 그 값(민감도용)."""
    if override is not None:
        return float(override)
    return INITIAL / float(spec.K)
```

`run_one` 시그니처/본문 수정:

```python
def run_one(spec: StrategySpec, data: Dict[str, pd.DataFrame],
            turnover: Dict[str, float],
            max_per_stock: Optional[float] = None,
            resolver=None) -> dict:
    cache = spec.build_signals(data)
    if resolver is not None:                              # Task 3 에서 활성
        from backtest.screener_universe import pit_gate_signal_cache
        cache = pit_gate_signal_cache(cache, data, resolver)
    n_sig = sum(len(v) for v in cache.values())
    per_stock = _per_stock_amount(spec, max_per_stock)
    res = run_portfolio(data=data, signal_cache=cache, adapter=spec.adapter,
                        params=spec.params, turnover=turnover,
                        initial_capital=INITIAL, max_positions=spec.K,
                        max_per_stock=per_stock)
    # ... (이하 기존 본문 동일: dr/eq/sells/return) ...
```

`MAX_PER_STOCK` 상수 주석(L75-79) 정정:

```python
# 라이브 per-stock 매수금액 = INITIAL/K (전략별; 라이브 자본÷K 정합, 2026-06-11 K-split).
# 과거 주석의 "고정 100만"은 stale(K-split 이전). 아래 상수는 --max-per-stock 기본/민감도용.
MAX_PER_STOCK = 1_000_000.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multiverse4.py::test_per_stock_amount_is_capital_over_k -v`
Expected: PASS

- [ ] **Step 5: Run full multiverse4 test to check no regression**

Run: `python -m pytest tests/test_multiverse4.py -v`
Expected: PASS (기존 테스트 포함)

- [ ] **Step 6: Commit**

```bash
git add RoboTrader_template/scripts/multiverse4_returns_export.py RoboTrader_template/tests/test_multiverse4.py
git commit -m "feat(mv4): per-stock sizing = INITIAL/K (live fidelity), fix stale 1M comment"
```

---

### Task 3: run_one PIT 게이팅 (주입형 resolver)

**Files:**
- Modify: `scripts/multiverse4_returns_export.py` — `run_one` (Task 2 에서 추가한 resolver 분기 검증)
- Test: `tests/test_multiverse4.py`

**Interfaces:**
- Consumes: `backtest.screener_universe.pit_gate_signal_cache(signal_cache, data, resolver)` (기존, 테스트됨); `resolver: (code:str, bar_date) -> bool`.
- Produces: `run_one(..., resolver=<callable>)` 가 build_signals 산출 캐시를 resolver 로 게이팅한 뒤 시뮬레이션.

- [ ] **Step 1: Write the failing test**

```python
def test_run_one_applies_pit_resolver():
    """resolver 가 특정 종목을 미적격 처리하면 그 종목 신호가 제거되어 매매되지 않는다."""
    from scripts.multiverse4_returns_export import run_one, StrategySpec
    from scripts.book_portfolio_multiverse import _SLTPMHAdapter

    n = 8
    def mk_df():
        return pd.DataFrame({
            "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": [100.0] * 3 + [120.0] * 5,
            "high": [121.0] * n, "low": [99.0] * n,
            "close": [100.0] * 3 + [120.0] * 5,
            "volume": [1000.0] * n,
        })
    data = {"AAA": mk_df(), "BBB": mk_df()}

    # build_signals 를 고정 캐시로 대체(룰/DB 비의존): 두 종목 모두 i=2 진입신호
    spec = StrategySpec(
        name="toy", warmup=0, K=2,
        params=dict(stop_loss_pct=0.5, take_profit_pct=0.10, max_hold_bars=99),
        adapter=_SLTPMHAdapter(),
        build_signals=lambda d: {"AAA": [2], "BBB": [2]},
    )
    turnover = {"AAA": 1.0, "BBB": 1.0}

    # AAA 만 적격(BBB 미적격)인 resolver
    resolver = lambda code, d: code == "AAA"

    r_all = run_one(spec, data, turnover, max_per_stock=10_000_000.0, resolver=None)
    r_gated = run_one(spec, data, turnover, max_per_stock=10_000_000.0, resolver=resolver)

    sells_all = {t["stock_code"] for t in r_all["trades"] if t["side"] == "sell"}
    sells_gated = {t["stock_code"] for t in r_gated["trades"] if t["side"] == "sell"}
    assert "BBB" in sells_all            # 게이트 없으면 둘 다 매매
    assert sells_gated == {"AAA"}        # 게이트 후 BBB 신호 제거 → AAA 만
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multiverse4.py::test_run_one_applies_pit_resolver -v`
Expected: FAIL (Task 2 에서 resolver 분기를 이미 넣었다면 PASS 가능 — 그 경우 이 Task 는 회귀 가드로 확정. 미반영이면 resolver 무시되어 `sells_gated == {"AAA","BBB"}` 로 FAIL)

- [ ] **Step 3: Confirm/complete implementation**

Task 2 의 `run_one` resolver 분기(`if resolver is not None: cache = pit_gate_signal_cache(...)`)가 적용돼 있는지 확인. 누락 시 추가.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multiverse4.py::test_run_one_applies_pit_resolver -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add RoboTrader_template/tests/test_multiverse4.py RoboTrader_template/scripts/multiverse4_returns_export.py
git commit -m "feat(mv4): gate run_one entry cache by injected PIT resolver"
```

---

### Task 4: main() — 전략별 스크리너 합집합 데이터 로드 + resolver 배선

**Files:**
- Modify: `scripts/multiverse4_returns_export.py` — `main()` 데이터 로드/실행 루프, 신규 헬퍼 `_load_strategy_universe_data`
- Test: `tests/test_multiverse4.py`

**Interfaces:**
- Consumes: `backtest.screener_universe.load_screener_universe_range(strategy, start, end, reader=...) -> Dict[date,List[str]]`; `make_scan_eligible_resolver(strategy, scan_dates, reader=...) -> callable`; `_load_daily_adj(codes, start, end)`; `_monthly_scan_dates`.
- Produces: `_load_strategy_universe_data(spec, start, end, scan_dates, reader, range_fn=load_screener_universe_range, load_daily_fn=_load_daily_adj) -> Tuple[Dict[str,pd.DataFrame], Dict[str,float]]` — 스크리너 합집합 종목의 일봉 데이터 + turnover 맵.

- [ ] **Step 1: Write the failing test**

```python
def test_load_strategy_universe_data_unions_screener(monkeypatch):
    """데이터 로드 유니버스 = 스크리너 일자별 통과집합의 합집합 (top-volume 정적 아님)."""
    from scripts.multiverse4_returns_export import _load_strategy_universe_data, SPECS

    # range_fn: 날짜별 통과집합 (합집합 = {AAA, BBB, CCC})
    def fake_range(strategy, start, end, reader=None):
        return {"2024-01-31": ["AAA", "BBB"], "2024-02-29": ["BBB", "CCC"]}

    loaded_codes = {}
    def fake_load_daily(codes, start, end):
        loaded_codes["arg"] = list(codes)
        # 토이 일봉
        import pandas as pd
        return {c: pd.DataFrame({
            "datetime": pd.date_range("2024-01-01", periods=3, freq="D"),
            "open": [1.0, 1.0, 1.0], "high": [1.0, 1.0, 1.0],
            "low": [1.0, 1.0, 1.0], "close": [1.0, 2.0, 3.0],
            "volume": [10.0, 10.0, 10.0]}) for c in codes}

    data, turnover = _load_strategy_universe_data(
        SPECS["minervini_volume_dryup"], "2024-01-01", "2024-02-29",
        ["2024-01-31", "2024-02-29"], reader=object(),
        range_fn=fake_range, load_daily_fn=fake_load_daily)

    assert set(loaded_codes["arg"]) == {"AAA", "BBB", "CCC"}   # 합집합 로드
    assert set(data.keys()) == {"AAA", "BBB", "CCC"}
    assert set(turnover.keys()) == {"AAA", "BBB", "CCC"}       # turnover 도 union 기준
    assert all(v > 0 for v in turnover.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multiverse4.py::test_load_strategy_universe_data_unions_screener -v`
Expected: FAIL — `ImportError: cannot import name '_load_strategy_universe_data'`

- [ ] **Step 3: Write minimal implementation**

상단 import 에 추가:

```python
from backtest.screener_universe import (  # noqa: E402
    load_screener_universe_range, make_scan_eligible_resolver,
)
```

신규 헬퍼 추가(`run_one` 위):

```python
def _load_strategy_universe_data(spec, start, end, scan_dates, reader,
                                 range_fn=None, load_daily_fn=None):
    """전략별 라이브 스크리너 합집합 종목의 일봉 + turnover. (PIT 유니버스 정합)"""
    if range_fn is None:
        range_fn = load_screener_universe_range
    if load_daily_fn is None:
        load_daily_fn = _load_daily_adj
    by_date = range_fn(spec.name, start, end, reader=reader)
    union = sorted({c for codes in by_date.values() for c in codes})
    data = load_daily_fn(union, start, end)
    turnover = {c: float((df["close"] * df["volume"]).sum()) for c, df in data.items()}
    return data, turnover
```

`main()` 수정 — 기존 `_get_data(top_n)` 공유 캐시 경로를 전략별 로드로 교체:

```python
    reader = None  # QuantDailyReader 지연 생성 (실행시 1회)
    summary_rows = []
    with _patch_costs(args.commission, args.tax, args.slippage):
        for name in args.strategies:
            spec = SPECS[name]
            scan_dates = _monthly_scan_dates(start, end)
            if reader is None:
                from db.quant_daily_reader import QuantDailyReader
                reader = QuantDailyReader()
            data, turnover = _load_strategy_universe_data(spec, start, end, scan_dates, reader)
            resolver = make_scan_eligible_resolver(spec.name, scan_dates, reader=reader)
            per_stock = args.max_per_stock if args.max_per_stock != MAX_PER_STOCK else None
            print(f"[run] {name} (K={spec.K}, universe={len(data)}, "
                  f"per_stock={_per_stock_amount(spec, per_stock):,.0f}) ...")
            r = run_one(spec, data, turnover, max_per_stock=per_stock, resolver=resolver)
            # ... (이하 기존 df_out 저장/summary append 동일) ...
```

`--smoke`/`top_n`/`_get_data`/`data_by_topn` 정적 로드 블록 및 `_load_top_volume_daily` import 는 본 산출 경로에서 제거(다른 스크립트가 쓰면 import 는 보존). `--smoke` 는 `scan_dates` 를 시작/끝 2개로 축소하는 의미로 재정의하거나 제거 — 최소구현은 제거하고 README/usage 주석 갱신.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multiverse4.py::test_load_strategy_universe_data_unions_screener -v`
Expected: PASS

- [ ] **Step 5: Run full file test**

Run: `python -m pytest tests/test_multiverse4.py -v`
Expected: PASS (전체)

- [ ] **Step 6: Lint**

Run: `ruff check RoboTrader_template/scripts/multiverse4_returns_export.py`
Expected: 통과(미사용 import 정리 포함)

- [ ] **Step 7: Commit**

```bash
git add RoboTrader_template/scripts/multiverse4_returns_export.py RoboTrader_template/tests/test_multiverse4.py
git commit -m "feat(mv4): load per-strategy screener-union universe + wire PIT resolver in main"
```

---

### Task 5: 스모크 실증 (DB 실행 — 측정 정합 확인)

**Files:** (코드 변경 없음 — 실행 검증)

**Interfaces:** Consumes: 완성된 `multiverse4_returns_export.py`.

- [ ] **Step 1: 단일 전략 단기 스모크 실행**

Run:
```bash
cd RoboTrader_template && python scripts/multiverse4_returns_export.py \
  --strategies minervini_volume_dryup --start 2024-01-01 --end 2024-06-30 \
  --out D:/tmp/mv4_pit_smoke
```
Expected: 로그에 `universe=<스크리너 통과 종목수>`(거래대금 top-50 정적 아님), `per_stock` 가 `INITIAL/K`(≈3,333,333) 로 출력. `D:/tmp/mv4_pit_smoke/minervini_volume_dryup.csv` 생성.

- [ ] **Step 2: 산출물 정합 점검**

`minervini_volume_dryup_trades.csv` 의 매수 종목이 해당 시점 시총≥3천억 종목인지 표본 확인(라이브 스크리너 멤버십). 거래대금 top-50 외 종목이 포함될 수 있음(정상 — PIT 스크리너 유니버스).

- [ ] **Step 3: 결과 기록**

`memory/` 에 changelog 작성: PIT 정합 전/후 minervini Sharpe·MaxDD 비교(특히 사이징 자본/K 적용으로 DD 확대 여부), daytrading 유니버스 변화. (별도 관리자 보고)

---

## Self-Review

**Spec coverage:**
- 유니버스 PIT 게이팅 → Task 3(게이팅 적용) + Task 4(데이터 union·resolver 배선) ✅
- 데이터 로드 union 확장 → Task 4 ✅
- 사이징 INITIAL/K → Task 2 ✅
- stale 주석 정정 → Task 2 ✅
- TDD 테스트 4종(scan_dates·sizing·gating·union) → Task 1~4 ✅
- 근사 명시(월별·base_filter) → Task 1 주석, spec §5 ✅
- 실증/산출물 영향 → Task 5 ✅

**Placeholder scan:** 모든 코드 스텝에 실제 코드 포함. "기존 본문 동일" 표기는 수정 비대상 라인 보존 지시(전체 재작성 방지)이며 신규/변경 코드는 전부 명시. ✅

**Type consistency:** `run_one(spec, data, turnover, max_per_stock=None, resolver=None)` 시그니처가 Task 2/3/4 에서 일관. `_per_stock_amount(spec, override)`·`_monthly_scan_dates(start,end)`·`_load_strategy_universe_data(...)` 시그니처 Task 간 일치. `pit_gate_signal_cache`/`make_scan_eligible_resolver`/`load_screener_universe_range` 는 `backtest/screener_universe.py` 기존 시그니처와 일치. ✅

**알려진 의존성/주의:**
- pandas 'ME'(월말) freq — 환경 pandas 버전 확인(>=2.2). 구버전이면 'M'.
- `make_scan_eligible_resolver`/`load_screener_universe_range` 는 `runners._adapter_factory.build_adapter` 가 대상 전 전략 지원해야 함(정직본 baseline 경로에서 검증됨).
- WIP(deep_mr·시총백필) 작업트리 위에서 편집 — 덮어쓰기 금지, 현 내용에 이어서 수정.
