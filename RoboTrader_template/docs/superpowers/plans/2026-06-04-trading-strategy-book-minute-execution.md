# Book 19 『트레이딩 전략서』 분봉 실행층 3전략 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 『트레이딩 전략서』 노트의 분봉 실행층 3전략(가격박스·볼린저밴드·눌림목 캔들)의 **진입 신호**를 사장님 확정 임계값으로 `rules.py`에 코드화하고, 정본 분봉 멀티버스로 채택 여부를 검증한다.

**Architecture:** 기존 일봉 A~I 룰(`rule_envelope_200d_high`)과 동일한 `Rule`/`RuleResult` 인터페이스로 3개 dataclass 룰을 추가한다. 진입만 코드화(청산=드라이버 sl/tp/mh 근사). 분봉 룰은 **세션 인식**(당일 누적고/저·당일 최다거래량을 `datetime`으로 당일 봉만 필터)이 핵심. `scripts/book_portfolio_multiverse.py`(분봉 경로, `--periods`+`--minute-resample-freq`)로 백테스트.

**Tech Stack:** Python 3.8+, pandas, pytest, PostgreSQL(minute_candles), 기존 드라이버 `book_portfolio_multiverse.py` 재사용.

**Spec:** `docs/superpowers/specs/2026-06-04-trading-strategy-book-minute-execution-design.md`

---

## 핵심 사실 (코드 작성 전 확정됨 — 드라이버 소스 검증)

1. 룰은 **확장 윈도우** `window = df.iloc[: i+1]`를 받는다(`book_portfolio_multiverse._precompute_signals:268-279`). 즉 평가 시점 t = `df` 마지막 행, df엔 0..t 전체 history. → 룩백 120봉 룰도 충분한 history면 발사.
2. 분봉 df 컬럼 = `datetime, open, high, low, close, volume`(리샘플 후 `reset_index`로 datetime 컬럼 유지, `core/timeframe_converter.py:67`). → 세션 인식 가능.
3. `--minute-resample-freq`는 **정수(분)**, 기본 15. 5분=`5`, 1분=`1`(거의 패스스루). minute은 `--start/--end` 대신 `--periods` 사용, 키 = `2025-10, 2026-04, 2026-05`(`book_portfolio_multiverse.MINUTE_PERIODS`)만 정의.
4. minute warmup=70 hardcoded(`:797`). 룩백>70인 룰(볼린저 121)은 **룰 자체 need-가드**로 부족 시 미트리거. 확장 윈도우라 history 충분하면(월 ~1700봉@5m) 정상 발사.
5. 룰 인터페이스: `from strategies.books._base_book_strategy import Rule, RuleResult`. `RuleResult(triggered, side="buy", confidence=70.0, reasons=[], metadata={})`. 기존 `rule_envelope_200d_high`와 동일 패턴.

---

## File Structure

- **Modify** `strategies/books/trading_strategy_book/rules.py` — 모듈 상단에 공통 헬퍼(`_today_mask`, `_bisector_at`) 추가, 3룰 dataclass 추가, `ALL_RULES` 확장. **기존 `rule_envelope_200d_high` 무수정**.
- **Create** `tests/books/test_trading_strategy_book_minute.py` — 3룰 단위테스트(조건 게이트 + no-lookahead + 세션 + 드라이버 해석).
- **Modify** `reports/books_research/trading_strategy_book/report.md` — 분봉 3전략 절 + 채택 판정 추가.
- `strategy.py` 무수정(`ALL_RULES` 자동 확장, 드라이버가 `--rule`로 개별 선택).

모든 지표 trailing(과거~t), t+1 접근 금지. 컬럼명 `datetime/open/high/low/close/volume`만 사용.

---

## Task 1: 공통 헬퍼 + 가격박스 룰 (`rule_price_box_tma`)

**Files:**
- Create: `tests/books/test_trading_strategy_book_minute.py`
- Modify: `strategies/books/trading_strategy_book/rules.py`

가격박스: 1분봉, 중심선 TMA(30)=SMA(SMA(close,15),15), 밴드=중심±(최근 60봉 |close−TMA|의 mean+2·std). 진입 = 하한 지지(close≤lower·1.002) OR 중심 상향돌파(close[t-1]<TMA[t-1] & close[t]≥TMA[t]), + 이등분선 위.

- [ ] **Step 1: Write the failing tests**

