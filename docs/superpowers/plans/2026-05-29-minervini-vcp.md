# Minervini VCP (Book 5/10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Minervini *Trade Like a Stock Market Wizard*의 SEPA Trend Template(8조건) + VCP 패턴을 한국 일봉 시장에 적용. 조사 → 기록 → 코드화 → 백테스트(Variant A/B) → 리포트 → 커밋까지 1권 완료.

**Architecture:** `strategies/books/minervini_vcp/{rules.py, strategy.py}` 에 `BookStrategy` 베이스 재사용으로 규칙 모듈화. 백테스트는 `BookBacktester(eod_liquidate=False)` 일봉 모드 + adj_factor 적용 가격 사용을 위해 `scripts/run_minervini_vcp.py` 별도 작성. RS는 universe 내부에서 12주 수익률 백분위로 자체 계산.

**Tech Stack:** Python 3.8+, pandas/numpy, PostgreSQL `daily_prices` 테이블, pytest, BookStrategy 베이스, BookBacktester.

**Spec:** [docs/superpowers/specs/2026-05-29-minervini-vcp-design.md](../specs/2026-05-29-minervini-vcp-design.md)

---

## File Structure

| 파일 | 역할 | 신규/수정 |
|---|---|---|
| `RoboTrader_template/strategies/books/minervini_vcp/__init__.py` | 패키지 선언 | 신규 |
| `RoboTrader_template/strategies/books/minervini_vcp/rules.py` | Trend Template / VCP / RS 규칙 + ALL_RULES | 신규 |
| `RoboTrader_template/strategies/books/minervini_vcp/strategy.py` | MinerviniVCPStrategy + build_strategy() + BOOK_META | 신규 |
| `RoboTrader_template/tests/books/test_minervini_rules.py` | rules 단위 테스트 (helper + 4 rule) | 신규 |
| `RoboTrader_template/scripts/run_minervini_vcp.py` | 일봉 백테스트 CLI (Variant A/B 지원, top_volume:50, adj_factor 적용) | 신규 |
| `RoboTrader_template/reports/books_research/minervini_vcp/research.md` | Phase 0 조사 보고서 | 신규 |
| `RoboTrader_template/reports/books_research/minervini_vcp/report.md` | Phase 4 결과 리포트 | 신규 |
| `RoboTrader_template/reports/books_research/index.md` | 5번 행 갱신 + 5권 비교 섹션 | 수정 |
| `RoboTrader_template/memory/changelog-2026-05-29-minervini.md` | 최종 changelog | 신규 |

`BookBacktester`는 일봉 모드(eod_liquidate=False, max_hold_bars=일수)로 재사용. Sharpe는 분봉 가정(252×390)이라 정확도 떨어지지만 Raschke daily와 동일 정책 유지.

---

## Phase 0 — 조사 (Research)

### Task 0.1: 조사 노트 골격 작성

**Files:**
- Create: `RoboTrader_template/reports/books_research/minervini_vcp/research.md` (skeleton)

- [ ] **Step 1: 빈 골격으로 파일 생성**

```markdown
# Minervini VCP — 조사 노트

> Book: Mark Minervini — *Trade Like a Stock Market Wizard* (2013) / *Think & Trade Like a Champion* (2017)
> 조사 시작: 2026-05-29
> 설계: [docs/superpowers/specs/2026-05-29-minervini-vcp-design.md](../../../docs/superpowers/specs/2026-05-29-minervini-vcp-design.md)

## 1. 핵심 개념
(SEPA = Specific Entry Point Analysis. Fundamental + Technical + RS + Pattern 4축.)

## 2. SEPA Trend Template (8조건)
(책 본문 정량 정의 + 외부 인터뷰 차이)

## 3. VCP Pattern
(단계·진폭·거래량·피벗 정량 정의)

## 4. RS 자체 계산
(IBD 식 + 단순 12주 백분위)

## 5. 청산 룰
(Variant A: Minervini 본인 / Variant B: 책간 획일)

## 6. 셋업 카탈로그 (10개+)
(코드화 가능 여부 표시)

## 7. 한국 시장 적용 시 주의점

## 8. 참고 자료
```

- [ ] **Step 2: 커밋**

```bash
git add RoboTrader_template/reports/books_research/minervini_vcp/research.md
git commit -m "research(minervini): 조사 노트 골격"
```

### Task 0.2: SEPA Trend Template 정량 정의 채우기

**Files:**
- Modify: `RoboTrader_template/reports/books_research/minervini_vcp/research.md` (section 2)

- [ ] **Step 1: 책 본문 8조건 + 외부 발화 차이 정리**

`research.md` section 2를 다음 표로 채운다 (책 본문 기준):

```markdown
## 2. SEPA Trend Template (8조건)

| # | 조건 | 책 본문 정의 | 외부 인터뷰 차이 |
|---|---|---|---|
| 1 | Price > 150 MA, Price > 200 MA | 종가 기준 | (확인) |
| 2 | 150 MA > 200 MA | 종가 기준 | (확인) |
| 3 | 200 MA 1개월(20거래일)+ 상승 추세 | MA200(today) > MA200(20일 전) | "최소 5개월 우상향" 발화 있음 → 보조 조건 |
| 4 | 50 MA > 150 MA > 200 MA | 다단 정렬 | (확인) |
| 5 | Price > 50 MA | 종가 기준 | (확인) |
| 6 | 52주 신고가 −25% 이내 | (52W high - close) / 52W high ≤ 0.25 | 일부 발화 "−15% 이내" 더 보수적 |
| 7 | 52주 신저가 +30% 이상 | (close - 52W low) / 52W low ≥ 0.30 | (확인) |
| 8 | RS Rating ≥ 70 (희망 80+) | IBD RS Rating | IBD 미사용 시 자체 계산 필요 |
```

- [ ] **Step 2: 커밋**

```bash
git add RoboTrader_template/reports/books_research/minervini_vcp/research.md
git commit -m "research(minervini): SEPA Trend Template 8조건 정량 정의"
```

### Task 0.3: VCP / RS / 청산 / 셋업 카탈로그 채우기

**Files:**
- Modify: `RoboTrader_template/reports/books_research/minervini_vcp/research.md` (section 3-6)

- [ ] **Step 1: VCP 정량 정의**

section 3에 다음 표 추가:

```markdown
## 3. VCP Pattern

| 요소 | 책 본문 정의 |
|---|---|
| 베이스 길이 | 7주~수개월 (≥ 25 거래일) |
| 수축 단계 | 2~6단계 |
| 각 단계 진폭 | 직전 단계의 50% 이내로 좁아짐 |
| 거래량 dry-up | 수축 단계 일평균 거래량 < 베이스 시작 시점 직전 20일 평균 |
| 피벗 포인트 | 베이스 직전 고점 |
| 돌파 트리거 | 종가 > 피벗 + RVOL ≥ 1.5x |
```

- [ ] **Step 2: RS 정의**

section 4 추가:

```markdown
## 4. RS 자체 계산

### 방식 1 (IBD 근사)
RS_raw = 0.40 × R(12W) + 0.20 × R(26W) + 0.20 × R(39W) + 0.20 × R(52W)
→ universe 전체에서 백분위 (0~99). RS ≥ 70 → 통과.

### 방식 2 (단순)
RS_raw = R(12W) → universe 백분위. 1차 구현 채택.

### 한국 시장 RS 기준 종목 풀
- universe = top_volume:50 일봉 평균 거래대금 상위 50.
- 백분위는 universe 내부 비교 (시장 전체 미사용).
```

- [ ] **Step 3: 청산 룰**

section 5 추가:

```markdown
## 5. 청산 룰

| Variant | sl | tp | trail | mh | 출처 |
|---|---|---|---|---|---|
| A (책 의도) | 7~8% (책 stop) | 2~3R (=14~24%) | 50 MA 이탈 | 35거래일 | 책 본문 / 인터뷰 |
| B (책간 획일) | 8% | 12% | (없음) | 20거래일 | 분봉 sl3/tp5/mh120 일봉 환산 |

### Variant A 본 plan 구현
- sl = 0.08
- tp = 0.20 (≈ 2.5R)
- trail = 50일 MA 이탈 (종가 < MA50)
- mh = 35 (max_hold_bars)

### Variant B
- sl = 0.08
- tp = 0.12
- trail = 없음
- mh = 20
```

