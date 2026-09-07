# 섹터 뉴스 부스트 (스펙 B) — 봇(kis-trading-template) 측 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 09:00 후보 로드 때 NewsQuant 가 쓴 `sector_news_score` 와 스펙 A 의 `fn_sector_map_as_of` 를 읽어 전략별 스냅샷 순서를 **최대 3칸** 움직인다. 기본 `shadow`(기록만), env 한 줄로 `live`. 어떤 실패도 후보 조회·매수를 막지 않는다(fail-open).

**Architecture:** 순수 함수 `core/sector_news_rerank.rerank()`(DB·로거·설정을 모른다) + 리포지토리 `db/repositories/sector_news.SectorNewsRepository`(읽기 2 · 쓰기 1) + `CandidateSelector._apply_sector_news_rerank()`(모드 분기·fail-open·기록·로그 — **예외를 밖으로 내지 않는다**) 를 `_fetch_candidates_for_strategy` 의 `provider()` 직후, 안전필터(limit 절단) **앞** 에 1줄로 끼운다. 스냅샷 표는 손대지 않는다. 텔레그램 표기는 `CandidateStock.sector_note`(기본 `""`) 로 전달한다.

**Tech Stack:** Python 3.9 호환(`typing.List/Dict`, `X | None` 금지) · psycopg2 · PostgreSQL 16 `kis_template` @ localhost:5433 (봇 롤 `robotrader`) · pytest 8 (`asyncio_mode=auto`) · pandas(평가 스크립트만)

**Spec:** `docs/superpowers/specs/2026-09-06-sector-news-boost-design.md` (v1 · 사장님 승인 2026-09-06) — 이 계획은 §2.2 · §3.3 · §5 · §7.2 · §8 · §9 를 구현한다. NewsQuant 측(§2.1·§3.1·§3.2·§4)은 `D:\GIT\NewsQuant\docs\superpowers\plans\2026-09-07-sector-news-boost-newsquant.md` 가 따로 구현한다 — **두 계획은 독립이며 순서 무관**(표가 없으면 이쪽은 `table_missing` 을 기록하며 원래 순서를 유지한다).

---

## Global Constraints

스펙에서 그대로 옮긴다 — 매 태스크에서 다시 읽을 것:

- **매매 룰 0줄** · **라이브 3표(`daily_prices`·`minute_candles`·`virtual_trading_records`) 불변** · **KIS 호출 0**
- **fail-open**: `_apply_sector_news_rerank` 는 예외를 «절대» 밖으로 내지 않는다. 호출자의 fail-closed `except` 에 잡히면 「후보 조회 실패 → 금일 매수 중단」이 되어 결정 8 을 깨뜨린다
- **재정렬은 안전필터 «앞»** (`_filter_unsafe_stocks(pool, limit=…)` 가 앞에서 자르므로)
- **`SECTOR_NEWS_BOOST_MODE` 기본 `shadow`** · `off` 는 DB 접근 0 · `live` 전환·롤백은 env 한 줄
- **상수**: `SECTOR_NEWS_MAX_SHIFT=3` `SECTOR_NEWS_MIN_ABS=0.2` `SECTOR_NEWS_STALE_MINUTES=60` `SECTOR_NEWS_EXCLUDE_STRATEGIES=frozenset()`
- **`reason` 값**: `ok | no_score_rows | stale | fn_missing | table_missing | excluded_strategy | error:<ExceptionName>` — `ok` 가 아니면 `new_rank = orig_rank`, `sector_score = NULL` 로 **그래도 행을 쓴다**
- **스펙 A 표·함수는 읽기만** (`fn_sector_map_as_of`) · `sector_news_score` 읽기만 · 봇이 쓰는 표는 `sector_news_rerank_log` 하나
- **워크트리에서 작업** · **라이브 트리에서 테스트 금지** · 연구 트리(`scripts/`·`multiverse/`·`lib/`·`backtest/`) **import 금지**(평가 스크립트는 연구 트리에 두고 테스트만 `sys.path.insert` 로 격리)
- 로거 `utils.logger.setup_logger(__name__)` · 시간 `utils.korean_time.now_kst()` · 파싱 실패는 `None`(0 아님) · 무징후 절단 금지
- **전체 스위트 실패 집합 main 과 양방향 차분 0** (`db` 마커 제외)
- **머지는 EOD(16:00) 이후** — 봇은 다음 07:40 기동 때 새 코드를 탄다

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|---|---|---|
| `core/sector_news_rerank.py` | `RerankRow` · `rerank()` · `classify_sector_news_exception()` — 순수 | 신규 |
| `config/constants.py` | `SECTOR_NEWS_BOOST_MODES` · `resolve_sector_news_mode()` · 상수 5개 (+`SECTOR_NEWS_BOOST_MODE_INVALID`) | 수정 |
| `db/repositories/sector_news.py` | `SectorNewsRepository`: `ensure_table()` `get_scores()` `get_sector_map()` `save_rerank_log()` | 신규 |
| `db/migrations/20260907_sector_news_rerank_log.sql` | §3.3 DDL 기록(SSOT 는 `ensure_table`) | 신규 |
| `db/database_manager.py` | `self.sector_news_repo = SectorNewsRepository()` + `ensure_table()`(try) | 수정 |
| `core/candidate_selector.py` | `CandidateStock.sector_note: str = ""` · `_apply_sector_news_rerank()` · `_fetch_candidates_for_strategy` 1줄 + `sector_note` 전달 | 수정 |
| `bot/candidate_loader.py` | `format_candidate_lines()` 추출 + `sector_note` 표기 | 수정 |
| `scripts/eval_sector_news_shadow.py` | §8 평가(연구 트리 · 읽기 전용) — 순수 헬퍼 4개 + `main()` | 신규 |
| `tests/test_sector_news_rerank.py` · `tests/test_sector_news_constants.py` · `tests/test_candidate_sector_news_wiring.py` · `tests/test_candidate_loader_format.py` · `tests/test_eval_sector_news_shadow.py` · `tests/db/test_sector_news_repo_db.py` | §7.2 | 신규 |
| `../pyproject.toml` (repo 루트) | `db` 마커 등록 | 수정 |
| `docs/DB통합_쉬운설명.md` | §9 에 스펙 B 표 3개 | 수정 |

**경계**: `sector_news_rerank` 는 DB·로거·`config` 를 import 하지 않는다. `SectorNewsRepository` 는 정렬 로직을 모른다. `_apply_sector_news_rerank` 만 둘 다 안다.

---

## 실행 환경 — 명령 원형

🔴 **모든 명령 블록은 Bash 도구(Git Bash)로 실행한다.** PowerShell 은 히어독·`VAR=x cmd`·`&&` 가 파서 오류다.

**워크트리** (스펙 A 와 같은 방식):

```
cd D:/GIT/kis-trading-template
git worktree add -b feat/sector-news-boost D:/tmp/kis-wt-sector-news main
git worktree add --detach D:/tmp/kis-wt-sector-news-base main
```

**단위 테스트** (cwd = 워크트리의 `RoboTrader_template` · 인터프리터는 라이브 트리 venv 를 빌려 쓴다):

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_sector_news_rerank.py -v
```

한 테스트만: `... -m pytest tests/test_sector_news_rerank.py::test_이름 -v`.

**전체 스위트** (회귀 판정 · repo 루트 + VS 번들 Python 조합만 완주한다 · venv 엔 `pykrx` 가 없어 전체 스위트를 venv 로 돌리면 안 된다):

```
cd D:/tmp/kis-wt-sector-news
PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest -q --tb=line -m "not db" 2>&1 | tail -30
```

- 🔑 회귀 판정은 **실패 «집합»의 양방향 차분**(실패 «수» 아님). 기준선은 `D:/tmp/kis-wt-sector-news-base` 에서 같은 명령으로 따로 돌린다.
- DB 테스트(`@pytest.mark.db`)는 실 DB 가 없으면 **skip**. 워크트리엔 `.env` 가 없지만 `db/connection.py` 기본값이 `localhost:5433/kis_template/robotrader/1234` 라 그대로 붙는다.

**커밋** (메시지는 파일로):

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
<제목 줄>

<본문>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add <파일들> && git commit -F D:/tmp/snb_commit_msg.txt
```

**모든 커밋 메시지는 위 두 트레일러 줄로 끝나야 한다.** 파일 경로는 repo 루트 기준(`RoboTrader_template/...`)으로 `git add` 한다.

---

### Task 0: 워크트리 · 기준선 · `db` 마커

**Files:**
- Create: 워크트리 `D:/tmp/kis-wt-sector-news` (브랜치 `feat/sector-news-boost`) · 기준선 `D:/tmp/kis-wt-sector-news-base`
- Modify: `pyproject.toml` (repo 루트) `markers` 에 `db` 추가

- [ ] **Step 1: 워크트리 두 개**

```
cd D:/GIT/kis-trading-template && git status --short | grep -v '^??' ; git worktree add -b feat/sector-news-boost D:/tmp/kis-wt-sector-news main && git worktree add --detach D:/tmp/kis-wt-sector-news-base main && git worktree list | grep sector-news
```

Expected: tracked 변경 없음(첫 grep 출력 없음) · 워크트리 2개.

- [ ] **Step 2: 기준선 전체 스위트** (실패 집합 기록)

```
cd D:/tmp/kis-wt-sector-news-base && PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest -q --tb=no -m "not db" 2>&1 | grep -E "^(FAILED|ERROR)" | sort > D:/tmp/snb_baseline_failures.txt; wc -l D:/tmp/snb_baseline_failures.txt
```

Expected: 파일 생성(0줄이면 기준선 전부 통과).

- [ ] **Step 3: `db` 마커 등록** — repo 루트 `pyproject.toml` 의 `markers = [` 블록 안, `"slow: ...",` 줄 아래에 추가 (스펙 A 계획도 같은 줄을 넣는다 — 이미 있으면 건너뛴다):

```toml
    "db: 실 DB(kis_template @ localhost:5433) 필요 — 없으면 skip",
```

- [ ] **Step 4: 마커 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest --markers 2>&1 | grep "@pytest.mark.db"
```

Expected: `@pytest.mark.db: 실 DB(...)` 1줄.

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
chore(test): pytest db 마커 등록 (스펙 B 봇 측 준비)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add pyproject.toml && git commit -F D:/tmp/snb_commit_msg.txt
```

---

