# Phase A2d — EOD 수집 훅 + KIS_DATA_SOURCE 읽기경로 플래그 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 일봉·분봉·지수 수집기(A2a/b/c)를 봇 EOD 훅에 묶어 매 장마감 후 자동 수집·교차비교하고, `KIS_DATA_SOURCE` 플래그로 읽기 경로(레거시↔새 DB)를 전환한다.

**Architecture:** 수집은 **항상 새 DB**에 적재(A2a/b/c). 본 계획은 (1) `KIS_DATA_SOURCE`(legacy|new) 플래그 + 일봉 읽기 리더(`QuantDailyReader`) DB 해석, (2) `run_data_collection()` 오케스트레이터(daily→minute→index→reconcile), (3) `system_monitor._handle_postmarket_tasks`에 `asyncio.to_thread` 비차단 훅을 추가한다. equity 스냅샷 훅과 동일 패턴(예외 흡수, 하루1회).

**Tech Stack:** Python 3.9, asyncio, psycopg2, PostgreSQL, pytest.

## Global Constraints

- 수집 적재 대상은 항상 `kis_template`(A2a/b/c). 플래그는 **읽기 경로만** 제어.
- `KIS_DATA_SOURCE`: `legacy`(기본) | `new`. env override.
- grace(=legacy): 레거시 읽기 + 교차비교. 전환(=new): 새 DB 읽기.
- EOD 훅은 `_handle_postmarket_tasks`(15:35+, 하루1회) 내부, equity 스냅샷 다음 단계. 예외는 EOD 흐름 비차단(흡수).
- ~10분 수집 루프는 `asyncio.to_thread`로 모니터 태스크 비차단.
- spec: `docs/superpowers/specs/2026-06-22-data-collection-migration-design.md` (Phase A4/5, D4).

---

### Task 1: KIS_DATA_SOURCE 플래그 + 일봉 리더 DB 해석

**Files:**
- Modify: `config/constants.py` (상수 추가)
- Modify: `db/quant_daily_reader.py` (DB 해석 교체)
- Test: `tests/db/test_data_source_flag.py`

**Interfaces:**
- Produces:
  - `config.constants.KIS_DATA_SOURCE: str`
  - `config.constants.resolve_daily_source_db() -> str` — `new`면 `"kis_template"`, 아니면 `os.getenv("QUANT_DB", "robotrader_quant")`.
- Modifies: `QuantDailyReader` 풀 init의 `database`가 `resolve_daily_source_db()`를 쓰도록.

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_data_source_flag.py
import importlib


def test_resolve_legacy_default(monkeypatch):
    monkeypatch.delenv("KIS_DATA_SOURCE", raising=False)
    monkeypatch.delenv("QUANT_DB", raising=False)
    import config.constants as c
    importlib.reload(c)
    assert c.resolve_daily_source_db() == "robotrader_quant"


def test_resolve_new_points_to_kis_template(monkeypatch):
    monkeypatch.setenv("KIS_DATA_SOURCE", "new")
    import config.constants as c
    importlib.reload(c)
    assert c.resolve_daily_source_db() == "kis_template"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/db/test_data_source_flag.py -v`
Expected: FAIL with `AttributeError: module 'config.constants' has no attribute 'resolve_daily_source_db'`

- [ ] **Step 3: Write minimal implementation**

`config/constants.py` 끝에 추가:
```python
import os as _os

# 데이터 읽기 소스 전환 플래그 (kis_template 전용 DB 이관)
#   legacy(기본): robotrader_quant / robotrader 에서 읽기 + 교차비교(grace)
#   new: kis_template 에서 읽기 (전환 완료)
KIS_DATA_SOURCE = _os.getenv("KIS_DATA_SOURCE", "legacy")


def resolve_daily_source_db() -> str:
    """일봉 읽기 대상 DB명. KIS_DATA_SOURCE=new 면 kis_template, 아니면 레거시."""
    if _os.getenv("KIS_DATA_SOURCE", "legacy") == "new":
        return "kis_template"
    return _os.getenv("QUANT_DB", "robotrader_quant")
```

`db/quant_daily_reader.py` 풀 init `database` 라인 교체:
```python
# 변경 전: "database": os.getenv("QUANT_DB", "robotrader_quant"),
from config.constants import resolve_daily_source_db
...
                        "database": resolve_daily_source_db(),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/db/test_data_source_flag.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 회귀 확인 (기본=legacy 불변)**

