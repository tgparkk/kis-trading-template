"""가짜 표식 게이트 — 스펙 §3-5.

실제 표식 행은 버리고(수익을 읽지 않음) 남은 표본에서 실제 표식마다 같은 날·같은 p_L 5분위 후보에 가짜 표식을 붙인다
(같은 실제 종목 → 같은 가짜 종목 대응 · 실제 표식 종목은 풀에서 제외 · 풀 없으면 같은 날 아무 분위 · 그래도 없으면 건너뜀).
양측 p<0.10 거부율이 [0.07, 0.13] 이면 그 도구를 쓴다(CR1 우선 → 2원 → 둘 다 탈락이면 «판정 불가»).
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from . import settings as S
from . import stats as ST


def fake_gate(df: pd.DataFrame, n_fake: int = S.N_FAKE, seed: int = S.SEED) -> Dict[str, Any]:
    real = df[df["x"] == 1][["day", "quint", "stock"]]
    base = df[df["x"] == 0].reset_index(drop=True)
    real_stocks = set(real["stock"])
    pool = base[~base["stock"].isin(real_stocks)]
    by_dq = {k: v.to_numpy() for k, v in pool.groupby(["day", "quint"]).groups.items()}
    by_d = {k: v.to_numpy() for k, v in pool.groupby("day").groups.items()}
    by_sd = {k: int(v[0]) for k, v in pool.groupby(["stock", "day"]).groups.items()}
    rej1 = rej2 = 0
    betas, ses = [], []
    skipped = 0
    for i in range(n_fake):
        rng = np.random.default_rng([seed, 7, i])
        mp: Dict[str, str] = {}
        chosen = set()
        for r in real.itertuples(index=False):
            h = mp.get(r.stock)
            idx = by_sd.get((h, r.day)) if h is not None else None
            if idx is None:
                cand = by_dq.get((r.day, r.quint))
                if cand is None or not len(cand):
                    cand = by_d.get(r.day)
                if cand is None or not len(cand):
                    skipped += 1
                    continue
                idx = int(cand[rng.integers(len(cand))])
                mp[r.stock] = str(base.at[idx, "stock"])
            chosen.add(idx)
        x = np.zeros(len(base))
        x[list(chosen)] = 1.0
        fe = ST.fe_regression(base["y_sl"].to_numpy(), x, base["day"].to_numpy(), base["stock"].to_numpy(),
                              base["block"].to_numpy())
        rej1 += int(fe.p2_cr1 < S.FAKE_P)
        rej2 += int(fe.p2_2w < S.FAKE_P)
        betas.append(fe.beta)
        ses.append(fe.se_cr1)
    r1, r2 = rej1 / n_fake, rej2 / n_fake
    tool = "cr1" if S.FAKE_LO <= r1 <= S.FAKE_HI else ("2way" if S.FAKE_LO <= r2 <= S.FAKE_HI else "fail")
    return {"rej_cr1": r1, "rej_2w": r2, "tool": tool, "sd_null": float(np.std(betas, ddof=1)),
            "mean_se_cr1": float(np.nanmean(ses)), "n_fake": n_fake, "n_real_marks": int(len(real)),
            "n_skipped": skipped}