파일 생성 `tests/books/test_trading_strategy_book_minute.py`:

```python
"""『트레이딩 전략서』 (Book 19) 분봉 실행층 3전략 단위테스트.

분봉 룰은 세션 인식(당일 누적고/저·당일 최다거래량). 평가시점 t=df 마지막 행.
모든 평가는 trailing(과거~t) — no-lookahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _mk(open_, high, low, close, volume, *, day="2025-10-06", start="09:00"):
    """1분 간격 datetime 부여한 분봉 df. 기본 단일 거래일(세션 단순화)."""
    n = len(close)
    dts = pd.date_range(f"{day} {start}", periods=n, freq="1min")
    return pd.DataFrame({
        "datetime": dts, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


# ---------- 전략 1: 가격박스 ----------

def _price_box():
    from strategies.books.trading_strategy_book.rules import rule_price_box_tma
    return rule_price_box_tma()


def _box_arrays(n=80):
    """all-pass(중심 상향돌파) 기본 배열.

    history(0..n-3)=1000 평탄에 ±8 진동(밴드 형성). t-1=998(<TMA), t=1003(>=TMA) 돌파.
    당일 고/저 좁게 → 이등분선~1000, close 1003>이등분선.
    """
    close = np.array([1000.0 + (8.0 if i % 2 else -8.0) for i in range(n)])
    close[-2] = 998.0      # 직전봉 TMA 아래
    close[-1] = 1003.0     # 현재봉 TMA 위 → 상향돌파
    open_ = close - 1.0
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    volume = np.full(n, 5000.0)
    return open_, high, low, close, volume


def test_box_all_pass_center_breakout_triggers():
    res = _price_box().evaluate(_mk(*_box_arrays()), {})
    assert res.triggered is True and res.side == "buy"


def test_box_no_breakout_no_support_blocks():
    o, h, l, c, v = _box_arrays()
    c[-2] = 1003.0  # 직전봉도 TMA 위 → 크로스(돌파) 없음
    c[-1] = 1004.0  # 하한 지지도 아님(밴드 상단 근처)
    o = c - 1.0; h = np.maximum(o, c) + 1.0; l = np.minimum(o, c) - 1.0
    assert _price_box().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_box_below_bisector_blocks():
    o, h, l, c, v = _box_arrays()
    h[-1] = 1100.0  # 당일 고가 급등 → 이등분선~(1100+low)/2 > close(1003)
    assert _price_box().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_box_support_path_triggers():
    """하한 지지 경로: 현재가가 하한선 근처로 하락 + 이등분선 위 유지."""
    n = 80
    close = np.array([1000.0 + (8.0 if i % 2 else -8.0) for i in range(n)])
    close[-1] = 985.0          # 하한선(~1000-band) 근처
    open_ = close + 1.0         # 음봉이어도 무관(진입은 지지)
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    low[:] = 984.0              # 당일 최저 고정 → 이등분선 낮춤
    high[:] = 986.0             # 당일 최고 낮춤 → 이등분선=(986+984)/2=985 <= close 985
    volume = np.full(n, 5000.0)
    res = _price_box().evaluate(_mk(open_, high, low, close, volume), {})
    assert res.triggered is True


def test_box_insufficient_bars_no_trigger():
    o, h, l, c, v = _box_arrays(n=40)  # need=max(30,60)+2=62 미만
    assert _price_box().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_box_no_datetime_no_trigger():
    o, h, l, c, v = _box_arrays()
    df = _mk(o, h, l, c, v).drop(columns=["datetime"])
    assert _price_box().evaluate(df, {}).triggered is False


def test_box_no_lookahead():
    o, h, l, c, v = _box_arrays()
    df = _mk(o, h, l, c, v)
    full = _price_box().evaluate(df, {})
    extra = _mk(np.full(5, 500.0), np.full(5, 501.0), np.full(5, 499.0),
                np.full(5, 500.0), np.full(5, 1.0),
                day="2025-10-06", start="11:00")
    more = pd.concat([df, extra], ignore_index=True)
    sliced = _price_box().evaluate(more.iloc[: len(df)], {})
    assert full.triggered == sliced.triggered is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_minute.py -q`
Expected: FAIL — `ImportError: cannot import name 'rule_price_box_tma'`

- [ ] **Step 3: Add shared helpers + rule to `rules.py`**

`strategies/books/trading_strategy_book/rules.py`의 `import` 직후(기존 `rule_envelope_200d_high` 위)에 헬퍼 추가:

