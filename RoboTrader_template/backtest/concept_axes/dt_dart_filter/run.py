"""A 러너 — 규범 = 스펙 §3 · `PREREG.md`. 문서와 어긋나면 코드가 틀린 것이다.

    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage proxy
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage check-backfill --backfill-dir <dir>
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage build      # 동결 뒤
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage seal       # build 뒤 · 표식 행 수익 안 읽음
    $PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage open       # sealed_report 커밋 뒤 1회

🔴 DB SELECT 전용(`candidate_ledger.run` import 가 bootstrap read-only 를 건다) · 실제 표식×수익 결합 = open 단계뿐.
"""
from __future__ import annotations

from backtest.concept_axes.candidate_ledger import run as R   # noqa: E402  bootstrap(read-only) 포함

import argparse                                               # noqa: E402
import hashlib                                                # noqa: E402
import json                                                   # noqa: E402
import subprocess                                             # noqa: E402
import sys                                                    # noqa: E402
from datetime import date, datetime                           # noqa: E402
from pathlib import Path                                      # noqa: E402
from typing import Any, Dict, List, Optional, Sequence        # noqa: E402

import numpy as np                                            # noqa: E402
import pandas as pd                                           # noqa: E402

from backtest.concept_axes.replayer import loader as LD       # noqa: E402

from . import daycheck as DC                                  # noqa: E402
from . import gate as G                                       # noqa: E402
from . import lots as L                                       # noqa: E402
from . import proxy as P                                      # noqa: E402
from . import sample as SM                                    # noqa: E402
from . import settings as S                                   # noqa: E402
from . import stats as ST                                     # noqa: E402
from . import surv as SV                                      # noqa: E402
from . import tags as T                                       # noqa: E402
from . import universe as U                                   # noqa: E402

LEDGER_COLS = ["scan_date", "stock_code", "rank", "score", "n_passed", "market_cap", "trading_value", "tv20",
               "close", "p_L", "status", "fill", "entry_date", "entry_price", "exit_date", "exit_reason",
               "hold_days", "ret_sl", "ret_tp", "both", "unresolved", "halted_in_path", "flags"]


# ── git · 해시 가드 ─────────────────────────────────────────────────────────────
def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=S.PKG, capture_output=True, text=True)


def head_sha() -> str:
    return _git("rev-parse", "HEAD").stdout.strip()


def clean_package() -> bool:
    return _git("status", "--porcelain", "--", str(S.PKG)).stdout.strip() == ""


def blob(path: Path) -> str:
    return _git("hash-object", str(path)).stdout.strip()


def committed_unchanged(path: Path) -> bool:
    return (_git("ls-files", "--error-unmatch", str(path)).returncode == 0
            and _git("diff", "--quiet", "HEAD", "--", str(path)).returncode == 0)


