# -*- coding: utf-8 -*-
"""ma5 «청산» 축 — 사전등록 `PREREG.md`(동결 + §11 개정) 실행부.

가족 등록부 `../REGISTRY.md` 의 **E1 문서**. 기계는 `concept_axes/minervini/run.py` 를
그대로 승계한다(`HIST0` 분리 · `(code,date)` 캐시 · `verify_strategy_params()` ·
`db_fingerprint()` · `--stage1`/`--stage2` 2모드).

🔴 **§11 이 §6-3·§3-1 을 덮어쓴다.** 어긋나는 곳은 §11 이 우선한다:

- §11-3 — **룰 창은 무조건 130봉**이다(동결본 §3-1 의 60봉이 아니다).
  기준은 「EMA 초기값 잔존 가중치 ≤ 2%」이고 EMA65 에 대입하면 129봉 ⇒ 130.
- §11-1 — 동결본 §6-3 의 **「결측률」은 폐기된 측정량**이다. `ewm(adjust=False)` 는
  첫 봉부터 값을 내므로 결측률이 항상 0% 다. 대신 **초기값 잔존 가중치**를 인쇄한다.
- §11-5 — `R_exit` 의 단위는 **봉 수**다(일봉만 쓰므로 「거래일」과 같다).

**Arm 11종 (PREREG §2-1) — 청산 축 «하나»만 바꾼다. 진입은 전 arm 동일:**

    FIXED  X0   sl 0.03 / tp 0.15            (현행 라이브 · 기준선)
           X1   sl 0.05 / tp 0.10            (사장님 ①)
           X2   sl 0.06 / tp 0.12            (사장님 ①)
    LINE   L5·L10·L20·L60·LE13·LE65
           = `close < 선` OR `ret ≤ −10%`     (%손절·익절 «없음»)
    귀무   R_exit  진입 후 U{1..30}봉째 청산, 시드 0..19
    참조   R_sel   무작위 «종목» + X0 청산, 시드 0..19  (인쇄만)

🔴 **홀드아웃(§3-1)**: `md5(code) % 2 == 0` 인 **A반만** 쓴다. B반(==1)은 봉인이다.
    `build_pools()` 가 A반으로 하드 필터하므로 **arm 선택·백테스트 경로에 B반이 들어올
    길이 없다.** B반이 등장하는 유일한 곳은 §6-1 이 «명령한» 분할 균형 카운트뿐이고,
    그것은 `stage1()` 안에서 진입 쪽 «건수»만 세고 버린다(PnL 없음).

**모드 두 개.**

- `--stage1` — PREREG §6 게이트. **arm 별 PnL 을 계산하지 않는다.** `BookBacktester` 는
  모듈 최상단에서 import 하지 않는다. 산출물 → `GATE.md`.
  ⚠️ **단 하나의 예외**: §11-4 가 *「60봉/130봉에서 `X0` 의 거래 기록이 완전히 동일함을
  실측으로 인쇄하라」*고 «명령»하므로 그 검증 함수 안에서만 지역 import 한다.
  그 함수는 **동일성 여부와 체결 건수만** 반환하고 **수익률 값을 반환하지도 인쇄하지도
  않는다** — 2단계 결과를 미리 노출하지 않기 위해서다.
- `--stage2` — PREREG §4·§5 판정. **이 커밋에서는 실행하지 않는다**(구현만).
  산출물 → `RESULTS.md`(판정) · `RESULTS_raw.md`(원시 출력).

🔴 **두 모드는 «같은» 선택 집합을 쓴다** — `build_cache`→`build_pools`→`select_*` 경로가
하나라서 2단계 arm 선택은 1단계가 인쇄한 것과 정의상 동일하다.

🔑 척도·창은 `rank_score_counterfactual` §10-1·§10-5 승계: 창 `2024-03-13~2026-05-31`,
가격은 `HIST0=2021-01-01` 부터, `volume × adj_factor` 는 **로더에서 1회**.

라이브 코드는 «읽기»만 한다(스크리너 어댑터 import). DB 는 SELECT 만.
"""
from __future__ import annotations

import argparse
import hashlib
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

from strategies.base import Signal, SignalType                                      # noqa: E402
from strategies.book_pullback_ma5.screener import (                                 # noqa: E402
    BookPullbackMa5ScreenerAdapter,
)
# 🔴 `BookBacktester` 는 여기서 import 하지 않는다 — 1단계가 「arm PnL 계산 경로가 아예
#    없다」를 구조로 보증하기 위해서다. 2단계 함수(`stage2`)와 §11-4 불변 검증 함수
#    (`invariance_check_x0`) 안에서만 지역 import 한다.

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
           dbname="kis_template")

# 신형 코드는 «중간»이 영문일 수 있다(`0001A0`). 의사티커는 첫 글자가 숫자가 아니라
# 이 술어에 이미 안 걸리지만 명시적으로도 배제한다.
STOCK_ONLY = ("stock_code ~ '^[0-9][0-9A-Z]{5}$' "
              "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')")

W0, W1 = "2024-03-13", "2026-05-31"   # PREREG §3 (rank_score §10-1 승계)
HIST0 = "2021-01-01"                   # 워밍업 — 룰 창을 창 «이전» 히스토리로 채운다

# 🔴🔴 PREREG §11-3 — 룰 창은 **무조건 130봉**. 동결본 §3-1 의 60봉을 덮어쓴다.
#      기준(동결) = 「EMA 초기값 잔존 가중치 ≤ 2%」. EMA65(α=2/66)에 대입하면
#      n ≥ 1 + ln(0.02)/ln(1−α) = 129.1 ⇒ 130.
RULE_WINDOW = 130
# 동결본 §3-1 의 60봉. **§11-4 불변 확인에만** 쓴다 — 산출에는 쓰지 않는다.
RULE_WINDOW_LEGACY = 60

SCORE_WINDOW = 5                       # §2 — score = volume.iloc[-5:].mean()
MAX_CANDIDATES = 10                    # §2 고정
N_SEEDS = 20                           # §2 — R_exit · R_sel 시드 0..19
MAX_HOLD = 30                          # §2 — 전 arm 공통
DISASTER_STOP = 0.10                   # §2-1 마지노선 — LINE 계열에만
RANDOM_EXIT_MAX_BARS = 30              # §5-1 · §11-5 — U{1..30} «봉»

# 🔴 §3-1 홀드아웃. A반(==0)만 쓴다. B반(==1)은 §10 프로토콜 밖에서 열지 않는다.
HALF_A = 0

# 🔴 PREREG §5 동결. **결과를 보고 바꾸지 않는다**(§8-1). 단위 = %p.
EPS_ECON = 0.5
ALPHA = 0.05                           # §5-5 Holm (주 검정 1개)

# §6-1 — A반 트리거가 전체의 이 구간 밖이면 「분할 불균형」 병기.
A_FRAC_LO, A_FRAC_HI = 0.40, 0.60
# §6-2 — 연도 쏠림은 원시·정규화 «양쪽» 모두 이 값 이하일 때만 ✅.
YEAR_SKEW_MAX = 50.0
# §6-4 — 2단계 사전 병기 조건 (여기서 미리 동결한다)
DISASTER_FIRE_FLAG = 33.0              # LINE arm 청산 중 마지노선 비중 > 33%
DISCARD_RATIO_FLAG = 2.0               # arm 간 폐기율 2배 이상
WORST_Q1_FLAG = -20.0                  # LINE arm 1% 분위 < −20%

# 지시서 기대 청산 파라미터 (config.yaml 이 정본이고 아래는 대조값)
EXP_SL, EXP_TP, EXP_MH, EXP_TRAIL = 0.03, 0.15, 30, 5

# ── Arm 정의 (PREREG §2-1 표 그대로) ────────────────────────────────────────
FIXED_ARMS = {                          # arm -> (stop_loss_pct, take_profit_pct)
    "X0": (0.03, 0.15),
    "X1": (0.05, 0.10),
    "X2": (0.06, 0.12),
}
LINE_ARMS = {                           # arm -> `BookBacktester.exit_line` 이름
    "L5": "SMA5", "L10": "SMA10", "L20": "SMA20",
    "L60": "SMA60", "LE13": "EMA13", "LE65": "EMA65",
}
FIXED_ORDER = ["X0", "X1", "X2"]
LINE_ORDER = ["L5", "L10", "L20", "L60", "LE13", "LE65"]
EXP_ARMS = FIXED_ORDER + LINE_ORDER      # 실험 9개

ARM_DESC = {
    "X0": "sl −3% / tp +15% (현행 라이브 · 기준선)",
    "X1": "sl −5% / tp +10% (사장님 ①)",
    "X2": "sl −6% / tp +12% (사장님 ①)",
    "L5": "close < SMA5 OR ret ≤ −10%",
    "L10": "close < SMA10 OR ret ≤ −10%",
    "L20": "close < SMA20 OR ret ≤ −10%",
    "L60": "close < SMA60 OR ret ≤ −10%",
    "LE13": "close < EMA13 OR ret ≤ −10%",
    "LE65": "close < EMA65 OR ret ≤ −10%",
}

