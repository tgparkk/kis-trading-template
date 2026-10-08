# 테마 순위 층(daytrading) 구현 계획 — 0단계 표시 · 1단계 과거 검정 준비

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 테마 소속표로 daytrading 후보의 「테마 돌출도」를 계산하고, 후보 원장 617거래일에서 밴드 재현 체결·도구 교정까지 마친 뒤 사전등록 초안을 만든다(판정 실행은 10-17 동결 뒤 Task 13). 함께 EOD 「다음 거래일 후보」 표에 테마 열을 붙인다.

**Architecture:** `RoboTrader_template/backtest/concept_axes/theme_rank/` 새 패키지(브랜치 `research/theme-rank` = `research/candidate-ledger` 위). 순수 함수 모듈(snapshot·membership·returns·signal·stats·bandfill·slots)을 합성 데이터로 TDD 하고, 러너(build_arena·build_signals·describe·ncut_evidence·calibrate·run)는 DB SELECT 전용으로 후보 원장 코드(`candidate_ledger/run.py`·`ledger8/exitsim8.py`)를 import 해 재사용한다. **결과(ret)와 실제 신호(S)를 합치는 코드는 `run.py` 하나뿐이고, `run.py` 는 동결 가드 없이는 돌지 않는다.**

**Tech Stack:** Python(kis-template venv) · pandas · numpy · psycopg2 · pytest. 새 의존성 없음(scipy 금지 — 이항 꼬리는 `math.lgamma` 로).

**범위 밖(스펙과 다른 점 포함 — 계획 승인 때 함께 확인):** 2단계 앞으로 측정(스펙 §6 · 1단계 PASS 때 별도 계획) · 3단계 실전 반영(§8) · EOD 돌출도 열(§7 「동결 뒤 추가」 → **판정 PASS 뒤로 미룸** — FAIL 이면 붙이지 않는다) · K2 인쇄(§5-3 「인쇄만」 → **생략** — 그룹 신호에 교정되지 않은 도구라 인쇄해도 해석할 수 없다).

**Spec:** `docs/superpowers/specs/2026-10-08-theme-rank-layer-daytrading-design.md`(main `6078e33`)

## Global Constraints

- 🔴 **봇 코드 0줄**: 수정·생성은 `RoboTrader_template/backtest/concept_axes/theme_rank/**` 와 이 계획·스펙 문서, Task 12 의 gitignore 된 EOD 스크립트·메모리 삽입뿐. `strategies/`·`core/`·`config/`·`ledger8/`·`candidate_ledger/` 는 import 만.
- 🔴 **DB SELECT 전용**: 러너 첫 줄은 `from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401`(PGOPTIONS read-only) · 접속은 `candidate_ledger.run._connect()`(readonly 세션).
- 🔴 **결과 엿보기 금지(동결 전)**: 실제 S(또는 §4-5 인쇄 항목)와 `ret`/`ret_net` 을 같은 계산에 넣지 않는다. 허용 = `build_arena`(결과만) · `build_signals`/`describe`/`ncut_evidence`(신호만) · `calibrate`(가짜 신호 × 결과). `run.py` 는 Task 13(동결 뒤)에서만 실행.
- 🔴 **라이브 트리 테스트 금지**: 모든 코드·테스트·러너는 워크트리 `D:/tmp/kis-wt-theme-rank` 에서. 라이브 트리 `D:/GIT/kis-trading-template` 의 브랜치를 바꾸지 않는다.
- 워크트리에는 `config/key.ini` 가 없어 import 때 「key.ini.example을 참고하여…」 경고가 찍힌다 — 원장 워크트리와 같고 무해하다(DB 접속은 `replayer.loader.dsn()`). key.ini 를 복사하지 않는다.
- 파이썬: `PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe` · 작업 디렉터리 `D:/tmp/kis-wt-theme-rank/RoboTrader_template` · 테스트 `$PY -m pytest backtest/concept_axes/theme_rank/tests -q` · 러너 `$PY -X utf8 -m backtest.concept_axes.theme_rank.<모듈>`.
- 커밋: 브랜치 `research/theme-rank` 커밋은 이 계획 승인 범위 · **push 는 사장님 별도 확인** · 커밋 메시지는 파일(`git commit -F`)로 — 각 Step 의 `# …` 주석 문장이 첫 줄, 빈 줄, 끝 줄 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`(`<메시지 파일>` = 그렇게 만든 임시 파일 경로).
- 주석·문서는 한국어. 기존 코드 관용(`from __future__ import annotations`, 🔒 표시, 모듈 docstring 에 규범 문서 지목)을 따른다.
- 🔒 동결 값(스펙 그대로): 튄 종목 `e ≥ +0.05` · `k ≥ 2` · `p0` 하한 `1/(2|U_D|)` · 테마 수 보정 `p_c = min(1, m·min p_T)` · 경기장 = 원장 `rank ≤ 20` ∧ 밴드 체결 · 밴드 상한 = 원장 `band_hi` · 비용 0.25%p(`freq_scenarios.COST_RATE` 0.0025) · IC 제외일 = 체결 후보 < 5 ∨ S 서로 다른 값 < 2 · HAC lag 11(판정) / 22(병기) · α 0.05 양측 · 교정 가짜 400개 · AR(1) φ 0.9 · 합격 거부율 [0.07, 0.13] · lag 상향 11→22→33 → 경험분포 · 플라시보 200회 · ε +0.5%p · 창 E 2024-03-13~2025-06-30 / C 2025-07-01~2026-09-23 · K=10 · 하루 5 · 스냅샷 2026-10-08(run_id 4).
- 원장 입력: `candidate_ledger/results/ledger.csv` md5 `980e58492a7ac2ed11d25526f4488dbc`(불일치면 중단).

## Review Focus

1. **`p0` 가 0 이거나 꼬리 확률이 언더플로하는 날**(전 종목 약세일·대형 테마 다수 튐) — S 는 유한한 실수여야 한다(로그 공간 계산 · `p0` 하한) → Task 4 `test_surprise_finite_when_no_stock_jumped_market_wide`·`test_log10_tail_no_underflow_for_extreme_k`.
2. **경기장이 퇴화한 날**(체결 후보 < 5 · S 가 전부 0) — IC 에서 빠지고 개수로 인쇄되며 NaN 이 평균을 오염시키지 않아야 한다 → Task 5 `test_daily_ic_skips_degenerate_days_and_counts_them`.
3. **같은 종목이 보유 중에 연속 후보로 다시 나오는 경우** — 기준선·테마 선택 모두 보유 종목을 건너뛰어야 한다 → Task 8 `test_held_stock_skipped_in_both_arms`.
4. **봉 결측**(D+1 봉 없음 = 미체결 · D−1 정지로 수익률 없음 = U_D 제외) → Task 3 `test_daily_returns_drops_gap_after_suspension` · Task 6 `test_arena_rows_no_bar_and_none_fill_have_blank_returns`.
5. **종목코드 앞자리 0**(원장 `5930` 형태 vs DB `005930`) — 조인이 조용히 비지 않아야 한다 → Task 1 `test_norm_code_pads_and_strips` · Task 6 `test_arena_rows_normalizes_stock_code`.

---

## File Structure

```
RoboTrader_template/backtest/concept_axes/theme_rank/
  __init__.py          패키지 docstring(규범 = 스펙 · PREREG)
  snapshot.py          표준 라이브러리만 — 스냅샷 조회 · 종목코드 정규화 · EOD 표시 열(EOD 스크립트가 파일 경로로 로드)
  membership.py        적격 테마(N_cut · 사건형 이름 제외)
  returns.py           KRX 일봉 → 날짜별 초과수익(U_D 제외 규칙)
  signal.py            돌출도 S · 인쇄 항목(A·C·B′·A″) · 이항 꼬리(로그 공간)
  stats.py             Spearman · 일별 IC · HAC t · 차수 보존 셔플 · AR(1) 잡음 · 가짜 S
  bandfill.py          밴드 재현 체결 · 밴드 터치 로트 청산 재시뮬 · 체결 행 필터
  slots.py             자리 K=10·하루 5 기준선 경로 · 빈 자리 고정 짝 비교
  build_arena.py       러너 — 경기장 원장(results/arena.csv) · 결과만
  build_signals.py     러너 — 신호(results/signals.csv) · 신호만 · run.py 가 상태 로더 재사용
  describe.py          러너 — 결과 없는 서술 진단(results/DESCRIBE.md)
  ncut_evidence.py     러너 — N_cut 근거표 · 제외 테마 목록(results/NCUT_EVIDENCE.md)
  calibrate.py         러너 — 가짜 테마 신호 400개 도구 교정(calibration/)
  run.py               러너 — 판정(동결 가드 · Task 13 에서만 실행)
  PREREG.md            사전등록(Task 11 초안 → 10-17 동결)
  results/  calibration/   러너 출력(커밋)
  tests/  conftest.py · test_*.py
```

---

### Task 1: 워크트리 · 패키지 · `snapshot.py`(EOD 표시 포함)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/__init__.py`
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/snapshot.py`
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/__init__.py`
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/conftest.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_snapshot.py`

**Interfaces:**
- Consumes: 없음
- Produces: `norm_code(code) -> str` · `Snapshot(snap_date: date, theme_name: Dict[int,str], members: Dict[int, FrozenSet[str]])` · `invert(members) -> Dict[str, FrozenSet[int]]` · `pick_snap_date(available: Sequence[date], target: date) -> Optional[date]` · `load_snap_dates(conn) -> List[date]` · `load_snapshot(conn, snap_date) -> Snapshot` · `shared_theme(code, themes_of, members, day_codes) -> Tuple[Optional[int], int]` · `theme_columns(codes, snap) -> Dict[str, Dict[str, object]]` · `FOOTER: str`

- [ ] **Step 1: 워크트리 만들기**

```bash
git -C D:/GIT/kis-trading-template worktree add D:/tmp/kis-wt-theme-rank -b research/theme-rank research/candidate-ledger
cd D:/tmp/kis-wt-theme-rank/RoboTrader_template
git log --oneline -1          # a9582da (research/candidate-ledger 끝)
md5sum backtest/concept_axes/candidate_ledger/results/ledger.csv   # 980e58492a7ac2ed11d25526f4488dbc
```

- [ ] **Step 2: 패키지 뼈대**

`theme_rank/__init__.py`:
```python
"""테마 순위 층(daytrading) — 규범 = `docs/superpowers/specs/2026-10-08-theme-rank-layer-daytrading-design.md` · `PREREG.md`.

🔴 봇 코드 0줄 · DB SELECT 전용 · 실제 신호와 결과의 결합은 동결 뒤 `run.py` 에서만.
"""
```

`theme_rank/tests/__init__.py`: 빈 파일.

`theme_rank/tests/conftest.py`:
```python
"""theme_rank 단위 테스트 — 합성 데이터 · DB 없음. 워크트리에서만 돌린다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 3: 실패하는 테스트 작성** — `tests/test_snapshot.py`

```python
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

from backtest.concept_axes.theme_rank import snapshot as SN

M = {1: frozenset({"000001", "000002", "000003"}), 2: frozenset({"000001", "000004"}), 3: frozenset({"000005"})}
SNAP = SN.Snapshot(date(2026, 10, 8), {1: "큰테마", 2: "작은테마", 3: "외톨이"}, M)


def test_norm_code_pads_and_strips():
    assert SN.norm_code(5930) == "005930"
    assert SN.norm_code(" 5930 ") == "005930"
    assert SN.norm_code("005930") == "005930"


def test_invert_maps_code_to_themes():
    inv = SN.invert(M)
    assert inv["000001"] == frozenset({1, 2})
    assert inv["000005"] == frozenset({3})


def test_pick_snap_date_latest_on_or_before():
    av = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 8)]
    assert SN.pick_snap_date(av, date(2026, 10, 7)) == date(2026, 10, 6)
    assert SN.pick_snap_date(av, date(2026, 10, 8)) == date(2026, 10, 8)
    assert SN.pick_snap_date(av, date(2026, 10, 4)) is None


def test_theme_columns_prefers_most_shared_then_smaller_theme():
    cols = SN.theme_columns(["000001", "000002", "000004"], SNAP)
    # 000001: 테마1 공유 {000002}=1 · 테마2 공유 {000004}=1 → 동점 → 작은 테마(2 · 크기 2)
    assert cols["000001"] == {"theme": "작은테마", "size": 2, "shared": 1}
    assert cols["000002"] == {"theme": "큰테마", "size": 3, "shared": 1}


def test_theme_columns_zero_shared_falls_back_to_smallest_theme_and_unthemed_is_dash():
    cols = SN.theme_columns(["5", "999999"], SNAP)          # "5" → "000005"
    assert cols["000005"] == {"theme": "외톨이", "size": 1, "shared": 0}
    assert cols["999999"] == {"theme": "-", "size": None, "shared": 0}


class _Cur:
    def __init__(self):
        self._sql = ""

    def execute(self, sql, args=None):
        self._sql = sql

    def fetchall(self):
        if "FROM theme_daily WHERE" in self._sql:
            return [(1, "큰테마")]
        if "FROM theme_member_daily" in self._sql:
            return [(1, "5930"), (1, "000660")]
        return [(date(2026, 10, 5),), (date(2026, 10, 8),)]


class _Conn:
    def __init__(self):
        self.c = _Cur()

    def cursor(self):
        return self.c


def test_load_snapshot_normalizes_codes_and_dates_list():
    s = SN.load_snapshot(_Conn(), date(2026, 10, 8))
    assert s.members[1] == frozenset({"005930", "000660"})
    assert s.theme_name == {1: "큰테마"}
    assert SN.load_snap_dates(_Conn()) == [date(2026, 10, 5), date(2026, 10, 8)]


def test_snapshot_module_loads_standalone_by_path():
    """EOD 스크립트는 다른 워크트리 sys.path 에서 이 파일 하나만 경로로 읽는다 — 패키지 import 없이 돌아야 한다."""
    path = Path(SN.__file__)
    spec = importlib.util.spec_from_file_location("theme_snapshot_standalone", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["theme_snapshot_standalone"] = mod
    spec.loader.exec_module(mod)
    assert mod.theme_columns(["000004"], mod.Snapshot(date(2026, 10, 8), {2: "작은테마"},
                                                      {2: frozenset({"000001", "000004"})}))["000004"]["size"] == 2
```

- [ ] **Step 4: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_snapshot.py -q`
Expected: FAIL — `ImportError: cannot import name 'snapshot'`

- [ ] **Step 5: 구현** — `theme_rank/snapshot.py`

```python
"""네이버 테마 스냅샷(NewsQuant · kis_template) 조회 + EOD 표시 열 — 표준 라이브러리만 쓴다.

