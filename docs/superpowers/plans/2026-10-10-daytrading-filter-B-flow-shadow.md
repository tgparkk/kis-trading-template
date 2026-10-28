# daytrading 거르기 층 B — 수급 4종 봉인 기록기(dtflow_shadow) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- 매수일 07:52 에 daytrading 룰 통과 후보 전부를 스크리너 복제로 다시 계산한다.
- 후보마다 KIS 조회 TR 4개(투자자·프로그램·공매도·신용)를 직접 받아 원문과 특징 4개를 전용 DB 스키마에 봉인한다.
- 시험 10거래일이 통과하면 봉인 단계로 자동 전환한다.

**Architecture:**
- 새 연구 패키지는 `RoboTrader_template/backtest/concept_axes/dtflow_shadow/`, 러너는 `RoboTrader_template/scripts/dtflow_shadow_recorder.py` 다. 브랜치 `research/dt-flow-shadow`(base main).
- 태쏘 shadow 틀(`research/tasso-daily-shadow` e34c9ff)을 **import 하지 않고** 형태만 복사한다(main 에 없음). `llm_shadow/lock.py` 만 파일째 복사한다.
- 순수 모듈(candidates·kis·features·store·guard·phase)은 합성 데이터·가짜 연결로 TDD 한다.
- 실행 위치:
  - 개발 = 워크트리 `D:/tmp/kis-wt-dt-flow-shadow`
  - 운영 = 동결 커밋 detached 워크트리 `D:/tmp/kis-wt-dtflow-run`
- 작업 스케줄러 2개: 07:52 기록 · 09:05 스냅샷 대조.

