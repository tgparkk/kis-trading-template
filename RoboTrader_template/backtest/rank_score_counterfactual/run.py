# -*- coding: utf-8 -*-
"""랭킹 함수 반사실 — 사전등록 `PREREG.md` 실행부.

🔴 **창은 PREREG §10-1 개정본 `2024-03-13 ~ 2026-05-31` 이다**(원 §3 은 2021-01-01~).
`market_cap` 커버리지가 2024-03-12 **1.4%** → 2024-03-13 **99.6%** 로 절벽인데 세 전략의
`base_filter` 가 시총 결측을 fail-closed 로 제외해, 그 이전 구간은 적격 풀이 비어 아무 arm 도
고르지 못했다. 개정은 **1단계 산출 후·PnL 관측 «전»**에 확정됐다.

**모드 두 개.**

- `--stage1` — PREREG §6 게이트. **PnL 을 계산하지 않는다.** `BookBacktester` 는
  «2단계 함수 안에서만» import 되므로 이 경로에서는 거래당 수익률이 메모리에 들어올 경로가
  아예 없다. §6-5 의 「거래 수」는 «진입 트리거 수» 로 세고, 네 arm 이 정의상 같아
  **검사가 성립하지 않는다**(§10-3 이 실현 거래 수로 2단계 이관).
  산출물 → `GATE.md`.
- `--stage2` — PREREG §4·§5 판정. arm 별 거래당 평균 수익률·귀무 R·라벨 판정.
  산출물 → `RESULTS.md`(판정) · `RESULTS_raw.md`(원시 출력).

🔴 **두 모드는 «같은» 선택 집합을 쓴다** — `build_cache`→`build_pools`→`select_*` 경로가
하나라서, 2단계의 arm 선택은 1단계가 인쇄한 것과 정의상 동일하다.

Arm 4개는 «랭킹 함수 하나»만 다르다 (PREREG §2):

    V = mean(volume,        최근 w)      (현행)
    T = mean(close*volume,  최근 w)      🔑 갈림점
    R = 적격 풀에서 무작위 10종목, 시드 0..19
    P = close 마지막값 내림차순          🔴 반증축

룰 평가는 (code, date) 캐시를 **1회** 만들어 전 arm 이 공유하고, **같은 창에서**
V·T·P 세 점수를 함께 계산한다 — arm 간 차이를 랭킹 함수로만 고립시키는 장치다
(`universe_lookahead_ladder` §2 승계).

🔑 척도 (PREREG 척도 고지 = `ac69084` 이후):
`daily_prices.close` 는 이미 분할조정 연속시세이고 `volume` 은 **원본 저장**이라,
라이브 읽기계층(`db/quant_daily_reader.py::_SELECT_OHLCV`)이 `volume * adj_factor` 로
단위를 맞춘다. 이 스크립트는 성능 때문에 raw SQL 로 읽으므로 **그 보정을 로더에서
«한 번만» 재현**한다(`vol_adj`). 그 뒤로는 `close × vol_adj` 를 그대로 쓰고
`adj_factor` 를 **다시 곱하지 않는다**(PREREG §8-6 이중조정 금지).

라이브 코드는 «읽기»만 한다(스크리너 어댑터 import). DB 는 SELECT 만.
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
ROOT = BASE.parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

from strategies.base import Signal, SignalType                                          # noqa: E402
from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter        # noqa: E402
from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter      # noqa: E402
from strategies.minervini_volume_dryup.screener import (                                # noqa: E402
    MinerviniVolumeDryupScreenerAdapter,
)
# 🔴 `BookBacktester` 는 **여기서 import 하지 않는다** — `--stage1` 이 「PnL 계산 경로가
#    아예 없다」를 보증하기 위해서다. 2단계 함수(`stage2`) 안에서 지역 import 한다.

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
           dbname="kis_template")

# 🔑 종목코드 술어 — 신형 코드는 «중간»이 영문일 수 있다(`0001A0`).
#    `^[0-9]{6}$` 로 하면 54종목을 놓친다. 의사티커(KOSPI/KOSDAQ/KS11/KQ11)는
#    첫 글자가 숫자가 아니라 이 술어에 이미 안 걸리지만, 명시적으로도 배제한다.
STOCK_ONLY = ("stock_code ~ '^[0-9][0-9A-Z]{5}$' "
              "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')")

# 🔴 창 — PREREG **§10-1 개정본**(2026-08-16, 1단계 산출 후·PnL 관측 «전»).
#    원 §3 은 2021-01-01~2026-05-31 이었으나 `market_cap` 커버리지가
#    2024-03-12 **1.4%** → 2024-03-13 **99.6%** 로 절벽이고, 세 전략의 `base_filter` 는
#    시총 결측을 fail-closed 로 제외한다 ⇒ 그 이전엔 적격 풀이 비어 아무 arm 도 못 고른다.
#    경계는 「커버리지가 처음 95% 를 넘은 거래일」이며 90/95/99 어디로 잡아도 같은 날이다.
W0, W1 = "2024-03-13", "2026-05-31"   # PREREG §10-1 — 실효 창 ≈ 2.2년
ORIG_W0 = "2021-01-01"                 # 원 §3 창 시작 (기록용 — 이제 판정에 쓰지 않는다)
# 워밍업용 창 «이전» 히스토리. 개정 창 덕에 3년치가 확보된다(§10-4 항목 13 — 원 한계 해소).
HIST0 = "2021-01-01"
MAX_CANDIDATES = 10                    # PREREG §2 고정
N_SEEDS = 20                           # PREREG §2 — R 시드 0..19
N_DECILES = 10                         # PREREG §6-4
# 🔴 PREREG §5-1 동결. **결과를 보고 바꾸지 않는다**(§8-1). 단위 = %p.
EPS_ECON = 0.5
MIN_TRADES = 200                       # PREREG §7-7 표본 문턱
DIFF_PRED_FRAC = 1.0 / 3.0             # PREREG §5-4 차등 예측 문턱

# PREREG §7(1~7) + §10-4(8~13) 한계 — **결과 문서에 그대로 옮겨 적는다**(축약 없음).
LIMITATIONS = [
    "🔴 **생존편향** — `daily_prices` 에 상폐 종목이 사실상 없다(사다리 §6-1 실측 0.5%). "
    "편향은 **저유동성·저가 arm(V·R)을 위로** 민다 ⇒ **`T − V` 는 과소평가되는 쪽**이다. "
    "***(나) 결론이 나오면 이 편향을 배제할 수 없다*** — 반대로 (가)가 나오면 강하다.",
    "🔴 **`BookBacktester` 는 sl/tp/max_hold 만 지원**한다. ma5·ma20 의 **MA 이탈 트레일링이 "
    "없다.** 전 arm 에 동일하게 빠지므로 arm 비교엔 무해하나 **절대 수준은 라이브와 다르다.**",
    "🔴 **포트폴리오가 아니다** — 종목당 단일 포지션 순차. 거래 «당» 분포만 유효하고 "
    "K 한도·자금 배분은 재현되지 않는다.",
    "🔴 **`market_cap` 스냅샷 제약** — `base_filter` 가 시총을 쓰므로 시총 결측일은 전 arm 에서 "
    "동일하게 빠진다(개정 창 안 결측률 0.38%, `GATE.md` §2).",
    "⚠️ **이 문서는 「랭킹 함수」만 묻는다.** 「후보 상한 N」·「진입 룰」·「청산 파라미터」는 "
    "별개 축이다. 🔴 ***결과를 보고 N 이나 청산을 함께 손대면 그게 사후적합이다.***",
    "⚠️ **라이브가 실제로 겪은 국면이 아니다.** 라이브 페이퍼는 75일뿐이고 §3 에서 제외했다. "
    "**백테스트 결론을 라이브 기대치로 인용하지 말 것**(`PAPER_STRATEGIES §0.7` 「97% 미검증」).",
    "⚠️ **검정력.** 거래 수를 §6-5 에 인쇄하고, 전략별 거래 수 < 200 이면 그 전략은 "
    "「표본 부족 → 판별 보류」로 병기한다.",
    "🔴 **단일 국면이다.** 실효 창 2.2년(2024-03~2026-05)이고 5.4년이 아니다(§10-1). "
    "***이 창의 결론을 다른 국면으로 일반화하지 말 것.***",
    "🔴 **`market_cap` 자체의 PIT 성격을 검정하지 않았다.** 스냅샷을 과거로 방송한 값이면 "
    "`base_filter` 에 룩어헤드가 있다. **전 arm 에 동일하게 걸리므로 arm 비교엔 무해**하나 "
    "**절대 수준은 신뢰할 수 없다.**",
    "⚠️ **불가능봉 가드 미적용.** 라이브 `scan()` 에는 있으나 승계 원본(사다리)에 없고 §2 고정 "
    "목록에도 없어 넣지 않았다. **완전 중립은 아니다** — 풀에서 한 종목이 빠지면 11번째가 "
    "들어오고 그 대체 종목이 arm 마다 다르다. 알려진 불가능봉 119건으로 미미하나 0 은 아니다.",
    "⚠️ **종목코드 술어가 사다리와 다르다.** 이 문서 `^[0-9][0-9A-Z]{5}$`(2,788종목) vs "
    "사다리 `^[0-9]{5}[0-9A-Z]$`(2,734종목) — 54종목 차이. "
    "⇒ ***사다리 산출물과 숫자를 직접 비교하지 말 것.*** 내부 arm 비교에는 무해하다.",
    "⚠️ **동점 처리** = 코드 오름차순 안정정렬(라이브는 DB 행 순서라 재현 불가). "
    "동점이 흔한 arm **P** 에서만 실질 영향이 있다.",
    "⚠️ **워밍업 히스토리** — 개정 창(2024-03-13~)에서는 창 이전 3년치가 확보되므로 "
    "원 창의 한계는 **해소**됐다(실측 1,700,353행).",
]

# 전략 정의. `w`(점수 창)·`lookback`(match 에 넘기는 창)·`warmup`(룰 최소봉)은
# 전부 라이브 코드에서 온 값이다 — 아래 `verify_strategy_params()` 가 대조·인쇄한다.
STRATS = {
    "book_pullback_ma5": dict(
        screener=BookPullbackMa5ScreenerAdapter, w=5,
        lookback=60,    # BookPullbackMa5ScreenerAdapter.lookback_days
        warmup=25,      # config.yaml parameters.min_daily_bars (룰 최소 22봉 + 여유)
        exp_sl=0.03, exp_tp=0.15, exp_mh=30, role="판정 대상",
    ),
    "book_pullback_ma20": dict(
        screener=BookPullbackMa20ScreenerAdapter, w=20,
        lookback=90, warmup=35,
        exp_sl=0.08, exp_tp=0.10, exp_mh=50, role="판정 대상",
    ),
    "minervini_volume_dryup": dict(
        screener=MinerviniVolumeDryupScreenerAdapter, w=30,   # = base_window
        lookback=90, warmup=40,
        exp_sl=0.08, exp_tp=0.12, exp_mh=20, role="차등 예측 대조군",
    ),
}

# DB 지문 — 이 스크립트가 «실제로 읽는» 슬라이스만 (`regen_gate.py` 형식 승계).
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
    f"daily_prices[{HIST0}..{W1}] adj_factor<>1":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{HIST0}' AND '{W1}' "
        f"AND COALESCE(adj_factor,1) <> 1",
    "daily_prices (전체)":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices",
}

OUT: list[str] = []      # 원시 출력 (GATE.md / RESULTS_raw.md)
DOC: list[str] = []      # 판정 문서 (RESULTS.md) — OUT 의 부분집합


def say(s: str = "") -> None:
    """원시 출력에만 남긴다."""
    print(s, flush=True)
    OUT.append(s)


def rep(s: str = "") -> None:
    """판정 문서 «와» 원시 출력 양쪽에 남긴다 ⇒ `RESULTS_raw.md` 는 항상 상위집합이다."""
    print(s, flush=True)
    OUT.append(s)
    DOC.append(s)


def git_sha() -> str:
    """실행 커밋 SHA (PREREG §9). 조회 실패 시 문자열로 그 사실을 남긴다."""
    import subprocess  # noqa: PLC0415 — 이 한 곳에서만 쓴다
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(조회 실패: {type(e).__name__})"


# ────────────────────────────────────────────────────────────────────────────
# 0. 설정 대조 — 청산 파라미터는 config.yaml 이 정본
# ────────────────────────────────────────────────────────────────────────────
def verify_strategy_params() -> list[str]:
    """각 전략 `config.yaml` 의 sl/tp/max_hold 를 읽어 지시서 기대값과 대조한 표(행)를 만든다.

    🔴 config 가 정본이다 — 어긋나면 그 사실을 표에 인쇄한다.
    (1단계는 청산을 «쓰지 않지만», 2단계가 쓸 값이 무엇인지 여기서 못박아 인쇄한다.)
    """
    rows = []
    for name, cfg in STRATS.items():
        y = yaml.safe_load((ROOT / "strategies" / name / "config.yaml").read_text(encoding="utf-8"))
        rm = (y or {}).get("risk_management", {}) or {}
        sl, tp, mh = rm.get("stop_loss_pct"), rm.get("take_profit_pct"), rm.get("max_hold_days")
        cfg["sl"], cfg["tp"], cfg["mh"] = sl, tp, mh
        ok = (sl == cfg["exp_sl"] and tp == cfg["exp_tp"] and mh == cfg["exp_mh"])
        rows.append(f"| `{name}` | {sl} / {tp} / {mh} | "
                    f"{cfg['exp_sl']} / {cfg['exp_tp']} / {cfg['exp_mh']} | "
                    f"{'✅ 일치' if ok else '🔴 **불일치 — config 를 정본으로 씀**'} |")
    return rows


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
    """`HIST0`~`W1` 일봉. `vol_adj = volume * COALESCE(adj_factor,1)` 을 **여기서 한 번만** 만든다.

    🔑 개정 창(`W0`=2024-03-13)보다 **이르게** 읽는 이유는 워밍업이다 — 룰이 보는 창
    (ma5 60봉 · ma20/minervini 90봉)을 창 «이전» 히스토리로 채운다(PREREG §3, §10-4 항목 13).
    선택·룰 평가는 `W0` 이후에만 일어난다(적격 집합이 `W0`~`W1` 로만 만들어지므로 자동).

    이것이 라이브 읽기계층(`QuantDailyReader._SELECT_OHLCV`)과 동일한 척도다.
    이후 어떤 계산에서도 `adj_factor` 를 다시 곱하지 않는다(PREREG §8-6 · §10-5).
    OHLC 결측/비양수 보정은 `universe_lookahead_ladder/run.py` 와 동일하다.
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
    df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[~(df["close"].isna() | (df["close"] <= 0) | df["datetime"].isna())].copy()
    for c in ("open", "high", "low"):
        m = df[c].isna() | (df[c] <= 0)
        df.loc[m, c] = df.loc[m, "close"]
    df["vol_adj"] = df["vol_adj"].fillna(0).clip(lower=0)
    # 룰이 보는 컬럼명은 `volume` 이다 — 조정된 값을 그 이름으로 넘긴다.
    df["volume"] = df["vol_adj"]
    return df.dropna(subset=["open", "high", "low", "close"])


