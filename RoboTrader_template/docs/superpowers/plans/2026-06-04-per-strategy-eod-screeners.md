# 전략별 EOD 스크리너 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 활성 5전략이 각자의 진입룰로 EOD에 자기 컨셉에 맞는 매수후보를 선정해 `screener_snapshots`에 저장하고, 익일 owner 격리된 후보만 매매하도록 한다.

**Architecture:** 공통 `RuleScreenerBase(ScreenerBase)`가 daily_prices 유니버스를 전략별 기초필터로 추린 뒤 각 종목 일봉에 전략 진입룰(`Rule.evaluate`)을 적용해 top-N `CandidateStock`을 반환한다. 전략별 얇은 어댑터 5개가 base_filter/rule만 정의한다. EOD 수집기는 하드코딩 대신 활성 config 전략을 스크리닝하고, 매수 경로는 owner 격리 + 거래량폴백 제거로 전략 간 풀 오염을 막는다.

**Tech Stack:** Python 3.9, psycopg2, pandas, pytest. 시스템 인터프리터(`python`, psycopg2 보유)로 테스트 실행. DB: PostgreSQL 5433 robotrader.

---

## 파일 구조

| 파일 | 책임 | 변경 |
|---|---|---|
| `strategies/_rule_screener_base.py` | 공통 룰 스크리너(유니버스 로드·일봉 조회·룰 적용·랭킹) | 생성 |
| `strategies/elder_ema_pullback/screener.py` | Elder 어댑터(KOSPI대형 + triple_screen_ema_pullback) | 생성 |
| `strategies/minervini_volume_dryup/screener.py` | Minervini 어댑터(KOSPI유동 + volume_dryup) | 생성 |
| `strategies/book_pullback_ma20/screener.py` | ma20 어댑터(중소형 + daily_ma20_pullback) | 생성 |
| `strategies/book_pullback_ma5/screener.py` | ma5 어댑터(중소형 + ma5_pullback) | 생성 |
| `strategies/daytrading_3methods_breakout/screener.py` | 유지윤 어댑터(KOSDAQ급등 + breakout_prev_high) | 생성 |
| `runners/_adapter_factory.py` | strategy→어댑터 매핑 | 5전략 분기 추가 |
| `runners/screener_snapshot_collector.py` | ALL_STRATEGIES 활성 config 파생 헬퍼 | 수정 |
| `bot/liquidation_handler.py` | EOD 훅이 활성 전략 전달 | 수정 |
| `core/trading_context.py` | get_selected_stocks owner 격리 | 수정 |
| `main.py` | 거래량순위 폴백 제거(전략별 스냅샷 모드) | 수정 |
| `tests/test_rule_screener_base.py` 외 | 테스트 | 생성 |

## 공통 사실 (모든 태스크 공유)

- 룰 객체: `@dataclass` (Rule 서브클래스), 호출 = `rule.evaluate(df, ctx) -> RuleResult`. `RuleResult.triggered: bool`, `.confidence: float`, `.reasons: List[str]`.
- 룰이 요구하는 df 컬럼: `open, high, low, close, volume` (날짜 오름차순). `RuleResult` 미트리거 시 `triggered=False`.
- 일봉 로드: `db_manager.price_repo.get_daily_prices(stock_code, days)` → `DataFrame[date,open,high,low,close,volume]` (오름차순). end-date 인자 없음 → 로드 후 `df[df['date'].dt.date <= scan_date]`로 절단(룩어헤드 가드).
- 유니버스(시총/거래대금/시장): `daily_prices`의 scan_date 행 + 시장구분. 시장구분 헬퍼는 `strategies.historical_data.get_sectors()`(컬럼 stock_code, stock_name, market∈{KOSPI,KOSDAQ}) 사용.
- `CandidateStock(code, name, market, score, reason, prev_close=0.0)`.
- 테스트 실행 인터프리터: `python`(시스템, psycopg2 보유). venv는 psycopg2 없음 주의.

---

## Task 1: RuleScreenerBase (공통 베이스)

