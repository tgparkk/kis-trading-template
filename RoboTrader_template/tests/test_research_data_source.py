"""연구(백테스트/멀티버스) 데이터 소스 통일 회귀 테스트.

사장님 지시(2026-07-16): "연구도 kis_template DB로 통일해야 합니다."

배경 — 왜 기본값이 문제인가:
    라이브 봇은 `.env`(TIMESCALE_DB=kis_template + KIS_DATA_SOURCE=new)를 읽어 이미
    kis_template 을 본다. 그러나 `.env` 는 gitignore 대상이라 **clean checkout·격리
    워크트리·CI 에는 존재하지 않는다**. 연구 프로세스는 main.py 부트스트랩을 타지
    않으므로 `.env` 를 못 읽고 **코드 기본값**으로 떨어진다.
    → 따라서 "롤백 가능하되 기본값이 kis_template" 이어야 연구가 env 없이 실행돼도
      올바른 소스를 쓴다. 이 파일은 그 기본값을 회귀 고정한다.

소스 SSOT (실측 2026-07-16 — kis_template 이 양쪽 다 상위집합):
    | 소스                        | 종목  | 기간                  | 행수       |
    | kis_template.daily_prices   | 2,606 | 2021-01-04~2026-07-16 | 2,823,971  |
    | robotrader_quant.daily_prices | 2,604 | 2021-01-12~2026-07-10 | 2,810,230  |
    | kis_template.minute_candles | 1,445 | 20250224~20260716     | 55,941,645 |
    | robotrader.minute_candles   | 1,432 | 20250224~20260710     | 55,486,380 |
    레거시 두 소스는 형제 봇 중단으로 2026-07-10 동결(더 이상 갱신 안 됨).

의도된 예외 — 재무는 robotrader_quant 유지:
    `quant_financial_ratio`(45,473행)·`quant_balance_sheet`·`quant_income_statement`·
    `financial_statements` 는 **robotrader_quant 에만 존재**하고 kis_template 엔
    테이블 자체가 없다(실측: kis_template 에서 조회 시 "릴레이션이 없습니다").
    → 재무 경로만 quant 를 계속 본다. 이 예외는 test_financial_* 로 고정한다.
"""
import importlib
from datetime import date

import pytest

import config.constants as constants


# ===========================================================================
# 1) resolver 기본값 + 롤백 경로
# ===========================================================================