- [ ] **Step 4: 셋업 카탈로그**

section 6 추가:

```markdown
## 6. 셋업 카탈로그

| # | 셋업 | 코드화 | 비고 |
|---|---|---|---|
| 1 | Trend Template 통과 (스크리너) | O | 8조건 |
| 2 | VCP 베이스 + 피벗 돌파 | O | 본 plan 핵심 |
| 3 | Power Play (90일 +100% 후 3~6주 횡보) | △ | 표본 부족 가능 |
| 4 | 3주 Tight Closes (3주 변동폭 ≤ 1.5%) | O | 보조 셋업 |
| 5 | Pocket Pivot (50 MA 위 거래량 폭증) | △ | 거래량 정의 필요 |
| 6 | Episodic Pivot (어닝 갭 + RVOL) | X | 분기 발표 데이터 필요 |
| 7 | Earnings Gap | X | 동상 |
| 8 | Industry Group Leader | X | 섹터 분류 없음 |
| 9 | Volume Dry-Up + Tightness | O | VCP 부분집합 |
| 10 | Stage 2 Uptrend (Weinstein 기반) | O | TT 1~5 부분집합 |

본 plan 코드화 대상: 1, 2, 4, 9 (단독 + AND 조합).
```

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/reports/books_research/minervini_vcp/research.md
git commit -m "research(minervini): VCP·RS·청산·셋업 카탈로그 정량 정의"
```

### Task 0.4: 한국 시장 주의점 + 참고 자료

**Files:**
- Modify: `RoboTrader_template/reports/books_research/minervini_vcp/research.md` (section 7-8)

- [ ] **Step 1: section 7 작성**

```markdown
## 7. 한국 시장 적용 시 주의점

- **상한가 30% 제한**: 미국식 갭 패턴 빈도 낮음. Episodic Pivot 적용 어려움.
- **공매도 제약**: Stage 4 short 셋업 제외.
- **IBD RS Rating 부재**: 자체 계산 필수.
- **거래대금 집중**: top_volume:50 사용으로 유동성 확보 + universe 표준화.
- **데이터 기간 한계**: daily_prices 약 318거래일. RS 12주 + MA200 워밍업 200일 → 검증 ~118일.
- **단일 BULL 구간**: 표본 부족 시 국면별 분해(BULL/BEAR/SIDEWAYS, KOSPI 기준)로 통계적 의미 분리.
```

- [ ] **Step 2: section 8 작성**

```markdown
## 8. 참고 자료

- *Trade Like a Stock Market Wizard* (McGraw-Hill, 2013) — SEPA·Trend Template 원본
- *Think & Trade Like a Champion* (2017) — R-multiple·risk management 보강
- Minervini Private Access blog (minervini.com) — 인터뷰·세미나 발화
- IBD MarketSmith RS Rating 정의 (investors.com)
- US Investing Championship 1997 / 2021 성적 보고

## 9. 본 plan 코드화 범위 (확정)

- rule_trend_template: 8조건 스크리너
- rule_vcp_breakout: VCP 베이스 + 피벗 돌파
- rule_tight_closes: 3주 변동폭 ≤ 1.5%
- rule_volume_dryup: 거래량 dry-up + tightness

청산: Variant A(sl 8% / tp 20% / trail 50MA / mh 35) + Variant B(sl 8% / tp 12% / mh 20) 둘 다 산출.
```

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/reports/books_research/minervini_vcp/research.md
git commit -m "research(minervini): 한국 시장 주의점 + 참고자료 + 코드화 범위 확정"
```

---

## Phase 2 — 코드화

> Phase 1은 research.md 작성으로 Phase 0과 통합 완료.

### Task 2.1: 패키지 스캐폴딩

**Files:**
- Create: `RoboTrader_template/strategies/books/minervini_vcp/__init__.py`

- [ ] **Step 1: 빈 패키지 파일 작성**

```python
"""Mark Minervini — Trade Like a Stock Market Wizard (SEPA + VCP)."""
```

- [ ] **Step 2: 커밋**

```bash
git add RoboTrader_template/strategies/books/minervini_vcp/__init__.py
git commit -m "feat(minervini): 패키지 스캐폴딩"
```

### Task 2.2: 테스트 디렉토리 + 헬퍼 단위테스트 작성 (실패 확인)

**Files:**
- Create: `RoboTrader_template/tests/books/__init__.py`
- Create: `RoboTrader_template/tests/books/test_minervini_rules.py`

- [ ] **Step 1: 빈 패키지 파일 작성**

```python
# RoboTrader_template/tests/books/__init__.py
```

- [ ] **Step 2: 헬퍼 (compute_rs_percentile) 테스트 작성**

`RoboTrader_template/tests/books/test_minervini_rules.py`:

```python
"""Minervini VCP rules — 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def trend_up_df():
    """200일 단조 상승 일봉 (TT 모든 조건 통과해야 함)."""
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(10_000, 30_000, n)
    high = close * 1.01
    low = close * 0.99
    volume = np.full(n, 1_000_000)
    return pd.DataFrame({
        "datetime": dates, "open": close, "high": high, "low": low,
        "close": close, "volume": volume,
    })


@pytest.fixture
def trend_down_df():
    """200일 단조 하락 (TT 통과 불가)."""
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(30_000, 10_000, n)
    return pd.DataFrame({
        "datetime": dates, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": np.full(n, 1_000_000),
    })


def test_compute_rs_percentile_returns_0_to_99():
    from strategies.books.minervini_vcp.rules import compute_rs_percentile_12w

    n = 100
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    universe_df = pd.DataFrame({
        code: 10_000 * (1 + i * 0.001) ** np.arange(n)
        for i, code in enumerate([f"A{i:03d}" for i in range(20)])
    }, index=dates)
    rs = compute_rs_percentile_12w(universe_df)
    assert rs.shape == (n, 20)
    last = rs.iloc[-1].dropna()
    assert (last.min() >= 0) and (last.max() <= 99)
    # 가장 강한 종목(i=19) RS == 99
    assert last["A019"] == pytest.approx(99, abs=1)
```

