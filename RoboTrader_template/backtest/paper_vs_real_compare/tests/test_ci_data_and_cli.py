# -*- coding: utf-8 -*-
"""합성 자료 시험 — 로그 파싱(ci_data, 파일·DB 접근 없음) · CLI 가드(compare_ci). 실데이터 접근 0.
로그 줄은 운영 코드의 문자열 꼴만 따르고 종목·주문번호·가격·시각은 전부 합성 값."""
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime

import pytest

import ci_data
import ci_stats as S
import compare_ci
from synthetic import full_synthetic

DAY = date(2026, 1, 7)
LINES = """2026-01-07 07:50:00 | utils.price_utils | INFO | 프로세스 PID 등록: 11111
2026-01-07 09:01:00 | core.trading_decision_engine | INFO | 900101 전달 매수신호 사용: breakout_prev_high close=3000.00 (신뢰도: 68.0%)
2026-01-07 09:01:01 | core.orders.order_base | INFO | 매수 주문 시도: 900101 50주 @3,003원 (타임아웃: 300초)
2026-01-07 09:01:01 | core.orders.order_base | INFO | 매수 주문 성공: 9000000001 - 900101(900101) 50주 @3,003원
2026-01-07 09:01:09 | core.orders.order_base | INFO | 주문 완전 체결 확정: 9000000001 (900101) - 50주 @3,005원
2026-01-07 09:01:10 | core.trading_decision_engine | INFO | [B2-실전] 900101 익절 10.0% 손절 10.0% (소유 전략 'x' config)
2026-01-07 09:02:00 | core.trading_decision_engine | WARNING | [B2-실전] 900105 소유 전략('x') config tp/sl 해소 실패 → 종전 값 유지
2026-01-07 09:30:00 | core.orders.order_base | INFO | 매수 주문 시도: 900102 100주 @1,500원 (타임아웃: 300초)
2026-01-07 09:30:00 | core.orders.order_base | INFO | 매수 주문 성공: 9000000002 - 900102(900102) 100주 @1,500원
2026-01-07 09:35:02 | core.orders.order_base | WARNING | 5분 타임아웃 처리: 9000000002 (900102) - 경과시간: 302초
2026-01-07 09:35:04 | core.orders.order_base | INFO | 타임아웃 취소 성공: 9000000002
2026-01-07 10:00:00 | core.orders.order_base | WARNING | 5분 타임아웃 처리: 9000000003 (900103) - 경과시간: 181초
2026-01-07 10:00:02 | core.orders.order_base | INFO | 타임아웃 취소 성공: 9000000003
2026-01-07 10:10:00 | strategy.X | INFO | [캡] daytrading_3methods_breakout 900104 평가 스킵 사유=daily_trades 보유=8/10 일일매수=4/5 경로=매수루프
2026-01-07 10:10:00 | strategy.X | INFO | [shadow] daytrading_3methods_breakout 90010K 캡사유=daily_trades 룰=참 보유=8/10 | x
2026-01-07 10:20:00 | bot.trading_analyzer | INFO | 900106 자금 부족: 필요=500,000원, 가용=100,000원
2026-01-07 10:20:01 | core.orders.order_base | WARNING | 자금 부족으로 매수 주문 거부: 900107 (필요: 500,000원)
2026-01-07 10:20:02 | core.orders.order_base | WARNING | 매수 주문 차단: 주문 불가 시간대 (closing) - 900108
2026-01-07 10:20:03 | core.orders.order_base | WARNING | 매수 주문 차단: 900109 VI 발동 중
2026-01-07 10:20:04 | core.orders.order_base | ERROR | 매수 주문 API 타임아웃: 900110
2026-01-07 10:30:00 | core.trading.position_monitor | INFO | 900101 손절 신호: 손절 실행 (-10.50% <= -10.00%)
Traceback (most recent call last):
  File "x.py", line 1
2026-01-07 11:00:00 | core.orders.order_base | INFO | 주문 부분 체결: 9000000004 (900111) - 3/10주
2026-01-07 15:40:00 | bot.initializer | INFO | 시스템 종료 완료
""".splitlines(True)


def T(h, m, s=0):
    return datetime(2026, 1, 7, h, m, s)