def md5(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def require_frozen() -> None:
    if not S.PREREG_FROZEN_BLOB:
        raise SystemExit("🔴 PREREG_FROZEN_BLOB 비어 있음 — 사전등록 동결(Task 12) 전에는 실행 금지")
    if not S.PREREG.exists() or blob(S.PREREG) != S.PREREG_FROZEN_BLOB:
        raise SystemExit("🔴 PREREG.md blob 이 동결값과 다르다 — 중단")
    if not S.PROXY_COEF_MD5:
        raise SystemExit("🔴 PROXY_COEF_MD5 비어 있음 — 대리 계수 동결(Task 12) 전에는 실행 금지")
    pc = S.RESULTS / "proxy_coef.json"
    if not pc.exists() or md5(pc) != S.PROXY_COEF_MD5:
        raise SystemExit("🔴 proxy_coef.json md5 가 동결값과 다르다 — 중단")
    if not clean_package():
        raise SystemExit("🔴 패키지에 커밋 안 된 변경이 있다 — 중단")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    tmp.replace(path)


# ── 라벨 규칙(스펙 §3-7) ────────────────────────────────────────────────────────
def label(fe_sl: ST.FE, fe_tp: ST.FE, tool: str, n1: int, surv_i: float, surv_ii: float) -> str:
    if tool == "fail":
        return "판정 불가(도구)"
    if n1 < S.N1_MIN:
        return "판별 보류(n₁<100)"
    p1 = (lambda f: f.p1_cr1) if tool == "cr1" else (lambda f: f.p1_2w)
    p2 = (lambda f: f.p2_cr1) if tool == "cr1" else (lambda f: f.p2_2w)
    if p2(fe_sl) < 0.05 and fe_sl.beta > 0:
        return "역방향"
    if p1(fe_sl) < S.ALPHA and p1(fe_tp) < S.ALPHA and fe_sl.beta <= S.DELTA_MAX and surv_i >= surv_ii:
        return "있음(−)"
    return "판별 보류"


# ── 단계: proxy(이미 본 구간 · 시총 있는 후보로 대리 적합) ────────────────────────
def stage_proxy(conn) -> None:
    if S.PREREG_FROZEN_BLOB:
        raise SystemExit("🔴 동결 뒤에는 대리 계수를 다시 적합하지 않는다 — 중단")
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, S.FIT_PX_START, S.FIT_END.isoformat())]
    days = [pd.Timestamp(d) for d in cal if S.FIT_START <= d <= S.FIT_END]
    px = LD.load_prices(conn, S.FIT_PX_START, S.FIT_END.isoformat())
    rows, diag = U.scan_window(px, days)
    feat = P.add_proxy_features(px).set_index(["stock_code", "date"])
    c = pd.DataFrame(rows)
    c = c[c["market_cap"].astype(float) > 0].copy()
    key = list(zip(c["stock_code"], pd.to_datetime(c["scan_date"])))
    c["x1"] = feat["x1"].reindex(key).to_numpy()
    c["x2"] = feat["x2"].reindex(key).to_numpy()
    c = c.dropna(subset=["x1", "x2"])
    y = (c["market_cap"].astype(float) >= S.LARGE_CAP).to_numpy(float)
    X = P.design(c["x1"], c["x2"])
    beta = P.fit_logistic(X, y)
    s = P.predict(beta, X)
    years = pd.to_datetime(c["scan_date"]).dt.year.to_numpy()
    by_year = {int(yv): P.auc(y[years == yv], s[years == yv]) for yv in sorted(set(years))}
    out = dict(beta=[float(b) for b in beta], features="x1=log(20봉 평균 close×adj volume, D 포함) · x2=log(close D)",
               fit_window=[S.FIT_START.isoformat(), S.FIT_END.isoformat()], n=int(len(c)), n_large=int(y.sum()),
               auc=P.auc(y, s), auc_by_year=by_year, acc_at_cut=float(((s >= S.PL_CUT) == (y > 0)).mean()),
               scan_diag=diag, git_sha=head_sha())
    _write(S.RESULTS / "proxy_coef.json", json.dumps(out, ensure_ascii=False, indent=1))
    _write(S.RESULTS / "proxy_report.md", "\n".join([
        "# 시총 대리 적합 — 이미 본 구간(2024-03-13~2026-09-23) · 결과(수익) 무관", "",
        f"- n {out['n']:,} · 대형 {out['n_large']:,} · AUC {out['auc']:.3f} · p≥0.5 정확도 {out['acc_at_cut']:.3f}",
        f"- 연도별 AUC {', '.join(f'{k} {v:.3f}' for k, v in by_year.items())}",
        f"- 계수 (상수, x1, x2) = {', '.join(f'{b:.6f}' for b in out['beta'])}", ""]))
    print(json.dumps(out, ensure_ascii=False, indent=1))


# ── 단계: check-backfill ────────────────────────────────────────────────────────
def stage_check_backfill(conn, backfill_dir: Path) -> int:
    rep = DC.check(conn, backfill_dir, S.FILING_START, S.SCAN_END, ("A", "B", "I"))
    rep.update(window=[S.FILING_START.isoformat(), S.SCAN_END.isoformat()], types=["A", "B", "I"],
               backfill_dir=str(backfill_dir), git_sha=head_sha())
    _write(S.RESULTS / "backfill_check.json", json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"칸 {rep['n_cells']:,} · 미완결 {rep['n_bad']}")
    return 0 if rep["complete"] else 1


