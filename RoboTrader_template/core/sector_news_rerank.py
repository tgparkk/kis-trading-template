"""섹터 뉴스 재정렬 — 순수 함수 (스펙 B §5.2). DB·로거·설정을 import 하지 않는다.

    shift_i = round_half_away(max_shift × s_i)      s_i = clip(score_signed, -1, 1); |s_i| < min_abs 또는 미상이면 0
    key_i   = orig_rank_i − shift_i − 0.5·sign(shift_i)
    key 오름차순 «안정» 정렬(동률 = 원래 순위)

0.5 편향: 혼자 움직이는 종목이 «정확히 shift 칸» 이동하게 한다(편향이 없으면 동률에서 원래 순위에 밀려 한 칸 덜 간다).
여러 종목이 동시에 움직이면 최종 위치 차이는 max_shift 를 넘을 수 있다 — 상한은 «자기 점수에 의한 이동»에 대한 것이다.
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RerankRow:
    stock_code: str
    sector_key: Optional[str]
    sector_score: Optional[float]   # 섹터 score_signed 원값 (min_abs 미만이어도 기록 · 미상이면 None)
    orig_rank: int                  # 1-based
    new_rank: int                   # 1-based


def _round_half_away(x: float) -> int:
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def rerank(codes: List[str], code_to_sector: Dict[str, str], sector_scores: Dict[str, float],
           *, max_shift: int = 3, min_abs: float = 0.2) -> Tuple[List[str], List[RerankRow]]:
    """(새 코드 순서, orig_rank 오름차순 RerankRow 목록)."""
    if len(set(codes)) != len(codes):
        raise ValueError("codes 에 중복이 있다 — screener_snapshots 계약 위반")
    if max_shift < 0:
        raise ValueError("max_shift 는 0 이상이어야 한다")

    entries = []  # (key, orig_rank, code, sector, raw_score)
    for idx, code in enumerate(codes):
        orig_rank = idx + 1
        sector = code_to_sector.get(code)
        raw = sector_scores.get(sector) if sector is not None else None
        s = 0.0
        if raw is not None:
            s = max(-1.0, min(1.0, float(raw)))
            if abs(s) < min_abs:
                s = 0.0
        shift = _round_half_away(max_shift * s)
        bias = 0.5 if shift > 0 else (-0.5 if shift < 0 else 0.0)
        entries.append((orig_rank - shift - bias, orig_rank, code, sector, None if raw is None else float(raw)))

    entries.sort(key=lambda e: (e[0], e[1]))
    new_codes = [e[2] for e in entries]
    rows = [RerankRow(stock_code=e[2], sector_key=e[3], sector_score=e[4], orig_rank=e[1], new_rank=pos + 1)
            for pos, e in enumerate(entries)]
    rows.sort(key=lambda r: r.orig_rank)
    return new_codes, rows


def classify_sector_news_exception(e: BaseException) -> str:
    """psycopg2 를 import 하지 않고 클래스 이름으로 분류한다(테스트에서 대역 예외를 쓸 수 있게)."""
    name = type(e).__name__
    if name == "UndefinedFunction":
        return "fn_missing"
    if name == "UndefinedTable":
        return "table_missing"
    return f"error:{name}"