# PREREG §7(1~15) 한계 — **결과 문서에 그대로 전재한다**(축약 없음).
LIMITATIONS = [
    "🔴🔴 **백테스터가 라이브의 장중 whipsaw 를 재현하지 못한다.** 확정 일봉 종가로 판정하고 "
    "다음 날 시가에 체결하므로, 라이브에서 실측된 *「2분 보유 · 1원 차이 청산」*(MA20 이탈 7건 "
    "**전부** 60분 미만)이 **원리상 나올 수 없다.** ⇒ ***LINE 계열이 실제보다 «좋게» 나온다.*** "
    "결론이 (가)여도 **라이브 반영 전에 별도 확인이 필요하다.**",
    "🔴 **분봉 트랙 판정이 FIXED 대안에 «불리»하다** — *「손절선에 닿은 건 진짜 하락의 시작이었다」* "
    "(되돌림 중앙 −0.61%). X1·X2 의 넓은 손절(−5 / −6%)은 그 하락을 더 오래 안고 간다. "
    "⚠️ 단 그 분석은 **익절 쪽 효과를 재지 않았다.**",
    "🔴 **현행 X0 는 이미 한 번 데이터에 맞춰진 값이다**(`config.yaml` 자기 진술 "
    "*「백테스트 검증값 1:1 반영」*). ⇒ **X0 에게 유리한 편향이 있다** — 대안이 X0 를 이기면 강하다.",
    "🔴 **`trail_ma 5` 가 X0 에서도 빠져 있다.** 라이브 X0 는 청산이 «넷»(sl/tp/max_hold/trail)인데 "
    "이 문서의 X0 는 셋이다. ⇒ ***이 문서의 X0 는 「라이브」가 아니라 「라이브에서 트레일링을 뺀 것」*** "
    "이다. L5 가 그 트레일링을 «손실 중에도» 켠 버전에 해당하므로 **`L5 − X0` 가 그 차이를 포함**한다.",
    "🔴 **EMA65 워밍업** — §11 개정으로 룰 창을 **130봉**으로 올렸다. 60봉에서 EMA65 는 "
    "첫 종가가 **16.3%** 를 차지했고 130봉에서는 **1.89%** 다. 결측이 아니라 «오염»이었다(§11-1·§11-2).",
    "🔴 **「같은 거래를 다르게 판 것」은 근사다.** 보유기간이 arm 마다 달라지면 「이미 보유 중」으로 "
    "막히는 후속 진입이 갈린다(종목당 단일 포지션). §6-4 폐기율 조건이 그 규모를 잡는다.",
    "🔴 **생존편향** — 상폐 종목이 사실상 없다(0.5%). 편향은 **약한 종목을 위로** 민다 ⇒ "
    "**손절이 늦은 arm(LINE·X1·X2)을 «과대»평가**한다. ⇒ ***(다) 결론이면 강하고, "
    "(가) 결론이면 이 편향을 배제할 수 없다.***",
    "🔴 **`score` 는 이미 「정보가 아님」으로 판정된 함수다**(`d751e21`). 이 문서의 수치는 "
    "「정보 없는 랭킹 위에서의 값」이다. 전 arm 공통이라 arm 비교엔 무해하다.",
    "🔴 **`market_cap` PIT 성격 미검정** — 전 arm 동일하게 걸리므로 arm 비교엔 무해.",
    "⚠️ **단일 국면 2.2년**(2024-03~2026-05). 일반화 금지.",
    "⚠️ **포트폴리오가 아니다**(종목당 단일 포지션 순차). `max_positions=5`·자금 배분 미재현.",
    "⚠️ **백테스트 유니버스 ≠ 라이브**(라이브 매수의 97%가 미검증). **라이브 기대치로 인용 금지.**",
    "⚠️ **실행 효과 미반영** — 슬리피지 외 호가·09:00~09:15 매수 타이밍.",
    "⚠️ **불가능봉 가드 미적용**(승계 원본과 동일).",
    "⚠️ **A반 표본이 절반**이다(§3-1). 검정력이 그만큼 준다.",
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
# 0. 설정 대조 — config.yaml 이 정본
# ────────────────────────────────────────────────────────────────────────────
def verify_strategy_params() -> tuple[list[str], dict]:
    """`config.yaml` 청산 파라미터와 스크리너 `base_filter` 임계를 읽어 대조 표를 만든다."""
    y = yaml.safe_load(
        (ROOT / "strategies" / "book_pullback_ma5" / "config.yaml").read_text(encoding="utf-8"))
    rm = (y or {}).get("risk_management", {}) or {}
    pr = (y or {}).get("parameters", {}) or {}
    sl, tp, mh = rm.get("stop_loss_pct"), rm.get("take_profit_pct"), rm.get("max_hold_days")
    trail = rm.get("trail_ma")
    min_bars = int(pr.get("min_daily_bars", 25))
    p = BookPullbackMa5ScreenerAdapter().default_params()
    ok = (sl == EXP_SL and tp == EXP_TP and mh == EXP_MH)
    rows = [
        "| 항목 | 읽은 값 | 기대값 | 일치 |",
        "|---|---|---|---|",
        f"| 청산 sl/tp/max_hold (`config.yaml`) | {sl} / {tp} / {mh} | "
        f"{EXP_SL} / {EXP_TP} / {EXP_MH} | "
        f"{'✅' if ok else '🔴 **불일치 — config 를 정본으로 씀**'} |",
        f"| `trail_ma` (`config.yaml`) | {trail} | {EXP_TRAIL} | "
        f"{'✅ (🔴 단 X0 에 «반영하지 않는다» — PREREG §7-4)' if trail == EXP_TRAIL else '🔴'} |",
        f"| `max_market_cap` (screener) | {p['max_market_cap']:,} | 3,000,000,000,000 | "
        f"{'✅' if p['max_market_cap'] == 3_000_000_000_000 else '🔴'} |",
        f"| `min_trading_value` (screener) | {p['min_trading_value']:,} | 1,000,000,000 | "
        f"{'✅' if p['min_trading_value'] == 1_000_000_000 else '🔴'} |",
        f"| `max_candidates` | {p['max_candidates']} | {MAX_CANDIDATES} | "
        f"{'✅' if p['max_candidates'] == MAX_CANDIDATES else '🔴'} |",
        f"| `min_daily_bars` (룰 최소봉 가드) | {min_bars} | 25 | "
        f"{'✅' if min_bars == 25 else '🔴'} |",
        f"| 룰 창 (§11-3 개정) | {RULE_WINDOW}봉 | 130봉 | "
        f"{'✅' if RULE_WINDOW == 130 else '🔴'} |",
    ]
    return rows, dict(sl=sl, tp=tp, mh=mh, trail=trail, min_bars=min_bars, **p)


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

    🔑 개정 창(`W0`)보다 이르게 읽는 이유는 워밍업이다 — 룰 창 130봉과 청산 기준선의
    EMA 경로를 창 «이전» 히스토리로 채운다(§11-2·§11-3).
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
                 mcap_missing=int((u["market_cap"].isna() | (u["market_cap"] <= 0)).sum()),
                 days_all=int(u["date"].nunique()))
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
# 2. 🔴 홀드아웃 분할 (PREREG §3-1) — 결과를 보기 «전»에 고정된 결정적 분할
# ────────────────────────────────────────────────────────────────────────────
def half_of(code: str) -> int:
    """`md5(code) % 2`. **0 = A반(탐색·판정) · 1 = B반(봉인).**

    종목으로 가르는 이유는 두 반이 «같은 국면»을 겪어야 *「그땐 장이 달랐다」* 는 변명이
    안 남기 때문이다. 코드 정렬 홀짝은 상장 순서와 상관될 수 있어 md5 를 쓴다.
    """
    return int(hashlib.md5(code.encode("utf-8")).hexdigest(), 16) % 2


# ────────────────────────────────────────────────────────────────────────────
# 3. 룰 평가 캐시 — 전 arm 공유 (진입은 전 arm 동일하므로 «한 번»만 만든다)
# ────────────────────────────────────────────────────────────────────────────
def build_cache(px: pd.DataFrame, elig: dict, screener, window: int,
                warmup: int) -> tuple[dict, dict]:
    """`{code: {date: score}}` — `base_filter` 통과 ∧ `rule_ma5_pullback` 발화한 (code,date).

    🔑 **라이브 스크리너 어댑터의 `match()` 를 그대로 호출한다** — 그 안에서
    `rule_ma5_pullback().evaluate()` 와 `score = df["volume"].iloc[-5:].mean()` 이
    같이 일어나므로 §2 의 「진입 룰 현행 고정 · score 현행 고정」이 코드 한 줄로 보장된다.

    🔴 `window` 는 §11-3 개정에 따라 **130봉**이다. `rule_ma5_pullback` 은 마지막 22봉,
    `score` 는 마지막 5봉만 보므로 이 값에 **불변**이다(§11-3 표) — 그 불변성은
    `invariance_check_x0()` 가 60봉 캐시와 대조해 실측한다.
    """
    params = screener.default_params()
    cache: dict = defaultdict(dict)
    n_eval = n_fire = 0
    done = 0
    total = px["stock_code"].nunique()
    t0 = time.perf_counter()
    for code, g in px.groupby("stock_code", sort=False):
        done += 1
        if done % 400 == 0:
            print(f"      ...{done}/{total} 종목 · 평가 {n_eval:,} · 발화 {n_fire:,} · "
                  f"{time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        n = len(g)
        for i in range(warmup, n):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            n_eval += 1
            v = screener.match(g.iloc[max(0, i + 1 - window):i + 1], params)
            if v is None:
                continue
            n_fire += 1
            cache[code][d] = float(v[0])
    return dict(cache), dict(n_eval=n_eval, n_fire=n_fire,
                             secs=time.perf_counter() - t0, window=window)


def build_pools(cache: dict, elig: dict, half: int = HALF_A) -> tuple[dict, dict]:
    """`(진입 풀, base 풀)` — **`half` 반으로 하드 필터한다.**

    🔴 기본값이 `HALF_A` 이고 2단계는 이 함수만 쓴다 ⇒ **arm 선택·백테스트 경로에
    B반이 들어올 길이 구조적으로 없다**(§3-1 · §8-7).

    - 진입 풀 `{date: [(code, score)]}` — `base_filter` ∧ 룰 발화. FIXED·LINE·`R_exit` 공용.
    - base 풀 `{date: [code]}` — `base_filter` 통과 전체. **`R_sel`(참조 arm) 전용**이고
      진입 룰 조건이 «없다» — 「종목 선택 자체」의 참조값이기 때문이다(§5-1).
    """
    entry: dict = defaultdict(list)
    for code, dd in cache.items():
        if half_of(code) != half:
            continue
        for d, score in dd.items():
            if code in elig.get(d, ()):
                entry[d].append((code, score))
    base = {}
    for d, cs in elig.items():
        v = sorted(c for c in cs if half_of(c) == half)
        if v:
            base[d] = v
    return {d: sorted(v) for d, v in entry.items() if v}, base


def select_top(pool: dict) -> dict:
    """현행 `score` 내림차순 top-`MAX_CANDIDATES`. 동점은 코드 오름차순 안정정렬."""
    return {d: [c for c, _ in sorted(v, key=lambda t: t[1], reverse=True)[:MAX_CANDIDATES]]
            for d, v in pool.items()}


def select_random_codes(base: dict, seed: int) -> dict:
    """`R_sel` — 그날 `base_filter` 통과 집합에서 무작위 `MAX_CANDIDATES` 종목(비복원)."""
    rng = np.random.RandomState(seed)
    out = {}
    for d in sorted(base):
        codes = base[d]
        k = min(MAX_CANDIDATES, len(codes))
        out[d] = list(rng.choice(codes, size=k, replace=False)) if k else []
    return out


# ────────────────────────────────────────────────────────────────────────────
# 4. Arm → `BookBacktester` 파라미터 (PREREG §2-1 · §2-3)
# ────────────────────────────────────────────────────────────────────────────
def arm_kwargs(arm: str) -> dict:
    """arm 이름 → `BookBacktester` 생성 인자. **§2-3 우선순위 축약이 여기서 결정된다.**

    구현의 단일 사슬은
        disaster → random_exit → stop_loss → take_profit → line_break → max_hold → eod
    인데, 계열별 파라미터를 넣으면 §2-3 이 적은 두 줄로 «축약»된다:

        FIXED : (disaster None · random None · line None) ⇒  손절 → 익절 → max_hold
        LINE  : (random None · sl None · tp None)         ⇒  마지노선 → 선 이탈 → max_hold

    이 대응은 `tests/strategies/books/test_book_backtester_exit_rules.py` 의
    `test_prereg_fixed_arm_reduces_to_stop_take_maxhold` ·
    `test_prereg_line_arm_reduces_to_disaster_line_maxhold` 가 arm 9개 전부에 대해 못박는다.
    """
    base = dict(warmup_bars=0, max_hold_bars=MAX_HOLD, eod_liquidate=False)
    if arm in FIXED_ARMS:
        sl, tp = FIXED_ARMS[arm]
        return dict(base, stop_loss_pct=sl, take_profit_pct=tp,
                    exit_line=None, disaster_stop_pct=None, random_exit_seed=None)
    if arm in LINE_ARMS:
        return dict(base, stop_loss_pct=None, take_profit_pct=None,
                    exit_line=LINE_ARMS[arm], disaster_stop_pct=DISASTER_STOP,
                    random_exit_seed=None)
    if arm.startswith("R_exit#"):
        seed = int(arm.split("#", 1)[1])
        # 🔴 `random_exit_max_bars ≤ 0` 이면 `BookBacktester` 가 첫 진입에서 죽는다.
        #    백테스터에도 생성자 가드를 넣었지만 «넘기기 전에» 여기서도 막는다.
        if RANDOM_EXIT_MAX_BARS < 1:
            raise ValueError(f"RANDOM_EXIT_MAX_BARS must be >= 1, got {RANDOM_EXIT_MAX_BARS}")
        return dict(base, stop_loss_pct=None, take_profit_pct=None,
                    exit_line=None, disaster_stop_pct=None,
                    random_exit_seed=seed, random_exit_max_bars=RANDOM_EXIT_MAX_BARS)
    if arm.startswith("R_sel#"):
        sl, tp = FIXED_ARMS["X0"]        # §2-1 — 참조 arm 은 X0 청산 그대로
        return dict(base, stop_loss_pct=sl, take_profit_pct=tp,
                    exit_line=None, disaster_stop_pct=None, random_exit_seed=None)
    raise ValueError(f"등록되지 않은 arm: {arm!r} — PREREG §2-1 표 밖이다(§8-2·§8-3)")


def active_chain(arm: str) -> str:
    """그 arm 에서 «실제로 발동 가능한» 청산 사슬을 문자열로 만든다(§2-3 대조용)."""
    kw = arm_kwargs(arm)
    links = []
    if kw.get("disaster_stop_pct") is not None:
        links.append("마지노선")
    if kw.get("random_exit_seed") is not None:
        links.append("무작위청산")
    if kw.get("stop_loss_pct") is not None:
        links.append("손절")
    if kw.get("take_profit_pct") is not None:
        links.append("익절")
    if kw.get("exit_line") is not None:
        links.append(f"선이탈({kw['exit_line']})")
    links.append(f"max_hold({kw['max_hold_bars']})")
    links.append("forced_close(창 끝)")
    return " → ".join(links)


# ────────────────────────────────────────────────────────────────────────────
# 5. §11-2 초기값 잔존 가중치 — 「결측률」이 아니라 이것을 잰다
# ────────────────────────────────────────────────────────────────────────────
def ema_alpha(span: int) -> float:
    return 2.0 / (span + 1.0)


def ema_initial_weight(span: int, n_bars: int) -> float:
    """`adjust=False` EMA 가 `n` 봉째에 «첫 종가»에 주는 가중치 = `(1−α)^(n−1)`."""
    return (1.0 - ema_alpha(span)) ** (n_bars - 1)


# ────────────────────────────────────────────────────────────────────────────
# 6. 백테스트 프레임 — 룰 창만큼의 «앞 히스토리»를 붙인다
# ────────────────────────────────────────────────────────────────────────────
def build_frames(px: pd.DataFrame, window: int) -> tuple[dict, dict]:
    """`{code: frame}`, `{code: {date: idx, "__last__": n-1}}`.

    🔑🔑 **프레임은 `W0` 에서 «자르지 않는다» — 앞에 `window−1` 봉을 붙인다.**
    `BookBacktester._exit_line_value()` 가 `df.iloc[: i+1]` 전체로 기준선을 계산하기
    때문이다. 앞 히스토리가 없으면 `W0` 근처 봉에서 EMA65 는 **첫 종가가 100%인 값**이
    되고, 그것이 §11 이 잡아낸 오염이다. `window−1` 봉을 붙이면 **평가되는 «모든» 봉에서
    초기값 잔존 가중치가 `(1−α)^(window−1)` 이하**로 보장된다(§11-2 기준 ≤2%).

    🔑 `warmup_bars=0` 은 이 구성과 짝을 이룬다 — 앞 히스토리 구간에서도 루프는 돌지만
    `ArmGated` 가 「그날 고른 종목」만 통과시키고 선택은 `W0` 이후에만 존재하므로
    진입이 일어날 수 없다.
    """
    frames, idxmap = {}, {}
    for code, g in px.groupby("stock_code", sort=False):
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        first = int(np.searchsorted(dates, W0, side="left"))
        if first >= len(g) - 1:
            continue
        start = max(0, first - (window - 1))
        g2 = g.iloc[start:].reset_index(drop=True)
        if len(g2) < 2:
            continue
        frames[code] = g2
        im = {d: i for i, d in enumerate(g2["date"].to_numpy())}
        im["__last__"] = len(g2) - 1
        idxmap[code] = im
    return frames, idxmap


# ────────────────────────────────────────────────────────────────────────────
# 7. arm 실행 — 🔴 `BookBacktester` 는 **호출자가 주입**한다(지역 import 유지)
# ────────────────────────────────────────────────────────────────────────────
class ArmGated:
    """arm 이 «그날 고른» 종목-일만 매수 신호로 바꾼다.

    🔑 진입 룰 판정은 1단계 캐시가 이미 끝냈고 arm 선택은 그 부분집합이므로 여기서는
    `(code, date)` 조회 하나뿐이다 — **룰을 다시 평가하지 않는다.** 이것이
    「arm 간 차이가 «청산» 하나로만 생긴다」를 보장하는 장치다(§1 · §2).
    """

    def __init__(self, allowed: dict):
        self.allowed = allowed          # {date_str: set(code)}

    def generate_signal(self, stock_code, df, timeframe="daily"):
        if stock_code in self.allowed.get(df["date"].iloc[-1], ()):
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=68)
        return None