**Files:**
- Create: `strategies/_rule_screener_base.py`
- Test: `tests/test_rule_screener_base.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_rule_screener_base.py
import pandas as pd
from datetime import date
from strategies._rule_screener_base import RuleScreenerBase
from core.candidate_selector import CandidateStock


class _StubScreener(RuleScreenerBase):
    strategy_name = "stub"

    def __init__(self, universe, frames):
        self._universe = universe          # [(code, name, market, market_cap, trading_value)]
        self._frames = frames              # {code: DataFrame}

    def base_filter(self, universe):
        return [u for u in universe if u["market"] == "KOSPI"]

    def match(self, df, params):
        # 마지막 종가가 1000 이상이면 통과, score=종가
        last = float(df["close"].iloc[-1])
        if last >= 1000:
            return (last, f"close={last}")
        return None

    # 테스트용 의존성 주입 오버라이드
    def _load_universe(self, scan_date):
        return self._universe

    def _load_daily(self, code, scan_date):
        return self._frames.get(code)


def _df(closes):
    return pd.DataFrame({
        "date": pd.to_datetime([f"2026-05-{i+1:02d}" for i in range(len(closes))]),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [100] * len(closes),
    })


def test_scan_filters_ranks_and_limits():
    universe = [
        {"code": "A", "name": "Aco", "market": "KOSPI", "market_cap": 1, "trading_value": 1},
        {"code": "B", "name": "Bco", "market": "KOSPI", "market_cap": 1, "trading_value": 1},
        {"code": "C", "name": "Cco", "market": "KOSDAQ", "market_cap": 1, "trading_value": 1},
    ]
    frames = {"A": _df([500, 1500]), "B": _df([500, 2000]), "C": _df([500, 3000])}
    s = _StubScreener(universe, frames)

    out = s.scan(date(2026, 5, 2), {"max_candidates": 10})

    codes = [c.code for c in out]
    assert codes == ["B", "A"]            # C는 KOSDAQ라 base_filter 탈락, score 내림차순
    assert isinstance(out[0], CandidateStock)
    assert out[0].score == 2000.0


def test_no_lookahead_truncates_future_bars():
    universe = [{"code": "A", "name": "Aco", "market": "KOSPI", "market_cap": 1, "trading_value": 1}]
    frames = {"A": _df([1500, 2000, 3000])}  # 3봉 (5/1,5/2,5/3)
    s = _StubScreener(universe, frames)

    out = s.scan(date(2026, 5, 1), {})       # 5/1까지만 → 마지막 종가 1500
    assert out[0].score == 1500.0            # 미래봉(2000,3000) 미사용
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_rule_screener_base.py -v`
Expected: FAIL (`ModuleNotFoundError: strategies._rule_screener_base`)

- [ ] **Step 3: 최소 구현**

```python
# strategies/_rule_screener_base.py
"""RuleScreenerBase — 전략 진입룰을 daily_prices 유니버스에 적용하는 공통 스크리너."""
from __future__ import annotations

from abc import abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies.screener_base import ScreenerBase
from core.candidate_selector import CandidateStock


class RuleScreenerBase(ScreenerBase):
    """서브클래스가 base_filter()/match() 만 정의하면 되는 룰 기반 스크리너.

    의존성(DB)은 _load_universe/_load_daily 로 캡슐화 — 테스트에서 오버라이드.
    """

    # 서브클래스가 설정
    strategy_name: str = "rule_screener_base"
    lookback_days: int = 120

    def __init__(self, config=None, broker=None, db_manager=None) -> None:
        self._config = config
        self._broker = broker
        self._db_manager = db_manager

    # ---- 서브클래스 훅 -------------------------------------------------
    @abstractmethod
    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """유니버스(dict 리스트)에서 전략 성격에 맞는 종목만 추린다."""

    @abstractmethod
    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        """진입룰 적용. 통과 시 (score, reason), 탈락 시 None."""

    # ---- 공통 scan ----------------------------------------------------
    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        merged = {**self.default_params(), **(params or {})}
        max_candidates = int(merged.get("max_candidates", 10))

        universe = self.base_filter(self._load_universe(scan_date))
        scored: List[Tuple[float, CandidateStock]] = []

        for u in universe:
            code = u["code"]
            df = self._load_daily(code, scan_date)
            if df is None or df.empty:
                continue
            # 룩어헤드 가드: scan_date 이하로 절단
            df = df[df["date"].dt.date <= scan_date]
            if df.empty:
                continue
            verdict = self.match(df, merged)
            if verdict is None:
                continue
            score, reason = verdict
            scored.append((score, CandidateStock(
                code=code, name=u.get("name", code), market=u.get("market", "KRX"),
                score=float(score), reason=reason,
                prev_close=float(df["close"].iloc[-1]),
            )))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [c for _, c in scored[:max_candidates]]

    # ---- DB 의존성 (테스트에서 오버라이드) ----------------------------
    def _load_universe(self, scan_date: date) -> List[Dict[str, Any]]:
        """scan_date 행의 (code, market_cap, trading_value) + 시장구분 결합."""
        from strategies.historical_data import get_sectors
        market_map: Dict[str, Dict[str, str]] = {}
        try:
            sdf = get_sectors()
            for _, r in sdf.iterrows():
                market_map[str(r["stock_code"])] = {
                    "name": str(r.get("stock_name", "") or ""),
                    "market": str(r.get("market", "") or ""),
                }
        except Exception:
            market_map = {}

        rows: List[Dict[str, Any]] = []
        if self._db_manager is None:
            return rows
        try:
            with self._db_manager.price_repo._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT stock_code, market_cap, trading_value FROM daily_prices "
                    "WHERE date = %s",
                    (scan_date.strftime("%Y-%m-%d"),),
                )
                for code, mcap, tval in cur.fetchall():
                    meta = market_map.get(str(code), {})
                    rows.append({
                        "code": str(code),
                        "name": meta.get("name", str(code)),
                        "market": meta.get("market", "KRX"),
                        "market_cap": float(mcap or 0),
                        "trading_value": float(tval or 0),
                    })
        except Exception:
            return rows
        return rows

    def _load_daily(self, code: str, scan_date: date) -> Optional[pd.DataFrame]:
        if self._db_manager is None:
            return None
        try:
            return self._db_manager.price_repo.get_daily_prices(code, days=self.lookback_days)
        except Exception:
            return None
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_rule_screener_base.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add strategies/_rule_screener_base.py tests/test_rule_screener_base.py
git commit -m "feat(screener): RuleScreenerBase 공통 룰 스크리너"
```

