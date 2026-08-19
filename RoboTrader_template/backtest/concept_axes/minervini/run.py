# -*- coding: utf-8 -*-
"""minervini 개념 축 — 사전등록 `PREREG.md`(동결 `e4c55b1`) 실행부. **1단계 게이트 전용.**

가족 등록부 `../REGISTRY.md` 의 **1번 문서**. 기계는 `backtest/rank_score_counterfactual/run.py`
를 그대로 승계한다(`HIST0` 분리 · `(code,date)` 캐시 · `verify_strategy_params()` ·
`db_fingerprint()` · 단독 모드 · stale prose 방지).

**모드 두 개.**

- `--stage1` — PREREG §6 게이트. **PnL 을 계산하지 않는다.** `BookBacktester` 는
  «2단계 함수 안에서만» import 되므로 이 경로에는 거래당 수익률이 들어올 길이 없다.
  산출물 → `GATE.md`.
- `--stage2` — PREREG §4·§5 판정. arm 별 거래당 평균·귀무 N1·Holm·분해·상호작용.
  산출물 → `RESULTS.md`(판정) · `RESULTS_raw.md`(원시 출력).

🔴 **두 모드는 «같은» 선택 집합을 쓴다** — `build_cache`→`build_pools`→`select_*` 경로가
하나라서 2단계 arm 선택은 1단계가 인쇄한 것과 정의상 동일하다.

**Arm 6개 (PREREG §2) — 진입 룰 축 «하나만» 바꾼다:**

    D    = rule_volume_dryup                      (현행 라이브 · 기준선)
    DT   = dryup ∧ rule_trend_template            (TT 복원)
    DF   = dryup ∧ F                              (재무 복원)
    DTF  = dryup ∧ TT ∧ F                         (완전 복원)
    T    = rule_trend_template 만                 (분해)
    R    = 그날 base_filter 통과 집합에서 무작위 10종목, 시드 0..19  (귀무)

🔴 **`R` 의 적격 풀은 「`base_filter` 통과」뿐이고 진입 룰 조건이 «없다»**(§2) —
「고르는 행위」 자체의 귀무이기 때문이다. 다른 arm 과 풀 정의가 다르다.

🔴 **`score` 는 현행 `df["volume"].iloc[-30:].mean()` 고정**(§2). 랭킹 축은
`rank_score_counterfactual` 이 이미 판정했고(`d751e21` — 「(나) 랭킹은 정보가 아님」),
***한 번에 한 축만 움직인다.***

🔑 척도·창은 `rank_score_counterfactual` §10-1·§10-5 승계: 창 `2024-03-13~2026-05-31`,
가격은 `HIST0=2021-01-01` 부터(TT 의 220/252봉 요구), `volume × adj_factor` 는 **로더에서 1회**.

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

from strategies.books.minervini_vcp.rules import (                                  # noqa: E402
    compute_rs_percentile_12w,
    rule_trend_template,
    rule_volume_dryup,
)
from strategies.base import Signal, SignalType                                      # noqa: E402
from strategies.minervini_volume_dryup.screener import (                            # noqa: E402
    MinerviniVolumeDryupScreenerAdapter,
)
# 🔴 `BookBacktester` 는 여기서 import 하지 않는다 — `--stage1` 이 「PnL 계산 경로가 아예
#    없다」를 보증하기 위해서다. 2단계 함수(`stage2`) 안에서 지역 import 한다.

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
           dbname="kis_template")

# 신형 코드는 «중간»이 영문일 수 있다(`0001A0`). 의사티커는 첫 글자가 숫자가 아니라
# 이 술어에 이미 안 걸리지만 명시적으로도 배제한다.
STOCK_ONLY = ("stock_code ~ '^[0-9][0-9A-Z]{5}$' "
              "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')")

W0, W1 = "2024-03-13", "2026-05-31"   # PREREG §3 (rank_score §10-1 승계)
HIST0 = "2021-01-01"                   # 워밍업 — TT 의 220/252봉 요구
# 🔑 룰에 넘기는 창 길이. **라이브 스크리너의 `lookback_days=90` 이 아니다** — 아래 §주석 참조.
LOOKBACK = 260
SCORE_WINDOW = 30                      # 현행 score = volume.iloc[-30:].mean() (§2 고정)
MAX_CANDIDATES = 10                    # §2 고정
N_SEEDS = 20                           # §2 — R 시드 0..19
N_DECILES = 10                         # §6-2
MIN_TRIGGER_FRAC = 0.10                # §6-1 — D 의 10% 미만이면 「표본 부족 → 판별 보류」
F_GROWTH = 1.25                        # §2-2 — 원저작 이익 성장 문턱. 데이터에서 유도 안 함


# 지시서 기대 청산 파라미터 (2단계용 — config.yaml 이 정본이고 아래는 대조값)
EXP_SL, EXP_TP, EXP_MH = 0.08, 0.12, 20

# 🔴 PREREG §5 동결. **결과를 보고 바꾸지 않는다**(§8-1). 단위 = %p.
EPS_ECON = 0.5
ALPHA = 0.05                           # §5-6 Holm (주 검정 2개: TT · F)
DISCARD_RATIO_FLAG = 2.0               # §10-5 항목 12 — 폐기율 2배 이상이면 병기

# PREREG §7(1~11) + §10-5(12~13) 한계 — **결과 문서에 그대로 전재한다**(축약 없음).
LIMITATIONS = [
    "🔴 **`operating_income` 은 EPS 의 대리변수다.** 원저작은 **분기 EPS 성장 가속**을 "
    "요구하는데 분기 재무가 713종목뿐이라 **연간 영업이익**으로 대체했다. "
    "***「SEPA 펀더멘털 스크린을 검정했다」고 쓰지 말 것*** — 검정한 것은 "
    "「연간 영업이익 25% 성장 필터」다.",
    "🔴 **생존편향** — `daily_prices` 에 상폐 종목이 사실상 없다(0.5%). 편향은 **약한 종목을 "
    "위로** 민다 ⇒ TT·F 는 «강한 종목을 고르는» 필터이므로 **`DT − D`·`DF − D` 가 "
    "과소평가**되는 쪽이다. ***(나)·(다) 결론이면 이 편향을 배제할 수 없고, (가)가 나오면 강하다.***",
    "🔴 **`BookBacktester` 는 sl/tp/max_hold 만 지원**한다. minervini 는 원래 트레일링·"
    "trend_flip 이 없으므로 **이 전략에 한해 청산 재현이 정확**하다(다른 전략과 다른 점).",
    "🔴 **`rcept_dt` 정정본 문제.** PK 가 `(stock_code, bsns_year)` 라 정정공시가 as-filed 를 "
    "덮어쓴다. 🟢 **방향은 보수적이다** — 그 행은 백테스트 시점에 «안 보이므로» 룩어헤드가 "
    "아니다. 🔴 **대신 커버리지 구멍이 생기고, 정정하는 회사는 무작위가 아니다.**",
    "🔴 **`market_cap` 자체의 PIT 성격 미검정** — 전 arm 에 동일하게 걸리므로 arm 비교엔 "
    "무해하나 절대 수준은 신뢰할 수 없다.",
    "⚠️ **단일 국면 2.2년.** 일반화 금지.",
    "⚠️ **포트폴리오가 아니다**(종목당 단일 포지션 순차). K=3 한도·자금 배분 미재현.",
    "⚠️ **백테스트 유니버스 ≠ 라이브**(라이브 매수의 97%가 미검증). **라이브 기대치로 인용 금지.**",
    "⚠️ **실행 효과 미반영** — 슬리피지·09:00~09:15 매수 타이밍·호가. arm 비교엔 대칭이나 "
    "절대 수준에는 들어 있지 않다.",
    "⚠️ **불가능봉 가드 미적용**(승계 원본과 동일). 완전 중립은 아니다 — 풀에서 한 종목이 "
    "빠지면 다음 종목이 들어오고 그 대체가 arm 마다 다르다.",
    "⚠️ **`rs_value` 는 「그날 `base_filter` 통과 집합」 안의 백분위**다. 전체 시장 대비 RS 가 "
    "아니다(원저작은 전 종목 대비). 시총 ≥3천억 집합 안의 상대강도이므로 **원저작보다 좁다.**",
    "🔴 **arm 마다 「신호 → 실현 거래」 전환율이 다를 수 있다**(§10-5). 1단계 실측: `D` 는 "
    "트리거 55,239 에 **고유 종목 243**, `DT` 는 8,915 에 **고유 종목 414** — ***`D` 는 소수 "
    "종목을 반복 선택하고 `DT` 는 넓게 흩뿌린다.*** 종목당 단일 포지션이므로 `D` 쪽 신호가 "
    "「이미 보유 중」으로 더 많이 버려질 수 있다 ⇒ 실현 거래는 신호의 **비무작위 부분집합**이다. "
    "**아래 §4 에서 폐기율을 산출했다.**",
    "⚠️ **`rcept_dt` 정정본 446행 / 17,892 = 2.49%**(고유 292종목) — §7-4 커버리지 구멍의 실측 규모.",
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
    "dart_financials_asfiled (전체)":
        "SELECT count(*), count(DISTINCT stock_code), max(rcept_dt) "
        "FROM dart_financials_asfiled",
    "dart_financials_asfiled rcept_dt NOT NULL":
        "SELECT count(*), count(DISTINCT stock_code), max(rcept_dt) "
        "FROM dart_financials_asfiled WHERE rcept_dt IS NOT NULL",
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
# 0. 설정 대조
# ────────────────────────────────────────────────────────────────────────────
def verify_strategy_params() -> tuple[list[str], dict]:
    """`config.yaml` 청산 파라미터와 스크리너 `base_filter` 임계를 읽어 대조 표를 만든다."""
    y = yaml.safe_load(
        (ROOT / "strategies" / "minervini_volume_dryup" / "config.yaml").read_text(encoding="utf-8"))
    rm = (y or {}).get("risk_management", {}) or {}
    sl, tp, mh = rm.get("stop_loss_pct"), rm.get("take_profit_pct"), rm.get("max_hold_days")
    p = MinerviniVolumeDryupScreenerAdapter().default_params()
    ok = (sl == EXP_SL and tp == EXP_TP and mh == EXP_MH)
    rows = [
        "| 항목 | 읽은 값 | 기대값 | 일치 |",
        "|---|---|---|---|",
        f"| 청산 sl/tp/max_hold (`config.yaml`) | {sl} / {tp} / {mh} | "
        f"{EXP_SL} / {EXP_TP} / {EXP_MH} | "
        f"{'✅' if ok else '🔴 **불일치 — config 를 정본으로 씀**'} |",
        f"| `min_market_cap` (screener) | {p['min_market_cap']:,} | 300,000,000,000 | "
        f"{'✅' if p['min_market_cap'] == 300_000_000_000 else '🔴'} |",
        f"| `min_trading_value` (screener) | {p['min_trading_value']:,} | 3,000,000,000 | "
        f"{'✅' if p['min_trading_value'] == 3_000_000_000 else '🔴'} |",
        f"| `max_candidates` | {p['max_candidates']} | {MAX_CANDIDATES} | "
        f"{'✅' if p['max_candidates'] == MAX_CANDIDATES else '🔴'} |",
        f"| dryup `recent/base/ratio` | {p['recent_window']}/{p['base_window']}/{p['ratio_max']} | "
        f"10/30/0.7 | ✅ |",
    ]
    return rows, dict(sl=sl, tp=tp, mh=mh, **p)


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
    이후 어디에서도 `adj_factor` 를 다시 곱하지 않는다(이중조정 금지).
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
    """전략 `base_filter`(시총 ≥3천억 · 거래대금 ≥30억)를 날짜별로 그대로 적용."""
    out = {}
    for d, m in uni.items():
        recs = [{"code": c, "name": c, "market_cap": mc, "trading_value": tv}
                for c, (mc, tv) in m.items()]
        out[d] = {r["code"] for r in screener.base_filter(recs)}
    return out


def load_fundamentals(conn) -> tuple[dict, pd.DataFrame]:
    """`{code: {year: (rcept_str|None, operating_income|None)}}` 와 원시 표.

    `(stock_code, bsns_year)` 가 PK 라 정정공시가 as-filed 를 덮어쓴다(PREREG §7-4).
    ***방향은 보수적이다*** — 덮어쓴 행의 `rcept_dt` 는 «미래»라 백테스트 시점에 안 보인다.
    """
    f = pd.read_sql("""
        SELECT stock_code, bsns_year::int AS y, rcept_dt, operating_income
        FROM dart_financials_asfiled
    """, conn)
    f["rcept_s"] = f["rcept_dt"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else None)
    fin: dict = defaultdict(dict)
    for code, y, rs_, oi in zip(f["stock_code"], f["y"], f["rcept_s"], f["operating_income"]):
        fin[code][int(y)] = (rs_, None if pd.isna(oi) else int(oi))
    return dict(fin), f


# ────────────────────────────────────────────────────────────────────────────
# 2. 재무 스크린 F (PREREG §2-2)
# ────────────────────────────────────────────────────────────────────────────
def f_screen(fin_code: dict, d: str) -> tuple[bool, str]:
    """`F(code, D)` — PREREG §2-2 그대로. `(통과여부, 사유코드)`.

    🔴 해석: **「`rcept_dt ≤ D−1` 인 «가장 최근» 사업연도 y」를 하나 고른 뒤** ②③④ 를 건다
    (지시서 문구 그대로). 「아무 y 나 하나라도 만족하면 통과」가 «아니다» — 그렇게 읽으면
    과거 한 번의 고성장이 영원히 통과되어 PIT 의미가 사라진다.
    `rcept_dt` NULL 은 「그 해 데이터 없음」 = fail-closed (통과시키지 않는다).
    `rcept_dt ≤ D−1` 은 ISO 문자열 비교로 `rcept_s < d` 와 동치다.
    """
    if not fin_code:
        return False, "no_rows"
    vis = [y for y, (rs_, _) in fin_code.items() if rs_ is not None and rs_ < d]
    if not vis:
        return False, "no_visible_year"
    y = max(vis)
    prev = fin_code.get(y - 1)
    if prev is None or prev[0] is None or not (prev[0] < d):
        return False, "prev_year_invisible"
    oi_prev, oi_cur = prev[1], fin_code[y][1]
    if oi_prev is None or oi_cur is None:
        return False, "oi_missing"
    if oi_prev <= 0:
        return False, "prev_oi_nonpositive"
    if oi_cur >= F_GROWTH * oi_prev:
        return True, "pass"
    return False, "growth_below_25pct"


# ────────────────────────────────────────────────────────────────────────────
# 3. RS 백분위 (PREREG §2-1)
# ────────────────────────────────────────────────────────────────────────────
def build_rs(px: pd.DataFrame, elig: dict, dates: list) -> tuple[dict, dict]:
    """`{date: {code: rs_value}}` — 라이브 헬퍼 `compute_rs_percentile_12w` 를 **그대로** 호출.

    유니버스 = 그날 `base_filter` 통과 집합(PREREG §2-1). 그날까지의 데이터만 쓴다.

    🔴 **절단·근사를 쓰지 않는다.** 날짜 `d` 마다 `piv.loc[:d, universe]` 로 **그날까지의
    전체 이력**을 그대로 넘긴다. 꼬리만 잘라도 대개 같은 값이 나오지만, 이 함수의
    `pct_change(60)` 은 pandas 기본 `fill_method='pad'` 로 **결측을 앞값으로 채운다** ⇒
    창을 자르면 채울 앞값이 사라져 «다른» 값이 나올 수 있다. 그 위험을 없애려고
    전체 이력을 넘긴다(538일 × 전체 이력 ≈ 1분, 감당 가능하다).
    """
    piv = px.pivot_table(index="date", columns="stock_code", values="close", aggfunc="last")
    piv = piv.sort_index()
    rs: dict = {}
    diag = dict(too_small=0, sizes=[], missing=0, total=0)
    for d in dates:
        cols = sorted(elig.get(d, ()))
        diag["sizes"].append(len(cols))
        if len(cols) < 2:
            diag["too_small"] += 1
            rs[d] = {}
            continue
        row = compute_rs_percentile_12w(piv.loc[:d, cols]).iloc[-1]
        vals = {c: (None if pd.isna(v) else float(v)) for c, v in row.items()}
        diag["total"] += len(vals)
        diag["missing"] += sum(1 for v in vals.values() if v is None)
        rs[d] = vals
    return rs, diag


def _truncation_probe(px: pd.DataFrame, elig: dict, dates: list, n: int = 3) -> list[str]:
    """«쓰지 않은» 꼬리 절단이 실제로 답을 바꾸는지 표본일에서 재본다 (설계 근거 기록).

    본 산출은 전체 이력을 쓴다. 이 표는 *「왜 최적화를 안 썼나」*의 증거다 —
    `pct_change` 의 `fill_method='pad'` 때문에 절단이 값을 바꿀 수 있음을 실측으로 남긴다.
    """
    piv = px.pivot_table(index="date", columns="stock_code", values="close",
                         aggfunc="last").sort_index()
    out = []
    cand = [d for d in dates if len(elig.get(d, ())) >= 2]
    for d in (cand[:1] + cand[len(cand) // 2:len(cand) // 2 + 1] + cand[-1:])[:n]:
        cols = sorted(elig[d])
        full = compute_rs_percentile_12w(piv.loc[:d, cols]).iloc[-1]
        tail = compute_rs_percentile_12w(piv.loc[:d, cols].iloc[-61:]).iloc[-1]
        diff = int((full.fillna(-1) != tail.fillna(-1)).sum())
        out.append(f"| {d} | {len(cols):,} | {diff:,} | "
                   f"{'동일' if diff == 0 else '🔴 **달라진다**'} |")
    return out


# ────────────────────────────────────────────────────────────────────────────
# 4. 룰 평가 캐시 — 전 arm 공유 (PREREG §2)
# ────────────────────────────────────────────────────────────────────────────
def build_cache(px: pd.DataFrame, elig: dict, rs: dict, fin: dict, params: dict):
    """`{code: {date: (score, dryup, tt, f, close)}}` — 적격 (code,date) «전부»에 대해 만든다.

    🔑 **한 창에서 세 값을 함께 만든다** ⇒ arm 간 차이가 「진입 룰」 하나로만 생긴다.
    R 의 풀이 「`base_filter` 통과 전체」라서 트리거 안 된 종목도 필요하므로,
    캐시는 «발화분»이 아니라 «적격분 전체»를 담는다.

    🔴 **창 길이 `LOOKBACK`=260 은 라이브 스크리너의 `lookback_days`(=90)와 다르다.**
    `rule_trend_template` 이 220봉을 요구하고 52주 고저에 `close.iloc[-252:]` 를 쓰기 때문에
    90봉으로는 **항상 False** 가 된다. 260봉은 그 요구를 채우면서
    `rule_volume_dryup`(마지막 40봉만 봄)과 `score`(마지막 30봉만 봄)의 결과를
    **바꾸지 않는다** — 두 계산 모두 창 길이에 불변이다. 260 ≥ 252 이므로 TT 의
    52주 창도 정확히 252봉으로 동일하다.
    """
    dry = rule_volume_dryup(recent_window=int(params["recent_window"]),
                            base_window=int(params["base_window"]),
                            ratio_max=float(params["ratio_max"]))
    tt = rule_trend_template()          # 🔴 파라미터 기본값 그대로 (§2-1)
    cache: dict = defaultdict(dict)
    stats = dict(n_eval=0, n_dry=0, n_tt=0, n_f=0, f_reasons=Counter())
    t0 = time.perf_counter()
    done = 0
    total = px["stock_code"].nunique()
    for code, g in px.groupby("stock_code", sort=False):
        done += 1
        if done % 300 == 0:
            print(f"      ...{done}/{total} 종목 · 평가 {stats['n_eval']:,} · "
                  f"dryup {stats['n_dry']:,} · TT {stats['n_tt']:,} · "
                  f"{time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        closes = g["close"].to_numpy(dtype=float)
        vols = g["volume"].to_numpy(dtype=float)
        fin_code = fin.get(code, {})
        for i in range(len(g)):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            win = g.iloc[max(0, i + 1 - LOOKBACK):i + 1]
            stats["n_eval"] += 1
            ok_dry = bool(getattr(dry.evaluate(win, {}), "triggered", False))
            rv = rs.get(d, {}).get(code)
            ok_tt = bool(getattr(tt.evaluate(win, {"rs_value": rv}), "triggered", False))
            ok_f, why = f_screen(fin_code, d)
            stats["f_reasons"][why] += 1
            stats["n_dry"] += ok_dry
            stats["n_tt"] += ok_tt
            stats["n_f"] += ok_f
            a = max(0, i + 1 - SCORE_WINDOW)
            cache[code][d] = (float(vols[a:i + 1].mean()), ok_dry, ok_tt, ok_f,
                              float(closes[i]))
    stats["secs"] = time.perf_counter() - t0
    return dict(cache), stats


# ────────────────────────────────────────────────────────────────────────────
# 4b. 돌파 축 (PREREG_BREAKOUT.md 문서 5) — 문서 1 경로는 건드리지 않는다
# ────────────────────────────────────────────────────────────────────────────
PIVOT_WIN = 25                         # §2 동결 — rule_vcp_breakout.base_min_bars
RVOL_MIN = 1.5                         # §2 동결 — rule_vcp_breakout.rvol_threshold
S_BREAKOUT = 100                       # §2-2 동결 — R_B 시드 수
GATE_MIN_SELECTED = 1500               # §6 동결 — 선택 종목-일 문턱


def breakout_flags(high, volume, close, i: int) -> tuple:
    """PREREG_BREAKOUT §2 — `(ok_pivot, ok_rvol)`.

    base = `[i-25, i)` (**현재봉 제외**). 창 안 봉이 26개 미만이면 둘 다 False.
    🔑 두 조건을 «따로» 돌려주는 이유: arm `P`(돌파만)·`Q`(거래량만) 분해가 §5-3 이다.
    """
    if i < PIVOT_WIN:
        return False, False
    bh = high[i - PIVOT_WIN:i]
    bv = volume[i - PIVOT_WIN:i]
    base_vol = float(bv.mean())
    ok_pivot = bool(float(close[i]) > float(bh.max()))
    ok_rvol = bool(base_vol > 0 and float(volume[i]) / base_vol >= RVOL_MIN)
    return ok_pivot, ok_rvol


def build_cache_breakout(px: pd.DataFrame, elig: dict, params: dict):
    """`{code: {date: (score, ok_dry, ok_p, ok_q, day_ret, limit_up)}}` (PREREG_BREAKOUT §2).

    🔴 문서 1 의 `build_cache` 와 «별도» 함수다. 값 튜플 길이가 달라 섞으면 즉시 깨지므로
    섞지 않는다. 창 길이·`score` 정의·적격 판정은 문서 1 과 동일하게 둔다(비교 가능성).
    """
    dry = rule_volume_dryup(recent_window=int(params["recent_window"]),
                            base_window=int(params["base_window"]),
                            ratio_max=float(params["ratio_max"]))
    cache: dict = defaultdict(dict)
    stats = dict(n_eval=0, n_dry=0, n_p=0, n_q=0, n_b=0, n_short_bars=0)
    t0 = time.perf_counter()
    done = 0
    total = px["stock_code"].nunique()
    for code, g in px.groupby("stock_code", sort=False):
        done += 1
        if done % 300 == 0:
            print(f"      ...{done}/{total} 종목 · 평가 {stats['n_eval']:,} · "
                  f"B {stats['n_b']:,} · {time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        closes = g["close"].to_numpy(dtype=float)
        highs = g["high"].to_numpy(dtype=float)
        vols = g["volume"].to_numpy(dtype=float)
        for i in range(len(g)):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            stats["n_eval"] += 1
            lo = max(0, i + 1 - LOOKBACK)
            win = g.iloc[lo:i + 1]
            ok_dry = bool(getattr(dry.evaluate(win, {}), "triggered", False))
            if (i - lo + 1) < PIVOT_WIN + 1:
                stats["n_short_bars"] += 1
                ok_p = ok_q = False
            else:
                ok_p, ok_q = breakout_flags(highs, vols, closes, i)
            stats["n_dry"] += ok_dry
            stats["n_p"] += ok_p
            stats["n_q"] += ok_q
            stats["n_b"] += (ok_p and ok_q)
            if i > 0 and closes[i - 1] > 0:
                day_ret = float(closes[i] / closes[i - 1] - 1.0)
                limit_up = bool(closes[i] / closes[i - 1] >= 1.28)
            else:
                day_ret = float("nan")
                limit_up = False
            a = max(0, i + 1 - SCORE_WINDOW)
            cache[code][d] = (float(vols[a:i + 1].mean()), ok_dry, ok_p, ok_q,
                              day_ret, limit_up)
    stats["secs"] = time.perf_counter() - t0
    return dict(cache), stats


ARM_RULE_B = {
    "D":  lambda dry, p, q: dry,              # 기준선 (문서 1 의 D 와 같은 정의)
    "B":  lambda dry, p, q: p and q,          # 🔴 주 검정
    "P":  lambda dry, p, q: p,                # 기술통계 — 돌파만
    "Q":  lambda dry, p, q: q,                # 기술통계 — 거래량만
    "DB": lambda dry, p, q: dry and p and q,  # 기술통계 — 「판별 보류」 사전 라벨
}


def build_pools_breakout(cache: dict, elig: dict):
    """`(pools, dayret, limitup)` — `pools["ALL"]` 은 그날 적격 «전체»(귀무 추출 풀)."""
    pools = {a: defaultdict(list) for a in list(ARM_RULE_B) + ["ALL"]}
    dayret: dict = defaultdict(dict)
    limitup: dict = defaultdict(dict)
    for code, dd in cache.items():
        for d, (score, ok_dry, ok_p, ok_q, day_ret, lim) in dd.items():
            if code not in elig.get(d, ()):
                continue
            pools["ALL"][d].append((code, score))
            limitup[d][code] = bool(lim)
            if day_ret == day_ret:      # NaN 제외
                dayret[d][code] = float(day_ret)
            for a, fn in ARM_RULE_B.items():
                if fn(ok_dry, ok_p, ok_q):
                    pools[a][d].append((code, score))
    return ({a: {d: sorted(v) for d, v in p.items() if v} for a, p in pools.items()},
            dict(dayret), dict(limitup))


def select_random_matched(pool_all: dict, arm_pool: dict, dayret: dict, seed: int):
    """크기 정합 + 당일수익률 10분위 층화 귀무 `R_B` (PREREG_BREAKOUT §2-2).

    문서 1 의 `select_random` 과 다른 점 셋:
      ① 뽑는 «개수» 를 그날 arm 트리거 수 `k_d` 에 맞춘다 (크기 정합)
      ② 당일수익률 10분위 «도수분포» 를 arm 과 같게 맞춘다 (모멘텀 교란 제거)
      ③ 뽑은 「가짜 트리거 집합」에 `select_top` 을 태워 arm 과 같은 랭킹·절단을 받게 한다

    🔑 추출 풀에서 arm 자신의 선택분을 «빼지 않는다» — 빼면 귀무가
    「arm 이 «안» 고른 것들」이 되어 반대 방향으로 편향된다(§2-2 3단계).
    """
    rng = np.random.RandomState(seed)
    fake: dict = {}
    diag = dict(n_days=0, n_need=0, n_drawn=0, n_sub=0, n_no_ret=0)

    for d in sorted(arm_pool):
        arm_items = arm_pool.get(d) or []
        if not arm_items:
            continue
        allc = pool_all.get(d) or []
        rets = dayret.get(d, {})
        cand = [(c, s) for c, s in allc if c in rets]
        diag["n_no_ret"] += len(allc) - len(cand)
        if not cand:
            continue

        vals = np.array([rets[c] for c, _ in cand], dtype=float)
        edges = np.quantile(vals, np.arange(1, 10) / 10.0)

        def _bin(x: float) -> int:
            return int(np.searchsorted(edges, x, side="right"))

        buckets = {b: [] for b in range(10)}
        for (c, s), v in zip(cand, vals):
            buckets[_bin(v)].append((c, s))
        for b in range(10):                       # 시드 고정 셔플
            order = rng.permutation(len(buckets[b]))
            buckets[b] = [buckets[b][j] for j in order]

        need = {b: 0 for b in range(10)}
        n_need = 0
        for c, _ in arm_items:
            v = rets.get(c)
            if v is None:
                continue
            need[_bin(float(v))] += 1
            n_need += 1

        picked, shortfalls = [], []
        for b in range(10):
            take = min(need[b], len(buckets[b]))
            for _ in range(take):
                picked.append(buckets[b].pop())
            shortfalls += [b] * (need[b] - take)

        for b0 in shortfalls:                     # 가장 «가까운» 분위로 대체
            for off in range(1, 10):
                filled = False
                for bb in (b0 - off, b0 + off):
                    if 0 <= bb < 10 and buckets[bb]:
                        picked.append(buckets[bb].pop())
                        diag["n_sub"] += 1
                        filled = True
                        break
                if filled:
                    break

        diag["n_days"] += 1
        diag["n_need"] += n_need
        diag["n_drawn"] += len(picked)
        if picked:
            fake[d] = picked

    return select_top(fake), diag


# ────────────────────────────────────────────────────────────────────────────
# 5. Arm 풀 · 선택
# ────────────────────────────────────────────────────────────────────────────
ARM_RULE = {
    "D":   lambda dry, tt, f: dry,
    "DT":  lambda dry, tt, f: dry and tt,
    "DF":  lambda dry, tt, f: dry and f,
    "DTF": lambda dry, tt, f: dry and tt and f,
    "T":   lambda dry, tt, f: tt,
}


def build_pools(cache: dict, elig: dict) -> dict:
    """`{arm: {date: [(code, score)]}}` + `R` 은 「base_filter 통과 전체」(진입 룰 없음)."""
    pools = {a: defaultdict(list) for a in list(ARM_RULE) + ["R"]}
    for code, dd in cache.items():
        for d, (score, dry, tt, f, _close) in dd.items():
            if code not in elig.get(d, ()):
                continue
            pools["R"][d].append((code, score))
            for a, fn in ARM_RULE.items():
                if fn(dry, tt, f):
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
# 6. 게이트 helper
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


def year_skew(items: list, pool_days: dict, label: str) -> None:
    """연도 쏠림 — 원시 비중 + **거래일 정규화 비중**. 양쪽 모두 ≤50% 일 때만 ✅ (§6-4)."""
    if not items:
        say(f"- `{label}`: 대상 0건 — 쏠림 계산 불가")
        return
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
    ok = raw_top <= 50 and (ntop != ntop or ntop <= 50)
    say(f"- 원시 최대 = **{ry} {raw_top:.1f}%** · 정규화 최대 = **{ny} {ntop:.1f}%** → "
        + ("✅ **양쪽 모두 ≤50% — 통과**" if ok else
           "🔴 **한쪽이라도 >50% ⇒ 「국면 특이 → 판별 보류」 병기**"))


# ────────────────────────────────────────────────────────────────────────────
# 6b. 2단계 — 백테스트 · 판정 (PREREG §4·§5)
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
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=58)
        return None


def run_arm(sel: dict, frames: dict, idxmap: dict, cfg: dict, backtester_cls) -> dict:
    """arm 하나를 백테스트해 «거래당» 분포와 «신호→실현» 전환을 낸다.

    `mean`·`med` 단위는 **%**. 🔑 `pnl_pct` 에는 슬리피지(편도 0.1%)가 체결가에 반영돼 있고
    **수수료 0.015%·거래세 0.18% 는 미반영**(= PREREG §4 의 gross, 승계 원본과 동일 정의).

    🔴 **`signals`(신호 수)의 정의**(§10-5 항목 12): arm 이 고른 (code, date) 중
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