def _count_signals(allowed: dict, idxmap: dict) -> int:
    """arm 이 제시한 (code,date) 중 «체결 가능»한 것의 수 (§6-4 폐기율의 분모).

    `BookBacktester` 는 보유 중이면 `generate_signal` 을 부르지도 않으므로 폐기 건수를
    백테스터 «안»에서 셀 수 없다 ⇒ 밖에서 제시 신호를 세고 실현 매수와 대조한다.
    """
    n = 0
    for d, cs in allowed.items():
        for c in cs:
            im = idxmap.get(c)
            if im is None:
                continue
            i = im.get(d)
            if i is not None and i <= im["__last__"] - 1:
                n += 1
    return n


def run_arm(sel: dict, frames: dict, idxmap: dict, arm: str, backtester_cls,
            trades_out: list = None) -> dict:
    """arm 하나를 백테스트해 «거래당» 분포와 «신호→실현» 전환을 낸다.

    `mean`·`med` 단위는 **%**. 🔑 `pnl_pct` 에는 슬리피지(편도 0.1%)가 체결가에 반영돼 있고
    **수수료 0.015%·거래세 0.18% 는 미반영**(= PREREG §4 의 gross, 승계 원본과 동일 정의).

    `trades_out` 이 주어지면 체결 원본을 그대로 담는다(§11-4 불변 확인 전용).
    """
    allowed = {d: set(v) for d, v in sel.items() if v}
    codes = set().union(*allowed.values()) if allowed else set()
    signals = _count_signals(allowed, idxmap)
    bt = backtester_cls(strategy=ArmGated(allowed), **arm_kwargs(arm))
    pnl, hold, reasons = [], [], []
    for c in sorted(codes):
        g = frames.get(c)
        if g is None or len(g) < 2:
            continue
        buy = None
        for t in bt.run_single(c, g).trades:
            if trades_out is not None:
                trades_out.append(t)
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
                    worst=float("nan"), q01=float("nan"), q05=float("nan"),
                    reasons=Counter())
    p = pd.Series(pnl)
    return dict(n=len(pnl), signals=signals,
                discard=(1 - len(pnl) / signals) * 100 if signals else float("nan"),
                mean=p.mean() * 100, med=p.median() * 100, win=(p > 0).mean() * 100,
                hold=float(pd.Series(hold).median()),
                worst=p.min() * 100, q01=p.quantile(0.01) * 100, q05=p.quantile(0.05) * 100,
                reasons=Counter(reasons))


# ────────────────────────────────────────────────────────────────────────────
# 8. 🔴🔴 §11-4 불변 확인 — 60봉 vs 130봉에서 X0 의 거래 기록이 같은가
# ────────────────────────────────────────────────────────────────────────────
def _trade_signature(trades: list) -> list:
    """프레임 «길이»에 의존하지 않는 체결 서명.

    🔴 `idx` 는 프레임 시작점이 달라지면 통째로 밀리므로 쓰지 않는다 — 대신 체결 봉의
    `datetime` 을 쓴다. 그 외 필드(사유·수량·체결가·진입가·손익)는 전부 그대로 비교한다.
    """
    return [(t["stock_code"], t["side"], str(t["datetime"]), t["reason"], int(t["qty"]),
             round(float(t["price"]), 9), round(float(t["entry_price"]), 9),
             round(float(t["pnl_pct"]), 12)) for t in trades]


def invariance_check_x0(px: pd.DataFrame, elig: dict, screener, warmup: int,
                        sel130: dict, cache130: dict) -> dict:
    """§11-4 — 룰 창 60봉과 130봉에서 `X0` 의 거래 기록이 «완전히 동일»한가.

    🔴 **이 함수만이 1단계에서 `BookBacktester` 를 만진다.** 사전등록 §11-4 가 그 실측을
    «명령»하기 때문이다. 반환값에는 **동일성 여부·체결 건수·소요 시간만** 들어가고
    **수익률은 들어가지 않는다** — 2단계 결과를 미리 노출하지 않기 위해서다.

    두 층을 각각 확인한다:
      ① **선택 불변** — 60봉 캐시로 만든 A반 선택이 130봉 것과 «같은가»
         (= `rule_ma5_pullback` 22봉 · `score` 5봉 이 창에 불변인가, §11-3 표 1·2행)
      ② **체결 불변** — 같은 선택을 60봉/130봉 프레임에서 X0 로 돌렸을 때 체결이 같은가
         (= `X0` 는 창과 무관하다, §11-3 마지막 줄)
    """
    from backtest.book_backtester import BookBacktester  # noqa: PLC0415 — §11-4 전용

    print(f"[§11-4] 룰 창 {RULE_WINDOW_LEGACY}봉 캐시 재구축", flush=True)
    cache60, cstats60 = build_cache(px, elig, screener, RULE_WINDOW_LEGACY, warmup)
    pool60, _base60 = build_pools(cache60, elig)
    sel60 = select_top(pool60)

    same_sel = (
        {d: list(v) for d, v in sel60.items() if v} ==
        {d: list(v) for d, v in sel130.items() if v}
    )
    fire_same = (cstats60["n_fire"] ==
                 sum(len(v) for v in cache130.values()))

    out = dict(n_fire_60=cstats60["n_fire"],
               n_fire_130=sum(len(v) for v in cache130.values()),
               fire_same=fire_same, sel_same=same_sel,
               sel_days_60=len([d for d, v in sel60.items() if v]),
               sel_days_130=len([d for d, v in sel130.items() if v]))

    print("[§11-4] X0 체결 대조 (60봉 프레임 / 130봉 프레임)", flush=True)
    res = {}
    for tag, win in (("60", RULE_WINDOW_LEGACY), ("130", RULE_WINDOW)):
        frames, idxmap = build_frames(px, win)
        tr: list = []
        t0 = time.perf_counter()
        m = run_arm(sel130, frames, idxmap, "X0", BookBacktester, trades_out=tr)
        res[tag] = dict(secs=time.perf_counter() - t0, sig=_trade_signature(tr),
                        n_sell=m["n"], signals=m["signals"])
        print(f"      창 {tag}봉 · 체결(매도) {m['n']:,} · {res[tag]['secs']:.0f}s", flush=True)

    same_tr = res["60"]["sig"] == res["130"]["sig"]
    mism = []
    if not same_tr:
        a, b = res["60"]["sig"], res["130"]["sig"]
        for i in range(min(len(a), len(b))):
            if a[i] != b[i]:
                mism.append((i, a[i], b[i]))
                if len(mism) >= 5:
                    break
    out.update(trades_same=same_tr, n_sell_60=res["60"]["n_sell"],
               n_sell_130=res["130"]["n_sell"], n_rows_60=len(res["60"]["sig"]),
               n_rows_130=len(res["130"]["sig"]), signals=res["130"]["signals"],
               secs_60=res["60"]["secs"], secs_130=res["130"]["secs"], mismatch=mism)
    return out


