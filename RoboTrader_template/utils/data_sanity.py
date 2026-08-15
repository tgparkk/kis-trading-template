"""일봉 데이터 위생 — «물리적으로 불가능한» 봉 탐지 (2026-08-15 감사).

================================================================================
왜 필요한가
================================================================================

KRX 일일 가격제한은 **±30%** 다. 그보다 큰 «하락»은 정상 시세로 만들어질 수 없고,
사실상 전부 **조정되지 않은 기업행위**(감자·미등록 분할 등)가 남긴 인공물이다.

실측(2026-08-15, `kis_template` 2021-01~2026-08): 일간 −32% 미만 하락 **119건**.
그중 **111건은 `corp_events` 에 대응 이벤트조차 없다**. 표본 −97.9% · −97.4% · −97.1% …
= 대략 1/48 배율. 가드 문서(`tests/test_adj_factor_no_arithmetic.py`, 2026-08-03)가
*「데이터 복구 트랙에서 푼다」* 고 적어둔 **101건/100종목**이 그사이 늘어난 것이다.

🔴 **이게 라이브를 실제로 물었다.** `deep_mr_dev20` 은 「MA20 대비 −20% 폭락 + RSI<30」을
사는 **폭락 저격** 전략이라, 가짜 절벽이 정확히 그 표적 모양이다. 실측(2026-06~08):

    476830  절벽 −44.9%(6/29) → 6/30 매수 +12.09% 익절 · 7/03 매수 −7.30% 손절
    356860  절벽 −56.2%(7/16) → 7/20 매수 **−12.38% 손절**(보유 1일, 선언 −7% 의 1.8배)
    025560  절벽 −75.5%(7/27) → 7/29 매수 **−16.16% 손절**(보유 1일, 선언 −7% 의 2.3배)

`deep_mr` 매수 46건 중 **4건(8.7%)** 이 이 경로였고, 다른 7전략은 **0건**이다.
둘은 손절선을 뚫고 갭다운했다 — 감사가 설명하지 못했던 *「하루 만에 큰 손절」* 의 한 갈래다.

================================================================================
설계 결정
================================================================================

1. **하락만 본다.** 상승 쪽 초과(신규상장일 ±60~400%, 미조정 액면병합 등)는
   «정상»인 경우가 섞여 있어 오탐 위험이 크다. 해악이 확인된 방향만 막는다.
2. **문턱은 −35%** = KRX 한도 −30% + 5%p 여유. 관측된 인공물은 −44.9% 가 가장 얕아
   전부 걸리고, 한도 근처의 정상 급락(−29~−30%)은 건드리지 않는다.
3. **룰이 «실제로 보는» 창만 검사한다.** 200봉 전의 절벽은 20봉 룰을 오염시키지 않는다.
   ⇒ 호출자는 `generate_signal`/`match` 에 넘길 바로 그 DataFrame 을 그대로 준다.
4. **정리매매(가격제한 없음) 종목이 함께 걸리는 것은 «의도된» 부작용**이다 —
   상장폐지 절차 중인 종목을 사지 않는 것이 옳다.

⚠️ 이건 **데이터 위생 가드**이지 전략 변경이 아니다. 「이렇게 하면 성과가 좋아진다」를
   주장하지 않는다 — 「물리적으로 불가능한 데이터로 매매하지 않는다」가 근거다.
🔴 **근본 해결이 아니다.** 오염된 데이터를 «피하는» 것이지 «고치는» 것이 아니므로,
   데이터 복구 트랙(119건 원인 규명·재적재)은 그대로 남는다.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd

# KRX 일일 가격제한 (2015-06-15~ ±30%).
KRX_DAILY_LIMIT_PCT: float = 0.30

# 탐지 문턱 — 한도에 5%p 여유. 이보다 «더 많이» 떨어진 하루는 정상 시세로 불가능하다.
IMPOSSIBLE_DROP_PCT: float = -0.35


def find_impossible_drops(
    data: Optional[pd.DataFrame],
    threshold: float = IMPOSSIBLE_DROP_PCT,
    close_col: str = "close",
) -> List[Tuple[int, float]]:
    """`threshold` 보다 큰 하루 하락이 난 위치를 찾는다.

    Args:
        data: 일봉 DataFrame (오름차순). 없거나 2행 미만이면 빈 목록.
        threshold: 음수. 종가 변화율이 이 값 «미만»이면 불가능봉으로 본다.
        close_col: 종가 컬럼명.

    Returns:
        [(행 위치(0-based), 변화율), ...] — 비면 정상.
    """
    if data is None or getattr(data, "empty", True) or close_col not in data.columns:
        return []
    close = pd.to_numeric(data[close_col], errors="coerce")
    if len(close) < 2:
        return []
    # 0·음수·결측 종가는 변화율이 무의미하다 → 비교에서 제외(NaN 은 비교가 항상 False).
    close = close.where(close > 0)
    # 🔑 fill_method=None 명시 — 기본값(pad)은 결측을 앞값으로 «채워» 손상 행을 정상처럼
    #    보이게 만든다. 여기선 채우지 않고 NaN 으로 남겨 그 구간을 «판정 불가»로 둔다
    #    (판정 불가 = 통과. 손상 데이터를 근거로 종목을 배제하지는 않는다).
    ret = close.pct_change(fill_method=None)
    hits = ret[ret < threshold]
    return [(int(pos), float(v)) for pos, v in zip(
        (ret.index.get_indexer(hits.index) if len(hits) else []), hits.values)]


def has_impossible_drop(
    data: Optional[pd.DataFrame],
    threshold: float = IMPOSSIBLE_DROP_PCT,
    close_col: str = "close",
) -> bool:
    """`find_impossible_drops` 가 하나라도 잡히면 True."""
    return bool(find_impossible_drops(data, threshold=threshold, close_col=close_col))


def describe_impossible_drop(
    data: Optional[pd.DataFrame],
    threshold: float = IMPOSSIBLE_DROP_PCT,
    close_col: str = "close",
    date_col: str = "date",
) -> str:
    """로그용 한 줄 설명. 없으면 빈 문자열."""
    hits = find_impossible_drops(data, threshold=threshold, close_col=close_col)
    if not hits:
        return ""
    pos, ret = min(hits, key=lambda t: t[1])          # 가장 큰 하락
    when = ""
    if data is not None and date_col in data.columns and 0 <= pos < len(data):
        try:
            when = f" @{pd.to_datetime(data[date_col].iloc[pos]).date()}"
        except (ValueError, TypeError):
            when = ""
    return (f"불가능봉 {len(hits)}건{when} 최대 {ret * 100:.1f}% "
            f"(KRX 한도 ±{KRX_DAILY_LIMIT_PCT * 100:.0f}%)")
