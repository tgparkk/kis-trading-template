"""지수 일봉 df(FDR·KIS) → index_daily 행 + UPSERT + 신선도 판정.

2026-09-10: 소스를 KIS 업종 일봉으로 옮기면서 «행 수»가 아니라 «날짜»를 보는
신선도 판정을 같이 넣는다(설계 §4). 판정은 소스 스위치 «밖»이라 FDR 로 롤백해도
계속 돈다 — 결함을 잡았어야 할 장치를 롤백이 같이 꺼버리면 안 된다.
  spec: docs/superpowers/specs/2026-09-10-index-kis-freshness-design.md
"""
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import timedelta
from typing import List, Optional

from config.constants import (
    INDEX_BAR_CONFIRM_HHMM,
    INDEX_FRESHNESS_MAX_CALENDAR_LAG,
)

_UPSERT = """
INSERT INTO index_daily (index_code, date, open, high, low, close, volume)
VALUES (%(index_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s)
ON CONFLICT (index_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
    close=EXCLUDED.close, volume=EXCLUDED.volume
"""

# KIS 업종 일봉(output2) 키 — 2026-09-10 프로브 «실측».
#   scratchpad/index_kis_probe/RESULT.md §2 (추측 배선 금지: 현재지수는 bstp_ 접두사,
#   종목 차트는 stck_ 접두사라 섞여 있다)
_KIS_DATE = "stck_bsop_date"
_KIS_OPEN = "bstp_nmix_oprc"
_KIS_HIGH = "bstp_nmix_hgpr"
_KIS_LOW = "bstp_nmix_lwpr"
_KIS_CLOSE = "bstp_nmix_prpr"
_KIS_VOLUME = "acml_vol"
# 🔑 KIS acml_vol = 천 주 · 반올림 오차 ≤ 999 (09-07 KOSPI: KIS 240,446 vs FDR
#    240,446,154 ⇒ ×1000 으로 기존 index_daily.volume 단위를 그대로 잇는다).
_KIS_VOLUME_UNIT = 1000


