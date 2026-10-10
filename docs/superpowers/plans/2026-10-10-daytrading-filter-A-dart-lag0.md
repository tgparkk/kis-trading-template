# daytrading 거르기 층 A — 공시 재료 다음날 추격 금지(lag0) 확인 검정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2021-02-01~2024-03-12(아무도 안 본 구간)에서 «돌파일 당일 유상증자·최대주주변경·소송횡령(경영권분쟁 제외) 원공시가 난 daytrading 후보는 같은 날 다른 후보보다 덜 번다»를 사전등록 확인 검정으로 한 번 판정한다.

**Architecture:**
- 새 연구 패키지 `RoboTrader_template/backtest/concept_axes/dt_dart_filter/` 를 만든다. 브랜치 `research/dt-dart-filter`(base main).
- `research/dart-events` 에서 `dart_tags.py`·백필 스크립트·그 테스트만 blob 을 고정해 가져온다(전체 머지 안 함).
- 순수 함수 모듈은 합성 데이터로 TDD 한다:
  - tags · daycheck · proxy · universe · lots · stats · gate · sample
- 러너 `run.py` 단계는 아래 순서다:
  1. `proxy`
  2. `check-backfill`
  3. `build`
  4. `seal`
  5. `open`
- 재사용하는 기존 모듈: 후보 원장 `candidate_ledger/run.py` · `replayer/{loader,scan}` · `ledger8/exitsim8` · `theme_rank/bandfill`.
- 🔴 실제 표식(lag0)과 실제 수익을 같은 계산에 넣는 곳은 `run.py --stage open` 하나뿐이다. 그 단계는 동결 가드 없이는 돌지 않는다.

**Tech Stack:** Python 3.9(kis-template venv) · pandas · numpy · scipy(t 분포만) · psycopg2 · pytest. 새 의존성은 없다(로지스틱은 numpy IRLS).

**Spec:** `docs/superpowers/specs/2026-10-10-daytrading-filter-layer-design.md`(main `75326bc`) §3 · §5 · §6 · §7 · §8.

**스펙과 다른 점(계획 승인 때 확인):**
1. 「band_ok(체결 가능)」 = 스펙 §3-4 체결 규칙(시가 체결 ∪ 상한 터치 체결)로 고정한다. 원장의 `band_ok`(시가만)가 아니다.
2. 에피소드 첫 행 = 분석 표본(대리 소형 ∧ 체결)으로 거른 «뒤» 다시 계산한다(`run_dart_events` band_ok 변형 선례).
3. 보유일 탐침(SellProbe)은 쓰지 않는다. 10거래일 만기는 KOSPI 달력 `open_phase` 만 쓴다. `korean_holidays` 연말 휴장 불일치 함정을 피하기 위해서다(DOSSIER_A 0-10).
4. 생존자 누락률 (ii)를 위해 백필 유형에 **A(정기공시)** 를 더한다(`--types A,B,I`).
5. 가짜 표식의 5분위 = 분석 표본 전체 p_L 5분위다(날짜 안 아님). 같은 날 같은 분위 풀에서 뽑는다.

## Global Constraints

- 🔴 **봇 코드 0줄**: 만드는 것·고치는 것은 아래뿐이다. `strategies/`·`core/`·`config/`·`candidate_ledger/`·`ledger8/`·`replayer/`·`theme_rank/` 는 import 만 한다.
  - `RoboTrader_template/backtest/concept_axes/dt_dart_filter/**`
  - Task 1 에서 가져오는 4파일
  - `backtest/concept_axes/REGISTRY.md` 한 행
- 🔴 **라이브 트리 실행 금지**: 모든 코드·테스트·러너는 워크트리 `D:/tmp/kis-wt-dt-dart-filter` 에서만 실행한다. 라이브 트리 `D:/GIT/kis-trading-template` 의 브랜치를 바꾸지 않는다.
  - 영구 워크트리 `D:/tmp/kis-wt-dart-events` 는 건드리지 않는다(LLM shadow 운영 중).
- 🔴 **DB**:
  - 러너는 `candidate_ledger.run._connect()`(readonly) 를 쓴다. 첫 import 가 `bootstrap`(PGOPTIONS read-only)이다.
  - 유일한 쓰기는 Task 11 의 DART 백필 스크립트다(`dart_disclosures` 에 과거분 INSERT … ON CONFLICT DO NOTHING). 이 프로세스는 bootstrap 을 import 하지 않는다.
- 🔴 **결과 엿보기 금지**:
  - `build` 는 수익 원장과 표식 파일을 **따로** 쓴다.
  - `seal` 은 표식 행을 뺀 표본만 수익을 읽는다(가짜 게이트·SD).
  - `open` 은 Task 13 에서 동결 뒤 1회만 돈다.
  - 2021-01~2024-03 구간에서 표식과 수익을 합치는 어떤 임시 계산도 금지다(에이전트 포함).
- 🔴 **DART 호출 시간대**: 08:25~08:35 · 15:50~16:15 에는 백필을 돌리지 않는다(LLM shadow 적재와 한도 충돌). 연도별로 나눠 돌린다.
- 파이썬·경로:
  - `PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe`
  - 작업 디렉터리 `D:/tmp/kis-wt-dt-dart-filter/RoboTrader_template`
  - 테스트 `$PY -m pytest backtest/concept_axes/dt_dart_filter/tests -q`
  - 러너 `$PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage <단계>`
  - 워크트리에 `config/key.ini` 가 없어 import 경고가 찍히지만 무해하다. key.ini 는 복사하지 않는다.
- 커밋:
  - 브랜치 `research/dt-dart-filter` 에 계획 범위 안에서만 커밋한다. **push·main 머지는 사장님 별도 확인.**
  - 메시지는 파일(`git commit -F <파일>`): 첫 줄 = 각 Step 의 `# …` 문장(형식 `type(scope): 한국어 요약`), 빈 줄, 끝 두 줄
    - `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
    - `Claude-Session: https://claude.ai/code/session_01AYpPHTabSgiYwGzubdKLxG`
- 🔒 **동결 값(스펙 §3 그대로 · `settings.py`)**:

| 항목 | 값 |
|---|---|
| 스캔 창 | 2021-02-01~2024-03-12 |
| 가격 | 2021-01-04~2024-04-30 |
| 공시 | 2021-01-01~ |
| 대리 적합 창 | 2024-03-13~2026-09-23 |
| 태그 | 유상증자 · 최대주주변경 · 소송·횡령(U+00B7 · 경영권분쟁 제외) · 정정 제외 · 자회사/종속회사 제외(`dart_tags` 규칙) |
| 후보 조건 | 거래대금 ≥ 10억 |
| 대형 기준 | 시총 ≥ 5,000억 |
| 대리 소형 | p_L < 0.5 |
| 대리 특징 | log(20봉 평균 거래대금) · log(종가) |
| 체결 상한 | 전일 종가 × 1.03 |
| 청산 | +10% / −10% / 10거래일 |
| 비용 | 0.25%p |
| 판정 | α 0.05 단측 · δ̂ ≤ −0.4%p · n₁ ≥ 100 |
| 가짜 게이트 | 400개 · p<0.10 양측 거부율 [0.07, 0.13] |
| 블록 | 20거래일 |
| 시드 | 20261010 |
| MDE 승수 | z.95 + z.80 = 2.486 |

## Review Focus

1. **시총이 NaN 인 날(2021~2023 전부)**
   - 무시해야 하는 곳: 유니버스·대리·후보.
   - 기대: 조용히 비지 않는다. NaN 이어도 거래대금 조건만으로 후보가 나온다.
   - 테스트: Task 5 `test_build_universe_all_keeps_nan_mcap_rows` · `test_nocap_adapter_ignores_mcap`.
2. **보유 중 거래정지(거래량 0 평평봉)**
   - 기대: 손익절을 일으키지 않는다. 재개 뒤 첫 봉 시가로 청산한다. 창 끝까지 정지면 «미해소».
   - 테스트: Task 6 `test_halt_days_removed_from_path_exit_at_resume_open` · `test_halt_to_window_end_is_unresolved`.
3. **주말·공휴일 접수 공시**
   - 기대: lag0(=스캔일과 같은 날)에 들어가지 않는다. W5 에는 들어간다.
   - 테스트: Task 2 `test_window_marks_weekend_filing_not_lag0_but_in_w5`.
4. **표식·대조 중 한쪽만 있는 날, 클러스터가 1개뿐인 경우**
   - 기대: 회귀에서 빠지거나 NaN 을 정직하게 돌려준다. 0 나누기 예외가 나지 않는다.
   - 테스트: Task 7 `test_fe_drops_single_group_days` · `test_fe_single_cluster_returns_nan_se`.
5. **가짜 표식 풀이 빈 날(같은 날 같은 분위 후보 없음)**
   - 기대: 같은 날 아무 분위로 내려가고, 그래도 없으면 그 표식만 건너뛴다(셈은 남긴다). 실제 표식 종목은 가짜 풀에 절대 들어가지 않는다.
   - 테스트: Task 8 `test_fake_pool_fallback_and_excludes_real_stocks`.

---

## File Structure

```
RoboTrader_template/backtest/concept_axes/dt_dart_filter/
  __init__.py      패키지 docstring(규범 = 스펙 §3 · PREREG.md)
  settings.py      🔒 동결 상수
  tags.py          lag0/W 창 표식(dart_tags 재사용) · 공시 적재
  daycheck.py      DART 백필 완결 판정(지름길 없는 day_complete)
  proxy.py         시총 대리 특징 · 로지스틱(IRLS) · AUC
  universe.py      시총 없는 유니버스 · 시총 조건만 뺀 어댑터 · 창 스캔
  lots.py          체결 규칙 · 정지 처리 · 청산 시뮬(손절 우선/익절 우선) · 에피소드 첫 행
  sample.py        분석 표본 조립(대리 소형 ∧ 체결 ∧ 첫 행 · 표식 열 · 블록 · 분위)
  stats.py         날짜 고정효과 회귀 · 종목 CR1 · 2원 클러스터 · MDE · Holm
  gate.py          가짜 표식 400 게이트(표식 행 제외 표본)
  run.py           러너 — proxy · check-backfill · build · seal · open(동결 가드)
  PREREG.md        사전등록(Task 12)
  results/         러너 출력(커밋)
  tests/  __init__.py · conftest.py · test_*.py
(가져옴) RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/{__init__.py, dart_tags.py}
(가져옴) RoboTrader_template/scripts/dart_disclosure_backfill.py
(가져옴) RoboTrader_template/tests/{test_dart_tags.py, test_dart_disclosure_backfill.py}
```

---

### Task 1: 워크트리 · `research/dart-events` 재료 2파일 고정 가져오기

**Files:**
- Create(가져옴): `RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/dart_tags.py` · `…/dart_events/__init__.py` · `RoboTrader_template/scripts/dart_disclosure_backfill.py` · `RoboTrader_template/tests/test_dart_tags.py` · `RoboTrader_template/tests/test_dart_disclosure_backfill.py`

**Interfaces:**
- Produces:
  - `dart_tags.tag_of(report_nm: str) -> Tuple[str, bool, Dict[str, object]]` — (태그, 정정 여부, flags). flags 에 `mgmt_dispute: bool` 이 있다.
  - 백필 CLI `scripts/dart_disclosure_backfill.py --bgn --end --types --limit-calls --resume --out --sleep`

- [ ] **Step 1: 워크트리 만들기(라이브 트리 작업 사본은 바꾸지 않는다)**

```bash
git -C D:/GIT/kis-trading-template worktree add D:/tmp/kis-wt-dt-dart-filter -b research/dt-dart-filter main
cd D:/tmp/kis-wt-dt-dart-filter
git log --oneline -1   # 기대: 75326bc 이후 main HEAD
```

- [ ] **Step 2: 2파일 + 테스트 2개를 `research/dart-events` 에서 가져오기**

```bash
cd D:/tmp/kis-wt-dt-dart-filter
git checkout research/dart-events -- \
  RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/dart_tags.py \
  RoboTrader_template/scripts/dart_disclosure_backfill.py \
  RoboTrader_template/tests/test_dart_tags.py \
  RoboTrader_template/tests/test_dart_disclosure_backfill.py
git cat-file -e research/dart-events:RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/__init__.py \
  && git checkout research/dart-events -- RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/__init__.py \
  || printf '"""09-26 DART 공시 유형 검정(태그 사전만 가져옴 · research/dart-events)."""\n' > RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/__init__.py
git hash-object RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/dart_tags.py   # 기대 접두 ca3ff3d
git hash-object RoboTrader_template/scripts/dart_disclosure_backfill.py                                # 기대 접두 6ff4cbb
```

blob 접두가 다르면 멈추고 보고한다.

