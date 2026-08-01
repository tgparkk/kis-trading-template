"""5차 대조군 — 깊이는 맞추고 「상승폭 → 깊이 대응관계」만 파괴한다.

⚠️ 4차 `control.py::control_levels` 는 `[min(전략레벨), peak]` 균등추출이라
   전략보다 구조적으로 얕게 샀다(삼성 15.7%p·다날 5.5%p). 같은 사건·같은
   청산일에 그만큼 싸게 사면 격차는 정보가 아니라 **산술**이다.
   그 모듈은 4차 재현용으로 그대로 두고, 판정은 이 모듈로만 한다.

C1 「상승폭 라벨 셔플」: 자기 상승폭 대신 **과거 사건의 상승폭**으로 밴드를
   만든다. 깊이의 주변분포는 보존되고 조건부 대응관계만 사라진다.
C2 「모양 무작위」: 중심은 전략과 동일, 폭계수·비중 순서만 무작위.
"""
from __future__ import annotations

import numpy as np

from lab.bands import WEIGHTS, ladder

MIN_LABEL_POOL = 30          # 사전등록 §2 — 풀이 이보다 작으면 양팔 모두 진입 금지
MAX_REDRAW = 20              # 밴드 생성 실패 시 재추첨 한도
C2_WIDTH_RANGE = (0.3, 2.0)  # C2 폭계수 c' ~ U(0.3, 2.0)


def intended_depth(peak: float, levels, weights=WEIGHTS) -> float:
    """지정가 기준 가중평균 하락폭. 체결 여부와 무관한 '걸어둔 깊이'."""
    w = list(weights)[: len(levels)]
    return float(np.dot(w, [1.0 - lv / peak for lv in levels]) / sum(w))


def shuffled_label_levels(peak: float, label_pool, band_fn, c: float,
                          rng: np.random.Generator):
    """C1 — 다른 사건의 상승폭 라벨을 빌려 같은 함수로 밴드를 만든다.

    ⚠️ `label_pool` 은 **같은 기간(분기) 내 다른 사건들의 상승폭**이어야 한다.
       과거 전체에서 뽑으면 상승폭 분포의 시간 드리프트가 그대로 깊이 비대칭이
       된다(실측: 과거풀 1.06%p, 분기 내 풀은 그보다 작다). 기간 내 교차
       셔플이라야 깊이의 주변분포가 사건과 같은 분포에서 나온다.
    """
    n = len(label_pool)
    if n < MIN_LABEL_POOL:
        return None
    for _ in range(MAX_REDRAW):
        # 인덱스로 뽑는다. rng.choice(list) 는 매 호출마다 풀 전체를 배열로
        # 변환해서, 풀이 수만 건으로 자라는 본실행에서 O(n) 이 된다.
        g = float(label_pool[int(rng.integers(n))])
        q = band_fn(g)
        if q is not None:
            return ladder(peak, q[0], q[1], c)
    return None


def random_shape_levels(peak: float, q1: float, q3: float,
                        rng: np.random.Generator, match_depth: float | None = None):
    """C2 — 폭계수 무작위 + 비중 무작위 순열, 깊이는 전략과 정확히 일치.

    ⚠️ 비중을 순열하면 가중평균 깊이가 얕아진다. 등록비중 10/13/17/25/35 는
       깊은 레벨에 무게가 쏠려 있어 `Σw(k−3) = +0.62` 인데, 무작위 순열은
       기댓값이 0 이라 **폭의 0.155배만큼 얕아진다**(실측 2.19%p).
       그대로 두면 C2 는 4차와 같은 깊이 교란 대조군이 된다.
       그래서 하락폭 전체를 상수만큼 평행이동해 의도 깊이를 못 박는다 —
       남는 차이는 **모양(폭·비중 배치)** 뿐이다.
    """
    c_rand = float(rng.uniform(*C2_WIDTH_RANGE))
    levels = ladder(peak, q1, q3, c_rand)
    weights = tuple(float(x) for x in rng.permutation(np.asarray(WEIGHTS)))
    if match_depth is not None:
        shift = match_depth - intended_depth(peak, levels, weights)
        levels = [peak * (1.0 - ((1.0 - lv / peak) + shift)) for lv in levels]
    return levels, weights
