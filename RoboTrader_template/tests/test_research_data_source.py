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

재무도 kis_template 으로 통일 (2026-08-16 DB 통합):
    과거에는 `quant_financial_ratio`(45,473행)·`quant_balance_sheet`·
    `quant_income_statement`·`financial_statements` 가 **robotrader_quant 에만 존재**해
    「의도된 예외」였다. 2026-08-16 사장님 원칙 「DB 는 kis_template 하나로」에 따라
    전부 이관됐고(전행 해시 검증 통과, 원본 미삭제) 예외는 **해소**됐다.
    → 재무 경로도 kis_template 을 본다. 이 사실을 test_financial_* 로 고정한다.

    ⚠️ 단 재무는 **가격 resolver 를 따르지 않는다** — 재무 override 는
    `QUANT_FINANCIAL_DB` 로 독립 제어한다. 그 비결합도 아래에서 고정한다.

🔴 2026-08-17 — 롤백 스위치 폐지로 **계약이 뒤집혔다**:
    이 파일은 원래 「`KIS_DATA_SOURCE=legacy` 면 레거시 DB 로 되돌아간다」를 단언했다.
    이제는 그 반대 —— **「넣어도 무시된다」**를 단언한다. 이유:
      1) 레거시 두 소스는 2026-07-10 동결이라 되돌려도 죽은 데이터였다(쓸 수 없는 기능).
      2) `robotrader` DB 는 통합 후 **삭제**된다. 스위치가 남으면 「누르면 죽는 버튼」이다.
    ⇒ 옛 사실을 단언하는 테스트를 그대로 두면 이 폐기 작업이 「회귀」로 오탐된다.
      테스트를 지우지 않고 **계약을 뒤집었다**(음성 대조 = 폐지 env 를 실제로 주입).
