"""rs_leader — 미조정 기업행위(합병) 의심 판정 (2026-09-10 사장님 결정 (b)).

spec: docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md

무엇인가
────────
이건 **데이터 위생 가드**이지 알파 주장이 아니다. 근거는 「이렇게 하면 성과가 좋아진다」가
아니라 **「RS 점수의 입력값이 오염된 종목을 랭킹에 넣지 않는다」**다.
`utils/data_sanity.py` 의 불가능봉 가드와 같은 계열이다(그쪽은 «하락» 절벽, 이쪽은
정지런 뒤의 «상승» 불연속 — 미조정 액면병합이 남기는 모양).

어떻게 판정하나 — 큐 파일이 아니라 «런타임 파생»
──────────────────────────────────────────────
`logs/corp_action_refetch_queue.jsonl` 을 읽지 않는다. 대신 큐를 «생산하는» 로직
(`collectors.corp_action_watch.scan_series`)을 **스크리너/전략이 이미 로드한 일봉
프레임에 그대로** 적용한다. 그래서:

  · 추가 DB 접근 **0** · 판정 대상이 룰이 «실제로 보는» 그 프레임이라 원리적으로 stale 불가
  · 데이터가 고쳐지면 그날부터 **자동 해제**(큐는 append-only 라 영원히 pending 이다 —
    실증: 014990 은 큐에 남아 있지만 지금 DB 값의 종가비 0.717 은 밴드 «안»이다)
  · 사건이 프레임(130봉)을 벗어나면 표시가 사라진다 ⇒ **별도 만료 장부·상수가 없다**

🔑 창의 순서가 안전한 방향이다: 가드 프레임 130봉 > RS 창 121봉
   ⇒ 사건이 RS 점수를 오염시키지 «않게 된 뒤에» 배제가 풀린다.

🔴 임계·밴드는 **여기에 다시 적지 않는다** — `corp_action_watch` 단일 소스를 재사용만
   한다(한 규칙을 두 곳에 적으면 한 곳만 고쳐진다). 이 모듈에는 숫자 상수가 «0개»다.

한계 (과대주장 금지)
──────────────────
「못 본다 ≠ 없다」. 이 판정은 미조정의 **부재를 증명하지 않는다**. 프레임 밖의 사건은
원리적으로 못 본다 — on_tick 경로의 프레임은 82봉뿐이라 사정거리가 더 짧다(§2 Q3).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import pandas as pd

from collectors.corp_action_watch import scan_series
from utils.logger import setup_logger

logger = setup_logger(__name__)


def resolve_mode() -> Tuple[str, Optional[str]]:
    """(mode, invalid_raw) — **호출 시점**에 읽는다.

    import 시점에 값을 박아 두면 테스트·운영 양쪽에서 「바꿨는데 안 바뀐다」가 된다
    (선례: `core/candidate_selector.py:1179` 도 호출 시점에 읽는다).
    """
    import config.constants as C
    mode = getattr(C, "RS_LEADER_CORP_ACTION_MODE", "off")
    invalid = getattr(C, "RS_LEADER_CORP_ACTION_MODE_INVALID", None)
    if mode not in getattr(C, "RS_LEADER_CORP_ACTION_MODES", ("off", "shadow", "live")):
        return "off", mode
    return mode, invalid


def invalid_mode_message(invalid: Any) -> str:
    """모르는 mode 값 WARNING 문구 (`resolve_sector_news_mode` 규약과 같은 형식)."""
    return (f"[rs-corp-action] RS_LEADER_CORP_ACTION_MODE={invalid!r} 는 모르는 값 → "
            f"off 로 동작 (허용: {_modes()})")


def _modes():
    import config.constants as C
    return getattr(C, "RS_LEADER_CORP_ACTION_MODES", ("off", "shadow", "live"))


def detect(stock_code: Any, df: Optional[pd.DataFrame]) -> Optional[Dict[str, Any]]:
    """이미 로드된 일봉 프레임에서 «미조정 기업행위 의심» 지점을 찾는다.

    Args:
        stock_code: 로그·반환 dict 표시용. 판정에는 쓰이지 않는다.
        df: 오름차순 일봉. `close`·`volume` 컬럼 필요(`date` 는 있으면 재개일 표시에 쓴다).

    Returns:
        가장 «최근» 사건 1건(dict) 또는 None. 사건이 여럿이면 마지막 것 — 창에서 먼저
        빠져나가는 건 오래된 쪽이라 해제 시점을 보수적으로 잡는 방향이다.

    🔑 **판정 불가 = 통과**(`utils/data_sanity.py:76-84` 규약). 손상 데이터를 «근거»로
       종목을 배제하지 않는다 — 배제의 근거는 항상 관측된 사건이어야 한다:
         · `volume` 결측/NaN → 「거래정지인지 모른다」를 「거래정지다」로 접지 않는다
         · `close` 0/NaN → `scan_series` 가 `close > 0` 을 요구하므로 그 지점은 판정 제외
    """
    if df is None or getattr(df, "empty", True):
        return None
    try:
        if "close" not in df.columns or "volume" not in df.columns:
            return None
        close = pd.to_numeric(df["close"], errors="coerce")
        volume = pd.to_numeric(df["volume"], errors="coerce")
        if "date" in df.columns:
            dates = pd.to_datetime(df["date"], errors="coerce")
            iso = ["" if pd.isna(d) else d.strftime("%Y-%m-%d") for d in dates]
        else:
            iso = [""] * len(df)
        bars = []
        for i in range(len(df)):
            c = close.iat[i]
            v = volume.iat[i]
            # NaN volume → 정지런을 «끊는» 값(-1.0)으로 둔다. 「모른다」를 「정지다」로
            # 접으면 없는 사건이 보인다. NaN close → 0.0 (scan_series 가 판정 제외).
            bars.append((iso[i],
                         0.0 if pd.isna(c) else float(c),
                         -1.0 if pd.isna(v) else float(v)))
        hits = scan_series(str(stock_code or ""), bars)
    except Exception as e:  # 판정이 라이브 경로를 죽이지 않는다 — 단, 조용히 넘기지도 않는다
        logger.warning("[rs-corp-action] %s: 판정 실패 → 통과 처리 (%s: %s)",
                       stock_code, type(e).__name__, e)
        return None
    return hits[-1] if hits else None


def describe(hit: Dict[str, Any]) -> str:
    """로그용 한 줄 설명 (스펙 §3-3 문구의 가운데 토막).

    예: `미조정 병합 의심(정지 13봉 → 재개 2026-09-09, 종가비 4.455)`
    """
    kind = "병합" if hit.get("direction") == "merge" else "분할"
    return (f"미조정 {kind} 의심(정지 {hit.get('halt_bars')}봉 → "
            f"재개 {hit.get('resumption_date')}, 종가비 {float(hit.get('ratio', 0)):.3f})")