```python
import numpy as np


def _today_mask(df: pd.DataFrame):
    """t(마지막 행)와 같은 거래일(KST date)의 봉 boolean mask. datetime 필수."""
    if "datetime" not in df.columns:
        return None
    dts = pd.to_datetime(df["datetime"])
    last_date = dts.iloc[-1].date()
    return (dts.dt.date == last_date).values


def _bisector_at(df: pd.DataFrame, mask) -> float:
    """당일 누적 이등분선 = (당일 고가 max + 당일 저가 min) / 2 (t까지)."""
    h = df["high"].astype(float).values[mask]
    l = df["low"].astype(float).values[mask]
    return (float(h.max()) + float(l.min())) / 2.0
```

기존 `ALL_RULES = [rule_envelope_200d_high]` **위에** 가격박스 룰 추가:

```python
@dataclass
class rule_price_box_tma(Rule):
    """전략1 가격박스(1분봉): TMA(30) 중심선 ± 편차밴드, 하한 지지/중심 상향돌파."""
    name: str = "price_box_tma"
    tma_period: int = 30      # 삼각이동평균 기간
    dev_window: int = 60      # 편차밴드 룩백
    dev_k: float = 2.0        # 편차 std 배수
    tol: float = 0.002        # 지지/돌파 tolerance

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        m = (self.tma_period + 1) // 2  # 15
        need = max(2 * m, self.dev_window) + 2
        mask = _today_mask(df)
        if df is None or len(df) < need or mask is None:
            return RuleResult(triggered=False)

        c = df["close"].astype(float)
        # TMA(30) ≈ SMA(SMA(close,15),15)
        tma = c.rolling(m).mean().rolling(m).mean()
        tma_t = float(tma.iloc[-1]); tma_prev = float(tma.iloc[-2])
        close_t = float(c.iloc[-1]); close_prev = float(c.iloc[-2])
        if any(np.isnan(x) for x in (tma_t, tma_prev, close_t, close_prev)):
            return RuleResult(triggered=False)

        # 편차밴드 (최근 dev_window 봉 |close-TMA| 의 mean+dev_k*std)
        dev = (c - tma).abs().iloc[-self.dev_window:]
        if dev.isna().any():
            return RuleResult(triggered=False)
        band = float(dev.mean()) + self.dev_k * float(dev.std())
        lower = tma_t - band

        support = close_t <= lower * (1.0 + self.tol)
        breakout = (close_prev < tma_prev) and (close_t >= tma_t)
        if not (support or breakout):
            return RuleResult(triggered=False)

        # 이등분선 위
        if close_t < _bisector_at(df, mask):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"price_box_tma close={close_t:.0f} tma={tma_t:.0f} "
                     f"lower={lower:.0f} {'support' if support else 'breakout'}"],
            metadata={"tma": tma_t, "lower": lower, "band": band},
        )
```

- [ ] **Step 4: Register in `ALL_RULES`**

`ALL_RULES` 를 다음으로 교체:

```python
# 책 전체 규칙 (일봉 A~I + 분봉 실행층 3전략)
ALL_RULES = [rule_envelope_200d_high, rule_price_box_tma]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_minute.py -q`
Expected: PASS (7 passed). 만약 `test_box_support_path_triggers` 또는 boundary 테스트가 fixture 수치 때문에 실패하면, 밴드 계산값(`metadata`)을 출력해 fixture 의 close/high/low 를 미세조정(트리거 의도는 유지). 게이트 로직 자체는 수정 금지.

- [ ] **Step 6: Commit (사장님 승인 후)**

```bash
git add strategies/books/trading_strategy_book/rules.py tests/books/test_trading_strategy_book_minute.py
git commit -m "feat(book19): 분봉 전략1 가격박스(price_box_tma) + 공통 세션헬퍼"
```
> 18·19권 관례: 커밋은 사장님 승인 후에만. 미승인 시 보류하고 다음 Task 진행.

---

## Task 2: 볼린저 스퀴즈 룰 (`rule_bollinger_squeeze`)

**Files:**
- Modify: `strategies/books/trading_strategy_book/rules.py`
- Test: `tests/books/test_trading_strategy_book_minute.py` (append)

