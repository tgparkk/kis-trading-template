"""후보 정의를 캡처 라벨에 맞춰 채점한다."""
from __future__ import annotations


def best_subset_avg(levels, weights) -> list[float]:
    """1차부터 연속으로 n개 체결됐을 때의 가중평균 전부 (n = 1..5)."""
    out = []
    for n in range(1, len(levels) + 1):
        w = weights[:n]
        tot = sum(w)
        out.append(sum(l * wi for l, wi in zip(levels[:n], w)) / tot)
    return out


def score_grade2(levels, fills, weights=None) -> float:
    """실제 매입가와 '연속 부분집합 가중평균' 사이 최소 상대오차의 평균."""
    from lab.bands import WEIGHTS
    weights = weights or WEIGHTS
    cands = best_subset_avg(levels, weights) + list(levels)
    errs = []
    for f in fills:
        buy = f.get("buy")
        if not buy:
            continue
        errs.append(min(abs(c - buy) / buy for c in cands))
    return sum(errs) / len(errs) if errs else float("inf")


def score_grade1(seg, label) -> float:
    """시작점·최고점 상대오차의 합. 낮을수록 좋다."""
    return (abs(seg.start_px - label["start"]) / label["start"]
            + abs(seg.peak_px - label["peak"]) / label["peak"])