---

## Task 2: Elder 스크리너 어댑터

**Files:**
- Create: `strategies/elder_ema_pullback/screener.py`
- Test: `tests/test_screener_elder.py`

**기초필터:** KOSPI + market_cap·trading_value 상위. **룰:** `rule_triple_screen_ema_pullback` (strategies/books/elder_triple_screen/rules.py).

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_screener_elder.py
import pandas as pd
from datetime import date
from strategies.elder_ema_pullback.screener import ElderEmaPullbackScreenerAdapter


def _uptrend_pullback_df(n=90):
    # 완만 상승 추세(EMA65 상승) + 마지막 봉이 EMA13 부근 눌림 양봉
    closes = [1000 + i * 5 for i in range(n - 1)]
    closes.append(closes[-1])  # 마지막은 살짝 눌림
    base = closes[-1]
    rows = {
        "date": pd.to_datetime([f"2026-0{1+(i//28)}-{(i%28)+1:02d}" for i in range(n)]),
        "open": [c - 2 for c in closes],
        "high": [c + 3 for c in closes],
        "low":  [c - 8 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    }
    return pd.DataFrame(rows)


def test_base_filter_keeps_only_kospi():
    a = ElderEmaPullbackScreenerAdapter()
    universe = [
        {"code": "A", "name": "x", "market": "KOSPI", "market_cap": 1e12, "trading_value": 1e10},
        {"code": "B", "name": "y", "market": "KOSDAQ", "market_cap": 1e12, "trading_value": 1e10},
    ]
    kept = a.base_filter(universe)
    assert [u["code"] for u in kept] == ["A"]


def test_match_triggers_on_uptrend_pullback():
    a = ElderEmaPullbackScreenerAdapter()
    df = _uptrend_pullback_df()
    verdict = a.match(df, a.default_params())
    assert verdict is not None
    score, reason = verdict
    assert "ema" in reason.lower() or "triple" in reason.lower()
```

> 참고: `_uptrend_pullback_df` 가 실제 룰을 트리거하지 않으면 Step 4에서 df 파라미터(기울기·터치폭)를 조정한다. 룰 본체는 strategies/books/elder_triple_screen/rules.py:233 의 조건(screen1_uptrend + low<=ema13*touch_band + close>ema13).

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_screener_elder.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# strategies/elder_ema_pullback/screener.py
"""Elder EMA 눌림 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.elder_triple_screen.rules import rule_triple_screen_ema_pullback


class ElderEmaPullbackScreenerAdapter(RuleScreenerBase):
    strategy_name = "elder_ema_pullback"
    lookback_days = 160  # EMA65 + 여유

    def default_params(self) -> Dict[str, Any]:
        return {
            "touch_band": 1.02,
            "min_market_cap": 500_000_000_000,   # 대형 5천억 이상
            "min_trading_value": 5_000_000_000,  # 거래대금 50억 이상
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        kept = [
            u for u in universe
            if u.get("market") == "KOSPI"
            and u.get("market_cap", 0) >= p["min_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]
        return kept

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rule = rule_triple_screen_ema_pullback(touch_band=float(params.get("touch_band", 1.02)))
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        score = float(df["trading_value"].iloc[-1]) if "trading_value" in df else float(df["close"].iloc[-1])
        reason = "; ".join(getattr(res, "reasons", []) or ["triple_screen_ema_pullback"])
        return (score, reason)
```

> 주의: `df` 에 `trading_value` 컬럼이 없으면(get_daily_prices 는 미포함) score는 close로 폴백. score 정렬용이므로 무방.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_screener_elder.py -v`
Expected: PASS (2 passed). FAIL 시 `_uptrend_pullback_df` 의 마지막 봉 low/close 를 `ema13*touch_band` 조건에 맞게 조정.

- [ ] **Step 5: 커밋**

```bash
git add strategies/elder_ema_pullback/screener.py tests/test_screener_elder.py
git commit -m "feat(screener): Elder EMA 눌림 스크리너 어댑터"
```

---

## Task 3: Minervini 스크리너 어댑터

**Files:**
- Create: `strategies/minervini_volume_dryup/screener.py`
- Test: `tests/test_screener_minervini.py`

**기초필터:** KOSPI + 유동성. **룰:** `rule_volume_dryup` (recent10/base30 ≤ 0.70).

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_screener_minervini.py
import pandas as pd
from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter


def _dryup_df():
    # 직전 30봉 거래량 1000, 최근 10봉 거래량 500 → ratio 0.5 ≤ 0.70
    vols = [1000] * 30 + [500] * 10
    n = len(vols)
    closes = [1000 + i for i in range(n)]
    return pd.DataFrame({
        "date": pd.to_datetime([f"2026-01-01"]) .repeat(0).tolist() or pd.date_range("2026-01-01", periods=n),
        "open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
        "close": closes, "volume": vols,
    })


def test_match_triggers_on_volume_dryup():
    a = MinerviniVolumeDryupScreenerAdapter()
    df = _dryup_df()
    verdict = a.match(df, a.default_params())
    assert verdict is not None
    assert "dryup" in verdict[1].lower()


def test_match_none_when_volume_not_dry():
    a = MinerviniVolumeDryupScreenerAdapter()
    df = _dryup_df()
    df.loc[df.index[-10:], "volume"] = 1000  # 최근도 1000 → ratio 1.0
    assert a.match(df, a.default_params()) is None
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_screener_minervini.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# strategies/minervini_volume_dryup/screener.py
"""Minervini 거래량 건조 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.minervini_vcp.rules import rule_volume_dryup


class MinerviniVolumeDryupScreenerAdapter(RuleScreenerBase):
    strategy_name = "minervini_volume_dryup"
    lookback_days = 90

    def default_params(self) -> Dict[str, Any]:
        return {
            "recent_window": 10,
            "base_window": 30,
            "ratio_max": 0.70,
            "min_market_cap": 300_000_000_000,
            "min_trading_value": 3_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        return [
            u for u in universe
            if u.get("market") == "KOSPI"
            and u.get("market_cap", 0) >= p["min_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rule = rule_volume_dryup(
            recent_window=int(params.get("recent_window", 10)),
            base_window=int(params.get("base_window", 30)),
            ratio_max=float(params.get("ratio_max", 0.70)),
        )
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        # 건조도 클수록(=비율 낮을수록) 우선 → score = 1/ratio 근사. reason에 비율 포함.
        reason = "; ".join(getattr(res, "reasons", []) or ["volume_dryup"])
        score = float(df["volume"].iloc[-30:].mean())  # 유동성 큰 쪽 우선(동률 깨기)
        return (score, reason)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_screener_minervini.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add strategies/minervini_volume_dryup/screener.py tests/test_screener_minervini.py
git commit -m "feat(screener): Minervini 거래량건조 스크리너 어댑터"
```

---

## Task 4: book_pullback_ma20 스크리너 어댑터

**Files:**
- Create: `strategies/book_pullback_ma20/screener.py`
- Test: `tests/test_screener_ma20.py`

**기초필터:** 중소형(market_cap 상한). **룰:** `rule_daily_ma20_pullback`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_screener_ma20.py
import pandas as pd
from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter


def _ma20_pullback_df():
    # 30일 내 +25% 급등 후 20일선 부근 눌림 양봉
    closes = [1000] * 5 + [1000 + i * 60 for i in range(20)] + [2100, 2050, 2080]
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": [c - 30 for c in closes],
        "high": [c + 20 for c in closes],
        "low": [c - 40 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def test_match_returns_tuple_or_none():
    a = BookPullbackMa20ScreenerAdapter()
    df = _ma20_pullback_df()
    verdict = a.match(df, a.default_params())
    # 룰 트리거 시 (score, reason), 아니면 None — 타입 계약만 검증
    assert verdict is None or (isinstance(verdict, tuple) and len(verdict) == 2)


def test_base_filter_excludes_megacap():
    a = BookPullbackMa20ScreenerAdapter()
    universe = [
        {"code": "S", "name": "small", "market": "KOSPI", "market_cap": 1e11, "trading_value": 1e9},
        {"code": "M", "name": "mega", "market": "KOSPI", "market_cap": 5e13, "trading_value": 1e9},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "S" in kept and "M" not in kept
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_screener_ma20.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# strategies/book_pullback_ma20/screener.py
"""MA20 눌림목 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.haru_silijeon.rules_daily import rule_daily_ma20_pullback


class BookPullbackMa20ScreenerAdapter(RuleScreenerBase):
    strategy_name = "book_pullback_ma20"
    lookback_days = 90

    def default_params(self) -> Dict[str, Any]:
        return {
            "max_market_cap": 3_000_000_000_000,  # 중소형: 3조 이하
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        return [
            u for u in universe
            if 0 < u.get("market_cap", 0) <= p["max_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        res = rule_daily_ma20_pullback().evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["daily_ma20_pullback"])
        score = float(df["volume"].iloc[-20:].mean())
        return (score, reason)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_screener_ma20.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add strategies/book_pullback_ma20/screener.py tests/test_screener_ma20.py
git commit -m "feat(screener): MA20 눌림 스크리너 어댑터"
```

---

## Task 5: book_pullback_ma5 스크리너 어댑터

**Files:**
- Create: `strategies/book_pullback_ma5/screener.py`
- Test: `tests/test_screener_ma5.py`

**기초필터:** 중소형. **룰:** `rule_ma5_pullback`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_screener_ma5.py
import pandas as pd
from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter


def test_match_returns_tuple_or_none():
    a = BookPullbackMa5ScreenerAdapter()
    closes = [1000] * 5 + [1000 + i * 60 for i in range(15)] + [1900, 1870, 1890]
    n = len(closes)
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": [c - 20 for c in closes], "high": [c + 15 for c in closes],
        "low": [c - 25 for c in closes], "close": closes, "volume": [1000] * n,
    })
    verdict = a.match(df, a.default_params())
    assert verdict is None or (isinstance(verdict, tuple) and len(verdict) == 2)


def test_base_filter_excludes_megacap():
    a = BookPullbackMa5ScreenerAdapter()
    universe = [
        {"code": "S", "name": "s", "market": "KOSDAQ", "market_cap": 5e10, "trading_value": 1e9},
        {"code": "M", "name": "m", "market": "KOSPI", "market_cap": 5e13, "trading_value": 1e9},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "S" in kept and "M" not in kept
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_screener_ma5.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# strategies/book_pullback_ma5/screener.py
"""MA5 단기 눌림목 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.trading_legends.rules_daily import rule_ma5_pullback


class BookPullbackMa5ScreenerAdapter(RuleScreenerBase):
    strategy_name = "book_pullback_ma5"
    lookback_days = 60

    def default_params(self) -> Dict[str, Any]:
        return {
            "max_market_cap": 3_000_000_000_000,
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        return [
            u for u in universe
            if 0 < u.get("market_cap", 0) <= p["max_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        res = rule_ma5_pullback().evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["ma5_pullback"])
        score = float(df["volume"].iloc[-5:].mean())
        return (score, reason)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_screener_ma5.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add strategies/book_pullback_ma5/screener.py tests/test_screener_ma5.py
git commit -m "feat(screener): MA5 눌림 스크리너 어댑터"
```

---

## Task 6: daytrading_3methods 스크리너 어댑터

**Files:**
- Create: `strategies/daytrading_3methods_breakout/screener.py`
- Test: `tests/test_screener_daytrading.py`

**기초필터:** KOSDAQ + 시총<5000억. **룰:** `rule_breakout_prev_high`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_screener_daytrading.py
import pandas as pd
from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter


def _breakout_df():
    # 직전 20봉 고가 ~1100, 마지막 봉 종가 1300 돌파 + 거래량 폭증 + 양봉
    closes = [1000 + (i % 5) * 20 for i in range(20)] + [1300]
    n = len(closes)
    vols = [1000] * 20 + [3000]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": [c - 5 for c in closes[:-1]] + [1250],
        "high": [1100] * 20 + [1320],
        "low": [c - 10 for c in closes],
        "close": closes,
        "volume": vols,
    })


def test_match_triggers_on_breakout():
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    verdict = a.match(_breakout_df(), a.default_params())
    assert verdict is not None
    assert "breakout" in verdict[1].lower()


def test_base_filter_kosdaq_smallcap_only():
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    universe = [
        {"code": "K", "name": "k", "market": "KOSDAQ", "market_cap": 3e11, "trading_value": 1e9},
        {"code": "B", "name": "b", "market": "KOSDAQ", "market_cap": 1e12, "trading_value": 1e9},
        {"code": "P", "name": "p", "market": "KOSPI", "market_cap": 3e11, "trading_value": 1e9},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == ["K"]  # KOSDAQ + 시총<5000억만
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_screener_daytrading.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# strategies/daytrading_3methods_breakout/screener.py
"""유지윤 전고 돌파 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high


class Daytrading3MethodsBreakoutScreenerAdapter(RuleScreenerBase):
    strategy_name = "daytrading_3methods_breakout"
    lookback_days = 60

    def default_params(self) -> Dict[str, Any]:
        return {
            "high_window": 20,
            "vol_lookback": 20,
            "vol_mult": 2.0,
            "max_market_cap": 500_000_000_000,  # 5천억 미만
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        return [
            u for u in universe
            if u.get("market") == "KOSDAQ"
            and 0 < u.get("market_cap", 0) < p["max_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rule = rule_breakout_prev_high(
            high_window=int(params.get("high_window", 20)),
            vol_lookback=int(params.get("vol_lookback", 20)),
            vol_mult=float(params.get("vol_mult", 2.0)),
        )
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["breakout_prev_high"])
        score = float(df["volume"].iloc[-1])
        return (score, reason)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_screener_daytrading.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add strategies/daytrading_3methods_breakout/screener.py tests/test_screener_daytrading.py
git commit -m "feat(screener): 유지윤 돌파 스크리너 어댑터"
```

---

## Task 7: build_adapter 5전략 등록

**Files:**
- Modify: `runners/_adapter_factory.py`
- Test: `tests/test_adapter_factory_active.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_adapter_factory_active.py
import pytest
from runners._adapter_factory import build_adapter

ACTIVE = [
    "elder_ema_pullback", "minervini_volume_dryup",
    "book_pullback_ma20", "book_pullback_ma5", "daytrading_3methods_breakout",
]

@pytest.mark.parametrize("name", ACTIVE)
def test_build_adapter_for_active_strategies(name):
    a = build_adapter(name)
    assert a is not None
    assert a.strategy_name == name
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_adapter_factory_active.py -v`
Expected: FAIL (5개 모두 None → assertion)

- [ ] **Step 3: 구현** — `runners/_adapter_factory.py` 의 `build_adapter` 내 `else:` 직전에 분기 추가

```python
        elif strategy_name == "elder_ema_pullback":
            from strategies.elder_ema_pullback.screener import ElderEmaPullbackScreenerAdapter
            return ElderEmaPullbackScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "minervini_volume_dryup":
            from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter
            return MinerviniVolumeDryupScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "book_pullback_ma20":
            from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter
            return BookPullbackMa20ScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "book_pullback_ma5":
            from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter
            return BookPullbackMa5ScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "daytrading_3methods_breakout":
            from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter
            return Daytrading3MethodsBreakoutScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_adapter_factory_active.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add runners/_adapter_factory.py tests/test_adapter_factory_active.py
git commit -m "feat(screener): build_adapter에 활성 5전략 등록"
```

---

## Task 8: EOD 수집기 — 활성 config 전략 파생

**Files:**
- Modify: `runners/screener_snapshot_collector.py` (헬퍼 추가)
- Modify: `bot/liquidation_handler.py:437-445` (ALL_STRATEGIES → 활성 전략)
- Test: `tests/test_active_strategies_resolver.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_active_strategies_resolver.py
from runners.screener_snapshot_collector import resolve_active_strategies


def test_resolve_from_config_strategies():
    config = type("C", (), {})()
    config.strategies = [
        {"name": "elder_ema_pullback", "enabled": True},
        {"name": "minervini_volume_dryup", "enabled": True},
        {"name": "disabled_one", "enabled": False},
    ]
    out = resolve_active_strategies(config)
    assert out == ["elder_ema_pullback", "minervini_volume_dryup"]


def test_resolve_fallback_to_all_when_no_config():
    out = resolve_active_strategies(None)
    assert isinstance(out, list) and len(out) > 0
```

> config.strategies 의 실제 형태(dict 리스트 vs 객체)는 config/trading_config.json 로드 결과를 따른다. 구현 시 dict/obj 양쪽 안전 접근.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_active_strategies_resolver.py -v`
Expected: FAIL (`ImportError: resolve_active_strategies`)

- [ ] **Step 3: 구현** — `runners/screener_snapshot_collector.py` 상단(`ALL_STRATEGIES` 정의 다음)에 추가

```python
def resolve_active_strategies(config) -> List[str]:
    """config 의 활성(enabled) 전략 폴더키 목록. config 없으면 ALL_STRATEGIES 폴백."""
    if config is None:
        return list(ALL_STRATEGIES)
    strategies = getattr(config, "strategies", None)
    if not strategies:
        return list(ALL_STRATEGIES)
    out: List[str] = []
    for s in strategies:
        if isinstance(s, dict):
            name, enabled = s.get("name"), s.get("enabled", True)
        else:
            name, enabled = getattr(s, "name", None), getattr(s, "enabled", True)
        if name and enabled:
            out.append(name)
    return out or list(ALL_STRATEGIES)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_active_strategies_resolver.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: liquidation_handler 배선 수정** — `bot/liquidation_handler.py` 의 import·호출 변경

```python
# 변경 전: from runners.screener_snapshot_collector import run_once, ALL_STRATEGIES
from runners.screener_snapshot_collector import run_once, resolve_active_strategies
...
            summaries = run_once(
                strategies=resolve_active_strategies(config),   # ALL_STRATEGIES → 활성 전략
                scan_date=scan_date,
                max_candidates=10,
                dry_run=False,
                broker=broker,
                db_manager=db_manager,
                config=config,
            )
```

- [ ] **Step 6: 회귀 확인 + 커밋**

Run: `python -m pytest tests/test_active_strategies_resolver.py -v`
Expected: PASS

```bash
git add runners/screener_snapshot_collector.py bot/liquidation_handler.py tests/test_active_strategies_resolver.py
git commit -m "feat(screener): EOD 스냅샷을 활성 config 전략으로 수집"
```

---

## Task 9: get_selected_stocks owner 격리

**Files:**
- Modify: `core/trading_context.py:243-250`
- Test: `tests/test_get_selected_stocks_owner.py`

**계약:** `get_selected_stocks()`는 기본적으로 현재 전략(`self._strategy_key`) 소유 종목만 반환. owner 정보는 `TradingStock.strategy_name`(폴더키)으로 매칭. 미설정(None) 종목은 공용으로 간주해 포함.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_get_selected_stocks_owner.py
from unittest.mock import Mock
from core.trading_context import TradingContext
from core.models import StockState


def _stock(code, owner):
    s = Mock()
    s.stock_code = code
    s.strategy_name = owner
    return s


def _ctx_with_selected(strategy_key, stocks):
    ctx = TradingContext.__new__(TradingContext)
    ctx.logger = Mock()
    ctx._strategy_key = strategy_key
    tm = Mock()
    tm.get_stocks_by_state.return_value = stocks
    ctx._trading_manager = tm
    return ctx


def test_returns_only_own_and_unowned():
    stocks = [
        _stock("A", "elder_ema_pullback"),
        _stock("B", "minervini_volume_dryup"),
        _stock("C", None),
    ]
    ctx = _ctx_with_selected("elder_ema_pullback", stocks)
    codes = [s.stock_code for s in ctx.get_selected_stocks()]
    assert codes == ["A", "C"]            # 자기 소유 + 미지정만


def test_explicit_owner_arg_overrides():
    stocks = [_stock("A", "elder_ema_pullback"), _stock("B", "minervini_volume_dryup")]
    ctx = _ctx_with_selected("elder_ema_pullback", stocks)
    codes = [s.stock_code for s in ctx.get_selected_stocks(owner="minervini_volume_dryup")]
    assert codes == ["B"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_get_selected_stocks_owner.py -v`
Expected: FAIL (현재 owner 필터 없음 → 전체 반환)

- [ ] **Step 3: 구현** — `core/trading_context.py` get_selected_stocks 교체

```python
    def get_selected_stocks(self, owner: 'Optional[str]' = None) -> List:
        """SELECTED 상태 종목 목록 반환 (owner 격리).

        owner 미지정 시 현재 전략(_strategy_key) 소유 + 소유자 미지정(공용) 종목만 반환.
        owner 지정 시 해당 전략 소유 종목만 반환.
        """
        from core.models import StockState
        try:
            stocks = self._trading_manager.get_stocks_by_state(StockState.SELECTED)
        except Exception as e:
            self.logger.debug(f"SELECTED 종목 조회 실패: {e}")
            return []
        target = owner if owner is not None else getattr(self, "_strategy_key", None)
        if not target:
            return stocks  # 레거시(단일/미할당): 전체 반환
        result = []
        for s in stocks:
            so = getattr(s, "strategy_name", None)
            if owner is not None:
                if so == owner:
                    result.append(s)
            else:
                if so == target or not so:   # 자기 소유 또는 공용
                    result.append(s)
        return result
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_get_selected_stocks_owner.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 회귀 — 기존 trading_context 테스트**

Run: `python -m pytest tests/ -k "trading_context or selected" -v`
Expected: 신규 2 PASS, 기존 무영향(레거시 _strategy_key 미설정 시 전체 반환 보존).

- [ ] **Step 6: 커밋**

```bash
git add core/trading_context.py tests/test_get_selected_stocks_owner.py
git commit -m "feat(screener): get_selected_stocks owner 격리"
```

---

## Task 10: 거래량순위 폴백 제거 (전략별 스냅샷 모드)

**Files:**
- Modify: `main.py` `_load_candidates_multi_strategy` (591~660 부근)
- Test: `tests/test_no_volume_fallback.py`

**계약:** 전략별 스크리너 스냅샷이 활성일 때, 특정 전략 후보 0건이면 그 전략은 후보 0으로 둔다(거래량순위 공유 폴백 호출 안 함). 단 **모든 전략이 0건**이면 안전망으로 기존 거래량 폴백 1회 허용(부트스트랩/장애 대비) — 플래그 `allow_volume_fallback_when_all_empty=True`.

- [ ] **Step 1: 실패 테스트 작성** — `_load_candidates_multi_strategy` 의 폴백 결정 로직을 순수함수로 추출해 테스트

```python
# tests/test_no_volume_fallback.py
from main import should_use_volume_fallback


def test_no_fallback_when_some_strategy_has_candidates():
    per = {"elder_ema_pullback": ["005930"], "book_pullback_ma5": []}
    assert should_use_volume_fallback(per) is False


def test_fallback_only_when_all_empty():
    per = {"elder_ema_pullback": [], "book_pullback_ma5": []}
    assert should_use_volume_fallback(per) is True
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_no_volume_fallback.py -v`
Expected: FAIL (`ImportError: should_use_volume_fallback`)

- [ ] **Step 3: 구현** — `main.py` 모듈 레벨에 순수함수 추가 + 기존 폴백 분기를 이 함수로 게이트

```python
def should_use_volume_fallback(per_strategy_candidates: dict) -> bool:
    """전략별 후보 dict 기준 거래량순위 폴백 사용 여부.

    하나라도 후보가 있으면 폴백 안 함(전략별 격리 유지).
    전부 비었을 때만 안전망으로 폴백.
    """
    if not per_strategy_candidates:
        return True
    return all(not v for v in per_strategy_candidates.values())
```

그리고 `_load_candidates_multi_strategy` 내부에서, 각 전략별 폴백을 무조건 호출하던 부분을 다음과 같이 게이트:

```python
        per = self.candidate_selector.select_candidates_per_strategy(
            self.strategies, max_per_strategy=max_per_strategy,
        )
        if should_use_volume_fallback(per):
            self.logger.info("[E6] 전 전략 후보 0건 → 거래량 순위 폴백(안전망) 1회")
            # (기존 거래량순위 폴백 경로 호출 — 공유 풀)
            ...
        else:
            # 전략별 후보를 owner=폴더키로 등록 (기존 등록 경로 사용)
            ...
```

> 구현 시: 기존 `[E6] {name}: 후보 없음 → 거래량 순위 fallback 시작` 루프(전략별 무조건 폴백)를 위 게이트로 대체. 등록 시 `ts.strategy_name = strategy_name`(폴더키) 보장(기존 동작 유지).

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_no_volume_fallback.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add main.py tests/test_no_volume_fallback.py
git commit -m "feat(screener): 전략별 후보 존재 시 거래량폴백 제거"
```

---

## Task 11: D-1 휴장일 폴백 검증

**Files:**
- Read/verify: `core/candidate_selector.py:880-929` (`_fetch_candidates_for_strategy`), `get_previous_trading_day`
- Test: `tests/test_snapshot_d1_holiday.py`

**목적:** D-1이 휴장일(예: 06-04의 D-1=06-03 지방선거)일 때 직전 거래일 스냅샷을 읽는지 확인. `get_previous_trading_day`가 이미 거래일을 반환하면 추가 구현 불필요(검증만), 아니면 보정.

- [ ] **Step 1: 동작 확인 테스트**

```python
# tests/test_snapshot_d1_holiday.py
from datetime import datetime
from utils.korean_time import now_kst
from core.candidate_selector import get_previous_trading_day  # 실제 import 경로 확인


def test_previous_trading_day_skips_holiday():
    # 2026-06-04(목)의 직전 거래일은 06-03(지방선거 휴장)이 아니라 06-02여야 함
    d = datetime(2026, 6, 4, 9, 0)
    prev = get_previous_trading_day(d)
    assert prev.strftime("%Y-%m-%d") == "2026-06-02"
```

> import 경로는 candidate_selector 가 사용하는 것과 동일하게 맞춘다(파일 상단 import 확인).

- [ ] **Step 2: 실행**

Run: `python -m pytest tests/test_snapshot_d1_holiday.py -v`
Expected: PASS 면 폴백 정상(추가 구현 불필요) → Step 4로. FAIL(06-03 반환)이면 Step 3.

- [ ] **Step 3: (FAIL 시에만) 보정** — `_fetch_candidates_for_strategy` 의 prev_trading_day 산출을 거래일 캘린더 기반으로 교체(`korean_holidays`로 휴장 스킵). 통과할 때까지 반복.

- [ ] **Step 4: 커밋**

```bash
git add tests/test_snapshot_d1_holiday.py
git commit -m "test(screener): D-1 휴장일 폴백 검증"
```

---

## Task 12: 통합 E2E — 실DB 스냅샷 1전략

**Files:**
- Test: `tests/test_screener_e2e_db.py`

**목적:** 실 DB(daily_prices)에서 한 전략 어댑터가 스캔→CandidateStock을 반환하는지(실데이터 스모크). DB 없으면 skip.

- [ ] **Step 1: 스모크 테스트**

```python
# tests/test_screener_e2e_db.py
import pytest
from datetime import date

try:
    from db.database_manager import DatabaseManager
    _db = DatabaseManager()
except Exception:
    _db = None


@pytest.mark.skipif(_db is None, reason="DB 불가")
def test_minervini_scan_runs_on_real_db():
    from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter
    a = MinerviniVolumeDryupScreenerAdapter(db_manager=_db)
    out = a.scan(date(2026, 6, 4), a.default_params())
    # 결과는 0개 이상이며, 있으면 CandidateStock 형태
    assert isinstance(out, list)
    for c in out:
        assert c.code and c.reason
```

- [ ] **Step 2: 실행**

Run: `python -m pytest tests/test_screener_e2e_db.py -v`
Expected: PASS (반환 리스트, 타입 정상). 예외 시 base/adapter 수정.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_screener_e2e_db.py
git commit -m "test(screener): 실DB 스캔 스모크"
```

---

## Task 13: 전체 회귀 + EOD 수동 실행 검증

**Files:** 없음(검증)

- [ ] **Step 1: 관련 전체 회귀**

Run: `python -m pytest tests/ -k "screener or candidate or trading_context or adapter or fallback" -v`
Expected: 신규 전부 PASS, 기존 무영향(인터프리터별 psycopg2/asyncio 사전존재 실패는 제외).

- [ ] **Step 2: EOD 수집 수동 실행(dry-run)** — 활성 5전략 스냅샷 생성 확인

Run:
```bash
python -c "from db.database_manager import DatabaseManager; from runners.screener_snapshot_collector import run_once, resolve_active_strategies; import datetime; db=DatabaseManager(); print(run_once(resolve_active_strategies(None) if False else ['elder_ema_pullback','minervini_volume_dryup','book_pullback_ma20','book_pullback_ma5','daytrading_3methods_breakout'], datetime.date(2026,6,4), 10, True, db_manager=db))"
```
Expected: 5전략 각각 count(0 이상) 출력, 예외 없음.

- [ ] **Step 3: 최종 커밋(있으면)**

```bash
git add -A
git commit -m "test(screener): 전략별 스크리너 통합 회귀 검증"
```

---

## 검증 기준 (완료 정의)
- Task1~12 테스트 전부 그린.
- EOD dry-run에서 활성 5전략 폴더키로 스캔 실행(예외 없음).
- (라이브 후속) 봇 재시작 후 EOD → screener_snapshots에 5전략 저장 → 익일 `[E6] {전략}: screener_snapshots N건` 로그 + 전략별 상이한 `매수검토 N종목` + 거래량폴백 로그 없음.

## 자체 검토 메모
- 스펙 ②(전종목→전략별 기초필터): Task1 _load_universe + 각 어댑터 base_filter로 커버.
- 스펙 ③(엄격격리+폴백제거): Task9(owner)+Task10(폴백 게이트)로 커버.
- 스펙 D-1 휴장 폴백: Task11로 커버(검증 우선, 필요시 보정).
- 룩어헤드: Task1 절단 + 테스트.
- 미커버 위험: 룰 `.evaluate(df, ctx={})` 호출이 ctx 필드를 요구하면 해당 어댑터 Step4에서 드러남 → ctx에 필요한 최소값 주입으로 보정(각 어댑터 태스크 내 처리).
