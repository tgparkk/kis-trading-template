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
import re                                                     # noqa: E402
import subprocess                                             # noqa: E402
import sys                                                    # noqa: E402
from datetime import date, datetime                           # noqa: E402
from pathlib import Path                                      # noqa: E402
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple   # noqa: E402

import numpy as np                                            # noqa: E402
import pandas as pd                                           # noqa: E402

from backtest.concept_axes.replayer import loader as LD       # noqa: E402

from . import daycheck as DC                                  # noqa: E402
from . import frozen_consts as FC                             # noqa: E402
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
               "hold_days", "ret_sl", "ret_tp", "both", "unresolved", "halted_in_path", "flags", "ca_path"]
# 태그별 lag0 표식 파일(critic B1) — marks_<이름>.csv · 순서 = S.TAGS_LAG0(유상증자 → 최대주주변경 → 소송·횡령)
TAG_MARKS = tuple(f"lag0_t{i + 1}" for i in range(len(S.TAGS_LAG0)))


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


def repo_root() -> Path:
    return Path(_git("rev-parse", "--show-toplevel").stdout.strip())


# ── 코드 고정(pins 블록 · 최종 리뷰 I4) ─────────────────────────────────────────
# PREREG.md 안에 정확히 1개:
#     ```pins
#     # 주석·빈 줄 허용
#     <레포 루트 기준 POSIX 경로> <git blob sha1 40자 소문자 hex>
#     ```
# blob = `git hash-object <파일>`(= `git ls-files -s` · `git rev-parse HEAD:<경로>` 와 같은 값). 고정 대상 = required_pins().
PIN_FENCE = "```pins"
_PKG_REL = "RoboTrader_template/backtest/concept_axes/dt_dart_filter"
PIN_EXCLUDE = ("frozen_consts.py",)          # 동결 해시 2개 — PREREG.md blob 을 담으므로 고정 대상에서 뺀다(순환 회피)
PIN_DEPS = (                                  # 표본·체결·청산·태그 규칙을 정하는 의존 모듈(레포 루트 기준)
    "RoboTrader_template/strategies/daytrading_3methods_breakout/screener.py",
    "RoboTrader_template/strategies/books/daytrading_3methods/rules.py",
    "RoboTrader_template/strategies/books/_base_book_strategy.py",
    "RoboTrader_template/strategies/_rule_screener_base.py",
    "RoboTrader_template/utils/data_sanity.py",
    "RoboTrader_template/backtest/concept_axes/replayer/scan.py",
    "RoboTrader_template/backtest/concept_axes/replayer/loader.py",
    "RoboTrader_template/backtest/concept_axes/replayer/flags.py",          # ca_path 의 FD1 동결식 flag_cliff(critic B2)
    "RoboTrader_template/backtest/concept_axes/candidate_ledger/run.py",
    "RoboTrader_template/backtest/concept_axes/candidate_ledger/tool_calibration/run_calib.py",
    "RoboTrader_template/backtest/concept_axes/ledger8/exitsim8.py",
    "RoboTrader_template/backtest/concept_axes/ledger8/sizing.py",
    "RoboTrader_template/backtest/concept_axes/ledger8/sources8.py",
    "RoboTrader_template/backtest/concept_axes/minervini/cap_skip_ledger/sim.py",
    "RoboTrader_template/backtest/concept_axes/theme_rank/bandfill.py",
    "RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/dart_tags.py",
    _PKG_REL + "/results/backfill_check.json",
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def required_pins(root: Path) -> List[str]:
    """이 패키지 최상위 *.py(frozen_consts.py 제외 · tests/ 제외) + PIN_DEPS."""
    pkg = sorted(f"{_PKG_REL}/{p.name}" for p in (Path(root) / _PKG_REL).glob("*.py") if p.name not in PIN_EXCLUDE)
    return pkg + list(PIN_DEPS)


def parse_pins(text: str) -> Dict[str, str]:
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == PIN_FENCE]
    if len(starts) != 1:
        raise SystemExit(f"🔴 PREREG.md 에 {PIN_FENCE} 블록이 정확히 1개여야 한다(지금 {len(starts)}) — 중단")
    end = next((j for j in range(starts[0] + 1, len(lines)) if lines[j].strip() == "```"), None)
    if end is None:
        raise SystemExit("🔴 pins 블록이 닫히지 않았다 — 중단")
    pins: Dict[str, str] = {}
    for ln in lines[starts[0] + 1:end]:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        tok = s.split()
        if len(tok) != 2 or not _SHA_RE.match(tok[1]):
            raise SystemExit(f"🔴 pins 줄 형식 오류 «{s}» — `<경로> <40자 소문자 hex>` — 중단")
        path = tok[0]
        if ("\\" in path or path.startswith("/") or ":" in path or ".." in path.split("/")):
            raise SystemExit(f"🔴 pins 경로는 레포 루트 기준 POSIX 상대 경로여야 한다 «{path}» — 중단")
        if path in pins:
            raise SystemExit(f"🔴 pins 경로 중복 «{path}» — 중단")
        pins[path] = tok[1]
    if not pins:
        raise SystemExit("🔴 pins 블록이 비어 있다 — 중단")
    return pins