볼린저: 5분봉, BB(20,2). 밀집 = **직전봉 bandwidth**(상-하)/중심 ≤ 최근 sqz_window 봉 중앙값(돌파봉 자체의 밴드확대 배제 위해 t-1 기준). 진입 = 이등분선 위 + 밀집 + (상한 돌파 OR 첫 하한 지지).

- [ ] **Step 1: Write the failing tests (append)**

```python
# ---------- 전략 2: 볼린저 스퀴즈 ----------

def _bb():
    from strategies.books.trading_strategy_book.rules import rule_bollinger_squeeze
    return rule_bollinger_squeeze()


def _bb_arrays(n=130, last=1050.0):
    """all-pass: history 일정진폭(스퀴즈 유지) + 마지막봉 상한 돌파."""
    close = np.array([1000.0 + (3.0 if i % 2 else -3.0) for i in range(n)])
    close[-1] = last
    open_ = close - 0.5
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    volume = np.full(n, 5000.0)
    return open_, high, low, close, volume


def test_bb_all_pass_squeeze_breakout_triggers():
    res = _bb().evaluate(_mk(*_bb_arrays()), {})
    assert res.triggered is True and res.side == "buy"


def test_bb_no_squeeze_blocks():
    """직전봉 밴드가 최근 중앙값보다 넓으면(변동성 확대) 스퀴즈 아님 → 미트리거."""
    o, h, l, c, v = _bb_arrays()
    # 뒤쪽 25봉 진폭을 크게 키움(t-1 bandwidth > median) but 마지막봉은 여전히 돌파
    for i in range(-25, -1):
        c[i] = 1000.0 + (60.0 if i % 2 else -60.0)
    o = c - 0.5; h = np.maximum(o, c) + 0.5; l = np.minimum(o, c) - 0.5
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_bb_no_breakout_no_support_blocks():
    o, h, l, c, v = _bb_arrays(last=1000.0)  # 마지막봉이 밴드 내부(돌파X·지지X)
    o = c - 0.5; h = np.maximum(o, c) + 0.5; l = np.minimum(o, c) - 0.5
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_bb_below_bisector_blocks():
    o, h, l, c, v = _bb_arrays()
    h[-1] = 2000.0  # 당일 고가 급등 → 이등분선 > close
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_bb_insufficient_bars_no_trigger():
    o, h, l, c, v = _bb_arrays(n=100)  # need=20+100+1=121 미만
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_minute.py -k bb -q`
Expected: FAIL — `ImportError: cannot import name 'rule_bollinger_squeeze'`

- [ ] **Step 3: Add rule to `rules.py`** (가격박스 룰 아래, `ALL_RULES` 위)

```python
@dataclass
class rule_bollinger_squeeze(Rule):
    """전략2 볼린저(5분봉): BB(20,2) 밴드밀집 후 상한돌파/첫 하한지지."""
    name: str = "bollinger_squeeze"
    bb_period: int = 20
    bb_k: float = 2.0
    sqz_window: int = 100   # 밀집 비교 중앙값 룩백
    tol: float = 0.002

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = self.bb_period + self.sqz_window + 1
        mask = _today_mask(df)
        if df is None or len(df) < need or mask is None:
            return RuleResult(triggered=False)

        c = df["close"].astype(float)
        mid = c.rolling(self.bb_period).mean()
        sd = c.rolling(self.bb_period).std()
        upper = mid + self.bb_k * sd
        lower = mid - self.bb_k * sd
        bandwidth = (upper - lower) / mid

        # 밀집: 직전봉(t-1) bandwidth ≤ 최근 sqz_window 중앙값(t-1 까지). 돌파봉 자체 배제.
        bw_prev = float(bandwidth.iloc[-2])
        bw_med = float(bandwidth.iloc[-(self.sqz_window + 1):-1].median())
        if np.isnan(bw_prev) or np.isnan(bw_med):
            return RuleResult(triggered=False)
        if not (bw_prev <= bw_med):
            return RuleResult(triggered=False)

        close_t = float(c.iloc[-1])
        up_t = float(upper.iloc[-1]); low_t = float(lower.iloc[-1])
        if any(np.isnan(x) for x in (close_t, up_t, low_t)):
            return RuleResult(triggered=False)

        breakout = close_t >= up_t
        support = close_t <= low_t * (1.0 + self.tol)
        if not (breakout or support):
            return RuleResult(triggered=False)

        if close_t < _bisector_at(df, mask):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"bollinger_squeeze close={close_t:.0f} upper={up_t:.0f} "
                     f"bw_prev={bw_prev:.4f}<=med={bw_med:.4f} "
                     f"{'breakout' if breakout else 'support'}"],
            metadata={"upper": up_t, "lower": low_t, "bw_prev": bw_prev, "bw_med": bw_med},
        )
```