"""
import importlib
import sys
from datetime import date
from pathlib import Path

import pytest

# multiverse/data/ 는 현재 .gitignore 의 `data/` 패턴에 먹혀 __init__.py 가 git
# 미추적이다(별건 이슈). 그래서 지금은 PEP 420 네임스페이스 패키지로 import 된다.
# 별건 수정으로 __init__.py 가 커밋되면 일반 패키지가 되는데, 그 __init__.py 는
# `from RoboTrader_template.multiverse.data import ...` 를 하므로 **repo 루트**
# (RoboTrader_template 의 부모)가 sys.path 에 있어야 import 된다.
# 두 상태 모두에서 이 파일이 돌도록 repo 루트를 미리 넣어둔다.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import config.constants as constants  # noqa: E402


# ===========================================================================
# 1) resolver = 항상 kis_template + **폐지된 롤백 스위치는 무시된다**
# ===========================================================================

# 2026-08-17 폐지된 소스 env 전부. 「설정해도 아무 일도 안 일어난다」를 단언하는 데 쓴다.
_RETIRED_SOURCE_ENVS = ("KIS_DATA_SOURCE", "QUANT_DB", "MINUTE_DB", "CORP_EVENTS_DB")


def _reload_constants(monkeypatch, **env):
    """env 를 적용한 상태로 config.constants 를 리로드해 반환."""
    for k in _RETIRED_SOURCE_ENVS:
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


def test_corp_events_resolver_defaults_to_kis_template(monkeypatch):
    """env 가 하나도 없어도(=연구 기본 실행) 기업이벤트는 kis_template.

    기존: corp_events._DB_DEFAULTS 가 getenv("TIMESCALE_DB", "robotrader") 라
    연구(.env 없음)가 **동결된 robotrader**(2026-05-22 stale)를 읽었다.
    """
    c = _reload_constants(monkeypatch)
    assert c.resolve_corp_events_source_db() == "kis_template"


# --- 음성 대조: 폐지된 스위치를 «실제로 넣고» 무반응을 확인 -------------------

def test_daily_resolver_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] KIS_DATA_SOURCE=legacy 를 넣어도 일봉은 kis_template.

    (2026-08-17 이전: robotrader_quant 를 단언했다. 그 DB 는 2026-07-10 동결이라
     되돌려도 죽은 데이터였고, 롤백 스위치는 `robotrader` 삭제와 함께 폐지됐다.)
    """
    c = _reload_constants(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_daily_source_db() == "kis_template"


def test_minute_resolver_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] KIS_DATA_SOURCE=legacy 를 넣어도 분봉은 kis_template."""
    c = _reload_constants(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_minute_source_db() == "kis_template"


def test_corp_events_resolver_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] KIS_DATA_SOURCE=legacy 를 넣어도 이벤트는 kis_template."""
    c = _reload_constants(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_corp_events_source_db() == "kis_template"


def test_retired_db_name_override_envs_are_inert(monkeypatch):
    """[계약 반전] 폐지된 DB명 override env 는 **전부 무시**된다.

    예전엔 legacy 모드에서 QUANT_DB/MINUTE_DB/CORP_EVENTS_DB 로 대상 DB명을
    바꿀 수 있었다. 지금은 legacy 를 켜든 안 켜든 아무 효과가 없어야 한다.
    (스위치가 「반쯤 살아 있는」 상태가 가장 위험하므로 두 조합 모두 고정한다.)
    """
    for extra in ({}, {"KIS_DATA_SOURCE": "legacy"}):
        c = _reload_constants(
            monkeypatch,
            QUANT_DB="some_other_quant",
            MINUTE_DB="some_other_minute",
            CORP_EVENTS_DB="some_other_events",
            **extra,
        )
        assert c.resolve_daily_source_db() == "kis_template", extra
        assert c.resolve_minute_source_db() == "kis_template", extra
        assert c.resolve_corp_events_source_db() == "kis_template", extra


def test_all_three_resolvers_agree_under_any_env(monkeypatch):
    """세 resolver 는 어떤 env 조합에서도 **갈라지지 않는다**.

    폐지 전에는 「같은 스위치를 공유한다」로 이 성질을 지켰다. 스위치가 사라진
    지금은 상수라서 자명하지만, 누군가 resolver 하나에만 env 분기를 되살리면
    여기서 잡힌다(그게 예전에 사고가 났던 형태다).
    """
    for env in ({}, {"KIS_DATA_SOURCE": "legacy"}, {"KIS_DATA_SOURCE": "new"},
                {"KIS_DATA_SOURCE": "legacy", "MINUTE_DB": "x", "QUANT_DB": "y"}):
        c = _reload_constants(monkeypatch, **env)
        got = {c.resolve_daily_source_db(),
               c.resolve_minute_source_db(),
               c.resolve_corp_events_source_db()}
        assert got == {"kis_template"}, f"env={env} → {got}"


def test_retired_switch_symbols_are_gone_from_constants():
    """소스 레벨 가드 — 폐지된 스위치가 슬쩍 되살아나지 않도록 고정.

    `_is_legacy_source` / 모듈 상수 `KIS_DATA_SOURCE` / 폐지 env 읽기가
    config/constants.py 에 다시 나타나면 실패한다.
    """
    import re
    from pathlib import Path
    text = Path(constants.__file__).read_text(encoding="utf-8")
    assert not hasattr(constants, "_is_legacy_source"), "롤백 판정 함수가 되살아났다"
    assert not hasattr(constants, "KIS_DATA_SOURCE"), "롤백 플래그 상수가 되살아났다"
    for tok in _RETIRED_SOURCE_ENVS:
        assert not re.search(
            r"""(getenv\(|environ\[|environ\.get\()\s*["']%s["']""" % tok, text
        ), f"폐지된 소스 env {tok} 를 다시 읽고 있다"


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


def test_pit_reader_daily_conn_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] 폐지 env 를 넣어도 pit_reader 일봉은 kis_template 에 붙는다.

    (2026-08-17 이전: robotrader_quant 를 단언 = 롤백이 «작동함»을 고정했다.)
    행동 증거 — 실제로 연결해 current_database() 를 읽는다.
    """
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    monkeypatch.setenv("QUANT_DB", "some_other_quant")
    from multiverse.data import pit_reader
    with pit_reader._conn_daily() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "kis_template"


def test_pit_reader_has_no_separate_quant_db_env():
    """중복 env(TIMESCALE_QUANT_DB) 는 제거되고 resolver 하나로 수렴한다."""
    from pathlib import Path
    src = Path(__import__("multiverse.data.pit_reader", fromlist=["x"]).__file__)
    text = src.read_text(encoding="utf-8")
    assert "TIMESCALE_QUANT_DB" not in text, (
        "TIMESCALE_QUANT_DB 는 resolver 를 우회하는 중복 스위치 — 제거돼야 함"
    )


# ===========================================================================
# 3) 재무 = kis_template (2026-08-16 이관으로 예외 해소)
# ===========================================================================

def test_financial_conn_defaults_to_kis_template():
    """재무 경로도 kis_template 을 본다 (2026-08-16 이관 후).

    이전에는 robotrader_quant 를 단언했다 — kis_template 에 재무 테이블이 아예
    없었기 때문. 이관으로 그 전제가 사라졌으므로 단언을 새 사실로 뒤집는다.
    """
    from multiverse.data import pit_reader
    with pit_reader._conn_financial() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "kis_template"


def test_financial_conn_unaffected_by_data_source_flag(monkeypatch):
    """재무는 가격 경로와 **비결합**이다 — 폐지된 KIS_DATA_SOURCE 에도 무반응.

    (스위치 폐지 후에도 이 가드를 남긴다: 누군가 가격 플래그를 되살리면서 재무까지
     끌고 가는 배선을 하면 여기서 잡힌다. 재무 override 는 QUANT_FINANCIAL_DB 하나뿐.)
    """
    for flag in ("new", "legacy"):
        monkeypatch.setenv("KIS_DATA_SOURCE", flag)
        from multiverse.data import pit_reader
        with pit_reader._conn_financial() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                assert cur.fetchone()[0] == "kis_template", f"KIS_DATA_SOURCE={flag}"


def test_financial_db_env_override_still_exists():
    """재무 롤백 스위치(QUANT_FINANCIAL_DB)는 살아 있어야 한다.

    기본값만 바뀌었을 뿐 override 경로를 지운 게 아니다 — 이관 원본과 대조할 때 쓴다.
    """
    from pathlib import Path
    src = Path(__import__("multiverse.data.pit_reader", fromlist=["x"]).__file__)
    assert "QUANT_FINANCIAL_DB" in src.read_text(encoding="utf-8")


def test_read_financial_ratio_still_works():
    """재무 읽기가 실제로 동작한다(이관 누락이면 relation 없음 에러)."""
    from multiverse.data import pit_reader
    out = pit_reader.read_financial_ratio("005930", date(2026, 6, 1))
    assert out is not None, "삼성전자 재무비율은 kis_template 에 존재해야 함"
    assert "roe" in out


def test_read_financial_ratio_works_inside_backtest_session():
    """backtest_session(일봉 재사용 연결) 안에서도 재무 읽기가 동작한다.

    가격·재무 연결은 이관 후에도 분리돼 있다(두 DB 이름이 서로 독립적으로 갈라질 수
    있으므로 — pit_reader.backtest_session docstring 참조). 그 분리가 재무 읽기를
    깨뜨리지 않는지 고정한다.
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
    assert "* COALESCE(adj_factor" not in text, (  # adj-factor-lint: ignore (가드 자신의 단언 리터럴)
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


def test_calendar_tom_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] 폐지 env 를 넣어도 calendar_tom 은 kis_template 을 읽는다.

    (2026-08-17 이전: `max(cal) <= 2026-07-10` = 동결 레거시로 «되돌아감»을 단언했다.)
    비-vacuous: 동결일 이후 영업일이 보이면 kis_template 이라는 행동 증거다.
    """
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    monkeypatch.setenv("QUANT_DB", "some_other_quant")
    from lib.signals.calendar_tom import get_trading_calendar
    cal = get_trading_calendar(date(2026, 7, 1), date(2026, 7, 16))
    assert cal, "영업일 캘린더가 비면 안 됨"
    assert max(cal) > date(2026, 7, 10), (
        f"동결(07-10) 이후 영업일이 없다 → 폐지된 스위치가 아직 살아 있다 (max={max(cal)})"
    )


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


# ===========================================================================
# 7) corp_events = 시장 참조 데이터 → 가격과 같은 스위치, TIMESCALE_DB 비의존
#    실측(2026-07-17): kis_template 1,205행/최신 2026-07-16
#                      robotrader   1,085행/최신 2026-05-22 (동결)
#    두 DB 의 컬럼 집합은 동일(stock_code/event_type/event_date/end_date/meta).
# ===========================================================================

def test_corp_events_conn_targets_kis_template():
    """corp_events 연결은 resolver 를 경유해 kis_template 에 붙는다."""
    from multiverse.data import corp_events
    with corp_events._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "kis_template"


def test_corp_events_conn_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] 폐지 env 를 넣어도 이벤트 연결은 kis_template 이다.

    (2026-08-17 이전: robotrader 를 단언 = 롤백이 «작동함»을 고정했다.)
    """
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    monkeypatch.setenv("CORP_EVENTS_DB", "some_other_events")
    from multiverse.data import corp_events
    with corp_events._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "kis_template"