EOD 스크립트가 이 파일 하나를 경로로 읽어 쓰므로(`importlib.util.spec_from_file_location`) 패키지 안 다른
모듈을 import 하지 않는다. DB 접속은 호출자가 넘긴 DB-API 연결로만(SELECT 전용).
표: `theme_daily(snap_date, theme_no, theme_name, …)` · `theme_member_daily(snap_date, theme_no, stock_code, …)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

FOOTER = "참고용 — 수동 개입 금지. 개입했다면 보고서에 기록."


def norm_code(code: object) -> str:
    """종목코드 6자리 문자열(앞자리 0 보존)."""
    return str(code).strip().zfill(6)


@dataclass(frozen=True)
class Snapshot:
    snap_date: date
    theme_name: Dict[int, str]
    members: Dict[int, FrozenSet[str]]


def invert(members: Mapping[int, FrozenSet[str]]) -> Dict[str, FrozenSet[int]]:
    """theme_no → 종목들 을 종목 → theme_no 들 로 뒤집는다."""
    out: Dict[str, Set[int]] = {}
    for t, codes in members.items():
        for c in codes:
            out.setdefault(c, set()).add(t)
    return {c: frozenset(ts) for c, ts in out.items()}


def pick_snap_date(available: Sequence[date], target: date) -> Optional[date]:
    """target 이하 가장 최근 snap_date(없으면 None)."""
    le = [d for d in available if d <= target]
    return max(le) if le else None


def load_snap_dates(conn) -> List[date]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT snap_date FROM theme_daily ORDER BY snap_date")
    return [r[0] for r in cur.fetchall()]


def load_snapshot(conn, snap_date: date) -> Snapshot:
    cur = conn.cursor()
    cur.execute("SELECT theme_no, theme_name FROM theme_daily WHERE snap_date = %s", (snap_date,))
    names = {int(t): str(n) for t, n in cur.fetchall()}
    if not names:
        raise LookupError(f"theme_daily 에 snap_date={snap_date} 행이 없다")
    cur.execute("SELECT theme_no, stock_code FROM theme_member_daily WHERE snap_date = %s", (snap_date,))
    mem: Dict[int, Set[str]] = {}
    for t, c in cur.fetchall():
        mem.setdefault(int(t), set()).add(norm_code(c))
    return Snapshot(snap_date, names, {t: frozenset(mem.get(t, ())) for t in names})


def shared_theme(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
                 day_codes: FrozenSet[str]) -> Tuple[Optional[int], int]:
    """같은 날 후보와 공유 수(자기 제외)가 가장 많은 테마와 그 수.

    동점 = 테마 크기 작은 것 → 번호 작은 것. 공유 0 이면 같은 규칙으로 가장 작은 소속 테마(공유 0).
    소속 없음 = (None, 0).
    """
    ts = sorted(themes_of.get(code, ()))
    if not ts:
        return None, 0

    def key(t: int) -> Tuple[int, int, int]:
        return (-len((members[t] - {code}) & day_codes), len(members[t]), t)

    best = min(ts, key=key)
    return best, len((members[best] - {code}) & day_codes)


def theme_columns(codes: Sequence[object], snap: Snapshot) -> Dict[str, Dict[str, object]]:
    """EOD 「다음 거래일 후보」 표 열(동결 전 · 스펙 §7) — 코드별 {"theme": 이름|"-", "size": int|None, "shared": int}.

    `codes` = 그날 조건 통과 후보 «전체»(표에 찍는 상위 10 만이 아니다 — 공유 수를 전체 기준으로 센다).
    """
    norm = [norm_code(c) for c in codes]
    day = frozenset(norm)
    th = invert(snap.members)
    out: Dict[str, Dict[str, object]] = {}
    for c in norm:
        t, k = shared_theme(c, th, snap.members, day)
        out[c] = {"theme": snap.theme_name[t] if t is not None else "-",
                  "size": len(snap.members[t]) if t is not None else None, "shared": k}
    return out
```

- [ ] **Step 6: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_snapshot.py -q`
Expected: 7 passed

- [ ] **Step 7: 커밋**

```bash
git add backtest/concept_axes/theme_rank/__init__.py backtest/concept_axes/theme_rank/snapshot.py backtest/concept_axes/theme_rank/tests/
git commit -F <메시지 파일>   # feat(theme_rank): 스냅샷 조회·종목코드 정규화·EOD 테마 열(표준 라이브러리만) · 봇 코드 0줄
```

---

### Task 2: `membership.py`(적격 테마) + `ncut_evidence.py`

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/membership.py`
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/ncut_evidence.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_membership.py`

**Interfaces:**
- Consumes: `snapshot.Snapshot`, `snapshot.load_snapshot`, `snapshot.invert`
- Produces: `EXCLUDED_NAME_PATTERNS: Tuple[str, ...]` · `excluded_themes(theme_name, patterns=EXCLUDED_NAME_PATTERNS) -> Set[int]` · `eligible_themes(theme_name, n_cut: Optional[int], patterns=EXCLUDED_NAME_PATTERNS) -> Set[int]` · `restrict(members, keep) -> Dict[int, FrozenSet[str]]` · `SNAP_DATE = date(2026, 10, 8)`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_membership.py`

```python
from __future__ import annotations

from backtest.concept_axes.theme_rank import membership as MB

NAMES = {10: "반도체 장비", 20: "밸류업(기업가치 제고)", 30: "SPAC(스팩)", 40: "코로나19(진단키트)",
         50: "여름", 546: "마이코플라스마 폐렴", 547: "새 테마", 600: "지주사"}


def test_excluded_themes_by_name_patterns():
    assert MB.excluded_themes(NAMES) == {20, 30, 40, 50, 600}


def test_eligible_applies_cut_and_exclusion():
    assert MB.eligible_themes(NAMES, n_cut=547) == {10, 546}


def test_full_variant_has_no_cut_and_no_exclusion():
    assert MB.eligible_themes(NAMES, n_cut=None, patterns=()) == set(NAMES)


def test_restrict_keeps_only_given_themes():
    mem = {10: frozenset({"000001"}), 20: frozenset({"000002"})}
    assert MB.restrict(mem, {10}) == {10: frozenset({"000001"})}
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_membership.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/membership.py`

```python
"""적격 테마(스펙 §4-2) — 검정 창 시작(2024-03-13) 전 테마(theme_no < N_cut) ∧ 사건·분류형 이름 제외.

N_cut 은 `ncut_evidence.py` 근거표로 PREREG 에서 정하고 `run.py`·러너 인자로 넘긴다(여기 기본값 없음).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Set, Tuple

SNAP_DATE = date(2026, 10, 8)        # 🔒 과거 검정 전 구간 고정 소속표(run_id 4 · 스펙 §4-3)

# 🔒 사건·분류형 테마 — 이름만 보고 정한다(결과 보기 전 · 스펙 §4-2 후보 목록 그대로).
EXCLUDED_NAME_PATTERNS: Tuple[str, ...] = (r"밸류업", r"지주사", r"SPAC|스팩", r"신규상장", r"여름", r"겨울", r"코로나")


def excluded_themes(theme_name: Mapping[int, str], patterns: Iterable[str] = EXCLUDED_NAME_PATTERNS) -> Set[int]:
    rx = [re.compile(p) for p in patterns]
    return {t for t, n in theme_name.items() if any(r.search(n) for r in rx)}


def eligible_themes(theme_name: Mapping[int, str], n_cut: Optional[int],
                    patterns: Iterable[str] = EXCLUDED_NAME_PATTERNS) -> Set[int]:
    """n_cut=None 이면 번호 경계 없음. 「전체 소속표」 변형은 `n_cut=None, patterns=()`."""
    ex = excluded_themes(theme_name, patterns)
    return {t for t in theme_name if (n_cut is None or t < n_cut) and t not in ex}


def restrict(members: Mapping[int, FrozenSet[str]], keep: Set[int]) -> Dict[int, FrozenSet[str]]:
    return {t: m for t, m in members.items() if t in keep}
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_membership.py -q`
Expected: 4 passed

- [ ] **Step 5: 근거 러너** — `theme_rank/ncut_evidence.py`

```python
"""N_cut 근거표 · 제외 테마 목록(스펙 §4-2) — 결과 없음 · DB SELECT 전용.

    python -X utf8 -m backtest.concept_axes.theme_rank.ncut_evidence

출력 `results/NCUT_EVIDENCE.md`: theme_no ≥ 500 테마의 이름·크기·설명 앞 120자·설명에 나온 연도들 + 사건형 제외 목록.
PREREG 작성자가 표를 읽고 「설명이 2024-03-13 이후 사건을 다루는 첫 번호」를 N_cut 으로 고른다(애매하면 작은 번호).
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import re                                                              # noqa: E402
from pathlib import Path                                               # noqa: E402

from backtest.concept_axes.candidate_ledger import run as CL           # noqa: E402
from backtest.concept_axes.theme_rank import membership as MB          # noqa: E402
from backtest.concept_axes.theme_rank import snapshot as SN            # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "NCUT_EVIDENCE.md"
FROM_NO = 500


def main() -> int:
    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE)
    cur = conn.cursor()
    cur.execute("SELECT theme_no, description FROM theme_daily WHERE snap_date = %s", (MB.SNAP_DATE,))
    desc = {int(t): (d or "") for t, d in cur.fetchall()}
    conn.close()
    lines = [f"# N_cut 근거표 — 스냅샷 {MB.SNAP_DATE} · theme_no ≥ {FROM_NO}", "",
             "| theme_no | 이름 | 크기 | 설명 속 연도 | 설명(앞 120자) |", "|---|---|---|---|---|"]
    for t in sorted(x for x in snap.theme_name if x >= FROM_NO):
        years = sorted(set(re.findall(r"20[0-2]\d", desc.get(t, ""))))
        text = desc.get(t, "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(f"| {t} | {snap.theme_name[t]} | {len(snap.members[t])} | {','.join(years)} | {text} |")
    ex = sorted(MB.excluded_themes(snap.theme_name))
    lines += ["", f"## 사건·분류형 제외({len(ex)}개 · 패턴 {MB.EXCLUDED_NAME_PATTERNS})", ""]
    lines += [f"- {t} {snap.theme_name[t]} ({len(snap.members[t])})" for t in ex]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"출력 → {OUT} · 테마 {len(snap.theme_name)} · 표 {sum(1 for x in snap.theme_name if x >= FROM_NO)}행 · 제외 {len(ex)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 러너 실행(결과 없는 서술)**

Run: `$PY -X utf8 -m backtest.concept_axes.theme_rank.ncut_evidence`
Expected: `출력 → …/results/NCUT_EVIDENCE.md · 테마 264 · …` · 파일에서 546 행이 「마이코플라스마 폐렴」인지 눈으로 확인.

- [ ] **Step 7: 커밋**

```bash
git add backtest/concept_axes/theme_rank/membership.py backtest/concept_axes/theme_rank/ncut_evidence.py backtest/concept_axes/theme_rank/tests/test_membership.py backtest/concept_axes/theme_rank/results/NCUT_EVIDENCE.md
git commit -F <메시지 파일>   # feat(theme_rank): 적격 테마(N_cut·사건형 제외) + N_cut 근거표 러너 · 결과 없음
```

---

### Task 3: `returns.py`(날짜별 초과수익)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/returns.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_returns.py`

**Interfaces:**
- Consumes: `snapshot.norm_code`; `backtest.concept_axes.replayer.flags.compute_bar_flags(px) -> Dict[str, np.ndarray]`(px 행 순서와 정렬된 불리언 배열 — `candidate_ledger/run.py:main` 이 같은 방식으로 씀)
- Produces: `bad_rows(px) -> np.ndarray` · `daily_returns(px, cal: Sequence[date], drop: Optional[np.ndarray]=None) -> pd.DataFrame[stock_code, date, r]` · `excess_by_day(rets) -> Dict[date, Dict[str, float]]` · `raw_by_day(rets) -> Dict[date, Dict[str, float]]`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_returns.py`

```python
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import returns as RT

CAL = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]


def _px(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "close"])


def test_daily_returns_needs_previous_calendar_day():
    px = _px([("1", "2026-01-02", 100.0), ("1", "2026-01-05", 110.0), ("1", "2026-01-06", 99.0),
              ("000002", "2026-01-02", 50.0), ("000002", "2026-01-05", 50.0)])
    r = RT.daily_returns(px, CAL)
    got = {(c, d): round(v, 10) for c, d, v in r.itertuples(index=False)}
    assert got == {("000001", date(2026, 1, 5)): 0.1, ("000001", date(2026, 1, 6)): -0.1,
                   ("000002", date(2026, 1, 5)): 0.0}


def test_daily_returns_drops_gap_after_suspension():
    """D−1 봉이 없으면(정지) D 수익률을 만들지 않는다 — 01-06 의 직전 봉이 01-02 라 제외."""
    px = _px([("000003", "2026-01-02", 100.0), ("000003", "2026-01-06", 130.0)])
    assert RT.daily_returns(px, CAL).empty


def test_daily_returns_drop_mask_removes_rows_before_pairing():
    px = _px([("000004", "2026-01-02", 100.0), ("000004", "2026-01-05", 100.0), ("000004", "2026-01-06", 120.0)])
    drop = np.array([False, True, False])            # 01-05 패딩봉 → 01-05·01-06 둘 다 수익률 없음
    assert RT.daily_returns(px, CAL, drop).empty


def test_excess_subtracts_equal_weight_market_mean():
    rets = pd.DataFrame({"stock_code": ["000001", "000002"], "date": [CAL[1], CAL[1]], "r": [0.10, 0.0]})
    ex = RT.excess_by_day(rets)
    assert ex[CAL[1]]["000001"] == pytest.approx(0.05)
    assert ex[CAL[1]]["000002"] == pytest.approx(-0.05)
    assert RT.raw_by_day(rets)[CAL[1]]["000001"] == pytest.approx(0.10)
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_returns.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/returns.py`

```python
"""KRX 일봉 → 날짜별 시장 대비 초과수익(스펙 §4-1 1~2).

가격은 `replayer.loader.load_prices` 그대로 쓴다(원장과 같은 규칙 — `adj_factor` 를 가격에 곱하지 않는다).
U_D 제외 = 패딩봉(거래 없는 평탄봉) ∨ 가짜 절벽. 잠김봉(상·하한가)은 «튄 종목»일 수 있으므로 빼지 않는다.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from backtest.concept_axes.theme_rank.snapshot import norm_code


def bad_rows(px: pd.DataFrame) -> np.ndarray:
    from backtest.concept_axes.replayer import flags as FL
    fl = FL.compute_bar_flags(px)
    return np.asarray(fl["flag_padding"], bool) | np.asarray(fl["flag_cliff"], bool)


def daily_returns(px: pd.DataFrame, cal: Sequence[date], drop: Optional[np.ndarray] = None) -> pd.DataFrame:
    """열 = stock_code, date(date), r. D 와 «달력상 D−1» 종가가 모두 있는 행만(정지 뒤 첫날은 없음)."""
    df = px[["stock_code", "date", "close"]].copy()
    if drop is not None:
        df = df.loc[~np.asarray(drop, bool)]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["stock_code"] = df["stock_code"].map(norm_code)
    df = df.sort_values(["stock_code", "date"], kind="mergesort").reset_index(drop=True)
    prev_of = {cal[i]: cal[i - 1] for i in range(1, len(cal))}
    g = df.groupby("stock_code", sort=False)
    prev_date = g["date"].shift(1)
    prev_close = g["close"].shift(1).astype(float)
    want = df["date"].map(prev_of)
    ok = (prev_date == want) & (prev_close > 0) & (df["close"].astype(float) > 0)
    out = df.loc[ok, ["stock_code", "date"]].copy()
    out["r"] = df.loc[ok, "close"].astype(float) / prev_close[ok] - 1.0
    return out.reset_index(drop=True)


def excess_by_day(rets: pd.DataFrame) -> Dict[date, Dict[str, float]]:
    out: Dict[date, Dict[str, float]] = {}
    for d, g in rets.groupby("date", sort=True):
        r = g["r"].astype(float)
        out[d] = dict(zip(g["stock_code"], (r - r.mean()).tolist()))
    return out


def raw_by_day(rets: pd.DataFrame) -> Dict[date, Dict[str, float]]:
    return {d: dict(zip(g["stock_code"], g["r"].astype(float).tolist())) for d, g in rets.groupby("date", sort=True)}
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_returns.py -q`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add backtest/concept_axes/theme_rank/returns.py backtest/concept_axes/theme_rank/tests/test_returns.py
git commit -F <메시지 파일>   # feat(theme_rank): KRX 일봉 초과수익(정지 뒤 첫날 제외·패딩/절벽 제외)
```

---

### Task 4: `signal.py`(돌출도 S · 인쇄 항목)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/signal.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_signal.py`

**Interfaces:**
- Consumes: 없음(순수)
- Produces: `JUMP_THR=0.05` · `K_MIN=2` · `LIMIT_UP_R=0.295` · `STREAK_LOGP=-2.0` · `log10_binom_tail(n, p, k) -> float` · `DayState(universe: FrozenSet[str], jumped: FrozenSet[str], p0: float)` · `day_state(excess: Mapping[str, float], thr=JUMP_THR) -> DayState` · `Surprise(s, log10_p, m, main_theme, k_main, n_main, single)` · `surprise(code, themes_of, members, st, k_min=K_MIN) -> Surprise` · `mean_excess_max(code, themes_of, members, excess) -> Optional[float]` · `same_theme_count(code, theme, members, day_codes) -> int` · `rank_in_theme(code, theme, members, excess) -> Optional[int]` · `theme_logp(theme, members, st, k_min=K_MIN) -> float` · `streak(logps: Sequence[float], thr=STREAK_LOGP) -> int`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_signal.py`

```python
from __future__ import annotations

import math

import pytest

from backtest.concept_axes.theme_rank import signal as SG


def test_log10_tail_matches_hand_calc():
    assert SG.log10_binom_tail(10, 0.03, 4) == pytest.approx(-3.83243151364107, rel=1e-9)
    assert SG.log10_binom_tail(99, 0.03, 6) == pytest.approx(-1.108682523122055, rel=1e-9)
    assert SG.log10_binom_tail(3, 0.5, 3) == pytest.approx(math.log10(0.125), rel=1e-12)


def test_log10_tail_edges():
    assert SG.log10_binom_tail(5, 0.2, 0) == 0.0
    assert SG.log10_binom_tail(5, 0.2, 6) == -math.inf


def test_log10_tail_no_underflow_for_extreme_k():
    v = SG.log10_binom_tail(148, 0.0002, 140)
    assert math.isfinite(v) and v < -400


def _st(universe, jumped):
    return SG.day_state({c: (0.06 if c in jumped else 0.0) for c in universe})


def test_day_state_p0_and_floor():
    st = _st({f"{i:06d}" for i in range(10)}, {"000000", "000001"})
    assert st.p0 == pytest.approx(0.2)
    flat = SG.day_state({f"{i:06d}": 0.0 for i in range(10)})
    assert flat.jumped == frozenset() and flat.p0 == pytest.approx(0.05)     # 하한 1/(2·10)


def test_surprise_example_from_spec_with_theme_count_correction():
    # 테마 1: 후보 c + 동료 5(2 튐) · 테마 2,3: 동료 1(안 튐) → m=3 · p0=0.2
    uni = {f"{i:06d}" for i in range(10)}
    st = _st(uni, {"000001", "000002"})
    members = {1: frozenset({"000009", "000001", "000002", "000003", "000004", "000005"}),
               2: frozenset({"000009", "000006"}), 3: frozenset({"000009", "000007"})}
    themes_of = {"000009": frozenset({1, 2, 3})}
    s = SG.surprise("000009", themes_of, members, st)
    assert s.m == 3 and s.main_theme == 1 and (s.k_main, s.n_main) == (2, 5) and not s.single
    assert s.s == pytest.approx(0.1033856098409906, rel=1e-9)        # −log10(3 × P(Bin(5,0.2) ≥ 2))


def test_surprise_k_below_two_counts_theme_but_scores_zero():
    uni = {f"{i:06d}" for i in range(10)}
    st = _st(uni, {"000001"})
    members = {1: frozenset({"000009", "000001", "000002"})}
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert (s.s, s.m, s.main_theme, s.single) == (0.0, 1, None, False)


def test_surprise_theme_with_only_self_is_not_counted_and_unthemed_is_single():
    uni = {f"{i:06d}" for i in range(10)}
    st = _st(uni, set())
    members = {1: frozenset({"000009"})}
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert (s.s, s.m, s.single) == (0.0, 0, True)
    assert SG.surprise("000008", {}, members, st).single


def test_surprise_peers_outside_universe_are_ignored():
    st = _st({"000009", "000001", "000002"}, {"000001", "000002"})
    members = {1: frozenset({"000009", "000001", "000002", "000077"})}   # 000077 은 그날 수익률 없음
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert s.n_main == 2 and s.k_main == 2


def test_surprise_finite_when_no_stock_jumped_market_wide():
    uni = {f"{i:06d}" for i in range(2000)}
    st = SG.day_state({c: -0.03 for c in uni} | {"000001": 0.2, "000002": 0.2, "000003": 0.2})
    members = {1: frozenset({"000009", "000001", "000002", "000003"})}
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert math.isfinite(s.s) and s.s > 5


def test_print_items():
    excess = {"000001": 0.08, "000002": 0.02, "000003": -0.01, "000009": 0.04}
    members = {1: frozenset({"000009", "000001", "000002"}), 2: frozenset({"000009", "000003"})}
    th = {"000009": frozenset({1, 2})}
    assert SG.mean_excess_max("000009", th, members, excess) == pytest.approx(0.05)
    assert SG.same_theme_count("000009", 1, members, frozenset({"000009", "000001", "000777"})) == 1
    assert SG.rank_in_theme("000009", 1, members, excess) == 2
    assert SG.streak([-3.0, -1.0, -2.5, -2.1]) == 2
    assert SG.streak([-1.0]) == 0
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_signal.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/signal.py`

```python
"""테마 돌출도 S 와 인쇄 항목(스펙 §4-1 · §4-5) — 순수 함수 · DB 없음.