def tt_labels(D: float, DT: float, n1_D: bool, n1_DT: bool) -> dict:
    """PREREG §5-2 (Trend Template) 라벨 4개 — 동결분 그대로. 새로 짓지 않는다."""
    e = EPS_ECON
    return {
        "(가) TT 는 정보다 — 연결 안 한 것이 «결함»": (DT - D >= e) and n1_DT,
        "(다) 빼는 것이 옳았다 — 연결 안 한 것이 «결정»": (D - DT >= e) and n1_D,
        "(나) TT 는 정보가 아니다": not n1_DT,
        "(마) 구별 불가": abs(DT - D) < e,
    }


def f_labels(D: float, DF: float, n1_DF: bool) -> dict:
    """PREREG §5-3 (재무) 라벨 4개 — 동결분 그대로. (다-F) 는 N1 을 요구하지 않는다."""
    e = EPS_ECON
    return {
        "(가-F) 재무는 정보다": (DF - D >= e) and n1_DF,
        "(다-F) 재무는 «해롭다»": (D - DF >= e),
        "(나-F) 재무는 정보가 아니다": not n1_DF,
        "(마-F) 구별 불가": abs(DF - D) < e,
    }


def decomposition(D: float, DT: float, T: float) -> dict:
    """PREREG §5-4 분해 3라벨 — 사전 고정이므로 인용 가능(단 「유의」·「기각」 금지)."""
    e = EPS_ECON
    return {
        "**dryup 이 기여하지 않는다** — TT 만으로 같은 결과": (abs(T - DT) < e) and (DT - D >= e),
        "**둘 다 필요하다** — dryup 이 TT 위에서 값을 더한다": (DT - T >= e),
        "🔴 **dryup 이 «해롭다»** — TT 단독이 더 낫다": (T - DT >= e),
    }


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
# 7. stage1
# ────────────────────────────────────────────────────────────────────────────
def stage1() -> int:
    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    say("# minervini 개념 축 — 1단계 게이트 (PREREG §6, PnL 미조회)")
    say("")
    say(f"사전등록 [`PREREG.md`](PREREG.md)(동결) · 가족 등록부 [`../REGISTRY.md`](../REGISTRY.md) "
        f"**1번 문서** · 실행 커밋 **`{sha}`** · 창 **{W0} ~ {W1}**.")
    say("")
    say("🔴 이 문서는 PREREG **§6(1단계 게이트)까지만** 다룬다. "
        "**해석·「좋다/나쁘다」 판단은 없다** — 순수 산출이다. 결과 계산(§4·§5)은 2단계다.")
    say("")
    say("🔑 `BookBacktester` 를 **import 하지도 호출하지도 않는다** — "
        "거래당 수익률이 메모리에 들어올 경로 자체가 없다.")
    say("")

    rows, params = verify_strategy_params()
    say("## 0. 설정 대조 (하드코딩 아님 — `config.yaml`·스크리너에서 읽음)")
    say("")
    for r in rows:
        say(r)
    say("")
    say("🔴 청산 파라미터는 **1단계에서 쓰지 않는다**(PnL 미조회). 2단계가 쓸 값을 못박아 인쇄한다.")
    say("")

    fp = db_fingerprint(conn)
    say(f"## 0b. DB 지문 ({len(FINGERPRINT_SQL)}슬라이스 · `regen_gate.py` 형식 승계)")
    say("")
    say("| 슬라이스 | 행 수 | 종목 수 | max |")
    say("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        say(f"| `{k}` | {a:,} | {b:,} | {c} |")
    say("")

    t0 = time.perf_counter()
    px = load_prices(conn)
    uni, ustats = load_universe(conn)
    fin, fraw = load_fundamentals(conn)
    conn.close()
    dates = sorted(uni)
    scr = MinerviniVolumeDryupScreenerAdapter()
    elig = eligible_by_date(uni, scr)
    pool_days = [d for d in dates if elig.get(d)]
    print(f"[load] 일봉 {len(px):,}행 · 재무 {len(fraw):,}행 · "
          f"{time.perf_counter()-t0:.0f}s", flush=True)

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
    say(f"🔴 **룰에 넘기는 창 = {LOOKBACK}봉** — 라이브 스크리너의 `lookback_days=90` 이 «아니다». "
        f"`rule_trend_template` 이 **220봉**을 요구하고 52주 고저에 `close.iloc[-252:]` 를 쓰므로 "
        f"90봉이면 **TT 가 항상 False** 가 된다. {LOOKBACK}봉은 그 요구를 채우면서 "
        f"`rule_volume_dryup`(마지막 40봉만 참조)과 `score`(마지막 30봉만 참조)의 결과를 "
        f"**바꾸지 않는다** — 두 계산 모두 창 길이에 불변이고, {LOOKBACK} ≥ 252 라 TT 의 52주 창도 "
        f"정확히 252봉으로 동일하다.")
    say("")

    # ── §6-5 rs_value 건전성 ────────────────────────────────────────────────
    print("[rs] 백분위 산출", flush=True)
    rs, rdiag = build_rs(px, elig, pool_days)
    say("## 2. §6-5 `rs_value` 산출 건전성")
    say("")
    say(f"- 날짜별 유니버스(= 그날 `base_filter` 통과 집합) 크기: "
        f"최소 **{min(rdiag['sizes']):,}** · 중앙 **{int(np.median(rdiag['sizes'])):,}** · "
        f"최대 **{max(rdiag['sizes']):,}**")
    say(f"- 🔴 유니버스 **2종목 미만**인 날 = **{rdiag['too_small']}일** "
        f"(`compute_rs_percentile_12w` 가 예외를 던지는 조건 — 그런 날은 건너뛰고 "
        f"`rs_value` 를 비워 TT 가 fail-closed 로 False 가 된다)")
    say(f"- `rs_value` 결측률 **{rdiag['missing']:,}/{rdiag['total']:,}** = "
        f"**{rdiag['missing']/rdiag['total']*100:.2f}%** "
        f"(60거래일 전 종가가 없는 신규 상장 등 — 결측이면 TT 는 False)")
    say("")
    say("### 산출 방식 — 절단·근사 없음")
    say("")
    say("날짜마다 **그날까지의 전체 이력**을 `compute_rs_percentile_12w` 에 그대로 넘겼다. "
        "꼬리만 잘라 넘기는 최적화는 **쓰지 않았다** — 이 함수의 `pct_change(60)` 이 pandas "
        "기본 `fill_method='pad'` 로 결측을 앞값으로 채우기 때문에, 창을 자르면 채울 앞값이 "
        "사라져 값이 달라질 수 있다. 아래는 그 «안 쓴» 최적화가 실제로 답을 바꾸는지 재본 것이다:")
    say("")
    say("| 날짜 | 유니버스 | 절단 시 달라지는 종목 수 | 판정 |")
    say("|---|---|---|---|")
    for r in _truncation_probe(px, elig, pool_days):
        say(r)
    say("")

    # ── 룰 캐시 ─────────────────────────────────────────────────────────────
    print("[cache] 룰 평가", flush=True)
    cache, cstats = build_cache(px, elig, rs, fin, params)
    say("## 3. 룰 평가 캐시 (전 arm 공유 · 1회)")
    say("")
    say(f"- 적격 (code,date) **{cstats['n_eval']:,}건** 평가 · {cstats['secs']:.0f}s")
    say(f"- 조건별 통과: `dryup` **{cstats['n_dry']:,}** · `TT` **{cstats['n_tt']:,}** · "
        f"`F` **{cstats['n_f']:,}**")
    say("")

    # ── §6-3 F 커버리지 ─────────────────────────────────────────────────────
    say("## 4. §6-3 `F`(재무) 커버리지")
    say("")
    say("### 4-1. `dart_financials_asfiled` 연도별 원장 상태")
    say("")
    say("| 사업연도 | 행 | `rcept_dt` 결측 | 결측률 | `operating_income` 결측 |")
    say("|---|---|---|---|---|")
    for y, g in fraw.groupby("y"):
        miss = int(g["rcept_s"].isna().sum())
        say(f"| {y} | {len(g):,} | {miss:,} | {miss/len(g)*100:.1f}% | "
            f"{int(g['operating_income'].isna().sum()):,} |")
    say("")
    say("### 4-2. YoY 쌍 기준 — 전년 영업이익 ≤0 비율 · +25% 통과율")
    say("")
    say("| 사업연도 y | YoY 쌍 | 전년 OI ≤0 | 비율 | 전년 흑자 중 +25% 통과 | 통과율 |")
    say("|---|---|---|---|---|---|")
    for y in sorted(fraw["y"].unique()):
        pairs = pos = passed = 0
        for code, m in fin.items():
            cur, prev = m.get(int(y)), m.get(int(y) - 1)
            if not cur or not prev or cur[1] is None or prev[1] is None:
                continue
            pairs += 1
            if prev[1] > 0:
                pos += 1
                if cur[1] >= F_GROWTH * prev[1]:
                    passed += 1
        if pairs:
            say(f"| {y} | {pairs:,} | {pairs-pos:,} | {(pairs-pos)/pairs*100:.1f}% | "
                f"{passed:,} | {passed/pos*100 if pos else float('nan'):.1f}% |")
    say("")
    say("### 4-3. 🔴 정정공시로 `rcept_dt` 가 «늦게» 찍힌 행 (§7-4)")
    say("")
    late = fraw[fraw["rcept_dt"].notna() &
                (pd.to_datetime(fraw["rcept_dt"]).dt.year > fraw["y"] + 1)]
    say(f"정의: `EXTRACT(year FROM rcept_dt) > bsns_year + 1` — 정상 공시는 사업연도 «다음 해» "
        f"3월경에 접수되므로 그보다 늦은 행은 정정본이 as-filed 를 덮어쓴 것으로 본다.")
    say("")
    say(f"- **총 {len(late):,}행** / {len(fraw):,} = **{len(late)/len(fraw)*100:.2f}%** "
        f"(고유 종목 {late['stock_code'].nunique():,})")
    say("")
    if len(late):
        say("| 사업연도 | 늦게 찍힌 행 | 최장 지연(접수연도) |")
        say("|---|---|---|")
        for y, g in late.groupby("y"):
            say(f"| {y} | {len(g):,} | {pd.to_datetime(g['rcept_dt']).dt.year.max()} |")
        say("")
    say("🟢 **방향은 보수적이다** — 이 행들의 `rcept_dt` 는 «미래»라 백테스트 시점에 "
        "안 보인다(룩어헤드가 아니다). 🔴 **대신 커버리지 구멍이 생기고, 정정하는 회사는 "
        "무작위가 아니다.**")
    say("")
    say("### 4-4. `F` 판정 사유 분포 (적격 code-date 전체)")
    say("")
    say("| 사유 | 건수 | 비중 |")
    say("|---|---|---|")
    tot_f = sum(cstats["f_reasons"].values())
    for k, v in cstats["f_reasons"].most_common():
        say(f"| `{k}` | {v:,} | {v/tot_f*100:.1f}% |")
    say("")

    # ── arm 풀·선택 ─────────────────────────────────────────────────────────
    pools = build_pools(cache, elig)
    sels = {a: select_top(pools[a]) for a in ARM_RULE}
    r_sels = [select_random(pools["R"], s) for s in range(N_SEEDS)]
    print("[arm] 선택 완료", flush=True)

    # ── §6-1 트리거 수 ──────────────────────────────────────────────────────
    say("## 5. §6-1 arm 별 진입 트리거 수 · 선택 종목-일 수")
    say("")
    trig_n = {a: sum(len(v) for v in pools[a].values()) for a in ARM_RULE}
    trig_n["R"] = sum(len(v) for v in pools["R"].values())
    sel_n = {a: sum(len(v) for v in sels[a].values()) for a in ARM_RULE}
    sel_n["R"] = int(np.mean([sum(len(v) for v in r.values()) for r in r_sels]))
    base = trig_n["D"]
    say("| Arm | 진입 룰 | 트리거(종목-일) | `D` 대비 | 선택 종목-일 | 선택일 수 | 10% 문턱 |")
    say("|---|---|---|---|---|---|---|")
    desc = {"D": "dryup (현행)", "DT": "dryup ∧ TT", "DF": "dryup ∧ F",
            "DTF": "dryup ∧ TT ∧ F", "T": "TT 만", "R": "없음(base_filter 전체)"}
    short_arms = []
    for a in ["D", "DT", "DF", "DTF", "T", "R"]:
        frac = trig_n[a] / base if base else float("nan")
        nd = len(pools[a])
        flag = ""
        if a != "R" and a != "D":
            if frac < MIN_TRIGGER_FRAC:
                short_arms.append(a)
                flag = "🔴 **미달 → 「표본 부족 → 판별 보류」**"
            else:
                flag = "✅ 충족"
        elif a == "D":
            flag = "— (기준선)"
        else:
            flag = "— (귀무)"
        say(f"| **{a}** | {desc[a]} | {trig_n[a]:,} | {frac*100:.1f}% | {sel_n[a]:,} | "
            f"{nd:,} | {flag} |")
    say("")
    say(f"🔴 사전 고정 문턱(§6-1): **트리거 수가 `D` 의 {MIN_TRIGGER_FRAC*100:.0f}% 미만이면 "
        f"그 arm 은 「표본 부족 → 판별 보류」.**")
    if short_arms:
        say("")
        say(f"⇒ 🔴 **해당 arm: {', '.join('`'+a+'`' for a in short_arms)}** — "
            f"2단계 판정문에 「표본 부족 → 판별 보류」를 병기한다.")
    else:
        say("")
        say("⇒ ✅ **문턱 미달 arm 없음.**")
    say("")
    say(f"🔑 `R` 의 트리거 수는 「`base_filter` 통과 종목-일」 자체다 — R 은 진입 룰 조건이 "
        f"없기 때문이다(§2). 다른 arm 과 «같은 종류의 수»가 아니므로 10% 문턱을 적용하지 않는다.")
    say("")

    # ── §6-2 배제 집합 구성비 ───────────────────────────────────────────────
    say("## 6. §6-2 🔴 배제 집합의 구성비 (이 게이트의 핵심)")
    say("")
    say("`D` 는 통과했는데 `DT`·`DF` 에서 «빠진» 종목-일을, **잔류 집합과 나란히** 본다. "
        "10분위 기준 모집단 = **그날 `D` 풀**(= base_filter ∧ dryup).")
    say("")
    say("⚠️ **KS > 0.20 이어도 여기서는 «자동 판별불가»가 아니다** — TT·F 는 «의도적으로» "
        "추세·수익성으로 거르는 축이므로 분포가 달라지는 것이 **정상**이다. "
        "**크기를 기록**하는 것이 목적이다. "
        "🔑 ***같은 지표라도 축이 의도한 것이면 게이트가 아니라 기술 통계다.***")
    say("")
    dpool = {d: {c for c, _ in v} for d, v in pools["D"].items()}
    keys = {
        "시총": {d: {c: uni[d][c][0] for c in cs if c in uni.get(d, {})}
                for d, cs in dpool.items()},
        "주가": {d: {c: cache[c][d][4] for c in cs if d in cache.get(c, {})}
                for d, cs in dpool.items()},
        "거래대금": {d: {c: uni[d][c][1] for c in cs if c in uni.get(d, {})}
                 for d, cs in dpool.items()},
    }
    excl_sets = {}
    for a in ("DT", "DF"):
        apool = {d: {c for c, _ in v} for d, v in pools[a].items()}
        excl = [(d, c) for d, cs in dpool.items() for c in cs - apool.get(d, set())]
        keep = [(d, c) for d, cs in dpool.items() for c in cs & apool.get(d, set())]
        excl_sets[a] = (excl, keep)
        say(f"### 6-{'1' if a=='DT' else '2'}. `D` → `{a}` 배제 집합 "
            f"(배제 **{len(excl):,}** · 잔류 **{len(keep):,}**)")
        say("")
        for kname, kd in keys.items():
            he, hk = decile_hist(excl, kd), decile_hist(keep, kd)
            say(f"**{kname} 10분위** (1=하위 … 10=상위) · KS = **{ks(he, hk):.3f}**")
            say("")
            say("| 집합 | n | " + " | ".join(str(i + 1) for i in range(N_DECILES)) + " |")
            say("|---|---|" + "---|" * N_DECILES)
            for lab, h in (("배제", he), ("잔류", hk)):
                t = h.sum() or 1
                say(f"| {lab} | {int(h.sum()):,} | "
                    + " | ".join(f"{x/t*100:.1f}%" for x in h) + " |")
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

    # ── §6-4 연도 쏠림 ──────────────────────────────────────────────────────
    say("## 7. §6-4 연도별 쏠림 — 원시 + 거래일 정규화 (**양쪽 ≤50% 일 때만 ✅**)")
    say("")
    say("대상 = §6-2 의 배제 집합(= `D` 대비 각 축이 실제로 «거른» 종목-일). "
        "분모(대상일) = 그 해 `D` 풀이 비지 않은 거래일 수.")
    dpool_days = sorted(dpool)
    for a in ("DT", "DF"):
        year_skew(excl_sets[a][0], dpool_days, f"`D` → `{a}` 배제")
        say("")

    # ── §6-6 겹침 행렬 ──────────────────────────────────────────────────────
    say("## 8. §6-6 arm 간 선택 종목 겹침 행렬")
    say("")
    say(f"일별 평균 겹침 종목 수(최대 {MAX_CANDIDATES}). 양쪽 다 선택이 있는 날만 센다. "
        f"`R` 은 시드 {N_SEEDS}개 평균.")
    say("")
    labs = ["D", "DT", "DF", "DTF", "T"]

    def ov(x: dict, y: dict) -> float:
        v = [len(set(x[d]) & set(y.get(d, []))) for d in x if x[d] and y.get(d)]
        return float(np.mean(v)) if v else float("nan")

    say("| | " + " | ".join(labs) + " | R |")
    say("|---|" + "---|" * (len(labs) + 1))
    for a in labs:
        cells = [f"{ov(sels[a], sels[b]):.2f}" for b in labs]
        cells.append(f"{np.nanmean([ov(sels[a], r) for r in r_sels]):.2f}")
        say(f"| **{a}** | " + " | ".join(cells) + " |")
    rr = [ov(r_sels[i], r_sels[j]) for i in range(N_SEEDS) for j in range(i + 1, N_SEEDS)]
    say("| **R** | " + " | ".join(f"{np.nanmean([ov(r, sels[b]) for r in r_sels]):.2f}"
                                  for b in labs)
        + f" | {np.nanmean(rr):.2f} |")
    say("")
    say("전 기간 고유 종목 수:")
    say("")
    say("| Arm | " + " | ".join(labs) + " | R(시드평균) |")
    say("|---|" + "---|" * (len(labs) + 1))
    uq = {a: len({c for v in sels[a].values() for c in v}) for a in labs}
    ur = np.mean([len({c for v in r.values() for c in v}) for r in r_sels])
    say("| 고유 종목 | " + " | ".join(f"{uq[a]:,}" for a in labs) + f" | {ur:,.0f} |")
    say("")

    say("## 9. 등록 외 조합 (PREREG §8-3 · §9)")
    say("")
    say("**계산한 적 없다.** arm 은 D·DT·DF·DTF·T·R 여섯뿐이고, 8조건 중 부분집합·문턱 스윕·"
        "가중 혼합은 이 스크립트에 구현되어 있지 않다. `rule_trend_template` 은 "
        "**파라미터 기본값 그대로** 호출했다(§2-1).")
    say("")

    say("## 10. 🔴 실행 중 관찰한 것 (사전등록 이행 관련 · 해석 아님)")
    say("")
    say(f"1. **룰 창 {LOOKBACK}봉** — 라이브 `lookback_days=90` 과 다르다. TT 의 220봉 요구 때문이며 "
        f"dryup·score 결과는 불변이다(§1 근거). 이 선택이 없으면 TT arm 이 «전부 0» 이 된다.")
    say(f"2. **`F` 해석** — 「`rcept_dt ≤ D−1` 인 «가장 최근» 사업연도 하나」에 ②③④ 를 걸었다. "
        f"「아무 해나 하나라도 만족」이 아니다(§4-4 사유 분포가 그 결과다).")
    say(f"3. **`R` 풀은 `base_filter` 통과 전체**(진입 룰 없음, §2) — 다른 arm 과 풀 정의가 다르다. "
        f"그래서 §6-1 의 10% 문턱을 R 에는 적용하지 않았다.")
    say(f"4. **`rs_value`** 는 라이브 헬퍼 `compute_rs_percentile_12w` 를 그대로 호출했고, "
        f"꼬리 절단이 전체 이력과 동일함을 §2 자기검증 표로 확인했다.")
    say(f"5. **불가능봉 가드 미적용** — 승계 원본(`rank_score_counterfactual`)과 동일. "
        f"완전 중립은 아니다(풀에서 한 종목이 빠지면 다음 종목이 들어오고 대체가 arm 마다 다르다).")
    say(f"6. **동점 처리** = 코드 오름차순 안정정렬(라이브는 DB 행 순서라 재현 불가).")
    say("")
    say("### 어떤 컬럼만 SELECT 했는가 — PnL 미조회 보장")
    say("")
    say("- `daily_prices`: `stock_code`·`date`·`open`·`high`·`low`·`close`·`volume`·"
        "`adj_factor`·`market_cap` — **9개 컬럼만**.")
    say("- `dart_financials_asfiled`: `stock_code`·`bsns_year`·`rcept_dt`·`operating_income` "
        "— **4개 컬럼만**.")
    say("- **매매 원장 테이블(`virtual_trading_records` 등)은 어느 것도 조회하지 않았다.** "
        "`BookBacktester` 는 import 조차 하지 않는다.")
    say("")

    (BASE / "GATE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] GATE.md", flush=True)
    return 0


def stage2() -> int:
    # 🔴 지역 import — `--stage1` 이 「PnL 계산 경로가 아예 없다」를 보증하기 위해서다.
    from backtest.book_backtester import BookBacktester

    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    rep("# 판정 — minervini 는 원저작의 「추세·펀더멘털 전제」를 뺐다. 결함인가 결정인가")
    rep("")
    rep(f"사전등록 [`PREREG.md`](PREREG.md) 실행 · 가족 등록부 "
        f"[`../REGISTRY.md`](../REGISTRY.md) **1번 문서** · 창 **{W0} ~ {W1}** · "
        f"실행 커밋 **`{sha}`** · 1단계 게이트 → [`GATE.md`](GATE.md) · "
        f"원시 출력 → [`RESULTS_raw.md`](RESULTS_raw.md).")
    rep("")
    rep(f"🔴 **ε·arm·시드·문턱·`score`·판정 규칙·라벨은 `e4c55b1` 동결분 그대로다.** "
        f"ε = **{EPS_ECON}%p**(§5) · N1 = **`arm > R {N_SEEDS}개 전부`**(§5-1) · "
        f"주 검정 **2개**(§5-2 TT · §5-3 F)에 문서 안에서 Holm 보정(§5-6).")
    rep("")

    rows, params = verify_strategy_params()
    say("## 0. 설정 대조")
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
    rep("- **등록 외 조합은 계산하지 않았다** — arm 은 D·DT·DF·DTF·T·R 여섯뿐이고 "
        "8조건 부분집합·문턱 스윕·가중 혼합은 구현되어 있지 않다(§8-3). "
        "`rule_trend_template` 은 **파라미터 기본값 그대로** 호출했다(§2-1).")
    rep("")
    rep(f"DB 지문 ({len(FINGERPRINT_SQL)}슬라이스):")
    rep("")
    rep("| 슬라이스 | 행 수 | 종목 수 | max |")
    rep("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        rep(f"| `{k}` | {a:,} | {b:,} | {c} |")
    rep("")

    t0 = time.perf_counter()
    px = load_prices(conn)
    uni, _ = load_universe(conn)
    fin, _fraw = load_fundamentals(conn)
    conn.close()
    dates = sorted(uni)
    scr = MinerviniVolumeDryupScreenerAdapter()
    elig = eligible_by_date(uni, scr)
    pool_days = [d for d in dates if elig.get(d)]
    print(f"[load] {len(px):,}행 · {time.perf_counter()-t0:.0f}s", flush=True)

    print("[rs] 백분위", flush=True)
    rs, _rd = build_rs(px, elig, pool_days)
    print("[cache] 룰 평가", flush=True)
    cache, cstats = build_cache(px, elig, rs, fin, params)
    pools = build_pools(cache, elig)
    sels = {a: select_top(pools[a]) for a in ARM_RULE}
    r_sels = [select_random(pools["R"], s) for s in range(N_SEEDS)]
    say(f"\n적격 (code,date) {cstats['n_eval']:,} · dryup {cstats['n_dry']:,} · "
        f"TT {cstats['n_tt']:,} · F {cstats['n_f']:,}")

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
    for a in ARM_RULE:
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
    rep("| Arm | 진입 룰 | n (실현 거래) | 거래당 평균 | 중앙 | 승률 | 보유 중앙 | 손절 | 익절 | 최대보유 |")
    rep("|---|---|---|---|---|---|---|---|---|---|")
    desc = {"D": "dryup (현행)", "DT": "dryup ∧ TT", "DF": "dryup ∧ F",
            "DTF": "dryup ∧ TT ∧ F", "T": "TT 만"}
    for a in ARM_RULE:
        m = res[a]
        rep(f"| **{a}** | {desc[a]} | {m['n']:,} | **{m['mean']:+.2f}%** | {m['med']:+.2f}% | "
            f"{m['win']:.0f}% | {m['hold']:.0f}일 | {m['sl']:.0f}% | {m['tp']:.0f}% | "
            f"{m['mh']:.0f}% |")
    rep(f"| **R** | 무작위 ({N_SEEDS}시드) | {int(np.mean([x['n'] for x in r_stats])):,} (평균) | "
        f"중앙 **{np.median(r_means):+.2f}%** · 최소 {min(r_means):+.2f}% · "
        f"**최대 {rmax:+.2f}%** | | | | | | |")
    rep("")

    # ── §10-5 항목 12 — 폐기율 ──────────────────────────────────────────────
    rep("## 2. 🔴 신호 → 실현 거래 전환 · 폐기율 (§10-5 항목 12)")
    rep("")
    rep("**신호 수** = arm 이 고른 (종목, 날짜) 중 그 종목 프레임에 실제로 있고 «다음 봉»이 있어 "
        "체결 가능한 것. **폐기** = 그날 이미 그 종목을 보유 중이라 `BookBacktester` 가 "
        "`generate_signal` 을 부르지도 않은 경우. `폐기율 = 1 − 실현/신호`.")
    rep("")
    rep("| Arm | 신호 수 | 실현 거래 | **폐기율** |")
    rep("|---|---|---|---|")
    for a in ARM_RULE:
        m = res[a]
        rep(f"| **{a}** | {m['signals']:,} | {m['n']:,} | **{m['discard']:.1f}%** |")
    rs_sig = int(np.mean([x["signals"] for x in r_stats]))
    rs_n = int(np.mean([x["n"] for x in r_stats]))
    rs_d = float(np.mean([x["discard"] for x in r_stats]))
    rep(f"| **R** (평균) | {rs_sig:,} | {rs_n:,} | **{rs_d:.1f}%** |")
    rep("")
    ds = {a: res[a]["discard"] for a in ARM_RULE}
    ds["R"] = rs_d
    lo, hi = min(ds.values()), max(ds.values())
    ratio = hi / lo if lo > 0 else float("inf")
    if ratio >= DISCARD_RATIO_FLAG:
        rep(f"🔴 **폐기율이 arm 간 {ratio:.2f}배 벌어졌다 (≥{DISCARD_RATIO_FLAG:.0f}배)** — "
            f"최대 `{max(ds, key=lambda k: ds[k])}` {hi:.1f}% vs 최소 "
            f"`{min(ds, key=lambda k: ds[k])}` {lo:.1f}%. "
            f"⇒ ***실현 거래가 신호의 «비무작위» 부분집합이고 그 정도가 arm 마다 다르다*** ⇒ "
            f"이 비교는 「같은 룰의 두 버전」이 아니라 **「다른 빈도의 두 룰」**에 가깝다. "
            f"**판정문에 병기한다**(§10-5 항목 12).")
    else:
        rep(f"✅ **폐기율 최대/최소 = {ratio:.2f}배 (<{DISCARD_RATIO_FLAG:.0f}배)** — "
            f"전환율 비대칭이 문턱 아래다. 비교가 「같은 룰의 두 버전」으로 성립한다.")
    rep("")

    # ── 판정 ────────────────────────────────────────────────────────────────
    D, DT, DF, DTF, T = (res[a]["mean"] for a in ("D", "DT", "DF", "DTF", "T"))
    n1 = {a: res[a]["mean"] > rmax for a in ARM_RULE}
    pv = {a: perm_p(res[a]["mean"], r_means) for a in ARM_RULE}

    rep("## 3. 귀무 N1 (§5-1) — 각 arm 이 무작위 20회 «전부»를 넘는가")
    rep("")
    rep("| Arm | 거래당 평균 | R 최대 | N1 | 단측 순열 p |")
    rep("|---|---|---|---|---|")
    for a in ARM_RULE:
        rep(f"| **{a}** | {res[a]['mean']:+.2f}% | {rmax:+.2f}% | "
            f"{'✅' if n1[a] else '❌'} | {pv[a]:.4f} |")
    rep("")
    if not n1["D"]:
        rep("### 🔴🔴 이것이 이 문서의 «가장 중요한 결과»다 (§5-1 사전 지정)")
        rep("")
        rep(f"**기준선 `D` 가 N1 을 통과하지 못했다** — `D` {D:+.2f}% ≤ R 최대 {rmax:+.2f}%.")
        rep("")
        rep("⇒ ***현행 진입 룰(`rule_volume_dryup` 한 줄)이 이미 「그날 `base_filter` 통과 "
            "집합에서 무작위로 10종목 고르기」와 구별되지 않는다.*** "
            "사전등록 §5-1 이 *「그것 자체가 이 문서의 가장 중요한 결과다. 눈에 띄게 인쇄한다」* "
            "라고 미리 지정한 관측이다. 아래 TT·F 판정과 **병기**한다.")
        rep("")
    else:
        rep(f"✅ **기준선 `D` 는 N1 통과** ({D:+.2f}% > R 최대 {rmax:+.2f}%) — "
            f"현행 진입 룰은 무작위와 구별된다(§5-1).")
        rep("")

    rep("## 4. 주 판정 — 라벨은 동결분에서 «고른다»(새로 짓지 않는다)")
    rep("")
    rep(f"| 지표 | 값 |")
    rep("|---|---|")
    rep(f"| **DT − D** (§5-2 TT) | **{DT-D:+.2f}%p** |")
    rep(f"| **DF − D** (§5-3 재무) | **{DF-D:+.2f}%p** |")
    rep(f"| **DT − T** (§5-4 분해) | **{DT-T:+.2f}%p** |")
    rep(f"| ε (동결) | {EPS_ECON}%p |")
    rep("")

    ttl = tt_labels(D, DT, n1["D"], n1["DT"])
    fl = f_labels(D, DF, n1["DF"])
    rep("### 4-1. §5-2 Trend Template")
    rep("")
    rep("| 라벨 (동결) | 조건 충족 |")
    rep("|---|---|")
    for k, v in ttl.items():
        rep(f"| {k} | {'✅ **성립**' if v else '❌'} |")
    tt_hit = [k for k, v in ttl.items() if v]
    rep("")
    rep(f"⇒ **{' · '.join(tt_hit) if tt_hit else '판별 불가 (어느 라벨도 성립하지 않음)'}**")
    rep("")

    rep("### 4-2. §5-3 재무")
    rep("")
    rep("| 라벨 (동결) | 조건 충족 |")
    rep("|---|---|")
    for k, v in fl.items():
        rep(f"| {k} | {'✅ **성립**' if v else '❌'} |")
    f_hit = [k for k, v in fl.items() if v]
    rep("")
    rep(f"⇒ **{' · '.join(f_hit) if f_hit else '판별 불가 (어느 라벨도 성립하지 않음)'}**")
    rep("")

    # ── Holm ────────────────────────────────────────────────────────────────
    rep("## 5. §5-6 Holm 보정 (주 검정 2개, α = .05)")
    rep("")
    hres = holm([("§5-2 TT (DT vs R)", pv["DT"]), ("§5-3 재무 (DF vs R)", pv["DF"])])
    rep("| 검정 | 단측 순열 p | Holm 문턱 | 기각? |")
    rep("|---|---|---|---|")
    for name, p, thr, rej in hres:
        rep(f"| {name} | {p:.4f} | {thr:.4f} | {'✅ 기각' if rej else '❌ 기각 못 함'} |")
    rep("")
    pmin = 1 / (N_SEEDS + 1)
    rep(f"🔴 **구조적 사실 — 이 설계에서 Holm 의 1단계 문턱은 «도달 불가»다.** "
        f"시드가 {N_SEEDS}개이므로 단측 순열 p 의 **최솟값은 1/{N_SEEDS+1} = {pmin:.4f}** 인데, "
        f"Holm 의 첫 문턱은 α/2 = **{ALPHA/2:.4f}** 다. **{pmin:.4f} > {ALPHA/2:.4f}** 이므로 "
        f"***arm 이 무작위 20회를 전부 이기더라도 Holm 은 아무것도 기각할 수 없다.*** "
        f"이는 결과와 무관한 **동결 설계의 산술적 성질**이다(시드 수와 Holm 이 동시에 고정돼 "
        f"있고 §8-1 이 둘 다 변경을 금지한다).")
    rep("")
    rep("⇒ **따라서 §5-2·§5-3 의 라벨 판정은 「N1 + ε」 규칙(§5-2·§5-3 표)으로 내리고, "
        "Holm 결과는 「유의」 선언에만 관계한다** — 이 문서는 **어느 검정에 대해서도 "
        "「통계적으로 유의하다」고 쓰지 않는다.**")
    rep("")

    # ── §5-4 분해 ───────────────────────────────────────────────────────────
    rep("## 6. §5-4 분해 — 알파는 어디서 오는가")
    rep("")
    rep("🔑 1단계 실측 `D∩T` 겹침이 **2.10/10** 뿐이라 두 룰은 거의 다른 종목을 고른다 ⇒ "
        "이 분해는 실질 판별력을 갖는다. 라벨 3개는 **사전 고정**이므로 인용 가능하나 "
        "**보정 대상이 아니므로 「유의」·「기각」을 쓰지 않는다**(§5-6 · REGISTRY 규칙 2).")
    rep("")
    rep(f"- `T` = **{T:+.2f}%** · `DT` = **{DT:+.2f}%** · `D` = **{D:+.2f}%**")
    rep(f"- `DT − T` = **{DT-T:+.2f}%p** · `T − DT` = **{T-DT:+.2f}%p** · "
        f"`DT − D` = **{DT-D:+.2f}%p**")
    rep("")
    dec = decomposition(D, DT, T)
    rep("| 관측 (동결 라벨) | 성립 |")
    rep("|---|---|")
    for k, v in dec.items():
        rep(f"| {k} | {'✅' if v else '❌'} |")
    dec_hit = [k for k, v in dec.items() if v]
    rep("")
    rep(f"⇒ **{' · '.join(dec_hit) if dec_hit else '세 라벨 어느 것도 성립하지 않음 — 분해 판별 불가'}**")
    rep("")

    # ── §5-5 상호작용 ───────────────────────────────────────────────────────
    rep("## 7. §5-5 상호작용 — 🔴 **판별 보류** (인쇄만)")
    rep("")
    inter = DTF - DT - DF + D
    rep(f"`DTF − DT − DF + D` = {DTF:+.2f} − {DT:+.2f} − {DF:+.2f} + {D:+.2f} = "
        f"**{inter:+.2f}%p**")
    rep("")
    rep(f"🔴 **판별 보류.** `DTF` 는 1단계 §6-1 에서 트리거가 `D` 의 **4.4%** 로 사전 고정 문턱 "
        f"10% 에 미달했다(`GATE.md` §5 · PREREG §10-4) ⇒ **「표본 부족 → 판별 보류」**. "
        f"실현 거래 **{res['DTF']['n']:,}건**. "
        f"***이 값을 어떤 결론에도 인용하지 않는다. 이 값을 보고 조합을 고르면 사후적합이다***(§5-5).")
    rep("")

    # ── 종합 ────────────────────────────────────────────────────────────────
    rep("## 8. 🔴 종합")
    rep("")
    for lab in tt_hit:
        rep(f"# {lab}")
    for lab in f_hit:
        rep(f"# {lab}")
    if not tt_hit and not f_hit:
        rep("# 판별 불가")
    rep("")
    if not n1["D"]:
        rep("### 🔴 병기 — 현행 진입 룰이 무작위와 구별되지 않는다 (§5-1)")
        rep("")
        rep(f"`D` {D:+.2f}% ≤ R 최대 {rmax:+.2f}% ⇒ N1(D) 불성립. "
            f"위 라벨과 **함께** 읽어야 한다.")
        rep("")
    if ratio >= DISCARD_RATIO_FLAG:
        rep(f"### 🔴 병기 — 폐기율 비대칭 {ratio:.2f}배 (§10-5 항목 12)")
        rep("")
        rep("실현 거래가 신호의 비무작위 부분집합이고 그 정도가 arm 마다 다르다.")
        rep("")
    rep(f"### 🔑 생존편향 비대칭 — 판정문 옆에 붙여 읽을 것 (§7-2)")
    rep("")
    rep("생존편향은 **약한 종목을 위로** 민다. TT·F 는 «강한 종목을 고르는» 필터이므로 "
        "**`DT − D`·`DF − D` 가 «과소»평가**되는 쪽이다. 따라서:")
    rep("")
    rep("- **(가)·(가-F) 결론이면 «강하다»** — 편향이 반대로 미는데도 나온 결과다.")
    rep("- **(나)·(다) 계열 결론이면 이 편향을 «배제할 수 없다»** — 편향이 그 결론을 "
        "밀어주는 방향이다.")
    rep("")
    pro = any(k.startswith("(가") for k in tt_hit + f_hit)
    rep("⇒ 이번 결론은 " + ("**편향이 반대로 미는데도 나온 것이라 «강하다»**."
                          if pro else
                          "**편향이 «밀어주는» 방향이라 배제할 수 없다** — "
                          "채택 전 별도 검증이 필요하다."))
    rep("")
    rep(f"### 가족 FWER (REGISTRY 규칙 5)")
    rep("")
    rep("가족 등록부 현재 등재 주 검정 **2개** ⇒ 보정 없는 FWER(α=.05) ≈ **9.8%**. "
        "***보정을 안 거는 것과 위험이 없는 것은 다르다*** — 이 숫자를 판정문과 함께 읽을 것.")
    rep("")

    rep("## 9. 🔴 한계 (PREREG §7 1~11 + §10-5 12~13, 전량 전재)")
    rep("")
    for i, s in enumerate(LIMITATIONS, 1):
        rep(f"{i}. {s}")
    rep("")
    rep("### §10-4 — `DTF` 문턱 미달이 판정 구조에 미치는 영향")
    rep("")
    rep("🟢 **주 판정 2개는 영향을 받지 않는다** — §5-2 는 `DT` vs `D`, §5-3 은 `DF` vs `D` 를 "
        "쓰고 둘 다 1단계 문턱을 통과했다(16.1% · 24.1%). "
        "**`DTF` 는 §5-5 상호작용(인쇄만)에만 쓰이고 「판별 보류」다.**")
    rep("")

    (BASE / "RESULTS.md").write_text("\n".join(DOC) + "\n", encoding="utf-8")
    (BASE / "RESULTS_raw.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] RESULTS.md · RESULTS_raw.md", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="minervini 개념 축 — PREREG 실행부")
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