### Task 1: 순수 함수 `rerank`

**Files:**
- Create: `RoboTrader_template/core/sector_news_rerank.py`
- Test: `RoboTrader_template/tests/test_sector_news_rerank.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) RerankRow(stock_code: str, sector_key: Optional[str], sector_score: Optional[float], orig_rank: int, new_rank: int)` — `sector_score` 는 섹터의 `score_signed` **원값**(min_abs 미만이어도 기록, 미상이면 None)
  - `rerank(codes: List[str], code_to_sector: Dict[str, str], sector_scores: Dict[str, float], *, max_shift: int = 3, min_abs: float = 0.2) -> Tuple[List[str], List[RerankRow]]` — rows 는 `orig_rank` 오름차순
  - `classify_sector_news_exception(e: BaseException) -> str` — `UndefinedFunction → 'fn_missing'` · `UndefinedTable → 'table_missing'` · 그 외 `'error:<ClassName>'`
- 스펙 §5.2 정제(v1.1): `shift_i = round_half_away(max_shift × s_i)` (정수) · `key_i = orig_rank_i − shift_i − 0.5·sign(shift_i)` · key 오름차순 안정 정렬(동률 = 원래 순위). 0.5 편향 때문에 **혼자 움직일 때 정확히 shift 칸** 이동한다(편향이 없으면 동률에서 원래 순위에 밀려 K−1 칸). 여러 종목이 동시에 움직이면 최종 위치 차이는 K 를 넘을 수 있다(정의는 «자기 점수에 의한 이동 상한»).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_sector_news_rerank.py`

```python
"""core.sector_news_rerank.rerank — 순수 함수 계약 (스펙 B §5.2)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sector_news_rerank import rerank, RerankRow, classify_sector_news_exception  # noqa: E402

C8 = [f"S{i}" for i in range(1, 9)]   # S1..S8, 원래 순위 = 번호


def _ranks(rows):
    return {r.stock_code: r.new_rank for r in rows}


def test_no_scores_keeps_order():
    codes, rows = rerank(C8, {}, {})
    assert codes == C8
    assert [r.new_rank for r in rows] == list(range(1, 9)) and [r.orig_rank for r in rows] == list(range(1, 9))
    assert all(r.sector_key is None and r.sector_score is None for r in rows)


def test_plus_one_moves_exactly_max_shift_up():
    codes, rows = rerank(C8, {"S5": "261"}, {"261": 1.0}, max_shift=3)
    assert codes == ["S1", "S5", "S2", "S3", "S4", "S6", "S7", "S8"]
    assert _ranks(rows)["S5"] == 2 and rows[4] == RerankRow("S5", "261", 1.0, 5, 2)


def test_minus_one_moves_exactly_max_shift_down():
    codes, rows = rerank(C8, {"S2": "641"}, {"641": -1.0}, max_shift=3)
    assert codes == ["S1", "S3", "S4", "S5", "S2", "S6", "S7", "S8"]
    assert _ranks(rows)["S2"] == 5


def test_cannot_move_above_first_or_below_last():
    codes, _ = rerank(C8, {"S2": "a"}, {"a": 1.0})
    assert codes[0] == "S2"
    codes, _ = rerank(C8, {"S7": "a"}, {"a": -1.0})
    assert codes[-1] == "S7"


def test_fractional_score_rounds_half_away_from_zero():
    codes, _ = rerank(C8, {"S5": "a"}, {"a": 0.5}, max_shift=3)     # 1.5 → 2
    assert codes.index("S5") + 1 == 3
    codes, _ = rerank(C8, {"S3": "a"}, {"a": -0.5}, max_shift=3)    # -1.5 → -2
    assert codes.index("S3") + 1 == 5
    codes, _ = rerank(C8, {"S5": "a"}, {"a": 0.4}, max_shift=3)     # 1.2 → 1
    assert codes.index("S5") + 1 == 4


def test_below_min_abs_does_not_move_but_is_recorded():
    codes, rows = rerank(C8, {"S5": "a"}, {"a": 0.19}, min_abs=0.2)
    assert codes == C8 and _ranks(rows)["S5"] == 5
    assert rows[4].sector_key == "a" and rows[4].sector_score == 0.19


def test_unknown_sector_and_sector_without_score_unchanged():
    codes, rows = rerank(C8, {"S5": "zzz"}, {"261": 1.0})
    assert codes == C8 and rows[4].sector_key == "zzz" and rows[4].sector_score is None


def test_score_is_clipped_to_unit_range():
    codes, rows = rerank(C8, {"S8": "a"}, {"a": 7.5}, max_shift=3)
    assert codes.index("S8") + 1 == 5 and rows[7].sector_score == 7.5


def test_tie_broken_by_original_rank():
    # S4 shift 1 → key 2.5 · S6 shift 3 → key 2.5 → 동률 → S4 먼저
    codes, _ = rerank(C8, {"S4": "a", "S6": "b"}, {"a": 0.34, "b": 1.0}, max_shift=3)
    assert codes[:4] == ["S1", "S2", "S4", "S6"]


def test_two_way_movement_together():
    codes, _ = rerank(C8, {"S5": "up", "S2": "dn"}, {"up": 1.0, "dn": -1.0})
    assert codes == ["S1", "S5", "S3", "S4", "S2", "S6", "S7", "S8"]


def test_permutation_preserved_and_new_ranks_are_1_to_n():
    codes, rows = rerank(C8, {"S1": "a", "S8": "b", "S4": "c"}, {"a": -1.0, "b": 1.0, "c": 0.6})
    assert sorted(codes) == sorted(C8) and sorted(r.new_rank for r in rows) == list(range(1, 9))
    assert [r.orig_rank for r in rows] == list(range(1, 9))


def test_max_shift_zero_is_identity():
    codes, _ = rerank(C8, {"S5": "a"}, {"a": 1.0}, max_shift=0)
    assert codes == C8


def test_duplicate_codes_rejected():
    with pytest.raises(ValueError, match="중복"):
        rerank(["S1", "S1"], {}, {})


def test_negative_max_shift_rejected():
    with pytest.raises(ValueError):
        rerank(C8, {}, {}, max_shift=-1)


def test_empty_input():
    assert rerank([], {}, {}) == ([], [])


def test_classify_exception():
    class UndefinedFunction(Exception):
        pass

    class UndefinedTable(Exception):
        pass
    assert classify_sector_news_exception(UndefinedFunction()) == "fn_missing"
    assert classify_sector_news_exception(UndefinedTable()) == "table_missing"
    assert classify_sector_news_exception(RuntimeError("x")) == "error:RuntimeError"
```

- [ ] **Step 2: 실패 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_sector_news_rerank.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.sector_news_rerank'`.

- [ ] **Step 3: 구현** — `core/sector_news_rerank.py`

```python
"""섹터 뉴스 재정렬 — 순수 함수 (스펙 B §5.2). DB·로거·설정을 import 하지 않는다.

    shift_i = round_half_away(max_shift × s_i)      s_i = clip(score_signed, -1, 1); |s_i| < min_abs 또는 미상이면 0
    key_i   = orig_rank_i − shift_i − 0.5·sign(shift_i)
    key 오름차순 «안정» 정렬(동률 = 원래 순위)

0.5 편향: 혼자 움직이는 종목이 «정확히 shift 칸» 이동하게 한다(편향이 없으면 동률에서 원래 순위에 밀려 한 칸 덜 간다).
여러 종목이 동시에 움직이면 최종 위치 차이는 max_shift 를 넘을 수 있다 — 상한은 «자기 점수에 의한 이동»에 대한 것이다.
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RerankRow:
    stock_code: str
    sector_key: Optional[str]
    sector_score: Optional[float]   # 섹터 score_signed 원값 (min_abs 미만이어도 기록 · 미상이면 None)
    orig_rank: int                  # 1-based
    new_rank: int                   # 1-based


def _round_half_away(x: float) -> int:
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def rerank(codes: List[str], code_to_sector: Dict[str, str], sector_scores: Dict[str, float],
           *, max_shift: int = 3, min_abs: float = 0.2) -> Tuple[List[str], List[RerankRow]]:
    """(새 코드 순서, orig_rank 오름차순 RerankRow 목록)."""
    if len(set(codes)) != len(codes):
        raise ValueError("codes 에 중복이 있다 — screener_snapshots 계약 위반")
    if max_shift < 0:
        raise ValueError("max_shift 는 0 이상이어야 한다")

    entries = []  # (key, orig_rank, code, sector, raw_score)
    for idx, code in enumerate(codes):
        orig_rank = idx + 1
        sector = code_to_sector.get(code)
        raw = sector_scores.get(sector) if sector is not None else None
        s = 0.0
        if raw is not None:
            s = max(-1.0, min(1.0, float(raw)))
            if abs(s) < min_abs:
                s = 0.0
        shift = _round_half_away(max_shift * s)
        bias = 0.5 if shift > 0 else (-0.5 if shift < 0 else 0.0)
        entries.append((orig_rank - shift - bias, orig_rank, code, sector, None if raw is None else float(raw)))

    entries.sort(key=lambda e: (e[0], e[1]))
    new_codes = [e[2] for e in entries]
    rows = [RerankRow(stock_code=e[2], sector_key=e[3], sector_score=e[4], orig_rank=e[1], new_rank=pos + 1)
            for pos, e in enumerate(entries)]
    rows.sort(key=lambda r: r.orig_rank)
    return new_codes, rows


def classify_sector_news_exception(e: BaseException) -> str:
    """psycopg2 를 import 하지 않고 클래스 이름으로 분류한다(테스트에서 대역 예외를 쓸 수 있게)."""
    name = type(e).__name__
    if name == "UndefinedFunction":
        return "fn_missing"
    if name == "UndefinedTable":
        return "table_missing"
    return f"error:{name}"
```

- [ ] **Step 4: 통과 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_sector_news_rerank.py -v
```

