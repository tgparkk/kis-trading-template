"""report — 실현/평가 분리 성과 · 원 정수 · 방향별 신호 표 · 표에서 만든 문장 · 절 구성 · 결정적 출력(DB 없음)."""
from __future__ import annotations

import re
from datetime import date

import pytest

from backtest.concept_axes.ledger8 import arms as A
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import report as RP
from backtest.concept_axes.ledger8 import run as RUN

DAY = "daytrading_3methods_breakout"
MIN = "minervini_volume_dryup"


def _lot(strategy, lot_id, status, ret, pnl, notional, arm="B1", code="000001", seq="1", repeat="N", other="",
         basis="replay", entry_basis="D_open", d5=""):
    return dict(arm=arm, lot_id=lot_id, tier="main", strategy=strategy, code=code, exit_status=status, ret_pct=ret,
                pnl_won=pnl, notional_won=notional, open_lot_seq=seq, is_repeat_while_open=repeat,
                other_holder_live=other, qty_basis="amount", crash_blocked="N", signal_basis=basis,
                entry_basis=entry_basis, d5_flags=d5)


def _sig(strategy, outcome, slot_state="slot_available", mode="", ov1=None, ov2=None, contra="N", contra_v2="N"):
    return dict(strategy=strategy, mode=mode, outcome=outcome, outcome_v1=ov1 or outcome, outcome_v2=ov2 or outcome,
                slot_state=slot_state, reasons_equal="Y", ref_equal="Y", no_slot_but_log_y=contra,
                no_slot_but_log_y_v2=contra_v2, signal_basis="log", vintage_fragile="", rule_margin_pct="")


def _acct(strategy, code, pnl, notional="1000000", status="open", fill_dates="2026-09-10", flags="", n_adds="0",
          fill_tiers=None):
    return dict(strategy=strategy, code=code, exit_status=status, ret_pct="", pnl_won=pnl, notional_won=notional,
                n_adds=n_adds, avg_flip="n/a(추가매수 없음)", hold_clock_reset_diff="n/a(추가매수 없음)",
                fill_dates=fill_dates, fill_tiers=fill_tiers or ",".join("main" for _ in fill_dates.split(",")),
                flags=flags)


def _led(strategy, code, lot_id="", stage="", result="", tier="main", **kw):
    row = dict(strategy=strategy, code=code, tier=tier, signal_used="Y", a_stop_stage=stage, a_stop_result=result,
               b1_lot_id=lot_id, crash_blocked="N", lift_status="", lift_unknown="", ub_status="", lift_reblocked="")
    row.update(kw)
    return row


META = dict(db="kis_template", window="2026-09-10~2026-09-18", n_days=7, last_bar="2026-09-18",
            log_dir="L", warnings=[], vintage=dict(n=3, vmin=0.004, vmax=0.243))


def test_perf_splits_realized_and_open():
    p = RP.perf([_lot("rs_leader", "B1-0000", "closed", "+10.00", "100000", "1000000"),
                 _lot("rs_leader", "B1-0001", "open", "-5.00", "-50000", "1000000")])
    assert (p["n"], p["n_closed"], p["n_open"], p["win"]) == (2, 1, 1, 1)
    assert (p["pnl_closed"], p["pnl_open"]) == (100000, -50000)
    assert p["nw"] == pytest.approx(2.5)
    assert RP.won(1234567) == "1,234,567" and RP.pct(2.5) == "+2.50%" and RP.ratio(0.9) == "90.00%"
    # 전역 제약 «% 는 소수 2자리» — 브리프의 "1/2 (50%)" 에서 바꿨다(과제 10 보고서 참조)
    assert RP.replay_share([_lot("a", "x", "open", "", "", "1"), _lot("a", "y", "open", "", "", "1", basis="log")]) \
        == "1/2 (50.00%)"