- [ ] **Step 3: 가져온 테스트가 이 브랜치에서 통과하는지**

```bash
cd D:/tmp/kis-wt-dt-dart-filter/RoboTrader_template
$PY -m pytest tests/test_dart_tags.py tests/test_dart_disclosure_backfill.py -q
```
기대: 전부 PASS(DB 없음).

- [ ] **Step 4: Commit**

```bash
git add RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events RoboTrader_template/scripts/dart_disclosure_backfill.py RoboTrader_template/tests/test_dart_tags.py RoboTrader_template/tests/test_dart_disclosure_backfill.py
git commit -F <메시지 파일>   # research(dt-dart-filter): research/dart-events 의 태그 사전·DART 백필 스크립트·테스트 2 고정 가져오기(blob ca3ff3d·6ff4cbb · 전체 머지 안 함)
```

---

### Task 2: 패키지 · `settings.py` · `tags.py`(lag0/W 창 표식)

**Files:**
- Create: `dt_dart_filter/__init__.py` · `dt_dart_filter/settings.py` · `dt_dart_filter/tags.py` · `dt_dart_filter/tests/__init__.py` · `dt_dart_filter/tests/conftest.py` · `dt_dart_filter/tests/test_tags.py`
  (아래 경로 접두 = `RoboTrader_template/backtest/concept_axes/`)

**Interfaces:**
- Consumes: `dart_tags.tag_of`
- Produces:
  - `tags.is_lag0_tag(report_nm: str) -> bool`
  - `tags.window_marks(filings: Iterable[Tuple[str, date, str]], cal: Sequence[date], back: int) -> Set[Tuple[str, date]]`
  - `tags.load_filings(conn, start: date, end: date) -> List[Tuple[str, date, str]]`
  - `tags.load_filings_typed(conn, start: date, end: date) -> List[Tuple[str, date, str, str]]` — 마지막 원소 = pblntf_ty
  - `settings` 모듈 상수 전부

- [ ] **Step 1: 패키지 파일**

`dt_dart_filter/__init__.py`:
```python
"""daytrading 거르기 층 A — 공시 재료 다음날 추격 금지(lag0) 확인 검정.

규범 = 스펙 `docs/superpowers/specs/2026-10-10-daytrading-filter-layer-design.md` §3 · 사전등록 `PREREG.md`.
🔴 라이브 봇 코드 0줄 · DB SELECT 전용(백필 스크립트만 예외) · 실제 표식×수익 결합은 `run.py --stage open` 하나뿐.
"""
```

`dt_dart_filter/settings.py`:
```python
"""🔒 동결 상수 — 스펙 §3 그대로. 바꾸면 사전등록 개정 대상이다."""
from __future__ import annotations

from datetime import date
from pathlib import Path

PKG = Path(__file__).resolve().parent
RESULTS = PKG / "results"
PREREG = PKG / "PREREG.md"
FOLDER = "daytrading_3methods_breakout"

SCAN_START, SCAN_END = date(2021, 2, 1), date(2024, 3, 12)
PX_START, PATH_END = "2021-01-04", "2024-04-30"
FILING_START = date(2021, 1, 1)
FIT_START, FIT_END = date(2024, 3, 13), date(2026, 9, 23)
FIT_PX_START = "2023-12-01"

TAGS_LAG0 = ("유상증자", "최대주주변경", "소송\u00b7횡령")
MGMT_TAG = "소송\u00b7횡령"

MIN_TV = 1_000_000_000
LARGE_CAP = 500_000_000_000
PL_CUT = 0.5
TV_AVG_BARS = 20
BAND_UP = 0.03

COST_PCT = 0.25
ALPHA = 0.05
DELTA_MAX = -0.4
N1_MIN = 100
BLOCK_TD = 20
SEED = 20261010
N_FAKE = 400
FAKE_P = 0.10
FAKE_LO, FAKE_HI = 0.07, 0.13
Z_ALPHA, Z_POWER = 1.6448536269514722, 0.8416212335729143
TAIL_LOSS = -15.0

PREREG_FROZEN_BLOB = ""   # Task 12 동결 커밋 뒤 설정 — 비어 있으면 seal·open 거부
```

`dt_dart_filter/tests/__init__.py`: 빈 파일.

`dt_dart_filter/tests/conftest.py`:
```python
"""dt_dart_filter 단위 테스트 — 합성 데이터 · DB 없음. 워크트리에서만 돌린다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 2: 실패하는 테스트**

`dt_dart_filter/tests/test_tags.py`:
```python
from datetime import date

from backtest.concept_axes.dt_dart_filter import tags as T

CAL = [date(2023, 3, 6), date(2023, 3, 7), date(2023, 3, 8), date(2023, 3, 9), date(2023, 3, 10),
       date(2023, 3, 13), date(2023, 3, 14)]


def test_is_lag0_tag_accepts_three_tags():
    assert T.is_lag0_tag("주요사항보고서(유상증자결정)")
    assert T.is_lag0_tag("최대주주변경을수반하는주식양수도계약체결")
    assert T.is_lag0_tag("소송등의제기ㆍ신청(일반사항)")
    assert T.is_lag0_tag("횡령ㆍ배임혐의발생")


def test_is_lag0_tag_rejects_correction_subsidiary_other_and_mgmt_dispute():
    assert not T.is_lag0_tag("[기재정정]주요사항보고서(유상증자결정)")
    assert not T.is_lag0_tag("주요사항보고서(유상증자결정)(자회사의주요경영사항)")
    assert not T.is_lag0_tag("주요사항보고서(자기주식취득결정)")
    assert not T.is_lag0_tag("단일판매ㆍ공급계약체결")
    assert not T.is_lag0_tag("소송등의제기ㆍ신청(경영권분쟁소송)")
    assert not T.is_lag0_tag("")


def test_window_marks_lag0_same_trading_day_only():
    f = [("000001", date(2023, 3, 8), "주요사항보고서(유상증자결정)")]
    assert T.window_marks(f, CAL, 0) == {("000001", date(2023, 3, 8))}


def test_window_marks_weekend_filing_not_lag0_but_in_w5():
    f = [("000002", date(2023, 3, 11), "최대주주변경")]          # 토요일
    assert T.window_marks(f, CAL, 0) == set()
    w5 = T.window_marks(f, CAL, 4)
    assert ("000002", date(2023, 3, 13)) in w5 and ("000002", date(2023, 3, 14)) in w5
    assert ("000002", date(2023, 3, 10)) not in w5


def test_window_marks_ignores_non_tags_and_blank_codes():
    f = [("000003", date(2023, 3, 8), "주요사항보고서(자기주식취득결정)"),
         ("", date(2023, 3, 8), "주요사항보고서(유상증자결정)")]
    assert T.window_marks(f, CAL, 4) == set()
```

> 표본 제목의 가운뎃점이 `dart_tags` 정규화에서 처리되는지가 의심되면 `tests/test_dart_tags.py` 의 손라벨 제목 형식을 보고 같은 형식으로 바꾼다. `tags.py` 의 의미(정정·자회사·경영권분쟁 제외)는 바꾸지 않는다.

- [ ] **Step 3: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/dt_dart_filter/tests/test_tags.py -q`
Expected: FAIL — `ImportError: cannot import name 'tags'`

- [ ] **Step 4: 구현**

`dt_dart_filter/tags.py`:
```python
"""lag0 · W 창 표식 — 스펙 §3-3. 태그 판정은 09-26 동결 `dart_tags.tag_of` 그대로."""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import date
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from backtest.concept_axes.candidate_ledger.dart_events.dart_tags import tag_of

from . import settings as S


def is_lag0_tag(report_nm: str) -> bool:
    """3태그 원공시(정정·자회사/종속회사 제외 · 소송·횡령 중 경영권분쟁 제외)면 참."""
    tag, is_corr, flags = tag_of(report_nm or "")
    if is_corr or tag not in S.TAGS_LAG0:
        return False
    return not (tag == S.MGMT_TAG and bool(flags.get("mgmt_dispute")))


def window_marks(filings: Iterable[Tuple[str, date, str]], cal: Sequence[date], back: int) -> Set[Tuple[str, date]]:
    """rcept_dt ∈ [cal[i−back], cal[i]](달력일 · 주말 포함)인 3태그 원공시가 있는 (종목, 스캔일 cal[i]).

    back=0 = lag0(스캔일과 같은 «거래일» 접수만 · 주말 접수는 없음) · back=4 = W5 · back=19 = W20.
    """
    cal = list(cal)
    out: Set[Tuple[str, date]] = set()
    for code, d, nm in filings:
        if not code or not is_lag0_tag(nm):
            continue
        j = bisect.bisect_left(cal, d)            # cal[j] ≥ d 인 첫 거래일
        jl = bisect.bisect_right(cal, d) - 1      # cal[jl] ≤ d 인 마지막 거래일
        for i in range(j, min(len(cal), jl + back + 1)):
            out.add((str(code), cal[i]))
    return out


def load_filings(conn, start: date, end: date) -> List[Tuple[str, date, str]]:
    """`dart_disclosures` (stock_code, rcept_dt, report_nm) — 종목코드 있는 행만 · SELECT 전용."""
    return [(c, d, n) for c, d, n, _ in load_filings_typed(conn, start, end)]


def load_filings_typed(conn, start: date, end: date) -> List[Tuple[str, date, str, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code, rcept_dt, report_nm, pblntf_ty FROM dart_disclosures "
                    "WHERE rcept_dt BETWEEN %s AND %s AND stock_code IS NOT NULL", (start, end))
        rows = cur.fetchall()
    conn.rollback()
    return [(str(c), d, str(n or ""), str(t or "")) for c, d, n, t in rows]
```

- [ ] **Step 5: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/dt_dart_filter/tests/test_tags.py -q`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add RoboTrader_template/backtest/concept_axes/dt_dart_filter
git commit -F <메시지 파일>   # research(dt-dart-filter): 패키지·동결 상수·lag0/W 창 표식(dart_tags 재사용 · 경영권분쟁 제외) + 테스트 5
```

---

### Task 3: `daycheck.py` — DART 백필 완결 판정(지름길 없음)

**Files:**
- Create: `dt_dart_filter/daycheck.py` · `dt_dart_filter/tests/test_daycheck.py`

**Interfaces:**
- Produces:
  - `daycheck.RawDay(state: str, total_count: int, rcept_nos: Tuple[str, ...])`
  - `daycheck.read_raw_day(out_dir: Path, ty: str, day: date) -> RawDay`
  - `daycheck.judge(rd: RawDay, n_db: int, dup: int) -> bool`
  - `daycheck.check(conn, out_dir: Path, start: date, end: date, types: Sequence[str]) -> Dict[str, Any]` — `{"n_cells", "n_bad", "bad": [...≤200], "complete": bool}`

- [ ] **Step 1: 실패하는 테스트**

`dt_dart_filter/tests/test_daycheck.py`:
```python
import json
from datetime import date

from backtest.concept_axes.dt_dart_filter import daycheck as C

D = date(2022, 5, 4)


def _page(raw, ty, p, items, tc, tp, status="000"):
    (raw / f"20220504_{ty}_p{p}.json").write_text(json.dumps(
        {"status": status, "total_count": tc, "total_page": tp, "list": items}), encoding="utf-8")


def test_ok_day_two_pages(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "B", 1, [{"rcept_no": "1"}, {"rcept_no": "2"}], 3, 2)
    _page(raw, "B", 2, [{"rcept_no": "3"}], 3, 2)
    rd = C.read_raw_day(tmp_path, "B", D)
    assert rd.state == "ok" and rd.total_count == 3 and rd.rcept_nos == ("1", "2", "3")
    assert C.judge(rd, n_db=2, dup=1) and not C.judge(rd, n_db=2, dup=0)


def test_missing_page_is_not_complete(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "I", 1, [{"rcept_no": "1"}], 2, 2)
    rd = C.read_raw_day(tmp_path, "I", D)
    assert rd.state == "missing" and not C.judge(rd, 1, 0)


def test_bad_status_page(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "B", 1, [], 0, 1, status="020")
    assert C.read_raw_day(tmp_path, "B", D).state == "bad"


def test_013_from_call_log_counts_as_empty_day(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "call_log.jsonl").write_text(json.dumps(
        {"url": "https://x/list.json?bgn_de=20220504&end_de=20220504&pblntf_ty=A&page_no=1", "status": "013"}) + "\n",
        encoding="utf-8")
    rd = C.read_raw_day(tmp_path, "A", D)
    assert rd.state == "empty013"
    assert C.judge(rd, 0, 0) and not C.judge(rd, 1, 0)


def test_no_raw_no_log_is_missing(tmp_path):
    (tmp_path / "raw").mkdir()
    assert C.read_raw_day(tmp_path, "B", D).state == "missing"
```

