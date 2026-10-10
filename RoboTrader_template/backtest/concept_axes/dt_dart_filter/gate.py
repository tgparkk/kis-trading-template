"""가짜 표식 게이트 — 스펙 §3-5.

실제 표식 행은 버리고(수익을 읽지 않음) 남은 표본에서 실제 표식마다 같은 날·같은 p_L 5분위 후보에 가짜 표식을 붙인다
(같은 실제 종목 → 같은 가짜 종목 대응 · 실제 표식 종목은 풀에서 제외 · 풀 없으면 같은 날 아무 분위 · 그래도 없으면 건너뜀).
한 복제 안에서는 비복원(이미 뽑힌 행은 다시 안 뽑음 — 대응 종목의 그날 행이 이미 뽑혔으면 새로 뽑는다).
양측 p<0.10 거부율이 [0.07, 0.13] 이면 그 도구를 쓴다(CR1 우선 → 2원 → 둘 다 탈락이면 «판정 불가»).

유효 복제 규칙(최종 리뷰 I3 · 관리자 판정 · PREREG 명시):
- 도구별 유효 복제 = β 와 그 도구의 양측 p 가 유한. 거부율 = 유효 복제 중 거부 / 유효 복제 수(NaN p 를 비거부로 세지 않음).
- `n_valid` = CR1 유효 복제 수. `n_valid < ceil(FAKE_VALID_FRAC × n_fake)`(400 → 380) 이면 tool="fail" · reason="degenerate".
  CR1 이 밴드 밖이라 2원으로 갈 때 2원 유효 복제가 문턱 미만이어도 "degenerate".
- sd_null · mean_se_cr1 · 하측 거부율(p1<0.05) · 평균 가짜 n₁ = CR1 유효 복제만으로.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from . import settings as S
from . import stats as ST


def build_pools(df: pd.DataFrame) -> Dict[str, Any]:
    """실제 표식 행(day·quint·stock) · 대조 표본 base(0..n−1) · 풀(실제 표식 종목 제외) 색인."""
    real = df[df["x"] == 1][["day", "quint", "stock"]].reset_index(drop=True)
    base = df[df["x"] == 0].reset_index(drop=True)
    real_stocks = set(real["stock"])
    pool = base[~base["stock"].isin(real_stocks)]
    return {"real": real, "base": base,
            "by_dq": {k: [int(i) for i in v] for k, v in pool.groupby(["day", "quint"]).groups.items()},
            "by_d": {k: [int(i) for i in v] for k, v in pool.groupby("day").groups.items()},
            "by_sd": {k: int(v[0]) for k, v in pool.groupby(["stock", "day"]).groups.items()}}


def draw_replicate(pools: Dict[str, Any], rng: np.random.Generator) -> Tuple[List[int], int]:
    """복제 1개 — 가짜 표식 base 행 번호(비복원) · 건너뛴 실제 표식 수."""
    base = pools["base"]
    mp: Dict[str, str] = {}
    chosen: List[int] = []
    taken = set()
    skipped = 0
    for r in pools["real"].itertuples(index=False):
        h = mp.get(r.stock)
        idx = pools["by_sd"].get((h, r.day)) if h is not None else None
        if idx is None or idx in taken:
            cand = [c for c in pools["by_dq"].get((r.day, r.quint), ()) if c not in taken]
            if not cand:
                cand = [c for c in pools["by_d"].get(r.day, ()) if c not in taken]
            if not cand:
                skipped += 1
                continue
            idx = int(cand[rng.integers(len(cand))])
            mp[r.stock] = str(base.at[idx, "stock"])
        taken.add(idx)
        chosen.append(idx)
    return chosen, skipped


def _finite(v: float) -> bool:
    return v is not None and math.isfinite(float(v))


def summarize(fes: Sequence[ST.FE], n_fake: int) -> Dict[str, Any]:
    need = math.ceil(S.FAKE_VALID_FRAC * n_fake)
    v1 = [f for f in fes if _finite(f.beta) and _finite(f.p2_cr1)]
    v2 = [f for f in fes if _finite(f.beta) and _finite(f.p2_2w)]
    nan = float("nan")
    r1 = sum(f.p2_cr1 < S.FAKE_P for f in v1) / len(v1) if v1 else nan
    r2 = sum(f.p2_2w < S.FAKE_P for f in v2) / len(v2) if v2 else nan
    in1 = len(v1) >= need and S.FAKE_LO <= r1 <= S.FAKE_HI
    in2 = len(v2) >= need and S.FAKE_LO <= r2 <= S.FAKE_HI
    if len(v1) < need:
        tool, reason = "fail", "degenerate"
    elif in1:
        tool, reason = "cr1", "ok"
    elif in2:
        tool, reason = "2way", "ok"
    else:
        tool, reason = "fail", ("degenerate" if len(v2) < need else "out_of_band")
    betas = [f.beta for f in v1]
    return {"rej_cr1": r1, "rej_2w": r2, "tool": tool, "reason": reason,
            "n_valid": len(v1), "n_valid_2w": len(v2), "n_valid_min": need,
            "sd_null": float(np.std(betas, ddof=1)) if len(betas) >= 2 else nan,
            "mean_se_cr1": float(np.mean([f.se_cr1 for f in v1])) if v1 else nan,
            "rej_lo_cr1": sum(f.p1_cr1 < S.ALPHA for f in v1) / len(v1) if v1 else nan,
            "mean_fake_n1": float(np.mean([f.n1 for f in v1])) if v1 else nan,
            "n_fake": n_fake}


def fake_gate(df: pd.DataFrame, n_fake: int = S.N_FAKE, seed: int = S.SEED) -> Dict[str, Any]:
    pools = build_pools(df)
    base = pools["base"]
    y, day, stock, block = (base["y_sl"].to_numpy(), base["day"].to_numpy(), base["stock"].to_numpy(),
                            base["block"].to_numpy())
    fes: List[ST.FE] = []
    skipped = 0
    for i in range(n_fake):
        chosen, sk = draw_replicate(pools, np.random.default_rng([seed, 7, i]))
        skipped += sk
        x = np.zeros(len(base))
        x[chosen] = 1.0
        fes.append(ST.fe_regression(y, x, day, stock, block))
    out = summarize(fes, n_fake)
    out.update(n_real_marks=int(len(pools["real"])), n_skipped=skipped)
    return out