def test_render_sections_flags_generated_sentences_and_determinism():
    meta = META
    sig = ([_sig("book_envelope_200d", "agree_Y", slot_state="bought")] * 6
           + [_sig("daytrading_3methods_breakout", "agree_N")] * 5
           + [_sig("daytrading_3methods_breakout", "replay_only", ov2="na", contra_v2="Y")] * 3)
    ledger = [dict(strategy="daytrading_3methods_breakout", tier="main", signal_used="Y", a_stop_stage="cash",
                   a_stop_result="qty_short", b1_lot_id="B1-0000", crash_blocked="N", lift_status="")]
    lots = [_lot("daytrading_3methods_breakout", "B1-0000", "closed", "+10.00", "100000", "1000000", d5="throttle")]
    accts = [dict(strategy="daytrading_3methods_breakout", exit_status="closed", ret_pct="+10.00", pnl_won="100000",
                  notional_won="1000000", n_adds="0", avg_flip="n/a(추가매수 없음)",
                  hold_clock_reset_diff="n/a(추가매수 없음)")]
    md = RP.render(meta, sig, [], [], ledger, lots, accts, [], [], [])
    assert "판정 근거로 쓰지 말 것" in md
    assert "daytrading_3methods_breakout [신호 충실도 낮음]" in md                 # N 방향 5/8 < 90%
    assert "`book_envelope_200d` 판정 가능 6행이 전부 실제 체결(bought)" in md      # 표에서 만든 문장
    assert "v2 3건" in md and "v3 0건" in md                                       # 재구성 모순 v2 → v3
    for h in ("## 0.", "## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8."):
        assert h in md
    assert "자본 대비" not in md and "100,000" in md and "D5 라이브였다면 진입억제" in md
    assert md == RP.render(meta, sig, [], [], ledger, lots, accts, [], [], [])   # 실행 시각 없음 → 멱등


# ── 과제 10 추가: 이전 과제 검수에서 넘어온 항목 ─────────────────────────────────