- [ ] **Step 2: 실패 확인** — Run: `$PY -m pytest backtest/concept_axes/dt_dart_filter/tests/test_daycheck.py -q` → FAIL(import)

- [ ] **Step 3: 구현**

`dt_dart_filter/daycheck.py`:
```python
"""DART 백필 완결 판정 — 스펙 §3-1.

`llm_shadow/dart_load.day_complete`(research/dart-events) 본문 규칙에서 «2026-09-23 이전이면 무조건 참» 지름길을
뺀 판. 하루×유형 칸이 완결 = (raw 전 페이지 status 000 ∧ 항목 합 = total_count ∧ DB 행 + 다른 유형 중복 = total_count)
또는 (013 무자료 증거 ∧ DB 행 0).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class RawDay:
    state: str                      # "ok" | "empty013" | "missing" | "bad"
    total_count: int
    rcept_nos: Tuple[str, ...]


def _has_013(call_log: Path, ds: str, ty: str) -> bool:
    if not call_log.exists():
        return False
    for line in call_log.read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        u = str(j.get("url", ""))
        if str(j.get("status")) == "013" and f"bgn_de={ds}" in u and f"pblntf_ty={ty}" in u:
            return True
    return False


def read_raw_day(out_dir: Path, ty: str, day: date) -> RawDay:
    ds = day.strftime("%Y%m%d")
    raw = Path(out_dir) / "raw"
    p1 = raw / f"{ds}_{ty}_p1.json"
    if not p1.exists():
        state = "empty013" if _has_013(Path(out_dir) / "call_log.jsonl", ds, ty) else "missing"
        return RawDay(state, 0, ())
    d1 = json.loads(p1.read_text(encoding="utf-8"))
    tc, tp = int(d1.get("total_count") or 0), int(d1.get("total_page") or 1)
    nos: List[str] = []
    for p in range(1, tp + 1):
        f = raw / f"{ds}_{ty}_p{p}.json"
        if not f.exists():
            return RawDay("missing", tc, ())
        dj = json.loads(f.read_text(encoding="utf-8"))
        if str(dj.get("status")) != "000":
            return RawDay("bad", tc, ())
        nos += [str(it.get("rcept_no", "")) for it in (dj.get("list") or [])]
    if len(nos) != tc:
        return RawDay("bad", tc, ())
    return RawDay("ok", tc, tuple(nos))


def judge(rd: RawDay, n_db: int, dup: int) -> bool:
    if rd.state == "empty013":
        return n_db == 0
    if rd.state != "ok":
        return False
    return n_db + dup == rd.total_count


def check(conn, out_dir: Path, start: date, end: date, types: Sequence[str]) -> Dict[str, Any]:
    bad: List[Dict[str, Any]] = []
    n = 0
    d = start
    with conn.cursor() as cur:
        while d <= end:
            for ty in types:
                rd = read_raw_day(out_dir, ty, d)
                cur.execute("SELECT count(*) FROM dart_disclosures WHERE rcept_dt = %s AND pblntf_ty = %s", (d, ty))
                n_db = int(cur.fetchone()[0])
                dup = 0
                if rd.rcept_nos:
                    cur.execute("SELECT count(*) FROM dart_disclosures WHERE rcept_no = ANY(%s) AND pblntf_ty <> %s",
                                (list(rd.rcept_nos), ty))
                    dup = int(cur.fetchone()[0])
                n += 1
                if not judge(rd, n_db, dup):
                    bad.append(dict(day=d.isoformat(), ty=ty, state=rd.state, tc=rd.total_count, n_db=n_db, dup=dup))
            d += timedelta(days=1)
    conn.rollback()
    return {"n_cells": n, "n_bad": len(bad), "bad": bad[:200], "complete": not bad}
```

- [ ] **Step 4: 통과 확인** — Run: `$PY -m pytest backtest/concept_axes/dt_dart_filter/tests/test_daycheck.py -q` → 5 passed

- [ ] **Step 5: Commit** — `# research(dt-dart-filter): DART 백필 완결 판정(지름길 없는 day_complete · 013 증거 · 다른 유형 중복) + 테스트 5`

---

### Task 4: `proxy.py` — 시총 대리(로지스틱 IRLS · AUC)

**Files:**
- Create: `dt_dart_filter/proxy.py` · `dt_dart_filter/tests/test_proxy.py`

**Interfaces:**
- Produces:
  - `proxy.add_proxy_features(px: pd.DataFrame, bars: int = 20) -> pd.DataFrame` — 입력 열 `stock_code, date, close, volume`(종목·날짜 오름차순 · volume 은 로더가 이미 조정). 출력 열 `stock_code, date, close, tv20, x1, x2`.
  - `proxy.design(x1, x2) -> np.ndarray` — `[1, x1, x2]`
  - `proxy.fit_logistic(X: np.ndarray, y: np.ndarray, max_iter: int = 100, tol: float = 1e-10) -> np.ndarray`
  - `proxy.predict(beta: np.ndarray, X: np.ndarray) -> np.ndarray`
  - `proxy.auc(y, s) -> float`

- [ ] **Step 1: 실패하는 테스트**

`dt_dart_filter/tests/test_proxy.py`:
```python
import numpy as np
import pandas as pd

from backtest.concept_axes.dt_dart_filter import proxy as P


def test_features_rolling_20_and_logs():
    n = 25
    px = pd.DataFrame({"stock_code": ["000001"] * n, "date": pd.date_range("2024-01-01", periods=n),
                       "close": [100.0] * n, "volume": [1000.0] * n})
    f = P.add_proxy_features(px)
    assert f["tv20"].iloc[:19].isna().all() and f["tv20"].iloc[19] == 100000.0
    assert np.isclose(f["x1"].iloc[24], np.log(100000.0)) and np.isclose(f["x2"].iloc[0], np.log(100.0))


def test_features_nonpositive_close_gives_nan():
    px = pd.DataFrame({"stock_code": ["1"] * 2, "date": pd.date_range("2024-01-01", periods=2),
                       "close": [0.0, 5.0], "volume": [1.0, 1.0]})
    assert np.isnan(P.add_proxy_features(px)["x2"].iloc[0])


def test_logistic_recovers_coefficients():
    rng = np.random.default_rng(1)
    x1, x2 = rng.normal(0, 1, 20000), rng.normal(0, 1, 20000)
    X = P.design(x1, x2)
    true = np.array([-0.5, 1.2, -0.8])
    y = (rng.random(20000) < P.predict(true, X)).astype(float)
    b = P.fit_logistic(X, y)
    assert np.allclose(b, true, atol=0.08)


def test_auc_extremes():
    assert P.auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert P.auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert np.isnan(P.auc([1, 1], [0.1, 0.2]))
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dt_dart_filter/proxy.py`:
```python
"""시총 대리 p_L — 스펙 §3-2. 입력은 결과와 무관한 거래대금·종가뿐이다.

🔴 거래량은 로더(`replayer.loader.load_prices`)가 이미 조정한 값이다 — 여기서 조정 계수를 다시 곱하지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import settings as S


def add_proxy_features(px: pd.DataFrame, bars: int = S.TV_AVG_BARS) -> pd.DataFrame:
    out = px[["stock_code", "date", "close", "volume"]].copy()
    close = out["close"].astype(float)
    tv = close * out["volume"].astype(float)
    out["tv20"] = tv.groupby(out["stock_code"]).transform(lambda s: s.rolling(bars, min_periods=bars).mean())
    out["x1"] = np.log(out["tv20"].where(out["tv20"] > 0))
    out["x2"] = np.log(close.where(close > 0))
    return out


def design(x1, x2) -> np.ndarray:
    x1, x2 = np.asarray(x1, float), np.asarray(x2, float)
    return np.column_stack([np.ones(len(x1)), x1, x2])


def predict(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    z = np.clip(X @ np.asarray(beta, float), -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-z))


def fit_logistic(X: np.ndarray, y: np.ndarray, max_iter: int = 100, tol: float = 1e-10) -> np.ndarray:
    y = np.asarray(y, float)
    beta = np.zeros(X.shape[1])
    for _ in range(max_iter):
        p = predict(beta, X)
        w = p * (1.0 - p)
        H = X.T @ (X * w[:, None]) + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ (y - p))
        beta = beta + step
        if float(np.max(np.abs(step))) < tol:
            break
    return beta


def auc(y, s) -> float:
    y = np.asarray(y, bool)
    r = pd.Series(np.asarray(s, float)).rank(method="average").to_numpy()
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))
```

- [ ] **Step 4: 통과 확인** → 4 passed

- [ ] **Step 5: Commit** — `# research(dt-dart-filter): 시총 대리(log 20봉 거래대금·log 종가 로지스틱 IRLS · AUC) + 테스트 4`

---

### Task 5: `universe.py` — 시총 없는 유니버스 · 시총 조건만 뺀 어댑터 · 창 스캔

**Files:**
- Create: `dt_dart_filter/universe.py` · `dt_dart_filter/tests/test_universe.py`

**Interfaces:**
- Consumes:
  - `replayer.scan.eligible_for_dates(uni, adapter, scan_dates) -> (elig, info)`
  - `replayer.scan.scan_strategy(px, elig, adapter, params, lookback, scan_dates=..., max_candidates=None, progress_every=0) -> (ms, dgs, imp)`
  - `candidate_ledger.run.GuardedAdapter`
  - `candidate_ledger.run.rank_day`
- Produces:
  - `universe.NoCapDaytradingAdapter`(라이브 어댑터 하위 클래스)
  - `universe.build_universe_all(px) -> Dict[pd.Timestamp, Dict[str, Tuple[float, float]]]`
  - `universe.scan_window(px: pd.DataFrame, scan_days: List[pd.Timestamp]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]`
    - 반환 행 키: `scan_date(date), stock_code, score, rank, n_passed, market_cap(float|nan), trading_value`
    - 진단 키: `n_errors, n_days, n_rows`

- [ ] **Step 1: 실패하는 테스트**

`dt_dart_filter/tests/test_universe.py`:
```python
import math

import pandas as pd

from backtest.concept_axes.dt_dart_filter import universe as U


def test_nocap_adapter_ignores_mcap():
    a = U.NoCapDaytradingAdapter()
    rows = [{"code": "1", "market_cap": 9e12, "trading_value": 2e9},
            {"code": "2", "market_cap": float("nan"), "trading_value": 2e9},
            {"code": "3", "market_cap": 1e11, "trading_value": 5e8}]
    assert [r["code"] for r in a.base_filter(rows)] == ["1", "2"]


def test_nocap_adapter_keeps_live_rule_params():
    p = U.NoCapDaytradingAdapter().default_params()
    assert p["high_window"] == 15 and p["vol_lookback"] == 20 and p["vol_mult"] == 2.0
    assert p["min_trading_value"] == 1_000_000_000


def test_build_universe_all_keeps_nan_mcap_rows():
    px = pd.DataFrame({"date": pd.to_datetime(["2021-02-01", "2021-02-01"]), "stock_code": ["1", "2"],
                       "market_cap": [float("nan"), 3e11], "close": [100.0, 10.0], "volume": [1e7, 1e6]})
    uni = U.build_universe_all(px)
    day = uni[pd.Timestamp("2021-02-01")]
    assert math.isnan(day["1"][0]) and day["1"][1] == 1e9
    assert day["2"] == (3e11, 1e7)
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dt_dart_filter/universe.py`:
```python
"""시총 조건만 뺀 daytrading 후보 재현 — 스펙 §3-2.

라이브 어댑터의 룰(15봉 고가 돌파 · 거래량 20봉 평균×2 · 양봉 · 불가능봉 가드 · 점수 = 거래량 배수)은 그대로,
`base_filter` 의 시총 조건만 뺀다. 유니버스는 시총 결측 행도 담는다(2021~2023 시총 = 결측).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

import pandas as pd

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.replayer import scan as SC
from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter


class NoCapDaytradingAdapter(Daytrading3MethodsBreakoutScreenerAdapter):
    """시총 조건만 뺀 판 — 거래대금 ≥ 10억만 남긴다."""

    def base_filter(self, universe):
        p = self.default_params()
        return [u for u in universe if float(u.get("trading_value") or 0.0) >= p["min_trading_value"]]


def build_universe_all(px: pd.DataFrame) -> Dict[pd.Timestamp, Dict[str, Tuple[float, float]]]:
    """`replayer.loader.build_universe` 와 같되 시총 결측 행도 담는다(시총 = NaN 유지)."""
    tv = (px["close"].astype(float) * px["volume"].astype(float)).to_numpy()
    out: Dict[pd.Timestamp, Dict[str, Tuple[float, float]]] = {}
    for d, c, mc, t in zip(px["date"].to_numpy(), px["stock_code"].to_numpy(), px["market_cap"].to_numpy(), tv):
        mcf = float(mc) if mc is not None and mc == mc else float("nan")
        out.setdefault(pd.Timestamp(d), {})[str(c)] = (mcf, float(t))
    return out


def scan_window(px: pd.DataFrame, scan_days: List[pd.Timestamp]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    adapter = NoCapDaytradingAdapter()
    params = adapter.default_params()
    uni = build_universe_all(px)
    elig, info = SC.eligible_for_dates(uni, adapter, scan_days)
    ga = R.GuardedAdapter(adapter)
    ms, _dgs, _imp = SC.scan_strategy(px, {d: elig.get(d, set()) for d in scan_days}, ga, params, 60,
                                      scan_dates=scan_days, max_candidates=None, progress_every=0)
    by: Dict[pd.Timestamp, List[Dict[str, Any]]] = defaultdict(list)
    for m in ms:
        by[pd.Timestamp(m["scan_date"])].append(m)
    rows: List[Dict[str, Any]] = []
    for d in scan_days:
        eff = info.get(d, {}).get("eff_date")
        day_uni = uni.get(eff, {}) if eff is not None else {}
        for r in R.rank_day(by.get(d, [])):
            mc, tv = day_uni.get(r["stock_code"], (float("nan"), float("nan")))
            rows.append(dict(scan_date=pd.Timestamp(d).date(), stock_code=r["stock_code"], score=float(r["score"]),
                             rank=int(r["rank"]), n_passed=int(r["n_passed"]), market_cap=mc, trading_value=tv))
    diag = {"n_errors": int(sum(ga.errors.values())), "n_days": len(scan_days), "n_rows": len(rows)}
    return rows, diag
```

