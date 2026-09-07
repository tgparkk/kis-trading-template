"""스펙 B §8 shadow 평가 — 읽기 전용. 연구 트리(scripts/). 운영 코드에서 import 금지.

세 표를 낸다:
  ① 섹터 점수 유효성: sector_news_score.score_signed vs 같은 날 sector_daily_stats.ret_median(ksic3)
     — 일자별 Spearman · 상위/하위 5분위 ret_median 중앙값 차
  ② 후보 수준: live 였다면 slots 안에 «들어왔을»(entered) vs «밀려났을»(displaced) 종목의 5거래일 수익률 차, 전략별
     (slots 안 순서 변화만 있는 날은 top3_in/top3_out 으로 같은 표)
  ③ 이동 규모·결측: 전략×reason 일수 · 일평균 이동 종목 수

사용:
  PYTHONUTF8=1 python scripts/eval_sector_news_shadow.py --from 2026-09-29 --to 2026-10-27 [--slots 20] [--csv-dir D:/tmp/sector_eval]

주의: 09:00 이전 값 = 그날 sector_news_score 행 자체(NewsQuant 가 09:05~15:30 동결하므로).
      daily_prices.date 는 text 'YYYY-MM-DD'. close 는 이미 분할조정 — adj_factor 를 곱하지 않는다.
      ① 표는 살아남은 sector_news_score 행을 쓴다 — NewsQuant 는 09:05~15:30 사이 쓰기를 동결하지만,
      09:00~09:05 사이의 실행이 봇이 읽은 행을 덮어썼을 수 있다. "봇이 실제로 본" 값은 그 시점에
      기록된 sector_news_rerank_log.score_asof / sector_score 만이 권위 있는 값이며, ②·③ 표는
      이 로그 값을 사용한다.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Q_SECTOR = """
SELECT s.trade_date, s.sector_key, s.score_signed, s.n_dir, d.ret_median
FROM sector_news_score s
JOIN sector_daily_stats d
  ON d.date = s.trade_date AND d.taxonomy = 'ksic3' AND d.sector_key = s.sector_key