# ────────────────────────────────────────────────────────────────────────────
# 9. 게이트 helper
# ────────────────────────────────────────────────────────────────────────────
def year_skew(items: list, pool_days: list, label: str) -> bool:
    """연도 쏠림 — 원시 비중 + **거래일 정규화 비중**. 양쪽 모두 ≤50% 일 때만 ✅ (§6-2)."""
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
    ny, ntop = ((max(norm, key=lambda k: norm[k]), max(norm.values()))
                if norm else ("—", float("nan")))
    say("")
    ok = raw_top <= YEAR_SKEW_MAX and (ntop != ntop or ntop <= YEAR_SKEW_MAX)
    say(f"- 원시 최대 = **{ry} {raw_top:.1f}%** · 정규화 최대 = **{ny} {ntop:.1f}%** → "
        + ("✅ **양쪽 모두 ≤50% — 통과**" if ok else
           "🔴 **한쪽이라도 >50% ⇒ 「국면 특이 → 판별 보류」 병기**"))
    return ok


def half_counts(cache: dict, elig: dict, half: int) -> dict:
    """§6-1 — 그 반의 진입 트리거 수 · 선택 종목-일 수 · 고유 종목 수.

    🔴 **B반에 대해 이 함수를 부르는 것은 §6-1 이 «명령»한 분할 균형 카운트다.**
    진입 쪽 «건수»만 세고 PnL 은 계산하지 않는다. 반환값은 `stage1()` 의 표에만 쓰이고
    arm 선택·백테스트 어느 경로에도 들어가지 않는다(§3-1 · §8-7).
    """
    pool, base = build_pools(cache, elig, half=half)
    sel = select_top(pool)
    return dict(trig=sum(len(v) for v in pool.values()),
                trig_codes=len({c for v in pool.values() for c, _ in v}),
                days=len(pool),
                sel=sum(len(v) for v in sel.values()),
                sel_codes=len({c for v in sel.values() for c in v}),
                base_days=len(base),
                base_codes=len({c for v in base.values() for c in v}))


# ────────────────────────────────────────────────────────────────────────────
# 10. 2단계 판정 helper (PREREG §5)
# ────────────────────────────────────────────────────────────────────────────
def selection_profile(sel: dict, uni: dict, frames: dict, idxmap: dict) -> dict:
    """§4 보조 — 선택 종목-일의 **중앙 주가 / 시총 / 거래대금**.

    🔑 FIXED·LINE·`R_exit` 은 «같은 선택»을 쓰므로 이 값이 하나뿐이다. `R_sel` 만 다르다.
    """
    cl, mc, tv = [], [], []
    for d, codes in sel.items():
        m = uni.get(d, {})
        for c in codes:
            im = idxmap.get(c)
            if im is not None and d in im:
                cl.append(float(frames[c]["close"].iat[im[d]]))
            if c in m:
                mc.append(m[c][0])
                tv.append(m[c][1])

    def _med(v):
        return float(np.median(v)) if v else float("nan")

    return dict(n=len(cl), close=_med(cl), mcap=_med(mc), tv=_med(tv))


def perm_p(arm_mean: float, r_means: list) -> float:
    """단측 순열 p — `(1 + #{R_i ≥ A}) / (1 + n_seeds)`. N1 성립 시 최솟값 `1/21`."""
    return (1 + sum(1 for x in r_means if x >= arm_mean)) / (1 + len(r_means))


def verdict_5_2(means: dict, n1: dict) -> tuple[str, dict]:
    """PREREG §5-2 주 판정 — 위에서부터 «처음 성립하는 것»을 채택. 라벨을 새로 짓지 않는다."""
    line = [means[a] for a in LINE_ORDER]
    fixed = [means[a] for a in FIXED_ORDER]
    d_line = min(line) - max(fixed)
    d_fixed = min(fixed) - max(line)
    all_line_n1 = all(n1[a] for a in LINE_ORDER)
    all_fixed_n1 = all(n1[a] for a in FIXED_ORDER)
    det = dict(min_line=min(line), max_line=max(line), min_fixed=min(fixed),
               max_fixed=max(fixed), d_line=d_line, d_fixed=d_fixed,
               all_line_n1=all_line_n1, all_fixed_n1=all_fixed_n1)
    if d_line >= EPS_ECON and all_line_n1:
        return "🟢 **(가) 기준선 «방식»이 낫다** — 가장 나쁜 선조차 가장 좋은 고정%보다 낫다", det
    if d_fixed >= EPS_ECON and all_fixed_n1:
        return "**(다) 고정 % «방식»이 낫다**", det
    return ("🔴 **(나) 「방식」이 아니라 «설정»이 결과를 지배한다** — 두 계열이 겹친다", det)