S_c = −log10( min(1, m_c · min_T p_T) ),  p_T = P(Bin(n_T, p0_D) ≥ k_T) (k_T ≥ 2 일 때만, 아니면 1).
꼬리 확률은 로그 공간(`math.lgamma`)으로 계산해 언더플로하지 않는다. p0 하한 = 1/(2|U_D|).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import FrozenSet, Mapping, Optional, Sequence

JUMP_THR = 0.05          # 🔒 튄 종목 = 시장 대비 +5%p 이상
K_MIN = 2                # 🔒 동료 2개 이상 튀어야 센다
LIMIT_UP_R = 0.295       # 인쇄 B′ — 상한가로 보는 당일 등락률
STREAK_LOGP = -2.0       # 인쇄 A″ — 테마 p_T < 0.01 인 날을 「강세 일차」로 센다
_LN10 = math.log(10.0)


def log10_binom_tail(n: int, p: float, k: int) -> float:
    """log10 P(X ≥ k), X ~ Bin(n, p)."""
    if k <= 0:
        return 0.0
    if k > n or p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
             for i in range(k, n + 1)]
    mx = max(terms)
    return min(0.0, (mx + math.log(sum(math.exp(t - mx) for t in terms))) / _LN10)


@dataclass(frozen=True)
class DayState:
    universe: FrozenSet[str]
    jumped: FrozenSet[str]
    p0: float


def day_state(excess: Mapping[str, float], thr: float = JUMP_THR) -> DayState:
    n = len(excess)
    jumped = frozenset(c for c, e in excess.items() if e >= thr)
    p0 = max(len(jumped) / n, 0.5 / n) if n else math.nan
    return DayState(frozenset(excess), jumped, p0)


@dataclass(frozen=True)
class Surprise:
    s: float
    log10_p: float
    m: int
    main_theme: Optional[int]
    k_main: int
    n_main: int
    single: bool


def surprise(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
             st: DayState, k_min: int = K_MIN) -> Surprise:
    best_lp, best_t, best_k, best_n = 0.0, None, 0, 0
    m = 0
    for t in sorted(themes_of.get(code, ())):
        peers = (members[t] - {code}) & st.universe
        n = len(peers)
        if n < 1:
            continue
        m += 1
        k = len(peers & st.jumped)
        lp = log10_binom_tail(n, st.p0, k) if k >= k_min else 0.0
        if lp < best_lp:
            best_lp, best_t, best_k, best_n = lp, t, k, n
    if m == 0:
        return Surprise(0.0, 0.0, 0, None, 0, 0, True)
    lpc = min(0.0, math.log10(m) + best_lp)
    return Surprise(-lpc, lpc, m, best_t, best_k, best_n, False)


def mean_excess_max(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
                    excess: Mapping[str, float]) -> Optional[float]:
    """인쇄 A — 테마별 동료(자기 제외 · 그날 수익률 있는 종목) 동일가중 초과수익의 최댓값."""
    vals = []
    for t in themes_of.get(code, ()):
        xs = [excess[c] for c in members[t] if c != code and c in excess]
        if xs:
            vals.append(sum(xs) / len(xs))
    return max(vals) if vals else None


def same_theme_count(code: str, theme: Optional[int], members: Mapping[int, FrozenSet[str]],
                     day_codes: FrozenSet[str]) -> int:
    """인쇄 C — 그날 조건 통과 후보 전체 중 같은 주 테마 후보 수(자기 제외)."""
    return 0 if theme is None else len((members[theme] - {code}) & day_codes)


def rank_in_theme(code: str, theme: Optional[int], members: Mapping[int, FrozenSet[str]],
                  excess: Mapping[str, float]) -> Optional[int]:
    """인쇄 B′ — 주 테마 소속 전체(자기 포함) 안에서 당일 초과수익 순위(1 = 최고). 순위 = 1 + 자기보다 큰 수."""
    if theme is None or code not in excess:
        return None
    me = excess[code]
    return 1 + sum(1 for c in members[theme] if c != code and c in excess and excess[c] > me)


def theme_logp(theme: int, members: Mapping[int, FrozenSet[str]], st: DayState, k_min: int = K_MIN) -> float:
    """테마 자체의 그날 log10 p_T(소속 전체 · 자기 제외 없음) — A″ 계산용."""
    inside = members[theme] & st.universe
    k = len(inside & st.jumped)
    return log10_binom_tail(len(inside), st.p0, k) if k >= k_min else 0.0


def streak(logps: Sequence[float], thr: float = STREAK_LOGP) -> int:
    """인쇄 A″ — 끝에서부터 연속으로 logp < thr 인 날 수."""
    n = 0
    for v in reversed(list(logps)):
        if v < thr:
            n += 1
        else:
            break
    return n
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_signal.py -q`
Expected: 10 passed

- [ ] **Step 5: 커밋**

```bash
git add backtest/concept_axes/theme_rank/signal.py backtest/concept_axes/theme_rank/tests/test_signal.py
git commit -F <메시지 파일>   # feat(theme_rank): 테마 돌출도 S(로그 공간 이항 꼬리·p0 하한·테마 수 보정) + 인쇄 항목
```

---

### Task 5: `stats.py`(IC · HAC · 셔플 · 가짜 신호)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/stats.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_stats.py`

**Interfaces:**
- Consumes: 없음(순수)
- Produces: `spearman(x, y) -> float` · `daily_ic(df, sig, ret, day="scan_date", min_n=5, min_distinct=2) -> Tuple[pd.Series, int]` · `hac_t(ic, lag) -> Dict[str, float]`(키 `n_days, mean_ic, se_hac, t_hac, p_hac, lag`) · `degree_preserving_shuffle(members, rng, swaps_per_edge=10) -> Dict[int, FrozenSet[str]]` · `ar1_noise(theme_nos, n_days, phi, rng) -> Dict[int, np.ndarray]` · `upper_p(z) -> float` · `fake_s(code, themes_of, members, noise_today: Mapping[int, float]) -> float` · `episode_first(df, cal_idx: Mapping[date, int]) -> pd.DataFrame`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_stats.py`

```python
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import stats as ST


def test_spearman_pins_including_ties():
    assert ST.spearman([1, 2, 3, 4, 5], [5, 6, 7, 8, 7]) == pytest.approx(0.8207826816681234)
    assert ST.spearman([0, 0, 0, 1, 2], [1, 3, 2, 5, 4]) == pytest.approx(0.7826237921249264)
    assert math.isnan(ST.spearman([1, 1, 1], [1, 2, 3]))


def test_daily_ic_skips_degenerate_days_and_counts_them():
    rows = []
    for i in range(5):                                          # 정상일 — 완전 정순
        rows.append(("2026-01-02", float(i), float(i)))
    for i in range(4):                                          # 체결 4개 < 5 → 제외
        rows.append(("2026-01-05", float(i), float(i)))
    for i in range(6):                                          # S 전부 0 → 제외
        rows.append(("2026-01-06", 0.0, float(i)))
    df = pd.DataFrame(rows, columns=["scan_date", "s", "ret"])
    ic, skipped = ST.daily_ic(df, "s", "ret")
    assert list(ic.index) == ["2026-01-02"] and ic.iloc[0] == pytest.approx(1.0)
    assert skipped == 2


def test_hac_t_pins_match_newsquant_metrics():
    """NewsQuant `news_scraper/backtest/metrics.hac_t` 와 같은 식(Bartlett) — 같은 손계산 핀."""
    s = pd.Series(([0.1] * 10 + [-0.1] * 10) * 3) + 0.02
    assert ST.hac_t(s, 3)["t_hac"] == pytest.approx(0.02 / math.sqrt(0.0308333333 / 60), rel=1e-6)
    xs = [0.03, -0.01, 0.05, 0.02, 0.04]
    n, mean = len(xs), sum(xs) / len(xs)
    ssd = sum((x - mean) ** 2 for x in xs)
    assert ST.hac_t(pd.Series(xs), 0)["t_hac"] == pytest.approx(mean / (math.sqrt(ssd / n) / math.sqrt(n)))
    assert math.isnan(ST.hac_t(pd.Series([0.1] * 5), 1)["t_hac"])
    assert math.isnan(ST.hac_t(pd.Series([0.01, 0.02, 0.04]), 5)["p_hac"])


def test_degree_preserving_shuffle_keeps_sizes_and_degrees_and_changes_graph():
    rng = np.random.default_rng(1)
    members = {t: frozenset(f"{(t * 7 + i) % 40:06d}" for i in range(5 + t % 4)) for t in range(12)}
    out = ST.degree_preserving_shuffle(members, rng)
    assert {t: len(v) for t, v in out.items()} == {t: len(v) for t, v in members.items()}
    deg = lambda m: pd.Series([c for v in m.values() for c in v]).value_counts().sort_index().to_dict()  # noqa: E731
    assert deg(out) == deg(members)
    assert out != members


def test_ar1_noise_shape_and_persistence():
    z = ST.ar1_noise([1, 2], 2000, 0.9, np.random.default_rng(3))
    assert set(z) == {1, 2} and z[1].shape == (2000,)
    lag1 = np.corrcoef(z[1][1:], z[1][:-1])[0, 1]
    assert 0.85 < lag1 < 0.95 and 0.9 < z[1].std() < 1.1


def test_fake_s_mirrors_real_structure():
    members = {1: frozenset({"000009", "000001"}), 2: frozenset({"000009", "000002"}), 3: frozenset({"000009"})}
    th = {"000009": frozenset({1, 2, 3})}
    # 동료 있는 테마 2개(1·2) · 최소 p = upper_p(1.0)=0.158655… → S = −log10(2 × 0.158655…)
    assert ST.fake_s("000009", th, members, {1: 1.0, 2: -1.0, 3: 9.0}) == pytest.approx(
        -math.log10(2 * 0.15865525393145707))
    assert ST.fake_s("000123", th, members, {1: 3.0}) == 0.0