Expected: `16 passed`.

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
feat(core): sector_news_rerank — 순위 이동 순수 함수(정수 shift·0.5 편향·안정 정렬) + 예외 분류 (스펙 B §5.2)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add RoboTrader_template/core/sector_news_rerank.py RoboTrader_template/tests/test_sector_news_rerank.py && git commit -F D:/tmp/snb_commit_msg.txt
```

---

### Task 2: 상수 · 모드 해석

**Files:**
- Modify: `RoboTrader_template/config/constants.py` (`SCREENER_SNAPSHOT_ENABLED` 블록(`:193-196`) 바로 아래)
- Test: `RoboTrader_template/tests/test_sector_news_constants.py`

**Interfaces:**
- Produces: `SECTOR_NEWS_BOOST_MODES = ("off", "shadow", "live")` · `resolve_sector_news_mode(raw: Optional[str]) -> Tuple[str, Optional[str]]` — `(mode, invalid_raw)`; None/빈 문자열 → `("shadow", None)`; 유효하지 않으면 `("off", raw)` · 모듈 상수 `SECTOR_NEWS_BOOST_MODE` `SECTOR_NEWS_BOOST_MODE_INVALID` `SECTOR_NEWS_MAX_SHIFT=3` `SECTOR_NEWS_MIN_ABS=0.2` `SECTOR_NEWS_STALE_MINUTES=60` `SECTOR_NEWS_EXCLUDE_STRATEGIES=frozenset()`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_sector_news_constants.py`

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config.constants as C  # noqa: E402


def test_resolve_mode_defaults_to_shadow():
    assert C.resolve_sector_news_mode(None) == ("shadow", None)
    assert C.resolve_sector_news_mode("") == ("shadow", None)
    assert C.resolve_sector_news_mode("  ") == ("shadow", None)


def test_resolve_mode_accepts_case_and_whitespace():
    assert C.resolve_sector_news_mode(" LIVE ") == ("live", None)
    assert C.resolve_sector_news_mode("Off") == ("off", None)


def test_resolve_mode_invalid_falls_to_off_and_reports_raw():
    assert C.resolve_sector_news_mode("on") == ("off", "on")


def test_module_constants_defaults():
    assert C.SECTOR_NEWS_BOOST_MODES == ("off", "shadow", "live")
    assert C.SECTOR_NEWS_BOOST_MODE in C.SECTOR_NEWS_BOOST_MODES
    assert C.SECTOR_NEWS_MAX_SHIFT == 3 and C.SECTOR_NEWS_MIN_ABS == 0.2 and C.SECTOR_NEWS_STALE_MINUTES == 60
    assert C.SECTOR_NEWS_EXCLUDE_STRATEGIES == frozenset()
```

- [ ] **Step 2: 실패 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_sector_news_constants.py -v
```

Expected: `AttributeError: module 'config.constants' has no attribute 'resolve_sector_news_mode'`.

- [ ] **Step 3: 구현** — `config/constants.py`, `del _os` (`:196`) 바로 뒤에 추가

```python
# =============================================================================
# 섹터 뉴스 부스트 (스펙 B, 2026-09-06) — 09:00 후보 로드 시 순위 이동. 기본 shadow.
#   spec: docs/superpowers/specs/2026-09-06-sector-news-boost-design.md §5.3
#   off    : 조회 안 함(DB 접근 0)
#   shadow : 계산·기록만, 원래 순서 반환  ← 기본값 (사장님 결정 2026-09-06)
#   live   : 새 순서 반환 (.env: SECTOR_NEWS_BOOST_MODE=live · 롤백은 off/삭제)
# =============================================================================
SECTOR_NEWS_BOOST_MODES = ("off", "shadow", "live")


def resolve_sector_news_mode(raw):
    """env 문자열 → (mode, invalid_raw). 비어 있으면 shadow, 모르는 값이면 off + 원문(호출자가 WARNING)."""
    if raw is None or not str(raw).strip():
        return "shadow", None
    v = str(raw).strip().lower()
    if v in SECTOR_NEWS_BOOST_MODES:
        return v, None
    return "off", raw


import os as _os
SECTOR_NEWS_BOOST_MODE, SECTOR_NEWS_BOOST_MODE_INVALID = resolve_sector_news_mode(_os.getenv("SECTOR_NEWS_BOOST_MODE"))
del _os
SECTOR_NEWS_MAX_SHIFT = 3               # 최대 이동 칸
SECTOR_NEWS_MIN_ABS = 0.2               # 이보다 약한 score_signed 는 0 취급
SECTOR_NEWS_STALE_MINUTES = 60          # computed_at 이 이보다 오래되면 없는 것으로(reason='stale')
SECTOR_NEWS_EXCLUDE_STRATEGIES = frozenset()   # 적용 제외 전략 (예: 평균회귀 deep_mr_dev20 — §8 결과 보고 결정)
```

- [ ] **Step 4: 통과 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_sector_news_constants.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
feat(config): SECTOR_NEWS_BOOST_MODE(off/shadow/live, 기본 shadow)·MAX_SHIFT·MIN_ABS·STALE·EXCLUDE (스펙 B §5.3)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add RoboTrader_template/config/constants.py RoboTrader_template/tests/test_sector_news_constants.py && git commit -F D:/tmp/snb_commit_msg.txt
```

---

### Task 3: `SectorNewsRepository` · 마이그레이션 SQL · `DatabaseManager` 배선

**Files:**
- Create: `RoboTrader_template/db/repositories/sector_news.py`
- Create: `RoboTrader_template/db/migrations/20260907_sector_news_rerank_log.sql`
- Modify: `RoboTrader_template/db/database_manager.py` (`:19-23` import · `:68-71` repo 초기화)
- Test: `RoboTrader_template/tests/db/test_sector_news_repo_db.py` (`@pytest.mark.db`)

**Interfaces:**
- Produces (`SectorNewsRepository(BaseRepository)`):
  - `ensure_table() -> None`
  - `get_scores(trade_date: date) -> Tuple[Dict[str, float], Optional[datetime]]` — `({sector_key: score_signed}, max(computed_at))`; 행 0 → `({}, None)`; 표 없음 → `psycopg2.errors.UndefinedTable` 그대로
  - `get_sector_map(as_of, codes: List[str]) -> Dict[str, str]` — `{code: ksic3}`; 함수 없음 → `UndefinedFunction` 그대로; `codes` 비면 DB 접근 없이 `{}`
  - `save_rerank_log(rows: List[Dict]) -> int` — dict 키 `trade_date strategy stock_code sector_key sector_score orig_rank new_rank applied mode reason score_asof`; UPSERT
- Produces: `DatabaseManager.sector_news_repo`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/db/test_sector_news_repo_db.py`

```python
"""SectorNewsRepository 실 DB 왕복. DB 없으면 skip. 쓰기는 센티널(1999-01-04, _test_sector_news)만."""
from datetime import date, datetime

import pytest

pytestmark = pytest.mark.db

TD = date(1999, 1, 4)
STRAT = "_test_sector_news"


@pytest.fixture(scope="module")
def repo():
    try:
        from db.connection import DatabaseConnection
        DatabaseConnection.initialize()
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
    except Exception as e:
        pytest.skip(f"실 DB 없음: {type(e).__name__}: {e}")
    from db.repositories.sector_news import SectorNewsRepository
    r = SectorNewsRepository()
    r.ensure_table()
    return r


@pytest.fixture
def clean(repo):
    yield
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sector_news_rerank_log WHERE trade_date = %s AND strategy = %s", (TD, STRAT))
        conn.commit()
        cur.close()


def _row(**kw):
    base = dict(trade_date=TD, strategy=STRAT, stock_code="000001", sector_key="261", sector_score=0.5,
                orig_rank=5, new_rank=2, applied=False, mode="shadow", reason="ok",
                score_asof=datetime(1999, 1, 4, 8, 50))
    base.update(kw)
    return base


def test_ensure_table_idempotent(repo):
    repo.ensure_table()
    repo.ensure_table()


def test_get_scores_empty_day(repo):
    try:
        scores, asof = repo.get_scores(date(1998, 1, 1))
    except Exception as e:
        assert type(e).__name__ == "UndefinedTable"     # NewsQuant 측 미배포 — 호출자가 table_missing 으로 분류
        return
    assert scores == {} and asof is None


def test_get_sector_map_roundtrip(repo):
    try:
        m = repo.get_sector_map("2026-09-04", ["005930", "000660"])
    except Exception as e:
        assert type(e).__name__ == "UndefinedFunction"  # 스펙 A 미배포
        return
    assert isinstance(m, dict) and all(len(k) == 6 and len(v) == 3 for k, v in m.items())
    assert repo.get_sector_map("2026-09-04", []) == {}


def test_save_rerank_log_upsert(repo, clean):
    assert repo.save_rerank_log([_row()]) == 1
    assert repo.save_rerank_log([_row(new_rank=3, reason="stale", sector_score=None)]) == 1
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT new_rank, reason, sector_score, applied FROM sector_news_rerank_log "
                    "WHERE trade_date = %s AND strategy = %s", (TD, STRAT))
        rows = cur.fetchall()
        cur.close()
    assert rows == [(3, "stale", None, False)]
    assert repo.save_rerank_log([]) == 0
```

- [ ] **Step 2: 실패 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/db/test_sector_news_repo_db.py -v
```

Expected: DB 있으면 `ModuleNotFoundError: db.repositories.sector_news`(픽스처 ERROR). 없으면 SKIP(그 경우 DB 있는 환경에서 완료).

- [ ] **Step 3: 구현** — `db/repositories/sector_news.py`

```python
"""섹터 뉴스 점수 읽기 + 재정렬 기록 쓰기 (스펙 B §3.3 · §5.4).

- 읽기: sector_news_score(NewsQuant 가 쓴다) · fn_sector_map_as_of(스펙 A)
- 쓰기: sector_news_rerank_log (봇이 쓰는 유일한 표)
- 예외는 «그대로 올린다». 분류·fail-open 은 호출자(CandidateSelector._apply_sector_news_rerank)의 몫.
"""
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from .base import BaseRepository

RERANK_LOG_DDL = """
CREATE TABLE IF NOT EXISTS sector_news_rerank_log (
    trade_date    date        NOT NULL,
    strategy      text        NOT NULL,
    stock_code    varchar(20) NOT NULL,
    sector_key    text,
    sector_score  double precision,
    orig_rank     integer     NOT NULL,
    new_rank      integer     NOT NULL,
    applied       boolean     NOT NULL,
    mode          text        NOT NULL,
    reason        text        NOT NULL,
    score_asof    timestamp,
    created_at    timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, strategy, stock_code)
)
"""