WHERE s.taxonomy = 'ksic3' AND s.trade_date BETWEEN %s AND %s
"""
Q_LOG = """
SELECT trade_date, strategy, stock_code, sector_key, sector_score, orig_rank, new_rank, applied, mode, reason
FROM sector_news_rerank_log
WHERE trade_date BETWEEN %s AND %s
"""
Q_PRICES = """
SELECT stock_code, date, close FROM daily_prices
WHERE stock_code = ANY(%s) AND date BETWEEN %s AND %s
ORDER BY stock_code, date
"""


# ── 순수 헬퍼 (테스트 대상) ──────────────────────────────────────────────────
def sector_validity(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for td, g in df.groupby("trade_date"):
        g = g[g["score_signed"] != 0]
        if len(g) < 5:
            out.append({"trade_date": td, "n": len(g), "spearman": None, "q5_minus_q1": None})
            continue
        rho = g["score_signed"].corr(g["ret_median"], method="spearman")
        q = pd.qcut(g["score_signed"].rank(method="first"), 5, labels=False)
        top = g.loc[q == 4, "ret_median"].median()
        bot = g.loc[q == 0, "ret_median"].median()
        out.append({"trade_date": td, "n": len(g), "spearman": float(rho), "q5_minus_q1": float(top - bot)})
    return pd.DataFrame(out, columns=["trade_date", "n", "spearman", "q5_minus_q1"])


def classify_transitions(log: pd.DataFrame, slots: int = 20) -> pd.DataFrame:
    def _g(r):
        if r.new_rank <= slots < r.orig_rank:
            return "entered"
        if r.orig_rank <= slots < r.new_rank:
            return "displaced"
        if r.new_rank <= 3 < r.orig_rank:
            return "top3_in"
        if r.orig_rank <= 3 < r.new_rank:
            return "top3_out"
        return None
    df = log.copy()
    df["group"] = df.apply(_g, axis=1) if len(df) else pd.Series(dtype=object)
    return df[df["group"].notna()]


def forward_return(prices: pd.DataFrame, stock_code: str, d0: str, n: int = 5) -> Optional[float]:
    s = prices[(prices["stock_code"] == stock_code) & (prices["date"] >= d0)].sort_values("date").reset_index(drop=True)
    if len(s) < n + 1 or s.loc[0, "date"] != d0:
        return None
    c0, cn = float(s.loc[0, "close"]), float(s.loc[n, "close"])
    if c0 <= 0:
        return None
    return cn / c0 - 1


def reason_distribution(log: pd.DataFrame) -> pd.DataFrame:
    df = log.copy()
    df["moved"] = (df["new_rank"] != df["orig_rank"]).astype(int)
    days = df.groupby(["strategy", "trade_date"]).agg(reason=("reason", "first"), moved=("moved", "sum")).reset_index()
    return days.groupby(["strategy", "reason"]).agg(days=("trade_date", "nunique"), avg_moved=("moved", "mean")).reset_index()


# ── DB 읽기 (읽기 전용) ─────────────────────────────────────────────────────
def _fetch(conn, sql: str, params) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=cols)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="스펙 B shadow 평가 (읽기 전용)")
    ap.add_argument("--from", dest="d_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="d_to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--slots", type=int, default=20)
    ap.add_argument("--csv-dir", default=None)
    args = ap.parse_args(argv)

    from db.kis_db_connection import KisDbConnection   # 기본값 localhost:5433/kis_template/robotrader
    KisDbConnection.initialize()
    with KisDbConnection.get_connection() as conn:
        sec = _fetch(conn, Q_SECTOR, (args.d_from, args.d_to))
        log = _fetch(conn, Q_LOG, (args.d_from, args.d_to))
        trans = classify_transitions(log, slots=args.slots) if len(log) else log.iloc[0:0]
        codes = sorted(trans["stock_code"].unique().tolist()) if len(trans) else []
        p_to = (date.fromisoformat(args.d_to) + timedelta(days=20)).isoformat()
        prices = _fetch(conn, Q_PRICES, (codes, args.d_from, p_to)) if codes else pd.DataFrame(columns=["stock_code", "date", "close"])

    pd.set_option("display.width", 200)
    print("\n① 섹터 점수 유효성 (일자별)")
    t1 = sector_validity(sec) if len(sec) else pd.DataFrame(columns=["trade_date", "n", "spearman", "q5_minus_q1"])
    print(t1.to_string(index=False))
    if len(t1):
        valid = t1.dropna(subset=["spearman"])
        print(f"  요약: 일수 {len(t1)} · spearman>0 일수 {(valid['spearman'] > 0).sum()}/{len(valid)} · q5−q1 중앙값 {valid['q5_minus_q1'].median():.4f}")

    print("\n② 후보 수준 (전략×그룹, 5거래일 수익률)")
    if len(trans):
        trans = trans.copy()
        trans["fwd5"] = [forward_return(prices, r.stock_code, str(r.trade_date), 5) for r in trans.itertuples()]
        t2 = trans.groupby(["strategy", "group"]).agg(n=("stock_code", "size"), n_ret=("fwd5", "count"), mean_fwd5=("fwd5", "mean")).reset_index()
        print(t2.to_string(index=False))
    else:
        t2 = pd.DataFrame()
        print("  (이동 행 없음)")

    print("\n③ 이동 규모·결측 (전략×reason)")
    t3 = reason_distribution(log) if len(log) else pd.DataFrame(columns=["strategy", "reason", "days", "avg_moved"])
    print(t3.to_string(index=False))

    if args.csv_dir:
        out = Path(args.csv_dir)
        out.mkdir(parents=True, exist_ok=True)
        t1.to_csv(out / "1_sector_validity.csv", index=False, encoding="utf-8-sig")
        t2.to_csv(out / "2_candidate_transitions.csv", index=False, encoding="utf-8-sig")
        t3.to_csv(out / "3_reason_distribution.csv", index=False, encoding="utf-8-sig")
        print(f"\nCSV 저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