- [ ] **Step 4: 통과 확인** → 3 passed

- [ ] **Step 5: Commit** — `# research(dt-dart-filter): 시총 조건만 뺀 어댑터·결측 시총 유니버스·창 스캔(라이브 룰 그대로) + 테스트 3`

---

### Task 6: `lots.py` — 체결 규칙 · 정지 처리 · 청산 두 규칙 · 에피소드 첫 행

**Files:**
- Create: `dt_dart_filter/lots.py` · `dt_dart_filter/tests/test_lots.py`

**Interfaces:**
- Consumes:
  - `theme_rank.bandfill.band_fill(open_, low, hi) -> Fill(status, price)` · `FILL_OPEN` · `FILL_BAND`
  - `candidate_ledger.run.build_path` · `candidate_ledger.run.ENTRY_TIME`
  - `exitsim8.{Pos, ExitRules, simulate_lot, BASIS_D_OPEN, BASIS_UPPER, FLAG_SL_TP_BOTH}`
  - `sizing.arm_b_qty` · `sources8.aware`
  - `tool_calibration.run_calib.episodes`
- Produces:
  - `lots.RULES: ExitRules(0.10, 0.10, 10)`
  - `lots.halt_dates(px) -> Dict[str, Set[date]]`
  - `lots.simulate_candidate(env, code: str, scan_d: date, halts: Set[date], rules=RULES) -> Dict[str, Any]`
    - 공통 키: `stock_code, scan_date, status`. status ∈ `filled | no_scan_bar | no_next_day | halt_entry | no_bar | no_fill`
    - filled 일 때 더 붙는 키: `fill, entry_date, entry_price, exit_date, exit_reason, hold_days, ret_sl, ret_tp, both, unresolved, halted_in_path, flags`
  - `lots.episode_first(stock: np.ndarray, cal_i: np.ndarray) -> np.ndarray[bool]`
- env 계약(덕 타이핑): `env.bars(code) -> Dict[date, Bar]` · `env.next_day(d) -> Optional[date]` · `env.bad_open: Set[(code, date)]` · `env.cal: List[date]` · `env.cal_idx: Dict[date, int]`

- [ ] **Step 1: 실패하는 테스트**

`dt_dart_filter/tests/test_lots.py`:
```python
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np

from backtest.concept_axes.dt_dart_filter import lots as L
from backtest.concept_axes.ledger8 import exitsim8 as X

CAL = [date(2022, 1, 3) + timedelta(days=i) for i in range(30)]   # 합성 달력(연속일)


def _env(bars):
    idx = {d: i for i, d in enumerate(CAL)}
    return SimpleNamespace(cal=CAL, cal_idx=idx, bad_open=set(), bars=lambda code: bars,
                           next_day=lambda d: CAL[idx[d] + 1] if idx.get(d, -9) + 1 < len(CAL) else None)


def _flat(d, p):
    return X.Bar(d, p, p, p, p)


def test_open_fill_then_take_profit():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: X.Bar(CAL[1], 101.0, 102.0, 100.0, 101.0),
            CAL[2]: X.Bar(CAL[2], 101.0, 112.0, 100.0, 110.0)}
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["status"] == "filled" and r["fill"] == "open" and r["entry_price"] == 101.0
    assert r["exit_reason"] == "tp" and round(r["ret_sl"], 6) == 10.0 and r["ret_tp"] == r["ret_sl"]


def test_band_touch_fill_at_upper():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: X.Bar(CAL[1], 104.0, 105.0, 102.5, 103.0)}
    for d in CAL[2:]:
        bars[d] = _flat(d, 103.0)
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["fill"] == "band_touch" and abs(r["entry_price"] - 103.0) < 1e-9


def test_no_fill_when_gap_above_band_all_day():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: X.Bar(CAL[1], 106.0, 108.0, 104.0, 107.0)}
    assert L.simulate_candidate(_env(bars), "1", CAL[0], set())["status"] == "no_fill"


def test_halt_on_entry_day_is_halt_entry():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    assert L.simulate_candidate(_env(bars), "1", CAL[0], {CAL[1]})["status"] == "halt_entry"


def test_same_bar_both_touch_gives_two_rules():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0),
            CAL[2]: X.Bar(CAL[2], 100.0, 111.0, 89.0, 100.0)}
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["both"] and round(r["ret_sl"], 6) == -10.0 and round(r["ret_tp"], 6) == 10.0


def test_halt_days_removed_from_path_exit_at_resume_open():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    for d in CAL[2:5]:
        bars[d] = _flat(d, 100.0)                       # 정지 평평봉(거래량 0) — 경로에서 빠져야 한다
    bars[CAL[5]] = X.Bar(CAL[5], 70.0, 72.0, 68.0, 71.0)  # 재개 첫 봉 갭 하락
    r = L.simulate_candidate(_env(bars), "1", CAL[0], {CAL[2], CAL[3], CAL[4]})
    assert r["exit_reason"] == "sl" and r["exit_date"] == CAL[5] and abs(r["ret_sl"] - (-30.0)) < 1e-9
    assert r["halted_in_path"] and not r["unresolved"]


def test_halt_to_window_end_is_unresolved():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    halts = set(CAL[2:])
    r = L.simulate_candidate(_env(bars), "1", CAL[0], halts)
    assert r["unresolved"]


def test_max_hold_exit_at_k10_open():
    bars = {d: _flat(d, 100.0) for d in CAL}
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["exit_reason"] == "max_hold" and r["exit_date"] == CAL[11]


def test_episode_first_breaks_on_gap():
    stock = np.array(["a", "a", "a", "b", "a"])
    ci = np.array([1, 2, 4, 2, 5])
    assert L.episode_first(stock, ci).tolist() == [True, False, True, True, False]
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dt_dart_filter/lots.py`:
```python
"""체결 · 정지 · 청산 — 스펙 §3-4.

- 체결 = `theme_rank.bandfill.band_fill`(시가 ≤ 상한 → 시가 · 시가 > 상한 ∧ 저가 ≤ 상한 → 상한 · 그 밖 미체결).
- 정지(거래량 ≤0 또는 결측) = 진입일이면 «진입 불가» · 보유 중이면 경로에서 빼서(봉 결측) 재개 뒤 첫 봉에서 판정.
- 청산 = `exitsim8.simulate_lot`(손절 우선) · 같은 봉 동시 터치 로트만 익절 우선 판으로 치환.
- 보유일 탐침 없음(KOSPI 달력 `open_phase` 만) — 계획 «스펙과 다른 점» 3.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, Set

import numpy as np
import pandas as pd

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.candidate_ledger.tool_calibration.run_calib import episodes
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import sizing as Z
from backtest.concept_axes.ledger8 import sources8 as SRC8
from backtest.concept_axes.theme_rank.bandfill import FILL_BAND, FILL_OPEN, band_fill

from . import settings as S

RULES = X.ExitRules(0.10, 0.10, 10, source="spec 2026-10-10 §3-4")


def _no_probe(pos, d):
    return None


def halt_dates(px: pd.DataFrame) -> Dict[str, Set[date]]:
    m = ~(px["volume"].astype(float) > 0)
    out: Dict[str, Set[date]] = defaultdict(set)
    for c, t in zip(px.loc[m, "stock_code"], px.loc[m, "date"]):
        out[str(c)].add(pd.Timestamp(t).date())
    return dict(out)


def simulate_candidate(env, code: str, scan_d: date, halts: Set[date], rules: X.ExitRules = RULES) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(stock_code=code, scan_date=scan_d)
    bars = env.bars(code)
    db = bars.get(scan_d)
    if db is None:
        return dict(base, status="no_scan_bar")
    hi = float(db.close) * (1.0 + S.BAND_UP)
    d1 = env.next_day(scan_d)
    if d1 is None:
        return dict(base, status="no_next_day")
    if d1 in halts:
        return dict(base, status="halt_entry", entry_date=d1)
    b1 = bars.get(d1)
    if b1 is None or (code, d1) in env.bad_open or not (b1.open > 0):
        return dict(base, status="no_bar", entry_date=d1)
    f = band_fill(float(b1.open), float(b1.low), hi)
    if f.status not in (FILL_OPEN, FILL_BAND):
        return dict(base, status="no_fill", entry_date=d1)
    price = float(f.price)
    basis = X.BASIS_D_OPEN if f.status == FILL_OPEN else X.BASIS_UPPER
    pos = X.Pos(code, d1, SRC8.aware(datetime.combine(d1, R.ENTRY_TIME)), price, Z.arm_b_qty(price).qty, basis)
    clean = {d: b for d, b in bars.items() if d not in halts}
    path = R.build_path(env.cal, env.cal_idx, clean, d1, rules.max_hold_days)
    ex = X.simulate_lot(pos, rules, path, _no_probe)
    both = X.FLAG_SL_TP_BOTH in list(ex.flags)
    ret_sl = float(ex.ret_pct) if ex.ret_pct is not None else float("nan")
    ret_tp = rules.tp * 100.0 if both else ret_sl
    return dict(base, status="filled", fill=f.status, entry_date=d1, entry_price=price, exit_date=ex.exit_date,
                exit_reason=ex.reason, hold_days=ex.hold_days, ret_sl=ret_sl, ret_tp=ret_tp, both=both,
                unresolved=not ex.closed, halted_in_path=any(b is None for _, _, b in path),
                flags=";".join(str(x) for x in ex.flags))


def episode_first(stock: np.ndarray, cal_i: np.ndarray) -> np.ndarray:
    """전략 1개 · 종목별 달력 순번이 직전 행과 1 넘게 벌어지면 새 에피소드(`run_calib.episodes` 그대로)."""
    codes = pd.factorize(np.asarray(stock))[0]
    _eid, first = episodes(np.zeros(len(codes), dtype=np.int64), codes.astype(np.int64),
                           np.asarray(cal_i, dtype=np.int64))
    return first
```

- [ ] **Step 4: 통과 확인** — Run: `$PY -m pytest backtest/concept_axes/dt_dart_filter/tests/test_lots.py -q` → 9 passed

  만약 `test_max_hold_exit_at_k10_open` 의 청산일이 다르면 `exitsim8.open_phase` 규칙(k ≥ max_hold 인 첫 봉 시가)을 읽고 **테스트 기대값을 원장 규칙에 맞춘다**. 진입일 CAL[1]=k0 이면 k10 = CAL[11] 이다. 코드의 청산 규칙은 바꾸지 않는다.

- [ ] **Step 5: Commit** — `# research(dt-dart-filter): 체결(시가∪상한 터치)·정지 경로 제거·손절/익절 우선 두 규칙·에피소드 첫 행 + 테스트 9`

---

### Task 7: `stats.py` — 날짜 고정효과 회귀 · 종목 CR1 · 2원 클러스터 · MDE · Holm

**Files:**
- Create: `dt_dart_filter/stats.py` · `dt_dart_filter/tests/test_stats.py`

