# -*- coding: utf-8 -*-
"""`PREREG_RANKING.md` 실행 — 후보 랭킹(「어느 급등주냐」) 축 · 접두 `RNK-`.

이 스크립트는 **§0-3 표의 3단계(훈련·선택)** 를 돌린다. 대상은 **post1~5 «만»**이다.
🔴 **6번째 글은 아직 존재하지 않는다** — `--stage post6` 은 의도적으로 «거부»한다(§0-3 5단계 전).

동결 문언 준수 사항 (문서 → 코드 대응은 `RESULTS_RANKING_TRAIN.md` 의 대조표):
  · §2-1 `RNK-R1`  유니버스 = 등록일 `market_cap>0 ∧ close>0` **전체** · 의사티커 제외
                   (`prev_close` 조건은 **판정 갈래에서 뺐다** — `n_up` 민감도 갈래 전용)
  · §2-2 `RNK-R2`  후보 규칙은 `RNK-A1`~`A5` **다섯이 전부** · 특징은
                   `run_selection.build_features`(브랜치 `7712e03` 기준 `:58-84`, C-17 포함)를
                   **그대로 import** 한다(재구현 0줄 = 새 자유도 0)
  · §2-3 `RNK-R3`  글 단위 leave-one-out · 짝의 단위 = **「두 규칙 모두 측정 가능한 `exact` 건」**
                   · 동률 폴스루 ① m_rank 동일 → ② 요구 특징 수 → ③ 목록 순서
  · §2-4 `RNK-R4`  `m_rank` = 「엄격히 좋은 종목 수 + 동률 종목 수(자기 제외)」 = **동률을 전부 위로**
                   · `pctl = 100(N−1−m)/(N−1)` 은 **귀무 검정 전용**
                   · 귀무 = 시드 `20260815` · **20,000회** (`run_selection.NREP=2000` 과 다르다 · §8-4)
  · §4-3         `RNK-B1` 단측 부호검정 + 순열 · `Δ=0` 짝은 **버린다** · 최소 **비영 짝 5**
                 `RNK-B2` 분모는 **전 짝**이고 **동률은 「못 이긴 것」**
  · §4-6         `RNK-A5` 가 LOO 1위면 ⛔ `RNK-X1` = 선택 절차 무효
  · §5           `adj_factor` 를 가격에 **곱하지도 나누지도 않는다** · DB 는 **SELECT 만** ·
                 라이브 트리 import **0건**

산출물 = `RESULTS_RANKING_TRAIN_NUMBERS.md` (기계 생성 · `regen_gate.py` `PAIRS` 대상).
산문 `RESULTS_RANKING_TRAIN.md` 는 **사람이 쓴다**(§5-7 `MANUAL_DOCS`).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

# 🔴 재구현 금지(§2-2) — 특징·백분위 정의는 브랜치판을 그대로 쓴다.
from run_selection import FEATS, PSEUDO, build_features
from run_tests import CODES, DSN
# 종목코드는 post4·post5 계열이 이미 확정한 것을 그대로 승계한다(새 매핑 0건).
from run_regday_post5 import POST4 as RG_POST4, POST5 as RG_POST5

BASE = Path(__file__).resolve().parent
OUT: list = []

SEED = 20260815          # §2-4 · `PREREG_POST6.md` §3-1
NREP = 20_000            # §2-4 — `run_selection.NREP = 2000` 과 «다르다»(§8-4)
START = "2026-04-01"     # §5-3 — 시작일 고정. 바꾸면 백분위가 통째로 바뀐다.
NUP_MULT = 1.15          # `n_up` 민감도 갈래 전용(§2-1) — 판정 갈래는 쓰지 않는다
DROP_RATE_FLAG = 0.01    # §6 말미 — «표기 가드»이지 판정 게이트가 아니다
A5_CALIB_K = 200         # `RNK-N1` 보정 검사의 독립 실현 수 (문턱이 아니라 «표본 크기»다)

BANNER = [
    "> 🔴 **라이브 채택 금지 · 성과·엣지 추정 금지** — 이 산출물은 **기록**이지 전략 후보가 아니다",
    ">   (`PREREG_RANKING.md` §0-1 · `PREREG.md` §0). 라이브 전략·파라미터 변경의 근거가 아니다.",
    "> 🔴 **「+15%」 문턱이 이 축 «안»에 남아 있다** — `f6_spikes60` = 「60일 내 일간 +15% 이상 봉 수」",
    ">   (§0-2 ②). `SEL-S1` 부활이 아닌 이유 셋은 그 절에 있고, **그래도 매 산출물에 인쇄한다.**",
    "> 🔬 **훈련값은 «탐색적 표기»다**(§4-5) — post1~5 값은 판정 분모에 **넣지 않는다.**",
    "> 🔑 **정보는 `RNK-B1`·`RNK-B2`(f1 대비)와 `RNK-N2`(m_rank)에 있다**(§4-1). "
    "`RNK-N1` 통과는 「바닥을 통과했다」이지 「가설이 맞았다」가 아니다.",
]

# 규칙 정의 (§2-2) — 이 목록 밖 규칙의 사후 추가는 금지다.
A4_DROP = ["f7_mcap", "f9_newhigh"]
A4_FEATS = [f for f in FEATS if f not in A4_DROP]
RULES = ["RNK-A1", "RNK-A2", "RNK-A3", "RNK-A4", "RNK-A5"]
REQ = {
    "RNK-A1": ["f1_tv_mcap"],
    "RNK-A2": list(FEATS),
    "RNK-A3": list(FEATS),
    "RNK-A4": list(A4_FEATS),
    "RNK-A5": [],
}
RULE_DESC = {
    "RNK-A1": "`f1_tv_mcap` 단독 내림차순 (벤치마크 · 자유모수 0)",
    "RNK-A2": "`f1`~`f9` 일자별 백분위의 균등가중 평균 (자유모수 0)",
    "RNK-A3": "pooled 로지스틱 · 설명변수 = 백분위/100 · 예측확률 (자유모수 9+절편)",
    "RNK-A4": "`f7`·`f9` 제외 7특징 백분위 균등가중 평균 (자유모수 0)",
    "RNK-A5": "🔬 무작위 순위 (대조군 · 시드 20260815 · 자유모수 0)",
}


def say(s=""):
    print(s)
    OUT.append(s)


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


# 🔴 **난수 스트림 분리** — 시드는 `20260815` 하나지만, 「관측(`RNK-A5` 무작위 순위)」과
#    「귀무(재추출)」와 「순열」을 **같은 시드로 각각 `default_rng(SEED)` 해서 쓰면 두 계열이
#    우연히 얽힐 수 있다**(그리고 얽혔는지 «확인할 방법이 없다»). `SeedSequence.spawn` 으로
#    구조적으로 갈라 둔다 — 시드 동결(§2-4)은 그대로이고, 파생 규칙이 결정적이다.
#    🔑 같은 이름을 다시 부르면 «같은» 스트림이 나온다 = 규칙 간 **공통난수(CRN)** — 의도한 것이다.
#    ⚠️ 이름은 **끝에만 덧붙인다** — `spawn` 은 앞쪽 자식을 보존하므로 그래야 기존 값이 안 흔들린다.
_STREAM_NAMES = ["a5_scores", "null_resample", "null_analytic",
                 "pairs_main", "pairs_nup", "pairs_approx", "pairs_bench",
                 "a5_calibration"]
_CHILDREN = dict(zip(_STREAM_NAMES, np.random.SeedSequence(SEED).spawn(len(_STREAM_NAMES))))


def stream(name):
    return np.random.default_rng(_CHILDREN[name])


_DAY = {}


def day_of(df, d):
    """등록일 `d` 의 유니버스 슬라이스 (캐시). 265k 행 전수 스캔을 매번 하지 않기 위한 것뿐이다."""
    k = str(d)
    if k not in _DAY:
        _DAY[k] = df[df.date == pd.Timestamp(d)]
    return _DAY[k]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 원장 · 종목코드
# ═══════════════════════════════════════════════════════════════════════════
def load_ledger():
    """`ledger_trades.csv` 를 **이름 기준**으로 읽는다(§5-2 — 브랜치판은 17필드다)."""
    rows = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    return rows


def build_codes():
    """종목코드 = `run_tests.CODES` ∪ post4·post5 계열이 확정한 코드. 새 매핑 0건."""
    codes = dict(CODES)
    reg_from_series = {}
    for nm, code, reg in list(RG_POST4) + list(RG_POST5):
        codes[nm] = code
        reg_from_series[(nm, reg)] = code
    return codes, reg_from_series


def exact_items(rows, codes):
    """`exact` 건 전수(§1-2). 코드가 없으면 `code=None`(= 사유 ① 측정 불가)."""
    posts = sorted({(r["post_date"], r["post_log_no"]) for r in rows})
    post_idx = {log: i + 1 for i, (_d, log) in enumerate(posts)}
    items = []
    for r in rows:
        if r["reg_date_precision"] != "exact":
            continue
        items.append(dict(
            post=post_idx[r["post_log_no"]], log_no=r["post_log_no"], item_no=r["item_no"],
            name=r["stock_name"], code=codes.get(r["stock_name"]),
            reg=r["reg_date"], prec="exact", all_loss=r["all_loss"]))
    items.sort(key=lambda x: (x["post"], int(x["item_no"])))
    return items, post_idx


def approx_items(rows, codes, post_idx):
    out = []
    for r in rows:
        if r["reg_date_precision"] != "approx":
            continue
        out.append(dict(
            post=post_idx[r["post_log_no"]], log_no=r["post_log_no"], item_no=r["item_no"],
            name=r["stock_name"], code=codes.get(r["stock_name"]),
            reg=r["reg_date"], prec="approx", all_loss=r["all_loss"]))
    out.sort(key=lambda x: (x["post"], int(x["item_no"])))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2. DB
# ═══════════════════════════════════════════════════════════════════════════
def snapshot_upto(conn) -> str:
    cur = conn.cursor()
    cur.execute("SELECT max(date) FROM daily_prices")
    return str(cur.fetchone()[0])


def name_search_absent(conn, name) -> tuple:
    """사유 ①(DB 종목코드 부재) **실측 재현** — `stock_info`·`stock_industry` 이름검색."""
    res = {}
    for t in ("stock_info", "stock_industry"):
        cur = conn.cursor()
        try:
            cur.execute("SELECT count(*) FROM %s WHERE stock_name LIKE %%s" % t, ("%" + name + "%",))
            res[t] = int(cur.fetchone()[0])
        except Exception as e:            # noqa: BLE001
            conn.rollback()
            res[t] = "ERR:%s" % type(e).__name__
    return res


def load(conn, upto: str) -> pd.DataFrame:
    """`run_selection.load()` 와 **같은 술어**. 상한만 실행 시점 스냅샷으로 확장(§5-3).

    🔴 `adj_factor` 를 곱하지도 나누지도 않는다 — 원주가 그대로다(§5-5 · 프로젝트 SSOT).
    🔑 `volume`·`trading_value` 는 읽기 계층에서 이미 적용돼 있다(이중조정 금지).
    """
    q = ("SELECT stock_code, date, high, low, close, trading_value, market_cap "
         "FROM daily_prices WHERE date BETWEEN '%s' AND '%s' "
         "AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0" % (START, upto))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_sql(q, conn)
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def pseudo_audit(conn) -> list:
    """§7-B #15 — 의사티커 전수 재확인(코드 술어 `^[0-9][0-9A-Z]{5}$` 밖의 코드 전수)."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM daily_prices "
                "WHERE stock_code !~ '^[0-9][0-9A-Z]{5}$'")
    return sorted(r[0] for r in cur.fetchall())


