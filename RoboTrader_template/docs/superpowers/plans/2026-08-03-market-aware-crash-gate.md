# 급락 게이트 시장 정합 (Market-Aware Crash Gate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 급락 게이트(`check_market_direction`)의 판정 지수를 매수 대상 종목의 소속 시장으로 정해, 8전략 전부의 보호 누락(daytrading)과 과잉 차단(나머지 7전략)을 동시에 해소한다.

**Architecture:** 공용 함수를 건드리지 않는다. 게이트 호출 **직전에** `resolve_regime_index(configured, stock_code)`로 해석해 기존 시그니처에 `"KOSPI"|"KOSDAQ"|"both"|"none"` 문자열을 넘긴다. 시장 매핑은 신규 `stock_market` 테이블 + FDR 수집기로 채우고, 프로세스 메모리에 캐시한다. 활성화는 마지막 Task의 config 전환 하나로만 일어난다.

**Tech Stack:** Python 3.8+ · psycopg2 · FinanceDataReader (`finance-datareader>=0.9.202`, 이미 선언·실사용) · pytest

**설계 문서:** [`../specs/2026-08-03-market-aware-crash-gate-design.md`](../specs/2026-08-03-market-aware-crash-gate-design.md) (커밋 `bf1c2eb`)

## Global Constraints

- **`daily_prices`에 컬럼을 추가하지 않는다.** 별도 세션이 이 테이블에 DELETE 동반 전 이력 교체(FAIL 471종목)를 대기 중이다(`6c4cffc` 후속).
- **`check_market_direction` / `check_regime_gate` / `analyze_buy_decision`의 시그니처를 바꾸지 않는다.** 캐시 키가 `regime_index` 문자열(TTL 60초)이라 종목코드가 들어가면 조용히 오염된다.
- **`check_regime_gate`에는 resolved를 넘기지 않는다.** PIT 일봉 국면게이트는 범위 밖이다(설계 §5). `regime_gate` 호출은 기존 config 값을 그대로 유지한다.
- **기존 `market` 필드를 폴백으로 쓰지 않는다.** `stock_list.json`은 962종목 전부 `"KOSPI"`로 오염됐고, `stock_sector` 테이블은 `kis_template`에 존재하지 않는다.
- **KIS API를 호출하지 않는다.** 매핑 수집은 FDR 전용이다(앱키당 토큰 1개라 봇 가동 중 KIS 호출은 라이브 토큰을 무효화한다).
- **테스트를 라이브 트리에서 실행하지 않는다.** 프로젝트 영구 규칙. 구현은 git worktree에서 진행하고 거기서 pytest를 돌린다.
- 시장 라벨 문자열은 `"KOSPI"` / `"KOSDAQ"` 두 값만 쓴다(지수 테이블 `index_daily.index_code`와 동일 표기).
- 커밋 메시지는 conventional 헤더 + 한글 본문, 끝에 `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## File Structure

| 파일 | 책임 |
|---|---|
| `scripts/kis_db/schema.py` (수정) | `stock_market` 테이블 DDL 추가 |
| `collectors/stock_market_writer.py` (신규) | FDR DataFrame → 행 변환(순수) + UPSERT |
| `collectors/stock_market_collector.py` (신규) | FDR `StockListing` 호출 + 오케스트레이션 |
| `core/regime/market_classifier.py` (신규) | 매핑 메모리 캐시 리더 + `resolve_regime_index`(순수) |
| `core/trading_context.py` (수정) | 게이트 호출 직전 해석 배선 |
| `core/trading_decision_engine.py` (수정) | 게이트 호출 직전 해석 배선 |
| `collectors/eod_collection.py` (수정) | EOD 파이프라인에 매핑 수집 등록 |
| `config/trading_config.json` (수정) | 8전략 `regime_index: "auto"` — **활성화 스위치** |

**`bot/trading_analyzer.py`는 수정하지 않는다.** 이 파일은 `analyze_buy_decision(regime_index=...)`을 호출할 뿐이고, 실제 게이트 호출은 `trading_decision_engine.py:320`에서 일어나며 그 함수는 `trading_stock.stock_code`를 이미 `code`로 보유한다(`:316`).

---

### Task 1: `stock_market` 테이블 + writer

**Files:**
- Modify: `scripts/kis_db/schema.py` (`create_all` 내 DDL 목록에 추가)
- Create: `collectors/stock_market_writer.py`
- Test: `tests/collectors/test_stock_market_writer.py`

**Interfaces:**
- Produces: `fdr_df_to_market_rows(market: str, df) -> list[dict]` — 각 dict는 `{"stock_code": str, "market": str}`
- Produces: `upsert_market_rows(conn, rows: list[dict]) -> int`

- [ ] **Step 1: Write the failing test**

`tests/collectors/test_stock_market_writer.py`:

```python
import pandas as pd
from collectors.stock_market_writer import fdr_df_to_market_rows


