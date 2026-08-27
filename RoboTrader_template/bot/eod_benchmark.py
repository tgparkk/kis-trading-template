"""EOD 벤치마크 한 줄 — 포트 성과를 KOSPI/KOSDAQ 옆에 나란히 남긴다.

배경(2026-08-25 전문가 3인 자문): 페이퍼 기간 동안 KOSPI 가 -23.6% 였는데 봇 로그
어디에도 시장 성과가 없었다. 그래서 「누적 -20%」가 알파인지 베타인지를 로그만
보고는 판별할 수 없었다. 이 모듈은 그 판별을 가능하게 하는 **계기(instrumentation)**
다 — 매매 판단에 관여하는 코드는 한 줄도 없다.

구조는 둘로 갈라 둔다:
  * :func:`format_benchmark_line` — **순수함수**. 이미 구해진 숫자만 받아 한 줄로
    만든다. DB·API 없이 유닛 테스트가 된다.
  * :func:`collect_benchmark_inputs` — 숫자를 실제로 구한다(FundManager·DB·KIS API).

숫자의 출처(각각 왜 그 출처인가):
  * ``total``  = FundManager 총자금. EOD 자금 정합성 검증이 쓰는 바로 그 값이다.
  * ``base``   = **할당 SSOT** ``VirtualTradingManager._strategy_initial`` 의 합.
                 ``len(bot.strategies)`` 로 세지 않는다 — on_init 실패 전략은
                 ``main.py`` 가 그 dict 에서 삭제하므로(7전략이 되면) 기준이 조용히
                 7천만으로 바뀐다. 실제로 자본이 배정된 원장만이 기준의 근거다
                 (bot/initializer.py:488 이 넣는 바로 그 값).
  * ``당일(equity원장)`` = **한 원장 안에서만** 계산한다:
                 ``Σequity(오늘) ÷ Σequity(직전 거래일) − 1``.
                 🔴 분자를 FundManager, 분모를 equity 원장에서 가져오면 **원장이 섞여**
                 하루 0.6~1.5% 의 가짜 등락이 찍힌다(코드리뷰 2026-08-27: 8/26 은
                 실제 +0.97% 인데 -0.55% 로 찍혔을 것). 두 원장의 정의가 다르므로
                 (현금주의 vs 발생주의·평가 시점) 비율의 분자·분모는 반드시 같은
                 원장이어야 한다. 총자금·누적은 FundManager 를 그대로 쓴다 —
                 그건 «비율»이 아니라 그 원장의 절대값 보고다.
                 ⚠️ ``paper_trading_state.eod_balance`` 는 **현금만**이라 못 쓴다.
                 ⚠️ 두 날짜 모두 **행 수가 배정 전략 수와 정확히 같을 때만** 쓴다
                 (부분 적재일을 전략 하나 사라진 것처럼 읽으면 -12% 가 찍힌다).
  * ``지수 당일`` = KIS 실시간 업종지수 API(``bstp_nmix_prdy_ctrt``). 15:35 시점에
                 DB 지수 테이블은 아직 안 채워져 있다(수집이 이 리포트 «뒤»에 돈다)
                 — API 가 유일한 신선 소스다.
  * ``에포크 이후`` = 오늘 지수(``bstp_nmix_prpr``) ÷ 에포크 종가. 에포크 종가는
                 ``daily_prices`` 의 의사티커 ``KOSPI``/``KOSDAQ`` 에서 읽고, DB 는
                 ``resolve_daily_source_db()`` 가 정한다(DB명 하드코딩 금지 규칙).
                 🔑 **지수 레벨을 같이 찍는다** — 실시간 API(KIS)와 일봉(FDR)의
                 스케일이 어긋나면 비율만 봐서는 알 수 없지만 레벨을 나란히 두면
                 사람이 즉시 알아본다.

못 구한 값은 **0 으로 위장하지 않고 ``n/a``** 로 찍는다.
"""

from typing import Dict, Optional, Tuple

from tools.paper_strategy_equity import DEFAULT_EPOCH, SOURCE
from utils.logger import setup_logger

logger = setup_logger(__name__)

# 에포크 = tools/paper_strategy_equity.DEFAULT_EPOCH (2026-06-01, 첫 kis_template 레코드일)
EPOCH = DEFAULT_EPOCH
EPOCH_LABEL = EPOCH.isoformat()