**Interfaces:**
- Produces:
  - `stats.FE` dataclass:

    | 필드 | 형 |
    |---|---|
    | `beta` | float |
    | `se_cr1` · `se_2w` | float |
    | `p1_cr1` · `p2_cr1` · `p1_2w` · `p2_2w` | float — p1 = 단측(δ<0) · p2 = 양측 |
    | `n` · `n1` · `n_days` · `g_stock` · `g_block` | int |

  - `stats.fe_regression(y, x, day, stock, block) -> FE` — 배열 5개(같은 길이) · x ∈ {0,1}
  - `stats.mde(se: float) -> float` = (z.95 + z.80)·se
  - `stats.holm(ps: Sequence[float]) -> List[float]`

- [ ] **Step 1: 실패하는 테스트**

`dt_dart_filter/tests/test_stats.py`:
```python
import math

import numpy as np

from backtest.concept_axes.dt_dart_filter import stats as ST


def _panel(beta, seed=0, n_days=200, per_day=30):
    rng = np.random.default_rng(seed)
    day = np.repeat(np.arange(n_days), per_day)
    stock = rng.integers(0, 400, len(day))
    x = (rng.random(len(day)) < 0.05).astype(float)
    y = rng.normal(0, 1, n_days)[day] * 5 + beta * x + rng.normal(0, 8, len(day))
    return y, x, day, stock, day // 20


def test_fe_recovers_effect_and_one_sided_p():
    fe = ST.fe_regression(*_panel(-3.0, seed=1))
    assert -4.5 < fe.beta < -1.5 and fe.se_cr1 > 0 and fe.p1_cr1 < 0.05 and fe.n1 > 0


def test_fe_null_effect_not_rejected_with_seed():
    fe = ST.fe_regression(*_panel(0.0, seed=2))
    assert fe.p2_cr1 > 0.01 and 0 <= fe.p1_cr1 <= 1


def test_fe_drops_single_group_days():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    x = np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0])
    day = np.array([0, 0, 1, 1, 2, 2])          # day 1 = 표식 없음 → 제외
    fe = ST.fe_regression(y, x, day, np.array([1, 2, 3, 4, 5, 6]), day)
    assert fe.n_days == 2 and fe.n == 4


def test_fe_single_cluster_returns_nan_se():
    y = np.array([1.0, 0.0, 2.0, 0.0]); x = np.array([1.0, 0.0, 1.0, 0.0])
    fe = ST.fe_regression(y, x, np.array([0, 0, 1, 1]), np.array([7, 7, 7, 7]), np.array([0, 0, 0, 0]))
    assert math.isnan(fe.se_cr1)


def test_mde_and_holm():
    assert abs(ST.mde(1.0) - 2.486) < 1e-3
    assert ST.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dt_dart_filter/stats.py`:
```python
"""날짜 고정효과 + 종목 CR1(+ 2원 클러스터) — 스펙 §3-5.

β = Σx̃ỹ/Σx̃² (x̃·ỹ = 날짜 안 평균 뺀 값 · 표식·대조가 둘 다 있는 날만) · ψ_i = x̃_i(ỹ_i − βx̃_i)/Σx̃².
V_CR1 = G/(G−1)·Σ_g(Σψ)² · 2원 = V_종목 + V_블록 − V_종목×블록(≤0 이면 max). 단측 p 는 δ<0 방향.
CR1 은 정규 근사 · 2원은 t(G_블록−1)(09-26 `stats_binary` 선례).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
import pandas as pd

from . import settings as S


@dataclass(frozen=True)
class FE:
    beta: float
    se_cr1: float
    se_2w: float
    p1_cr1: float
    p2_cr1: float
    p1_2w: float
    p2_2w: float
    n: int
    n1: int
    n_days: int
    g_stock: int
    g_block: int


def _ncdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _cluster_v(psi: pd.Series, keys: pd.Series):
    s = psi.groupby(keys.to_numpy()).sum()
    g = len(s)
    if g < 2:
        return float("nan"), g
    return g / (g - 1) * float((s * s).sum()), g


def fe_regression(y, x, day, stock, block) -> FE:
    df = pd.DataFrame({"y": np.asarray(y, float), "x": np.asarray(x, float), "day": np.asarray(day),
                       "stock": np.asarray(stock).astype(str), "block": np.asarray(block)})
    df = df[np.isfinite(df["y"])]
    g = df.groupby("day")["x"]
    df = df[(g.transform("max") > 0) & (g.transform("min") < 1)]
    nan = float("nan")
    if df.empty:
        return FE(nan, nan, nan, nan, nan, nan, nan, 0, 0, 0, 0, 0)
    xt = df["x"] - df.groupby("day")["x"].transform("mean")
    yt = df["y"] - df.groupby("day")["y"].transform("mean")
    sxx = float((xt * xt).sum())
    beta = float((xt * yt).sum() / sxx)
    psi = xt * (yt - beta * xt) / sxx
    v_s, gs = _cluster_v(psi, df["stock"])
    v_b, gb = _cluster_v(psi, df["block"].astype(str))
    v_sb, _ = _cluster_v(psi, df["stock"] + "|" + df["block"].astype(str))
    v2 = v_s + v_b - v_sb
    if not (v2 > 0):
        v2 = max(v_s, v_b) if not (math.isnan(v_s) or math.isnan(v_b)) else nan
    se1 = math.sqrt(v_s) if v_s == v_s and v_s > 0 else nan
    se2 = math.sqrt(v2) if v2 == v2 and v2 > 0 else nan
    p1c = p2c = p1w = p2w = nan
    if se1 == se1:
        t1 = beta / se1
        p1c, p2c = _ncdf(t1), 2.0 * (1.0 - _ncdf(abs(t1)))
    if se2 == se2 and gb >= 2:
        from scipy.stats import t as tdist
        t2 = beta / se2
        dfree = max(1, gb - 1)
        p1w, p2w = float(tdist.cdf(t2, dfree)), float(2.0 * tdist.sf(abs(t2), dfree))
    return FE(beta, se1, se2, p1c, p2c, p1w, p2w, int(len(df)), int((df["x"] > 0).sum()),
              int(df["day"].nunique()), gs, gb)


def mde(se: float) -> float:
    return (S.Z_ALPHA + S.Z_POWER) * float(se)


def holm(ps: Sequence[float]) -> List[float]:
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj = [0.0] * m
    run = 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * ps[i]))
        adj[i] = round(run, 12)
    return adj
```

- [ ] **Step 4: 통과 확인** → 5 passed

- [ ] **Step 5: Commit** — `# research(dt-dart-filter): 날짜 고정효과 회귀·종목 CR1·2원 클러스터·MDE·Holm + 테스트 5`

---

### Task 8: `gate.py` + `sample.py` — 분석 표본 · 가짜 표식 400 게이트

**Files:**
- Create: `dt_dart_filter/sample.py` · `dt_dart_filter/gate.py` · `dt_dart_filter/tests/test_gate.py`

**Interfaces:**
- Consumes: `stats.fe_regression` · `lots.episode_first`
- Produces:
  - `sample.analysis_frame(led: pd.DataFrame, marks: Set[Tuple[str, date]], cal_idx: Dict[date, int], small_only: bool = True) -> pd.DataFrame`
    - 입력 led: `run.py build` 원장(열 `scan_date(date), stock_code, status, p_L, ret_sl, ret_tp, unresolved, both, halted_in_path, trading_value`)
    - 출력 열: `y_sl, y_tp`(net %p) · `x`(0/1) · `day`(달력 순번) · `stock` · `block` · `quint`(p_L 5분위 1..5) · `scan_date` · `p_L` · `trading_value` · `both` · `halted_in_path` · `ret_sl`
    - 행 = 체결 ∧ (small_only 면 p_L < 0.5) ∧ 에피소드 첫 행
  - `gate.fake_gate(df: pd.DataFrame, n_fake: int = 400, seed: int = SEED) -> Dict[str, Any]`
    - 입력 df = `analysis_frame` 출력
    - 실제 표식 행은 **수익을 읽지 않고 버린다**
    - 반환 키: `rej_cr1, rej_2w, tool("cr1"|"2way"|"fail"), sd_null, mean_se_cr1, n_fake, n_real_marks, n_skipped`

- [ ] **Step 1: 실패하는 테스트**

`dt_dart_filter/tests/test_gate.py`:
```python
from datetime import date, timedelta

import numpy as np
import pandas as pd

from backtest.concept_axes.dt_dart_filter import gate as G
from backtest.concept_axes.dt_dart_filter import sample as SM

DAYS = [date(2022, 1, 3) + timedelta(days=i) for i in range(120)]
CI = {d: i for i, d in enumerate(DAYS)}


def _led(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in DAYS:
        for k in range(25):
            code = f"{rng.integers(0, 600):06d}"
            rows.append(dict(scan_date=d, stock_code=code, status="filled", p_L=float(rng.random() * 0.49),
                             ret_sl=float(rng.normal(0, 8)), ret_tp=0.0, unresolved=False, both=False,
                             halted_in_path=False, trading_value=1e10))
    led = pd.DataFrame(rows).drop_duplicates(["scan_date", "stock_code"])
    led["ret_tp"] = led["ret_sl"]
    return led


def test_analysis_frame_filters_and_marks():
    led = _led()
    led.loc[led.index[0], "status"] = "no_fill"
    led.loc[led.index[1], "p_L"] = 0.9
    mk = {(led.iloc[2]["stock_code"], led.iloc[2]["scan_date"])}
    df = SM.analysis_frame(led, mk, CI)
    assert (df["x"] == 1).sum() == 1 and len(df) <= len(led) - 2
    assert set(df["quint"].unique()) <= {1, 2, 3, 4, 5}
    assert np.allclose(df["y_sl"] + 0.25, df["ret_sl"])


def test_fake_pool_fallback_and_excludes_real_stocks():
    led = _led(1)
    real = led.sample(60, random_state=3)
    mk = set(zip(real["stock_code"], real["scan_date"]))
    df = SM.analysis_frame(led, mk, CI)
    out = G.fake_gate(df, n_fake=20, seed=7)
    assert out["n_real_marks"] == int((df["x"] == 1).sum())
    assert 0.0 <= out["rej_cr1"] <= 1.0 and out["tool"] in ("cr1", "2way", "fail")
    assert out["sd_null"] > 0


def test_fake_gate_deterministic_with_seed():
    led = _led(2)
    mk = set(zip(led["stock_code"].iloc[:40], led["scan_date"].iloc[:40]))
    df = SM.analysis_frame(led, mk, CI)
    assert G.fake_gate(df, n_fake=10, seed=5) == G.fake_gate(df, n_fake=10, seed=5)
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dt_dart_filter/sample.py`:
```python
"""분석 표본 — 스펙 §3-2 · §3-4. 체결 ∧ 대리 소형 ∧ (거른 «뒤») 에피소드 첫 행 · net 수익 = ret − 0.25."""
from __future__ import annotations

from datetime import date
from typing import Dict, Set, Tuple

import numpy as np
import pandas as pd

from . import lots as L
from . import settings as S


def analysis_frame(led: pd.DataFrame, marks: Set[Tuple[str, date]], cal_idx: Dict[date, int],
                   small_only: bool = True) -> pd.DataFrame:
    df = led[led["status"] == "filled"].copy()
    if small_only:
        df = df[df["p_L"].astype(float) < S.PL_CUT]
    df["day"] = [cal_idx[d] for d in df["scan_date"]]
    df = df.sort_values(["stock_code", "day"]).reset_index(drop=True)
    df = df[L.episode_first(df["stock_code"].to_numpy(), df["day"].to_numpy())].reset_index(drop=True)
    df["x"] = [1 if (c, d) in marks else 0 for c, d in zip(df["stock_code"], df["scan_date"])]
    df["y_sl"] = df["ret_sl"].astype(float) - S.COST_PCT
    df["y_tp"] = df["ret_tp"].astype(float) - S.COST_PCT
    df["stock"] = df["stock_code"].astype(str)
    df["block"] = df["day"] // S.BLOCK_TD
    q = pd.qcut(df["p_L"].astype(float).rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    df["quint"] = np.asarray(q, dtype=int)
    return df
```