def test_corp_events_conn_resolves_db_at_call_time(monkeypatch):
    """DB명은 **호출 시점**에 resolver 로 정해진다(import 시점에 굳지 않는다).

    옛 `_DB_DEFAULTS` 모듈 상수 구조로 되돌아가면 여기서 잡힌다. resolver 가
    이제 상수를 돌려주므로 env 로는 관측할 수 없어졌다 → resolver 자체를
    가로채서 「연결할 때마다 다시 물어본다」를 확인한다(비-vacuous 유지).
    """
    from multiverse.data import corp_events
    calls = []

    def _spy():
        calls.append(1)
        return "kis_template"

    monkeypatch.setattr(corp_events, "resolve_corp_events_source_db", _spy)
    with corp_events._conn():
        pass
    with corp_events._conn():
        pass
    assert len(calls) == 2, (
        f"연결마다 resolver 를 호출해야 한다 — 실제 {len(calls)}회 "
        f"(0이면 DB명이 import 시점에 굳은 것)"
    )


def test_corp_events_does_not_read_timescale_db_env():
    """corp_events 는 TIMESCALE_DB 를 읽으면 안 된다 — 운영 env 오염 차단.

    TIMESCALE_DB 는 **라이브 봇 운영 env** 이고, scripts/kis_db/smoke_state_restore.py
    가 os.environ["TIMESCALE_DB"] 를 테스트 DB 로 덮고 복구하지 않는다(알려진 이슈).
    이벤트 소스가 TIMESCALE_DB 를 읽으면 연구가 조용히 테스트 DB 를 따라간다.
    시장 참조 데이터는 가격 resolver 들과 동일하게 KIS_DATA_SOURCE 만 따른다.
    """
    from pathlib import Path
    from multiverse.data import corp_events
    text = Path(corp_events.__file__).read_text(encoding="utf-8")
    import re
    assert not re.search(
        r"""(getenv\(|environ\[|environ\.get\()\s*["']TIMESCALE_DB["']""", text
    ), "corp_events 가 TIMESCALE_DB(운영 env)를 읽고 있다 — resolver 로 수렴해야 함"


def test_corp_events_sees_events_newer_than_legacy_freeze():
    """행동 증거 — 레거시 동결(2026-05-22) 이후 이벤트가 실제로 보여야 한다.

    검체 196170(bonus_issue 2026-07-16): kis_template 1건 / robotrader **0건**(실측).
    → robotrader 를 읽고 있으면 빈 DataFrame 이라 반드시 실패한다(비-vacuous).
    """
    from multiverse.data import corp_events
    df = corp_events.read_events("196170", date(2026, 7, 17))
    assert not df.empty, (
        "196170 이벤트가 안 보인다 → 동결된 레거시(robotrader)를 읽는 중"
    )
    assert df["event_date"].max() > date(2026, 5, 22)