# 에포크 종가를 찾기 위해 되돌아볼 일봉 행 수. 에포크는 60거래일 남짓 전이라
# 400 이면 넉넉하다. 창이 에포크를 못 덮으면 n/a 로 떨어진다(아래 참조).
EPOCH_LOOKBACK_ROWS = 400

_NA = "n/a"


# ── 포맷(순수함수) ─────────────────────────────────────────────────────────

def _fmt_pct(value: Optional[float]) -> str:
    return _NA if value is None else f"{value:+.2%}"


def _fmt_won(value: Optional[float]) -> str:
    return _NA if value is None else f"{int(round(value)):,}"


def _fmt_level(value: Optional[float]) -> str:
    """지수 레벨(정수 자리)."""
    return _NA if value is None else f"{value:,.0f}"


def format_benchmark_line(*, total: Optional[float], base: Optional[float],
                          day_return: Optional[float],
                          kospi_level: Optional[float], kospi_day: Optional[float],
                          kospi_cum: Optional[float],
                          kosdaq_level: Optional[float], kosdaq_day: Optional[float],
                          kosdaq_cum: Optional[float],
                          epoch_label: str = EPOCH_LABEL) -> str:
    """벤치마크 한 줄을 만든다. 어떤 인자가 None 이어도 예외 없이 ``n/a`` 로 찍는다.

    누적은 ``total/base - 1`` 로 **파생**한다 — 두 숫자가 서로 어긋날 여지를 없앤다.
    당일은 파생하지 않고 «equity 원장 안에서 이미 계산된» 값을 그대로 받는다
    (원장 혼용 금지 — 모듈 docstring 참조). 라벨에 출처를 박아 둔다.
    """
    cum = None
    if total is not None and base:
        cum = float(total) / float(base) - 1.0
    return (
        f"[벤치마크] 포트 총자금 {_fmt_won(total)}원 · "
        f"누적 {_fmt_pct(cum)}(기준 {_fmt_won(base)}원) · "
        f"당일(equity원장) {_fmt_pct(day_return)} "
        f"| KOSPI {_fmt_level(kospi_level)} 당일 {_fmt_pct(kospi_day)} · "
        f"{epoch_label} 이후 {_fmt_pct(kospi_cum)} "
        f"| KOSDAQ {_fmt_level(kosdaq_level)} 당일 {_fmt_pct(kosdaq_day)} · "
        f"{epoch_label} 이후 {_fmt_pct(kosdaq_cum)}"
    )


# ── 수집(DB·API) ───────────────────────────────────────────────────────────

def _safe_float(value) -> Optional[float]:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def fetch_total_funds(bot) -> Optional[float]:
    """FundManager 총자금 — EOD 자금 정합성 검증이 보고하는 그 값(``total_funds``)."""
    fund_manager = getattr(bot, "fund_manager", None)
    if fund_manager is None:
        return None
    return _safe_float(getattr(fund_manager, "total_funds", None))


def fetch_strategy_initial_capitals(bot) -> Dict[str, float]:
    """전략 폴더키 → 실제로 «배정된» 초기자본 (VirtualTradingManager 할당 SSOT).

    ``bot/initializer.py:488`` 의 ``vtm.allocate_strategy_capital(key, amount, ...)``
    이 채우는 바로 그 dict 를 읽는다. ``len(bot.strategies)`` 를 세지 않는 이유:
    on_init 에 실패한 전략은 ``main.py`` 가 ``strategies`` dict 에서 **삭제**하므로
    기준자본이 조용히 7천만으로 내려앉는다(그러면 누적 수익률이 부풀어 보인다).
    실전 모드처럼 할당이 없으면 빈 dict → 기준·당일 모두 ``n/a``.
    """
    vtm = getattr(getattr(bot, "decision_engine", None), "virtual_trading", None)
    allocated = getattr(vtm, "_strategy_initial", None)
    if not isinstance(allocated, dict):
        return {}
    out = {}
    for key, amount in allocated.items():
        value = _safe_float(amount)
        if value is not None:
            out[str(key)] = value
    return out