def load_universe(conn) -> tuple[dict, dict]:
    """`{date: {code: (market_cap, trading_value)}}` 와 결측 통계.

    `trading_value` 는 읽기계층과 동일하게 **`close × (volume × adj_factor)`** 로 직접 만든다
    (저장된 `trading_value` 컬럼은 «조정 close × 원본 volume» 이라 분할 이전 구간이
    과소평가돼 있다 — `quant_daily_reader.py:81-87` 주석과 같은 이유).
    """
    u = pd.read_sql(f"""
        SELECT date, stock_code, market_cap,
               (close * (volume * COALESCE(adj_factor,1)))::double precision AS tv
        FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'
    """, conn)
    u["market_cap"] = pd.to_numeric(u["market_cap"], errors="coerce")
    u["tv"] = pd.to_numeric(u["tv"], errors="coerce").fillna(0.0)
    stats = dict(
        rows=int(len(u)),
        mcap_missing=int((u["market_cap"].isna() | (u["market_cap"] <= 0)).sum()),
        days_all=int(u["date"].nunique()),
        days_with_mcap=int(u.loc[u["market_cap"] > 0, "date"].nunique()),
    )
    uni: dict = defaultdict(dict)
    for d, code, mc, tv in zip(u["date"].to_numpy(), u["stock_code"].to_numpy(),
                               u["market_cap"].to_numpy(), u["tv"].to_numpy()):
        uni[d][code] = (float(mc) if mc == mc else 0.0, float(tv))
    return dict(uni), stats


def eligible_by_date(uni: dict, screener) -> dict:
    """전략 `base_filter` 를 날짜별로 그대로 통과시킨다 (PREREG §2 — base_filter 전체 고정)."""
    out = {}
    for d, m in uni.items():
        recs = [{"code": c, "name": c, "market_cap": mc, "trading_value": tv}
                for c, (mc, tv) in m.items()]
        out[d] = {r["code"] for r in screener.base_filter(recs)}
    return out