def test_fdr_df_to_market_rows_maps_code_and_market():
    df = pd.DataFrame({"Code": ["005930", "000660"], "Name": ["삼성전자", "SK하이닉스"]})
    rows = fdr_df_to_market_rows("KOSPI", df)
    assert rows == [
        {"stock_code": "005930", "market": "KOSPI"},
        {"stock_code": "000660", "market": "KOSPI"},
    ]


def test_fdr_df_to_market_rows_empty():
    assert fdr_df_to_market_rows("KOSPI", pd.DataFrame()) == []
    assert fdr_df_to_market_rows("KOSPI", None) == []


def test_fdr_df_to_market_rows_zero_pads_short_codes():
    # FDR 이 정수로 준 코드를 6자리로 복원해야 daily_prices 와 조인된다
    df = pd.DataFrame({"Code": [5930], "Name": ["삼성전자"]})
    assert fdr_df_to_market_rows("KOSPI", df) == [{"stock_code": "005930", "market": "KOSPI"}]


def test_fdr_df_to_market_rows_skips_blank_codes():
    df = pd.DataFrame({"Code": ["005930", None, ""], "Name": ["a", "b", "c"]})
    assert fdr_df_to_market_rows("KOSDAQ", df) == [{"stock_code": "005930", "market": "KOSDAQ"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/collectors/test_stock_market_writer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.stock_market_writer'`

- [ ] **Step 3: Write minimal implementation**

`collectors/stock_market_writer.py`:

```python
"""FDR 상장목록 df → stock_market 행 + UPSERT.

시장 라벨의 유일한 소스다. `stock_list.json`·`stock_sector` 의 market 필드는
전부 "KOSPI" 로 오염돼 있으므로 폴백으로도 쓰지 않는다(2026-08-03 실측).
"""

_UPSERT = """
INSERT INTO stock_market (stock_code, market)
VALUES (%(stock_code)s, %(market)s)
ON CONFLICT (stock_code) DO UPDATE SET
    market=EXCLUDED.market, updated_at=now()
"""


def fdr_df_to_market_rows(market: str, df) -> list:
    if df is None or len(df) == 0:
        return []
    rows = []
    for _, r in df.iterrows():
        raw = r.get("Code")
        if raw is None:
            continue
        code = str(raw).strip()
        if not code or code.lower() == "nan":
            continue
        rows.append({"stock_code": code.zfill(6), "market": market})
    return rows


def upsert_market_rows(conn, rows) -> int:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT, r)
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Add the table DDL**

`scripts/kis_db/schema.py` — 다른 `CREATE TABLE IF NOT EXISTS` 블록과 같은 자리(`create_all`이 실행하는 DDL 목록)에 추가:

```sql
    CREATE TABLE IF NOT EXISTS stock_market (
        stock_code   VARCHAR(10) PRIMARY KEY,
        market       VARCHAR(10) NOT NULL,
        updated_at   TIMESTAMPTZ DEFAULT now()
    );
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/collectors/test_stock_market_writer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add scripts/kis_db/schema.py collectors/stock_market_writer.py tests/collectors/test_stock_market_writer.py
git commit -F - <<'EOF'
feat(collectors): stock_market 매핑 테이블 + writer

시장 라벨의 단일 소스를 신설한다. 기존 `stock_list.json`(962종목 전부 KOSPI)
과 `stock_sector`(kis_template 에 부재)는 오염이라 폴백으로도 쓰지 않는다.

`daily_prices` 에 컬럼을 붙이지 않은 이유: 별도 트랙이 그 테이블에 DELETE 동반
전 이력 교체를 대기 중이다(`6c4cffc` 후속).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: FDR 매핑 수집기

**Files:**
- Create: `collectors/stock_market_collector.py`
- Test: `tests/collectors/test_stock_market_collector.py`

**Interfaces:**
- Consumes: `fdr_df_to_market_rows`, `upsert_market_rows` (Task 1)
- Produces: `collect_stock_market(listing_fn=None, conn=None) -> dict` — 반환 `{"KOSPI": int, "KOSDAQ": int, "overlap": int}`

`listing_fn`은 테스트 주입용이다. 기본값은 `FinanceDataReader.StockListing`.

- [ ] **Step 1: Write the failing test**

`tests/collectors/test_stock_market_collector.py`:

```python
import pandas as pd
import pytest
from collectors.stock_market_collector import collect_stock_market


class FakeCursor:
    def __init__(self, sink): self.sink = sink
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None): self.sink.append(params)


class FakeConn:
    def __init__(self): self.rows = []; self.commits = 0
    def cursor(self): return FakeCursor(self.rows)
    def commit(self): self.commits += 1


def _listing(mapping):
    def fn(market):
        return pd.DataFrame({"Code": mapping[market]})
    return fn


def test_collect_writes_both_markets():
    conn = FakeConn()
    res = collect_stock_market(
        listing_fn=_listing({"KOSPI": ["005930"], "KOSDAQ": ["035720", "247540"]}),
        conn=conn,
    )
    assert res["KOSPI"] == 1
    assert res["KOSDAQ"] == 2
    assert res["overlap"] == 0
    assert {"stock_code": "005930", "market": "KOSPI"} in conn.rows
    assert {"stock_code": "247540", "market": "KOSDAQ"} in conn.rows


def test_collect_raises_when_a_market_is_empty():
    # 한쪽이 비면 조용한 수집 실패다 — 기존 매핑을 덮어쓰지 않고 즉시 실패시킨다
    conn = FakeConn()
    with pytest.raises(RuntimeError, match="KOSDAQ"):
        collect_stock_market(
            listing_fn=_listing({"KOSPI": ["005930"], "KOSDAQ": []}), conn=conn
        )
    assert conn.rows == []


def test_collect_raises_on_overlap():
    # 같은 코드가 양쪽에 있으면 라벨이 모순이다 — 쓰지 않는다
    conn = FakeConn()
    with pytest.raises(RuntimeError, match="교집합"):
        collect_stock_market(
            listing_fn=_listing({"KOSPI": ["005930"], "KOSDAQ": ["005930"]}), conn=conn
        )
    assert conn.rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/collectors/test_stock_market_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.stock_market_collector'`

- [ ] **Step 3: Write minimal implementation**

`collectors/stock_market_collector.py`:

```python
"""종목→시장(KOSPI/KOSDAQ) 매핑 수집 — FDR StockListing → stock_market.

usage:
  python -m collectors.stock_market_collector

⚠️ KIS API 를 쓰지 않는다. 앱키당 토큰이 1개라 봇 가동 중 KIS 호출은 라이브
   토큰을 무효화한다. FDR 은 KIS 와 무관하므로 장중에도 안전하다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.stock_market_writer import (  # noqa: E402
    fdr_df_to_market_rows,
    upsert_market_rows,
)
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
MARKETS = ("KOSPI", "KOSDAQ")


def _default_listing(market: str):
    import FinanceDataReader as fdr
    return fdr.StockListing(market)


def collect_stock_market(listing_fn=None, conn=None) -> dict:
    """FDR 로 KOSPI/KOSDAQ 상장목록을 받아 stock_market 에 UPSERT.

    검증을 통과하지 못하면 **한 행도 쓰지 않고** RuntimeError 를 낸다.
    부분 수집으로 기존 매핑을 오염시키지 않기 위해서다.
    """
    fn = listing_fn or _default_listing

    collected = {}
    for market in MARKETS:
        rows = fdr_df_to_market_rows(market, fn(market))
        if not rows:
            raise RuntimeError(f"시장 매핑 수집 실패: {market} 0건 (기존 매핑 보존)")
        collected[market] = rows

    codes = {m: {r["stock_code"] for r in rs} for m, rs in collected.items()}
    overlap = codes["KOSPI"] & codes["KOSDAQ"]
    if overlap:
        raise RuntimeError(
            f"시장 매핑 교집합 {len(overlap)}건 — 라벨 모순이라 쓰지 않음: "
            f"{sorted(overlap)[:5]}"
        )

    if conn is not None:
        result = {m: upsert_market_rows(conn, rs) for m, rs in collected.items()}
    else:
        with KisDbConnection.get_connection() as c:
            result = {m: upsert_market_rows(c, rs) for m, rs in collected.items()}

    result["overlap"] = 0
    logger.info(
        f"시장 매핑 수집 완료: KOSPI {result['KOSPI']}종목 · KOSDAQ {result['KOSDAQ']}종목"
    )
    return result


if __name__ == "__main__":
    print(collect_stock_market())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/collectors/test_stock_market_collector.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add collectors/stock_market_collector.py tests/collectors/test_stock_market_collector.py
git commit -F - <<'EOF'
feat(collectors): FDR 시장 매핑 수집기

🔑 부분 수집으로 기존 매핑을 오염시키지 않는다 — 한쪽 시장이 0건이거나
KOSPI∩KOSDAQ 교집합이 있으면 **한 행도 쓰지 않고** RuntimeError.
`index_collector` 의 "new_rows=0 이면 반드시 FAIL"(조용한 수집 실패 탐지)과
같은 방침이다.

KIS API 미사용 — 앱키당 토큰 1개라 봇 가동 중 호출하면 라이브 토큰이 무효화된다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: 매핑 리더 + `resolve_regime_index` (핵심)

**Files:**
- Create: `core/regime/market_classifier.py`
- Test: `tests/regime/test_market_classifier.py`

**Interfaces:**
- Produces: `resolve_regime_index(configured: str, stock_code: str, market_lookup=None) -> str` — 반환은 `"KOSPI"|"KOSDAQ"|"both"|"none"` 중 하나
- Produces: `get_stock_market(stock_code: str) -> Optional[str]` — 프로세스 메모리 캐시 조회
- Produces: `reset_cache() -> None` — 테스트/재적재용

- [ ] **Step 1: Write the failing test**

`tests/regime/test_market_classifier.py`:

```python
from core.regime.market_classifier import resolve_regime_index


def test_non_auto_passes_through_without_lookup():
    """configured != "auto" 면 매핑을 조회조차 하지 않는다 — 기존 동작 100% 보존."""
    def boom(_code):
        raise AssertionError("non-auto 에서 매핑을 조회하면 안 된다")

    assert resolve_regime_index("KOSPI", "005930", market_lookup=boom) == "KOSPI"
    assert resolve_regime_index("KOSDAQ", "035720", market_lookup=boom) == "KOSDAQ"
    assert resolve_regime_index("both", "005930", market_lookup=boom) == "both"
    assert resolve_regime_index("none", "005930", market_lookup=boom) == "none"


def test_auto_resolves_to_stock_market():
    lookup = {"005930": "KOSPI", "035720": "KOSDAQ"}.get
    assert resolve_regime_index("auto", "005930", market_lookup=lookup) == "KOSPI"
    assert resolve_regime_index("auto", "035720", market_lookup=lookup) == "KOSDAQ"


def test_auto_falls_back_to_both_when_unmapped():
    """결측은 보호 과잉 쪽으로만 실패한다 — both 는 두 지수를 모두 검사한다."""
    assert resolve_regime_index("auto", "999999", market_lookup=lambda c: None) == "both"


def test_auto_falls_back_to_both_on_garbage_label():
    """FDR 이 예상 밖 라벨을 주면 그대로 흘리지 않고 both 로 막는다."""
    assert resolve_regime_index("auto", "005930", market_lookup=lambda c: "KONEX") == "both"


def test_auto_falls_back_to_both_when_lookup_raises():
    """DB 장애로 조회가 터져도 매수 경로를 죽이지 않는다."""
    def boom(_code):
        raise RuntimeError("db down")

    assert resolve_regime_index("auto", "005930", market_lookup=boom) == "both"


def test_empty_configured_is_treated_as_both():
    """기존 _get_strategy_regime_settings 의 기본값 규약(None/"" → both)과 일치."""
    assert resolve_regime_index("", "005930", market_lookup=lambda c: "KOSPI") == "both"
    assert resolve_regime_index(None, "005930", market_lookup=lambda c: "KOSPI") == "both"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/regime/test_market_classifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.regime.market_classifier'`

- [ ] **Step 3: Write minimal implementation**

`core/regime/market_classifier.py`:

```python
"""종목 소속 시장 조회 + 급락게이트 판정 지수 해석.

급락게이트(`check_market_direction`)는 캐시 키가 `regime_index` 문자열이라
종목코드를 넘기면 조용히 오염된다. 그래서 **호출 전에** 여기서 해석해
기존 시그니처가 받는 문자열로 바꿔 넘긴다.

⚠️ `stock_list.json`·`stock_sector` 의 market 필드는 전부 "KOSPI" 로 오염돼
   있으므로 폴백으로도 쓰지 않는다(2026-08-03 실측). 소스는 `stock_market` 뿐.
"""
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

VALID_MARKETS = ("KOSPI", "KOSDAQ")
_cache: Optional[dict] = None


def reset_cache() -> None:
    """캐시 무효화 — 매핑 재적재 후/테스트에서 사용."""
    global _cache
    _cache = None


def _load_cache() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    from db.kis_db_connection import KisDbConnection

    mapping = {}
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, market FROM stock_market")
            for code, market in cur.fetchall():
                mapping[str(code)] = str(market)
    _cache = mapping
    logger.info(f"시장 매핑 캐시 로드: {len(mapping)}종목")
    return _cache


def get_stock_market(stock_code: str) -> Optional[str]:
    """종목의 소속 시장. 매핑이 없거나 조회 실패면 None."""
    try:
        return _load_cache().get(str(stock_code))
    except Exception as e:
        logger.warning(f"[시장매핑] 조회 실패(both 폴백): {e}")
        return None


def resolve_regime_index(configured: str, stock_code: str, market_lookup=None) -> str:
    """급락게이트에 넘길 지수 문자열을 정한다.

    configured != "auto"  → 그대로 통과 (기존 동작 100% 보존, 매핑 미조회)
    configured == "auto"  → 종목 소속 시장. 결측/불명이면 "both"

    "both" 는 KOSPI·KOSDAQ 을 모두 검사하므로 결측은 **보호 과잉 쪽으로만**
    실패한다. 무방비 구간이 생기지 않는다.
    """
    cfg = configured or "both"
    if cfg != "auto":
        return cfg

    lookup = market_lookup or get_stock_market
    try:
        market = lookup(stock_code)
    except Exception as e:
        logger.warning(f"[시장매핑] {stock_code} 조회 예외(both 폴백): {e}")
        return "both"

    return market if market in VALID_MARKETS else "both"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/regime/test_market_classifier.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add core/regime/market_classifier.py tests/regime/test_market_classifier.py
git commit -F - <<'EOF'
feat(regime): 종목 소속 시장 기준 급락게이트 지수 해석

`resolve_regime_index(configured, stock_code)` — configured != "auto" 면
매핑을 **조회조차 하지 않고** 그대로 통과시킨다(기존 동작 100% 보존).
아직 배선 전이라 라이브 동작은 변하지 않는다.

🔑 결측은 보호 과잉 쪽으로만 실패한다 — 매핑 없음·불명 라벨·DB 장애 3경로가
전부 "both"(두 지수 모두 검사)로 떨어진다. 무방비 구간이 생기지 않는다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: 호출부 배선 + 캐시 오염 회귀

**Files:**
- Modify: `core/trading_context.py:338-343`
- Modify: `core/trading_decision_engine.py:319-322`
- Test: `tests/regime/test_crash_gate_market_scope.py`

**Interfaces:**
- Consumes: `resolve_regime_index` (Task 3)
- Produces: 없음 (배선만)

- [ ] **Step 1: Write the failing test**

`tests/regime/test_crash_gate_market_scope.py`:

```python
"""급락게이트가 종목 소속 시장으로 판정하는지 — 대칭 단언.

한쪽만 단언하면 판별력이 없다. "KOSPI 종목이 차단된다"만 보면
게이트가 전부 차단해도 통과하기 때문에, 같은 조건에서
"KOSDAQ 종목은 통과한다"를 함께 단언한다.
"""
import pytest

from core.regime.market_classifier import resolve_regime_index


# 2026-08-03 실측: KOSPI -5.29% / KOSDAQ +2.45%
INDEX_CHANGE = {"KOSPI": -5.29, "KOSDAQ": +2.45}
THRESHOLD = {"KOSPI": -2.5, "KOSDAQ": -3.0}
MARKET_OF = {"005930": "KOSPI", "035720": "KOSDAQ"}


def _is_crashing(regime_index: str) -> bool:
    """check_market_direction 의 판정 규칙(:165-168, :186)을 그대로 옮긴 것."""
    if regime_index == "none":
        return False
    checks = []
    if regime_index in ("both", "KOSPI"):
        checks.append("KOSPI")
    if regime_index in ("both", "KOSDAQ"):
        checks.append("KOSDAQ")
    return any(INDEX_CHANGE[n] <= THRESHOLD[n] for n in checks)


def test_auto_blocks_kospi_stock_and_allows_kosdaq_on_2026_08_03():
    """같은 날·같은 설정에서 시장에 따라 판정이 갈려야 한다."""
    kospi = resolve_regime_index("auto", "005930", market_lookup=MARKET_OF.get)
    kosdaq = resolve_regime_index("auto", "035720", market_lookup=MARKET_OF.get)

    assert kospi == "KOSPI" and _is_crashing(kospi) is True
    assert kosdaq == "KOSDAQ" and _is_crashing(kosdaq) is False


def test_cache_key_is_the_resolved_index_not_the_stock():
    """서로 다른 시장 종목을 연속 조회해도 각자 지수로 해석돼야 한다.

    캐시 키가 종목코드로 오염되면 이 단언이 깨진다.
    """
    seq = ["005930", "035720", "005930", "035720"]
    resolved = [resolve_regime_index("auto", c, market_lookup=MARKET_OF.get) for c in seq]
    assert resolved == ["KOSPI", "KOSDAQ", "KOSPI", "KOSDAQ"]
    assert {r for r in resolved} <= {"KOSPI", "KOSDAQ", "both", "none"}


def test_unmapped_stock_is_blocked_on_2026_08_03():
    """결측 → both → KOSPI 급락에 걸려 차단(보호 과잉 쪽)."""
    resolved = resolve_regime_index("auto", "999999", market_lookup=lambda c: None)
    assert resolved == "both"
    assert _is_crashing(resolved) is True


@pytest.mark.parametrize("configured,expected", [
    ("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ"), ("both", "both"), ("none", "none"),
])
def test_legacy_config_values_unchanged(configured, expected):
    """config 를 되돌리면 코드를 되돌리지 않아도 변경 전 동작이 복원된다(롤백 경로)."""
    assert resolve_regime_index(configured, "035720", market_lookup=MARKET_OF.get) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/regime/test_crash_gate_market_scope.py -v`
Expected: 4개 중 일부 FAIL — Task 3 이 이미 있으면 통과할 수도 있다. 통과한다면 **이 테스트는 배선 자체를 검증하지 않는다**는 뜻이므로, Step 3의 배선을 마친 뒤 Step 4에서 실제 호출부가 `resolve_regime_index`를 거치는지 grep으로 확인한다.

- [ ] **Step 3: Wire both call sites**

`core/trading_context.py` — `:338-343`을 다음으로 교체:

```python
            # 전략별 국면 설정 조회 (regime_index/regime_gate). 미설정 전략은 기본값(both/none).
            regime_index, regime_gate = self._get_strategy_regime_settings()

            # regime_index="auto" 면 매수 대상 종목의 소속 시장으로 판정 지수를 정한다.
            # 게이트 캐시 키가 regime_index 문자열이라 여기서 해석해 넘겨야 오염되지 않는다.
            from core.regime.market_classifier import resolve_regime_index
            resolved_index = resolve_regime_index(regime_index, stock_code)

            # 시장 방향성 필터: 종목 소속 시장의 지수 급락 시 매수 스킵
            is_crashing, crash_reason = self._decision_engine.check_market_direction(
                regime_index=resolved_index
            )
```

`:349-351`의 `check_regime_gate` 호출은 **그대로 둔다** — `regime_index=regime_index`(원본). 국면게이트는 범위 밖이다(설계 §5).

`core/trading_decision_engine.py` — `:319-320`을 다음으로 교체:

```python
            # 시장 방향성 필터: 종목 소속 시장의 지수 급락 시 매수 차단.
            # regime_index="auto" 해석은 게이트 호출 전에 끝낸다(캐시 키 오염 방지).
            from core.regime.market_classifier import resolve_regime_index
            resolved_index = resolve_regime_index(regime_index, code)
            is_crashing, crash_reason = self.check_market_direction(regime_index=resolved_index)
```

- [ ] **Step 4: Verify the wiring exists**

Run:
```bash
grep -n "resolve_regime_index" core/trading_context.py core/trading_decision_engine.py
grep -n "check_regime_gate" core/trading_context.py
```
Expected:
- `resolve_regime_index`가 두 파일에 각각 2줄씩(import + 호출) 나온다
- `check_regime_gate` 호출 인자가 여전히 `regime_index=regime_index`(원본)이고 `resolved_index`가 **아니다**

- [ ] **Step 5: Run the full regime + decision engine test suites**

Run: `pytest tests/regime/ tests/test_trading_decision_engine.py -v`
Expected: PASS — 기존 8전략 테스트가 깨지지 않아야 한다(모든 config가 아직 non-auto라 동작 무변경)

- [ ] **Step 6: Commit**

```bash
git add core/trading_context.py core/trading_decision_engine.py tests/regime/test_crash_gate_market_scope.py
git commit -F - <<'EOF'
feat(regime): 급락게이트 호출부에 시장 해석 배선

호출부 2곳(`trading_context.py:341`, `trading_decision_engine.py:320`)에서
게이트 호출 **직전에** resolve 한다. `check_market_direction` 시그니처는
건드리지 않았다 — 캐시 키(TTL 60초)가 여전히 실제 지수라 오염이 구조적으로 불가능.

`bot/trading_analyzer.py` 는 수정하지 않았다. 그 파일은 analyze_buy_decision 을
호출할 뿐이고 실제 게이트 호출은 decision_engine 안에서 일어나며 거기엔
`trading_stock.stock_code` 가 이미 `code` 로 있다(:316).

⚠️ `check_regime_gate` 에는 넘기지 않았다 — KOSDAQ 일봉 국면 SSOT 유무가
미확인이라 넘기면 3전략의 BEAR 차단이 fail-open 으로 조용히 풀린다(설계 §5).

회귀 테스트는 **대칭 단언**이다. "KOSPI 종목 차단"만 보면 전부 차단해도
통과하므로 같은 조건에서 "KOSDAQ 종목 통과"를 함께 단언한다.

이 시점까지 config 는 전부 non-auto 라 라이브 동작은 변하지 않는다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 5: EOD 파이프라인 등록

**Files:**
- Modify: `collectors/eod_collection.py` (`run_data_collection` 오케스트레이터)
- Test: `tests/collectors/test_eod_collection.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: `collect_stock_market` (Task 2), `reset_cache` (Task 3, `reset_market_cache`로 alias import)

> **주의:** `run_data_collection`은 이미 `_safe(fn, *args)` 헬퍼로 단계별 예외를 격리한다(실패 시 해당 키에 `{"error": ...}`). **직접 `try/except`를 쓰지 말고 `_safe`를 쓴다.**
>
> **기존 테스트 1건이 깨진다:** `test_run_data_collection_calls_all_stages`의 `assert calls == ["daily", "minute", "index", "foreign_flow", "corp_events"]` — 단계가 6개가 되므로 이 단언을 함께 갱신해야 한다. 갱신을 빠뜨리면 Step 5에서 실패한다.

- [ ] **Step 1: Write the failing test**

`tests/collectors/test_eod_collection.py`에 추가 (기존 monkeypatch 패턴 그대로):

```python
def test_stock_market_stage_exception_is_isolated(monkeypatch):
    """(단계격리) 시장 매핑 수집 실패가 다른 단계·EOD 흐름을 막지 않는다.

    매핑 결측은 resolve_regime_index 가 "both"(보호 과잉) 로 흡수하지만,
    분봉은 그날 못 받으면 자가치유되지 않는다(minute_collector.py:26-38).
    """
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(
        eod, "collect_stock_market",
        lambda: (_ for _ in ()).throw(RuntimeError("FDR down")))
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")
    out = eod.run_data_collection("20260623")
    assert "error" in out["stock_market"]
    assert out["daily"] == {"rows": 1}
    assert out["minute"] == {"rows": 2}


def test_stock_market_success_resets_classifier_cache(monkeypatch):
    """수집 성공 시 프로세스 캐시를 무효화해야 다음 조회가 새 매핑을 본다."""
    reset_calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 900, "KOSDAQ": 1700})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "reset_market_cache", lambda: reset_calls.append(1))
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")
    out = eod.run_data_collection("20260623")
    assert out["stock_market"] == {"KOSPI": 900, "KOSDAQ": 1700}
    assert reset_calls == [1]