`dt_dart_filter/gate.py`:
```python
"""가짜 표식 게이트 — 스펙 §3-5.

실제 표식 행은 버리고(수익을 읽지 않음) 남은 표본에서 실제 표식마다 같은 날·같은 p_L 5분위 후보에 가짜 표식을 붙인다
(같은 실제 종목 → 같은 가짜 종목 대응 · 실제 표식 종목은 풀에서 제외 · 풀 없으면 같은 날 아무 분위 · 그래도 없으면 건너뜀).
양측 p<0.10 거부율이 [0.07, 0.13] 이면 그 도구를 쓴다(CR1 우선 → 2원 → 둘 다 탈락이면 «판정 불가»).
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from . import settings as S
from . import stats as ST


def fake_gate(df: pd.DataFrame, n_fake: int = S.N_FAKE, seed: int = S.SEED) -> Dict[str, Any]:
    real = df[df["x"] == 1][["day", "quint", "stock"]]
    base = df[df["x"] == 0].reset_index(drop=True)
    real_stocks = set(real["stock"])
    pool = base[~base["stock"].isin(real_stocks)]
    by_dq = {k: v.to_numpy() for k, v in pool.groupby(["day", "quint"]).groups.items()}
    by_d = {k: v.to_numpy() for k, v in pool.groupby("day").groups.items()}
    by_sd = {k: int(v[0]) for k, v in pool.groupby(["stock", "day"]).groups.items()}
    rej1 = rej2 = 0
    betas, ses = [], []
    skipped = 0
    for i in range(n_fake):
        rng = np.random.default_rng([seed, 7, i])
        mp: Dict[str, str] = {}
        chosen = set()
        for r in real.itertuples(index=False):
            h = mp.get(r.stock)
            idx = by_sd.get((h, r.day)) if h is not None else None
            if idx is None:
                cand = by_dq.get((r.day, r.quint))
                if cand is None or not len(cand):
                    cand = by_d.get(r.day)
                if cand is None or not len(cand):
                    skipped += 1
                    continue
                idx = int(cand[rng.integers(len(cand))])
                mp[r.stock] = str(base.at[idx, "stock"])
            chosen.add(idx)
        x = np.zeros(len(base))
        x[list(chosen)] = 1.0
        fe = ST.fe_regression(base["y_sl"].to_numpy(), x, base["day"].to_numpy(), base["stock"].to_numpy(),
                              base["block"].to_numpy())
        rej1 += int(fe.p2_cr1 < S.FAKE_P)
        rej2 += int(fe.p2_2w < S.FAKE_P)
        betas.append(fe.beta)
        ses.append(fe.se_cr1)
    r1, r2 = rej1 / n_fake, rej2 / n_fake
    tool = "cr1" if S.FAKE_LO <= r1 <= S.FAKE_HI else ("2way" if S.FAKE_LO <= r2 <= S.FAKE_HI else "fail")
    return {"rej_cr1": r1, "rej_2w": r2, "tool": tool, "sd_null": float(np.std(betas, ddof=1)),
            "mean_se_cr1": float(np.nanmean(ses)), "n_fake": n_fake, "n_real_marks": int(len(real)),
            "n_skipped": skipped}
```

- [ ] **Step 4: 통과 확인** → 3 passed

- [ ] **Step 5: Commit** — `# research(dt-dart-filter): 분석 표본(체결∧대리 소형∧첫 행·net)·가짜 표식 400 게이트(실제 표식 행 제외·종목 대응·풀 폴백) + 테스트 3`

---

### Task 9: `run.py` — 단계 러너 · 동결 가드 · 라벨 규칙

**Files:**
- Create: `dt_dart_filter/run.py` · `dt_dart_filter/tests/test_run.py`

**Interfaces:**
- Consumes: Task 2~8 전부 · `candidate_ledger.run.{_connect, build_book, load_bad_open, Env}` · `replayer.loader.{load_prices, load_trading_calendar, db_fingerprint}`
- Produces:
  - CLI `--stage proxy | check-backfill | build | seal | open`(`--backfill-dir` 는 check-backfill 용)
  - `run.label(fe_sl, fe_tp, tool, n1, surv_i, surv_ii) -> str`
  - `run.require_frozen() -> None` — 비었거나 불일치면 SystemExit
  - 산출물 `results/`:

    | 단계 | 파일 |
    |---|---|
    | proxy | `proxy_coef.json` · `proxy_report.md` |
    | check-backfill | `backfill_check.json` |
    | build | `ledger_A.csv` · `marks_lag0.csv` · `marks_w5.csv` · `marks_w20.csv` · `build_meta.json` |
    | seal | `seal.json` · `sealed_report.md` |
    | open | `open.json` · `RESULTS_<날짜>.md` |

- [ ] **Step 1: 실패하는 테스트**

