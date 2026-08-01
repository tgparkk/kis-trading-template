from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lab.stats import delta_t, mde, white_reality_check


def _panel(n_cells: int, n_codes: int, edge_cell: str | None = None, seed: int = 0):
    """셀 × 종목코드 패널. 같은 코드가 모든 셀에 등장해 블록 구조를 만든다."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_cells):
        cell = f"c{i}"
        mu = 0.04 if cell == edge_cell else 0.0
        for k in range(n_codes):
            for _ in range(4):
                rows.append({"cell": cell, "code": f"S{k:03d}", "d": rng.normal(mu, 0.05)})
    return pd.DataFrame(rows)


def test_reality_check_false_positive_rate_across_seeds():
    """귀무 하에서 거짓양성이 없어야 한다.

    단일 시드로 p>0.10 을 단언하면 안 된다 — 귀무 하에서 p 는 분포를 갖는다.
    """
    ps = [white_reality_check(_panel(20, 100, seed=s), b=200, seed=s + 100) for s in range(5)]
    assert sum(p < 0.05 for p in ps) == 0, ps


def test_reality_check_detects_a_genuinely_strong_cell():
    p = white_reality_check(_panel(20, 100, edge_cell="c7", seed=7), b=200, seed=1)
    assert p < 0.05, p


def test_reality_check_requires_a_code_column():
    """행 단위 리샘플링이면 유효표본을 거래 수로 착각한다 — 블록이어야 한다.

    code 컬럼을 요구하는 API 자체가 호출부에서 블록 구조를 강제한다.
    """
    import inspect
    assert "df" in inspect.signature(white_reality_check).parameters
    with pytest.raises(KeyError):
        white_reality_check(pd.DataFrame({"cell": ["a"], "d": [0.1]}), b=5)


def test_mde_shrinks_as_sample_grows():
    assert mde(n=400, sd=0.20) > mde(n=4000, sd=0.20)


def test_delta_is_strategy_minus_control():
    d, _ = delta_t(np.array([0.10, 0.10]), np.array([0.04, 0.04]))
    assert abs(d - 0.06) < 1e-12