def test_stock_market_failure_does_not_reset_cache(monkeypatch):
    """수집이 실패했으면 기존 캐시를 그대로 둔다(빈 매핑으로 갈아끼우지 않는다)."""
    reset_calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(
        eod, "collect_stock_market",
        lambda: (_ for _ in ()).throw(RuntimeError("FDR down")))
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "reset_market_cache", lambda: reset_calls.append(1))
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")
    eod.run_data_collection("20260623")
    assert reset_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/collectors/test_eod_collection.py -v -k stock_market`
Expected: FAIL — `AttributeError: <module 'collectors.eod_collection'> does not have the attribute 'collect_stock_market'`

- [ ] **Step 3: Register in the orchestrator**

`collectors/eod_collection.py` — import 추가 (다른 collector import 옆):

```python
from collectors.stock_market_collector import collect_stock_market
from core.regime.market_classifier import reset_cache as reset_market_cache
```

`run_data_collection`의 `out` dict에 `index` 다음 줄로 단계 추가하고, dict 생성 뒤 캐시 무효화를 붙인다:

```python
def run_data_collection(trade_date: str = None) -> dict:
    out = {
        "daily": _safe(collect_daily, trade_date),
        "minute": _safe(collect_minute, trade_date),
        "index": _safe(collect_index),
        "stock_market": _safe(collect_stock_market),
        "foreign_flow": _safe(collect_foreign_flow, trade_date),
        "corp_events": _safe(collect_corp_events, trade_date),
        "reconcile": {},
    }
    # 매핑이 실제로 갱신된 경우에만 프로세스 캐시를 무효화한다.
    # 실패했는데 리셋하면 다음 조회가 빈/낡은 테이블을 다시 읽어 매핑을 잃는다.
    if "error" not in out["stock_market"]:
        _safe(reset_market_cache)