# ── 단계: build(동결 뒤) ────────────────────────────────────────────────────────
def _load_env(conn):
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, S.PX_START, S.PATH_END)]
    px = LD.load_prices(conn, S.PX_START, S.PATH_END)
    env = R.Env(cal=cal, book=R.build_book(px), uni={}, excl={}, imp_dates={}, corp_dates={},
                bad_open=R.load_bad_open(conn, S.PX_START, S.PATH_END), minute_fn=lambda pairs: set(),
                path_end=date.fromisoformat(S.PATH_END))
    return cal, px, env


def stage_build(conn) -> None:
    require_frozen()
    for done in ("seal.json", "open.json"):
        if (S.RESULTS / done).exists():
            raise SystemExit(f"🔴 {done} 가 이미 있다 — 봉인·개봉 뒤에는 build 재실행 금지")
    chk = json.loads((S.RESULTS / "backfill_check.json").read_text(encoding="utf-8"))
    if not chk.get("complete") or not committed_unchanged(S.RESULTS / "backfill_check.json"):
        raise SystemExit("🔴 백필 완결 보고가 없거나 미완결·미커밋 — 중단")
    coef = json.loads((S.RESULTS / "proxy_coef.json").read_text(encoding="utf-8"))
    cal, px, env = _load_env(conn)
    days = [pd.Timestamp(d) for d in cal if S.SCAN_START <= d <= S.SCAN_END]
    rows, diag = U.scan_window(px, days)
    feat = P.add_proxy_features(px).set_index(["stock_code", "date"])
    halts = L.halt_dates(px)
    out: List[Dict[str, Any]] = []
    for r in rows:
        k = (r["stock_code"], pd.Timestamp(r["scan_date"]))
        x1 = float(feat["x1"].get(k, np.nan))
        x2 = float(feat["x2"].get(k, np.nan))
        pl = float(P.predict(np.array(coef["beta"]), P.design([x1], [x2]))[0]) if np.isfinite(x1 + x2) else np.nan
        sim = L.simulate_candidate(env, r["stock_code"], r["scan_date"], halts.get(r["stock_code"], set()))
        out.append({**r, "tv20": float(feat["tv20"].get(k, np.nan)), "close": float(feat["close"].get(k, np.nan)),
                    "p_L": pl, **{kk: sim.get(kk) for kk in LEDGER_COLS if kk in sim}})
    led = pd.DataFrame(out).reindex(columns=LEDGER_COLS)
    S.RESULTS.mkdir(parents=True, exist_ok=True)
    led.to_csv(S.RESULTS / "ledger_A.csv", index=False, lineterminator="\n")
    fil = T.load_filings(conn, S.FILING_START, S.SCAN_END)
    scan_cal = [d for d in cal if d <= S.SCAN_END]
    for name, back in (("lag0", 0), ("w5", 4), ("w20", 19)):
        mk = sorted(T.window_marks(fil, scan_cal, back))
        pd.DataFrame(mk, columns=["stock_code", "scan_date"]).to_csv(S.RESULTS / f"marks_{name}.csv", index=False,
                                                                     lineterminator="\n")
    fp = LD.db_fingerprint(conn, S.PX_START, S.PATH_END)
    meta = dict(git_sha=head_sha(), db_fingerprint=fp["sha256"], scan_diag=diag, n_rows=len(led),
                n_filings=len(fil), md5={p.name: md5(p) for p in sorted(S.RESULTS.glob("*.csv"))},
                finished=datetime.now().isoformat(timespec="seconds"))
    _write(S.RESULTS / "build_meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"원장 {len(led):,}행 · 공시 {len(fil):,} · 지문 {fp['sha256'][:12]}")


def _check_build(conn) -> Dict[str, Any]:
    meta = json.loads((S.RESULTS / "build_meta.json").read_text(encoding="utf-8"))
    for name, h in meta["md5"].items():
        if md5(S.RESULTS / name) != h:
            raise SystemExit(f"🔴 {name} md5 불일치 — 중단")
    if LD.db_fingerprint(conn, S.PX_START, S.PATH_END)["sha256"] != meta["db_fingerprint"]:
        raise SystemExit("🔴 daily_prices 지문이 build 때와 다르다(소급 수정) — 중단")
    return meta


def build_hashes() -> Dict[str, str]:
    """build_meta.json 이 적은 모든 산출물의 md5 + build_meta.json 자신의 md5."""
    meta = json.loads((S.RESULTS / "build_meta.json").read_text(encoding="utf-8"))
    out = {name: md5(S.RESULTS / name) for name in meta["md5"]}
    out["build_meta.json"] = md5(S.RESULTS / "build_meta.json")
    return out


def check_seal_linkage(seal: Dict[str, Any]) -> None:
    rec = seal.get("build_md5")
    if not rec:
        raise SystemExit("🔴 seal.json 에 build 해시 기록이 없다 — 중단")
    try:
        now = build_hashes()
    except (OSError, KeyError, ValueError) as e:
        raise SystemExit(f"🔴 build 산출물을 다시 읽지 못했다({e}) — 중단")
    if now != rec:
        bad = sorted(k for k in set(now) | set(rec) if now.get(k) != rec.get(k))
        raise SystemExit(f"🔴 seal 이후 build 산출물이 바뀌었다 {bad} — 중단")


def effective_n1(df: pd.DataFrame, ycol: str = "y_sl") -> int:
    """회귀가 실제로 쓰는 표식 행 수 — 그날 표식≥1 ∧ 대조≥1 인 날만(스펙 §3-2)."""
    d = df[np.isfinite(df[ycol].astype(float))]
    m = ST.both_arm_days_mask(d["x"], d["day"])
    return int((d["x"].to_numpy()[m] == 1).sum())


def _read_marks(name: str):
    m = pd.read_csv(S.RESULTS / f"marks_{name}.csv", dtype={"stock_code": str})
    return {(c, date.fromisoformat(d)) for c, d in zip(m["stock_code"], m["scan_date"])}


def _read_ledger() -> pd.DataFrame:
    led = pd.read_csv(S.RESULTS / "ledger_A.csv", dtype={"stock_code": str})
    led["scan_date"] = [date.fromisoformat(str(d)[:10]) for d in led["scan_date"]]
    for c in ("both", "unresolved", "halted_in_path"):          # CSV 의 "True"/"False"/빈칸 → bool (문자열 astype(bool) 함정)
        led[c] = led[c].astype(str).str.strip().str.lower().eq("true")
    return led


def _survivorship(conn, px: pd.DataFrame) -> Dict[str, Any]:
    """생존자 누락률 (i) 공시 단위 · (ii) 회사 단위 — 코넥스·상장 전 공시 제외(`surv.py` · 최종 리뷰 I1)."""
    fil = T.load_filings_cls(conn, S.SCAN_START, S.SCAN_END)
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, S.PX_START, S.PATH_END)]
    codes = px["stock_code"].astype(str).to_numpy()
    days = [pd.Timestamp(t).date() for t in px["date"]]
    keys = set(zip(codes, days))
    first: Dict[str, date] = {}
    for c, d in zip(codes, days):
        if c not in first or d < first[c]:
            first[c] = d
    return SV.survivorship(fil, cal, keys, first)