def _equity_sum_for_date(cur, trade_date, expected_strategies: int) -> Optional[float]:
    """해당 거래일의 Σequity — 단, 행 수가 기대 전략 수와 **정확히** 같을 때만.

    ``HAVING COUNT(*) = %s`` 가 가드다. 부분 적재일(전략 하나가 아직 안 써진 날)을
    그대로 더하면 「하루 만에 -12%」 같은 가짜 급락이 찍힌다 — 없는 것을 0 으로
    세는 대신 아예 ``n/a`` 로 떨어뜨린다.

    가드가 걸리면 **실제 행 수를 DEBUG 로 남긴다.** 그러지 않으면 「당일 n/a」가
    영구히 찍히는데 왜 그런지 알 길이 없다 — 조용한 계기 고장은 이 프로젝트의
    반복 실패 유형이다.
    """
    expected = int(expected_strategies)
    cur.execute(
        "SELECT SUM(equity) FROM paper_strategy_equity "
        "WHERE source = %s AND trade_date = %s "
        "HAVING COUNT(*) = %s",
        (SOURCE, trade_date, expected),
    )
    row = cur.fetchone()
    if row:
        return _safe_float(row[0])

    # 가드에 걸린 «이유» 를 남긴다(실패 경로에서만 도는 추가 조회 1회).
    actual = None
    try:
        cur.execute(
            "SELECT COUNT(*) FROM paper_strategy_equity "
            "WHERE source = %s AND trade_date = %s",
            (SOURCE, trade_date),
        )
        diag = cur.fetchone()
        actual = diag[0] if diag else None
    except Exception:  # 진단이 본 기능을 죽이면 안 된다
        pass
    logger.debug(
        "[벤치마크] equity 행수 불일치로 당일 n/a: trade_date=%s 기대=%s 실제=%s",
        trade_date, expected, actual,
    )
    return None


def fetch_equity_ledger_day_return(today, expected_strategies: int) -> Optional[float]:
    """당일 수익률을 **equity 원장 안에서만** 계산한다.

    ``Σequity(today) ÷ Σequity(trade_date < today 최신일) − 1``.

    🔴 분자를 FundManager 총자금으로 바꿔 끼우면 안 된다 — 두 원장은 정의가 달라
    (현금주의 vs 발생주의·평가 시점) 하루 0.6~1.5% 의 가짜 등락이 생긴다.
    이 함수가 오늘자 행을 요구하므로 호출측은 **EOD equity 재스냅샷(데이터 수집
    뒤) 다음**에 불러야 한다 — 1차 스냅샷 값은 보유분이 D-1 종가로 평가돼 있다.
    반대로 직전일 판정이 오늘을 주워오지 않는 근거는 순서가 아니라
    ``trade_date < today`` 의 **엄격 부등호**다.

    ``expected_strategies`` 는 «스냅샷이 실제로 쓴 전략 행 수» 여야 한다. 할당
    원장 수를 쓰면, 갓 배정돼 아직 체결이 없는 전략에서 두 수가 영구히 어긋난다
    (writer 는 virtual_trading_records 에 있는 전략만 쓴다).
    """
    if not expected_strategies:
        return None

    from db.connection import DatabaseConnection

    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            today_sum = _equity_sum_for_date(cur, today, expected_strategies)
            if today_sum is None:
                return None
            cur.execute(
                "SELECT MAX(trade_date) FROM paper_strategy_equity "
                "WHERE source = %s AND trade_date < %s",
                (SOURCE, today),
            )
            row = cur.fetchone()
            prev_date = row[0] if row else None
            if prev_date is None:
                return None
            prev_sum = _equity_sum_for_date(cur, prev_date, expected_strategies)
    return _ratio(today_sum, prev_sum)


def _get_index_data(index_code: str):
    """KIS 실시간 업종지수 조회(테스트에서 갈아끼우는 이음매)."""
    from api.kis_market_api import get_index_data
    return get_index_data(index_code)


def fetch_index_snapshot(index_code: str) -> Tuple[Optional[float], Optional[float]]:
    """(현재 지수레벨, 전일대비 **비율**). 실패 시 (None, None).

    KIS 는 ``bstp_nmix_prdy_ctrt`` 를 «퍼센트»로 준다 → 100 으로 나눠 비율로 맞춘다.
    """
    data = _get_index_data(index_code)
    if not isinstance(data, dict):
        return None, None
    level = _safe_float(data.get("bstp_nmix_prpr"))
    pct = _safe_float(data.get("bstp_nmix_prdy_ctrt"))
    return level, (None if pct is None else pct / 100.0)


