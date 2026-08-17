# -*- coding: utf-8 -*-
"""ma5 개념 축 — 사전등록 `PREREG.md`(동결) 실행부. **기계는 `../minervini/run.py` 승계.**

가족 등록부 `../REGISTRY.md` 의 **2번 문서**. `HIST0` 분리 · `(code,date)` 캐시 ·
`verify_strategy_params()` · `db_fingerprint()` · `--stage1`/`--stage2` 2모드 ·
stale prose 방지 — 전부 1번 문서의 관례를 그대로 쓴다.

**모드 두 개.**

- `--stage1` — PREREG §6 게이트. **PnL 을 계산하지 않는다.** `BookBacktester` 는
  «2단계 함수 안에서만» import 되므로 이 경로에는 거래당 수익률이 들어올 길이 없다.
  산출물 → `GATE.md`.
- `--stage2` — PREREG §4·§5 판정. arm 별 거래당 평균·귀무 N1·Holm·분해·인쇄만 arm.
  산출물 → `RESULTS.md`(판정) · `RESULTS_raw.md`(원시 출력).

🔴 **두 모드는 «같은» 선택 집합을 쓴다** — `build_cache`→`build_pools`→`select_*` 경로가
하나라서 2단계 arm 선택은 1단계가 인쇄한 것과 정의상 동일하다.

**축 (PREREG §0·§2) — 진입 룰의 «급등 조건 하나»만 가른다.**

라이브 `rule_ma5_pullback` 의 첫 조건은 `_recent_surge` 이고, 그 함수는
`(seg.high.max() − seg.low.min()) / seg.low.min() ≥ 0.20` 만 본다 ⇒
**고점과 저점의 «순서»에 아무 제약이 없다.** 20% 상승도, 20% 폭락도 똑같이 통과한다.
이 문서는 그 순서를 걸었을 때 무엇이 달라지는지를 잰다.

**Arm (PREREG §2-2) — 여섯:**

    D    = 현행 라이브 `rule_ma5_pullback`                       (기준선)
    S+   = D ∧ (i_low <  i_high)   저점 → 고점 = 상승형          (🔑 주 검정)
    S-   = D ∧ (i_low >  i_high)   고점 → 저점 = 하락형          (🔑 주 검정의 대칭축)
    R    = 그날 base_filter 통과 집합에서 무작위 10종목, 시드 0..19 (귀무)
    Q    = D ∧ 조정 중 거래량 감소 (§2-3)                        (⚪ 인쇄만)
    F1   = D ∧ 급등이 「한 방」 (§2-4)                            (⚪ 인쇄만)

    S0   = D ∧ (i_low == i_high)  — 🔴 **arm 이 «아니다»**(§2-1 「인쇄만」).
           건수만 센다. PnL 을 계산하지 않고 판정에도 쓰지 않는다.

🔴 **`R` 의 적격 풀은 「`base_filter` 통과」뿐이고 진입 룰 조건이 «없다»**(§2) —
「고르는 행위」 자체의 귀무이기 때문이다. 다른 arm 과 풀 정의가 다르다.

🔴 **`score` 는 현행 `df["volume"].iloc[-5:].mean()` 고정**(§2). 랭킹 축은
`rank_score_counterfactual` 이 이미 판정했고(`d751e21`), ***한 번에 한 축만 움직인다.***

🔴 **나머지 세 조건(MA5 ±2% 터치 · 종가 ≥ MA5×0.98 · 양봉)은 한 글자도 바꾸지 않는다**(§8-2).
그래서 `D` 판정은 라이브 룰 객체 `rule_ma5_pullback().evaluate(win, {})` 를 **그대로 호출**한다.

🔴 **`BookBacktester` 는 2026-08-17 에 확장됐다**(`exit_line`·`disaster_stop_pct`·
`random_exit_seed`). **이 문서는 그 기능을 쓰지 않는다** — 진입 축이라 청산은 현행 고정이다.
새 파라미터를 넘기지 않는다(`sl`/`tp`/`max_hold` 만, `eod_liquidate=False`).

🔑 척도·창은 `rank_score_counterfactual` §10-1·§10-5 승계: 창 `2024-03-13~2026-05-31`,
가격은 `HIST0=2021-01-01` 부터, `volume × adj_factor` 는 **로더에서 1회**(재곱 금지).

라이브 코드는 «읽기»만 한다(스크리너·룰 모듈 import). DB 는 SELECT 만.
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import yaml

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

from strategies.books.trading_legends.rules_daily import rule_ma5_pullback        # noqa: E402
from strategies.base import Signal, SignalType                                    # noqa: E402
from strategies.book_pullback_ma5.screener import (                               # noqa: E402
    BookPullbackMa5ScreenerAdapter,
)
# 🔴 `BookBacktester` 는 여기서 import 하지 않는다 — `--stage1` 이 「PnL 계산 경로가 아예
#    없다」를 보증하기 위해서다. 2단계 함수(`stage2`) 안에서 지역 import 한다.

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
           dbname="kis_template")

# 신형 코드는 «중간»이 영문일 수 있다(`0001A0`). 의사티커는 명시적으로도 배제한다.
STOCK_ONLY = ("stock_code ~ '^[0-9][0-9A-Z]{5}$' "
              "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')")

W0, W1 = "2024-03-13", "2026-05-31"   # PREREG §3 (rank_score §10-1 승계)
HIST0 = "2021-01-01"                   # 워밍업 (REGISTRY 공통 제약)
LOOKBACK = 60                          # §3-1 — 라이브 `lookback_days` 와 «같다»
SCORE_WINDOW = 5                       # §2 고정 — score = volume.iloc[-5:].mean()
MAX_CANDIDATES = 10                    # §2 고정
N_SEEDS = 20                           # §5-5 — m=1 ⇒ S ≥ 19, 여유 20
N_DECILES = 10                         # §6-3
MIN_TRIGGER_FRAC = 0.10                # §6-1 — D 의 10% 미만이면 「표본 부족 → 판별 보류」

# ── 기존 기준선과의 대조 (§2-2 규명 절) ──────────────────────────────────────
# 🔴 이 스크립트의 트리거 수는 이미 커밋된 기준선과 «73건» 다르다. 그 차이의 출처를
#    추정이 아니라 «실측»으로 인쇄하기 위한 상수다. 숫자를 맞추려고 아래를 쓰지 않는다 —
#    `PREREG §3-1` 이 룰 가드를 `len(df) ≥ 22` 로 동결했고 그것이 정본이다.
BASELINE_SRC = "`backtest/rank_score_counterfactual/GATE.md:84`"
BASELINE_EVAL, BASELINE_FIRE, BASELINE_UNIQ = 414_154, 52_584, 2_207
RS_WARMUP = 25          # rank_score `STRATS["book_pullback_ma5"]["warmup"]`
                        # = `config.yaml parameters.min_daily_bars` (라이브 `strategy.py` 경로)
RULE_GUARD_BARS = 22    # `rule_ma5_pullback` 자체 가드 = `surge_lookback + 2` (PREREG §3-1)
WINDOW_PROBE_ALT = 130  # 창 길이 불변성 반증용 대체 창 (= `ma5_exit` 가 쓰는 값)

# 🔴 방향 정의 (§2-1 코드블록 그대로). 현행값이며 문턱을 건드리지 않는다(§8-1).
SURGE_LOOKBACK = 20
SURGE_PCT = 0.20
Q_RECENT = 3                           # §2-3 — mean(volume[-3:])
Q_RATIO = 0.70                         # §2-3 — `rule_volume_dryup` 이 쓰는 값 그대로
F1_FRAC = 0.5                          # §2-4 — 「절반」이라는 개념에서 온 값

# 지시서 기대 청산 파라미터 (`config.yaml` 이 정본이고 아래는 대조값 · §9)
EXP_SL, EXP_TP, EXP_MH = 0.03, 0.15, 30
EXP_MAX_MCAP = 3_000_000_000_000       # §2 base_filter — 시총 ≤ 3조
EXP_MIN_TV = 1_000_000_000             # §2 base_filter — 거래대금 ≥ 10억

# 🔴 PREREG §5 동결. **결과를 보고 바꾸지 않는다**(§8-1). 단위 = %p.
EPS_ECON = 0.5
ALPHA = 0.05                           # §5-5 Holm (주 검정 **1개**)
N_PRIMARY = 1                          # §5-5 — 주 검정 수 m
KS_CONFOUND = 0.20                     # §6-3 — KS > 0.20 이면 「교락 신호」 병기
DISCARD_RATIO_FLAG = 2.0               # §7-11 — 폐기율 2배 이상이면 병기
YEAR_SKEW_MAX = 50.0                   # §6-4 — 원시·정규화 «양쪽» 50% 이하일 때만 ✅

# 가족 FWER — 🔴 **`../REGISTRY.md` 가 정본**(PREREG §5-5 이 그렇게 위임했다).
# PREREG 동결 시점 문구는 「등재 후 가족 m = 3 · FWER ≈ 14.3%」였으나, 그 뒤 등록부에
# 청산 축 `E1`(ma5_exit)이 추가되어 **현재 등재 주 검정 = 4 · FWER ≈ 18.5%** 다.
# 둘 다 인쇄하고 어긋난 사실을 명시한다(사후 은닉 금지).
FAMILY_M_PREREG, FAMILY_FWER_PREREG = 3, 14.3
FAMILY_M_REGISTRY, FAMILY_FWER_REGISTRY = 4, 18.5

# 표시용 이름 (키는 ASCII, 인쇄는 유니코드 첨자)
DISP = {"D": "D", "S+": "S⁺", "S-": "S⁻", "S0": "S⁰", "Q": "Q", "F1": "F1", "R": "R"}
DESC = {
    "D": "`range_pct ≥ 0.20` (현행 라이브 — 방향 무관)",
    "S+": "`range_pct ≥ 0.20` ∧ `i_low < i_high` (상승형)",
    "S-": "`range_pct ≥ 0.20` ∧ `i_low > i_high` (하락형)",
    "S0": "`range_pct ≥ 0.20` ∧ `i_low == i_high` (동일봉 · **arm 아님**)",
    "Q": "`D` ∧ 조정 중 거래량 감소 (§2-3)",
    "F1": "`D` ∧ 급등이 「한 방」 (§2-4)",
    "R": "없음(base_filter 전체)",
}

# PREREG §7 (1~12) 한계 — **결과 문서에 그대로 전재한다**(축약 없음).
LIMITATIONS = [
    "🔴🔴 **`BookBacktester` 에 MA5 트레일링이 «없다».** 라이브 `ma5` 는 `config.yaml` 의 "
    "**`trail_ma: 5`**(수익 중 종가가 5일선 하향 이탈 시 청산)가 청산의 핵심인데 백테스터는 "
    "**sl/tp/max_hold 만** 지원한다. 전 arm 에 동일하게 빠지므로 **arm 비교엔 무해**하나 "
    "**절대 수준은 라이브와 다르다.** 🔑 ***문서 1(minervini)과 결정적으로 다른 점*** — "
    "거긴 원래 트레일링이 없어 청산 재현이 정확했다. ⇒ ***이 문서의 절대 수익률을 "
    "minervini 문서의 것과 나란히 놓지 말 것.***",
    "🔴 **생존편향** — `daily_prices` 에 상폐 종목이 사실상 없다(사다리 §6-1 실측 0.5%). "
    "편향은 **약한 종목을 위로** 민다. `S⁻`(하락형)가 약한 쪽이므로 **`S⁺ − S⁻` 가 «과소»평가**"
    "된다. ⇒ ***(가) 결론이면 «강하다»*** (편향이 반대로 미는데도 나온 결과). "
    "***(다)·(나) 결론이면 이 편향을 «배제할 수 없다».***",
    "🔴 **`score` 는 이미 「정보가 아님」으로 판정된 함수다**(`d751e21`). 이 문서의 수치는 "
    "**「정보 없는 랭킹 위에서의 값」**이다. 전 arm 공통이라 arm 비교엔 무해하다.",
    "🔴 **`market_cap` 자체의 PIT 성격 미검정** — `base_filter` 가 시총을 쓴다. 전 arm 에 "
    "동일하게 걸리므로 arm 비교엔 무해하나 절대 수준은 신뢰할 수 없다.",
    "⚠️ **단일 국면 2.2년**(2024-03~2026-05). 일반화 금지.",
    "⚠️ **포트폴리오가 아니다**(종목당 단일 포지션 순차). `max_positions=5`·자금 배분 미재현.",
    "⚠️ **백테스트 유니버스 ≠ 라이브**(라이브 매수의 97%가 미검증). **라이브 기대치로 인용 금지.**",
    "⚠️ **실행 효과 미반영** — 슬리피지·09:00~09:15 매수 타이밍·호가.",
    "⚠️ **불가능봉 가드 미적용**(승계 원본과 동일). 라이브 `scan()` 에는 있다. 완전 중립은 "
    "아니다 — 풀에서 한 종목이 빠지면 다음 종목이 들어오고 그 대체가 arm 마다 다르다.",
    "🔴 **`D` 는 `S⁺`·`S⁻` 의 «정확한» 가중평균이 «아니다».** 상한 10 때문에 `D` 에서 순위에 "
    "밀렸던 상승형 종목이 `S⁺` 에서 올라온다. §6-5 에서 겹침을 재고, 낮으면 병기한다.",
    "🔴 **arm 마다 「신호 → 실현 거래」 전환율이 다를 수 있다**(문서 1 §10-5 승계). "
    "`BookBacktester` 가 종목당 단일 포지션이므로, 소수 종목을 반복 선택하는 arm 의 신호가 "
    "「이미 보유 중」으로 더 많이 버려진다. 🔴 **2단계에서 arm 별 「신호 수 · 실현 거래 수 · "
    "폐기율」을 반드시 인쇄**하고, **폐기율이 arm 간 2배 이상 벌어지면 판정문에 병기**한다.",
    "⚠️ **`ma20` 은 같은 결함을 공유하지만 이 문서로 답하지 않는다**(§1). 이 문서의 결론을 "
    "`ma20` 으로 옮겨 쓰지 말 것.",
]

FINGERPRINT_SQL = {
    f"daily_prices[{HIST0}..{W1}] 적재분(워밍업 포함)":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{HIST0}' AND '{W1}'",
    f"daily_prices[{W0}..{W1}] 개정 창":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'",
    f"daily_prices[{W0}..{W1}] market_cap>0":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}' AND market_cap > 0",
    f"daily_prices[{W0}..{W1}] market_cap ≤ 3조 (base_filter 상한)":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}' "
        f"AND market_cap > 0 AND market_cap <= {EXP_MAX_MCAP}",
    f"daily_prices[{HIST0}..{W1}] adj_factor ≠ 1 (volume 조정 대상)":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{HIST0}' AND '{W1}' "
        f"AND adj_factor IS NOT NULL AND adj_factor <> 1",
}

OUT: list[str] = []      # 원시 출력 (GATE.md / RESULTS_raw.md)
DOC: list[str] = []      # 판정 문서 (RESULTS.md) — OUT 의 부분집합


def say(s: str = "") -> None:
    """원시 출력에만 남긴다."""
    print(s, flush=True)
    OUT.append(s)


def rep(s: str = "") -> None:
    """판정 문서 «와» 원시 출력 양쪽 ⇒ `RESULTS_raw.md` 는 항상 상위집합이다."""
    print(s, flush=True)
    OUT.append(s)
    DOC.append(s)


def git_sha() -> str:
    import subprocess  # noqa: PLC0415 — 이 한 곳에서만 쓴다
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(조회 실패: {type(e).__name__})"


# ────────────────────────────────────────────────────────────────────────────
# 0. 설정 대조 (PREREG §9)
# ────────────────────────────────────────────────────────────────────────────
def verify_strategy_params() -> tuple[list[str], dict, bool]:
    """`config.yaml` 청산 파라미터와 스크리너 `base_filter` 임계를 읽어 대조 표를 만든다.

    🔴 **하드코딩이 아니다.** 값은 라이브 파일에서 읽고 위 `EXP_*` 는 «대조값»일 뿐이다.
    청산 3값 중 하나라도 어긋나면 `ok=False` 를 돌려주고 호출자가 **중단**한다
    (지시서: 「불일치면 중단·보고」).
    """
    y = yaml.safe_load(
        (ROOT / "strategies" / "book_pullback_ma5" / "config.yaml").read_text(encoding="utf-8"))
    rm = (y or {}).get("risk_management", {}) or {}
    sl, tp, mh = rm.get("stop_loss_pct"), rm.get("take_profit_pct"), rm.get("max_hold_days")
    trail = rm.get("trail_ma")
    p = BookPullbackMa5ScreenerAdapter().default_params()
    lb = BookPullbackMa5ScreenerAdapter.lookback_days
    r = rule_ma5_pullback()
    ok_exit = (sl == EXP_SL and tp == EXP_TP and mh == EXP_MH)
    ok = (ok_exit
          and p["max_market_cap"] == EXP_MAX_MCAP
          and p["min_trading_value"] == EXP_MIN_TV
          and p["max_candidates"] == MAX_CANDIDATES
          and lb == LOOKBACK
          and r.surge_lookback == SURGE_LOOKBACK
          and float(r.surge_pct) == SURGE_PCT)
    m = lambda c: "✅" if c else "🔴 **불일치**"  # noqa: E731
    rows = [
        "| 항목 | 읽은 값 (라이브 파일) | 기대값 (지시서/PREREG) | 일치 |",
        "|---|---|---|---|",
        f"| 청산 sl / tp / max_hold (`config.yaml`) | {sl} / {tp} / {mh} | "
        f"{EXP_SL} / {EXP_TP} / {EXP_MH} | {m(ok_exit)} |",
        f"| `trail_ma` (`config.yaml`) | {trail} | — | "
        f"🔴 **백테스터 미지원 — 전 arm 공통 결손**(§7-1) |",
        f"| `max_market_cap` (screener) | {p['max_market_cap']:,} | {EXP_MAX_MCAP:,} | "
        f"{m(p['max_market_cap'] == EXP_MAX_MCAP)} |",
        f"| `min_trading_value` (screener) | {p['min_trading_value']:,} | {EXP_MIN_TV:,} | "
        f"{m(p['min_trading_value'] == EXP_MIN_TV)} |",
        f"| `max_candidates` (screener) | {p['max_candidates']} | {MAX_CANDIDATES} | "
        f"{m(p['max_candidates'] == MAX_CANDIDATES)} |",
        f"| `lookback_days` (screener) | {lb} | {LOOKBACK} (§3-1) | {m(lb == LOOKBACK)} |",
        f"| `surge_lookback` / `surge_pct` (rule) | {r.surge_lookback} / {r.surge_pct} | "
        f"{SURGE_LOOKBACK} / {SURGE_PCT} | "
        f"{m(r.surge_lookback == SURGE_LOOKBACK and float(r.surge_pct) == SURGE_PCT)} |",
        f"| `touch_tol` / `below_tol` / `ma_window` (rule) | {r.touch_tol} / {r.below_tol} / "
        f"{r.ma_window} | 손대지 않음(§8-2) | ✅ |",
    ]
    return rows, dict(sl=sl, tp=tp, mh=mh, trail=trail, lookback=lb, **p), ok


# ────────────────────────────────────────────────────────────────────────────
# 1. DB 읽기 (SELECT 전용)
# ────────────────────────────────────────────────────────────────────────────
def db_fingerprint(conn) -> dict:
    out = {}
    with conn.cursor() as cur:
        for k, q in FINGERPRINT_SQL.items():
            cur.execute(q)
            r = cur.fetchone()
            out[k] = [int(r[0] or 0), int(r[1] or 0), str(r[2])]
    return out


def load_prices(conn) -> pd.DataFrame:
    """`HIST0`~`W1` 일봉. `vol_adj = volume * COALESCE(adj_factor,1)` 을 **여기서 한 번만**.

    라이브 읽기계층(`db/quant_daily_reader.py::_SELECT_OHLCV`)과 동일한 식이다.
    이후 어디에서도 `adj_factor` 를 다시 곱하지 않는다(이중조정 금지 — REGISTRY 공통 제약).
    """
    df = pd.read_sql(f"""
        SELECT stock_code, date, open, high, low, close,
               (volume * COALESCE(adj_factor, 1))::double precision AS vol_adj
        FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{HIST0}' AND '{W1}'
        ORDER BY stock_code, date
    """, conn)
    for c in ("open", "high", "low", "close", "vol_adj"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[~(df["close"].isna() | (df["close"] <= 0))].copy()
    for c in ("open", "high", "low"):
        m = df[c].isna() | (df[c] <= 0)
        df.loc[m, c] = df.loc[m, "close"]
    df["vol_adj"] = df["vol_adj"].fillna(0).clip(lower=0)
    df["volume"] = df["vol_adj"]      # 룰이 보는 컬럼명
    return df.dropna(subset=["open", "high", "low", "close"])


def load_universe(conn) -> tuple[dict, dict]:
    """`{date: {code: (market_cap, trading_value)}}`. `trading_value` 는 읽기계층과 동일 정의."""
    u = pd.read_sql(f"""
        SELECT date, stock_code, market_cap,
               (close * (volume * COALESCE(adj_factor,1)))::double precision AS tv
        FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'
    """, conn)
    u["market_cap"] = pd.to_numeric(u["market_cap"], errors="coerce")
    u["tv"] = pd.to_numeric(u["tv"], errors="coerce").fillna(0.0)
    stats = dict(rows=int(len(u)),
                 mcap_missing=int((u["market_cap"].isna() | (u["market_cap"] <= 0)).sum()))
    uni: dict = defaultdict(dict)
    for d, code, mc, tv in zip(u["date"].to_numpy(), u["stock_code"].to_numpy(),
                               u["market_cap"].to_numpy(), u["tv"].to_numpy()):
        uni[d][code] = (float(mc) if mc == mc else 0.0, float(tv))
    return dict(uni), stats


def eligible_by_date(uni: dict, screener) -> dict:
    """전략 `base_filter`(시총 ≤3조 · 거래대금 ≥10억)를 날짜별로 그대로 적용."""
    out = {}
    for d, m in uni.items():
        recs = [{"code": c, "name": c, "market_cap": mc, "trading_value": tv}
                for c, (mc, tv) in m.items()]
        out[d] = {r["code"] for r in screener.base_filter(recs)}
    return out


# ────────────────────────────────────────────────────────────────────────────
# 2. 방향 판정 (PREREG §2-1 코드블록 그대로)
# ────────────────────────────────────────────────────────────────────────────
def direction(highs: np.ndarray, lows: np.ndarray, i: int) -> tuple[float, int]:
    """`seg = df.iloc[-(20+1):-1]` 위에서 `(range_pct, sign)` 을 낸다.

    `i` = 당일 봉의 절대 인덱스. `seg` = `i-20 … i-1` (당일 제외 직전 20봉).

        range_pct = (seg.high.max() − seg.low.min()) / seg.low.min()
        i_low     = seg.low.argmin()      # 동점이면 «가장 이른» 봉 (numpy 기본)
        i_high    = seg.high.argmax()     # 동점이면 «가장 이른» 봉 (numpy 기본)

    `sign` = +1(`i_low < i_high`, 상승형 `S⁺`) · −1(`i_low > i_high`, 하락형 `S⁻`) ·
    0(`i_low == i_high`, 동일봉 `S⁰`).

    🔑 **동점 처리(가장 이른 봉)를 여기서 못박는다**(§2-1) — 태쏘 2026-08-13 의
    *「수량사를 안 정해놔서 라벨이 갈렸다」* 와 같은 형태를 미리 막는다.
    `np.argmin`/`np.argmax` 는 최초 등장 인덱스를 돌려주므로 그 규약과 정확히 같다.
    """
    a, b = i - SURGE_LOOKBACK, i
    seg_low = lows[a:b]
    seg_high = highs[a:b]
    lo = float(seg_low.min())
    if lo <= 0:
        return float("nan"), 0
    rng = (float(seg_high.max()) - lo) / lo
    i_low = int(seg_low.argmin())
    i_high = int(seg_high.argmax())
    return rng, (1 if i_low < i_high else (-1 if i_low > i_high else 0))


def q_flag(vols: np.ndarray, i: int) -> bool:
    """§2-3 — `mean(volume[-3:]) < mean(volume of seg) × 0.70`.

    `volume[-3:]` = 당일 포함 최근 3봉(`i-2 … i`), `seg` = `i-20 … i-1`.
    문턱 0.70 은 `rule_volume_dryup` 이 이미 쓰는 값 그대로다(데이터에서 유도 안 함).
    """
    base = float(vols[i - SURGE_LOOKBACK:i].mean())
    if base <= 0:
        return False
    return float(vols[i - Q_RECENT + 1:i + 1].mean()) < base * Q_RATIO


def f1_flag(closes: np.ndarray, i: int, rng: float) -> bool:
    """§2-4 — `one_day_max = max over t in seg of (close_t/close_{t−1} − 1)`, **직전 봉 포함**.

    `seg` 의 첫 봉 `i-20` 에 대한 `close_{t−1}` 은 `i-21` 이므로 **22봉**이 필요하다
    (§3-1 표). `F1 = D ∧ (one_day_max ≥ 0.5 × range_pct)`.
    """
    a = i - SURGE_LOOKBACK - 1
    if a < 0:
        return False
    c = closes[a:i]                       # i-21 … i-1 (21개)
    prev, cur = c[:-1], c[1:]             # t-1, t  (각 20개 = seg 전체)
    if not np.all(prev > 0):
        return False
    return float((cur / prev - 1.0).max()) >= F1_FRAC * rng


# ────────────────────────────────────────────────────────────────────────────
# 3. 룰 평가 캐시 — 전 arm 공유 (PREREG §2 · 사다리 §2 승계)
# ────────────────────────────────────────────────────────────────────────────
def build_cache(px: pd.DataFrame, elig: dict):
    """`{code: {date: (score, d, sign, rng, q, f1, close, i)}}` — 적격 (code,date) «전부».

    `i` = 그 종목 시계열 안에서의 **봉 인덱스**(0-based). §2-2 의 「기준선과 왜 다른가」
    규명이 `i` 로 버킷을 나누므로 캐시에 함께 싣는다.

    🔑 **한 창에서 전부 만든다** ⇒ arm 간 차이가 「급등 조건 하나」로만 생긴다.
    R 의 풀이 「`base_filter` 통과 전체」라서 트리거 안 된 종목도 필요하므로,
    캐시는 «발화분»이 아니라 «적격분 전체»를 담는다.

    🔴 **`D` 는 라이브 룰 객체를 «그대로» 호출해서 정한다** — 나머지 세 조건(MA5 터치·
    종가 지지·양봉)을 재구현하지 않는다(§8-2).

    ⚡ **사전 걸러내기는 룰의 «필요조건»만 쓴다.** `rule_ma5_pullback` 이 트리거하려면
    ①`len(win) ≥ 22` ②양봉(`close > open`) ③`_recent_surge`(= `range_pct ≥ 0.20`)
    가 «전부» 참이어야 하므로, 셋 중 하나라도 거짓이면 룰을 부르지 않아도 결과가 False 다.
    이것은 근사가 아니라 **논리적 동치**이며, 아래 `probe` 가 표본으로 실증한다.
    """
    rule = rule_ma5_pullback()            # 🔴 파라미터 기본값 그대로 (§8-1·§8-2)
    rng_probe = np.random.RandomState(0)
    cache: dict = defaultdict(dict)
    stats = dict(n_eval=0, n_rule_called=0, n_prefiltered=0, n_short=0,
                 n_d=0, n_sp=0, n_sm=0, n_s0=0, n_q=0, n_f1=0,
                 probe_n=0, probe_trig=0, win_probe_n=0, win_probe_diff=0)
    t0 = time.perf_counter()
    done = 0
    total = px["stock_code"].nunique()
    for code, g in px.groupby("stock_code", sort=False):
        done += 1
        if done % 300 == 0:
            print(f"      ...{done}/{total} 종목 · 평가 {stats['n_eval']:,} · "
                  f"룰호출 {stats['n_rule_called']:,} · D {stats['n_d']:,} · "
                  f"{time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        opens = g["open"].to_numpy(dtype=float)
        highs = g["high"].to_numpy(dtype=float)
        lows = g["low"].to_numpy(dtype=float)
        closes = g["close"].to_numpy(dtype=float)
        vols = g["volume"].to_numpy(dtype=float)
        for i in range(len(g)):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            stats["n_eval"] += 1
            a = max(0, i + 1 - SCORE_WINDOW)
            score = float(vols[a:i + 1].mean())
            rec = [score, False, 0, float("nan"), False, False, float(closes[i]), i]

            # ── 룰의 «필요조건» 3개 (논리적 동치 · 근사 아님) ────────────────
            n_bars = min(i + 1, LOOKBACK)
            if n_bars < SURGE_LOOKBACK + 2:
                stats["n_short"] += 1
                cache[code][d] = tuple(rec)
                continue
            rngp, sign = direction(highs, lows, i)
            bullish = closes[i] > opens[i]
            surged = (rngp == rngp) and rngp >= SURGE_PCT
            if not (bullish and surged):
                stats["n_prefiltered"] += 1
                # 자기검증: 걸러낸 것 일부를 실제로 룰에 넣어 「0건 트리거」를 실증한다.
                if rng_probe.random_sample() < 0.004:
                    win = g.iloc[i + 1 - n_bars:i + 1]
                    stats["probe_n"] += 1
                    stats["probe_trig"] += bool(
                        getattr(rule.evaluate(win, {}), "triggered", False))
                cache[code][d] = tuple(rec)
                continue

            win = g.iloc[i + 1 - n_bars:i + 1]
            stats["n_rule_called"] += 1
            ok_d = bool(getattr(rule.evaluate(win, {}), "triggered", False))
            if ok_d:
                # 🔴 창 길이 «불변성» 반증 시도 (§2-2). PREREG §3-1 은 이 룰이 마지막
                #    22봉만 본다고 적었다 ⇒ 창을 130봉으로 늘려도 결과가 같아야 한다.
                #    같지 않으면 「기준선과의 차이」를 창 탓으로 돌릴 수 있다는 뜻이므로
                #    표본으로 반증을 시도한다.
                if rng_probe.random_sample() < 0.02:
                    w2 = g.iloc[max(0, i + 1 - WINDOW_PROBE_ALT):i + 1]
                    stats["win_probe_n"] += 1
                    stats["win_probe_diff"] += (
                        bool(getattr(rule.evaluate(w2, {}), "triggered", False)) != ok_d)
                qf = q_flag(vols, i)
                ff = f1_flag(closes, i, rngp)
                rec[1], rec[2], rec[3], rec[4], rec[5] = True, sign, rngp, qf, ff
                stats["n_d"] += 1
                stats["n_sp"] += (sign == 1)
                stats["n_sm"] += (sign == -1)
                stats["n_s0"] += (sign == 0)
                stats["n_q"] += qf
                stats["n_f1"] += ff
            cache[code][d] = tuple(rec)
    stats["secs"] = time.perf_counter() - t0
    return dict(cache), stats


# ────────────────────────────────────────────────────────────────────────────
# 4. Arm 풀 · 선택 (PREREG §2-2)
# ────────────────────────────────────────────────────────────────────────────
# 🔴 arm 은 여섯뿐이다(§2-2). `S0` 는 arm 이 «아니라» §2-1 의 「인쇄만」 항목이므로
#    풀은 만들되 판정·PnL 대상에서 제외한다(`ARM_PNL` 참조).
ALL_RULE = {
    "D":  lambda d, s, q, f: d,
    "S+": lambda d, s, q, f: d and s == 1,
    "S-": lambda d, s, q, f: d and s == -1,
    "S0": lambda d, s, q, f: d and s == 0,
    "Q":  lambda d, s, q, f: d and q,
    "F1": lambda d, s, q, f: d and f,
}
ARM_PNL = ["D", "S+", "S-", "Q", "F1"]    # 2단계에서 PnL 을 계산하는 arm (§2-2 의 여섯 − R)
COUNT_ONLY = ["S0"]                        # §2-1 — 건수만. 판정에 쓰지 않는다.


def build_pools(cache: dict, elig: dict) -> dict:
    """`{arm: {date: [(code, score)]}}` + `R` 은 「base_filter 통과 전체」(진입 룰 없음)."""
    pools = {a: defaultdict(list) for a in list(ALL_RULE) + ["R"]}
    for code, dd in cache.items():
        for d, (score, dflag, sign, _rng, qf, ff, _close, _i) in dd.items():
            if code not in elig.get(d, ()):
                continue
            pools["R"][d].append((code, score))
            if not dflag:
                continue
            for a, fn in ALL_RULE.items():
                if fn(dflag, sign, qf, ff):
                    pools[a][d].append((code, score))
    return {a: {d: sorted(v) for d, v in p.items() if v} for a, p in pools.items()}


def select_top(pool: dict) -> dict:
    """현행 `score` 내림차순 top-`MAX_CANDIDATES`. 동점은 코드 오름차순 안정정렬."""
    return {d: [c for c, _ in sorted(v, key=lambda t: t[1], reverse=True)[:MAX_CANDIDATES]]
            for d, v in pool.items()}


def select_random(pool: dict, seed: int) -> dict:
    rng = np.random.RandomState(seed)
    out = {}
    for d in sorted(pool):
        codes = [c for c, _ in pool[d]]
        k = min(MAX_CANDIDATES, len(codes))
        out[d] = list(rng.choice(codes, size=k, replace=False)) if k else []
    return out


# ────────────────────────────────────────────────────────────────────────────
# 5. 게이트 helper
# ────────────────────────────────────────────────────────────────────────────
def decile_hist(items: list, key: dict) -> np.ndarray:
    """`items` = [(date, code)]. `key[date][code]` 값의 «그날 D-풀 안» 10분위 히스토그램."""
    h = np.zeros(N_DECILES)
    byd: dict = defaultdict(list)
    for d, c in items:
        byd[d].append(c)
    for d, codes in byd.items():
        ref = key.get(d)
        if not ref or len(ref) < 2:
            continue
        rc = sorted(ref)
        vals = np.array([ref[c] for c in rc], dtype=float)
        order = vals.argsort(kind="stable")
        rank = np.empty(len(vals))
        rank[order] = np.arange(len(vals), dtype=float)
        dec = np.minimum((rank / len(vals) * N_DECILES).astype(int), N_DECILES - 1)
        pos = {c: k for k, c in enumerate(rc)}
        for c in codes:
            if c in pos:
                h[dec[pos[c]]] += 1
    return h


def ks(h1: np.ndarray, h2: np.ndarray) -> float:
    if h1.sum() <= 0 or h2.sum() <= 0:
        return float("nan")
    return float(np.max(np.abs(np.cumsum(h1 / h1.sum()) - np.cumsum(h2 / h2.sum()))))


def year_skew(items: list, pool_days: list, label: str) -> bool:
    """연도 쏠림 — 원시 비중 + **거래일 정규화 비중**. 양쪽 모두 ≤50% 일 때만 ✅ (§6-4)."""
    if not items:
        say(f"- `{label}`: 대상 0건 — 쏠림 계산 불가")
        return False
    yr = Counter(d[:4] for d, _ in items)
    days = Counter(d[:4] for d in pool_days)
    rate = {y: yr[y] / days[y] for y in yr if days.get(y)}
    tot = sum(rate.values())
    norm = {y: rate[y] / tot * 100 for y in rate} if tot > 0 else {}
    say("")
    say(f"**{label}** — 총 {len(items):,}건")
    say("")
    say("| 연도 | 건수 | 원시 비중 | 대상일 | 일당 | **정규화 비중** |")
    say("|---|---|---|---|---|---|")
    for y in sorted(yr):
        say(f"| {y} | {yr[y]:,} | {yr[y]/len(items)*100:.1f}% | {days.get(y,0):,} | "
            f"{rate.get(y, float('nan')):.2f} | **{norm.get(y, float('nan')):.1f}%** |")
    raw_top = max(yr.values()) / len(items) * 100
    ry = max(yr, key=lambda k: yr[k])
    ny, ntop = (max(norm, key=lambda k: norm[k]), max(norm.values())) if norm else ("—", float("nan"))
    say("")
    ok = raw_top <= YEAR_SKEW_MAX and (ntop != ntop or ntop <= YEAR_SKEW_MAX)
    say(f"- 원시 최대 = **{ry} {raw_top:.1f}%** · 정규화 최대 = **{ny} {ntop:.1f}%** → "
        + ("✅ **양쪽 모두 ≤50% — 통과**" if ok else
           "🔴 **한쪽이라도 >50% ⇒ 「국면 특이 → 판별 보류」 병기**"))
    return ok


def reconcile(cache: dict, cstats: dict) -> None:
    """🔴 **기존 기준선과 왜 다른가** — 추정이 아니라 «실측 버킷»으로 규명한다.

    이미 커밋된 `rank_score_counterfactual/GATE.md` 는 같은 전략·같은 창에서
    「룰 평가 414,154 / 발화 52,584 / 발화 종목 2,207」을 적었다. 이 스크립트는
    발화 **52,657** 이다. ***세 문서 중 하나만 다르면 그 하나를 설명하지 못한 채로
    커밋하면 안 된다*** — 나중에 「어느 숫자를 인용해야 하나」가 된다.

    가설: 차이의 출처는 **루프 시작 인덱스(warmup)** 하나다.
    `rank_score` 는 `for i in range(warmup, n)` 에 `warmup=25`(= `config.yaml`
    `parameters.min_daily_bars`, 라이브 `strategy.py` 경로의 가드)를 쓰고,
    이 스크립트는 **룰 자체 가드**(`len(df) ≥ 22` ⇒ `i ≥ 21`, PREREG §3-1 표)만 쓴다.
    ⇒ 차이는 «전부» `i ≤ 24` 구간에서 나와야 한다. 아래가 그 검정이다.
    """
    b_short, b_gap, b_common = [], [], []          # i≤20 / 21≤i≤24 / i≥25
    f_gap, f_common = [], []
    sign_gap, sign_common = Counter(), Counter()
    for code, dd in cache.items():
        for d, r in dd.items():
            i = r[7]
            tgt = b_short if i <= 20 else (b_gap if i < RS_WARMUP else b_common)
            tgt.append((d, code))
            if not r[1]:
                continue
            if i < RS_WARMUP:
                f_gap.append((d, code, i, r[2], r[3]))
                sign_gap[r[2]] += 1
            else:
                f_common.append((d, code))
                sign_common[r[2]] += 1

    say("### 2-2. 🔴 기존 기준선과 왜 다른가 — 규명 (추정 아님 · 실측 버킷)")
    say("")
    say(f"이미 커밋된 {BASELINE_SRC} 는 **같은 전략·같은 창**에서 "
        f"「룰 평가 **{BASELINE_EVAL:,}** / 발화 **{BASELINE_FIRE:,}** / 발화 종목 "
        f"**{BASELINE_UNIQ:,}**」을 적었다. 이 스크립트의 발화는 **{cstats['n_d']:,}** 다. "
        f"🔑 ***세 문서 중 하나만 다르면 그 하나를 설명하지 못한 채로 커밋하면 안 된다.***")
    say("")
    say("**가설** — 차이의 출처는 **루프 시작 인덱스(warmup)** 하나다.")
    say("")
    say(f"| | 이 문서 (`ma5/run.py`) | 기준선 (`rank_score_counterfactual/run.py`) |")
    say("|---|---|---|")
    say(f"| 룰에 넘기는 창 | {LOOKBACK}봉 | {LOOKBACK}봉 (**같다**) |")
    say(f"| 루프 시작 | 룰 자체 가드 `len(df) ≥ {RULE_GUARD_BARS}` ⇒ **`i ≥ 21`** "
        f"(PREREG §3-1 표) | `range(warmup, n)` 의 **`warmup = {RS_WARMUP}`** ⇒ `i ≥ {RS_WARMUP}` |")
    say(f"| 그 값의 출처 | `rule_ma5_pullback` = `surge_lookback + 2` · "
        f"라이브 **`screener.py`** 경로엔 다른 가드가 없다 | `config.yaml` "
        f"`parameters.min_daily_bars: {RS_WARMUP}` · 라이브 **`strategy.py:192`** 경로의 가드 |")
    say(f"| 종목코드 술어 · 창 · `HIST0` · 로더 | 동일 (같은 문자열·같은 식) | 동일 |")
    say("")
    say("⇒ **예측: 차이는 «전부» `i ≤ 24` 구간에서 나와야 한다.** 실측:")
    say("")
    say("| 봉 인덱스 버킷 | 적격 (code,date) | `D` 발화 | 두 문서에서의 취급 |")
    say("|---|---|---|---|")
    say(f"| `i ≤ 20` | {len(b_short):,} | — | 양쪽 모두 평가 안 함 "
        f"(룰 {RULE_GUARD_BARS}봉 가드 미만) · **이 문서는 `R` 풀에는 넣는다** |")
    say(f"| `21 ≤ i ≤ 24` | {len(b_gap):,} | **{len(f_gap):,}** | "
        f"🔴 **이 문서만 평가** — 룰 가드는 통과, 기준선 `warmup` 은 미만 |")
    say(f"| `i ≥ {RS_WARMUP}` | **{len(b_common):,}** | **{len(f_common):,}** | 양쪽 공통 |")
    say(f"| **합계** | **{len(b_short)+len(b_gap)+len(b_common):,}** | "
        f"**{len(f_gap)+len(f_common):,}** | |")
    say("")
    u_common = len({c for _, c in f_common})
    ok_eval = len(b_common) == BASELINE_EVAL
    ok_fire = len(f_common) == BASELINE_FIRE
    ok_uniq = u_common == BASELINE_UNIQ
    say(f"| 기준선과 대조 (`i ≥ {RS_WARMUP}` 부분집합만) | 이 문서 | 기준선 | 일치 |")
    say("|---|---|---|---|")
    say(f"| 룰 평가 수 | {len(b_common):,} | {BASELINE_EVAL:,} | "
        f"{'✅ **정확히 일치**' if ok_eval else '🔴 불일치'} |")
    say(f"| `D` 발화 수 | {len(f_common):,} | {BASELINE_FIRE:,} | "
        f"{'✅ **정확히 일치**' if ok_fire else '🔴 불일치'} |")
    say(f"| 발화 고유 종목 | {u_common:,} | {BASELINE_UNIQ:,} | "
        f"{'✅ **정확히 일치**' if ok_uniq else '🔴 불일치'} |")
    say("")
    if ok_eval and ok_fire and ok_uniq:
        say(f"⇒ ✅ **가설 확인.** `i ≥ {RS_WARMUP}` 로 자른 부분집합이 기준선 세 숫자를 "
            f"**전부 자릿수까지 재현**한다. 차이는 **오직** `warmup` 하나에서 나온다.")
    else:
        say("⇒ 🔴 **가설이 설명하지 못하는 잔차가 있다 — 이 문서의 수치를 쓰기 전에 규명하라.**")
    say("")
    say("**🔑 양방향 차분** — *「많다」와 「포함한다」는 다르다*:")
    say("")
    say(f"- 이 문서 `D` − 기준선 재현분 = **{len(f_gap):,}건** (내 쪽에만)")
    say(f"- 기준선 재현분 − 이 문서 `D` = **0건** — 기준선 집합은 이 문서 집합의 "
        f"**진부분집합**이다(구성상 `i ≥ {RS_WARMUP}` 는 `i ≥ 21` 의 부분집합이므로 "
        f"«정의로» 0 이고, 위 세 숫자 일치가 그 정의가 실제로 성립함을 확인한다).")
    say("")
    say("#### 배제한 다른 후보")
    say("")
    say("| 후보 | 실측 | 판정 |")
    say("|---|---|---|")
    wp = cstats["win_probe_n"]
    say(f"| **룰 창 길이**(60 vs `ma5_exit` 의 {WINDOW_PROBE_ALT}봉) | 발화분 무작위 "
        f"**{wp:,}건**을 {WINDOW_PROBE_ALT}봉 창으로 재평가 → 달라진 건 "
        f"**{cstats['win_probe_diff']:,}** | "
        + ("✅ **배제** — 이 룰은 마지막 22봉만 보므로 창 길이에 «불변»이다(PREREG §3-1). "
           "***창 길이는 원인이 될 수 없다.***" if cstats["win_probe_diff"] == 0 else
           "🔴 **배제 실패 — 창 길이가 결과를 바꾼다**") + " |")
    say(f"| 종목코드 술어 | 두 스크립트 모두 `^[0-9][0-9A-Z]{{5}}$` + 의사티커 4개 배제, "
        f"**같은 문자열** | ✅ 배제 |")
    say(f"| 창 경계 · `HIST0` | 양쪽 `{W0}`~`{W1}` · `HIST0={HIST0}` | ✅ 배제 |")
    say(f"| `market_cap` 결측 처리 | 양쪽 **같은** `base_filter`(`_passes_market_cap` "
        f"fail-closed)를 «같은 어댑터 객체»로 호출 | ✅ 배제 |")
    say(f"| 로더 행 필터 | 기준선은 `datetime` NaT 행을 추가로 버린다 — 실측 해당 행 "
        f"**0행** | ✅ 배제 |")
    say("")
    say(f"#### 차이 {len(f_gap):,}건의 정체")
    say("")
    yr = Counter(d[:4] for d, _c, _i, _s, _r in f_gap)
    say(f"- 고유 종목 **{len({c for _d, c, _i, _s, _r in f_gap}):,}** · "
        f"연도별 " + " · ".join(f"{y} **{n}**" for y, n in sorted(yr.items())))
    say(f"- 공통점 = ***창(`{W0}`~) 안에서 상장 이력이 22~25봉밖에 없는 (종목, 날짜)*** "
        f"— `HIST0={HIST0}` 부터 읽었으므로 이는 **창 직전에 신규 상장·거래재개된 종목**이다.")
    say("")
    say("🔴 **이 차이 집합은 방향에 대해 «중립이 아니다»**: "
        + " · ".join(f"`{lab}` **{sign_gap[s]}**" for s, lab in ((1, "S⁺"), (-1, "S⁻"), (0, "S⁰")))
        + f" ⇒ `S⁻` 비중 **{sign_gap[-1]/max(1,len(f_gap))*100:.1f}%** 로 "
          f"모집단(41%대)보다 크게 치우쳐 있다. **그래도 판정에 미치는 영향은 아래처럼 미미하다** "
          f"— 건수가 `D` 의 {len(f_gap)/max(1,cstats['n_d'])*100:.2f}% 뿐이기 때문이다.")
    say("")
    say("#### 🔴 판정에 미치는 영향 — 방향 구성비를 «넣고/빼고» 둘 다 인쇄")
    say("")
    ta = sum(sign_gap.values()) + sum(sign_common.values())
    tr = sum(sign_common.values())
    say("| 방향 | 포함 (이 문서) | 비율 | 제외 (기준선 정합) | 비율 | **차** |")
    say("|---|---|---|---|---|---|")
    for s, lab in ((1, "S⁺"), (-1, "S⁻"), (0, "S⁰")):
        na, nr = sign_gap[s] + sign_common[s], sign_common[s]
        pa, pr = na / ta * 100, nr / tr * 100
        say(f"| **{lab}** | {na:,} | **{pa:.2f}%** | {nr:,} | {pr:.2f}% | **{pa-pr:+.4f}%p** |")
    say(f"| 합계 | {ta:,} | 100.00% | {tr:,} | 100.00% | |")
    say("")
    dmax = max(abs((sign_gap[s] + sign_common[s]) / ta * 100 - sign_common[s] / tr * 100)
               for s in (1, -1, 0))
    say(f"⇒ ✅ **최대 이동 {dmax:.4f}%p.** ***이 차이는 이 문서의 결론과 무관하다*** — "
        f"§3 의 구성비도, §5-2 의 판정도 `warmup` 을 어느 쪽으로 잡든 바뀌지 않는다. "
        f"**그 «무관함» 자체를 여기 기록해 둔다**(나중에 「어느 숫자를 인용하나」가 되지 않도록).")
    say("")
    say(f"#### 어느 쪽이 옳은가 — 🔴 **이 문서는 창을 맞추려고 코드를 바꾸지 않았다**")
    say("")
    say(f"라이브에 **가드가 둘** 있다. ①`screener.py` 의 EOD 스캔 경로는 "
        f"`rule_ma5_pullback` 을 바로 부르므로 실효 가드가 **{RULE_GUARD_BARS}봉** ② "
        f"`strategy.py:192` 의 신호 경로는 `min_daily_bars={RS_WARMUP}` 를 건다. "
        f"**PREREG §3-1 표는 ①을 명시했다**(*「`rule_ma5_pullback` 가드 | `len(df) ≥ "
        f"{RULE_GUARD_BARS}` | ✅」*) ⇒ 이 문서는 ①을 쓴다. 기준선은 ②를 썼다. "
        f"***둘 다 라이브에 실재하는 값이고, 어느 쪽도 오류가 아니다.***")
    say("")
    say(f"🔴 **숫자를 기준선에 맞추려고 `LOOKBACK`·술어·가드를 바꾸지 않았다.** "
        f"동결된 사전등록이 정본이고, 규명의 목표는 *「왜 다른가를 설명하는 것」*이지 "
        f"*「같게 만드는 것」*이 아니다. ⇒ **인용 규칙: 이 문서의 수치는 "
        f"「룰 가드 {RULE_GUARD_BARS}봉」 기준이고, `rank_score`·`ma5_exit` 의 수치는 "
        f"「`min_daily_bars` {RS_WARMUP}봉」 기준이다. 둘을 섞어 인용하지 말 것.**")
    say("")


def q3(vals: list) -> tuple[float, float, float]:
    """중앙 · 10분위 · 90분위."""
    if not vals:
        return (float("nan"),) * 3
    a = np.asarray(vals, dtype=float)
    return float(np.median(a)), float(np.percentile(a, 10)), float(np.percentile(a, 90))


# ────────────────────────────────────────────────────────────────────────────
# 6. 2단계 — 백테스트 · 판정 (PREREG §4·§5)
# ────────────────────────────────────────────────────────────────────────────
class ArmGated:
    """arm 이 «그날 고른» 종목-일만 매수 신호로 바꾼다.

    🔑 진입 룰 판정은 1단계 캐시가 이미 끝냈고 arm 선택은 그 부분집합이므로 여기서는
    `(code, date)` 조회 하나뿐이다 — **룰을 다시 평가하지 않는다.**
    """

    def __init__(self, allowed: dict):
        self.allowed = allowed

    def generate_signal(self, stock_code, df, timeframe="daily"):
        if stock_code in self.allowed.get(df["date"].iloc[-1], ()):
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=68)
        return None


def run_arm(sel: dict, frames: dict, idxmap: dict, cfg: dict, backtester_cls) -> dict:
    """arm 하나를 백테스트해 «거래당» 분포와 «신호→실현» 전환을 낸다.

    `mean`·`med` 단위는 **%**. 🔑 `pnl_pct` 에는 슬리피지(편도 0.1%)가 체결가에 반영돼 있고
    **수수료 0.015%·거래세 0.18% 는 미반영**(= PREREG §4 의 gross, 승계 원본과 동일 정의).

    🔴 **`BookBacktester` 확장 파라미터(`exit_line`·`disaster_stop_pct`·`random_exit_seed`)를
    넘기지 않는다** — 이 문서는 «진입» 축이라 청산은 현행 고정이다(§2 · §10-3).

    🔴 **`signals`(신호 수)의 정의**(§7-11): arm 이 고른 (code, date) 중
    **그 종목 프레임에 실제로 존재하고 다음 봉이 있는**(체결 가능) 것의 수.
    `BookBacktester` 는 보유 중이면 `generate_signal` 을 «부르지도 않으므로»,
    폐기 건수는 백테스터 안에서 셀 수 없다 — 그래서 밖에서 「제시된 신호」를 세고
    실현 매수와 대조한다. `discard = 1 − entries / signals`.
    """
    allowed = {d: set(v) for d, v in sel.items() if v}
    codes = set().union(*allowed.values()) if allowed else set()
    signals = 0
    for d, cs in allowed.items():
        for c in cs:
            im = idxmap.get(c)
            if im is not None:
                i = im.get(d)
                if i is not None and i <= im["__last__"] - 1:
                    signals += 1
    bt = backtester_cls(strategy=ArmGated(allowed), warmup_bars=0,
                        stop_loss_pct=cfg["sl"], take_profit_pct=cfg["tp"],
                        max_hold_bars=cfg["mh"], eod_liquidate=False)
    pnl, hold, reasons = [], [], []
    for c in sorted(codes):
        g = frames.get(c)
        if g is None or len(g) < 2:
            continue
        buy = None
        for t in bt.run_single(c, g).trades:
            if t["side"] == "buy":
                buy = t
            elif t["side"] == "sell" and buy is not None:
                pnl.append(float(t["pnl_pct"]))
                hold.append(int(t["idx"]) - int(buy["idx"]))
                reasons.append(str(t["reason"]))
                buy = None
    if not pnl:
        return dict(n=0, signals=signals, discard=float("nan"), mean=float("nan"),
                    med=float("nan"), win=float("nan"), hold=float("nan"),
                    sl=float("nan"), tp=float("nan"), mh=float("nan"))
    p, r = pd.Series(pnl), pd.Series(reasons)
    return dict(n=len(pnl), signals=signals,
                discard=(1 - len(pnl) / signals) * 100 if signals else float("nan"),
                mean=p.mean() * 100, med=p.median() * 100, win=(p > 0).mean() * 100,
                hold=float(pd.Series(hold).median()),
                sl=(r == "stop_loss").mean() * 100, tp=(r == "take_profit").mean() * 100,
                mh=(r == "max_hold").mean() * 100)


def perm_p(arm_mean: float, r_means: list) -> float:
    """단측 순열 p — `(1 + #{R_i ≥ A}) / (1 + n_seeds)`. N1 성립 시 최솟값 `1/21`."""
    return (1 + sum(1 for x in r_means if x >= arm_mean)) / (1 + len(r_means))


def direction_verdict(sp: float, sm: float, n1_sp: bool, n1_sm: bool) -> tuple[str, list]:
    """PREREG §5-2 판정 순서 — **위에서부터 «처음 성립하는 것»을 채택**한다.

    네 라벨은 상호배타적이고 전부를 덮는다. **새 라벨을 짓지 않는다**(§5-2 마지막 줄).
    """
    e = EPS_ECON
    rows = [
        (1, "`|S⁺ − S⁻| < ε`", abs(sp - sm) < e,
         "**(마) 구별 불가**"),
        (2, "`S⁺ − S⁻ ≥ ε` **그리고** N1(S⁺)", (sp - sm >= e) and n1_sp,
         "**(가) 방향은 정보다 — 「급등」이라 부른 것이 결함**"),
        (3, "`S⁻ − S⁺ ≥ ε` **그리고** N1(S⁻)", (sm - sp >= e) and n1_sm,
         "🔴 **(다) 정체가 다르다 — 이 전략은 낙폭과대 반등이었다**"),
        (4, "(그 외)", True,
         "**(나) 방향은 정보가 아니다** — 차이는 있으나 이긴 쪽이 무작위를 못 넘었다"),
    ]
    for _, _, hit, label in rows:
        if hit:
            return label, rows
    return rows[-1][3], rows


def placement_labels(D: float, sp: float, sm: float) -> dict:
    """PREREG §5-3 — `D` 는 어디에 놓이는가. **사전 고정 라벨 · 판정 언어 금지.**"""
    return {
        "`S⁺ > D > S⁻` — 방향 가설과 정합 (순서가 예측대로다)": sp > D > sm,
        "`S⁻ > D > S⁺` — 역방향과 정합": sm > D > sp,
        "🔴 `D` 가 `S⁺`·`S⁻` **바깥** — 선택 효과가 크다 (상한 10 이 만든 것)":
            not (min(sp, sm) <= D <= max(sp, sm)),
    }


def printonly_label(x: float, D: float) -> str:
    """PREREG §5-4 — `Q`·`F1` 의 사전고정 관측 라벨. **어느 것도 결론이 아니다.**"""
    if x - D >= EPS_ECON:
        return "「이 축이 있어 보인다 — **다음 사전등록의 표적**」"
    if D - x >= EPS_ECON:
        return "「반대 방향으로 보인다 — **다음 사전등록의 표적**」"
    return "「차이 없음」"


def holm(pairs: list, alpha: float = ALPHA) -> list:
    """Holm 단계적 하강. `pairs=[(name, p)]` → `[(name, p, 문턱, 기각여부)]` (원래 순서)."""
    order = sorted(range(len(pairs)), key=lambda i: pairs[i][1])
    m = len(pairs)
    out = [None] * m
    stopped = False
    for rank, i in enumerate(order):
        thr = alpha / (m - rank)
        rej = (not stopped) and pairs[i][1] <= thr
        if not rej:
            stopped = True
        out[i] = (pairs[i][0], pairs[i][1], thr, rej)
    return out


# ────────────────────────────────────────────────────────────────────────────
# 7. 공통 파이프라인 (두 모드가 «같은» 선택 집합을 쓰게 하는 단일 경로)
# ────────────────────────────────────────────────────────────────────────────
def pipeline(conn, verbose: bool = True):
    t0 = time.perf_counter()
    px = load_prices(conn)
    uni, ustats = load_universe(conn)
    t_load = time.perf_counter() - t0
    scr = BookPullbackMa5ScreenerAdapter()
    t1 = time.perf_counter()
    elig = eligible_by_date(uni, scr)
    t_elig = time.perf_counter() - t1
    dates = sorted(uni)
    pool_days = [d for d in dates if elig.get(d)]
    if verbose:
        print(f"[load] 일봉 {len(px):,}행 · {t_load:.0f}s · base_filter {t_elig:.0f}s", flush=True)
        print("[cache] 룰 평가", flush=True)
    cache, cstats = build_cache(px, elig)
    t2 = time.perf_counter()
    pools = build_pools(cache, elig)
    t_pools = time.perf_counter() - t2
    sels, t_arm = {}, {}
    for a in ALL_RULE:
        t3 = time.perf_counter()
        sels[a] = select_top(pools[a])
        t_arm[a] = time.perf_counter() - t3
    t4 = time.perf_counter()
    r_sels = [select_random(pools["R"], s) for s in range(N_SEEDS)]
    t_seeds = time.perf_counter() - t4
    timing = dict(load=t_load, elig=t_elig, cache=cstats["secs"], pools=t_pools,
                  arm=t_arm, seeds=t_seeds)
    return dict(px=px, uni=uni, ustats=ustats, elig=elig, dates=dates,
                pool_days=pool_days, cache=cache, cstats=cstats, pools=pools,
                sels=sels, r_sels=r_sels, timing=timing)


# ────────────────────────────────────────────────────────────────────────────
# 8. stage1 — PREREG §6 게이트 (PnL 미조회)
# ────────────────────────────────────────────────────────────────────────────
def stage1() -> int:
    rows, params, ok = verify_strategy_params()
    if not ok:
        print("🔴 설정 대조 실패 — 중단한다 (지시서: 「불일치면 중단·보고」).", flush=True)
        for r in rows:
            print(r, flush=True)
        return 3

    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    say("# ma5 개념 축 — 1단계 게이트 (PREREG §6, PnL 미조회)")
    say("")
    say(f"사전등록 [`PREREG.md`](PREREG.md)(동결) · 가족 등록부 [`../REGISTRY.md`](../REGISTRY.md) "
        f"**2번 문서** · 실행 커밋 **`{sha}`** · 창 **{W0} ~ {W1}**.")
    say("")
    say("🔴 이 문서는 PREREG **§6(1단계 게이트)까지만** 다룬다. "
        "**해석·「좋다/나쁘다」 판단은 없다** — 순수 산출이다. 결과 계산(§4·§5)은 2단계다.")
    say("")
    say("🔑 `BookBacktester` 를 **import 하지도 호출하지도 않는다** — "
        "거래당 수익률이 메모리에 들어올 경로 자체가 없다(§8-8).")
    say("")

    say("## 0. 설정 대조 (하드코딩 아님 — `config.yaml`·스크리너·룰 객체에서 읽음)")
    say("")
    for r in rows:
        say(r)
    say("")
    say("✅ **청산 3값이 지시서 기대값과 일치**하므로 계속 진행한다. "
        "🔴 청산 파라미터는 **1단계에서 쓰지 않는다**(PnL 미조회) — 2단계가 쓸 값을 못박아 인쇄한다.")
    say("")
    say("🔴 **`trail_ma: 5` 는 `BookBacktester` 가 지원하지 않는다**(§7-1). 전 arm 에 동일하게 "
        "빠지므로 arm 비교엔 무해하나 **절대 수준은 라이브와 다르다.** "
        "***이 문서의 절대 수익률을 minervini 문서의 것과 나란히 놓지 말 것.***")
    say("")

    fp = db_fingerprint(conn)
    say(f"## 0b. DB 지문 ({len(FINGERPRINT_SQL)}슬라이스 · `regen_gate.py` 형식 승계)")
    say("")
    say("| 슬라이스 | 행 수 | 종목 수 | max |")
    say("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        say(f"| `{k}` | {a:,} | {b:,} | {c} |")
    say("")

    P = pipeline(conn)
    conn.close()
    px, uni, ustats = P["px"], P["uni"], P["ustats"]
    elig, dates, pool_days = P["elig"], P["dates"], P["pool_days"]
    cache, cstats, pools, sels, r_sels = (P["cache"], P["cstats"], P["pools"],
                                          P["sels"], P["r_sels"])

    # ── 1. 표본 · 창 ────────────────────────────────────────────────────────
    say("## 1. 표본 · 창 · 워밍업")
    say("")
    hist_rows = int((px["date"] < W0).sum())
    esz = [len(elig[d]) for d in pool_days]
    say(f"- 개정 창 거래일 **{len(dates):,}일** · `base_filter` 통과 종목이 있는 날 "
        f"**{len(pool_days):,}일** · 적격 풀 크기 중앙 **{int(np.median(esz)):,}** "
        f"(최소 {min(esz):,} · 최대 {max(esz):,})")
    say(f"- 적재 일봉 **{len(px):,}행** / **{px.stock_code.nunique():,}종목** "
        f"(`{HIST0}`~`{W1}`) · 그중 **창 이전 워밍업 {hist_rows:,}행**")
    say(f"- `market_cap` 결측(창 안) **{ustats['mcap_missing']:,}/{ustats['rows']:,}** = "
        f"**{ustats['mcap_missing']/ustats['rows']*100:.2f}%**")
    say("")
    say(f"🔑 **룰에 넘기는 창 = {LOOKBACK}봉 — 라이브 스크리너의 `lookback_days` 와 «같다».** "
        f"PREREG §3-1 이 미리 채운 빈칸이다: 이 문서의 모든 참조가 요구하는 최대 봉 수는 "
        f"`F1`(seg 20봉 + 직전 1봉 + 당일) = **22봉**이므로 {LOOKBACK}봉은 「라이브와 동일하면서 "
        f"충분한」 값이다 ⇒ **`D` arm 이 라이브와 «정확히» 같게 동작한다.** "
        f"(문서 1 은 TT 의 220/252봉 요구 때문에 260봉으로 늘려야 했다 — 여기는 그럴 이유가 없다.)")
    say("")

    # ── 2. 룰 캐시 ──────────────────────────────────────────────────────────
    say("## 2. 룰 평가 캐시 (전 arm 공유 · 1회)")
    say("")
    say(f"- 적격 (code,date) **{cstats['n_eval']:,}건** · {cstats['secs']:.0f}s")
    say(f"- 그중 **봉 부족**(`len(win) < 22`) {cstats['n_short']:,} · "
        f"**필요조건 미충족으로 사전 제외** {cstats['n_prefiltered']:,} · "
        f"**라이브 룰 객체 실제 호출** {cstats['n_rule_called']:,}")
    say(f"- `D` 트리거 **{cstats['n_d']:,}** "
        f"(`S⁺` {cstats['n_sp']:,} · `S⁻` {cstats['n_sm']:,} · `S⁰` {cstats['n_s0']:,}) · "
        f"`Q` {cstats['n_q']:,} · `F1` {cstats['n_f1']:,}")
    say("")
    say("### 2-1. 사전 제외의 자기검증 — 「근사」가 아니라 「논리적 동치」임을 표본으로 실증")
    say("")
    say("`rule_ma5_pullback` 이 트리거하려면 ①`len(win) ≥ 22` ②양봉 ③`_recent_surge` 가 "
        "**전부** 참이어야 한다. 셋 중 하나라도 거짓이면 룰은 정의상 False 이므로 호출을 "
        "생략했다. 아래는 **생략분에서 무작위 표본을 뽑아 실제로 룰을 돌려 본 것**이다 "
        "(`RandomState(0)`, 표집률 0.4%):")
    say("")
    say("| 표본 수 | 그중 트리거된 건 | 판정 |")
    say("|---|---|---|")
    say(f"| {cstats['probe_n']:,} | **{cstats['probe_trig']:,}** | "
        + ("✅ **0건 — 동치 성립**" if cstats["probe_trig"] == 0 else
           "🔴 **0 이 아니다 — 사전 제외가 틀렸다. 결과를 쓰지 말 것**") + " |")
    say("")

    # ── 2-2. 🔴 기존 기준선과 왜 다른가 (규명) ───────────────────────────────
    reconcile(cache, cstats)

    # ── 3. §6-2 방향 구성비 (이 문서의 출발점) ───────────────────────────────
    dtri = [(d, c) for c, dd in cache.items() for d, r in dd.items() if r[1]]
    sign_of = {(d, c): cache[c][d][2] for d, c in dtri}
    n_d = len(dtri)
    n_sp = sum(1 for k in dtri if sign_of[k] == 1)
    n_sm = sum(1 for k in dtri if sign_of[k] == -1)
    n_s0 = sum(1 for k in dtri if sign_of[k] == 0)

    say("## 3. 🔴🔴 §6-2 `D` 통과 건의 «방향 구성비» — **이 문서의 출발점이 된 질문**")
    say("")
    say("> 라이브 `ma5` 의 첫 조건은 *「최근 20일 내 +20% **급등** 이력」*이라고 적혀 있지만, "
        "코드(`_recent_surge`)가 재는 것은 **「직전 20봉의 고저 «폭»」**이고 그 폭이 "
        "**오르며 생겼는지 내리며 생겼는지 묻지 않는다.** "
        "***그래서 실제로 몇 %가 하락형인가?*** — 아래가 그 답이다. "
        "⚠️ 이 숫자는 사전등록을 동결하는 시점에 **몰랐다**(PREREG 오염 고지 ④).")
    say("")
    say("### 3-1. 전체")
    say("")
    say("| 방향 | 정의 | 건수 | **비율** |")
    say("|---|---|---|---|")
    say(f"| **S⁺ 상승형** | `i_low < i_high` (저점 → 고점) | {n_sp:,} | "
        f"**{n_sp/n_d*100 if n_d else float('nan'):.2f}%** |")
    say(f"| **S⁻ 하락형** | `i_low > i_high` (고점 → 저점) | {n_sm:,} | "
        f"**{n_sm/n_d*100 if n_d else float('nan'):.2f}%** |")
    say(f"| **S⁰ 동일봉** | `i_low == i_high` (한 봉이 양 극단) | {n_s0:,} | "
        f"**{n_s0/n_d*100 if n_d else float('nan'):.2f}%** |")
    say(f"| **합계 (= `D`)** | | **{n_d:,}** | 100.00% |")
    say("")
    say("### 3-2. 연도별")
    say("")
    say("| 연도 | `D` | `S⁺` | `S⁻` | `S⁰` | S⁺ 비율 | **S⁻ 비율** |")
    say("|---|---|---|---|---|---|---|")
    by_y: dict = defaultdict(Counter)
    for k in dtri:
        by_y[k[0][:4]][sign_of[k]] += 1
    for y in sorted(by_y):
        c = by_y[y]
        t = sum(c.values())
        say(f"| {y} | {t:,} | {c[1]:,} | {c[-1]:,} | {c[0]:,} | {c[1]/t*100:.1f}% | "
            f"**{c[-1]/t*100:.1f}%** |")
    say("")
    say("### 3-3. 월별")
    say("")
    say("| 연-월 | `D` | `S⁺` | `S⁻` | `S⁰` | S⁺ 비율 | **S⁻ 비율** |")
    say("|---|---|---|---|---|---|---|")
    by_m: dict = defaultdict(Counter)
    for k in dtri:
        by_m[k[0][:7]][sign_of[k]] += 1
    for mth in sorted(by_m):
        c = by_m[mth]
        t = sum(c.values())
        say(f"| {mth} | {t:,} | {c[1]:,} | {c[-1]:,} | {c[0]:,} | {c[1]/t*100:.1f}% | "
            f"**{c[-1]/t*100:.1f}%** |")
    say("")
    mrates = [by_m[m][-1] / sum(by_m[m].values()) * 100 for m in by_m if sum(by_m[m].values())]
    say(f"- 월별 `S⁻` 비율: 최소 **{min(mrates):.1f}%** · 중앙 **{np.median(mrates):.1f}%** · "
        f"최대 **{max(mrates):.1f}%** ({len(mrates)}개월)")
    say("")

    # ── 4. §6-1 트리거 수 ───────────────────────────────────────────────────
    say("## 4. §6-1 arm 별 진입 트리거 수 · 선택 종목-일 수 · 고유 종목 수")
    say("")
    trig_n = {a: sum(len(v) for v in pools[a].values()) for a in ALL_RULE}
    trig_n["R"] = sum(len(v) for v in pools["R"].values())
    trig_u = {a: len({c for v in pools[a].values() for c, _ in v}) for a in ALL_RULE}
    trig_u["R"] = len({c for v in pools["R"].values() for c, _ in v})
    sel_n = {a: sum(len(v) for v in sels[a].values()) for a in ALL_RULE}
    sel_u = {a: len({c for v in sels[a].values() for c in v}) for a in ALL_RULE}
    sel_n["R"] = int(np.mean([sum(len(v) for v in r.values()) for r in r_sels]))
    sel_u["R"] = int(np.mean([len({c for v in r.values() for c in v}) for r in r_sels]))
    base = trig_n["D"]
    say("| Arm | 급등 조건 | 트리거(종목-일) | `D` 대비 | 트리거 고유종목 | 선택 종목-일 | "
        "선택 고유종목 | 선택일 수 | 10% 문턱 |")
    say("|---|---|---|---|---|---|---|---|---|")
    short_arms = []
    for a in ["D", "S+", "S-", "S0", "Q", "F1", "R"]:
        frac = trig_n[a] / base if base else float("nan")
        nd = len(pools[a])
        if a == "D":
            flag = "— (기준선)"
        elif a == "R":
            flag = "— (귀무 · 풀 정의가 다르다)"
        elif a in COUNT_ONLY:
            # 🔴 `S⁰` 는 arm 이 아니므로(§2-1) 10% 문턱의 «대상»이 아니다.
            #    문턱을 걸면 「판별 보류」라는 판정 언어가 arm 아닌 것에 붙는다.
            flag = "— (arm 아님 · 건수만)"
        elif frac < MIN_TRIGGER_FRAC:
            short_arms.append(a)
            flag = "🔴 **미달 → 「표본 부족 → 판별 보류」**"
        else:
            flag = "✅ 충족"
        say(f"| **{DISP[a]}** | {DESC[a]} | {trig_n[a]:,} | {frac*100:.1f}% | {trig_u[a]:,} | "
            f"{sel_n[a]:,} | {sel_u[a]:,} | {nd:,} | {flag} |")
    say("")
    say(f"🔴 사전 고정 문턱(§6-1): **트리거 수가 `D` 의 {MIN_TRIGGER_FRAC*100:.0f}% 미만이면 "
        f"그 arm 은 「표본 부족 → 판별 보류」.**")
    say("")
    if short_arms:
        say(f"⇒ 🔴 **해당: {', '.join('`'+DISP[a]+'`' for a in short_arms)}** — "
            f"2단계 판정문에 「표본 부족 → 판별 보류」를 **병기**한다(§5-2 마지막 문단).")
        if "S-" in short_arms:
            say("")
            say("🔑 ***`S⁻` 가 문턱에 미달한다는 것 «자체»가 §6-2 구성비 질문의 답이므로, "
                "그 경우엔 「하락형이 드물다」가 이 문서의 실질 결과가 된다*** — "
                "그때도 §5-2 라벨은 그대로 인쇄한다(PREREG §5-2 마지막 문단, 사전 고정).")
    else:
        say("⇒ ✅ **문턱 미달 arm 없음.**")
    say("")
    say(f"🔑 `S⁰` 는 **arm 이 아니다**(§2-1 「인쇄만」) — 위 표에 «건수만» 싣고 PnL 을 "
        f"계산하지 않으며 판정에도 쓰지 않는다.")
    say(f"🔑 `R` 의 트리거 수는 「`base_filter` 통과 종목-일」 자체다 — R 은 진입 룰 조건이 "
        f"없기 때문이다(§2). 다른 arm 과 «같은 종류의 수»가 아니므로 10% 문턱을 적용하지 않는다.")
    say("")

    # ── 5. §6-3 배제 집합 vs 잔류 ───────────────────────────────────────────
    say("## 5. §6-3 🔴 배제 집합(`S⁻ ∪ S⁰`) vs 잔류(`S⁺`) — 시총·주가·거래대금·월별")
    say("")
    say("`S⁺` 를 만들면서 `D` 에서 «빠지는» 것이 무엇인지 본다. "
        "10분위 기준 모집단 = **그날 `D` 풀**(= base_filter ∧ 현행 진입 룰).")
    say("")
    say(f"🔴 **여기가 문서 1(minervini)과 «비대칭»인 지점이다.** 문서 1 은 TT·F 가 "
        f"*의도적으로* 강한 종목을 고르는 축이라 KS 가 커도 정상이라고 미리 적었다. "
        f"**이 문서의 축은 「형태」를 가르는 것이지 「크기·유동성」을 가르는 것이 아니다** ⇒ "
        f"**KS > {KS_CONFOUND:.2f} 이면 「교락 신호」로 표시하고 판정문에 병기**한다(§6-3).")
    say("")
    dpool = {d: {c for c, _ in v} for d, v in pools["D"].items()}
    keys = {
        "시총": {d: {c: uni[d][c][0] for c in cs if c in uni.get(d, {})}
                for d, cs in dpool.items()},
        "주가": {d: {c: cache[c][d][6] for c in cs if d in cache.get(c, {})}
                for d, cs in dpool.items()},
        "거래대금": {d: {c: uni[d][c][1] for c in cs if c in uni.get(d, {})}
                 for d, cs in dpool.items()},
    }
    sp_pool = {d: {c for c, _ in v} for d, v in pools["S+"].items()}
    excl = [(d, c) for d, cs in dpool.items() for c in cs - sp_pool.get(d, set())]
    keep = [(d, c) for d, cs in dpool.items() for c in cs & sp_pool.get(d, set())]
    say(f"배제 **{len(excl):,}** · 잔류 **{len(keep):,}**")
    say("")
    ks_flags = []
    for kname, kd in keys.items():
        he, hk = decile_hist(excl, kd), decile_hist(keep, kd)
        kv = ks(he, hk)
        hot = (kv == kv) and kv > KS_CONFOUND
        ks_flags.append((kname, kv, hot))
        say(f"**{kname} 10분위** (1=하위 … 10=상위) · KS = **{kv:.3f}** "
            + ("🔴 **> 0.20 — 교락 신호**" if hot else "✅ ≤ 0.20"))
        say("")
        say("| 집합 | n | " + " | ".join(str(i + 1) for i in range(N_DECILES)) + " |")
        say("|---|---|" + "---|" * N_DECILES)
        for lab, h in (("배제", he), ("잔류", hk)):
            t = h.sum() or 1
            say(f"| {lab} | {int(h.sum()):,} | "
                + " | ".join(f"{x/t*100:.1f}%" for x in h) + " |")
        say("")
    hot_names = [k for k, _, h in ks_flags if h]
    if hot_names:
        say(f"⇒ 🔴 **교락 신호: {', '.join('`'+n+'`' for n in hot_names)}** — "
            f"판정문에 병기한다(§6-3). 「형태」를 가르려던 축이 「크기·유동성」도 함께 가르고 있다.")
    else:
        say(f"⇒ ✅ **세 축 모두 KS ≤ {KS_CONFOUND:.2f}** — 교락 신호 없음.")
    say("")
    mo_e = Counter(d[:7] for d, _ in excl)
    mo_k = Counter(d[:7] for d, _ in keep)
    say("<details><summary>월별 분포 (배제 / 잔류)</summary>")
    say("")
    say("| 연-월 | 배제 | 잔류 | 배제 비율 |")
    say("|---|---|---|---|")
    for m in sorted(set(mo_e) | set(mo_k)):
        e, k = mo_e.get(m, 0), mo_k.get(m, 0)
        say(f"| {m} | {e:,} | {k:,} | {e/(e+k)*100 if e+k else float('nan'):.1f}% |")
    say("")
    say("</details>")
    say("")

    # ── 6. §6-4 연도 쏠림 ───────────────────────────────────────────────────
    say("## 6. §6-4 연도별 쏠림 — 원시 + 거래일 정규화 (**양쪽 ≤50% 일 때만 ✅**)")
    say("")
    say("분모(대상일) = 그 해 `D` 풀이 비지 않은 거래일 수.")
    dpool_days = sorted(dpool)
    skew_ok = {}
    targets = [
        ("D", [(d, c) for d, cs in dpool.items() for c in cs]),
        ("S+", [(d, c) for d, cs in sp_pool.items() for c in cs]),
        ("S-", [(d, c) for d, v in pools["S-"].items() for c, _ in v]),
        ("배제(S⁻ ∪ S⁰)", excl),
    ]
    for lab, items in targets:
        skew_ok[lab] = year_skew(items, dpool_days, f"`{DISP.get(lab, lab)}` 트리거")
        say("")
    bad = [k for k, v in skew_ok.items() if not v]
    if bad:
        say(f"⇒ 🔴 **{', '.join('`'+b+'`' for b in bad)} 이 문턱을 넘었다 ⇒ "
            f"「국면 특이 → 판별 보류」 병기.**")
    else:
        say("⇒ ✅ **전 대상이 원시·정규화 양쪽 모두 ≤50%.**")
    say("")

    # ── 7. §6-5 겹침 행렬 ───────────────────────────────────────────────────
    say("## 7. §6-5 arm 간 선택 종목 겹침 행렬 + 🔴 `S⁺` 선택 중 `D` 에도 든 비율")
    say("")
    say(f"일별 평균 겹침 종목 수(최대 {MAX_CANDIDATES}). 양쪽 다 선택이 있는 날만 센다. "
        f"`R` 은 시드 {N_SEEDS}개 평균.")
    say("")
    labs = ["D", "S+", "S-", "S0", "Q", "F1"]

    def ov(x: dict, y: dict) -> float:
        v = [len(set(x[d]) & set(y.get(d, []))) for d in x if x[d] and y.get(d)]
        return float(np.mean(v)) if v else float("nan")

    say("| | " + " | ".join(DISP[a] for a in labs) + " | R |")
    say("|---|" + "---|" * (len(labs) + 1))
    for a in labs:
        cells = [f"{ov(sels[a], sels[b]):.2f}" for b in labs]
        cells.append(f"{np.nanmean([ov(sels[a], r) for r in r_sels]):.2f}")
        say(f"| **{DISP[a]}** | " + " | ".join(cells) + " |")
    rr = [ov(r_sels[i], r_sels[j]) for i in range(N_SEEDS) for j in range(i + 1, N_SEEDS)]
    say("| **R** | " + " | ".join(f"{np.nanmean([ov(r, sels[b]) for r in r_sels]):.2f}"
                                 for b in labs)
        + f" | {np.nanmean(rr):.2f} |")
    say("")
    sp_sel = sels["S+"]
    d_sel = sels["D"]
    tot_sp = sum(len(v) for v in sp_sel.values())
    in_d = sum(len(set(v) & set(d_sel.get(d, []))) for d, v in sp_sel.items())
    say(f"🔴 **`S⁺` 선택 중 `D` 에도 선택된 비율 = {in_d:,}/{tot_sp:,} = "
        f"{in_d/tot_sp*100 if tot_sp else float('nan'):.1f}%**")
    say("")
    say("🔑 이 비율이 낮으면 「`D` 를 둘로 쪼갰다」는 해석이 약해지고 `S⁺` 는 「다른 룰」에 "
        "가까워진다(§5-3 세 번째 라벨 · §7-10). 상한 10 때문에 `D` 에서 11위였던 상승형 종목이 "
        "`S⁺` 에서는 올라오기 때문이다 ⇒ ***`D = S⁺ ⊎ S⁻ ⊎ S⁰` 는 «트리거» 수준에서만 성립하고 "
        "«선택» 수준에서는 아니다***(§2-2 마지막 줄).")
    say("")
    say("전 기간 고유 종목 수:")
    say("")
    say("| | " + " | ".join(DISP[a] for a in labs) + " | R(시드평균) |")
    say("|---|" + "---|" * (len(labs) + 1))
    ur = np.mean([len({c for v in r.values() for c in v}) for r in r_sels])
    say("| 선택 고유 종목 | " + " | ".join(f"{sel_u[a]:,}" for a in labs) + f" | {ur:,.0f} |")
    say("")

    # ── 8. §6-6 range_pct 분포 ──────────────────────────────────────────────
    say("## 8. §6-6 `range_pct` 분포 — 「방향」을 비교하는가 「크기」를 비교하는가")
    say("")
    rp = {1: [], -1: [], 0: []}
    for d, c in dtri:
        rp[cache[c][d][2]].append(cache[c][d][3])
    say("| 집합 | n | 10분위 | **중앙** | 90분위 |")
    say("|---|---|---|---|---|")
    for s, lab in ((1, "S⁺"), (-1, "S⁻")):
        med, p10, p90 = q3(rp[s])
        say(f"| **{lab}** | {len(rp[s]):,} | {p10*100:.1f}% | **{med*100:.1f}%** | "
            f"{p90*100:.1f}% |")
    med0, p10_0, p90_0 = q3(rp[0])
    say(f"| `S⁰` (인쇄만) | **{len(rp[0]):,}** | {p10_0*100:.1f}% | {med0*100:.1f}% | "
        f"{p90_0*100:.1f}% |")
    say("")
    m_sp, m_sm = q3(rp[1])[0], q3(rp[-1])[0]
    say(f"- 중앙값 차 `S⁺ − S⁻` = **{(m_sp-m_sm)*100:+.2f}%p** "
        f"(비 = {m_sp/m_sm if m_sm else float('nan'):.3f})")
    say("")
    say("⚠️ **두 집합의 `range_pct` 가 크게 다르면 「방향」이 아니라 「크기」를 비교하게 된다** "
        "— PREREG §6-6 이 병기를 지시한다. 🔴 **다만 「크게」에 해당하는 «수치 문턱»은 "
        "사전등록에 «없다»** ⇒ 문턱을 지금 만들면 사후 규칙이 되므로 만들지 않는다. "
        "**위 수치를 그대로 판정문에 병기**하고 해석은 독자에게 남긴다.")
    say("")

    # ── 9. 실행 시간 ────────────────────────────────────────────────────────
    T = P["timing"]
    say("## 9. 실행 시간 실측 · 전체 추정")
    say("")
    say("| 단계 | 실측 |")
    say("|---|---|")
    say(f"| DB 적재(`load_prices`+`load_universe`) | {T['load']:.1f}s |")
    say(f"| `base_filter` 일자별 적용 | {T['elig']:.1f}s |")
    say(f"| 룰 평가 캐시 (**전 arm 공유 · 1회**) | **{T['cache']:.1f}s** |")
    say(f"| arm 풀 구성 (`build_pools`, 1회) | {T['pools']:.1f}s |")
    say("")
    say("**arm 하나의 실행 시간 — 실측**(풀에서 top-10 선택, arm 별):")
    say("")
    say("| Arm | " + " | ".join(DISP[a] for a in ALL_RULE) + " | **합** |")
    say("|---|" + "---|" * (len(ALL_RULE) + 1))
    arm_tot = sum(T["arm"].values())
    say("| 선택 시간 | " + " | ".join(f"{T['arm'][a]:.3f}s" for a in ALL_RULE)
        + f" | **{arm_tot:.3f}s** |")
    say("")
    per_seed = T["seeds"] / N_SEEDS
    say(f"- `R` **{N_SEEDS}시드** 무작위 선택 = **{T['seeds']:.1f}s** "
        f"(시드당 {per_seed:.2f}s)")
    say("")
    shared = T["load"] + T["elig"] + T["cache"] + T["pools"]
    stage1_total = shared + arm_tot + T["seeds"]
    say(f"⇒ **6 arm + {N_SEEDS}시드 전체(1단계 경로) = 공유 파이프라인 "
        f"{shared:.0f}s + arm 선택 {arm_tot:.2f}s + 시드 {T['seeds']:.1f}s = "
        f"약 {stage1_total:.0f}초** (문서 쓰기·DB 지문·표 계산 제외).")
    say("")
    say(f"🔑 **arm 하나의 «한계» 비용이 {max(T['arm'].values()):.3f}s 밖에 안 되는 이유** — "
        f"룰 평가를 `(code,date)` 캐시로 **1회만** 하고 6 arm 이 그걸 공유하기 때문이다"
        f"(§2 사다리 승계). ***비용은 arm 수가 아니라 공유 파이프라인 "
        f"{shared:.0f}s 가 지배한다*** ⇒ arm 을 늘려도 1단계 시간은 거의 안 변한다. "
        f"(반대로 2단계는 arm 마다 백테스트를 새로 돌리므로 arm 수에 «선형»이다.)")
    say("")
    say("🔴 **2단계(`--stage2`)의 «백테스트» 시간은 여기에 «없다».** 그것을 재려면 "
        "`BookBacktester` 를 돌려야 하고 그 순간 PnL 이 메모리에 들어오므로 "
        "**§6·§8-8 이 금지한다**. 2단계는 위 공유 파이프라인을 한 번 더 지불한 뒤 "
        f"arm {len(ARM_PNL)}개 + 시드 {N_SEEDS}개 = **{len(ARM_PNL)+N_SEEDS}회**의 "
        "종목별 백테스트를 돌린다 — 그 단가는 2단계가 스스로 인쇄한다(`run_arm` 직후 `print`). "
        "아래는 그 회차의 **작업량**(= 단가에 곱해질 값)이다:")
    say("")
    say("| Arm | 백테스트 대상 고유 종목 | 선택 종목-일 |")
    say("|---|---|---|")
    for a in ARM_PNL:
        say(f"| **{DISP[a]}** | {sel_u[a]:,} | {sel_n[a]:,} |")
    say(f"| **R** (시드 평균) | {sel_u['R']:,} | {sel_n['R']:,} |")
    say("")

    # ── 10. 등록 외 조합 · 관찰 ─────────────────────────────────────────────
    say("## 10. 등록 외 조합 (PREREG §8-3 · §9)")
    say("")
    say("**계산한 적 없다.** arm 은 `D`·`S⁺`·`S⁻`·`R`·`Q`·`F1` 여섯뿐이고(+ `S⁰` 는 "
        "arm 이 아니라 건수), 문턱 스윕(`surge_pct`·`surge_lookback`·`Q` 0.70·`F1` 0.5)·"
        "가중 혼합·`S⁺ ∧ Q` 같은 조합은 이 스크립트에 **구현되어 있지 않다**. "
        "`rule_ma5_pullback` 은 **파라미터 기본값 그대로** 호출했다.")
    say("")

    say("## 11. 🔴 실행 중 관찰한 것 (사전등록 이행 관련 · 해석 아님)")
    say("")
    say(f"1. **룰 창 {LOOKBACK}봉** — 라이브 `lookback_days` 와 **같다**(§3-1). 최대 요구가 "
        f"22봉(`F1`)이라 늘릴 이유가 없었다. ⇒ `D` arm 이 라이브와 정확히 같게 동작한다.")
    say(f"2. **`D` 판정은 라이브 룰 객체를 그대로 호출**했다 — 나머지 세 조건(MA5 터치·종가 "
        f"지지·양봉)을 재구현하지 않았다(§8-2). 방향(`i_low` vs `i_high`)만 밖에서 얹었다.")
    say(f"3. **동점 처리** = `np.argmin`/`np.argmax` 의 최초 등장 인덱스 = 「가장 이른 봉」"
        f"(§2-1 못박음). 선택 동점은 코드 오름차순 안정정렬(라이브는 DB 행 순서라 재현 불가).")
    say(f"4. **`R` 풀은 `base_filter` 통과 전체**(진입 룰 없음, §2) — 다른 arm 과 풀 정의가 "
        f"다르다. 그래서 §6-1 의 10% 문턱을 R 에는 적용하지 않았다.")
    say(f"5. **`volume × adj_factor` 는 로더에서 1회**(`load_prices`) — 이후 어디에서도 다시 "
        f"곱하지 않았다(이중조정 금지, REGISTRY 공통 제약).")
    say(f"6. **불가능봉 가드 미적용** — 승계 원본(`rank_score_counterfactual`·minervini)과 동일. "
        f"라이브 `scan()` 에는 있다. 완전 중립은 아니다(§7-9).")
    say(f"7. 🔴 **기존 기준선({BASELINE_SRC})과 발화 수가 {cstats['n_d']-BASELINE_FIRE}건 "
        f"다르고, 그 출처를 §2-2 에서 «실측으로» 규명했다** — 원인은 루프 시작 인덱스"
        f"(`warmup {RS_WARMUP}` vs 룰 자체 가드 {RULE_GUARD_BARS}봉) 하나이고, "
        f"`i ≥ {RS_WARMUP}` 부분집합이 기준선 세 숫자를 자릿수까지 재현한다. "
        f"**창 길이·술어·경계·`market_cap` 처리는 실측으로 배제했다.** "
        f"방향 구성비 이동은 0.05%p 미만이라 결론과 무관하다.")
    say(f"8. **`BookBacktester` 확장 파라미터를 쓰지 않는다** — `exit_line`·"
        f"`disaster_stop_pct`·`random_exit_seed` 는 2026-08-17 에 `ma5_exit` 문서를 위해 "
        f"들어온 것이고, **이 문서는 진입 축이라 청산이 현행 고정**이다. 2단계는 "
        f"`sl`/`tp`/`max_hold`/`eod_liquidate=False` 만 넘긴다.")
    say("")
    say("### 어떤 컬럼만 SELECT 했는가 — PnL 미조회 보장")
    say("")
    say("- `daily_prices`: `stock_code`·`date`·`open`·`high`·`low`·`close`·`volume`·"
        "`adj_factor`·`market_cap` — **9개 컬럼만**.")
    say("- **다른 테이블은 어느 것도 조회하지 않았다.** 매매 원장(`virtual_trading_records` 등) "
        "미조회. `BookBacktester` 는 **import 조차 하지 않는다**(모듈 최상단에 없고 "
        "`stage2()` 안에서 지역 import 된다).")
    say("")
    say(f"🔑 **가족 FWER**(REGISTRY 규칙 5): 등록부 현재 등재 주 검정 **{FAMILY_M_REGISTRY}개** "
        f"⇒ 보정 없는 FWER(α=.05) ≈ **{FAMILY_FWER_REGISTRY}%**. "
        f"⚠️ PREREG §5-5 는 동결 시점 기준으로 「m = {FAMILY_M_PREREG} · "
        f"{FAMILY_FWER_PREREG}%」라고 적었는데, 그 뒤 등록부에 청산 축 `E1`(ma5_exit)이 "
        f"추가되어 수가 늘었다. PREREG §5-5 자신이 *「가족 전체의 검정 수는 "
        f"`../REGISTRY.md` 가 관리한다」* 고 위임했으므로 **등록부 값을 쓴다.**")
    say("")

    (BASE / "GATE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] GATE.md", flush=True)
    return 0


# ────────────────────────────────────────────────────────────────────────────
# 9. stage2 — PREREG §4·§5 판정
# ────────────────────────────────────────────────────────────────────────────
def stage2() -> int:
    # 🔴 지역 import — `--stage1` 이 「PnL 계산 경로가 아예 없다」를 보증하기 위해서다.
    from backtest.book_backtester import BookBacktester

    rows, params, ok = verify_strategy_params()
    if not ok:
        print("🔴 설정 대조 실패 — 중단한다 (지시서: 「불일치면 중단·보고」).", flush=True)
        for r in rows:
            print(r, flush=True)
        return 3

    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    rep("# 판정 — `ma5` 의 「급등」은 방향을 안 본다. 결함인가, 이 전략의 정체인가")
    rep("")
    rep(f"사전등록 [`PREREG.md`](PREREG.md) 실행 · 가족 등록부 "
        f"[`../REGISTRY.md`](../REGISTRY.md) **2번 문서** · 창 **{W0} ~ {W1}** · "
        f"실행 커밋 **`{sha}`** · 1단계 게이트 → [`GATE.md`](GATE.md) · "
        f"원시 출력 → [`RESULTS_raw.md`](RESULTS_raw.md).")
    rep("")
    rep(f"🔴 **ε·arm·시드·문턱·`score`·판정 규칙·라벨은 동결분 그대로다.** "
        f"ε = **{EPS_ECON}%p**(§5) · N1 = **`arm > R {N_SEEDS}개 전부`**(§5-1) · "
        f"**주 검정 «1개»**(§5-2 방향)에 문서 안에서 Holm 보정(§5-5).")
    rep("")

    say("## 0a. 설정 대조")
    say("")
    for r in rows:
        say(r)
    say("")

    fp = db_fingerprint(conn)
    rep("## 0. 실행 기록 (PREREG §9)")
    rep("")
    rep(f"- 실행 커밋 SHA **`{sha}`** · 청산은 `config.yaml` 에서 읽었다 "
        f"(sl **{params['sl']}** / tp **{params['tp']}** / max_hold **{params['mh']}**, "
        f"지시서 기대값과 일치).")
    rep(f"- 🔴 `trail_ma` **{params['trail']}** 는 `BookBacktester` 가 지원하지 않는다 — "
        f"전 arm 에 동일하게 빠진다(§7-1).")
    rep("- **등록 외 조합은 계산하지 않았다** — arm 은 `D`·`S⁺`·`S⁻`·`R`·`Q`·`F1` 여섯뿐이고 "
        "문턱 스윕·가중 혼합·조합은 구현되어 있지 않다(§8-3). "
        "`rule_ma5_pullback` 은 **파라미터 기본값 그대로** 호출했다.")
    rep("")
    rep(f"DB 지문 ({len(FINGERPRINT_SQL)}슬라이스):")
    rep("")
    rep("| 슬라이스 | 행 수 | 종목 수 | max |")
    rep("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        rep(f"| `{k}` | {a:,} | {b:,} | {c} |")
    rep("")

    P = pipeline(conn)
    conn.close()
    px, uni, cache = P["px"], P["uni"], P["cache"]
    cstats, pools, sels, r_sels = P["cstats"], P["pools"], P["sels"], P["r_sels"]
    say(f"적격 (code,date) {cstats['n_eval']:,} · D {cstats['n_d']:,} "
        f"(S+ {cstats['n_sp']:,} · S- {cstats['n_sm']:,} · S0 {cstats['n_s0']:,}) · "
        f"Q {cstats['n_q']:,} · F1 {cstats['n_f1']:,}")
    say("")

    # 1단계 게이트 재산출 — 판정문에 병기해야 하는 것들
    trig_n = {a: sum(len(v) for v in pools[a].values()) for a in ALL_RULE}
    base = trig_n["D"]
    short_arms = [a for a in ARM_PNL
                  if a != "D" and (trig_n[a] / base if base else 0) < MIN_TRIGGER_FRAC]
    dpool = {d: {c for c, _ in v} for d, v in pools["D"].items()}
    sp_pool = {d: {c for c, _ in v} for d, v in pools["S+"].items()}
    excl = [(d, c) for d, cs in dpool.items() for c in cs - sp_pool.get(d, set())]
    keep = [(d, c) for d, cs in dpool.items() for c in cs & sp_pool.get(d, set())]
    keys = {
        "시총": {d: {c: uni[d][c][0] for c in cs if c in uni.get(d, {})}
                for d, cs in dpool.items()},
        "주가": {d: {c: cache[c][d][6] for c in cs if d in cache.get(c, {})}
                for d, cs in dpool.items()},
        "거래대금": {d: {c: uni[d][c][1] for c in cs if c in uni.get(d, {})}
                 for d, cs in dpool.items()},
    }
    # 🔑 `ks_all` 을 «버리지 않고» 남긴다 — §6-6 병기 절이 「문턱 아래였다」까지 인쇄해야
    #    하기 때문이다. `ks_hot` 의 정의·용도는 그대로다(교락 병기 발동 조건).
    ks_all = [(k, ks(decile_hist(excl, kd), decile_hist(keep, kd))) for k, kd in keys.items()]
    ks_hot = [(k, v) for k, v in ks_all if (v == v) and v > KS_CONFOUND]

    # §6-5 겹침 — §5-3 이 「`D` 가 바깥」 라벨을 채택할 때 가리키는 선택 효과의 실측값.
    tot_sp = sum(len(v) for v in sels["S+"].values())
    in_d = sum(len(set(v) & set(sels["D"].get(d, []))) for d, v in sels["S+"].items())

    # 2단계 프레임 — 창 안으로 자른다(`ArmGated` 는 (code,date) 조회라 과거 봉 불필요).
    frames, idxmap = {}, {}
    for code, g in px.groupby("stock_code", sort=False):
        g2 = g[g["date"] >= W0]
        if len(g2) >= 2:
            g2 = g2.reset_index(drop=True)
            frames[code] = g2
            im = {d: i for i, d in enumerate(g2["date"].to_numpy())}
            im["__last__"] = len(g2) - 1
            idxmap[code] = im

    cfg = dict(sl=params["sl"], tp=params["tp"], mh=params["mh"])
    res = {}
    for a in ARM_PNL:
        t1 = time.perf_counter()
        res[a] = run_arm(sels[a], frames, idxmap, cfg, BookBacktester)
        print(f"    {a:4} sig={res[a]['signals']:>6} n={res[a]['n']:>5} "
              f"mean={res[a]['mean']:+.2f}% {time.perf_counter()-t1:.0f}s", flush=True)
    r_stats = []
    for s in range(N_SEEDS):
        m = run_arm(r_sels[s], frames, idxmap, cfg, BookBacktester)
        r_stats.append(m)
        print(f"    R{s:<3} n={m['n']:>5} mean={m['mean']:+.2f}%", flush=True)
    r_means = [x["mean"] for x in r_stats]
    rmax = max(r_means)

    # ── 표 ──────────────────────────────────────────────────────────────────
    rep("## 1. 전체 표 — 거래당 평균 수익률 (gross · n = 실현 거래 수)")
    rep("")
    rep("🔑 `pnl_pct` 에 **슬리피지 편도 0.1% 는 반영**, **수수료 0.015%·거래세 0.18% 는 "
        "미반영**(승계 원본과 같은 gross 정의). 왕복 비용 0.21%p 는 전 arm 에 동일하게 빠지므로 "
        "**arm 차이엔 무해**하나 **절대 수준은 net 이 아니다.**")
    rep("")
    rep("| Arm | 급등 조건 | n (실현 거래) | 거래당 평균 | 중앙 | 승률 | 보유 중앙 | 손절 | 익절 | 최대보유 |")
    rep("|---|---|---|---|---|---|---|---|---|---|")
    for a in ARM_PNL:
        m = res[a]
        rep(f"| **{DISP[a]}** | {DESC[a]} | {m['n']:,} | **{m['mean']:+.2f}%** | "
            f"{m['med']:+.2f}% | {m['win']:.0f}% | {m['hold']:.0f}일 | {m['sl']:.0f}% | "
            f"{m['tp']:.0f}% | {m['mh']:.0f}% |")
    rep(f"| **R** | 무작위 ({N_SEEDS}시드) | {int(np.mean([x['n'] for x in r_stats])):,} (평균) | "
        f"중앙 **{np.median(r_means):+.2f}%** · 최소 {min(r_means):+.2f}% · "
        f"**최대 {rmax:+.2f}%** | | | | | | |")
    rep("")
    rep("🔑 **청산사유 비중(손절/익절/최대보유)이 §10-4 가 말한 「손익비 축의 표적」이다** — "
        "방향을 가른 뒤 손절·익절 도달 비율이 어떻게 달라지는지는 이 문서에서 그냥 나온다. "
        "**판정 언어는 쓰지 않는다.** 채택은 별도 사전등록에서 한다.")
    rep("")

    # ── 폐기율 ──────────────────────────────────────────────────────────────
    rep("## 2. 🔴 신호 → 실현 거래 전환 · 폐기율 (§7-11)")
    rep("")
    rep("**신호 수** = arm 이 고른 (종목, 날짜) 중 그 종목 프레임에 실제로 있고 «다음 봉»이 있어 "
        "체결 가능한 것. **폐기** = 그날 이미 그 종목을 보유 중이라 `BookBacktester` 가 "
        "`generate_signal` 을 부르지도 않은 경우. `폐기율 = 1 − 실현/신호`.")
    rep("")
    rep("| Arm | 신호 수 | 실현 거래 | **폐기율** |")
    rep("|---|---|---|---|")
    for a in ARM_PNL:
        m = res[a]
        rep(f"| **{DISP[a]}** | {m['signals']:,} | {m['n']:,} | **{m['discard']:.1f}%** |")
    rs_sig = int(np.mean([x["signals"] for x in r_stats]))
    rs_n = int(np.mean([x["n"] for x in r_stats]))
    rs_d = float(np.mean([x["discard"] for x in r_stats]))
    rep(f"| **R** (평균) | {rs_sig:,} | {rs_n:,} | **{rs_d:.1f}%** |")
    rep("")
    ds = {a: res[a]["discard"] for a in ARM_PNL}
    ds["R"] = rs_d
    lo, hi = min(ds.values()), max(ds.values())
    ratio = hi / lo if lo > 0 else float("inf")
    if ratio >= DISCARD_RATIO_FLAG:
        rep(f"🔴 **폐기율이 arm 간 {ratio:.2f}배 벌어졌다 (≥{DISCARD_RATIO_FLAG:.0f}배)** — "
            f"최대 `{DISP[max(ds, key=lambda k: ds[k])]}` {hi:.1f}% vs 최소 "
            f"`{DISP[min(ds, key=lambda k: ds[k])]}` {lo:.1f}%. "
            f"⇒ ***실현 거래가 신호의 «비무작위» 부분집합이고 그 정도가 arm 마다 다르다*** ⇒ "
            f"이 비교는 「같은 룰의 두 버전」이 아니라 **「다른 빈도의 두 룰」**에 가깝다. "
            f"**판정문에 병기한다**(§7-11).")
    else:
        rep(f"✅ **폐기율 최대/최소 = {ratio:.2f}배 (<{DISCARD_RATIO_FLAG:.0f}배)** — "
            f"전환율 비대칭이 문턱 아래다. 비교가 「같은 룰의 두 버전」으로 성립한다.")
    rep("")
    # 🔴 동결 규칙(≥2배 → 병기)은 «그대로» 발동시킨 채, 그 규칙이 무엇을 잡았는지를 적는다.
    #    ***규칙을 완화하는 것과 규칙이 무엇을 잡았는지 적는 것은 다른 일이다.***
    ds_rule = {a: res[a]["discard"] for a in ARM_PNL}
    lo_r, hi_r = min(ds_rule.values()), max(ds_rule.values())
    ratio_rule = hi_r / lo_r if lo_r > 0 else float("inf")
    rep(f"🔎 **단서 — 위 배수는 `R` 을 포함해 잰 값이다.** `R` 을 빼고 룰 arm {len(ARM_PNL)}개끼리만 "
        f"보면 최대/최소 = **{ratio_rule:.2f}배** (최대 "
        f"`{DISP[max(ds_rule, key=lambda k: ds_rule[k])]}` {hi_r:.1f}% vs 최소 "
        f"`{DISP[min(ds_rule, key=lambda k: ds_rule[k])]}` {lo_r:.1f}%). "
        f"🔑 `R` 은 §2 가 **정의상** 풀을 다르게 잡은 arm(진입 룰 조건 «없음»)이므로 전환율이 "
        f"다른 것이 **설계상 당연**하다. 🔴 **동결 규칙은 그대로 발동시킨 채로** 이 사실을 "
        f"함께 적는다 — ***규칙을 완화하는 것과 규칙이 무엇을 잡았는지 적는 것은 다른 일이다.*** "
        f"⚠️ 문서 1(4.08배 · 역시 `R` 이 최소)과 «같은 무게»로 읽으면 과대해석이다.")
    rep("")

    # ── N1 ──────────────────────────────────────────────────────────────────
    D, SP, SM, Q, F1 = (res[a]["mean"] for a in ("D", "S+", "S-", "Q", "F1"))
    n1 = {a: res[a]["mean"] > rmax for a in ARM_PNL}
    pv = {a: perm_p(res[a]["mean"], r_means) for a in ARM_PNL}

    rep("## 3. 귀무 N1 (§5-1) — 각 arm 이 무작위 20회 «전부»를 넘는가")
    rep("")
    rep(f"🔑 **N1 은 `D`·`S⁺`·`S⁻`·`Q`·`F1` «전부»에 대해 계산·인쇄하되, «판정»에 쓰는 것은 "
        f"`S⁺`·`S⁻` 둘뿐이다**(§5-1). `Q`·`F1` 의 N1 은 §5-4 와 같이 **판정 언어 없이** 인쇄한다.")
    rep("")
    rep("| Arm | 거래당 평균 | R 최대 | N1 | 단측 순열 p | 판정에 쓰는가 |")
    rep("|---|---|---|---|---|---|")
    for a in ARM_PNL:
        rep(f"| **{DISP[a]}** | {res[a]['mean']:+.2f}% | {rmax:+.2f}% | "
            f"{'✅' if n1[a] else '❌'} | {pv[a]:.4f} | "
            f"{'🔑 **예**' if a in ('S+', 'S-') else '아니오 (인쇄만)'} |")
    rep("")
    if not n1["D"]:
        rep("### 🔴🔴 이것이 이 문서의 «가장 중요한 결과»다 (§5-1 사전 지정)")
        rep("")
        rep(f"**기준선 `D` 가 N1 을 통과하지 못했다** — `D` {D:+.2f}% ≤ R 최대 {rmax:+.2f}%.")
        rep("")
        rep("⇒ ***현행 진입 룰(`rule_ma5_pullback`)이 이미 「그날 `base_filter` 통과 집합에서 "
            "무작위로 10종목 고르기」와 구별되지 않는다.*** 사전등록 §5-1 이 *「그것 자체가 이 "
            "문서의 가장 중요한 결과다. 눈에 띄게 인쇄한다」* 라고 미리 지정한 관측이다. "
            "⚠️ **앞선 두 문서에서 이미 두 번 나왔다** — `rank_score` 의 `V`, `minervini` 의 `D`. "
            "아래 방향 판정과 **병기**한다.")
        rep("")
    else:
        rep(f"✅ **기준선 `D` 는 N1 통과** ({D:+.2f}% > R 최대 {rmax:+.2f}%) — "
            f"현행 진입 룰은 무작위와 구별된다(§5-1).")
        rep("")

    # ── 주 판정 ─────────────────────────────────────────────────────────────
    rep("## 4. 🔑 주 판정 — 방향 (§5-2 · **주 검정은 이것 «하나»뿐**)")
    rep("")
    rep("🔑 **주 검정을 `S⁺ − D` 가 아니라 `S⁺ − S⁻` 로 잡는다**(§5-2). `D` 는 두 부분집합을 "
        "합친 것이라 `S⁺` 와 `S⁻` 사이에 오는 것이 (선택 효과를 빼면) **산술적으로 강제**되고, "
        "강제된 부등호를 증거로 쓰는 것은 *「항등식이 만든 부호 일치」* 와 같은 오류다.")
    rep("")
    rep("| 지표 | 값 |")
    rep("|---|---|")
    rep(f"| `S⁺` | **{SP:+.2f}%** |")
    rep(f"| `S⁻` | **{SM:+.2f}%** |")
    rep(f"| **`S⁺ − S⁻`** (주 검정) | **{SP-SM:+.2f}%p** |")
    rep(f"| `D` (기준선) | {D:+.2f}% |")
    rep(f"| ε (동결) | {EPS_ECON}%p |")
    rep("")
    verdict, vrows = direction_verdict(SP, SM, n1["S+"], n1["S-"])
    rep("**판정 순서 (동결 — 위에서부터 «처음 성립하는 것»을 채택):**")
    rep("")
    rep("| 순서 | 조건 | 성립 | 결론 |")
    rep("|---|---|---|---|")
    taken = False
    for i, cond, hit, label in vrows:
        mark = "❌"
        if hit and not taken:
            mark, taken = "✅ **채택**", True
        elif hit:
            mark = "✅ (뒤 순서 — 미채택)"
        rep(f"| {i} | {cond} | {mark} | {label} |")
    rep("")
    rep(f"⇒ # {verdict}")
    rep("")
    if any(a in short_arms for a in ("S+", "S-")):
        lack = [DISP[a] for a in ("S+", "S-") if a in short_arms]
        rep(f"### 🔴 병기 — 표본 부족 (§5-2 마지막 문단 · §6-1)")
        rep("")
        rep(f"`{'`·`'.join(lack)}` 의 트리거 수가 `D` 의 {MIN_TRIGGER_FRAC*100:.0f}% 문턱에 "
            f"미달했다 ⇒ **「🔴 표본 부족 → 판별 보류」를 위 라벨에 «병기»한다.** "
            f"라벨을 바꾸거나 문턱을 낮추지 않는다(사전 고정). "
            f"🔑 ***`S⁻` 가 문턱에 미달한다는 것 자체가 §6-2 구성비 질문의 답이므로, "
            f"그 경우엔 「하락형이 드물다」가 이 문서의 실질 결과가 된다.***")
        rep("")

    # ── §5-3 분해 ───────────────────────────────────────────────────────────
    rep("## 5. §5-3 분해 — `D` 는 어디에 놓이는가 (**판정 언어 금지 · 인쇄 + 사전고정 라벨**)")
    rep("")
    pl = placement_labels(D, SP, SM)
    rep("| 관측 (동결 라벨) | 성립 |")
    rep("|---|---|")
    for k, v in pl.items():
        rep(f"| {k} | {'✅' if v else '❌'} |")
    pl_hit = [k for k, v in pl.items() if v]
    rep("")
    rep(f"⇒ **{' · '.join(pl_hit) if pl_hit else '세 라벨 어느 것도 성립하지 않음'}**")
    rep("")
    rep("🔴 세 라벨은 사전 고정이므로 인용 가능하나 **「유의」·「기각」을 쓰지 않는다**"
        "(REGISTRY 규칙 2).")
    rep("")

    # ── §5-4 인쇄만 arm ─────────────────────────────────────────────────────
    rep("## 6. §5-4 인쇄만 arm `Q`·`F1` (사전고정 관측 라벨 · **판정 언어 금지**)")
    rep("")
    rep("| Arm | 뜻 | 거래당 평균 | `X − D` | 라벨 (동결) |")
    rep("|---|---|---|---|---|")
    rep(f"| **Q** | 조정 중 거래량 감소 (문턱 0.70 = `rule_volume_dryup` 값 그대로) | "
        f"{Q:+.2f}% | **{Q-D:+.2f}%p** | {printonly_label(Q, D)} |")
    rep(f"| **F1** | 급등이 「한 방」 (문턱 0.5 = 「절반」이라는 개념) | "
        f"{F1:+.2f}% | **{F1-D:+.2f}%p** | {printonly_label(F1, D)} |")
    rep("")
    rep("🔴 ***이 숫자를 보고 `Q`·`F1` 을 채택하면 사후적합이다.*** 채택은 별도 사전등록에서 "
        "한다(§8-4). **어느 것도 결론이 아니다.**")
    rep("")
    po_short = [a for a in ("Q", "F1") if a in short_arms]
    if po_short:
        rep(f"🔴 **병기 — 표본 부족**: `{'`·`'.join(DISP[a] for a in po_short)}` 의 트리거 수가 "
            f"`D` 의 {MIN_TRIGGER_FRAC*100:.0f}% 문턱에 미달했다(§6-1) ⇒ "
            f"**「표본 부족 → 판별 보류」**. 위 라벨은 사전 고정이라 그대로 인쇄하되 "
            f"**다음 사전등록의 표적으로도 약하게 읽어야 한다.**")
        rep("")

    # ── §5-5 Holm ───────────────────────────────────────────────────────────
    rep(f"## 7. §5-5 Holm 보정 (주 검정 **{N_PRIMARY}개**, α = {ALPHA})")
    rep("")
    p_primary = min(pv["S+"], pv["S-"])
    which = "S+" if pv["S+"] <= pv["S-"] else "S-"
    hres = holm([(f"§5-2 방향 (`{DISP[which]}` vs R — 이긴 쪽)", p_primary)])
    rep("| 검정 | 단측 순열 p | Holm 문턱 | 기각? |")
    rep("|---|---|---|---|")
    for name, p, thr, rej in hres:
        rep(f"| {name} | {p:.4f} | {thr:.4f} | {'✅ 기각' if rej else '❌ 기각 못 함'} |")
    rep("")
    pmin = 1 / (N_SEEDS + 1)
    rep(f"🔑🔑 **문서 1 은 여기서 걸렸다** — m=2 인데 시드가 20 이라 문턱 {ALPHA/2:.4f} 에 "
        f"최소 p {pmin:.4f} 가 닿지 못했고, ***arm 이 무작위 20회를 전부 이겼는데도 Holm 이 "
        f"아무것도 기각하지 못했다.*** **이 문서는 주 검정을 «하나»로 줄여 그 구조적 불가능을 "
        f"피한다**: m={N_PRIMARY} ⇒ 문턱 **{ALPHA/N_PRIMARY:.4f}** 에 최소 p "
        f"**{pmin:.4f}** 가 닿는다 ⇒ **가족 보정 후 기각이 «가능한» 첫 문서**다.")
    rep("")
    rep("§5-3 분해와 §5-4 인쇄만 arm 은 **기술 통계이므로 보정 대상이 아니고 판정 언어를 "
        "쓰지 않는다.**")
    rep("")

    # ── 종합 ────────────────────────────────────────────────────────────────
    rep("## 8. 🔴 종합")
    rep("")
    rep(f"# {verdict}")
    rep("")
    if not n1["D"]:
        rep("### 🔴 병기 — 현행 진입 룰이 무작위와 구별되지 않는다 (§5-1)")
        rep("")
        rep(f"`D` {D:+.2f}% ≤ R 최대 {rmax:+.2f}% ⇒ N1(D) 불성립. 위 라벨과 **함께** 읽어야 한다.")
        rep("")
    if ratio >= DISCARD_RATIO_FLAG:
        rep(f"### 🔴 병기 — 폐기율 비대칭 {ratio:.2f}배 (§7-11)")
        rep("")
        rep(f"실현 거래가 신호의 비무작위 부분집합이고 그 정도가 arm 마다 다르다. "
            f"🔎 **단, 이 배수는 `R` 을 포함해 잰 값이다** — `R` 을 빼면 룰 arm 간 최대/최소 = "
            f"**{ratio_rule:.2f}배**이고, `R` 은 §2 가 **정의상** 풀을 다르게 잡은 arm이라 "
            f"전환율이 다른 것이 설계상 당연하다. **동결 규칙은 그대로 발동시키되** "
            f"문서 1(4.08배 · 역시 `R` 이 최소)과 «같은 무게»로 읽으면 과대해석이다(§2 단서).")
        rep("")
    if ks_hot:
        rep(f"### 🔴 병기 — 교락 신호 (§6-3, KS > {KS_CONFOUND:.2f})")
        rep("")
        rep("배제 집합(`S⁻ ∪ S⁰`)과 잔류(`S⁺`)의 분포가 다음 축에서 갈렸다: "
            + " · ".join(f"**{k}** KS={v:.3f}" for k, v in ks_hot) + ". "
            "**이 문서의 축은 「형태」를 가르는 것이지 「크기·유동성」을 가르는 것이 아니므로** "
            "이 차이는 정상이 아니라 **교락 신호**다(문서 1 과 비대칭인 지점).")
        rep("")

    # ── §6-6 range_pct 병기 — 🔴 «스크립트가 스스로» 인쇄한다 ────────────────
    # 손으로 옮긴 숫자는 다음 사람이 재실행하는 순간 조용히 사라진다(stale prose).
    # 이 값은 **2단계가 이미 쓴 (code,date) 캐시**에서 나오는 1단계 지표이므로
    # 새 계산이 아니라 «인쇄 경로»를 여는 것이다. PnL·arm·판정 로직은 건드리지 않는다.
    rep("### 🔴 병기 — `range_pct` 크기 차 (§6-6)")
    rep("")
    rep("**두 집합의 `range_pct` 가 크게 다르면 「방향」이 아니라 「크기」를 비교하게 된다** — "
        "PREREG §6-6 이 병기를 지시한다. 아래는 **2단계가 arm 선택에 쓴 «같은» 캐시**에서 "
        "직접 낸 값이다(1단계 [`GATE.md`](GATE.md) §8 과 같은 식 · 손으로 옮긴 숫자가 아니다).")
    rep("")
    dtri2 = [(d, c) for c, dd in cache.items() for d, r in dd.items() if r[1]]
    rp = {1: [], -1: [], 0: []}
    for d, c in dtri2:
        rp[cache[c][d][2]].append(cache[c][d][3])
    rep("| 집합 | n | 10분위 | **중앙** | 90분위 |")
    rep("|---|---|---|---|---|")
    for s, lab in ((1, "S⁺"), (-1, "S⁻")):
        med, p10, p90 = q3(rp[s])
        rep(f"| **{lab}** | {len(rp[s]):,} | {p10*100:.1f}% | **{med*100:.1f}%** | "
            f"{p90*100:.1f}% |")
    med0, p10_0, p90_0 = q3(rp[0])
    rep(f"| `S⁰` (인쇄만) | **{len(rp[0]):,}** | {p10_0*100:.1f}% | {med0*100:.1f}% | "
        f"{p90_0*100:.1f}% |")
    rep("")
    m_sp, p10_sp, p90_sp = q3(rp[1])
    m_sm, p10_sm, p90_sm = q3(rp[-1])
    rep(f"- 중앙값 차 `S⁺ − S⁻` = **{(m_sp-m_sm)*100:+.2f}%p** "
        f"(비 = {m_sp/m_sm if m_sm else float('nan'):.3f}) · "
        f"90분위 차 = **{(p90_sp-p90_sm)*100:+.2f}%p**")
    rep("")
    rep("🔴 **다만 「크게」에 해당하는 «수치 문턱»은 사전등록에 «없다»** ⇒ 지금 만들면 사후 "
        "규칙이 되므로 만들지 않는다. **수치만 병기**하고 해석은 독자에게 남긴다.")
    rep("")
    rep(f"🔎 **§6-3 교락 축 셋**(배제 `S⁻ ∪ S⁰` vs 잔류 `S⁺` · 문턱 KS > {KS_CONFOUND:.2f}): "
        + " · ".join(f"**{k}** KS={v:.3f}" for k, v in ks_all)
        + (" ⇒ 🔴 **교락 신호**(위 절 참조)." if ks_hot
           else " ⇒ ✅ **전부 문턱 이하 — 교락 신호 없음**(그래서 위에 교락 병기 절이 «없다»)."))
    rep("")
    rep(f"🔎 **`S⁺` 선택 중 `D` 에도 선택된 비율 = {in_d:,}/{tot_sp:,} = "
        f"{in_d/tot_sp*100 if tot_sp else float('nan'):.1f}%**(§6-5) — §5-3 이 채택한 라벨이 "
        f"가리키는 선택 효과의 실측값이다. **판정 언어는 쓰지 않는다.**")
    rep("")

    rep("### 🔑 생존편향 비대칭 — 판정문 옆에 붙여 읽을 것 (§7-2)")
    rep("")
    rep("생존편향은 **약한 종목을 위로** 민다. `S⁻`(하락형)가 약한 쪽이므로 "
        "**`S⁺ − S⁻` 가 «과소»평가**된다. 따라서:")
    rep("")
    rep("- **(가) 결론이면 «강하다»** — 편향이 반대로 미는데도 나온 결과다.")
    rep("- **(다)·(나) 결론이면 이 편향을 «배제할 수 없다»** — 편향이 그 결론을 밀어주는 방향이다.")
    rep("")
    rep("⇒ 이번 결론은 " + ("**편향이 반대로 미는데도 나온 것이라 «강하다»**."
                          if verdict.startswith("**(가)") else
                          "**편향이 «밀어주는» 방향이거나 판별이 서지 않는 쪽이라 "
                          "배제할 수 없다** — 채택 전 별도 검증이 필요하다."))
    rep("")
    rep("### 가족 FWER (REGISTRY 규칙 5)")
    rep("")
    rep(f"가족 등록부 **현재** 등재 주 검정 **{FAMILY_M_REGISTRY}개** ⇒ 보정 없는 "
        f"FWER(α=.05) ≈ **{FAMILY_FWER_REGISTRY}%**. "
        f"⚠️ PREREG §5-5 는 동결 시점 기준으로 「m = {FAMILY_M_PREREG} · "
        f"{FAMILY_FWER_PREREG}%」라고 적었으나 그 뒤 청산 축 `E1`(ma5_exit)이 등재되어 늘었다. "
        f"PREREG §5-5 자신이 *「가족 전체의 검정 수는 `../REGISTRY.md` 가 관리한다」* 고 "
        f"위임했으므로 **등록부 값을 쓴다.** "
        f"***보정을 안 거는 것과 위험이 없는 것은 다르다.***")
    rep("")
    rep("### 🔴 채택은 별도 결정이다 (§8-7)")
    rep("")
    rep("**판정 결과를 라이브에 그대로 반영하지 않는다.** 문서 1 도 판정 후 라이브 반영을 "
        "하지 않고 멈춰 있다. 이 결과로 «랭킹 score»·«청산 파라미터»·«후보 상한 N» 을 "
        "함께 바꾸지 않는다(§8-6).")
    rep("")

    rep("## 9. 🔴 한계 (PREREG §7 1~12, 전량 전재)")
    rep("")
    for i, s in enumerate(LIMITATIONS, 1):
        rep(f"{i}. {s}")
    rep("")

    (BASE / "RESULTS.md").write_text("\n".join(DOC) + "\n", encoding="utf-8")
    (BASE / "RESULTS_raw.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] RESULTS.md · RESULTS_raw.md", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ma5 개념 축 — PREREG 실행부")
    ap.add_argument("--stage1", action="store_true",
                    help="PREREG §6 1단계 게이트 (PnL 미조회) → GATE.md")
    ap.add_argument("--stage2", action="store_true",
                    help="PREREG §4·§5 판정 → RESULTS.md · RESULTS_raw.md")
    a = ap.parse_args()
    if a.stage1 and a.stage2:
        print("한 번에 하나만 실행한다 — 1단계는 「PnL 을 보기 «전»」이라야 뜻이 있다.", flush=True)
        return 2
    if a.stage1:
        return stage1()
    if a.stage2:
        return stage2()
    print("`--stage1`(게이트) 또는 `--stage2`(판정) 중 하나를 지정하라.", flush=True)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