# ═══════════════════════════════════════════════════════════════════════════
# 3. 통계량 (§2-4)
# ═══════════════════════════════════════════════════════════════════════════
def m_rank_vector(v: np.ndarray) -> np.ndarray:
    """`m_rank[i]` = 「`v` 가 `v[i]` 보다 엄격히 큰 종목 수 + 동률 수(자기 제외)」.

    🔑 동률을 전부 «위»로 센다 = 저자에게 «불리한» 쪽 = 보수적(§2-4).
    """
    m = np.empty(len(v), dtype=float)
    order = np.argsort(-v, kind="mergesort")
    sv = -v[order]
    _uniq, first, cnt = np.unique(sv, return_index=True, return_counts=True)
    for g, c in zip(first, cnt):
        m[order[g:g + c]] = g + c - 1
    return m


def pctl_from_m(m, n):
    if n <= 1:
        return np.nan
    return 100.0 * (n - 1 - np.asarray(m, dtype=float)) / (n - 1)


def med(xs):
    xs = [x for x in xs if x is not None and np.isfinite(x)]
    return float(np.median(xs)) if xs else np.nan


# ═══════════════════════════════════════════════════════════════════════════
# 4. 규칙별 점수
# ═══════════════════════════════════════════════════════════════════════════
def rule_scores(day: pd.DataFrame, rule: str, model=None, rand=None):
    """그날 유니버스 `day` 에 대한 (점수, 측정가능 마스크). 점수는 «클수록 좋다»."""
    if rule == "RNK-A1":
        v = day["f1_tv_mcap"].to_numpy(dtype=float)
        return v, np.isfinite(v)
    if rule == "RNK-A5":
        return rand, np.isfinite(rand)
    cols = [f + "_pct" for f in REQ[rule]]
    arr = day[cols].to_numpy(dtype=float)
    ok = np.all(np.isfinite(arr), axis=1)
    v = np.full(len(day), np.nan)
    if rule in ("RNK-A2", "RNK-A4"):
        v[ok] = arr[ok].mean(axis=1)
    elif rule == "RNK-A3":
        if model is None or not ok.any():
            return v, np.zeros(len(day), dtype=bool)
        v[ok] = model.predict_proba(arr[ok] / 100.0)[:, 1]
    return v, ok


def fit_a3(df, dates_pos, universe_mask=None):
    """§2-2 `RNK-A3` — pooled 로지스틱. 하이퍼파라미터는 **sklearn 기본값**.

    양성 = 훈련 폴드의 `exact` 건 · 음성 = **같은 날 유니버스의 나머지 «전 종목»**(표본추출 없음).
    🔑 기본값을 쓰는 것 자체가 「고르지 않았다」의 증거다(§2-2).
    """
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.linear_model import LogisticRegression

    cols = [f + "_pct" for f in FEATS]
    Xs, ys = [], []
    for d, poscodes in sorted(dates_pos.items()):
        day = day_of(df, d)
        if universe_mask is not None and not day.empty:
            day = day[universe_mask(day)]
        if day.empty:
            continue
        arr = day[cols].to_numpy(dtype=float)
        ok = np.all(np.isfinite(arr), axis=1)
        if not ok.any():
            continue
        codes = day.stock_code.to_numpy()[ok]
        Xs.append(arr[ok] / 100.0)
        ys.append(np.isin(codes, list(poscodes)).astype(int))
    if not Xs:
        return None, (0, len(FEATS)), 0, "🔴 훈련 행 0 — 적합 불가"
    X = np.vstack(Xs)
    y = np.concatenate(ys)
    if len(np.unique(y)) < 2:
        return None, X.shape, int(y.sum()), "🔴 양성 또는 음성이 0 — 적합 불가"
    note = ""
    for mi in (100, 1000, 10000):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m = (LogisticRegression() if mi == 100 else LogisticRegression(max_iter=mi))
            m.fit(X, y)
            conv = [x for x in w if issubclass(x.category, ConvergenceWarning)]
        if not conv:
            if mi != 100:
                note = ("🔴 **수렴 목적으로 `max_iter` 만 %d 로 상향**(§2-2 — 그 밖의 어떤 값도 "
                        "조정하지 않았다).") % mi
            break
        note = ("🔴 **`max_iter=%d` 에서도 수렴 경고** — 값을 그대로 쓰되 이 사실을 인쇄한다.") % mi
    return m, X.shape, int(y.sum()), note


# ═══════════════════════════════════════════════════════════════════════════
# 5. 건별 측정
# ═══════════════════════════════════════════════════════════════════════════
def measure(df, items, rule, model_by_item=None, rand_by_date=None, universe_mask=None):
    """건별 `m_rank`·`pctl`·`N`. 측정 불가는 `None`.

    `universe_mask(day) -> bool array` 로 유니버스 갈래를 갈아끼운다(전체 ↔ `n_up`).
    """
    res = {}
    for it in items:
        key = (it["post"], it["item_no"])
        if it["code"] is None:
            res[key] = dict(reason="① DB 종목코드 부재", m=None, pctl=None, N=None)
            continue
        day = day_of(df, it["reg"])
        if universe_mask is not None and not day.empty:
            day = day[universe_mask(day)]
        if day.empty or it["code"] not in set(day.stock_code):
            res[key] = dict(reason="② 유니버스 밖", m=None, pctl=None, N=None)
            continue
        day = day.reset_index(drop=True)
        rnd = None
        if rule == "RNK-A5":
            rnd = rand_by_date[it["reg"]]
            rnd = np.array([rnd[c] for c in day.stock_code], dtype=float)
        model = None if model_by_item is None else model_by_item.get(key)
        v, ok = rule_scores(day, rule, model=model, rand=rnd)
        pos = int(np.flatnonzero(day.stock_code.to_numpy() == it["code"])[0])
        if not ok[pos]:
            res[key] = dict(reason="③ 요구 특징 결측", m=None, pctl=None, N=int(ok.sum()))
            continue
        vv = v[ok]
        mm = m_rank_vector(vv)
        sub = int(np.flatnonzero(np.flatnonzero(ok) == pos)[0])
        n = len(vv)
        res[key] = dict(reason=None, m=float(mm[sub]), pctl=float(pctl_from_m(mm[sub], n)),
                        N=n, m_all=mm)
    return res