def _num(v) -> float:
    """문자열 숫자 → float. 빈 값은 0.0(KIS 는 결측 칸을 빈 문자열로 준다)."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    return float(s)


def fdr_df_to_index_rows(index_code: str, df) -> list:
    if df is None or len(df) == 0:
        return []
    rows = []
    for idx, r in df.iterrows():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        rows.append({
            "index_code": index_code, "date": d,
            "open": float(r["Open"]), "high": float(r["High"]),
            "low": float(r["Low"]), "close": float(r["Close"]),
            "volume": float(r.get("Volume", 0) or 0),
        })
    return rows


def kis_df_to_index_rows(index_code: str, df) -> list:
    """KIS 업종 일봉 output2 df → index_daily 행. FDR 경로와 «같은» 스키마를 낸다.

    - 날짜: `YYYYMMDD` → `YYYY-MM-DD` (index_daily.date 는 text · ISO 규약)
    - 거래량: KIS `acml_vol` 은 «천 주» 단위 ⇒ `int(acml_vol) * 1000`
      (반올림 오차 ≤ 999주 · 소비자 0이지만 단위가 바뀌면 조용한 불연속이 된다)
    - 응답은 최신순이지만 UPSERT 는 순서에 무관하므로 정렬하지 않는다.
    - 🔴 `close <= 0` 인 봉은 «버린다». KIS 는 장 시작 «전»에도 T 라벨 봉을 준다(2026-09-10
      리뷰 실측: 07:40:2x 에 T 로 찍힌 daily_prices 행이 매 거래일 31~36건). 미확정 칸은
      빈 문자열로 오고 `_num` 이 0.0 으로 접으므로, 거르지 않으면 «종가 0» 인 T 행이 표에
      남고 그 순간 max = T 가 되어 신선도 두 축이 «무조건 PASS» 가 된다 — 판정이 자기
      데이터로 무력화된다. 지수 종가 0 은 유효값이 아니다.
    """
    if df is None or len(df) == 0:
        return []
    rows = []
    for _, r in df.iterrows():
        raw = str(r.get(_KIS_DATE, "") or "").strip()
        if not raw:
            continue
        close = _num(r.get(_KIS_CLOSE))
        if close <= 0:
            continue
        d = "%s-%s-%s" % (raw[0:4], raw[4:6], raw[6:8]) if len(raw) == 8 else raw[:10]
        vol = int(_num(r.get(_KIS_VOLUME, 0))) * _KIS_VOLUME_UNIT
        rows.append({
            "index_code": index_code, "date": d,
            "open": _num(r.get(_KIS_OPEN)), "high": _num(r.get(_KIS_HIGH)),
            "low": _num(r.get(_KIS_LOW)), "close": close,
            "volume": float(vol),
        })
    return rows


def upsert_index_rows(conn, rows) -> int:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT, r)
    conn.commit()
    return len(rows)


# ─────────────────────── 신선도 판정 (설계 §4 · 순수 함수) ───────────────────────
def to_date(v) -> Optional[_date]:
    """date / datetime / 'YYYY-MM-DD' 문자열 → date. 못 읽으면 None."""
    if v is None:
        return None
    if isinstance(v, _datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    s = str(v).strip()[:10]
    if len(s) != 10:
        return None
    try:
        return _date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, TypeError):
        return None


def freshness_cutoff(now) -> _date:
    """오늘 봉을 «확정»으로 볼 경계일. INDEX_BAR_CONFIRM_HHMM 이후면 today, 전이면 today−1.

    🔴 이 자름이 없으면 장전 W1 훅이 07:40 에 넣는 «오늘 행» 탓에 D_ref=T 가 되어
       정상인 지수(T−1)가 매일 아침 STALE 로 오탐한다(설계 §4-1 실측).
    """
    hh, mm = INDEX_BAR_CONFIRM_HHMM
    today = now.date()
    return today if (now.hour, now.minute) >= (hh, mm) else today - timedelta(days=1)


def reference_trade_date(oracle_dates, now) -> Optional[_date]:
    """오라클 종목이 실제로 가진 «cutoff 이하» 최신 거래일 = D_ref. 없으면 None(=모른다).

    달력·휴장일을 달력이 아니라 데이터로 푼다 — 휴장일·주말에는 직전 거래일이 나온다.
    """
    cutoff = freshness_cutoff(now)
    cand = [d for d in (to_date(x) for x in (oracle_dates or [])) if d is not None and d <= cutoff]
    return max(cand) if cand else None


def evaluate_freshness(index_code: str, table: str, max_date, ref_date, today, src: str,
                       max_calendar_lag: int = INDEX_FRESHNESS_MAX_CALENDAR_LAG) -> List[dict]:
    """두 축을 «따로» 판정한다. stale 인 축마다 1개씩, 신선하면 [].

    축 A(상대) `max < D_ref` — 지수만 밀린 경우(2026-09-08 결함)를 잡는다.
                D_ref 가 None 이면 「모른다」라 판정하지 않는다.
    축 B(절대) `today − max > max_calendar_lag` — A 의 사각(오라클도 같이 멈춤)을 잡는다.

    🔑 한 규칙의 두 축은 한 줄로 뭉치지 않는다(2026-09-08 교훈).
    """
    mx = to_date(max_date)
    ref = to_date(ref_date)
    td = to_date(today)
    out: List[dict] = []

    def _rec(axis, lag):
        return {"index": index_code, "table": table, "max": mx.isoformat() if mx else None,
                "ref": ref.isoformat() if ref else None, "stale": True,
                "axis": axis, "lag_days": lag, "src": src}

    if ref is not None and (mx is None or mx < ref):
        out.append(_rec("A", None if mx is None else (ref - mx).days))
    if td is not None and (mx is None or (td - mx).days > max_calendar_lag):
        out.append(_rec("B", None if mx is None else (td - mx).days))
    return out


def format_freshness_warning(rec: dict) -> str:
    """설계 §4-3 의 고정 태그 한 줄. 태그가 흔들리면 로그 grep 판정이 무너진다."""
    lag = rec.get("lag_days")
    return ("[index-freshness] STALE axis=%s table=%s index=%s max=%s ref=%s lag=%s src=%s"
            % (rec.get("axis"), rec.get("table"), rec.get("index"),
               rec.get("max") or "none", rec.get("ref") or "none",
               "?" if lag is None else lag, rec.get("src")))


def check_index_freshness(index_max_dates: dict, oracle_dates, now, table: str, src: str,
                          logger=None) -> List[dict]:
    """지수별 신선도 판정 + 경고 로그. stale 기록 리스트를 돌려준다(축마다 1개).

    Args:
        index_max_dates: {'KOSPI': max_date|None, 'KOSDAQ': ...} — «표에 실제로 있는» 최신 봉.
        oracle_dates: 오라클 종목들의 최신 거래일(들). cutoff 는 이 함수가 «다시» 건다.
        now: KST datetime. table: 'index_daily' | 'daily_prices'. src: 'kis' | 'fdr'.
        logger: 있으면 stale 축마다 warning 1줄.

    🔑 함수명이 `check_index_freshness` 인 이유: 2026-08-17 에 지운 레거시 대조
       (`reconcile_index`·`reconcile_verdict`·`_LEGACY_CODE_MAP`)와 이름이 겹치면
       부활 금지 가드(tests/collectors/test_index_collector.py)를 무의미하게 만든다.
       이건 죽은 DB 와의 교차비교가 아니라 sector/financials 와 같은 «자기완결 판정»이다.
    """
    ref = reference_trade_date(oracle_dates, now)
    today = now.date()
    if ref is None and logger is not None:
        # 「모른다」를 「안전」으로도 「고장」으로도 접지 않는다 — 축 A 만 건너뛴다.
        logger.warning("[index-freshness] unknown axis=A table=%s ref=none src=%s "
                       "— 오라클 종목 일봉을 못 읽어 상대 판정을 생략한다", table, src)
    out: List[dict] = []
    for name in sorted(index_max_dates or {}):
        for rec in evaluate_freshness(name, table, index_max_dates[name], ref, today, src):
            if logger is not None:
                logger.warning("%s", format_freshness_warning(rec))
            out.append(rec)
    return out


# ─────────────── collection_reconciliation (dataset='index') ───────────────
# sector/financials 와 같은 «자기완결 건강 판정» 행이다(collectors/sector_writer.py:654).
# value_match_rate 는 NULL — 대조할 2차 소스가 없다. 가짜 숫자를 넣지 않는다.
_UPSERT_RECON = """
INSERT INTO collection_reconciliation
  (trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict)
VALUES (%s, 'index', %s, %s, %s, %s, %s, %s)
ON CONFLICT (trade_date, dataset) DO UPDATE SET
    real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap,
    value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage,
    verdict=EXCLUDED.verdict
"""


def upsert_index_reconciliation(conn, trade_date: str, real_rows: int, new_rows: int,
                                overlap: int, coverage, verdict: str) -> None:
    """지수 수집 판정 행. trade_date 는 ISO 'YYYY-MM-DD'(minute 의 'YYYYMMDD' 와 안 섞는다).

    🔑 `new_rows` 는 «직전 max(date) 보다 뒤인 행 수»다 — 「N행 갱신 ≠ 최신성」을
       표에서 갈라놓는 칸이다(2026-09-08: 창 단위 UPSERT 반환행수가 6이었는데 새 날짜는 0).
    """
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_RECON, (trade_date, real_rows, new_rows, overlap,
                                        None, coverage, verdict))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