def test_banner_heads_summary_and_run_meta_but_not_csv(tmp_path):
    md = RP.render(META, [], [], [], [], [], [], [], [], [])
    assert any("관측 원장이다 — 판정 근거로 쓰지 말 것" in ln for ln in md.splitlines()[:3])
    meta = RUN._meta([date(2026, 9, 10), date(2026, 9, 18)], RUN.DEFAULT_OUT, "all", [])
    assert "관측 원장이다 — 판정 근거로 쓰지 말 것" in meta["banner"]
    RUN._atomic_write_csv(tmp_path / "x.csv", ["a", "b"], [dict(a=1, b=2)])     # 관리자 판정: CSV 첫 줄 = 머리글
    assert (tmp_path / "x.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_d5_values_match_run_and_old_cooldown_value_is_gone():
    assert (RP.D5_THROTTLE, RP.D5_THROTTLE_DELAY, RP.D5_COOLDOWN_UNKNOWN, RP.D5_DAILY_LOSS) == (
        RUN.D5_THROTTLE, RUN.D5_THROTTLE_DELAY, RUN.D5_COOLDOWN_UNKNOWN, RUN.D5_DAILY_LOSS)
    assert "buy_cooldown" not in [k for k, _ in RP.D5_LABELS]
    assert dict(RP.D5_LABELS)[RUN.D5_COOLDOWN_UNKNOWN].endswith("관측 불가")


def test_throttle_splits_three_ways_by_a_stop_stage():
    lots = [_lot(DAY, "B1-0000", "open", "", "10", "100", d5="throttle"),
            _lot(DAY, "B1-0001", "open", "", "20", "100", d5="throttle_delay"),
            _lot(DAY, "B1-0002", "open", "", "30", "100", d5="throttle,daily_loss"),
            _lot(DAY, "B1-0003", "open", "", "40", "100", d5="throttle"),
            _lot(DAY, "B1-0004", "open", "", "50", "100", d5="")]
    ledger = [_led(DAY, "000001", "B1-0000", "gate", "throttle"), _led(DAY, "000001", "B1-0001", "fill", "filled"),
              _led(DAY, "000001", "B1-0002", "cash", "qty_short"), _led(DAY, "000001", "B1-0003", "gate", "band"),
              _led(DAY, "000001", "B1-0004", "fill", "filled")]
    final, delay, later, why = RP.throttle_split(lots, RP.lot_groups(ledger))
    assert [r["lot_id"] for r in final] == ["B1-0000"]
    assert [r["lot_id"] for r in delay] == ["B1-0001"]
    assert [r["lot_id"] for r in later] == ["B1-0002", "B1-0003"]
    assert why == {"cash": 1, "gate:band": 1}
    md = RP.render(META, [], [], [], ledger, lots, [], [], [], [])
    assert "D5 라이브였다면 진입억제에서 최종 차단" in md
    assert "D5 라이브였다면 진입억제로 지연 뒤 체결" in md
    assert "D5 라이브였다면 진입억제를 지나 다른 단계에서 멈춤(A 현금(수량부족·잔고) 1 · A 밴드·매수스톱 1)" in md
    assert "25분 매수 쿨다운 — 관측 불가" in md and "buy_cooldown |" not in md


def test_scenarios_never_sum_main_with_upper_bound_nogate_or_ext():
    main = _lot(DAY, "B1-0000", "closed", "+10.00", "100", "1000")
    lots = [main,
            dict(main, arm="B1_ub", lot_id="B1U-0000"),                                   # main 을 반복한다
            dict(_lot(DAY, "B1U-0001", "open", "", "50", "1000", arm="B1_ub"), tier="lift_ub"),
            _lot(DAY, "B1G-0000", "open", "", "-30", "1000", arm="B1_nogate"),
            dict(_lot(DAY, "B1X-0000", "open", "", "7", "1000", arm="B1_ext"), tier="ext")]
    accts = [_acct(DAY, "000001", "100")]
    accts_ub = [_acct(DAY, "000001", "100"), _acct(DAY, "000002", "50", fill_tiers="lift_ub")]
    sc = {label: (b1p, b2p) for label, _, b1p, b2p in RP.scenarios(lots, accts, accts_ub)}
    tot = {k: v[0]["pnl_closed"] + v[0]["pnl_open"] for k, v in sc.items()}
    assert list(tot.values()) == [100, 150, 100, -30, 7]        # main · 상한 · 하루 종일 막힘 · 게이트 없음 · ext
    assert sc[RP.SCN_MAIN][0]["n"] == 1 and sc[RP.SCN_UB][0]["n"] == 2
    assert sc[RP.SCN_MAIN][1]["pnl_open"] == 100 and sc[RP.SCN_UB][1]["pnl_open"] == 150
    assert sc[RP.SCN_NOGATE][1] is None and sc[RP.SCN_EXT][1] is None
    md = RP.render(META, [], [], [], [], lots, accts, [], [], [], accts_ub)
    sec3 = md.split("## 3.")[1].split("## 4.")[0]
    assert f"| {DAY} | 1 | 1 |" in sec3                                                # B1 로트 1 · B2 계좌 1 (B1_ub 제외)


def test_main_totals_skip_stray_non_main_inputs_and_say_so():
    lots = [_lot(DAY, "B1-0000", "open", "", "100", "1000"),
            dict(_lot(DAY, "B1-0001", "open", "", "999", "1000"), tier="lift_ub")]
    accts = [_acct(DAY, "000001", "100"), _acct(DAY, "000002", "999", fill_tiers="main,lift_ub",
                                                   fill_dates="2026-09-10,2026-09-11")]
    sc = {label: b1p for label, _, b1p, _ in RP.scenarios(lots, accts, [])}
    assert sc[RP.SCN_MAIN]["n"] == 1
    md = RP.render(META, [], [], [], [], lots, accts, [], [], [])
    assert "본 집계 입력에 main 밖 체결이 섞인 행 2 — 본 집계에서 뺐다" in md


def test_crash_rows_unknown_bounds_reblock_and_add_unknown_counts():
    base = dict(crash_blocked="Y")
    ledger = [_led(DAY, "000001", "B1-0000", **base, lift_status=X.LIFT_FILLED),
              _led(DAY, "000002", **base, lift_status=X.LIFT_NO_MINUTE, lift_unknown="Y", ub_status=X.LIFT_FILLED),
              _led(DAY, "000003", **base, lift_status=X.LIFT_NO_MINUTE, lift_unknown="Y", ub_status="unfillable"),
              _led(DAY, "000004", **base, lift_status="unfillable", lift_reblocked="Y"),
              _led(DAY, "000005", "B1-0001", **base, lift_status=X.LIFT_FILLED, lift_reblocked="Y"),
              _led(DAY, "000006", tier="ext", **base, lift_status=X.LIFT_FILLED, lift_reblocked="Y"),
              _led(DAY, "000007", tier="ext", **base, lift_status=X.LIFT_NO_MINUTE, lift_unknown="Y")]
    cs = RP.crash_summary(ledger)
    assert (cs["n_main"], cs["n_unknown"], cs["ub"]) == (5, 2, {X.LIFT_FILLED: 1, "unfillable": 1})
    assert (cs["rb_main"], cs["rb_main_filled"], cs["rb_ext"], cs["unknown_ext"]) == (2, 1, 1, 1)
    lots = [_lot(DAY, "B1-0000", "open", "", "100", "1000", entry_basis=X.BASIS_LIFT),
            _lot(DAY, "B1-0001", "open", "", "10", "1000", entry_basis=X.BASIS_LIFT, code="000005"),
            dict(_lot(DAY, "B1-0000", "open", "", "100", "1000", arm="B1_ub", entry_basis=X.BASIS_LIFT)),
            dict(_lot(DAY, "B1-0001", "open", "", "10", "1000", arm="B1_ub", entry_basis=X.BASIS_LIFT, code="000005")),
            dict(_lot(DAY, "B1U-0002", "open", "", "-40", "1000", arm="B1_ub", code="000002",
                      entry_basis=X.BASIS_UPPER), tier="lift_ub")]
    accts_ub = [_acct(DAY, "000001", "100", flags=f"{A.FLAG_ADD_UNKNOWN}:2026-09-14 · mark_to_market(마지막 종가)"),
                _acct(DAY, "000002", "-40", fill_tiers="lift_ub")]
    md = RP.render(META, [], [], [], ledger, lots, [], [], [], [], accts_ub)
    sec6 = md.split("## 6.")[1].split("## 7.")[0]
    assert "분봉 없음(모른다 · 본 집계 밖) main 2행" in sec6
    assert "| B1 로트 | 2 | 3 |" in sec6                              # 하한(= 본 집계) · 상한 나란히
    assert "| B1 손익(원·실현+평가) | 110 | 70 |" in sec6
    assert "추가매수 불명(FLAG_ADD_UNKNOWN) B2 상한 계좌 1" in sec6
    assert "재차단 구간에서 샀을 main 행 2 → 다음 열린 구간 체결 1 · 미체결 1 · ext 1" in sec6


def test_lift_add_share_of_b1_vs_b2_difference_is_separated():
    b1 = [_lot(MIN, "B1-0000", "open", "", "100", "1000", code="000001"),
          _lot(MIN, "B1-0001", "open", "", "20", "1000", code="000001", entry_basis=X.BASIS_LIFT),
          _lot(MIN, "B1-0002", "open", "", "50", "1000", code="000002")]
    for r, d in zip(b1, ("2026-09-10", "2026-09-11", "2026-09-10")):
        r["entry_date"] = d
    accts = [_acct(MIN, "000001", "150", fill_dates="2026-09-10,2026-09-11", n_adds="1",
                   flags=f"{X.FLAG_LIFT_ADD}:2026-09-11 · mark_to_market(마지막 종가)"),
             _acct(MIN, "000002", "40")]
    s = RP.lift_add_split(b1, accts)[MIN]
    assert (s["n_flag"], s["diff_flag"], s["diff_all"], s["diff_rest"]) == (1, 30, 20, -10)
    md = RP.render(META, [], [], [], [], b1, accts, [], [], [])
    sec3 = md.split("## 3.")[1].split("## 4.")[0]
    assert "| 20 | 1 | 30 | -10 |" in sec3


def test_rule_sensitivity_prints_thin_n_as_unjudged_and_ok_with_its_note():
    assert RP.dir_cell(0, 3, 0.0) == "0/3 판정 불가"
    assert RP.dir_cell(12, 13, 12 / 13) == "12/13 92.31%"
    assert RP.verdict_cell(dict(verdict="ok", verdict_note="N 방향 판정 불가(n=3<5)")) == "ok — N 방향 판정 불가(n=3<5)"
    assert RP.verdict_cell(dict(verdict="LOW", verdict_note="")) == "LOW"
    sig = ([_sig(MIN, "agree_Y", slot_state="bought")] * 6 + [_sig(MIN, "na", ov1="replay_only")] * 3
           + [_sig(DAY, "agree_Y")] * 6 + [_sig(DAY, "agree_N", ov1="replay_only")] * 5)
    md = RP.render(META, sig, [], [], [], [], [], [], [], [])
    sec12 = md.split("### 1-2.")[1].split("### 1-3.")[0]
    assert "N 0/3 판정 불가" in sec12 and "N 0.00%" not in sec12
    assert "ok — N 방향 판정 불가(n=3<5)" in sec12                   # v1 칸 minervini
    sec0 = md.split("## 0.")[1].split("## 1.")[0]
    assert f"v1(옛 09:02) 규칙에서는 {DAY} 이 LOW 였다(§1-2 참조)" in sec0
    assert f"{DAY} [신호 충실도 낮음]" not in md                     # 채택 v3 에선 ok
    sec11 = md.split("### 1-1.")[1].split("### 1-2.")[0]
    assert "ok — N 방향 판정 불가(n=0<5)" in sec11                    # §1-1 v3 minervini: ok 옆에 note


def test_money_is_integer_won_and_forbidden_words_absent():
    lots = [_lot(DAY, "B1-0000", "closed", "+1.23", "1234567", "100000000")]
    md = RP.render(META, [], [], [], [], lots, [_acct(DAY, "000001", "1234567")], [], [], [])
    assert "1,234,567" in md
    for w in ("총자산", "누적수익률", "자본 대비"):
        assert w not in md
    pcts = re.findall(r"(\d[\d.]*)%", md)                                          # 한계 문구 포함 전부
    assert pcts and all(re.fullmatch(r"\d+\.\d\d", m) for m in pcts)               # % 는 소수 2자리만


def test_live_fill_rows_leave_unknown_and_live_buys_are_checked_against_b1_main():
    """과제 10 fix 1 — 분봉 없음이라도 라이브가 해제 뒤 산 행은 live_fill 로 본 집계 안(모름에서 빠짐) · §2 에 라이브 매수
    대비 B1 본 집계 포함 여부 · §6 에 건수 · «하루 종일 막았으면»은 live_fill 도 뺀다."""
    base = dict(crash_blocked="Y", lift_status=X.LIFT_NO_MINUTE)
    ledger = [_led(DAY, "000001", "B1-0000", "fill", "filled", **base, b_entry_basis=X.BASIS_LIVE_FILL),
              _led(DAY, "000002", **base, lift_unknown="Y", ub_status=X.LIFT_FILLED),
              _led(DAY, "000003", "B1-0001", "fill", "filled"),
              _led(MIN, "000004", "", "fill", "filled")]
    lots = [_lot(DAY, "B1-0000", "open", "", "10", "1000", entry_basis=X.BASIS_LIVE_FILL),
            _lot(DAY, "B1-0001", "open", "", "20", "1000", code="000003")]
    actual = [_lot(DAY, "a1", "open", "", "1", "1000", arm="A"), _lot(DAY, "a2", "open", "", "1", "1000", arm="A"),
              _lot(MIN, "a3", "open", "", "1", "1000", arm="A")]
    cs = RP.crash_summary(ledger)
    assert (cs["n_live"], cs["n_unknown"], cs["status"][X.LIFT_NO_MINUTE]) == (1, 1, 2)
    sc = {label: b1p for label, _, b1p, _ in RP.scenarios(lots, [], [])}
    assert sc[RP.SCN_ALLDAY]["pnl_open"] == 20                                          # live_fill 은 막힌 날 체결
    md = RP.render(META, [], [], [], ledger, lots, [], [], actual, [])
    sec2 = md.split("## 2.")[1].split("## 3.")[0]
    assert ("라이브 실제 매수 3건(A_actual) · main 후보 행 3 · 그중 B1 본 집계 로트가 있는 것 2(live_fill 1) · "
            f"빠진 것 {MIN} 1") in sec2
    sec6 = md.split("## 6.")[1].split("## 7.")[0]
    assert "분봉 없음 main 2행 중 1행은 라이브가 게이트 해제 뒤 실제로 샀다" in sec6
    assert "분봉 없음(모른다 · 본 집계 밖) main 1행" in sec6
    assert "| D3′ 분봉 없음 — 라이브 실제 체결로 진입(live_fill · 본 집계 안) | 1 |" in sec6


# ── 최종 검수 수정 목록 2 · 1 · 4 ─────────────────────────────────────────────────────────────────
def _exit(strategy, outcome="Y", reason="tp"):
    return dict(strategy=strategy, outcome=outcome, actual_reason=reason, same_day_actual="N", tp_sl_match="Y")


def _section0(md):
    return md.split("## 0.", 1)[1].split("## 1.", 1)[0]


def test_section0_lists_exit_fidelity_groups_that_cannot_be_judged_next_to_low():
    """#48 — §0 이 «LOW: 없음» 만 말하고 청산 충실도 «판정 불가»(표본 < FID_MIN_N) 전략을 숨기지 않는다(표에서 생성)."""
    rows = [_exit(MIN)] * 4 + [_exit(DAY)] * 5
    s0 = _section0(RP.render(META, [], rows, [], [], [], [], [], [], []))
    assert "충실도 LOW: 없음" in s0
    line = next(ln for ln in s0.splitlines() if "청산 충실도 판정 불가" in ln)
    assert f"{MIN} 판정 불가(n=4<5)" in line and DAY not in line
    s0_all_ok = _section0(RP.render(META, [], [_exit(MIN)] * 5, [], [], [], [], [], [], []))
    assert "청산 충실도 판정 불가" not in s0_all_ok


def test_entry_bias_table_says_live_fill_rows_are_not_simulated_entries():
    """I1 — 급락일 실제 매수가 분봉 없이 live_fill 로 들어가면 진입가 = 실제 체결가(시뮬 아님) → §1-6 표본에서 빼고 그 수를 적는다."""
    entry = [dict(strategy=MIN, entry_diff_pct="+1.00", first_tick="N", sim_entry_basis="D_open"),
             dict(strategy=MIN, entry_diff_pct="", first_tick="N", sim_entry_basis=X.BASIS_LIVE_FILL)]
    md = RP.render(META, [], [], entry, [], [], [], [], [], [])
    s16 = md.split("### 1-6.", 1)[1].split("## 2.", 1)[0]
    assert "| (전체) | 1 |" in s16 and "`live_fill` 1건" in s16
    assert "live_fill" not in RP.render(META, [], [], entry[:1], [], [], [], [], [], []).split("### 1-6.", 1)[1] \
        .split("## 2.", 1)[0]


def test_reuse_fills_run_heads_summary_with_the_frozen_entry_source():
    """M1(수정 목록 4) — 재추적(--reuse-fills) 실행은 summary 머리에 «진입 집합 동결» 배너(출처 파일 · 그 실행 SHA)."""
    meta = dict(META, reuse_fills="backtest/concept_axes/ledger8/results/fills_b.csv", reuse_fills_sha="09b951b")
    head = RP.render(meta, [], [], [], [], [], [], [], [], []).splitlines()[:5]
    line = next(ln for ln in head if "재추적 모드" in ln)
    assert "backtest/concept_axes/ledger8/results/fills_b.csv" in line and "09b951b" in line
    assert "판정 근거로 쓰지 말 것" in "".join(head[:3])                            # 관측 원장 배너는 그대로 3번째 줄
    unknown = RP.render(dict(meta, reuse_fills_sha=""), [], [], [], [], [], [], [], [], []).splitlines()[:5]
    assert any("재추적 모드" in ln and "불명" in ln for ln in unknown)
    assert "재추적 모드" not in RP.render(dict(META, reuse_fills=""), [], [], [], [], [], [], [], [], [])
    assert "재추적 모드" not in RP.render(META, [], [], [], [], [], [], [], [], [])