def test_episode_first_keeps_first_of_consecutive_days_per_stock():
    cal = {date(2026, 1, d): i for i, d in enumerate([2, 5, 6, 7])}
    df = pd.DataFrame({"scan_date": [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 7), date(2026, 1, 5)],
                       "stock_code": ["000001", "000001", "000001", "000002"]})
    out = ST.episode_first(df, cal)
    assert sorted(map(tuple, out[["scan_date", "stock_code"]].values.tolist())) == [
        (date(2026, 1, 2), "000001"), (date(2026, 1, 5), "000002"), (date(2026, 1, 7), "000001")]
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_stats.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/stats.py`

```python
"""검정 통계(스펙 §5-2 · §5-3 · §5-5) — 순수 함수 · scipy 없음.

`hac_t` 는 NewsQuant `news_scraper/backtest/metrics.hac_t`(2026-10-07 `4f833cb`)와 같은 식이다
(Bartlett 커널 · γ0 = 모집단 분산 · 정규근사 양측 p). 두 레포의 판정 통계를 맞추려고 그대로 옮겼다.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, FrozenSet, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    xs, ys = pd.Series(list(x), dtype=float), pd.Series(list(y), dtype=float)
    if xs.nunique() < 2 or ys.nunique() < 2:
        return float("nan")
    return float(xs.rank(method="average").corr(ys.rank(method="average")))


def daily_ic(df: pd.DataFrame, sig: str, ret: str, day: str = "scan_date", min_n: int = 5,
             min_distinct: int = 2) -> Tuple[pd.Series, int]:
    """날짜별 Spearman(sig, ret). 제외 = 행 < min_n ∨ sig 서로 다른 값 < min_distinct ∨ ret 상수. (IC, 제외 일수)."""
    vals: Dict[object, float] = {}
    skipped = 0
    for d, g in df.groupby(day, sort=True):
        g = g[[sig, ret]].dropna()
        if len(g) < min_n or g[sig].nunique() < min_distinct or g[ret].nunique() < 2:
            skipped += 1
            continue
        vals[d] = spearman(g[sig], g[ret])
    return pd.Series(vals, dtype=float), skipped


def hac_t(ic: pd.Series, lag: int) -> Dict[str, float]:
    nan = float("nan")
    x = pd.Series(ic, dtype=float).dropna().to_numpy(dtype=float)
    n = int(x.size)
    out = {"n_days": n, "mean_ic": nan, "se_hac": nan, "t_hac": nan, "p_hac": nan, "lag": int(lag)}
    if n == 0:
        return out
    mean = float(x.mean())
    out["mean_ic"] = mean
    if n < lag + 2:
        return out
    d = x - mean if np.ptp(x) > 0 else np.zeros_like(x)
    var = float(d @ d) / n
    for k in range(1, lag + 1):
        var += 2.0 * (1.0 - k / (lag + 1)) * float(d[k:] @ d[:-k]) / n
    if not var > 0:
        return out
    se = math.sqrt(var / n)
    t = mean / se
    out.update(se_hac=se, t_hac=t, p_hac=math.erfc(abs(t) / math.sqrt(2)))
    return out


def degree_preserving_shuffle(members: Mapping[int, FrozenSet[str]], rng: np.random.Generator,
                              swaps_per_edge: int = 10) -> Dict[int, FrozenSet[str]]:
    """테마 크기·종목별 소속 수를 보존하는 이분 그래프 간선 교환(플라시보 · 스펙 §5-5)."""
    edges: List[Tuple[int, str]] = [(t, c) for t in sorted(members) for c in sorted(members[t])]
    eset = set(edges)
    n = len(edges)
    for _ in range(swaps_per_edge * n):
        i, j = (int(v) for v in rng.integers(n, size=2))
        (t1, c1), (t2, c2) = edges[i], edges[j]
        if t1 == t2 or c1 == c2 or (t1, c2) in eset or (t2, c1) in eset:
            continue
        eset.difference_update({(t1, c1), (t2, c2)})
        eset.update({(t1, c2), (t2, c1)})
        edges[i], edges[j] = (t1, c2), (t2, c1)
    out: Dict[int, set] = {t: set() for t in members}
    for t, c in edges:
        out[t].add(c)
    return {t: frozenset(v) for t, v in out.items()}


def ar1_noise(theme_nos: Iterable[int], n_days: int, phi: float, rng: np.random.Generator) -> Dict[int, np.ndarray]:
    """테마별 정상 AR(1) 표준정규 잡음(분산 1) — 가짜 테마 신호(스펙 §5-3)."""
    out: Dict[int, np.ndarray] = {}
    s = math.sqrt(1.0 - phi * phi)
    for t in sorted(theme_nos):
        e = rng.standard_normal(n_days)
        z = np.empty(n_days)
        z[0] = e[0]
        for i in range(1, n_days):
            z[i] = phi * z[i - 1] + s * e[i]
        out[t] = z
    return out


def upper_p(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def fake_s(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
           noise_today: Mapping[int, float]) -> float:
    """실제 S 와 같은 구조(동료 있는 테마만 · 최소 p · 테마 수 보정)를 잡음 z 로 만든 가짜 S."""
    ts = [t for t in themes_of.get(code, ()) if len(members[t] - {code}) >= 1 and t in noise_today]
    if not ts:
        return 0.0
    p = min(upper_p(noise_today[t]) for t in ts)
    return -min(0.0, math.log10(len(ts)) + math.log10(max(p, 1e-300)))


def episode_first(df: pd.DataFrame, cal_idx: Mapping[date, int]) -> pd.DataFrame:
    """같은 종목의 «연속 거래일» 후보 묶음마다 첫 행만(스펙 §5-7 민감도)."""
    o = df.copy()
    o["_i"] = o["scan_date"].map(cal_idx)
    o = o.sort_values(["stock_code", "_i"], kind="mergesort")
    prev = o.groupby("stock_code")["_i"].shift(1)
    keep = prev.isna() | (o["_i"] - prev != 1)
    return o.loc[keep].drop(columns="_i").reset_index(drop=True)
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_stats.py -q`
Expected: 7 passed

- [ ] **Step 5: 커밋**

```bash
git add backtest/concept_axes/theme_rank/stats.py backtest/concept_axes/theme_rank/tests/test_stats.py
git commit -F <메시지 파일>   # feat(theme_rank): 일별 IC·HAC t(NewsQuant 같은 식)·차수 보존 셔플·AR(1) 가짜 신호·에피소드 첫 행
```

---

### Task 6: `bandfill.py` + `build_arena.py`(경기장 원장 · 결과만)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/bandfill.py`
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/build_arena.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_bandfill.py`

**Interfaces:**
- Consumes: `snapshot.norm_code`; `candidate_ledger.run`(`ENTRY_TIME`, `build_path`, `Env`, `build_book`, `excl_class_map`, `_date_index`, `load_bad_open`, `make_minute_fn`, `make_window_fn`, `_connect`, `PX_START`, `W_END`, `BASE`); `ledger8.exitsim8`(`Pos`, `ExitRules`, `simulate_lot`, `BASIS_UPPER`); `ledger8.sizing.arm_b_qty`; `ledger8.sources8.aware`; `ledger8.sellprobe8`(`resolve_live_tp_sl`, `SellProbe`); `ledger8.livesignal8.load8`
- Produces: `FILL_OPEN/FILL_BAND/FILL_NONE/FILL_NO_BAR` · `Fill(status, price)` · `band_fill(open_, low, hi) -> Fill` · `resim_band_touch(code, d1, price, env, rules, probe) -> ExitOut` · `filled(arena: pd.DataFrame) -> pd.DataFrame`(fill ∈ {open, band_touch} ∧ ret_net 있음) · `build_arena.STRATEGY` · `ARENA_MAX_RANK=20` · `COST_PCT=0.25` · `LEDGER_MD5` · `load_ledger() -> pd.DataFrame` · `arena_rows(led, low_of, resim) -> List[Dict]` · 출력 `results/arena.csv`(열 `ARENA_COLS`) + `results/arena_meta.json`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_bandfill.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.theme_rank import bandfill as BF
from backtest.concept_axes.theme_rank import build_arena as BA


def test_band_fill_rules():
    assert BF.band_fill(102.0, 101.0, 103.0) == BF.Fill(BF.FILL_OPEN, 102.0)
    assert BF.band_fill(103.0, 99.0, 103.0) == BF.Fill(BF.FILL_OPEN, 103.0)          # 경계 포함
    assert BF.band_fill(106.0, 102.0, 103.0) == BF.Fill(BF.FILL_BAND, 103.0)
    assert BF.band_fill(106.0, 104.0, 103.0) == BF.Fill(BF.FILL_NONE, None)
    assert BF.band_fill(None, None, 103.0) == BF.Fill(BF.FILL_NO_BAR, None)
    assert BF.band_fill(0.0, 0.0, 103.0).status == BF.FILL_NO_BAR


def _bar(d, o, h, lo, c):
    return X.Bar(d, o, h, lo, c)


def test_resim_band_touch_enters_at_upper_and_skips_entry_day_touch():
    d1, d2 = date(2026, 1, 5), date(2026, 1, 6)
    bars = {d1: _bar(d1, 106.0, 120.0, 90.0, 104.0),          # 진입일: 고저가 ±10% 를 넘지만 시각 불명 → 안 봄
            d2: _bar(d2, 105.0, 114.0, 104.0, 110.0)}         # 다음 날 고가 114 ≥ 103×1.1 → 익절
    env = SimpleNamespace(cal=[d1, d2], cal_idx={d1: 0, d2: 1}, bars=lambda code: bars)
    ex = BF.resim_band_touch("000001", d1, 103.0, env, X.ExitRules(0.10, 0.10, 10), lambda pos, d: None)
    assert ex.reason == "tp" and ex.exit_date == d2
    assert ex.price == pytest.approx(113.3) and ex.ret_pct == pytest.approx(10.0)


@dataclass
class _Ex:
    exit_date: date
    reason: str
    hold_days: int
    ret_pct: float
    flags: list


def _led(rows):
    cols = ["strategy", "scan_date", "stock_code", "rank", "score", "n_passed", "band_hi", "entry_date",
            "entry_price", "exit_date", "exit_reason", "hold_days", "ret_pct", "flags"]
    return pd.DataFrame(rows, columns=cols)


def test_arena_rows_open_band_none_and_rank_cut():
    led = _led([
        (BA.STRATEGY, "2026-01-02", "1", 1, 9.0, 30, 103.0, "2026-01-05", 102.0, "2026-01-07", "tp", 2, 10.0, "a"),
        (BA.STRATEGY, "2026-01-02", "2", 2, 8.0, 30, 103.0, "2026-01-05", 106.0, "2026-01-06", "sl", 1, -10.0, "b"),
        (BA.STRATEGY, "2026-01-02", "3", 3, 7.0, 30, 103.0, "2026-01-05", 106.0, "2026-01-06", "sl", 1, -10.0, "c"),
        (BA.STRATEGY, "2026-01-02", "4", 21, 1.0, 30, 103.0, "2026-01-05", 102.0, "2026-01-07", "tp", 2, 10.0, "d"),
    ])
    lows = {("000002", date(2026, 1, 5)): 101.0, ("000003", date(2026, 1, 5)): 104.0}
    calls = []

    def resim(code, d1, price):
        calls.append((code, d1, price))
        return _Ex(date(2026, 1, 8), "max_hold", 3, 1.5, ["x"])

    rows = BA.arena_rows(led, lambda c, d: lows.get((c, d)), resim)
    by = {r["stock_code"]: r for r in rows}
    assert set(by) == {"000001", "000002", "000003"}                       # rank 21 제외
    assert by["000001"]["fill"] == "open" and by["000001"]["ret_net"] == pytest.approx(9.75)
    assert by["000002"]["fill"] == "band_touch" and by["000002"]["entry_price"] == 103.0
    assert by["000002"]["ret_pct"] == 1.5 and by["000002"]["ret_net"] == pytest.approx(1.25)
    assert calls == [("000002", date(2026, 1, 5), 103.0)]
    assert by["000003"]["fill"] == "none"


def test_arena_rows_no_bar_and_none_fill_have_blank_returns():
    led = _led([(BA.STRATEGY, "2026-01-02", "5", 1, 9.0, 3, 103.0, None, None, None, None, None, None, "no_open")])
    r = BA.arena_rows(led, lambda c, d: None, lambda *a: None)[0]
    assert r["fill"] == "no_bar" and r["ret_pct"] == "" and r["ret_net"] == ""


def test_arena_rows_normalizes_stock_code():
    led = _led([(BA.STRATEGY, "2026-01-02", "5930", 1, 9.0, 3, 103.0, "2026-01-05", 102.0, "2026-01-06",
                 "tp", 1, 10.0, "")])
    assert BA.arena_rows(led, lambda c, d: None, lambda *a: None)[0]["stock_code"] == "005930"


def test_filled_keeps_only_bought_rows_with_returns():
    a = pd.DataFrame({"fill": ["open", "band_touch", "none", "open"], "ret_net": [1.0, 2.0, None, None]})
    assert BF.filled(a)["ret_net"].tolist() == [1.0, 2.0]
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_bandfill.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/bandfill.py`

```python
"""라이브 +3% 밴드 체결의 일봉 재현(스펙 §5-1) + 밴드 터치 로트의 청산 재시뮬.

시가 ≤ 상한 → 시가 체결(원장 결과 그대로) · 시가 > 상한 ∧ 저가 ≤ 상한 → 상한가 체결(재시뮬) · 그 밖 미체결.
daytrading 은 하한이 없다(`entry_band_down_pct` None) — 하한은 보지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

FILL_OPEN, FILL_BAND, FILL_NONE, FILL_NO_BAR = "open", "band_touch", "none", "no_bar"


@dataclass(frozen=True)
class Fill:
    status: str
    price: Optional[float]


def band_fill(open_: Optional[float], low: Optional[float], hi: Optional[float]) -> Fill:
    if open_ is None or not open_ > 0:
        return Fill(FILL_NO_BAR, None)
    if hi is None or open_ <= hi:
        return Fill(FILL_OPEN, float(open_))
    if low is not None and low <= hi:
        return Fill(FILL_BAND, float(hi))
    return Fill(FILL_NONE, None)


def resim_band_touch(code: str, d1: date, price: float, env: Any, rules: Any, probe: Any) -> Any:
    """상한가에 산 것으로 보고 원장과 같은 청산기(`exitsim8.simulate_lot`)로 다시 돈다.

    체결 시각을 모르므로 진입일 터치 청산은 보지 않는다(ledger8 A3 상한 민감도 규칙 · `BASIS_UPPER` · touch_bar=None).
    """
    from backtest.concept_axes.candidate_ledger import run as CL
    from backtest.concept_axes.ledger8 import exitsim8 as X
    from backtest.concept_axes.ledger8 import sizing as Z
    from backtest.concept_axes.ledger8 import sources8 as SRC8
    q = Z.arm_b_qty(price)
    pos = X.Pos(code, d1, SRC8.aware(datetime.combine(d1, CL.ENTRY_TIME)), float(price), q.qty, X.BASIS_UPPER)
    path = CL.build_path(env.cal, env.cal_idx, env.bars(code), d1, rules.max_hold_days)
    return X.simulate_lot(pos, rules, path, probe)


def filled(arena: pd.DataFrame) -> pd.DataFrame:
    """판정에 쓰는 행 = 체결(시가·밴드 터치) ∧ 순수익 있음."""
    a = arena[arena["fill"].isin([FILL_OPEN, FILL_BAND])].copy()
    a["ret_net"] = pd.to_numeric(a["ret_net"], errors="coerce")
    return a[a["ret_net"].notna()].reset_index(drop=True)