_UPSERT_LOG = """
INSERT INTO sector_news_rerank_log
    (trade_date, strategy, stock_code, sector_key, sector_score, orig_rank, new_rank,
     applied, mode, reason, score_asof, created_at)
VALUES
    (%(trade_date)s, %(strategy)s, %(stock_code)s, %(sector_key)s, %(sector_score)s, %(orig_rank)s, %(new_rank)s,
     %(applied)s, %(mode)s, %(reason)s, %(score_asof)s, now())
ON CONFLICT (trade_date, strategy, stock_code) DO UPDATE SET
    sector_key = EXCLUDED.sector_key, sector_score = EXCLUDED.sector_score,
    orig_rank = EXCLUDED.orig_rank, new_rank = EXCLUDED.new_rank,
    applied = EXCLUDED.applied, mode = EXCLUDED.mode, reason = EXCLUDED.reason,
    score_asof = EXCLUDED.score_asof, created_at = now()
"""


class SectorNewsRepository(BaseRepository):
    """섹터 뉴스 점수·명부 읽기, 재정렬 기록 쓰기."""

    def ensure_table(self) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(RERANK_LOG_DDL)
            conn.commit()
            cur.close()

    def get_scores(self, trade_date: date) -> Tuple[Dict[str, float], Optional[datetime]]:
        """({sector_key: score_signed}, max(computed_at)). 행 0 이면 ({}, None). 표 없음은 UndefinedTable 그대로."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT sector_key, score_signed, computed_at FROM sector_news_score "
                "WHERE trade_date = %s AND taxonomy = 'ksic3'",
                (trade_date,),
            )
            rows = cur.fetchall()
            cur.close()
        scores = {r[0]: float(r[1]) for r in rows if r[1] is not None}
        asof = max((r[2] for r in rows if r[2] is not None), default=None)
        return scores, asof

    def get_sector_map(self, as_of, codes: List[str]) -> Dict[str, str]:
        """{code: ksic3} — fn_sector_map_as_of(as_of). 함수 없음은 UndefinedFunction 그대로."""
        if not codes:
            return {}
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT stock_code, left(ksic_code, 3) FROM fn_sector_map_as_of(%s) "
                "WHERE stock_code = ANY(%s) AND ksic_code IS NOT NULL AND length(ksic_code) >= 3",
                (as_of, list(codes)),
            )
            rows = cur.fetchall()
            cur.close()
        return {r[0]: r[1] for r in rows}

    def save_rerank_log(self, rows: List[Dict]) -> int:
        """UPSERT. 저장 건수."""
        if not rows:
            return 0
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.executemany(_UPSERT_LOG, rows)
            conn.commit()
            cur.close()
        return len(rows)
```

`db/migrations/20260907_sector_news_rerank_log.sql`:

```sql
-- 섹터 뉴스 재정렬 기록 (스펙 B §3.3, 2026-09-06 승인)
--
-- 왜 필요한가: 09:00 후보 로드 때 섹터 뉴스 점수로 «움직였을» 순위를 매일 기록한다.
--   shadow 기간(≥20거래일)의 이 표가 live 전환 판단(§8)의 원천이다.
-- SSOT 는 db/repositories/sector_news.py::RERANK_LOG_DDL (ensure_table 이 기동 시 실행). 이 파일은 기록용.
-- reason: 'ok' | 'no_score_rows' | 'stale' | 'fn_missing' | 'table_missing' | 'excluded_strategy' | 'error:<종류>'
--         ok 가 아니면 new_rank = orig_rank · sector_score NULL 로 «그래도 행을 쓴다».

CREATE TABLE IF NOT EXISTS sector_news_rerank_log (
    trade_date    date        NOT NULL,
    strategy      text        NOT NULL,
    stock_code    varchar(20) NOT NULL,
    sector_key    text,                   -- NULL = 섹터 미상
    sector_score  double precision,       -- sector_news_score.score_signed 원값
    orig_rank     integer     NOT NULL,   -- screener_snapshots 순위 (1-based)
    new_rank      integer     NOT NULL,   -- 재정렬 후 순위 (shadow 에서도 «됐을» 순위)
    applied       boolean     NOT NULL,   -- live 에서 실제 적용됐으면 true
    mode          text        NOT NULL,   -- 'shadow' | 'live'
    reason        text        NOT NULL,
    score_asof    timestamp,              -- 읽은 sector_news_score.computed_at (max)
    created_at    timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, strategy, stock_code)
);
```

`db/database_manager.py` — import 블록(`:19-23`)에 한 줄:

```python
from db.repositories.sector_news import SectorNewsRepository
```

`self.quant_repo = QuantRepository()` (`:71`) 바로 뒤에:

```python
        # 스펙 B: 섹터 뉴스 재정렬 기록. 표 생성 실패는 기동을 막지 않는다(fail-open — 로드 시 다시 WARNING).
        self.sector_news_repo = SectorNewsRepository()
        try:
            self.sector_news_repo.ensure_table()
        except Exception as e:
            self.logger.warning(f"[섹터뉴스] sector_news_rerank_log 표 확인 실패(무시): {e}")
```

- [ ] **Step 4: 통과 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/db/test_sector_news_repo_db.py tests/db/test_verify_tables_robustness.py -v
```

Expected: 새 파일 `4 passed`(DB 있을 때) · 기존 `test_verify_tables_robustness.py` 는 이전과 같은 결과.

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
feat(db): SectorNewsRepository(점수·명부 읽기, rerank_log UPSERT) + 마이그레이션 SQL + DatabaseManager 배선 (스펙 B §3.3·§5.4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add RoboTrader_template/db/repositories/sector_news.py RoboTrader_template/db/migrations/20260907_sector_news_rerank_log.sql RoboTrader_template/db/database_manager.py RoboTrader_template/tests/db/test_sector_news_repo_db.py && git commit -F D:/tmp/snb_commit_msg.txt
```

---

### Task 4: `CandidateSelector` 배선 — `_apply_sector_news_rerank` · `sector_note`

**Files:**
- Modify: `RoboTrader_template/core/candidate_selector.py` — `:9` typing import · `:18-26` `CandidateStock` · `:1094-1120` `_fetch_candidates_for_strategy` 본문 · 클래스 끝(`:1137` 뒤) 메서드 추가
- Test: `RoboTrader_template/tests/test_candidate_sector_news_wiring.py`

**Interfaces:**
- Consumes: `rerank`·`RerankRow`·`classify_sector_news_exception`(Task 1) · `config.constants.SECTOR_NEWS_*`(Task 2) · `db_manager.sector_news_repo`(Task 3, duck-typed: `get_scores`/`get_sector_map`/`save_rerank_log`)
- Produces:
  - `CandidateStock.sector_note: str = ""` (마지막 필드, 기본값 — 기존 생성자 호출 전부 호환)
  - `CandidateSelector._apply_sector_news_rerank(strategy_name: str, codes: List[str], prev_day_str: str) -> Tuple[List[str], Dict[str, str]]` — `(반환 순서, {code: 표기})`. shadow 는 항상 원래 순서·빈 dict. **예외 0**.
- 상수는 호출 시점에 `config.constants` 모듈 속성으로 읽는다(테스트 monkeypatch 가능).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_candidate_sector_news_wiring.py`

```python
"""_fetch_candidates_for_strategy 의 섹터 뉴스 재정렬 배선 — off/shadow/live · 안전필터 앞 · fail-open 전 경로 (스펙 B §5.1·§5.5)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests._mock_modules  # noqa: F401,E402
import config.constants as C  # noqa: E402
import core.candidate_selector as cs  # noqa: E402
from core.candidate_selector import CandidateSelector, CandidateStock  # noqa: E402

NOW = datetime(2026, 9, 8, 9, 0)      # 화 09:00
CODES = ["A1", "A2", "A3", "A4", "A5", "A6"]


class UndefinedFunction(Exception):
    pass


class UndefinedTable(Exception):
    pass


class FakeRepo:
    def __init__(self, scores=None, asof=None, sector_map=None, exc_scores=None, exc_map=None, exc_save=None):
        self.scores, self.asof, self.sector_map = scores or {}, asof, sector_map or {}
        self.exc_scores, self.exc_map, self.exc_save = exc_scores, exc_map, exc_save
        self.saved, self.calls = [], []

    def get_scores(self, trade_date):
        self.calls.append("get_scores")
        if self.exc_scores:
            raise self.exc_scores
        return dict(self.scores), self.asof

    def get_sector_map(self, as_of, codes):
        self.calls.append("get_sector_map")
        if self.exc_map:
            raise self.exc_map
        return {c: s for c, s in self.sector_map.items() if c in codes}

    def save_rerank_log(self, rows):
        self.calls.append("save")
        if self.exc_save:
            raise self.exc_save
        self.saved.extend(rows)
        return len(rows)


GOOD = dict(scores={"261": 1.0, "641": -1.0}, asof=NOW - timedelta(minutes=5), sector_map={"A5": "261", "A2": "641"})


@pytest.fixture
def selector(monkeypatch):
    sel = CandidateSelector(config=MagicMock(), broker=MagicMock(), db_manager=MagicMock())
    monkeypatch.setattr(cs, "now_kst", lambda: NOW)
    monkeypatch.setattr(cs, "get_previous_trading_day", lambda dt=None, market="KRX": datetime(2026, 9, 7))
    monkeypatch.setattr("core.screener_snapshot_provider.make_screener_snapshot_provider",
                        lambda strategy_name, params_hash=None: (lambda s, d: list(CODES)))
    monkeypatch.setattr(sel, "_filter_unsafe_stocks", lambda pool, limit=None: pool[:limit] if limit else pool)
    for name, val in (("SECTOR_NEWS_MAX_SHIFT", 3), ("SECTOR_NEWS_MIN_ABS", 0.2),
                      ("SECTOR_NEWS_STALE_MINUTES", 60), ("SECTOR_NEWS_EXCLUDE_STRATEGIES", frozenset())):
        monkeypatch.setattr(C, name, val)
    return sel


def _run(sel, repo, mode, monkeypatch, strategy="s1", limit=20):
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", mode)
    sel.db_manager.sector_news_repo = repo
    return sel._fetch_candidates_for_strategy(strategy, limit)


def _codes(cands):
    return [c.code for c in cands]


def test_candidate_stock_has_default_sector_note():
    assert CandidateStock(code="x", name="x", market="KRX", score=1.0, reason="r").sector_note == ""


def test_off_touches_nothing(selector, monkeypatch):
    repo = FakeRepo(**GOOD)
    assert _codes(_run(selector, repo, "off", monkeypatch)) == CODES
    assert repo.calls == []