# ── 단계: seal(표식 행 수익 안 읽음) ───────────────────────────────────────────
def stage_seal(conn) -> None:
    require_frozen()
    _check_build(conn)
    cal, px, _env = _load_env(conn)
    cal_idx = {d: i for i, d in enumerate(cal)}
    led = _read_ledger()
    df = SM.analysis_frame(led, _read_marks("lag0"), cal_idx)
    gate = G.fake_gate(df)
    ctrl = df[df["x"] == 0]
    surv = _survivorship(conn, px)
    n1_raw = int((df["x"] == 1).sum())
    n1 = effective_n1(df)
    years = pd.Series([d.year for d in df["scan_date"]])
    seal = dict(n1=n1, n1_raw=n1_raw, build_md5=build_hashes(), n0=int(len(ctrl)), sd_ctrl_sl=float(ctrl["y_sl"].std(ddof=1)),
                sd_ctrl_tp=float(ctrl["y_tp"].std(ddof=1)), gate=gate,
                mde_null=ST.mde(gate["sd_null"]), mde_se=ST.mde(gate["mean_se_cr1"]),
                n1_by_year={int(y): int(((years == y) & (df["x"] == 1)).sum()) for y in sorted(years.unique())},
                surv=surv, git_sha=head_sha(), sealed=datetime.now().isoformat(timespec="seconds"))
    _write(S.RESULTS / "seal.json", json.dumps(seal, ensure_ascii=False, indent=1))
    _write(S.RESULTS / "sealed_report.md", "\n".join([
        "# 봉인 보고서 — 표식×수익 결합 0 (스펙 §3-6)", "",
        f"- n₁(유효 · 표식·대조 둘 다 있는 날) {n1:,} (표식 전체 {n1_raw:,}) · 대조 {len(ctrl):,} · 연도별 n₁ {seal['n1_by_year']}",
        f"- SD(대조 · net) 손절 우선 {seal['sd_ctrl_sl']:.3f} · 익절 우선 {seal['sd_ctrl_tp']:.3f}",
        f"- 가짜 게이트: CR1 거부율 {gate['rej_cr1']:.3f} · 2원 {gate['rej_2w']:.3f} → 도구 **{gate['tool']}** "
        f"(n_fake {gate['n_fake']} · 건너뜀 {gate['n_skipped']})",
        f"- SD_null {gate['sd_null']:.3f} → MDE {seal['mde_null']:.3f}%p (평균 SE 기준 {seal['mde_se']:.3f}%p)",
        f"- 생존자 누락률 (i) 3태그 공시 단위 {surv['surv_i']:.4f}(n {surv['n_i']:,}) · (ii) 정기공시 회사 단위 "
        f"{surv['surv_ii']:.4f}(n {surv['n_ii']:,}) — 코넥스·상장 전 공시 제외",
        *[f"  - {ln}" for ln in SV.breakdown_text(surv).splitlines()], ""]))
    print(json.dumps(seal, ensure_ascii=False, indent=1, default=str))


