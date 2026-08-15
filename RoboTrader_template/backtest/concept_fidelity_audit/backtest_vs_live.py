# -*- coding: utf-8 -*-
"""②층 완주 — 백테스트 «실측» 보유기간·청산사유를 ④ 라이브와 같은 단위로 나란히 놓는다.

초판 감사는 ③선언(config `max_hold`)과 ④라이브만 비교해 「5~50배 어긋났다」고 했다.
그러나 ***백테스트도 짧게 들고 있었다면 그건 「어긋난 것」이 아니라 「원래 그런 전략」***이다.
이 스크립트가 그 갈림을 잰다.

🔑 단위 함정: 라이브 원장은 «캘린더일», 백테스트 `idx` 는 «거래일(봉)» 이다.
   라이브를 KRX 거래일 달력으로 환산해 **양쪽 다 거래일**로 맞춘다.

기술 통계다. 귀무가 필요한 주장은 하지 않는다. 라이브 트리 import 0건 · DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
import psycopg2

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent           # RoboTrader_template/
DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
LIVE0, LIVE1 = "2026-06-01", "2026-08-14"
IDX_TICKERS = {"KOSPI", "KOSDAQ", "KS11", "KQ11"}
OUT: list[str] = []

# 라이브 config 와 «같은 variant» 인 백테스트 산출물만 쓴다.
# 🔴 envelope·ma20·rs_leader·deep_mr 는 라이브 config 와 일치하는 거래단위 산출물을
#    reports/ 에서 찾지 못했다 — 없는 것을 있는 척하지 않는다(아래 표에 명시).
ARTIFACTS = {
    "elder_ema_pullback":
        "reports/books_research/elder_triple_screen/results_variantA_single_triple_screen_ema_pullback.parquet",
    "daytrading_3methods_breakout":
        "reports/books_research/daytrading_3methods/results_variantB_single_breakout_prev_high.parquet",
    "minervini_volume_dryup":
        "reports/books_research/minervini_vcp/results_variantB_single_volume_dryup.parquet",
    "book_pullback_ma5":
        "reports/books_research/trading_legends/results_variantB_single_ma5_pullback.parquet",
}
MISSING = ["book_envelope_200d", "book_pullback_ma20", "rs_leader", "deep_mr_dev20"]

# 백테스트 reason → 공통 라벨
BT_CAT = {"stop_loss": "손절", "take_profit": "익절", "max_hold": "보유기간", "eod": "기타"}


def say(s: str = "") -> None:
    print(s)
    OUT.append(s)


def live_cat(reason: str | None) -> str:
    r = reason or ""
    for k, v in (("손절", "손절"), ("목표 익절", "익절"), ("보유기간", "보유기간"),
                 ("트레일", "트레일링"), ("추적", "트레일링")):
        if k in r:
            return v
    return "기타"


def load_live() -> pd.DataFrame:
    """라이브 청산 + KRX 거래일 달력으로 보유 «거래일» 산출."""
    conn = psycopg2.connect(**DSN)
    tr = pd.read_sql(f"""
        SELECT s.timestamp::date AS sell_d, s.strategy, s.reason,
               b.timestamp::date AS buy_d
        FROM virtual_trading_records s
        JOIN virtual_trading_records b ON b.id = s.buy_record_id
        WHERE s.action='SELL' AND s.timestamp::date BETWEEN '{LIVE0}' AND '{LIVE1}'
    """, conn)
    # KOSPI 의사티커 = KRX 개장일 달력(메모리 검증분: index_daily 와 상관 0.99999)
    cal = pd.read_sql(f"""
        SELECT DISTINCT date FROM daily_prices
        WHERE stock_code='KOSPI' AND date BETWEEN '2026-05-01' AND '{LIVE1}'
        ORDER BY date
    """, conn).date.astype(str).tolist()
    conn.close()
    pos = {d: i for i, d in enumerate(cal)}
    tr["buy_d"] = tr.buy_d.astype(str)
    tr["sell_d"] = tr.sell_d.astype(str)
    tr["hold"] = [
        pos[s] - pos[b] if (b in pos and s in pos) else None
        for b, s in zip(tr.buy_d, tr.sell_d)
    ]
    tr["cat"] = tr.reason.map(live_cat)
    return tr


def load_bt(path: str) -> pd.DataFrame | None:
    p = ROOT / path
    if not p.exists():
        return None
    d = pd.read_parquet(p)
    b = d[d.side == "buy"].reset_index(drop=True)
    s = d[d.side == "sell"].reset_index(drop=True)
    n = min(len(b), len(s))                       # 미청산 마지막 포지션 절사
    out = pd.DataFrame({
        "stock_code": b.stock_code[:n].values,
        "hold": (s.idx[:n].values - b.idx[:n].values),
        "reason": s.reason[:n].values,
        "pnl": s.pnl_pct[:n].values,
    })
    out["cat"] = out.reason.map(lambda r: BT_CAT.get(str(r), "기타"))
    return out


def main() -> int:
    live = load_live()
    say("# ②↔④ 백테스트 실측 vs 라이브 실측 — 같은 단위(거래일)로\n")
    say("초판 감사는 **③선언 `max_hold` vs ④라이브**만 비교해 「5~50배 어긋났다」고 했다. "
        "이 표는 그 비교에 **②백테스트 실측**을 넣어 ***「라이브가 어긋난 것」인지 "
        "「원래 그런 전략」인지***를 가른다.\n")
    say("🔑 **단위를 맞췄다** — 라이브 원장은 캘린더일이라 KRX 거래일 달력으로 환산했다. "
        "백테스트 `idx` 는 원래 거래일(봉)이다.\n")

    say("## 보유기간 (거래일)\n")
    say("| 전략 | 선언 max_hold | 백테스트 중앙 | 라이브 중앙 | 백테스트 ≤1일 | 라이브 ≤1일 | 판정 |")
    say("|---|---|---|---|---|---|---|")
    for st, path in ARTIFACTS.items():
        bt = load_bt(path)
        lv = live[live.strategy == st].dropna(subset=["hold"])
        if bt is None or lv.empty:
            say(f"| {st} | — | 산출물 없음 | — | — | — | — |")
            continue
        bm, lm = bt.hold.median(), lv.hold.median()
        b1, l1 = (bt.hold <= 1).mean() * 100, (lv.hold <= 1).mean() * 100
        verdict = "🟢 원래 그렇다" if abs(bm - lm) <= 1 and abs(b1 - l1) <= 15 else "🔴 라이브가 더 짧다"
        say(f"| {st} | — | **{bm:.0f}일** (n={len(bt)}) | **{lm:.0f}일** (n={len(lv)}) | "
            f"{b1:.0f}% | {l1:.0f}% | {verdict} |")
    for st in MISSING:
        say(f"| {st} | — | 🔴 **라이브 config 일치 산출물 미발견** | — | — | — | 미판정 |")
    say()

    say("## 청산 사유 비중 (%)\n")
    say("| 전략 | | 손절 | 익절 | 보유기간 | 트레일링/기타 |")
    say("|---|---|---|---|---|---|")
    for st, path in ARTIFACTS.items():
        bt, lv = load_bt(path), live[live.strategy == st]
        if bt is None or lv.empty:
            continue
        for lbl, df in (("백테스트", bt), ("라이브", lv)):
            r = [f"{(df.cat == c).mean()*100:.0f}%" for c in ("손절", "익절", "보유기간")]
            other = (~df.cat.isin(["손절", "익절", "보유기간"])).mean() * 100
            say(f"| {st if lbl=='백테스트' else ''} | {lbl} | {r[0]} | {r[1]} | {r[2]} | {other:.0f}% |")
    say()

    say("## 🔴 한계\n")
    say("- 🔴 **비교 구간이 다르다.** 백테스트는 2021~2026 전 구간, 라이브는 **2026-06~08 한 국면**이다. "
        "***보유기간·손절비중은 국면에 강하게 의존하므로 이 표는 「같은 조건 비교」가 아니다.***")
    say("- 🔴🔴 **유니버스가 다르다** — 백테스트 `top_volume:50`, 라이브 매수의 97%가 그 밖이다"
        "([UNIVERSE_GAP.md](UNIVERSE_GAP.md)). ***엄밀히는 「같은 전략의 두 관측」이 아니다.***")
    say("- 🔴 **8전략 중 4전략만 대조했다.** 나머지 4는 라이브 config 와 일치하는 거래단위 산출물을 "
        "`reports/` 에서 찾지 못했다 — **없는 것을 추정으로 채우지 않았다.**")
    say("- ⚠️ 백테스트는 **종목당 단일 포지션 순차** 시뮬레이션이고 라이브는 **K 슬롯 포트폴리오**다. "
        "거래 «건수» 는 비교 불가, 거래 «당» 분포만 비교 가능하다.")
    say("- ⚠️ 산출물은 전부 **2026-05-31** 생성분이며 지수 의사티커 행이 "
        "**0.1~3.0%** 섞여 있다(`SQL_STOCK_ONLY` 도입 이전). 규모는 작지만 0 은 아니다.")

    (BASE / "BT_VS_LIVE.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] BT_VS_LIVE.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