def test_shadow_keeps_order_but_records_would_be_ranks(selector, monkeypatch):
    repo = FakeRepo(**GOOD)
    cands = _run(selector, repo, "shadow", monkeypatch)
    assert _codes(cands) == CODES and all(c.sector_note == "" for c in cands)
    assert repo.calls == ["get_scores", "get_sector_map", "save"]
    by = {r["stock_code"]: r for r in repo.saved}
    assert len(by) == 6
    assert all(r["mode"] == "shadow" and r["reason"] == "ok" and r["applied"] is False
               and r["strategy"] == "s1" and r["trade_date"] == NOW.date() for r in by.values())
    assert by["A5"] == dict(by["A5"], new_rank=2, orig_rank=5, sector_key="261", sector_score=1.0)
    assert by["A2"]["new_rank"] == 5 and by["A1"]["new_rank"] == 1 and by["A1"]["sector_key"] is None
    assert by["A1"]["score_asof"] == NOW - timedelta(minutes=5)


def test_live_applies_new_order_and_notes(selector, monkeypatch):
    repo = FakeRepo(**GOOD)
    cands = _run(selector, repo, "live", monkeypatch)
    assert _codes(cands) == ["A1", "A5", "A3", "A4", "A2", "A6"]
    assert all(r["applied"] is True and r["mode"] == "live" for r in repo.saved)
    notes = {c.code: c.sector_note for c in cands}
    assert notes["A5"] == " (↑3 261 +1.0)" and notes["A2"] == " (↓3 641 -1.0)" and notes["A1"] == ""


def test_live_rerank_happens_before_limit_cut(selector, monkeypatch):
    repo = FakeRepo(scores={"261": 1.0}, asof=NOW, sector_map={"A6": "261"})
    assert _codes(_run(selector, repo, "live", monkeypatch, limit=3)) == ["A1", "A2", "A6"]


@pytest.mark.parametrize("repo_kwargs,reason", [
    (dict(scores={}, asof=None), "no_score_rows"),
    (dict(scores={"261": 1.0}, asof=NOW - timedelta(minutes=61), sector_map={"A5": "261"}), "stale"),
    (dict(exc_scores=UndefinedTable("relation sector_news_score does not exist")), "table_missing"),
    (dict(scores={"261": 1.0}, asof=NOW, exc_map=UndefinedFunction("fn_sector_map_as_of")), "fn_missing"),
    (dict(scores={"261": 1.0}, asof=NOW, exc_map=RuntimeError("boom")), "error:RuntimeError"),
])
def test_fail_open_paths_keep_order_and_record_reason(selector, monkeypatch, repo_kwargs, reason):
    repo = FakeRepo(**repo_kwargs)
    assert _codes(_run(selector, repo, "live", monkeypatch)) == CODES
    assert len(repo.saved) == 6
    assert all(r["reason"] == reason and r["new_rank"] == r["orig_rank"] and r["applied"] is False
               and r["sector_score"] is None for r in repo.saved)


def test_stale_boundary_exactly_60_minutes_is_fresh(selector, monkeypatch):
    repo = FakeRepo(scores={"261": 1.0}, asof=NOW - timedelta(minutes=60), sector_map={"A5": "261"})
    assert _codes(_run(selector, repo, "live", monkeypatch)) == ["A1", "A5", "A2", "A3", "A4", "A6"]


def test_save_failure_does_not_change_order(selector, monkeypatch):
    repo = FakeRepo(exc_save=RuntimeError("db down"), **GOOD)
    assert _codes(_run(selector, repo, "live", monkeypatch)) == ["A1", "A5", "A3", "A4", "A2", "A6"]
    assert repo.calls[-1] == "save"


def test_excluded_strategy_records_and_keeps_order(selector, monkeypatch):
    monkeypatch.setattr(C, "SECTOR_NEWS_EXCLUDE_STRATEGIES", frozenset({"deep_mr_dev20"}))
    repo = FakeRepo(**GOOD)
    assert _codes(_run(selector, repo, "live", monkeypatch, strategy="deep_mr_dev20")) == CODES
    assert repo.calls == ["save"] and all(r["reason"] == "excluded_strategy" for r in repo.saved)


def test_missing_repo_attribute_is_fail_open(selector, monkeypatch):
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "live")
    selector.db_manager = object()    # sector_news_repo 없음
    assert _codes(selector._fetch_candidates_for_strategy("s1", 20)) == CODES


def test_exception_inside_rerank_never_escapes(selector, monkeypatch):
    repo = FakeRepo(**GOOD)

    def _boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr("core.sector_news_rerank.rerank", _boom)
    assert _codes(_run(selector, repo, "live", monkeypatch)) == CODES


def test_apply_method_direct_contract(selector, monkeypatch):
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "shadow")
    selector.db_manager.sector_news_repo = FakeRepo(**GOOD)
    codes, notes = selector._apply_sector_news_rerank("s1", list(CODES), "2026-09-07")
    assert codes == CODES and notes == {}
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "live")
    codes, notes = selector._apply_sector_news_rerank("s1", list(CODES), "2026-09-07")
    assert codes == ["A1", "A5", "A3", "A4", "A2", "A6"] and set(notes) == {"A5", "A2"}


def test_import_failure_inside_method_is_fail_open(selector, monkeypatch):
    # core.sector_news_rerank 를 「임포트 불가」 상태로 만든다(부분 배포·롤백 도중을 흉내).
    # import 문이 outer try 안에 있어야만 여기서 ImportError 가 fail-open 으로 잡힌다 —
    # 밖에 있으면 _fetch_candidates_for_strategy 의 fail-closed try 는 이미 끝난 뒤라
    # bot/candidate_loader.py 까지 그대로 샌다.
    monkeypatch.setitem(sys.modules, "core.sector_news_rerank", None)
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "live")
    repo = FakeRepo(**GOOD)
    selector.db_manager.sector_news_repo = repo
    cands = selector._fetch_candidates_for_strategy("s1", 20)
    assert _codes(cands) == CODES
    assert repo.calls == []


def test_missing_mode_constant_is_fail_open(selector, monkeypatch):
    # 상수가 삭제된 상태(예: 부분 롤백)를 흉내 — getattr 기본값 "off" 로 떨어져야 하고,
    # AttributeError 가 나면 안 된다(off 는 DB 접근 0 이 계약이므로 repo 는 건드리지 않는다).
    monkeypatch.delattr(C, "SECTOR_NEWS_BOOST_MODE")
    repo = FakeRepo(**GOOD)
    selector.db_manager.sector_news_repo = repo
    assert _codes(selector._fetch_candidates_for_strategy("s1", 20)) == CODES
    assert repo.calls == []


def test_aware_now_kst_is_normalized(selector, monkeypatch):
    # now_kst() 가 tz-aware 를 돌려줘도(운영 환경의 실제 모습) stale 판정용 뺄셈 전에
    # tzinfo 를 벗겨내는 경로가 정상 동작하는지 — GOOD 의 asof 는 naive 다.
    import pytz
    monkeypatch.setattr(cs, "now_kst", lambda: pytz.timezone("Asia/Seoul").localize(NOW))
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "live")
    repo = FakeRepo(**GOOD)
    selector.db_manager.sector_news_repo = repo
    assert _codes(selector._fetch_candidates_for_strategy("s1", 20)) == ["A1", "A5", "A3", "A4", "A2", "A6"]
```

- [ ] **Step 2: 실패 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_candidate_sector_news_wiring.py -v
```

Expected: `test_candidate_stock_has_default_sector_note` → `AttributeError: 'CandidateStock' object has no attribute 'sector_note'`; 나머지는 `off`/`shadow` 가 우연히 통과하거나 `live` 가 FAIL — 어느 쪽이든 최소 5개 FAIL.

- [ ] **Step 3: 구현** — `core/candidate_selector.py`

`:9` typing import 를 다음으로 바꾼다:

```python
from typing import List, Dict, Optional, Callable, Tuple
```

`CandidateStock` (`:18-26`) 마지막 필드 뒤에:

```python
    sector_note: str = ""   # 스펙 B live 재정렬 표기 (예: " (↑2 261 +0.8)") — 텔레그램 후보 알림용
```

`_fetch_candidates_for_strategy` 의 `if not codes: ... return []` 블록(`:1094-1101`) 바로 뒤, 기존 주석 `# code 리스트 → CandidateStock 변환` 앞에:

```python
        # 스펙 B: 섹터 뉴스 재정렬 — 안전필터(limit 절단) «앞». 아래 메서드는 예외를 내지 않는다(fail-open).
        codes, sector_notes = self._apply_sector_news_rerank(strategy_name, codes, prev_day_str)

```

`pool = [ CandidateStock(...) ]` (`:1106-1116`) 의 `prev_close=0.0,` 뒤에 한 줄:

```python
                sector_note=sector_notes.get(code, ""),
```

클래스 끝(`:1137` 의 `return candidates` 뒤)에 메서드 추가:

(2026-09-07 구현 중 정정: import·상수 읽기를 outer try 안으로 — ImportError/AttributeError 도 fail-open; 섹터 미상 종목의 표기 f-string 이 None 에서 터지던 것을 건너뜀. 호출 지점은 `_fetch_candidates_for_strategy` 의 두 try 블록 «바깥»이라 새는 예외는 candidate_loader 까지 간다.)

