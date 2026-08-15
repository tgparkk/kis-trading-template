# -*- coding: utf-8 -*-
"""손절폭 vs 봉폭 게이트 — 1단계: `gate_pass` 산출 (PIT 데이터만, PnL 미조회).

사전등록: `PREREG.md`(동결 §0~§9 `7652c99` + §10 개정 2026-08-16). §3(지표·데이터 정의)·
§4(게이트 정의·K·N)·§5-2(퇴화일)·§6 G2(카운트 문턱)·⬜체크리스트, 그리고 §10(arm-B)을 구현한다.

🔴 이 스크립트는 §4(게이트 산출)까지만 한다 — PREREG 의 사전등록 체크리스트가
「게이트 산출(PIT 데이터만) → 커밋 → 그 다음에야 결과 계산(§5~§7, PnL 필요)」 순서를
강제하기 때문이다. 이 파일은 `virtual_trading_records` 에서 **`id`·`stock_code`·
`timestamp`·`strategy`·`action`·`buy_record_id`·`stop_loss_rate`** 만 SELECT 한다 —
`profit_rate`·`price`·`profit_loss` 는 어디에서도 SELECT 하지 않는다
(604건 식별은 `buy_record_id` 연결의 «존재 여부»만으로 한다, 매도가·수익률 조회 없음).
🆕 `stop_loss_rate` 는 **매수 시점에 확정·저장되는 파라미터**이지 결과(PnL)가 아니다 — PIT다
(§10-1). arm-B(§10)가 이 컬럼을 「선언 손절폭」 대신 「실제 손절률」로 쓴다.

`daily_prices` 는 `high`·`low`·`close`·`date`·`stock_code` 만 쓴다(비율 게이트라
`adj_factor` 는 곱하지 않는다 — §3-1·§8-7).

라이브 트리 import 0건 · DB 는 SELECT 만 · `utils/logger.py` 미사용.
관례: `entry_quality_audit/run.py`(`1eb1db5`)의 DSN·`say()`·모듈 docstring 구조를 따른다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import yaml

BASE = Path(__file__).resolve().parent
STRATEGIES_DIR = BASE.parent.parent / "strategies"
OUT: list[str] = []
DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
WINDOW = ("2026-06-01", "2026-08-14")

# K·N 동결(PREREG §4) — 코드에서 임의 조정 금지.
K = 0.5
N_MAIN = 20
N_SENSITIVITY = (10, 40, 60)
# n_excluded 카운트 문턱(604건 기준, PREREG §6 G2 / §8-3) — 동결.
N_EXCLUDED_LOW = 30      # < 30 이면 자동 판별불가
N_EXCLUDED_HIGH = 403    # >= 403 이면 자동 판별불가
# 퇴화일 비중 문턱(§5-2) — 동결.
DEGENERATE_THRESHOLD = 1.0 / 3.0
# G4(부수) 하한(§6) — 동결.
G4_MIN_EXCLUDED = 10
G4_STRATEGIES = ("book_pullback_ma5", "daytrading_3methods_breakout")

# 전략 폴더키 — DB `strategy` 컬럼 값과 동일함을 실측 확인(646건 GROUP BY).
STRATEGY_FOLDERS = [
    "book_envelope_200d",
    "book_pullback_ma20",
    "book_pullback_ma5",
    "daytrading_3methods_breakout",
    "deep_mr_dev20",
    "elder_ema_pullback",
    "minervini_volume_dryup",
    "rs_leader",
]


def say(s=""):
    print(s)
    OUT.append(s)


def load_stop_loss_pct() -> dict:
    """`strategies/{folder}/config.yaml` 의 `risk_management.stop_loss_pct` 를 직접 읽는다.

    하드코딩 금지(작업 지시) — PREREG 참고 관례(`entry_quality_audit`)가 하드코딩했던
    표를 이번엔 코드에서 직접 읽어 재확인한다.
    """
    out = {}
    for folder in STRATEGY_FOLDERS:
        cfg_path = STRATEGIES_DIR / folder / "config.yaml"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        pct = cfg["risk_management"]["stop_loss_pct"]
        out[folder] = float(pct)
    return out


def load_buys(conn) -> pd.DataFrame:
    """646건 — `id`·`stock_code`·매수일·`strategy`·`stop_loss_rate`.

    🆕 `stop_loss_rate` 추가(2026-08-16 §10 개정) — 매수 시점에 확정·저장되는 PIT 파라미터다
    (`trading_decision_engine.py:697` 에서 `trading_stock.stop_loss_rate` 에 박히고
    `execute_virtual_buy` 가 BUY 행에 저장). PnL 컬럼(`price`·`profit_rate`·`profit_loss`)은
    여전히 SELECT 하지 않는다.
    """
    df = pd.read_sql("""
        SELECT id, stock_code, timestamp::date AS buy_date, strategy, stop_loss_rate
        FROM virtual_trading_records
        WHERE action = 'BUY' AND timestamp::date BETWEEN %s AND %s
    """, conn, params=WINDOW)
    df["buy_date"] = df["buy_date"].astype(str)
    df["stop_loss_rate"] = pd.to_numeric(df["stop_loss_rate"], errors="coerce")
    return df


def load_closed_buy_ids(conn) -> set:
    """604건 식별 — `buy_record_id` «연결의 존재»만 본다. 매도가·수익률 SELECT 없음."""
    df = pd.read_sql("""
        SELECT buy_record_id
        FROM virtual_trading_records
        WHERE action = 'SELL' AND buy_record_id IS NOT NULL
    """, conn)
    return set(df["buy_record_id"].dropna().astype(int).tolist())


def load_price_history(conn, codes: list) -> pd.DataFrame:
    """게이트 계산용 PIT 가격 이력. `high`·`low`·`close`·`date`·`stock_code` 만."""
    df = pd.read_sql("""
        SELECT stock_code, date, high, low, close
        FROM daily_prices
        WHERE stock_code = ANY(%s) AND date < %s
        ORDER BY stock_code, date
    """, conn, params=(codes, WINDOW[1]))
    for c in ("high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def compute_range_med(hist_by_stock: dict, stock: str, buy_date: str, n: int):
    """range_med_N(stock, buy_date) — 그 종목의 직전 N «실제 거래일»(매수일 자체 제외).

    반환: (range_med 또는 None(결측), 사용된 창의 행 수, 그 창에 0-range 봉이 있는가)
    """
    dates = hist_by_stock.get(stock)
    if dates is None:
        return None, 0, False
    d, h, l, c = dates
    # d < buy_date 인 마지막 n 개(정렬된 배열이므로 searchsorted 로 절단점을 찾는다)
    cut = np.searchsorted(d, buy_date, side="left")  # d[:cut] 이 전부 buy_date 미만
    if cut <= 0:
        return None, 0, False
    lo = max(0, cut - n)
    window_h = h[lo:cut]
    window_l = l[lo:cut]
    window_c = c[lo:cut]
    n_rows = len(window_h)
    if n_rows < n:
        return None, n_rows, False
    zero_range = bool(np.any(window_h == window_l))
    ranges = (window_h - window_l) / window_c
    ranges = ranges[~np.isnan(ranges)]
    if len(ranges) == 0:
        return None, n_rows, zero_range
    return float(np.median(ranges)), n_rows, zero_range


def main() -> int:
    stop_loss_pct = load_stop_loss_pct()

    conn = psycopg2.connect(**DSN)
    buys = load_buys(conn)
    closed_ids = load_closed_buy_ids(conn)
    codes = buys["stock_code"].unique().tolist()
    hist = load_price_history(conn, codes)
    conn.close()

    buys["is_closed"] = buys["id"].isin(closed_ids)

    # 종목별 정렬된 numpy 배열로 색인 준비(searchsorted 용).
    hist_by_stock = {}
    for code, g in hist.groupby("stock_code"):
        g = g.sort_values("date")
        hist_by_stock[code] = (
            g["date"].to_numpy(),
            g["high"].to_numpy(dtype=float),
            g["low"].to_numpy(dtype=float),
            g["close"].to_numpy(dtype=float),
        )

    # ── 메인(N=20) 게이트 계산 ───────────────────────────────────────────
    range_med_list, n_rows_list, zero_range_list, gate_pass_list = [], [], [], []
    for row in buys.itertuples(index=False):
        rmed, n_rows, zr = compute_range_med(hist_by_stock, row.stock_code, row.buy_date, N_MAIN)
        range_med_list.append(rmed)
        n_rows_list.append(n_rows)
        zero_range_list.append(zr)
        sl = stop_loss_pct[row.strategy]
        if rmed is None:
            gate_pass_list.append(True)  # 결측 → 보수적 «유지»(§3-3)
        else:
            gate_pass_list.append(sl >= K * rmed)
    buys["range_med_20"] = range_med_list
    buys["n_rows_20"] = n_rows_list
    buys["zero_range_20"] = zero_range_list
    buys["gate_pass"] = gate_pass_list
    buys["excluded"] = ~buys["gate_pass"]

    # ── 민감도(N=10·40·60) — 판정에 안 씀, 인쇄만 ───────────────────────
    sens_excluded = {}
    for n in N_SENSITIVITY:
        gp = []
        for row in buys.itertuples(index=False):
            rmed, _, _ = compute_range_med(hist_by_stock, row.stock_code, row.buy_date, n)
            sl = stop_loss_pct[row.strategy]
            if rmed is None:
                gp.append(True)
            else:
                gp.append(sl >= K * rmed)
        buys[f"gate_pass_n{n}"] = gp
        excl = ~pd.Series(gp)
        sens_excluded[n] = {
            "646": int(excl.sum()),
            "604": int(excl[buys["is_closed"].to_numpy()].sum()),
        }

    # ── 🆕 arm-B(§10-2) — 실제 `stop_loss_rate`(BUY 시점 저장값) 기준 게이트 ──────
    # PREREG §10-4: 결측(NULL) 은 §3-3 과 같은 원칙 — 보수적 «유지»(gate_pass_B=TRUE).
    # range_med_20 자체가 결측이면 arm-A 와 동일하게 «유지»(정보가 없으면 배제하지 않는다).
    FLOOR = 0.03
    EPS = 1e-9
    gate_pass_b_list, missing_sl_list = [], []
    for row in buys.itertuples(index=False):
        rmed = row.range_med_20
        rmed_missing = rmed is None or (isinstance(rmed, float) and np.isnan(rmed))
        sl_actual = row.stop_loss_rate
        sl_missing = sl_actual is None or (isinstance(sl_actual, float) and np.isnan(sl_actual))
        missing_sl_list.append(sl_missing)
        if rmed_missing or sl_missing:
            gate_pass_b_list.append(True)  # 결측 → 보수적 «유지»(§10-4)
        else:
            gate_pass_b_list.append(float(sl_actual) >= K * rmed)
    buys["stop_loss_missing"] = missing_sl_list
    buys["gate_pass_B"] = gate_pass_b_list
    buys["excluded_B"] = ~buys["gate_pass_B"]

    # 실제 stop_loss_rate vs config 손절폭 — narrower/same/wider(§10-1 실측, floor-clamp 포함)
    narrower_wider_rows = []
    for row in buys.itertuples(index=False):
        cfg_val = stop_loss_pct[row.strategy]
        if row.stop_loss_missing:
            cat = "missing"
        else:
            sl_actual = float(row.stop_loss_rate)
            if sl_actual < cfg_val - EPS:
                cat = "narrower"
            elif abs(sl_actual - cfg_val) < EPS:
                cat = "same"
            else:
                cat = "wider"
        floor_clamped = (
            not row.stop_loss_missing
            and abs(float(row.stop_loss_rate) - FLOOR) < EPS
            and abs(cfg_val - FLOOR) >= EPS
        )
        narrower_wider_rows.append((row.strategy, cat, floor_clamped))
    nw_df = pd.DataFrame(narrower_wider_rows, columns=["strategy", "category", "floor_clamped"])

    n_646 = len(buys)
    n_604 = int(buys["is_closed"].sum())
    n_excluded_646 = int(buys["excluded"].sum())
    excluded_604_mask = buys["excluded"] & buys["is_closed"]
    n_excluded_604 = int(excluded_604_mask.sum())

    # ── 리포트 시작 ──────────────────────────────────────────────────────
    say("# 손절폭 vs 봉폭 게이트 — 1단계 산출 (`gate_pass`, PIT 전용, PnL 미조회)\n")
    say(f"사전등록: `PREREG.md`(동결). 창 {WINDOW[0]}~{WINDOW[1]} · K={K} · N={N_MAIN}거래일.\n")
    say("🔴 이 문서는 §4(게이트 산출)까지만 다룬다. **해석·「좋다/나쁘다」 판단은 없다** — "
        "순수 산출이다. 결과 계산(§5~§7, PnL 필요)은 2단계다.\n")

    say("## 0. config.yaml 에서 읽은 선언 손절폭(하드코딩 아님)\n")
    say("| 전략 | stop_loss_pct | 지시서 기대값 | 일치 |")
    say("|---|---|---|---|")
    expected = {
        "book_envelope_200d": 0.08, "book_pullback_ma20": 0.08, "elder_ema_pullback": 0.08,
        "minervini_volume_dryup": 0.08, "rs_leader": 0.08, "deep_mr_dev20": 0.07,
        "book_pullback_ma5": 0.03, "daytrading_3methods_breakout": 0.10,
    }
    for folder in STRATEGY_FOLDERS:
        v = stop_loss_pct[folder]
        exp = expected[folder]
        say(f"| {folder} | {v:.0%} | {exp:.0%} | {'✅' if abs(v - exp) < 1e-9 else '❌ 상이 — 보고 필요'} |")
    say()

    say("## 1. 표본 규모\n")
    say(f"매수 646건 실측 **{n_646}**건 · 청산완료(604 추정) 실측 **{n_604}**건 "
        f"(`buy_record_id` 연결 존재 여부만으로 식별 — 매도가·수익률 SELECT 없음).\n")

    say("## 2. n_excluded — 646 기준 / 604 기준\n")
    say(f"- **646 기준**: {n_excluded_646} / {n_646} (배제율 {n_excluded_646/n_646*100:.1f}%)")
    say(f"- **604 기준**: {n_excluded_604} / {n_604} (배제율 {n_excluded_604/n_604*100:.1f}%)\n")

    say("## 3. 🔴 카운트 문턱 판정 — [30, 403) — 퇴화일 계산보다 «먼저»(§8-3)\n")
    count_gate_pass = N_EXCLUDED_LOW <= n_excluded_604 < N_EXCLUDED_HIGH
    say(f"PREREG §6 G2 동결 문턱: `n_excluded < 30` → 자동 판별불가 · `n_excluded ≥ 403` → 자동 판별불가.")
    say(f"604 기준 n_excluded = **{n_excluded_604}**.")
    if count_gate_pass:
        say(f"⇒ **[30, 403) 안 — 카운트 문턱 통과.** G2-simple·G2-strat 계산이 2단계에서 유효할 자격이 있다.\n")
    else:
        reason = "< 30 (배제율 5% 미만)" if n_excluded_604 < N_EXCLUDED_LOW else "≥ 403 (배제율 2/3 초과)"
        say(f"⇒ 🔴 **[30, 403) 밖 — {reason}. G2-simple·G2-strat 은 결과와 무관하게 자동 「검정력 부족 → "
            f"판별불가」로 확정된다(§6 G2, §8-3).** 아래 퇴화일·민감도는 투명성을 위해 그대로 계산·인쇄한다.\n")

    say("## 4. 퇴화일 (§5-2) — 604 연결 매수 중 게이트가 실제로 거른 건 기준\n")
    say("매수일 `d` 별 `(n_d, k_d)`: 604-연결 매수 중 그날 건수(`n_d`)와 그중 게이트가 거른 건수(`k_d`).\n")
    closed = buys[buys["is_closed"]].copy()
    by_day = closed.groupby("buy_date").agg(n_d=("excluded", "size"), k_d=("excluded", "sum")).reset_index()
    by_day["k_d"] = by_day["k_d"].astype(int)
    by_day["degenerate"] = by_day["k_d"] == by_day["n_d"]
    say("| 매수일 | n_d | k_d | 퇴화일? |")
    say("|---|---|---|---|")
    for r in by_day.itertuples(index=False):
        say(f"| {r.buy_date} | {r.n_d} | {r.k_d} | {'예' if r.degenerate else ''} |")
    say()
    degenerate_excluded = int(by_day.loc[by_day["degenerate"], "k_d"].sum())
    degenerate_share = degenerate_excluded / n_excluded_604 if n_excluded_604 > 0 else float("nan")
    say(f"퇴화일 배제건수(그런 날들의 `k_d` 합) = **{degenerate_excluded}**")
    say(f"퇴화일 비중 = {degenerate_excluded} / {n_excluded_604} = **{degenerate_share*100:.1f}%**" if n_excluded_604 > 0 else "퇴화일 비중 = 계산불가(n_excluded_604=0)")
    if n_excluded_604 == 0:
        say("⇒ n_excluded_604 = 0 이라 비중 계산 자체가 불가 — 그 자체로 카운트 문턱(§3) 미달과 같은 결론(판별불가).\n")
    elif not count_gate_pass:
        say("⇒ 카운트 문턱을 이미 벗어났으므로(§3) 이 비중은 «인쇄만» 하고 최종 판정에는 관여하지 않는다(§8-3 순서).\n")
    elif degenerate_share >= DEGENERATE_THRESHOLD:
        say(f"⇒ 🔴 **비중 {degenerate_share*100:.1f}% ≥ 1/3 — N0-strat 은 검정력 부족으로 「판별 불가」 자동 처리(§5-2).**\n")
    else:
        say(f"⇒ 비중 {degenerate_share*100:.1f}% < 1/3 — N0-strat 퇴화일 문턱 통과, 2단계에서 정상 계산 가능.\n")

    say("## 5. 결측 (§3-3) — 직전 20거래일 이력 20행 미만\n")
    missing_mask_646 = buys["range_med_20"].isna()
    missing_646 = int(missing_mask_646.sum())
    missing_604 = int((missing_mask_646 & buys["is_closed"]).sum())
    say(f"646 기준 결측 **{missing_646}**건, 그중 604 안에 **{missing_604}**건.")
    say("🔴 결측 건들의 평균 수익률은 이 턴에 계산하지 않는다(PnL 조회 금지 — 2단계 몫).\n")
    if missing_646:
        say("결측 건 상세(종목·매수일·전략·보유 이력 행수):\n")
        say("| 종목 | 매수일 | 전략 | 이력행수(<20) |")
        say("|---|---|---|---|")
        for r in buys[missing_mask_646].itertuples(index=False):
            say(f"| {r.stock_code} | {r.buy_date} | {r.strategy} | {r.n_rows_20} |")
        say()

    say("## 6. 0-range 봉 혼입 (§3-3) — 직전 20거래일 창에 high=low 봉\n")
    zr_646 = int(buys["zero_range_20"].sum())
    zr_604 = int((buys["zero_range_20"] & buys["is_closed"]).sum())
    say(f"646 기준 **{zr_646}**건 (그중 604 안 **{zr_604}**건, 참고).\n")

    say("## 7. 전략별 n_excluded (604 연결 기준) — G4(ma5·daytrading) 하한 10 포함\n")
    say("| 전략 | n_646 | excl_646 | n_604 | excl_604 | G4 대상 | 하한(10) 충족 |")
    say("|---|---|---|---|---|---|---|")
    for folder in STRATEGY_FOLDERS:
        g646 = buys[buys["strategy"] == folder]
        g604 = g646[g646["is_closed"]]
        e646 = int(g646["excluded"].sum())
        e604 = int(g604["excluded"].sum())
        is_g4 = folder in G4_STRATEGIES
        ok = "" if not is_g4 else ("✅" if e604 >= G4_MIN_EXCLUDED else "❌ 미달 → 검정력 부족 보고")
        say(f"| {folder} | {len(g646)} | {e646} | {len(g604)} | {e604} | {'예' if is_g4 else ''} | {ok} |")
    say()

    say("## 8. 부수 민감도 — N=10·40·60 의 n_excluded (🔴 판정에 안 씀, PREREG §4)\n")
    say("| N | excl_646 | excl_604 |")
    say("|---|---|---|")
    say(f"| 20(주) | {n_excluded_646} | {n_excluded_604} |")
    for n in N_SENSITIVITY:
        say(f"| {n} | {sens_excluded[n]['646']} | {sens_excluded[n]['604']} |")
    say()

    say("## 9. 어떤 컬럼만 SELECT 했는가 — PnL 미조회 보장\n")
    say("- `virtual_trading_records`: `id`(BUY 쿼리) · `stock_code` · `timestamp::date` · `strategy` · "
        "`action`(WHERE 절) · `buy_record_id`(SELL 쿼리, 연결 존재 확인용) · 🆕`stop_loss_rate`"
        "(2026-08-16 §10 개정 — 매수 시점 확정 파라미터, PIT. PnL 아님) — 이상 **7개 컬럼만**. "
        "`price`·`profit_rate`·`profit_loss`·`target_profit_rate` 는 **어디에서도 SELECT 하지 않았다.**")
    say("- `daily_prices`: `stock_code` · `date` · `high` · `low` · `close` — 4개 컬럼만. "
        "`volume`·`adj_factor`·`market_cap` 등은 SELECT 하지 않았다(비율 게이트라 불필요, §3-1).\n")

    # ══════════════════════════════════════════════════════════════════════
    # 🆕 §10 개정(2026-08-16, 결과 관측 전) — arm-B: 실제 stop_loss_rate 기준 게이트
    # ══════════════════════════════════════════════════════════════════════
    say("---\n")
    say("## 🆕 10. arm-B — 실제 `stop_loss_rate`(BUY 시점 저장값) 기준 게이트 (PREREG §10)\n")
    say("🔴 arm-A(§0~§9, 위)는 **원본 그대로 유지**했다 — 아래는 «추가»다. arm-A 와 arm-B 는 "
        "**다른 질문**이다(PREREG §10-2). 이 절도 §4 와 같은 순수 산출이며 해석은 없다.\n")

    say("### 10-1. 실제 stop_loss_rate vs config — narrower/same/wider(§10-1 실측 표)\n")
    say("`missing`(NULL)·`floor_clamped`(실제값이 정확히 0.03 인데 그 전략 config 는 0.03 이 아닌 건, "
        "narrower 의 부분집합)도 함께 센다. **646건(BUY 전체) 기준** — 관리자 눈대중(`reason` 문자열 기반 "
        "손절 368건 모집단, 손으로 추정 narrower≈98·wider≈24)과는 **모집단이 다르므로 직접 비교하지 않는다.**\n")
    say("| 전략 | n | narrower | same | wider | missing | floor_clamped |")
    say("|---|---|---|---|---|---|---|")
    tot_narrower = tot_same = tot_wider = tot_missing = tot_floor = 0
    for folder in STRATEGY_FOLDERS:
        g = nw_df[nw_df["strategy"] == folder]
        n_ = len(g)
        narrower = int((g["category"] == "narrower").sum())
        same = int((g["category"] == "same").sum())
        wider = int((g["category"] == "wider").sum())
        missing = int((g["category"] == "missing").sum())
        floor_c = int(g["floor_clamped"].sum())
        tot_narrower += narrower; tot_same += same; tot_wider += wider
        tot_missing += missing; tot_floor += floor_c
        say(f"| {folder} | {n_} | {narrower} | {same} | {wider} | {missing} | {floor_c} |")
    say(f"| **전체** | **{len(nw_df)}** | **{tot_narrower}** | **{tot_same}** | **{tot_wider}** | "
        f"**{tot_missing}** | **{tot_floor}** |\n")
    if tot_narrower > tot_wider:
        say(f"⇒ **narrower({tot_narrower}) > wider({tot_wider})** — 실제 손절선이 config 보다 "
            f"«더 좁은» 쪽으로 치우쳐 있다(§10-3 편향 방향).\n")
    elif tot_wider > tot_narrower:
        say(f"⇒ **wider({tot_wider}) > narrower({tot_narrower})** — 실제 손절선이 config 보다 "
            f"«더 넓은» 쪽으로 치우쳐 있다(§10-3 편향 방향과 반대 — 그대로 보고한다).\n")
    else:
        say(f"⇒ narrower({tot_narrower}) == wider({tot_wider}) — 치우침 없음.\n")

    say("### 10-2. arm-B n_excluded — 646 기준 / 604 기준\n")
    n_excluded_646_B = int(buys["excluded_B"].sum())
    excluded_604_mask_B = buys["excluded_B"] & buys["is_closed"]
    n_excluded_604_B = int(excluded_604_mask_B.sum())
    say(f"- **646 기준**: {n_excluded_646_B} / {n_646} (배제율 {n_excluded_646_B/n_646*100:.1f}%)")
    say(f"- **604 기준**: {n_excluded_604_B} / {n_604} (배제율 {n_excluded_604_B/n_604*100:.1f}%)\n")

    say("### 10-3. 🔴 arm-B 카운트 문턱 판정 — [30, 403) (PREREG §10-5)\n")
    count_gate_pass_B = N_EXCLUDED_LOW <= n_excluded_604_B < N_EXCLUDED_HIGH
    say(f"604 기준 n_excluded_B = **{n_excluded_604_B}**.")
    if count_gate_pass_B:
        say("⇒ **[30, 403) 안 — 카운트 문턱 통과.** arm-B 의 G1~G4 계산이 2단계에서 유효할 자격이 있다.\n")
    else:
        reason_b = "< 30 (배제율 5% 미만)" if n_excluded_604_B < N_EXCLUDED_LOW else "≥ 403 (배제율 2/3 초과)"
        say(f"⇒ 🔴 **[30, 403) 밖 — {reason_b}. arm-B 는 결과와 무관하게 자동 「검정력 부족 → "
            f"판별불가」로 확정된다(PREREG §10-5). arm-A 만 진행한다.** 아래 퇴화일은 투명성을 위해 "
            f"그대로 계산·인쇄한다.\n")

    say("### 10-4. arm-B 퇴화일 (§5-2 원칙, PREREG §10-5) — 604 연결 매수 중 arm-B 가 실제로 거른 건 기준\n")
    closed_B = buys[buys["is_closed"]].copy()
    by_day_B = closed_B.groupby("buy_date").agg(
        n_d=("excluded_B", "size"), k_d=("excluded_B", "sum")
    ).reset_index()
    by_day_B["k_d"] = by_day_B["k_d"].astype(int)
    by_day_B["degenerate"] = by_day_B["k_d"] == by_day_B["n_d"]
    say("| 매수일 | n_d | k_d | 퇴화일? |")
    say("|---|---|---|---|")
    for r in by_day_B.itertuples(index=False):
        say(f"| {r.buy_date} | {r.n_d} | {r.k_d} | {'예' if r.degenerate else ''} |")
    say()
    degenerate_excluded_B = int(by_day_B.loc[by_day_B["degenerate"], "k_d"].sum())
    degenerate_share_B = (
        degenerate_excluded_B / n_excluded_604_B if n_excluded_604_B > 0 else float("nan")
    )
    say(f"퇴화일 배제건수(그런 날들의 `k_d` 합) = **{degenerate_excluded_B}**")
    if n_excluded_604_B > 0:
        say(f"퇴화일 비중 = {degenerate_excluded_B} / {n_excluded_604_B} = **{degenerate_share_B*100:.1f}%**")
    else:
        say("퇴화일 비중 = 계산불가(n_excluded_604_B=0)")
    if n_excluded_604_B == 0:
        say("⇒ n_excluded_604_B = 0 이라 비중 계산 자체가 불가 — 카운트 문턱 미달과 같은 결론(판별불가).\n")
    elif not count_gate_pass_B:
        say("⇒ 카운트 문턱을 이미 벗어났으므로 이 비중은 «인쇄만» 하고 최종 판정에는 관여하지 않는다.\n")
    elif degenerate_share_B >= DEGENERATE_THRESHOLD:
        say(f"⇒ 🔴 **비중 {degenerate_share_B*100:.1f}% ≥ 1/3 — arm-B 는 검정력 부족으로 「판별 불가」 "
            f"자동 처리(PREREG §10-5).**\n")
    else:
        say(f"⇒ 비중 {degenerate_share_B*100:.1f}% < 1/3 — arm-B 퇴화일 문턱 통과, 2단계에서 정상 계산 가능.\n")

    arm_b_verdict = "판별불가" if not count_gate_pass_B else (
        "판별불가(퇴화일)" if (n_excluded_604_B > 0 and degenerate_share_B >= DEGENERATE_THRESHOLD)
        else "유효(2단계 진행 가능)"
    )
    say(f"### 10-5. arm-B 종합 판정 — **{arm_b_verdict}**\n")

    say("### 10-6. arm-B 결측(`stop_loss_rate` NULL) — §10-4 원칙(보수적 «유지»)\n")
    missing_sl_646 = int(buys["stop_loss_missing"].sum())
    missing_sl_604 = int((buys["stop_loss_missing"] & buys["is_closed"]).sum())
    say(f"646 기준 `stop_loss_rate` 결측 **{missing_sl_646}**건, 그중 604 안에 **{missing_sl_604}**건.")
    say("🔴 결측 건은 gate_pass_B=TRUE(«유지»)로 보수적 처리했다(§10-4, §3-3 과 동일 원칙) — "
        "결측이 있었다면 그 건들의 평균 수익률은 이 턴에 계산하지 않는다(PnL 조회 금지, 2단계 몫).\n")

    say("### 10-7. 전략별 arm-B n_excluded (604 연결 기준) — G4(ma5·daytrading) 하한 10\n")
    say("| 전략 | n_646 | excl_646_B | n_604 | excl_604_B | G4 대상 | 하한(10) 충족 |")
    say("|---|---|---|---|---|---|---|")
    for folder in STRATEGY_FOLDERS:
        g646b = buys[buys["strategy"] == folder]
        g604b = g646b[g646b["is_closed"]]
        e646b = int(g646b["excluded_B"].sum())
        e604b = int(g604b["excluded_B"].sum())
        is_g4 = folder in G4_STRATEGIES
        ok = "" if not is_g4 else ("✅" if e604b >= G4_MIN_EXCLUDED else "❌ 미달 → 검정력 부족 보고")
        say(f"| {folder} | {len(g646b)} | {e646b} | {len(g604b)} | {e604b} | {'예' if is_g4 else ''} | {ok} |")
    say()

    say("### 10-8. arm-A vs arm-B 교차표 — 어느 건이 갈리는가 (646 전체)\n")
    both = int((buys["excluded"] & buys["excluded_B"]).sum())
    a_only = int((buys["excluded"] & ~buys["excluded_B"]).sum())
    b_only = int((~buys["excluded"] & buys["excluded_B"]).sum())
    neither = int((~buys["excluded"] & ~buys["excluded_B"]).sum())
    say("| | arm-B 배제 | arm-B 유지 | 합계 |")
    say("|---|---|---|---|")
    say(f"| **arm-A 배제** | {both}(둘 다) | {a_only}(A만) | {both + a_only} |")
    say(f"| **arm-A 유지** | {b_only}(B만) | {neither}(둘 다 아님) | {b_only + neither} |")
    say(f"| **합계** | {both + b_only} | {a_only + neither} | {n_646} |\n")

    both604 = int((excluded_604_mask & excluded_604_mask_B).sum())
    a_only604 = int((excluded_604_mask & ~excluded_604_mask_B).sum())
    b_only604 = int((~excluded_604_mask & excluded_604_mask_B).sum())
    neither604 = n_604 - both604 - a_only604 - b_only604
    say("604(청산완료) 부분집합만:\n")
    say("| | arm-B 배제 | arm-B 유지 | 합계 |")
    say("|---|---|---|---|")
    say(f"| **arm-A 배제** | {both604}(둘 다) | {a_only604}(A만) | {both604 + a_only604} |")
    say(f"| **arm-A 유지** | {b_only604}(B만) | {neither604}(둘 다 아님) | {b_only604 + neither604} |")
    say(f"| **합계** | {both604 + b_only604} | {a_only604 + neither604} | {n_604} |\n")

    say("## 🔴 실행 중 관찰한 것(사전등록 이행 관련, 해석 아님)\n")
    say("- `range_med_N` 은 `(high−low)/close` 비율이라 `adj_factor` 미적용(§3-1·§8-7 그대로).")
    say("- 「직전 N 거래일」은 그 종목의 `daily_prices` 실제 존재일 기준, 매수일 자체는 `date < buy_date` "
        "로 제외했다(§3-1 계약대로 — 매수 «당일» 고가·저가를 쓰지 않았다).")
    say("- 결측 처리(§3-3)는 게이트 판정에서 `gate_pass=TRUE`(«유지»)로 보수적으로 처리했다 — "
        "실행 코드가 이 규칙을 어기지 않았음을 위 §5 표로 확인할 수 있다(결측 건은 전부 `gate_pass=TRUE`).")
    say("- 🆕 arm-B(§10) 도 같은 원칙으로 결측을 «유지» 처리했다 — §10-6 표로 확인 가능.")

    (BASE / "GATE.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] GATE.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