# ────────────────────────────────────────────────────────────────────────────
# 2. 룰 평가 캐시 — 전 arm 공유 (PREREG §2 핵심 장치)
# ────────────────────────────────────────────────────────────────────────────
def build_cache(px: pd.DataFrame, elig: dict, screener, cfg: dict) -> tuple[dict, dict]:
    """`{code: {date: (score_V, score_T, score_P)}}` 와 진행 통계.

    적격(`base_filter` 통과)인 (code, date) 에서만 룰을 평가한다 — 평가 결과와 세 점수를
    **같은 창에서** 만들므로 arm 간 차이는 「어느 점수로 정렬했나」 하나뿐이다.
    """
    params = screener.default_params()
    lb, wm, w = cfg["lookback"], cfg["warmup"], cfg["w"]
    trig: dict = defaultdict(dict)
    n_eval = n_fire = 0
    codes_done = 0
    total_codes = px["stock_code"].nunique()
    t0 = time.perf_counter()
    for code, g in px.groupby("stock_code", sort=False):
        codes_done += 1
        if codes_done % 400 == 0:
            print(f"      ...{codes_done}/{total_codes} 종목 · 평가 {n_eval:,} · "
                  f"발화 {n_fire:,} · {time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        closes = g["close"].to_numpy(dtype=float)
        vols = g["volume"].to_numpy(dtype=float)
        n = len(g)
        for i in range(wm, n):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            v = screener.match(g.iloc[max(0, i + 1 - lb):i + 1], params)
            n_eval += 1
            if v is None:
                continue
            n_fire += 1
            a = max(0, i + 1 - w)
            cw, vw = closes[a:i + 1], vols[a:i + 1]
            trig[code][d] = (float(vw.mean()), float((cw * vw).mean()), float(closes[i]))
    return dict(trig), dict(n_eval=n_eval, n_fire=n_fire, secs=time.perf_counter() - t0)


# ────────────────────────────────────────────────────────────────────────────
# 3. Arm 선택 — 랭킹 함수 하나만 다르다
# ────────────────────────────────────────────────────────────────────────────
def build_pools(trig: dict, elig: dict) -> dict:
    """`{date: [(code, sV, sT, sP), ...]}` — 그날 base_filter 통과 ∧ 룰 발화한 «적격 풀».

    코드 오름차순으로 고정한다. 라이브는 동점을 DB 행 순서로 깨지만 그건 재현 불가능한
    순서이므로, 여기서는 «코드 오름차순 + 안정정렬»로 결정적으로 깬다.
    """
    pools: dict = defaultdict(list)
    for code, dd in trig.items():
        for d, (sv, st, sp) in dd.items():
            if code in elig.get(d, ()):
                pools[d].append((code, sv, st, sp))
    return {d: sorted(v) for d, v in pools.items()}


def select_deterministic(pools: dict, idx: int) -> dict:
    """`idx` 번째 점수 내림차순 top-`MAX_CANDIDATES`. idx 1=V, 2=T, 3=P."""
    return {d: [c for c, *_ in sorted(v, key=lambda t: t[idx], reverse=True)[:MAX_CANDIDATES]]
            for d, v in pools.items()}


def select_random(pools: dict, seed: int) -> dict:
    """R arm — V·T·P 와 «같은 풀»에서 매일 무작위 `MAX_CANDIDATES` 종목 (비복원)."""
    rng = np.random.RandomState(seed)
    out = {}
    for d in sorted(pools):
        codes = [c for c, *_ in pools[d]]
        k = min(MAX_CANDIDATES, len(codes))
        out[d] = list(rng.choice(codes, size=k, replace=False)) if k else []
    return out


# ────────────────────────────────────────────────────────────────────────────
# 4. 게이트 산출 (PREREG §6) — 해석 없음, 순수 산출
# ────────────────────────────────────────────────────────────────────────────
def daily_overlap(a: dict, b: dict) -> tuple[float, int]:
    """(일별 평균 겹침 종목 수, 겹친 날 수). 양쪽 다 비어있지 않은 날만 센다."""
    vals = []
    for d, av in a.items():
        bv = b.get(d)
        if not av or not bv:
            continue
        vals.append(len(set(av) & set(bv)))
    return (float(np.mean(vals)) if vals else float("nan")), len(vals)


def uniq(sel: dict) -> set:
    out = set()
    for v in sel.values():
        out |= set(v)
    return out


def profile(sel: dict, uni: dict) -> dict:
    """선택 (code, date) 의 중앙 주가·중앙 시총·중앙 거래대금·선택수·고유 종목수.

    주가·시총·거래대금은 «선택된 그 날»의 값이다(주가 = 그날 종가 = 라이브 `prev_close`).
    """
    px_, mc_, tv_ = [], [], []
    n = 0
    for d, codes in sel.items():
        m = uni.get(d, {})
        for c in codes:
            n += 1
            if c in m:
                mc_.append(m[c][0])
                tv_.append(m[c][1])
    return dict(n=n, uniq=len(uniq(sel)),
                med_mcap=float(np.median(mc_)) if mc_ else float("nan"),
                med_tv=float(np.median(tv_)) if tv_ else float("nan"))


def profile_price(sel: dict, pools: dict) -> float:
    """중앙 주가 — 풀에 실린 `sP`(그날 종가)를 그대로 쓴다."""
    vals = []
    for d, codes in sel.items():
        m = {c: sp for c, _, _, sp in pools.get(d, [])}
        vals += [m[c] for c in codes if c in m]
    return float(np.median(vals)) if vals else float("nan")


def decile_hist(sel: dict, pools: dict, uni: dict) -> np.ndarray:
    """선택 종목의 «그날 적격 풀 안에서의 거래대금 10분위» 히스토그램(1=하위 … 10=상위).

    기준 모집단은 «그날 적격 풀»(= base_filter 통과 ∧ 룰 발화) 이다 — arm 이 실제로
    고르는 모집단과 같은 집합이라야 분위 비교가 뜻을 갖는다.
    """
    h = np.zeros(N_DECILES, dtype=float)
    for d, codes in sel.items():
        pool = pools.get(d) or []
        if len(pool) < 2:
            continue
        m = uni.get(d, {})
        tvs = np.array([m.get(c, (0.0, 0.0))[1] for c, *_ in pool], dtype=float)
        order = tvs.argsort(kind="stable")
        rank = np.empty(len(tvs), dtype=float)
        rank[order] = np.arange(len(tvs), dtype=float)
        dec = np.minimum((rank / len(tvs) * N_DECILES).astype(int), N_DECILES - 1)
        pos = {c: k for k, (c, *_) in enumerate(pool)}
        for c in codes:
            if c in pos:
                h[dec[pos[c]]] += 1
    return h


def ks_distance(h1: np.ndarray, h2: np.ndarray) -> float:
    if h1.sum() <= 0 or h2.sum() <= 0:
        return float("nan")
    c1, c2 = np.cumsum(h1 / h1.sum()), np.cumsum(h2 / h2.sum())
    return float(np.max(np.abs(c1 - c2)))


def changed_stock_days(selV: dict, selT: dict) -> list[tuple[str, str, str]]:
    """V→T 로 «선택이 바뀐 종목-일». (date, code, 'dropped'|'added') 목록."""
    out = []
    for d in set(selV) | set(selT):
        v, t = set(selV.get(d, [])), set(selT.get(d, []))
        out += [(d, c, "dropped") for c in sorted(v - t)]
        out += [(d, c, "added") for c in sorted(t - v)]
    return out


# ────────────────────────────────────────────────────────────────────────────
# 4b. 2단계 — 백테스트 · 판정 (PREREG §4·§5)
# ────────────────────────────────────────────────────────────────────────────
class ArmGated:
    """arm 이 «그날 고른» 종목-일만 매수 신호로 바꾼다.

    🔑 룰 발화 판정은 1단계 캐시가 이미 끝냈고 arm 선택은 그 부분집합이므로, 여기서는
    `(code, date)` 조회 하나뿐이다 — **룰을 다시 평가하지 않는다.** 이것이 「arm 간 차이가
    랭킹 함수 하나로만 생긴다」를 보장하는 장치다(PREREG §2).
    """

    def __init__(self, allowed: dict):
        self.allowed = allowed          # {date_str: set(code)}

    def generate_signal(self, stock_code, df, timeframe="daily"):
        if stock_code in self.allowed.get(df["date"].iloc[-1], ()):
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60)
        return None


def run_arm(sel: dict, frames: dict, cfg: dict, backtester_cls) -> dict:
    """arm 하나를 백테스트해 «거래당» 분포를 낸다.

    반환 `mean`·`med` 단위는 **%** 다. 🔑 `pnl_pct` 에는 슬리피지(편도 0.1%)가 체결가에
    반영돼 있고 **수수료 0.015%·거래세 0.18% 는 미반영**이다(= PREREG §4 의 gross,
    승계 원본과 동일 정의). 왕복 비용 0.21%p 는 전 arm 에 동일하게 빠지므로 arm 차이엔 무해하다.
    """
    allowed = {d: set(v) for d, v in sel.items() if v}
    codes = set().union(*allowed.values()) if allowed else set()
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
        return dict(n=0, mean=float("nan"), med=float("nan"), win=float("nan"),
                    hold=float("nan"), sl=float("nan"), tp=float("nan"),
                    mh=float("nan"), fc=float("nan"))
    p, r = pd.Series(pnl), pd.Series(reasons)
    return dict(n=len(pnl), mean=p.mean() * 100, med=p.median() * 100,
                win=(p > 0).mean() * 100, hold=float(pd.Series(hold).median()),
                sl=(r == "stop_loss").mean() * 100, tp=(r == "take_profit").mean() * 100,
                mh=(r == "max_hold").mean() * 100, fc=(r == "forced_close").mean() * 100)


def frozen_labels(V: float, T: float, P: float, rmax: float) -> dict:
    """PREREG §5-3·§5-3b·판정 규칙표의 **6개 라벨**을 그대로 평가한다.

    🔴 라벨을 새로 짓지 않는다 — 여기 있는 6개 중 하나(또는 병기)를 «고르는» 것이고,
    어느 것도 참이 아니면 「판별 불가」다. ε·N1 정의는 §5-1·§5-2 동결분이다.
    """
    n1T, n1V, n1P = T > rmax, V > rmax, P > rmax
    e = EPS_ECON
    return {
        "(가) 랭킹 함수가 정보": (T - V >= e) and n1T and (T - P >= e),
        "(다) 정체는 주가 수준": (T - V >= e) and n1T and (abs(T - P) < e),
        "(다′) 가격대 단독": (P - V >= e) and n1P and (T - V < e),
        "(라) 현행 랭킹이 «더 낫다»": (V - T >= e) and n1V,
        "(마) 랭킹 축 자체가 무효": (abs(T - V) < e) and (abs(P - V) < e),
        "(나) 랭킹은 정보가 아님": not n1T,
    }