`ALL_RULES` 교체:

```python
ALL_RULES = [rule_envelope_200d_high, rule_price_box_tma, rule_bollinger_squeeze]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_minute.py -k bb -q`
Expected: PASS (5 passed). fixture 수치 미세조정만 허용(게이트 로직 불변).

- [ ] **Step 5: Commit (사장님 승인 후)**

```bash
git add strategies/books/trading_strategy_book/rules.py tests/books/test_trading_strategy_book_minute.py
git commit -m "feat(book19): 분봉 전략2 볼린저 스퀴즈(bollinger_squeeze)"
```

---

## Task 3: 눌림목 거래량 건조 룰 (`rule_pullback_volume_dry`)

**Files:**
- Modify: `strategies/books/trading_strategy_book/rules.py`
- Test: `tests/books/test_trading_strategy_book_minute.py` (append)

눌림목: 5분봉. t=확대(매수)봉, t-1=급감/축소봉. 주가↑추세(close[t]>close[t-6]) + 거래량↓추세 + 이등분선 위 + 직전봉 거래량 급감(≤당일최다·¼)·캔들 축소 + 현재봉 거래량 확대(>직전 & ≤당일최다·½)·캔들 확대.

- [ ] **Step 1: Write the failing tests (append)**

```python
# ---------- 전략 3: 눌림목 거래량 건조 ----------

def _pb():
    from strategies.books.trading_strategy_book.rules import rule_pullback_volume_dry
    return rule_pullback_volume_dry()


def _pb_arrays(n=20):
    """all-pass: 우상향 추세 + 직전봉 거래량 급감·캔들 축소 + 현재봉 확대."""
    close = np.linspace(980.0, 1000.0, n)   # 우상향 (close[t]>close[t-6])
    open_ = close - 1.0
    high = close + 2.0
    low = open_ - 2.0                        # range≈5
    volume = np.full(n, 4000.0)
    volume[0] = 20000.0                      # 당일 최다 거래량(기준)
    # 거래량 감소추세(직전 6봉 평균보다 t-1 낮게)
    volume[-8:-2] = 5000.0
    volume[-2] = 4000.0                      # t-1 급감: <= 20000*0.25=5000
    high[-2] = open_[-2] + 1.0; low[-2] = open_[-2] - 1.0  # t-1 캔들 축소(range≈2)
    volume[-1] = 9000.0                      # t 확대: >4000 & <= 20000*0.5=10000
    high[-1] = open_[-1] + 4.0; low[-1] = open_[-1] - 4.0  # t 캔들 확대(range≈8>2)
    return open_, high, low, close, volume


def test_pb_all_pass_triggers():
    res = _pb().evaluate(_mk(*_pb_arrays()), {})
    assert res.triggered is True and res.side == "buy"


def test_pb_volume_over_half_blocks():
    o, h, l, c, v = _pb_arrays()
    v[-1] = 12000.0  # 현재봉 > 당일최다·0.5(10000) → 매수금지
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb_no_expansion_blocks():
    o, h, l, c, v = _pb_arrays()
    v[-1] = 3500.0  # 현재봉 거래량 < 직전봉(4000) → 확대 아님
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb_dry_not_met_blocks():
    o, h, l, c, v = _pb_arrays()
    v[-2] = 8000.0  # 직전봉 > 당일최다·0.25(5000) → 급감 아님
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb_no_uptrend_blocks():
    o, h, l, c, v = _pb_arrays()
    c[:] = c[-1]  # 평탄 → close[t] > close[t-6] 불성립
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb_below_bisector_blocks():
    o, h, l, c, v = _pb_arrays()
    h[5] = 1200.0  # 당일 고가 급등 → 이등분선 > close[t]
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb_insufficient_bars_no_trigger():
    o, h, l, c, v = _pb_arrays(n=10)  # need=trend_window+8=14 미만
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_minute.py -k pb -q`
Expected: FAIL — `ImportError: cannot import name 'rule_pullback_volume_dry'`

- [ ] **Step 3: Add rule to `rules.py`**