```

이후 `if KIS_DATA_SOURCE == "legacy" and trade_date:` 블록은 그대로 둔다. **`reconcile`에 `stock_market`을 추가하지 않는다** — 레거시 DB에 대응 테이블이 없다.

- [ ] **Step 4: Update the broken existing assertion**

`test_run_data_collection_calls_all_stages`에 매핑 단계를 추가하고 순서 단언을 갱신한다:

```python
    monkeypatch.setattr(eod, "collect_stock_market", lambda: calls.append("stock_market") or {"KOSPI": 1, "KOSDAQ": 1})
```
그리고
```python
    assert calls == ["daily", "minute", "index", "stock_market", "foreign_flow", "corp_events"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/collectors/test_eod_collection.py -v`
Expected: PASS (7 passed — 기존 4 + 신규 3)

- [ ] **Step 6: Backfill the mapping once (manual, worktree)**

Run: `python -m collectors.stock_market_collector`
Expected: `시장 매핑 수집 완료: KOSPI N종목 · KOSDAQ M종목` — N·M 모두 0이 아니어야 한다.

검증 쿼리:
```sql
SELECT market, count(*) FROM stock_market GROUP BY market;
SELECT count(*) FROM stock_market a JOIN stock_market b USING (stock_code)
  WHERE a.market <> b.market;   -- 0 이어야 함
```

- [ ] **Step 7: Commit**

```bash
git add collectors/eod_collection.py tests/collectors/test_eod_collection.py
git commit -F - <<'EOF'
feat(collectors): EOD 파이프라인에 시장 매핑 수집 등록

매핑 수집 실패는 EOD 를 멈추지 않는다 — 결측은 resolve_regime_index 가
"both"(보호 과잉) 로 흡수하는 반면, 분봉은 그날 못 받으면 자가치유되지 않기
때문이다(`minute_collector.py:26-38`). 기존 `_safe()` 단계격리를 그대로 쓴다.

🔑 캐시 무효화는 **수집 성공 시에만** 한다. 실패했는데 리셋하면 다음 조회가
빈/낡은 테이블을 다시 읽어 들고 있던 매핑을 잃는다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 6: 활성화 — 8전략 `regime_index: "auto"`

**이 Task 하나가 라이브 동작을 바꾸는 유일한 지점이다.** Task 1~5까지는 코드가 들어가도 모든 config가 non-auto라 동작이 변하지 않는다.

**Files:**
- Modify: `config/trading_config.json` (8전략 `regime_index`)
- Modify: `docs/PAPER_STRATEGIES.md` (regime 열 갱신)
- Test: `tests/test_active_strategies_resolver.py` 또는 신규 `tests/test_regime_config.py`

**Interfaces:**
- Consumes: `resolve_regime_index` (Task 3), 배선 (Task 4)

- [ ] **Step 1: Write the failing test**

`tests/test_regime_config.py`:

```python
"""활성 8전략의 regime_index 가 전부 "auto" 인지 고정.

이 단언이 깨지면 일부 전략만 시장 정합이 적용되는 상태로 조용히 되돌아간 것이다.
"""
import json
import os

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "config", "trading_config.json")
EXPECTED_STRATEGIES = {
    "elder_ema_pullback", "book_envelope_200d", "daytrading_3methods_breakout",
    "minervini_volume_dryup", "book_pullback_ma20", "book_pullback_ma5",
    "rs_leader", "deep_mr_dev20",
}


def _active_regime_settings():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    found = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("name") in EXPECTED_STRATEGIES and o.get("enabled"):
                found[o["name"]] = o.get("regime_index")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(cfg)
    return found


def test_all_active_strategies_use_auto_regime_index():
    settings = _active_regime_settings()
    assert set(settings) == EXPECTED_STRATEGIES, f"활성 전략 목록 불일치: {sorted(settings)}"
    non_auto = {k: v for k, v in settings.items() if v != "auto"}
    assert non_auto == {}, f'"auto" 가 아닌 전략: {non_auto}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_regime_config.py -v`
Expected: FAIL — `"auto" 가 아닌 전략: {'elder_ema_pullback': 'KOSPI', ...}` (8건 전부)

- [ ] **Step 3: Flip the config**

`config/trading_config.json` — 8전략의 `"regime_index"` 값을 `"auto"`로 변경:

| 전략 | 변경 전 | 변경 후 |
|---|---|---|
| elder_ema_pullback | `"KOSPI"` | `"auto"` |
| book_envelope_200d | `"KOSPI"` | `"auto"` |
| daytrading_3methods_breakout | `"KOSDAQ"` | `"auto"` |
| minervini_volume_dryup | `"KOSPI"` | `"auto"` |
| book_pullback_ma20 | `"KOSPI"` | `"auto"` |
| book_pullback_ma5 | `"KOSPI"` | `"auto"` |
| rs_leader | `"KOSPI"` | `"auto"` |
| deep_mr_dev20 | `"KOSPI"` | `"auto"` |

`"regime_gate"` 값은 **건드리지 않는다** (`exclude_bear` 3건 유지).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_regime_config.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -q`
Expected: 기존 통과 테스트가 새로 깨지지 않는다. 실패가 있으면 **원인을 규명하기 전까지 커밋하지 않는다.**

- [ ] **Step 6: Update the strategy hub doc**

`docs/PAPER_STRATEGIES.md`의 regime 열을 `auto`로 갱신하고, 각주를 추가:

```markdown
> `regime_index: "auto"` — 급락게이트가 **매수 대상 종목의 소속 시장** 지수로 판정한다
> (KOSPI 임계 -2.5% / KOSDAQ -3.0%). 매핑 결측 시 `both`(두 지수 모두 검사)로 폴백한다.
> 설계: [`superpowers/specs/2026-08-03-market-aware-crash-gate-design.md`](superpowers/specs/2026-08-03-market-aware-crash-gate-design.md)
> 롤백: 이 값을 `"KOSPI"`/`"KOSDAQ"` 로 되돌리면 코드 배포 없이 변경 전 동작이 복원된다.
```

- [ ] **Step 7: Commit**

```bash
git add config/trading_config.json docs/PAPER_STRATEGIES.md tests/test_regime_config.py
git commit -F - <<'EOF'
feat(regime): 활성 8전략 regime_index="auto" — 시장 정합 활성화

**이 커밋이 라이브 동작을 바꾸는 유일한 지점이다.** 앞선 5커밋은 코드가 들어가도
config 가 전부 non-auto 라 동작이 변하지 않았다.

해소되는 것(2026-08-03 EOD 발견):
  daytrading(KOSDAQ 게이트) → KOSPI 종목 매수 시 **보호 없음**
  나머지 7(KOSPI 게이트)    → KOSDAQ 종목 매수 시 **엉뚱한 지수로 차단**

`regime_gate` 는 건드리지 않았다(`exclude_bear` 3건 유지) — 국면게이트는 범위 밖.

롤백: 이 파일의 값을 원래대로 되돌리면 코드 배포 없이 복원된다.
`resolve_regime_index` 가 non-auto 를 매핑 조회 없이 그대로 통과시키기 때문이다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

## 배포 후 확인 (다음 거래일 EOD)

1. 로그에서 `매수 판단 스킵: 시장급락` 의 지수 표기가 **종목에 따라 KOSPI/KOSDAQ 로 갈리는지** 확인. 전부 한 지수면 매핑이 안 걸린 것이다.
2. `SELECT market, count(*) FROM stock_market GROUP BY market;` — 두 시장 모두 0이 아닌지.
3. 매핑 결측 종목이 몇 건이나 `both` 폴백을 탔는지 (로그 `[시장매핑]` WARNING 건수).
4. **사후 산출 가능해지는 것**: 2026-08-03 매수 3종목(`340810`·`475400`·`309930`)의 실제 소속 시장, 그리고 그날 차단 2,909건 중 과잉 차단 규모.

## 범위 밖 (별건)

| 항목 | 선행 조건 |
|---|---|
| PIT 일봉 국면게이트의 시장 정합 | KOSDAQ 일봉 국면 SSOT 존재 여부 확인 |
| ETF·우선주·리츠 등 비보통주 처리 | 현행 유니버스 정책 유지 |
| `stock_list.json`·`stock_sector` 오염 필드 정리 | 소비자 전수 확인 |