def verify_pins(pins: Dict[str, str], root: Path, required: Sequence[str]) -> None:
    missing = sorted(set(required) - set(pins))
    if missing:
        raise SystemExit(f"🔴 pins 블록에 없는 필수 경로 {missing} — 중단")
    bad = []
    for rel, sha in sorted(pins.items()):
        p = Path(root) / rel
        if not p.is_file():
            bad.append(f"{rel}(없음)")
        elif blob(p) != sha:
            bad.append(rel)
    if bad:
        raise SystemExit(f"🔴 고정 blob 과 다른 파일 {bad} — 중단")


def code_changes_since_freeze() -> List[str]:
    """frozen_consts.py 를 마지막으로 바꾼 커밋 → HEAD 사이에 바뀐 경로 중 `<패키지>/results/` 밖인 것(critic M5).

    동결 뒤 커밋은 build·seal·open 산출물(results/)뿐이어야 한다 — pins 가 못 덮는 간접 import(utils·__init__ 등)도
    «동결 뒤 커밋» 으로 바뀌면 여기서 막힌다(커밋 안 된 작업 트리 변경은 pins·clean_package 몫).
    """
    log = _git("log", "-1", "--format=%H", "--", "frozen_consts.py")
    sha = log.stdout.strip()
    if log.returncode != 0 or not sha:
        raise SystemExit("🔴 frozen_consts.py 의 커밋 기록이 없다(동결 커밋 전) — 중단")
    diff = _git("-c", "core.quotepath=off", "diff", "--name-only", sha, "HEAD")
    pre = _git("rev-parse", "--show-prefix")
    if diff.returncode != 0 or pre.returncode != 0:
        raise SystemExit(f"🔴 git diff {sha[:12]}..HEAD 실패 — 중단")
    try:
        rel = Path(S.RESULTS).resolve().relative_to(Path(S.PKG).resolve()).as_posix()
    except ValueError:
        raise SystemExit("🔴 results 폴더가 패키지 밖이다 — 중단")
    res = pre.stdout.strip() + rel + "/"
    return sorted(p for p in (ln.strip() for ln in diff.stdout.splitlines()) if p and not p.startswith(res))


def lib_versions() -> Dict[str, str]:
    """수치 결과를 좌우하는 라이브러리 버전 — seal.json 에 기록 · open 이 대조(critic M5)."""
    import scipy
    return {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__}


def check_lib_versions(seal: Dict[str, Any]) -> None:
    rec, now = seal.get("lib_versions"), lib_versions()
    if rec != now:
        raise SystemExit(f"🔴 라이브러리 버전이 봉인 때와 다르다(봉인 {rec} · 지금 {now}) — 중단")