def test_get_adj_factor_reads_daily_price_source(monkeypatch):
    """get_adj_factor 는 daily_prices 를 읽으므로 **일봉** resolver 를 따라야 한다.

    기존엔 corp_events._DB_DEFAULTS(=TIMESCALE_DB, 기본 robotrader)로 daily_prices
    를 읽어 **일봉 SSOT 를 우회**하고 있었다. 그 회귀를 막는 테스트다.

    🔑 판별력 유지 방법이 바뀌었다: 예전엔 `KIS_DATA_SOURCE=legacy` 로 두 소스를
      서로 다른 DB(일봉=robotrader_quant / 이벤트=robotrader)로 «갈라놓고» 확인했다.
      스위치가 폐지돼 두 resolver 가 같은 값을 돌려주는 지금 그 방법을 쓰면
      **아무것도 구별하지 못하는 vacuous 테스트**가 된다.
      → resolver 두 개를 서로 다른 sentinel 로 몽키패치해 갈라놓는다.
        (실제 연결은 하지 않는다 — connect 를 가로채 DB명만 확인한다.)
    """
    import psycopg2 as pg
    from multiverse.data import corp_events

    monkeypatch.setattr(corp_events, "resolve_daily_source_db", lambda: "sentinel_daily")
    monkeypatch.setattr(
        corp_events, "resolve_corp_events_source_db", lambda: "sentinel_events")

    captured = []

    class _Boom(Exception):
        pass

    def _spy(**kwargs):
        captured.append(kwargs.get("database"))
        raise _Boom("연결까지 갈 필요 없음 — DB명만 확인")

    monkeypatch.setattr(pg, "connect", _spy)
    # 1순위(daily_prices) 조회 실패는 get_adj_factor 가 흡수하고 corp_events 폴백으로
    # 넘어간다 → 그 폴백 연결에서 _Boom 이 다시 나 밖으로 전파된다. 여기서 잡는다:
    # 우리가 확인하려는 건 «첫 connect 의 DB명» 뿐이다.
    try:
        corp_events.get_adj_factor("005930", date(2026, 4, 1))
    except _Boom:
        pass

    assert captured, "connect 가 호출되지 않음 — 테스트가 아무것도 검증 못 함"
    assert captured[0] == "sentinel_daily", (
        f"daily_prices 를 일봉 소스가 아닌 '{captured[0]}' 에서 읽고 있다"
        f" (sentinel_events 면 이벤트 소스를 잘못 쓰는 것)"
    )


def test_no_lingering_duplicate_source_envs():
    """중복 소스 env 를 **실제로 읽는** 코드가 없는지 리포 전역 가드.

    TIMESCALE_QUANT_DB / REBOUND_MINUTE_DB / REBOUND_DAILY_DB 는 먼저 KIS_DATA_SOURCE
    하나로 수렴됐고, 그 KIS_DATA_SOURCE(+ QUANT_DB / MINUTE_DB / CORP_EVENTS_DB)마저
    2026-08-17 **폐지**됐다. 이력을 설명하는 주석·docstring 언급은 허용하고(그 편이
    다음 사람에게 유용하다) `os.getenv("X")` / `os.environ["X"]` 같은 **읽기**만 잡는다.
    (archive/ 는 동결된 과거 산출물이라 제외.)

    🔑 이게 「스위치가 정말 죽었는가」의 리포 전역 음성 대조다 — resolver 만 고쳐도
      다른 모듈이 몰래 env 를 읽고 있으면 반쯤 살아 있는 스위치가 남는다.

    🔴 2026-08-17 범위·검증 보강 (탐지 규칙은 **불변** — 무엇을 위반으로 보는가는
      그대로다. 「어디를 훑는가」와 「정말 훑었는가」만 손봤다):
      ① **루트를 `parents[1]` → `parents[2]`(리포 루트)로 넓혔다.**
        형제 DROP 게이트와 **같은 이유**다 — 리포 루트 `scripts/` 에도 연구 코드가
        산다. 특히 `scripts/10pct_strategy/p0_backfill_corp_events.py` 는
        corp_events 에 **INSERT** 하는 쓰기 스크립트라, 대상 DB를 `CORP_EVENTS_DB`
        로 고르는 배선이 재유입되기 딱 좋은 자리인데 `parents[1]` 은 그걸 못 본다.
        실측(2026-08-17): 넓혀서 새로 훑는 추적 .py 는 **3개뿐**이고
          · scripts/10pct_strategy/_p0_worker.py
          · scripts/10pct_strategy/p0_backfill_corp_events.py
          · scripts/run_multiverse_smoke.py
        셋 다 폐지 토큰을 **문자열로도 갖고 있지 않다**(읽기 0 · 언급 0)
        ⇒ 넓혀도 새로 걸리는 건 없다. 지금 사는 걸 깨지 않고 「구멍만」 막는다.
      ② **`rglob`(디스크의 .py 전부) → git 추적 .py** 로 바꿨다. 두 게이트가 같은
        헬퍼(`_drop_gate_scan_paths`, 아래 정의)를 공유하므로 「저장소가 배포하는
        것」의 정의가 **하나**다 — 한쪽 게이트만 스크래치에 뚫리는 사고가 구조적으로
        불가능해진다. 종전 `rglob` 은 미추적 스크래치(`.omc/scientist/scripts/` 등)
        까지 훑어 **체크아웃마다 답이 달랐다**(DROP 게이트가 2026-08-17 에 실제로
        그렇게 빨개졌다. 이 게이트는 그 스크래치가 마침 폐지 env 를 안 써서
        «우연히» 초록이었을 뿐이다).
      ③ ⚠️ 공유 헬퍼를 쓰면 `_DROP_GATE_ALLOWED_DIRS` 의 `kis_db` 도 함께 빠진다
        (종전 이 게이트는 `archive` 만 뺐다). 실측: allowlist 로 빠지는 추적 .py
        90개(archive 76 + kis_db 14) 중 폐지 env **읽기는 0건** ⇒ 지금은 탐지력
        손실이 없다. 그리고 `scripts/kis_db/` 는 레거시→kis 「이관 전용」 도구라
        레거시 DB 를 가리키는 것이 설계다(DROP 게이트가 같은 이유로 이미 면제한다).
      ④ **「훑은 양」을 offenders 보기 «전에» 단언**한다 — 아래 바닥값 주석 참조.
    """
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    banned = ("TIMESCALE_QUANT_DB", "REBOUND_MINUTE_DB", "REBOUND_DAILY_DB") \
        + _RETIRED_SOURCE_ENVS
    # 실제 env 읽기 패턴만: getenv("X" / environ["X"] / environ.get("X"
    patterns = {
        tok: re.compile(r"""(getenv\(|environ\[|environ\.get\()\s*["']%s["']""" % tok)
        for tok in banned
    }

    # 🔴 git 을 못 쓰면 **조용히 통과시키지 않는다** (DROP 게이트와 동일 처리).
    #   추적 목록 없이 「0개 훑고 초록불」이 되는 것보다 눈에 보이는 skip 이 낫다.
    try:
        scanned = _drop_gate_scan_paths(root)
    except _GitUnavailable as exc:
        pytest.skip(
            f"env 게이트를 실행할 수 없다 — {exc} (root={root}). "
            "추적 목록 없이 「0개 훑고 통과」가 되는 것을 막기 위해 skip 한다."
        )

    # 🔑 「입력이 비어 있음」과 「위반이 없음」은 **같은 얼굴로** 통과한다.
    #   root 오지정·git 이상으로 0개를 훑고도 초록불이 뜨는 게 이 프로젝트의 대표
    #   실패 형태(「거짓 통과」)다. 그래서 **훑은 양을 offenders 보기 전에** 단언한다.
    #
    #   바닥값 근거(실측 2026-08-17, 이 게이트와 DROP 게이트는 «같은 목록»을 쓴다):
    #     · 훑는 파일 1,042개 → 바닥 700. 파일 수라서 env 정리 작업으로 줄지 않는다
    #       ⇒ **주 가드**. DROP 게이트와 입력이 동일하므로 바닥값도 같은 700 을 쓴다.
    #     · 그중 폐지 토큰을 문자열로 보유한 후보 32개 → 바닥 10. 이 수는 정리가
    #       진행되면 «정당하게» 줄어든다(현재 32 중 14개가 intraday_rebound 의
    #       MINUTE_DB 로, 한 번의 정리로 함께 빠질 수 있다) ⇒ 여유를 크게 둔다.
    assert len(scanned) >= 700, (
        f"게이트가 훑은 추적 .py 가 {len(scanned)}개뿐이다 — «돌지 않았을» 수 있다"
        f" (root={root}). 통과했다는 사실만으로 안심하지 말 것."
    )

    candidates = []
    offenders = []
    for path in scanned:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not any(tok in text for tok in banned):
            continue  # 빠른 컷 (겸 후보 집계)
        candidates.append(path)
        if path.resolve() == Path(__file__).resolve():
            continue  # 이 테스트 자신(패턴 문자열 보유)
        for tok, pat in patterns.items():
            if pat.search(text):
                offenders.append(f"{path.relative_to(root)}:{tok}")

    assert len(candidates) >= 10, (
        f"폐지 토큰 문자열 보유 후보가 {len(candidates)}개뿐이다 — 훑는 파일 수는"
        f" 정상인데 내용 판독이 안 되고 있을 수 있다 (root={root})."
    )
    assert offenders == [], f"중복 소스 env 를 읽는 코드 재유입: {offenders}"