```python
    # =========================================================================
    # 섹터 뉴스 재정렬 (스펙 B, 2026-09-06)
    # =========================================================================

    def _apply_sector_news_rerank(
        self,
        strategy_name: str,
        codes: List[str],
        prev_day_str: str,
    ) -> Tuple[List[str], Dict[str, str]]:
        """스냅샷 코드 순서에 섹터 뉴스 점수를 얹어 최대 K칸 순위 이동 (스펙 B §5).

        🔑 **fail-open — 이 메서드는 예외를 «절대» 밖으로 내지 않는다.**
           호출자 `_fetch_candidates_for_strategy` 의 이 호출 지점은 «양쪽» try 블록
           바깥이다(첫 조회 실패용 fail-closed try 는 이미 끝났고, 안전필터용 try 는
           아직 시작 전) — 여기서 예외가 새면 그 fail-closed `except` 가 잡아주지
           «않는다». `bot/candidate_loader.py` 까지 그대로 올라가 3회 재시도 후
           «전 전략» 「금일 매수 불가」로 이어진다(결정 8: 재정렬은 장식이어야 한다는
           전제를 정면으로 깬다). 그래서 import 문·상수 읽기까지 포함해 메서드
           «전체»를 outer try 안에 둔다 — `ImportError`(부분 배포·롤백 도중)나
           `AttributeError`(상수 삭제) 도 예외가 아니라 fail-open 대상이다.
           어떤 실패든 원래 순서를 돌려주고 WARNING 한 줄 + 기록 행(reason≠ok)만 남긴다.

        모드(config.constants.SECTOR_NEWS_BOOST_MODE — 호출 시점에 읽는다):
          off    → DB 접근 0, 로그 0
          shadow → 계산·기록, «원래 순서» 반환 (기본값)
          live   → 새 순서 + 텔레그램 표기 반환

        Returns:
            (반환할 코드 순서, {code: 표기 문자열}) — shadow/실패 는 (원래 순서, {}).
        """
        try:
            from config import constants as C
            from core.sector_news_rerank import rerank, RerankRow, classify_sector_news_exception

            mode = getattr(C, "SECTOR_NEWS_BOOST_MODE", "off")
            if mode == "off" or not codes:
                return list(codes), {}

            repo = getattr(self.db_manager, "sector_news_repo", None)
            if repo is None:
                self.logger.warning(f"[섹터뉴스] {strategy_name}: db_manager.sector_news_repo 없음 → 원래 순서")
                return list(codes), {}

            now = now_kst()
            now_naive = now.replace(tzinfo=None)
            trade_date = now.date()
            reason = "ok"
            scores: Dict[str, float] = {}
            asof = None
            code_to_sector: Dict[str, str] = {}
            try:
                if strategy_name in C.SECTOR_NEWS_EXCLUDE_STRATEGIES:
                    reason = "excluded_strategy"
                else:
                    scores, asof = repo.get_scores(trade_date)
                    if not scores:
                        reason = "no_score_rows"
                    else:
                        asof_naive = asof.replace(tzinfo=None) if asof is not None else None
                        if asof_naive is None or (now_naive - asof_naive).total_seconds() > C.SECTOR_NEWS_STALE_MINUTES * 60:
                            reason = "stale"
                        else:
                            code_to_sector = repo.get_sector_map(prev_day_str, list(codes))
            except Exception as e:
                reason = classify_sector_news_exception(e)

            if reason == "ok":
                new_codes, rows = rerank(list(codes), code_to_sector, scores,
                                         max_shift=C.SECTOR_NEWS_MAX_SHIFT, min_abs=C.SECTOR_NEWS_MIN_ABS)
            else:
                new_codes = list(codes)
                rows = [RerankRow(stock_code=c, sector_key=None, sector_score=None, orig_rank=i + 1, new_rank=i + 1)
                        for i, c in enumerate(codes)]
            applied = (mode == "live" and reason == "ok")

            try:
                repo.save_rerank_log([
                    {"trade_date": trade_date, "strategy": strategy_name, "stock_code": r.stock_code,
                     "sector_key": r.sector_key, "sector_score": r.sector_score,
                     "orig_rank": r.orig_rank, "new_rank": r.new_rank, "applied": applied,
                     "mode": mode, "reason": reason, "score_asof": asof}
                    for r in rows
                ])
            except Exception as e:
                self.logger.warning(f"[섹터뉴스] {strategy_name}: 기록 저장 실패(무시): {e}")

            moved = [r for r in rows if r.new_rank != r.orig_rank]
            up = sum(1 for r in moved if r.new_rank < r.orig_rank)
            mapped = sum(1 for r in rows if r.sector_key)
            asof_txt = asof.strftime("%H:%M") if asof else "-"
            line = (f"[섹터뉴스] {strategy_name} mode={mode} reason={reason} "
                    f"이동 {len(moved)}종목(↑{up} ↓{len(moved) - up}) 점수 as-of {asof_txt} "
                    f"섹터매핑 {mapped}/{len(codes)}")
            if reason == "ok":
                self.logger.info(line)
            else:
                self.logger.warning(line)

            notes: Dict[str, str] = {}
            if applied:
                for r in moved:
                    if r.sector_score is None:
                        # 자기 자신은 섹터 미매핑인데 다른 종목의 이동 때문에 순위만 밀린 경우
                        # (예: 유일하게 매핑된 종목이 3칸 올라오며 사이 종목들을 뒤로 미는 경우).
                        # 표기할 섹터 점수가 없으므로 스킵 — 여기서 포맷하면 TypeError.
                        continue
                    arrow = "↑" if r.new_rank < r.orig_rank else "↓"
                    notes[r.stock_code] = f" ({arrow}{abs(r.orig_rank - r.new_rank)} {r.sector_key} {r.sector_score:+.1f})"
            return (new_codes if applied else list(codes)), notes

        except Exception as e:
            self.logger.warning(f"[섹터뉴스] {strategy_name}: 재정렬 실패(fail-open, 원래 순서): {type(e).__name__}: {e}")
            return list(codes), {}
```

- [ ] **Step 4: 통과 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_candidate_sector_news_wiring.py tests/test_candidate_filter_unsafe.py -v
```

Expected: 새 파일 `19 passed` · 기존 `test_candidate_filter_unsafe.py` 전과 동일(변경 전 결과를 먼저 적어 두고 비교).

- [ ] **Step 5: 기존 후보 경로 회귀 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_candidate_foreign_pool_gate.py tests/test_bot_trading_analyzer.py -q 2>&1 | tail -3
```

Expected: 변경 전과 같은 결과.

- [ ] **Step 6: 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
feat(core): 후보 조회에 섹터 뉴스 재정렬 배선 — _apply_sector_news_rerank(off/shadow/live·stale·fail-open·기록) + CandidateStock.sector_note (스펙 B §5.1·§5.5)

안전필터(limit 절단) 앞에서 1줄. 예외는 절대 밖으로 나가지 않는다 — 호출자의 fail-closed 와 구분.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add RoboTrader_template/core/candidate_selector.py RoboTrader_template/tests/test_candidate_sector_news_wiring.py && git commit -F D:/tmp/snb_commit_msg.txt
```

---

### Task 5: 텔레그램 후보 알림 표기

**Files:**
- Modify: `RoboTrader_template/bot/candidate_loader.py` (`:218-225` 알림 줄 조립 → 모듈 함수로 추출)
- Test: `RoboTrader_template/tests/test_candidate_loader_format.py`

**Interfaces:**
- Produces: `format_candidate_lines(pool_by_strategy: Dict[str, list]) -> List[str]` — 전략별 `"  [전략] 코드(이름){sector_note}, …"`; 후보 없는 전략은 줄 없음.
- Consumes: `CandidateStock.sector_note`(Task 4)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_candidate_loader_format.py`

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests._mock_modules  # noqa: F401,E402
from bot.candidate_loader import format_candidate_lines  # noqa: E402
from core.candidate_selector import CandidateStock  # noqa: E402


def _c(code, note=""):
    return CandidateStock(code=code, name=f"N{code}", market="KRX", score=50.0, reason="r", sector_note=note)


def test_lines_include_sector_note_only_when_present():
    pool = {"s1": [_c("A1"), _c("A5", " (↑3 261 +1.0)")], "s2": [], "s3": [_c("B1")]}
    assert format_candidate_lines(pool) == [
        "  [s1] A1(NA1), A5(NA5) (↑3 261 +1.0)",
        "  [s3] B1(NB1)",
    ]


def test_objects_without_sector_note_attribute_are_fine():
    class Legacy:
        code, name = "L1", "레거시"
    assert format_candidate_lines({"s": [Legacy()]}) == ["  [s] L1(레거시)"]
```

- [ ] **Step 2: 실패 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_candidate_loader_format.py -v
```

Expected: `ImportError: cannot import name 'format_candidate_lines'`.

- [ ] **Step 3: 구현** — `bot/candidate_loader.py`

`from typing import Dict, Optional, TYPE_CHECKING` (`:6`) → `from typing import Dict, List, Optional, TYPE_CHECKING`.

`_load_candidates_multi_strategy` 의 텔레그램 블록(`:218-225`)에서

```python
            lines = []
            for s_name, cands in pool_by_strategy.items():
                if cands:
                    lines.append(
                        f"  [{s_name}] "
                        + ", ".join(f"{c.code}({c.name})" for c in cands)
                    )
```

를 다음 한 줄로 바꾼다:

```python
            lines = format_candidate_lines(pool_by_strategy)
```

파일 끝(`should_use_volume_fallback` 앞)에 모듈 함수 추가:

```python
def format_candidate_lines(pool_by_strategy: Dict[str, list]) -> List[str]:
    """텔레그램 후보 알림 줄. 스펙 B live 재정렬로 움직인 종목은 CandidateStock.sector_note 가 뒤에 붙는다
    (예: '005930(삼성전자) (↑2 261 +0.8)'). shadow 에서는 note 가 비어 있어 종전과 같다."""
    lines: List[str] = []
    for s_name, cands in pool_by_strategy.items():
        if cands:
            lines.append(
                f"  [{s_name}] "
                + ", ".join(f"{c.code}({c.name}){getattr(c, 'sector_note', '')}" for c in cands)
            )
    return lines
```

- [ ] **Step 4: 통과 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_candidate_loader_format.py tests/bot -q 2>&1 | tail -3
```

Expected: 새 파일 `2 passed` · `tests/bot` 전과 동일.

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
feat(bot): 후보 알림 줄 조립을 format_candidate_lines 로 추출 + live 재정렬 표기(sector_note) (스펙 B §5.6)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add RoboTrader_template/bot/candidate_loader.py RoboTrader_template/tests/test_candidate_loader_format.py && git commit -F D:/tmp/snb_commit_msg.txt
```

---

### Task 6: Shadow 평가 스크립트 (§8)

**Files:**
- Create: `RoboTrader_template/scripts/eval_sector_news_shadow.py` (연구 트리 · 읽기 전용)
- Test: `RoboTrader_template/tests/test_eval_sector_news_shadow.py` (순수 헬퍼만 · `sys.path.insert` + `importorskip` 격리)