def test_parse_day_log_lines():
    lg = ci_data.parse_day_log_lines(LINES, DAY)
    assert lg.first_ts == T(7, 50) and lg.last_ts == T(15, 40)
    assert lg.signals == [(T(9, 1), "900101")]
    assert [(c, q, p) for _, c, q, p in lg.tries] == [("900101", 50, 3003.0), ("900102", 100, 1500.0)]
    assert lg.stops == [(T(10, 30), "900101", -10.50, -10.00)]
    assert [c for _, c in lg.caps] == ["900104", "90010K"]
    assert [c for _, c in lg.cash] == ["900106", "900107"]
    assert [c for _, c in lg.blocks] == ["900108", "900109"]
    assert [c for _, c in lg.api_timeouts] == ["900110"]
    assert [c for _, c in lg.delayed_cancels] == ["900102"]      # 900103 은 매수 주문이 아니라 빠짐
    assert [c for _, c in lg.b2_fail] == ["900105"]               # 정상 [B2-실전] 줄은 표식 아님
    assert [c for _, c in lg.partial] == ["900111"]


def test_fill_uses_rounded_order_price_from_log():
    lg = ci_data.parse_day_log_lines(LINES, DAY)
    rb = S.RealBuy(1, "900101", T(9, 1, 9), 3005.0, 50)
    f = S.build_real_fills([rb], {DAY: lg})[0]
    assert f.order_price == 3005.0                               # round_to_tick(3,003) — 5원 격자
    assert f.signal_ts == T(9, 1) and f.try_qty == 50


def test_kospi_signs():
    k = [(date(2026, 1, 2), 100.0), (date(2026, 1, 5), 101.0), (date(2026, 1, 6), 100.5), (date(2026, 1, 7), 100.5)]
    signs, days = ci_data.kospi_signs(k, date(2026, 1, 5), date(2026, 1, 7))
    assert days == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    assert signs == {date(2026, 1, 5): 1, date(2026, 1, 6): -1, date(2026, 1, 7): 0}


def test_load_cost_csv(tmp_path):
    dcsv = tmp_path / "d.csv"
    pcsv = tmp_path / "p.csv"
    dcsv.write_text("﻿date,kis_buy_amt,kis_sell_amt,actual_fee,actual_tax,actual_cost\n"
                    "20260107,1000000.0,500000.0,50.0,1000.0,1050.0\nTOTAL,1,1,1,1,1\n", encoding="utf-8")
    pcsv.write_text("﻿date,code,name,qty,internal_id,kis_amount\n20260107,012345,x,40,1,500000.0\n", encoding="utf-8")
    days, rows = ci_data.load_cost(dcsv, pcsv)
    assert list(days) == [DAY] and days[DAY].fee == 50.0
    assert rows == {(DAY, "012345", 40): 500000.0}


# ---------------------------------------------------------------- CLI 가드
AFTER_CLOSE = datetime(2026, 11, 13, 17, 0)
CLEAN = {"git_head": "abc1234", "dirty": False, "dirty_paths": [], "sha256": {"ci_stats.py": "0" * 64}}
SR = compare_ci.SINGLE_RUN_FLAG


def _run(argv, loader=None, now=AFTER_CLOSE, code_id=CLEAN):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = compare_ci.main(argv, loader=loader, now=now, code_id=code_id)
    return rc, out.getvalue(), err.getvalue()


def _no_load(a):
    pytest.fail("적재하면 안 됨")


def test_cli_refuses_without_mode():
    rc, out, err = _run([], loader=_no_load)
    assert rc == 2 and "거부" in err and out == ""


def test_cli_refuses_during_market_hours():
    rc, _, err = _run(["--dry-run"], loader=_no_load, now=datetime(2026, 11, 13, 10, 0))
    assert rc == 3 and "장중" in err


def test_cli_modes_mutually_exclusive():
    with pytest.raises(SystemExit):
        _run(["--dry-run", SR])