def require_frozen() -> None:
    if not FC.PREREG_FROZEN_BLOB:
        raise SystemExit("🔴 PREREG_FROZEN_BLOB 비어 있음 — 사전등록 동결(Task 12) 전에는 실행 금지")
    if not S.PREREG.exists() or blob(S.PREREG) != FC.PREREG_FROZEN_BLOB:
        raise SystemExit("🔴 PREREG.md blob 이 동결값과 다르다 — 중단")
    if not FC.PROXY_COEF_MD5:
        raise SystemExit("🔴 PROXY_COEF_MD5 비어 있음 — 대리 계수 동결(Task 12) 전에는 실행 금지")
    pc = S.RESULTS / "proxy_coef.json"
    if not pc.exists() or md5(pc) != FC.PROXY_COEF_MD5:
        raise SystemExit("🔴 proxy_coef.json md5 가 동결값과 다르다 — 중단")
    if not clean_package():
        raise SystemExit("🔴 패키지에 커밋 안 된 변경이 있다 — 중단")
    after = code_changes_since_freeze()
    if after:
        more = f" 외 {len(after) - 20}개" if len(after) > 20 else ""
        raise SystemExit(f"🔴 동결 커밋(frozen_consts.py 마지막 커밋) 뒤 results/ 밖 변경 {after[:20]}{more} — 중단")
    root = repo_root()
    verify_pins(parse_pins(S.PREREG.read_text(encoding="utf-8")), root, required_pins(root))
    U.check_adapter_params()


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
    if FC.PREREG_FROZEN_BLOB:
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
    rep = DC.check(conn, backfill_dir, S.FILING_START, S.SCAN_END, S.BACKFILL_TYPES)
    rep.update(window=[S.FILING_START.isoformat(), S.SCAN_END.isoformat()], types=list(S.BACKFILL_TYPES),
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


def check_backfill_report(chk: Dict[str, Any]) -> None:
    """backfill_check.json 이 완결이고 그 창·유형이 동결 settings 와 같은지(최종 리뷰 «동결 전 수정»)."""
    want_w = [S.FILING_START.isoformat(), S.SCAN_END.isoformat()]
    if not chk.get("complete"):
        raise SystemExit("🔴 백필 완결 보고가 미완결 — 중단")
    if chk.get("window") != want_w:
        raise SystemExit(f"🔴 백필 보고 창 {chk.get('window')} ≠ settings {want_w} — 중단")
    if sorted(chk.get("types") or []) != sorted(S.BACKFILL_TYPES):
        raise SystemExit(f"🔴 백필 보고 유형 {chk.get('types')} ≠ settings {list(S.BACKFILL_TYPES)} — 중단")


def check_backfill_rows(n: int) -> None:
    """build 멈춤 규칙 — 공시 창·유형(settings) 행 수 = 백필 적재 기록(S.BACKFILL_ROWS_EXPECTED)."""
    if n != S.BACKFILL_ROWS_EXPECTED:
        raise SystemExit(f"🔴 dart_disclosures 창 {S.FILING_START}~{S.SCAN_END} · 유형 {list(S.BACKFILL_TYPES)} 행 수 "
                         f"{n:,} ≠ 백필 기록 {S.BACKFILL_ROWS_EXPECTED:,} — 중단")


def check_scan_diag(diag: Dict[str, Any]) -> None:
    """build 멈춤 규칙 — 스캔 어댑터 오류가 하나라도 있으면(표본이 라이브 룰과 달라질 수 있음) 거부."""
    if diag.get("n_errors") != 0:
        raise SystemExit(f"🔴 스캔 어댑터 오류 n_errors={diag.get('n_errors')} — 중단")


def stage_build(conn) -> None:
    require_frozen()
    for done in ("seal.json", "open.started", "open.json"):
        if (S.RESULTS / done).exists():
            raise SystemExit(f"🔴 {done} 가 이미 있다 — 봉인·개봉 뒤에는 build 재실행 금지")
    bf = S.RESULTS / "backfill_check.json"
    if not bf.exists() or not committed_unchanged(bf):
        raise SystemExit("🔴 백필 완결 보고가 없거나 미커밋 — 중단")
    check_backfill_report(json.loads(bf.read_text(encoding="utf-8")))
    n_bf = T.count_backfill_rows(conn, S.FILING_START, S.SCAN_END, S.BACKFILL_TYPES)
    check_backfill_rows(n_bf)
    coef = json.loads((S.RESULTS / "proxy_coef.json").read_text(encoding="utf-8"))
    cal, px, env = _load_env(conn)
    cal_idx = {d: i for i, d in enumerate(cal)}
    days = [pd.Timestamp(d) for d in cal if S.SCAN_START <= d <= S.SCAN_END]
    rows, diag = U.scan_window(px, days)
    check_scan_diag(diag)
    feat = P.add_proxy_features(px).set_index(["stock_code", "date"])
    halts = L.halt_dates(px)
    cad = L.ca_flag_days(px, cal_idx)
    out: List[Dict[str, Any]] = []
    for r in rows:
        k = (r["stock_code"], pd.Timestamp(r["scan_date"]))
        x1 = float(feat["x1"].get(k, np.nan))
        x2 = float(feat["x2"].get(k, np.nan))
        pl = float(P.predict(np.array(coef["beta"]), P.design([x1], [x2]))[0]) if np.isfinite(x1 + x2) else np.nan
        sim = L.simulate_candidate(env, r["stock_code"], r["scan_date"], halts.get(r["stock_code"], set()))
        ca = L.ca_path(cad, r["stock_code"], sim["entry_date"], cal_idx) if sim.get("status") == "filled" else None
        out.append({**r, "tv20": float(feat["tv20"].get(k, np.nan)), "close": float(feat["close"].get(k, np.nan)),
                    "p_L": pl, **{kk: sim.get(kk) for kk in LEDGER_COLS if kk in sim}, "ca_path": ca})
    led = pd.DataFrame(out).reindex(columns=LEDGER_COLS)
    S.RESULTS.mkdir(parents=True, exist_ok=True)
    led.to_csv(S.RESULTS / "ledger_A.csv", index=False, lineterminator="\n")
    fil = T.load_filings(conn, S.FILING_START, S.SCAN_END)
    scan_cal = [d for d in cal if d <= S.SCAN_END]
    specs = [("lag0", 0, None), ("w5", 4, None), ("w20", 19, None)] + [(n, 0, t) for n, t in zip(TAG_MARKS, S.TAGS_LAG0)]
    for name, back, only in specs:
        mk = sorted(T.window_marks(fil, scan_cal, back, only=only))
        pd.DataFrame(mk, columns=["stock_code", "scan_date"]).to_csv(S.RESULTS / f"marks_{name}.csv", index=False,
                                                                     lineterminator="\n")
    fp = LD.db_fingerprint(conn, S.PX_START, S.PATH_END)
    meta = dict(git_sha=head_sha(), db_fingerprint=fp["sha256"], per_stock=fp["per_stock"], scan_diag=diag,
                normalize_counts=px.attrs.get("normalize_counts"), n_backfill_rows=n_bf, n_rows=len(led),
                n_filings=len(fil), md5={p.name: md5(p) for p in sorted(S.RESULTS.glob("*.csv"))},
                finished=datetime.now().isoformat(timespec="seconds"))
    _write(S.RESULTS / "build_meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"원장 {len(led):,}행 · 공시 {len(fil):,} · 지문 {fp['sha256'][:12]}")


def fingerprint_diff(old: Optional[Dict[str, str]], new: Optional[Dict[str, str]]) -> Dict[str, List[str]]:
    """종목별 지문 차이 — 종목 코드만(critic M4 · 문제 3)."""
    old, new = old or {}, new or {}
    return {"changed": sorted(c for c in set(old) & set(new) if old[c] != new[c]),
            "added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new))}


def _check_build(conn) -> Dict[str, Any]:
    meta = json.loads((S.RESULTS / "build_meta.json").read_text(encoding="utf-8"))
    for name, h in meta["md5"].items():
        if md5(S.RESULTS / name) != h:
            raise SystemExit(f"🔴 {name} md5 불일치 — 중단")
    fp = LD.db_fingerprint(conn, S.PX_START, S.PATH_END)
    if fp["sha256"] != meta["db_fingerprint"]:
        if meta.get("per_stock") is None:
            print("daily_prices 지문 불일치 — build_meta 에 종목별 지문 없음(어느 종목인지 모름)")
        else:
            diff = fingerprint_diff(meta["per_stock"], fp.get("per_stock"))
            print("daily_prices 지문 불일치 — 종목 코드(해시 아님):")
            for key, lab in (("changed", "값이 바뀐 종목"), ("added", "새로 생긴 종목"), ("removed", "사라진 종목")):
                print(f"- {lab} {len(diff[key]):,}: {', '.join(diff[key])}")
        raise SystemExit("🔴 daily_prices 지문이 build 때와 다르다(소급 수정 · 위 종목 확인) — 중단")
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


def effective_n0(df: pd.DataFrame, ycol: str = "y_sl") -> int:
    """회귀가 실제로 쓰는 대조 행 수(effective_n1 과 같은 날 거르기)."""
    d = df[np.isfinite(df[ycol].astype(float))]
    m = ST.both_arm_days_mask(d["x"], d["day"])
    return int((d["x"].to_numpy()[m] == 0).sum())


# ── 봉인 고정(최종 리뷰 I5) ───────────────────────────────────────────────────────
_SEAL_MD5_RE = re.compile(r"seal\.json md5 `([0-9a-f]{32})`")


def seal_md5_line(h: str) -> str:
    return f"- seal.json md5 `{h}` — open 이 이 값과 seal.json 을 대조한다(봉인 고정)"


def check_sealed_report(report: Path, seal_path: Path) -> None:
    """커밋된 sealed_report.md 의 seal.json md5 줄(정확히 1개)이 지금 seal.json 과 같은지."""
    if not Path(report).exists() or not Path(seal_path).exists():
        raise SystemExit("🔴 sealed_report.md 또는 seal.json 이 없다 — 중단")
    found = _SEAL_MD5_RE.findall(Path(report).read_text(encoding="utf-8"))
    if len(found) != 1:
        raise SystemExit(f"🔴 sealed_report.md 의 seal.json md5 줄이 정확히 1개가 아니다({len(found)}) — 중단")
    if md5(seal_path) != found[0]:
        raise SystemExit("🔴 seal.json 이 봉인 보고서에 적힌 md5 와 다르다(봉인 뒤 변경) — 중단")


# ── 블라인드 안전 인쇄(수익 무관) · 개봉 보조 ────────────────────────────────────
def pl_small_share_by_year(led: pd.DataFrame) -> Dict[int, Dict[str, Any]]:
    """연도별 후보 행(원장 전체 · 체결 무관) 중 p_L<0.5 비율 — 시총 없는 해의 대리 분류 안정성 점검용."""
    out: Dict[int, Dict[str, Any]] = {}
    pl = led["p_L"].astype(float).to_numpy()
    yrs = np.array([d.year for d in led["scan_date"]])
    for y in sorted(set(yrs.tolist())):
        v = pl[yrs == y]
        fin = v[np.isfinite(v)]
        out[int(y)] = {"n": int(len(fin)), "n_nan": int(len(v) - len(fin)),
                       "share_small": float((fin < S.PL_CUT).mean()) if len(fin) else float("nan")}
    return out


def halt_entry_counts(led: pd.DataFrame, marks) -> Dict[str, Dict[str, int]]:
    """«진입 불가»(진입 봉 정지) 수 — 대리 소형 · 집단별(스펙 :84 «따로 셈»). n = 체결 + 진입 불가 행."""
    d = led[(led["p_L"].astype(float) < S.PL_CUT) & led["status"].isin(["filled", "halt_entry"])]
    x = np.array([(c, s) in marks for c, s in zip(d["stock_code"], d["scan_date"])], dtype=bool)
    st = d["status"].to_numpy()
    return {arm: {"halt_entry": int(((x == flag) & (st == "halt_entry")).sum()), "n": int((x == flag).sum())}
            for arm, flag in (("표식", True), ("대조", False))}


def seal_report_lines(seal: Dict[str, Any]) -> List[str]:
    g, sv = seal["gate"], seal["surv"]
    pls = " · ".join(f"{y} {v['share_small']:.3f}(n {v['n']:,} · NaN {v['n_nan']:,})"
                     for y, v in seal["pl_small_share_by_year"].items())
    return [
        "# 봉인 보고서 — 표식×수익 결합 0 (스펙 §3-6)", "",
        f"- n₁(유효 · 표식·대조 둘 다 있는 날) {seal['n1']:,} · 대조(유효) {seal['n0']:,}",
        f"- 원시(날 거르기 전) 개수: 표식 원시 {seal['n1_raw']:,} · 대조 원시 {seal['n0_raw']:,} · "
        f"n₁ 원시 연도별 {seal['n1_raw_by_year']}",
        f"- 후보 중 p_L<0.5 비율(연도별 · 원장 전체 · 수익 무관): {pls}",
        f"- SD(대조 · net) 손절 우선 {seal['sd_ctrl_sl']:.3f} · 익절 우선 {seal['sd_ctrl_tp']:.3f}",
        f"- 가짜 게이트: CR1 거부율 {g['rej_cr1']:.3f} · 2원 {g['rej_2w']:.3f} → 도구 **{g['tool']}** ({g['reason']}) · "
        f"유효 {g['n_valid']}/{g['n_fake']}(문턱 {g['n_valid_min']}) · 2원 유효 {g['n_valid_2w']} · 건너뜀 {g['n_skipped']}",
        f"- 가짜 게이트 하측(p1<0.05) {g['rej_lo_cr1']:.3f} · 가짜 평균 n₁ {g['mean_fake_n1']:.1f}",
        f"- SD_null {g['sd_null']:.3f} → MDE {seal['mde_null']:.3f}%p (평균 SE 기준 {seal['mde_se']:.3f}%p)",
        f"- 생존자 누락률 (i) 3태그 공시 단위 {sv['surv_i']:.4f}(n {sv['n_i']:,}) · (ii) 정기공시 회사 단위 "
        f"{sv['surv_ii']:.4f}(n {sv['n_ii']:,}) — 코넥스·상장 전 공시 제외",
        *[f"  - {ln}" for ln in SV.breakdown_text(sv).splitlines()],
        *([f"- 라이브러리 {' · '.join(f'{k} {v}' for k, v in seal['lib_versions'].items())} — open 이 대조"]
          if seal.get("lib_versions") else []),
    ]


def _read_marks(name: str):
    m = pd.read_csv(S.RESULTS / f"marks_{name}.csv", dtype={"stock_code": str})
    return {(c, date.fromisoformat(d)) for c, d in zip(m["stock_code"], m["scan_date"])}


def _read_ledger() -> pd.DataFrame:
    led = pd.read_csv(S.RESULTS / "ledger_A.csv", dtype={"stock_code": str})
    led["scan_date"] = [date.fromisoformat(str(d)[:10]) for d in led["scan_date"]]
    for c in ("both", "unresolved", "halted_in_path", "ca_path"):   # CSV "True"/"False"/빈칸 → bool (문자열 astype(bool) 함정)
        led[c] = led[c].astype(str).str.strip().str.lower().eq("true")
    return led


# ── 개봉 계산 도우미(태그별 · ca_path · 팔별 보조) ─────────────────────────────────
def _fe(d: pd.DataFrame, col: str = "y_sl", key: str = "day") -> ST.FE:
    return ST.fe_regression(d[col].to_numpy(), d["x"].to_numpy(), d[key].to_numpy(), d["stock"].to_numpy(),
                            d["block"].to_numpy())


def tool_label(tool: str) -> str:
    return tool if tool in ("cr1", "2way") else "cr1(인쇄만 · 봉인 도구 fail)"


def tool_p1(fe: ST.FE, tool: str) -> Tuple[float, str]:
    """봉인 도구의 단측 p — 도구 fail 이면 CR1 로 계산하되 «인쇄만»(판정 불가는 그대로)."""
    return (fe.p1_2w if tool == "2way" else fe.p1_cr1), tool_label(tool)


def per_tag_frame(df: pd.DataFrame, marks_t: Set[Tuple[str, date]]) -> pd.DataFrame:
    """태그 t 회귀 표본 = 대조(3태그 lag0 표식 없음 · x==0) ∪ 태그 t 표식 행 · 다른 태그로만 표식된 행은 뺀다."""
    xt = np.array([1 if (c, s) in marks_t else 0 for c, s in zip(df["stock_code"], df["scan_date"])], dtype=int)
    keep = (df["x"].to_numpy() == 0) | (xt == 1)
    out = df[keep].copy()
    out["x"] = xt[keep]
    return out


def per_tag_results(df: pd.DataFrame, tag_marks: Sequence[Set[Tuple[str, date]]], tool: str,
                    lab: str) -> Tuple[Dict[str, Any], List[str]]:
    """태그별 3개 + 표준 Holm m=3(손절 우선 판 · 봉인 도구 p · NaN p → 1.0) — 라벨과 무관하게 항상 계산·인쇄(critic B1).

    해석(조정 p < 0.05 → 「그 태그 기여 있음」)은 주 라벨이 「있음(−)」일 때만 적는다.
    """
    rows: List[Dict[str, Any]] = []
    used = tool_label(tool)
    for name, tag, mk in zip(TAG_MARKS, S.TAGS_LAG0, tag_marks):
        f = _fe(per_tag_frame(df, mk))
        rows.append(dict(tag=tag, marks=f"marks_{name}.csv", beta=f.beta, n1=int(f.n1), p1=tool_p1(f, tool)[0],
                         fe=f.__dict__))
    for r, a in zip(rows, ST.holm([r["p1"] for r in rows])):
        r["p_holm"] = a
    interp = lab == "있음(−)"
    lines = [f"## 태그별 3개 + Holm m=3 (보조 · 라벨 불변 · 손절 우선 판 · 도구 {used})", ""]
    lines += [f"- {r['tag']}: δ̂ {r['beta']:+.3f}%p · n₁ {r['n1']:,} · 단측 p {r['p1']:.4f} · Holm p {r['p_holm']:.4f}"
              for r in rows]
    if interp:
        for r in rows:
            hit = r["p_holm"] < S.ALPHA
            lines.append(f"  - 해석: {r['tag']} Holm p {r['p_holm']:.4f} {'<' if hit else '≥'} {S.ALPHA} → "
                         + ("그 태그 기여 있음" if hit else "그 태그 기여 확인 안 됨"))
    else:
        lines.append(f"- 해석 안 함(주 라벨 «{lab}» ≠ 있음(−)) — 숫자만 인쇄")
    return dict(tool_used=used, interpreted=interp, tags=rows), lines


def ca_path_results(df: pd.DataFrame, tool: str) -> Tuple[Dict[str, Any], List[str]]:
    """팔별 ca_path 수 + ca_path 로트를 양 팔에서 대칭으로 뺀 손절 우선 판(봉인 도구 p) — 인쇄만(critic B2)."""
    ca = df["ca_path"].astype(bool).to_numpy()
    x = df["x"].to_numpy() == 1
    counts = {arm: {"ca_path": int((m & ca).sum()), "n": int(m.sum())} for arm, m in (("표식", x), ("대조", ~x))}
    f = _fe(df[~ca])
    p, used = tool_p1(f, tool)
    lines = [f"## 보유 창 기업행위 의심 ca_path (진입 다음 거래일 k=1..{S.CA_WINDOW_TD} · 인쇄만 · 라벨 불변)", "",
             "- 팔별 ca_path: " + " · ".join(f"{arm} {v['ca_path']:,}/{v['n']:,}" for arm, v in counts.items()),
             f"- ca_path 로트 양 팔 제외 손절 우선 판: δ̂ {f.beta:+.3f}%p · n₁ {f.n1:,} · 단측 p {p:.4f} ({used})"]
    return dict(counts=counts, fe_sl_excl=f.__dict__, p1=p, tool_used=used), lines


def fill_counts(led: pd.DataFrame, marks: Set[Tuple[str, date]]) -> Dict[str, Dict[str, Any]]:
    """팔별 밴드 미체결 비율 — 대리 소형 원장 행 중 체결 시도(filled + no_fill) 대비 no_fill(open 보조)."""
    d = led[(led["p_L"].astype(float) < S.PL_CUT) & led["status"].isin(["filled", "no_fill"])]
    x = np.array([(c, s) in marks for c, s in zip(d["stock_code"], d["scan_date"])], dtype=bool)
    nf = d["status"].to_numpy() == "no_fill"
    out: Dict[str, Dict[str, Any]] = {}
    for arm, m in (("표식", x), ("대조", ~x)):
        n, k = int(m.sum()), int((m & nf).sum())
        out[arm] = {"no_fill": k, "n": n, "rate": k / n if n else float("nan")}
    return out


def unresolved_counts(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    """팔별 «미해소»(창 끝까지 청산 안 됨 · 마지막 값) 로트 수 — 분석 표본(open 보조)."""
    x = df["x"].to_numpy() == 1
    u = df["unresolved"].astype(bool).to_numpy()
    return {arm: {"unresolved": int((m & u).sum()), "n": int(m.sum())} for arm, m in (("표식", x), ("대조", ~x))}


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
    for done in ("seal.json", "open.started", "open.json"):
        if (S.RESULTS / done).exists():
            raise SystemExit(f"🔴 {done} 가 이미 있다 — 봉인은 1회만(재봉인 금지)")
    _check_build(conn)
    cal, px, _env = _load_env(conn)
    cal_idx = {d: i for i, d in enumerate(cal)}
    led = _read_ledger()
    df = SM.analysis_frame(led, _read_marks("lag0"), cal_idx)
    gate = G.fake_gate(df)
    ctrl = df[df["x"] == 0]
    surv = _survivorship(conn, px)
    years = pd.Series([d.year for d in df["scan_date"]])
    seal = dict(n1=effective_n1(df), n0=effective_n0(df), n1_raw=int((df["x"] == 1).sum()), n0_raw=int(len(ctrl)),
                n1_raw_by_year={int(y): int(((years == y) & (df["x"] == 1)).sum()) for y in sorted(years.unique())},
                pl_small_share_by_year=pl_small_share_by_year(led), build_md5=build_hashes(),
                sd_ctrl_sl=float(ctrl["y_sl"].std(ddof=1)), sd_ctrl_tp=float(ctrl["y_tp"].std(ddof=1)), gate=gate,
                mde_null=ST.mde(gate["sd_null"]), mde_se=ST.mde(gate["mean_se_cr1"]),
                surv=surv, lib_versions=lib_versions(), git_sha=head_sha(),
                sealed=datetime.now().isoformat(timespec="seconds"))
    _write(S.RESULTS / "seal.json", json.dumps(seal, ensure_ascii=False, indent=1))
    _write(S.RESULTS / "sealed_report.md",
           "\n".join(seal_report_lines(seal) + [seal_md5_line(md5(S.RESULTS / "seal.json")), ""]))
    print(json.dumps(seal, ensure_ascii=False, indent=1, default=str))


# ── 단계: open(1회) ──────────────────────────────────────────────────────────────
def stage_open(conn) -> None:
    """무결성 확인(봉인 보고서 커밋 · seal.json md5 · build 해시 · DB 지문) → `open.started` 표식 → 그 뒤에만 계산.

    표식은 무결성 확인 «뒤»·데이터 읽기 «전»에 쓴다 — 확인 실패(예: DB 지문 불일치)는 결과를 하나도 보지 않았으므로
    복구 뒤 다시 돌 수 있고, 표식이 생긴 뒤에는 중간에 죽어도 두 번째 개봉을 거부한다.
    """
    require_frozen()
    if (S.RESULTS / "open.json").exists():
        raise SystemExit("🔴 이미 개봉됨(open.json 있음) — 1회만 허용")
    if (S.RESULTS / "open.started").exists():
        raise SystemExit("🔴 open.started 가 이미 있다(개봉이 시작됐었다) — 두 번째 개봉 금지")
    if not committed_unchanged(S.RESULTS / "sealed_report.md"):
        raise SystemExit("🔴 sealed_report.md 가 커밋돼 있지 않거나 바뀌었다 — 중단")
    check_sealed_report(S.RESULTS / "sealed_report.md", S.RESULTS / "seal.json")
    seal = json.loads((S.RESULTS / "seal.json").read_text(encoding="utf-8"))
    check_seal_linkage(seal)
    check_lib_versions(seal)
    _check_build(conn)
    _write(S.RESULTS / "open.started", json.dumps(dict(started=datetime.now().isoformat(timespec="seconds"),
                                                       seal_md5=md5(S.RESULTS / "seal.json"), git_sha=head_sha()),
                                                  ensure_ascii=False, indent=1))
    cal, _px, _env = _load_env(conn)
    cal_idx = {d: i for i, d in enumerate(cal)}
    led = _read_ledger()
    marks0 = _read_marks("lag0")
    df = SM.analysis_frame(led, marks0, cal_idx)
    fe_sl, fe_tp = _fe(df, "y_sl"), _fe(df, "y_tp")
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
        f2 = _fe(d2, "y_sl")
        sec[name] = f2.__dict__
        lines.append(f"- {name}: δ̂ {f2.beta:+.3f} · n₁ {f2.n1} · 단측 p {f2.p1_cr1:.4f}")
    big = SM.analysis_frame(led, _read_marks("lag0"), cal_idx, small_only=False)
    big["key"] = big["day"].astype(str) + "|" + pd.qcut(big["p_L"].rank(method="first"), 3, labels=False).astype(str)
    fb = _fe(big, "y_sl", key="key")
    sec["all_sizes"] = fb.__dict__
    lines.append(f"- 대형 포함 전체(날짜×대리 3분위 FE): δ̂ {fb.beta:+.3f} · n₁ {fb.n1} · 단측 p {fb.p1_cr1:.4f}")
    for y in sorted({d.year for d in df["scan_date"]}):
        dy = df[[d.year == y for d in df["scan_date"]]]
        fy = _fe(dy, "y_sl")
        lines.append(f"- {y}: δ̂ {fy.beta:+.3f} · n₁ {fy.n1}")
    tv_t = pd.qcut(df["trading_value"].rank(method="first"), 3, labels=False)
    for t in range(3):
        ft = _fe(df[tv_t == t], "y_sl")
        lines.append(f"- 거래대금 3분위 {t + 1}: δ̂ {ft.beta:+.3f} · n₁ {ft.n1}")
    for arm, sub in (("표식", df[df["x"] == 1]), ("대조", df[df["x"] == 0])):
        lines.append(f"- {arm}: 정지 낀 비율 {sub['halted_in_path'].astype(bool).mean():.4f} · "
                     f"ret ≤ −15% {(sub['ret_sl'] <= S.TAIL_LOSS).mean():.4f} · 동시 터치 {sub['both'].astype(bool).mean():.4f}")
    he = halt_entry_counts(led, marks0)
    sec["halt_entry"] = he
    lines.append("- 진입 불가(진입 봉 정지 · 대리 소형 · 원장 행 단위 · 따로 셈): "
                 + " · ".join(f"{arm} {v['halt_entry']:,}/{v['n']:,}" for arm, v in he.items()))
    aux = dict(no_fill=fill_counts(led, marks0), unresolved=unresolved_counts(df))
    lines.append("- 팔별 밴드 미체결 no_fill(대리 소형 · 원장 행 · 체결 시도 = filled+no_fill 대비): "
                 + " · ".join(f"{arm} {v['no_fill']:,}/{v['n']:,} ({v['rate']:.4f})" for arm, v in aux["no_fill"].items()))
    lines.append("- 팔별 미해소 unresolved(분석 표본 · 창 끝 마지막 값): "
                 + " · ".join(f"{arm} {v['unresolved']:,}/{v['n']:,}" for arm, v in aux["unresolved"].items()))
    per_tag, tag_lines = per_tag_results(df, [_read_marks(n) for n in TAG_MARKS], tool, lab)
    ca, ca_lines = ca_path_results(df, tool)
    lines += [""] + tag_lines + [""] + ca_lines
    today = date.today().isoformat()
    _write(S.RESULTS / f"RESULTS_{today}.md", "\n".join(lines) + "\n")
    _write(S.RESULTS / "open.json", json.dumps(dict(label=lab, fe_sl=fe_sl.__dict__, fe_tp=fe_tp.__dict__,
                                                    secondary=sec, per_tag=per_tag, ca_path=ca, aux=aux,
                                                    opened=datetime.now().isoformat(timespec="seconds"),
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