```python
@dataclass
class rule_pullback_volume_dry(Rule):
    """전략3 눌림목(5분봉): 우상향 추세 중 거래량 급감·캔들 축소 후 확대 매수.

    t=확대(매수)봉, t-1=급감/축소봉. 거래량 기준 = 당일 최다거래량(세션).
    """
    name: str = "pullback_volume_dry"
    trend_window: int = 6
    vol_dry_ratio: float = 0.25    # 직전봉 급감 상한(당일최다 대비)
    vol_block_ratio: float = 0.50  # 현재봉 거래량 초과금지(당일최다 대비)

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = self.trend_window + 8
        mask = _today_mask(df)
        if df is None or len(df) < need or mask is None:
            return RuleResult(triggered=False)

        c = df["close"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        v = df["volume"].astype(float)
        rng = (h - l)

        close_t = float(c.iloc[-1]); close_tw = float(c.iloc[-1 - self.trend_window])
        vol_t = float(v.iloc[-1]); vol_prev = float(v.iloc[-2])
        rng_t = float(rng.iloc[-1]); rng_prev = float(rng.iloc[-2])
        scalars = (close_t, close_tw, vol_t, vol_prev, rng_t, rng_prev)
        if any(np.isnan(x) for x in scalars):
            return RuleResult(triggered=False)

        # 1) 주가 우상향 추세
        if not (close_t > close_tw):
            return RuleResult(triggered=False)

        # 2) 거래량 감소추세: 직전봉 vol < 그 이전 trend_window 봉 평균
        prior_vol = v.iloc[-(self.trend_window + 2):-2]
        if len(prior_vol) < self.trend_window or not (vol_prev < float(prior_vol.mean())):
            return RuleResult(triggered=False)

        # 3) 당일 최다거래량(세션) 기준
        day_max_vol = float(v.values[mask].max())
        if day_max_vol <= 0:
            return RuleResult(triggered=False)

        # 4) 직전봉 거래량 급감 + 캔들 축소
        dry = vol_prev <= day_max_vol * self.vol_dry_ratio
        prior_rng = rng.iloc[-(self.trend_window + 2):-2]
        contract = rng_prev < float(prior_rng.mean())
        if not (dry and contract):
            return RuleResult(triggered=False)

        # 5) 현재봉 거래량 확대(직전 초과·당일최다 절반 이하) + 캔들 확대
        expand_vol = (vol_t > vol_prev) and (vol_t <= day_max_vol * self.vol_block_ratio)
        expand_rng = rng_t > rng_prev
        if not (expand_vol and expand_rng):
            return RuleResult(triggered=False)

        # 6) 이등분선 위
        if close_t < _bisector_at(df, mask):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"pullback_volume_dry close={close_t:.0f} "
                     f"dry_vol={vol_prev:.0f}<= {day_max_vol * self.vol_dry_ratio:.0f} "
                     f"expand_vol={vol_t:.0f}"],
            metadata={"day_max_vol": day_max_vol, "vol_prev": vol_prev, "vol_t": vol_t},
        )
```

`ALL_RULES` 교체:

```python
ALL_RULES = [
    rule_envelope_200d_high,
    rule_price_box_tma,
    rule_bollinger_squeeze,
    rule_pullback_volume_dry,
]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_minute.py -k pb -q`
Expected: PASS (7 passed). fixture 미세조정만 허용.

- [ ] **Step 5: Commit (사장님 승인 후)**

```bash
git add strategies/books/trading_strategy_book/rules.py tests/books/test_trading_strategy_book_minute.py
git commit -m "feat(book19): 분봉 전략3 눌림목 거래량건조(pullback_volume_dry)"
```

---

## Task 4: 드라이버 해석 스모크 + 전체 회귀

**Files:**
- Test: `tests/books/test_trading_strategy_book_minute.py` (append)

- [ ] **Step 1: Write the failing smoke test (append)**

```python
# ---------- 드라이버 해석 ----------

def test_driver_resolves_minute_rules():
    """멀티버스 드라이버가 3룰을 모두 해석할 수 있어야 한다."""
    from scripts.book_portfolio_multiverse import _load_book, _resolve_rule_cls
    _strat, rules_mod = _load_book("trading_strategy_book")
    for nm in ("price_box_tma", "bollinger_squeeze", "pullback_volume_dry"):
        cls = _resolve_rule_cls(rules_mod, nm)
        assert cls().name == nm
        # rule_ 접두 입력도 동일 해석
        assert _resolve_rule_cls(rules_mod, f"rule_{nm}") is cls


def test_all_rules_registered():
    from strategies.books.trading_strategy_book.rules import ALL_RULES
    names = {r().name for r in ALL_RULES}
    assert names == {"envelope_200d_high", "price_box_tma",
                     "bollinger_squeeze", "pullback_volume_dry"}
```