**Tech Stack:** Python 3.9(kis-template venv) · psycopg2 · pandas · requests · pytest. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-10-10-daytrading-filter-layer-design.md`(main `75326bc`) §4 · §5 · §6 · §8.
**조사 근거:** 세션 scratchpad `plan_dossier/DOSSIER_B.md`(TR 경로·파라미터·응답 키·단위·토큰 형식·스냅샷 열·태쏘 틀 API).

**스펙과 다른 점(계획 승인 때 확인):**
1. 판정·통계 코드는 이 계획에 없다. 스펙 §4-5 판정은 봉인 120거래일 뒤의 별도 계획이다(개봉 도구). 이 계획의 산출물 = 기록기 + 사전등록 + 0단계 자동 전환.
2. 시험 기록은 같은 스키마의 `trial_*` 표에 쓴다. 봉인 표 `candidates/raw/run` 과 물리적으로 분리한다(스펙 「시험 표」).
3. 신용 시차 k 는 시험 기록의 `credit_lag` 분포로 정해 상수 `CREDIT_LAG_K` 에 동결한다(재동결 1회). k 가 정해지기 전에는 봉인으로 넘어가지 않는다.

## Global Constraints

- 🔴 **봇 코드 0줄**: 만드는 것·고치는 것은 아래뿐이다. 라이브 `api/`·`strategies/`·`db/`·`utils/`·`core/` 는 **import 하지 않는다**(복제 + sha 고정).
  - `RoboTrader_template/backtest/concept_axes/dtflow_shadow/**`
  - `RoboTrader_template/scripts/dtflow_shadow_recorder.py`
  - `RoboTrader_template/config/key.ini.example` 섹션 1개
  - `backtest/concept_axes/REGISTRY.md` 한 행
  - 예외 import: `utils.korean_holidays`(달력) · `config.constants.resolve_daily_source_db` · `backtest.concept_axes.replayer.loader.dsn` — 가벼운 모듈만.
- 🔴 **라이브 트리 실행 금지**: 러너는 라이브 트리 경로에서 시작하면 거부한다. 라이브 트리는 **읽기만** 한다: `config/key.ini`([KIS]·[TELEGRAM]·[DTFLOW_SHADOW]) · `token_info.json` · 원본 7파일 sha.
- 🔴 **토큰 발급 0**:
  - 페이퍼 봇 `RoboTrader_template/token_info.json`(YAML 2줄: `token:` · `valid-date:`)을 읽기만 한다.
  - 만료 20분 전 이하·없음·만료 응답(EGW00123)이면 그날 `missed_token` + 경보.
  - `/oauth2/tokenP` 호출 코드를 만들지 않는다.
  - 실전 인스턴스 토큰 `token_info_daytrading.json` 은 열지 않는다.
- 🔴 **KIS = 조회 TR 4개만**: investor `FHKST01010900` · program `FHPPG04650201` · short `FHPST04830000` · credit `FHPST04760000`. 주문 TR 0 · 0.1초 간격 · EGW00201 이면 1.5×2ⁿ초 대기 최대 3회.
- 🔴 **DB**:
  - 쓰기는 `dtflow_shadow_writer` 역할로 `dtflow_shadow` 스키마에만 한다(`ON CONFLICT DO NOTHING` · 한 트랜잭션).
  - 읽기는 `daily_prices`·`screener_snapshots`·`stock_info` 에서만 한다.
  - DDL 적용은 사장님 확인 뒤 1회(Task 10).
- 🔴 **adj_factor 규칙**: 거래량·거래대금 조정은 SQL 한 줄 안의 `volume * COALESCE(adj_factor, 1)` 형태로만 쓴다(레포 가드 `tests/test_adj_factor_no_arithmetic.py`). 파이썬에서 조정 계수를 곱하지 않는다.
- 파이썬·경로:
  - `PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe`
  - 개발 cwd `D:/tmp/kis-wt-dt-flow-shadow/RoboTrader_template`
  - 테스트 `$PY -m pytest backtest/concept_axes/dtflow_shadow/tests -q`
- 커밋: 브랜치 `research/dt-flow-shadow` · **push·main 머지·작업 등록·DDL 적용은 사장님 별도 확인**. 메시지 파일 규칙은 A 계획과 같다(첫 줄 `type(scope): 한국어 요약` + 끝 두 줄 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` · `Claude-Session: https://claude.ai/code/session_01AYpPHTabSgiYwGzubdKLxG`).
- 🔒 **동결 값(스펙 §4)**:

| 항목 | 값 |
|---|---|
| 기록 시각 | 07:52 시작 · 07:50 전 거부 · 08:38 이후 시작 거부 |
| 봉인 마감 | 08:40(넘으면 `late`) |
| 스냅샷 대조 | 09:05 |
| 스크리너 복제 | 60봉 · 15봉 고가 · 20봉 거래량 ×2 · 양봉 · 시총 < 5,000억(결측 제외) · 거래대금 ≥ 10억 · 하락 > 35% 봉 = 불가능봉 · 점수 = 마지막 거래량 / 직전 20봉 평균 |
| 스냅샷 params_hash | `46594669e8b6af417143556ea3c0066d2ccc9984` |
| 특징 ① | 기관 순매수 금액 `orgn_ntby_tr_pbmn`×1e6 ÷ program `acml_tr_pbmn` |
| 특징 ② | `whol_smtn_ntby_tr_pbmn` ÷ `acml_tr_pbmn` |
| 특징 ③ | `ssts_vol_rlim` |
| 특징 ④ | `whol_loan_rmnd_rate` @ deal_date = D−k |
| 봉인 조건 | 연속 10거래일 「후보 일치 100% ∧ 4종 가용률 ≥ 0.95」 |
| D 완결 | D/D′ 행수 ≥ 0.98 |

## Review Focus

1. **07:52 응답의 첫 행이 오늘(B) 0/NULL 행인 경우**
   - 기대: `stck_bsop_date == D` 행만 써야 한다. 첫 행을 쓰면 특징이 0으로 오염된다.
   - 테스트: Task 4 `test_pick_uses_date_not_first_row`.
2. **토큰 파일이 곧 만료되거나 없거나 YAML 이 깨진 경우, 만료 응답이 오는 경우**
   - 기대: 발급하지 않고 `missed_token` 으로 끝난다.
   - 테스트: Task 3 `test_read_token_expiring_raises` · `test_client_token_expired_raises_no_reissue`.
3. **D 가격이 덜 들어온 날(07:40 봇 기동 직후 부분 행)·유니버스 날짜 ≠ D**
   - 기대: 후보를 만들지 않고 `missed_sweep`/`universe_stale` 로 남긴다.
   - 테스트: Task 2 `test_d_complete_ratio` · Task 7 `test_record_universe_stale`.
4. **08:40 을 넘겨 끝난 기록 · 08:38 이후 시작(PC 늦게 켬)**
   - 기대: 앞의 것은 `late` 표시(주 판정 제외), 뒤의 것은 시작 거부(`missed_host`).
   - 테스트: Task 7 `test_record_late_marks_rows` · `test_record_refuses_after_0838`.
5. **CRLF 작업 사본인 라이브 원본(screener.py)**
   - 기대: sha 고정이 줄바꿈 차이로 영원히 불일치하면 안 된다.
   - 테스트: Task 1 `test_source_sha_normalizes_crlf`.

---

## File Structure

```
RoboTrader_template/backtest/concept_axes/dtflow_shadow/
  __init__.py      패키지 docstring(규범 = 스펙 §4 · PREREG.md)
  settings.py      🔒 상수 · 홈/경로 · TR 표 · 원본 7파일 목록
  lock.py          llm_shadow/lock.py 파일째 복사(표준 라이브러리만 · 단일 실행 잠금)
  guard.py         라이브 트리 거부 · git(HEAD=동결·clean·detached) · frozen.json · 원본 sha(LF 정규화)
  candidates.py    스크리너 SQL·룰 복제 · D 결정·완결 · 스냅샷 대조
  kis.py           토큰 읽기(발급 0) · key.ini 읽기 · 조회 TR 4개 클라이언트
  features.py      응답 → D 행 선택 → 특징 4 + 탐색 열 + 가용 표시
  store.py         PgStore/MemoryStore · trial_/봉인 표 · CSV 원장 · 쓰기 연결
  phase.py         시험→봉인 전환 판정 · k 선택표
  alerts.py        텔레그램 1통(key.ini [TELEGRAM] 읽기만)
  ddl.sql          역할·스키마·표 6개(1회 실행)
  register_tasks.ps1 / unregister_tasks.ps1   작업 스케줄러(실행은 사장님 확인 뒤)
  PREREG.md        사전등록(Task 9)
  tests/  __init__.py · conftest.py · test_*.py
RoboTrader_template/scripts/dtflow_shadow_recorder.py   러너(--freeze · --record · --check-snapshot · --choose-k · --dry-run)
```

---

### Task 1: 워크트리 · 패키지 · `settings.py` · `lock.py` 복사 · `guard.py`

**Files:**
- Create: `dtflow_shadow/__init__.py` · `settings.py` · `lock.py` · `guard.py` · `tests/__init__.py` · `tests/conftest.py` · `tests/test_guard.py`

**Interfaces:**
- Produces:
  - `settings.*` 상수
  - `settings.home_dir() -> Path` · `other_homes() -> List[Path]` · `frozen_path()` · `lock_path()` · `log_dir()` · `archive_dir()` · `key_ini_path()` · `token_path()`
  - `lock.RunnerLock(path, owner="")` · `lock.LockBusy`
  - `guard.GuardError` · `guard.source_sha(rel: str, root: str = S.LIVE_RT) -> str` · `guard.Frozen(code_sha, rule_v, frozen_at, sources: Dict[str,str], credit_lag_k: Optional[int])`
  - `guard.write_frozen(repo: Path, path: Optional[Path] = None) -> Frozen` · `guard.load_frozen(path=None) -> Frozen`
  - `guard.check_runtime(repo: Path, fr: Frozen) -> str` · `guard.refuse_live_tree(path)` · `guard.check_home(home=None) -> Path`

- [ ] **Step 1: 워크트리 + lock.py 복사**

```bash
git -C D:/GIT/kis-trading-template worktree add D:/tmp/kis-wt-dt-flow-shadow -b research/dt-flow-shadow main
cd D:/tmp/kis-wt-dt-flow-shadow
mkdir -p RoboTrader_template/backtest/concept_axes/dtflow_shadow/tests
git show research/dart-events:RoboTrader_template/backtest/concept_axes/candidate_ledger/llm_shadow/lock.py > RoboTrader_template/backtest/concept_axes/dtflow_shadow/lock.py
grep -n "^from \|^import " RoboTrader_template/backtest/concept_axes/dtflow_shadow/lock.py   # 표준 라이브러리만이어야 한다
```

- [ ] **Step 2: 실패하는 테스트**

`dtflow_shadow/tests/conftest.py`:
```python
"""dtflow_shadow 단위 테스트 — 합성 데이터 · 가짜 연결 · DB·KIS 없음. 워크트리에서만."""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]          # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if "backtest" not in sys.modules:                   # backtest/__init__ 의 엔진·전략 import 회피(태쏘 러너 선례)
    _pkg = types.ModuleType("backtest")
    _pkg.__path__ = [str(ROOT / "backtest")]
    sys.modules["backtest"] = _pkg
```

`dtflow_shadow/tests/test_guard.py`:
```python
import json
import subprocess

import pytest

from backtest.concept_axes.dtflow_shadow import guard as G
from backtest.concept_axes.dtflow_shadow import settings as S


def test_source_sha_normalizes_crlf(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    (tmp_path / "b.py").write_bytes(b"x = 1\ny = 2\n")
    assert G.source_sha("a.py", str(tmp_path)) == G.source_sha("b.py", str(tmp_path))


def test_refuse_live_tree():
    with pytest.raises(G.GuardError, match="라이브"):
        G.refuse_live_tree(S.LIVE_TREE + "/RoboTrader_template/scripts")


def test_check_home_collision(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "x"))
    monkeypatch.setenv("KIS_TASSO_SHADOW_HOME", str(tmp_path / "x"))
    with pytest.raises(G.GuardError, match="홈"):
        G.check_home()


def _repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    for a in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *a], cwd=r, check=True)
    (r / "f.txt").write_text("1")
    subprocess.run(["git", "add", "."], cwd=r, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=r, check=True)
    return r


def test_frozen_roundtrip_and_runtime_checks(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(tmp_path)
    fr = G.write_frozen(r)
    assert G.load_frozen() == fr and json.loads(S.frozen_path().read_text(encoding="utf-8"))["rule_v"] == S.RULE_V
    with pytest.raises(G.GuardError, match="브랜치"):
        G.check_runtime(r, fr)                       # 브랜치 위 = 거부(detached 만 허용)
    subprocess.run(["git", "switch", "-q", "--detach", fr.code_sha], cwd=r, check=True)
    assert G.check_runtime(r, fr) == fr.code_sha
    (r / "f.txt").write_text("2")
    with pytest.raises(G.GuardError, match="깨끗"):
        G.check_runtime(r, fr)


def test_runtime_refuses_changed_live_source(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(tmp_path)
    fr = G.write_frozen(r)
    subprocess.run(["git", "switch", "-q", "--detach", fr.code_sha], cwd=r, check=True)
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "zzz"})
    with pytest.raises(G.GuardError, match="원본 sha"):
        G.check_runtime(r, fr)
```

- [ ] **Step 3: 실패 확인** — `$PY -m pytest backtest/concept_axes/dtflow_shadow/tests/test_guard.py -q` → FAIL(import)

- [ ] **Step 4: 구현**

`dtflow_shadow/__init__.py`:
```python
"""daytrading 거르기 층 B — 수급 4종 봉인 기록기.

규범 = 스펙 `docs/superpowers/specs/2026-10-10-daytrading-filter-layer-design.md` §4 · 사전등록 `PREREG.md`.
🔴 봇 import 0(복제 + sha 고정) · KIS 조회 TR 4개만 · 토큰 발급 0 · 라이브 트리 실행 거부.
"""
```

`dtflow_shadow/settings.py`:
```python
"""🔒 상수 — 스펙 §4. 바꾸면 사전등록 개정(새 rule_v)."""
from __future__ import annotations

import os
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PKG = Path(__file__).resolve().parent
RT_ROOT = PKG.parents[2]                       # …/RoboTrader_template
REPO_ROOT = RT_ROOT.parent
PREREG = PKG / "PREREG.md"
LIVE_TREE = "D:/GIT/kis-trading-template"
LIVE_RT = LIVE_TREE + "/RoboTrader_template"

RULE_V = "v1"
SCHEMA = "dtflow_shadow"
WRITER_ROLE = "dtflow_shadow_writer"
FOLDER = "daytrading_3methods_breakout"
PARAMS_HASH = "46594669e8b6af417143556ea3c0066d2ccc9984"

START_NOT_BEFORE = time(7, 50)
REFUSE_AFTER = time(8, 38)
SEAL_DEADLINE = time(8, 40)
SNAPSHOT_NOT_BEFORE = time(9, 3)

LOOKBACK_BARS = 60
HIGH_WINDOW = 15
VOL_LOOKBACK = 20
VOL_MULT = 2.0
MAX_MCAP = 500_000_000_000
MIN_TV = 1_000_000_000
IMPOSSIBLE_RET = -0.35
D_ROWS_RATIO_MIN = 0.98

CALL_INTERVAL_S = 0.10
RETRY_BASE_S = 1.5
RETRY_MAX = 3
HTTP_TIMEOUT = (5, 30)
TOKEN_MIN_LEFT_S = 1200
TRS: Dict[str, Tuple[str, str]] = {
    "investor": ("FHKST01010900", "/uapi/domestic-stock/v1/quotations/inquire-investor"),
    "program": ("FHPPG04650201", "/uapi/domestic-stock/v1/quotations/program-trade-by-stock-daily"),
    "short": ("FHPST04830000", "/uapi/domestic-stock/v1/quotations/daily-short-sale"),
    "credit": ("FHPST04760000", "/uapi/domestic-stock/v1/quotations/daily-credit-balance"),
}
KINDS = ("investor", "program", "short", "credit")
SHORT_SPAN_DAYS = 20

INVESTOR_AMT_UNIT = 1_000_000                  # investor *_tr_pbmn = 백만원(DOSSIER_B §0-3)
CREDIT_LAG_K: Optional[int] = None             # 🔒 Task 11 에서 시험 분포로 정해 동결
TRIAL_DAYS = 10
AVAIL_MIN = 0.95

LIVE_SOURCES = (
    "strategies/daytrading_3methods_breakout/screener.py",
    "strategies/_rule_screener_base.py",
    "strategies/books/daytrading_3methods/rules.py",
    "db/quant_daily_reader.py",
    "utils/data_sanity.py",
    "api/kis_market_api.py",
    "api/kis_auth.py",
)


def _local() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home())))


def home_dir() -> Path:
    env = os.environ.get("KIS_DTFLOW_SHADOW_HOME")
    return Path(env) if env else _local() / "kis-dtflow-shadow"


def other_homes() -> List[Path]:
    llm = os.environ.get("KIS_LLM_SHADOW_HOME")
    tasso = os.environ.get("KIS_TASSO_SHADOW_HOME")
    return [Path(llm) if llm else _local() / "kis-llm-shadow", Path(tasso) if tasso else _local() / "kis-tasso-shadow"]


def frozen_path() -> Path:
    return home_dir() / "frozen.json"


def lock_path() -> Path:
    return home_dir() / "runner.lock"


def log_dir() -> Path:
    return home_dir() / "logs"


def archive_dir() -> Path:
    return Path(os.environ.get("KIS_DTFLOW_SHADOW_ARCHIVE", "D:/research-archive/dtflow_shadow"))


def config_dir() -> Path:
    return Path(os.environ.get("KIS_DTFLOW_SHADOW_CONFIG_DIR", LIVE_RT))


def key_ini_path() -> Path:
    return config_dir() / "config" / "key.ini"


def token_path() -> Path:
    return Path(os.environ.get("KIS_DTFLOW_SHADOW_TOKEN", LIVE_RT + "/token_info.json"))
```

`dtflow_shadow/guard.py`:
```python
"""실행 가드 — 라이브 트리 거부 · HEAD=동결 · clean · detached · 원본 7파일 sha(LF 정규화) · 홈 분리."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from . import settings as S


class GuardError(RuntimeError):
    pass


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))).replace("\\", "/").rstrip("/")


def refuse_live_tree(path) -> None:
    live = _norm(S.LIVE_TREE)
    p = _norm(path)
    if p == live or p.startswith(live + "/"):
        raise GuardError(f"라이브 트리에서 실행 거부: {path}")


def check_home(home: Optional[Path] = None) -> Path:
    h = Path(home or S.home_dir())
    for o in S.other_homes():
        if _norm(h) == _norm(o):
            raise GuardError(f"홈 충돌: {h} = 다른 shadow 홈")
    return h


def _git(repo, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, shell=False)
    if r.returncode != 0:
        raise GuardError(f"git {' '.join(args)} 실패: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def git_head(repo) -> str:
    return _git(repo, "rev-parse", "HEAD")


def git_dirty(repo) -> bool:
    return _git(repo, "status", "--porcelain") != ""


def git_detached(repo) -> bool:
    r = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=str(repo), capture_output=True, text=True)
    if r.returncode == 0:
        return False
    if r.returncode == 1:
        return True
    raise GuardError(f"git symbolic-ref 실패: {r.stderr.strip()[:200]}")


def source_sha(rel: str, root: str = S.LIVE_RT) -> str:
    return hashlib.sha256((Path(root) / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _sources() -> Dict[str, str]:
    return {rel: source_sha(rel) for rel in S.LIVE_SOURCES}


@dataclass(frozen=True)
class Frozen:
    code_sha: str
    rule_v: str
    frozen_at: str
    sources: Dict[str, str] = field(default_factory=dict)
    credit_lag_k: Optional[int] = None


def load_frozen(path: Optional[Path] = None) -> Frozen:
    p = Path(path or S.frozen_path())
    if not p.exists():
        raise GuardError("frozen.json 없음 — `--freeze` 먼저")
    return Frozen(**json.loads(p.read_text(encoding="utf-8")))


def write_frozen(repo, path: Optional[Path] = None) -> Frozen:
    refuse_live_tree(repo)
    check_home()
    if git_dirty(repo):
        raise GuardError("작업 트리가 깨끗하지 않다 — 동결 거부")
    fr = Frozen(git_head(repo), S.RULE_V, datetime.now().isoformat(timespec="seconds"), _sources(), S.CREDIT_LAG_K)
    p = Path(path or S.frozen_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with open(p.parent / "frozen_history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(json.loads(p.read_text(encoding="utf-8")), ensure_ascii=False) + "\n")
    tmp = p.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(asdict(fr), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return fr


def check_runtime(repo, fr: Frozen) -> str:
    refuse_live_tree(repo)
    check_home()
    if fr.rule_v != S.RULE_V:
        raise GuardError(f"rule_v 불일치 {fr.rule_v} ≠ {S.RULE_V}")
    if fr.credit_lag_k != S.CREDIT_LAG_K:
        raise GuardError("credit_lag_k 불일치 — 다시 동결")
    head = git_head(repo)
    if head != fr.code_sha:
        raise GuardError(f"HEAD {head[:10]} ≠ 동결 code_sha {fr.code_sha[:10]}")
    if git_dirty(repo):
        raise GuardError("작업 트리가 깨끗하지 않다")
    if not git_detached(repo):
        raise GuardError("브랜치 위에서 실행 거부 — detached 워크트리만")
    now = _sources()
    bad = [k for k, v in fr.sources.items() if now.get(k) != v]
    if bad:
        raise GuardError(f"라이브 원본 sha 불일치: {', '.join(bad)} — 다시 검토·동결")
    return head
```

- [ ] **Step 5: 통과 확인** — 5 passed

- [ ] **Step 6: Commit** — `# research(dt-flow-shadow): 패키지·동결 상수·잠금(llm_shadow/lock.py 복사)·가드(라이브 거부·detached·원본 sha LF 정규화·홈 분리) + 테스트 5`

---

### Task 2: `candidates.py` — 스크리너 SQL·룰 복제 · D 결정·완결 · 스냅샷 대조

**Files:**
- Create: `dtflow_shadow/candidates.py` · `dtflow_shadow/tests/test_candidates.py`

**Interfaces:**
- Produces:
  - `candidates.UNIVERSE_SQL` · `candidates.DAILY_SQL`(문자열)
  - `candidates.base_filter(rows: List[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]`
  - `candidates.impossible(df: pd.DataFrame) -> bool`
  - `candidates.match(df: pd.DataFrame) -> Optional[float]` — 통과 시 점수, 아니면 None
  - `candidates.rank(scored: List[Tuple[str, float]]) -> List[Cand]` — `Cand(stock_code, score, rank)` · 점수 내림차순 · 동점은 입력 순서
  - `candidates.prev_trading_day(cur, T: date) -> Optional[date]`
  - `candidates.d_complete(cur, D: date) -> Tuple[bool, Dict[str, Any]]` — `{d_rows, dprev_rows, universe_date}`
  - `candidates.compute(cur, D: date) -> List[Cand]`
  - `candidates.load_snapshot(cur, D: date) -> List[Tuple[str, int, float]]`
  - `candidates.compare(mine: List[Cand], snap: List[Tuple[str, int, float]]) -> Dict[str, Any]` — `{match, mine_n, snapshot_n, max_score_diff, only_mine, only_snap, rank_equal}`

- [ ] **Step 1: 실패하는 테스트**

`dtflow_shadow/tests/test_candidates.py`:
```python
import numpy as np
import pandas as pd

from backtest.concept_axes.dtflow_shadow import candidates as C


def _df(closes, highs=None, vols=None, opens=None):
    n = len(closes)
    return pd.DataFrame({"date": pd.date_range("2026-08-01", periods=n), "open": opens or [c * 0.99 for c in closes],
                         "high": highs or closes, "low": closes, "close": closes, "volume": vols or [1000.0] * n})


def test_sql_keeps_adj_factor_on_one_line():
    for sql in (C.UNIVERSE_SQL, C.DAILY_SQL):
        assert any("volume * COALESCE(adj_factor, 1)" in line for line in sql.splitlines())


def test_base_filter_live_rules():
    rows = [("1", 4.9e11, 2e9), ("2", 5e11, 2e9), ("3", 0.0, 2e9), ("4", 1e11, 9.9e8)]
    assert [r[0] for r in C.base_filter(rows)] == ["1"]


def test_match_breakout_volume_bullish():
    closes = [100.0] * 30 + [110.0]
    vols = [1000.0] * 30 + [2500.0]
    s = C.match(_df(closes, vols=vols))
    assert s is not None and abs(s - 2.5) < 1e-12


def test_match_rejects_short_window_no_volume_or_bearish():
    assert C.match(_df([100.0] * 16)) is None
    assert C.match(_df([100.0] * 30 + [110.0], vols=[1000.0] * 30 + [1500.0])) is None
    closes = [100.0] * 30 + [110.0]
    assert C.match(_df(closes, vols=[1000.0] * 30 + [2500.0], opens=[99.0] * 30 + [111.0])) is None


def test_impossible_drop():
    assert C.impossible(_df([100.0, 60.0, 61.0]))
    assert not C.impossible(_df([100.0, 70.0, 71.0]))


def test_rank_stable_desc():
    r = C.rank([("a", 2.0), ("b", 3.0), ("c", 2.0)])
    assert [(x.stock_code, x.rank) for x in r] == [("b", 1), ("a", 2), ("c", 3)]


def test_compare_exact_and_mismatch():
    mine = C.rank([("a", 3.0), ("b", 2.0)])
    assert C.compare(mine, [("a", 1, 3.0), ("b", 2, 2.0)])["match"]
    m = C.compare(mine, [("a", 1, 3.0)])
    assert not m["match"] and m["only_mine"] == ["b"]
    assert not C.compare(mine, [("a", 1, 3.0), ("b", 2, 2.1)])["match"]
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dtflow_shadow/candidates.py`:
```python
"""daytrading 후보 복제 — 라이브 `screener.py`·`_rule_screener_base.py`·`rules.py`·`quant_daily_reader.py`·`data_sanity.py`
의 SQL·룰을 «그대로» 옮긴 판(라이브 import 0 · 원본 sha 는 guard 가 고정).

🔴 거래량 조정은 SQL 한 줄 안의 `volume * COALESCE(adj_factor, 1)` 뿐(레포 가드).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from . import settings as S

UNIVERSE_SQL = (
    "SELECT stock_code, COALESCE(market_cap,0), COALESCE((close * (volume * COALESCE(adj_factor, 1)))::numeric, 0) AS trading_value "
    "FROM daily_prices WHERE date = (SELECT max(date) FROM daily_prices WHERE date <= %s AND market_cap IS NOT NULL) "
    "AND market_cap IS NOT NULL"
)
UNIVERSE_DATE_SQL = "SELECT max(date) FROM daily_prices WHERE date <= %s AND market_cap IS NOT NULL"
DAILY_SQL = (
    "SELECT date, open, high, low, close, (volume * COALESCE(adj_factor, 1))::double precision AS volume "
    "FROM daily_prices WHERE stock_code = %s AND date <= %s ORDER BY date DESC LIMIT %s"
)
SNAPSHOT_SQL = ("SELECT stock_code, rank_in_snapshot, score FROM screener_snapshots "
                "WHERE strategy = %s AND scan_date = %s AND params_hash = %s ORDER BY rank_in_snapshot")


@dataclass(frozen=True)
class Cand:
    stock_code: str
    score: float
    rank: int


def base_filter(rows: List[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]:
    out = []
    for code, mcap, tv in rows:
        if mcap is None or mcap <= 0 or mcap >= S.MAX_MCAP:
            continue
        if (tv or 0.0) < S.MIN_TV:
            continue
        out.append((code, mcap, tv))
    return out


def impossible(df: pd.DataFrame) -> bool:
    close = pd.to_numeric(df["close"], errors="coerce")
    close = close.where(close > 0)
    ret = close.pct_change(fill_method=None)
    return bool((ret < S.IMPOSSIBLE_RET).any())


def match(df: pd.DataFrame) -> Optional[float]:
    if len(df) < S.HIGH_WINDOW + 2:
        return None
    last = df.iloc[-1]
    prior_high = float(df["high"].iloc[-(S.HIGH_WINDOW + 1):-1].max())
    avg_vol = float(df["volume"].iloc[-(S.VOL_LOOKBACK + 1):-1].mean())
    close, vol, open_ = float(last["close"]), float(last["volume"]), float(last["open"])
    if not (close >= prior_high and avg_vol > 0 and vol >= avg_vol * S.VOL_MULT and close > open_):
        return None
    if not close > 0:
        return None
    return vol / (float(df["volume"].iloc[-21:-1].mean()) or 1.0)


def rank(scored: List[Tuple[str, float]]) -> List[Cand]:
    ordered = sorted(scored, key=lambda t: -t[1])          # 안정 정렬 = 동점은 유니버스(입력) 순서
    return [Cand(c, float(s), i + 1) for i, (c, s) in enumerate(ordered)]


def prev_trading_day(cur, T: date) -> Optional[date]:
    cur.execute("SELECT max(date) FROM daily_prices WHERE stock_code = 'KOSPI' AND date < %s", (T.isoformat(),))
    v = cur.fetchone()[0]
    return date.fromisoformat(str(v)[:10]) if v else None


def d_complete(cur, D: date) -> Tuple[bool, Dict[str, Any]]:
    cur.execute("SELECT max(date) FROM daily_prices WHERE stock_code = 'KOSPI' AND date < %s", (D.isoformat(),))
    dp = cur.fetchone()[0]
    q = "SELECT count(*) FROM daily_prices WHERE date = %s AND market_cap IS NOT NULL"
    cur.execute(q, (D.isoformat(),))
    n_d = int(cur.fetchone()[0])
    n_p = 0
    if dp:
        cur.execute(q, (str(dp)[:10],))
        n_p = int(cur.fetchone()[0])
    cur.execute(UNIVERSE_DATE_SQL, (D.isoformat(),))
    ud = cur.fetchone()[0]
    info = {"d_rows": n_d, "dprev_rows": n_p, "universe_date": str(ud)[:10] if ud else None}
    ok = n_p > 0 and n_d / n_p >= S.D_ROWS_RATIO_MIN and info["universe_date"] == D.isoformat()
    return ok, info


def _daily(cur, code: str, D: date) -> pd.DataFrame:
    cur.execute(DAILY_SQL, (code, D.isoformat(), S.LOOKBACK_BARS))
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df[df["date"].dt.date <= D]


def compute(cur, D: date) -> List[Cand]:
    cur.execute(UNIVERSE_SQL, (D.isoformat(),))
    uni = [(str(c), float(m or 0), float(t or 0)) for c, m, t in cur.fetchall()]
    scored: List[Tuple[str, float]] = []
    for code, _m, _t in base_filter(uni):
        df = _daily(cur, code, D)
        if df.empty or impossible(df):
            continue
        s = match(df)
        if s is not None:
            scored.append((code, s))
    return rank(scored)


def load_snapshot(cur, D: date) -> List[Tuple[str, int, float]]:
    cur.execute(SNAPSHOT_SQL, (S.FOLDER, D, S.PARAMS_HASH))
    return [(str(c), int(r), float(s) if s is not None else float("nan")) for c, r, s in cur.fetchall()]


def compare(mine: List[Cand], snap: List[Tuple[str, int, float]]) -> Dict[str, Any]:
    m = {c.stock_code: c for c in mine}
    s = {c: (r, sc) for c, r, sc in snap}
    only_mine = sorted(set(m) - set(s))
    only_snap = sorted(set(s) - set(m))
    common = set(m) & set(s)
    diffs = [abs(m[c].score - s[c][1]) for c in common]
    rank_equal = all(m[c].rank == s[c][0] for c in common)
    max_diff = max(diffs) if diffs else 0.0
    ok = not only_mine and not only_snap and rank_equal and max_diff < 1e-9
    return {"match": ok, "mine_n": len(m), "snapshot_n": len(s), "max_score_diff": max_diff,
            "only_mine": only_mine, "only_snap": only_snap, "rank_equal": rank_equal}
```

- [ ] **Step 4: 통과 확인** → 7 passed. 이어서 레포 가드 테스트도 돌린다: `$PY -m pytest tests/test_adj_factor_no_arithmetic.py -q` → PASS(새 SQL 형태가 허용 목록에 맞는지 확인).

- [ ] **Step 5: Commit** — `# research(dt-flow-shadow): 스크리너 SQL·룰 복제(라이브 import 0)·D 결정·완결·스냅샷 대조 + 테스트 7`

---

### Task 3: `kis.py` — 토큰 읽기(발급 0) · key.ini · 조회 TR 4개 클라이언트

**Files:**
- Create: `dtflow_shadow/kis.py` · `dtflow_shadow/tests/test_kis.py`

**Interfaces:**
- Produces:
  - `kis.TokenUnavailable(Exception)`
  - `kis.read_token(path: Path, now: datetime, min_left_s: int = 1200) -> str`
  - `kis.read_kis_conf(path: Path) -> Dict[str, str]` — 키 `base_url, appkey, appsecret`
  - `kis.params_for(kind: str, code: str, D: date, T: date) -> Dict[str, str]`
  - `kis.Client(base_url, token, appkey, appsecret, session=None, sleep=time.sleep, clock=time.monotonic)`
  - `.get(kind: str, params: Dict[str, str]) -> Tuple[dict, str]` — (응답 본문, fetched_at ISO) · 만료면 `TokenUnavailable`
  - `.calls: int`

- [ ] **Step 1: 실패하는 테스트**

`dtflow_shadow/tests/test_kis.py`:
```python
from datetime import date, datetime

import pytest

from backtest.concept_axes.dtflow_shadow import kis as K


def test_read_token_ok_and_expiring(tmp_path):
    p = tmp_path / "token_info.json"
    p.write_text("token: abc\nvalid-date: 2026-10-12 15:35:08\n", encoding="utf-8")
    assert K.read_token(p, datetime(2026, 10, 12, 7, 52)) == "abc"
    with pytest.raises(K.TokenUnavailable):
        K.read_token(p, datetime(2026, 10, 12, 15, 20))


def test_read_token_expiring_raises(tmp_path):
    p = tmp_path / "t.json"
    p.write_text("token: abc\n", encoding="utf-8")
    with pytest.raises(K.TokenUnavailable):
        K.read_token(p, datetime(2026, 10, 12, 7, 52))
    with pytest.raises(K.TokenUnavailable):
        K.read_token(tmp_path / "none.json", datetime(2026, 10, 12, 7, 52))


def test_params_for_each_kind():
    D, T = date(2026, 10, 8), date(2026, 10, 12)
    assert K.params_for("investor", "005930", D, T) == {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
    assert K.params_for("credit", "005930", D, T)["FID_COND_SCR_DIV_CODE"] == "20476"
    sh = K.params_for("short", "005930", D, T)
    assert sh["FID_INPUT_DATE_2"] == "20261008" and sh["FID_INPUT_DATE_1"] == "20260918"


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class _Sess:
    def __init__(self, seq):
        self.seq, self.calls = list(seq), []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, headers, params))
        return self.seq.pop(0)


def test_client_headers_throttle_and_retry_201():
    s = _Sess([_Resp(200, {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과"}),
               _Resp(200, {"rt_cd": "0", "output": []})])
    slept = []
    c = K.Client("https://h", "tok", "ak", "as", session=s, sleep=slept.append, clock=lambda: 0.0)
    body, at = c.get("investor", {"FID_INPUT_ISCD": "1"})
    assert body["rt_cd"] == "0" and c.calls == 2 and 1.5 in slept
    url, h, _ = s.calls[0]
    assert url.endswith("/inquire-investor") and h["tr_id"] == "FHKST01010900" and h["authorization"] == "Bearer tok"
    assert h["custtype"] == "P"


def test_client_token_expired_raises_no_reissue():
    s = _Sess([_Resp(200, {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다"})])
    c = K.Client("https://h", "tok", "ak", "as", session=s, sleep=lambda x: None, clock=lambda: 0.0)
    with pytest.raises(K.TokenUnavailable):
        c.get("credit", {})
    assert all("/oauth2" not in u for u, _, _ in s.calls)
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dtflow_shadow/kis.py`:
```python
"""KIS 조회 TR 4개 최소 클라이언트 — 라이브 `api/kis_auth.py`·`api/kis_market_api.py` 의 경로·헤더·파라미터를 복제
(원본 sha 는 guard 가 고정). 🔴 토큰 발급 0 — 파일을 읽기만 하고, 만료·없음·만료 응답이면 `TokenUnavailable`."""
from __future__ import annotations

import configparser
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from . import settings as S


class TokenUnavailable(Exception):
    pass


def read_token(path: Path, now: datetime, min_left_s: int = S.TOKEN_MIN_LEFT_S) -> str:
    p = Path(path)
    if not p.exists():
        raise TokenUnavailable("토큰 파일 없음")
    tok, valid = None, None
    for line in p.read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition(":")
        if k.strip() == "token":
            tok = v.strip()
        elif k.strip() == "valid-date":
            try:
                valid = datetime.strptime(v.strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                valid = None
    if not tok or valid is None:
        raise TokenUnavailable("토큰 파일 형식 이상")
    if (valid - now).total_seconds() < min_left_s:
        raise TokenUnavailable("토큰 곧 만료")
    return tok


def read_kis_conf(path: Path) -> Dict[str, str]:
    cp = configparser.ConfigParser()
    cp.read(str(path), encoding="utf-8")
    sec = cp["KIS"]
    get = lambda k: str(sec.get(k, "")).strip().strip('"')   # noqa: E731
    return {"base_url": get("KIS_BASE_URL"), "appkey": get("KIS_APP_KEY"), "appsecret": get("KIS_APP_SECRET")}


def params_for(kind: str, code: str, D: date, T: date) -> Dict[str, str]:
    base = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    if kind == "investor":
        return base
    if kind == "program":
        return {**base, "FID_INPUT_DATE_1": T.strftime("%Y%m%d")}
    if kind == "short":
        return {**base, "FID_INPUT_DATE_1": (D - timedelta(days=S.SHORT_SPAN_DAYS)).strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": D.strftime("%Y%m%d")}
    if kind == "credit":
        return {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20476", "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": T.strftime("%Y%m%d")}
    raise ValueError(kind)


def _expired(body: Dict[str, Any]) -> bool:
    return body.get("msg_cd") == "EGW00123" or "기간이 만료된 token" in str(body.get("msg1", ""))


def _too_fast(body: Dict[str, Any]) -> bool:
    return body.get("msg_cd") == "EGW00201" or "초당 거래건수를 초과" in str(body.get("msg1", ""))


class Client:
    def __init__(self, base_url: str, token: str, appkey: str, appsecret: str, session=None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        if session is None:
            import requests
            session = requests.Session()
        self.base_url, self.token, self.appkey, self.appsecret = base_url.rstrip("/"), token, appkey, appsecret
        self.session, self.sleep, self.clock = session, sleep, clock
        self._last = -1e9
        self.calls = 0

    def _headers(self, tr_id: str) -> Dict[str, str]:
        return {"Content-Type": "application/json", "Accept": "text/plain", "charset": "UTF-8",
                "User-Agent": "StockBot/1.0", "authorization": f"Bearer {self.token}", "appkey": self.appkey,
                "appsecret": self.appsecret, "tr_id": tr_id, "custtype": "P", "tr_cont": ""}

    def get(self, kind: str, params: Dict[str, str]) -> Tuple[dict, str]:
        tr_id, path = S.TRS[kind]
        body: Dict[str, Any] = {}
        for attempt in range(S.RETRY_MAX + 1):
            wait = S.CALL_INTERVAL_S - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            r = self.session.get(self.base_url + path, headers=self._headers(tr_id), params=params,
                                 timeout=S.HTTP_TIMEOUT)
            self.calls += 1
            try:
                body = r.json()
            except ValueError:
                body = {"rt_cd": "X", "msg_cd": f"HTTP{r.status_code}", "msg1": "JSON 아님"}
            if _expired(body):
                raise TokenUnavailable("만료 응답(EGW00123)")
            if _too_fast(body) and attempt < S.RETRY_MAX:
                self.sleep(S.RETRY_BASE_S * (2 ** attempt))
                continue
            break
        return body, datetime.now().isoformat(timespec="milliseconds")
```

- [ ] **Step 4: 통과 확인** → 5 passed

- [ ] **Step 5: Commit** — `# research(dt-flow-shadow): KIS 조회 TR 4개 최소 클라이언트(토큰 읽기만·발급 0·EGW00201 재시도·만료 응답 중단) + 테스트 5`

---

### Task 4: `features.py` — D 행 선택 · 특징 4 · 탐색 열 · 가용 표시

**Files:**
- Create: `dtflow_shadow/features.py` · `dtflow_shadow/tests/test_features.py`

**Interfaces:**
- Produces:
  - `features.rows_of(kind: str, body: dict) -> List[dict]`(short = `output2` · 그 밖 = `output`)
  - `features.num(v) -> Optional[float]`
  - `features.pick(rows, field: str, ymd: str) -> Optional[dict]`
  - `features.compute(D: date, bodies: Dict[str, dict], cal: List[date], k: Optional[int]) -> Dict[str, Any]`
    - 특징 키: `f1_orgn, f2_prog, f3_short, f4_credit`
    - 신용·분모 키: `credit_deal_date, credit_lag, acml_tr_pbmn`
    - 가용 표시: `has_investor, has_program, has_short, has_credit`
    - 탐색 열: `x_frgn, x_prsn, x_orgn5, x_loan_gvrt, x_ssts_amt_rlim`

- [ ] **Step 1: 실패하는 테스트**

`dtflow_shadow/tests/test_features.py`:
```python
from datetime import date

from backtest.concept_axes.dtflow_shadow import features as F

CAL = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
D = date(2026, 10, 8)


def _bodies():
    inv = {"rt_cd": "0", "output": [
        {"stck_bsop_date": "20261012", "orgn_ntby_tr_pbmn": "0", "frgn_ntby_tr_pbmn": "0", "prsn_ntby_tr_pbmn": ""},
        {"stck_bsop_date": "20261008", "orgn_ntby_tr_pbmn": "-500", "frgn_ntby_tr_pbmn": "1,000", "prsn_ntby_tr_pbmn": "-500"},
        {"stck_bsop_date": "20261007", "orgn_ntby_tr_pbmn": "100", "frgn_ntby_tr_pbmn": "0", "prsn_ntby_tr_pbmn": "0"}]}
    prog = {"rt_cd": "0", "output": [
        {"stck_bsop_date": "20261008", "acml_tr_pbmn": "10000000000", "whol_smtn_ntby_tr_pbmn": "-2000000000"},
        {"stck_bsop_date": "20261007", "acml_tr_pbmn": "5000000000", "whol_smtn_ntby_tr_pbmn": "0"}]}
    short = {"rt_cd": "0", "output1": {}, "output2": [
        {"stck_bsop_date": "20261008", "ssts_vol_rlim": "1.25", "ssts_tr_pbmn_rlim": "1.10"}]}
    credit = {"rt_cd": "0", "output": [
        {"deal_date": "20261002", "whol_loan_rmnd_rate": "3.5", "whol_loan_gvrt": "10.0"},
        {"deal_date": "20261001", "whol_loan_rmnd_rate": "3.4", "whol_loan_gvrt": "9.0"}]}
    return {"investor": inv, "program": prog, "short": short, "credit": credit}


def test_pick_uses_date_not_first_row():
    out = F.compute(D, _bodies(), CAL, k=3)
    assert abs(out["f1_orgn"] - (-500 * 1e6 / 1e10)) < 1e-12        # 첫 행(20261012 0) 아님
    assert abs(out["f2_prog"] - (-0.2)) < 1e-12
    assert out["f3_short"] == 1.25


def test_credit_lag_and_fixed_k():
    out = F.compute(D, _bodies(), CAL, k=3)
    assert out["credit_deal_date"] == "20261002" and out["credit_lag"] == 3
    assert out["f4_credit"] == 3.5 and out["has_credit"]
    assert F.compute(D, _bodies(), CAL, k=2)["f4_credit"] is None
    assert F.compute(D, _bodies(), CAL, k=None)["f4_credit"] is None


def test_missing_denominator_gives_none_and_flags():
    b = _bodies()
    b["program"] = {"rt_cd": "0", "output": []}
    out = F.compute(D, b, CAL, k=3)
    assert out["f1_orgn"] is None and out["f2_prog"] is None and not out["has_investor"] and not out["has_program"]


def test_num_parsing():
    assert F.num("1,234") == 1234.0 and F.num("") is None and F.num("-") is None and F.num(None) is None
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dtflow_shadow/features.py`:
```python
"""응답 → 특징 — 스펙 §4-3. D 행은 «날짜 필드 == D» 로만 고른다(첫 행 금지).

단위: investor 금액 = 백만원(×1e6) · program/short 금액 = 원 · 분모 거래대금 = 같은 아침 program `acml_tr_pbmn`.
신용 = deal_date 기준 · ④ = deal_date == cal[D−k] 행 · k 미정이면 None(시험 단계에서는 `credit_lag` 만 기록).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from . import settings as S


def rows_of(kind: str, body: dict) -> List[dict]:
    out = (body or {}).get("output2" if kind == "short" else "output")
    if isinstance(out, list):
        return [r for r in out if isinstance(r, dict)]
    return [out] if isinstance(out, dict) and out else []


def num(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "+"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pick(rows: List[dict], field: str, ymd: str) -> Optional[dict]:
    for r in rows:
        if str(r.get(field, "")).strip() == ymd:
            return r
    return None


def compute(D: date, bodies: Dict[str, dict], cal: List[date], k: Optional[int]) -> Dict[str, Any]:
    ymd = D.strftime("%Y%m%d")
    inv_rows = rows_of("investor", bodies.get("investor") or {})
    prog_rows = rows_of("program", bodies.get("program") or {})
    inv = pick(inv_rows, "stck_bsop_date", ymd)
    prog = pick(prog_rows, "stck_bsop_date", ymd)
    sh = pick(rows_of("short", bodies.get("short") or {}), "stck_bsop_date", ymd)
    cr_rows = rows_of("credit", bodies.get("credit") or {})

    tv = num(prog.get("acml_tr_pbmn")) if prog else None
    ok_tv = tv is not None and tv > 0

    def ratio(v: Optional[float], unit: float = 1.0) -> Optional[float]:
        return (v * unit / tv) if (v is not None and ok_tv) else None

    f1 = ratio(num(inv.get("orgn_ntby_tr_pbmn")) if inv else None, S.INVESTOR_AMT_UNIT)
    f2 = ratio(num(prog.get("whol_smtn_ntby_tr_pbmn")) if prog else None)
    f3 = num(sh.get("ssts_vol_rlim")) if sh else None

    deal = sorted({str(r.get("deal_date", "")).strip() for r in cr_rows
                   if len(str(r.get("deal_date", "")).strip()) == 8 and str(r.get("deal_date", "")).strip() <= ymd},
                  reverse=True)
    latest = deal[0] if deal else None
    lag = None
    if latest and D in cal:
        ld = date(int(latest[:4]), int(latest[4:6]), int(latest[6:]))
        if ld in cal:
            lag = cal.index(D) - cal.index(ld)
    f4 = None
    gvrt = None
    if k is not None and D in cal and cal.index(D) - k >= 0:
        row = pick(cr_rows, "deal_date", cal[cal.index(D) - k].strftime("%Y%m%d"))
        if row:
            f4 = num(row.get("whol_loan_rmnd_rate"))
            gvrt = num(row.get("whol_loan_gvrt"))

    inv5 = sorted([r for r in inv_rows if str(r.get("stck_bsop_date", "")).strip() <= ymd],
                  key=lambda r: str(r.get("stck_bsop_date")), reverse=True)[:5]
    days5 = {str(r.get("stck_bsop_date")).strip() for r in inv5}
    tv5 = sum(num(r.get("acml_tr_pbmn")) or 0.0 for r in prog_rows if str(r.get("stck_bsop_date", "")).strip() in days5)
    o5 = [num(r.get("orgn_ntby_tr_pbmn")) for r in inv5]
    x_orgn5 = (sum(v for v in o5 if v is not None) * S.INVESTOR_AMT_UNIT / tv5) if (tv5 > 0 and len(inv5) == 5) else None

    return {"f1_orgn": f1, "f2_prog": f2, "f3_short": f3, "f4_credit": f4,
            "credit_deal_date": latest, "credit_lag": lag, "acml_tr_pbmn": tv,
            "has_investor": f1 is not None, "has_program": f2 is not None, "has_short": f3 is not None,
            "has_credit": f4 is not None,
            "x_frgn": ratio(num(inv.get("frgn_ntby_tr_pbmn")) if inv else None, S.INVESTOR_AMT_UNIT),
            "x_prsn": ratio(num(inv.get("prsn_ntby_tr_pbmn")) if inv else None, S.INVESTOR_AMT_UNIT),
            "x_orgn5": x_orgn5, "x_loan_gvrt": gvrt,
            "x_ssts_amt_rlim": num(sh.get("ssts_tr_pbmn_rlim")) if sh else None}
```

- [ ] **Step 4: 통과 확인** → 4 passed

- [ ] **Step 5: Commit** — `# research(dt-flow-shadow): 특징 4(기관·프로그램·공매도·신용 @D−k)·탐색 열·D 행 날짜 선택·단위 고정 + 테스트 4`

---

### Task 5: `store.py` + `ddl.sql` — 시험/봉인 표 · 한 트랜잭션 · CSV 원장

**Files:**
- Create: `dtflow_shadow/store.py` · `dtflow_shadow/ddl.sql` · `dtflow_shadow/tests/test_store.py`
- Modify: `RoboTrader_template/config/key.ini.example`(섹션 `[DTFLOW_SHADOW]` 추가)

**Interfaces:**
- Produces:
  - `store.CAND_COLS` · `store.RAW_COLS` · `store.RUN_COLS`(리스트 · DDL 열 순서와 같음)
  - `store.table(phase: str, kind: str) -> str` — phase ∈ {"trial", "sealed"}; kind ∈ {"candidates", "raw", "run"} → `dtflow_shadow.trial_candidates` 등
  - `store.row_sha(row: Dict, cols: List[str]) -> str` · `store.to_csv(rows, cols) -> bytes` · `store.rows_sha256(rows) -> str`
  - `store.MemoryStore()` · `store.PgStore(conn)` — 공통:
    - `write_day(phase, cands, raws, run) -> None`(한 트랜잭션 · 충돌 행 있으면 예외)
    - `write_raws(phase, raws) -> None`
    - `write_run(phase, run) -> None`
    - `runs(phase) -> List[Dict]`
    - `cands(phase, D) -> List[Dict]`
    - `any_sealed() -> bool`
  - `store.export_ledger(rows, cols, root: Path, D: date, name: str) -> str`(sha256)
  - `store.connect_writer()`

- [ ] **Step 1: DDL 작성**

`dtflow_shadow/ddl.sql`:
```sql
-- 실행(사장님 확인 뒤 1회 · Task 10): psql -h 127.0.0.1 -p 5433 -U postgres -d kis_template -f ddl.sql
-- 비밀번호는 실행 중 \prompt 로 받는다 = config/key.ini [DTFLOW_SHADOW] db_password 값.
-- 규약: retention 없음 · DROP 없음 · IF NOT EXISTS 없음(이미 있으면 멈춘다).
\set ON_ERROR_STOP on
\if :{?dtflow_pw}
\else
\prompt 'dtflow_shadow_writer password (key.ini [DTFLOW_SHADOW] db_password): ' dtflow_pw
\endif
CREATE ROLE dtflow_shadow_writer LOGIN PASSWORD :'dtflow_pw';
CREATE SCHEMA dtflow_shadow AUTHORIZATION dtflow_shadow_writer;
REVOKE ALL ON SCHEMA dtflow_shadow FROM PUBLIC;
GRANT CONNECT ON DATABASE kis_template TO dtflow_shadow_writer;
GRANT USAGE ON SCHEMA public TO dtflow_shadow_writer;
GRANT SELECT ON public.daily_prices, public.stock_info, public.screener_snapshots TO dtflow_shadow_writer;
SET ROLE dtflow_shadow_writer;
CREATE TABLE dtflow_shadow.trial_candidates (rule_v text, scan_date date, stock_code text, rank int, score double precision,
  run_at timestamptz, f1_orgn double precision, f2_prog double precision, f3_short double precision, f4_credit double precision,
  credit_deal_date text, credit_lag int, has_investor boolean, has_program boolean, has_short boolean, has_credit boolean,
  x_frgn double precision, x_prsn double precision, x_orgn5 double precision, x_loan_gvrt double precision,
  x_ssts_amt_rlim double precision, acml_tr_pbmn double precision, late boolean, code_sha text NOT NULL, row_sha text NOT NULL,
  PRIMARY KEY (rule_v, scan_date, stock_code));
CREATE TABLE dtflow_shadow.trial_raw (rule_v text, scan_date date, stock_code text, kind text, vintage smallint,
  fetched_at text, rt_cd text, msg_cd text, body jsonb, body_sha256 text NOT NULL,
  PRIMARY KEY (rule_v, scan_date, stock_code, kind, vintage));
CREATE TABLE dtflow_shadow.trial_run (rule_v text, scan_date date, run_kind text, run_at timestamptz, status text NOT NULL,
  n_cands int, n_calls int, n_fail int, avail_investor double precision, avail_program double precision,
  avail_short double precision, avail_credit double precision, snapshot_match boolean, snapshot_n int, mine_n int,
  max_score_diff double precision, universe_date text, d_rows int, dprev_rows int, rows_sha256 text, duration_ms int,
  code_sha text NOT NULL, error_text text, PRIMARY KEY (rule_v, scan_date, run_kind, run_at));
CREATE TABLE dtflow_shadow.candidates (LIKE dtflow_shadow.trial_candidates INCLUDING ALL);
CREATE TABLE dtflow_shadow.raw (LIKE dtflow_shadow.trial_raw INCLUDING ALL);
CREATE TABLE dtflow_shadow.run (LIKE dtflow_shadow.trial_run INCLUDING ALL);
RESET ROLE;
GRANT USAGE ON SCHEMA dtflow_shadow TO robotrader;
GRANT SELECT ON ALL TABLES IN SCHEMA dtflow_shadow TO robotrader;
```

- [ ] **Step 2: 실패하는 테스트**

`dtflow_shadow/tests/test_store.py`:
```python
import re
from datetime import date

import pytest

from backtest.concept_axes.dtflow_shadow import settings as S
from backtest.concept_axes.dtflow_shadow import store as ST


def _cand(code="000001", D=date(2026, 10, 8)):
    r = {c: None for c in ST.CAND_COLS}
    r.update(rule_v="v1", scan_date=D, stock_code=code, rank=1, score=2.5, code_sha="x", late=False)
    r["row_sha"] = ST.row_sha(r, ST.CAND_COLS)
    return r


def _run(D=date(2026, 10, 8), status="ok"):
    r = {c: None for c in ST.RUN_COLS}
    r.update(rule_v="v1", scan_date=D, run_kind="record", run_at="2026-10-12T07:52:00+09:00", status=status, code_sha="x")
    return r


def test_ddl_columns_match_lists():
    ddl = (S.PKG / "ddl.sql").read_text(encoding="utf-8")
    for table, cols in (("trial_candidates", ST.CAND_COLS), ("trial_raw", ST.RAW_COLS), ("trial_run", ST.RUN_COLS)):
        body = re.search(rf"CREATE TABLE dtflow_shadow\.{table} \((.*?)PRIMARY KEY", ddl, re.S).group(1)
        names = [p.strip().split()[0] for p in body.split(",") if p.strip()]
        assert names == cols, table


def test_memory_store_atomic_and_conflict():
    s = ST.MemoryStore()
    s.write_day("trial", [_cand()], [], _run())
    assert len(s.cands("trial", date(2026, 10, 8))) == 1 and s.runs("trial")[0]["status"] == "ok"
    with pytest.raises(RuntimeError):
        s.write_day("trial", [_cand()], [], _run())                     # 같은 PK = 충돌
    assert len(s.runs("trial")) == 1                                   # 실패한 트랜잭션은 흔적 없음
    assert not s.any_sealed()


def test_row_sha_deterministic_and_csv_sorted():
    a, b = _cand("000002"), _cand("000001")
    assert ST.row_sha(a, ST.CAND_COLS) == ST.row_sha(dict(a), ST.CAND_COLS)
    csv = ST.to_csv([a, b], ST.CAND_COLS).decode("utf-8").splitlines()
    assert csv[1].count("000001") == 1


def test_table_names():
    assert ST.table("trial", "run") == "dtflow_shadow.trial_run"
    assert ST.table("sealed", "candidates") == "dtflow_shadow.candidates"
    with pytest.raises(ValueError):
        ST.table("x", "run")
```

- [ ] **Step 3: 실패 확인** → FAIL(import)

- [ ] **Step 4: 구현**

`dtflow_shadow/store.py`:
```python
"""저장 — 태쏘 shadow `store.py` 형태 복사(한 트랜잭션 · ON CONFLICT DO NOTHING · 충돌이면 롤백 · CSV 원장 + sha 덧붙임)."""
from __future__ import annotations

import configparser
import copy
import csv
import hashlib
import io
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

from . import settings as S

CAND_COLS = ["rule_v", "scan_date", "stock_code", "rank", "score", "run_at", "f1_orgn", "f2_prog", "f3_short",
             "f4_credit", "credit_deal_date", "credit_lag", "has_investor", "has_program", "has_short", "has_credit",
             "x_frgn", "x_prsn", "x_orgn5", "x_loan_gvrt", "x_ssts_amt_rlim", "acml_tr_pbmn", "late", "code_sha",
             "row_sha"]
RAW_COLS = ["rule_v", "scan_date", "stock_code", "kind", "vintage", "fetched_at", "rt_cd", "msg_cd", "body",
            "body_sha256"]
RUN_COLS = ["rule_v", "scan_date", "run_kind", "run_at", "status", "n_cands", "n_calls", "n_fail", "avail_investor",
            "avail_program", "avail_short", "avail_credit", "snapshot_match", "snapshot_n", "mine_n",
            "max_score_diff", "universe_date", "d_rows", "dprev_rows", "rows_sha256", "duration_ms", "code_sha",
            "error_text"]
PK = {"candidates": ("rule_v", "scan_date", "stock_code"),
      "raw": ("rule_v", "scan_date", "stock_code", "kind", "vintage"),
      "run": ("rule_v", "scan_date", "run_kind", "run_at")}
COLS = {"candidates": CAND_COLS, "raw": RAW_COLS, "run": RUN_COLS}


def table(phase: str, kind: str) -> str:
    if phase not in ("trial", "sealed") or kind not in COLS:
        raise ValueError(f"{phase}/{kind}")
    return f"{S.SCHEMA}.{'trial_' if phase == 'trial' else ''}{kind}"


def cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, float):
        return "" if v != v else repr(v)
    return str(v)


def row_sha(row: Dict[str, Any], cols: List[str]) -> str:
    keys = sorted(c for c in cols if c not in ("run_at", "code_sha", "row_sha"))
    return hashlib.sha256("\n".join(f"{c}={cell(row.get(c))}" for c in keys).encode("utf-8")).hexdigest()


def to_csv(rows: List[Dict[str, Any]], cols: List[str]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in sorted(rows, key=lambda r: tuple(cell(r.get(c)) for c in ("scan_date", "stock_code"))):
        w.writerow([cell(r.get(c)) for c in cols])
    return buf.getvalue().encode("utf-8")


def rows_sha256(cands: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(to_csv(cands, CAND_COLS)).hexdigest()


class MemoryStore:
    def __init__(self) -> None:
        self.t: Dict[str, List[Dict[str, Any]]] = {}

    def _ins(self, t: Dict[str, List[Dict[str, Any]]], name: str, kind: str, row: Dict[str, Any]) -> None:
        key = tuple(cell(row.get(c)) for c in PK[kind])
        rows = t.setdefault(name, [])
        if any(tuple(cell(r.get(c)) for c in PK[kind]) == key for r in rows):
            raise RuntimeError(f"충돌 행 있음 {name} {key}")
        rows.append(dict(row))

    def write_day(self, phase, cands, raws, run) -> None:
        staged = copy.deepcopy(self.t)
        for r in cands:
            self._ins(staged, table(phase, "candidates"), "candidates", r)
        for r in raws:
            self._ins(staged, table(phase, "raw"), "raw", r)
        self._ins(staged, table(phase, "run"), "run", run)
        self.t = staged

    def write_raws(self, phase, raws) -> None:
        staged = copy.deepcopy(self.t)
        for r in raws:
            self._ins(staged, table(phase, "raw"), "raw", r)
        self.t = staged

    def write_run(self, phase, run) -> None:
        staged = copy.deepcopy(self.t)
        self._ins(staged, table(phase, "run"), "run", run)
        self.t = staged

    def runs(self, phase) -> List[Dict[str, Any]]:
        return list(self.t.get(table(phase, "run"), []))

    def cands(self, phase, D) -> List[Dict[str, Any]]:
        return [r for r in self.t.get(table(phase, "candidates"), []) if r["scan_date"] == D]

    def any_sealed(self) -> bool:
        return any(r["status"] == "ok" for r in self.t.get(table("sealed", "run"), []))


class PgStore:
    def __init__(self, conn) -> None:
        self.conn = conn

    def _insert(self, cur, phase, kind, row) -> int:
        cols = COLS[kind]
        vals = [json.dumps(row.get(c), ensure_ascii=False) if c == "body" and row.get(c) is not None else row.get(c)
                for c in cols]
        cur.execute(f"INSERT INTO {table(phase, kind)} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                    f"ON CONFLICT DO NOTHING", vals)
        return cur.rowcount

    def _tx(self, items) -> None:
        try:
            with self.conn.cursor() as cur:
                for phase, kind, row in items:
                    if self._insert(cur, phase, kind, row) != 1:
                        raise RuntimeError(f"충돌 행 있음 {table(phase, kind)}")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def write_day(self, phase, cands, raws, run) -> None:
        self._tx([(phase, "candidates", r) for r in cands] + [(phase, "raw", r) for r in raws] + [(phase, "run", run)])

    def write_raws(self, phase, raws) -> None:
        self._tx([(phase, "raw", r) for r in raws])

    def write_run(self, phase, run) -> None:
        self._tx([(phase, "run", run)])

    def _select(self, sql, params) -> List[Dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            names = [d[0] for d in cur.description]
            out = [dict(zip(names, r)) for r in cur.fetchall()]
        self.conn.rollback()
        return out

    def runs(self, phase) -> List[Dict[str, Any]]:
        return self._select(f"SELECT {', '.join(RUN_COLS)} FROM {table(phase, 'run')} WHERE rule_v = %s", (S.RULE_V,))

    def cands(self, phase, D) -> List[Dict[str, Any]]:
        return self._select(f"SELECT {', '.join(CAND_COLS)} FROM {table(phase, 'candidates')} "
                            f"WHERE rule_v = %s AND scan_date = %s", (S.RULE_V, D))

    def any_sealed(self) -> bool:
        return bool(self._select(f"SELECT 1 AS one FROM {table('sealed', 'run')} WHERE rule_v = %s AND status = 'ok' "
                                 f"LIMIT 1", (S.RULE_V,)))


def export_ledger(rows: List[Dict[str, Any]], cols: List[str], root: Path, D: date, name: str) -> str:
    data = to_csv(rows, cols)
    sha = hashlib.sha256(data).hexdigest()
    d = Path(root) / D.isoformat()
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.{datetime.now().strftime('%Y%m%dT%H%M%S')}.csv"
    f.write_bytes(data)
    with open(Path(root) / "ledger_sha256.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{D.isoformat()}\t{name}\t{len(rows)}\t{sha}\t{f.name}\t{datetime.now().isoformat(timespec='seconds')}\n")
    return sha


def writer_password() -> str:
    cp = configparser.ConfigParser()
    cp.read(str(S.key_ini_path()), encoding="utf-8")
    if not cp.has_section("DTFLOW_SHADOW") or not cp.get("DTFLOW_SHADOW", "db_password", fallback=""):
        raise RuntimeError("key.ini [DTFLOW_SHADOW] db_password 없음")
    return cp.get("DTFLOW_SHADOW", "db_password").strip()


def connect_writer():
    import psycopg2
    from config.constants import resolve_daily_source_db
    return psycopg2.connect(host=os.getenv("TIMESCALE_HOST", "127.0.0.1"), port=int(os.getenv("TIMESCALE_PORT", "5433")),
                            dbname=resolve_daily_source_db(), user=S.WRITER_ROLE, password=writer_password())
```

`config/key.ini.example` 끝에 추가:
```ini

[DTFLOW_SHADOW]
# daytrading 수급 봉인 기록기(dtflow_shadow) 쓰기 역할 비밀번호 — ddl.sql 실행 때 같은 값을 입력
db_password=YOUR_DTFLOW_SHADOW_DB_PASSWORD_HERE
```

- [ ] **Step 5: 통과 확인** → 4 passed

- [ ] **Step 6: Commit** — `# research(dt-flow-shadow): 저장(시험/봉인 표·한 트랜잭션·충돌 롤백·CSV 원장)·DDL·key.ini.example 섹션 + 테스트 4`

---

### Task 6: `phase.py` + `alerts.py` — 시험→봉인 전환 판정 · k 선택표 · 텔레그램

**Files:**
- Create: `dtflow_shadow/phase.py` · `dtflow_shadow/alerts.py` · `dtflow_shadow/tests/test_phase.py`

**Interfaces:**
- Consumes: `store.*.runs(phase)` · 시험 후보 행(`credit_lag`)
- Produces:
  - `phase.seal_ready(trial_runs: List[Dict], trial_lags: Dict[date, List[Optional[int]]], scan_days_desc: List[date], k: Optional[int]) -> Tuple[bool, str]`
  - `phase.choose_k_table(trial_lags: Dict[date, List[Optional[int]]], ks=range(1, 7)) -> List[Tuple[int, float, float]]` — (k, 최소 일 가용률, 평균)
  - `phase.decide(store, scan_days_desc: List[date], k: Optional[int], trial_lags) -> str` — "trial" | "sealed"
  - `alerts.body(D, status, n=None) -> str` · `alerts.send(text, dry_run=False, poster=None, log=print) -> bool`

- [ ] **Step 1: 실패하는 테스트**

`dtflow_shadow/tests/test_phase.py`:
```python
from datetime import date, timedelta

from backtest.concept_axes.dtflow_shadow import alerts as A
from backtest.concept_axes.dtflow_shadow import phase as P

DAYS = [date(2026, 10, 30) - timedelta(days=i) for i in range(12)]   # 내림차순(합성 연속일)


def _runs(n_ok=10, bad_day=None, snap_bad=None):
    out = []
    for d in DAYS[:n_ok]:
        out.append(dict(scan_date=d, run_kind="record", status="ok", avail_investor=0.99, avail_program=0.99,
                        avail_short=0.99, avail_credit=None))
        out.append(dict(scan_date=d, run_kind="snapshot_check", status="ok", snapshot_match=(d != snap_bad)))
    if bad_day:
        for r in out:
            if r["scan_date"] == bad_day and r["run_kind"] == "record":
                r["avail_short"] = 0.5
    return out


LAGS = {d: [3] * 40 for d in DAYS}


def test_seal_ready_all_good():
    ok, why = P.seal_ready(_runs(), LAGS, DAYS, k=3)
    assert ok, why


def test_seal_ready_requires_k_and_consecutive_days():
    assert not P.seal_ready(_runs(), LAGS, DAYS, k=None)[0]
    assert not P.seal_ready(_runs(n_ok=9), LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(_runs(bad_day=DAYS[4]), LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(_runs(snap_bad=DAYS[2]), LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(_runs(), {d: [4] * 40 for d in DAYS}, DAYS, k=3)[0]   # 신용 가용률 0


def test_choose_k_table():
    lags = {DAYS[0]: [3, 3, 4, None], DAYS[1]: [3, 3, 3, 3]}
    t = dict((k, (mn, mean)) for k, mn, mean in P.choose_k_table(lags, ks=range(3, 5)))
    assert t[3][0] == 0.5 and t[4][0] == 0.75


def test_alert_body_and_dry_run():
    assert A.body(date(2026, 10, 12), "missed_token", 0) == "D=2026-10-12 status=missed_token n=0"
    sent = []
    assert A.send("x", dry_run=True, log=sent.append) and "[kis-dtflow-shadow] x" in sent[0]
```

- [ ] **Step 2: 실패 확인** → FAIL(import)

- [ ] **Step 3: 구현**

`dtflow_shadow/phase.py`:
```python
"""시험 → 봉인 전환 — 스펙 §4-1: 연속 10거래일 「후보 일치 100% ∧ 4종 가용률 ≥ 0.95(신용은 고정 시차 k)」.
k 가 동결되기 전(None)에는 전환하지 않는다. 한 번 봉인되면 계속 봉인(되돌리지 않음)."""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from . import settings as S


def _credit_avail(lags: List[Optional[int]], k: int) -> float:
    if not lags:
        return 0.0
    return sum(1 for v in lags if v is not None and v <= k) / len(lags)


def seal_ready(trial_runs: List[Dict], trial_lags: Dict[date, List[Optional[int]]], scan_days_desc: List[date],
               k: Optional[int]) -> Tuple[bool, str]:
    if k is None:
        return False, "신용 시차 k 미동결"
    need = scan_days_desc[:S.TRIAL_DAYS]
    if len(need) < S.TRIAL_DAYS:
        return False, "거래일 부족"
    rec = {r["scan_date"]: r for r in trial_runs if r.get("run_kind") == "record" and r.get("status") == "ok"}
    snap = {r["scan_date"]: r for r in trial_runs if r.get("run_kind") == "snapshot_check" and r.get("status") == "ok"}
    for d in need:
        r = rec.get(d)
        if r is None:
            return False, f"{d} 기록 없음"
        if min(float(r.get(c) or 0.0) for c in ("avail_investor", "avail_program", "avail_short")) < S.AVAIL_MIN:
            return False, f"{d} 가용률 미달"
        if _credit_avail(trial_lags.get(d, []), k) < S.AVAIL_MIN:
            return False, f"{d} 신용 가용률 미달"
        if not (snap.get(d) or {}).get("snapshot_match"):
            return False, f"{d} 스냅샷 불일치/없음"
    return True, "ok"


def choose_k_table(trial_lags: Dict[date, List[Optional[int]]], ks=range(1, 7)) -> List[Tuple[int, float, float]]:
    out = []
    for k in ks:
        v = [_credit_avail(lags, k) for lags in trial_lags.values()]
        out.append((k, min(v) if v else 0.0, sum(v) / len(v) if v else 0.0))
    return out


def decide(store, scan_days_desc: List[date], k: Optional[int], trial_lags) -> str:
    if store.any_sealed():
        return "sealed"
    return "sealed" if seal_ready(store.runs("trial"), trial_lags, scan_days_desc, k)[0] else "trial"
```

`dtflow_shadow/alerts.py`:
```python
"""텔레그램 경보 — 태쏘 shadow `alerts.py` 형태. key.ini [TELEGRAM] token·chat_id 를 읽기만 · 한 실행 1통 · 본문 = D·status·건수."""
from __future__ import annotations

import configparser
from datetime import date
from typing import Callable, Optional, Tuple

from . import settings as S

PREFIX = "[kis-dtflow-shadow]"


def body(D: date, status: str, n: Optional[int] = None) -> str:
    return f"D={D.isoformat()} status={status}" + (f" n={n}" if n is not None else "")


def _conf() -> Optional[Tuple[str, str]]:
    try:
        cp = configparser.ConfigParser()
        cp.read(str(S.key_ini_path()), encoding="utf-8")
        tok = cp.get("TELEGRAM", "token", fallback="").strip()
        chat = cp.get("TELEGRAM", "chat_id", fallback="").strip()
        return (tok, chat) if tok and chat else None
    except (configparser.Error, OSError):
        return None


def send(text: str, dry_run: bool = False, poster: Optional[Callable] = None, log: Callable = print) -> bool:
    msg = f"{PREFIX} {text}"[:1000]
    if dry_run:
        log(f"(dry-run 경보) {msg}")
        return True
    conf = _conf()
    if conf is None:
        log("경보 설정 없음 — 로그만")
        return False
    try:
        if poster is None:
            import requests
            poster = requests.post
        r = poster(f"https://api.telegram.org/bot{conf[0]}/sendMessage", data={"chat_id": conf[1], "text": msg}, timeout=10)
        return getattr(r, "status_code", 0) == 200
    except Exception as e:  # noqa: BLE001 — URL 에 토큰이 있으므로 예외 이름만
        log(f"경보 실패: {type(e).__name__}")
        return False
```

- [ ] **Step 4: 통과 확인** → 4 passed

- [ ] **Step 5: Commit** — `# research(dt-flow-shadow): 시험→봉인 전환 판정(연속 10일·가용률·스냅샷 일치·k 필수)·k 선택표·텔레그램 1통 + 테스트 4`

---

### Task 7: 러너 `scripts/dtflow_shadow_recorder.py` — 기록 · 스냅샷 대조 · 동결 · k 표 · dry-run

**Files:**
- Create: `RoboTrader_template/scripts/dtflow_shadow_recorder.py` · `dtflow_shadow/tests/test_recorder.py`

**Interfaces:**
- Consumes: Task 1~6 전부
- Produces:
  - CLI: `--freeze` · `--record` · `--check-snapshot` · `--choose-k` · `--dry-run --date YYYY-MM-DD --no-guard --home <dir> --archive <dir>`
  - 종료 코드: 0 정상·휴장 · 1 예외 · 2 가드 거부 · 3 잠금 사용 중
  - `run_record(ctx: Ctx) -> str`(status) · `run_snapshot(ctx: Ctx) -> str`
  - `Ctx`(dataclass) 필드: `T, now_fn, store, inputs_cur, kis_factory, code_sha, archive, log, alerts, k, dry_run`
  - status 값: `ok · late · missed_host · missed_sweep · universe_stale · missed_token · error · no_record`

- [ ] **Step 1: 실패하는 테스트**

`dtflow_shadow/tests/test_recorder.py`:
```python
import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from backtest.concept_axes.dtflow_shadow import candidates as C
from backtest.concept_axes.dtflow_shadow import kis as K
from backtest.concept_axes.dtflow_shadow import store as ST

RT = Path(__file__).resolve().parents[4]


def load_runner():
    spec = importlib.util.spec_from_file_location("dtflow_runner", RT / "scripts" / "dtflow_shadow_recorder.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeKis:
    def __init__(self, expire=False):
        self.calls, self.expire = 0, expire

    def get(self, kind, params):
        self.calls += 1
        if self.expire:
            raise K.TokenUnavailable("x")
        return {"rt_cd": "0", "output": [], "output2": []}, "2026-10-12T07:52:01"


def _ctx(R, now, kis=None, complete=True, uni_date="2026-10-08"):
    store = ST.MemoryStore()
    alerts = []
    ctx = R.Ctx(T=date(2026, 10, 12), now_fn=lambda: now, store=store, inputs_cur=None,
                kis_factory=lambda: kis or FakeKis(), code_sha="sha", archive=None, log=lambda *a: None,
                alerts=alerts, k=None, dry_run=True)
    R._prev_day = lambda cur, T: date(2026, 10, 8)
    R._d_complete = lambda cur, D: (complete and uni_date == "2026-10-08",
                                    {"d_rows": 2700, "dprev_rows": 2700, "universe_date": uni_date})
    R._compute = lambda cur, D: [C.Cand("000001", 2.5, 1), C.Cand("000002", 2.1, 2)]
    R._cal = lambda cur, D: [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 7), D]
    R._scan_days_desc = lambda cur, D: [D]
    return ctx


def test_record_ok_writes_trial_rows():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    assert R.run_record(ctx) == "ok"
    assert len(ctx.store.cands("trial", date(2026, 10, 8))) == 2
    assert ctx.store.runs("trial")[0]["n_calls"] == 8


def test_record_refuses_after_0838():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 8, 39))
    assert R.run_record(ctx) == "missed_host" and ctx.alerts


def test_record_universe_stale():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52), uni_date="2026-10-07")
    assert R.run_record(ctx) == "universe_stale" and not ctx.store.cands("trial", date(2026, 10, 8))


def test_record_missed_token_no_rows():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52), kis=FakeKis(expire=True))
    assert R.run_record(ctx) == "missed_token" and not ctx.store.cands("trial", date(2026, 10, 8))


def test_record_late_marks_rows():
    R = load_runner()
    times = iter([datetime(2026, 10, 12, 8, 37), datetime(2026, 10, 12, 8, 41)] + [datetime(2026, 10, 12, 8, 41)] * 50)
    ctx = _ctx(R, None)
    ctx.now_fn = lambda: next(times)
    assert R.run_record(ctx) == "late"
    assert all(r["late"] for r in ctx.store.cands("trial", date(2026, 10, 8)))


def test_snapshot_check_records_match():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R.run_record(ctx)
    ctx.now_fn = lambda: datetime(2026, 10, 12, 9, 5)
    R._load_snapshot = lambda cur, D: [("000001", 1, 2.5), ("000002", 2, 2.1)]
    assert R.run_snapshot(ctx) == "ok"
    snap = [r for r in ctx.store.runs("trial") if r["run_kind"] == "snapshot_check"][0]
    assert snap["snapshot_match"] is True


def test_record_vintage2_refetches_prev_day():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    prevD = date(2026, 10, 7)
    prev = {c: None for c in ST.CAND_COLS}
    prev.update(rule_v="v1", scan_date=prevD, stock_code="000009", rank=1, score=2.0, code_sha="x", late=False,
                row_sha="r")
    run = {c: None for c in ST.RUN_COLS}
    run.update(rule_v="v1", scan_date=prevD, run_kind="record", run_at="2026-10-08T07:52:00", status="ok", code_sha="x")
    ctx.store.write_day("trial", [prev], [], run)
    R._scan_days_desc = lambda cur, D: [D, prevD]
    assert R.run_record(ctx) == "ok"
    raws = ctx.store.t["dtflow_shadow.trial_raw"]
    assert sum(1 for r in raws if r["vintage"] == 2 and r["scan_date"] == prevD) == 4
    assert sum(1 for r in raws if r["vintage"] == 1) == 8          # 오늘 기록은 그대로


def test_cli_rejects_dev_flags_without_dry_run():
    R = load_runner()
    with pytest.raises(SystemExit):
        R.main(["--record", "--date", "2026-10-12"])
```

- [ ] **Step 2: 실패 확인** → FAIL(파일 없음)

- [ ] **Step 3: 구현**

`RoboTrader_template/scripts/dtflow_shadow_recorder.py`:
```python
"""daytrading 수급 4종 봉인 기록기 — 스펙 §4 · `backtest/concept_axes/dtflow_shadow/PREREG.md`.

usage:
  python scripts/dtflow_shadow_recorder.py --freeze           # 동결 커밋 detached 워크트리에서 1회
  python scripts/dtflow_shadow_recorder.py --record           # 작업 스케줄러 월~금 07:52
  python scripts/dtflow_shadow_recorder.py --check-snapshot   # 작업 스케줄러 월~금 09:05
  python scripts/dtflow_shadow_recorder.py --choose-k         # 시험 10거래일 뒤 신용 시차 표
  python scripts/dtflow_shadow_recorder.py --record --dry-run --date 2026-10-12 --no-guard --home <tmp> --archive <tmp>

🔴 봇 import 0 · KIS 조회 TR 4개 · 토큰 발급 0 · 라이브 트리 실행 거부 · 로그엔 건수·status·sha 만.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time as _time
import types
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

RT = Path(__file__).resolve().parents[1]
if str(RT) not in sys.path:
    sys.path.insert(0, str(RT))
if "backtest" not in sys.modules:
    _pkg = types.ModuleType("backtest")
    _pkg.__path__ = [str(RT / "backtest")]
    sys.modules["backtest"] = _pkg

from backtest.concept_axes.dtflow_shadow import alerts as AL      # noqa: E402
from backtest.concept_axes.dtflow_shadow import candidates as C    # noqa: E402
from backtest.concept_axes.dtflow_shadow import features as F      # noqa: E402
from backtest.concept_axes.dtflow_shadow import guard as G         # noqa: E402
from backtest.concept_axes.dtflow_shadow import kis as K           # noqa: E402
from backtest.concept_axes.dtflow_shadow import phase as PH        # noqa: E402
from backtest.concept_axes.dtflow_shadow import settings as S      # noqa: E402
from backtest.concept_axes.dtflow_shadow import store as ST        # noqa: E402
from backtest.concept_axes.dtflow_shadow.lock import LockBusy, RunnerLock   # noqa: E402

# DB 읽기 훅(테스트가 바꿔 끼운다)
_prev_day = C.prev_trading_day
_d_complete = C.d_complete
_compute = C.compute
_load_snapshot = C.load_snapshot


def _cal(cur, D: date) -> List[date]:
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE stock_code = 'KOSPI' AND date <= %s "
                "ORDER BY date DESC LIMIT 40", (D.isoformat(),))
    return sorted(date.fromisoformat(str(r[0])[:10]) for r in cur.fetchall())


def _scan_days_desc(cur, D: date) -> List[date]:
    return sorted(_cal(cur, D), reverse=True)


@dataclass
class Ctx:
    T: date
    now_fn: Callable[[], datetime]
    store: Any
    inputs_cur: Any
    kis_factory: Callable[[], Any]
    code_sha: str
    archive: Optional[Path]
    log: Callable[..., None]
    alerts: List[str] = field(default_factory=list)
    k: Optional[int] = None
    dry_run: bool = False
    t0: float = field(default_factory=_time.perf_counter)

    def ms(self) -> int:
        return int((_time.perf_counter() - self.t0) * 1000)


def _run_row(ctx: Ctx, D: date, kind: str, status: str, **kw) -> Dict[str, Any]:
    r = {c: None for c in ST.RUN_COLS}
    r.update(rule_v=S.RULE_V, scan_date=D, run_kind=kind, run_at=ctx.now_fn().isoformat(timespec="seconds"),
             status=status, code_sha=ctx.code_sha, duration_ms=ctx.ms(), **kw)
    return r


def _alert(ctx: Ctx, D: date, status: str, n: Optional[int] = None) -> None:
    ctx.alerts.append(AL.body(D, status, n))


def _trial_lags(ctx: Ctx, days: List[date]) -> Dict[date, List[Optional[int]]]:
    return {d: [r.get("credit_lag") for r in ctx.store.cands("trial", d)] for d in days}


def run_record(ctx: Ctx) -> str:
    now = ctx.now_fn()
    cur = ctx.inputs_cur
    D = _prev_day(cur, ctx.T)
    if D is None:
        return "error"
    days_desc = _scan_days_desc(cur, D)
    phase = PH.decide(ctx.store, days_desc, ctx.k, _trial_lags(ctx, days_desc[:S.TRIAL_DAYS]))
    if now.time() >= S.REFUSE_AFTER:
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "missed_host"))
        _alert(ctx, D, "missed_host")
        return "missed_host"
    ok, info = _d_complete(cur, D)
    if not ok:
        st = "universe_stale" if info.get("universe_date") != D.isoformat() else "missed_sweep"
        ctx.store.write_run(phase, _run_row(ctx, D, "record", st, universe_date=info.get("universe_date"),
                                            d_rows=info.get("d_rows"), dprev_rows=info.get("dprev_rows")))
        _alert(ctx, D, st)
        return st
    cands = _compute(cur, D)
    cal = _cal(cur, D)
    try:
        client = ctx.kis_factory()
        raws: List[Dict[str, Any]] = []
        rows: List[Dict[str, Any]] = []
        n_fail = 0
        for c in cands:
            bodies: Dict[str, dict] = {}
            for kind in S.KINDS:
                body, at = client.get(kind, K.params_for(kind, c.stock_code, D, ctx.T))
                bodies[kind] = body
                n_fail += int(str(body.get("rt_cd")) != "0")
                canon = json.dumps(body, ensure_ascii=False, sort_keys=True)
                raws.append(dict(rule_v=S.RULE_V, scan_date=D, stock_code=c.stock_code, kind=kind, vintage=1,
                                 fetched_at=at, rt_cd=str(body.get("rt_cd")), msg_cd=str(body.get("msg_cd") or ""),
                                 body=body, body_sha256=hashlib.sha256(canon.encode("utf-8")).hexdigest()))
            feat = F.compute(D, bodies, cal, ctx.k)
            r = {col: None for col in ST.CAND_COLS}
            r.update(rule_v=S.RULE_V, scan_date=D, stock_code=c.stock_code, rank=c.rank, score=c.score,
                     run_at=ctx.now_fn().isoformat(timespec="seconds"), code_sha=ctx.code_sha, **feat)
            rows.append(r)
    except K.TokenUnavailable:
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "missed_token", n_cands=len(cands)))
        _alert(ctx, D, "missed_token", len(cands))
        return "missed_token"
    late = ctx.now_fn().time() > S.SEAL_DEADLINE
    for r in rows:
        r["late"] = late
        r["row_sha"] = ST.row_sha(r, ST.CAND_COLS)
    n = max(1, len(rows))
    avail = {k: sum(1 for r in rows if r[f"has_{k}"]) / n for k in ("investor", "program", "short", "credit")}
    status = "late" if late else "ok"
    run = _run_row(ctx, D, "record", status, n_cands=len(rows), n_calls=getattr(client, "calls", len(raws)),
                   n_fail=n_fail, avail_investor=avail["investor"], avail_program=avail["program"],
                   avail_short=avail["short"], avail_credit=avail["credit"] if ctx.k is not None else None,
                   universe_date=info.get("universe_date"), d_rows=info.get("d_rows"), dprev_rows=info.get("dprev_rows"),
                   rows_sha256=ST.rows_sha256(rows))
    ctx.store.write_day(phase, rows, raws, run)
    if late:
        _alert(ctx, D, "late", len(rows))
    if ctx.archive is not None:
        ST.export_ledger(rows, ST.CAND_COLS, ctx.archive / phase, D, "candidates")
    _vintage2(ctx, client, days_desc)
    return status


def _vintage2(ctx: Ctx, client, days_desc: List[date]) -> None:
    """판정 미사용 — 직전 스캔일 D′ 후보의 같은 D′ 값을 오늘 아침 다시 받아 원문만 저장(«아침 값 = 최종값» 비율 인쇄용).
    봉인 «뒤»에 따로 돌고, 실패해도 그날 기록 결과는 바뀌지 않는다."""
    if len(days_desc) < 2 or ctx.now_fn().time() >= S.REFUSE_AFTER:
        return
    pD = days_desc[1]
    pphase = "sealed" if ctx.store.cands("sealed", pD) else "trial"
    prev = ctx.store.cands(pphase, pD)
    if not prev:
        return
    try:
        v2: List[Dict[str, Any]] = []
        for r in prev:
            for kind in S.KINDS:
                body, at = client.get(kind, K.params_for(kind, r["stock_code"], pD, ctx.T))
                canon = json.dumps(body, ensure_ascii=False, sort_keys=True)
                v2.append(dict(rule_v=S.RULE_V, scan_date=pD, stock_code=r["stock_code"], kind=kind, vintage=2,
                               fetched_at=at, rt_cd=str(body.get("rt_cd")), msg_cd=str(body.get("msg_cd") or ""),
                               body=body, body_sha256=hashlib.sha256(canon.encode("utf-8")).hexdigest()))
        ctx.store.write_raws(pphase, v2)
    except Exception as e:  # noqa: BLE001 — 보조 수집 · 기록 결과 불변
        ctx.log(f"vintage2 실패(무시): {type(e).__name__}")


def run_snapshot(ctx: Ctx) -> str:
    cur = ctx.inputs_cur
    D = _prev_day(cur, ctx.T)
    phase = "sealed" if ctx.store.cands("sealed", D) else "trial"
    mine = [C.Cand(r["stock_code"], float(r["score"]), int(r["rank"])) for r in ctx.store.cands(phase, D)]
    if not mine and not any(r["scan_date"] == D and r["run_kind"] == "record" and r["status"] == "ok"
                            for r in ctx.store.runs(phase)):
        ctx.store.write_run(phase, _run_row(ctx, D, "snapshot_check", "no_record"))
        _alert(ctx, D, "no_record")
        return "no_record"
    m = C.compare(sorted(mine, key=lambda c: c.rank), _load_snapshot(cur, D))
    ctx.store.write_run(phase, _run_row(ctx, D, "snapshot_check", "ok", snapshot_match=m["match"],
                                        snapshot_n=m["snapshot_n"], mine_n=m["mine_n"],
                                        max_score_diff=m["max_score_diff"]))
    if not m["match"]:
        _alert(ctx, D, "snapshot_mismatch", m["mine_n"])
    return "ok"


def run_choose_k(ctx: Ctx) -> None:
    D = _prev_day(ctx.inputs_cur, ctx.T)
    days = _scan_days_desc(ctx.inputs_cur, D)[:S.TRIAL_DAYS]
    for k, mn, mean in PH.choose_k_table(_trial_lags(ctx, days)):
        print(f"k={k} · 최소 일 가용률 {mn:.3f} · 평균 {mean:.3f}")


def main(argv: Optional[List[str]] = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="dtflow shadow recorder")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", action="store_true")
    g.add_argument("--record", action="store_true")
    g.add_argument("--check-snapshot", action="store_true")
    g.add_argument("--choose-k", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--no-guard", action="store_true")
    ap.add_argument("--home")
    ap.add_argument("--archive")
    a = ap.parse_args(argv)
    if (a.date or a.no_guard or a.home or a.archive) and not a.dry_run:
        ap.error("--date/--no-guard/--home/--archive 는 --dry-run 과 함께만")
    if a.freeze:
        fr = G.write_frozen(S.REPO_ROOT)
        print(f"동결 {fr.code_sha[:10]} · k={fr.credit_lag_k}")
        return 0
    code_sha = "dry-run"
    if not (a.dry_run and a.no_guard):
        try:
            G.refuse_live_tree(__file__)
            fr = G.load_frozen()
            code_sha = G.check_runtime(S.REPO_ROOT, fr)
        except G.GuardError as e:
            AL.send(f"guard_refused {type(e).__name__}", dry_run=a.dry_run)
            print(f"가드 거부: {e}")
            return 2
    T = date.fromisoformat(a.date) if a.date else datetime.now().date()
    try:
        from utils.korean_holidays import is_holiday
        if T.weekday() >= 5 or is_holiday(datetime(T.year, T.month, T.day)) or (T.month, T.day) == (12, 31):
            print(f"[휴장] {T}")
            return 0
    except ImportError:
        pass
    if a.record and not a.dry_run and datetime.now().time() < S.START_NOT_BEFORE:
        print("시작 시각 전 — 거부")
        return 2
    lk = RunnerLock(Path(a.home or S.home_dir()) / "runner.lock", owner="record" if a.record else "other")
    try:
        lk.acquire()
    except LockBusy:
        return 3
    try:
        from backtest.concept_axes.replayer.loader import dsn
        import psycopg2
        rconn = psycopg2.connect(**dsn())
        rconn.set_session(readonly=True)
        cur = rconn.cursor()
        store = ST.MemoryStore() if a.dry_run else ST.PgStore(ST.connect_writer())

        def kis_factory():
            conf = K.read_kis_conf(S.key_ini_path())
            tok = K.read_token(S.token_path(), datetime.now())
            return K.Client(conf["base_url"], tok, conf["appkey"], conf["appsecret"])
        now_fn = (lambda: datetime.combine(T, datetime.now().time())) if a.dry_run else datetime.now
        ctx = Ctx(T=T, now_fn=now_fn, store=store, inputs_cur=cur, kis_factory=kis_factory, code_sha=code_sha,
                  archive=Path(a.archive) if a.archive else (None if a.dry_run else S.archive_dir()),
                  log=print, k=S.CREDIT_LAG_K, dry_run=a.dry_run)
        if a.record:
            st = run_record(ctx)
        elif a.check_snapshot:
            st = run_snapshot(ctx)
        else:
            run_choose_k(ctx)
            st = "ok"
        print(f"status={st}")
        return 0
    except Exception as e:  # noqa: BLE001
        AL.send(f"error {type(e).__name__}", dry_run=a.dry_run)
        print(f"예외: {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            if ctx.alerts:
                AL.send(" | ".join(ctx.alerts), dry_run=a.dry_run)
        except NameError:
            pass
        lk.release()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과 확인** — `$PY -m pytest backtest/concept_axes/dtflow_shadow/tests -q` → 전부 passed(누계 32)

  `test_record_late_marks_rows` 가 now_fn 호출 횟수에 따라 깨지면 now_fn 호출 지점(시작 1회 · 행 시각 · late 판정)을 세고 이터레이터 길이를 맞춘다. late 판정 로직은 바꾸지 않는다.

- [ ] **Step 5: Commit** — `# research(dt-flow-shadow): 러너(07:52 기록·vintage 2·09:05 스냅샷 대조·동결·k 표·dry-run · 시작 거부·late·missed_token·universe_stale) + 테스트 8`

---

### Task 8: 작업 스케줄러 스크립트(실행 안 함) · 실 DB dry-run(KIS 0)

**Files:**
- Create: `dtflow_shadow/register_tasks.ps1` · `dtflow_shadow/unregister_tasks.ps1`

- [ ] **Step 1: 등록 스크립트(실행은 Task 10 사장님 확인 뒤)**

`dtflow_shadow/register_tasks.ps1`:
```powershell
# dtflow shadow 작업 2개 등록 — 🔴 사장님 확인 뒤에만 실행. 실행 워크트리 = 동결 커밋 detached.
$py = "D:\GIT\kis-trading-template\RoboTrader_template\venv\Scripts\python.exe"
$wt = "D:\tmp\kis-wt-dtflow-run"
$script = "RoboTrader_template\scripts\dtflow_shadow_recorder.py"
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$pr = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 07:52
$a1 = New-ScheduledTaskAction -Execute $py -Argument "$script --record" -WorkingDirectory $wt
Register-ScheduledTask -TaskName "kis-dtflow-shadow-record" -Trigger $t1 -Action $a1 -Settings $set -Principal $pr
$t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:05
$a2 = New-ScheduledTaskAction -Execute $py -Argument "$script --check-snapshot" -WorkingDirectory $wt
Register-ScheduledTask -TaskName "kis-dtflow-shadow-snapshot" -Trigger $t2 -Action $a2 -Settings $set -Principal $pr
```

`dtflow_shadow/unregister_tasks.ps1`:
```powershell
Unregister-ScheduledTask -TaskName "kis-dtflow-shadow-record" -Confirm:$false
Unregister-ScheduledTask -TaskName "kis-dtflow-shadow-snapshot" -Confirm:$false
```

- [ ] **Step 2: 실 DB dry-run(읽기 전용 · KIS 호출 없이 후보 복제만 확인)**

임시 확인 스크립트(커밋 안 함 · 세션 scratchpad)를 만든다. 지난 거래일 D 1개에 대해 아래만 출력한다:
- `C.compute(cur, D)` 의 종목 수·상위 5
- `C.load_snapshot(cur, D)` 의 종목 수·상위 5
- `C.compare(...)` 결과

> DOSSIER_B §0-4 대로 지난날 재계산은 sweep 때문에 정확히 일치하지 **않을 수 있다**(종목 수 ±4·점수 차). 이 단계의 합격 기준은 «SQL·룰이 돌아가고 집합 대부분이 겹친다» 이다. 100% 일치는 Task 11 전향 시험에서 본다.

- [ ] **Step 3: Commit** — `# research(dt-flow-shadow): 작업 스케줄러 등록·해제 스크립트(미실행) — 07:52 기록 · 09:05 스냅샷`

---

### Task 9: 사전등록 `PREREG.md` 초안 → critic → 🔒 사장님 동결(A 와 묶음) → REGISTRY

**Files:**
- Create: `dtflow_shadow/PREREG.md`
- Modify: `backtest/concept_axes/REGISTRY.md`(행 1 · 주 검정 4)

- [ ] **Step 1: 초안** — 아래 절을 빠짐없이(값은 `settings.py`·스펙 §4):

| 절 | 내용 |
|---|---|
| §0 | 사장님 결정 원문(스펙 §0) · 09-24 면제 문장 |
| §1 | 가설 4개(방향 고정): ① 기관 하위 20% · ② 프로그램 하위 20% · ③ 공매도 상위 20% · ④ 신용 상위 20% 가 나머지보다 net 수익이 낮다 |
| §2 | 기록 규칙(07:52 · 08:40 · 미도착 NULL · late 제외 · vintage 2 는 판정 미사용) |
| §3 | 특징 정의·단위(스펙 §4-3 표) · k 결정 규칙 = 「시험 10거래일에서 최소 일 가용률 ≥ 0.95 인 가장 작은 k」 · 동결 1회 |
| §4 | 시험→봉인 전환 조건(스펙 §4-1) |
| §5 | 판정(스펙 §4-5): 표본 · K2 · Holm m=4 · 가짜 게이트 · 라벨 문장 · 60+10 블라인드 점검 · 연장 공식 · 120(250)+10 개봉 |
| §6 | 한계(스펙 §7) |
| §7 | 동결 전 본 것 — `feature_study` 기관/외국인 itd5 인쇄 · 전문가 패널 수급 상관(0.968 등) · DOSSIER_B 실측 |
| §8 | KIS 호출 = 태쏘 shadow 「KIS 0」 원칙에서의 이탈 선언 |
| 부록 | `ddl.sql` 전문 |

- [ ] **Step 2: critic 1패스**(opus) → 블로커 반영.
- [ ] **Step 3: 🔒 사장님 동결** — A 사전등록·DDL 적용·작업 등록과 **한 번에** 묶어 요청한다(쉬운 한 장 먼저).
- [ ] **Step 4: 동결 커밋** — `# docs(prereg): dt-flow-shadow B 사전등록 동결 — 수급 4종 봉인 기록(🔒 사장님 <날짜> 「…」)`
- [ ] **Step 5: REGISTRY 행** — `| **DF2** | [PREREG](dtflow_shadow/PREREG.md) | daytrading_3methods_breakout | 수급 4종 꼬리 20% | ⚪ 탐색 열 | **4** | ✅ 동결 <날짜> · <SHA> |` · 총계는 «한 push 연속 마지막 커밋»에서 갱신(규칙 3 · DF1·TN1·SR1·테마 층과 충돌 → 나중 머지 쪽이 다시 셈).

---

### Task 10: 🔒 사장님 확인 뒤 — DDL 적용 · 비밀번호 · 운영 워크트리 · 동결 · 작업 등록

- [ ] **Step 1: key.ini 비밀번호** — 사장님이 라이브 `config/key.ini` 에 `[DTFLOW_SHADOW] db_password=<값>` 을 넣는다. 관리자는 값을 보지 않는다.
- [ ] **Step 2: DDL 1회**

```bash
"C:/Program Files/PostgreSQL/16/bin/psql" -h 127.0.0.1 -p 5433 -U postgres -d kis_template -f RoboTrader_template/backtest/concept_axes/dtflow_shadow/ddl.sql
```
이어서 SELECT 로 표 6개·권한을 확인한다.

- [ ] **Step 3: 운영 워크트리 + 동결**

```bash
git -C D:/GIT/kis-trading-template worktree add --detach D:/tmp/kis-wt-dtflow-run <동결 code_sha>
cd D:/tmp/kis-wt-dtflow-run
$PY RoboTrader_template/scripts/dtflow_shadow_recorder.py --freeze
```

- [ ] **Step 4: 장 전 수동 1회(시험 표에 기록 · KIS 조회 약 160회)** — 사장님 확인한 날 07:52~08:30 에 `--record` 1회 → `trial_run` status·가용률 확인 → 09:05 `--check-snapshot` → `snapshot_match` 확인.
- [ ] **Step 5: 작업 등록** — `register_tasks.ps1` 실행 → `Get-ScheduledTask kis-dtflow-shadow-*` 로 State=Ready 를 확인한다.

---

### Task 11: 0단계 — 시험 10거래일 → k 결정 → 재동결 → 봉인 자동 시작

- [ ] **Step 1: 매일 확인(EOD 보고서 한 줄)** — `trial_run` 에서:
  - record status
  - 4종 가용률
  - snapshot_match
  - late·missed_* 건수
- [ ] **Step 2: 10거래일 뒤 k 표** — `--choose-k` 출력으로 규칙(§3)에 맞는 k 를 고른다.
  - 0.95 를 만족하는 k 가 없으면 멈추고 사장님께 보고한다(특징 ④ 제외 개정 여부).
- [ ] **Step 3: k 동결 커밋 → 재동결**
  - `settings.CREDIT_LAG_K = <k>` 를 커밋한다: `# research(dt-flow-shadow): 신용 시차 k=<k> 동결(시험 10거래일 최소 가용률 <x>)`
  - 운영 워크트리를 새 커밋으로 `git switch --detach` → `--freeze`
  - 다음 07:52 실행부터 `phase.decide` 가 조건을 보고 봉인으로 넘어간다.
- [ ] **Step 4: 봉인 시작 확인** — 첫 `dtflow_shadow.run` status ok 행이 생긴 날을 기록하고 사장님께 보고한다(블라인드 점검·판정 예정일 함께).
- [ ] **Step 5: 메모리·NEXT_SESSION 갱신** — 봉인 시작일 · 60+10 블라인드 점검일 · 120+10 판정일(거래일 달력으로 계산).
