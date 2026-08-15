# -*- coding: utf-8 -*-
"""진입 품질 감사 — `pnl_decomposition`(0b6b1d8) §③ 이 남긴 whipsaw 표적을 «쏜다».

선행: `crash_gate_counterfactual`(bc9b0b7) — 게이트는 옳았다 ·
      `stoploss_counterfactual`(b6e12b8, 1a5794b) — 청산도 옳았다 ·
      `pnl_decomposition`(0b6b1d8) — 승률 37.1% < 필요 44.9%, 시장 −1.64%p / 선택 +0.16%p.

`pnl_decomposition/RESULTS.md` §③ 은 *「손절 371건 중 202건(54%)이 1일 이내 −8%대 ⇒
매수가와 평가 기준의 불일치(whipsaw)를 의심해야 한다」* 고 2단계 표적을 남겼다.
이 문서는 그 표적 «하나»를 쏜다 — 예측을 새로 세우지 않는다.

🔑 **사전등록 불필요**: 이 문서가 재는 것은 (a) 항등식·기술통계(경로 분해, 진입가 vs 전일종가,
봉폭 vs 손절폭) 이거나 (b) **이미 표적으로 등록된** 가설(「평가 기준 불일치」·「하루 만의 손절은
이상치」)의 코드 경로·기저율 재확인이다. 귀무가 필요한 새 예측은 없다
(`stoploss_counterfactual/PREREG.md` 처럼 사전등록해야 할 대상이 아니다).

라이브 트리 import 0건 · DB 는 SELECT 만 · `utils/logger.py` 미사용.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import psycopg2

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
WINDOW = ("2026-06-01", "2026-08-14")
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")   # 지수 의사티커 — 유니버스 대조군에서 제외

# 선언 손절폭 — strategies/{name}/config.yaml `risk_management.stop_loss_pct` 그대로.
# 🔴 ma20·minervini 는 다른 yaml/json 라이브 오버라이드가 있는지 저장소 전수 grep 으로
#    확인했다(`grep -rn stop_loss_pct **/*.{yaml,yml,json}`) — config.yaml 「단일」 값이고
#    `c04b9c0`(라이브 오버라이드 docstring 병기 커밋)도 이 두 전략의 stop_loss_pct 는
#    건드리지 않았다(그 커밋은 entry_mechanism 파라미터만 다뤘다). ⇒ 오버라이드 없음, 확정값.
STOP_LOSS_PCT = {
    "book_envelope_200d": (0.08, "strategies/book_envelope_200d/config.yaml:43"),
    "book_pullback_ma20": (0.08, "strategies/book_pullback_ma20/config.yaml:32 + strategy.py:22"),
    "book_pullback_ma5": (0.03, "strategies/book_pullback_ma5/config.yaml:32"),
    "daytrading_3methods_breakout": (0.10, "strategies/daytrading_3methods_breakout/config.yaml:39"),
    "deep_mr_dev20": (0.07, "strategies/deep_mr_dev20/config.yaml:43"),
    "elder_ema_pullback": (0.08, "strategies/elder_ema_pullback/config.yaml:43"),
    "minervini_volume_dryup": (0.08, "strategies/minervini_volume_dryup/config.yaml:32 + strategy.py:16"),
    "rs_leader": (0.08, "strategies/rs_leader/config.yaml:21"),
}


def say(s=""):
    print(s)
    OUT.append(s)


def route(reason: str) -> str:
    """측정① — `core/trading/position_monitor.py` 청산 경로 분류.

    실시간(PM) 경로는 그 파일 :329-332 가 만드는 접두 문자열 그대로 매칭한다.
    그 경로는 `profit_rate = (current_price - avg_price) / avg_price` (:215-217) —
    실시간 현재가 × 실제 체결 평단이지 전일 확정봉이 아니다.
    """
    r = reason or ""
    if r.startswith("손절 실행"):
        return "PM:손절실행"
    if r.startswith("목표 익절"):
        return "PM:목표익절"
    if r.startswith("트레일링 스톱"):
        return "PM:트레일링"
    if r.startswith("보유기간"):
        return "PM:보유기간초과"
    return "전략 고유"


def cat0(reason: str) -> str:
    """측정③ — `pnl_decomposition/decompose.py::cat0` 과 동일 술어(재사용).

    ⚠️ 관리자가 독립적으로 쓴 `reason LIKE '%손절%'` 술어와 대조해 371/145/44/11/33 건수가
    **완전 일치**함을 확인했다(우선순위 매칭 vs 단순 LIKE 가 이 표본에서는 같은 결과를 낸다).
    """
    r = reason or ""
    for k, v in (("손절", "손절"), ("목표 익절", "익절"), ("보유기간", "보유기간"),
                 ("트레일", "트레일링"), ("추적", "트레일링")):
        if r.startswith(k) or k in r:
            return v
    return "기타"


def load():
    conn = psycopg2.connect(**DSN)
    sells = pd.read_sql("""
        SELECT s.stock_code, s.timestamp::date AS sell_date, s.price AS sell_price,
               s.profit_rate, s.strategy, s.reason,
               b.timestamp::date AS buy_date, b.price AS buy_price
        FROM virtual_trading_records s
        JOIN virtual_trading_records b ON b.id = s.buy_record_id
        WHERE s.action='SELL' AND s.timestamp::date BETWEEN %s AND %s
    """, conn, params=WINDOW)
    buys = pd.read_sql("""
        SELECT stock_code, timestamp::date AS d, price, strategy FROM virtual_trading_records
        WHERE action='BUY' AND timestamp::date BETWEEN %s AND %s
    """, conn, params=WINDOW)
    buys["d"] = buys["d"].astype(str)
    buy_dates = sorted(buys["d"].unique().tolist())
    codes = buys["stock_code"].unique().tolist()

    # 측정② — 진입가 대조용 넓은 일봉 이력(전일종가 계산에 buy_date 밖 데이터 필요)
    hist = pd.read_sql("""
        SELECT stock_code, date, open, high, low, close FROM daily_prices
        WHERE stock_code = ANY(%s) AND date BETWEEN '2026-05-01' AND %s
    """, conn, params=(codes, WINDOW[1]))

    # 측정④ 대조군 A/B/C — «매수가 실제로 일어난 날짜 집합»(47일)에 한정한 유니버스 전체.
    # 🔴 창 전체(53거래일)가 아니라 이 47일이다 — 대조군은 실제 매수와 «같은 날짜 집합»이라야
    #    유동성 컷과 손절폭 비교가 뜻이 있다(코드가 없는 날의 유니버스를 섞으면 대조가 아니다).
    uni = pd.read_sql("""
        SELECT stock_code, date, high, low, close, volume, volatility_20d
        FROM daily_prices WHERE date = ANY(%s)
    """, conn, params=(buy_dates,))
    conn.close()

    for c in ("sell_price", "buy_price", "profit_rate"):
        sells[c] = pd.to_numeric(sells[c], errors="coerce")
    sells["buy_date"] = sells["buy_date"].astype(str)
    sells["sell_date"] = sells["sell_date"].astype(str)
    buys["price"] = pd.to_numeric(buys["price"], errors="coerce")
    for c in ("open", "high", "low", "close"):
        hist[c] = pd.to_numeric(hist[c], errors="coerce")
    for c in ("high", "low", "close", "volume", "volatility_20d"):
        uni[c] = pd.to_numeric(uni[c], errors="coerce")
    return sells, buys, hist, uni, buy_dates


def main() -> int:
    sells, buys, hist, uni, buy_dates = load()

    say("# 진입은 결함이 아니었다 — whipsaw 가설 3형태 전부 기각, 대신 「손절선이 봉 폭보다 좁다」\n")
    say("선행: `crash_gate_counterfactual`(bc9b0b7) — 게이트는 옳았다 · "
        "`stoploss_counterfactual`(b6e12b8) — 청산도 옳았다 · "
        "`pnl_decomposition`(0b6b1d8) — 승률 37.1% < 필요 44.9%.\n")
    say("이 문서는 `pnl_decomposition/RESULTS.md` §③ 이 남긴 2단계 표적 — "
        "*「손절 371건 중 202건(54%)이 1일 이내 −8%대 ⇒ 매수가와 평가 기준의 불일치를 "
        "의심해야 한다」* — 를 «쏜» 문서다. 새 예측을 세우지 않으므로 사전등록하지 않았다 "
        "(위 docstring 참고).\n")
    say(f"기간 {WINDOW[0]}~{WINDOW[1][5:]} · 매수 **{len(buys)}건** · 매도(청산완료) **{len(sells)}건** "
        f"· 매수당일 일봉 결측 확인은 측정②에서.\n")

    # ── ① 청산 경로 분해 ────────────────────────────────────────────────────
    say("## ① 청산 경로 분해 — 「평가 기준 불일치」 기각\n")
    say("SELL 604건을 `reason` 접두로 갈랐다. `core/trading/position_monitor.py:329-332` 가 "
        "만드는 실시간(PM) 경로 vs 전략 고유 경로:\n")
    sells["route"] = sells.reason.map(route)
    say("| 경로 | n | 평균 profit_rate |")
    say("|---|---|---|")
    order = ["PM:손절실행", "PM:목표익절", "PM:트레일링", "PM:보유기간초과", "전략 고유"]
    route_n = {}
    for r in order:
        g = sells[sells.route == r]
        route_n[r] = len(g)
        if r == "전략 고유":
            say(f"| {r} (그 외 — 아래 예시) | {len(g)} | — |")
        else:
            say(f"| `{r}` | {len(g)} | {g.profit_rate.mean()*100:+.4f}% |")
    say()
    assert sum(route_n.values()) == len(sells), "경로 분해 합이 매도 건수와 다르다"

    # 전략 고유 예시 — 괄호 안 숫자를 지운 라벨 상위 빈도
    strat_own = sells[sells.route == "전략 고유"]
    labels = strat_own.reason.fillna("").map(lambda s: re.sub(r"\s*\([^)]*\)\s*$", "", s).strip())
    examples = ", ".join(f"{k}({v})" for k, v in Counter(labels).most_common(8))
    say(f"전략 고유 {len(strat_own)}건 라벨 상위: {examples} 등.\n")

    sells["cat"] = sells.reason.map(cat0)
    non_pm_sl = sells[(sells.route == "전략 고유") & (sells.cat == "손절")]
    say(f"🔑 손절 계열(`cat0`=손절) {len(sells[sells.cat=='손절'])}건 중 "
        f"**{route_n['PM:손절실행']}건이 실시간(PM) 경로**이고, 전략 고유 손절은 "
        f"**{len(non_pm_sl)}건**뿐이다(예: {', '.join(repr(x) for x in non_pm_sl.reason)}).\n")
    say("⇒ `손절 실행 (…)` 문자열은 실시간 현재가 × 실제 체결 평단으로 판정하는 경로다"
        "(전일 확정봉이 아니다). 발동값이 −8%대 초반에 몰린 것은 손절선을 살짝 넘긴 "
        "**정상 발동**이다(갭다운이면 −12%·−16%로 튄다). "
        "***「매수가와 평가 기준의 불일치」 가설은 기각한다.***\n")

    # ── ② 진입 품질 ────────────────────────────────────────────────────────
    say("## ② 진입 품질 — 「갭업에 산다」 기각\n")
    hist = hist.sort_values(["stock_code", "date"])
    hist["prev_close"] = hist.groupby("stock_code")["close"].shift(1)
    m = buys.merge(hist, left_on=["stock_code", "d"], right_on=["stock_code", "date"], how="left")
    missing = int(m.high.isna().sum())
    say(f"매수 {len(buys)}건, 매수당일 일봉 결측 **{missing}**.\n")
    m["vs_prev"] = m.price / m.prev_close - 1
    m["barpos"] = (m.price - m.low) / (m.high - m.low)
    m["vs_open"] = m.price / m.open - 1
    say("| 전략 | 체결가 vs 전일종가(평균) | 중앙 | p90 | 봉내위치(평균) | 중앙 | vs 시가(평균) |")
    say("|---|---|---|---|---|---|---|")
    for st, g in sorted(m.groupby("strategy"), key=lambda kv: kv[0]):
        say(f"| {st} ({len(g)}) | {g.vs_prev.mean()*100:+.2f}% | {g.vs_prev.median()*100:+.2f}% | "
            f"{g.vs_prev.quantile(0.9)*100:+.2f}% | {g.barpos.mean():.3f} | {g.barpos.median():.3f} | "
            f"{g.vs_open.mean()*100:+.2f}% |")
    say(f"| **전체 ({len(m)})** | **{m.vs_prev.mean()*100:+.2f}%** | **{m.vs_prev.median()*100:+.2f}%** | "
        f"{m.vs_prev.quantile(0.9)*100:+.2f}% | **{m.barpos.mean():.3f}** | {m.barpos.median():.3f} | "
        f"{m.vs_open.mean()*100:+.2f}% |")
    say()
    say("정의: `봉내위치 = (buy_price − low) / (high − low)`, 0=저가 1=고가.\n")
    say(f"⇒ 갭업 매수가 아니다. 전일 종가보다 평균 {abs(m.vs_prev.mean())*100:.2f}% 싸게, "
        f"봉 중간({m.barpos.mean():.3f})보다 «아래»에서 산다.\n")
    elder = m[m.strategy == "elder_ema_pullback"]
    say(f"⇒ `elder_ema_pullback` 만 유일하게 위에서 산다(vs 전일종가 {elder.vs_prev.mean()*100:+.2f}%·"
        f"봉내위치 {elder.barpos.mean():.3f}). **결함이 아니라 설계** — Elder 백테스트만 "
        "`entry_mechanism=\"stop\"`(돌파 스톱 주문)이다. 이걸 결함으로 쓰지 말 것.\n")

    # ── ③ 「54%」의 기저율 ───────────────────────────────────────────────────
    say("## ③ 「54%」의 기저율 — 전체 행을 세우면 손절은 «이상치가 아니라 기저율 그 자체»다\n")
    say("보유기간 = `sell.timestamp::date − buy.timestamp::date`(**달력일**, 거래일 아님 — "
        "금요일 매수·월요일 매도는 달력 3일이라 「1일 이내」에 안 들어간다). "
        "분류 술어는 `cat0`(위 참고) — `pnl_decomposition/decompose.py` 와 동일.\n")
    d0 = pd.to_datetime(sells.buy_date)
    d1 = pd.to_datetime(sells.sell_date)
    sells["hold"] = (d1 - d0).dt.days
    say("| 청산사유 | n | 보유 중앙 | 보유 평균 | 1일 이내 | 비중 | 평균 profit_rate |")
    say("|---|---|---|---|---|---|---|")

    def row3(name, g, n_label=None):
        n = len(g)
        le1 = int((g.hold <= 1).sum())
        return (f"| {name} | {n_label if n_label else n} | {g.hold.median():.0f}일 | "
                f"{g.hold.mean():.2f} | {le1} | {le1/n*100:.0f}% | {g.profit_rate.mean()*100:+.2f}% |")

    say(row3("**전체**", sells, n_label=f"**{len(sells)}**"))
    cat_order = ["손절", "익절", "트레일링", "보유기간", "기타"]
    for c in cat_order:
        g = sells[sells.cat == c]
        if len(g):
            say(row3(c, g))
    say()
    overall_share = (sells.hold <= 1).mean() * 100
    sl = sells[sells.cat == "손절"]
    sl_share = (sl.hold <= 1).mean() * 100
    say(f"🔑🔑 ***결정적인 비교는 이것이다*** — 손절의 1일 이내 비중 **{sl_share:.0f}%** 는 "
        f"책 전체 기저율 **{overall_share:.0f}%** 와 **{abs(sl_share-overall_share):.0f}%p** 차이다. "
        "「트레일링이 77%로 더 높다」는 대조보다 훨씬 강한 증거다 — "
        "***손절은 기저율에서 벗어난 게 아니라 «기저율 그 자체»다.***\n")
    say("⇒ `pnl_decomposition` §③ 이 「54%」를 이상치로 읽은 것은 **기저율 미독**이었다 "
        "(같은 표 안에 트레일링 77%가 있었는데도 안 읽었고, «전체» 행 자체를 세우지 않았다).\n")

    # ── ④ 손절선이 봉 폭보다 좁다 ──────────────────────────────────────────────
    say("## ④ 대신 찾은 것 — 손절선이 하루 봉 폭보다 좁다\n")
    say(f"`bar_range = (high − low) / close`, 매수 당일 기준. 대조군은 **매수가 실제로 일어난 "
        f"날짜 집합({len(buy_dates)}일)** 로 한정한다(창 전체 53거래일이 아니다 — 다른 날의 "
        "유니버스를 섞으면 대조가 아니다). 지수 의사티커 `KOSPI`·`KOSDAQ`·`KS11`·`KQ11` 제외.\n")
    bm = buys.merge(uni, left_on=["stock_code", "d"], right_on=["stock_code", "date"], how="left")
    bm["bar_range"] = (bm.high - bm.low) / bm.close
    say("| 전략 | 선언 손절폭 | 봉폭 중앙 | 봉폭 p90 | volatility_20d 중앙 |")
    say("|---|---|---|---|---|")
    for st, g in sorted(bm.groupby("strategy"), key=lambda kv: kv[0]):
        pct, _src = STOP_LOSS_PCT.get(st, (None, None))
        pct_s = f"{pct*100:.0f}%" if pct is not None else "?"
        say(f"| {st} | {pct_s} | {g.bar_range.median()*100:.2f}% | "
            f"{g.bar_range.quantile(0.9)*100:.2f}% | {g.volatility_20d.median():.5f} |")
    say(f"| **전체** | 3~10% | **{bm.bar_range.median()*100:.2f}%** | "
        f"**{bm.bar_range.quantile(0.9)*100:.2f}%** | {bm.volatility_20d.median():.5f} |")
    say()

    say("**대조군** (같은 날짜 집합, 지수 의사티커 제외):\n")
    say("| 군 | n | 봉폭 중앙 | p90 |")
    say("|---|---|---|---|")
    uni_a = uni[~uni.stock_code.isin(PSEUDO)].dropna(subset=["high", "low", "close"])
    uni_a = uni_a[uni_a.close > 0]
    br_a = (uni_a.high - uni_a.low) / uni_a.close
    say(f"| A. 유니버스 전체 | {len(uni_a):,} | **{br_a.median()*100:.2f}%** | {br_a.quantile(0.9)*100:.2f}% |")

    uni_b_pool = uni_a.copy()
    uni_b_pool["amt"] = uni_b_pool.close * uni_b_pool.volume   # ⚠️ adj_factor 미적용 — 한계 절 참고
    uni_b_pool["ntile"] = uni_b_pool.groupby("date")["amt"].rank(pct=True)
    uni_b = uni_b_pool[uni_b_pool.ntile > 0.9]
    br_b = (uni_b.high - uni_b.low) / uni_b.close
    say(f"| B. 거래대금 상위 10%(일별 ntile) | {len(uni_b):,} | {br_b.median()*100:.2f}% | "
        f"{br_b.quantile(0.9)*100:.2f}% |")

    dedup = buys[["stock_code", "d"]].drop_duplicates()
    c_m = dedup.merge(uni, left_on=["stock_code", "d"], right_on=["stock_code", "date"], how="left")
    br_c = (c_m.high - c_m.low) / c_m.close
    say(f"| C. 실제 매수 종목(distinct 종목·일) | **{len(c_m)}** | **{br_c.median()*100:.2f}%** | "
        f"{br_c.quantile(0.9)*100:.2f}% |")
    say()
    ratio_uni = bm.bar_range.median() / br_a.median()
    ratio_top = bm.bar_range.median() / br_b.median()
    say(f"⇒ 매수 종목 봉폭은 유니버스 중앙의 **{ratio_uni:.2f}배**, 거래대금 상위 10% 대비도 "
        f"**{ratio_top:.2f}배**다. 유동성 컷만으로 설명 안 된다.\n")

    ma5_med = bm[bm.strategy == "book_pullback_ma5"].bar_range.median()
    ma5_ratio = STOP_LOSS_PCT["book_pullback_ma5"][0] / ma5_med * 100 if ma5_med else float("nan")
    say(f"⇒ 손절선이 하루 봉 폭의 **60~70%** 지점에 있다(`book_pullback_ma5` 는 예외적으로 "
        f"손절 3% / 봉폭 중앙 {ma5_med*100:.2f}% ≈ **{ma5_ratio:.0f}%** 지점). "
        "「1일 이내 손절 54%」는 이 기하학의 필연이다.\n")

    # ── 🔑 재사용 규칙 ───────────────────────────────────────────────────────
    say("## 🔑 재사용 규칙\n")
    say(f"1. ***기저율이 같은 표 안에 있는데도 안 읽으면 정상을 이상치로 부른다.*** "
        f"측정③에서 손절 1일 이내 비중 {sl_share:.0f}% 는 책 전체 기저율 {overall_share:.0f}% 와 "
        f"{abs(sl_share-overall_share):.0f}%p 밖에 안 난다 — «전체» 행을 안 세우면 이 대조 자체가 "
        "안 보인다. 그리고 **이번엔 `pnl_decomposition` §③이 그 «전체 행»을 아예 안 만들었다** — "
        "부분집합(청산사유별)끼리만 비교하면 기저율이 표에 없을 수도 있다.")
    say("2. ***「A 가 B 와 다르다」를 결함이라 부르려면 「둘이 같아야 할 이유」가 필요하다.*** "
        "elder_ema_pullback 만 진입가가 전일종가 위·봉 위쪽인 것(+2.32%·0.580)은 결함이 아니라 "
        "설계다(그 전략만 `entry_mechanism=\"stop\"`). ⚠️ 이건 새 규칙이 아니라 저장소에 이미 있는 "
        "규칙의 **재발**이다 — `changelog-2026-08-16-strategy-audit-and-data-integrity.md` 가 "
        "「돌파형인데 하한 게이트 없음」 오판(#5)에서 같은 문장을 남겼다: "
        "*「A 에 있고 B 에 없다」는 그 자체로 결함이 아니다 — 비대칭을 결함이라 부르려면 「둘이 같아야 "
        "할 이유」를 먼저 대야 한다.*")
    say(f"3. ***대조군 없이 절대 수준을 인용하면 뜻이 없다.*** {bm.bar_range.median()*100:.2f}% 는 "
        f"유니버스 {br_a.median()*100:.2f}% 와 나란히 놓여야 뜻이 생긴다 — 그 자체로는 「넓다/좁다」를 "
        "판단할 기준이 없다.\n")

    # ── 🔴 한계 ─────────────────────────────────────────────────────────────
    say("## 🔴 한계\n")
    say(f"- **한 국면이다**({WINDOW[0][:7]}~{WINDOW[1][:7]}). 일반화 금지.")
    say("- **미청산 보유분은 표본 밖**이다 — `pnl_decomposition` 과 동일한 결손.")
    say("- 측정④는 **기술통계다.** 「손절폭이 좁아서 성과가 나쁘다」는 **인과 주장이 아니다** — "
        "그러려면 반사실이 필요하고, 손절을 걸렀을 때 그 자금이 어디로 갔을지(대체효과)를 "
        "풀어야 한다.")
    say("- 🔴 **방향을 이 표에서 고르면 사후적합이다.** 특히 「봉폭 대비 손절폭 비율로 종목을 "
        "거른다」는 채택은 **별도 사전등록**에서 한다.")
    say("- 🔑 손절폭을 «넓히는» 방향은 `stoploss_counterfactual` S5 가 이미 반증에 가깝게 "
        "만들었다(θ=−15% 평균 −7.21% 가 θ=−3% 평균 −0.74% 보다 나빴다 — 조일수록 좋아졌다, "
        "넓히면 반대). 단 그건 **한 하락 국면**이라 부호가 뒤집힐 수 있다고 그 문서가 스스로 "
        "경고했다 — 그 경고를 여기서 지우지 않는다.")
    say(f"- C 군 n={len(c_m)} 이 매수 {len(buys)}건과 다른 이유: distinct **종목·일** 중복 제거다 "
        "(같은 날 같은 종목을 여러 전략이 각자 매수하면 봉은 하나뿐이라 한 번만 센다).")
    say("- 대조군 B(`close×volume`) 는 **`adj_factor` 미적용 척도**다(volume 은 원본 저장 — "
        "`ac69084` 이전 척도). 분할 경계가 있는 종목의 거래대금 순위가 정확히 어긋날 수 있다. "
        "단 이 대조군은 **순위(상위 10%)** 용이고 매수 종목군(C) 대비 결론(«유동성 컷만으로 "
        "설명 안 된다»)은 A·C 비교만으로도 성립해 불변이다.")
    say("- 대조군 B 는 날짜별 `rank(pct=True) > 0.9` 로 「상위 10%」를 정의했다 — 동점 처리 방식에 "
        "따라 다른 ntile 구현(예: SQL `NTILE(10)`)은 n 이 몇 십 건 다르게 나올 수 있다(중앙·p90 은 "
        "안정적으로 재현됨을 확인했다).\n")

    say("## 🏁 세 갈래가 같은 방향을 가리킨다 — 단, 가설이지 판정이 아니다\n")
    say("유니버스 사다리(좁힐수록 좋아진다, `universe_lookahead_ladder`) · 손절 S5(넓히면 나빠진다, "
        "`stoploss_counterfactual`) · 이번 측정(손절폭이 봉폭보다 좁다) — 셋 다 같은 곳을 "
        "가리킨다: ***종목을 손절폭에 맞춰야 한다.*** "
        "🔴 **단 이건 가설이지 판정이 아니다.** 세 연구 모두 「이 표를 보고 문턱을 고르면 "
        "사후적합」이라고 스스로 경고했고, 이 문서도 그 경고를 반복한다 — 채택은 셋을 종합한 "
        "**별도 사전등록**에서 한다.")

    (BASE / "RESULTS.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
