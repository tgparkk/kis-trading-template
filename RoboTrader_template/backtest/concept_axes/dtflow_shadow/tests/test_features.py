from datetime import date

from backtest.concept_axes.dtflow_shadow import features as F

CAL = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
D = date(2026, 10, 8)


def _bodies():
    inv = {"rt_cd": "0", "output": [
        {"stck_bsop_date": "20261012", "orgn_ntby_tr_pbmn": "0", "frgn_ntby_tr_pbmn": "0", "prsn_ntby_tr_pbmn": ""},
        {"stck_bsop_date": "20261008", "orgn_ntby_tr_pbmn": "-500", "frgn_ntby_tr_pbmn": "1,000", "prsn_ntby_tr_pbmn": "-500"},
        {"stck_bsop_date": "20261007", "orgn_ntby_tr_pbmn": "100", "frgn_ntby_tr_pbmn": "0", "prsn_ntby_tr_pbmn": "0"}]}
    prog = {"rt_cd": "0", "output": [
        {"stck_bsop_date": "20261008", "acml_tr_pbmn": "10000000000", "whol_smtn_ntby_tr_pbmn": "-2000000000"},
        {"stck_bsop_date": "20261007", "acml_tr_pbmn": "5000000000", "whol_smtn_ntby_tr_pbmn": "0"}]}
    short = {"rt_cd": "0", "output1": {}, "output2": [
        {"stck_bsop_date": "20261008", "ssts_vol_rlim": "1.25", "ssts_tr_pbmn_rlim": "1.10"}]}
    credit = {"rt_cd": "0", "output": [
        {"deal_date": "20261002", "whol_loan_rmnd_rate": "3.5", "whol_loan_gvrt": "10.0"},
        {"deal_date": "20261001", "whol_loan_rmnd_rate": "3.4", "whol_loan_gvrt": "9.0"}]}
    return {"investor": inv, "program": prog, "short": short, "credit": credit}


def test_pick_uses_date_not_first_row():
    out = F.compute(D, _bodies(), CAL, k=3)
    assert abs(out["f1_orgn"] - (-500 * 1e6 / 1e10)) < 1e-12        # 첫 행(20261012 0) 아님
    assert abs(out["f2_prog"] - (-0.2)) < 1e-12
    assert out["f3_short"] == 1.25


def test_credit_lag_and_fixed_k():
    out = F.compute(D, _bodies(), CAL, k=3)
    assert out["credit_deal_date"] == "20261002" and out["credit_lag"] == 3
    assert out["f4_credit"] == 3.5 and out["has_credit"]
    assert F.compute(D, _bodies(), CAL, k=2)["f4_credit"] is None
    assert F.compute(D, _bodies(), CAL, k=None)["f4_credit"] is None


def test_missing_denominator_gives_none_and_flags():
    b = _bodies()
    b["program"] = {"rt_cd": "0", "output": []}
    out = F.compute(D, b, CAL, k=3)
    assert out["f1_orgn"] is None and out["f2_prog"] is None and not out["has_investor"] and not out["has_program"]


def test_num_parsing():
    assert F.num("1,234") == 1234.0 and F.num("") is None and F.num("-") is None and F.num(None) is None