Run: `PYTHONIOENCODING=utf-8 python -X utf8 -c "from config.constants import resolve_daily_source_db; print(resolve_daily_source_db())"`
Expected: `robotrader_quant` (플래그 미설정 시 기존 동작 불변)

- [ ] **Step 6: Commit**

```bash
git add config/constants.py db/quant_daily_reader.py tests/db/test_data_source_flag.py
git commit -m "feat(data-source): KIS_DATA_SOURCE 플래그 + 일봉 리더 DB 해석(legacy 기본)"
```

---

### Task 2: EOD 수집 오케스트레이터 `run_data_collection`

**Files:**
- Create: `collectors/eod_collection.py`
- Test: `tests/collectors/test_eod_collection.py`

**Interfaces:**
- Consumes: `collectors.daily_collector.collect_daily`/`reconcile_daily`, `collectors.minute_collector.collect_minute`/`reconcile_minute`, `collectors.index_collector.collect_index`, `config.constants.KIS_DATA_SOURCE`.
- Produces:
  - `run_data_collection(trade_date: str = None) -> dict` — daily→minute→index 수집 후, `KIS_DATA_SOURCE=='legacy'`면 daily/minute 교차비교까지. 각 단계 예외는 잡아 결과 dict에 기록(전체 비차단). 반환 `{daily, minute, index, reconcile}`.

- [ ] **Step 1: Write the failing test (구조: 단계 호출·예외격리)**

```python
# tests/collectors/test_eod_collection.py
import collectors.eod_collection as eod


def test_run_data_collection_calls_all_stages(monkeypatch):
    calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: calls.append("daily") or {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: calls.append("minute") or {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: calls.append("index") or {"KOSPI": 1})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "legacy")
    out = eod.run_data_collection("20260623")
    assert calls == ["daily", "minute", "index"]
    assert out["daily"] == {"rows": 1}
    assert out["reconcile"]["daily"]["verdict"] == "PASS"


def test_stage_exception_is_isolated(monkeypatch):
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")  # 전환 후 비교 생략
    out = eod.run_data_collection("20260623")
    assert "error" in out["daily"]
    assert out["minute"] == {"rows": 2}
    assert out["reconcile"] == {}  # new 모드 비교 생략
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_eod_collection.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/eod_collection.py
"""EOD 수집 오케스트레이터 — daily→minute→index 수집 + (grace) 교차비교.

각 단계는 예외 격리(한 단계 실패가 다른 단계·EOD 흐름 비차단).
수집은 항상 새 DB. 비교는 KIS_DATA_SOURCE=='legacy'(grace) 일 때만.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.daily_collector import collect_daily, reconcile_daily  # noqa: E402
from collectors.minute_collector import collect_minute, reconcile_minute  # noqa: E402
from collectors.index_collector import collect_index  # noqa: E402
from config.constants import KIS_DATA_SOURCE  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001 — 단계 격리
        logger.error(f"EOD 수집 단계 실패 {getattr(fn, '__name__', fn)}: {e}")
        return {"error": str(e)}


def run_data_collection(trade_date: str = None) -> dict:
    out = {
        "daily": _safe(collect_daily, trade_date),
        "minute": _safe(collect_minute, trade_date),
        "index": _safe(collect_index),
        "reconcile": {},
    }
    if KIS_DATA_SOURCE == "legacy" and trade_date:
        # reconcile_*는 'YYYY-MM-DD'(daily)·'YYYYMMDD'(minute) 형식차 주의 — 호출측이 맞춰 전달
        dash = trade_date if "-" in trade_date else f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        compact = trade_date.replace("-", "")
        out["reconcile"] = {
            "daily": _safe(reconcile_daily, dash),
            "minute": _safe(reconcile_minute, compact),
        }
    return out
```

> 형식 주의: daily는 `daily_prices.date`가 TEXT `YYYY-MM-DD`, minute은 `trade_date` `YYYYMMDD`. 오케스트레이터가 양형식을 만들어 각 reconcile에 전달.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_eod_collection.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add collectors/eod_collection.py tests/collectors/test_eod_collection.py
git commit -m "feat(collectors): EOD 수집 오케스트레이터(단계 격리 + grace 교차비교)"
```

---

### Task 3: system_monitor EOD 훅 배선 (`_run_data_collection`)

**Files:**
- Modify: `bot/system_monitor.py` (`_handle_postmarket_tasks`에 단계 추가 + `_run_data_collection` 메서드)
- Test: `tests/bot/test_system_monitor_data_collection.py`

**Interfaces:**
- Consumes: `collectors.eod_collection.run_data_collection`, `utils.korean_time.now_kst`.
- Produces: `SystemMonitor._run_data_collection(self, current_time)` — `asyncio.to_thread(run_data_collection, <YYYYMMDD>)` 비차단 실행 + 결과 로깅. 예외 흡수.

- [ ] **Step 1: Write the failing test**

```python
# tests/bot/test_system_monitor_data_collection.py
import asyncio
import types
import bot.system_monitor as sm


