"""기업행위 가격 보정 — 순수 계산. DB·KIS 에 접근하지 않는다.

🔴 방향 고정: 저장 규약은 `adj_close = raw_close / adj_factor` 이고
읽기 계층은 `volume * adj_factor` 를 한다(`db/quant_daily_reader.py`).
⇒ **adj_factor = vol_adj / vol_raw = raw_close / adj_close.**
사양 초안은 `vol_raw / vol_adj` 로 «뒤집혀» 있었다 — 그대로 썼으면 25배 틀렸다.
"""
from typing import Dict, Tuple


def _volume(row):
    return float(row[4])


def derive_factors(raw: Dict[str, tuple], adj: Dict[str, tuple]) -> Tuple[dict, dict]:
    """두 피드의 «거래량 비» 로 날짜별 adj_factor 를 구한다.

    거래량을 쓰는 이유: **배당의 영향을 안 받는다.** 가격 비로 구하면 KIS 수정주가가
    배당까지 조정하므로 순수 분할/병합 배수가 안 나온다(실측 15종목이 그 형태).
    """
    dates = sorted(set(raw) & set(adj))
    diag = dict(n_dates=len(dates), n_derived=0, n_zero_vol=0, n_filled=0)

    out: Dict[str, float] = {}
    for d in dates:
        vr, va = _volume(raw[d]), _volume(adj[d])
        if vr <= 0 or va <= 0:
            diag["n_zero_vol"] += 1
            continue
        out[d] = va / vr
        diag["n_derived"] += 1

    if not out:
        return {}, diag

    # 빈 날짜를 «이전 유효값» 으로 채운다. 정지 구간은 이벤트 «전» 에 속하므로
    # 앞에서 가져오는 것이 맞다. 앞이 없으면 뒤에서 가져온다.
    prev = None
    for d in dates:
        if d in out:
            prev = out[d]
            continue
        if prev is not None:
            out[d] = prev
            diag["n_filled"] += 1
    nxt = None
    for d in reversed(dates):
        if d in out:
            nxt = out[d]
        elif nxt is not None:
            out[d] = nxt
            diag["n_filled"] += 1
    return out, diag