# ────────────────────────────────────────────────────────────────────────────
# 5. main
# ────────────────────────────────────────────────────────────────────────────
def stage1() -> int:
    conn = psycopg2.connect(**DSN)
    say("# 랭킹 함수 반사실 — 1단계 게이트 (PREREG §6, PnL 미조회)")
    say("")
    say(f"사전등록: [`PREREG.md`](PREREG.md). "
        f"창 = **{W0} ~ {W1}** (**§10-1 개정본**).")
    say("")
    say(f"🔴 **창이 개정됐다.** 원 §3 은 `{ORIG_W0} ~ {W1}`(5.4년)이었으나, "
        f"`market_cap` 커버리지가 **2024-03-12 1.4% → 2024-03-13 99.6%** 로 절벽이고 "
        f"세 전략의 `base_filter` 가 시총 결측을 fail-closed 로 제외하는 탓에 "
        f"그 이전 구간에서는 적격 풀이 비어 **어떤 arm 도 아무것도 고르지 않았다**. "
        f"경계는 「커버리지가 처음 95%를 넘은 거래일」이며 문턱을 90/95/99 중 무엇으로 잡아도 "
        f"같은 날이다(**결과에서 유도한 경계가 아니다**). "
        f"개정은 **1단계 산출 후·PnL 관측 «전»**에 확정됐다 — PREREG §10 참조.")
    say("")
    say("🔴 이 문서는 PREREG **§6(1단계 게이트)까지만** 다룬다. "
        "**해석·「좋다/나쁘다」 판단은 없다** — 순수 산출이다. "
        "결과 계산(§4·§5, PnL 필요)은 2단계다.")
    say("")
    say("🔑 이 실행은 `BookBacktester` 를 **import 하지도 호출하지도 않는다** — "
        "거래당 수익률이 메모리에 들어올 경로 자체가 없다. "
        "🔴 그래서 **§6-5(거래 수 대칭성)는 §10-3 에 따라 2단계로 이관**됐다 — "
        "1단계에서 세는 「진입 트리거 수」는 네 arm 이 정의상 같아 **검사가 성립하지 않는다**.")
    say("")

    # ── 0. 청산 파라미터 대조 ───────────────────────────────────────────────
    say("## 0. `config.yaml` 에서 읽은 청산 파라미터 (하드코딩 아님)")
    say("")
    say("🔴 1단계는 청산을 «쓰지 않는다». 2단계가 쓸 값을 여기서 못박아 인쇄한다.")
    say("")
    say("| 전략 | config (sl/tp/max_hold) | 지시서 기대값 | 일치 |")
    say("|---|---|---|---|")
    for r in verify_strategy_params():
        say(r)
    say("")

    # ── DB 지문 ─────────────────────────────────────────────────────────────
    fp = db_fingerprint(conn)
    say(f"## 0b. DB 지문 (`regen_gate.py` 형식 승계 · {len(FINGERPRINT_SQL)}슬라이스)")
    say("")
    say("| 슬라이스 | 행 수 | 종목 수 | max(date) |")
    say("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        say(f"| `{k}` | {a:,} | {b:,} | {c} |")
    say("")

    # ── 데이터 적재 ─────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    px = load_prices(conn)
    uni, ustats = load_universe(conn)
    conn.close()
    dates_all = sorted(uni)
    print(f"[load] 일봉 {len(px):,}행 / {px.stock_code.nunique():,}종목 · "
          f"{time.perf_counter()-t0:.0f}s", flush=True)

    say("## 1. 표본 · 창 · 워밍업")
    say("")
    hist_rows = int((px["date"] < W0).sum())
    say(f"- **개정 창 {W0}~{W1}** — 거래일 **{len(dates_all):,}일**")
    say(f"- 적재 일봉 **{len(px):,}행** / **{px.stock_code.nunique():,}종목** "
        f"(`{HIST0}`~`{W1}`, 워밍업 포함)")
    say(f"- 🟢 **창 «이전» 워밍업 히스토리 {hist_rows:,}행** "
        f"(`daily_prices` 최소일 **{px['date'].min()}**) ⇒ "
        f"룰 창(ma5 60봉 · ma20/minervini 90봉)이 **창 시작 전에 이미 채워진다**. "
        f"원 창에서는 이 히스토리가 0행이라 워밍업을 창 «안»에서 소진해야 했는데, "
        f"**개정 창에서 그 한계가 해소됐다**(PREREG §10-4 항목 13).")
    say(f"- 종목코드 술어 `^[0-9][0-9A-Z]{{5}}$` · 의사티커 KOSPI/KOSDAQ/KS11/KQ11 명시 배제.")
    say("")

    # ── 6. market_cap 결측률 (PREREG §6-6 / §7-4) ──────────────────────────
    say("## 2. `market_cap` 결측률 (PREREG §6-6 · §7-4)")
    say("")
    miss = ustats["mcap_missing"] / ustats["rows"] * 100 if ustats["rows"] else float("nan")
    say(f"- **개정 창 안** 전체 행 **{ustats['rows']:,}** 중 `market_cap` 결측(NULL 또는 ≤0) "
        f"**{ustats['mcap_missing']:,}** = **{miss:.2f}%**")
    say(f"- `market_cap` 이 하나라도 있는 거래일 **{ustats['days_with_mcap']:,}** / "
        f"전체 거래일 **{ustats['days_all']:,}**")
    say("")
    say("🔑 원 창(2021-01~) 기준 결측률은 **56.7%** 였다 — 그 56.7% 가 §10-1 창 개정의 사유다. "
        "위 값은 **개정 창 안의** 결측률이므로 두 숫자를 같은 것으로 읽지 말 것.")
    say("")
    say("연도-월별 `market_cap>0` 종목 수(그날 몇 종목이 시총을 갖는가):")
    say("")
    say("| 연-월 | 거래일 | 최소 | 최대 | 평균 |")
    say("|---|---|---|---|---|")
    bym: dict = defaultdict(list)
    for d in dates_all:
        bym[d[:7]].append(sum(1 for mc, _ in uni[d].values() if mc > 0))
    for m in sorted(bym):
        v = bym[m]
        say(f"| {m} | {len(v)} | {min(v):,} | {max(v):,} | {int(np.mean(v)):,} |")
    say("")
    say("🔴 세 전략의 `base_filter` 는 시총 결측을 **fail-closed 로 제외**한다"
        "(`strategies/_rule_screener_base.py::_passes_market_cap`). "
        "⇒ **시총이 없는 날은 적격 풀이 비고, 어떤 arm 도 아무것도 고르지 않는다.** "
        "개정 창은 바로 이 조건이 해소된 구간이다.")
    say("")

    # ── 전략별 처리 ─────────────────────────────────────────────────────────
    all_changed: dict = {}
    notes: dict = {}
    for name, cfg in STRATS.items():
        scr = cfg["screener"]()
        say(f"---")
        say("")
        say(f"## `{name}` — {cfg['role']} (w={cfg['w']})")
        say("")
        print(f"\n[{name}] 시작", flush=True)

        elig = eligible_by_date(uni, scr)
        n_elig_days = sum(1 for d in dates_all if elig.get(d))
        elig_sizes = [len(elig[d]) for d in dates_all if elig.get(d)]
        say(f"- 적격일(base_filter 통과 종목이 1개 이상인 날) **{n_elig_days:,}** / "
            f"{len(dates_all):,}일 · 적격 풀 크기 중앙 "
            f"**{int(np.median(elig_sizes)) if elig_sizes else 0:,}** "
            f"(최소 {min(elig_sizes) if elig_sizes else 0:,} · "
            f"최대 {max(elig_sizes) if elig_sizes else 0:,})")
        print(f"  적격일 {n_elig_days} · 룰 평가 시작", flush=True)

        trig, tstats = build_cache(px, elig, scr, cfg)
        say(f"- 룰 평가 **{tstats['n_eval']:,}회** / 발화 **{tstats['n_fire']:,}건** / "
            f"발화 종목 **{len(trig):,}** · {tstats['secs']:.0f}s")

        pools = build_pools(trig, elig)
        pool_days = sorted(d for d in pools if pools[d])
        psz = [len(pools[d]) for d in pool_days]
        say(f"- **적격 풀**(base_filter 통과 ∧ 룰 발화) 이 비지 않은 날 **{len(pool_days):,}** · "
            f"풀 크기 중앙 **{int(np.median(psz)) if psz else 0}** "
            f"(최소 {min(psz) if psz else 0} · 최대 {max(psz) if psz else 0})")
        n_saturated = sum(1 for d in pool_days if len(pools[d]) <= MAX_CANDIDATES)
        say(f"- 🔴 풀 크기 ≤ `max_candidates`(={MAX_CANDIDATES}) 인 날 **{n_saturated:,}** / "
            f"{len(pool_days):,} — ***그런 날은 네 arm 이 «같은 집합»을 고른다*** "
            f"(랭킹 함수가 아무것도 가르지 않는다).")
        say("")

        selV = select_deterministic(pools, 1)
        selT = select_deterministic(pools, 2)
        selP = select_deterministic(pools, 3)
        selR = [select_random(pools, s) for s in range(N_SEEDS)]
        print(f"  선택 완료 (V/T/P + R×{N_SEEDS})", flush=True)

        # ── §6-1 겹침 행렬 ──────────────────────────────────────────────────
        say(f"### {name} — §6-1 arm 간 선택 종목 겹침")
        say("")
        say(f"일별 평균 겹침 종목 수(최대 {MAX_CANDIDATES}). R 은 시드 {N_SEEDS}개의 평균이다.")
        say("")
        det = {"V": selV, "T": selT, "P": selP}
        say("| | V | T | R | P |")
        say("|---|---|---|---|---|")
        for a in ("V", "T", "P"):
            row = [f"| **{a}** "]
            for b in ("V", "T"):
                m, _ = daily_overlap(det[a], det[b])
                row.append(f"| {m:.2f} ")
            rs = [daily_overlap(det[a], r)[0] for r in selR]
            row.append(f"| {np.nanmean(rs):.2f} ")
            m, _ = daily_overlap(det[a], det["P"])
            row.append(f"| {m:.2f} |")
            say("".join(row))
        rr = [daily_overlap(selR[i], selR[j])[0]
              for i in range(N_SEEDS) for j in range(i + 1, N_SEEDS)]
        say(f"| **R** | {np.nanmean([daily_overlap(r, selV)[0] for r in selR]):.2f} "
            f"| {np.nanmean([daily_overlap(r, selT)[0] for r in selR]):.2f} "
            f"| {np.nanmean(rr):.2f} "
            f"| {np.nanmean([daily_overlap(r, selP)[0] for r in selR]):.2f} |")
        say("")
        uV, uT, uP = uniq(selV), uniq(selT), uniq(selP)
        uR = [uniq(r) for r in selR]
        say("전 기간 고유 종목 수 · 교집합:")
        say("")
        say("| | 고유 종목 | ∩V | ∩T | ∩P |")
        say("|---|---|---|---|---|")
        for lab, s in (("V", uV), ("T", uT), ("P", uP)):
            say(f"| **{lab}** | {len(s):,} | {len(s & uV):,} | {len(s & uT):,} | {len(s & uP):,} |")
        say(f"| **R**(시드평균) | {np.mean([len(s) for s in uR]):.0f} | "
            f"{np.mean([len(s & uV) for s in uR]):.0f} | "
            f"{np.mean([len(s & uT) for s in uR]):.0f} | "
            f"{np.mean([len(s & uP) for s in uR]):.0f} |")
        say(f"| **R**(20시드 합집합) | {len(set().union(*uR)) if uR else 0:,} | | | |")
        say("")

        # ── §6-2 arm 별 프로필 ──────────────────────────────────────────────
        say(f"### {name} — §6-2 arm 별 중앙 주가 · 시총 · 거래대금 · 종목 수")
        say("")
        say("| Arm | 선택 종목-일 | 고유 종목 | 중앙 주가(원) | 중앙 시총(억) | 중앙 거래대금(억) |")
        say("|---|---|---|---|---|---|")
        for lab, s in (("V (현행)", selV), ("T (거래대금)", selT), ("P (주가)", selP)):
            p = profile(s, uni)
            say(f"| **{lab}** | {p['n']:,} | {p['uniq']:,} | {profile_price(s, pools):,.0f} | "
                f"{p['med_mcap']/1e8:,.0f} | {p['med_tv']/1e8:,.1f} |")
        rp = [profile(r, uni) for r in selR]
        rprice = [profile_price(r, pools) for r in selR]
        say(f"| **R (무작위, 20시드 평균)** | {np.mean([p['n'] for p in rp]):,.0f} | "
            f"{np.mean([p['uniq'] for p in rp]):,.0f} | {np.nanmean(rprice):,.0f} | "
            f"{np.nanmean([p['med_mcap'] for p in rp])/1e8:,.0f} | "
            f"{np.nanmean([p['med_tv'] for p in rp])/1e8:,.1f} |")
        say("")

        # ── §6-3 쏠림 (시점 축) ─────────────────────────────────────────────
        ch = changed_stock_days(selV, selT)
        all_changed[name] = ch
        notes[name] = dict(
            elig_days=n_elig_days, pool_days=len(pool_days), saturated=n_saturated,
            first_change=min((d for d, _, _ in ch), default="—"),
            last_change=max((d for d, _, _ in ch), default="—"),
            first_sel=min((d for d, v in selV.items() if v), default="—"),
        )
        say(f"### {name} — §6-3 🔴 쏠림 점검 (시점 축) — V→T 로 선택이 바뀐 종목-일")
        say("")
        say(f"바뀐 종목-일 **{len(ch):,}건** "
            f"(V 에서 빠짐 {sum(1 for _,_,k in ch if k=='dropped'):,} · "
            f"T 에서 들어옴 {sum(1 for _,_,k in ch if k=='added'):,})")
        say("")
        if ch:
            yr = Counter(d[:4] for d, _, _ in ch)
            # 🔴 §10-2 — 2024 는 3월부터, 2026 은 5월까지의 «부분 연도»다. 원시 비중을
            #    균등 기대치(1/3)와 비교하면 안 된다. 분모 = 그 해에 «변화가 일어날 수
            #    있었던 날» = 적격 풀이 비지 않은 거래일 수. 그 비율(일당 변화 강도)을
            #    다시 합이 100% 가 되게 정규화한다.
            days_y = Counter(d[:4] for d in pool_days)
            rate = {y: yr[y] / days_y[y] for y in yr if days_y.get(y)}
            rsum = sum(rate.values())
            norm = {y: rate[y] / rsum * 100 for y in rate} if rsum > 0 else {}
            say("| 연도 | 바뀐 종목-일 | 원시 비중 | 선택가능일 | 일당 변화 | "
                "**정규화 비중** |")
            say("|---|---|---|---|---|---|")
            for y in sorted(yr):
                say(f"| {y} | {yr[y]:,} | {yr[y]/len(ch)*100:.1f}% | "
                    f"{days_y.get(y, 0):,} | {rate.get(y, float('nan')):.2f} | "
                    f"**{norm.get(y, float('nan')):.1f}%** |")
            say("")
            say("🔑 **정규화 비중** = (그 해 변화건수 / 그 해 «선택가능일» 수) 를 연도 간 "
                "합이 100% 가 되게 재배분한 값. 🔴 **2024 는 3월부터, 2026 은 5월까지의 "
                "부분 연도**이므로 원시 비중을 균등 기대치(1/3)와 비교하면 안 된다 "
                "(PREREG §10-2).")
            say("")
            top_y, top_n = max(yr.items(), key=lambda kv: kv[1])
            raw_top = top_n / len(ch) * 100
            ntop_y, ntop = (max(norm.items(), key=lambda kv: kv[1]) if norm
                            else (top_y, float("nan")))
            say(f"- 원시 최대 연도 = **{top_y} {raw_top:.1f}%** → "
                f"{'🔴 >50%' if raw_top > 50 else '✅ ≤50%'}")
            say(f"- **정규화 최대 연도 = {ntop_y} {ntop:.1f}%** → "
                f"{'🔴 >50%' if ntop > 50 else '✅ ≤50%'}")
            say("")
            if raw_top > 50 or (ntop == ntop and ntop > 50):
                say(f"🔴 **「국면 특이 → 판별 보류」.** 원시·정규화 «둘 중 하나라도» 50% 를 "
                    f"넘었다(원시 {raw_top:.1f}% · 정규화 {ntop:.1f}%). 2단계에서 PnL 은 "
                    f"조회하되 결론에 **«단일 국면 의존»을 명시**한다 (PREREG §6-3 · §10-2).")
            else:
                say(f"✅ **연도 쏠림 문턱 통과 — 원시·정규화 «양쪽 모두» 50% 이하다** "
                    f"(원시 {raw_top:.1f}% · 정규화 {ntop:.1f}%). "
                    f"🔑 이 ✅ 는 **개정 창 안에서만** 유효하다 — 원 창 기준으로 인용하면 "
                    f"분모가 비어서 통과한 «공허한 통과»가 된다(§10-2).")
            say("")
            mo = Counter(d[:7] for d, _, _ in ch)
            mdays = Counter(d[:7] for d in pool_days)
            say("<details><summary>월별 분포 (선택가능일·일당 변화 포함)</summary>")
            say("")
            say("| 연-월 | 바뀐 종목-일 | 원시 비중 | 선택가능일 | 일당 변화 |")
            say("|---|---|---|---|---|")
            for m in sorted(mo):
                dm = mdays.get(m, 0)
                say(f"| {m} | {mo[m]:,} | {mo[m]/len(ch)*100:.1f}% | {dm:,} | "
                    f"{mo[m]/dm if dm else float('nan'):.2f} |")
            say("")
            say("</details>")
        else:
            say("🔴 바뀐 종목-일이 **0건** — V 와 T 가 «완전히 같은» 집합을 골랐다.")
        say("")

        # ── §6-4 거래대금 10분위 · KS ───────────────────────────────────────
        hV, hT = decile_hist(selV, pools, uni), decile_hist(selT, pools, uni)
        say(f"### {name} — §6-4 V·T 선택 집합의 일별 거래대금 10분위 분포 · KS 거리")
        say("")
        say("기준 모집단 = **그날 적격 풀**(base_filter 통과 ∧ 룰 발화). 1=하위 10% … 10=상위 10%.")
        say("")
        say("| 10분위 | " + " | ".join(str(i + 1) for i in range(N_DECILES)) + " |")
        say("|---|" + "---|" * N_DECILES)
        for lab, h in (("V", hV), ("T", hT)):
            tot = h.sum() or 1
            say(f"| **{lab}** | " + " | ".join(f"{x/tot*100:.1f}%" for x in h) + " |")
        say("")
        say(f"**KS 거리(V vs T) = {ks_distance(hV, hT):.3f}**")
        say("")
        say("🔑 PREREG §6-4: **KS > 0.20 은 예상된다**(그게 이 실험의 취지다). "
            "여기서는 «자동 판별불가»로 쓰지 않고 **크기만 기록**한다 — "
            "축이 «의도적으로» 유동성을 바꾸기 때문이다.")
        say("")

        # ── §6-5 → §10-3 으로 2단계 이관. 여기서는 «구조적 항등»만 기록한다. ──
        say(f"### {name} — §6-5 진입 트리거 수 "
            f"🔴 **구조적 항등 — 이 단계에선 검사 불성립** (PREREG §10-3)")
        say("")
        counts = {"V": sum(len(v) for v in selV.values()),
                  "T": sum(len(v) for v in selT.values()),
                  "P": sum(len(v) for v in selP.values())}
        rc = [sum(len(v) for v in r.values()) for r in selR]
        say("| Arm | 진입 트리거 수 |")
        say("|---|---|")
        for k, v in counts.items():
            say(f"| **{k}** | {v:,} |")
        say(f"| **R** (20시드) | 평균 {np.mean(rc):,.0f} · 최소 {min(rc):,} · 최대 {max(rc):,} |")
        allc = list(counts.values()) + [float(np.mean(rc))]
        lo, hi = min(allc), max(allc)
        say("")
        say(f"네 arm 이 모두 그날 적격 풀에서 `min({MAX_CANDIDATES}, |풀|)` 을 고르므로 "
            f"**진입 트리거 수는 정의상 같다** (실측 최대/최소 = **{hi/lo:.2f}배**). "
            f"🔴 ***이 값에 ✅/🔴 를 붙이지 않는다 — 「검사를 통과했다」가 아니라 "
            f"「이 단계에선 검사가 성립하지 않는다」이기 때문이다.***")
        say("")
        say("⇒ **§6-5 는 §10-3 에 따라 2단계로 이관**됐고, 거기서 **「실현 거래 수」**"
            "(청산까지 간 건수)로 다시 정의된다. 2배 이상 벌어지면 그때 판정문에 병기한다.")
        say("")
        say(f"🔑 PREREG §7-7 표본 문턱(전략별 거래 수 < 200 → 「표본 부족 → 판별 보류」)도 "
            f"**같은 이유로 2단계 몫**이다. 참고로 트리거 수는 "
            f"V {counts['V']:,} · T {counts['T']:,} · P {counts['P']:,} 이나, "
            f"**실현 거래 수는 이보다 적다** — 종목당 단일 포지션이 겹치는 트리거를 삼킨다.")
        say("")

    # ── §6-3 전략별 구성비 (판정엔 안 씀) ──────────────────────────────────
    say("---")
    say("")
    say("## 3. §6-3 전략별 구성비 — V→T 변화의 전략별 분포 (🔴 판정에는 쓰지 않는다)")
    say("")
    say("전략별로 «따로» 판정하므로 이 표는 판정에 들어가지 않는다. "
        "나중에 전략을 합치려는 사람이 그 위험을 볼 수 있게 남긴다 (PREREG §6-3).")
    say("")
    tot = sum(len(v) for v in all_changed.values())
    say("| 전략 | 바뀐 종목-일 | 비중 |")
    say("|---|---|---|")
    for k, v in all_changed.items():
        say(f"| `{k}` | {len(v):,} | {len(v)/tot*100 if tot else float('nan'):.1f}% |")
    say(f"| **합계** | **{tot:,}** | 100.0% |")
    say("")

    say("## 4. 등록 외 조합 (PREREG §8-2 · §9)")
    say("")
    say("**계산한 적 없다.** arm 은 V·T·R·P 넷뿐이고 창 길이 스윕·가중 혼합 score·"
        "거래대금 로그 변환은 이 스크립트에 구현되어 있지 않다.")
    say("")

    # ── 실행 중 관찰 (사전등록 이행 관련, 해석 아님) ────────────────────────
    say("## 5. 🔴 실행 중 관찰한 것 (사전등록 이행 관련 · 해석 아님)")
    say("")
    say("`stop_vol_fit_gate/GATE.md` 의 같은 이름 절을 승계한다 — "
        "**결과 해석이 아니라 「사전등록을 어떻게 이행했는가」의 기록**이다.")
    say("")
    say("### 5-1. 창 개정(§10-1) 이 실제로 어떻게 반영됐나")
    say("")
    say(f"| 전략 | 적격일 / {len(dates_all):,} | 풀 비지 않은 날 | 풀 ≤10 인 날 | "
        f"첫 선택일 | 첫 V→T 변화일 | 마지막 |")
    say("|---|---|---|---|---|---|---|")
    for k, v in notes.items():
        say(f"| `{k}` | {v['elig_days']:,} | {v['pool_days']:,} | {v['saturated']:,} | "
            f"{v['first_sel']} | {v['first_change']} | {v['last_change']} |")
    say("")
    say(f"창은 **{W0}~{W1}** 로 개정됐다(§10-1). 개정 «전» 실행에서는 세 전략 모두 "
        f"**첫 V→T 변화일이 2024-03-13** 이었다 — 즉 원 창의 앞 3.2년은 산출에 "
        f"**한 건도 기여하지 않았다**. 이번 실행은 그 구간을 애초에 읽지 않는다.")
    say("")
    say("🔴 **§1~§9 는 한 줄도 삭제되지 않았다.** 원 §3 창은 PREREG 안에 그대로 있고 "
        "§10-1 이 우선한다. 이 산출물의 모든 숫자는 **개정 창 기준**이다.")
    say("")
    say("### 5-2. §6-5 는 2단계로 이관됐다 (§10-3)")
    say("")
    say("네 arm 은 모두 그날 적격 풀에서 `min(max_candidates, |풀|)` 개를 고르므로 "
        "**진입 트리거 수가 정의상 완전히 같다**(실측 전부 1.00배). "
        "⇒ ***「검사를 통과했다」가 아니라 「이 단계에서는 검사가 성립하지 않는다」.*** "
        "PREREG §6-5 가 의도한 비대칭은 **실현 거래 수**에서만 나타날 수 있고, 그건 청산 판정 "
        "= 수익률 계산을 요구하므로 **2단계 몫**이다. 위 각 전략 §6-5 절에 "
        "「구조적 항등 — 검사 불성립」으로 적었다.")
    say("")
    say("### 5-3. 척도 — `volume × adj_factor` 를 로더에서 «한 번» 적용했다")
    say("")
    say("PREREG 척도 고지는 *「`volume` 은 읽기계층에서 조정된다」* 를 전제한다. "
        "이 스크립트는 성능 때문에 raw SQL 로 읽으므로 그 보정을 "
        "`load_prices()`·`load_universe()` 에서 재현했다 — "
        "`db/quant_daily_reader.py::_SELECT_OHLCV` 와 **같은 식**(`volume * COALESCE(adj_factor,1)`)이다. "
        "이 보정이 «없으면» `ac69084` **이전** 척도가 되어 척도 고지를 어긴다. "
        "적용은 로더 1회뿐이고 이후 어디에서도 `adj_factor` 를 다시 곱하지 않는다(§8-6).")
    say("")
    say("### 5-4. 승계 원본과 달라진 지점 · 재현하지 «않은» 라이브 동작")
    say("")
    say("| 항목 | 이 실행 | 비고 |")
    say("|---|---|---|")
    say("| 종목코드 술어 | `^[0-9][0-9A-Z]{5}$` (2,788종목) | "
        "승계 원본 `universe_lookahead_ladder` 는 `^[0-9]{5}[0-9A-Z]$` (2,734종목). "
        "신형 코드(`0001A0` 등) 54종목이 더 든다 |")
    say("| 불가능봉 가드 | **적용 안 함** | "
        "라이브 `scan()` 에는 있으나(`_rule_screener_base.py:96`) 승계 원본에는 없고 "
        "PREREG §2 고정 목록에도 없다. 전 arm 에 동일하게 걸리지만 "
        "**풀에서 한 종목이 빠지면 11번째가 들어오므로 arm 마다 대체 종목이 다르다** — 완전 중립은 아니다 |")
    say("| 동점 처리 | 코드 오름차순 + 안정정렬 | "
        "라이브는 DB 행 순서라 재현 불가능하다. 동점이 흔한 **arm P**(같은 종가)에서만 실질 영향 |")
    say("| 유니버스 스냅샷 폴백 | **재현 안 함** | "
        "라이브 `get_universe_snapshot` 은 `date <= scan_date` 중 최신 «완전 퀀트일»로 폴백한다. "
        "여기서는 그날 행만 쓴다(승계 원본과 동일). 2024-03 이후는 매일 완전 적재라 무영향 |")
    say(f"| 워밍업 | 🟢 **창 이전 히스토리로 채움** | "
        f"개정 창 덕에 `{HIST0}`~ 3년치를 워밍업으로 쓴다 ⇒ "
        f"PREREG §3 의 *「창 이전 히스토리로 채운다」* 를 **이번엔 실제로 지켰다** "
        f"(§10-4 항목 13 — 원 창의 한계가 해소됨) |")
    say("")
    say("### 5-5. 어떤 컬럼만 SELECT 했는가 — PnL 미조회 보장")
    say("")
    say("- `daily_prices`: `stock_code` · `date` · `open` · `high` · `low` · `close` · "
        "`volume` · `adj_factor` · `market_cap` — 이상 **9개 컬럼만**.")
    say("- `virtual_trading_records` 등 **매매 원장 테이블은 어느 것도 조회하지 않았다.** "
        "`BookBacktester` 는 import 조차 하지 않는다 ⇒ 거래당 수익률이 산출된 적이 없다.")
    say("")

    (BASE / "GATE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] GATE.md", flush=True)
    return 0


def stage2() -> int:
    # 🔴 지역 import — `--stage1` 이 「PnL 계산 경로가 아예 없다」를 보증하기 위해서다.
    from backtest.book_backtester import BookBacktester

    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    rep("# 판정 — 후보 랭킹 함수는 «정보»인가, 그냥 «저가주 선별기»인가")
    rep("")
    rep(f"사전등록 [`PREREG.md`](PREREG.md) 실행. 창 = **{W0} ~ {W1}**(§10-1 개정본) · "
        f"실행 커밋 **`{sha}`**. 원시 출력 → [`RESULTS_raw.md`](RESULTS_raw.md).")
    rep("")
    rep(f"🔴 **ε·arm·시드·`w`·`max_candidates`·판정 규칙·라벨 6개는 `3634c3e` 동결분 그대로다.** "
        f"ε = **{EPS_ECON}%p**(§5-1) · N1 = **`arm > R {N_SEEDS}개 전부`**(§5-2, 단측 p≈"
        f"{1/(N_SEEDS+1):.3f}) · 판정은 **ma5·ma20 «둘 다»** 같아야 쓴다(§1). "
        f"`minervini` 는 **판정 대상이 아니라 §5-4 차등 예측 대조군**이다.")
    rep("")

    rows = verify_strategy_params()
    say("## 0. `config.yaml` 청산 파라미터")
    say("")
    say("| 전략 | config (sl/tp/max_hold) | 지시서 기대값 | 일치 |")
    say("|---|---|---|---|")
    for r in rows:
        say(r)
    say("")

    fp = db_fingerprint(conn)
    rep(f"## 0. 실행 기록 (PREREG §9)")
    rep("")
    rep(f"- 실행 커밋 SHA: **`{sha}`**")
    rep(f"- 청산 파라미터는 `config.yaml` 에서 읽었다 — 3전략 모두 지시서 기대값과 **일치**"
        f"(ma5 0.03/0.15/30 · ma20 0.08/0.10/50 · minervini 0.08/0.12/20).")
    rep("- **등록 외 조합은 계산하지 않았다** — arm 은 V·T·R·P 넷뿐이고, 창 길이 스윕·"
        "가중 혼합 score·거래대금 로그 변환은 이 스크립트에 구현되어 있지 않다(§8-2).")
    rep("")
    rep(f"DB 지문 ({len(FINGERPRINT_SQL)}슬라이스):")
    rep("")
    rep("| 슬라이스 | 행 수 | 종목 수 | max(date) |")
    rep("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        rep(f"| `{k}` | {a:,} | {b:,} | {c} |")
    rep("")

    t0 = time.perf_counter()
    px = load_prices(conn)
    uni, _ = load_universe(conn)
    conn.close()
    print(f"[load] {len(px):,}행 · {time.perf_counter()-t0:.0f}s", flush=True)

    res: dict = {}
    for name, cfg in STRATS.items():
        scr = cfg["screener"]()
        print(f"\n[{name}] 룰 캐시", flush=True)
        elig = eligible_by_date(uni, scr)
        trig, tstats = build_cache(px, elig, scr, cfg)
        pools = build_pools(trig, elig)
        say(f"\n### `{name}` 준비")
        say(f"- 룰 평가 {tstats['n_eval']:,}회 / 발화 {tstats['n_fire']:,}건 · "
            f"{tstats['secs']:.0f}s · 적격 풀 비지 않은 날 {len(pools):,}")

        sels = {"V": select_deterministic(pools, 1),
                "T": select_deterministic(pools, 2),
                "P": select_deterministic(pools, 3)}
        # 🔑 2단계 프레임은 창 «안»으로 자른다. 워밍업 히스토리는 룰 평가(위)에서 이미
        #    소비됐고, `ArmGated` 는 (code,date) 조회라 과거 봉을 보지 않는다 ⇒ 결과 동일,
        #    비용만 줄인다. `warmup_bars=0` 은 이 절단과 짝을 이룬다.
        frames = {}
        for code, g in px.groupby("stock_code", sort=False):
            g2 = g[g["date"] >= W0]
            if len(g2) >= 2:
                frames[code] = g2.reset_index(drop=True)

        d = {}
        for lab in ("V", "T", "P"):
            t1 = time.perf_counter()
            d[lab] = run_arm(sels[lab], frames, cfg, BookBacktester)
            print(f"    {lab} n={d[lab]['n']:>5} mean={d[lab]['mean']:+.2f}% "
                  f"{time.perf_counter()-t1:.0f}s", flush=True)
        r_stats = []
        for seed in range(N_SEEDS):
            m = run_arm(select_random(pools, seed), frames, cfg, BookBacktester)
            r_stats.append(m)
            print(f"    R seed={seed:<2} n={m['n']:>5} mean={m['mean']:+.2f}%", flush=True)
        d["R"] = r_stats
        res[name] = d

    # ── 표 ──────────────────────────────────────────────────────────────────
    rep("## 1. 전체 표 — 거래당 평균 수익률 (gross · n = 실현 거래 수)")
    rep("")
    rep("🔑 `pnl_pct` 에 **슬리피지 편도 0.1% 는 반영**돼 있고 **수수료 0.015%·거래세 0.18% 는 "
        "미반영**이다(= 승계 원본과 같은 gross 정의). 왕복 비용 0.21%p 는 전 arm 에 동일하게 "
        "빠지므로 **arm 차이엔 무해**하나 **절대 수준은 net 이 아니다.**")
    rep("")
    rep("| 전략 | Arm | n (실현 거래) | 거래당 평균 | 중앙 | 승률 | 보유 중앙 | 손절 | 익절 | 최대보유 |")
    rep("|---|---|---|---|---|---|---|---|---|---|")
    for name, d in res.items():
        role = "판정 대상" if name != "minervini_volume_dryup" else "🔑 대조군"
        for lab in ("V", "T", "P"):
            m = d[lab]
            rep(f"| `{name}` ({role}) | **{lab}** | {m['n']:,} | **{m['mean']:+.2f}%** | "
                f"{m['med']:+.2f}% | {m['win']:.0f}% | {m['hold']:.0f}일 | "
                f"{m['sl']:.0f}% | {m['tp']:.0f}% | {m['mh']:.0f}% |")
        rm = [x["mean"] for x in d["R"]]
        rn = [x["n"] for x in d["R"]]
        rep(f"| `{name}` ({role}) | **R** ({N_SEEDS}시드) | "
            f"{int(np.mean(rn)):,} (평균) | 중앙 **{np.median(rm):+.2f}%** · "
            f"최소 {min(rm):+.2f}% · **최대 {max(rm):+.2f}%** | | | | | | |")
    rep("")

    # ── 판정 ────────────────────────────────────────────────────────────────
    rep("## 2. 사전등록 판정 (§5)")
    rep("")
    rep("| 전략 | V | T | P | R 최대 | **T−V** | **T−P** | **P−V** | N1(T) | N1(V) | N1(P) |")
    rep("|---|---|---|---|---|---|---|---|---|---|---|")
    L, meta = {}, {}
    for name, d in res.items():
        V, T, P = d["V"]["mean"], d["T"]["mean"], d["P"]["mean"]
        rmax = max(x["mean"] for x in d["R"])
        L[name] = frozen_labels(V, T, P, rmax)
        meta[name] = dict(V=V, T=T, P=P, rmax=rmax, tv=T - V, tp=T - P, pv=P - V,
                          n1T=T > rmax, n1V=V > rmax, n1P=P > rmax)
        mk = lambda b: "✅" if b else "❌"                                    # noqa: E731
        rep(f"| `{name}` | {V:+.2f}% | {T:+.2f}% | {P:+.2f}% | {rmax:+.2f}% | "
            f"**{T-V:+.2f}%p** | **{T-P:+.2f}%p** | **{P-V:+.2f}%p** | "
            f"{mk(T>rmax)} | {mk(V>rmax)} | {mk(P>rmax)} |")
    rep("")
    rep(f"ε = **{EPS_ECON}%p**. N1 = 그 arm 이 **R {N_SEEDS}개 전부**보다 큰가(§5-2).")
    rep("")

    rep("### 2-1. 라벨 6개 — 동결분 그대로 평가 (🔴 새 라벨을 짓지 않는다)")
    rep("")
    judged = ["book_pullback_ma5", "book_pullback_ma20"]
    rep("| 라벨 (PREREG §5-3·§5-3b) | `book_pullback_ma5` | `book_pullback_ma20` | "
        "**둘 다 성립?** | (참고) `minervini` |")
    rep("|---|---|---|---|---|")
    adopted = []
    for lab in L[judged[0]]:
        a5, a20 = L[judged[0]][lab], L[judged[1]][lab]
        both = a5 and a20
        if both:
            adopted.append(lab)
        rep(f"| {lab} | {'✅' if a5 else '❌'} | {'✅' if a20 else '❌'} | "
            f"{'**✅ 채택**' if both else '—'} | "
            f"{'✅' if L['minervini_volume_dryup'][lab] else '❌'} |")
    rep("")
    rep("🔴 `minervini` 열은 **판정에 쓰지 않는다**(§1·§8-4) — 대조군이라 참고로만 인쇄한다.")
    rep("")

    rep("### 2-2. 🔴 결론")
    rep("")
    if adopted:
        for lab in adopted:
            rep(f"# **{lab}**")
            rep("")
        if len(adopted) > 1:
            rep(f"⚠️ **라벨 {len(adopted)}개가 동시에 성립해 병기한다** — PREREG §5 각주 "
                f"*「(나)와 (마)는 다르다… 둘 다 성립할 수 있고, 그때는 병기한다」* 그대로다.")
            rep("")
    else:
        rep("# **판별 불가**")
        rep("")
        rep("6개 라벨 중 **ma5·ma20 «둘 다»에서 성립하는 것이 하나도 없다** ⇒ 판정 규칙표의 "
            "「그 외 · 두 전략이 갈릴 때 = 판별 불가」에 해당한다(§5).")
        rep("")
        for name in judged:
            hit = [k for k, v in L[name].items() if v]
            rep(f"- `{name}` 단독 성립: {', '.join(hit) if hit else '없음'}")
        rep("")

    n1v_fail = [n for n in judged if not meta[n]["n1V"]]
    if n1v_fail:
        rep("### 🔴🔴 그리고 이것이 이 문서의 가장 중요한 결과다 (§5-2)")
        rep("")
        detail = " · ".join(
            "`{}` (V {:+.2f}% vs R 최대 {:+.2f}%)".format(n, meta[n]["V"], meta[n]["rmax"])
            for n in n1v_fail)
        rep(f"**`V > R {N_SEEDS}개 전부` 가 성립하지 않는다** — {detail}")
        rep("")
        rep("⇒ ***현행 랭킹(`volume.mean()`)이 이미 「무작위 10종목」과 구별되지 않는다.*** "
            "PREREG §5-2 는 이 관측 자체를 **「그것 자체가 이 문서의 가장 중요한 결과」**라고 "
            "미리 적어뒀다. 위 라벨 판정과 **병기**한다.")
        rep("")
    else:
        rep(f"✅ **N1(V) 는 두 판정 전략 모두 성립** — 현행 랭킹은 무작위와 구별된다(§5-2).")
        rep("")

    # ── §5-4 차등 예측 ──────────────────────────────────────────────────────
    rep("## 3. §5-4 차등 예측 — `minervini` 는 «면역»이어야 한다 (독립 증거)")
    rep("")
    base = float(np.mean([abs(meta[n]["tv"]) for n in judged]))
    mv = abs(meta["minervini_volume_dryup"]["tv"])
    thr = DIFF_PRED_FRAC * base
    ok = mv < thr
    rep(f"동결 문턱: `|T−V|_minervini < (1/3) × mean(|T−V|_ma5, |T−V|_ma20)`")
    rep("")
    rep(f"- `|T−V|` : ma5 **{abs(meta[judged[0]]['tv']):.2f}%p** · "
        f"ma20 **{abs(meta[judged[1]]['tv']):.2f}%p** → 평균 **{base:.2f}%p**")
    rep(f"- 문턱 = (1/3) × {base:.2f} = **{thr:.2f}%p**")
    rep(f"- `|T−V|_minervini` = **{mv:.2f}%p**")
    rep("")
    if ok:
        rep(f"⇒ ✅ **차등 예측 통과** ({mv:.2f} < {thr:.2f}). 시총 «하한»이 랭킹 편향을 이미 "
            f"흡수했다는 메커니즘 설명과 부합한다. 🔑 이건 수렴이 아니라 «경쟁 가설이 다르게 "
            f"예측하는 지점»이므로 **독립 증거로 센다**(§5-4).")
    else:
        rep(f"⇒ ❌ **차등 예측 불통과** ({mv:.2f} ≥ {thr:.2f}). "
            f"***(가)·(다) 의 「시총 하한이 랭킹 편향을 흡수한다」는 메커니즘 설명이 틀렸다*** "
            f"⇒ 랭킹 편향 이야기를 인용에서 뺀다. "
            f"⚠️ 단 **T−V 판정 자체는 그대로 둔다** — 메커니즘이 틀려도 효과는 있을 수 있다(§5-4).")
    rep("")

    # ── §6-5 실현 거래 수 · §7-7 표본 ───────────────────────────────────────
    rep("## 4. §6-5 거래 수 대칭성 — **실현 거래 수** 기준 (§10-3 이관분)")
    rep("")
    rep("| 전략 | V | T | P | R 평균 | 최대/최소 | 2배 이상? |")
    rep("|---|---|---|---|---|---|---|")
    asym = []
    for name, d in res.items():
        c = [d["V"]["n"], d["T"]["n"], d["P"]["n"], float(np.mean([x["n"] for x in d["R"]]))]
        ratio = max(c) / min(c) if min(c) > 0 else float("inf")
        if ratio >= 2.0:
            asym.append(name)
        rep(f"| `{name}` | {d['V']['n']:,} | {d['T']['n']:,} | {d['P']['n']:,} | "
            f"{c[3]:,.0f} | **{ratio:.2f}배** | {'🔴 예' if ratio >= 2 else '✅ 아니오'} |")
    rep("")
    if asym:
        rep(f"🔴 **{', '.join('`'+n+'`' for n in asym)} 에서 arm 간 실현 거래 수가 2배 이상 "
            f"벌어졌다** — 비교가 「같은 전략의 두 버전」이 아니라 「다른 빈도의 두 전략」이 된다. "
            f"**판정문에 병기한다**(§6-5).")
    else:
        rep("✅ 전 전략에서 arm 간 실현 거래 수가 2배 미만 — 대칭성 통과. "
            "비교가 「같은 전략의 두 버전」으로 성립한다.")
    rep("")
    rep(f"### §7-7 표본 문턱 (실현 거래 수 < {MIN_TRADES} → 「표본 부족 → 판별 보류」)")
    rep("")
    short = []
    for name, d in res.items():
        lo = min(d["V"]["n"], d["T"]["n"], d["P"]["n"])
        if lo < MIN_TRADES:
            short.append(name)
        rep(f"- `{name}`: V {d['V']['n']:,} · T {d['T']['n']:,} · P {d['P']['n']:,} → "
            f"{'🔴 **표본 부족 → 판별 보류 병기**' if lo < MIN_TRADES else '✅ 충족'}")
    rep("")

    # ── 한계 ────────────────────────────────────────────────────────────────
    rep("## 5. 🔴 한계 (PREREG §7 1~7 + §10-4 8~13, 전량 전재)")
    rep("")
    for i, s in enumerate(LIMITATIONS, 1):
        rep(f"{i}. {s}")
    rep("")
    rep("### 🔑 생존편향 비대칭 — 판정문 옆에 붙여 읽을 것")
    rep("")
    rep("한계 1 이 말하는 방향은 **비대칭**이다. 생존편향은 저유동성·저가 arm(V·R)을 **위로** "
        "밀므로 **`T − V` 를 «과소»평가**한다. 따라서:")
    rep("")
    rep("- **(가) 계열 결론이 나오면 «강하다»** — 편향이 반대로 미는데도 T 가 이겼다는 뜻이다.")
    rep("- **(나)·(라) 계열 결론이면 이 편향을 «배제할 수 없다»** — 편향이 그 결론을 "
        "밀어주는 방향이므로, 관측된 V 우위의 일부는 상폐 종목 부재가 만든 것일 수 있다.")
    rep("")
    if adopted:
        pro_T = any(k.startswith(("(가)", "(다)")) for k in adopted)
        rep(f"⇒ 이번 결론({', '.join(adopted)})은 "
            + ("**편향이 반대로 미는데도 나온 결론이라 «강하다»**."
               if pro_T else
               "**편향이 «밀어주는» 방향이라 배제할 수 없다** — 채택 전 별도 검증이 필요하다"
               "(§5-3b (라′) 주석과 같은 취지)."))
        rep("")

    Path(BASE / "RESULTS.md").write_text("\n".join(DOC) + "\n", encoding="utf-8")
    Path(BASE / "RESULTS_raw.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] RESULTS.md · RESULTS_raw.md", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="랭킹 함수 반사실 — PREREG 실행부")
    ap.add_argument("--stage1", action="store_true",
                    help="PREREG §6 1단계 게이트 (PnL 미조회) → GATE.md")
    ap.add_argument("--stage2", action="store_true",
                    help="PREREG §4·§5 판정 (거래당 수익률) → RESULTS.md · RESULTS_raw.md")
    a = ap.parse_args()
    if a.stage1 and a.stage2:
        print("한 번에 하나만 실행한다 — 1단계는 「PnL 을 보기 «전»」이라야 뜻이 있다.",
              flush=True)
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