> 주의: 드라이버 모듈은 `book_portfolio_multiverse`(daily 검증에 쓴 것)와 `book_param_multiverse` 둘 다 `_load_book`/`_resolve_rule_cls`를 제공한다. 기존 일봉 스모크가 `book_param_multiverse`를 import 하므로, 분봉은 실제 백테스트에 쓰는 `book_portfolio_multiverse`로 검증한다. import 실패 시 `from scripts.book_param_multiverse import ...`로 폴백(둘 다 동일 함수명).

- [ ] **Step 2: Run to verify fail/pass**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_minute.py::test_driver_resolves_minute_rules tests/books/test_trading_strategy_book_minute.py::test_all_rules_registered -q`
Expected: PASS (룰이 Task1~3에서 이미 등록됨). 만약 `_resolve_rule_cls`가 `book_portfolio_multiverse`에 없으면 `book_param_multiverse`로 수정.

- [ ] **Step 3: 책 테스트 전체 회귀**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_daily.py tests/books/test_trading_strategy_book_minute.py -q`
Expected: 일봉 12 + 분봉(7+5+7+2=21) = 33 passed. 일봉 룰 무영향 확인.

- [ ] **Step 4: Commit (사장님 승인 후)**

```bash
git add tests/books/test_trading_strategy_book_minute.py
git commit -m "test(book19): 분봉 3룰 드라이버 해석 + 등록 스모크"
```

---

## Task 5: 정본 분봉 멀티버스 백테스트

**Files:** 없음(실행만). 출력: `D:\tmp\multiverse\book19_minute_*`

분봉은 장시간 → **반드시 `run_in_background=true`**. 3룰 각각 실행(가격박스=1분, 볼린저·눌림목=5분).

- [ ] **Step 1: 가격박스(1분) 멀티버스 — 백그라운드**

Run (run_in_background=true):
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python scripts/book_portfolio_multiverse.py \
  --book trading_strategy_book --rule price_box_tma --granularity minute \
  --periods 2025-10,2026-04,2026-05 --minute-resample-freq 1 \
  --universe top_volume:50 --K-list 3 5 \
  --max-per-stock 3000000 --initial-capital 10000000 \
  --entry-grid '{"tma_period":[30]}' \
  --exit-grid '{"sl":[0.02,0.03],"tp":[0.02,0.03,0.05],"mh":[2,4,8]}' \
  --workers 4 --out D:\tmp\multiverse\book19_minute_pricebox
```
Expected: `<out>/book_portfolio_trading_strategy_book_price_box_tma.tsv` + 콘솔 top-K + best vs baseline. **신호 거래수(ntr) 기록** — 희소하면 결론.

- [ ] **Step 2: 볼린저(5분) 멀티버스 — 백그라운드**

Run (run_in_background=true):
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python scripts/book_portfolio_multiverse.py \
  --book trading_strategy_book --rule bollinger_squeeze --granularity minute \
  --periods 2025-10,2026-04,2026-05 --minute-resample-freq 5 \
  --universe top_volume:50 --K-list 3 5 \
  --max-per-stock 3000000 --initial-capital 10000000 \
  --entry-grid '{"bb_period":[20]}' \
  --exit-grid '{"sl":[0.02,0.03],"tp":[0.02,0.03,0.05],"mh":[2,4,8]}' \
  --workers 4 --out D:\tmp\multiverse\book19_minute_bollinger
```

- [ ] **Step 3: 눌림목(5분) 멀티버스 — 백그라운드**

Run (run_in_background=true):
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python scripts/book_portfolio_multiverse.py \
  --book trading_strategy_book --rule pullback_volume_dry --granularity minute \
  --periods 2025-10,2026-04,2026-05 --minute-resample-freq 5 \
  --universe top_volume:50 --K-list 3 5 \
  --max-per-stock 3000000 --initial-capital 10000000 \
  --entry-grid '{"trend_window":[6]}' \
  --exit-grid '{"sl":[0.02,0.03],"tp":[0.02,0.03,0.05],"mh":[2,4,8]}' \
  --workers 4 --out D:\tmp\multiverse\book19_minute_pullback