- [ ] **Step 3: 실패 확인 실행**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py::test_compute_rs_percentile_returns_0_to_99 -v`
Expected: FAIL with `ModuleNotFoundError: strategies.books.minervini_vcp.rules`

### Task 2.3: rules.py — RS 헬퍼 구현

**Files:**
- Create: `RoboTrader_template/strategies/books/minervini_vcp/rules.py`

- [ ] **Step 1: rules.py 초기 작성 (헬퍼만)**

```python
"""Minervini VCP — Rule 집합.

규칙들:
- rule_trend_template: SEPA Trend Template 8조건
- rule_vcp_breakout: VCP 베이스 + 피벗 돌파
- rule_tight_closes: 3주 변동폭 ≤ 1.5%
- rule_volume_dryup: 거래량 dry-up + tightness

헬퍼:
- compute_rs_percentile_12w: universe 12주 수익률 백분위
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def compute_rs_percentile_12w(universe_close: pd.DataFrame) -> pd.DataFrame:
    """universe 종목 12주(60거래일) 수익률을 0~99 백분위로 변환.

    Args:
        universe_close: index=date, columns=stock_code, values=close.
    Returns:
        같은 shape의 DataFrame. 각 행은 해당 날짜의 RS 백분위 (0~99).
    """
    ret_12w = universe_close.pct_change(60)
    rank = ret_12w.rank(axis=1, pct=True, na_option="keep")
    return (rank * 99).round().astype("Int64")
```

- [ ] **Step 2: RS 테스트 통과 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py::test_compute_rs_percentile_returns_0_to_99 -v`
Expected: PASS

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/strategies/books/minervini_vcp/rules.py RoboTrader_template/tests/books/__init__.py RoboTrader_template/tests/books/test_minervini_rules.py
git commit -m "feat(minervini): compute_rs_percentile_12w 헬퍼 + 단위테스트"
```

### Task 2.4: rule_trend_template — 8조건 테스트 + 구현

**Files:**
- Modify: `RoboTrader_template/tests/books/test_minervini_rules.py` (테스트 추가)
- Modify: `RoboTrader_template/strategies/books/minervini_vcp/rules.py` (rule 추가)

- [ ] **Step 1: 테스트 추가 (단조 상승 통과 / 단조 하락 실패)**

`tests/books/test_minervini_rules.py` 끝에 추가:

```python
def test_trend_template_passes_on_uptrend(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_trend_template
    rule = rule_trend_template()
    ctx = {"stock_code": "TEST", "rs_value": 85}
    res = rule.evaluate(trend_up_df, ctx)
    assert res.triggered is True
    assert res.side == "buy"


def test_trend_template_fails_on_downtrend(trend_down_df):
    from strategies.books.minervini_vcp.rules import rule_trend_template
    rule = rule_trend_template()
    ctx = {"stock_code": "TEST", "rs_value": 85}
    res = rule.evaluate(trend_down_df, ctx)
    assert res.triggered is False


def test_trend_template_fails_when_rs_below_70(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_trend_template
    rule = rule_trend_template()
    ctx = {"stock_code": "TEST", "rs_value": 50}
    res = rule.evaluate(trend_up_df, ctx)
    assert res.triggered is False
```

- [ ] **Step 2: 실패 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py::test_trend_template_passes_on_uptrend -v`
Expected: FAIL with `ImportError: cannot import name 'rule_trend_template'`

- [ ] **Step 3: rule_trend_template 구현**

`strategies/books/minervini_vcp/rules.py` 끝에 추가:

```python
@dataclass
class rule_trend_template(Rule):
    """SEPA Trend Template 8조건. ctx['rs_value'] 필요."""
    name: str = "trend_template"
    rs_threshold: float = 70.0
    high_52w_drawdown_max: float = 0.25
    low_52w_advance_min: float = 0.30

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 220:
            return RuleResult(triggered=False)
        close = df["close"].astype(float)
        ma50 = close.rolling(50).mean()
        ma150 = close.rolling(150).mean()
        ma200 = close.rolling(200).mean()
        last_close = float(close.iloc[-1])
        last_ma50 = float(ma50.iloc[-1])
        last_ma150 = float(ma150.iloc[-1])
        last_ma200 = float(ma200.iloc[-1])
        ma200_20d_ago = float(ma200.iloc[-21])
        high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
        low_52w = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())
        rs_value = ctx.get("rs_value")
        if rs_value is None or pd.isna(rs_value):
            return RuleResult(triggered=False)

        c1 = last_close > last_ma150 and last_close > last_ma200
        c2 = last_ma150 > last_ma200
        c3 = last_ma200 > ma200_20d_ago
        c4 = last_ma50 > last_ma150 > last_ma200
        c5 = last_close > last_ma50
        c6 = (high_52w - last_close) / high_52w <= self.high_52w_drawdown_max if high_52w > 0 else False
        c7 = (last_close - low_52w) / low_52w >= self.low_52w_advance_min if low_52w > 0 else False
        c8 = float(rs_value) >= self.rs_threshold

        if c1 and c2 and c3 and c4 and c5 and c6 and c7 and c8:
            return RuleResult(
                triggered=True, side="buy", confidence=72.0,
                reasons=[f"TT close={last_close:.0f} ma50={last_ma50:.0f} ma200={last_ma200:.0f} rs={rs_value}"],
                metadata={"rs": float(rs_value)},
            )
        return RuleResult(triggered=False)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py -v -k trend_template`
Expected: 3 PASSED

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/strategies/books/minervini_vcp/rules.py RoboTrader_template/tests/books/test_minervini_rules.py
git commit -m "feat(minervini): rule_trend_template (SEPA 8조건) + 테스트"
```

### Task 2.5: rule_vcp_breakout — VCP 패턴 인식 + 테스트

**Files:**
- Modify: `RoboTrader_template/tests/books/test_minervini_rules.py`
- Modify: `RoboTrader_template/strategies/books/minervini_vcp/rules.py`

- [ ] **Step 1: 테스트 추가 (수축 후 돌파 통과 / 비수축 실패)**

`tests/books/test_minervini_rules.py` 끝에 추가:

```python
def _vcp_synthetic_df():
    """베이스 25일 + 진폭 수축 2단계 + 마지막 봉 피벗 돌파 + 거래량 폭증."""
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(10_000, 12_000, n - 30).tolist()
    pivot = max(close[-25:])  # 베이스 시작 직전 고점
    # 베이스 25일 수축: 첫 12일 진폭 5%, 다음 12일 진폭 2%
    base_high = pivot
    base = []
    for i in range(12):
        base.append(pivot * (1 - 0.05 + 0.0042 * i))
    for i in range(12):
        base.append(pivot * (1 - 0.02 + 0.0017 * i))
    base.append(pivot * 1.03)  # 피벗 돌파
    high = [c * 1.01 for c in close + base]
    low = [c * 0.99 for c in close + base]
    closes = close + base
    # 거래량: 베이스 25일 dry-up + 마지막 봉 폭증
    base_avg_vol = 1_000_000
    volume = [base_avg_vol] * (n - 26) + [base_avg_vol * 0.4] * 25 + [base_avg_vol * 2.0]
    return pd.DataFrame({
        "datetime": dates, "open": closes, "high": high, "low": low,
        "close": closes, "volume": volume,
    })


def test_vcp_breakout_triggers_on_synthetic_pattern():
    from strategies.books.minervini_vcp.rules import rule_vcp_breakout
    rule = rule_vcp_breakout()
    df = _vcp_synthetic_df()
    res = rule.evaluate(df, {"stock_code": "TEST"})
    assert res.triggered is True
    assert res.side == "buy"


def test_vcp_breakout_fails_on_flat_volume(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_vcp_breakout
    rule = rule_vcp_breakout()
    res = rule.evaluate(trend_up_df, {"stock_code": "TEST"})
    # 단조 상승은 베이스/수축 없음 → 실패
    assert res.triggered is False
```

- [ ] **Step 2: 실패 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py -v -k vcp_breakout`
Expected: FAIL `ImportError: cannot import name 'rule_vcp_breakout'`

- [ ] **Step 3: rule_vcp_breakout 구현**

`strategies/books/minervini_vcp/rules.py` 끝에 추가:

```python
@dataclass
class rule_vcp_breakout(Rule):
    """VCP 베이스(≥25일) + 진폭 수축 + 거래량 dry-up + 피벗 돌파 + RVOL."""
    name: str = "vcp_breakout"
    base_min_bars: int = 25
    rvol_threshold: float = 1.5
    dryup_ratio_max: float = 0.7  # 베이스 평균 거래량 / 직전 20일 평균 ≤ 0.7
    contraction_ratio_max: float = 0.6  # 후반 진폭 / 전반 진폭 ≤ 0.6

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.base_min_bars + 21:
            return RuleResult(triggered=False)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)

        base = df.iloc[-(self.base_min_bars + 1):-1]
        pre_base = df.iloc[-(self.base_min_bars + 21):-(self.base_min_bars + 1)]
        last = df.iloc[-1]

        pivot = float(pre_base["high"].max())
        last_close = float(last["close"])
        last_vol = float(last["volume"])

        # 1. 피벗 돌파
        if last_close <= pivot:
            return RuleResult(triggered=False)

        # 2. RVOL (최근 봉 거래량 / 베이스 평균 거래량)
        base_avg_vol = float(base["volume"].mean())
        if base_avg_vol <= 0:
            return RuleResult(triggered=False)
        rvol = last_vol / base_avg_vol
        if rvol < self.rvol_threshold:
            return RuleResult(triggered=False)

        # 3. 거래량 dry-up: 베이스 평균 < pre_base 평균 × dryup_ratio_max
        pre_base_avg_vol = float(pre_base["volume"].mean())
        if pre_base_avg_vol <= 0 or base_avg_vol / pre_base_avg_vol > self.dryup_ratio_max:
            return RuleResult(triggered=False)

        # 4. 진폭 수축: 베이스 전반 12봉 진폭 vs 후반 12봉 진폭
        mid = len(base) // 2
        early_range = float((base["high"].iloc[:mid] - base["low"].iloc[:mid]).mean())
        late_range = float((base["high"].iloc[mid:] - base["low"].iloc[mid:]).mean())
        if early_range <= 0 or late_range / early_range > self.contraction_ratio_max:
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=75.0,
            reasons=[
                f"vcp_breakout pivot={pivot:.0f} close={last_close:.0f} rvol={rvol:.2f} "
                f"dryup={base_avg_vol/pre_base_avg_vol:.2f} contract={late_range/early_range:.2f}"
            ],
            metadata={"pivot": pivot, "rvol": rvol},
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py -v -k vcp_breakout`
Expected: 2 PASSED

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/strategies/books/minervini_vcp/rules.py RoboTrader_template/tests/books/test_minervini_rules.py
git commit -m "feat(minervini): rule_vcp_breakout (베이스+수축+dryup+피벗 돌파) + 테스트"
```

### Task 2.6: rule_tight_closes + rule_volume_dryup + ALL_RULES export

**Files:**
- Modify: `RoboTrader_template/tests/books/test_minervini_rules.py`
- Modify: `RoboTrader_template/strategies/books/minervini_vcp/rules.py`

- [ ] **Step 1: 테스트 추가**

`tests/books/test_minervini_rules.py` 끝에 추가:

```python
def test_tight_closes_triggers_on_narrow_3w_range(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_tight_closes
    rule = rule_tight_closes()
    # 마지막 15봉 종가 변동폭을 강제로 1% 이하로
    df = trend_up_df.copy()
    last_15_close = df["close"].iloc[-15].copy()
    df.loc[df.index[-15:], "close"] = last_15_close * (1 + np.linspace(-0.005, 0.005, 15))
    res = rule.evaluate(df, {"stock_code": "TEST"})
    assert res.triggered is True


def test_volume_dryup_triggers_on_low_recent_volume(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_volume_dryup
    df = trend_up_df.copy()
    df.loc[df.index[-10:], "volume"] = 400_000  # 직전 평균 1M의 40%
    rule = rule_volume_dryup()
    res = rule.evaluate(df, {"stock_code": "TEST"})
    assert res.triggered is True


def test_all_rules_export_has_4_classes():
    from strategies.books.minervini_vcp import rules as rules_mod
    assert len(rules_mod.ALL_RULES) == 4
    names = [cls().name for cls in rules_mod.ALL_RULES]
    assert set(names) == {"trend_template", "vcp_breakout", "tight_closes", "volume_dryup"}
```

- [ ] **Step 2: 실패 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py -v -k "tight_closes or volume_dryup or all_rules"`
Expected: 3 FAIL `ImportError`

- [ ] **Step 3: rule_tight_closes + rule_volume_dryup + ALL_RULES 구현**

`strategies/books/minervini_vcp/rules.py` 끝에 추가:

```python
@dataclass
class rule_tight_closes(Rule):
    """3주(15봉) 종가 변동폭 ≤ 1.5%."""
    name: str = "tight_closes"
    window: int = 15
    range_pct_max: float = 0.015

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.window:
            return RuleResult(triggered=False)
        recent_close = df["close"].astype(float).iloc[-self.window:]
        range_pct = (recent_close.max() - recent_close.min()) / recent_close.mean()
        if range_pct <= self.range_pct_max:
            return RuleResult(
                triggered=True, side="buy", confidence=60.0,
                reasons=[f"tight_closes range={range_pct:.3%} ≤ {self.range_pct_max:.1%}"],
            )
        return RuleResult(triggered=False)


@dataclass
class rule_volume_dryup(Rule):
    """최근 10봉 평균 거래량 ≤ 직전 30봉 평균의 70%."""
    name: str = "volume_dryup"
    recent_window: int = 10
    base_window: int = 30
    ratio_max: float = 0.7

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.recent_window + self.base_window:
            return RuleResult(triggered=False)
        vol = df["volume"].astype(float)
        recent_avg = float(vol.iloc[-self.recent_window:].mean())
        base_avg = float(vol.iloc[-(self.recent_window + self.base_window):-self.recent_window].mean())
        if base_avg <= 0:
            return RuleResult(triggered=False)
        ratio = recent_avg / base_avg
        if ratio <= self.ratio_max:
            return RuleResult(
                triggered=True, side="buy", confidence=58.0,
                reasons=[f"volume_dryup recent/base={ratio:.2f} ≤ {self.ratio_max:.2f}"],
            )
        return RuleResult(triggered=False)


ALL_RULES = [
    rule_trend_template,
    rule_vcp_breakout,
    rule_tight_closes,
    rule_volume_dryup,
]
```

- [ ] **Step 4: 통과 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py -v`
Expected: 모든 테스트 PASS (≥ 8개)

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/strategies/books/minervini_vcp/rules.py RoboTrader_template/tests/books/test_minervini_rules.py
git commit -m "feat(minervini): rule_tight_closes + rule_volume_dryup + ALL_RULES export"
```

### Task 2.7: strategy.py — MinerviniVCPStrategy + build_strategy

**Files:**
- Create: `RoboTrader_template/strategies/books/minervini_vcp/strategy.py`

- [ ] **Step 1: 테스트 추가**

`tests/books/test_minervini_rules.py` 끝에 추가:

```python
def test_build_strategy_single_mode_returns_book_strategy():
    from strategies.books.minervini_vcp.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="trend_template")
    assert strat.name == "MinerviniVCPStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "trend_template"


def test_build_strategy_all_and_mode():
    from strategies.books.minervini_vcp.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 4
```

- [ ] **Step 2: 실패 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py -v -k build_strategy`
Expected: 2 FAIL `ImportError`

- [ ] **Step 3: strategy.py 작성**

```python
"""Minervini VCP — 일봉 전략."""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.minervini_vcp.rules import ALL_RULES


BOOK_META = {
    "id": "minervini_vcp",
    "name": "Minervini SEPA + VCP (Trade Like a Stock Market Wizard)",
    "category": "growth",
    "data_granularity": "daily",
}


class MinerviniVCPStrategy(BookStrategy):
    name = "MinerviniVCPStrategy"
    version = "1.0.0"
    description = "Minervini SEPA Trend Template + VCP breakout"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> MinerviniVCPStrategy:
    return MinerviniVCPStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py -v`
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/strategies/books/minervini_vcp/strategy.py
git commit -m "feat(minervini): MinerviniVCPStrategy + build_strategy"
```

---

## Phase 3 — 백테스트

### Task 3.1: scripts/run_minervini_vcp.py — 데이터 로더 + 골격

**Files:**
- Create: `RoboTrader_template/scripts/run_minervini_vcp.py`

- [ ] **Step 1: 스크립트 골격 작성 (데이터 로드 + universe 선정 + RS 계산)**

```python
"""Minervini VCP 일봉 백테스트.