**Interfaces:**
- Produces (순수, pandas):
  - `sector_validity(df) -> DataFrame[trade_date, n, spearman, q5_minus_q1]` — 입력 열 `trade_date score_signed ret_median`; `score_signed == 0` 행 제외; 5행 미만이면 `None`
  - `classify_transitions(log, slots=20) -> DataFrame` — `group ∈ {entered, displaced, top3_in, top3_out}` 인 행만
  - `forward_return(prices, stock_code, d0: str, n=5) -> Optional[float]` — `prices` 열 `stock_code date close`(`date` 는 `'YYYY-MM-DD'` 문자열); d0 행이 없거나 n 봉 부족이면 `None`(0 아님)
  - `reason_distribution(log) -> DataFrame[strategy, reason, days, avg_moved]`
- CLI: `PYTHONUTF8=1 python scripts/eval_sector_news_shadow.py --from 2026-09-29 --to 2026-10-27 [--slots 20] [--csv-dir D:/tmp/sector_eval]`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_eval_sector_news_shadow.py`

```python
"""scripts/eval_sector_news_shadow 순수 헬퍼. 연구 트리 격리: sys.path + importorskip."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
pd = pytest.importorskip("pandas")
ev = pytest.importorskip("scripts.eval_sector_news_shadow")


def test_sector_validity_quintiles_and_small_days():
    rows = []
    for i in range(10):                         # 점수와 수익률이 같은 방향 → 양의 상관 (0 점은 없음)
        rows.append({"trade_date": "2026-10-01", "score_signed": (i - 4.5) / 4.5, "ret_median": (i - 4.5) / 100})
    rows.append({"trade_date": "2026-10-01", "score_signed": 0.0, "ret_median": 9.9})   # 0 은 제외
    rows += [{"trade_date": "2026-10-02", "score_signed": 0.5, "ret_median": 0.01}] * 3   # 5행 미만
    out = ev.sector_validity(pd.DataFrame(rows)).set_index("trade_date")
    assert out.loc["2026-10-01", "n"] == 10 and out.loc["2026-10-01", "spearman"] > 0.9
    assert out.loc["2026-10-01", "q5_minus_q1"] > 0
    assert out.loc["2026-10-02", "n"] == 3 and pd.isna(out.loc["2026-10-02", "spearman"])   # float 열이라 None→NaN


def test_classify_transitions():
    log = pd.DataFrame([
        {"stock_code": "A", "orig_rank": 22, "new_rank": 19},   # entered
        {"stock_code": "B", "orig_rank": 20, "new_rank": 21},   # displaced
        {"stock_code": "C", "orig_rank": 5, "new_rank": 3},     # top3_in
        {"stock_code": "D", "orig_rank": 2, "new_rank": 4},     # top3_out
        {"stock_code": "E", "orig_rank": 7, "new_rank": 6},     # 해당 없음
    ])
    out = ev.classify_transitions(log, slots=20).set_index("stock_code")["group"].to_dict()
    assert out == {"A": "entered", "B": "displaced", "C": "top3_in", "D": "top3_out"}


def test_forward_return_none_when_insufficient():
    prices = pd.DataFrame([{"stock_code": "A", "date": f"2026-10-0{d}", "close": 100 + d} for d in range(1, 8)])
    assert abs(ev.forward_return(prices, "A", "2026-10-01", n=5) - (106 / 101 - 1)) < 1e-12
    assert ev.forward_return(prices, "A", "2026-10-03", n=5) is None       # 5봉 부족
    assert ev.forward_return(prices, "A", "2026-09-30", n=5) is None       # d0 행 없음
    assert ev.forward_return(prices, "Z", "2026-10-01", n=5) is None


def test_reason_distribution():
    log = pd.DataFrame([
        {"strategy": "s1", "trade_date": "2026-10-01", "reason": "ok", "orig_rank": 1, "new_rank": 2},
        {"strategy": "s1", "trade_date": "2026-10-01", "reason": "ok", "orig_rank": 2, "new_rank": 1},
        {"strategy": "s1", "trade_date": "2026-10-02", "reason": "stale", "orig_rank": 1, "new_rank": 1},
    ])
    out = ev.reason_distribution(log).set_index(["strategy", "reason"])
    assert out.loc[("s1", "ok"), "days"] == 1 and out.loc[("s1", "ok"), "avg_moved"] == 2
    assert out.loc[("s1", "stale"), "days"] == 1 and out.loc[("s1", "stale"), "avg_moved"] == 0
```

- [ ] **Step 2: 실패 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_eval_sector_news_shadow.py -v
```

Expected: 4 SKIP(`importorskip` 실패) — 구현 뒤 FAIL/PASS 로 바뀌어야 한다. `scripts/__init__.py` 가 없으면 만든다(빈 파일 · 기존 `scripts/kis_db/schema.py` 를 테스트가 import 하는 선례가 있으므로 있을 가능성이 높다 — `ls scripts/__init__.py` 로 확인).

- [ ] **Step 3: 구현** — `scripts/eval_sector_news_shadow.py`

```python
"""스펙 B §8 shadow 평가 — 읽기 전용. 연구 트리(scripts/). 운영 코드에서 import 금지.

세 표를 낸다:
  ① 섹터 점수 유효성: sector_news_score.score_signed vs 같은 날 sector_daily_stats.ret_median(ksic3)
     — 일자별 Spearman · 상위/하위 5분위 ret_median 중앙값 차
  ② 후보 수준: live 였다면 slots 안에 «들어왔을»(entered) vs «밀려났을»(displaced) 종목의 5거래일 수익률 차, 전략별
     (slots 안 순서 변화만 있는 날은 top3_in/top3_out 으로 같은 표)
  ③ 이동 규모·결측: 전략×reason 일수 · 일평균 이동 종목 수

사용:
  PYTHONUTF8=1 python scripts/eval_sector_news_shadow.py --from 2026-09-29 --to 2026-10-27 [--slots 20] [--csv-dir D:/tmp/sector_eval]

주의: 09:00 이전 값 = 그날 sector_news_score 행 자체(NewsQuant 가 09:05~15:30 동결하므로).
      daily_prices.date 는 text 'YYYY-MM-DD'. close 는 이미 분할조정 — adj_factor 를 곱하지 않는다.
      ① 표는 살아남은 sector_news_score 행을 쓴다 — NewsQuant 는 09:05~15:30 사이 쓰기를 동결하지만,
      09:00~09:05 사이의 실행이 봇이 읽은 행을 덮어썼을 수 있다. "봇이 실제로 본" 값은 그 시점에
      기록된 sector_news_rerank_log.score_asof / sector_score 만이 권위 있는 값이며, ②·③ 표는
      이 로그 값을 사용한다.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Q_SECTOR = """
SELECT s.trade_date, s.sector_key, s.score_signed, s.n_dir, d.ret_median
FROM sector_news_score s
JOIN sector_daily_stats d
  ON d.date = s.trade_date AND d.taxonomy = 'ksic3' AND d.sector_key = s.sector_key
WHERE s.taxonomy = 'ksic3' AND s.trade_date BETWEEN %s AND %s
"""
Q_LOG = """
SELECT trade_date, strategy, stock_code, sector_key, sector_score, orig_rank, new_rank, applied, mode, reason
FROM sector_news_rerank_log
WHERE trade_date BETWEEN %s AND %s
"""
Q_PRICES = """
SELECT stock_code, date, close FROM daily_prices
WHERE stock_code = ANY(%s) AND date BETWEEN %s AND %s
ORDER BY stock_code, date
"""