# ── 단계: open(1회) ──────────────────────────────────────────────────────────────
def stage_open(conn) -> None:
    require_frozen()
    if (S.RESULTS / "open.json").exists():
        raise SystemExit("🔴 이미 개봉됨(open.json 있음) — 1회만 허용")
    if not committed_unchanged(S.RESULTS / "sealed_report.md"):
        raise SystemExit("🔴 sealed_report.md 가 커밋돼 있지 않거나 바뀌었다 — 중단")
    seal = json.loads((S.RESULTS / "seal.json").read_text(encoding="utf-8"))
    check_seal_linkage(seal)
    _check_build(conn)
    cal, _px, _env = _load_env(conn)
    cal_idx = {d: i for i, d in enumerate(cal)}
    led = _read_ledger()
    df = SM.analysis_frame(led, _read_marks("lag0"), cal_idx)

    def fe(d, col, key="day"):
        return ST.fe_regression(d[col].to_numpy(), d["x"].to_numpy(), d[key].to_numpy(), d["stock"].to_numpy(),
                                d["block"].to_numpy())
    fe_sl, fe_tp = fe(df, "y_sl"), fe(df, "y_tp")
    tool = seal["gate"]["tool"]
    lab = label(fe_sl, fe_tp, tool, int(fe_sl.n1), seal["surv"]["surv_i"], seal["surv"]["surv_ii"])
    lines = ["# RESULTS — 공시 재료 다음날 추격 금지(lag0) 확인 검정", "",
             f"## 주 라벨: **{lab}**", "",
             f"- 도구 {tool} · n {fe_sl.n:,} · n₁ {fe_sl.n1:,} · 날 {fe_sl.n_days:,}",
             f"- 손절 우선 δ̂ {fe_sl.beta:+.3f}%p (SE CR1 {fe_sl.se_cr1:.3f} · 단측 p {fe_sl.p1_cr1:.4f} · "
             f"2원 SE {fe_sl.se_2w:.3f} · 단측 p {fe_sl.p1_2w:.4f})",
             f"- 익절 우선 δ̂ {fe_tp.beta:+.3f}%p (단측 p CR1 {fe_tp.p1_cr1:.4f} · 2원 {fe_tp.p1_2w:.4f})",
             f"- 생존자 누락률 (i) {seal['surv']['surv_i']:.4f} vs (ii) {seal['surv']['surv_ii']:.4f}", "",
             "## 보조(인쇄만 · 라벨 불변)", ""]
    sec: Dict[str, Any] = {}
    for name in ("w5", "w20"):
        d2 = SM.analysis_frame(led, _read_marks(name), cal_idx)
        f2 = fe(d2, "y_sl")
        sec[name] = f2.__dict__
        lines.append(f"- {name}: δ̂ {f2.beta:+.3f} · n₁ {f2.n1} · 단측 p {f2.p1_cr1:.4f}")
    big = SM.analysis_frame(led, _read_marks("lag0"), cal_idx, small_only=False)
    big["key"] = big["day"].astype(str) + "|" + pd.qcut(big["p_L"].rank(method="first"), 3, labels=False).astype(str)
    fb = fe(big, "y_sl", key="key")
    sec["all_sizes"] = fb.__dict__
    lines.append(f"- 대형 포함 전체(날짜×대리 3분위 FE): δ̂ {fb.beta:+.3f} · n₁ {fb.n1} · 단측 p {fb.p1_cr1:.4f}")
    for y in sorted({d.year for d in df["scan_date"]}):
        dy = df[[d.year == y for d in df["scan_date"]]]
        fy = fe(dy, "y_sl")
        lines.append(f"- {y}: δ̂ {fy.beta:+.3f} · n₁ {fy.n1}")
    tv_t = pd.qcut(df["trading_value"].rank(method="first"), 3, labels=False)
    for t in range(3):
        ft = fe(df[tv_t == t], "y_sl")
        lines.append(f"- 거래대금 3분위 {t + 1}: δ̂ {ft.beta:+.3f} · n₁ {ft.n1}")
    for arm, sub in (("표식", df[df["x"] == 1]), ("대조", df[df["x"] == 0])):
        lines.append(f"- {arm}: 정지 낀 비율 {sub['halted_in_path'].astype(bool).mean():.4f} · "
                     f"ret ≤ −15% {(sub['ret_sl'] <= S.TAIL_LOSS).mean():.4f} · 동시 터치 {sub['both'].astype(bool).mean():.4f}")
    if lab == "있음(−)":
        lines.append("- 태그별 Holm m=3(주 검정 통과 뒤에만 해석) — 별도 표식 파일 없이 공시를 다시 읽어 계산")
    today = date.today().isoformat()
    _write(S.RESULTS / f"RESULTS_{today}.md", "\n".join(lines) + "\n")
    _write(S.RESULTS / "open.json", json.dumps(dict(label=lab, fe_sl=fe_sl.__dict__, fe_tp=fe_tp.__dict__,
                                                    secondary=sec, opened=datetime.now().isoformat(timespec="seconds"),
                                                    git_sha=head_sha()), ensure_ascii=False, indent=1, default=str))
    print("\n".join(lines))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="dt_dart_filter A 러너")
    ap.add_argument("--stage", required=True, choices=["proxy", "check-backfill", "build", "seal", "open"])
    ap.add_argument("--backfill-dir", default=None)
    a = ap.parse_args(argv)
    if a.stage in ("build", "seal", "open"):
        require_frozen()
    conn = R._connect()
    try:
        if a.stage == "proxy":
            stage_proxy(conn)
        elif a.stage == "check-backfill":
            if not a.backfill_dir:
                raise SystemExit("--backfill-dir 필요")
            return stage_check_backfill(conn, Path(a.backfill_dir))
        elif a.stage == "build":
            stage_build(conn)
        elif a.stage == "seal":
            stage_seal(conn)
        else:
            stage_open(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