def label_5_4(x0: float, x1: float, x2: float) -> str:
    """PREREG §5-4 — 사장님 ① 대안의 개별 대조. **인쇄만 · 판정 언어 금지.**"""
    e = EPS_ECON
    if (x1 - x0 >= e) and (x2 - x0 >= e):
        return "「손익비를 2:1 로 낮추는 쪽이 있어 보인다 — **다음 사전등록의 표적**」"
    if (x0 - x1 >= e) and (x0 - x2 >= e):
        return "「현행 1:5 쪽이 있어 보인다 — **표적**」"
    return "「일관되지 않음」"


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
# 11. stage1 — PREREG §6 게이트 (arm PnL 미산출)
# ────────────────────────────────────────────────────────────────────────────
def stage1() -> int:
    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    say("# ma5 청산 축 — 1단계 게이트 (PREREG §6 · §11, arm PnL 미산출)")
    say("")
    say(f"사전등록 [`PREREG.md`](PREREG.md)(동결 + §11 개정) · 가족 등록부 "
        f"[`../REGISTRY.md`](../REGISTRY.md) **E1 문서** · 실행 커밋 **`{sha}`** · "
        f"창 **{W0} ~ {W1}**.")
    say("")
    say("🔴 이 문서는 PREREG **§6(1단계 게이트) + §11(개정) 확인까지만** 다룬다. "
        "**해석·「좋다/나쁘다」 판단은 없다** — 순수 산출이다. 결과 계산(§4·§5)은 2단계다.")
    say("")
    say("🔑 **arm 별 수익률을 계산하지 않는다.** `BookBacktester` 는 모듈 최상단에서 "
        "import 하지 않으며, 아래 §5(§11-4 불변 확인) **한 곳에서만** 지역 import 된다 — "
        "사전등록 §11-4 가 *「60봉/130봉에서 X0 의 거래 기록이 동일함을 실측하라」*고 "
        "명령하기 때문이다. 🔴 **그 절은 동일성 여부와 체결 건수만 인쇄하고 "
        "수익률 값은 인쇄하지 않는다.**")
    say("")

    rows, params = verify_strategy_params()
    say("## 0. 설정 대조 (하드코딩 아님 — `config.yaml`·스크리너에서 읽음)")
    say("")
    for r in rows:
        say(r)
    say("")
    say("🔴 `trail_ma 5` 는 **이 문서의 X0 에 넣지 않는다**(§7-4) — 라이브 X0 는 청산이 넷인데 "
        "이 문서의 X0 는 셋이다. ***이 문서의 X0 는 「라이브」가 아니라 「라이브에서 트레일링을 "
        "뺀 것」이다.*** `L5` 가 그 트레일링을 «손실 중에도» 켠 버전에 해당한다.")
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
    conn.close()
    dates = sorted(uni)
    scr = BookPullbackMa5ScreenerAdapter()
    elig = eligible_by_date(uni, scr)
    pool_days_all = [d for d in dates if elig.get(d)]
    print(f"[load] 일봉 {len(px):,}행 · {time.perf_counter()-t0:.0f}s", flush=True)

    say("## 1. 표본 · 창 · 워밍업")
    say("")
    hist_rows = int((px["date"] < W0).sum())
    esz = [len(elig[d]) for d in pool_days_all]
    say(f"- 개정 창 거래일 **{len(dates):,}일** · `base_filter` 통과 종목이 있는 날 "
        f"**{len(pool_days_all):,}일** · 적격 풀 크기 중앙 **{int(np.median(esz)):,}** "
        f"(최소 {min(esz):,} · 최대 {max(esz):,})")
    say(f"- 적재 일봉 **{len(px):,}행** / **{px.stock_code.nunique():,}종목** "
        f"(`{HIST0}`~`{W1}`) · 그중 **창 이전 워밍업 {hist_rows:,}행**")
    say(f"- `market_cap` 결측(창 안) **{ustats['mcap_missing']:,}/{ustats['rows']:,}** = "
        f"**{ustats['mcap_missing']/ustats['rows']*100:.2f}%**")
    say("")
    n_need_top = 1 + np.log(0.02) / np.log(1 - ema_alpha(65))
    say(f"🔴🔴 **룰 창 = {RULE_WINDOW}봉** — 동결본 §3-1 의 **60봉이 아니다.** §11-3 이 "
        f"*「룰 창을 무조건 130봉으로 올린다(조건부 아님)」*로 덮어썼다. 기준(동결)은 "
        f"**「EMA 초기값 잔존 가중치 ≤ 2%」**이고 EMA65 에 대입하면 "
        f"`n ≥ 1 + ln(0.02)/ln(1−α) = {n_need_top:.1f}` ⇒ **{RULE_WINDOW}봉**이다. "
        f"🔑 130 은 동결본 §6-3 이 이미 적어둔 숫자이고, 바뀐 것은 「언제 올리나」뿐이다.")
    say("")
    say(f"⚠️ **동결본 §11-3 의 산술 표기 한 곳이 어긋난다(결론은 그대로).** 동결본은 "
        f"`= 1 + 127.1 = 129` 라 적었는데 `1 + 127.1 = {n_need_top:.1f}` 이다. "
        f"🟢 **채택 값 130 은 어느 쪽이든 기준을 만족하므로 창을 바꾸지 않았다** — "
        f"`{n_need_top:.1f} ≤ 129 ≤ 130`. 🔴 ***사전등록이 정본이므로 코드가 숫자를 고치지 "
        f"않고, 이 줄이 그 어긋남의 기록이다.***")
    say("")
    say(f"🔑 **프레임에도 같은 창을 붙였다.** 2단계 백테스트 프레임은 `{W0}` 에서 자르지 않고 "
        f"**앞에 {RULE_WINDOW-1}봉을 덧붙인다** — `BookBacktester._exit_line_value()` 가 "
        f"`df.iloc[: i+1]` «전체»로 기준선을 계산하기 때문이다. 앞 히스토리가 없으면 창 초입의 "
        f"EMA65 는 *「첫 종가가 100%인 값」*이 되고, 그것이 §11 이 잡아낸 오염이다. "
        f"이 구성에서 **평가되는 모든 봉의 초기값 잔존 가중치가 §5 표의 값 이하**로 보장된다.")
    say("")

    # ── 룰 캐시 (전 arm 공통) ────────────────────────────────────────────────
    print(f"[cache] 룰 평가 (창 {RULE_WINDOW}봉)", flush=True)
    cache, cstats = build_cache(px, elig, scr, RULE_WINDOW, params["min_bars"])
    pool_a, base_a = build_pools(cache, elig)
    sel_a = select_top(pool_a)
    say("## 2. 룰 평가 캐시 (전 arm 공유 · 1회)")
    say("")
    say(f"- 적격 (code,date) **{cstats['n_eval']:,}건** 평가 · 발화 **{cstats['n_fire']:,}건** · "
        f"{cstats['secs']:.0f}s")
    say(f"- 발화 고유 종목 **{len({c for c in cache}):,}**")
    say("")
    say("🔑 **진입은 전 arm 동일하다**(§1·§2) ⇒ 이 캐시 하나가 FIXED 3 · LINE 6 · `R_exit` 20 "
        "**전부의 선택**을 만든다. `R_sel`(참조)만 다른 풀(= `base_filter` 통과 전체)을 쓴다.")
    say("")

    # ── §6-1 트리거·선택·고유 종목 (A/B 각각) ────────────────────────────────
    say("## 3. §6-1 진입 트리거 수 · 선택 종목-일 수 · 고유 종목 수 — **A반 / B반**")
    say("")
    say("🔴 **아래 B반 칸은 §6-1 이 «명령»한 분할 균형 카운트다** — 진입 쪽 «건수»만 세고 "
        "PnL 은 계산하지 않는다. 이 숫자는 arm 선택·백테스트 어느 경로에도 들어가지 않으며, "
        "**§4~§6 의 모든 산출과 §5-2 판정은 A반에서만** 한다(§3-1).")
    say("")
    ca = half_counts(cache, elig, HALF_A)
    cb = half_counts(cache, elig, 1 - HALF_A)
    tot_trig = ca["trig"] + cb["trig"]
    say("| 항목 | **A반 (탐색·판정)** | B반 (봉인) | 합계 |")
    say("|---|---|---|---|")
    say(f"| 진입 트리거 (종목-일) | **{ca['trig']:,}** | {cb['trig']:,} | {tot_trig:,} |")
    say(f"| 트리거 고유 종목 | **{ca['trig_codes']:,}** | {cb['trig_codes']:,} | "
        f"{ca['trig_codes']+cb['trig_codes']:,} |")
    say(f"| 진입 풀이 비지 않은 날 | **{ca['days']:,}** | {cb['days']:,} | — |")
    say(f"| **선택 종목-일** (top {MAX_CANDIDATES}) | **{ca['sel']:,}** | {cb['sel']:,} | "
        f"{ca['sel']+cb['sel']:,} |")
    say(f"| **선택 고유 종목** | **{ca['sel_codes']:,}** | {cb['sel_codes']:,} | "
        f"{ca['sel_codes']+cb['sel_codes']:,} |")
    say(f"| `base_filter` 통과 고유 종목 | **{ca['base_codes']:,}** | {cb['base_codes']:,} | "
        f"{ca['base_codes']+cb['base_codes']:,} |")
    say("")
    a_frac = ca["trig"] / tot_trig if tot_trig else float("nan")
    balanced = A_FRAC_LO <= a_frac <= A_FRAC_HI
    say(f"- **A반 트리거 비중 = {a_frac*100:.1f}%** "
        + ("✅ **40~60% 안 — 분할 균형**" if balanced else
           "🔴 **40~60% 밖 ⇒ 「분할 불균형」 병기** — 판정문에 그대로 옮긴다"))
    say("")
    say("🔑 위 값들은 **전 arm 공통**이다 — 진입 룰·`score`·`max_candidates` 가 arm 간에 "
        "완전히 같기 때문이다(§2). arm 마다 달라지는 것은 «판 시점»뿐이다.")
    say("")

    # ── §6-2 연도 쏠림 ──────────────────────────────────────────────────────
    say("## 4. §6-2 연도별 쏠림 — 원시 + 거래일 정규화 (**양쪽 ≤50% 일 때만 ✅**)")
    say("")
    say("대상 = **A반 선택 종목-일**(전 arm 공통). 분모(대상일) = 그 해 A반 진입 풀이 "
        "비지 않은 거래일 수.")
    a_days = sorted(pool_a)
    sel_items = [(d, c) for d, v in sel_a.items() for c in v]
    ok_year = year_skew(sel_items, a_days, "A반 선택 종목-일")
    say("")
    trig_items = [(d, c) for d, v in pool_a.items() for c, _ in v]
    ok_year_trig = year_skew(trig_items, a_days, "A반 진입 트리거 (참고)")
    say("")

    # ── §11-2 초기값 잔존 가중치 ────────────────────────────────────────────
    say("## 5. §11-2 🔴 EMA 초기값 잔존 가중치 — 「결측률」이 아니다")
    say("")
    say("🔑🔑 동결본 §6-3 은 *「EMA65 결측률을 인쇄하고 5% 를 넘으면 창을 올린다」*고 적었다. "
        "**§11-1 이 그 측정량을 폐기했다** — `ewm(span=N, adjust=False)` 는 **첫 봉부터 값을 "
        "낸다**(`EMA₁ = close₁`)라 `NaN` 이 원리적으로 안 생기고 **결측률은 «항상 0%»** 다. "
        "***가드를 달아놓고 그 가드가 재는 양이 상수라면, 그건 가드가 아니라 장식이다.***")
    say("")
    say(f"올바른 측정량은 **초기값 잔존 가중치** `(1−α)^(n−1)`, `α = 2/(span+1)` 이다. "
        f"아래는 **실제 실행 창 길이 n = {RULE_WINDOW}봉**(§11-4 요구)으로 계산한 값이고, "
        f"동결본 §11-2 표의 60봉 값을 대조로 함께 싣는다.")
    say("")
    say("| 선 | span | α | 60봉(동결본 대조) | **실제 실행 창 "
        f"{RULE_WINDOW}봉** | ≤2% 기준 |")
    say("|---|---|---|---|---|---|")
    for name, span in (("EMA13", 13), ("EMA65", 65)):
        w60 = ema_initial_weight(span, RULE_WINDOW_LEGACY) * 100
        wnow = ema_initial_weight(span, RULE_WINDOW) * 100
        say(f"| **{name}** | {span} | {ema_alpha(span):.5f} | {w60:.3f}% | "
            f"**{wnow:.3f}%** | {'✅' if wnow <= 2.0 else '🔴 **초과**'} |")
    say("")
    n_need = 1 + np.log(0.02) / np.log(1 - ema_alpha(65))
    say(f"- 기준(동결) `초기값 잔존 ≤ 2%` 를 EMA65 에 대입: "
        f"`n ≥ 1 + ln(0.02)/ln(1−α)` = **{n_need:.1f}** ⇒ **{RULE_WINDOW}봉**. "
        f"실행 창이 그 값이므로 ✅.")
    say(f"- 🔑 프레임에 앞 히스토리 {RULE_WINDOW-1}봉을 붙였으므로 이 값은 **평가되는 첫 봉의 "
        f"상한**이고, 창 안쪽으로 들어갈수록 잔존은 더 줄어든다.")
    say("")
    say("🔴 **결측률은 인쇄하지 않는다** — §11-1 이 폐기한 측정량이기 때문이다. "
        "기계검사는 `tests/strategies/books/test_book_backtester_exit_rules.py::"
        "test_ema_has_no_warmup_nan_by_construction` 이 「EMA 는 NaN 워밍업이 없다」를, "
        "그 아래 대조 단언이 「같은 길이에서 SMA5 는 NaN 이다」를 못박는다.")
    say("")

    # ── §11-4 불변 확인 ─────────────────────────────────────────────────────
    say("## 6. §11-4 🔴🔴 불변 확인 — 60봉 / 130봉에서 `X0` 의 거래 기록이 «완전히 동일»한가")
    say("")
    say("🔴 **이 절은 「게이트 지표」가 아니라 「불변 검증」이다.** X0 를 실제로 돌려야 확인할 수 "
        "있으므로 PnL 이 «메모리에» 생기지만, **여기에는 동일/불일치 여부와 체결 건수만 적는다** "
        "— 수익률은 2단계 결과이고 1단계에서 미리 노출하면 안 된다.")
    say("")
    inv = invariance_check_x0(px, elig, scr, params["min_bars"], sel_a, cache)
    say("| 층 | 60봉 | 130봉 | 동일? |")
    say("|---|---|---|---|")
    say(f"| 룰 발화 (종목-일, 전체) | {inv['n_fire_60']:,} | {inv['n_fire_130']:,} | "
        f"{'✅' if inv['fire_same'] else '🔴 **다르다**'} |")
    say(f"| A반 선택 (날짜별 종목 리스트) | 선택일 {inv['sel_days_60']:,} | "
        f"선택일 {inv['sel_days_130']:,} | {'✅' if inv['sel_same'] else '🔴 **다르다**'} |")
    say(f"| `X0` 체결 기록 (매수+매도 행) | {inv['n_rows_60']:,}행 | {inv['n_rows_130']:,}행 | "
        f"{'✅' if inv['trades_same'] else '🔴 **다르다**'} |")
    say(f"| `X0` 실현 매도 건수 | {inv['n_sell_60']:,} | {inv['n_sell_130']:,} | "
        f"{'✅' if inv['n_sell_60'] == inv['n_sell_130'] else '🔴 **다르다**'} |")
    say("")
    say("비교 서명 = `(종목, side, 체결 봉 datetime, 사유, 수량, 체결가, 진입가, 손익률)`. "
        "🔴 `idx` 는 프레임 시작점이 달라지면 통째로 밀리므로 «체결 봉 datetime» 으로 바꿔 "
        "비교했다 — 그래야 「창 길이에 불변인가」라는 질문에 답이 된다.")
    say("")
    all_same = inv["fire_same"] and inv["sel_same"] and inv["trades_same"]
    if all_same:
        say("### ✅ **세 층 모두 동일 — §11-3 표가 실측으로 확인됐다**")
        say("")
        say("⇒ `rule_ma5_pullback`(마지막 22봉) · `score`(마지막 5봉) · `X0`(sl/tp/max_hold) 는 "
            "**창 길이에 산술적으로 불변**이고, §11 개정이 값을 바꾸는 것은 "
            "**EMA 두 arm(`LE13`·`LE65`)뿐**이다. 🔴 **기준선(X0)이 흔들리지 않는다.**")
    else:
        say("### 🔴🔴 **불일치 — 진행을 멈추고 보고한다 (§11-4)**")
        say("")
        say("§11-3 의 불변 표가 틀렸다는 뜻이다. 아래는 처음 어긋난 지점 최대 5건이다.")
        say("")
        for i, a, b in inv["mismatch"]:
            say(f"- `#{i}` 60봉 `{a}` vs 130봉 `{b}`")
    say("")

    # ── §6-5 실행 시간 실측·추정 ────────────────────────────────────────────
    say("## 7. §6 «항목 4» 실행 시간 실측 → 전체 추정")
    say("")
    say("⚠️ **번호 주의** — 동결본 §6 은 항목 1~4 를 매긴 뒤 «별도로» `### 6-4` 소절(2단계 사전 "
        "병기 조건)을 둔다. 그래서 **「§6-4」가 두 곳을 가리킨다**(항목 4 = 실행 시간 보고 / "
        "소절 6-4 = 병기 조건). 이 문서는 전자를 **「§6 항목 4」**, 후자를 **「§6-4」**로 적어 "
        "구분한다. 🔴 **동결본을 고치지 않았다 — 번호만 이 산출물에서 갈라 부른다.**")
    say("")
    t_arm = inv["secs_130"]
    uniq_sel = ca["sel_codes"]
    r_sel_uniq = len({c for v in base_a.values() for c in v})
    scale = r_sel_uniq / uniq_sel if uniq_sel else float("nan")
    say(f"- **`X0` 1 arm 실측 = {t_arm:.0f}초** (창 {RULE_WINDOW}봉 프레임 · A반 선택 "
        f"{ca['sel']:,} 종목-일 · 고유 종목 {uniq_sel:,} · 체결 가능 신호 {inv['signals']:,})")
    say(f"- (대조) 창 {RULE_WINDOW_LEGACY}봉 프레임 = {inv['secs_60']:.0f}초")
    say("")
    say("비용은 «고유 종목 수 × 프레임 길이»가 지배한다(`run_single` 이 종목마다 전 봉을 훑는다). "
        f"`R_sel` 은 `base_filter` 통과 전체에서 뽑으므로 고유 종목이 "
        f"**{r_sel_uniq:,}** 로 X0 의 **{scale:.1f}배**다.")
    say("")
    est_exp = 9 * t_arm
    est_rexit = N_SEEDS * t_arm
    est_rsel = N_SEEDS * t_arm * scale
    est_tot = est_exp + est_rexit + est_rsel
    say("| 묶음 | arm 수 | 1 arm 추정 | 합계 추정 |")
    say("|---|---|---|---|")
    say(f"| 실험 (FIXED 3 + LINE 6) | 9 | {t_arm:.0f}s | **{est_exp/60:.1f}분** |")
    say(f"| 귀무 `R_exit` (시드 0..19) | {N_SEEDS} | {t_arm:.0f}s | **{est_rexit/60:.1f}분** |")
    say(f"| 참조 `R_sel` (시드 0..19) | {N_SEEDS} | {t_arm*scale:.0f}s | **{est_rsel/60:.1f}분** |")
    say(f"| **전체** | **{9+2*N_SEEDS}** | — | **{est_tot/60:.1f}분** |")
    say("")
    say("⚠️ **추정의 불확실성 — 정직하게 적는다.**")
    say("")
    say(f"1. **LINE 계열 6 arm 은 위 추정보다 «비싸다».** `_exit_line_value()` 가 보유 중인 "
        f"봉마다 `df.iloc[: i+1]` 전체에 `rolling`/`ewm` 을 돌린다. 다만 **`max_hold`=30 이 "
        f"전 arm 공통**이므로 보유 봉 수는 «신호 수 × 30» 을 넘을 수 없고, 그 상한은 "
        f"**{inv['signals']*MAX_HOLD:,}회 호출**이다.")
    say(f"2. `R_exit` 은 청산이 이르므로 보유 봉이 짧아 X0 보다 **싸거나 같다** — 위 추정은 상한이다.")
    say(f"3. `R_sel` 추정은 «고유 종목 비율»만으로 스케일한 것이라 오차가 가장 크다.")
    say("")
    if est_tot > 3600:
        say(f"🔴 **전체 추정 {est_tot/60:.0f}분 > 60분 — §6 항목 4 에 따라 진행 전에 보고한다.**")
    else:
        say(f"✅ **전체 추정 {est_tot/60:.1f}분** — 진행 가능한 규모다(§6 항목 4 보고 문턱 미만).")
    say("")

    # ── §2-3 우선순위 대조 ──────────────────────────────────────────────────
    say("## 8. §2-3 우선순위 ↔ `BookBacktester` 통합 사슬 대조")
    say("")
    say("구현의 단일 사슬은 "
        "`disaster → random_exit → stop_loss → take_profit → line_break → max_hold → eod` "
        "하나뿐이다. 계열별 파라미터를 넣었을 때 그것이 §2-3 의 두 줄로 «축약»되는지를 "
        "arm 마다 직접 대조한다.")
    say("")
    say("| Arm | 계열 | `BookBacktester` 인자 | **실제 발동 가능 사슬** | §2-3 과 일치 |")
    say("|---|---|---|---|---|")
    ok_chain = True
    for a in EXP_ARMS:
        kw = arm_kwargs(a)
        fam = "FIXED" if a in FIXED_ARMS else "LINE"
        if fam == "FIXED":
            want = (kw["disaster_stop_pct"] is None and kw["random_exit_seed"] is None
                    and kw["exit_line"] is None and kw["stop_loss_pct"] is not None
                    and kw["take_profit_pct"] is not None)
        else:
            want = (kw["random_exit_seed"] is None and kw["stop_loss_pct"] is None
                    and kw["take_profit_pct"] is None and kw["exit_line"] is not None
                    and kw["disaster_stop_pct"] == DISASTER_STOP)
        ok_chain = ok_chain and want
        args = (f"sl={kw['stop_loss_pct']} tp={kw['take_profit_pct']} "
                f"line={kw['exit_line']} disaster={kw['disaster_stop_pct']} "
                f"mh={kw['max_hold_bars']}")
        say(f"| **{a}** | {fam} | `{args}` | {active_chain(a)} | {'✅' if want else '🔴'} |")
    kw = arm_kwargs("R_exit#0")
    say(f"| **R_exit** (시드 0..19) | 귀무 | `sl=None tp=None line=None disaster=None "
        f"random_max={kw['random_exit_max_bars']} mh={kw['max_hold_bars']}` | "
        f"{active_chain('R_exit#0')} | ✅ |")
    say(f"| **R_sel** (시드 0..19) | 참조 | `X0 와 동일 (종목만 무작위)` | "
        f"{active_chain('R_sel#0')} | ✅ |")
    say("")
    say("- **FIXED**: 마지노선도 선도 없으므로 사슬이 **손절 → 익절 → max_hold** 로 축약된다. "
        "🔑 §2-1 이 적은 대로 −3/−5/−6% 손절은 −10% 마지노선보다 «타이트»해서 마지노선이 "
        "발동할 수 없다 — 그래서 FIXED 에는 아예 넣지 않는다.")
    say("- **LINE**: 익절도 %손절도 없으므로 **마지노선 → 선 이탈 → max_hold** 로 축약된다. "
        "🔑 마지노선을 «먼저» 두는 이유는 §2-3 이 적은 대로 「§6-4 의 마지노선 발동 비율이 "
        "상한이 아니라 실제 발동 횟수가 되도록」이다.")
    say(f"- **R_exit**: 다른 청산 규칙이 없다. `max_hold`={MAX_HOLD} 을 «형식상» 같이 켜지만 "
        f"무작위 `k ≤ {RANDOM_EXIT_MAX_BARS}` 가 사슬에서 «먼저» 잡히므로 max_hold 는 "
        f"발동할 수 없다. ⚠️ §5-1 이 적은 대로 ***`R_exit` 은 「30일째에 파는 arm」이 아니라 "
        f"「30봉 안 아무 날에 파는 arm」이다.***")
    say(f"- **단위(§11-5)**: `R_exit` 의 `k` 는 **봉 수**(`hold_bars = i − entry_idx`)로 센다. "
        f"이 문서는 일봉만 쓰므로 「거래일」과 같다.")
    say("")
    say(f"⇒ **{'✅ arm 9개 전부 §2-3 축약과 일치' if ok_chain else '🔴 불일치 — 보고 대상'}**. "
        f"같은 대응을 `tests/strategies/books/test_book_backtester_exit_rules.py` 가 "
        f"`test_prereg_fixed_arm_reduces_to_stop_take_maxhold`(3건) · "
        f"`test_prereg_line_arm_reduces_to_disaster_line_maxhold`(6건)로 못박는다.")
    say("")

    # ── §6-4 2단계 사전 병기 조건 ───────────────────────────────────────────
    say("## 9. §6-4 🔴🔴 2단계 사전 병기 조건 — **여기서 미리 동결한다**")
    say("")
    say("청산사유 비중·최악 손실 분포는 PnL 의 산물이라 1단계에서 낼 수 없다. "
        "그래서 **문턱을 지금 못박는다** — 2단계가 이 표를 그대로 평가한다.")
    say("")
    say("| 조건 | 문턱 (동결) | 병기문 |")
    say("|---|---|---|")
    say(f"| LINE arm 의 「마지노선(−10%)」 발동 비중 | > **{DISASTER_FIRE_FLAG:.0f}%** | "
        f"🔴 ***「선이 아니라 손절폭을 재고 있다」*** — 그 arm 은 사실상 「−10% 손절 전략」이다 |")
    say(f"| arm 간 **폐기율**(신호→실현 전환 실패) 격차 | ≥ **{DISCARD_RATIO_FLAG:.0f}배** | "
        f"문서 1 §10-5 승계 — 병기 |")
    say(f"| LINE arm 의 최악 손실 1% 분위 | < **{WORST_Q1_FLAG:.0f}%** | "
        f"🔴 갭하락으로 마지노선이 «지켜지지 않았다» — 실체 규모를 병기 |")
    say("")

    # ── 실행 중 관찰 ────────────────────────────────────────────────────────
    say("## 10. 🔴 실행 중 관찰한 것 (사전등록 이행 관련 · 해석 아님)")
    say("")
    say(f"1. **룰 창 {RULE_WINDOW}봉** — §11-3 개정을 따랐다(동결본 §3-1 의 60봉이 아니다). "
        f"§6 위 표에서 «불변»을 실측으로 확인했다.")
    say(f"2. **프레임 앞 히스토리 {RULE_WINDOW-1}봉** — §11 의 목적(EMA 오염 제거)이 "
        f"실제로 달성되려면 룰 평가 창뿐 아니라 **백테스트 프레임**도 같이 늘려야 한다. "
        f"`BookBacktester` 는 기준선을 `df.iloc[: i+1]` «전체»로 계산하기 때문이다. "
        f"🔴 이것은 §11-3 표가 SMA/EMA 를 「창」 아래 함께 적은 것을 실행부에서 이렇게 "
        f"해석한 결과다 — **해석 지점이므로 명시해 둔다.**")
    say(f"3. **진입은 전 arm 동일** — 룰 캐시를 «한 번»만 만들고 FIXED·LINE·`R_exit` 이 "
        f"같은 선택을 쓴다. arm 간 차이의 출처가 청산 하나로 좁혀진다(§1).")
    say(f"4. **`R_sel` 풀은 `base_filter` 통과 전체**(진입 룰 없음) — 다른 arm 과 풀 정의가 "
        f"다르다. §5-1 이 「인쇄만」으로 지정한 참조값이다.")
    say(f"5. **홀드아웃** — `md5(code) % 2 == 0` 인 A반만 산출에 넣었다. B반은 §6-1 이 명령한 "
        f"«건수»에만 등장하고 `build_pools()` 가 A반으로 하드 필터하므로 "
        f"**arm 선택·백테스트 경로에 들어갈 수 없다**(§8-7).")
    say(f"6. **동점 처리** = 코드 오름차순 안정정렬(라이브는 DB 행 순서라 재현 불가).")
    say(f"7. **불가능봉 가드 미적용** — 승계 원본과 동일(§7-14).")
    say("")
    say("### 어떤 컬럼만 SELECT 했는가")
    say("")
    say("- `daily_prices`: `stock_code`·`date`·`open`·`high`·`low`·`close`·`volume`·"
        "`adj_factor`·`market_cap` — **9개 컬럼만**.")
    say("- **매매 원장 테이블(`virtual_trading_records` 등)은 어느 것도 조회하지 않았다.**")
    say("")

    say("## 11. 게이트 종합 (판정 아님 — 조건 성립 여부만)")
    say("")
    say("| 항목 | 결과 |")
    say("|---|---|")
    say(f"| §6-1 A/B 분할 균형 (40~60%) | {'✅' if balanced else '🔴 병기'} "
        f"(A반 {a_frac*100:.1f}%) |")
    say(f"| §6-2 연도 쏠림 — 선택 종목-일 | {'✅' if ok_year else '🔴 병기'} |")
    say(f"| §6-2 연도 쏠림 — 진입 트리거(참고) | {'✅' if ok_year_trig else '🔴'} |")
    say(f"| §11-2 초기값 잔존 ≤2% | "
        f"{'✅' if ema_initial_weight(65, RULE_WINDOW) <= 0.02 else '🔴'} |")
    say(f"| §11-4 60↔130 불변 | {'✅ 동일' if all_same else '🔴 **불일치 — 중단·보고**'} |")
    say(f"| §2-3 사슬 축약 대조 | {'✅' if ok_chain else '🔴'} |")
    say(f"| §6 항목 4 전체 실행 추정 | {est_tot/60:.1f}분 |")
    say("")

    (BASE / "GATE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] GATE.md", flush=True)
    return 0 if all_same else 1