```

- [ ] **Step 4: 구현** — `theme_rank/build_arena.py`

```python
"""경기장 원장(스펙 §5-1) — daytrading 후보 원장 rank ≤ 20 행에 밴드 재현 체결·청산·순수익을 붙인다.

🔴 테마 신호를 읽지 않는다(신호와 결과의 결합은 동결 뒤 `run.py` 에서만) · DB SELECT 전용.

    python -X utf8 -m backtest.concept_axes.theme_rank.build_arena
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import hashlib                                                         # noqa: E402
import json                                                            # noqa: E402
import subprocess                                                      # noqa: E402
from collections import Counter                                        # noqa: E402
from datetime import date                                              # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Callable, Dict, List, Optional, Tuple          # noqa: E402

import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger import run as CL           # noqa: E402
from backtest.concept_axes.theme_rank import bandfill as BF            # noqa: E402
from backtest.concept_axes.theme_rank.snapshot import norm_code        # noqa: E402

STRATEGY = "daytrading_3methods_breakout"
ARENA_MAX_RANK = 20                                  # 🔒 라이브 E6 가 읽는 범위
COST_PCT = 0.25                                      # 🔒 freq_scenarios COST_RATE 0.0025 × 100(왕복 %p)
LEDGER_CSV = CL.BASE / "results" / "ledger.csv"
LEDGER_MD5 = "980e58492a7ac2ed11d25526f4488dbc"
OUT = Path(__file__).resolve().parent / "results"
ARENA_COLS = ["scan_date", "stock_code", "rank", "score", "n_passed", "band_hi", "fill", "entry_date",
              "entry_price", "exit_date", "exit_reason", "hold_days", "ret_pct", "ret_net", "flags"]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def load_ledger() -> pd.DataFrame:
    got = md5(LEDGER_CSV)
    if got != LEDGER_MD5:
        raise SystemExit(f"ledger.csv md5 불일치 {got} ≠ {LEDGER_MD5} — 중단")
    led = pd.read_csv(LEDGER_CSV, dtype={"stock_code": str, "scan_date": str, "entry_date": str,
                                         "exit_date": str}, low_memory=False)
    return led[led["strategy"] == STRATEGY].reset_index(drop=True)


def _num(x: Any) -> Optional[float]:
    v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
    return None if pd.isna(v) else float(v)


def _txt(x: Any) -> str:
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)


def arena_rows(led: pd.DataFrame, low_of: Callable[[str, date], Optional[float]],
               resim: Callable[[str, date, float], Any]) -> List[Dict[str, Any]]:
    """순수 조립 — low_of(code, d1) = D+1 저가 · resim(code, d1, price) = 밴드 터치 로트 ExitOut."""
    out: List[Dict[str, Any]] = []
    for r in led.itertuples(index=False):
        if int(r.rank) > ARENA_MAX_RANK:
            continue
        code = norm_code(r.stock_code)
        open_, hi = _num(r.entry_price), _num(r.band_hi)
        d1 = date.fromisoformat(str(r.entry_date)) if _txt(r.entry_date) else None
        low = low_of(code, d1) if (open_ is not None and hi is not None and d1 is not None and open_ > hi) else None
        f = BF.band_fill(open_, low, hi)
        row: Dict[str, Any] = dict(scan_date=r.scan_date, stock_code=code, rank=int(r.rank), score=r.score,
                                   n_passed=int(r.n_passed), band_hi=_txt(r.band_hi), fill=f.status,
                                   entry_date=_txt(r.entry_date), entry_price="", exit_date="", exit_reason="",
                                   hold_days="", ret_pct="", ret_net="", flags=_txt(r.flags))
        if f.status == BF.FILL_OPEN:
            row.update(entry_price=open_, exit_date=_txt(r.exit_date), exit_reason=_txt(r.exit_reason),
                       hold_days=_txt(r.hold_days), ret_pct=_num(r.ret_pct) if _num(r.ret_pct) is not None else "")
        elif f.status == BF.FILL_BAND:
            ex = resim(code, d1, f.price)
            row.update(entry_price=f.price, exit_date=_txt(ex.exit_date), exit_reason=_txt(ex.reason),
                       hold_days=_txt(ex.hold_days), ret_pct=ex.ret_pct if ex.ret_pct is not None else "",
                       flags=";".join(ex.flags))
        if row["ret_pct"] != "":
            row["ret_net"] = float(row["ret_pct"]) - COST_PCT
        out.append(row)
    return out


def build_env(conn) -> Any:
    """`candidate_ledger.run.main` 과 같은 벌크 로드(재사용 모듈 수정 0줄)."""
    from backtest.concept_axes.replayer import flags as FL
    from backtest.concept_axes.replayer import loader as LD
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, CL.PX_START, CL.W_END)]
    px = LD.load_prices(conn, CL.PX_START, CL.W_END)
    book = CL.build_book(px)
    fl = FL.compute_bar_flags(px)
    m_imp = fl["flag_padding"] | fl["flag_locked_limit"] | fl["flag_cliff"]
    return CL.Env(cal=cal, book=book, uni=LD.build_universe(px),
                  excl=CL.excl_class_map(sorted(book), LD.load_stock_names(conn)),
                  imp_dates=CL._date_index(zip(px.loc[m_imp, "stock_code"], px.loc[m_imp, "date"])),
                  corp_dates=CL._date_index(LD.load_corp_events(conn).keys()),
                  bad_open=CL.load_bad_open(conn, CL.PX_START, CL.W_END), minute_fn=CL.make_minute_fn(conn))


def main() -> int:
    from backtest.concept_axes.ledger8 import sellprobe8 as SP
    from backtest.concept_axes.ledger8.livesignal8 import load8
    led = load_ledger()
    conn = CL._connect()
    env = build_env(conn)
    strategy = load8(STRATEGY)
    rules = SP.resolve_live_tp_sl(STRATEGY, strategy)
    if (rules.tp, rules.sl, rules.max_hold_days) != (0.10, 0.10, 10):
        raise SystemExit(f"청산 규칙이 스펙과 다르다: {rules}")
    probe = SP.SellProbe(STRATEGY, strategy, CL.make_window_fn(env.book))

    def low_of(code: str, d1: date) -> Optional[float]:
        b = env.bars(code).get(d1)
        return float(b.low) if b is not None else None

    rows = arena_rows(led, low_of, lambda code, d1, px: BF.resim_band_touch(code, d1, px, env, rules, probe))
    conn.close()
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=ARENA_COLS).to_csv(OUT / "arena.csv", index=False, encoding="utf-8")
    cnt = Counter(r["fill"] for r in rows)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = dict(git_sha=sha, ledger_md5=LEDGER_MD5, n_rows=len(rows), fill_counts=dict(cnt),
                n_days=len({r["scan_date"] for r in rows}), arena_md5=md5(OUT / "arena.csv"))
    (OUT / "arena_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"경기장 {len(rows):,}행 · {meta['n_days']}일 · 체결 {dict(cnt)} · md5 {meta['arena_md5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_bandfill.py -q`
Expected: 6 passed

- [ ] **Step 6: 러너 실행(결과만 · 신호 없음)** — 백그라운드 권장(벌크 로드 수 분)

Run: `$PY -X utf8 -m backtest.concept_axes.theme_rank.build_arena`
Expected: `경기장 N행 · 617일(이하) · 체결 {'open': …, 'band_touch': …, 'none': …, 'no_bar': …} · md5 …`. 수익률 분포·평균을 출력하거나 들여다보지 않는다(개수만).

- [ ] **Step 7: 커밋**

```bash
git add backtest/concept_axes/theme_rank/bandfill.py backtest/concept_axes/theme_rank/build_arena.py backtest/concept_axes/theme_rank/tests/test_bandfill.py backtest/concept_axes/theme_rank/results/arena.csv backtest/concept_axes/theme_rank/results/arena_meta.json
git commit -F <메시지 파일>   # feat(theme_rank): 밴드 재현 체결 + 경기장 원장(rank≤20·밴드 터치 재시뮬·비용 0.25%p) · 신호 0
```

---

### Task 7: `build_signals.py` + `describe.py`(신호만 · 결과 없음)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/build_signals.py`
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/describe.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_build_signals.py`

**Interfaces:**
- Consumes: `snapshot`(`load_snapshot`, `invert`, `norm_code`) · `membership`(`SNAP_DATE`, `eligible_themes`, `restrict`, `EXCLUDED_NAME_PATTERNS`) · `returns`(`bad_rows`, `daily_returns`, `excess_by_day`, `raw_by_day`) · `signal`(전부) · `stats.spearman` · `build_arena`(`LEDGER_CSV`, `LEDGER_MD5`, `STRATEGY`, `ARENA_MAX_RANK`, `md5`)
- Produces: `SIG_COLS` · `PX_START="2024-02-01"` · `Inputs`(dataclass) · `compute_rows(keys: Sequence[Tuple[date, str]], inp: Inputs) -> List[Dict]` · `load_keys() -> Tuple[List[Tuple[date,str]], Dict[date, FrozenSet[str]]]`(경기장 키 · 그날 전체 후보) · `load_day_states(conn) -> Tuple[Dict[date, DayState], Dict[date, Dict[str,float]], Dict[date, Dict[str,float]], List[date]]` · `primary_s(keys, states, themes_of, members) -> List[float]` · 출력 `results/signals.csv` + `results/signals_meta.json` · `results/DESCRIBE.md`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_build_signals.py`

```python
from __future__ import annotations

from datetime import date

import pytest

from backtest.concept_axes.theme_rank import build_signals as BS
from backtest.concept_axes.theme_rank import signal as SG

D0, D1 = date(2026, 1, 5), date(2026, 1, 6)
UNI = {f"{i:06d}" for i in range(10)}


def _inputs():
    ex0 = {c: 0.0 for c in UNI}
    ex1 = {c: (0.06 if c in {"000001", "000002"} else 0.0) for c in UNI}
    members = {1: frozenset({"000009", "000001", "000002", "000003"}), 2: frozenset({"000009", "000004"})}
    th = {"000009": frozenset({1, 2})}
    full_members = dict(members) | {3: frozenset({"000009", "000005", "000006"})}
    return BS.Inputs(states={D0: SG.day_state(ex0), D1: SG.day_state(ex1)}, excess={D0: ex0, D1: ex1},
                     raw_r={D0: dict(ex0), D1: {**ex1, "000009": 0.30}},
                     themes_of=th, members=members,
                     themes_of_full={"000009": frozenset({1, 2, 3})}, members_full=full_members,
                     day_codes={D1: frozenset({"000009", "000001", "000777"})},
                     streak_of={(1, D1): 1, (2, D1): 0})


def test_compute_rows_primary_and_print_items():
    row = BS.compute_rows([(D1, "000009")], _inputs())[0]
    expect = -SG.log10_binom_tail(3, 0.2, 2) - __import__("math").log10(2)
    assert row["s"] == pytest.approx(expect) and row["m"] == 2 and row["main_theme"] == 1
    assert row["single"] is False and row["s_input_ok"] is True
    assert row["c_same_theme"] == 1 and row["b_rank_in_theme"] == 3 and row["b_limit_up"] is True
    assert row["a2_streak"] == 1 and row["a_mean_excess"] == pytest.approx(0.04)
    assert row["s_full"] == pytest.approx(-SG.log10_binom_tail(3, 0.2, 2) - __import__("math").log10(3))


def test_compute_rows_missing_day_state_marks_input_not_ok():
    row = BS.compute_rows([(date(2026, 1, 7), "000009")], _inputs())[0]
    assert row["s_input_ok"] is False and row["s"] == "" and row["main_theme"] == ""


def test_primary_s_matches_compute_rows():
    inp = _inputs()
    assert BS.primary_s([(D1, "000009"), (D0, "000009")], inp.states, inp.themes_of, inp.members) == [
        pytest.approx(BS.compute_rows([(D1, "000009")], inp)[0]["s"]), 0.0]
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_build_signals.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/build_signals.py`

```python
"""테마 신호(스펙 §4) — 경기장 키(scan_date·stock_code)마다 돌출도 S 와 인쇄 항목.

🔴 결과 열(ret·exit 등)을 읽지 않는다 — 원장에서 `strategy, scan_date, stock_code, rank` 만 읽는다.

    python -X utf8 -m backtest.concept_axes.theme_rank.build_signals --n-cut <N_CUT>
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import json                                                            # noqa: E402
import subprocess                                                      # noqa: E402
from dataclasses import dataclass                                      # noqa: E402
from datetime import date                                              # noqa: E402
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple  # noqa: E402

import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger import run as CL           # noqa: E402
from backtest.concept_axes.theme_rank import build_arena as BA         # noqa: E402
from backtest.concept_axes.theme_rank import membership as MB          # noqa: E402
from backtest.concept_axes.theme_rank import returns as RT             # noqa: E402
from backtest.concept_axes.theme_rank import signal as SG              # noqa: E402
from backtest.concept_axes.theme_rank import snapshot as SN            # noqa: E402

PX_START = "2024-02-01"          # 창 첫날(2024-03-13)의 D−1 과 A″ 연속 일수 여유
SIG_COLS = ["scan_date", "stock_code", "s_input_ok", "s", "log10_p", "m", "main_theme", "k_main", "n_main",
            "single", "s_full", "a_mean_excess", "c_same_theme", "b_rank_in_theme", "b_limit_up", "a2_streak"]


@dataclass
class Inputs:
    states: Dict[date, SG.DayState]
    excess: Dict[date, Dict[str, float]]
    raw_r: Dict[date, Dict[str, float]]
    themes_of: Dict[str, FrozenSet[int]]
    members: Dict[int, FrozenSet[str]]
    themes_of_full: Dict[str, FrozenSet[int]]
    members_full: Dict[int, FrozenSet[str]]
    day_codes: Dict[date, FrozenSet[str]]
    streak_of: Dict[Tuple[int, date], int]


def compute_rows(keys: Sequence[Tuple[date, str]], inp: Inputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d, code in keys:
        st = inp.states.get(d)
        if st is None:
            out.append({k: "" for k in SIG_COLS} | dict(scan_date=d, stock_code=code, s_input_ok=False))
            continue
        sp = SG.surprise(code, inp.themes_of, inp.members, st)
        full = SG.surprise(code, inp.themes_of_full, inp.members_full, st)
        ex = inp.excess[d]
        t = sp.main_theme
        out.append(dict(
            scan_date=d, stock_code=code, s_input_ok=True, s=sp.s, log10_p=sp.log10_p, m=sp.m,
            main_theme="" if t is None else t, k_main=sp.k_main, n_main=sp.n_main, single=sp.single,
            s_full=full.s,
            a_mean_excess=SG.mean_excess_max(code, inp.themes_of, inp.members, ex),
            c_same_theme="" if t is None else SG.same_theme_count(code, t, inp.members,
                                                                   inp.day_codes.get(d, frozenset())),
            b_rank_in_theme="" if t is None else SG.rank_in_theme(code, t, inp.members, ex),
            b_limit_up=inp.raw_r[d].get(code, 0.0) >= SG.LIMIT_UP_R,
            a2_streak="" if t is None else inp.streak_of.get((t, d), 0)))
    return out


def primary_s(keys: Sequence[Tuple[date, str]], states: Mapping[date, SG.DayState],
              themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]]) -> List[float]:
    """S 만(플라시보 재계산용 · run.py). 상태 없는 날 = NaN."""
    return [SG.surprise(c, themes_of, members, states[d]).s if d in states else float("nan") for d, c in keys]


def load_keys() -> Tuple[List[Tuple[date, str]], Dict[date, FrozenSet[str]]]:
    if BA.md5(BA.LEDGER_CSV) != BA.LEDGER_MD5:
        raise SystemExit("ledger.csv md5 불일치 — 중단")
    led = pd.read_csv(BA.LEDGER_CSV, usecols=["strategy", "scan_date", "stock_code", "rank"],
                      dtype={"stock_code": str, "scan_date": str})
    led = led[led["strategy"] == BA.STRATEGY]
    led["d"] = pd.to_datetime(led["scan_date"]).dt.date
    led["c"] = led["stock_code"].map(SN.norm_code)
    day_codes = {d: frozenset(g["c"]) for d, g in led.groupby("d")}
    arena = led[led["rank"] <= BA.ARENA_MAX_RANK].sort_values(["d", "rank"])
    return list(zip(arena["d"], arena["c"])), day_codes


def load_day_states(conn) -> Tuple[Dict[date, SG.DayState], Dict[date, Dict[str, float]],
                                   Dict[date, Dict[str, float]], List[date]]:
    from backtest.concept_axes.replayer import loader as LD
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, PX_START, CL.W_END)]
    px = LD.load_prices(conn, PX_START, CL.W_END)
    rets = RT.daily_returns(px, cal, RT.bad_rows(px))
    excess = RT.excess_by_day(rets)
    return {d: SG.day_state(e) for d, e in excess.items()}, excess, RT.raw_by_day(rets), cal


