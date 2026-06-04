"""『트레이딩 전략서』 (Book 19) 분봉 실행층 3전략 단위테스트.

분봉 룰은 세션 인식(당일 누적고/저·당일 최다거래량). 평가시점 t=df 마지막 행.
모든 평가는 trailing(과거~t) — no-lookahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _mk(open_, high, low, close, volume, *, day="2025-10-06", start="09:00"):
    """1분 간격 datetime 부여한 분봉 df. 기본 단일 거래일(세션 단순화)."""
    n = len(close)
    dts = pd.date_range(f"{day} {start}", periods=n, freq="1min")
    return pd.DataFrame({
        "datetime": dts, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


# ---------- 전략 1: 가격박스 ----------

def _price_box():
    from strategies.books.trading_strategy_book.rules import rule_price_box_tma
    return rule_price_box_tma()


def _box_arrays(n=80):
    """all-pass(중심 상향돌파) 기본 배열.

    history(0..n-3)=1000 평탄에 ±8 진동(밴드 형성). t-1=998(<TMA), t=1003(>=TMA) 돌파.
    당일 고/저 좁게 → 이등분선~1000, close 1003>이등분선.
    """
    close = np.array([1000.0 + (8.0 if i % 2 else -8.0) for i in range(n)])
    close[-2] = 998.0      # 직전봉 TMA 아래
    close[-1] = 1003.0     # 현재봉 TMA 위 → 상향돌파
    open_ = close - 1.0
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    volume = np.full(n, 5000.0)
    return open_, high, low, close, volume


def test_box_all_pass_center_breakout_triggers():
    res = _price_box().evaluate(_mk(*_box_arrays()), {})
    assert res.triggered is True and res.side == "buy"


def test_box_no_breakout_no_support_blocks():
    o, h, l, c, v = _box_arrays()
    c[-2] = 1003.0  # 직전봉도 TMA 위 → 크로스(돌파) 없음
    c[-1] = 1004.0  # 하한 지지도 아님(밴드 상단 근처)
    o = c - 1.0; h = np.maximum(o, c) + 1.0; l = np.minimum(o, c) - 1.0
    assert _price_box().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_box_below_bisector_blocks():
    o, h, l, c, v = _box_arrays()
    h[-1] = 1100.0  # 당일 고가 급등 → 이등분선~(1100+low)/2 > close(1003)
    assert _price_box().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_box_support_path_triggers():
    """하한 지지 경로: 현재가가 하한선 근처로 하락 + 이등분선 위 유지."""
    n = 80
    close = np.array([1000.0 + (8.0 if i % 2 else -8.0) for i in range(n)])
    close[-1] = 985.0          # 하한선(~1000-band) 근처
    open_ = close + 1.0         # 음봉이어도 무관(진입은 지지)
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    low[:] = 984.0              # 당일 최저 고정 → 이등분선 낮춤
    high[:] = 986.0             # 당일 최고 낮춤 → 이등분선=(986+984)/2=985 <= close 985
    volume = np.full(n, 5000.0)
    res = _price_box().evaluate(_mk(open_, high, low, close, volume), {})
    assert res.triggered is True


def test_box_insufficient_bars_no_trigger():
    o, h, l, c, v = _box_arrays(n=40)  # need=max(30,60)+2=62 미만
    assert _price_box().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_box_no_datetime_no_trigger():
    o, h, l, c, v = _box_arrays()
    df = _mk(o, h, l, c, v).drop(columns=["datetime"])
    assert _price_box().evaluate(df, {}).triggered is False


def test_box_no_lookahead():
    o, h, l, c, v = _box_arrays()
    df = _mk(o, h, l, c, v)
    full = _price_box().evaluate(df, {})
    extra = _mk(np.full(5, 500.0), np.full(5, 501.0), np.full(5, 499.0),
                np.full(5, 500.0), np.full(5, 1.0),
                day="2025-10-06", start="11:00")
    more = pd.concat([df, extra], ignore_index=True)
    sliced = _price_box().evaluate(more.iloc[: len(df)], {})
    assert full.triggered == sliced.triggered is True


# ---------- 전략 2: 볼린저 스퀴즈 ----------

def _bb():
    from strategies.books.trading_strategy_book.rules import rule_bollinger_squeeze
    return rule_bollinger_squeeze()


def _bb_arrays(n=130, last=1010.0):
    """all-pass: history 일정진폭(스퀴즈 유지) + 마지막봉 상한 돌파."""
    close = np.array([1000.0 + (3.0 if i % 2 else -3.0) for i in range(n)])
    close[-1] = last
    open_ = close - 0.5
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    volume = np.full(n, 5000.0)
    return open_, high, low, close, volume


def test_bb_all_pass_squeeze_breakout_triggers():
    res = _bb().evaluate(_mk(*_bb_arrays()), {})
    assert res.triggered is True and res.side == "buy"


def test_bb_no_squeeze_blocks():
    """직전봉 밴드가 최근 중앙값보다 넓으면(변동성 확대) 스퀴즈 아님 → 미트리거."""
    o, h, l, c, v = _bb_arrays()
    for i in range(-25, -1):
        c[i] = 1000.0 + (60.0 if i % 2 else -60.0)
    o = c - 0.5; h = np.maximum(o, c) + 0.5; l = np.minimum(o, c) - 0.5
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_bb_no_breakout_no_support_blocks():
    o, h, l, c, v = _bb_arrays(last=1000.0)  # 마지막봉이 밴드 내부(돌파X·지지X)
    o = c - 0.5; h = np.maximum(o, c) + 0.5; l = np.minimum(o, c) - 0.5
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_bb_below_bisector_blocks():
    o, h, l, c, v = _bb_arrays()
    h[-1] = 2000.0  # 당일 고가 급등 → 이등분선 > close
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_bb_insufficient_bars_no_trigger():
    o, h, l, c, v = _bb_arrays(n=100)  # need=20+100+1=121 미만
    assert _bb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_bb_no_datetime_no_trigger():
    o, h, l, c, v = _bb_arrays()
    df = _mk(o, h, l, c, v).drop(columns=["datetime"])
    assert _bb().evaluate(df, {}).triggered is False


# ---------- 전략 3: 눌림목 4단계(상승·하락·횡보·돌파) ----------

def _pb():
    from strategies.books.trading_strategy_book.rules import rule_pullback_volume_dry
    return rule_pullback_volume_dry()


def _pb4_arrays():
    """all-pass 4단계 픽스처 (22봉, 단일세션).

    bars 0-8: 아침 저가대(당일 저가 975 형성, bar3 vol=40000=당일최다)
    bars 9-12: 상승 leg (저점 992 → 고점 high[12]=1014, +2.2%)
    bars 13-15: 되돌림 dip (저점 low[14]=1000, -1.38%, 이등분선 위 유지)
    bars 16-20: 횡보·건조 (range 축소·vol 급감, t-1=bar20 vol=3000)
    bar 21(t): 돌파 (close 1010 > box_high 1005, vol 18000, range 12 확대)
    """
    close = np.array([
        980, 980, 980, 980, 980, 980, 980, 980, 980,   # 0-8
        998, 1004, 1009, 1012,                          # 9-12 상승
        1006, 1002, 1003,                               # 13-15 하락
        1002, 1003, 1002, 1003, 1002,                   # 16-20 횡보
        1010,                                           # 21 돌파
    ], dtype=float)
    high = np.array([
        982, 982, 982, 982, 982, 982, 982, 982, 982,
        999, 1006, 1011, 1014,
        1010, 1005, 1004,
        1004, 1004, 1003, 1004, 1004,
        1020,
    ], dtype=float)
    low = np.array([
        975, 975, 975, 975, 975, 975, 975, 975, 975,
        992, 998, 1003, 1007,
        1004, 1000, 1001,
        1001, 1002, 1001, 1002, 1001,
        1008,
    ], dtype=float)
    volume = np.array([
        8000, 8000, 8000, 40000, 8000, 8000, 8000, 8000, 8000,
        9000, 9000, 9000, 9000,
        7000, 5000, 4000,
        4000, 3500, 3500, 3000, 3000,
        18000,
    ], dtype=float)
    open_ = close.copy()  # open 불필요(룰 미사용) — close 복사
    return open_, high, low, close, volume


def test_pb4_all_pass_triggers():
    res = _pb().evaluate(_mk(*_pb4_arrays()), {})
    assert res.triggered is True and res.side == "buy"


def test_pb4_no_rise_blocks():
    o, h, l, c, v = _pb4_arrays()
    # 전체 pre-breakout 구간 평탄화 → 어디에도 의미있는 상승 leg 없음(상승폭<2%)
    h[9:21] = 1000.0; l[9:21] = 996.0; c[9:21] = 998.0
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb4_no_dip_blocks():
    """단조 상승(되돌림 없음) → ②하락 불성립 → 미트리거 (핵심 회귀: 프록시 갭 해소)."""
    o, h, l, c, v = _pb4_arrays()
    # dip 구간을 고점 부근으로 들어올려 되돌림<1%
    l[13:21] = 1012.0; h[13:21] = 1014.0; c[13:21] = 1013.0
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb4_dip_below_bisector_blocks():
    o, h, l, c, v = _pb4_arrays()
    l[14] = 985.0  # 되돌림 저점이 이등분선 아래로 깊게 → 지지 실패
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb4_not_dry_blocks():
    o, h, l, c, v = _pb4_arrays()
    v[20] = 15000.0  # day_max_vol=day_vols[:-1].max()=40000(bar3); 15000 > 40000*0.25=10000 → 건조 미통과
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb4_no_breakout_blocks():
    o, h, l, c, v = _pb4_arrays()
    c[21] = 1004.0  # 횡보 박스 상단(1005) 미돌파
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb4_overheat_blocks():
    o, h, l, c, v = _pb4_arrays()
    v[21] = 25000.0  # 현재봉 > 당일최다*0.5=20000 → 과열 차단
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb4_no_datetime_no_trigger():
    o, h, l, c, v = _pb4_arrays()
    df = _mk(o, h, l, c, v).drop(columns=["datetime"])
    assert _pb().evaluate(df, {}).triggered is False


def test_pb4_insufficient_bars_no_trigger():
    o, h, l, c, v = _pb4_arrays()
    df = _mk(o, h, l, c, v).iloc[-10:]  # need=leg_window+3=15 미만
    assert _pb().evaluate(df, {}).triggered is False


def test_pb4_late_peak_blocks():
    """고점이 t-2면 되돌림+횡보 공간 부족(hi_idx > n-4) → 미트리거."""
    o, h, l, c, v = _pb4_arrays()
    h[-3] = 1100.0  # t-2 봉을 전역 최고가로 → hi_idx = n-3 (룸 가드에 걸림)
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


def test_pb4_no_candle_contraction_blocks():
    """건조(거래량 급감)는 충족하나 직전봉 캔들이 상승 leg보다 넓으면(축소 실패) → 미트리거.

    h[20]=1012 (<h[12]=1014이므로 argmax 불변·룸가드 통과), l[20]=1001(원본 유지).
    rng_prev=11 > leg_mean≈7.5 → 캔들 축소 불성립. vol_dry는 여전히 통과.
    """
    o, h, l, c, v = _pb4_arrays()
    h[20] = 1012.0  # rng_prev=11 > leg_mean~7.5, high argmax(bar12=1014) 불변
    assert _pb().evaluate(_mk(o, h, l, c, v), {}).triggered is False


# ---------- 드라이버 해석 ----------

def test_driver_resolves_minute_rules():
    """멀티버스 드라이버가 3룰을 모두 해석할 수 있어야 한다."""
    from scripts.book_portfolio_multiverse import _load_book, _resolve_rule_cls
    _strat, rules_mod = _load_book("trading_strategy_book")
    for nm in ("price_box_tma", "bollinger_squeeze", "pullback_volume_dry"):
        cls = _resolve_rule_cls(rules_mod, nm)
        assert cls().name == nm
        # rule_ 접두 입력도 동일 해석
        assert _resolve_rule_cls(rules_mod, f"rule_{nm}") is cls


def test_all_rules_registered():
    from strategies.books.trading_strategy_book.rules import ALL_RULES
    names = {r().name for r in ALL_RULES}
    assert names == {"envelope_200d_high", "price_box_tma",
                     "bollinger_squeeze", "pullback_volume_dry"}
