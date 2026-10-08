"""결과 없는 서술 진단(사전등록 근거) — signals.csv + 원장 순위 열만 읽는다.

    python -X utf8 -m backtest.concept_axes.theme_rank.describe
"""
from __future__ import annotations

import pandas as pd

from backtest.concept_axes.theme_rank import build_arena as BA
from backtest.concept_axes.theme_rank import stats as ST


def main() -> int:
    sig = pd.read_csv(BA.OUT / "signals.csv", dtype={"stock_code": str})
    s = pd.to_numeric(sig["s"], errors="coerce")
    n_day = sig.groupby("scan_date").size()
    rank = sig.groupby("scan_date").cumcount() + 1                      # load_keys 가 (d, rank) 순으로 썼다
    corr = pd.Series({d: ST.spearman(g["s"], rank.loc[g.index]) for d, g in sig.assign(s=s).groupby("scan_date")})
    top3 = sig.assign(s=s, r=rank).sort_values(["scan_date", "s"], ascending=[True, False]).groupby("scan_date").head(3)
    dup = top3[top3["main_theme"].notna()].groupby(["scan_date", "main_theme"]).size()
    days_dup = dup[dup >= 2].index.get_level_values(0).nunique()
    lines = ["# 서술 진단 — 결과 없음", "",
             f"- 경기장 키 {len(sig):,} · 날짜 {n_day.size} · 하루 키 중앙 {int(n_day.median())} · 최대 {int(n_day.max())}",
             f"- S 계산률 {sig['s_input_ok'].astype(str).eq('True').mean():.3f}",
             f"- S = 0 비율 {(s == 0).mean():.3f} · 단독 재료 비율 {sig['single'].astype(str).eq('True').mean():.3f}",
             f"- 하루 안 Spearman(S, 현재 순위) 평균 {corr.mean():+.3f}(유효 {corr.notna().sum()}일)",
             f"- S 상위 3 안 같은 주 테마 2종목 이상인 날 {days_dup}/{n_day.size}",
             f"- 주 테마 상위 10: {sig['main_theme'].dropna().astype(int).value_counts().head(10).to_dict()}"]
    BA.write_lf(BA.OUT / "DESCRIBE.md", "\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
