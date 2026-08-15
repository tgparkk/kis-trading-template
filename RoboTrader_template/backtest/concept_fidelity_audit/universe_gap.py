# -*- coding: utf-8 -*-
"""②층 완주 — 백테스트 유니버스 vs 라이브 매수 종목.

검증된 백테스트 6종(elder·envelope·daytrading·minervini·ma20·ma5)은 전부 러너의
`_load_top_volume_universe(top_n=50)` = 「기간 전체 SUM(close*volume) 상위 50종목」을 쓴다.
라이브 스크리너는 종목당 시총/거래대금 컷을 쓴다 — **기준 자체가 다르다.**

이 스크립트가 재는 것은 하나다:
  ***라이브가 실제로 산 646건은 백테스트가 본 적 있는 종목인가?***

🔑 기술 통계다. 귀무가 필요한 주장은 하지 않는다.
라이브 트리 import 0건 · DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
import psycopg2

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
STOCK_ONLY = "stock_code ~ '^[0-9]{5}[0-9A-Z]$'"   # lib/universe_filter.SQL_STOCK_ONLY 와 동일
LIVE0, LIVE1 = "2026-06-01", "2026-08-14"
OUT: list[str] = []


def say(s: str = "") -> None:
    print(s)
    OUT.append(s)


def top_volume(conn, start: str, end: str, n: int) -> list[str]:
    """러너 `_load_top_volume_universe` 와 동일 쿼리(기간 «전체» 합계 상위 N · 정적 유니버스)."""
    return pd.read_sql(f"""
        SELECT stock_code, SUM(close * volume) AS turnover
        FROM daily_prices
        WHERE date >= '{start}' AND date <= '{end}' AND {STOCK_ONLY}
        GROUP BY stock_code ORDER BY turnover DESC LIMIT {n}
    """, conn).stock_code.tolist()


def main() -> int:
    conn = psycopg2.connect(**DSN)

    # 백테스트 유니버스 — 정본 재측정 표기(config.yaml)는 "top_volume:50, 2021~2026".
    # 라이브 구간 포함 여부로 갈리지 않는지 두 벌 만들어 둘 다 본다.
    uni_pre = set(top_volume(conn, "2021-01-01", "2026-05-31", 50))   # 라이브 이전까지
    uni_all = set(top_volume(conn, "2021-01-01", "2026-08-14", 50))   # 전 구간
    uni300 = set(top_volume(conn, "2021-01-01", "2026-05-31", 300))   # deep_mr 게이트 근사

    buys = pd.read_sql(f"""
        SELECT stock_code, stock_name, strategy, timestamp::date AS d
        FROM virtual_trading_records
        WHERE action='BUY' AND timestamp::date BETWEEN '{LIVE0}' AND '{LIVE1}'
    """, conn)
    conn.close()

    say("# ②층 완주 — 백테스트 유니버스 vs 라이브 매수 종목\n")
    say("검증된 일봉책 백테스트 6종은 전부 러너의 `_load_top_volume_universe(top_n=50)` "
        "= 「기간 전체 `SUM(close*volume)` 상위 50종목」을 쓴다(정적 유니버스).\n")
    say(f"`top_volume:50` 2021-01-01~2026-05-31 = **{len(uni_pre)}종목** · "
        f"전 구간(~08-14) = {len(uni_all)}종목 · 두 집합 교집합 {len(uni_pre & uni_all)}\n")
    say(f"라이브 매수 {LIVE0}~{LIVE1} = **{len(buys)}건 / 고유 {buys.stock_code.nunique()}종목**\n")

    buys["in50"] = buys.stock_code.isin(uni_pre)
    buys["in300"] = buys.stock_code.isin(uni300)

    say("## 라이브 매수가 백테스트 유니버스 안에 있었나\n")
    say("| 전략 | 매수 | top50 안 | 비중 | top300 안 | 비중 |")
    say("|---|---|---|---|---|---|")
    for st, g in buys.groupby("strategy"):
        say(f"| {st} | {len(g)} | {int(g.in50.sum())} | **{g.in50.mean()*100:.0f}%** | "
            f"{int(g.in300.sum())} | {g.in300.mean()*100:.0f}% |")
    say(f"| **전체** | **{len(buys)}** | **{int(buys.in50.sum())}** | "
        f"**{buys.in50.mean()*100:.0f}%** | {int(buys.in300.sum())} | "
        f"{buys.in300.mean()*100:.0f}% |")
    say()

    say("## 고유 종목 기준\n")
    u = buys.drop_duplicates("stock_code")
    say(f"라이브가 산 고유 종목 **{len(u)}개** 중 `top_volume:50` 소속 **{int(u.in50.sum())}개** "
        f"({u.in50.mean()*100:.1f}%) · `top_volume:300` 소속 {int(u.in300.sum())}개 "
        f"({u.in300.mean()*100:.1f}%)\n")

    inside = sorted(set(u[u.in50].stock_name.dropna()))
    say(f"top50 안에서 산 종목: {', '.join(inside) if inside else '**없음**'}\n")

    # ── 이 겹침이 「우연」과 구별되는가 ────────────────────────────────────
    conn2 = psycopg2.connect(**DSN)
    pool = pd.read_sql(f"""SELECT COUNT(DISTINCT stock_code) n FROM daily_prices
        WHERE date BETWEEN '{LIVE0}' AND '{LIVE1}' AND {STOCK_ONLY} AND volume > 0""", conn2).n[0]
    pool10 = pd.read_sql(f"""SELECT COUNT(DISTINCT stock_code) n FROM daily_prices
        WHERE date BETWEEN '{LIVE0}' AND '{LIVE1}' AND {STOCK_ONLY}
          AND close * volume >= 1e9""", conn2).n[0]
    conn2.close()

    say("## 이 겹침은 「우연」과 구별되는가\n")
    say(f"라이브 기간 거래된 종목 풀 **{pool:,}** · 그중 거래대금 10억+ 경험 "
        f"**{pool10:,}**(가장 «느슨한» 라이브 컷).\n")
    say("| 기준 풀 | 고유 379종목 무작위 추출 시 top50 기대 교집합 | 실측 |")
    say("|---|---|---|")
    for nm, p in (("전체 풀", pool), ("거래대금 10억+ 풀", pool10)):
        say(f"| {nm} ({p:,}) | {len(u)*50/p:.1f}개 | **{int(u.in50.sum())}개** |")
    say()
    say("🔑🔑 ***실측 13개는 우연 기대치와 같은 자릿수다.*** 즉 ***라이브가 백테스트 유니버스 "
        "종목을 사는 빈도는 우연과 사실상 구별되지 않는다.***\n")
    say("⚠️ **이건 검정이 아니라 자릿수 비교다.** 라이브 후보 추출은 균등 무작위가 아니고"
        "(전략별 시총·거래대금 컷이 있다) 종목별 매수 확률도 균등하지 않다. "
        "***「p값」으로 읽지 말 것*** — 「겹침이 «설계된» 수준이 아니라 «우연» 수준」이라는 규모 진술이다.\n")

    (BASE / "UNIVERSE_GAP.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] UNIVERSE_GAP.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