def test_cli_dry_run_computes_no_values(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("dry-run 에서 지표 값/CI 계산 호출")
    for fn in ("values_coverage", "values_fill_ratio", "values_slippage", "values_latency", "stop_values", "cost_values",
               "cluster_bootstrap_ci", "summarize", "build_summary"):
        monkeypatch.setattr(S, fn, boom)
    rc, out, _ = _run(["--dry-run"], loader=lambda a: full_synthetic())
    assert rc == 0
    payload = json.loads(out.split("\n", 1)[1])
    assert set(payload) >= {"rows", "pairs", "metric_n", "min_condition_§1", "trading_days_in_period", "format_checks"}
    assert all("거래일(군집)" in v for v in payload["metric_n"].values())
    for k in ("median", "ci", "mean_daily", "trim20", "pooled"):
        assert f'"{k}"' not in out


@pytest.mark.parametrize("argv, msg", [
    ([SR], "--cost-source"),
    ([SR, "--cost-source", "allocated", "--end", "2026-11-12"], "고정"),
    ([SR, "--cost-source", "allocated", "--start", "2026-10-20"], "고정"),
    ([SR, "--cost-source", "allocated", "--retry-after-failed-run"], "--retry-reason"),
    (["--dry-run", "--retry-after-failed-run"], "단일 실행에만"),
])
def test_cli_single_run_arg_guards(argv, msg, tmp_path):
    rc, _, err = _run(argv + ["--out", str(tmp_path)], loader=_no_load)
    assert rc == 5 and msg in err and not (tmp_path / compare_ci.MARKER_NAME).exists()


def test_cli_single_run_refuses_dirty_tree(tmp_path):
    rc, _, err = _run([SR, "--cost-source", "allocated", "--out", str(tmp_path)], loader=_no_load,
                      code_id=dict(CLEAN, dirty=True, dirty_paths=["?? x.py"]))
    assert rc == 6 and "dirty" in err and not (tmp_path / compare_ci.MARKER_NAME).exists()


def test_cli_single_run_refuses_wrong_trading_days_before_marker(tmp_path):
    def short(a):
        ds = full_synthetic()
        ds.trading_days = ds.trading_days[:-1]          # 11-13 빠짐 · 19일
        return ds
    rc, _, err = _run([SR, "--cost-source", "allocated", "--out", str(tmp_path)], loader=short)
    assert rc == 7 and not (tmp_path / compare_ci.MARKER_NAME).exists()


def test_cli_single_run_marker_stages_and_blocks_second_run(tmp_path):
    rc1, out1, _ = _run([SR, "--cost-source", "allocated", "--out", str(tmp_path)], loader=lambda a: full_synthetic())
    assert rc1 == 0 and "§8 요약 1장" in out1 and (tmp_path / "summary_20261113.md").exists()
    m = json.loads((tmp_path / compare_ci.MARKER_NAME).read_text(encoding="utf-8"))
    att = m["attempts"][0]
    assert [s["stage"] for s in att["stages"]] == ["적재 완료", "계산 완료", "저장 완료"]
    assert att["code"]["git_head"] == "abc1234" and att["cost_source"] == "allocated" and att["result_path"]
    rc2, _, err2 = _run([SR, "--cost-source", "allocated", "--out", str(tmp_path)], loader=_no_load)
    assert rc2 == 4 and "이미" in err2
    rc3, _, err3 = _run([SR, "--cost-source", "allocated", "--retry-after-failed-run", "--retry-reason", "x",
                         "--out", str(tmp_path)], loader=_no_load)
    assert rc3 == 4 and "결과를 저장" in err3


def test_cli_retry_after_failed_run_once(tmp_path):
    def crash(a):
        ds = full_synthetic()
        ds.kospi_sign = None                             # 계산 단계에서 죽는 자료
        return ds
    with pytest.raises(Exception):
        _run([SR, "--cost-source", "strict", "--out", str(tmp_path)], loader=crash)
    m = json.loads((tmp_path / compare_ci.MARKER_NAME).read_text(encoding="utf-8"))
    assert [s["stage"] for s in m["attempts"][0]["stages"]] == ["적재 완료"]       # 어디서 죽었는지 남음
    rc0, _, _ = _run([SR, "--cost-source", "strict", "--out", str(tmp_path)], loader=_no_load)
    assert rc0 == 4                                                                # 기본 = 재시도 없음
    rc1, _, _ = _run([SR, "--cost-source", "strict", "--retry-after-failed-run", "--retry-reason", "계산 중 예외",
                      "--out", str(tmp_path)], loader=lambda a: full_synthetic())
    assert rc1 == 0
    m = json.loads((tmp_path / compare_ci.MARKER_NAME).read_text(encoding="utf-8"))
    assert len(m["attempts"]) == 2 and m["attempts"][1]["retry"] and m["attempts"][1]["retry_reason"] == "계산 중 예외"
    (tmp_path / "summary_20261113.md").unlink()
    m["attempts"][1].pop("result_path")
    (tmp_path / compare_ci.MARKER_NAME).write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    rc2, _, err2 = _run([SR, "--cost-source", "strict", "--retry-after-failed-run", "--retry-reason", "y",
                         "--out", str(tmp_path)], loader=_no_load)
    assert rc2 == 4 and "1회뿐" in err2


def test_cli_retry_without_marker_refused(tmp_path):
    rc, _, err = _run([SR, "--cost-source", "strict", "--retry-after-failed-run", "--retry-reason", "x",
                       "--out", str(tmp_path)], loader=_no_load)
    assert rc == 4 and "없음" in err


def test_code_identity_shape():
    cid = compare_ci.code_identity()
    assert set(cid["sha256"]) == set(compare_ci.CODE_FILES) and all(len(v) == 64 for v in cid["sha256"].values())
    assert isinstance(cid["dirty"], bool)


def test_cli_synthetic_demo_needs_no_db():
    rc, out, _ = _run(["--synthetic-demo"], loader=_no_load, now=datetime(2026, 11, 13, 10, 0))
    assert rc == 0 and "합성 자료 데모" in out
