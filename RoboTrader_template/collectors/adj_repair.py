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


def build_repair_rows(code: str, raw: Dict[str, tuple], adj: Dict[str, tuple],
                      factors: Dict[str, float]) -> list:
    """OHLC ← 조정 피드 · volume ← 원본 피드 · adj_factor ← factors.

    🔑 컬럼별 출처를 섞으면 규약이 깨진다(`CLAUDE.md` — 가격은 조정 저장, volume 은 원본 저장).
    """
    rows = []
    for d in sorted(set(raw) & set(adj) & set(factors)):
        a, r = adj[d], raw[d]
        rows.append(dict(
            stock_code=code, date=d,
            open=float(a[0]), high=float(a[1]), low=float(a[2]), close=float(a[3]),
            volume=int(_volume(r)),
            adj_factor=float(factors[d]),
        ))
    return rows


def needs_repair(db_rows: Dict[str, tuple], new_rows: list,
                 rel_tol: float = 0.01) -> list:
    """DB 와 «이미 같은» 행은 뺀다 (멱등).

    db_rows: {date_iso: (open, high, low, close, volume, adj_factor)}
    🔑 `adj_factor` 도 비교 대상이다 — 가격이 맞아도 계수가 틀린 종목이 실측 9건 있다.
    """
    def same(a, b):
        if a is None or b is None:
            return False
        if b == 0:
            return a == 0
        return abs(a / b - 1.0) <= rel_tol

    out = []
    for n in new_rows:
        cur = db_rows.get(n["date"])
        if cur is None:
            out.append(n)
            continue
        o, h, l, c, v, f = cur
        if (same(n["open"], o) and same(n["high"], h) and same(n["low"], l)
                and same(n["close"], c) and same(float(n["volume"]), float(v))
                and same(n["adj_factor"], f)):
            continue
        out.append(n)
    return out


def _f(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _parse_feed(items) -> Dict[str, tuple]:
    out = {}
    for it in items or []:
        d = str(it.get("stck_bsop_date", ""))
        if len(d) != 8 or not d.isdigit():
            continue
        c = _f(it.get("stck_clpr"))
        if c <= 0:
            continue
        iso = "%s-%s-%s" % (d[0:4], d[4:6], d[6:8])
        out[iso] = (_f(it.get("stck_oprc")), _f(it.get("stck_hgpr")),
                    _f(it.get("stck_lwpr")), c, _f(it.get("acml_vol")))
    return out


def fetch_both(code: str, start: str, end: str, fetcher) -> Tuple[dict, dict]:
    """`(raw, adj)` — `fetcher` 를 «주입» 받아 테스트가 API 없이 돈다.

    🔴 `adj_prc="1"` = 원주가 · `"0"` = 수정주가. 우리 수집기 전부가 기본값 `"1"` 을 써서
    이 결함이 생겼다(사양 §2-2). 여기서는 **둘 다 명시**한다.
    """
    raw = _parse_feed(fetcher(code, start, end, "1"))
    adj = _parse_feed(fetcher(code, start, end, "0"))
    return raw, adj


def count_impossible(rows, up: float = 0.31, down: float = -0.35) -> int:
    """KRX 일일 한도(±30%)를 넘는 봉 수. 검증 지표 — 줄지 않으면 중단한다.

    🔑 위생 가드(`utils/data_sanity.py`)는 «하락» 만 보지만 실측 불가능봉의
    다수는 «상승» 이다(액면병합이 가격을 올리므로). 여기서는 **양방향**을 센다.
    """
    n = 0
    prev = None
    for _, c in rows:
        if prev is not None and prev > 0:
            r = c / prev - 1.0
            if r >= up or r <= down:
                n += 1
        prev = c
    return n
