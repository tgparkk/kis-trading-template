"""분석 생성기 — `RESULTS_explore`·`RESULTS_confirm`·`RESULTS_c2`·`sealed_indep` 문서(사전등록 §5·§6·§8 + 수정 1).

    python -X utf8 -m backtest.concept_axes.minute_rules.analyze explore    # 로트 csv = 비공개/E · 메타 = results/E
    python -X utf8 -m backtest.concept_axes.minute_rules.analyze confirm
    python -X utf8 -m backtest.concept_axes.minute_rules.analyze c2
    python -X utf8 -m backtest.concept_axes.minute_rules.analyze sealed --i-understand-sealed

🔒 실자료 관문(CLI · 수정 1 §7 NB2): 작업 트리 깨끗 · 입력 csv sha256 = 그 창 run_meta `outputs` · run_meta `ok` ·
   run_meta 코드 해시 = 지금 코드(`run.code_hashes`) · C·C2·U = run_meta `explore.sha256` = 커밋된 RESULTS_explore.md ·
   앞 단계 json·md = git 추적 ∧ HEAD 와 같음 ∧ json `results_md_sha256` = md · E = 가짜 시점 csv 필수(100개).
   함수(`explore`·`confirm`·…)를 직접 부르는 합성 테스트 경로에는 관문이 없다(`prov=None`).

🔒 `SPEC` = 이 생성기가 쓰는 모든 판정 상수(방향·모집단·순위 기준일·주 분석 제외·θ·m·B·시드 번호) — 결과를
   보기 «전»에 고정했다(수정 1 · 2026-11-11). `SPEC_SHA256` 이 run_meta·결과 문서 머리에 찍힌다. 바꾸면 해시가 바뀐다.
🔴 관측 — 판정 근거 아님(§8 배너). EOD 출력 금지. 독립 가족 결과와 주 가족 «≤09:10/>09:10» 두 칸 표는 `sealed` 로만
   (레포 밖 봉인 폴더 · 레포에는 `results/sealed_indep.sha256` 만).
⚙ 사전등록이 정하지 않아 여기서 정한 것(수정 1 문서 §3): 독립 가족 θ = θ_시점 · 거르기 «상위 10종목 기여» =
   한 종목씩 빼 본 영향 상위 10종목을 함께 뺐을 때 Δ 가 줄어든 몫 · 시점 = 종목별 δ 합 상위 10 ÷ 전체 합
   (둘 다 점추정 부호 기준) · MDE 재계산 = (z_{1−α/2m}+z_{0.8})×SE · 국면 칸 n ≥ 100 만 «반대 부호 없음»
   판정에 씀 · «같은 부호» = 점추정 부호.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from statistics import NormalDist
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import test_stats as S

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "results"

SPEC: Dict[str, Any] = {
    "version": 1,
    "prereg": "docs/prereg_2026-11-11_minute_rules.md@e2945ee",
    "amendment": "docs/prereg_2026-11-11_minute_rules_amendment1.md",
    "population_main": "band_ok_open == True",                    # 수정 1 결정 1
    "population_ref": "all lots(band_ok_open 무관 · 참고)",
    "rank_basis_main": "tv_bucket_d",                             # 수정 1 결정 2(신호일 D)
    "rank_basis_ref": "tv_bucket_d1",
    "main_excl": "excl_reason == '' and main_excl == '' and print_only != True",
    "inclusive_ref": "excl_reason == '' and print_only != True(market_gap_day·open_gap 포함판)",
    "filter_undetermined": "양 군 제외 · 건수 인쇄",
    "model_b_missing": "그 짝 제외(현금 아님)",
    "timing_rules": ["R1", "R3", "R7", "R6"],
    "filter_rules": ["R4", "R5"],
    "indep_rules": ["H2_HIST", "H_PLUS2"],
    "base": {"timing": "R0", "filter": "R0_0905", "indep": "R0"},
    "direction": {"R1": S.GREATER, "R6": S.GREATER, "R3": S.TWO, "R7": S.TWO, "R4": S.GREATER, "R5": S.GREATER,
                  "H2_HIST": S.LESS, "H_PLUS2": S.GREATER},
    "alpha": S.ALPHA, "m_main": 6, "m_indep": 2, "B": S.B_DEFAULT,
    "theta_timing": 0.754, "theta_filter": 2.0, "theta_indep": 0.754, "cost_roundtrip_pct": 0.20703,
    "f_min_filter": 0.15, "fake_n": 100, "fake_f": 0.2, "fake_cut": S.FAKE_CUT, "fake_switch": S.FAKE_SWITCH,
    "ipw_cap": S.IPW_CAP, "regime_min_n": 100, "kospi_day_split_pct": 3.0, "top_k": 10, "top_share_max": 0.5,
    "c2_min_pairs": 300, "split_0910": "090959", "mde_power": 0.8, "mde_m": [1, 4, 6, 10], "c_plan_n": 960,
    "windows_w": {"E": S.W_E, "C": S.W_C, "C2": S.W_C2, "U": S.W_U}, "w_fake": S.W_FAKE,
    "rule_no": S.RULE_NO, "fake_filter_r0": S.FAKE_FILTER_R0, "fake_timing_p_r0": S.FAKE_TIMING_P_R0,
    "ci": "basic — p 와 같은 순서통계량(하한>0 ⇔ p_greater ≤ α/2 · 상한<0 ⇔ p_less ≤ α/2 · 수정 1 결정 3·§7 D1)",
    "two_sided_p": "min(1, 2·min(p_greater, p_less))(등꼬리 · 수정 1 §7 D1)",
    "ret_missing": "ret 결측 로트 = 그 규칙 주 분석 제외 + 건수 인쇄(R5)",
    "g9": "filled_minutes 상위 사분위(주 분석 로트 75백분위 초과) 뺀 점추정 인쇄",
    "g10_cut": "2026-07-03(scan_date ≥ 이 날 = vintage_m4 아님 · 부분 점추정 인쇄)",
    "f_below_min": "판정 불가(불통과와 구분 · R3)",
    "c2_only_c_passed": True,
    "split_rule": "규칙 arm 진입 분 시작 ≤ 09:09 = «≤09:10» 칸 · 09:10 분 진입 = «>09:10» 칸"
                  "(H②-hist «≥09:10 = 늦음» 경계)",
    "fakes_required": 100,
}
SPEC_SHA256 = hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
BANNER = "> 🔴 관측 — 판정 근거 아님(사전등록 §8) · EOD 출력 금지 · 룰 변경은 사장님 결정(§6-D)"
SEALED_BANNER = "> 🔒 봉인 — 그림자 ② 판정(짝 ≥40 · 매수일 ≥15) 전 열람·인용 금지(§4-2·§8)"
META = ["lot_id", "window", "strategy", "scan_date", "entry_date", "stock_code", "month", "band_ok_open", "main_excl",
        "excl_reason", "print_only", "tv_bucket_d", "tv_bucket_d1", "kospi20", "kospi_day_ret", "daily_fallback",
        "adj_null_prev", "adj_null_entry", "market_gap_day", "open_gap_flag", "corp_event", "filled_minutes",
        "vintage_m4"]
ARMF = ["ret", "b_ret", "c_ret", "entered", "entry_time", "label", "b_missing", "b_on_empty", "sl_tp_same_minute",
        "gap_tp_overridden", "undetermined_minutes"]
NAN = float("nan")


# ── 입력 ─────────────────────────────────────────────────────────────────
def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_lots(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def wide(df: pd.DataFrame) -> pd.DataFrame:
    """로트 × arm 긴 표 → 로트 1행(`<arm>:<열>`) · lot_id 정렬 · (lot_id, arm) 중복이면 중단."""
    if df.duplicated(["lot_id", "arm"]).any():
        raise SystemExit("🔴 입력에 (lot_id, arm) 중복 — lots_rule.csv 가 아니거나 손상")
    meta = df.drop_duplicates("lot_id")[[c for c in META if c in df.columns]].set_index("lot_id")
    p = df.pivot(index="lot_id", columns="arm", values=[c for c in ARMF if c in df.columns])
    p.columns = [f"{a}:{f}" for f, a in p.columns]
    return meta.join(p).sort_index()


def _num(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s.replace("", np.nan), errors="coerce").to_numpy(dtype=np.float64)


def _true(s: pd.Series) -> np.ndarray:
    return (s == "True").to_numpy()


def masks(W: pd.DataFrame) -> Dict[str, np.ndarray]:
    """🔒 모집단(결정 1)·주 분석 제외(SPEC.main_excl) — 주 = pop ∧ clean · 참고 = 모집단 무관 · 포함판 = 공백일 포함."""
    pop = _true(W["band_ok_open"])
    held = (W["excl_reason"] == "").to_numpy()
    not_po = ~_true(W["print_only"])
    clean = held & (W["main_excl"] == "").to_numpy() & not_po
    return dict(pop=pop, held=held, not_po=not_po, main=pop & clean, ref=clean, incl=pop & held & not_po)


def _sign(x: Optional[float]) -> int:
    return 0 if x is None or x != x else int(np.sign(x))


def fav(rule: str) -> int:
    """유리한 방향 부호 — 단측 less = −1 · greater·양측 = +1(양측 음의 방향 = «현행 쪽» 기록만 · §4-1)."""
    return -1 if SPEC["direction"][rule] == S.LESS else 1


# ── 규칙 1개 ──────────────────────────────────────────────────────────────
class RuleCalc:
    """규칙 1개 · 창 1개의 점추정·p·부트스트랩 분포·부가 표(IPW·국면·월·한 달 빼기·상위 10·순위 구간·모델 b·c)."""

    def __init__(self, W: pd.DataFrame, mask: np.ndarray, rule: str, kind: str, w: int, B: int,
                 ipw: Dict[str, pd.Series], full: bool = True):
        self.rule, self.kind, self.dirn = rule, kind, SPEC["direction"][rule]
        base = SPEC["base"]["filter" if kind == "filter" else "timing"]
        sub = W[mask]
        self.n_undetermined = 0
        if kind == "filter":
            lab = sub[f"{rule}:label"]
            self.n_undetermined = int((lab == "undetermined").sum())
            sub = sub[lab.isin(["keep", "filter"]).to_numpy()]
            self.keep = (sub[f"{rule}:label"] == "keep").to_numpy()
            self.y = _num(sub[f"{base}:ret"])
            self.shift = float(np.mean(_num(sub[f"{base}:ret"]) - _num(sub["R0:ret"]))) if len(sub) else NAN
        else:
            self.y = _num(sub[f"{rule}:ret"]) - _num(sub[f"{base}:ret"])
            aff = ((sub[f"{rule}:entered"] != sub[f"{base}:entered"])
                   | (sub[f"{rule}:entry_time"] != sub[f"{base}:entry_time"])).to_numpy()
            self.aff = aff
        ok = np.isfinite(self.y)                                  # R5 — ret 결측 = 제외 + 건수
        self.n_ret_missing = int((~ok).sum())
        if not ok.all():
            sub, self.y = sub[ok], self.y[ok]
            if kind == "filter":
                self.keep = self.keep[ok]
            else:
                self.aff = self.aff[ok]
        self.sub, self.base = sub, base
        self.days = sub["entry_date"].to_numpy()
        self.stocks = sub["stock_code"].to_numpy()
        self.n = len(sub)
        self.est = self.stat(np.ones(self.n, bool))[0] if self.n else NAN
        self.out: Dict[str, Any] = dict(rule=rule, kind=kind, direction=self.dirn, n=self.n,
                                        n_days=len(set(self.days)), n_codes=len(set(self.stocks)), est=self.est,
                                        n_ret_missing=self.n_ret_missing)
        if kind == "filter":
            st = S.filter_stat(self.y, self.keep, self.days)
            self.out.update(n_undetermined=self.n_undetermined, n_keep=st.n_keep, n_filter=st.n_filter,
                            n_info_days=st.n_info_days, f=st.f, judgeable=bool(st.f >= SPEC["f_min_filter"]),
                            shift_0905_minus_r0=self.shift)
        else:
            ts = S.timing_stat(self.y, self.aff)
            um = _num(sub[f"{rule}:undetermined_minutes"]) if f"{rule}:undetermined_minutes" in sub else np.zeros(0)
            um = np.nan_to_num(um)
            self.out.update(f=ts.f, est_aff=ts.mean_aff, undet_min_lots=int((um > 0).sum()),
                            undet_min_total=int(um.sum()))
        self.dist: Dict[str, np.ndarray] = {}
        if full and self.n:
            self._tests(w, B)
            self._extras(W, ipw)

    def stat(self, m: np.ndarray, weights: Optional[np.ndarray] = None) -> Tuple[float, int]:
        """부분 집합 m 의 (δ̄ 또는 Δ, n)."""
        if not m.any():
            return NAN, 0
        if self.kind == "filter":
            wts = None if weights is None else weights[m]
            return S.filter_stat(self.y[m], self.keep[m], self.days[m], weights=wts).delta, int(m.sum())
        if weights is None:
            return float(self.y[m].mean()), int(m.sum())
        w = weights[m]
        return (float((w * self.y[m]).sum() / w.sum()) if w.sum() > 0 else NAN), int(m.sum())

    def _tests(self, w: int, B: int) -> None:
        rng = S.rng_for(w, SPEC["rule_no"][self.rule])
        if self.kind == "filter":
            perm = S.filter_perm(self.y, self.keep, self.days, B, rng)
            self.out["p_main"] = S.p_perm(self.est, perm, self.dirn)
            self.dist["main_ci"] = S.filter_block_boot(self.y, self.keep, self.days, B, rng)
            tw = S.twoway_boot(S.filter_weighted_stat(self.y, self.keep, self.days), self.stocks, self.days, B, rng)
        else:
            boot = S.block_boot_means(self.y, self.days, B, rng)
            self.out["p_main"] = S.p_boot(self.est, boot, self.dirn)
            self.dist["main_ci"] = boot
            tw = S.twoway_boot(S.weighted_mean_stat(self.y), self.stocks, self.days, B, rng)
        self.dist["twoway"] = tw
        self.out["p_twoway"] = S.p_boot(self.est, tw, self.dirn)
        self.out["se"] = float(np.nanstd(self.dist["main_ci"]))

    def _extras(self, W: pd.DataFrame, ipw: Dict[str, pd.Series]) -> None:
        sub, o, c = self.sub, self.out, SPEC["cost_roundtrip_pct"]
        # 순(비용) · 모델 b·c
        if self.kind == "filter":
            ent = _true(sub[f"{self.base}:entered"]).astype(float)
            o["net_filter_mean"] = float(np.mean((self.y - c * ent)[~self.keep])) if (~self.keep).any() else NAN
            for mdl in ("b", "c"):
                v = _num(sub[f"{self.base}:{mdl}_ret"])
                ok = np.isfinite(v)
                o[f"est_{mdl}"] = (S.filter_stat(v[ok], self.keep[ok], self.days[ok]).delta if ok.any() else NAN)
                o[f"n_{mdl}"] = int(ok.sum())
        else:
            ex = _true(sub[f"{self.rule}:entered"]).astype(float)
            eb = _true(sub[f"{self.base}:entered"]).astype(float)
            o["net_est"] = float(np.mean(self.y - c * (ex - eb)))
            for mdl in ("b", "c"):
                v = _num(sub[f"{self.rule}:{mdl}_ret"]) - _num(sub[f"{self.base}:{mdl}_ret"])
                ok = np.isfinite(v)
                o[f"est_{mdl}"] = float(v[ok].mean()) if ok.any() else NAN
                o[f"n_{mdl}"] = int(ok.sum())
        # IPW(주 = D · 참고 = D+1)
        for key, ser in ipw.items():
            wts = ser.reindex(sub.index).to_numpy(dtype=np.float64)
            ok = np.isfinite(wts)
            o[f"ipw_{key}"] = self.stat(ok, np.where(ok, wts, 0.0))[0]
            o[f"ipw_{key}_ess"] = S.ess(wts[ok])
        # 국면 칸
        k20, kd = _num(sub["kospi20"]), _num(sub["kospi_day_ret"])
        cut = SPEC["kospi_day_split_pct"]
        cells = {"kospi20>=0": k20 >= 0, "kospi20<0": k20 < 0, f"day>=+{cut:g}": kd >= cut,
                 f"day<=-{cut:g}": kd <= -cut, "day_between": (kd > -cut) & (kd < cut)}
        o["regime"] = {k: dict(zip(("est", "n"), self.stat(m))) for k, m in cells.items()}
        # 월 · 한 달 빼기
        months = sub["month"].to_numpy()
        o["months"] = {mo: dict(zip(("est", "n"), self.stat(months == mo))) for mo in sorted(set(months))}
        loo = [self.stat(months != mo)[0] for mo in sorted(set(months))] if len(set(months)) > 1 else []
        s = _sign(self.est) or 1                                   # «같은 부호» = 점추정의 부호 기준
        o["loo_month_min_signed"] = float(min(s * v for v in loo)) if loo else NAN
        # 상위 10종목 기여
        o["top10_share"] = self._top_share(s)
        # G9 — filled_minutes 상위 사분위 뺀 결과 · G10 — scan_date ≥ 07-03 부분
        fm = _num(sub["filled_minutes"]) if "filled_minutes" in sub else np.full(self.n, np.nan)
        if np.isfinite(fm).any():
            q = float(np.nanquantile(fm, 0.75))
            o["g9_q75"], (o["g9_est"], o["g9_n"]) = q, self.stat(np.isfinite(fm) & (fm <= q))
        if "vintage_m4" in sub:
            o["post0703_est"], o["post0703_n"] = self.stat((sub["vintage_m4"] == "False").to_numpy())
        # 순위 구간(보유율은 창 수준 표에서)
        for key in ("tv_bucket_d", "tv_bucket_d1"):
            b = sub[key].to_numpy()
            o[f"by_{key}"] = {k: dict(zip(("est", "n"), self.stat(b == k))) for k in sorted(set(b))}

    def _top_share(self, s: int) -> float:
        k = SPEC["top_k"]
        uniq = sorted(set(self.stocks))
        if self.kind == "timing":
            contrib = {u: float(self.y[self.stocks == u].sum()) for u in uniq}
            tot = s * sum(contrib.values())
            if not tot > 0:
                return NAN
            top = sorted((s * v for v in contrib.values()), reverse=True)[:k]
            return float(sum(top) / tot)
        if not s * self.est > 0:
            return NAN
        infl = {u: s * (self.est - self.stat(self.stocks != u)[0]) for u in uniq}
        top = [u for u, _ in sorted(infl.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]
        rest = self.stat(~np.isin(self.stocks, top))[0]
        return float(1.0 - s * rest / (s * self.est)) if rest == rest else 1.0

    def mde(self, n_plan: Optional[int]) -> Dict[str, Any]:
        """검정력 재계산 — MDE_m = (z_{1−α/(2m)} + z_{power}) × SE(이 창) · n_plan 이면 √(n/n_plan) 로 옮긴 값도."""
        se = self.out.get("se", NAN)
        z = NormalDist().inv_cdf
        out = {}
        for m in SPEC["mde_m"]:
            v = (z(1 - SPEC["alpha"] / (2 * m)) + z(SPEC["mde_power"])) * se
            out[f"m{m}"] = v
            if n_plan:
                out[f"m{m}_at_{n_plan}"] = v * (self.n / n_plan) ** 0.5
        return out


def ipw_series(W: pd.DataFrame, mk: Dict[str, np.ndarray]) -> Dict[str, pd.Series]:
    """IPW 가중(로트 lot_id → w) — P(보유 | 순위 구간, 월) · 분모 = 모집단(주) ∧ print_only 아님 · 보유 = 분봉 있음."""
    base = mk["pop"] & mk["not_po"]
    sub = W[base]
    held = mk["held"][base]
    out = {}
    for key, col in (("d", SPEC["rank_basis_main"]), ("d1", SPEC["rank_basis_ref"])):
        r = S.ipw_weights(held, sub[col].to_numpy(), sub["month"].to_numpy(), SPEC["ipw_cap"])
        out[key] = pd.Series(r.weights, index=sub.index[held])
    return out


def holding_table(W: pd.DataFrame, mk: Dict[str, np.ndarray]) -> Dict[str, Dict[str, Any]]:
    """보유율(분봉 있음 몫) — 순위 구간(D·D+1) · 월(§5-1 월별 표 · D2)."""
    base = mk["pop"] & mk["not_po"]
    out = {}
    for col in ("tv_bucket_d", "tv_bucket_d1", "month"):
        b = W[col].to_numpy()[base]
        h = mk["held"][base]
        out[col] = {k: dict(n=int((b == k).sum()), held=int(h[b == k].sum()),
                            rate=float(h[b == k].mean()) if (b == k).any() else NAN) for k in sorted(set(b))}
    return out


# ── 창 1개 ───────────────────────────────────────────────────────────────
def window_calc(W: pd.DataFrame, window: str, rules: Sequence[str], B: int, full: bool = True
                ) -> Tuple[Dict[str, RuleCalc], Dict[str, Any]]:
    mk = masks(W)
    ipw = ipw_series(W, mk)
    w = SPEC["windows_w"][window]
    calcs = {r: RuleCalc(W, mk["main"], r, "filter" if r in SPEC["filter_rules"] else "timing", w, B, ipw, full)
             for r in rules}
    info: Dict[str, Any] = dict(
        n_lots=len(W), n_pop=int(mk["pop"].sum()), n_held=int(mk["held"].sum()), n_main=int(mk["main"].sum()),
        n_print_only=int((~mk["not_po"]).sum()),
        n_main_excl=int((mk["pop"] & mk["held"] & mk["not_po"] & (W["main_excl"] != "").to_numpy()).sum()),
        n_excl_g5=int((mk["pop"] & mk["held"] & mk["not_po"] & _true(W["market_gap_day"])).sum()),
        n_excl_g7=int((mk["pop"] & mk["held"] & mk["not_po"] & _true(W["open_gap_flag"])).sum()),
        n_no_rank_d=int((mk["pop"] & mk["not_po"] & (W["tv_bucket_d"] == "").to_numpy()).sum()),
        excl_reason={k: int(v) for k, v in W["excl_reason"][mk["pop"]].value_counts().items() if k},
        holding=holding_table(W, mk),
        ipw_ess={k: S.ess(v.to_numpy()) for k, v in ipw.items()},
        flags={f: int(_true(W[f])[mk["main"]].sum()) for f in ("adj_null_prev", "adj_null_entry", "corp_event")
               if f in W.columns})
    arms = sorted({c.split(":")[0] for c in W.columns if ":" in c})
    info["arm_flags"] = {a: {f: int(_true(W[f"{a}:{f}"])[mk["main"]].sum())
                             for f in ("b_missing", "b_on_empty", "sl_tp_same_minute", "gap_tp_overridden")
                             if f"{a}:{f}" in W.columns} for a in arms}
    # 참고판(모집단 무관) · 포함판(공백일 포함) — 점추정만
    info["ref"] = {r: RuleCalc(W, mk["ref"], r, calcs[r].kind, w, B, ipw, full=False).out for r in rules}
    info["incl"] = {r: RuleCalc(W, mk["incl"], r, calcs[r].kind, w, B, ipw, full=False).out for r in rules}
    return calcs, info


def fake_rates(W: pd.DataFrame, fakes: pd.DataFrame, B: int) -> Dict[str, Any]:
    """§5-3 가짜 규칙 보정(E) — ① 종목 상수 노이즈 거르기 100(f=0.2 · 블록 순열 p 양측)
    ② 무작위 u 시점 100(블록 부트스트랩 p 양측)."""
    mk = masks(W)
    sub = W[mk["main"]]
    days, stocks = sub["entry_date"].to_numpy(), sub["stock_code"].to_numpy()
    y0905 = _num(sub["R0_0905:ret"])
    r0 = _num(sub["R0:ret"])
    pf = []
    for k in range(SPEC["fake_n"]):
        rng = S.rng_for(SPEC["w_fake"], SPEC["fake_filter_r0"] + k)
        keep = S.fake_filter_keep(stocks, SPEC["fake_f"], rng)
        t = S.filter_stat(y0905, keep, days).delta
        pf.append(S.p_perm(t, S.filter_perm(y0905, keep, days, B, rng), S.TWO))
    pt = []
    n_t = 0
    if fakes is not None and len(fakes):
        mat = fakes.pivot(index="lot_id", columns="fake_k", values="ret")
        for k in sorted(mat.columns, key=int):
            v = _num(mat[k].reindex(sub.index).fillna(""))
            d = v - r0
            ok = np.isfinite(d)
            if not ok.any():
                continue
            n_t += 1
            rng = S.rng_for(SPEC["w_fake"], SPEC["fake_timing_p_r0"] + int(k))
            boot = S.block_boot_means(d[ok], days[ok], B, rng)
            pt.append(S.p_boot(float(d[ok].mean()), boot, S.TWO))
    rf, rt = S.fake_rate(pf), S.fake_rate(pt)
    return dict(filter_rate=rf, timing_rate=rt, n_filter=len(pf), n_timing=n_t,
                switch_filter=S.use_twoway(rf), switch_timing=S.use_twoway(rt))


def holm_and_ci(calcs: Dict[str, RuleCalc], m: int, switch: Dict[str, bool]) -> None:
    """Holm(비교값 = 단측 2p · 양측 p) · 조정 구간 = basic(1 − α_k) · 가짜 비율 > 0.075 인 분류는 2원 군집 p·분포."""
    cmp = {}
    for r, c in calcs.items():
        if "p_main" not in c.out:
            cmp[r] = 1.0
            continue
        use_tw = switch.get(c.kind, False)
        p = c.out["p_twoway"] if use_tw else c.out["p_main"]
        c.out["p_used"], c.out["p_used_kind"] = p, "twoway" if use_tw else "main"
        cmp[r] = S.compare_value(p, one_sided=c.dirn != S.TWO)
    for row in S.holm(cmp, m=m, alpha=SPEC["alpha"]):
        c = calcs[row.rule]
        c.out.update(holm_compare=row.compare, holm_order=row.order, holm_threshold=row.threshold,
                     holm_rejected=row.rejected)
        dist = c.dist.get("twoway" if c.out.get("p_used_kind") == "twoway" else "main_ci")
        if dist is None:
            continue
        lo, hi = S.basic_ci(dist, c.est, row.threshold)
        c.out.update(ci_lo=lo, ci_hi=hi, ci_level=1 - row.threshold)
        s = fav(c.rule)
        c.out["ci_fav"] = bool(lo > 0) if s > 0 else bool(hi < 0)
        if c.dirn == S.TWO:
            c.out["ci_current_side"] = bool(hi < 0)      # 양측 음의 방향 = «현행 쪽» 기록만


def verdict_of(conds: Dict[str, Optional[bool]]) -> str:
    """조건 dict → «통과» · «불통과» · «판정 불가»(거르기 f < 0.15 · R3)."""
    if conds.get("f_min") is False:
        return "판정 불가"
    return "통과" if all(v for v in conds.values() if v is not None) else "불통과"


def c2_verdict(rule: str, kind: str, n: int, est: float, c_sign: int, c_verdict: str) -> str:
    """§6-B — C 를 통과한 규칙만 판정(R4 · 나머지 «해당 없음») · 시점 = 짝 ≥300 ∧ 같은 부호 ∧ 유리 방향 ≥ θ/2 ·
    거르기 = 부호 일치만."""
    if c_verdict != "통과":
        return "해당 없음"
    same = _sign(est) == c_sign != 0
    if kind == "filter":
        return "통과" if same else "불통과"
    if n < SPEC["c2_min_pairs"]:
        return "판정 불가 · 연장"
    return "통과" if same and fav(rule) * est >= SPEC["theta_timing"] / 2 else "불통과"


def cell_of(entered: bool, entry_time: str) -> str:
    """두 칸 표 칸(D5 · SPEC.split_rule) — 안 삼 · ≤09:10(분 시작 ≤ 09:09) · >09:10(09:10 분 진입 포함)."""
    if not entered:
        return "cash"
    return "le0910" if entry_time <= SPEC["split_0910"] else "gt0910"


def criteria(c: RuleCalc, theta: float, e_sign: Optional[int]) -> Dict[str, Optional[bool]]:
    """§6-A 조건 목록(모두 참이어야 통과) · e_sign None = 독립 가족(«E 와 같은 부호» 없음)."""
    o, s = c.out, fav(c.rule)
    sg = _sign(c.est)
    big = [v["est"] for v in (o["regime"]["kospi20>=0"], o["regime"]["kospi20<0"]) if v["n"] >= SPEC["regime_min_n"]]
    conds: Dict[str, Optional[bool]] = {
        "holm_ci": bool(o.get("holm_rejected")) and bool(o.get("ci_fav")),
        "theta": bool(s * c.est >= theta),
        "same_sign_E": None if e_sign is None else bool(e_sign == sg != 0),
        "models_abc": bool(sg != 0 and _sign(o.get("est_b")) == sg and _sign(o.get("est_c")) == sg),
        "net": bool(o["net_filter_mean"] < 0) if c.kind == "filter" else bool(s * o["net_est"] > 0),
        "ipw": bool(_sign(o.get("ipw_d")) == sg != 0),
        "regime": all(_sign(v) != -sg for v in big),
        "loo_month": bool(o.get("loo_month_min_signed", NAN) > 0),
        "top10": bool(o.get("top10_share", NAN) < SPEC["top_share_max"]),
    }
    if c.kind == "filter":
        conds["f_min"] = bool(o["judgeable"])
    return conds


# ── 문서 ─────────────────────────────────────────────────────────────────
def _f(x: Any, nd: int = 3) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    if isinstance(x, bool):
        return "예" if x else "아니오"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    return f"{float(x):+.{nd}f}" if nd else f"{float(x):.0f}"


def _head(title: str, inputs: Dict[str, str], B: int, extra: Sequence[str] = (),
          prov: Optional[Dict[str, Any]] = None) -> List[str]:
    L = [f"# {title}", "", BANNER, "", f"- SPEC sha256 `{SPEC_SHA256}` · B = {B:,}"
         + ("" if B == SPEC["B"] else f" 🔴 등록값 {SPEC['B']:,} 과 다름 — 판정 무효(시험용)")]
    if prov is None:
        L.append("- 🔴 출처 관문 없음(합성·시험 경로) — 판정 근거 아님")
    else:
        L += [f"- 출처: git `{prov['git_sha']}` · 코드 해시 digest `{prov['code_digest']}` · "
              f"run_meta sha256 {prov['run_meta']}"]
        L += [f"  - 앞 단계 `{k}` 커밋 `{v}`" for k, v in prov["prior"].items()]
    L += [f"- 입력 `{k}` sha256 `{v}`" for k, v in inputs.items()] + list(extra) + [""]
    return L


def _info_lines(info: Dict[str, Any]) -> List[str]:
    L = ["## 표본 · 제외 · 플래그", "",
         f"- 로트 {info['n_lots']:,} · 모집단(시가 band_ok) {info['n_pop']:,} · 분봉 있음 {info['n_held']:,} · "
         f"주 분석 {info['n_main']:,} · 공백일·시가 차 제외 {info['n_main_excl']:,}(G5 공백일 {info['n_excl_g5']:,} · "
         f"G7 시가 차 >2% {info['n_excl_g7']:,}) · print_only {info['n_print_only']:,} · D 순위 없음 "
         f"{info['n_no_rank_d']:,} · 분봉 제외 사유 {info['excl_reason']}",
         f"- 주 분석 플래그: {info['flags']} · IPW ESS(D/D+1) {info['ipw_ess']}"]
    for a, fl in info["arm_flags"].items():
        L.append(f"  - {a}: {fl}")
    L += ["", "### 보유율(분봉 있음 몫) — 순위 구간(주 = 신호일 D · 참고 = 진입일 D+1) · 월별", ""]
    for col, tab in info["holding"].items():
        L.append(f"- {col}: " + " · ".join(f"{k or '(없음)'} {v['held']}/{v['n']} = {_f(v['rate'])}"
                                           for k, v in tab.items()))
    return L + [""]


def _rule_table(calcs: Dict[str, RuleCalc], judge: bool) -> List[str]:
    hdr = ("| 규칙 | 방향 | n | 매수일 | 종목 | f | 점추정(gross) | 순 | p | 2원 p | Holm 비교값 | 문턱 |"
           " 조정 구간(basic) |"
           " b | c | IPW D | IPW D+1 |")
    L = [hdr, "|" + "---|" * 17]
    for r, c in calcs.items():
        o = c.out
        net = o.get("net_est", o.get("net_filter_mean"))
        ci = f"[{_f(o.get('ci_lo'))}, {_f(o.get('ci_hi'))}]" if "ci_lo" in o else "—"
        L.append(f"| {r} | {o['direction']} | {o['n']:,} | {o['n_days']} | {o['n_codes']} | {_f(o['f'])} | "
                 f"{_f(o['est'])} | {_f(net)} | {_f(o.get('p_main'), 4)} | {_f(o.get('p_twoway'), 4)} | "
                 f"{_f(o.get('holm_compare'), 4) if judge else '(참고)'} | {_f(o.get('holm_threshold'), 4)} | {ci} | "
                 f"{_f(o.get('est_b'))} | {_f(o.get('est_c'))} | {_f(o.get('ipw_d'))} | {_f(o.get('ipw_d1'))} |")
    L.append("")
    for r, c in calcs.items():
        o = c.out
        extra = [f"δ̄_aff {_f(o.get('est_aff'))} · 분 단위 판단 불가 로트 {o.get('undet_min_lots', 0)}"
                 f"(분 합 {o.get('undet_min_total', 0)})"] if c.kind == "timing" else [
            f"keep {o['n_keep']} · filter {o['n_filter']} · undetermined {o['n_undetermined']} · 정보 있는 날 "
            f"{o['n_info_days']} · 판정 가능(f ≥ 0.15) {_f(o['judgeable'])} · 09:05 이동 몫 "
            f"{_f(o['shift_0905_minus_r0'])}"]
        L.append(f"- **{r}** " + " · ".join(extra)
                 + f" · 한 달 빼기 최소(점추정 부호 기준) {_f(o.get('loo_month_min_signed'))}"
                 f" · 상위 10종목 기여 {_f(o.get('top10_share'))} · ret 결측 제외 {o.get('n_ret_missing', 0)}")
        L.append(f"  - G9 filled_minutes ≤ q75({_f(o.get('g9_q75'), 0)}) {_f(o.get('g9_est'))}(n {o.get('g9_n', 0)}) · "
                 f"G10 scan_date ≥ 07-03 {_f(o.get('post0703_est'))}(n {o.get('post0703_n', 0)})")
        L.append("  - 국면: " + " · ".join(f"{k} {_f(v['est'])}(n {v['n']})" for k, v in o.get("regime", {}).items()))
        L.append("  - 월: " + " · ".join(f"{k} {_f(v['est'])}({v['n']})" for k, v in o.get("months", {}).items()))
        for key in ("by_tv_bucket_d", "by_tv_bucket_d1"):
            L.append(f"  - {key}: " + " · ".join(f"{k or '(없음)'} {_f(v['est'])}({v['n']})"
                                                 for k, v in o.get(key, {}).items()))
    return L + [""]


def _ref_lines(info: Dict[str, Any]) -> List[str]:
    L = ["## 참고판(판정에 쓰지 않음)", "",
         "- 모집단 무관(시가 밖 로트 포함 · 수정 1 결정 1 참고) / 공백일 포함판(market_gap_day·open_gap 포함 · A11: "
         "10시 개장일"
         "(2025-11-13·2026-01-02)엔 R5 가 «09:00~09:04 거래 0 → filter», R3 가 전부 skip 이 된다)", "",
         "| 규칙 | 모집단 무관 n | 점추정 | 공백일 포함 n | 점추정 |", "|---|---|---|---|---|"]
    for r in info["ref"]:
        a, b = info["ref"][r], info["incl"][r]
        L.append(f"| {r} | {a['n']:,} | {_f(a['est'])} | {b['n']:,} | {_f(b['est'])} |")
    return L + [""]


def _json_ready(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _json_ready(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_ready(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if o != o else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_window(W: pd.DataFrame, want: str) -> None:
    got = set(W["window"])
    if got != {want}:
        raise SystemExit(f"🔴 창 불일치: 입력 {sorted(got)} ≠ {want}")


MAIN_RULES = SPEC["timing_rules"] + SPEC["filter_rules"]


# ── 단계 ─────────────────────────────────────────────────────────────────
def explore(lots: Path, fakes: Optional[Path], out_dir: Path, B: int,
            prov: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """① E — 부호·f·분산·가짜 보정·MDE 재계산 → `RESULTS_explore.md` + `.json`(다음 단계 입력). 판정 없음."""
    W = wide(read_lots(lots))
    _check_window(W, "E")
    calcs, info = window_calc(W, "E", MAIN_RULES, B)
    fk = fake_rates(W, read_lots(fakes) if fakes else None, B)
    holm_and_ci(calcs, SPEC["m_main"], {"timing": fk["switch_timing"], "filter": fk["switch_filter"]})
    inputs = {"lots_rule.csv": sha256_file(lots), **({"fake_timing.csv": sha256_file(fakes)} if fakes else {})}
    L = _head("RESULTS_explore — 탐색 창 E(2025-04-17~2025-12-31)", inputs, B,
              ["- 이 문서는 판정하지 않는다(§5-1 · 부호·f·분산·가짜 보정만) · 이 파일 sha256 커밋 뒤 C 를 연다(§8)",
               "- 가짜 규칙은 «p<0.05 비율»만 싣는다(개별 가짜 값 없음 · u=10 = H②-hist 와 같아 봉인 · 수정 1 §7 NB1)"],
              prov)
    L += _info_lines(info)
    L += ["## 규칙별(주 가족 · 주 분석)", ""] + _rule_table(calcs, judge=False)
    L += ["## 가짜 규칙 보정(§5-3 · 비율 > 0.075 → 그 분류 판정 p 를 2원 군집 p 로)", "",
          f"- 거르기(종목 상수 노이즈 f=0.2) {fk['n_filter']}개 · p<0.05 비율 {_f(fk['filter_rate'])} · 전환 "
          f"{_f(fk['switch_filter'])}",
          f"- 시점(u ~ 09:02~10:00) {fk['n_timing']}개 · p<0.05 비율 {_f(fk['timing_rate'])} · 전환 "
          f"{_f(fk['switch_timing'])}" + ("" if fk["n_timing"] == SPEC["fake_n"] else
                                         f" 🔴 등록 {SPEC['fake_n']}개와 다름"), ""]
    L += ["## 검정력 재계산(MDE · SE = 이 창 블록 부트스트랩 sd · C 계획 n 960 으로 옮긴 값 병기)", "",
          "| 규칙 | SE | m=1 | m=4 | m=6 | m=10 | m=6 @960 |", "|---|---|---|---|---|---|---|"]
    mdes = {}
    for r, c in calcs.items():
        md = c.mde(SPEC["c_plan_n"])
        mdes[r] = md
        L.append(f"| {r} | {_f(c.out.get('se'))} | {_f(md['m1'])} | {_f(md['m4'])} | {_f(md['m6'])} | "
                 f"{_f(md['m10'])} | {_f(md['m6_at_960'])} |")
    L += [""] + _ref_lines(info)
    md_text = "\n".join(L) + "\n"
    sha = _write(out_dir / "RESULTS_explore.md", md_text)
    js = dict(spec_sha256=SPEC_SHA256, B=B, inputs=inputs, results_md_sha256=sha, fake=fk, prov=prov,
              rules={r: dict(sign=_sign(c.est), est=c.est, f=c.out["f"], se=c.out.get("se")) for r, c in calcs.items()},
              mde=mdes)
    _write(out_dir / "RESULTS_explore.json", json.dumps(_json_ready(js), ensure_ascii=False, indent=1) + "\n")
    return js


def _load_json(p: Path) -> Dict[str, Any]:
    if not Path(p).exists():
        raise SystemExit(f"🔴 앞 단계 결과가 없다(§8 순서) — {p}")
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    if d.get("spec_sha256") != SPEC_SHA256:
        raise SystemExit(f"🔴 SPEC 해시가 다르다 — {p}")
    return d


def confirm(lots: Path, explore_json: Path, out_dir: Path, B: int,
            prov: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """② C — 주 가족 판정(Holm m=6 · §6-A 조건 전부) → `RESULTS_confirm.md` + `.json`."""
    ej = _load_json(explore_json)
    W = wide(read_lots(lots))
    _check_window(W, "C")
    calcs, info = window_calc(W, "C", MAIN_RULES, B)
    sw = {"timing": ej["fake"]["switch_timing"], "filter": ej["fake"]["switch_filter"]}
    holm_and_ci(calcs, SPEC["m_main"], sw)
    inputs = {"lots_rule.csv": sha256_file(lots), "RESULTS_explore.json": sha256_file(explore_json)}
    L = _head("RESULTS_confirm — 확인 창 C(2026-01-01~2026-09-23) · 주 가족 판정", inputs, B,
              [f"- 판정 p 종류(E 가짜 보정): 시점 {'2원 군집' if sw['timing'] else '블록'} · "
               f"거르기 {'2원 군집' if sw['filter'] else '블록 순열'}"], prov)
    L += _info_lines(info) + ["## 규칙별", ""] + _rule_table(calcs, judge=True)
    L += ["## §6-A 조건(모두 참 = 다음 단계 C2 로)", "", "| 규칙 | " + " | ".join(
        ["Holm·구간", "θ", "E 부호", "모델 a·b·c", "순", "IPW", "국면", "한 달 빼기", "상위 10", "f≥0.15", "통과"])
        + " |",
          "|" + "---|" * 12]
    res = {}
    for r, c in calcs.items():
        theta = SPEC["theta_filter"] if c.kind == "filter" else SPEC["theta_timing"]
        cd = criteria(c, theta, ej["rules"][r]["sign"])
        vd = verdict_of(cd)
        ok = vd == "통과"
        res[r] = dict(sign=_sign(c.est), est=c.est, passed=ok, verdict=vd, criteria=cd,
                      current_side=c.out.get("ci_current_side", False) and c.out.get("holm_rejected", False))
        L.append(f"| {r} | " + " | ".join(_f(cd.get(k)) for k in ("holm_ci", "theta", "same_sign_E", "models_abc",
                                                                  "net", "ipw", "regime", "loo_month", "top10",
                                                                  "f_min")) + f" | {vd} |")
    cur = ", ".join(r for r, v in res.items() if v["current_side"]) or "(해당 없음)"
    L += ["", f"- 양측 규칙(R3·R7)이 음의 방향으로 기준을 넘으면 «현행(첫 분 진입) 쪽» 기록만(룰 변경 후보 아님 · "
          f"§4-1): {cur}",
          ""]
    L += _ref_lines(info)
    sha = _write(out_dir / "RESULTS_confirm.md", "\n".join(L) + "\n")
    js = dict(spec_sha256=SPEC_SHA256, B=B, inputs=inputs, results_md_sha256=sha, rules=res, prov=prov)
    _write(out_dir / "RESULTS_confirm.json", json.dumps(_json_ready(js), ensure_ascii=False, indent=1) + "\n")
    return js


def c2(lots: Path, confirm_json: Path, out_dir: Path, B: int,
       prov: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """③ C2 — 쏠림 없는 확인(§6-B): 시점 = 짝 ≥300 ∧ C 와 같은 부호 ∧ 점추정 ≥ θ/2 · 거르기 = 부호 일치만."""
    cj = _load_json(confirm_json)
    W = wide(read_lots(lots))
    _check_window(W, "C2")
    calcs, info = window_calc(W, "C2", MAIN_RULES, B)
    inputs = {"lots_rule.csv": sha256_file(lots), "RESULTS_confirm.json": sha256_file(confirm_json)}
    L = _head("RESULTS_c2 — 10-06~ 스냅샷 창 확인(§6-B)", inputs, B,
              ["- C2 는 그림자 ② 판정 표본과 날짜가 겹친다 → 독립 증거로 세지 않음(§5-1)",
               "- C 를 통과한 규칙만 판정(§6 «앞 단계 미충족이면 다음 없음») · 나머지 = 해당 없음"], prov)
    L += _info_lines(info) + ["## 규칙별", ""] + _rule_table(calcs, judge=False)
    L += ["| 규칙 | C 통과 | n | C 부호 | C2 부호 | 점추정 | 기준 | 판정 |", "|---|---|---|---|---|---|---|---|"]
    res = {}
    for r, c in calcs.items():
        cs = cj["rules"][r]["sign"]
        cv = cj["rules"][r].get("verdict", "통과" if cj["rules"][r]["passed"] else "불통과")
        verdict = c2_verdict(r, c.kind, c.n, c.est, cs, cv)
        rule_txt = "부호 일치만" if c.kind == "filter" else f"짝 ≥{SPEC['c2_min_pairs']} ∧ 같은 부호 ∧ ≥ θ/2"
        res[r] = dict(verdict=verdict, sign=_sign(c.est), est=c.est, n=c.n)
        L.append(f"| {r} | {cv} | {c.n:,} | {cs:+d} | {_sign(c.est):+d} | {_f(c.est)} | {rule_txt} | {verdict} |")
    L += [""] + _ref_lines(info)
    sha = _write(out_dir / "RESULTS_c2.md", "\n".join(L) + "\n")
    js = dict(spec_sha256=SPEC_SHA256, B=B, inputs=inputs, results_md_sha256=sha, rules=res, prov=prov)
    _write(out_dir / "RESULTS_c2.json", json.dumps(_json_ready(js), ensure_ascii=False, indent=1) + "\n")
    return js


def two_cell_lines(path: Path) -> List[str]:
    """§4-1 봉인 대상 — R1·R3·R4·R5 를 «규칙 arm 진입 ≤09:10 / >09:10 / 안 삼» 칸으로 나눈 점추정(주 분석)."""
    W = wide(read_lots(path))
    window = sorted(set(W["window"]))[0]
    calcs, _ = window_calc(W, window, ["R1", "R3", "R4", "R5"], 0, full=False)
    L = [f"### {window} 창 «≤09:10 / >09:10» 두 칸(§4-1 · 09:10 분 진입 = >09:10 · 수정 1 §7 D5)", "",
         "| 규칙 | ≤09:10 | >09:10 | 안 삼 |",
         "|---|---|---|---|"]
    for r, c in calcs.items():
        arm = c.base if c.kind == "filter" else r
        t = c.sub[f"{arm}:entry_time"].to_numpy()
        ent = _true(c.sub[f"{arm}:entered"])
        cell = np.array([cell_of(bool(e), str(x)) for e, x in zip(ent, t)])
        cells = [cell == "le0910", cell == "gt0910", cell == "cash"]
        L.append(f"| {r} | " + " | ".join(f"{_f(v)}(n {n})" for v, n in (c.stat(m) for m in cells)) + " |")
    return L + [""]


def sealed(lots: Path, main_lots: Sequence[Path], explore_json: Path, sealed_dir: Path, out_dir: Path,
           B: int, prov: Optional[Dict[str, Any]] = None) -> str:
    """④ 독립 가족(U · Holm m=2) + 주 가족 두 칸 표 → 봉인 폴더 `sealed_indep.md` · 레포엔 sha256 한 줄만(B1)."""
    ej = _load_json(explore_json)
    W = wide(read_lots(lots))
    _check_window(W, "U")
    rules = SPEC["indep_rules"]
    calcs, info = window_calc(W, "U", rules, B)
    holm_and_ci(calcs, SPEC["m_indep"], {"timing": ej["fake"]["switch_timing"]})
    inputs = {"U/lots_rule.csv": sha256_file(lots), **{f"{p.parent.name}/lots_rule.csv": sha256_file(p)
                                                        for p in main_lots}}
    L = _head("sealed_indep — 독립 가족(H②-hist · H+2%) + 주 가족 두 칸 표", inputs, B,
              [SEALED_BANNER, "- 기준 R0 = 주 가족 E·C 의 R0 와 같은 값(§5-1 겹침 허용 · A12) · 그림자 ② 와 합산 금지"
               "(§4-2)",
               "- 판정 창 = 2025-04-17~2026-05-31(print_only 06-01~09-23 은 인쇄만 · 아래 참고판)"], prov)
    L += _info_lines(info) + ["## 독립 가족(Holm m=2)", ""] + _rule_table(calcs, judge=True)
    L += ["| 규칙 | " + " | ".join(["Holm·구간", "θ", "모델 a·b·c", "순", "IPW", "국면", "한 달 빼기", "상위 10",
                                   "통과"])
          + " |", "|" + "---|" * 10]
    for r, c in calcs.items():
        cd = criteria(c, SPEC["theta_indep"], None)
        L.append(f"| {r} | " + " | ".join(_f(cd[k]) for k in ("holm_ci", "theta", "models_abc", "net", "ipw", "regime",
                                                              "loo_month", "top10")) + f" | {verdict_of(cd)} |")
    mk = masks(W)
    po = W[mk["pop"] & mk["held"] & (W["main_excl"] == "").to_numpy() & ~mk["not_po"]]
    L += ["", "### 인쇄만 — 2026-06-01~09-23(print_only)", ""]
    for r in rules:
        d = _num(po[f"{r}:ret"]) - _num(po["R0:ret"])
        L.append(f"- {r}: n {len(d):,} · δ̄ {_f(float(d.mean()) if len(d) else NAN)}")
    L += [""]
    for p in main_lots:
        L += two_cell_lines(p)
    text = "\n".join(L) + "\n"
    sha = _write(sealed_dir / "sealed_indep.md", text)
    _write(out_dir / "sealed_indep.sha256", f"{sha}  sealed_indep.md\n")
    return sha


def _git_head() -> str:
    from .run import _git_run
    return _git_run("rev-parse", "HEAD").stdout.strip()


def code_digest(hashes: Dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()


def verify_run_output(csv_path: Path, meta_path: Path, window: str, name: str = "lots_rule.csv",
                      code_now: Optional[Dict[str, str]] = None, explore_sha: Optional[str] = None) -> Dict[str, Any]:
    """NB2 ④ — 입력 csv 가 그 창 run_meta 의 산출물인지: 창 · ok · plumbing 아님 · outputs sha256 · 코드 해시 =
    지금 코드 · (C·C2·U) explore.sha256 = 커밋된 RESULTS_explore.md. 반환 = run_meta."""
    if not meta_path.exists() or not csv_path.exists():
        raise SystemExit(f"🔴 NB2: 입력 없음 — {csv_path} · {meta_path}")
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    bad = []
    if m.get("window") != window or m.get("plumbing") or not m.get("ok"):
        bad.append(f"창 {m.get('window')}/{window} · plumbing {m.get('plumbing')} · ok {m.get('ok')}")
    want = (m.get("outputs") or {}).get(name, {}).get("sha256")
    if want != sha256_file(csv_path):
        bad.append(f"{name} sha256 ≠ run_meta outputs")
    if code_now is not None and m.get("code_sha256") != code_now:
        bad.append("run_meta 코드 해시 ≠ 지금 코드")
    if m.get("analysis_spec_sha256") != SPEC_SHA256:
        bad.append("run_meta SPEC 해시 ≠ 지금 SPEC")
    if explore_sha is not None and (m.get("explore") or {}).get("sha256") != explore_sha:
        bad.append("run_meta explore.sha256 ≠ 커밋된 RESULTS_explore.md")
    if bad:
        raise SystemExit(f"🔴 NB2 {window}: " + " · ".join(bad))
    return m


def verify_prior(json_path: Path, md_path: Path, git: Optional[Callable[..., Any]] = None,
                 code_now: Optional[Dict[str, str]] = None,
                 run_meta_expect: Optional[Dict[str, Path]] = None) -> Dict[str, str]:
    """NB2 ③ + G1 — 앞 단계 json·md 가 둘 다 git 추적 ∧ HEAD 와 같음 · json `results_md_sha256` = md sha256 ·
    (code_now 가 있으면) 그 json 이 «출처 관문을 거친» 실행 = `prov` 있음 ∧ B = 등록값 ∧ `prov.code_digest` = 지금 코드
    digest ∧ `prov.run_meta[창]` = 그 창 run_meta sha256(run_meta_expect)."""
    from .run import _git_run, check_committed
    g = git or _git_run
    cm, cj = check_committed(md_path, g), check_committed(json_path, g)
    d = _load_json(json_path)
    if d.get("results_md_sha256") != cm["sha256"]:
        raise SystemExit(f"🔴 NB2: {json_path.name} 의 results_md_sha256 ≠ {md_path.name}")
    if code_now is not None:
        prov = d.get("prov")
        bad = []
        if not prov:
            bad.append("출처 관문 없이 만든 문서(prov 없음)")
        else:
            if prov.get("code_digest") != code_digest(code_now):
                bad.append("앞 단계 코드 digest ≠ 지금 코드(수정 2 필요)")
            for w, mp in (run_meta_expect or {}).items():
                if (prov.get("run_meta") or {}).get(w) != (sha256_file(mp) if Path(mp).exists() else None):
                    bad.append(f"prov.run_meta.{w} ≠ results/{w}/run_meta.json")
        if d.get("B") != SPEC["B"]:
            bad.append(f"B {d.get('B')} ≠ 등록값 {SPEC['B']}")
        if bad:
            raise SystemExit(f"🔴 G1 {json_path.name}: " + " · ".join(bad))
    return {md_path.name: cm["commit"], json_path.name: cj["commit"]}


def main(argv: Optional[Sequence[str]] = None) -> int:
    from . import run as RUN
    ap = argparse.ArgumentParser(description="분석 생성기(사전등록 §5·§6·§8 + 수정 1 · 실자료 관문)")
    ap.add_argument("stage", choices=["explore", "confirm", "c2", "sealed"])
    ap.add_argument("--private-dir", default=None, help="로트 csv 비공개 폴더(run 과 같은 규칙)")
    ap.add_argument("--sealed-dir", default=None)
    ap.add_argument("--i-understand-sealed", action="store_true")
    ap.add_argument("--B", type=int, default=SPEC["B"])
    a = ap.parse_args(argv)
    RUN.require_clean_tree()                                       # NB2 ①
    code_now = RUN.code_hashes()
    out = RESULTS
    priv = RUN.private_dir(a.private_dir)
    meta_of = {w: RESULTS / w / "run_meta.json" for w in ("E", "C", "C2")}
    lots_of = {w: priv / w / "lots_rule.csv" for w in ("E", "C", "C2")}
    prov: Dict[str, Any] = dict(git_sha=_git_head(), code_digest=code_digest(code_now), run_meta={}, prior={})
    expl = (RESULTS / "RESULTS_explore.json", RESULTS / "RESULTS_explore.md")
    conf = (RESULTS / "RESULTS_confirm.json", RESULTS / "RESULTS_confirm.md")
    if a.stage == "explore":
        m = verify_run_output(lots_of["E"], meta_of["E"], "E", code_now=code_now)
        verify_run_output(priv / "E" / "fake_timing.csv", meta_of["E"], "E", "fake_timing.csv", code_now)
        if m.get("fakes") != SPEC["fakes_required"]:
            raise SystemExit(f"🔴 R2: E 가짜 시점 규칙 {m.get('fakes')} ≠ {SPEC['fakes_required']}")
        prov["run_meta"] = {"E": sha256_file(meta_of["E"])}
        got = explore(lots_of["E"], priv / "E" / "fake_timing.csv", out, a.B, prov)
    elif a.stage in ("confirm", "c2"):
        prov["prior"] = verify_prior(*expl, code_now=code_now, run_meta_expect={"E": meta_of["E"]})
        ex_sha = RUN.check_committed(expl[1])["sha256"]
        w = "C" if a.stage == "confirm" else "C2"
        verify_run_output(lots_of[w], meta_of[w], w, code_now=code_now, explore_sha=ex_sha)
        prov["run_meta"] = {w: sha256_file(meta_of[w])}
        if a.stage == "confirm":
            got = confirm(lots_of["C"], expl[0], out, a.B, prov)
        else:
            prov["prior"].update(verify_prior(*conf, code_now=code_now, run_meta_expect={"C": meta_of["C"]}))
            got = c2(lots_of["C2"], conf[0], out, a.B, prov)
    else:
        if not a.i_understand_sealed:
            raise SystemExit("🔴 B1: sealed 는 --i-understand-sealed 가 필요하다")
        sdir = RUN.sealed_dir(a.sealed_dir)
        prov["prior"] = verify_prior(*expl, code_now=code_now, run_meta_expect={"E": meta_of["E"]})
        ex_sha = RUN.check_committed(expl[1])["sha256"]
        verify_run_output(sdir / "U" / "lots_rule.csv", sdir / "U" / "run_meta.json", "U", code_now=code_now,
                          explore_sha=ex_sha)
        mains = [w for w in ("E", "C") if lots_of[w].exists()]
        for w in mains:
            verify_run_output(lots_of[w], meta_of[w], w, code_now=code_now,
                              explore_sha=None if w == "E" else ex_sha)
        prov["run_meta"] = {"U": sha256_file(sdir / "U" / "run_meta.json"),
                            **{w: sha256_file(meta_of[w]) for w in mains}}
        got = sealed(sdir / "U" / "lots_rule.csv", [lots_of[w] for w in mains], expl[0], sdir / "sealed", out,
                     a.B, prov)
        RUN._atomic_write(sdir / "sealed" / RUN.SEAL_README, RUN.SEAL_NOTE)
        print(f"sealed_indep.md sha256 {got}")          # 내용은 출력하지 않는다
        return 0
    print(f"{a.stage} → {out} · 문서 sha256 {got['results_md_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