def _reload_constants(monkeypatch, **env):
    """env 를 적용한 상태로 config.constants 를 리로드해 반환."""
    for k in ("KIS_DATA_SOURCE", "QUANT_DB", "MINUTE_DB"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(constants)


def test_daily_resolver_defaults_to_kis_template(monkeypatch):
    """env 가 하나도 없어도(=연구 기본 실행) 일봉은 kis_template."""
    c = _reload_constants(monkeypatch)
    assert c.resolve_daily_source_db() == "kis_template"


def test_minute_resolver_defaults_to_kis_template(monkeypatch):
    """env 가 하나도 없어도(=연구 기본 실행) 분봉은 kis_template."""
    c = _reload_constants(monkeypatch)
    assert c.resolve_minute_source_db() == "kis_template"


def test_daily_resolver_legacy_rollback(monkeypatch):
    """롤백 경로 유지: KIS_DATA_SOURCE=legacy → 레거시 일봉 DB."""
    c = _reload_constants(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_daily_source_db() == "robotrader_quant"


def test_minute_resolver_legacy_rollback(monkeypatch):
    """롤백 경로 유지: KIS_DATA_SOURCE=legacy → 레거시 분봉 DB."""
    c = _reload_constants(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_minute_source_db() == "robotrader"


def test_daily_resolver_legacy_db_name_override(monkeypatch):
    """레거시 모드에서 DB명 자체도 override 가능(운영 유연성 유지)."""
    c = _reload_constants(monkeypatch, KIS_DATA_SOURCE="legacy", QUANT_DB="some_other_quant")
    assert c.resolve_daily_source_db() == "some_other_quant"


def test_minute_resolver_legacy_db_name_override(monkeypatch):
    c = _reload_constants(monkeypatch, KIS_DATA_SOURCE="legacy", MINUTE_DB="some_other_minute")
    assert c.resolve_minute_source_db() == "some_other_minute"


def test_legacy_db_name_override_ignored_in_new_mode(monkeypatch):
    """기본(new) 모드에서는 레거시 DB명 override 가 통하지 않는다.

    QUANT_DB 가 어딘가에 남아 있어도 연구가 조용히 죽은 레거시로 새지 않도록,
    소스 선택은 KIS_DATA_SOURCE 하나로만 제어된다(단일 스위치).
    """
    c = _reload_constants(monkeypatch, QUANT_DB="robotrader_quant", MINUTE_DB="robotrader")
    assert c.resolve_daily_source_db() == "kis_template"
    assert c.resolve_minute_source_db() == "kis_template"


# ===========================================================================
# 2) pit_reader — 우회 지점 제거 (별도 env TIMESCALE_QUANT_DB 폐지)
# ===========================================================================

def test_pit_reader_daily_conn_targets_kis_template():
    """pit_reader 일봉 연결은 resolver 를 경유해 kis_template 에 붙는다.

    (기존: _QUANT_DB = getenv("TIMESCALE_QUANT_DB", "robotrader_quant") — resolver 우회)
    """
    from multiverse.data import pit_reader
    with pit_reader._conn_daily() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "kis_template"


def test_pit_reader_daily_conn_follows_legacy_rollback(monkeypatch):
    """롤백: KIS_DATA_SOURCE=legacy 면 pit_reader 일봉도 레거시로 되돌아간다."""
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    from multiverse.data import pit_reader
    with pit_reader._conn_daily() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "robotrader_quant"


def test_pit_reader_has_no_separate_quant_db_env():
    """중복 env(TIMESCALE_QUANT_DB) 는 제거되고 resolver 하나로 수렴한다."""
    from pathlib import Path
    src = Path(__import__("multiverse.data.pit_reader", fromlist=["x"]).__file__)
    text = src.read_text(encoding="utf-8")
    assert "TIMESCALE_QUANT_DB" not in text, (
        "TIMESCALE_QUANT_DB 는 resolver 를 우회하는 중복 스위치 — 제거돼야 함"
    )


# ===========================================================================
# 3) 재무 = robotrader_quant 유지 (의도된 예외)
# ===========================================================================

def test_financial_conn_stays_on_quant():
    """재무 경로는 kis_template 로 옮기면 안 된다 — 테이블 자체가 없다."""
    from multiverse.data import pit_reader
    with pit_reader._conn_financial() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "robotrader_quant"


def test_financial_conn_unaffected_by_data_source_flag(monkeypatch):
    """재무 예외는 KIS_DATA_SOURCE 와 무관하게 항상 quant (플래그 오염 방지)."""
    monkeypatch.setenv("KIS_DATA_SOURCE", "new")
    from multiverse.data import pit_reader
    with pit_reader._conn_financial() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "robotrader_quant"


def test_read_financial_ratio_still_works():
    """재무 읽기가 실제로 동작한다(kis_template 로 잘못 옮기면 relation 없음 에러)."""
    from multiverse.data import pit_reader
    out = pit_reader.read_financial_ratio("005930", date(2026, 6, 1))
    assert out is not None, "삼성전자 재무비율은 quant 에 존재해야 함"
    assert "roe" in out


def test_read_financial_ratio_works_inside_backtest_session():
    """backtest_session(일봉 재사용 연결) 안에서도 재무는 quant 로 읽어야 한다.

    일봉과 재무가 서로 다른 DB 로 갈라졌으므로, 단일 재사용 연결을 재무에까지
    쓰면 kis_template 에서 quant_financial_ratio 를 찾다 실패한다(회귀 가드).
    """
    from multiverse.data import pit_reader
    with pit_reader.backtest_session():
        out = pit_reader.read_financial_ratio("005930", date(2026, 6, 1))
        assert out is not None
        assert "roe" in out


# ===========================================================================
# 4) adj_factor 곱셈 금지 규약 (불변)
#    daily_prices.close 는 이미 분할조정된 연속 시세다. adj_factor 를 곱하면
#    이중조정되어 분할일에 가짜 절벽이 생긴다(과거 Minervini MaxDD 를 거짓 99%
#    로 부풀린 버그). 실측(2026-07-16, kis_template):
#      035720 2021-04-14 close=112,000 adj_factor=5 → 곱하면 560,000
#      035720 2021-04-15 close=120,500 adj_factor=1 → 120,500
#      ⇒ 곱한 시계열은 분할일에 -78.5% 가짜 폭락. raw 는 +7.6%(정상).
# ===========================================================================

def test_read_daily_does_not_multiply_adj_factor_on_split():
    """카카오 5:1 분할(2021-04-15) 구간에 가짜 절벽이 없어야 한다.

    adj_factor 를 곱하면 -78.5% 가짜 폭락이 발생한다(한국 가격제한 ±30% 초과 =
    물리적으로 불가능한 수익률이므로 판별 가능).
    """
    from multiverse.data import pit_reader
    df = pit_reader.read_daily("035720", date(2021, 5, 1), lookback_days=30)
    assert not df.empty, "카카오 일봉이 로드돼야 함"
    rets = df["close"].astype(float).pct_change().dropna()
    assert rets.min() > -0.30, (
        f"분할일 가짜 절벽 감지(min daily ret={rets.min():.4f}) — "
        f"adj_factor 이중조정 의심"
    )


def test_read_daily_returns_raw_adjusted_close_values():
    """반환 close 가 DB 의 raw close 와 동일해야 한다(어떤 배율도 곱하지 않음).

    분할 전날(2021-04-14) close 는 DB raw 112,000. adj_factor(=5)를 곱한
    560,000 이 나오면 이중조정이다.
    """
    from multiverse.data import pit_reader
    df = pit_reader.read_daily("035720", date(2021, 4, 15), lookback_days=5)
    assert not df.empty
    last = df.iloc[-1]
    assert str(last["date"]) == "2021-04-14", "PIT: as_of_date 미만 최신일"
    assert float(last["close"]) == pytest.approx(112000.0), (
        f"raw close(112,000) 이어야 함 — 실제 {last['close']} "
        f"(560,000 이면 adj_factor 5 를 곱한 이중조정)"
    )


def test_pit_reader_source_has_no_adj_factor_multiplication():
    """소스 레벨 가드 — adj_factor 곱셈 SQL 이 재유입되지 않도록 고정."""
    from pathlib import Path
    from multiverse.data import pit_reader
    text = Path(pit_reader.__file__).read_text(encoding="utf-8")
    assert "* COALESCE(adj_factor" not in text, (
        "adj_factor 곱셈 금지 규약 위반 — close 는 이미 분할조정된 연속 시세"
    )


def test_read_open_does_not_multiply_adj_factor():
    """read_open 도 동일 규약 — 시가가 raw 여야 한다.

    검체 선정 주의: 035720 의 분할 전 구간은 open/high/low 가 0 이라
    (0 × adj_factor = 0) 곱셈 버그를 탐지하지 못한다(가짜 통과).
    → open>0 이면서 adj_factor>1 인 실제 행을 쓴다.
      실측: 000860 2021-01-12 open=10,178 adj_factor=2 → 곱하면 20,356.
    """
    from multiverse.data import pit_reader
    px = pit_reader.read_open("000860", date(2021, 1, 12))
    assert px is not None
    assert float(px) == pytest.approx(10178.0), (
        f"raw open(10,178) 이어야 함 — 실제 {px} "
        f"(20,356 이면 adj_factor 2 를 곱한 이중조정)"
    )


# ===========================================================================
# 5) NULL adj_factor 방어
#    kis_template.daily_prices 에는 adj_factor NULL 행이 44,923개 존재한다
#    (robotrader_quant 는 같은 자리에 1.0). KOSPI 지수행 1,357 개는 전부 NULL.
#    → 곱하지 않으므로 NaN 전파 자체가 발생하지 않아야 한다.
# ===========================================================================

def test_null_adj_factor_rows_do_not_produce_nan():
    """adj_factor 가 NULL 인 종목도 OHLC 에 NaN 이 섞이지 않는다."""
    from multiverse.data import pit_reader
    # KOSPI 지수행: kis_template 에서 adj_factor 가 전 행 NULL (실측)
    df = pit_reader.read_daily("KOSPI", date(2026, 7, 1), lookback_days=20)
    assert not df.empty, "KOSPI 지수 일봉이 kis_template 에 있어야 함"
    for col in ("open", "high", "low", "close"):
        assert df[col].notna().all(), f"{col} 에 NaN 전파 — NULL adj_factor 방어 실패"


def test_load_daily_adj_null_adj_factor_no_nan():
    """멀티버스 일봉 로더도 NULL adj_factor 행에서 NaN 이 없어야 한다.

    _load_daily_adj 는 adj_factor 를 SELECT 하지만 산술에 쓰지 않는다(곱셈 금지).
    → NULL 이어도 OHLC 로 전파되지 않는다.
    """
    from scripts import book_param_multiverse as bpm
    # 046940: adj_factor NULL 행 보유 종목(실측)
    data = bpm._load_daily_adj(["046940"], "2021-01-01", "2026-07-16")
    assert "046940" in data
    df = data["046940"]
    for col in ("open", "high", "low", "close"):
        assert df[col].notna().all(), f"{col} 에 NaN — NULL adj_factor 전파"


# ===========================================================================
# 6) 나머지 우회 지점 — calendar_tom / portfolio_engine / env 수렴
# ===========================================================================

def test_calendar_tom_reads_kis_template_by_default():
    """lib/signals/calendar_tom 은 daily_prices 를 읽으므로 일봉 resolver 를 따른다.

    행동 증거: 레거시 동결일(2026-07-10) 이후 영업일이 보이면 kis_template 이다
    (robotrader_quant 는 2026-07-10 에서 멈춤).
    """
    from lib.signals.calendar_tom import get_trading_calendar
    cal = get_trading_calendar(date(2026, 7, 1), date(2026, 7, 16))
    assert cal, "영업일 캘린더가 비면 안 됨"
    assert max(cal) > date(2026, 7, 10), (
        f"동결(07-10) 이후 영업일이 없다 → 여전히 레거시를 읽는 중 (max={max(cal)})"
    )


def test_calendar_tom_legacy_rollback(monkeypatch):
    """롤백 시 calendar_tom 도 레거시로 되돌아간다(동결일 이후 영업일 없음)."""
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    from lib.signals.calendar_tom import get_trading_calendar
    cal = get_trading_calendar(date(2026, 7, 1), date(2026, 7, 16))
    assert max(cal) <= date(2026, 7, 10), "레거시는 2026-07-10 동결"


def test_portfolio_engine_uses_pit_reader_daily_conn():
    """portfolio_engine 거래일 조회가 resolver 경유 연결을 쓴다(소스 가드).

    multiverse.engine 은 import 체인이 무거워(그리고 이 워크트리에선 multiverse/data
    패키지가 .gitignore 에 먹혀 불완전) 행동 테스트가 불가 → 소스 레벨로 고정한다.
    """
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "multiverse" / "engine" / "portfolio_engine.py"
    text = src.read_text(encoding="utf-8")
    assert "pit_reader._conn_daily()" in text, "resolver 경유 연결을 써야 함"
    assert "pit_reader._QUANT_DB" not in text, "resolver 우회 상수 참조가 남아 있음"


def test_no_lingering_duplicate_source_envs():
    """중복 소스 env 를 **실제로 읽는** 코드가 없는지 리포 전역 가드.

    TIMESCALE_QUANT_DB / REBOUND_MINUTE_DB / REBOUND_DAILY_DB 는 KIS_DATA_SOURCE
    하나로 수렴됐다. 이력을 설명하는 주석·docstring 언급은 허용하고(그 편이 다음
    사람에게 유용하다) `os.getenv("X")` / `os.environ["X"]` 같은 **읽기**만 잡는다.
    (archive/ 는 동결된 과거 산출물이라 제외.)
    """
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    banned = ("TIMESCALE_QUANT_DB", "REBOUND_MINUTE_DB", "REBOUND_DAILY_DB")
    # 실제 env 읽기 패턴만: getenv("X" / environ["X"] / environ.get("X"
    patterns = {
        tok: re.compile(r"""(getenv\(|environ\[|environ\.get\()\s*["']%s["']""" % tok)
        for tok in banned
    }
    offenders = []
    for path in root.rglob("*.py"):
        parts = path.parts
        if "archive" in parts or "__pycache__" in parts or "venv" in parts:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue  # 이 테스트 자신(패턴 문자열 보유)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for tok, pat in patterns.items():
            if pat.search(text):
                offenders.append(f"{path.relative_to(root)}:{tok}")
    assert offenders == [], f"중복 소스 env 를 읽는 코드 재유입: {offenders}"