`dt_dart_filter/tests/test_run.py`:
```python
import pytest

from backtest.concept_axes.dt_dart_filter import run as RUN
from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter.stats import FE


def _fe(beta, p1, p2):
    return FE(beta, 1.0, 1.0, p1, p2, p1, p2, 500, 120, 300, 200, 40)


def test_label_present_requires_both_rules_threshold_and_survivorship():
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.03, 0.06), "cr1", 120, 0.3, 0.1) == "있음(−)"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.20, 0.40), "cr1", 120, 0.3, 0.1) == "판별 보류"
    assert RUN.label(_fe(-0.3, 0.01, 0.02), _fe(-0.3, 0.01, 0.02), "cr1", 120, 0.3, 0.1) == "판별 보류"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.01, 0.02), "cr1", 120, 0.05, 0.1) == "판별 보류"


def test_label_reverse_tool_fail_and_small_n():
    assert RUN.label(_fe(1.2, 0.99, 0.01), _fe(1.2, 0.99, 0.01), "cr1", 120, 0.3, 0.1) == "역방향"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-1.0, 0.01, 0.02), "fail", 120, 0.3, 0.1) == "판정 불가(도구)"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-1.0, 0.01, 0.02), "cr1", 99, 0.3, 0.1) == "판별 보류(n₁<100)"


def test_require_frozen_refuses_when_blob_empty(monkeypatch):
    monkeypatch.setattr(S, "PREREG_FROZEN_BLOB", "")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_open_refuses_without_frozen(monkeypatch):
    monkeypatch.setattr(S, "PREREG_FROZEN_BLOB", "")
    with pytest.raises(SystemExit):
        RUN.main(["--stage", "open"])
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dt_dart_filter/run.py`:
```python
"""A 러너 — 규범 = 스펙 §3 · `PREREG.md`. 문서와 어긋나면 코드가 틀린 것이다.

    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage proxy
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage check-backfill --backfill-dir <dir>
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage build      # 동결 뒤
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage seal       # build 뒤 · 표식 행 수익 안 읽음
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage open       # sealed_report 커밋 뒤 1회

🔴 DB SELECT 전용(`candidate_ledger.run` import 가 bootstrap read-only 를 건다) · 실제 표식×수익 결합 = open 단계뿐.
"""
from __future__ import annotations

from backtest.concept_axes.candidate_ledger import run as R   # noqa: E402  bootstrap(read-only) 포함

import argparse                                               # noqa: E402
import hashlib                                                # noqa: E402
import json                                                   # noqa: E402
import subprocess                                             # noqa: E402
import sys                                                    # noqa: E402
from datetime import date, datetime                           # noqa: E402
from pathlib import Path                                      # noqa: E402
from typing import Any, Dict, List, Optional, Sequence        # noqa: E402

import numpy as np                                            # noqa: E402
import pandas as pd                                           # noqa: E402

from backtest.concept_axes.replayer import loader as LD       # noqa: E402

from . import daycheck as DC                                  # noqa: E402
from . import gate as G                                       # noqa: E402
from . import lots as L                                       # noqa: E402
from . import proxy as P                                      # noqa: E402
from . import sample as SM                                    # noqa: E402
from . import settings as S                                   # noqa: E402
from . import stats as ST                                     # noqa: E402
from . import tags as T                                       # noqa: E402
from . import universe as U                                   # noqa: E402

LEDGER_COLS = ["scan_date", "stock_code", "rank", "score", "n_passed", "market_cap", "trading_value", "tv20",
               "close", "p_L", "status", "fill", "entry_date", "entry_price", "exit_date", "exit_reason",
               "hold_days", "ret_sl", "ret_tp", "both", "unresolved", "halted_in_path", "flags"]


# ── git · 해시 가드 ─────────────────────────────────────────────────────────────
def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=S.PKG, capture_output=True, text=True)


def head_sha() -> str:
    return _git("rev-parse", "HEAD").stdout.strip()


def clean_package() -> bool:
    return _git("status", "--porcelain", "--", str(S.PKG)).stdout.strip() == ""


def blob(path: Path) -> str:
    return _git("hash-object", str(path)).stdout.strip()


def committed_unchanged(path: Path) -> bool:
    return (_git("ls-files", "--error-unmatch", str(path)).returncode == 0
            and _git("diff", "--quiet", "HEAD", "--", str(path)).returncode == 0)


def md5(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def require_frozen() -> None:
    if not S.PREREG_FROZEN_BLOB:
        raise SystemExit("🔴 PREREG_FROZEN_BLOB 비어 있음 — 사전등록 동결(Task 12) 전에는 실행 금지")
    if not S.PREREG.exists() or blob(S.PREREG) != S.PREREG_FROZEN_BLOB:
        raise SystemExit("🔴 PREREG.md blob 이 동결값과 다르다 — 중단")
    if not clean_package():
        raise SystemExit("🔴 패키지에 커밋 안 된 변경이 있다 — 중단")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    tmp.replace(path)


# ── 라벨 규칙(스펙 §3-7) ────────────────────────────────────────────────────────
def label(fe_sl: ST.FE, fe_tp: ST.FE, tool: str, n1: int, surv_i: float, surv_ii: float) -> str:
    if tool == "fail":
        return "판정 불가(도구)"
    if n1 < S.N1_MIN:
        return "판별 보류(n₁<100)"
    p1 = (lambda f: f.p1_cr1) if tool == "cr1" else (lambda f: f.p1_2w)
    p2 = (lambda f: f.p2_cr1) if tool == "cr1" else (lambda f: f.p2_2w)
    if p2(fe_sl) < 0.05 and fe_sl.beta > 0:
        return "역방향"
    if p1(fe_sl) < S.ALPHA and p1(fe_tp) < S.ALPHA and fe_sl.beta <= S.DELTA_MAX and surv_i >= surv_ii:
        return "있음(−)"
    return "판별 보류"


# ── 단계: proxy(이미 본 구간 · 시총 있는 후보로 대리 적합) ────────────────────────
def stage_proxy(conn) -> None:
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, S.FIT_PX_START, S.FIT_END.isoformat())]
    days = [pd.Timestamp(d) for d in cal if S.FIT_START <= d <= S.FIT_END]
    px = LD.load_prices(conn, S.FIT_PX_START, S.FIT_END.isoformat())
    rows, diag = U.scan_window(px, days)
    feat = P.add_proxy_features(px).set_index(["stock_code", "date"])
    c = pd.DataFrame(rows)
    c = c[c["market_cap"].astype(float) > 0].copy()
    key = list(zip(c["stock_code"], pd.to_datetime(c["scan_date"])))
    c["x1"] = feat["x1"].reindex(key).to_numpy()
    c["x2"] = feat["x2"].reindex(key).to_numpy()
    c = c.dropna(subset=["x1", "x2"])
    y = (c["market_cap"].astype(float) >= S.LARGE_CAP).to_numpy(float)
    X = P.design(c["x1"], c["x2"])
    beta = P.fit_logistic(X, y)
    s = P.predict(beta, X)
    years = pd.to_datetime(c["scan_date"]).dt.year.to_numpy()
    by_year = {int(yv): P.auc(y[years == yv], s[years == yv]) for yv in sorted(set(years))}
    out = dict(beta=[float(b) for b in beta], features="x1=log(20봉 평균 close×adj volume, D 포함) · x2=log(close D)",
               fit_window=[S.FIT_START.isoformat(), S.FIT_END.isoformat()], n=int(len(c)), n_large=int(y.sum()),
               auc=P.auc(y, s), auc_by_year=by_year, acc_at_cut=float(((s >= S.PL_CUT) == (y > 0)).mean()),
               scan_diag=diag, git_sha=head_sha())
    _write(S.RESULTS / "proxy_coef.json", json.dumps(out, ensure_ascii=False, indent=1))
    _write(S.RESULTS / "proxy_report.md", "\n".join([
        "# 시총 대리 적합 — 이미 본 구간(2024-03-13~2026-09-23) · 결과(수익) 무관", "",
        f"- n {out['n']:,} · 대형 {out['n_large']:,} · AUC {out['auc']:.3f} · p≥0.5 정확도 {out['acc_at_cut']:.3f}",
        f"- 연도별 AUC {', '.join(f'{k} {v:.3f}' for k, v in by_year.items())}",
        f"- 계수 (상수, x1, x2) = {', '.join(f'{b:.6f}' for b in out['beta'])}", ""]))
    print(json.dumps(out, ensure_ascii=False, indent=1))


# ── 단계: check-backfill ────────────────────────────────────────────────────────
def stage_check_backfill(conn, backfill_dir: Path) -> int:
    rep = DC.check(conn, backfill_dir, S.FILING_START, S.SCAN_END, ("A", "B", "I"))
    rep.update(window=[S.FILING_START.isoformat(), S.SCAN_END.isoformat()], types=["A", "B", "I"],
               backfill_dir=str(backfill_dir), git_sha=head_sha())
    _write(S.RESULTS / "backfill_check.json", json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"칸 {rep['n_cells']:,} · 미완결 {rep['n_bad']}")
    return 0 if rep["complete"] else 1


# ── 단계: build(동결 뒤) ────────────────────────────────────────────────────────
def _load_env(conn):
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, S.PX_START, S.PATH_END)]
    px = LD.load_prices(conn, S.PX_START, S.PATH_END)
    env = R.Env(cal=cal, book=R.build_book(px), uni={}, excl={}, imp_dates={}, corp_dates={},
                bad_open=R.load_bad_open(conn, S.PX_START, S.PATH_END), minute_fn=lambda pairs: set(),
                path_end=date.fromisoformat(S.PATH_END))
    return cal, px, env


def stage_build(conn) -> None:
    require_frozen()
    chk = json.loads((S.RESULTS / "backfill_check.json").read_text(encoding="utf-8"))
    if not chk.get("complete") or not committed_unchanged(S.RESULTS / "backfill_check.json"):
        raise SystemExit("🔴 백필 완결 보고가 없거나 미완결·미커밋 — 중단")
    coef = json.loads((S.RESULTS / "proxy_coef.json").read_text(encoding="utf-8"))
    cal, px, env = _load_env(conn)
    days = [pd.Timestamp(d) for d in cal if S.SCAN_START <= d <= S.SCAN_END]
    rows, diag = U.scan_window(px, days)
    feat = P.add_proxy_features(px).set_index(["stock_code", "date"])
    halts = L.halt_dates(px)
    out: List[Dict[str, Any]] = []
    for r in rows:
        k = (r["stock_code"], pd.Timestamp(r["scan_date"]))
        x1 = float(feat["x1"].get(k, np.nan))
        x2 = float(feat["x2"].get(k, np.nan))
        pl = float(P.predict(np.array(coef["beta"]), P.design([x1], [x2]))[0]) if np.isfinite(x1 + x2) else np.nan
        sim = L.simulate_candidate(env, r["stock_code"], r["scan_date"], halts.get(r["stock_code"], set()))
        out.append({**r, "tv20": float(feat["tv20"].get(k, np.nan)), "close": float(feat["close"].get(k, np.nan)),
                    "p_L": pl, **{kk: sim.get(kk) for kk in LEDGER_COLS if kk in sim}})
    led = pd.DataFrame(out).reindex(columns=LEDGER_COLS)
    S.RESULTS.mkdir(parents=True, exist_ok=True)
    led.to_csv(S.RESULTS / "ledger_A.csv", index=False, lineterminator="\n")
    fil = T.load_filings(conn, S.FILING_START, S.SCAN_END)
    scan_cal = [d for d in cal if d <= S.SCAN_END]
    for name, back in (("lag0", 0), ("w5", 4), ("w20", 19)):
        mk = sorted(T.window_marks(fil, scan_cal, back))
        pd.DataFrame(mk, columns=["stock_code", "scan_date"]).to_csv(S.RESULTS / f"marks_{name}.csv", index=False,
                                                                     lineterminator="\n")
    fp = LD.db_fingerprint(conn, S.PX_START, S.PATH_END)
    meta = dict(git_sha=head_sha(), db_fingerprint=fp["sha256"], scan_diag=diag, n_rows=len(led),
                n_filings=len(fil), md5={p.name: md5(p) for p in sorted(S.RESULTS.glob("*.csv"))},
                finished=datetime.now().isoformat(timespec="seconds"))
    _write(S.RESULTS / "build_meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"원장 {len(led):,}행 · 공시 {len(fil):,} · 지문 {fp['sha256'][:12]}")


def _check_build(conn) -> Dict[str, Any]:
    meta = json.loads((S.RESULTS / "build_meta.json").read_text(encoding="utf-8"))
    for name, h in meta["md5"].items():
        if md5(S.RESULTS / name) != h:
            raise SystemExit(f"🔴 {name} md5 불일치 — 중단")
    if LD.db_fingerprint(conn, S.PX_START, S.PATH_END)["sha256"] != meta["db_fingerprint"]:
        raise SystemExit("🔴 daily_prices 지문이 build 때와 다르다(소급 수정) — 중단")
    return meta


def _read_marks(name: str):
    m = pd.read_csv(S.RESULTS / f"marks_{name}.csv", dtype={"stock_code": str})
    return {(c, date.fromisoformat(d)) for c, d in zip(m["stock_code"], m["scan_date"])}


def _read_ledger() -> pd.DataFrame:
    led = pd.read_csv(S.RESULTS / "ledger_A.csv", dtype={"stock_code": str})
    led["scan_date"] = [date.fromisoformat(str(d)[:10]) for d in led["scan_date"]]
    for c in ("both", "unresolved", "halted_in_path"):          # CSV 의 "True"/"False"/빈칸 → bool (문자열 astype(bool) 함정)
        led[c] = led[c].astype(str).str.strip().str.lower().eq("true")
    return led


def _survivorship(conn, px_keys) -> Dict[str, float]:
    fil = T.load_filings_typed(conn, S.SCAN_START, S.SCAN_END)
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, S.PX_START, S.PATH_END)]
    import bisect

    def miss(rows):
        n = m = 0
        for c, d, _nm, _t in rows:
            j = bisect.bisect_left(cal, d)
            if j >= len(cal):
                continue
            n += 1
            m += int((c, cal[j]) not in px_keys)
        return (m / n if n else float("nan")), n
    tagged = [r for r in fil if T.is_lag0_tag(r[2])]
    periodic = [r for r in fil if r[3] == "A" and "정정" not in r[2]]
    si, ni = miss(tagged)
    sii, nii = miss(periodic)
    return {"surv_i": si, "n_i": ni, "surv_ii": sii, "n_ii": nii}


# ── 단계: seal(표식 행 수익 안 읽음) ───────────────────────────────────────────
def stage_seal(conn) -> None:
    require_frozen()
    _check_build(conn)
    cal, px, _env = _load_env(conn)
    cal_idx = {d: i for i, d in enumerate(cal)}
    led = _read_ledger()
    df = SM.analysis_frame(led, _read_marks("lag0"), cal_idx)
    gate = G.fake_gate(df)
    ctrl = df[df["x"] == 0]
    keys = set(zip(px["stock_code"].astype(str), [pd.Timestamp(t).date() for t in px["date"]]))
    surv = _survivorship(conn, keys)
    n1 = int((df["x"] == 1).sum())
    years = pd.Series([d.year for d in df["scan_date"]])
    seal = dict(n1=n1, n0=int(len(ctrl)), sd_ctrl_sl=float(ctrl["y_sl"].std(ddof=1)),
                sd_ctrl_tp=float(ctrl["y_tp"].std(ddof=1)), gate=gate,
                mde_null=ST.mde(gate["sd_null"]), mde_se=ST.mde(gate["mean_se_cr1"]),
                n1_by_year={int(y): int(((years == y) & (df["x"] == 1)).sum()) for y in sorted(years.unique())},
                surv=surv, git_sha=head_sha(), sealed=datetime.now().isoformat(timespec="seconds"))
    _write(S.RESULTS / "seal.json", json.dumps(seal, ensure_ascii=False, indent=1))
    _write(S.RESULTS / "sealed_report.md", "\n".join([
        "# 봉인 보고서 — 표식×수익 결합 0 (스펙 §3-6)", "",
        f"- n₁(lag0 표식) {n1:,} · 대조 {len(ctrl):,} · 연도별 n₁ {seal['n1_by_year']}",
        f"- SD(대조 · net) 손절 우선 {seal['sd_ctrl_sl']:.3f} · 익절 우선 {seal['sd_ctrl_tp']:.3f}",
        f"- 가짜 게이트: CR1 거부율 {gate['rej_cr1']:.3f} · 2원 {gate['rej_2w']:.3f} → 도구 **{gate['tool']}** "
        f"(n_fake {gate['n_fake']} · 건너뜀 {gate['n_skipped']})",
        f"- SD_null {gate['sd_null']:.3f} → MDE {seal['mde_null']:.3f}%p (평균 SE 기준 {seal['mde_se']:.3f}%p)",
        f"- 생존자 누락률 (i) 3태그 {surv['surv_i']:.4f}(n {surv['n_i']:,}) · (ii) 정기공시 {surv['surv_ii']:.4f}"
        f"(n {surv['n_ii']:,})", ""]))
    print(json.dumps(seal, ensure_ascii=False, indent=1, default=str))


# ── 단계: open(1회) ──────────────────────────────────────────────────────────────
def stage_open(conn) -> None:
    require_frozen()
    if (S.RESULTS / "open.json").exists():
        raise SystemExit("🔴 이미 개봉됨(open.json 있음) — 1회만 허용")
    if not committed_unchanged(S.RESULTS / "sealed_report.md"):
        raise SystemExit("🔴 sealed_report.md 가 커밋돼 있지 않거나 바뀌었다 — 중단")
    _check_build(conn)
    seal = json.loads((S.RESULTS / "seal.json").read_text(encoding="utf-8"))
    cal, _px, _env = _load_env(conn)
    cal_idx = {d: i for i, d in enumerate(cal)}
    led = _read_ledger()
    df = SM.analysis_frame(led, _read_marks("lag0"), cal_idx)

    def fe(d, col, key="day"):
        return ST.fe_regression(d[col].to_numpy(), d["x"].to_numpy(), d[key].to_numpy(), d["stock"].to_numpy(),
                                d["block"].to_numpy())
    fe_sl, fe_tp = fe(df, "y_sl"), fe(df, "y_tp")
    tool = seal["gate"]["tool"]
    lab = label(fe_sl, fe_tp, tool, int(seal["n1"]), seal["surv"]["surv_i"], seal["surv"]["surv_ii"])
    lines = ["# RESULTS — 공시 재료 다음날 추격 금지(lag0) 확인 검정", "",
             f"## 주 라벨: **{lab}**", "",
             f"- 도구 {tool} · n {fe_sl.n:,} · n₁ {fe_sl.n1:,} · 날 {fe_sl.n_days:,}",
             f"- 손절 우선 δ̂ {fe_sl.beta:+.3f}%p (SE CR1 {fe_sl.se_cr1:.3f} · 단측 p {fe_sl.p1_cr1:.4f} · "
             f"2원 SE {fe_sl.se_2w:.3f} · 단측 p {fe_sl.p1_2w:.4f})",
             f"- 익절 우선 δ̂ {fe_tp.beta:+.3f}%p (단측 p CR1 {fe_tp.p1_cr1:.4f} · 2원 {fe_tp.p1_2w:.4f})",
             f"- 생존자 누락률 (i) {seal['surv']['surv_i']:.4f} vs (ii) {seal['surv']['surv_ii']:.4f}", "",
             "## 보조(인쇄만 · 라벨 불변)", ""]
    sec: Dict[str, Any] = {}
    for name in ("w5", "w20"):
        d2 = SM.analysis_frame(led, _read_marks(name), cal_idx)
        f2 = fe(d2, "y_sl")
        sec[name] = f2.__dict__
        lines.append(f"- {name}: δ̂ {f2.beta:+.3f} · n₁ {f2.n1} · 단측 p {f2.p1_cr1:.4f}")
    big = SM.analysis_frame(led, _read_marks("lag0"), cal_idx, small_only=False)
    big["key"] = big["day"].astype(str) + "|" + pd.qcut(big["p_L"].rank(method="first"), 3, labels=False).astype(str)
    fb = fe(big, "y_sl", key="key")
    sec["all_sizes"] = fb.__dict__
    lines.append(f"- 대형 포함 전체(날짜×대리 3분위 FE): δ̂ {fb.beta:+.3f} · n₁ {fb.n1} · 단측 p {fb.p1_cr1:.4f}")
    for y in sorted({d.year for d in df["scan_date"]}):
        dy = df[[d.year == y for d in df["scan_date"]]]
        fy = fe(dy, "y_sl")
        lines.append(f"- {y}: δ̂ {fy.beta:+.3f} · n₁ {fy.n1}")
    tv_t = pd.qcut(df["trading_value"].rank(method="first"), 3, labels=False)
    for t in range(3):
        ft = fe(df[tv_t == t], "y_sl")
        lines.append(f"- 거래대금 3분위 {t + 1}: δ̂ {ft.beta:+.3f} · n₁ {ft.n1}")
    for arm, sub in (("표식", df[df["x"] == 1]), ("대조", df[df["x"] == 0])):
        lines.append(f"- {arm}: 정지 낀 비율 {sub['halted_in_path'].astype(bool).mean():.4f} · "
                     f"ret ≤ −15% {(sub['ret_sl'] <= S.TAIL_LOSS).mean():.4f} · 동시 터치 {sub['both'].astype(bool).mean():.4f}")
    if lab == "있음(−)":
        lines.append("- 태그별 Holm m=3(주 검정 통과 뒤에만 해석) — 별도 표식 파일 없이 공시를 다시 읽어 계산")
    today = date.today().isoformat()
    _write(S.RESULTS / f"RESULTS_{today}.md", "\n".join(lines) + "\n")
    _write(S.RESULTS / "open.json", json.dumps(dict(label=lab, fe_sl=fe_sl.__dict__, fe_tp=fe_tp.__dict__,
                                                    secondary=sec, opened=datetime.now().isoformat(timespec="seconds"),
                                                    git_sha=head_sha()), ensure_ascii=False, indent=1, default=str))
    print("\n".join(lines))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="dt_dart_filter A 러너")
    ap.add_argument("--stage", required=True, choices=["proxy", "check-backfill", "build", "seal", "open"])
    ap.add_argument("--backfill-dir", default=None)
    a = ap.parse_args(argv)
    if a.stage in ("build", "seal", "open"):
        require_frozen()
    conn = R._connect()
    try:
        if a.stage == "proxy":
            stage_proxy(conn)
        elif a.stage == "check-backfill":
            if not a.backfill_dir:
                raise SystemExit("--backfill-dir 필요")
            return stage_check_backfill(conn, Path(a.backfill_dir))
        elif a.stage == "build":
            stage_build(conn)
        elif a.stage == "seal":
            stage_seal(conn)
        else:
            stage_open(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> 태그별 Holm 줄은 주 라벨이 「있음(−)」일 때만 인쇄 안내를 한다. 실제 태그별 계산은 Task 13 의 verifier 가 같은 표본에서 공시를 태그별로 다시 나눠 수행한다(사전등록 §「보조」 문장 그대로).

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/dt_dart_filter/tests -q` → 전부 passed(Task 2~9 누계 33)