# ────────────────────────────────────────────────────────────────────────────
# 12. stage2 — PREREG §4·§5 판정
# ────────────────────────────────────────────────────────────────────────────
def stage2() -> int:
    # 🔴 지역 import — 1단계가 「arm PnL 계산 경로가 아예 없다」를 보증하기 위해서다.
    from backtest.book_backtester import BookBacktester  # noqa: PLC0415

    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    rep("# 판정 — `ma5` 의 청산: 고정 손익비인가, 기준선 이탈인가")
    rep("")
    rep(f"사전등록 [`PREREG.md`](PREREG.md)(동결 + §11 개정) 실행 · 가족 등록부 "
        f"[`../REGISTRY.md`](../REGISTRY.md) **E1 문서** · 창 **{W0} ~ {W1}** · "
        f"실행 커밋 **`{sha}`** · 1단계 게이트 → [`GATE.md`](GATE.md) · "
        f"원시 출력 → [`RESULTS_raw.md`](RESULTS_raw.md).")
    rep("")
    rep(f"🔴 **ε·arm·시드·문턱·`score`·`max_hold`·마지노선·홀드아웃 분할은 동결분 그대로다.** "
        f"ε = **{EPS_ECON}%p**(§5) · N1 = **`arm > R_exit {N_SEEDS}개 전부`**(§5-1) · "
        f"주 검정 **1개**(§5-2)에 Holm(§5-5). 룰 창 **{RULE_WINDOW}봉**(§11-3).")
    rep("")
    rep("🔴 **판정·산출은 전부 A반(`md5(code)%2==0`)에서만 한다.** B반은 §10 프로토콜 밖에서 "
        "열지 않으며, 이 스크립트에는 **B반을 백테스트하는 코드 경로가 없다**(§8-7).")
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
    rep(f"- 실행 커밋 SHA **`{sha}`** · 청산 기준선은 `config.yaml` 에서 읽었다 "
        f"(sl **{params['sl']}** / tp **{params['tp']}** / max_hold **{params['mh']}**).")
    rep("- **등록 외 조합은 계산하지 않았다** — arm 은 FIXED 3 · LINE 6 · `R_exit` · `R_sel` "
        "뿐이고 선 추가·문턱 스윕·조합(선 ∧ 익절)은 이 스크립트에 구현되어 있지 않다(§8-2·§8-3).")
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
    conn.close()
    scr = BookPullbackMa5ScreenerAdapter()
    elig = eligible_by_date(uni, scr)
    print(f"[load] {len(px):,}행 · {time.perf_counter()-t0:.0f}s", flush=True)

    print(f"[cache] 룰 평가 (창 {RULE_WINDOW}봉)", flush=True)
    cache, cstats = build_cache(px, elig, scr, RULE_WINDOW, params["min_bars"])
    pool_a, base_a = build_pools(cache, elig)      # 🔴 A반 하드 필터
    sel_a = select_top(pool_a)
    frames, idxmap = build_frames(px, RULE_WINDOW)
    say(f"\n발화 {cstats['n_fire']:,} · A반 선택 종목-일 "
        f"{sum(len(v) for v in sel_a.values()):,} · 프레임 {len(frames):,}종목")

    # ── arm 실행 ────────────────────────────────────────────────────────────
    res = {}
    for a in EXP_ARMS:
        t1 = time.perf_counter()
        res[a] = run_arm(sel_a, frames, idxmap, a, BookBacktester)
        print(f"    {a:5} sig={res[a]['signals']:>6} n={res[a]['n']:>5} "
              f"mean={res[a]['mean']:+.2f}% {time.perf_counter()-t1:.0f}s", flush=True)
    r_exit = []
    for s in range(N_SEEDS):
        m = run_arm(sel_a, frames, idxmap, f"R_exit#{s}", BookBacktester)
        r_exit.append(m)
        print(f"    R_exit{s:<3} n={m['n']:>5} mean={m['mean']:+.2f}%", flush=True)
    r_sel = []
    for s in range(N_SEEDS):
        m = run_arm(select_random_codes(base_a, s), frames, idxmap,
                    f"R_sel#{s}", BookBacktester)
        r_sel.append(m)
        print(f"    R_sel {s:<3} n={m['n']:>5} mean={m['mean']:+.2f}%", flush=True)

    r_means = [x["mean"] for x in r_exit]
    rmax = max(r_means)
    means = {a: res[a]["mean"] for a in EXP_ARMS}
    n1 = {a: means[a] > rmax for a in EXP_ARMS}
    pv = {a: perm_p(means[a], r_means) for a in EXP_ARMS}

    # ── §5-3 탐색 지도 ──────────────────────────────────────────────────────
    rep("## 1. §5-3 전 arm 표 — 🔴 **탐색 지도 (인쇄만 · 판정 언어 금지)**")
    rep("")
    rep("🔑 `pnl_pct` 에 **슬리피지 편도 0.1% 는 반영**, **수수료 0.015%·거래세 0.18% 는 "
        "미반영**(승계 원본과 같은 gross 정의).")
    rep("")
    rep("| Arm | 청산 규칙 | n | 거래당 평균 | 중앙 | 승률 | 보유 중앙 | 최악 | 1% 분위 | 5% 분위 |")
    rep("|---|---|---|---|---|---|---|---|---|---|")
    for a in EXP_ARMS:
        m = res[a]
        rep(f"| **{a}** | {ARM_DESC[a]} | {m['n']:,} | **{m['mean']:+.2f}%** | "
            f"{m['med']:+.2f}% | {m['win']:.0f}% | {m['hold']:.0f}봉 | {m['worst']:+.1f}% | "
            f"{m['q01']:+.1f}% | {m['q05']:+.1f}% |")
    rep(f"| **R_exit** | 무작위 청산 ({N_SEEDS}시드) | "
        f"{int(np.mean([x['n'] for x in r_exit])):,} (평균) | "
        f"중앙 **{np.median(r_means):+.2f}%** · 최소 {min(r_means):+.2f}% · "
        f"**최대 {rmax:+.2f}%** | | | | | | |")
    rsm = [x["mean"] for x in r_sel]
    rep(f"| **R_sel** (참조) | 무작위 종목 + X0 ({N_SEEDS}시드) | "
        f"{int(np.mean([x['n'] for x in r_sel])):,} (평균) | "
        f"중앙 **{np.median(rsm):+.2f}%** · 최대 {max(rsm):+.2f}% | | | | | | |")
    rep("")
    rep("🔴 **이 표를 보고 arm 을 «채택»하지 않는다**(§8-4). REGISTRY 규칙 4 에 따라 "
        "**「탐색적 관측 — 다음 사전등록의 표적」**으로만 쓴다.")
    rep("")

    # ── 청산사유 비중 ───────────────────────────────────────────────────────
    rep("## 2. §4 청산사유 비중 (보조 · 인쇄만)")
    rep("")
    all_reasons = ["disaster_stop", "random_exit", "stop_loss", "take_profit",
                   "line_break", "max_hold", "forced_close"]
    rep("| Arm | " + " | ".join(f"`{r}`" for r in all_reasons) + " |")
    rep("|---|" + "---|" * len(all_reasons))
    for a in EXP_ARMS:
        c, tot = res[a]["reasons"], max(res[a]["n"], 1)
        rep(f"| **{a}** | " + " | ".join(f"{c.get(r,0)/tot*100:.0f}%" for r in all_reasons) + " |")
    rep("")

    # ── §4 보조 — 중앙 주가/시총/거래대금 ───────────────────────────────────
    rep("### 2-1. §4 보조 — 선택 종목-일의 중앙 주가 / 시총 / 거래대금 (인쇄만)")
    rep("")
    prof = selection_profile(sel_a, uni, frames, idxmap)
    prof_r = selection_profile(select_random_codes(base_a, 0), uni, frames, idxmap)
    rep("| 선택 집합 | 종목-일 | 중앙 주가 | 중앙 시총 | 중앙 거래대금 |")
    rep("|---|---|---|---|---|")
    rep(f"| **FIXED·LINE·`R_exit` 공통** | {prof['n']:,} | {prof['close']:,.0f}원 | "
        f"{prof['mcap']/1e8:,.0f}억 | {prof['tv']/1e8:,.1f}억 |")
    rep(f"| `R_sel` (시드 0, 대표값) | {prof_r['n']:,} | {prof_r['close']:,.0f}원 | "
        f"{prof_r['mcap']/1e8:,.0f}억 | {prof_r['tv']/1e8:,.1f}억 |")
    rep("")
    rep("🔑 위 칸이 **하나**인 이유 — 진입이 전 arm 동일하므로 FIXED·LINE·`R_exit` 은 "
        "«같은 종목-일»을 산다(§2). arm 마다 달라지는 것은 «판 시점»뿐이다.")
    rep("")

    # ── §6-4 병기 조건 평가 ─────────────────────────────────────────────────
    rep("## 3. §6-4 사전 병기 조건 (1단계에서 동결한 문턱을 그대로 평가)")
    rep("")
    flags = []
    rep("| LINE arm | 마지노선 발동 비중 | > 33%? | 1% 분위 | < −20%? |")
    rep("|---|---|---|---|---|")
    for a in LINE_ORDER:
        m = res[a]
        dfire = m["reasons"].get("disaster_stop", 0) / max(m["n"], 1) * 100
        hit1 = dfire > DISASTER_FIRE_FLAG
        hit2 = m["q01"] < WORST_Q1_FLAG
        if hit1:
            flags.append(f"🔴 `{a}`: 마지노선 발동 {dfire:.0f}% > {DISASTER_FIRE_FLAG:.0f}% ⇒ "
                         f"***「선이 아니라 손절폭을 재고 있다」*** — 사실상 「−10% 손절 전략」")
        if hit2:
            flags.append(f"🔴 `{a}`: 1% 분위 {m['q01']:+.1f}% < {WORST_Q1_FLAG:.0f}% ⇒ "
                         f"갭하락으로 마지노선이 «지켜지지 않았다»")
        rep(f"| **{a}** | {dfire:.0f}% | {'🔴 예' if hit1 else '✅ 아니오'} | "
            f"{m['q01']:+.1f}% | {'🔴 예' if hit2 else '✅ 아니오'} |")
    rep("")
    ds = {a: res[a]["discard"] for a in EXP_ARMS}
    ds["R_exit"] = float(np.mean([x["discard"] for x in r_exit]))
    rep("| Arm | 신호 수 | 실현 거래 | **폐기율** |")
    rep("|---|---|---|---|")
    for a in EXP_ARMS:
        rep(f"| **{a}** | {res[a]['signals']:,} | {res[a]['n']:,} | "
            f"**{res[a]['discard']:.1f}%** |")
    rep(f"| **R_exit** (평균) | {int(np.mean([x['signals'] for x in r_exit])):,} | "
        f"{int(np.mean([x['n'] for x in r_exit])):,} | **{ds['R_exit']:.1f}%** |")
    rep("")
    lo, hi = min(ds.values()), max(ds.values())
    ratio = hi / lo if lo > 0 else float("inf")
    if ratio >= DISCARD_RATIO_FLAG:
        flags.append(f"🔴 폐기율이 arm 간 **{ratio:.2f}배** 벌어졌다 (≥{DISCARD_RATIO_FLAG:.0f}배) "
                     f"⇒ 실현 거래가 신호의 «비무작위» 부분집합이고 그 정도가 arm 마다 다르다")
        rep(f"🔴 **폐기율 최대/최소 = {ratio:.2f}배** — 병기 대상(§6-4).")
    else:
        rep(f"✅ **폐기율 최대/최소 = {ratio:.2f}배 (<{DISCARD_RATIO_FLAG:.0f}배)**.")
    rep("")

    # ── §5-1 귀무 N1 ────────────────────────────────────────────────────────
    rep("## 4. §5-1 귀무 `N1` — 각 arm 이 «무작위 청산» 20회 «전부»를 넘는가")
    rep("")
    rep("🔑 **이 문서의 귀무는 「무작위 종목」이 아니라 「무작위 «청산»」이다.** 진입이 전 arm "
        "동일하므로 종목 귀무를 쓰면 차이가 「청산 때문인지 종목 선택 때문인지」 갈리지 않는다.")
    rep("")
    rep("| Arm | 거래당 평균 | `R_exit` 최대 | N1 | 단측 순열 p |")
    rep("|---|---|---|---|---|")
    for a in EXP_ARMS:
        rep(f"| **{a}** | {means[a]:+.2f}% | {rmax:+.2f}% | {'✅' if n1[a] else '❌'} | "
            f"{pv[a]:.4f} |")
    rep("")
    if not n1["X0"]:
        rep("### 🔴🔴 이것이 이 문서의 «가장 중요한 결과»다 (§5-1 사전 지정)")
        rep("")
        rep(f"**기준선 `X0`(현행 라이브)가 N1 을 통과하지 못했다** — "
            f"`X0` {means['X0']:+.2f}% ≤ `R_exit` 최대 {rmax:+.2f}%.")
        rep("")
        rep("⇒ ***현행 청산 규칙(−3%/+15%)이 이미 「30봉 안 아무 날에나 파는 것」과 구별되지 "
            "않는다.*** 사전등록 §5-1 이 *「그것 자체가 이 문서의 가장 중요한 결과다. 눈에 띄게 "
            "인쇄한다」* 라고 미리 지정한 관측이다. (앞선 두 문서에서 기준선이 귀무를 못 넘는 "
            "일이 **이미 두 번** 나왔다 — `rank_score` 의 `V`, `minervini` 의 `D`.)")
        rep("")
    else:
        rep(f"✅ **기준선 `X0` 는 N1 통과** ({means['X0']:+.2f}% > `R_exit` 최대 {rmax:+.2f}%).")
        rep("")
    rep(f"**참조 `R_sel`**(무작위 종목 + X0 청산) 중앙 **{np.median(rsm):+.2f}%** · "
        f"최대 **{max(rsm):+.2f}%** — 🔴 **§5-2 판정에 쓰지 않는다**(§5-1). "
        f"「전략 전체가 무작위 종목보다 나은가」라는 **별개 질문의 sanity 값**이다.")
    rep("")
    rep(f"⚠️ `R_exit` 은 `max_hold`={MAX_HOLD} 과 «상한이 같다» — 즉 무작위 청산은 "
        f"「30봉 안 아무 날」이고, `max_hold` 만 켠 arm 의 특수 경우가 «아니다»"
        f"(그건 항상 30일째다). §5-1 이 미리 적으라고 지정한 구분이다.")
    rep("")

    # ── §5-2 주 판정 ────────────────────────────────────────────────────────
    rep("## 5. §5-2 주 판정 — 🔴 **주 검정은 이것 «하나»뿐이다**")
    rep("")
    rep("***「어느 선이 제일 좋은가」를 묻지 않는다.*** 그건 1등을 고르는 일이고 사후적합이다. "
        "대신 **계열 «전체»에게 묻는다.**")
    rep("")
    verdict, det = verdict_5_2(means, n1)
    rep("| 지표 | 값 |")
    rep("|---|---|")
    rep(f"| `min(LINE)` | **{det['min_line']:+.2f}%** |")
    rep(f"| `max(LINE)` | {det['max_line']:+.2f}% |")
    rep(f"| `min(FIXED)` | {det['min_fixed']:+.2f}% |")
    rep(f"| `max(FIXED)` | **{det['max_fixed']:+.2f}%** |")
    rep(f"| **`min(LINE) − max(FIXED)`** | **{det['d_line']:+.2f}%p** |")
    rep(f"| **`min(FIXED) − max(LINE)`** | **{det['d_fixed']:+.2f}%p** |")
    rep(f"| LINE 전 arm N1 | {'✅' if det['all_line_n1'] else '❌'} |")
    rep(f"| FIXED 전 arm N1 | {'✅' if det['all_fixed_n1'] else '❌'} |")
    rep(f"| ε (동결) | {EPS_ECON}%p |")
    rep("")
    rep(f"# {verdict}")
    rep("")
    rep("⚠️ **세 라벨은 상호배타적이고 전부를 덮는다. 결과가 어느 쪽이든 새 라벨을 짓지 않는다.** "
        "🔴 **(나) 는 실패가 아니다** — *「이 전략의 성적은 청산 튜닝의 산물이다」* 라는 결론이다.")
    rep("")

    # ── §5-4 사장님 ① 대조 ──────────────────────────────────────────────────
    rep("## 6. §5-4 사장님 ① 대안의 개별 대조 (인쇄만 · 사전고정 라벨 · 판정 언어 금지)")
    rep("")
    rep("| 대조 | 값 |")
    rep("|---|---|")
    rep(f"| `X1 − X0` | **{means['X1']-means['X0']:+.2f}%p** |")
    rep(f"| `X2 − X0` | **{means['X2']-means['X0']:+.2f}%p** |")
    rep("")
    rep(f"⇒ **{label_5_4(means['X0'], means['X1'], means['X2'])}**")
    rep("")
    rep("🔑 **둘 «다»** 같은 방향일 때만 라벨한다 — 하나만 보고 말하면 그게 1등 고르기다.")
    rep("")

    # ── §5-5 Holm ───────────────────────────────────────────────────────────
    rep("## 7. §5-5 다중검정 (주 검정 1개, α = .05)")
    rep("")
    if det["d_line"] >= EPS_ECON:
        pmain = max(pv[a] for a in LINE_ORDER)
        mname = "§5-2 주 검정 (LINE 계열 전체 vs R_exit)"
    elif det["d_fixed"] >= EPS_ECON:
        pmain = max(pv[a] for a in FIXED_ORDER)
        mname = "§5-2 주 검정 (FIXED 계열 전체 vs R_exit)"
    else:
        pmain = min(max(pv[a] for a in LINE_ORDER), max(pv[a] for a in FIXED_ORDER))
        mname = "§5-2 주 검정 (계열 우세 미성립 — 참고값)"
    hres = holm([(mname, pmain)])
    rep("| 검정 | 단측 순열 p (계열 내 최댓값) | Holm 문턱 | 기각? |")
    rep("|---|---|---|---|")
    for name, p, thr, rej in hres:
        rep(f"| {name} | {p:.4f} | {thr:.4f} | {'✅ 기각' if rej else '❌ 기각 못 함'} |")
    rep("")
    pmin = 1 / (N_SEEDS + 1)
    rep(f"🔑 **이 설계는 기각이 «도달 가능»하다.** 주 검정 m=1 이라 Holm 1단계 문턱은 "
        f"α/m = **{ALPHA:.4f}** 이고, 시드 {N_SEEDS} 의 최소 순열 p 는 "
        f"**1/{N_SEEDS+1} = {pmin:.4f} < {ALPHA:.4f}** 다. "
        f"🔴 문서 1(minervini)은 m=2 에 시드 20 이라 **구조적으로 기각 불가**였다 — 반복하지 않았다.")
    rep("")
    rep("🔴 **해석 지점 — 동결본이 명시하지 않은 곳이다.** §5-2 의 주 검정은 «계열 전체»에 "
        "대한 복합 조건(*「계열 전 arm 이 N1」*)인데, 동결본은 그 복합 조건의 **단일 p 값을 "
        "어떻게 만드는지 적지 않았다.** 이 실행부는 **계열 내 arm 별 순열 p 의 «최댓값»**을 "
        "썼다 — 「전부 넘어야 한다」의 p 는 「가장 못 넘은 것」의 p 이기 때문이다. "
        "***결과를 보고 고른 규칙이 아니라 구현 시점에 고정한 규칙이고, 이 문장이 그 기록이다.***")
    rep("")
    rep("§5-3·§5-4 는 **기술 통계이므로 보정 대상이 아니고 판정 언어를 쓰지 않는다.**")
    rep("")
    rep("🔴 **가족 FWER** — `../REGISTRY.md` 현재 등재 주 검정 **4개** ⇒ 보정 없는 "
        "FWER(α=.05) ≈ **18.5%**. ***보정을 안 거는 것과 위험이 없는 것은 다르다*** — "
        "이 숫자를 판정문과 함께 읽을 것.")
    rep("")

    # ── §10 홀드아웃 프로토콜 ───────────────────────────────────────────────
    rep("## 8. §10 홀드아웃 프로토콜 — B반을 «언제·어떻게» 여는가")
    rep("")
    is_na = verdict.startswith("🔴 **(나)")
    if not is_na:
        rep("**§5-2 가 (가) 또는 (다)로 나왔다 ⇒ §10 은 발동하지 않는다.** "
            "방식 수준에서 답이 나왔으므로 B반을 열 이유가 없다. B반은 봉인된 채 남는다.")
    else:
        # §10-1 — 「거래당 평균이 가장 높은 arm 하나」. 동점이면 arm 이름 «사전순»으로 가장
        # 앞선 것(동점 규칙은 사전 고정). NaN(거래 0건)은 후보에서 밀어낸다.
        best = sorted(EXP_ARMS,
                      key=lambda a: (-(means[a] if means[a] == means[a] else -np.inf), a))[0]
        rep(f"**§5-2 가 (나)로 나왔다 ⇒ §10 발동 조건 성립.** A반 §5-3 표에서 거래당 평균이 "
            f"가장 높은 arm 은 **`{best}`** 다(동점이면 arm 이름 사전순 — 동점 규칙은 사전 고정).")
        rep("")
        if best == "X0":
            rep("🔴 **§10-0 — A반 1등이 `X0`(현행) 자신이므로 B반을 «열지 않는다».** "
                "검정할 «선택»이 없기 때문이다. 결론은 「(나) + 현행이 A반 최고」로 끝내고 "
                "B반은 다음 문서를 위해 봉인된 채 남긴다.")
        else:
            rep(f"🔴🔴 **B반은 이 스크립트가 열지 않는다.** §10 은 «별도 결정»이고, "
                f"이 실행부에는 **B반을 백테스트하는 코드 경로가 없다**(`build_pools()` 가 "
                f"A반으로 하드 필터한다). 프로토콜은 다음과 같다:")
            rep("")
            rep(f"```")
            rep(f"1) 선택 arm = `{best}` (A반 1등, 사후 선택 — 그래서 B반이 검정한다)")
            rep(f"2) `{best}` «하나»와 `X0` «하나»만 B반에서 돌린다 — 다른 arm 은 돌리지 않는다")
            rep(f"3) B반에서도 ({best} − X0) ≥ {EPS_ECON}%p 이고 N1 성립 → 🟢 재현됨")
            rep(f"                                    그 외          → 🔴 재현 실패 = A반 1등은 우연")
            rep(f"4) 결과가 무엇이든 B반은 «다시 열지 않는다»")
            rep(f"```")
    rep("")
    rep("⚠️ **B반 재현 성공도 「라이브 채택」이 아니다.** §7-1(whipsaw 미재현)이 그대로 남는다.")
    rep("")

    # ── 병기 ────────────────────────────────────────────────────────────────
    if flags:
        rep("## 9. 🔴 병기 (§6-4 사전 조건 성립분)")
        rep("")
        for f in flags:
            rep(f"- {f}")
        rep("")

    rep("## 10. 🔴 한계 (PREREG §7 1~15, 전량 전재)")
    rep("")
    for i, s in enumerate(LIMITATIONS, 1):
        rep(f"{i}. {s}")
    rep("")

    (BASE / "RESULTS.md").write_text("\n".join(DOC) + "\n", encoding="utf-8")
    (BASE / "RESULTS_raw.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] RESULTS.md · RESULTS_raw.md", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ma5 청산 축 — PREREG 실행부")
    ap.add_argument("--stage1", action="store_true",
                    help="PREREG §6·§11 1단계 게이트 (arm PnL 미산출) → GATE.md")
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