def fetch_epoch_close(pseudo_ticker: str) -> Optional[float]:
    """에포크(2026-06-01) 당일 또는 그 이후 첫 거래일의 종가 — 의사티커 일봉에서.

    DB 는 ``resolve_daily_source_db()`` 를 경유하는 QuantDailyReader 가 정한다
    (DB명 하드코딩 금지). 조회 창이 에포크를 못 덮으면(=가장 오래된 행이 에포크보다
    뒤) ``첫 거래일`` 을 증명할 수 없으므로 None 을 돌려준다 — 엉뚱한 날을 에포크로
    삼아 조용히 틀린 수익률을 찍는 것보다 ``n/a`` 가 낫다.
    """
    import pandas as pd
    from db.quant_daily_reader import QuantDailyReader

    df = QuantDailyReader().get_daily_prices(
        pseudo_ticker, end_date=None, days=EPOCH_LOOKBACK_ROWS)
    if df is None or df.empty or "date" not in df.columns:
        return None
    epoch_ts = pd.Timestamp(EPOCH)
    if df["date"].min() > epoch_ts:
        return None
    on_or_after = df[df["date"] >= epoch_ts]
    if on_or_after.empty:
        return None
    return _safe_float(on_or_after.iloc[0]["close"])


def _ratio(now: Optional[float], then: Optional[float]) -> Optional[float]:
    if now is None or not then:
        return None
    return float(now) / float(then) - 1.0


def collect_benchmark_inputs(bot, today=None, expected_strategies=None) -> dict:
    """벤치마크 한 줄에 필요한 숫자를 모아 :func:`format_benchmark_line` 인자로 돌려준다.

    예외를 삼키지 않는다 — 호출측(SystemMonitor._log_eod_benchmark)이 WARNING 한 줄로
    흡수한다. ``get_index_data`` 는 자체적으로 실패를 None 으로 접으므로 지수 실패는
    ``n/a`` 로 나타난다.

    ``expected_strategies``: equity 행수 가드의 기대값(스냅샷이 쓴 전략 수).
    None/0 이면 할당 원장 수로 폴백한다.
    """
    if today is None:
        from utils.korean_time import now_kst
        today = now_kst().date()

    # 총자금·누적은 FundManager 원장(절대값 보고), 당일은 equity 원장(비율) —
    # 섞지 않는다.
    capitals = fetch_strategy_initial_capitals(bot)
    base = sum(capitals.values()) if capitals else None

    # 행수 가드 기대값: 1순위 = «스냅샷이 실제로 쓴 전략 수»(호출측이 넘긴 값),
    # 폴백 = 할당 원장 수. 두 수는 다를 수 있다 — 스냅샷 writer 는 체결 기록이
    # 있는 전략만 쓴다. 기준자본(base)은 폴백과 무관하게 «항상» 할당 원장 합이다.
    expected = expected_strategies if expected_strategies else len(capitals)
    day_return = (fetch_equity_ledger_day_return(today, int(expected))
                  if expected else None)

    # 분자가 없으면 분모를 읽지 않는다 — 어차피 n/a 인데 DB 를 한 번 더 칠 이유가 없다.
    kospi_level, kospi_day = fetch_index_snapshot("0001")
    kosdaq_level, kosdaq_day = fetch_index_snapshot("1001")
    kospi_cum = _ratio(kospi_level, fetch_epoch_close("KOSPI")) if kospi_level else None
    kosdaq_cum = _ratio(kosdaq_level, fetch_epoch_close("KOSDAQ")) if kosdaq_level else None

    return {
        "total": fetch_total_funds(bot),
        "base": base,
        "day_return": day_return,
        "kospi_level": kospi_level,
        "kospi_day": kospi_day,
        "kospi_cum": kospi_cum,
        "kosdaq_level": kosdaq_level,
        "kosdaq_day": kosdaq_day,
        "kosdaq_cum": kosdaq_cum,
        "epoch_label": EPOCH_LABEL,
    }