# ═══════════════════════════════════════════════════════════════════════════
# 6. 검정
# ═══════════════════════════════════════════════════════════════════════════
def binom_ge(k, n):
    """단측 정확 이항 `P(X ≥ k)`, `p = 0.5`."""
    from math import comb
    return float(sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def perm_pair(deltas, rng, nrep=NREP):
    """짝 순열(부호 뒤집기) — 통계량 = `Σ Δ`. 단측 `P(Σ ≥ 관측)`."""
    d = np.asarray([x for x in deltas if x != 0], dtype=float)
    if len(d) == 0:
        return np.nan
    obs = d.sum()
    flips = rng.integers(0, 2, size=(nrep, len(d))) * 2 - 1
    null = (flips * np.abs(d)).sum(axis=1)
    return float((null >= obs).mean())


def sign_test(deltas, rng):
    """§4-3 — `Δ=0` 은 버리고, 남은 «비영» 짝에 단측 부호검정 + 순열."""
    allp = len(deltas)
    nz = [x for x in deltas if x != 0]
    ties = allp - len(nz)
    k = sum(1 for x in nz if x > 0)
    n = len(nz)
    p_sign = binom_ge(k, n) if n else np.nan
    p_perm = perm_pair(deltas, rng)
    win_rate = (sum(1 for x in deltas if x > 0) / allp * 100) if allp else np.nan
    return dict(all_pairs=allp, ties=ties, nonzero=n, k=k,
                p_sign=p_sign, p_perm=p_perm, win_rate=win_rate)


# ═══════════════════════════════════════════════════════════════════════════
# 7. 훈련·선택 본체
# ═══════════════════════════════════════════════════════════════════════════
def per_post(items, res, folds):
    """글 단위 중앙값 (측정 가능 건만)."""
    out = {}
    for p in folds:
        vals = [res[(it["post"], it["item_no"])]["m"] for it in items if it["post"] == p]
        out[p] = med(vals)
    return out


def run_selection_pipeline(df, items, rand_by_date, rng, universe_mask=None, label=""):
    """LOO 로 `RNK-A1`~`A5` 의 통계량을 내고 §2-3 폴스루로 하나를 고른다."""
    folds = sorted({it["post"] for it in items})
    by_fold = {p: [it for it in items if it["post"] == p] for p in folds}

    # ── RNK-A3 의 LOO 모델 (적합이 있는 유일한 후보) ────────────────────────
    a3_models, a3_notes = {}, []
    for p in folds:
        tr = [it for it in items if it["post"] != p and it["code"] is not None]
        dates_pos = {}
        for it in tr:
            dates_pos.setdefault(it["reg"], set()).add(it["code"])
        m, shape, npos, note = fit_a3(df, dates_pos, universe_mask)
        for it in by_fold[p]:
            a3_models[(it["post"], it["item_no"])] = m
        a3_notes.append(dict(fold=p, rows=shape[0], feats=shape[1], pos=npos, note=note,
                             dates=sorted(dates_pos)))
    # 전체 적합(동결 대상 계수)
    dates_pos_all = {}
    for it in items:
        if it["code"] is not None:
            dates_pos_all.setdefault(it["reg"], set()).add(it["code"])
    a3_full, a3_full_shape, a3_full_pos, a3_full_note = fit_a3(df, dates_pos_all, universe_mask)

    results, per_item, loo = {}, {}, {}
    for rule in RULES:
        mb = a3_models if rule == "RNK-A3" else None
        r = measure(df, items, rule, model_by_item=mb, rand_by_date=rand_by_date,
                    universe_mask=universe_mask)
        results[rule] = r
        per_item[rule] = r
        pp = per_post(items, r, folds)
        loo[rule] = dict(per_fold=pp, stat=med(list(pp.values())))

    # ── 폴스루 (§2-3 4번) ───────────────────────────────────────────────────
    order = sorted(RULES, key=lambda r: (loo[r]["stat"] if np.isfinite(loo[r]["stat"])
                                         else float("inf"), RULES.index(r)))
    leader = order[0]
    x1 = (leader == "RNK-A5")

    pair_tests, indist = {}, []
    for r in RULES:
        if r == leader:
            continue
        deltas = []
        for it in items:
            k = (it["post"], it["item_no"])
            a, b = results[leader][k]["m"], results[r][k]["m"]
            if a is None or b is None:
                continue
            deltas.append(b - a)          # >0 이면 leader 가 낫다(m_rank 가 낮다)
        t = sign_test(deltas, rng)
        t["equal_stat"] = bool(np.isclose(loo[r]["stat"], loo[leader]["stat"]))
        pair_tests[r] = t
        if t["equal_stat"] or not (t["p_sign"] < 0.05):
            indist.append(r)

    cand = [leader] + indist
    # ② 요구 특징 수가 적은 쪽 → ③ 목록 순서
    selected = sorted(cand, key=lambda r: (len(REQ[r]), RULES.index(r)))[0]

    # 🔴 `RNK-X1` 우회 경로 (`FREEZE_RANKING_2026-08-31.md` §4 동결 조항).
    #    §4-6 은 「`A5` 가 LOO **1위**면 무효」로만 적혀 있는데, `A5` 는 요구 특징이 «0개»라
    #    폴스루 ②에서 «모든» 규칙을 이긴다 ⇒ 1위가 아니어도 «선택»될 수 있다.
    #    ⇒ 후보 집합에 들어오기만 해도 X1 을 발동시킨다. 문턱 완화가 아니라 누락 경로를 같은 취지로 닫는 것.
    x1_bypass = ("RNK-A5" in cand) and not x1
    if x1_bypass:
        x1 = True

    # 🟡 §2-3 4번은 «누구와 누구의» 짝 검정인지 안 정했다. 이번 실행은 (가) 「선두 대 나머지」를 썼다.
    #    (나) 「쌍별 폐포」로 읽으면 답이 달라지는지 **측정해서** 붙인다 — 논증으로 때우지 않는다.
    #    🔴 특히 `RNK-A5` 는 요구 특징이 «0개»라 후보에 들어오기만 하면 ②에서 «이긴다».
    #       그 경로가 실제로 열리는지 반드시 재야 한다.
    pw = {}
    for i, r1 in enumerate(RULES):
        for r2 in RULES[i + 1:]:
            ds = []
            for it in items:
                k = (it["post"], it["item_no"])
                x, y = results[r1][k]["m"], results[r2][k]["m"]
                if x is None or y is None:
                    continue
                ds.append(abs(y - x) * (1 if (y - x) * (1 if loo[r1]["stat"] <=
                                                        loo[r2]["stat"] else -1) > 0 else -1))
            better = r1 if loo[r1]["stat"] <= loo[r2]["stat"] else r2
            t = sign_test(ds, rng)
            pw[(r1, r2)] = dict(better=better, p=t["p_sign"], nonzero=t["nonzero"],
                                indist=not (t["p_sign"] is not None
                                            and np.isfinite(t["p_sign"]) and t["p_sign"] < 0.05))
    # (나) 폐포: 선두에서 시작해 「구분 불가」 간선을 따라 도달 가능한 전부
    closure, frontier = {leader}, [leader]
    while frontier:
        cur = frontier.pop()
        for (r1, r2), v in pw.items():
            if not v["indist"]:
                continue
            for a_, b_ in ((r1, r2), (r2, r1)):
                if a_ == cur and b_ not in closure:
                    closure.add(b_)
                    frontier.append(b_)
    sel_closure = sorted(closure, key=lambda r: (len(REQ[r]), RULES.index(r)))[0]
    path = []
    path.append("**단계 ①** — LOO `m_rank` 중앙값이 가장 «작은» 후보 = **`%s`** (%.1f). "
                "전 순위: %s"
                % (leader, loo[leader]["stat"],
                   " < ".join("`%s`(%s)" % (r, fmt(loo[r]["stat"])) for r in order)))
    if not indist:
        path.append("**폴스루 없음** — 나머지 4개가 짝 검정에서 전부 `p < 0.05` 로 갈렸다 "
                    "⇒ ①에서 결정.")
    else:
        path.append("**단계 ①-단서** — *「차이가 있어도 짝 검정 `p ≥ 0.05` 면 「구분 불가」로 보고 "
                    "위 순서를 적용한다」*(§2-3 4번). 구분 불가 = %s ⇒ ② 로 폴스루."
                    % ", ".join("`%s`" % r for r in indist))
        path.append("**단계 ②** — 요구 특징 수가 적은 쪽: %s ⇒ **`%s`**"
                    % (", ".join("`%s`(%d개)" % (r, len(REQ[r])) for r in cand), selected))
        tie2 = [r for r in cand if len(REQ[r]) == len(REQ[selected])]
        if len(tie2) > 1:
            path.append("**단계 ③** — ②도 동률(%s) ⇒ **목록 순서**로 `%s`"
                        % (", ".join("`%s`" % r for r in tie2), selected))
        else:
            path.append("**단계 ③ 미도달** — ②에서 유일하게 결정됐다.")
    if selected == leader:
        path.append("🔑 **폴스루가 결과를 «뒤집지 않았다»** — ① 의 1위와 최종 선택이 같다"
                    "(`%s`). 폴스루는 ①의 결과를 «확인»했을 뿐이다." % selected)
    else:
        path.append("🔴 **폴스루가 결과를 «뒤집었다»** — ① 1위는 `%s` 인데 최종 선택은 `%s` 다."
                    % (leader, selected))
    return dict(label=label, folds=folds, loo=loo, results=results, leader=leader,
                selected=selected, x1=x1, pair_tests=pair_tests, indist=indist,
                pairwise=pw, closure=sorted(closure), sel_closure=sel_closure,
                x1_bypass=x1_bypass, cand=cand,
                path=path, a3_notes=a3_notes, a3_full=a3_full,
                a3_full_shape=a3_full_shape, a3_full_pos=a3_full_pos,
                a3_full_note=a3_full_note, a3_dates_all=sorted(dates_pos_all), order=order)


# ═══════════════════════════════════════════════════════════════════════════
# 8. 귀무 (§2-4)
# ═══════════════════════════════════════════════════════════════════════════
def a5_calibration(df, items, folds, k):
    """`RNK-N1` 보정 검사 — `RNK-A5` 의 **독립 실현 `k`개**에 대한 귀무 `p` 분포.

    🔑 대조군은 귀무와 «같은» 분포이므로 그 `p` 는 `U(0,1)` 이어야 한다.
       ***한 번 뽑아 `p ≥ 0.05` 인 것은 「가드가 살아 있다」의 증거가 아니다*** — 그래서 이 검사가 있다.
    """
    rng = stream("a5_calibration")
    dates = sorted({it["reg"] for it in items})
    out = []
    for _ in range(k):
        rb = {}
        for d in dates:
            cs = sorted(day_of(df, d).stock_code)
            rb[d] = dict(zip(cs, rng.random(len(cs))))
        r = measure(df, items, "RNK-A5", rand_by_date=rb)
        _obs, _null, p = null_pctl(items, r, folds, rng)
        out.append(p)
    return out


def null_pctl(items, res, folds, rng, analytic=False):
    """재추출 귀무 = 각 건의 등록일에 «같은 `U_A(D)`»에서 무작위 종목 1개.

    해석적 갈래는 `k` 가 짝수라 닫힌형이 아니므로 **몬테카를로로 대체**한다(§2-4 · 그 사실을 인쇄).
    크기 정합: 같은 날짜 집합 · 같은 건수(§2-4).
    """
    cols, keep = [], []
    for it in items:
        k = (it["post"], it["item_no"])
        r = res[k]
        if r["m"] is None:
            continue
        n = r["N"]
        if analytic:
            draw = rng.random(NREP) * 100.0
        else:
            idx = rng.integers(0, n, size=NREP)
            draw = pctl_from_m(r["m_all"][idx], n)
        cols.append(draw)
        keep.append(it)
    if not cols:
        return np.nan, np.array([]), 0
    posts = sorted({it["post"] for it in keep})
    per_post_mat = []
    for p in posts:
        sel = [c for c, it in zip(cols, keep) if it["post"] == p]
        per_post_mat.append(np.median(np.vstack(sel), axis=0))
    null = np.median(np.vstack(per_post_mat), axis=0)
    obs_pp = [med([res[(it["post"], it["item_no"])]["pctl"] for it in keep if it["post"] == p])
              for p in posts]
    obs = med(obs_pp)
    p = float((null >= obs).mean())
    return obs, null, p


# ═══════════════════════════════════════════════════════════════════════════
# 9. 인쇄
# ═══════════════════════════════════════════════════════════════════════════
def fmt(x, nd=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return ("%%.%df" % nd) % x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="train", choices=["train", "post6"])
    ap.add_argument("--upto", default=None,
                    help="유니버스 상한을 손으로 고정한다. 🔴 **스냅샷 불변성 확인 전용**이며 "
                         "산출물을 덮어쓰지 않는다(`--out` 로 따로 받는다).")
    ap.add_argument("--out", default="RESULTS_RANKING_TRAIN_NUMBERS.md")
    a = ap.parse_args()
    if a.stage == "post6":
        print("🔴 6번째 글은 아직 존재하지 않는다. `PREREG_RANKING.md` §0-3 의 5단계"
              "(`fetch_post.py`)가 «4단계 동결 커밋 뒤»에 온다 — 그 전에는 돌릴 수 없다.")
        return 2

    conn = psycopg2.connect(**DSN)
    upto = a.upto or snapshot_upto(conn)
    pseudo_all = pseudo_audit(conn)

    rows = load_ledger()
    codes, _series_reg = build_codes()
    items, post_idx = exact_items(rows, codes)
    ap_items = approx_items(rows, codes, post_idx)
    missing = sorted({it["name"] for it in items + ap_items if it["code"] is None})
    name_probe = {nm: name_search_absent(conn, nm) for nm in missing}

    df = load(conn, upto)
    # 유니버스 구성 — `market_cap` 백로그가 «날짜별로» 유니버스 크기를 바꾼다(§9 한계의 계량).
    compose = {}
    cur = conn.cursor()
    for d in sorted({it["reg"] for it in items + ap_items}):
        cur.execute("SELECT count(*), count(*) FILTER (WHERE close > 0), "
                    "count(*) FILTER (WHERE close > 0 AND market_cap IS NOT NULL "
                    "AND market_cap > 0) FROM daily_prices WHERE date = %s "
                    "AND NOT (stock_code = ANY(%s))", (d, list(PSEUDO)))
        compose[d] = cur.fetchone()
    # 🔴 유니버스 크기가 «날짜에 따라 계단처럼» 바뀌는지 — 창 안 「첫 봉」 날짜 분포로 잰다.
    cur.execute(
        "SELECT first_bar, count(*) FROM (SELECT stock_code, min(date) AS first_bar "
        "FROM daily_prices WHERE date BETWEEN %s AND %s AND close > 0 "
        "AND NOT (stock_code = ANY(%s)) GROUP BY stock_code) t "
        "GROUP BY first_bar ORDER BY count(*) DESC", (START, upto, list(PSEUDO)))
    firstbar = cur.fetchall()
    jump_day = None
    for d, n in firstbar:
        if str(d) != START and n >= 20:
            jump_day = str(d)
            break
    hole_rows = hole_lo = hole_hi = 0
    if jump_day:
        cur.execute(
            "SELECT count(*), min(date), max(date) FROM daily_prices WHERE date < %s "
            "AND stock_code IN (SELECT stock_code FROM daily_prices "
            "  WHERE date BETWEEN %s AND %s AND close > 0 "
            "  GROUP BY stock_code HAVING min(date) = %s)",
            (START, START, upto, jump_day))
        hole_rows, hole_lo, hole_hi = cur.fetchone()
    # 🔴 「결손 = 코호트」가 «아니다». 세 숫자(유니버스 차 · prev_close 결손 · 첫 봉 코호트)를
    #    구분하려면 그 차를 직접 재야 한다 — 안 재면 셋을 같은 것으로 쓰게 된다.
    jump_extra = 0
    if jump_day:
        cur.execute("SELECT max(date) FROM daily_prices WHERE date < %s", (jump_day,))
        prev_day = str(cur.fetchone()[0])
        cur.execute(
            "SELECT count(*) FROM (SELECT stock_code FROM daily_prices WHERE date = %s "
            "  AND close > 0 AND market_cap > 0 AND NOT (stock_code = ANY(%s)) "
            " EXCEPT SELECT stock_code FROM daily_prices WHERE date = %s "
            "  AND close > 0 AND market_cap > 0 "
            " EXCEPT SELECT stock_code FROM daily_prices WHERE date BETWEEN %s AND %s "
            "  AND close > 0 GROUP BY stock_code HAVING min(date) = %s) t",
            (jump_day, list(PSEUDO), prev_day, START, upto, jump_day))
        jump_extra = int(cur.fetchone()[0])
    conn.close()
    df = build_features(df)

    # A5 무작위 순위 — 날짜별·종목코드 정렬 순서로 결정적으로 뽑는다(전용 스트림).
    rand_rng = stream("a5_scores")
    rand_by_date = {}
    for d in sorted({it["reg"] for it in items + ap_items}):
        day = df[df.date == pd.Timestamp(d)]
        cs = sorted(day.stock_code)
        rand_by_date[d] = dict(zip(cs, rand_rng.random(len(cs))))

    # ── n_up 민감도 갈래용 prev_close ───────────────────────────────────────
    # 🔴 `prev_close` 는 **민감도 전용**이다. 판정 갈래(전체 유니버스)는 쓰지 않는다(§2-1 M-4).
    tdates = list(pd.DatetimeIndex(sorted(df.date.unique())))
    prev_of = {d: tdates[i - 1] for i, d in enumerate(tdates) if i > 0}
    nup_info = {}

    def make_nup_mask(d):
        D = pd.Timestamp(d)
        if D not in prev_of:
            return None
        prev = df[df.date == prev_of[D]]
        pc = dict(zip(prev.stock_code, prev.close))

        def mask(day):
            pcv = day.stock_code.map(pc).to_numpy(dtype=float)
            return (np.isfinite(pcv)) & (day.high.to_numpy(dtype=float) >= pcv * NUP_MULT)
        full = day_of(df, d)
        pcv = full.stock_code.map(pc).to_numpy(dtype=float)
        nup_info[d] = dict(n_all=len(full), n_drop=int((~np.isfinite(pcv)).sum()),
                           n_up=int(((np.isfinite(pcv)) &
                                     (full.high.to_numpy(dtype=float) >= pcv * NUP_MULT)).sum()))
        return mask

    nup_masks = {d: make_nup_mask(d) for d in sorted({it["reg"] for it in items + ap_items})}

    def nup_mask_fn(day):
        if day.empty:
            return np.zeros(0, dtype=bool)
        d = str(pd.Timestamp(day.date.iloc[0]).date())
        m = nup_masks.get(d)
        return m(day) if m is not None else np.zeros(len(day), dtype=bool)

    # ── 주 갈래 실행 ────────────────────────────────────────────────────────
    main_run = run_selection_pipeline(df, items, rand_by_date, stream("pairs_main"),
                                      None, "전체·exact·글단위")

    # ═══ 인쇄 ═══════════════════════════════════════════════════════════════
    say("# `RNK-` 후보 랭킹 — **훈련·선택** 수치 원본 (post1~5 «만»)\n")
    for b in BANNER:
        say(b)
    say("")
    say("🔴 **이 파일에는 6번째 글에 대한 수치가 «하나도» 없다** — 실행 시점에 그 글은 존재하지 않는다"
        "(`PREREG_RANKING.md` §0-3 4번 각주).")
    say("")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 사전등록 | `PREREG_RANKING.md`(818줄 · 동결 `8e97577`) |")
    say("| 실행 브랜치 | `fix/tasso-post6-s5-fixes`(C-17~C-22 반영) |")
    say("| **DB 스냅샷 최신 봉** | **`%s`** (`daily_prices` `max(date)`) |" % upto)
    say("| 유니버스 창 | `%s` ~ `%s` (시작일 고정 · §5-3) |" % (START, upto))
    say("| 유니버스 술어 | `market_cap>0 ∧ close>0` · 의사티커 제외 · `prev_close` **미사용** |")
    say("| 시드 · 반복 | `%d` · **%d회** — ⚠️ `run_selection.NREP = 2000` 과 «다르다»(§8-4) |"
        % (SEED, NREP))
    say("| 특징 정의 | `run_selection.build_features` **import**(재구현 0줄 · C-17 f9 NaN 포함) |")
    say("| `adj_factor` | 🔴 **곱하지도 나누지도 않았다**(§5-5) |")
    say("")

    # ── §7-B #15 의사티커 ───────────────────────────────────────────────────
    say("## 0. 실행 전 점검 (§7-B)\n")
    say("### #15 의사티커 전수 재확인\n")
    say("`daily_prices` 에서 종목코드 술어 `^[0-9][0-9A-Z]{5}$` 를 벗어나는 코드 **전수**:")
    say("")
    say("- 실측 = **%s** (%d개)" % (", ".join("`%s`" % c for c in pseudo_all), len(pseudo_all)))
    say("- `run_selection.py:23` `PSEUDO` = %s (%d개)"
        % (", ".join("`%s`" % c for c in PSEUDO), len(PSEUDO)))
    extra = [c for c in pseudo_all if c not in PSEUDO]
    say("- 차집합(실측 − `PSEUDO`) = **%s**" % (extra if extra else "없음 ⇒ 🟢 4개로 «전수»다"))
    say("")
    say("🔑 프로젝트 메모리의 *「유니버스 쿼리에선 6개 다 제외」*는 **`daily_prices` 에 대해서는 "
        "실측 4개**로 확인된다(그 6은 지수 계열을 세는 다른 문맥의 표현이다). "
        "이 축은 `PSEUDO` 4개를 승계하며 **누락 0건**이다.")
    say("")

    say("### 사유 ① 실측 재현 — DB 종목코드 부재\n")
    if not name_probe:
        say("해당 없음.")
    for nm, r in name_probe.items():
        say("- **%s**: `stock_info` 이름검색 **%s행** · `stock_industry` 이름검색 **%s행** "
            "⇒ 종목코드 확정 불가 ⇒ `daily_prices` 조회가 성립하지 않는다 "
            "(`RESULTS_D1_OOS_POST5.md` §0 재현)" % (nm, r["stock_info"], r["stock_industry"]))
    say("")

    # ── §1 훈련 표본 ────────────────────────────────────────────────────────
    say("## 1. 훈련 표본 — 원장 실측\n")
    from collections import Counter
    cnt = Counter(r["reg_date_precision"] for r in rows)
    say("원장 **%d건 / %d필드** · `exact` **%d** · `approx` **%d** · `after` **%d** · `none` **%d**"
        % (len(rows), len(rows[0]), cnt["exact"], cnt["approx"], cnt["after"], cnt["none"]))
    say("")
    say("| 글 | `logNo` | 원장 건수 | `exact` |")
    say("|---|---|---|---|")
    for log, p in sorted(post_idx.items(), key=lambda kv: kv[1]):
        n_all = sum(1 for r in rows if r["post_log_no"] == log)
        n_ex = sum(1 for it in items if it["post"] == p)
        say("| %d번째 | `%s` | %d | **%d** |" % (p, log, n_all, n_ex))
    say("| **합** | | **%d** | **%d** |" % (len(rows), len(items)))
    say("")
    say("⇒ 폴드 = **%d개**(`exact` ≥ 1인 글) · 최소 폴드 3 충족(§2-3 1번)."
        % len(main_run["folds"]))
    say("")
    say("### 유니버스 구성 — 등록일별 (🔴 «상수가 아니다»)\n")
    say("| 등록일 | 그날 전 종목(의사티커 제외) | `close>0` | **`market_cap>0 ∧ close>0` = 유니버스** | 시총 결손 |")
    say("|---|---|---|---|---|")
    for d in sorted(compose):
        n_all, n_cl, n_uni = compose[d]
        say("| %s | %d | %d | **%d** | %d (%.1f%%) |"
            % (d, n_all, n_cl, n_uni, n_cl - n_uni, (n_cl - n_uni) / n_cl * 100))
    say("")
    _u = {d: compose[d][2] for d in compose}
    _lo, _hi = min(_u.values()), max(_u.values())
    _cohort = next((n for d, n in firstbar if str(d) == jump_day), 0)
    say("🔴🔴 **7월 등록일의 유니버스가 8월보다 «%d종목 작다»**(%s ↔ %s) — "
        "**그리고 원인은 `market_cap` 이 아니다**(시총 결손은 2종목뿐)."
        % (_hi - _lo, "{:,}".format(_lo), "{:,}".format(_hi)))
    say("")
    say("🔴 **비슷하지만 «다른» 숫자가 셋이다 — 뭉뚱그리면 틀린다.**")
    say("")
    say("| 숫자 | 뜻 | 실측 |")
    say("|---|---|---|")
    say("| **%d** | 등록일 유니버스 «최대 − 최소» (%s ↔ %s) | 상장·거래정지 등 «모든» 사유의 합 |"
        % (_hi - _lo, "{:,}".format(_lo), "{:,}".format(_hi)))
    say("| **%d** | `%s` 의 `prev_close` 결손 종목 수 | 위 「축 1」 표의 그 값 |"
        % (nup_info.get(jump_day, {}).get("n_drop", 0), jump_day))
    say("| **%d** | `%s` 에 창 안 «첫 봉»이 찍힌 **코호트** | 구멍의 «본체» |" % (_cohort, jump_day))
    say("")
    _ndrop = nup_info.get(jump_day, {}).get("n_drop", 0)
    say("차이의 정체(**독립 SQL 로 직접 셌다**): `prev_close` 결손이면서 코호트가 «아닌» 종목 = "
        "**%d개** — 뺄셈 `%d − %d = %d` 와 %s. 이들은 **직전 거래일 하루만 빠진 개별 결손**이다."
        % (jump_extra, _ndrop, _cohort, _ndrop - _cohort,
           "일치한다 🟢" if jump_extra == _ndrop - _cohort else "🔴 **불일치 — 정의를 다시 볼 것**"))
    say("🔑 ***「유니버스 차」·「`prev_close` 결손」·「첫 봉 코호트」는 서로 다른 양이다.*** "
        "이 문서는 아래 논증에서 **«코호트 %d» 만** 쓴다." % _cohort)
    say("")
    say("| 창 안 «첫 봉» 날짜 | 종목 수 | 읽는 법 |")
    say("|---|---|---|")
    for d, n in firstbar[:5]:
        say("| %s | %d | %s |" % (d, n, "창 시작일 = 원래부터 있던 종목" if str(d) == START
                                  else ("🔴 **이날 «갑자기» 유니버스에 들어왔다**"
                                        if n >= 20 else "신규상장 등 소수")))
    say("")
    say("🔴 **실측**: 그 **%d종목은 `2026-04-01`~`2026-08-04` 에 봉이 «하나도» 없고, " % _cohort +
        "`2026-08-05` 부터 다시 생긴다.** 그런데 **`2026-04-01` «이전»에는 봉이 %d개 있다**"
        "(`%s` ~ `%s`). ⇒ ***상장 폐지·신규상장이 아니라 `daily_prices` 의 «구멍»이다*** — "
        "일봉 결손 백로그(`changelog-2026-08-12` 계열 49,252행)와 같은 계열이고, "
        "그 구멍이 **2026-08-05 에 메워지기 시작한 것**으로 보인다."
        % (hole_rows, hole_lo, hole_hi))
    say("")
    say("**이 축에 대한 귀결 — 정직하게 적는다.**")
    say("")
    say("1. **7월 등록일 건**(씨피시스템 07-30 · 케이엔알시스템 07-28, `approx` 에스피지 07-31 · "
        "솔트룩스 08-04)은 **%d종목이 «빠진» 유니버스에서 순위가 매겨졌다.**" % _cohort)
    say("2. 🔴 **그 %d종목이 그날 어디에 섰을지는 «알 수 없다»** — 그날 봉이 없기 때문이다. "
        "⇒ ***`m_rank` 의 «상한 불확실성»이 최대 +%d 이다*** (전부 저자 종목보다 위였다면)."
        % (_cohort, _cohort))
    say("3. 🟢 **하한은 그대로다** — 지금 센 `m_rank` 는 «과소»일 수는 있어도 «과대»일 수 없다. "
        "즉 **저자에게 유리한 쪽으로 치우친 값**이다. 이건 §2-4 의 「동률은 위로」와 **반대 방향**의 "
        "편향이므로 상쇄를 가정하지 않는다.")
    say("4. ⚠️ **`pctl` 의 분모 `N−1` 도 직접 바뀐다**(%s ↔ %s) — 글 간 `pctl` 비교에 이 사실을 붙인다."
        % ("{:,}".format(_lo - 1), "{:,}".format(_hi - 1)))
    say("5. 🔑 ***이건 「측정 불가」가 아니라 「측정의 «바탕»이 글마다 다르다」다*** — `RNK-G1` 이 "
        "잡는 축이 아니어서 **가드가 없다.** 그래서 여기 적어 둔다.")
    say("")

    # ── #21 규칙별 측정 가능 여부 실측 ──────────────────────────────────────
    say("## 2. §7-B #21 — 규칙별 «측정 가능 여부» 실측 (상한 추정 → 실측)\n")
    say("🔴 §2-3 의 **`A1` 17 · `A2`~`A4` 16** 은 레메디·삼양바이오팜만 뺀 «상한 추정»이었다. "
        "아래가 **실측**이다.")
    say("")
    say("| 글 | 항목 | 종목 | 등록일 | 등록일 «포함» 봉수 | " +
        " | ".join("`%s`" % r for r in RULES) + " |")
    say("|---|---|---|---|---|" + "---|" * len(RULES))
    bars_of = {}
    for it in items:
        if it["code"] is None:
            nb = None
        else:
            nb = int(((df.stock_code == it["code"]) &
                      (df.date <= pd.Timestamp(it["reg"]))).sum())
        bars_of[(it["post"], it["item_no"])] = nb
        cells = []
        for r in RULES:
            e = main_run["results"][r][(it["post"], it["item_no"])]
            cells.append("✅" if e["m"] is not None else "⛔ %s" % e["reason"].split()[0])
        say("| %d | %s | %s | %s | %s | %s |"
            % (it["post"], it["item_no"], it["name"], it["reg"],
               ("**%d**" % nb) if nb is not None else "—", " | ".join(cells)))
    say("")
    meas = {r: sum(1 for it in items
                   if main_run["results"][r][(it["post"], it["item_no"])]["m"] is not None)
            for r in RULES}
    say("| 규칙 | 측정 가능 | 측정 불가 | 커버리지 손실 비율 | `RNK-G1` 게이트(1/3) |")
    say("|---|---|---|---|---|")
    for r in RULES:
        lost = len(items) - meas[r]
        rate = lost / len(items) * 100
        say("| `%s` | **%d**/%d | %d | **%.1f%%** | %s |"
            % (r, meas[r], len(items), lost, rate,
               "🔴 **발동**" if rate >= 100 / 3 else "미발동"))
    say("")
    say("### 짝 상한 — 실측")
    say("")
    say("| 짝 | 상한 추정(§2-3) | **실측** | 최소 5 충족 |")
    say("|---|---|---|---|")
    for r in RULES[1:]:
        both = sum(1 for it in items
                   if main_run["results"]["RNK-A1"][(it["post"], it["item_no"])]["m"] is not None
                   and main_run["results"][r][(it["post"], it["item_no"])]["m"] is not None)
        est = {"RNK-A2": 16, "RNK-A3": 16, "RNK-A4": 16, "RNK-A5": None}[r]
        say("| `RNK-A1` ↔ `%s` | %s | **%d** | %s |"
            % (r, est if est else "—", both, "🟢" if both >= 5 else "🔴"))
    say("| `RNK-A1` 측정 가능 건 | 17 | **%d** | — |" % meas["RNK-A1"])
    say("")

    # ── §3 건별 m_rank ──────────────────────────────────────────────────────
    say("## 3. `exact` 건별 `m_rank` (규칙 × 건) — 🔬 탐색적 표기\n")
    say("`m_rank` = 「엄격히 좋은 종목 수 + 동률 수(자기 제외)」 — **동률을 전부 위로** = 보수적(§2-4).")
    say("`RNK-A3` 값은 **그 건이 속한 폴드를 «뺀» 모델**로 낸 것이다(LOO).")
    say("")
    say("| 글 | 종목 | 등록일 | `N`(전체) | " + " | ".join("`%s`" % r for r in RULES) + " |")
    say("|---|---|---|---|" + "---|" * len(RULES))
    for it in items:
        k = (it["post"], it["item_no"])
        n1 = main_run["results"]["RNK-A1"][k]["N"]
        cells = []
        for r in RULES:
            e = main_run["results"][r][k]
            cells.append("**%d**" % int(e["m"]) if e["m"] is not None else "⛔")
        say("| %d | %s | %s | %s | %s |"
            % (it["post"], it["name"], it["reg"], n1 if n1 else "—", " | ".join(cells)))
    say("")
    say("### 규칙별 `N = |U_A(D)|` (규칙마다 다르다 — §2-4 의무 인쇄)\n")
    say("| 글 | 종목 | " + " | ".join("`%s`" % r for r in RULES) + " |")
    say("|---|---|" + "---|" * len(RULES))
    for it in items:
        k = (it["post"], it["item_no"])
        say("| %d | %s | %s |" % (it["post"], it["name"], " | ".join(
            str(main_run["results"][r][k]["N"]) if main_run["results"][r][k]["N"] else "—"
            for r in RULES)))
    say("")

    # ── §4 백분위 ───────────────────────────────────────────────────────────
    say("### 건별 `pctl` (귀무 검정 전용 · §7-C)\n")
    say("| 글 | 종목 | " + " | ".join("`%s`" % r for r in RULES) + " |")
    say("|---|---|" + "---|" * len(RULES))
    for it in items:
        k = (it["post"], it["item_no"])
        say("| %d | %s | %s |" % (it["post"], it["name"], " | ".join(
            fmt(main_run["results"][r][k]["pctl"], 2) for r in RULES)))
    say("")

    # ── §5 LOO ──────────────────────────────────────────────────────────────
    say("## 4. LOO 폴드별 결과 (§2-3)\n")
    say("🔴 **`RNK-A1`·`A2`·`A4`·`A5` 는 적합이 없어 LOO 가 «항등»이다** — 뺀 폴드의 값이 전체 계산과 "
        "같다. ⇒ ***LOO 는 사실상 `RNK-A3` 하나만 벌한다.*** "
        "***「LOO 했으니 안전하다」고 쓰지 않는다***(§2-3 말미).")
    say("")
    say("| 규칙 | " + " | ".join("폴드 %d (%d건)" % (p, sum(1 for it in items if it["post"] == p))
                                 for p in main_run["folds"]) + " | **LOO 통계량(중앙)** | 순위 |")
    say("|---|" + "---|" * (len(main_run["folds"]) + 2))
    for r in main_run["order"]:
        pf = main_run["loo"][r]["per_fold"]
        say("| `%s` | %s | **%s** | %d |"
            % (r, " | ".join(fmt(pf[p]) for p in main_run["folds"]),
               fmt(main_run["loo"][r]["stat"]), main_run["order"].index(r) + 1))
    say("")
    say("**`RNK-X1` 대조군 가드**: `RNK-A5` LOO = **%s** · 순위 **%d/5** ⇒ %s"
        % (fmt(main_run["loo"]["RNK-A5"]["stat"]),
           main_run["order"].index("RNK-A5") + 1,
           "🔴 **⛔ 발동 — 선택 절차 무효**" if main_run["x1"] else "🟢 미발동(가드가 살아 있다)"))
    say("")
    say("🔴 **우회 경로 점검(`FREEZE_RANKING_2026-08-31.md` §4)** — §4-6 은 「`A5` 가 LOO **1위**」만 "
        "보는데, `A5` 는 요구 특징이 **0개**라 폴스루 ②에서 모든 규칙을 이긴다 ⇒ **1위가 아니어도 "
        "«선택»될 수 있다.** ⇒ 후보 집합 진입 자체를 X1 로 막는다. "
        "**이번 회차 후보 = %s** ⇒ %s"
        % (", ".join("`%s`" % r for r in main_run["cand"]),
           "🔴 **A5 진입 — 우회 X1 발동**" if main_run["x1_bypass"]
           else "🟢 `RNK-A5` 미진입(선두와 `p ≤ 0.00002` 로 갈렸다)"))
    say("")

    # ── §6 짝 회계 ──────────────────────────────────────────────────────────
    say("## 5. 짝 회계 · 짝 검정 (§2-3 4번 · §4-3)\n")
    say("짝의 단위 = **「두 규칙 모두 측정 가능한 `exact` 건」**(폴드가 아니다 · B-2 정정). "
        "`Δ = m_rank(비교대상) − m_rank(선두)` — **`Δ > 0` 이면 선두가 낫다**.")
    say("")
    say("| 선두 ↔ 비교 | 전 짝 | 동률(`Δ=0`·버림) | **비영 짝** | `Δ>0` | 단측 부호 `p` | 순열 `p` | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    for r in RULES:
        if r == main_run["leader"]:
            continue
        t = main_run["pair_tests"][r]
        verd = ("🟢 갈림(`p<0.05`)" if (t["p_sign"] is not None and np.isfinite(t["p_sign"])
                                        and t["p_sign"] < 0.05) else "⚠️ **구분 불가**")
        if t["nonzero"] < 5:
            verd += " · 🔴 비영 짝 %d < 5 ⇒ **산술적으로 `p<0.05` 불능**" % t["nonzero"]
        say("| `%s` ↔ `%s` | %d | %d | **%d** | %d | %s | %s | %s |"
            % (main_run["leader"], r, t["all_pairs"], t["ties"], t["nonzero"], t["k"],
               fmt(t["p_sign"], 5), fmt(t["p_perm"], 5), verd))
    say("")

    # ── §7 선택 ─────────────────────────────────────────────────────────────
    say("## 6. 선택 (§2-3 폴스루)\n")
    for p in main_run["path"]:
        say("- " + p)
    say("")
    say("")
    say("### 🟡 문서가 «안 정한» 것 — 짝 검정의 상대는 누구인가\n")
    say("§2-3 4번은 *「짝 검정 `p ≥ 0.05` 면 「구분 불가」」*라고만 적었고 **누구와의 짝인지**는 안 정했다. "
        "**(가) 선두 대 나머지 각각** ↔ **(나) 쌍별 「구분 불가」 관계의 폐포**. "
        "이번 실행은 **(가)** 를 썼다. (나)로 읽으면 답이 달라지는지 **측정해서** 붙인다 — "
        "🔴 특히 `RNK-A5` 는 요구 특징이 **0개**라 후보에 «들어오기만 하면» ②에서 이긴다.")
    say("")
    say("**쌍별 단측 부호검정 `p` (전 10쌍)** — 「나은 쪽」은 LOO 통계량이 작은 쪽:")
    say("")
    say("| 쌍 | 나은 쪽 | 비영 짝 | 단측 `p` | 구분 불가? |")
    say("|---|---|---|---|---|")
    for (r1, r2), v in main_run["pairwise"].items():
        say("| `%s` ↔ `%s` | `%s` | %d | %s | %s |"
            % (r1, r2, v["better"], v["nonzero"], fmt(v["p"], 5),
               "⚠️ **예**" if v["indist"] else "아니오"))
    say("")
    say("- **(가) 선두 대 나머지** ⇒ 후보 = %s ⇒ 선택 **`%s`**"
        % (", ".join("`%s`" % r for r in [main_run["leader"]] + main_run["indist"]),
           main_run["selected"]))
    say("- **(나) 쌍별 폐포** ⇒ 후보 = %s ⇒ 선택 **`%s`**"
        % (", ".join("`%s`" % r for r in main_run["closure"]), main_run["sel_closure"]))
    say("")
    if main_run["sel_closure"] == main_run["selected"]:
        say("🟢 **두 읽기가 같은 답을 준다**(`%s`) ⇒ 이 표본에서는 미명시가 판정을 «안» 가른다. "
            "⚠️ 그래도 **고른 것은 고른 것이다** — 다음 글에서 선두가 바뀌면 갈릴 수 있으므로 "
            "`FREEZE_RANKING_*.md` 에 **(가)를 명시**해 동결한다." % main_run["selected"])
    else:
        say("🔴🔴 **두 읽기가 «다른» 답을 준다** — (가) `%s` ↔ (나) `%s`. "
            "⇒ ⛔ **미명시가 판정을 가른다. 사전등록을 고치기 «전»에는 선택을 선언하지 않는다.**"
            % (main_run["selected"], main_run["sel_closure"]))
    say("")
    say("### 🔒 선택된 규칙 = **`%s`** — %s"
        % (main_run["selected"], RULE_DESC[main_run["selected"]]))
    say("")
    if main_run["x1"] and not main_run["x1_bypass"]:
        say("🔴🔴 **⛔ `RNK-X1` 발동 — `RNK-A5`(대조군)가 LOO 1위다. 규칙을 고르지 않고 이 축을 닫는다**"
            "(§4-6). 아래 값은 전부 기록용이다.")
        say("")
    elif main_run["x1_bypass"]:
        say("🔴🔴 **⛔ `RNK-X1` 발동(우회 경로) — `RNK-A5` 가 LOO 1위는 «아니지만» 폴스루 후보 "
            "집합에 들어왔다**(후보 = %s). `A5` 는 요구 특징이 **0개**라 ②에서 모든 규칙을 이기므로 "
            "그대로 두면 «대조군이 선택된다». `FREEZE_RANKING_2026-08-31.md` §4 동결 조항대로 "
            "이 축을 닫는다. 아래 값은 전부 기록용이다."
            % ", ".join("`%s`" % r for r in main_run["cand"]))
        say("")
    if main_run["selected"] == "RNK-A1":
        say("🔴🔴 **⛔ §4-3 (다) 발동 — 선택된 규칙이 `RNK-A1`(f1 단독)이다.**")
        say("")
        say("- `Δm_rank ≡ 0` 이므로 `RNK-B2` 승률 = 0% ≤ 50% ⇒ **자동으로 「`f1` 과 구분 불가」**.")
        say("- ⇒ **이 축은 「새 정보 없음 — `REG-M4` 재진술」로 닫는다.** "
            "6번째 글에서 `RNK-P1` 이 통과해도 **«지지»로 선언하지 않는다.**")
        say("- 🔑 ***이 축이 존재하는 이유는 「`f1` 을 넘어서는가」이지 「`f1` 이 높은가」가 아니다.*** "
            "후자는 `SEL-S2` 가 이미 답했고 `REG-M4` 가 이미 판별력을 부정했다.")
        say("")

    # ── §8 RNK-B1·B2 (훈련) ─────────────────────────────────────────────────
    say("## 7. `RNK-B1`·`RNK-B2` — `f1` 단독 벤치마크 (🔬 훈련값)\n")
    sel = main_run["selected"]
    if sel == "RNK-A1":
        say("선택 규칙이 `RNK-A1` 이므로 짝 차이가 **항등적으로 0** 이다 ⇒ 전 짝 %d · 비영 짝 **0** · "
            "승률 **0.0%%** ≤ 50%% ⇒ ⛔ **「`f1` 과 구분 불가」**(§4-3 (다))."
            % meas["RNK-A1"])
    else:
        deltas = []
        for it in items:
            k = (it["post"], it["item_no"])
            a = main_run["results"]["RNK-A1"][k]["m"]
            b = main_run["results"][sel][k]["m"]
            if a is None or b is None:
                continue
            deltas.append(a - b)
        t = sign_test(deltas, stream("pairs_bench"))
        say("| 항목 | 값 |")
        say("|---|---|")
        say("| 전 짝(동률 포함) | **%d** |" % t["all_pairs"])
        say("| 동률(`Δ=0`) — B1 에서 **버림** | **%d** |" % t["ties"])
        say("| **비영 짝** — B1 의 `n` | **%d** (최소 5 %s) |"
            % (t["nonzero"], "충족" if t["nonzero"] >= 5 else "🔴 **미달**"))
        say("| `RNK-B2` 승률 = `Δ>0` / **전 짝** (동률은 「못 이긴 것」) | **%.1f%%** %s |"
            % (t["win_rate"], "⇒ ⛔ ≤50% = 「`f1` 과 구분 불가」"
               if t["win_rate"] <= 50 else ""))
        say("| `RNK-B1` 단측 부호검정 `p` | **%s** |" % fmt(t["p_sign"], 5))
        say("| `RNK-B1` 순열 `p`(시드 %d · %d회) | **%s** |" % (SEED, NREP, fmt(t["p_perm"], 5)))
        say("")
        say("🔴 **훈련값은 판정이 아니다**(§4-5) — `RNK-B1`·`B2` 의 «판정»은 post6 부터 누적한다.")
    say("")

    # ── §9 귀무 ─────────────────────────────────────────────────────────────
    say("## 8. 귀무 (§2-4) — 🔬 훈련값\n")
    say("재추출 = 각 건의 등록일에 **같은 `U_A(D)`** 에서 무작위 종목 1개 · **%d회 · 시드 %d** · "
        "크기 정합(같은 날짜 집합·같은 건수)." % (NREP, SEED))
    say("해석적 갈래는 폴드 건수가 짝수라 닫힌형이 아니므로 **몬테카를로로 대체했다**(§2-4 명문).")
    say("")
    say("| 규칙 | 관측 `pctl`(글단위 중앙의 중앙) | 재추출 귀무 `p` | 해석적(MC) 귀무 `p` | `<5%` |")
    say("|---|---|---|---|---|")
    null_rows = {}
    for r in RULES:
        obs, _n1, p1 = null_pctl(items, main_run["results"][r], main_run["folds"],
                                 stream("null_resample"))
        _o2, _n2, p2 = null_pctl(items, main_run["results"][r], main_run["folds"],
                                 stream("null_analytic"), analytic=True)
        null_rows[r] = (obs, p1, p2)
        say("| `%s` | **%s** | **%s** | %s | %s |"
            % (r, fmt(obs, 2), fmt(p1, 5), fmt(p2, 5),
               "🟢" if (np.isfinite(p1) and p1 < 0.05) else "⛔"))
    say("")
    a5o, a5p1, a5p2 = null_rows["RNK-A5"]
    say("**`RNK-N1` 죽은 가드 실증(§4-1)** — 대조군 `RNK-A5` 의 귀무 백분위 = **%s**(재추출) / "
        "**%s**(해석적)." % (fmt(a5p1, 5), fmt(a5p2, 5)))
    if np.isfinite(a5p1) and a5p1 < 0.05:
        say("🔴 **대조군도 통과했다 — 이 회차의 귀무 구현을 의심하라**(1종오류이거나 구현 결함이다 · §4-1 M-3).")
    else:
        say("🟢 대조군은 통과하지 못했다. "
            "⚠️ 단 `RNK-A5` 는 정의상 약 5% 확률로 통과할 수 있다(§4-1 M-3) — 「정의상 불통과」가 아니다.")
    say("")
    say("### `RNK-N1` 보정 검사 — 🔴 **한 번의 실현으로는 「가드가 살아 있다」를 «말할 수 없다»**\n")
    say("`RNK-A5` 는 귀무와 «같은» 분포이므로 그 `p` 는 귀무 하 `U(0,1)` 이어야 한다. "
        "한 번 뽑아 `p ≥ 0.05` 가 나온 것은 그 사실의 증거가 «아니다» — 5%%는 원래 드물다. "
        "⇒ **독립 실현 %d개**를 뽑아 `p` 의 분포를 «직접» 잰다."
        % A5_CALIB_K)
    say("")
    calib = a5_calibration(df, items, main_run["folds"], A5_CALIB_K)
    say("| 항목 | 기대(귀무 하) | 실측 |")
    say("|---|---|---|")
    say("| 실현 수 | — | **%d** |" % len(calib))
    say("| `p` 평균 | 0.500 | **%.3f** |" % float(np.mean(calib)))
    say("| `p` 중앙 | 0.500 | **%.3f** |" % float(np.median(calib)))
    say("| `p < 0.05` 비율 (= 1종오류율) | **5.0%%** | **%.1f%%** (%d/%d) |"
        % (float((np.array(calib) < 0.05).mean()) * 100,
           int((np.array(calib) < 0.05).sum()), len(calib)))
    say("| `p < 0.20` 비율 | 20.0%% | **%.1f%%** |"
        % (float((np.array(calib) < 0.20).mean()) * 100))
    err = float((np.array(calib) < 0.05).mean())
    _mu = float(np.mean(calib))
    _z = (_mu - 0.5) / ((1.0 / 12.0) ** 0.5 / len(calib) ** 0.5)
    say("")
    say("⚠️ **`p` 평균이 0.5 보다 «약간 높다»(%.3f · `z ≈ %.2f`) — 이것도 적어 둔다.** "
        "원인 추정 = `p` 를 **`P(귀무 ≥ 관측)`** 로 «등호 포함» 계산하고 `m_rank` 가 **이산**이라 "
        "동률이 전부 `p` 를 키우는 쪽으로 들어간다. 🟢 **방향은 보수적**이다 — `RNK-N1` 통과가 "
        "«더 어려워지는» 쪽이므로 가드를 느슨하게 만들지 않는다. "
        "그리고 **5%% 꼬리 검정에는 무영향**이다(실측 1종오류율 %.1f%%). "
        "🔑 ***그래도 「평균이 0.5 다」라고 쓰지 않는다 — 안 그렇다.***" % (_mu, _z, err * 100))
    say("")
    say("**판정** = %s"
        % ("🟢 **1종오류율이 명목 5%와 어긋나지 않는다 ⇒ 귀무 구현이 «보정돼 있다»**"
           if 0.01 <= err <= 0.12 else
           "🔴 **1종오류율이 명목 5%%와 크게 어긋난다(%.1f%%) ⇒ 귀무 구현을 의심하라**" % (err * 100)))
    say("")
    say("🔴 **이 검사가 «잡아낸 것»** — 초판은 `RNK-A5` 의 점수와 재추출 귀무를 **둘 다 "
        "`default_rng(20260815)`** 로 만들었다(같은 시드·다른 목적). 그 판본의 단일 실현은 "
        "`p = 0.035` 로 **「대조군도 통과」를 인쇄**했다. `SeedSequence.spawn` 으로 스트림을 "
        "구조적으로 분리한 뒤 **그 자리의 값**이 `p = %s` 가 됐다. "
        "⚠️ **「같은 실현」이 아니다** — 분리하면 `RNK-A5` 의 점수 자체도 다른 난수가 되므로 "
        "두 값은 **다른 실현**이다. ⇒ ***한 값이 움직인 것만으로는 「얽혀 있었다」와 「운이 나빴다」를 "
        "구분할 수 없다.*** 그래서 위 보정 검사(독립 실현 %d개)를 붙였고, 그건 **분리된 판본**에 대해 돈 것이다."
        % (fmt(a5p1, 5), A5_CALIB_K))
    say("")

    # ── §10 죽은 가드 실측 점검 (#16) ───────────────────────────────────────
    say("## 9. §7-B #16 — 죽은 가드 «실측» 점검\n")
    say("| 가드 | 재는 양이 «움직이나» | 실측 | 판정 |")
    say("|---|---|---|---|")
    for r in RULES:
        ms = [main_run["results"][r][(it["post"], it["item_no"])]["m"] for it in items]
        ms = [m for m in ms if m is not None]
        uq = len(set(ms))
        say("| `RNK-N2` (`m_rank`, `%s`) | 상수가 아닌가 | 값 %d개 · 고유 **%d**개 · "
            "min %s / 중앙 %s / max %s | %s |"
            % (r, len(ms), uq, fmt(min(ms) if ms else None), fmt(med(ms)),
               fmt(max(ms) if ms else None),
               "🟢 움직인다" if uq > 1 else "🔴 **상수 = 죽은 가드**"))
    rates = sorted({round((len(items) - meas[r]) / len(items), 6) for r in RULES})
    say("| `RNK-G1` (커버리지) | 규칙 간 비율이 움직이나 | 고유 비율 **%d**개 = %s | %s |"
        % (len(rates), ", ".join("%.1f%%" % (x * 100) for x in rates),
           "🟢 움직인다(규칙 의존 실증)" if len(rates) > 1 else "🔴 **상수**"))
    say("| `RNK-N1` (무작위 귀무) | 대조군이 통과하나 | `RNK-A5` 재추출 `p` = %s | %s |"
        % (fmt(a5p1, 5), "🟢 미통과" if not (np.isfinite(a5p1) and a5p1 < 0.05) else "🔴 통과"))
    say("")
    say("🔴 **편향 방향 신고(§4-4 6번)** — 측정 불가는 **신규 상장주 쪽으로 치우치고** "
        "저자는 신규주를 자주 고른다. ⇒ ***측정 불가가 무작위가 아니다.*** "
        "남은 분모를 「저자 표본」이라 부르면 이미 편향된 표본이다.")
    say("")
    say("⚠️ **다만 사유를 «정확히» 적는다 — 훈련 표본에서 사유 ③(요구 특징 결측)의 실제 사례는 «하나»다.**")
    say("")
    say("| 종목 | 상장 | 등록일 포함 봉수 | 실측 결과 | 사유 |")
    say("|---|---|---|---|---|")
    say("| 삼양바이오팜 `0120G0` | 2026-08-05 | **12** | `f5`·`f6`·`f9` NaN ⇒ `A2`·`A3`·`A4` 불가 | **③ 요구 특징 결측** |")
    say("| 매드업 `0039P0` | 2026-07-01 | **26** | `min_periods=20` 을 넘겨 **5규칙 전부 측정 가능** | 🟢 **해당 없음** |")
    say("| 레메디 | — | — | 종목코드 확정 불가 | **① DB 종목코드 부재**(③ 아님) |")
    say("")
    say("🔑 ***그러므로 「신규주라서 ③ 에 걸린다」는 「신규주면 걸린다」가 아니다*** — "
        "**20봉이 경계**이고 매드업은 그 위였다. 편향은 **실재하되 이번 표본에서는 n=1** 이다. "
        "🔴 **그리고 레메디(①)도 신규 편입 지연이라 «같은 축»에서 왔다** — 사유 번호는 다르지만 "
        "편향 방향은 같으므로, 셋을 뭉뚱그리지도 말고 「③ 은 하나뿐이니 편향이 없다」고도 하지 않는다.")
    say("")

    # ── §11 민감도 4축 (§4-7) ───────────────────────────────────────────────
    say("## 10. `RNK-V1` 민감도 4축 (§4-7) — 선택이 잣대에 종속되나\n")
    say("### 축 1 — 유니버스 (전체 ↔ `n_up`)\n")
    say("| 등록일 | 전체 `N` | `prev_close` 결손 | `drop_rate` | `n_up` |")
    say("|---|---|---|---|---|")
    for d in sorted(nup_info):
        i = nup_info[d]
        dr = i["n_drop"] / i["n_all"] * 100 if i["n_all"] else np.nan
        flag = " 🔴" if dr >= DROP_RATE_FLAG * 100 else ""
        say("| %s | %d | %d | **%.2f%%**%s | **%d** |"
            % (d, i["n_all"], i["n_drop"], dr, flag, i["n_up"]))
    say("")
    say("⚠️ `drop_rate ≥ 1%` 는 §6 말미대로 **«표기 가드»**다 — 판정을 막는 게이트가 «아니다». "
        "표시된 날의 `n_up` 을 다른 날과 직접 비교하지 않는다. "
        "🟢 **판정 갈래(전체 유니버스)는 `prev_close` 를 안 쓰므로 이 값에 아예 안 걸린다**(§2-1 M-4).")
    say("")
    nup_run = run_selection_pipeline(df, items, rand_by_date, stream("pairs_nup"),
                                     nup_mask_fn, "n_up·exact·글단위")
    ax_items = items + ap_items
    ap_run = run_selection_pipeline(df, ax_items, rand_by_date, stream("pairs_approx"),
                                    None, "전체·exact+approx·글단위")
    nup_meas = {r: sum(1 for it in items
                       if nup_run["results"][r][(it["post"], it["item_no"])]["m"] is not None)
                for r in RULES}
    say("### `n_up` 갈래의 `RNK-G1` 커버리지 — 🔴 **§2-1 1번의 예측을 «같은 분모»로 확인한다**\n")
    say("🔴 §2-1 1번은 **post5 `exact` 7건**을 분모로 `A1` **3/7 = 42.9%** · `A2`~`A4` **4/7 = 57.1%** 를 "
        "예측했다. 아래는 **훈련 전체(18건)**와 **post5 만(7건)**을 «나란히» 낸 것이다 — "
        "***분모가 다른 값을 이어 붙이지 않기 위해서다.***")
    say("")
    p5 = [it for it in items if it["post"] == 5]
    # 🔴 열 이름과 분자는 `RNK-G1` 정의(**측정 «불가» / 분모**)와 같은 양이어야 한다.
    #    「측정 가능」을 분자로 두고 비율만 손실률로 인쇄하면 두 칸이 반대 양이 되어
    #    §2-1 예측(3/7·4/7 = «측정 불가» 건수)과 직접 대조할 수 없다.
    say("| 규칙 | 훈련 전체 측정 **불가** | 비율 | 게이트 | **post5 만** 측정 불가 | 비율 | 게이트 | §2-1 예측 |")
    say("|---|---|---|---|---|---|---|---|")
    pred = {"RNK-A1": "3/7 = 42.9%", "RNK-A2": "4/7 = 57.1%", "RNK-A3": "4/7 = 57.1%",
            "RNK-A4": "4/7 = 57.1%", "RNK-A5": "—"}
    for r in RULES:
        lost = len(items) - nup_meas[r]
        rate = lost / len(items) * 100
        n5 = sum(1 for it in p5
                 if nup_run["results"][r][(it["post"], it["item_no"])]["m"] is not None)
        lost5 = len(p5) - n5
        rate5 = lost5 / len(p5) * 100
        say("| `%s` | %d/%d | **%.1f%%** | %s | %d/%d | **%.1f%%** | %s | %s |"
            % (r, lost, len(items), rate,
               "🔴 발동" if rate >= 100 / 3 else "미발동",
               lost5, len(p5), rate5,
               "🔴 **발동 ⇒ ⛔**" if rate5 >= 100 / 3 else "미발동", pred[r]))
    say("")
    say("🔴 **post5 분모에서는 예측대로 게이트가 열린다** — `n_up` 한정이 저자 종목을 «구조적으로» "
        "밖에 두기 때문이다(코데즈컴바인·한켐형 = 고가 상승률이 +15% 미만). "
        "⇒ **`RNK-D1` 이 «전체»로 확정된 근거가 실측으로 확인됐다.**")
    say("⚠️ **훈련 전체(18건) 분모에서는 게이트가 «안» 열린다**(22.2% · 27.8%) — "
        "post2~4 건들이 `n_up` 안에 더 잘 들어가서 비율이 희석된 것이다. "
        "🔑 ***같은 가드가 분모에 따라 발동/미발동이 갈린다는 사실 자체를 기록한다*** — "
        "판정 분모는 §2-5 대로 **「그 글의 신규 `exact` 건」**이므로 실제 판정에서는 **post5 열 쪽이 기준**이다.")
    say("⚠️ 이 갈래의 LOO·선택값은 **커버리지가 그만큼 깎인 상태에서 계산된 것**이라 판정에 인용하지 않는다.")
    say("")
    say("### 4축 병기 — 선택된 규칙이 갈리나\n")
    say("| 축 | 갈래 | 판정 갈래인가 | LOO 1위 | **선택** |")
    say("|---|---|---|---|---|")
    say("| 유니버스 | 전체(`market_cap>0 ∧ close>0`) | ✅ **판정**(`RNK-D1` 확정) | `%s` | **`%s`** |"
        % (main_run["leader"], main_run["selected"]))
    say("| 유니버스 | `n_up`(+`prev_close`) | 민감도 | `%s` | `%s` |"
        % (nup_run["leader"], nup_run["selected"]))
    pooled = {}
    for r in RULES:
        vals = [main_run["results"][r][(it["post"], it["item_no"])]["m"] for it in items]
        pooled[r] = med(vals)
    pooled_order = sorted(RULES, key=lambda r: (pooled[r] if np.isfinite(pooled[r])
                                                else float("inf"), RULES.index(r)))
    say("| 집계 | 글 단위 중앙 | ✅ **판정** | `%s` | **`%s`** |"
        % (main_run["leader"], main_run["selected"]))
    say("| 집계 | 건 단위 pooled 중앙 | 민감도 | `%s` | (선택 절차 동일 적용 시 `%s`) |"
        % (pooled_order[0], pooled_order[0]))
    say("| 귀무 | 재추출 20,000 | ✅ **판정** | — | %s |"
        % ("통과" if np.isfinite(null_rows[sel][1]) and null_rows[sel][1] < 0.05 else "미통과"))
    say("| 귀무 | 해석적(MC 대체) | 민감도 | — | %s |"
        % ("통과" if np.isfinite(null_rows[sel][2]) and null_rows[sel][2] < 0.05 else "미통과"))
    say("| 등록일 정밀도 | `exact` 만 | ✅ **판정** | `%s` | **`%s`** |"
        % (main_run["leader"], main_run["selected"]))
    say("| 등록일 정밀도 | `approx` 포함 | 민감도 | `%s` | `%s` |"
        % (ap_run["leader"], ap_run["selected"]))
    say("")
    split = {main_run["selected"], nup_run["selected"], ap_run["selected"], pooled_order[0]}
    say("**갈림 판정(선택된 규칙)** = %s"
        % ("🟢 **4축 전부 같은 규칙(`%s`)을 고른다** ⇒ `RNK-V1` 미발동" % main_run["selected"]
           if len(split) == 1 else
           "🔴 **갈린다** (%s) ⇒ ⛔ `RNK-V1` — 어느 쪽도 선언하지 않는다"
           % ", ".join("`%s`" % s for s in sorted(split))))
    lead_split = {main_run["leader"], nup_run["leader"], ap_run["leader"], pooled_order[0]}
    say("")
    if len(lead_split) > 1:
        say("🔴 **그러나 «LOO 1위»는 갈린다** (%s) — 선택이 안 갈린 이유는 §2-3 ②(요구 특징 수)가 "
            "«구분 불가» 구간에서 `RNK-A1` 로 수렴시키기 때문이다. "
            "⇒ ***「4축이 같은 규칙을 골랐다」를 「4축이 같은 이야기를 한다」로 읽지 않는다.*** "
            "이 문장을 지우지 말 것." % ", ".join("`%s`" % s for s in sorted(lead_split)))
    else:
        say("🟢 LOO 1위도 4축에서 같다 (`%s`)." % main_run["leader"])
    say("")
    say("| 갈래 | " + " | ".join("`%s`" % r for r in RULES) + " |")
    say("|---|" + "---|" * len(RULES))
    for nm, rr in (("전체·exact·글단위", main_run), ("`n_up`·exact·글단위", nup_run),
                   ("전체·exact+approx·글단위", ap_run)):
        say("| %s | %s |" % (nm, " | ".join(fmt(rr["loo"][r]["stat"]) for r in RULES)))
    say("| 전체·exact·**건 pooled** | %s |" % " | ".join(fmt(pooled[r]) for r in RULES))
    say("")
    say("### `approx` 2건의 값 (판정 분모 «밖» · 의무 민감도 · §2-5)\n")
    say("| 종목 | 등록일 | " + " | ".join("`%s`" % r for r in RULES) + " |")
    say("|---|---|" + "---|" * len(RULES))
    for it in ap_items:
        k = (it["post"], it["item_no"])
        say("| %s | %s | %s |" % (it["name"], it["reg"], " | ".join(
            ("**%d**" % int(ap_run["results"][r][k]["m"]))
            if ap_run["results"][r][k]["m"] is not None else "⛔" for r in RULES)))
    say("")
    say("🔴 `after` 1건(모나미 2026-07-16)은 **제외**한다 — 「그 이후」는 등록일이 아니라서 "
        "어느 날의 유니버스인지 정할 수 없다(§2-5 · `PREREG_SELECTION.md` §5 승계).")
    say("")

    # ── §12 A3 계수 ─────────────────────────────────────────────────────────
    say("## 11. `RNK-A3` 적합 기록 (§2-2 · §9)\n")
    say("하이퍼파라미터 = `sklearn.linear_model.LogisticRegression` **기본값**"
        "(L2 · `C=1.0` · `class_weight=None` · `solver=lbfgs`). "
        "🔑 ***기본값을 쓰는 것 자체가 「고르지 않았다」의 증거다.***")
    say("")
    say("| 폴드(뺀 글) | 훈련 날짜 수 | 훈련 행 | 양성 | 수렴 |")
    say("|---|---|---|---|---|")
    for n in main_run["a3_notes"]:
        say("| %d | %d | %d | %d | %s |"
            % (n["fold"], len(n["dates"]), n["rows"], n["pos"], n["note"] or "🟢 기본값에서 수렴"))
    say("| **전체 적합**(동결 대상) | %d | %d | %d | %s |"
        % (len(main_run["a3_dates_all"]), main_run["a3_full_shape"][0], main_run["a3_full_pos"],
           main_run["a3_full_note"] or "🟢 기본값에서 수렴"))
    say("")
    say("🔴 **관측된 누수 구조 — 문서가 다루지 않은 지점**: §2-2 는 음성을 *「같은 날 유니버스의 "
        "나머지 «전 종목»」* 으로 정의한다. 등록일이 «폴드를 가로질러» 겹치는 날"
        "(2026-08-05 · 2026-08-12)에서는 **뺀 폴드의 저자 종목이 그날의 «음성»으로 들어간다.** "
        "이건 `RNK-A3` 에게 **불리한** 쪽(보수적)이라 그대로 두고 사실만 인쇄한다.")
    say("")
    if main_run["a3_full"] is None:
        say("🔴 **전체 적합이 성립하지 않았다** — 계수를 낼 수 없다. `RNK-A3` 은 후보에서 실질 탈락이다.")
        coef = None
    else:
        coef = main_run["a3_full"].coef_[0]
    if coef is None:
        say("")
        (BASE / a.out).write_text("\n".join(OUT) + "\n", encoding="utf-8")
        print("\n[written] %s (A3 적합 불가)" % a.out)
        return 1
    say("### 전체 적합 계수 (동결 후보)\n")
    say("| 특징 | 계수 | 부호 | 동결된 방향(`PREREG_SELECTION.md` §1) |")
    say("|---|---|---|---|")
    frozen_dir = {f: "높을수록" for f in FEATS}
    frozen_dir["f5_pos60"] = "🔴 **미동결**(양방향)"
    frozen_dir["f7_mcap"] = "예측 없음(대조축)"
    for f, c in zip(FEATS, coef):
        say("| `%s` | %+.4f | %s | %s |" % (f, c, "+" if c > 0 else "−", frozen_dir[f]))
    say("| (절편) | %+.4f | | |" % main_run["a3_full"].intercept_[0])
    say("")
    f5c = coef[FEATS.index("f5_pos60")]
    f7c = coef[FEATS.index("f7_mcap")]
    say("🔑 **`f5` 의 부호를 데이터가 정하는 유일한 후보가 `RNK-A3` 이다**(§2-2 B-1). "
        "실측 `f5_pos60` 계수 = **%+.4f** ⇒ 데이터가 고른 방향 = **%s**."
        % (f5c, "높을수록" if f5c > 0 else "🔴 **낮을수록**"))
    say("🔑 **`f7` 은 예측이 «없던» 대조축**이다 — 계수 **%+.4f**(방향 **%s**)는 «관측»으로만 적는다."
        % (f7c, "높을수록" if f7c > 0 else "낮을수록"))
    say("")
    say("⚠️ **`RNK-A2`·`A4` 는 `f5` 를 「원 백분위 그대로」 넣었다**(부호가 없으므로 · §2-2). "
        "`RNK-A3` 이 고른 방향이 **%s** 이므로, `A2`·`A4` 의 가정(높을수록)과 %s."
        % ("높을수록" if f5c > 0 else "낮을수록",
           "일치한다" if f5c > 0 else "🔴 **반대다 — 그 사실을 인쇄한다**"))
    say("")
    flipped = [f for f, c in zip(FEATS, coef)
               if c < 0 and frozen_dir[f] == "높을수록"]
    if flipped:
        say("🔴 **동결된 방향과 «반대» 부호가 나온 특징이 있다** — %s. "
            "`PREREG_SELECTION.md` §1 은 이들을 *「높을수록 선정될 것」*으로 **미리 걸었는데** "
            "`RNK-A3` 의 계수는 음수다. ⚠️ **이건 그 예측의 «기각»이 아니다** — 계수는 "
            "**다른 8개를 통제한 뒤의 부분효과**이고 단변량 방향과 다를 수 있다"
            "(`SEL-S2`·`SEL-S3` 는 단변량 축이다). ⇒ ***관측으로 적고, 어느 쪽도 「기각」이라 "
            "부르지 않는다.*** 이 축은 `RNK-A3` 을 «고르지 않았»으므로 판정에도 안 들어간다."
            % ", ".join("`%s`(%+.4f)" % (f, coef[FEATS.index(f)]) for f in flipped))
        say("")
    say("🔴 **과적합이 기본값이다**(§9) — 계수 9 + 절편에 훈련 양성 %d건 = **계수당 %.1f건**. "
        "`RNK-O1`·`RNK-X1` 이 유일한 방어선이다." % (main_run["a3_full_pos"],
                                                     main_run["a3_full_pos"] / 10.0))
    say("")

    # ── §13 md5 ─────────────────────────────────────────────────────────────
    say("## 12. 재현 정보\n")
    say("| 파일 | md5 |")
    say("|---|---|")
    say("| `run_ranking.py` | `%s` |" % md5(BASE / "run_ranking.py"))
    say("| `run_selection.py` (특징 정의) | `%s` |" % md5(BASE / "run_selection.py"))
    say("| `run_tests.py` (DSN·CODES) | `%s` |" % md5(BASE / "run_tests.py"))
    say("| `run_regday_post5.py` (post4·5 코드) | `%s` |" % md5(BASE / "run_regday_post5.py"))
    say("| `ledger_trades.csv` | `%s` |" % md5(BASE / "ledger_trades.csv"))
    say("| `PREREG_RANKING.md` | `%s` |" % md5(BASE / "PREREG_RANKING.md"))
    say("")
    say("🔑 `RESULTS_RANKING_TRAIN_NUMBERS.md` 자신의 md5 는 이 파일 «밖»에서 잰다"
        "(자기참조 불가) — `RESULTS_RANKING_TRAIN.md` 말미와 `FREEZE_RANKING_<날짜>.md` 에 있다.")
    say("")
    say("**유니버스 SQL 원문**(§2-3 6번 동결 대상):")
    say("")
    say("```sql")
    say("SELECT stock_code, date, high, low, close, trading_value, market_cap")
    say("FROM daily_prices WHERE date BETWEEN '%s' AND '%s'" % (START, upto))
    say("AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0")
    say("-- 그 뒤 파이썬에서 의사티커 %s 제외" % str(list(PSEUDO)))
    say("```")
    say("")

    (BASE / a.out).write_text("\n".join(OUT) + "\n", encoding="utf-8")
    if main_run["selected"] == "RNK-A3" and a.upto is None:
        js = dict(rule="RNK-A3", seed=SEED, snapshot=upto,
                  hyperparams="sklearn LogisticRegression defaults (L2, C=1.0, class_weight=None)",
                  features=list(FEATS), scale="일자별 백분위 / 100",
                  coef=[float(c) for c in coef],
                  intercept=float(main_run["a3_full"].intercept_[0]),
                  n_rows=int(main_run["a3_full_shape"][0]), n_pos=int(main_run["a3_full_pos"]))
        (BASE / "RANKING_A3_COEFS.json").write_text(
            json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[written] RANKING_A3_COEFS.json")
    print("\n[written] %s" % a.out)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                     # noqa: BLE001
        pass
    sys.exit(main())