usage:
  python scripts/run_minervini_vcp.py --variant A --all-modes
  python scripts/run_minervini_vcp.py --variant B --mode single --rule vcp_breakout

데이터: daily_prices (adj_factor 적용 수정주가)
universe: top_volume:50 (일평균 거래대금 상위 50)
RS: universe 내부 12주 수익률 백분위
청산: Variant A (sl 8% / tp 20% / mh 35 / 50MA trail) 또는 B (sl 8% / tp 12% / mh 20)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.minervini_vcp.rules import ALL_RULES, compute_rs_percentile_12w
from strategies.books.minervini_vcp.strategy import BOOK_META, build_strategy

LOG = logging.getLogger("minervini_vcp")

VARIANT_PARAMS = {
    "A": dict(stop_loss_pct=0.08, take_profit_pct=0.20, max_hold_bars=35, trail_ma=50),
    "B": dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20, trail_ma=None),
}


def _load_top_volume_universe(start: str, end: str, top_n: int = 50) -> List[str]:
    """daily_prices의 (close*volume) 합계 상위 N종목."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
            GROUP BY stock_code
            ORDER BY turnover DESC
            LIMIT %s
        """, (start, end, top_n))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """종목별 daily_prices (adj_factor 적용 수정주가) 로드."""
    from db.connection import DatabaseConnection
    out: Dict[str, pd.DataFrame] = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, volume, adj_factor
                FROM daily_prices
                WHERE stock_code = %s
                  AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if not rows or len(rows) < 30:
                continue
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "adj_factor"])
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "high", "low", "close", "volume", "adj_factor"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["adj_factor"] = df["adj_factor"].fillna(1.0)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col] * df["adj_factor"]
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def _build_universe_close(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """{code: df} → wide close DataFrame (index=date, columns=code)."""
    series = {code: df.set_index("datetime")["close"] for code, df in data.items()}
    wide = pd.DataFrame(series)
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


if __name__ == "__main__":
    pass  # main() 다음 task에서 추가
```

- [ ] **Step 2: 커밋**

```bash
git add RoboTrader_template/scripts/run_minervini_vcp.py
git commit -m "feat(minervini): 백테스트 스크립트 골격 (데이터 로더 + RS 헬퍼)"
```

### Task 3.2: 시뮬레이션 함수 (Variant A/B 지원)

**Files:**
- Modify: `RoboTrader_template/scripts/run_minervini_vcp.py`

- [ ] **Step 1: simulate_book_trades 함수 추가**

`run_minervini_vcp.py` 끝에 (`if __name__` 위에) 추가:

```python
def simulate_one_stock(
    code: str,
    df: pd.DataFrame,
    rs_series: Optional[pd.Series],
    strategy,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_hold_bars: int,
    trail_ma: Optional[int],
    warmup_bars: int = 220,
    commission_rate: float = 0.00015,
    tax_rate: float = 0.0018,
    slippage_rate: float = 0.001,
    initial_capital: float = 10_000_000,
) -> dict:
    """단일 종목 일봉 시뮬레이션. 신호 → 다음 봉 시가 매수 → sl/tp/mh/trail 청산."""
    from strategies.base import SignalType
    n = len(df)
    if n < warmup_bars + 2:
        return {"n_trades": 0, "trades": [], "equity_curve": [initial_capital]}

    df = df.reset_index(drop=True).copy()
    cash = initial_capital
    position: Optional[dict] = None
    trades: List[dict] = []
    equity: List[float] = []

    for i in range(warmup_bars, n - 1):
        bar_now = df.iloc[i]
        bar_next = df.iloc[i + 1]
        cur_date = bar_now["datetime"]

        # 청산 체크
        if position is not None:
            entry_price = position["entry_price"]
            cur_close = float(bar_now["close"])
            ret = (cur_close - entry_price) / entry_price
            hold_bars = i - position["entry_idx"]
            exit_reason = None
            if ret <= -stop_loss_pct:
                exit_reason = "stop_loss"
            elif ret >= take_profit_pct:
                exit_reason = "take_profit"
            elif hold_bars >= max_hold_bars:
                exit_reason = "max_hold"
            elif trail_ma is not None and i >= trail_ma:
                ma = df["close"].iloc[i - trail_ma + 1:i + 1].mean()
                if cur_close < ma:
                    exit_reason = "trail_ma"
            if exit_reason is not None:
                fill = float(bar_next["open"]) * (1 - slippage_rate)
                proceeds = position["qty"] * fill
                fee = proceeds * (commission_rate + tax_rate)
                cash += proceeds - fee
                pnl = (fill - entry_price) / entry_price
                trades.append({
                    "stock_code": code, "side": "sell", "idx": i + 1,
                    "datetime": str(bar_next["datetime"]), "price": fill,
                    "qty": position["qty"], "reason": exit_reason,
                    "entry_price": entry_price, "pnl_pct": pnl,
                })
                position = None

        # 신호 평가
        if position is None:
            window = df.iloc[: i + 1]
            rs_value = float(rs_series.loc[cur_date]) if rs_series is not None and cur_date in rs_series.index else np.nan
            ctx_extra = {"rs_value": rs_value}
            # ctx_extra를 BookStrategy에 전달하려면 rule이 ctx에서 읽어야 함.
            # BookStrategy.generate_signal은 ctx={"stock_code", "timeframe"}만 넘기므로,
            # rule_trend_template은 ctx['rs_value']가 필요. ctx를 패치하기 위해
            # 임시로 strategy._rs_value를 monkey-patch 후 rule.evaluate 호출 패턴 사용.
            # 이를 위해 BookStrategy.generate_signal을 우회하지 않고
            # 각 rule에 ctx['rs_value']를 전달할 방법: strategy.generate_signal 호출 전
            # 전역 dict 대신 strategy 측 ctx를 직접 사용한다 → 다음 task에서 BookStrategy
            # 인터페이스 확장으로 처리.
            try:
                signal = strategy.generate_signal_with_extra_ctx(code, window, "daily", ctx_extra)  # type: ignore[attr-defined]
            except AttributeError:
                signal = strategy.generate_signal(code, window, "daily")
            if signal is not None and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                fill = float(bar_next["open"]) * (1 + slippage_rate)
                qty = int((cash * 0.99) // fill)
                if qty > 0:
                    cost = qty * fill
                    fee = cost * commission_rate
                    cash -= cost + fee
                    position = {"entry_idx": i + 1, "entry_price": fill, "qty": qty}
                    trades.append({
                        "stock_code": code, "side": "buy", "idx": i + 1,
                        "datetime": str(bar_next["datetime"]), "price": fill,
                        "qty": qty, "reason": ",".join(signal.reasons or ["signal"]),
                        "entry_price": fill, "pnl_pct": 0.0,
                    })

        mtm = cash
        if position is not None:
            mtm += position["qty"] * float(bar_now["close"])
        equity.append(mtm)

    # 강제 청산
    if position is not None:
        last = df.iloc[-1]
        fill = float(last["close"]) * (1 - slippage_rate)
        proceeds = position["qty"] * fill
        fee = proceeds * (commission_rate + tax_rate)
        cash += proceeds - fee
        entry_price = position["entry_price"]
        trades.append({
            "stock_code": code, "side": "sell", "idx": n - 1,
            "datetime": str(last["datetime"]), "price": fill,
            "qty": position["qty"], "reason": "forced_close",
            "entry_price": entry_price,
            "pnl_pct": (fill - entry_price) / entry_price,
        })
        equity.append(cash)

    return {"n_trades": sum(1 for t in trades if t["side"] == "sell"), "trades": trades, "equity_curve": equity}
```

- [ ] **Step 2: 커밋**

```bash
git add RoboTrader_template/scripts/run_minervini_vcp.py
git commit -m "feat(minervini): simulate_one_stock (Variant A/B 청산 + 50MA trail)"
```

### Task 3.3: BookStrategy 확장 — generate_signal_with_extra_ctx

**Files:**
- Modify: `RoboTrader_template/strategies/books/_base_book_strategy.py`

- [ ] **Step 1: ctx 확장 메서드 테스트 추가**

`tests/books/test_minervini_rules.py` 끝에 추가:

```python
def test_generate_signal_with_extra_ctx_passes_rs_value(trend_up_df):
    from strategies.books.minervini_vcp.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="trend_template")
    # rs_value 미전달 시 None → 실패
    sig_none = strat.generate_signal("TEST", trend_up_df, "daily")
    assert sig_none is None
    # rs_value 85 전달 시 통과
    sig_ok = strat.generate_signal_with_extra_ctx("TEST", trend_up_df, "daily", {"rs_value": 85})
    assert sig_ok is not None
```

- [ ] **Step 2: 실패 확인**

Run: `pytest RoboTrader_template/tests/books/test_minervini_rules.py::test_generate_signal_with_extra_ctx_passes_rs_value -v`
Expected: FAIL `AttributeError: ... has no attribute 'generate_signal_with_extra_ctx'`

- [ ] **Step 3: BookStrategy에 메서드 추가**

`strategies/books/_base_book_strategy.py` 의 `BookStrategy` 클래스에서 `generate_signal` 메서드 바로 뒤에 추가 (78~111 라인 이후):

```python
    def generate_signal_with_extra_ctx(
        self, stock_code: str, data: pd.DataFrame, timeframe: str, extra: Dict[str, Any]
    ) -> Optional[Signal]:
        """generate_signal과 같지만 ctx에 extra dict를 머지해서 rule에 전달."""
        if data is None or len(data) == 0:
            return None
        ctx = {"stock_code": stock_code, "timeframe": timeframe, **extra}

        if self.mode == "single":
            rule = self._rule_map.get(self.target_rule)
            if rule is None:
                return None
            res = rule.evaluate(data, ctx)
            return self._to_signal(stock_code, res, res.reasons if res.triggered else [])

        if self.mode == "all_AND":
            if not self.rules:
                return None
            results = [(r.name, r.evaluate(data, ctx)) for r in self.rules]
            if all(res.triggered for _, res in results):
                merged_reasons = [r for _, res in results for r in res.reasons]
                return self._to_signal(stock_code, results[0][1], merged_reasons)
            return None

        if self.mode == "top_K_OR":
            for name in self.or_members:
                rule = self._rule_map.get(name)
                if rule is None:
                    continue
                res = rule.evaluate(data, ctx)
                if res.triggered:
                    return self._to_signal(stock_code, res, [name])
            return None
        return None
```

- [ ] **Step 4: 통과 확인 + 기존 Raschke 테스트 회귀 확인**

Run: `pytest RoboTrader_template/tests/books/ -v`
Expected: 전체 PASS

Run: `pytest RoboTrader_template/tests/ -v --no-header -q | tail -20`
Expected: 기존 테스트 PASS (회귀 없음)

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/strategies/books/_base_book_strategy.py RoboTrader_template/tests/books/test_minervini_rules.py
git commit -m "feat(books): BookStrategy.generate_signal_with_extra_ctx (rule에 ctx 확장 전달)"
```

### Task 3.4: main() — Variant 1개 종목 스모크 실행

**Files:**
- Modify: `RoboTrader_template/scripts/run_minervini_vcp.py`

- [ ] **Step 1: main() 추가 + run_books_research 정책 미러**

`run_minervini_vcp.py` 의 `if __name__ == "__main__":` 을 다음으로 교체:

```python
def _compute_metrics(initial: float, equity: List[float], trades: List[dict]) -> dict:
    import math
    if not equity:
        return dict(n_trades=0, pnl_pct=0.0, sharpe=0.0, calmar=0.0, max_dd=0.0,
                    hit_rate=0.0, avg_hold_days=0.0)
    eq = np.array(equity, dtype=float)
    pnl_pct = (eq[-1] - initial) / initial
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if len(dd) else 0.0
    calmar = float(pnl_pct / max_dd) if max_dd > 1e-9 else 0.0
    sells = [t for t in trades if t["side"] == "sell"]
    wins = sum(1 for t in sells if t["pnl_pct"] > 0)
    hit = wins / len(sells) if sells else 0.0
    holds: List[int] = []
    buy_idx: Optional[int] = None
    for t in trades:
        if t["side"] == "buy":
            buy_idx = t["idx"]
        elif t["side"] == "sell" and buy_idx is not None:
            holds.append(t["idx"] - buy_idx)
            buy_idx = None
    avg_hold = float(np.mean(holds)) if holds else 0.0
    return dict(n_trades=len(sells), pnl_pct=pnl_pct, sharpe=sharpe, calmar=calmar,
                max_dd=max_dd, hit_rate=hit, avg_hold_days=avg_hold)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", required=True, choices=["A", "B"])
    p.add_argument("--mode", default=None, choices=["single", "all_AND"])
    p.add_argument("--rule", default=None)
    p.add_argument("--all-modes", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--start", default=None, help="YYYY-MM-DD (기본: daily_prices 최소 날짜)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD (기본: daily_prices 최대 날짜)")
    p.add_argument("--reports-dir", default="reports/books_research/minervini_vcp")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나 필수")

    # 기간 자동
    if args.start is None or args.end is None:
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices")
            mn, mx = cur.fetchone()
        args.start = args.start or str(mn)
        args.end = args.end or str(mx)
    LOG.info(f"period: {args.start} ~ {args.end}")

    universe = _load_top_volume_universe(args.start, args.end, args.top_n)
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_daily_adj(universe, args.start, args.end)
    LOG.info(f"loaded data for {len(data)} stocks")
    if not data:
        LOG.error("no data — aborting")
        return

    wide_close = _build_universe_close(data)
    rs_wide = compute_rs_percentile_12w(wide_close)

    params = VARIANT_PARAMS[args.variant]
    rule_names = [cls().name for cls in ALL_RULES]
    combos = [("single", n) for n in rule_names] + [("all_AND", None)] if args.all_modes else [(args.mode, args.rule)]

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path("reports/books_research/leaderboard.parquet")

    from backtest.book_backtester import append_leaderboard

    for mode, rule_name in combos:
        strategy = build_strategy(mode=mode, target_rule=rule_name)
        per_stock_pnl = []
        all_trades = []
        per_stock_metrics = []
        for code, df in data.items():
            rs_series = rs_wide[code] if code in rs_wide.columns else None
            res = simulate_one_stock(
                code=code, df=df, rs_series=rs_series, strategy=strategy,
                stop_loss_pct=params["stop_loss_pct"],
                take_profit_pct=params["take_profit_pct"],
                max_hold_bars=params["max_hold_bars"],
                trail_ma=params["trail_ma"],
            )
            metrics = _compute_metrics(10_000_000, res["equity_curve"], res["trades"])
            per_stock_metrics.append(metrics)
            per_stock_pnl.append(metrics["pnl_pct"])
            for t in res["trades"]:
                all_trades.append(t)

        n_stocks = len(per_stock_metrics)
        agg = {
            "n_stocks": n_stocks,
            "n_trades": int(sum(m["n_trades"] for m in per_stock_metrics)),
            "pnl_pct": float(np.mean(per_stock_pnl)) if per_stock_pnl else 0.0,
            "sharpe": float(np.mean([m["sharpe"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "calmar": float(np.mean([m["calmar"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "max_dd": float(np.mean([m["max_dd"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "hit_rate": float(np.mean([m["hit_rate"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "avg_hold_days": float(np.mean([m["avg_hold_days"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
        }
        label = rule_name if mode == "single" else mode
        LOG.info(f"[variant={args.variant} {mode}/{label}] n_stocks={n_stocks} n_trades={agg['n_trades']} "
                 f"pnl={agg['pnl_pct']:.4%} sharpe={agg['sharpe']:.2f}")

        out_file = reports_dir / f"results_variant{args.variant}_{mode}_{label}.parquet"
        if all_trades:
            pd.DataFrame(all_trades).to_parquet(out_file, index=False)

        append_leaderboard(
            path=leaderboard_path,
            row={
                "book_id": "minervini_vcp",
                "book_name": BOOK_META["name"],
                "period": "daily_full",
                "rule_combo": label,
                "mode": mode,
                "variant": args.variant,
                "universe": f"top_volume:{args.top_n}",
                "stop_loss_pct": params["stop_loss_pct"],
                "take_profit_pct": params["take_profit_pct"],
                "max_hold_bars": params["max_hold_bars"],
                "n_stocks": agg["n_stocks"],
                "n_trades": agg["n_trades"],
                "pnl_pct": agg["pnl_pct"],
                "sharpe": agg["sharpe"],
                "calmar": agg["calmar"],
                "max_dd_pct": agg["max_dd"],
                "hit_rate": agg["hit_rate"],
                "avg_hold_bars": agg["avg_hold_days"],
            },
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스모크 실행 (5종목, single, vcp_breakout, Variant A)**

Run:
```bash
cd RoboTrader_template
python scripts/run_minervini_vcp.py --variant A --mode single --rule vcp_breakout --limit 5 --log-level INFO
```
Expected: 에러 없이 "loaded data for N stocks" + `[variant=A single/vcp_breakout] n_stocks=N n_trades=X pnl=...` 출력

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/scripts/run_minervini_vcp.py
git commit -m "feat(minervini): main() + _compute_metrics + Variant A/B 풀런 인프라"
```

### Task 3.5: 풀런 — Variant A (전체 universe, all-modes)

**Files:**
- Modify: 없음 (실행만)

- [ ] **Step 1: Variant A 풀런 실행**

Run:
```bash
cd RoboTrader_template
python scripts/run_minervini_vcp.py --variant A --all-modes --log-level INFO 2>&1 | tee /tmp/minervini_A.log
```
Expected: 5개 mode 결과 (single×4 + all_AND) 각각 LOG 출력. parquet 파일 5개 생성.

- [ ] **Step 2: 결과 검증**

Run:
```bash
cd RoboTrader_template
ls -la reports/books_research/minervini_vcp/results_variantA_*.parquet
python -c "import pandas as pd; df = pd.read_parquet('reports/books_research/leaderboard.parquet'); print(df[df['book_id']=='minervini_vcp'][['rule_combo','variant','n_trades','pnl_pct','sharpe']].to_string())"
```
Expected: leaderboard에 minervini_vcp 5행 (variant=A) 확인.

- [ ] **Step 3: 커밋 (결과 parquet)**

```bash
git add RoboTrader_template/reports/books_research/minervini_vcp/results_variantA_*.parquet RoboTrader_template/reports/books_research/leaderboard.parquet
git commit -m "backtest(minervini): Variant A 풀런 (4 single + all_AND)"
```

### Task 3.6: 풀런 — Variant B

**Files:**
- Modify: 없음 (실행만)

- [ ] **Step 1: Variant B 풀런 실행**

Run:
```bash
cd RoboTrader_template
python scripts/run_minervini_vcp.py --variant B --all-modes --log-level INFO 2>&1 | tee /tmp/minervini_B.log
```
Expected: 5개 mode 결과. parquet 5개 추가 생성.

- [ ] **Step 2: 결과 검증**

Run:
```bash
cd RoboTrader_template
python -c "import pandas as pd; df = pd.read_parquet('reports/books_research/leaderboard.parquet'); m = df[df['book_id']=='minervini_vcp']; print(m[['rule_combo','variant','n_trades','pnl_pct','sharpe','calmar']].to_string())"
```
Expected: minervini_vcp 10행 (A 5 + B 5) 확인.

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/reports/books_research/minervini_vcp/results_variantB_*.parquet RoboTrader_template/reports/books_research/leaderboard.parquet
git commit -m "backtest(minervini): Variant B 풀런 (4 single + all_AND)"
```

### Task 3.7: 국면별 분해 (BULL/BEAR/SIDEWAYS)

**Files:**
- Create: `RoboTrader_template/scripts/regime_split_minervini.py`

- [ ] **Step 1: 국면 분류 + Variant별 PnL 분해 스크립트**

```python
"""KOSPI 국면(BULL/BEAR/SIDEWAYS) 기준으로 Minervini 매도일 분류 후 PnL 집계.

기준 (기존 Phase 5 합의):
- BULL:  20일 KOSPI 수익률 > +2%
- BEAR:  20일 KOSPI 수익률 < -2%
- SIDE:  그 외
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_kospi_regime() -> pd.Series:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT date, close FROM daily_prices
            WHERE stock_code = 'KS11' ORDER BY date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    ret20 = df["close"].pct_change(20)
    regime = pd.Series("SIDEWAYS", index=df.index)
    regime[ret20 > 0.02] = "BULL"
    regime[ret20 < -0.02] = "BEAR"
    return regime


def main():
    reports = Path("reports/books_research/minervini_vcp")
    regime = _load_kospi_regime()
    rows = []
    for f in sorted(reports.glob("results_variant*_*.parquet")):
        df = pd.read_parquet(f)
        sells = df[df["side"] == "sell"].copy()
        if sells.empty:
            continue
        sells["dt"] = pd.to_datetime(sells["datetime"], errors="coerce")
        sells["regime"] = sells["dt"].map(lambda d: regime.asof(d) if pd.notna(d) else "UNKNOWN")
        for reg, grp in sells.groupby("regime"):
            rows.append({
                "file": f.name,
                "regime": reg,
                "n_trades": len(grp),
                "mean_pnl": float(grp["pnl_pct"].mean()),
                "hit_rate": float((grp["pnl_pct"] > 0).mean()),
            })
    out_df = pd.DataFrame(rows)
    out_file = reports / "regime_breakdown.parquet"
    out_df.to_parquet(out_file, index=False)
    print(out_df.to_string())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

Run:
```bash
cd RoboTrader_template
python scripts/regime_split_minervini.py
```
Expected: 콘솔에 file × regime × n_trades × mean_pnl × hit_rate 테이블 출력. `regime_breakdown.parquet` 생성.

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/scripts/regime_split_minervini.py RoboTrader_template/reports/books_research/minervini_vcp/regime_breakdown.parquet
git commit -m "backtest(minervini): BULL/BEAR/SIDEWAYS 국면 분해"
```

---

## Phase 4 — 리포트 + 인덱스 갱신

### Task 4.1: report.md 작성

**Files:**
- Create: `RoboTrader_template/reports/books_research/minervini_vcp/report.md`

- [ ] **Step 1: 결과 추출**

Run:
```bash
cd RoboTrader_template
python -c "
import pandas as pd
df = pd.read_parquet('reports/books_research/leaderboard.parquet')
m = df[df['book_id']=='minervini_vcp'].copy()
m = m[['rule_combo','variant','n_stocks','n_trades','pnl_pct','sharpe','calmar','max_dd_pct','hit_rate','avg_hold_bars']]
m = m.sort_values(['variant','pnl_pct'], ascending=[True, False])
print(m.to_markdown(index=False, floatfmt='.4f'))
"
```
Expected: 10행 마크다운 표 출력 (Variant A 5행 + B 5행). 출력을 복사.

- [ ] **Step 2: report.md 작성**

`reports/books_research/minervini_vcp/report.md`:

```markdown
# Minervini VCP — 백테스트 결과 (Book 5/10)

> 데이터: daily_prices (adj_factor 적용 수정주가)
> 기간: daily_prices 전체 단일 긴 구간 (~318거래일)
> universe: top_volume:50 (일평균 거래대금 상위 50)
> RS: universe 내부 12주 수익률 백분위
> 청산 Variant: A(sl 8% / tp 20% / mh 35 / 50MA trail) + B(sl 8% / tp 12% / mh 20)
> 워밍업: 220봉 (200 MA + 12주 RS)
> 설계: [../../../docs/superpowers/specs/2026-05-29-minervini-vcp-design.md](../../../docs/superpowers/specs/2026-05-29-minervini-vcp-design.md)

## 1. 풀런 결과

### Variant A (Minervini 본인 룰)

<!-- Step 1 결과 Variant A 행 5개 붙여넣기 -->

### Variant B (책간 획일)

<!-- Step 1 결과 Variant B 행 5개 붙여넣기 -->

## 2. 국면별 분해

<!-- regime_breakdown.parquet 결과 마크다운 표 -->

## 3. 5권 비교

| 책 | 데이터 | 베스트 | 평균 PnL | 평균 Sharpe | 표본 |
|---|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | -0.11 | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% | +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | -2.27 | 1,860T |
| O'Neil | 일봉+재무+RS | CANSLIM+패턴 | +7.04% | — | 7T |
| **Minervini** | **일봉+RS자체** | **(베스트 결정)** | **(평균)** | **(Sharpe)** | **(거래수)** |

## 4. CANDIDATE_ALPHAS 자격 검토

| 기준 | 임계값 | 베스트 룰 값 | 통과 |
|---|---|---|---|
| 표본 | ≥ 30 트레이드 | (값) | (Y/N) |
| Sharpe | > 0 | (값) | (Y/N) |
| Calmar | ≥ 1.0 | (값) | (Y/N) |

결정: (등록 / 미등록 + 사유)

## 5. 한계와 후속 검증 항목

- 단일 구간 백테스트 — walk-forward 미수행
- RS 백분위가 universe 내부 비교 — 전체 시장 대비 미반영
- VCP 합성 패턴 단위테스트만 검증 — 실제 한국 시장 베이스 빈도 미정
- top_volume:50 종목 풀 의존 — 유니버스 확대 영향 미검증
```

- [ ] **Step 3: Step 1 결과를 report.md section 1에 붙여넣기 (수동 편집)**

`reports/books_research/minervini_vcp/report.md` 의 `<!-- ... 붙여넣기 -->` 자리를 Step 1 출력으로 교체. 국면 분해는 `regime_breakdown.parquet` 의 결과로 채움 (`python -c "import pandas as pd; print(pd.read_parquet('...').to_markdown(index=False, floatfmt='.4f'))"`).

- [ ] **Step 4: 5권 비교 / CANDIDATE_ALPHAS 자격 / 한계 섹션 데이터 채우기**

Variant A/B 중 베스트 룰을 골라 `## 3` 표 마지막 행 채움.
`## 4` 표는 베스트 룰의 n_trades / sharpe / calmar 로 채움.
CANDIDATE_ALPHAS 자격: 표본 ≥ 30, Sharpe > 0, Calmar ≥ 1 모두 통과 시 등록. O'Neil(표본 7건)과 동일 기준.

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/reports/books_research/minervini_vcp/report.md
git commit -m "docs(minervini): 백테스트 결과 리포트 (Variant A/B + 국면 분해 + 5권 비교)"
```

### Task 4.2: index.md — 5번 행 갱신 + 5권 비교 섹션

**Files:**
- Modify: `RoboTrader_template/reports/books_research/index.md`

- [ ] **Step 1: 진행 상태 표 5번 행 갱신**

`index.md`의 다음 라인을 찾아:
```
| 5 | minervini_vcp | Mark Minervini — 초수익 성장주 투자 | ⏳ 대기 | — |
```
다음으로 교체 (베스트 값은 report.md 기준):
```
| 5 | minervini_vcp | Mark Minervini — 초수익 성장주 투자 | ✅ 완료 | (베스트 Variant + PnL + Sharpe) |
```

- [ ] **Step 2: 책 5권 비교 섹션 추가**

`index.md` 의 책 4권 비교 표 바로 다음에 Minervini 행을 추가하고, 추세 비교 섹션 신설:

```markdown
## Minervini VCP 결과 — 일봉 (Book 5)

> daily_prices 전체 ~318일 + RS 자체 계산 (12주 universe 백분위). universe top_volume:50.

### Variant A/B 베스트
(report.md section 1 베스트 룰 요약 — 2~3행)

### 책 5권 비교

| 책 | 데이터 | 베스트 | 평균 PnL | 평균 Sharpe | 표본 |
|---|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | -0.11 | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% | +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | -2.27 | 1,860T |
| O'Neil | 일봉+재무+RS | CANSLIM+패턴 | +7.04% | — | 7T |
| **Minervini** | **일봉+RS자체** | (베스트) | (평균) | (Sharpe) | (거래수) |

### 결론
(report.md section 3~4 요약)

상세: [minervini_vcp/report.md](minervini_vcp/report.md)
```

- [ ] **Step 3: "다음 책" 섹션 갱신**

`index.md` 마지막의 "다음 책" 섹션을:
```
- **Plan 2** = ...
```
다음으로 교체:
```
- **다음 책 (Book 6)** = `weinstein_stages` (Stan Weinstein — Secrets for Profiting in Bull and Bear Markets). Stage Analysis 주봉 + Stage 2 추세. Minervini 인프라(RS 자체 계산) 재사용 + 주봉 집계 신규 인프라 필요.
```

- [ ] **Step 4: 커밋**

```bash
git add RoboTrader_template/reports/books_research/index.md
git commit -m "docs(books): index.md Minervini 완료 + 5권 비교 + 다음 책 Weinstein 표기"
```

---

## Phase 5 — changelog + 종료

### Task 5.1: changelog 작성

**Files:**
- Create: `RoboTrader_template/memory/changelog-2026-05-29-minervini.md`

- [ ] **Step 1: changelog 작성**

```markdown
# changelog 2026-05-29 — Minervini VCP (Book 5/10)

## 요약
- Book 5/10 완료. SEPA Trend Template 8조건 + VCP 패턴 + RS 자체 계산 + 청산 Variant A/B 이중 비교.
- 단권 깊이 조사 원칙 적용 (사장님 지시 2026-05-29).

## 산출물
- 조사: `reports/books_research/minervini_vcp/research.md`
- 코드: `strategies/books/minervini_vcp/{rules.py, strategy.py}`
- 스크립트: `scripts/run_minervini_vcp.py`, `scripts/regime_split_minervini.py`
- 테스트: `tests/books/test_minervini_rules.py` (≥ 10 cases)
- 결과: `reports/books_research/minervini_vcp/{report.md, results_variant*.parquet, regime_breakdown.parquet}`
- 인덱스: `reports/books_research/index.md` 5번 행 갱신 + 5권 비교 섹션

## 인프라 변경
- `strategies/books/_base_book_strategy.py` 에 `generate_signal_with_extra_ctx()` 추가 (rule에 ctx 확장 dict 전달용)
- `scripts/run_minervini_vcp.py` 신규 (daily_prices + adj_factor + RS 자체 계산 + Variant A/B 청산 통합)

## 결과 (베스트)
(report.md section 1 베스트 1행 인용)

## CANDIDATE_ALPHAS 자격
- (등록 / 미등록 + 사유)

## 한계
- 단일 구간 (walk-forward 미수행)
- RS 백분위가 universe 내부 비교 — 시장 전체 미반영
- VCP 합성 패턴만 단위테스트 검증

## 다음 책
- Book 6 = Weinstein Stage Analysis (주봉)
- Minervini RS 자체 계산 인프라 재사용. 주봉 집계는 신규.
```

- [ ] **Step 2: MEMORY.md 인덱스에 한 줄 추가**

`C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory\MEMORY.md` 의 `## 5/1 Phase B 완료` 섹션 뒤에 추가:

```markdown
## 5/29 Minervini VCP 완료 (Book 5/10)
- 상세: [changelog-2026-05-29-minervini.md](changelog-2026-05-29-minervini.md)
- SEPA 8조건 + VCP + RS 자체 계산 + Variant A/B 청산 이중 비교
- (베스트 룰 + PnL + Sharpe)
- 다음: Book 6 Weinstein Stage (주봉)
```

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/memory/changelog-2026-05-29-minervini.md
git add C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory\MEMORY.md
git commit -m "docs(memory): changelog Minervini VCP 완료 + MEMORY.md 인덱스 갱신"
```

### Task 5.2: 회귀 테스트 풀런 + 종료

**Files:**
- 없음 (검증만)

- [ ] **Step 1: 전체 테스트 풀런**

Run:
```bash
cd RoboTrader_template
pytest tests/ -v --no-header -q 2>&1 | tail -30
```
Expected: 기존 통과 테스트 (1285+ 회귀 없음) + Minervini 신규 테스트 (≥ 10) 모두 PASS.

- [ ] **Step 2: lint 점검**

Run:
```bash
cd RoboTrader_template
ruff check strategies/books/minervini_vcp/ scripts/run_minervini_vcp.py scripts/regime_split_minervini.py tests/books/
```
Expected: 0 errors.

- [ ] **Step 3: 커밋 로그 정리 확인**

Run: `git log --oneline -20`
Expected: Phase 0/2/3/4/5 커밋들이 차례로 보임. 누락 없음.

- [ ] **Step 4: 사장님께 종료 보고 + Weinstein 탐색 시작 승인 요청 (작업자 텍스트 응답)**

작업자는 응답 텍스트에 다음 보고:
- Minervini Book 5/10 완료
- 베스트 Variant + 룰 + PnL + Sharpe
- CANDIDATE_ALPHAS 등록 여부 + 사유
- "다음 책 Weinstein Stage Analysis 탐색 착수해도 될까요?" 결재 요청
- 사장님 결재 전 Weinstein 디자인·plan 작성 금지

---

## Self-Review Notes (writer's pass)

**1. Spec coverage:**
- Phase 0~5 → Task 0.1~5.2 모두 매핑됨.
- 청산 Variant A/B → Task 3.2 (simulate_one_stock), 3.5/3.6 (풀런).
- RS 자체 계산 → Task 2.3 (compute_rs_percentile_12w) + 3.3 (BookStrategy ctx 확장).
- VCP 패턴 → Task 2.5.
- Trend Template 8조건 → Task 2.4.
- 국면별 분해 → Task 3.7.
- 5권 비교 → Task 4.1, 4.2.
- CANDIDATE_ALPHAS 자격 → Task 4.1 section 4.
- changelog + MEMORY.md → Task 5.1.

**2. Placeholder scan:** 없음. 코드 블록과 명령어 모두 구체.

**3. Type consistency:**
- `rule_trend_template` ctx['rs_value'] 키 — Task 2.4(정의) ↔ Task 3.2(전달) ↔ Task 3.3(생성) 일치.
- `compute_rs_percentile_12w(universe_close)` 시그니처 — Task 2.3(정의) ↔ Task 3.4(호출) 일치.
- `ALL_RULES` — Task 2.6(정의) ↔ Task 2.7, 3.4(호출) 일치.
- `build_strategy(mode, target_rule, or_members)` — Task 2.7(정의) ↔ Task 3.4(호출) 일치.
- `BookStrategy.generate_signal_with_extra_ctx(stock_code, data, timeframe, extra)` — Task 3.3(정의) ↔ Task 3.2(호출) 일치.
- `simulate_one_stock(code, df, rs_series, strategy, stop_loss_pct, take_profit_pct, max_hold_bars, trail_ma, ...)` — Task 3.2(정의) ↔ Task 3.4(호출) 일치.
