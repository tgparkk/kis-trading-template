"""판정(스펙 §5-6) — 🔒 동결 가드 통과 시에만 실행(Task 13 · 10-17 동결 뒤).

가드: PREREG.md 의 git blob = PREREG_FROZEN_BLOB(비어 있으면 거부) ∧ N_CUT 설정 ∧ PREREG 의 N_cut = N_CUT ∧
arena.csv·signals.csv·calib.json md5 = PREREG.md 에 적힌 값. 이어서 theme_rank 미커밋 변경 0 · calib.arena_md5 ·
ledger md5 · DB 재계산 S = 고정 S 를 확인한다. 실제 S 와 결과를 처음 합치는 곳이 여기다.

    python -X utf8 -m backtest.concept_axes.theme_rank.run
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import json                                                            # noqa: E402
import math                                                            # noqa: E402
import re                                                              # noqa: E402
import subprocess                                                      # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Callable, Dict, List, Optional                      # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.theme_rank import bandfill as BF            # noqa: E402
from backtest.concept_axes.theme_rank import build_arena as BA         # noqa: E402
from backtest.concept_axes.theme_rank import calibrate as CA           # noqa: E402
from backtest.concept_axes.theme_rank import slots as SL               # noqa: E402
from backtest.concept_axes.theme_rank import stats as ST               # noqa: E402

N_CUT: Optional[int] = None          # 🔒 Task 13 동결 때 PREREG 값으로 설정
PREREG_FROZEN_BLOB = ""              # 🔒 Task 13 동결본 PREREG.md(작업 트리 파일)의 `git hash-object` 값
ALPHA, EPS = 0.05, 0.5
S_TOL = 1e-12                        # DB 재계산 S 와 고정 signals.csv S 의 허용 차(R13)
LAG_ROBUST = 22
N_PLACEBO = 200
SEED = 20261017
WIN_E = ("2024-03-13", "2025-06-30")
WIN_C = ("2025-07-01", "2026-09-23")
HERE = Path(__file__).resolve().parent
PREREG = HERE / "PREREG.md"
FILES = {"arena.csv": BA.OUT / "arena.csv", "signals.csv": BA.OUT / "signals.csv",
         "calib.json": CA.OUT / "calib.json"}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=HERE.parents[3])


def prereg_blob() -> str:
    """작업 트리 PREREG.md 의 `git hash-object`(읽는 파일 = 해시하는 파일)."""
    r = _git("hash-object", str(PREREG))
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit("git hash-object 실패 — 중단")
    return r.stdout.strip()


def head_if_clean() -> str:
    """theme_rank 아래 커밋 안 된 변경(코드·데이터)이 있으면 거부 — 깨끗하면 HEAD sha."""
    st = _git("status", "--porcelain", "--", str(HERE))
    if st.returncode != 0 or st.stdout.strip():
        raise SystemExit("theme_rank 에 커밋 안 된 변경이 있다(git status --porcelain) — 중단")
    head = _git("rev-parse", "HEAD")
    if head.returncode != 0 or not head.stdout.strip():
        raise SystemExit("git rev-parse HEAD 실패 — 중단")
    return head.stdout.strip()


def read_frozen_md5(text: str) -> Dict[str, str]:
    return {m.group(1): m.group(2)
            for m in re.finditer(r"^- (arena\.csv|signals\.csv|calib\.json) md5: ([0-9a-f]{32})$", text, re.M)}


def guard(blob_of: Callable[[], str], prereg_text: str, md5_of: Callable[[str], Optional[str]]) -> None:
    if not PREREG_FROZEN_BLOB or N_CUT is None:
        raise SystemExit("🔒 동결 전 — PREREG_FROZEN_BLOB·N_CUT 미설정. run.py 는 Task 13 에서만 돈다.")
    m = re.search(r"N_cut = (\d+)", prereg_text)
    if m is None or int(m.group(1)) != N_CUT:
        raise SystemExit(f"PREREG 의 N_cut({m.group(1) if m else '없음'}) ≠ run.py N_CUT({N_CUT}) — 중단")
    if blob_of() != PREREG_FROZEN_BLOB:
        raise SystemExit("PREREG.md 가 동결본과 다르다 — 중단")
    want = read_frozen_md5(prereg_text)
    for name in FILES:
        if name not in want or md5_of(name) != want[name]:
            raise SystemExit(f"{name} md5 가 PREREG 와 다르다 — 중단")


def verdict(p: float, mean_ic: float, mean_e: float, mean_c: float, d_theme: float, ic_minus_bias: float) -> str:
    if not all(math.isfinite(x) for x in (p, mean_ic, mean_e, mean_c)):
        return "FAIL"                                                   # NaN 은 닫힌 쪽(FAIL)으로
    if not (p < ALPHA) or mean_e * mean_c <= 0 or mean_e * mean_ic <= 0:
        return "FAIL"
    if mean_ic > 0:
        if not (math.isfinite(d_theme) and math.isfinite(ic_minus_bias)):
            return "FAIL"
        return "PASS" if (d_theme >= EPS and ic_minus_bias > 0) else "FAIL"
    return "NEG"


def _window(ic: pd.Series, win) -> float:
    idx = pd.Index(ic.index.astype(str))
    return float(ic[(idx >= win[0]) & (idx <= win[1])].mean())


def main() -> int:
    from backtest.concept_axes.candidate_ledger import run as CL
    from backtest.concept_axes.theme_rank import build_signals as BS
    from backtest.concept_axes.theme_rank import membership as MB
    from backtest.concept_axes.theme_rank import snapshot as SN
    text = PREREG.read_text(encoding="utf-8") if PREREG.exists() else ""        # 없어도 가드가 먼저 막는다
    guard(prereg_blob, text, lambda n: BA.md5(FILES[n]) if FILES[n].exists() else None)
    head = head_if_clean()                                              # 입력을 읽기 전에(RESULTS.md 는 뒤에 쓴다)
    calib = json.loads(FILES["calib.json"].read_text(encoding="utf-8"))
    meta_path = BA.OUT / "signals_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if calib.get("n_cut") != N_CUT or meta.get("n_cut") != N_CUT:
        raise SystemExit("N_cut 불일치(run.py · calib.json · signals_meta.json) — 중단")
    if calib.get("arena_md5") != BA.md5(FILES["arena.csv"]):
        raise SystemExit("calib.json 의 arena_md5 ≠ arena.csv md5 — 중단")
    if BA.md5(BA.LEDGER_CSV) != BA.LEDGER_MD5:
        raise SystemExit("ledger.csv md5 불일치(거래일 달력) — 중단")

    arena = BF.filled(pd.read_csv(FILES["arena.csv"], dtype={"stock_code": str, "scan_date": str}))
    sig = pd.read_csv(FILES["signals.csv"], dtype={"stock_code": str, "scan_date": str})
    df = arena.merge(sig, on=["scan_date", "stock_code"], how="left", validate="one_to_one")
    df["s"] = pd.to_numeric(df["s"], errors="coerce")
    if df["s"].isna().any():
        raise SystemExit("S 결측 행이 있다 — 중단")

    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE, MB.SNAP_RUN_ID)
    states, _, _, _ = BS.load_day_states(conn)
    conn.close()
    members = MB.restrict(snap.members, MB.eligible_themes(snap.theme_name, N_CUT))
    keys = [(pd.Timestamp(d).date(), c) for d, c in zip(df["scan_date"], df["stock_code"])]
    s_now = np.asarray(BS.primary_s(keys, states, SN.invert(members), members), dtype=float)
    gap = np.abs(s_now - df["s"].to_numpy(dtype=float))                 # 플라시보 입력 = 고정 S 의 입력(R13)
    if gap.size == 0 or not np.isfinite(gap).all() or gap.max() > S_TOL:
        raise SystemExit("DB 상태가 동결 신호와 다르다 — 중단")

    ic, skipped = ST.daily_ic(df, "s", "ret_net")
    h = ST.hac_t(ic, int(calib["lag"]))
    h22 = ST.hac_t(ic, LAG_ROBUST)
    p = CA.calibrated_p(h["t_hac"], calib)
    mean_e, mean_c = _window(ic, WIN_E), _window(ic, WIN_C)

    rng = np.random.default_rng(SEED)
    pl: List[float] = []
    for _ in range(N_PLACEBO):
        sh = ST.degree_preserving_shuffle(members, rng)
        s_pl = BS.primary_s(keys, states, SN.invert(sh), sh)
        pic, _ = ST.daily_ic(df.assign(_pl=s_pl), "_pl", "ret_net")
        pl.append(float(pic.mean()))
    bias = float(np.mean(pl))

    cal = sorted(pd.read_csv(BA.LEDGER_CSV, usecols=["scan_date"], dtype={"scan_date": str})["scan_date"].unique())
    lots = SL.lots_from(df, cal)
    buys, held = SL.baseline_path(lots, len(cal))
    eco = SL.summarize(SL.paired(lots, buys, held))
    eco2 = SL.summarize(SL.paired(lots, buys, held, cap_per_theme=2))
    v = verdict(p, h["mean_ic"], mean_e, mean_c, eco["d_theme"], h["mean_ic"] - bias)
    p22 = CA.calibrated_p(h22["t_hac"], calib, LAG_ROBUST)
    v22 = verdict(p22, h22["mean_ic"], mean_e, mean_c, eco["d_theme"], h22["mean_ic"] - bias)
    sz = df.groupby("scan_date").size()

    extra = []
    for col in ["s_full", "a_mean_excess", "c_same_theme", "b_rank_in_theme", "b_limit_up", "a2_streak"]:
        x = pd.to_numeric(df[col].replace({"True": 1, "False": 0}), errors="coerce")
        if col == "b_rank_in_theme":
            x = -x                                                      # 순위 1 = 최고 → 부호 맞춤
        eic, _ = ST.daily_ic(df.assign(_x=x), "_x", "ret_net")
        eh = ST.hac_t(eic, int(calib["lag"]))
        extra.append(f"| {col} | {eh['mean_ic']:+.4f} | {eh['t_hac']:+.2f} | {eh['n_days']} |")
    epi = ST.episode_first(df.assign(scan_date=pd.to_datetime(df["scan_date"]).dt.date),
                           {pd.Timestamp(d).date(): i for i, d in enumerate(cal)})
    eic, _ = ST.daily_ic(epi, "s", "ret_net")
    mde = (1.959963984540054 + 0.8416212335729143) * h["se_hac"]
    lines = [
        "# 판정 결과 — 테마 순위 층(daytrading)", "", f"- 코드 HEAD {head} · dirty=no", "",
        f"## 판정: **{v}**", "",
        f"- 1차 IC 평균 {h['mean_ic']:+.4f} · HAC t(lag {calib['lag']}) {h['t_hac']:+.2f} · 교정 p {p:.4f}"
        f"({calib['mode']})",
        f"- lag 22 판정 {v22}(교정 p {p22:.4f}) · 1차 판정과 {'일치' if v22 == v else '불일치'}",
        f"- 유효일 {h['n_days']} · 제외일 {skipped} · 창 E {mean_e:+.4f} · 창 C {mean_c:+.4f}",
        f"- 플라시보 평균 편향 b {bias:+.4f}({N_PLACEBO}회) · IC − b {h['mean_ic'] - bias:+.4f}",
        f"- 돈: R_base {eco['R_base']:+.3f} · R_arena {eco['R_arena']:+.3f} · R_theme {eco['R_theme']:+.3f} %p · "
        f"Δ_cur {eco['d_cur']:+.3f} · **Δ_theme {eco['d_theme']:+.3f}** · 날 {eco['n_days']} · 로트 {eco['n_lots']}",
        f"- 같은 테마 최대 2개 변형: R_base {eco2['R_base']:+.3f} · R_arena {eco2['R_arena']:+.3f} · "
        f"R_theme {eco2['R_theme']:+.3f} %p · Δ_cur {eco2['d_cur']:+.3f} · **Δ_theme {eco2['d_theme']:+.3f}** · "
        f"날 {eco2['n_days']} · 로트 {eco2['n_lots']} · 3종목 이상 날 비율(무제한) {eco['share_same_theme3']:.3f}",
        f"- 경기장 체결 크기(일별) 중앙 {sz.median():.1f} · 최소 {sz.min()} · 최대 {sz.max()} · {sz.size}일",
        f"- MDE(80%·양측 5%) ≈ {mde:.4f} · 에피소드 첫 행 IC {eic.mean():+.4f}({eic.size}일)",
        f"- S=0 비율 {(df['s'] == 0).mean():.3f} · 경기장 체결 행 {len(df):,}", "",
        "## 인쇄 항목(판정 불변)", "", "| 항목 | IC 평균 | HAC t | 일수 |", "|---|---|---|---|", *extra, "",
        "🔴 기각 전용 — 통과해도 소속표 미래 참조·생존 편향 때문에 상한이다(스펙 §5-7)."]
    BA.write_lf(BA.OUT / "RESULTS.md", "\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