# ── 순수 헬퍼 (테스트 대상) ──────────────────────────────────────────────────
def sector_validity(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for td, g in df.groupby("trade_date"):
        g = g[g["score_signed"] != 0]
        if len(g) < 5:
            out.append({"trade_date": td, "n": len(g), "spearman": None, "q5_minus_q1": None})
            continue
        rho = g["score_signed"].corr(g["ret_median"], method="spearman")
        q = pd.qcut(g["score_signed"].rank(method="first"), 5, labels=False)
        top = g.loc[q == 4, "ret_median"].median()
        bot = g.loc[q == 0, "ret_median"].median()
        out.append({"trade_date": td, "n": len(g), "spearman": float(rho), "q5_minus_q1": float(top - bot)})
    return pd.DataFrame(out, columns=["trade_date", "n", "spearman", "q5_minus_q1"])


def classify_transitions(log: pd.DataFrame, slots: int = 20) -> pd.DataFrame:
    def _g(r):
        if r.new_rank <= slots < r.orig_rank:
            return "entered"
        if r.orig_rank <= slots < r.new_rank:
            return "displaced"
        if r.new_rank <= 3 < r.orig_rank:
            return "top3_in"
        if r.orig_rank <= 3 < r.new_rank:
            return "top3_out"
        return None
    df = log.copy()
    df["group"] = df.apply(_g, axis=1) if len(df) else pd.Series(dtype=object)
    return df[df["group"].notna()]


def forward_return(prices: pd.DataFrame, stock_code: str, d0: str, n: int = 5) -> Optional[float]:
    s = prices[(prices["stock_code"] == stock_code) & (prices["date"] >= d0)].sort_values("date").reset_index(drop=True)
    if len(s) < n + 1 or s.loc[0, "date"] != d0:
        return None
    c0, cn = float(s.loc[0, "close"]), float(s.loc[n, "close"])
    if c0 <= 0:
        return None
    return cn / c0 - 1


def reason_distribution(log: pd.DataFrame) -> pd.DataFrame:
    df = log.copy()
    df["moved"] = (df["new_rank"] != df["orig_rank"]).astype(int)
    days = df.groupby(["strategy", "trade_date"]).agg(reason=("reason", "first"), moved=("moved", "sum")).reset_index()
    return days.groupby(["strategy", "reason"]).agg(days=("trade_date", "nunique"), avg_moved=("moved", "mean")).reset_index()


# ── DB 읽기 (읽기 전용) ─────────────────────────────────────────────────────
def _fetch(conn, sql: str, params) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=cols)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="스펙 B shadow 평가 (읽기 전용)")
    ap.add_argument("--from", dest="d_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="d_to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--slots", type=int, default=20)
    ap.add_argument("--csv-dir", default=None)
    args = ap.parse_args(argv)

    from db.kis_db_connection import KisDbConnection   # 기본값 localhost:5433/kis_template/robotrader
    KisDbConnection.initialize()
    with KisDbConnection.get_connection() as conn:
        sec = _fetch(conn, Q_SECTOR, (args.d_from, args.d_to))
        log = _fetch(conn, Q_LOG, (args.d_from, args.d_to))
        trans = classify_transitions(log, slots=args.slots) if len(log) else log.iloc[0:0]
        codes = sorted(trans["stock_code"].unique().tolist()) if len(trans) else []
        p_to = (date.fromisoformat(args.d_to) + timedelta(days=20)).isoformat()
        prices = _fetch(conn, Q_PRICES, (codes, args.d_from, p_to)) if codes else pd.DataFrame(columns=["stock_code", "date", "close"])

    pd.set_option("display.width", 200)
    print("\n① 섹터 점수 유효성 (일자별)")
    t1 = sector_validity(sec) if len(sec) else pd.DataFrame(columns=["trade_date", "n", "spearman", "q5_minus_q1"])
    print(t1.to_string(index=False))
    if len(t1):
        valid = t1.dropna(subset=["spearman"])
        print(f"  요약: 일수 {len(t1)} · spearman>0 일수 {(valid['spearman'] > 0).sum()}/{len(valid)} · q5−q1 중앙값 {valid['q5_minus_q1'].median():.4f}")

    print("\n② 후보 수준 (전략×그룹, 5거래일 수익률)")
    if len(trans):
        trans = trans.copy()
        trans["fwd5"] = [forward_return(prices, r.stock_code, str(r.trade_date), 5) for r in trans.itertuples()]
        t2 = trans.groupby(["strategy", "group"]).agg(n=("stock_code", "size"), n_ret=("fwd5", "count"), mean_fwd5=("fwd5", "mean")).reset_index()
        print(t2.to_string(index=False))
    else:
        t2 = pd.DataFrame()
        print("  (이동 행 없음)")

    print("\n③ 이동 규모·결측 (전략×reason)")
    t3 = reason_distribution(log) if len(log) else pd.DataFrame(columns=["strategy", "reason", "days", "avg_moved"])
    print(t3.to_string(index=False))

    if args.csv_dir:
        out = Path(args.csv_dir)
        out.mkdir(parents=True, exist_ok=True)
        t1.to_csv(out / "1_sector_validity.csv", index=False, encoding="utf-8-sig")
        t2.to_csv(out / "2_candidate_transitions.csv", index=False, encoding="utf-8-sig")
        t3.to_csv(out / "3_reason_distribution.csv", index=False, encoding="utf-8-sig")
        print(f"\nCSV 저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과 확인**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/test_eval_sector_news_shadow.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: 실 DB 드라이런** (행이 없어도 세 표 헤더가 찍혀야 한다)

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" scripts/eval_sector_news_shadow.py --from 2026-09-01 --to 2026-09-30
```

Expected: ①②③ 세 블록 출력, 예외 없음(표가 없으면 `UndefinedTable` — NewsQuant 측·스펙 A 미배포 시 정상. 그 경우 출력 대신 오류 메시지를 기록하고 넘어간다).

- [ ] **Step 6: 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
feat(scripts): shadow 평가 스크립트 — 섹터 점수 유효성·후보 진입/이탈 5일 수익률·reason 분포 (스펙 B §8, 읽기 전용)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add RoboTrader_template/scripts/eval_sector_news_shadow.py RoboTrader_template/tests/test_eval_sector_news_shadow.py && git commit -F D:/tmp/snb_commit_msg.txt
```

---

### Task 7: 문서 · 전체 스위트 회귀 · 머지

**Files:**
- Modify: `RoboTrader_template/docs/DB통합_쉬운설명.md` (§9 끝, `---` 앞)
- Modify: `RoboTrader_template/docs/superpowers/specs/2026-09-06-sector-news-boost-design.md` (§9 표에 구현 커밋 기록 — 머지 후)

- [ ] **Step 1: 문서** — `docs/DB통합_쉬운설명.md` §9 「⬜ 사장님 판단이 필요한 것」 목록 뒤, `---` 앞에 추가:

```markdown
**🆕 스펙 B(섹터 뉴스 부스트, 2026-09) 표 3개** — 설계 `docs/superpowers/specs/2026-09-06-sector-news-boost-design.md`
- `sector_news_score` · `news_sector_hit` — **NewsQuant 가 쓴다**(postgres 로 붙어서 만든 뒤 OWNER 를 robotrader 로 넘긴다). 봇은 읽기만.
- `sector_news_rerank_log` — **봇이 쓴다**(09:00 후보 로드 때 전략별 «움직였을» 순위). shadow 20거래일 뒤 live 판단의 원천.
```

- [ ] **Step 2: 전체 스위트 회귀 (양방향 차분)**

```
cd D:/tmp/kis-wt-sector-news && PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest -q --tb=no -m "not db" 2>&1 | grep -E "^(FAILED|ERROR)" | sort > D:/tmp/snb_branch_failures.txt; echo "--- only in branch"; comm -13 D:/tmp/snb_baseline_failures.txt D:/tmp/snb_branch_failures.txt; echo "--- only in base"; comm -23 D:/tmp/snb_baseline_failures.txt D:/tmp/snb_branch_failures.txt
```

Expected: 두 목록 모두 **비어 있음**. 「only in branch」에 뭔가 있으면 그 테스트를 고치기 전엔 머지하지 않는다.

- [ ] **Step 3: DB 마커 테스트 별도 기록**

```
cd D:/tmp/kis-wt-sector-news/RoboTrader_template && PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest -m db -q 2>&1 | tail -3
```

Expected: `passed`/`skipped` 만(실패 0). 결과를 머지 커밋 본문에 적는다.

- [ ] **Step 4: 문서 커밋**

```
cat > D:/tmp/snb_commit_msg.txt <<'MSG'
docs: DB통합_쉬운설명 §9 에 스펙 B 표 3개(소유·쓰기 주체) 추가

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
MSG
cd D:/tmp/kis-wt-sector-news && git add RoboTrader_template/docs/DB통합_쉬운설명.md && git commit -F D:/tmp/snb_commit_msg.txt
```

- [ ] **Step 5: 머지 (EOD 16:00 이후 · 라이브 트리 clean 확인)**

```
cd D:/GIT/kis-trading-template && git status --short | grep -v '^??' ; git merge --no-ff feat/sector-news-boost -F D:/tmp/snb_merge_msg.txt && git log --oneline -3
```

머지 메시지 `D:/tmp/snb_merge_msg.txt` (먼저 작성):

```
merge(core): 섹터 뉴스 부스트(스펙 B) 봇 측 — 09:00 후보 재정렬(shadow 기본)·rerank_log·평가 스크립트 (feat/sector-news-boost · 사장님 승인 2026-09-06)

전체 스위트(-m "not db") 실패 집합 main 과 양방향 차분 0. db 마커: <passed/skipped 수>.
라이브 동작 변화: shadow 기본 → 순서 불변, sector_news_rerank_log 에 매일 기록만. live 는 .env SECTOR_NEWS_BOOST_MODE=live.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016jwWaZvM9aCiFTpLVurMpq
```

Expected: merge 커밋 · `git status --short` 에 tracked 변경 없음.

- [ ] **Step 6: 다음 거래일 첫 로드 관측**

다음 거래일 09:00 이후 로그에서 확인:

```
cd D:/GIT/kis-trading-template/RoboTrader_template && grep -h "\[섹터뉴스\]" logs/*.log | tail -20
```

Expected: 전략당 1줄 `[섹터뉴스] {전략} mode=shadow reason=… 이동 N종목 …`. `reason=fn_missing` 이면 스펙 A 미배포, `no_score_rows`/`table_missing` 이면 NewsQuant 측 미배포 — 둘 다 정상(스펙 결정 10). DB 확인:

```
cd D:/GIT/NewsQuant && PYTHONUTF8=1 python -c "
import psycopg2; c = psycopg2.connect(host='localhost', port=5433, dbname='kis_template', user='postgres', password='postgres'); cur = c.cursor()
cur.execute(\"SELECT trade_date, strategy, reason, count(*), sum((new_rank<>orig_rank)::int) FROM sector_news_rerank_log GROUP BY 1,2,3 ORDER BY 1 DESC, 2 LIMIT 20\")
for r in cur.fetchall(): print(r)"
```

- [ ] **Step 7: 워크트리 정리 · 스펙 §9 갱신**

```
cd D:/GIT/kis-trading-template && git worktree remove D:/tmp/kis-wt-sector-news && git worktree remove D:/tmp/kis-wt-sector-news-base && git branch -d feat/sector-news-boost
```

스펙 §9 표의 단계 3 행 「조건」 칸에 `구현 완료: <머지 sha> (<날짜>)` 를 적고 커밋한다(메시지 `docs(spec): 스펙 B §9 봇 측 구현 완료 기록`).

---

## Self-Review (작성 후 점검)

- **스펙 커버리지**: §2.2 파일 전부(T1 rerank · T3 repo/migration/manager · T2 constants · T4 selector · T5 loader · T6 scripts · T7 docs) · §3.3 T3 · §5.1 T4 · §5.2 T1(정수 shift + 0.5 편향 = 스펙 v1.1 정제) · §5.3 T2 · §5.4 T3 · §5.5 T4(모든 reason 값 · stale 경계 · 예외 0) · §5.6 T4(로그)+T5(텔레그램) · §7.2 T1·T3·T4 · §8 T6 · §9 T0·T7.
- **타입 일관성**: `rerank(...) -> (List[str], List[RerankRow])` 를 T4 가 언팩 · `RerankRow` 필드 5개 T1=T4 · `save_rerank_log(rows: List[Dict])` 의 dict 키 11개 T3(SQL `%(key)s`)=T4(dict 조립)=T3 테스트 `_row` · `get_scores -> (Dict, Optional[datetime])` T3=T4 · `_apply_sector_news_rerank -> (List[str], Dict[str,str])` T4 = `_fetch_candidates_for_strategy` 언팩 · `CandidateStock.sector_note` T4=T5.
- **플레이스홀더**: 없음.
- **NewsQuant 계획과의 계약**: 표 `sector_news_score(trade_date, taxonomy='ksic3', sector_key, score_signed, computed_at)` 열 이름이 양쪽 SQL 에서 동일(NQ T6 DDL · 봇 T3 `get_scores`).
- 구현 중 정정 3건(2026-09-07): T4 import/상수 try 안·None 가드 · T6 픽스처 off-by-one · T3 리뷰어의 db 마커 미등록 지적은 오인(루트 pyproject 에 등록됨).
