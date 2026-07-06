from datetime import datetime

import pandas as pd

import scripts.kis_db.smoke_state_restore as smk
from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE


def test_build_summary_positions_and_candidates_sorted():
    ops = [
        {"stock_code": "000660", "quantity": 5, "buy_price": 100.0, "strategy": "elder"},
        {"stock_code": "005930", "quantity": 3, "buy_price": 200.0, "strategy": "ma5"},
    ]
    s = smk.build_restore_summary(ops, {}, ["005930", "000660", "000660"])
    assert s["open_position_codes"] == ["000660", "005930"]
    assert s["n_open"] == 2
    assert s["candidate_codes"] == ["000660", "005930"]  # dedup + sorted


def test_build_summary_cash_uses_live_formula():
    sums = {"elder": {"buy_gross": 1000.0, "sell_gross": 500.0}}
    s = smk.build_restore_summary([], sums, [], capital=10000.0)
    expected = 10000.0 - 1000.0 * (1 + COMMISSION_RATE) + 500.0 * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE)
    assert s["per_strategy_cash"]["elder"] == round(expected, 2)


def test_compare_summaries_pass_when_identical():
    base = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.4}}  # 0.4 < 1.0 → 일치
    c = smk.compare_summaries(base, cand)
    assert c["open_positions_match"] is True
    assert c["candidates_match"] is True
    assert c["cash_match"] is True
    assert c["verdict"] == "PASS"


def test_compare_summaries_fail_on_position_mismatch():
    base = {"open_position_codes": ["A", "B"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    c = smk.compare_summaries(base, cand)
    assert c["open_positions_match"] is False
    assert c["verdict"] == "FAIL"


def test_compare_summaries_fail_on_cash_drift():
    base = {"open_position_codes": [], "candidate_codes": [],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": [], "candidate_codes": [],
            "per_strategy_cash": {"elder": 250.0}}  # 150 diff
    c = smk.compare_summaries(base, cand)
    assert c["cash_max_abs_diff"] == 150.0
    assert c["cash_match"] is False
    assert c["verdict"] == "FAIL"


# ── CRITICAL 회귀: run_smoke() 요약배선(quantity 필터) ──────────────────────
#
# 실DB/서브프로세스 없이 run_smoke() 내부에서 임포트되는 StateRestorer /
# TradingRepository / CandidateRepository / now_kst 를 fake 로 대체해,
# "후보 스캔(quantity=0)"과 "진짜 보유(quantity>0)"를 구분하는 배선 자체를
# 검증한다(build_restore_summary 단위테스트만으로는 이 배선 자체가 커버되지 않았음).

class _FakeStateRestorerCapturesCandidatesAndHoldings:
    """StateRestorer 대역. 실제 흐름(후보 등록 → 보유 등록+set_position)을
    smk._FakeTradingManager/_FakeTradingStock 위에 재현한다.

    시나리오:
      - "999001": 순수 후보(후보 등록만, 실보유 아님) → quantity=0 유지
      - "000660", "035720": 실보유(후보 아님, set_position 으로 quantity>0)
      - "005930": 후보로도 등록되지만 보유복원 경로가 드롭됨(set_position 미호출)
                  → 실제로는 유실된 보유. 이 코드가 "후보"라는 이유로
                  오픈포지션에 새는지가 이 회귀의 핵심.
    """

    def __init__(self, trading_manager, db_manager, telegram_integration, config,
                 get_previous_close_callback, broker=None, fund_manager=None,
                 virtual_trading_manager=None, strategies=None):
        self.trading_manager = trading_manager

    async def restore_todays_candidates(self):
        tm = self.trading_manager

        await tm.add_selected_stock("999001", "CandOnly", "reason")

        await tm.add_selected_stock("000660", "HoldA", "reason", owner_strategy="elder")
        tm.get_trading_stock("000660", strategy="elder").set_position(5, 100.0)

        await tm.add_selected_stock("035720", "HoldB", "reason", owner_strategy="ma5")
        tm.get_trading_stock("035720", strategy="ma5").set_position(3, 50.0)

        # 유실 시나리오: 후보 등록만 되고 보유복원(set_position)이 실행되지 않음
        await tm.add_selected_stock("005930", "LostHoldingAlsoCandidate", "reason")


class _FakeTradingRepoRecordsCtorArgs:
    """TradingRepository 대역. real_table_name 인자를 기록해 HIGH 회귀(ensure_real_table
    DDL 미발동)를 같은 배선 위에서 검증한다."""
    last_real_table_name = "__not_called__"

    def __init__(self, real_table_name=None):
        type(self).last_real_table_name = real_table_name

    def get_strategy_trade_sums(self):
        return {"elder": {"buy_gross": 0.0, "sell_gross": 0.0}}


class _FakeCandidateRepoWithMixedDates:
    """CandidateRepository 대역. 당일 후보 2건(999001, 005930) + 전일 후보 1건(999999)을
    반환해 MEDIUM 회귀(정확일치 날짜필터)도 같은 배선 위에서 검증한다."""

    def get_candidate_history(self, days=1):
        return pd.DataFrame({
            "stock_code": ["999001", "005930", "999999"],
            "selection_date": [
                pd.Timestamp("2026-07-06 09:05:00"),
                pd.Timestamp("2026-07-06 09:10:00"),
                pd.Timestamp("2026-07-05 09:00:00"),  # 전일 → 정확일치 필터로 제외돼야 함
            ],
        })


def test_run_smoke_only_counts_genuine_holdings_and_detects_dropped_holding(monkeypatch):
    monkeypatch.setattr("bot.state_restorer.StateRestorer",
                        _FakeStateRestorerCapturesCandidatesAndHoldings)
    monkeypatch.setattr("db.repositories.trading.TradingRepository",
                        _FakeTradingRepoRecordsCtorArgs)
    monkeypatch.setattr("db.repositories.candidate.CandidateRepository",
                        _FakeCandidateRepoWithMixedDates)
    monkeypatch.setattr("utils.korean_time.now_kst",
                        lambda: datetime(2026, 7, 6, 10, 0, 0))

    summary = smk.run_smoke("kis_template_test", capital=10_000.0)

    # 진짜 보유만 오픈포지션(순수 후보 999001 제외)
    assert summary["open_position_codes"] == ["000660", "035720"]
    assert summary["n_open"] == 2

    # 유실 시나리오: 005930 은 당일 후보 목록엔 정상 포함되지만
    # (보유복원이 드롭됐으므로) 오픈포지션에는 절대 나타나면 안 된다.
    # quantity 필터가 없으면 이 assert 가 실패한다(회귀 재현).
    assert "005930" in summary["candidate_codes"]
    assert "005930" not in summary["open_position_codes"]

    # MEDIUM 회귀: 전일 후보(999999)는 정확일치 날짜필터로 제외
    assert "999999" not in summary["candidate_codes"]
    assert summary["candidate_codes"] == ["005930", "999001"]

    # HIGH 회귀: TradingRepository 가 기본 real_table 명으로 명시 생성됨
    # (KIS_INSTANCE_DIR 환경에서 인자 없이 생성 시 ensure_real_table DDL 이 발동한다)
    assert _FakeTradingRepoRecordsCtorArgs.last_real_table_name == "real_trading_records"