# ===========================================================================
# 6) 🔴 DROP 게이트 — DB명 'robotrader' 하드코딩 금지
# ===========================================================================
# 위 (5)번 게이트는 「폐지된 **env 이름**을 읽는가」만 본다. 그것과 별개로,
# 연결 인자에 **DB명 문자열이 직박혀 있으면** `DROP DATABASE robotrader` 순간
# 그 경로가 즉사한다 — env 게이트는 그걸 하나도 못 잡는다.
# ---------------------------------------------------------------------------

# 「값이 DB명 자리에 있는 'robotrader'」만 잡는다.
#   · dbname="robotrader" / dbname='robotrader'
#   · database="robotrader" / "database": "robotrader"   (dict·JSON 리터럴)
#   · _conn("robotrader")                                (위치인자 첫 자리)
_HARDCODED_DB_PATTERNS = (
    r"""(?:dbname|database)["']?\s*(?:=|:)\s*["']robotrader["']""",
    r"""\(\s*["']robotrader["']""",
)

# 예외 — **추적되는데도** 설계상 레거시를 가리켜야 하는 곳. 여기서 걸려도 결함이 아니다.
#
# 🔴 2026-08-17 축소: 예전엔 여기에 `scratchpad`·`.git`·`venv`·`__pycache__`·
#   `node_modules`·`.pytest_cache`·`site-packages`·`.worktrees` 도 있었다. 그건
#   「소스가 아닌 것」을 **디렉터리 이름으로** 빼려는 시도였고, 바로 그 방식이
#   2026-08-17 에 뚫렸다 — 목록에 없던 `.omc/scientist/scripts/` 하나 때문에
#   라이브 트리에서만 게이트가 빨개졌다(워크트리엔 그 파일이 없어 초록이었다).
#   ⇒ 이제 스캔 대상 자체를 **git 추적 파일**로 한정하므로 그 항목들은 «자동으로»
#     빠진다(전부 미추적·gitignore 대상). 목록에 남겨두면 「다음 스크래치 폴더」를
#     또 손으로 추가해야 한다는 착각을 준다 — 그래서 지웠다.
_DROP_GATE_ALLOWED_DIRS = (
    "archive",       # 동결된 과거 산출물. 되살릴 일이 없다.
    "kis_db",        # scripts/kis_db/ = 레거시→kis 「이관 전용」 도구.
                     #   DB 와 함께 죽는 것이 설계다(원본을 읽어야 이관이 성립).
)