```

- [ ] **Step 4: 결과 수집**

각 `.tsv`의 best 행(sharpe desc→pnl desc), 거래수(ntr), K별 메트릭, best vs baseline을 표로 정리. 신호 0/희소면 그대로 기록(억지 채택 금지). PnL 전조합 음수·Sharpe<0.6 여부 확인. (커밋 없음 — 산출물은 D:\tmp.)

---

## Task 6: report 갱신 + 최종 검증

**Files:**
- Modify: `reports/books_research/trading_strategy_book/report.md`

- [ ] **Step 1: report.md 에 분봉 절 추가**

기존 일봉 report 끝에 "## 5. 분봉 실행층 3전략 (2026-06-04)" 절 추가. 포함: ① 코드화 범위(진입만·청산 sl/tp/mh 근사·spec 링크) ② 3룰 확정 임계값 표(가격박스 TMA30/dev60, 볼린저 BB20·스퀴즈100, 눌림목 6봉·¼/½) ③ 백테스트 결과(3룰×3구간, K별, 거래수) ④ **채택 판정**(Sharpe≳0.6·강건성·BEAR부재 명기) ⑤ 미코드화 사유(청산 재량·장중게이트·"조건부"/TMA 해석 단순화 R4·R5).

- [ ] **Step 2: 책 테스트 전체 회귀 최종 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/ -q`
Expected: 신규 33(일봉12+분봉21) 통과 + 기존 책 테스트 무영향(사전존재 minervini 2 fail 은 무관, 메모리 기록).

- [ ] **Step 3: py_compile 점검**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m py_compile strategies/books/trading_strategy_book/rules.py`
Expected: 무출력(성공).

- [ ] **Step 4: 채택 판정 verifier 재확인**

판정이 증거(거래수·Sharpe·BEAR부재)와 일치하는지 재확인. 분봉단타 전멸 전례 + BEAR 부재 → 부적격 가능성 높음. 억지 채택 금지.

- [ ] **Step 5: Commit (사장님 승인 후)**

```bash
git add reports/books_research/trading_strategy_book/report.md
git commit -m "research(book19): 분봉 실행층 3전략 백테스트 + 채택판정"
```
> **git 커밋·push 는 사장님 승인 후에만.** 18·19권 관례. 신규/수정 책 파일만(라이브 무영향).

---

## Self-Review (작성자 점검 결과)

1. **Spec coverage**: spec §1.1(진입만)→Task1~3 룰, §2.0(이등분선·세션)→`_today_mask`/`_bisector_at`(Task1) + 각 룰 bisector 게이트, §2.1 가격박스→Task1, §2.2 볼린저→Task2, §2.3 눌림목→Task3, §3 청산 드라이버→Task5 exit-grid, §4 산출물→Task1~3·6, §5 백테스트→Task5, §6 판정→Task6, §8 R1(datetime)→`_today_mask` None가드, R2(리샘플)→Task5 freq 1/5, R3(BEAR부재)→Task6 명기, R4("조건부" 단순화)→가격박스 docstring·report, R5(TMA정의)→Task1 `m=(period+1)//2` 이중SMA 명시. 누락 없음.
2. **Placeholder scan**: 모든 코드 step 완전. fixture 수치 "미세조정 허용"은 TDD red 단계의 정상 보정(게이트 로직 불변 조건 명시) — placeholder 아님.
3. **Type consistency**: 룰 클래스명/`.name`(price_box_tma·bollinger_squeeze·pullback_volume_dry), 헬퍼(`_today_mask`/`_bisector_at`), 필드명(tma_period·dev_window·dev_k·tol / bb_period·bb_k·sqz_window / trend_window·vol_dry_ratio·vol_block_ratio), `ALL_RULES`, `RuleResult(triggered/side/confidence/reasons/metadata)` 가 rules.py·테스트·스모크 전반 일관. 드라이버 함수 `_load_book`/`_resolve_rule_cls`는 Task4에서 출처(book_portfolio_multiverse) 명시·폴백 기재.
4. **밴드/스퀴즈 정의 정밀화**: 볼린저 밀집은 돌파봉 자체의 밴드확대를 배제하려 **t-1 bandwidth** 기준으로 구현(spec "밀집" 의도 충실). report에 명기.
```