def streak_table(themes: Sequence[int], members: Mapping[int, FrozenSet[str]],
                 states: Mapping[date, SG.DayState], cal: Sequence[date]) -> Dict[Tuple[int, date], int]:
    out: Dict[Tuple[int, date], int] = {}
    for t in themes:
        run = 0
        for d in cal:
            st = states.get(d)
            run = run + 1 if (st is not None and SG.theme_logp(t, members, st) < SG.STREAK_LOGP) else 0
            out[(t, d)] = run
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-cut", type=int, required=True)
    a = ap.parse_args(argv)
    keys, day_codes = load_keys()
    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE)
    states, excess, raw_r, cal = load_day_states(conn)
    conn.close()
    elig = MB.eligible_themes(snap.theme_name, a.n_cut)
    members = MB.restrict(snap.members, elig)
    inp = Inputs(states=states, excess=excess, raw_r=raw_r, themes_of=SN.invert(members), members=members,
                 themes_of_full=SN.invert(snap.members), members_full=dict(snap.members), day_codes=day_codes,
                 streak_of=streak_table(sorted(elig), members, states, cal))
    rows = compute_rows(keys, inp)
    BA.OUT.mkdir(parents=True, exist_ok=True)
    path = BA.OUT / "signals.csv"
    pd.DataFrame(rows, columns=SIG_COLS).to_csv(path, index=False, encoding="utf-8")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = dict(git_sha=sha, n_cut=a.n_cut, patterns=list(MB.EXCLUDED_NAME_PATTERNS), snap_date=str(MB.SNAP_DATE),
                n_eligible_themes=len(elig), n_rows=len(rows), ledger_md5=BA.LEDGER_MD5, signals_md5=BA.md5(path))
    (BA.OUT / "signals_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"신호 {len(rows):,}행 · 적격 테마 {len(elig)} · md5 {meta['signals_md5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_build_signals.py -q`
Expected: 3 passed

- [ ] **Step 5: 서술 진단** — `theme_rank/describe.py`(결과 열을 읽지 않는다)

```python
"""결과 없는 서술 진단(사전등록 근거) — signals.csv + 원장 순위 열만 읽는다.

    python -X utf8 -m backtest.concept_axes.theme_rank.describe
"""
from __future__ import annotations

import pandas as pd

from backtest.concept_axes.theme_rank import build_arena as BA
from backtest.concept_axes.theme_rank import stats as ST


def main() -> int:
    sig = pd.read_csv(BA.OUT / "signals.csv", dtype={"stock_code": str})
    s = pd.to_numeric(sig["s"], errors="coerce")
    n_day = sig.groupby("scan_date").size()
    rank = sig.groupby("scan_date").cumcount() + 1                      # load_keys 가 (d, rank) 순으로 썼다
    corr = pd.Series({d: ST.spearman(g["s"], rank.loc[g.index]) for d, g in sig.assign(s=s).groupby("scan_date")})
    top3 = sig.assign(s=s, r=rank).sort_values(["scan_date", "s"], ascending=[True, False]).groupby("scan_date").head(3)
    dup = top3[top3["main_theme"].notna()].groupby(["scan_date", "main_theme"]).size()
    days_dup = dup[dup >= 2].index.get_level_values(0).nunique()
    lines = ["# 서술 진단 — 결과 없음", "",
             f"- 경기장 키 {len(sig):,} · 날짜 {n_day.size} · 하루 키 중앙 {int(n_day.median())} · 최대 {int(n_day.max())}",
             f"- S 계산률 {sig['s_input_ok'].astype(str).eq('True').mean():.3f}",
             f"- S = 0 비율 {(s == 0).mean():.3f} · 단독 재료 비율 {sig['single'].astype(str).eq('True').mean():.3f}",
             f"- 하루 안 Spearman(S, 현재 순위) 평균 {corr.mean():+.3f}(유효 {corr.notna().sum()}일)",
             f"- S 상위 3 안 같은 주 테마 2종목 이상인 날 {days_dup}/{n_day.size}",
             f"- 주 테마 상위 10: {sig['main_theme'].dropna().astype(int).value_counts().head(10).to_dict()}"]
    (BA.OUT / "DESCRIBE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 러너 실행(N_cut 은 Task 11 전 예비값 547 로 한 번 · PREREG 확정 뒤 다시 돈다)**

Run: `$PY -X utf8 -m backtest.concept_axes.theme_rank.build_signals --n-cut 547 && $PY -X utf8 -m backtest.concept_axes.theme_rank.describe`
Expected: `신호 N행 · 적격 테마 …` · DESCRIBE.md 6줄. S 계산률 ≈ 1.000.

- [ ] **Step 7: 커밋**

```bash
git add backtest/concept_axes/theme_rank/build_signals.py backtest/concept_axes/theme_rank/describe.py backtest/concept_axes/theme_rank/tests/test_build_signals.py backtest/concept_axes/theme_rank/results/signals.csv backtest/concept_axes/theme_rank/results/signals_meta.json backtest/concept_axes/theme_rank/results/DESCRIBE.md
git commit -F <메시지 파일>   # feat(theme_rank): 경기장 키별 돌출도 S·인쇄 항목 + 결과 없는 서술 진단 · 예비 N_cut 547
```

---

### Task 8: `slots.py`(자리 경로 · 빈 자리 고정 짝 비교)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/slots.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_slots.py`

**Interfaces:**
- Consumes: 없음(순수 · DataFrame 열 이름만 약속: `scan_date, stock_code, rank, entry_date, exit_date, exit_reason, ret_net, s, main_theme`)
- Produces: `Lot(day, code, release, ret, base_rank, sig, main_theme)` · `lots_from(df, cal: Sequence[str]) -> Dict[int, List[Lot]]` · `baseline_path(lots_by_day, n_days, n_cap=5, k_cap=10) -> Tuple[Dict[int, List[Lot]], Dict[int, FrozenSet[str]]]` · `pick(eligible, f, descending=True, cap_per_theme=None) -> List[Lot]` · `DayCmp(day, f, base, theme, arena, n_eligible, max_same_theme)` · `paired(lots_by_day, buys, held_before, descending=True, cap_per_theme=None) -> List[DayCmp]` · `summarize(cmps) -> Dict[str, float]`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_slots.py`

```python
from __future__ import annotations

import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import slots as SL


def L(day, code, rel, ret, rank, sig, theme=None):
    return SL.Lot(day, code, rel, ret, rank, sig, theme)


def test_baseline_path_rank_order_daily_cap_and_slots():
    lots = {0: [L(0, "A", 5, 1.0, 1, 0.0), L(0, "B", 5, 2.0, 2, 0.0), L(0, "C", 5, 3.0, 3, 0.0)],
            1: [L(1, "D", 5, 4.0, 1, 0.0)]}
    buys, held = SL.baseline_path(lots, 3, n_cap=2, k_cap=3)
    assert [l.code for l in buys[0]] == ["A", "B"]           # 하루 2
    assert [l.code for l in buys[1]] == ["D"]                # 자리 3 중 2 사용 → 1 남음
    assert held[1] == frozenset({"A", "B"})


def test_held_stock_skipped_in_both_arms():
    lots = {0: [L(0, "A", 3, 1.0, 1, 0.0)],
            1: [L(1, "A", 4, 9.0, 1, 5.0), L(1, "B", 4, 2.0, 2, 1.0), L(1, "C", 4, 3.0, 3, 2.0)]}
    buys, held = SL.baseline_path(lots, 2, n_cap=1, k_cap=10)
    assert [l.code for l in buys[1]] == ["B"]                 # A 는 보유 중
    cmp_ = SL.paired(lots, buys, held)
    d1 = [c for c in cmp_ if c.day == 1][0]
    assert d1.f == 1 and d1.theme == 3.0 and d1.base == 2.0  # 테마 쪽도 A 를 건너뛰고 C(sig 2) 선택
    assert d1.arena == pytest.approx(2.5) and d1.n_eligible == 2


def test_pick_descending_ties_by_rank_and_theme_cap():
    el = [L(0, "A", 9, 0, 3, 1.0, 7), L(0, "B", 9, 0, 1, 1.0, 7), L(0, "C", 9, 0, 2, 0.5, 7), L(0, "D", 9, 0, 4, 0.1, 8)]
    assert [l.code for l in SL.pick(el, 3)] == ["B", "A", "C"]
    assert [l.code for l in SL.pick(el, 3, cap_per_theme=2)] == ["B", "A", "D"]
    assert [l.code for l in SL.pick(el, 2, descending=False)] == ["D", "C"]


def test_summarize_weights_by_f():
    cmps = [SL.DayCmp(0, 1, 1.0, 3.0, 2.0, 4, 1), SL.DayCmp(1, 3, 0.0, 1.0, 1.0, 5, 2)]
    s = SL.summarize(cmps)
    assert s["R_base"] == pytest.approx(0.25) and s["R_theme"] == pytest.approx(1.5) and s["R_arena"] == pytest.approx(1.25)
    assert s["d_cur"] == pytest.approx(1.0) and s["d_theme"] == pytest.approx(0.25)
    assert s["n_days"] == 2 and s["n_lots"] == 4


def test_lots_from_release_rules():
    cal = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    df = pd.DataFrame({"scan_date": ["2026-01-02", "2026-01-02"], "stock_code": ["000001", "000002"],
                       "rank": [1, 2], "entry_date": ["2026-01-05", "2026-01-05"],
                       "exit_date": ["2026-01-06", "2026-01-07"], "exit_reason": ["tp", "open"],
                       "ret_net": [9.75, 1.0], "s": [1.0, 0.0], "main_theme": [7.0, None]})
    by = SL.lots_from(df, cal)
    a, b = by[1]
    assert (a.release, b.release) == (3, 4)                   # 청산 다음 날 / open = 창 끝
    assert a.main_theme == 7 and b.main_theme is None
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_slots.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/slots.py`

```python
"""자리 K=10 · 하루 5 기준선 경로와 빈 자리 고정 짝 비교(스펙 §5-4).

기준선 = 현재 순위(원장 rank) 순서 · 같은 종목 보유 중이면 건너뜀(`freq_scenarios.simulate_capped` 와 같은 규칙).
같은 날 테마 쪽은 «기준선이 그날 산 수 f_D» 만큼 S 순으로 고른다(경로가 갈라지지 않게 · 보유 중 제외).
자리 반환: exit_reason=open 은 창 끝까지, 그 밖은 청산 다음 거래일부터 빈다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

import pandas as pd


@dataclass(frozen=True)
class Lot:
    day: int
    code: str
    release: int
    ret: float
    base_rank: int
    sig: float
    main_theme: Optional[int]


def lots_from(df: pd.DataFrame, cal: Sequence[str]) -> Dict[int, List[Lot]]:
    idx = {d: i for i, d in enumerate(cal)}
    n = len(cal)
    out: Dict[int, List[Lot]] = {}
    for r in df.itertuples(index=False):
        if str(r.entry_date) not in idx:
            continue
        day = idx[str(r.entry_date)]
        rel = n if str(r.exit_reason) == "open" else idx[str(r.exit_date)] + 1
        t = None if pd.isna(r.main_theme) or r.main_theme == "" else int(float(r.main_theme))
        out.setdefault(day, []).append(Lot(day, str(r.stock_code), rel, float(r.ret_net), int(r.rank),
                                           float(r.s), t))
    return out


def baseline_path(lots_by_day: Mapping[int, Sequence[Lot]], n_days: int, n_cap: int = 5,
                  k_cap: int = 10) -> Tuple[Dict[int, List[Lot]], Dict[int, FrozenSet[str]]]:
    held: Dict[str, int] = {}
    buys: Dict[int, List[Lot]] = {}
    held_before: Dict[int, FrozenSet[str]] = {}
    for day in range(n_days):
        for c in [c for c, rel in held.items() if rel <= day]:
            del held[c]
        held_before[day] = frozenset(held)
        got: List[Lot] = []
        for lot in sorted(lots_by_day.get(day, ()), key=lambda x: x.base_rank):
            if lot.code in held or len(got) >= n_cap or len(held) >= k_cap:
                continue
            held[lot.code] = lot.release
            got.append(lot)
        buys[day] = got
    return buys, held_before


def pick(eligible: Sequence[Lot], f: int, descending: bool = True, cap_per_theme: Optional[int] = None) -> List[Lot]:
    order = sorted(eligible, key=lambda x: ((-x.sig if descending else x.sig), x.base_rank))
    out: List[Lot] = []
    per: Dict[int, int] = {}
    for lot in order:
        if len(out) >= f:
            break
        if cap_per_theme is not None and lot.main_theme is not None and per.get(lot.main_theme, 0) >= cap_per_theme:
            continue
        out.append(lot)
        if lot.main_theme is not None:
            per[lot.main_theme] = per.get(lot.main_theme, 0) + 1
    return out


@dataclass(frozen=True)
class DayCmp:
    day: int
    f: int
    base: float
    theme: float
    arena: float
    n_eligible: int
    max_same_theme: int


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def paired(lots_by_day: Mapping[int, Sequence[Lot]], buys: Mapping[int, Sequence[Lot]],
           held_before: Mapping[int, FrozenSet[str]], descending: bool = True,
           cap_per_theme: Optional[int] = None) -> List[DayCmp]:
    out: List[DayCmp] = []
    for day in sorted(buys):
        f = len(buys[day])
        eligible = [l for l in lots_by_day.get(day, ()) if l.code not in held_before[day]]
        if f == 0 or not eligible:
            continue
        th = pick(eligible, f, descending, cap_per_theme)
        cnt: Dict[int, int] = {}
        for l in th:
            if l.main_theme is not None:
                cnt[l.main_theme] = cnt.get(l.main_theme, 0) + 1
        out.append(DayCmp(day, f, _mean([l.ret for l in buys[day]]), _mean([l.ret for l in th]),
                          _mean([l.ret for l in eligible]), len(eligible), max(cnt.values(), default=0)))
    return out


def summarize(cmps: Sequence[DayCmp]) -> Dict[str, float]:
    w = sum(c.f for c in cmps)
    if not w:
        return dict(R_base=float("nan"), R_theme=float("nan"), R_arena=float("nan"), d_cur=float("nan"),
                    d_theme=float("nan"), n_days=0, n_lots=0, share_same_theme3=float("nan"))
    rb = sum(c.f * c.base for c in cmps) / w
    rt = sum(c.f * c.theme for c in cmps) / w
    ra = sum(c.f * c.arena for c in cmps) / w
    return dict(R_base=rb, R_theme=rt, R_arena=ra, d_cur=ra - rb, d_theme=rt - ra, n_days=len(cmps), n_lots=w,
                share_same_theme3=sum(1 for c in cmps if c.max_same_theme >= 3) / len(cmps))
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_slots.py -q`
Expected: 5 passed

- [ ] **Step 5: 커밋**

```bash
git add backtest/concept_axes/theme_rank/slots.py backtest/concept_axes/theme_rank/tests/test_slots.py
git commit -F <메시지 파일>   # feat(theme_rank): 자리 K=10·하루 5 기준선 경로 + 빈 자리 고정 짝 비교(Δ_cur·Δ_theme) · 같은 테마 상한 변형
```

---

### Task 9: `calibrate.py`(가짜 테마 신호 400개 · 도구 교정)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/calibrate.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_calibrate.py`

**Interfaces:**
- Consumes: `stats`(`daily_ic`, `hac_t`, `ar1_noise`, `fake_s`) · `bandfill.filled` · `membership`(`SNAP_DATE`, `eligible_themes`, `restrict`) · `snapshot`(`load_snapshot`, `invert`) · `build_arena`(`OUT`, `md5`)
- Produces: `N_FAKES=400` · `PHI=0.9` · `ACCEPT=(0.07, 0.13)` · `LAGS=(11, 22, 33)` · `fake_t_stats(arena, themes_of, members, days, lags, n_fakes, seed) -> Dict[int, List[float]]` · `choose(t_by_lag) -> Dict`(키 `mode`, `lag`, `rates`) · `calibrated_p(t, calib: Mapping) -> float` · 출력 `calibration/calib.json` + `calibration/RESULTS.md`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_calibrate.py`

```python
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import calibrate as CA


def _null_arena(n_days=120, per_day=12, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for i in range(per_day):
            rows.append((f"2026-{d:04d}", f"{i:06d}", float(rng.standard_normal())))
    return pd.DataFrame(rows, columns=["scan_date", "stock_code", "ret_net"])


def test_choose_picks_first_lag_inside_band_else_empirical():
    t_ok = {11: [3.0] * 10 + [0.0] * 90, 22: [0.0] * 100, 33: [0.0] * 100}       # |t|≥1.645 비율 0.10
    assert CA.choose(t_ok) == {"mode": "hac", "lag": 11, "rates": {11: 0.10, 22: 0.0, 33: 0.0}}
    t_bad = {11: [3.0] * 40 + [0.0] * 60, 22: [3.0] * 30 + [0.0] * 70, 33: [3.0] * 20 + [0.0] * 80}
    c = CA.choose(t_bad)
    assert c["mode"] == "empirical" and c["lag"] == 11


def test_calibrated_p_modes():
    assert CA.calibrated_p(1.96, {"mode": "hac", "lag": 11}) == pytest.approx(math.erfc(1.96 / math.sqrt(2)))
    calib = {"mode": "empirical", "lag": 11, "t_fakes": {"11": [0.5, -2.5, 3.0, 1.0]}}
    assert CA.calibrated_p(2.0, calib) == pytest.approx((1 + 2) / 5)


def test_fake_t_stats_rejection_rate_near_nominal_on_null_data():
    arena = _null_arena()
    members = {t: frozenset(f"{(t * 3 + i) % 12:06d}" for i in range(4)) for t in range(8)}
    th = {}
    for t, m in members.items():
        for c in m:
            th.setdefault(c, set()).add(t)
    th = {c: frozenset(v) for c, v in th.items()}
    days = sorted(arena["scan_date"].unique())
    t = CA.fake_t_stats(arena, th, members, days, lags=(11,), n_fakes=60, seed=7)
    rate = sum(abs(x) >= 1.6448536269514722 for x in t[11]) / len(t[11])
    assert len(t[11]) == 60 and rate <= 0.30
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_calibrate.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/calibrate.py`

```python
"""도구 교정(스펙 §5-3) — 실제 소속표 + 테마×날짜 AR(1) 잡음으로 만든 가짜 S 400개를 실제 결과에 돌린다.

실제 S 는 읽지 않는다(가짜 신호 × 결과만). 합격 = p<0.10 거부율 ∈ [0.07, 0.13].
lag 11 → 22 → 33 순으로 첫 합격 lag 를 쓰고, 모두 불합격이면 lag 11 가짜 t 의 경험분포로 p 를 보정한다.

    python -X utf8 -m backtest.concept_axes.theme_rank.calibrate --n-cut <N_CUT>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from backtest.concept_axes.theme_rank import bandfill as BF
from backtest.concept_axes.theme_rank import build_arena as BA
from backtest.concept_axes.theme_rank import stats as ST

N_FAKES = 400
PHI = 0.9
ACCEPT = (0.07, 0.13)
LAGS = (11, 22, 33)
SEED = 20261008
Z10 = 1.6448536269514722                    # 양측 p < 0.10 ⟺ |t| ≥ 1.645
OUT = Path(__file__).resolve().parent / "calibration"


def fake_t_stats(arena: pd.DataFrame, themes_of: Mapping[str, FrozenSet[int]],
                 members: Mapping[int, FrozenSet[str]], days: Sequence[str], lags: Sequence[int] = LAGS,
                 n_fakes: int = N_FAKES, seed: int = SEED) -> Dict[int, List[float]]:
    di = {d: i for i, d in enumerate(days)}
    out: Dict[int, List[float]] = {L: [] for L in lags}
    for i in range(n_fakes):
        z = ST.ar1_noise(members.keys(), len(days), PHI, np.random.default_rng([seed, i]))
        sig = [ST.fake_s(c, themes_of, members, {t: z[t][di[d]] for t in themes_of.get(c, ())})
               for d, c in zip(arena["scan_date"], arena["stock_code"])]
        ic, _ = ST.daily_ic(arena.assign(_f=sig), "_f", "ret_net")
        for L in lags:
            out[L].append(ST.hac_t(ic, L)["t_hac"])
    return out


def choose(t_by_lag: Mapping[int, Sequence[float]]) -> Dict[str, object]:
    rates = {L: sum(1 for t in ts if math.isfinite(t) and abs(t) >= Z10) / len(ts) for L, ts in t_by_lag.items()}
    for L in sorted(t_by_lag):
        if ACCEPT[0] <= rates[L] <= ACCEPT[1]:
            return {"mode": "hac", "lag": L, "rates": rates}
    return {"mode": "empirical", "lag": min(t_by_lag), "rates": rates}


def calibrated_p(t: float, calib: Mapping[str, object]) -> float:
    if calib["mode"] == "hac":
        return math.erfc(abs(t) / math.sqrt(2))
    fakes = [x for x in calib["t_fakes"][str(calib["lag"])] if math.isfinite(x)]
    return (1 + sum(1 for x in fakes if abs(x) >= abs(t))) / (len(fakes) + 1)


def main(argv: Optional[Sequence[str]] = None) -> int:
    from backtest.concept_axes.candidate_ledger import run as CL
    from backtest.concept_axes.theme_rank import membership as MB
    from backtest.concept_axes.theme_rank import snapshot as SN
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-cut", type=int, required=True)
    a = ap.parse_args(argv)
    arena = BF.filled(pd.read_csv(BA.OUT / "arena.csv", dtype={"stock_code": str, "scan_date": str}))
    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE)
    conn.close()
    members = MB.restrict(snap.members, MB.eligible_themes(snap.theme_name, a.n_cut))
    days = sorted(arena["scan_date"].unique())
    t = fake_t_stats(arena, SN.invert(members), members, days)
    c = choose(t)
    calib = dict(c, t_fakes={str(L): v for L, v in t.items()}, n_fakes=N_FAKES, phi=PHI, accept=list(ACCEPT),
                 n_cut=a.n_cut, arena_md5=BA.md5(BA.OUT / "arena.csv"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calib.json").write_text(json.dumps(calib, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 도구 교정 결과(가짜 테마 신호)", "",
             f"- 가짜 {N_FAKES}개 · AR(1) φ={PHI} · 합격 [{ACCEPT[0]}, {ACCEPT[1]}] · N_cut {a.n_cut}",
             *[f"- lag {L}: p<0.10 거부율 {r:.3f}" for L, r in c["rates"].items()],
             f"- 선택: mode={c['mode']} · lag={c['lag']}", f"- calib.json md5 {BA.md5(OUT / 'calib.json')}"]
    (OUT / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_calibrate.py -q`
Expected: 3 passed

- [ ] **Step 5: 커밋(실행은 Task 11 에서 확정 N_cut 으로)**

```bash
git add backtest/concept_axes/theme_rank/calibrate.py backtest/concept_axes/theme_rank/tests/test_calibrate.py
git commit -F <메시지 파일>   # feat(theme_rank): 가짜 테마 신호 400개 도구 교정(lag 11→22→33 · 경험분포 대체)
```

---

### Task 10: `run.py`(판정 · 동결 가드 — 이 Task 에서는 실행하지 않는다)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/run.py`
- Test: `RoboTrader_template/backtest/concept_axes/theme_rank/tests/test_run.py`

**Interfaces:**
- Consumes: `stats` · `slots` · `bandfill.filled` · `calibrate.calibrated_p` · `build_signals`(`load_day_states`, `load_keys`, `primary_s`) · `membership` · `snapshot` · `build_arena`(`OUT`, `md5`)
- Produces: `N_CUT: Optional[int] = None` · `PREREG_FROZEN_BLOB = ""` · `ALPHA=0.05` · `EPS=0.5` · `LAG_ROBUST=22` · `N_PLACEBO=200` · `WIN_E`, `WIN_C` · `read_frozen_md5(text) -> Dict[str, str]` · `guard(blob_of, prereg_text, md5_of) -> None`(어긋나면 `SystemExit`) · `verdict(p, mean_ic, mean_e, mean_c, d_theme, ic_minus_bias) -> str`(`"PASS"|"NEG"|"FAIL"`) · 출력 `results/RESULTS.md`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_run.py`

```python
from __future__ import annotations

import pytest

from backtest.concept_axes.theme_rank import run as RN

TXT = ("…\n- arena.csv md5: " + "a" * 32 + "\n- signals.csv md5: " + "b" * 32 +
       "\n- calib.json md5: " + "c" * 32 + "\n")


def test_read_frozen_md5():
    assert RN.read_frozen_md5(TXT) == {"arena.csv": "a" * 32, "signals.csv": "b" * 32, "calib.json": "c" * 32}


def test_guard_refuses_when_not_frozen_or_mismatch(monkeypatch):
    monkeypatch.setattr(RN, "PREREG_FROZEN_BLOB", "")
    monkeypatch.setattr(RN, "N_CUT", 547)
    with pytest.raises(SystemExit):
        RN.guard(lambda: "x" * 40, TXT, lambda name: "a" * 32)
    monkeypatch.setattr(RN, "PREREG_FROZEN_BLOB", "f" * 40)
    with pytest.raises(SystemExit):
        RN.guard(lambda: "e" * 40, TXT, lambda name: "a" * 32)                 # blob 불일치
    md5s = {"arena.csv": "a" * 32, "signals.csv": "b" * 32, "calib.json": "0" * 32}
    with pytest.raises(SystemExit):
        RN.guard(lambda: "f" * 40, TXT, md5s.get)                             # calib md5 불일치
    md5s["calib.json"] = "c" * 32
    RN.guard(lambda: "f" * 40, TXT, md5s.get)                                 # 통과


def test_guard_refuses_without_n_cut(monkeypatch):
    monkeypatch.setattr(RN, "PREREG_FROZEN_BLOB", "f" * 40)
    monkeypatch.setattr(RN, "N_CUT", None)
    with pytest.raises(SystemExit):
        RN.guard(lambda: "f" * 40, TXT, {"arena.csv": "a" * 32, "signals.csv": "b" * 32, "calib.json": "c" * 32}.get)


@pytest.mark.parametrize("args,expected", [
    ((0.01, 0.03, 0.02, 0.04, 0.6, 0.02), "PASS"),
    ((0.01, 0.03, 0.02, 0.04, 0.4, 0.02), "FAIL"),     # 돈 게이트 미달
    ((0.01, 0.03, 0.02, 0.04, 0.6, -0.01), "FAIL"),    # 편향 빼면 부호 뒤집힘
    ((0.01, 0.03, -0.01, 0.04, 0.6, 0.02), "FAIL"),    # 두 창 부호 불일치
    ((0.20, 0.03, 0.02, 0.04, 0.6, 0.02), "FAIL"),     # 유의 아님
    ((0.01, -0.03, -0.02, -0.04, -0.6, -0.02), "NEG"),
    ((0.01, -0.03, 0.02, -0.04, -0.6, -0.02), "FAIL"),
])
def test_verdict_table(args, expected):
    assert RN.verdict(*args) == expected
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_run.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현** — `theme_rank/run.py`

```python
"""판정(스펙 §5-6) — 🔒 동결 가드 통과 시에만 실행(Task 13 · 10-17 동결 뒤).

가드: PREREG.md 의 git blob = PREREG_FROZEN_BLOB(비어 있으면 거부) ∧ N_CUT 설정 ∧ arena.csv·signals.csv·calib.json
md5 = PREREG.md 에 적힌 값. 실제 S 와 결과를 처음 합치는 곳이 여기다.

    python -X utf8 -m backtest.concept_axes.theme_rank.run
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import json                                                            # noqa: E402
import math                                                            # noqa: E402
import re                                                              # noqa: E402
import subprocess                                                      # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Callable, Dict, List, Optional                      # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.theme_rank import bandfill as BF            # noqa: E402
from backtest.concept_axes.theme_rank import build_arena as BA         # noqa: E402
from backtest.concept_axes.theme_rank import calibrate as CA           # noqa: E402
from backtest.concept_axes.theme_rank import slots as SL               # noqa: E402
from backtest.concept_axes.theme_rank import stats as ST               # noqa: E402

N_CUT: Optional[int] = None          # 🔒 Task 13 동결 때 PREREG 값으로 설정
PREREG_FROZEN_BLOB = ""              # 🔒 Task 13 동결 커밋의 `git rev-parse HEAD:<PREREG.md 경로>`
ALPHA, EPS = 0.05, 0.5
LAG_ROBUST = 22
N_PLACEBO = 200
SEED = 20261017
WIN_E = ("2024-03-13", "2025-06-30")
WIN_C = ("2025-07-01", "2026-09-23")
HERE = Path(__file__).resolve().parent
PREREG = HERE / "PREREG.md"
FILES = {"arena.csv": BA.OUT / "arena.csv", "signals.csv": BA.OUT / "signals.csv",
         "calib.json": CA.OUT / "calib.json"}


def read_frozen_md5(text: str) -> Dict[str, str]:
    return {m.group(1): m.group(2)
            for m in re.finditer(r"^- (arena\.csv|signals\.csv|calib\.json) md5: ([0-9a-f]{32})$", text, re.M)}


def guard(blob_of: Callable[[], str], prereg_text: str, md5_of: Callable[[str], Optional[str]]) -> None:
    if not PREREG_FROZEN_BLOB or N_CUT is None:
        raise SystemExit("🔒 동결 전 — PREREG_FROZEN_BLOB·N_CUT 미설정. run.py 는 Task 13 에서만 돈다.")
    if blob_of() != PREREG_FROZEN_BLOB:
        raise SystemExit("PREREG.md 가 동결본과 다르다 — 중단")
    want = read_frozen_md5(prereg_text)
    for name in FILES:
        if name not in want or md5_of(name) != want[name]:
            raise SystemExit(f"{name} md5 가 PREREG 와 다르다 — 중단")


def verdict(p: float, mean_ic: float, mean_e: float, mean_c: float, d_theme: float, ic_minus_bias: float) -> str:
    if not (p < ALPHA) or mean_e * mean_c <= 0 or mean_e * mean_ic <= 0:
        return "FAIL"
    if mean_ic > 0:
        return "PASS" if (d_theme >= EPS and ic_minus_bias > 0) else "FAIL"
    return "NEG"


def _window(ic: pd.Series, win) -> float:
    idx = pd.Index(ic.index.astype(str))
    return float(ic[(idx >= win[0]) & (idx <= win[1])].mean())


def main() -> int:
    from backtest.concept_axes.candidate_ledger import run as CL
    from backtest.concept_axes.theme_rank import build_signals as BS
    from backtest.concept_axes.theme_rank import membership as MB
    from backtest.concept_axes.theme_rank import snapshot as SN
    rel = PREREG.relative_to(HERE.parents[3]).as_posix()
    blob = lambda: subprocess.run(["git", "rev-parse", f"HEAD:{rel}"], capture_output=True,  # noqa: E731
                                  text=True, cwd=HERE.parents[3]).stdout.strip()
    text = PREREG.read_text(encoding="utf-8") if PREREG.exists() else ""        # 없어도 가드가 먼저 막는다
    guard(blob, text, lambda n: BA.md5(FILES[n]) if FILES[n].exists() else None)
    calib = json.loads(FILES["calib.json"].read_text(encoding="utf-8"))

    arena = BF.filled(pd.read_csv(FILES["arena.csv"], dtype={"stock_code": str, "scan_date": str}))
    sig = pd.read_csv(FILES["signals.csv"], dtype={"stock_code": str, "scan_date": str})
    df = arena.merge(sig, on=["scan_date", "stock_code"], how="left", validate="one_to_one")
    df["s"] = pd.to_numeric(df["s"], errors="coerce")

    ic, skipped = ST.daily_ic(df, "s", "ret_net")
    h = ST.hac_t(ic, int(calib["lag"]))
    h22 = ST.hac_t(ic, LAG_ROBUST)
    p = CA.calibrated_p(h["t_hac"], calib)
    mean_e, mean_c = _window(ic, WIN_E), _window(ic, WIN_C)

    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE)
    states, _, _, _ = BS.load_day_states(conn)
    conn.close()
    members = MB.restrict(snap.members, MB.eligible_themes(snap.theme_name, N_CUT))
    keys = [(pd.Timestamp(d).date(), c) for d, c in zip(df["scan_date"], df["stock_code"])]
    rng = np.random.default_rng(SEED)
    pl: List[float] = []
    for _ in range(N_PLACEBO):
        sh = ST.degree_preserving_shuffle(members, rng)
        s_pl = BS.primary_s(keys, states, SN.invert(sh), sh)
        pic, _ = ST.daily_ic(df.assign(_pl=s_pl), "_pl", "ret_net")
        pl.append(float(pic.mean()))
    bias = float(np.mean(pl))

    cal = sorted(pd.read_csv(BA.LEDGER_CSV, usecols=["scan_date"], dtype={"scan_date": str})["scan_date"].unique())
    lots = SL.lots_from(df, cal)
    buys, held = SL.baseline_path(lots, len(cal))
    eco = SL.summarize(SL.paired(lots, buys, held))
    eco2 = SL.summarize(SL.paired(lots, buys, held, cap_per_theme=2))
    v = verdict(p, h["mean_ic"], mean_e, mean_c, eco["d_theme"], h["mean_ic"] - bias)

    extra = []
    for col in ["s_full", "a_mean_excess", "c_same_theme", "b_rank_in_theme", "b_limit_up", "a2_streak"]:
        x = pd.to_numeric(df[col].replace({"True": 1, "False": 0}), errors="coerce")
        if col == "b_rank_in_theme":
            x = -x                                                      # 순위 1 = 최고 → 부호 맞춤
        eic, _ = ST.daily_ic(df.assign(_x=x), "_x", "ret_net")
        eh = ST.hac_t(eic, int(calib["lag"]))
        extra.append(f"| {col} | {eh['mean_ic']:+.4f} | {eh['t_hac']:+.2f} | {eh['n_days']} |")
    epi = ST.episode_first(df.assign(scan_date=pd.to_datetime(df["scan_date"]).dt.date),
                           {pd.Timestamp(d).date(): i for i, d in enumerate(cal)})
    eic, _ = ST.daily_ic(epi, "s", "ret_net")
    mde = (1.959963984540054 + 0.8416212335729143) * h["se_hac"]
    lines = [
        "# 판정 결과 — 테마 순위 층(daytrading)", "", f"## 판정: **{v}**", "",
        f"- 1차 IC 평균 {h['mean_ic']:+.4f} · HAC t(lag {calib['lag']}) {h['t_hac']:+.2f} · 교정 p {p:.4f}"
        f"({calib['mode']}) · lag 22 t {h22['t_hac']:+.2f} p {h22['p_hac']:.4f}",
        f"- 유효일 {h['n_days']} · 제외일 {skipped} · 창 E {mean_e:+.4f} · 창 C {mean_c:+.4f}",
        f"- 플라시보 평균 편향 b {bias:+.4f}(200회) · IC − b {h['mean_ic'] - bias:+.4f}",
        f"- 돈: R_base {eco['R_base']:+.3f} · R_arena {eco['R_arena']:+.3f} · R_theme {eco['R_theme']:+.3f} %p · "
        f"Δ_cur {eco['d_cur']:+.3f} · **Δ_theme {eco['d_theme']:+.3f}** · 날 {eco['n_days']} · 로트 {eco['n_lots']}",
        f"- 같은 테마 최대 2개 변형: Δ_theme {eco2['d_theme']:+.3f} · 3종목 이상 날 비율(무제한) {eco['share_same_theme3']:.3f}",
        f"- MDE(80%·양측 5%) ≈ {mde:.4f} · 에피소드 첫 행 IC {eic.mean():+.4f}({eic.size}일)",
        f"- S=0 비율 {(df['s'] == 0).mean():.3f} · 경기장 체결 행 {len(df):,}", "",
        "## 인쇄 항목(판정 불변)", "", "| 항목 | IC 평균 | HAC t | 일수 |", "|---|---|---|---|", *extra, "",
        "🔴 기각 전용 — 통과해도 소속표 미래 참조·생존 편향 때문에 상한이다(스펙 §5-7)."]
    (BA.OUT / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests/test_run.py -q`
Expected: 10 passed

- [ ] **Step 5: 가드가 실제로 막는지 확인(실행 0 — 가드에서 끝나야 한다)**

Run: `$PY -X utf8 -m backtest.concept_axes.theme_rank.run`
Expected: `SystemExit: 🔒 동결 전 — PREREG_FROZEN_BLOB·N_CUT 미설정. run.py 는 Task 13 에서만 돈다.`(DB 접속·결과 출력 없음)

- [ ] **Step 6: 커밋**

```bash
git add backtest/concept_axes/theme_rank/run.py backtest/concept_axes/theme_rank/tests/test_run.py
git commit -F <메시지 파일>   # feat(theme_rank): 판정 러너(동결 가드·판정표·플라시보·짝 비교·인쇄 항목) · 실행 0
```

---

### Task 11: 사전등록 초안 `PREREG.md`(N_cut 확정 → 신호·교정 재실행 → md5 기록)

**Files:**
- Create: `RoboTrader_template/backtest/concept_axes/theme_rank/PREREG.md`
- Modify(재생성): `theme_rank/results/signals.csv`, `signals_meta.json`, `DESCRIBE.md`, `theme_rank/calibration/calib.json`, `RESULTS.md`

**Interfaces:**
- Consumes: `results/NCUT_EVIDENCE.md`(Task 2) · `results/arena_meta.json`(Task 6) · 러너 `build_signals`·`describe`·`calibrate`
- Produces: `PREREG.md`(동결 전 초안 — 머리말 `상태: 초안 · 10-17 사장님 승인 시 동결`) · `- arena.csv md5: …` / `- signals.csv md5: …` / `- calib.json md5: …` 세 줄(run.py `read_frozen_md5` 형식 그대로)

- [ ] **Step 1: N_cut 확정** — `results/NCUT_EVIDENCE.md` 를 읽고 규칙대로 고른다: 「설명이 2024-03-13 이후 사건을 다루는 첫 theme_no」(애매하면 작은 번호). 고른 번호와 그 앞뒤 3개 테마(번호·이름·근거 연도)를 메모해 둔다(Step 4 에 그대로 붙인다).

- [ ] **Step 2: 확정 N_cut 으로 신호·서술·교정 재실행**

```bash
$PY -X utf8 -m backtest.concept_axes.theme_rank.build_signals --n-cut <Step 1 번호>
$PY -X utf8 -m backtest.concept_axes.theme_rank.describe
$PY -X utf8 -m backtest.concept_axes.theme_rank.calibrate --n-cut <Step 1 번호>     # 백그라운드 권장
```
Expected: calibrate 가 `lag 11/22/33 거부율` 과 `선택: mode=… · lag=…` 출력. 결과 수익률 통계는 출력되지 않는다.

- [ ] **Step 3: md5 세 개 얻기**

```bash
md5sum backtest/concept_axes/theme_rank/results/arena.csv backtest/concept_axes/theme_rank/results/signals.csv backtest/concept_axes/theme_rank/calibration/calib.json
```

- [ ] **Step 4: `PREREG.md` 작성** — 아래 본문을 쓰고 `⟪…⟫` 표시 6곳을 Step 1~3 출력값으로 바꾼다.

```markdown
# 사전등록 — 테마 순위 층(daytrading) 과거 검정

- 상태: **초안** · 10-17 사장님 승인 시 동결(동결 커밋 sha 를 여기 적고 `run.py` `PREREG_FROZEN_BLOB` 설정)
- 규범 스펙: `docs/superpowers/specs/2026-10-08-theme-rank-layer-daytrading-design.md`(main `6078e33`) — 이 문서와 어긋나면 이 문서가 우선(더 구체적)
- 🔒 규칙 면제: 후보 특성 연구 사전등록 §4-6(같은 원장 재시도 금지)을 이 건에 한해 면제 — 사장님 2026-10-08 「면제 + 수정판 과거 검정」. 동결 때 `backtest/concept_axes/REGISTRY.md` 등재.

## 1. 입력(동결)
- 원장 `candidate_ledger/results/ledger.csv` md5 `980e58492a7ac2ed11d25526f4488dbc` · daytrading · rank ≤ 20
- 소속표 스냅샷 2026-10-08(run_id 4) 전 구간 고정
- arena.csv md5: ⟪Step 3 arena.csv⟫
- signals.csv md5: ⟪Step 3 signals.csv⟫
- calib.json md5: ⟪Step 3 calib.json⟫

## 2. 신호(스펙 §4 그대로 + 구체화)
- 튄 종목 e ≥ +0.05 · k ≥ 2 · p0 하한 1/(2|U_D|) · S = −log10(min(1, m·min p_T)) · 적격 테마 없음 → S=0(단독 재료)
- U_D = D 와 달력상 D−1 종가가 모두 있는 종목 − 패딩봉 − 가짜 절벽(잠김봉은 포함) · 의사티커 제외(loader STOCK_ONLY)
- N_cut = ⟪Step 1 번호⟫ — 근거: ⟪Step 1 앞뒤 3개 테마 번호·이름·연도⟫
- 사건·분류형 제외 패턴 `밸류업 · 지주사 · SPAC|스팩 · 신규상장 · 여름 · 겨울 · 코로나` — 해당 테마 목록은 `results/NCUT_EVIDENCE.md` 끝 절
- 인쇄만: s_full(경계·제외 없음) · A(동료 평균 초과수익 최댓값) · C(주 테마 같은 후보 수) · B′(주 테마 안 순위 · 상한가 여부) · A″(주 테마 p<0.01 연속 일수)

## 3. 체결·결과
- 밴드 상한 = 원장 band_hi · 시가 ≤ 상한 → 시가(원장 결과) · 시가 > 상한 ∧ 저가 ≤ 상한 → 상한가 체결 재시뮬(진입일 터치 안 봄 · BASIS_UPPER) · 그 밖 미체결
- 청산 TP +10% · SL −10% · 10거래일 · 같은 봉 → 손절 · 비용 0.25%p · ret_net = ret_pct − 0.25
- 서술(결과 없음): ⟪results/DESCRIBE.md 6줄 그대로⟫

## 4. 통계·교정
- 일별 Spearman(S, ret_net) · 제외일 = 체결 < 5 ∨ S 서로 다른 값 < 2
- 교정: 가짜 400 · AR(1) φ 0.9 · 합격 [0.07, 0.13] → 결과 ⟪calibration/RESULTS.md 의 lag 별 거부율과 선택 줄⟫
- 판정 p = 위 교정 방식 · lag 22 HAC 병기(판정 불변)

## 5. 판정(스펙 §5-6)
| 결과 | 조건(모두) |
|---|---|
| PASS(상한) | p < 0.05 ∧ IC > 0 ∧ 창 E·C 평균 IC 부호 = 전체 부호 ∧ Δ_theme ≥ +0.5%p ∧ IC − b > 0 |
| NEG | p < 0.05 ∧ IC < 0 ∧ 창 E·C 부호 = 전체 부호 |
| FAIL | 그 밖 |
- 창 E 2024-03-13~2025-06-30 · C 2025-07-01~2026-09-23 · b = 차수 보존 셔플 200회 평균 IC(seed 20261017)
- Δ_theme = 빈 자리 고정 짝 비교(K=10 · 하루 5 · 기준선 = 원장 rank) R_theme − R_arena

## 6. 인쇄(판정 불변)
같은 테마 최대 2개 변형 · s_full · 인쇄 항목 IC · 에피소드 첫 행 IC · MDE · S=0 비율 · 3종목 이상 같은 테마 날 비율

## 7. 금지
동결 전 run.py 실행 · 결과 본 뒤 정의 변경 · 같은 원장으로 다른 특징 재시도(면제는 이 건 1회) · 판정 문구를 인쇄 항목에 쓰기

## 8. 한계
소속표 미래 참조 · 생존 종목만 · 밴드 터치 체결 시각 불명 · 검정력 5~25%(퀀트 추정) ⇒ 기각 전용
```

- [ ] **Step 5: 표시가 남지 않았는지 확인**

Run: `grep -n "⟪" backtest/concept_axes/theme_rank/PREREG.md`
Expected: 출력 없음(0줄)

- [ ] **Step 6: 커밋**

```bash
git add backtest/concept_axes/theme_rank/PREREG.md backtest/concept_axes/theme_rank/results/ backtest/concept_axes/theme_rank/calibration/
git commit -F <메시지 파일>   # docs(theme_rank): 사전등록 초안(N_cut 확정·교정 결과·입력 md5) · 동결 = 10-17 사장님 승인
```

---

### Task 12: 0단계 — EOD 「다음 거래일 후보」 표 테마 열

**Files:**
- Modify(gitignore 됨 · 라이브 트리 scratchpad — 코드 아님): EOD 세션이 그날 쓰는 `RoboTrader_template/scratchpad/eod_YYYYMMDD/next_day_candidates_MMDD.py` 최신본(10-08 기준 `scratchpad/eod_20261008/next_day_candidates_1012.py`)
- Modify(메모리 «삽입»): `C:/Users/sttgp/.claude/projects/d--GIT-kis-trading-template/memory/feedback-eod-report-next-day-candidates.md`

**Interfaces:**
- Consumes: `D:/tmp/kis-wt-theme-rank/RoboTrader_template/backtest/concept_axes/theme_rank/snapshot.py`(`load_snap_dates`, `pick_snap_date`, `load_snapshot`, `theme_columns`, `FOOTER`) — 파일 경로 로드
- Produces: daytrading 상위 10 표에 `테마 · 크기 · 같은 테마 후보` 열 + 표 아래 고정 문구

- [ ] **Step 1: 스크립트 머리에 로더 추가**(`DatabaseConnection.initialize()` 다음 줄)

```python
import importlib.util as _ilu
_TP = r"D:/tmp/kis-wt-theme-rank/RoboTrader_template/backtest/concept_axes/theme_rank/snapshot.py"
_spec = _ilu.spec_from_file_location("theme_snapshot", _TP)
SN = _ilu.module_from_spec(_spec)
sys.modules["theme_snapshot"] = SN
_spec.loader.exec_module(SN)
with DatabaseConnection.get_connection() as _c:
    _sd = SN.pick_snap_date(SN.load_snap_dates(_c), date.today())
    SNAP = SN.load_snapshot(_c, _sd) if _sd else None
```

- [ ] **Step 2: daytrading 표에만 열 추가** — 전략별 표 루프(`for n, (up, dn, K) in STRATS.items():` 두 번째 것) 안에서 `L.append("|순위|코드|종목명|점수|룰 사유|전일종가|밴드(하~상)|보유|")` 줄부터 루프 끝 `L.append("")` 까지를 아래로 바꾼다(`h`·`dtxt` 줄과 `## …` 제목·밴드 설명 줄은 그대로 · 다른 두 전략 표 모양은 그대로).

```python
    is_dt = n == "daytrading_3methods_breakout" and SNAP is not None
    cols = SN.theme_columns([c.code for c in res8[n]], SNAP) if is_dt else {}
    head = "|순위|코드|종목명|점수|룰 사유|전일종가|밴드(하~상)|보유|" + ("테마|크기|같은 테마 후보|" if is_dt else "")
    L.append(head)
    L.append("|---" * (head.count("|") - 1) + "|")
    for i, c in enumerate(res8[n][:10], 1):
        pc = c.prev_close
        lo = f"{pc*(1-dn):,.0f}" if dn else "-"
        hi = f"{pc*(1+up):,.0f}"
        tail = ""
        if is_dt:
            tc = cols[SN.norm_code(c.code)]
            tail = f"{tc['theme']}|{tc['size'] if tc['size'] is not None else '-'}|{tc['shared']}|"
        L.append(f"|{i}|{c.code}|{names.get(c.code,'?')}|{c.score:,.2f}|{c.reason[:70]}|{pc:,.0f}|{lo}~{hi}|"
                 f"{'보유' if c.code in h else ''}|{tail}")
    if is_dt:
        L.append(f"- 테마 = 네이버 테마 스냅샷 {SNAP.snap_date}(07:45) · 같은 날 조건 통과 후보 전체와 공유 수 최다 테마. {SN.FOOTER}")
    L.append("")
```

- [ ] **Step 3: 실행해 표 확인**(라이브 트리 밖 실행 규칙 그대로 — 스크립트가 워크트리로 chdir)

Run: `$PY -X utf8 RoboTrader_template/scratchpad/eod_20261008/next_day_candidates_1012.py`(작업 디렉터리 `D:/GIT/kis-trading-template`)
Expected: daytrading 표에 테마 열 3개 · 끝 줄 「참고용 — 수동 개입 금지. 개입했다면 보고서에 기록.」 · `screener_snapshots` 실행 전후 행 수 동일(기존 첫 줄).

- [ ] **Step 4: EOD 규칙 메모리에 한 줄 «삽입»**(바이트 모드 · 임시파일 → `os.replace`) — `feedback-eod-report-next-day-candidates.md` 의 `**How to apply:**` 목록 끝에:

```markdown
- 🆕 10-12~ daytrading 표에 테마 열(테마·크기·같은 테마 후보 · 스냅샷 = 그날 07:45 · 표 아래 「참고용 — 수동 개입 금지. 개입했다면 보고서에 기록.」) — 로더 = 워크트리 `D:/tmp/kis-wt-theme-rank` 의 `theme_rank/snapshot.py` 경로 로드(스펙 `2026-10-08-theme-rank-layer-daytrading-design.md` §7 · 동결 전엔 돌출도 열 금지).
```

- [ ] **Step 5: 커밋 없음**(gitignore 된 scratchpad · 메모리 레포는 시작 훅이 자동 커밋). 실행 출력 첫 표를 사장님께 보여 드린다.

---

### Task 13: 🔒 동결 뒤 판정 실행(10-17 사장님 승인 이후에만)

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/theme_rank/PREREG.md`(상태 줄 → 동결)
- Modify: `RoboTrader_template/backtest/concept_axes/theme_rank/run.py:N_CUT, PREREG_FROZEN_BLOB`
- Modify: `RoboTrader_template/backtest/concept_axes/REGISTRY.md`(등재 1줄)
- Create: `theme_rank/results/RESULTS.md`(run.py 출력)

**Interfaces:**
- Consumes: Task 1~11 전부
- Produces: 판정 `PASS | NEG | FAIL` + `RESULTS.md`

- [ ] **Step 1: 승인 확인** — 10-17 안건에서 사장님 「동결」 승인 원문을 받는다. 없으면 여기서 멈춘다.
- [ ] **Step 2: PREREG 동결 커밋** — 상태 줄을 `🔒 동결 2026-10-17 · 사장님 「<원문>」` 으로 바꾸고 커밋. `git rev-parse HEAD:RoboTrader_template/backtest/concept_axes/theme_rank/PREREG.md` 값을 적어 둔다.
- [ ] **Step 3: run.py 상수 설정 커밋** — `N_CUT = <PREREG §2 번호>` · `PREREG_FROZEN_BLOB = "<Step 2 값>"` · REGISTRY.md 에 `theme_rank — 테마 돌출도 순위 층(daytrading) · 동결 <sha> · §4-6 면제` 1줄 · 커밋.
- [ ] **Step 4: 테스트 전체**

Run: `$PY -m pytest backtest/concept_axes/theme_rank/tests -q`
Expected: 전부 통과(test_run 의 가드 테스트는 monkeypatch 라 상수 설정과 무관)

- [ ] **Step 5: 판정 실행**(백그라운드 · 플라시보 200회)

Run: `$PY -X utf8 -m backtest.concept_axes.theme_rank.run`
Expected: `## 판정: **PASS|NEG|FAIL**` 와 숫자 줄. 가드에서 멈추면 원인(md5·blob)을 고치지 말고 보고한다.

- [ ] **Step 6: 커밋 · 보고** — `results/RESULTS.md` 커밋 · 사장님께 판정과 다음 단계(스펙 §5-6 표) 보고 · push 는 별도 확인. PASS 면 2단계 계획(스펙 §6)과 EOD 돌출도 열을 새로 기획하고, FAIL 이면 10-17 안건 daytrading 몫을 닫는다(0단계 표시만 유지).