class _GitUnavailable(RuntimeError):
    """추적 목록을 git 에서 못 얻었다.

    🔴 이 상태를 **통과로 접으면 안 된다** — 0개를 훑고 초록불이 뜨는 게 이 프로젝트가
      반복해서 밟은 「거짓 통과」다. 호출부는 skip(명시) 아니면 실패로 처리한다.
    """


def _git_tracked_py_files(root):
    """`git ls-files` 가 보고하는 **추적 중인** *.py 절대경로 목록.

    🔑 스캔 범위를 「디스크에 있는 파일」이 아니라 「저장소가 배포하는 파일」로 바꾼다.
      디렉터리 allowlist 는 새 스크래치 폴더가 생길 때마다 뚫리지만(정의상 목록에
      없으니까), 추적 여부는 스크래치가 **자기 자신을 등록하지 않는 한** 뚫리지 않는다.

    실패하면 조용히 빈 목록을 주지 않고 `_GitUnavailable` 을 올린다.
    """
    import subprocess
    from pathlib import Path

    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # git 부재·타임아웃 등
        raise _GitUnavailable(
            f"`git ls-files` 를 실행하지 못했다 ({type(exc).__name__}: {exc})") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise _GitUnavailable(
            f"`git ls-files` 가 비영 종료했다 (rc={proc.returncode}): "
            f"{err or '(stderr 없음)'}")
    # -z 출력은 인용되지 않은 raw 바이트다(core.quotepath 무관). 한글 경로가 실재하므로
    # surrogateescape 로 받아 어떤 바이트열이 와도 죽지 않게 한다.
    names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [Path(root) / n for n in names if n.endswith(".py")]


def _drop_gate_scan_paths(root):
    """게이트가 **실제로 훑을** 파일 목록 = 추적 .py − allowlist − 워킹트리 부재분.

    「훑은 양」 단언과 실제 스캔이 같은 목록을 쓰도록 여기 한 곳에서 만든다
    (둘이 따로 계산되면 한쪽만 0이어도 다른 쪽 단언이 통과해 버린다).
    """
    from pathlib import Path

    root = Path(root)
    keep = []
    for path in _git_tracked_py_files(root):
        if any(d in path.relative_to(root).parts for d in _DROP_GATE_ALLOWED_DIRS):
            continue
        if not path.is_file():
            continue  # 인덱스엔 있으나 워킹트리에서 지워진 파일(읽을 게 없다)
        keep.append(path)
    return keep


def _drop_gate_code_only_lines(text: str):
    """주석·삼중따옴표 문자열을 **뺀** {lineno: 코드} 맵.

    🔑 이력을 설명하는 산문은 허용해야 한다 — 「예전엔 dbname="robotrader" 였다」는
      다음 사람에게 유용한 정보지 결함이 아니다. 그래서 순수 텍스트 grep 이 아니라
      **토크나이저**로 (a) `#` 주석 (b) docstring(삼중따옴표 리터럴) 을 걷어내고
      «코드로 살아 있는» 토큰만 검사한다.
      (일반 문자열 리터럴은 남긴다 — `"database": "robotrader"` 가 바로 그 형태다.)
    """
    import io
    import tokenize

    lines = {}
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except Exception:
        # 파싱 실패(구문오류·인코딩 등)면 원문 그대로 검사한다 — 미탐보다 과탐이 낫다.
        return {i: ln for i, ln in enumerate(text.splitlines(), 1)}
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING:
            body = tok.string.lstrip("rbfuRBFU")
            if body[:3] in ('"""', "'''"):
                continue  # docstring/블록 산문
        lines[tok.start[0]] = lines.get(tok.start[0], "") + tok.string
    return lines


def _scan_hardcoded_robotrader_db(root, self_path, paths=None):
    """*.py 에서 DB명 하드코딩을 찾아 ["경로:줄: 원문", ...] 반환.

    `paths` 를 주면 그 목록만 훑는다(리포 게이트는 **git 추적 목록**을 넘긴다).
    안 주면 `root` 아래를 rglob 한다 — tmp_path 위에서 도는 음성 대조용 경로다
    (거긴 git 저장소가 아니라 추적 목록이라는 개념 자체가 없다).
    """
    import re
    from pathlib import Path

    pats = [re.compile(p) for p in _HARDCODED_DB_PATTERNS]
    if paths is None:
        paths = Path(root).rglob("*.py")
    root = Path(root)
    offenders = []
    for path in paths:
        # 🔑 allowlist 는 **root 기준 상대경로**로 본다. 절대경로 parts 로 보면
        #   체크아웃 «위치»가 판정에 섞인다 — 예컨대 워크트리가 `D:/GIT/archive/…`
        #   아래 있으면 전 파일이 조용히 제외돼 「0개 훑고 통과」가 된다.
        try:
            parts = path.relative_to(root).parts
        except ValueError:  # root 밖(있어선 안 되지만) → 절대경로로 보수 판정
            parts = path.parts
        if any(d in parts for d in _DROP_GATE_ALLOWED_DIRS):
            continue
        if path.resolve() == Path(self_path).resolve():
            continue  # 이 테스트 자신(패턴 문자열 보유)
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "robotrader" not in text:
            continue  # 빠른 컷
        raw = text.splitlines()
        for lineno, code in _drop_gate_code_only_lines(text).items():
            if any(p.search(code) for p in pats):
                src = raw[lineno - 1].strip() if lineno <= len(raw) else code
                offenders.append(f"{path.relative_to(root)}:{lineno}: {src}")
    return sorted(offenders)