- [ ] **Step 5: lint**

Run: `cd D:/tmp/kis-wt-dt-dart-filter/RoboTrader_template && $PY -m ruff check backtest/concept_axes/dt_dart_filter`
Expected: All checks passed. (ruff 가 venv 에 없으면 `$PY -m pyflakes` 로 대체하고 보고)

- [ ] **Step 6: Commit** — `# research(dt-dart-filter): 단계 러너(proxy·check-backfill·build·seal·open) · 동결 가드 · 라벨 규칙 · 1회 개봉 + 테스트 4`

---

### Task 10: 시총 대리 적합 실행(이미 본 구간 · DB SELECT)

**Files:**
- Create(출력): `dt_dart_filter/results/proxy_coef.json` · `dt_dart_filter/results/proxy_report.md`

- [ ] **Step 1: 실행**

```bash
cd D:/tmp/kis-wt-dt-dart-filter/RoboTrader_template
$PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage proxy
```
Expected: 아래 수치가 인쇄된다.
- n 약 2만
- AUC ≥ 0.90(퀀트 고수 적합 0.927 근처)
- 연도별 AUC 3개

- [ ] **Step 2: 판정**
- AUC < 0.85 면 멈추고 보고한다(대리가 시총을 못 가른다 = 스펙 §3-2 전제 붕괴).
- 계수 부호 기대: x1(+) · x2(+).

- [ ] **Step 3: Commit** — `# research(dt-dart-filter): 시총 대리 적합 결과(이미 본 구간 · 수익 무관 · AUC <값>)`

---

### Task 11: DART 공시 백필 2021-01-01~2024-03-12(A·B·I) + 완결 점검

**Files:**
- Create(출력): `dt_dart_filter/results/backfill_check.json`
- 원자료(커밋 안 함): `D:/research-archive/dt_dart_backfill_2021_2024/`

- [ ] **Step 1: 사전 점검**
- 실행 시각이 08:25~08:35 · 15:50~16:15 가 아닌지 본다.
- LLM shadow 잠금이 비어 있는지 본다: `%LOCALAPPDATA%/kis-llm-shadow/runner.lock` 이 다른 프로세스에 잡혀 있지 않은지 확인.
- 전후 기록: LLM shadow 이름 폴백 영향 종목 수를 SELECT 해 남긴다(스펙 §3-1).

```sql
-- 덧붙이기 «전» 기록(SELECT)
SELECT count(*) FROM (SELECT DISTINCT stock_code FROM dart_disclosures WHERE stock_code IS NOT NULL) a
WHERE stock_code NOT IN (SELECT stock_code FROM dart_disclosures WHERE rcept_dt >= '2024-03-13' AND stock_code IS NOT NULL);
```

- [ ] **Step 2: 연도별 백필(쓰기 프로세스 · bootstrap 미사용)**

```bash
cd D:/tmp/kis-wt-dt-dart-filter/RoboTrader_template
OUT=D:/research-archive/dt_dart_backfill_2021_2024
$PY -X utf8 scripts/dart_disclosure_backfill.py --bgn 2021-01-01 --end 2021-12-31 --types A,B,I --limit-calls 5000 --out $OUT --resume
$PY -X utf8 scripts/dart_disclosure_backfill.py --bgn 2022-01-01 --end 2022-12-31 --types A,B,I --limit-calls 5000 --out $OUT --resume
$PY -X utf8 scripts/dart_disclosure_backfill.py --bgn 2023-01-01 --end 2023-12-31 --types A,B,I --limit-calls 5000 --out $OUT --resume
$PY -X utf8 scripts/dart_disclosure_backfill.py --bgn 2024-01-01 --end 2024-03-12 --types A,B,I --limit-calls 5000 --out $OUT --resume
```
- 각 실행 뒤 `$OUT/summary.json` 의 calls·warnings 를 기록한다.
- 네트워크 예외로 멈추면 같은 명령으로 `--resume` 한다.
- 강제 종료로 `$OUT/.lock` 이 남으면 PID 가 죽었는지 `Get-Process -Id` 로 확인한 뒤에만 지운다.

- [ ] **Step 3: 완결 점검**

```bash
$PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage check-backfill --backfill-dir D:/research-archive/dt_dart_backfill_2021_2024
```
Expected: `미완결 0` · exit 0.
- 미완결이면 그 날짜만 `--bgn/--end` 로 다시 받고 재점검한다.

- [ ] **Step 4: 전후 기록**
- Step 1 SELECT 를 다시 실행한다.
- 차이와 call 수 합계를 `results/backfill_check.json` 옆 `backfill_notes.md` 에 3줄로 남긴다.

- [ ] **Step 5: Commit** — `# research(dt-dart-filter): DART 공시 백필 2021-01~2024-03(A·B·I) 완결 점검 — 미완결 0 · 호출 <n> · 이름 폴백 영향 <전→후>`

---

### Task 12: 사전등록 `PREREG.md` 초안 → critic → 🔒 사장님 동결 → REGISTRY 등재

**Files:**
- Create: `dt_dart_filter/PREREG.md`
- Modify: `dt_dart_filter/settings.py`(`PREREG_FROZEN_BLOB`)
- Modify: `RoboTrader_template/backtest/concept_axes/REGISTRY.md`(행 1개 + 총계)

- [ ] **Step 1: 초안 작성** — 아래 절을 빠짐없이(값은 `settings.py`·스펙 그대로):

| 절 | 내용 |
|---|---|
| §0 | 사장님 결정 원문(스펙 §0 표) · 09-24 결정 이 건 면제 문장 |
| §1 | 가설 「돌파일 당일 3태그 원공시 후보의 net 수익 < 같은 날 다른 후보」 · 단측 |
| §2 | 표본(스캔 창 · 시총 조건만 뺀 룰 · 대리 계수 `results/proxy_coef.json` md5 · p_L<0.5 · 체결 규칙 · 필터 «뒤» 에피소드 첫 행) |
| §3 | 표식(lag0 정의 · 태그 3 · 정정/자회사/경영권분쟁 제외 · 공시 창) |
| §4 | 결과(체결·청산·정지·두 규칙·비용) |
| §5 | 통계(날짜 FE · CR1/2원 · 가짜 게이트 400 · 도구 선택 순서) |
| §6 | 봉인 보고서 항목(n₁·SD·SD_null·MDE·누락률) |
| §7 | 라벨 문장(스펙 §3-7) · 보조 인쇄 목록(스펙 §3-8) |
| §8 | 통과 시 L-1~L-4(스펙 §3-9) — 이 사전등록의 판정이 아니라 다음 결정의 조건 |
| §9 | 한계(스펙 §7) |
| §10 | **동결 전 본 것** — 스펙 §5 목록 4개 + Task 10 대리 적합 결과 + Task 11 백필 건수(수익 결합 0) |
| §11 | 입력 고정 — `backfill_check.json` md5 · `proxy_coef.json` md5 · 코드 커밋 SHA |

- [ ] **Step 2: critic 1패스**
- `oh-my-claudecode:critic`(opus)에 PREREG.md 와 스펙을 준다.
- 「결과 엿보기 경로」·「자유도」·「라벨 문장 모호성」을 검토시킨다.
- 블로커는 반영하고 재검토한다.

- [ ] **Step 3: 🔒 사장님 동결 확인** — B 사전등록과 **한 번에 묶어** 요청한다(스펙 §6).
- 쉬운 한 장 먼저: 무엇을 재나 · 언제 · 통과하면.
- 그다음 AskUserQuestion「동결 커밋할까요」.

- [ ] **Step 4: 동결 커밋 → blob 고정 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/dt_dart_filter/PREREG.md
git commit -F <메시지 파일>   # docs(prereg): dt-dart-filter A 사전등록 동결 — lag0 확인 검정(🔒 사장님 <날짜> 「…」)
git hash-object RoboTrader_template/backtest/concept_axes/dt_dart_filter/PREREG.md   # → settings.PREREG_FROZEN_BLOB
# settings.py 의 PREREG_FROZEN_BLOB = "<blob>" 로 고친 뒤
git add RoboTrader_template/backtest/concept_axes/dt_dart_filter/settings.py
git commit -F <메시지 파일>   # research(dt-dart-filter): PREREG_FROZEN_BLOB 고정(<blob 앞 7>)
```

- [ ] **Step 5: REGISTRY 등재**
- 행 형식은 NW1 행과 같다: `| **DF1** | [PREREG](dt_dart_filter/PREREG.md) | daytrading_3methods_breakout | 공시 재료 다음날 추격 금지(lag0) | ⚪ 인쇄만: W5·W20·태그별·대형 포함·연도별 | **1** | ✅ 동결 <날짜> · <SHA> |`
- 총계 줄은 «한 push 안 연속 마지막 커밋»에서 갱신한다(규칙 3 · 동결 SHA 열거).
- 🔴 TN1·SR1·테마 층·B(DF2)와 총계 충돌 → 나중에 머지되는 쪽이 다시 센다.

---

### Task 13: 🔒 동결 뒤 build → seal → 봉인 커밋 → open 1회 → verifier

- [ ] **Step 1: build**

```bash
$PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage build
```
Expected:
- 원장 약 3.5만 행(퀀트 추정 34,735 근처).
- 공시 건수와 지문이 인쇄된다.
- 행 수가 2만 미만 또는 5만 초과면 멈추고 보고한다.

- [ ] **Step 2: seal** — `--stage seal` → `sealed_report.md` 를 읽고 아래를 확인한다.
  - n₁ ≥ 100 인지
  - 도구가 `fail` 이 아닌지
  - MDE 를 기록한다

  도구가 `fail` 이면 개봉해도 라벨은 「판정 불가(도구)」다. 사장님께 보고하고 개봉 여부를 묻는다.

- [ ] **Step 3: 봉인 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/dt_dart_filter/results
git commit -F <메시지 파일>   # research(dt-dart-filter): 봉인 — 원장·표식·봉인 보고서(n₁ <n> · 도구 <tool> · MDE <x>%p · 표식×수익 결합 0)
```

- [ ] **Step 4: open 1회** — `--stage open` → `RESULTS_<날짜>.md` · `open.json`

- [ ] **Step 5: verifier(opus)**
- 같은 원장으로 δ·SE·라벨을 독립 재계산한다.
- 태그별 Holm m=3 은 주 라벨이 「있음(−)」일 때만 계산한다.
- 손계산 로트 10개를 대조한다.
- 결과는 RESULTS 부록으로 붙인다.

- [ ] **Step 6: Commit + 보고**
- `# research(dt-dart-filter): 개봉 — 주 라벨 <라벨> · δ̂ <x>%p · verifier <판정>`
- 사장님께 쉬운 한 장을 드린다(예시 1~2건 · 「보험 크기」 문장 포함).
- push·main 머지는 별도 확인.