def test_run_data_collection_invokes_orchestrator(monkeypatch):
    captured = {}
    def fake_run(td):
        captured["td"] = td
        return {"daily": {"rows": 1}, "minute": {"rows": 2}, "index": {"KOSPI": 1}, "reconcile": {}}
    monkeypatch.setattr(sm, "run_data_collection", fake_run, raising=False)

    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)   # __init__ 우회
    mon.logger = types.SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None,
                                       warning=lambda *a, **k: None)

    class _T:
        def strftime(self, f): return "20260623"
    asyncio.run(mon._run_data_collection(_T()))
    assert captured["td"] == "20260623"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bot/test_system_monitor_data_collection.py -v`
Expected: FAIL (`AttributeError: _run_data_collection` 또는 import name)

- [ ] **Step 3: Write minimal implementation**

`bot/system_monitor.py` 상단 import에 추가:
```python
from collectors.eod_collection import run_data_collection
```

`_handle_postmarket_tasks`의 equity 스냅샷 블록 다음에 추가(하루1회 가드 내부):
```python
                # EOD 데이터 수집(일봉·분봉·지수 → kis_template) + grace 교차비교
                try:
                    await self._run_data_collection(current_time)
                except Exception as dc_err:
                    self.logger.error(f"EOD 데이터 수집 오류: {dc_err}")
```

새 메서드 추가:
```python
    async def _run_data_collection(self, current_time) -> None:
        """EOD 데이터 수집(비차단). ~수분 루프라 to_thread로 모니터 태스크 비차단."""
        import asyncio
        trade_date = current_time.strftime("%Y%m%d")
        result = await asyncio.to_thread(run_data_collection, trade_date)
        daily = result.get("daily", {})
        minute = result.get("minute", {})
        index = result.get("index", {})
        rec = result.get("reconcile", {})
        self.logger.info(
            f"EOD 데이터 수집 완료: 일봉 {daily} · 분봉 {minute} · 지수 {index}"
            + (f" · 교차비교 {rec}" if rec else " · (전환완료 비교생략)")
        )
        for ds, r in (rec or {}).items():
            if isinstance(r, dict) and r.get("verdict") not in ("PASS", "EMPTY", None):
                self.logger.warning(f"EOD 교차비교 {ds} 불일치: {r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bot/test_system_monitor_data_collection.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: import·구문 회귀 확인**

Run: `python -c "import bot.system_monitor; print('system_monitor import OK')"`
Expected: `system_monitor import OK`

- [ ] **Step 6: Commit**

```bash
git add bot/system_monitor.py tests/bot/test_system_monitor_data_collection.py
git commit -m "feat(eod): system_monitor EOD 데이터 수집 훅(_run_data_collection, to_thread)"
```

---

## Self-Review (작성자 체크)

- **Spec 커버리지(훅·플래그)**: D5 EOD 훅(to_thread 비차단·하루1회·예외흡수)·D4 KIS_DATA_SOURCE 읽기경로 전환·교차비교 grace 한정 — 충족.
- **Placeholder 스캔**: 실제 코드·명령·기대출력. TODO 없음.
- **타입 일관성**: `resolve_daily_source_db()->str`(Task1) → QuantDailyReader 사용. `run_data_collection(trade_date)->dict`(Task2) → Task3 `_run_data_collection`에서 to_thread 호출. reconcile 형식차(YYYY-MM-DD vs YYYYMMDD) 오케스트레이터가 변환.
- **미해결(계획 세부)**: 분봉 읽기 리더 repoint — 봇은 장중 분봉을 자체 라이브 수집기로 읽고 DB minute_candles는 주로 백테스트/외부 소비라, 분봉 읽기경로 전환은 소비처 확인 후 별도 처리(전환 핵심은 일봉 리더). Phase B(운영테이블)·C(폐기)는 별도 계획.