def test_no_hardcoded_robotrader_dbname():
    """🔴 DROP 게이트 — DB명 `robotrader` 를 직박은 연결이 없어야 한다.

    `robotrader` DB 는 2026-08-16 통합으로 데이터가 전부 kis_template 에 이관됐고
    **삭제 예정**이다. 삭제되는 순간 이 문자열을 들고 있는 경로는 전부 즉사한다.
    폐지된 env 를 잡는 `test_no_lingering_duplicate_source_envs` 는 이 형태를
    **하나도 못 잡는다**(env 를 안 읽고 리터럴을 쓰니까) — 그래서 게이트가 둘이다.

    ⚠️ **롤명과 구분한다.** `robotrader` 는 DB명이자 **PostgreSQL 롤명**이기도 하다:
      `user="robotrader"` · `TIMESCALE_USER` · `KIS_DB_USER` · `EXTERNAL_DB_USER` ·
      `psql -U robotrader` 는 **계정명이라 정상**이고 DB 삭제와 무관하다. 이걸 잡으면
      오탐이다(리포 전역에 50곳 넘게 있다). 그래서 「dbname/database 자리」와
      「함수 첫 위치인자」라는 **자리**로만 판정한다.

    허용:
      · `archive/`      — 동결된 과거 산출물
      · `scripts/kis_db/` — 레거시→kis 이관 «전용» 도구. DB 와 함께 죽는 게 설계다.
      · 이력 주석·docstring — 토크나이저로 걷어낸다(위 헬퍼 참조).
      · **git 미추적 파일 전부** — 스크래치·산출물·`venv/`·`.omc/` 등. 배포되지
        않으므로 DROP 으로 죽을 「경로」가 아니다.

    🔑 스캔 범위는 **리포 루트의 git 추적 .py 전부**다.
      ① 루트는 형제 env 게이트의 `parents[1]` 보다 한 칸 위다 — `RoboTrader_template/`
        만 훑으면 리포 루트의 `scripts/10pct_strategy/p0_backfill_corp_events.py`
        (corp_events 에 **INSERT** 하는 쓰기 스크립트)를 놓친다.
      ② 🔴 2026-08-17: 「디스크의 .py 전부」에서 「**추적되는** .py」로 바꿨다.
        직전 방식은 디렉터리 allowlist 로 비-소스를 뺐는데, 목록에 없던
        `RoboTrader_template/.omc/scientist/scripts/`(gitignore 된 스크래치) 하나가
        라이브 트리에서 게이트를 빨갛게 만들었다 — **워크트리엔 그 파일이 체크아웃
        되지 않아 초록이었다**. 즉 게이트의 답이 「어느 체크아웃에서 돌렸나」에
        달려 있었다. allowlist 를 하나 더 추가하는 건 다음 스크래치 폴더까지 같은
        사고를 미루는 것이다. ***배포되는 것만 훑는다*** 로 바꿔 뿌리를 끊는다.
        실측(2026-08-17): 추적 .py 1,131개 → allowlist 제외 후 **1,041개**.
        같은 값이 라이브 트리·워크트리에서 «동일»하다(rglob 이면 1,044 vs 1,041).
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]

    # 🔴 git 을 못 쓰면 **조용히 통과시키지 않는다.** 0개를 훑고 초록불이 되는 것보다
    #   눈에 보이는 skip 이 낫다(그리고 CI 는 skip 을 세면 이 상태를 잡을 수 있다).
    try:
        scanned = _drop_gate_scan_paths(root)
    except _GitUnavailable as exc:
        pytest.skip(
            f"DROP 게이트를 실행할 수 없다 — {exc} (root={root}). "
            "추적 목록 없이 「0개 훑고 통과」가 되는 것을 막기 위해 skip 한다."
        )

    # 🔑 「입력이 비어 있음」과 「위반이 없음」은 **같은 얼굴로** 통과한다.
    #   경로 오지정·allowlist 과잉·git 이상으로 0개를 훑고도 초록불이 뜨는 게 이
    #   프로젝트가 반복해서 밟은 「거짓 통과」다. 그래서 **훑은 양**을 먼저 단언한다.
    #
    #   바닥값 근거(실측 2026-08-17, 두 트리 동일):
    #     · 훑는 파일 1,041개 → 바닥 700. 이 수는 `robotrader` 정리 작업으로 줄지
    #       않는다(파일 수라서). 그래서 **주 가드**로 쓰고 문턱을 높게 잡는다.
    #     · 그중 'robotrader' 문자열 보유 후보 124개 → 바닥 30(종전과 동일 유지).
    #       이 수는 정리가 진행되면 «정당하게» 줄어들 수 있어 여유를 크게 둔다.
    assert len(scanned) >= 700, (
        f"게이트가 훑은 추적 .py 가 {len(scanned)}개뿐이다 — «돌지 않았을» 수 있다"
        f" (root={root}). 통과했다는 사실만으로 안심하지 말 것."
    )
    candidates = [
        p for p in scanned
        if "robotrader" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert len(candidates) >= 30, (
        f"'robotrader' 문자열 보유 후보가 {len(candidates)}개뿐이다 — 훑는 파일 수는"
        f" 정상인데 내용 판독이 안 되고 있을 수 있다 (root={root})."
    )

    offenders = _scan_hardcoded_robotrader_db(root, __file__, paths=scanned)
    assert offenders == [], (
        "DB명 'robotrader' 하드코딩 재유입 — **이 DB 는 폐기 예정이다. "
        "resolver 를 쓰라** (config.constants.resolve_daily_source_db / "
        "resolve_minute_source_db / resolve_corp_events_source_db):\n  "
        + "\n  ".join(offenders)
    )


def test_drop_gate_scanner_actually_catches(tmp_path):
    """[음성 대조] 위 스캐너가 **정말로 잡는가** — 일부러 위반을 심어 확인한다.

    🔑 「통과했다」는 스캐너가 돌았다는 증거가 아니다. 정규식 오타·경로 오지정으로
      **0개를 훑고도 통과**할 수 있다. 그래서 양성 검체를 넣어 잡히는 걸 보이고,
      같은 자리의 **롤명**은 잡히지 않는 걸(오탐 없음) 함께 고정한다.
    """
    (tmp_path / "offender_kwarg.py").write_text(
        'import psycopg2\nc = psycopg2.connect(host="h", dbname="robotrader")\n',
        encoding="utf-8")
    (tmp_path / "offender_dict.py").write_text(
        'DB = {"host": "h", "database": "robotrader"}\n', encoding="utf-8")
    (tmp_path / "offender_positional.py").write_text(
        'def _conn(n): ...\nwith _conn("robotrader") as c:\n    pass\n',
        encoding="utf-8")

    caught = _scan_hardcoded_robotrader_db(tmp_path, __file__)
    assert len(caught) == 3, f"양성 3건을 다 못 잡았다: {caught}"
    assert any("offender_kwarg.py:2" in c for c in caught)
    assert any("offender_dict.py:1" in c for c in caught)
    assert any("offender_positional.py:2" in c for c in caught)

    # ── 오탐 대조: 롤명·이력 주석·docstring·허용 디렉터리는 잡히면 안 된다 ──
    (tmp_path / "clean_role.py").write_text(
        'import psycopg2\n'
        'c = psycopg2.connect(dbname="kis_template", user="robotrader")\n'
        'import subprocess\n'
        'subprocess.run(["psql", "-U", "robotrader", "-d", "kis_template"])\n',
        encoding="utf-8")
    (tmp_path / "clean_history.py").write_text(
        '"""옛 코드는 dbname="robotrader" 였다 — 2026-08-17 resolver 로 교체."""\n'
        '# 이전: database="robotrader"\n'
        'DB = {"database": "kis_template"}\n',
        encoding="utf-8")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "frozen.py").write_text(
        'DB = {"database": "robotrader"}\n', encoding="utf-8")
    (tmp_path / "kis_db").mkdir()
    (tmp_path / "kis_db" / "migrate.py").write_text(
        'c = connect(dbname="robotrader")\n', encoding="utf-8")

    caught2 = _scan_hardcoded_robotrader_db(tmp_path, __file__)
    assert len(caught2) == 3, (
        f"오탐 발생 — 롤명/이력주석/허용디렉터리까지 잡았다: {caught2}")


def test_drop_gate_scans_tracked_files_only(tmp_path):
    """[음성 대조] 미추적 파일은 스캔 «대상»에서 빠진다 — 2026-08-17 사고 재발 방지.

    사고 재현: gitignore 된 `.omc/scientist/scripts/` 스크래치 하나가 라이브 트리에서
    게이트를 빨갛게 만들었고, 워크트리엔 그 파일이 없어 초록이었다 = **게이트의 답이
    체크아웃마다 달랐다**. 그 성질을 여기서 못 박는다.

    🔑 「같은 내용의 두 파일 — 하나는 추적, 하나는 미추적」이 결정적 검체다. 둘 다
      빠지거나 둘 다 잡히면 이 테스트가 통과하지 못하므로, 판정 기준이 「내용」이
      아니라 「추적 여부」임을 실제로 갈라 보인다.
    """
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True,
                   capture_output=True)
    violation = 'import psycopg2\nc = psycopg2.connect(dbname="robotrader")\n'
    (tmp_path / "tracked.py").write_text(violation, encoding="utf-8")
    (tmp_path / "untracked.py").write_text(violation, encoding="utf-8")
    # 커밋까지 갈 필요 없다 — `git ls-files` 는 인덱스를 본다(신원 설정 의존 회피).
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.py"],
                   check=True, capture_output=True)

    listed = {p.name for p in _git_tracked_py_files(tmp_path)}
    assert listed == {"tracked.py"}, f"추적 목록이 어긋난다: {listed}"

    scanned = _drop_gate_scan_paths(tmp_path)
    caught = _scan_hardcoded_robotrader_db(tmp_path, __file__, paths=scanned)
    assert len(caught) == 1 and "tracked.py" in caught[0], (
        f"추적 파일의 위반을 못 잡거나 미추적까지 잡았다: {caught}")


def test_drop_gate_does_not_pass_silently_without_git(tmp_path):
    """[음성 대조] git 을 못 쓰면 «조용히 통과»가 아니라 실패한다.

    🔴 이 프로젝트가 반복해서 밟은 형태 = 「입력이 비어 있음」이 「위반이 없음」과
      같은 얼굴로 초록불이 되는 것. 추적 목록 조회가 실패하면 빈 목록이 아니라
      예외가 나와야 하고(그래야 호출부가 skip 으로 «명시»할 수 있다), 그걸 확인한다.

    검체 = git 저장소가 «아닌» 디렉터리(pytest tmp_path 는 저장소 밖이다) →
    `git ls-files` 가 rc=128 로 죽는다.
    """
    with pytest.raises(_GitUnavailable):
        _git_tracked_py_files(tmp_path)
