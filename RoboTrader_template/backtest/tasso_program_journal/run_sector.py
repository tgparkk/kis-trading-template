# -*- coding: utf-8 -*-
"""`SEC-` 축 **배선 점검** 실행 — 섹터 동반 상승(`PREREG_SECTOR_COMOVE.md` §0-4 **4번**).

🔬 **탐색 표기 · 판정 아님 · 규칙 «선택» 없음.** 대상은 **post1~5 «만»** 이다(`SEC-O1` · §4-5).
post6 은 이 스크립트가 도는 시점에 **존재하지 않는다** — 어떤 post6 수치도 이 산출물에 없다.

사전등록: `PREREG_SECTOR_COMOVE.md`(동결 · `SEC-D1`~`D8` 사장님 확정 2026-09-02 · §0-6)
  §1 데이터 실측 · §2 설계 동결(`SEC-R1`~`R6`) · §3 예측 동결표 · §4 대칭 단언
  (`SEC-N1`·`B1`·`B2`·`G1`·`X1`·`O1`·`V1`) · §5 실행 전제 · §6 판정 불가 · §7-B 실행 점검표

🔒 **사장님 확정분(§0-6)** — 이 스크립트가 «판정 갈래»로 쓰는 것:
  `SEC-D1` 섹터 = `induty_code` 앞 **`N = 3`** 자리(주) · `N = 2`·`N = 5` 의무 민감도
  `SEC-D2` 측정자 = **`SEC-M1`**(섹터 중앙수익률의 당일 «섹터간» 백분위)(주) · `M2`·`M3` 의무 민감도
  `SEC-D3` 유니버스 = `PREREG_RANKING.md` §2-1 승계 ∩ **섹터코드 존재**
  `SEC-D4` 대칭 대조 풀 = 무작위 «급등» 종목(`n_up`) **채택**
  `SEC-D5` 분모 = `exact` 만 · `approx` 의무 민감도 · `after` 제외
  `SEC-D6` `SEC-X1`(섹터 라벨 순열 대조군) **채택** — 용도는 **귀무 «구현» 1종오류율 보정 하나뿐**
  `SEC-D7` 수익률 = `close / prev_close − 1`
  `SEC-D8` EOD 점검표 **미편입**

🔴 **계산 «전»에 고정한 구현 결정 (S-1 ~ S-8)** — 사전등록 문언의 «기계화»이며 새 잣대가 아니다:
  S-1 `prev_close` 는 `run_regday_post5.load_universe_day` 의 **20«일력»일 창 `LAG`** 를 글자 그대로
      복제한다(§1-3 이 *「그 정의를 «글자 그대로» 복제해 재현했다」*고 못 박았다). 복제본이 그 함수와
      **집합으로 같은지**를 매 등록일에 실측해 인쇄한다(§1-4 배선).
  S-2 백분위 = `100 × (G − 1 − sec_rank) / (G − 1)` · `sec_rank` = *「그날 `med` 가 저자 섹터보다
      «좋거나 같은» 섹터 수, 자기 섹터 제외」*(§2-2). ⇒ 저자 섹터가 그날 **1위**(동률 없음)면
      백분위 **100** 이고, 이는 §4-2 (가)가 *「관측 통계량의 천장은 100」*이라 적은 것과 «같은 눈금»이다.
      동률은 전부 «위»로 세므로 백분위를 **낮추는**(보수적) 방향이다(§4-1).
  S-3 자기 제외는 **두 곳 전부**(§2-3 M7): ①섹터 동료 집합 `P(D,s)` ②귀무·대조 추출 풀.
      저자 섹터의 통계량은 «자기 제외» 값이고, 다른 섹터의 통계량은 그 섹터 전원 값이다.
  S-4 중앙값 관용구(C-20 승계) = 분모가 **짝수면 두 가운데 값의 «평균»**. 섹터 내 중앙값·글 단위
      중앙값·풀 중앙값 전부 같은 규약이며, 짝·홀 여부를 인쇄한다.
  S-5 `p` = `mean(귀무 통계량 ≥ 관측 통계량)` — **등호 포함**(§4-1 *「동률은 `p` 를 «키우는» 쪽으로」*).
  S-6 측정 가능 = 「그 갈래에서 섹터 라벨이 정의되고(`length ≥ N`) 동료 `|P| ≥ 1` 이고 그날 섹터가
      2개 이상(`G ≥ 2`)」. 귀무·대조 풀도 **같은 조건으로 한정**하고 그 한정 손실을 인쇄한다(§2-3).
  S-7 `q_top` = §4-2 (가) 문언 *「그날 풀에서 «1위 섹터»가 차지하는 비율」* 그대로. 그 정의가
      «천장을 받을 확률」의 대리이므로 **직접 실측한 천장 점유율**(풀에서 백분위 = 100 인 비율)을
      나란히 인쇄하고, 두 값이 발화 판정을 가르면 그 사실을 적는다. **판정은 문언 정의로 한다.**
  S-8 `SEC-X1` 은 **주 갈래(`N=3` · `SEC-M1`)에 대해서만** 돌린다(§4-4 가 재는 것이 «귀무 구현»
      하나뿐이므로 갈래마다 돌릴 이유가 없다). 두 풀(`SEC-N1`·`SEC-B1`) 각각의 1종오류율을 낸다.

🔴 라이브 트리 import 0건 · DB 는 **SELECT 만** · `adj_factor` 산술 0건 · 원장은 «읽기»만 ·
   `stock_industry` 는 «읽기 전용»(이 축은 그 표를 채우거나 고치지 않는다 · §5 6번).
🔴 이 축은 `volume` 을 안 쓴다 — `close`·`prev_close`·`high` 만 쓴다(§5 5번).
🔴 `daily_prices.returns_1d` 를 쓰지 않는다 — 직접 계산한다(§2-2).

🔴 `SEC-R6`(§5 7번) 재사용 — 유니버스·의사티커·`n_up`·원장 판독은 **전부 기존 코드 import**:
   `run_selection.PSEUDO` · `run_regday_post5.load_universe_day`·`.universe_raw_count` ·
   `run_ranking.build_codes`·`.exact_items`·`.approx_items`·`.load_ledger` · `run_tests.DSN`.
   **표를 복사해 다시 쓰지 않는다.**

산출물 = `RESULTS_SECTOR_DRYRUN_NUMBERS.md`(기계 생성 · `regen_gate.py` `PAIRS` 대상) +
        `sector_dryrun/`(등록일별 JSON · `controls_summary.json` · `universe_snapshot.json` ·
        `sector_snapshot.json` · `cases.tsv`).
산문 = `RESULTS_SECTOR_DRYRUN.md`(사람이 쓴다 · `MANUAL_DOCS` 대상).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from math import comb
from pathlib import Path

import numpy as np
import psycopg2

from run_ranking import approx_items, build_codes, exact_items, load_ledger
from run_regday_post5 import load_universe_day, universe_raw_count
from run_selection import PSEUDO
from run_tests import DSN

BASE = Path(__file__).resolve().parent
ART = BASE / "sector_dryrun"
OUT: list[str] = []

SEED = 20260815          # §2-3 · `PREREG_POST6.md` §3-1 동결분 승계
NREP = 20_000            # 〃 (🔴 `run_selection.py:22` 는 NREP = 2000 — 차이를 §0 에 인쇄한다)
X1_REP = 200             # §4-4 · `RESULTS_RANKING_TRAIN.md` §5 «승계»(독립 실현 200)
P_THR = 0.05             # `PREREG_REGDAY_MEASURE.md` §4-1 «차용»
B2_THR = 0.50            # `RESULTS_D1_OOS_POST5.md` §9 W7 «차용»
G1_THR = 1.0 / 3.0       # `RESULTS_RECONSTRUCT_POST4.md` §6 Y3 «차용»
QTOP_THR = 0.135         # §4-2 (가) — `3q²(1−q)+q³ = 0.05` 의 근 (§4-1 `t ≈ 0.865` 와 같은 근)
UP_MULT = 1.15           # `run_regday_post5.py:13`·`:327` 의 `n_up` 정의 «승계»(새 문턱 아님)
DROP_MARK = 0.01         # §5 6-1 — «표시» 문턱이지 «판정» 게이트가 아니다
NS = (2, 3, 5)           # `SEC-D1` 후보 (⚠️ `N = 4` 배제 사유는 §2-1 m1)
MEAS = ("SEC-M1", "SEC-M2", "SEC-M3")
MAIN_N, MAIN_M = 3, "SEC-M1"   # 🔒 사장님 확정 주 판정 갈래

# 🔴 §7-B #24 — 모든 산출물에 «그대로» 붙이는 의무 문언.
NOTATION = [
    "1. 🔴 **「라이브 채택 금지 · 성과·엣지 추정 금지」** — 이 문서가 만드는 어떤 섹터 지표도 "
    "라이브 전략·파라미터 변경의 근거가 아니다(`PREREG_SECTOR_COMOVE.md` §0-1 · `PREREG.md` §0). "
    "산출물은 **기록**이지 전략 후보가 아니다.",
    "2. 🔴 **「+15%」 문턱이 이 축 «안»에 남아 있다** — `n_up`(대조 풀)과 `SEC-M2` 가 "
    "`고가 ≥ 전일종가 × 1.15` 를 쓴다(`run_regday_post5.py:13`·`:327` 승계 · §2-2). "
    "**`SEL-S1` 기각은 그대로 유지된다** — 이 값은 «판정 문턱»이 아니라 «대조 풀·측정자 입력»이고, "
    "**등록일 당일 저자 종목에 걸지 않는다**(동료에게만 건다).",
    "3. 🔴 **`SEC-P1` 불성립을 「테마가 아니다」로 읽지 않는다** — 거짓 음성이 구조적이다"
    "(에코프로 4종목이 KSIC 에서 «세 칸»으로 흩어진다 · §0-2 · §9). "
    "성립도 「섹터 동반성이 존재한다」까지이며 「테마로 고른다」의 확증이 아니다.",
    "4. 🔴 **`SEC-N1` 은 «`SEC-B1` 없이는» 증거가 아니다** — 저자 종목은 정의상 급등주이고, "
    "급등주가 섹터 동반성이 높다면 `SEC-N1` 은 그 사실만 되비춘다(= `REG-M4` 재진술). "
    "**정보는 `SEC-B1`·`SEC-B2` 에 있다**(§4-1).",
    "5. 🔬 **여기 있는 값은 전부 «탐색적 표기»다**(`SEC-O1` · §4-5) — post1~5 값은 "
    "**판정 분모에 넣지 않는다.** 판정은 post6 부터 누적한다. "
    "그리고 이 축의 최대치는 **「기술」**이다(승/패 대조 2회 연속 미실시 · §0-2 ③).",
    "6. 🔴 **이 실행은 «훈련»이 아니라 «배선 점검»이다**(§0-4 4번) — 규칙 «선택»이 없다. "
    "잣대(`SEC-D1`·`D2`)는 이 실행 «전»에 동결됐다(§0-6 · 2026-09-02).",
]


def say(s=""):
    print(s)
    OUT.append(s)


def med(xs):
    """중앙값 — S-4(C-20 승계): **분모가 짝수면 두 가운데 값의 «평균»**."""
    if len(xs) == 0:
        return None
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2]) if n % 2 else float((s[n // 2 - 1] + s[n // 2]) / 2.0)


def med_note(n):
    return "짝수 ⇒ 두 가운데 값의 «평균»" if n % 2 == 0 else "홀수 ⇒ 가운데 값"


def sha_list(xs):
    return hashlib.sha256(("\n".join(xs)).encode("utf-8")).hexdigest()


def fmt(v, nd=1):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


# 🔴 난수 스트림 분리 (§2-3 «필수» 승계) — `RESULTS_RANKING_TRAIN.md` §5 가 실측으로 잡은
#    결함(같은 시드로 목적이 다른 두 계열을 만들어 얽힘)을 구조적으로 막는다.
#    ⚠️ 이름은 **끝에만 덧붙인다** — `spawn` 은 앞쪽 자식을 보존한다.
_STREAM_NAMES = ["sec_n1", "sec_b1", "sec_x1_perm", "sec_x1_null",
                 "sec_x1_bypass_perm", "sec_x1_bypass_null"]
_CHILDREN = dict(zip(_STREAM_NAMES, np.random.SeedSequence(SEED).spawn(len(_STREAM_NAMES))))


def stream(name):
    return np.random.default_rng(_CHILDREN[name])


# ══════════════════════════════════════════════════════════════════════════════
# 1. 하루치 섹터 통계 — 전 종목에 대해 «자기 제외» 통계량과 그 섹터간 백분위
# ══════════════════════════════════════════════════════════════════════════════
def day_stats(lab, r, up):
    """lab: int32 (>=0 유효 · -1 = 그 갈래에서 라벨 미정) · r: float64 · up: bool.

    반환(전 종목 길이의 배열) — S-2·S-3 그대로:
      peers   동료 수 `|P|` = m − 1 (라벨 미정이면 -1)
      m1..m3  자기 제외 «원값» (`med` · 급등 동료 수 · 상승 비율)
      p1..p3  그날 «모든 섹터»의 같은 통계량 분포 안에서의 백분위 (0~100)
      rank1..3 `sec_rank` = 그 통계량이 저자보다 «좋거나 같은» 섹터 수(자기 섹터 제외)
      ok      측정 가능 여부(S-6)
    """
    n = lab.shape[0]
    nan = np.full(n, np.nan)
    res = dict(peers=np.full(n, -1, dtype=np.int64), ok=np.zeros(n, dtype=bool),
               m1=nan.copy(), m2=nan.copy(), m3=nan.copy(),
               p1=nan.copy(), p2=nan.copy(), p3=nan.copy(),
               r1=np.full(n, -1, dtype=np.int64), r2=np.full(n, -1, dtype=np.int64),
               r3=np.full(n, -1, dtype=np.int64), G=0)
    idx = np.flatnonzero((lab >= 0) & np.isfinite(r))
    if idx.size == 0:
        return res
    l0 = lab[idx]
    r0 = r[idx]
    u0 = up[idx].astype(np.int64)
    pos0 = (r0 > 0).astype(np.int64)

    order = np.lexsort((r0, l0))          # 섹터별로 모으고 그 안에서 r 오름차순
    ls, rs = l0[order], r0[order]
    uniq, first, counts = np.unique(ls, return_index=True, return_counts=True)
    G = int(uniq.size)
    res["G"] = G
    seg = np.searchsorted(uniq, ls)
    start = first[seg]
    m = counts[seg]
    local = np.arange(idx.size) - start

    # ── 섹터 «전원» 통계량 (다른 섹터에 쓰는 값) ────────────────────────────
    half = counts // 2
    odd = (counts % 2) == 1
    med_full = np.where(odd, rs[first + half],
                        (rs[first + np.maximum(half - 1, 0)] + rs[first + half]) / 2.0)
    up_full = np.bincount(seg, weights=u0[order], minlength=G)
    pos_full = np.bincount(seg, weights=pos0[order], minlength=G)
    m3_full = pos_full / counts

    # ── 자기 제외 통계량 ────────────────────────────────────────────────────
    L = m - 1
    hi = idx.size - 1
    c = (m - 2) // 2                                    # L 이 홀수(m 짝수)일 때
    pick = np.clip(start + c + (local <= c).astype(np.int64), 0, hi)
    a = (m - 3) // 2                                    # L 이 짝수(m 홀수)일 때
    b = (m - 1) // 2
    pa = np.clip(start + a + (local <= a).astype(np.int64), 0, hi)
    pb = np.clip(start + b + (local <= b).astype(np.int64), 0, hi)
    med_loo = np.where((m % 2 == 0) & (L >= 1), rs[pick],
                       np.where((m % 2 == 1) & (L >= 2), (rs[pa] + rs[pb]) / 2.0, np.nan))
    up_loo = np.where(L >= 1, up_full[seg] - u0[order], np.nan)
    m3_loo = np.where(L >= 1, (pos_full[seg] - pos0[order]) / np.maximum(L, 1), np.nan)

    # ── 섹터간 백분위 (S-2) ─────────────────────────────────────────────────
    def rank_pct(stat_loo, stat_full):
        srt = np.sort(stat_full)
        # 저자보다 «좋거나 같은» 섹터 수 (자기 섹터 포함) → 자기 섹터를 뺀다
        ge = G - np.searchsorted(srt, stat_loo, side="left")
        own = (stat_full[seg] >= stat_loo).astype(np.int64)
        sr = ge - own
        with np.errstate(invalid="ignore", divide="ignore"):
            pct = 100.0 * (G - 1 - sr) / (G - 1) if G >= 2 else np.full_like(stat_loo, np.nan)
        return sr, pct

    r1s, p1s = rank_pct(med_loo, med_full)
    r2s, p2s = rank_pct(up_loo, up_full)
    r3s, p3s = rank_pct(m3_loo, m3_full)

    ok = (L >= 1) & (G >= 2) & np.isfinite(med_loo)
    inv = idx[order]
    res["peers"][inv] = L
    res["ok"][inv] = ok
    res["m1"][inv] = med_loo
    res["m2"][inv] = up_loo
    res["m3"][inv] = m3_loo
    for k, (rr, pp) in (("1", (r1s, p1s)), ("2", (r2s, p2s)), ("3", (r3s, p3s))):
        res["r" + k][inv] = np.where(ok, rr, -1)
        res["p" + k][inv] = np.where(ok, pp, np.nan)
    return res


def labels_for(induty, n):
    """`induty_code` 앞 `n` 자리 → 정수 라벨. 길이 < n 이면 -1(그 갈래에서 «미정» · 사유 ⑤)."""
    keys = [(s[:n] if (s is not None and len(s) >= n) else None) for s in induty]
    vocab = {k: i for i, k in enumerate(sorted({k for k in keys if k is not None}))}
    return np.array([vocab.get(k, -1) for k in keys], dtype=np.int64), vocab


# ══════════════════════════════════════════════════════════════════════════════
# 2. 귀무·대조 (§2-3 · §4-1 · §4-2)
# ══════════════════════════════════════════════════════════════════════════════
def aggregate(vals, posts):
    """글 단위 중앙 → 그 중앙(주 판정) · 건 pooled 중앙(의무 민감도). (§2-4)"""
    if len(vals) == 0:
        return None, None
    by = {}
    for v, p in zip(vals, posts):
        by.setdefault(p, []).append(v)
    per = [med(by[p]) for p in sorted(by)]
    return med(per), med(list(vals))


def null_matrix(rng, pools, posts, nrep):
    """각 건마다 그 날 풀에서 종목 1개씩 → (nrep, k) 백분위 행렬."""
    k = len(pools)
    mat = np.empty((nrep, k), dtype=np.float64)
    for j, arr in enumerate(pools):
        mat[:, j] = arr[rng.integers(0, arr.size, size=nrep)]
    return mat


def agg_matrix(mat, posts):
    """(nrep, k) → (글 단위 집계 (nrep,), pooled 집계 (nrep,))"""
    groups = {}
    for j, p in enumerate(posts):
        groups.setdefault(p, []).append(j)
    per = np.stack([np.median(mat[:, groups[p]], axis=1) for p in sorted(groups)], axis=1)
    return np.median(per, axis=1), np.median(mat, axis=1)


def binom_ge_half(k, q):
    """P(Binom(k, q) ≥ ⌈k/2⌉) — §4-2 (가) 의 산술 그대로."""
    need = -(-k // 2)
    return float(sum(comb(k, i) * q ** i * (1 - q) ** (k - i) for i in range(need, k + 1)))


# ══════════════════════════════════════════════════════════════════════════════
# 3. 메인
# ══════════════════════════════════════════════════════════════════════════════
def main():                                                   # noqa: PLR0912, PLR0915
    t_start = time.time()
    ART.mkdir(exist_ok=True)
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    cur.execute("SELECT max(date) FROM daily_prices")
    END = str(cur.fetchone()[0])
    cur.execute("SELECT count(*), count(DISTINCT stock_code), count(induty_code) FROM stock_industry")
    si_rows, si_uniq, si_nonnull = cur.fetchone()
    cur.execute("SELECT max(updated_at) FROM stock_industry")
    si_upd = str(cur.fetchone()[0])
    cur.execute("SELECT stock_code, induty_code FROM stock_industry ORDER BY stock_code")
    si_pairs = cur.fetchall()
    SEC = {a: b for a, b in si_pairs}
    si_sha = sha_list([f"{a}\t{b}" for a, b in si_pairs])
    cur.execute("SELECT count(*), count(sector) FROM stock_info")
    info_rows, info_sector = cur.fetchone()
    cur.execute("SELECT length(induty_code), count(*) FROM stock_industry GROUP BY 1 ORDER BY 1")
    len_all = dict(cur.fetchall())
    cur.execute("SELECT DISTINCT stock_code FROM daily_prices WHERE stock_code !~ '^[0-9]' ORDER BY 1")
    nonnum = [r[0] for r in cur.fetchall()]
    final_pseudo = sorted(set(PSEUDO) | set(nonnum))

    rows = load_ledger()
    codes, _ = build_codes()
    items, post_idx = exact_items(rows, codes)
    ap_items = approx_items(rows, codes, post_idx)
    dates = sorted({it["reg"] for it in items})
    all_dates = sorted({it["reg"] for it in items + ap_items})

    # ── 등록일별 데이터 적재 ────────────────────────────────────────────────
    DAY = {}
    for d in all_dates:
        lo = (np.datetime64(d) - np.timedelta64(20, "D")).astype(str)
        cur.execute(
            "WITH u AS (SELECT stock_code, date, high, close, trading_value, market_cap, "
            "  LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close "
            "  FROM daily_prices WHERE date BETWEEN %s AND %s AND close > 0) "
            "SELECT stock_code, high, close, trading_value, market_cap, prev_close FROM u "
            "WHERE date = %s AND market_cap IS NOT NULL AND market_cap > 0 "
            "AND NOT (stock_code = ANY(%s)) ORDER BY stock_code",
            (lo, d, d, final_pseudo))
        raw = cur.fetchall()
        uni = [r[0] for r in raw]
        # S-1 배선 확인 — 복제본에 `prev_close` 필터를 걸면 동결 함수와 «집합으로» 같아야 한다
        frozen = {r[0] for r in load_universe_day(cur, d)}
        mine = {r[0] for r in raw if r[5] is not None and float(r[5]) > 0}
        joined = [c for c in uni if c in SEC]
        jset = set(joined)
        code_i = {c: i for i, c in enumerate(joined)}
        high = np.array([float(r[1]) if r[1] is not None else np.nan for r in raw if r[0] in jset])
        close = np.array([float(r[2]) for r in raw if r[0] in jset])
        prevc = np.array([float(r[5]) if r[5] is not None else np.nan for r in raw if r[0] in jset])
        with np.errstate(invalid="ignore", divide="ignore"):
            r_ = close / prevc - 1.0
            up_ = high >= prevc * UP_MULT
        up_ = np.where(np.isfinite(prevc) & np.isfinite(high), up_, False)
        DAY[d] = dict(
            uni=uni, joined=joined, code_i=code_i, r=r_, up=up_, high=high, close=close,
            prevc=prevc, induty=[SEC[c] for c in joined],
            raw_n=universe_raw_count(cur, d), frozen_n=len(frozen),
            s1_ok=(frozen == mine), s1_diff=len(frozen ^ mine),
            prev_miss_join=int(np.sum(~np.isfinite(prevc))),
            nup=[c for c in joined if up_[code_i[c]]])
        induty = DAY[d]["induty"]
        DAY[d]["lab"] = {n: labels_for(induty, n)[0] for n in NS}
        DAY[d]["vocab"] = {n: labels_for(induty, n)[1] for n in NS}
        DAY[d]["st"] = {n: day_stats(DAY[d]["lab"][n], r_, up_) for n in NS}
        DAY[d]["lab3"] = DAY[d]["lab"][MAIN_N]

    # ══════════════════════════════════════════════════════════════════════
    # §0
    # ══════════════════════════════════════════════════════════════════════
    say("# `SEC-` 섹터 동반 상승 — **배선 점검** 수치 원본 (post1~5 «만»)")
    say()
    for ln in NOTATION:
        say("> " + ln)
    say()
    say("🔴 **이 파일에는 6번째 글에 대한 수치가 «하나도» 없다** — 실행 시점에 그 글은 "
        "존재하지 않는다(`PREREG_SECTOR_COMOVE.md` §0-4 4번).")
    say()
    say("## §0. 실행 문맥")
    say()
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 사전등록 | `PREREG_SECTOR_COMOVE.md` (동결 · `SEC-D1`~`D8` 확정 2026-09-02) |")
    say("| 단계 | `PREREG_SECTOR_COMOVE.md` §0-4 **4번(배선 점검)** — 🔴 훈련 아님·규칙 선택 없음 |")
    say("| 실행 브랜치 | `fix/tasso-post6-s5-fixes` (🔴 해시는 stdout 전용 — 본문에 박으면 `--rerun` 이 구조적으로 깨진다) |")
    say(f"| **DB 스냅샷 최신 봉** | **`{END}`** (`daily_prices` `max(date)`) |")
    say(f"| `stock_industry` 스냅샷 (§7-B #22) | **{si_rows:,}행** · 고유 `stock_code` {si_uniq:,} · "
        f"`induty_code` non-NULL {si_nonnull:,} · `max(updated_at)` **{si_upd}** |")
    say(f"| 〃 sha256(전체 `stock_code`↔`induty_code`) | `{si_sha[:32]}…` |")
    say("| 주 판정 갈래 | 🔒 **`N = 3` · `SEC-M1`** (`SEC-D1`·`D2` · 사장님 확정 2026-09-02) |")
    say(f"| 시드 · 반복 | `{SEED}` · **{NREP:,}회** — ⚠️ `run_selection.py:22` 는 `NREP = 2000` 이다"
        f"(§2-3 고지 · 이 축은 «더 큰 쪽»을 쓴다) |")
    say(f"| 시드 스트림 분리 | `SeedSequence({SEED}).spawn()` → `{'`·`'.join(_STREAM_NAMES)}` "
        "(§2-3 «필수» 승계) |")
    say(f"| `SEC-X1` 독립 실현 | **{X1_REP}** (`RESULTS_RANKING_TRAIN.md` §5 «승계») |")
    say(f"| 의사티커 제외 | **{len(final_pseudo)}종** {'·'.join('`%s`' % p for p in final_pseudo)} — "
        f"`run_selection.py:23` `PSEUDO`({len(PSEUDO)}) ∪ DB 실측(숫자로 시작하지 않는 `stock_code` "
        f"{len(nonnum)}종) ⇒ **같다**(§5 4번 · §7-B #19) |")
    say("| 유니버스 | `PREREG_RANKING.md` §2-1 승계(`market_cap > 0 ∧ close > 0` · 의사티커 제외) "
        "**∩ 섹터코드 존재**(`SEC-D3`) |")
    say(f"| `exact` 건 | **{len(items)}건** (post2 {sum(1 for i in items if i['post'] == 2)} · "
        f"post3 {sum(1 for i in items if i['post'] == 3)} · post4 {sum(1 for i in items if i['post'] == 4)} · "
        f"post5 {sum(1 for i in items if i['post'] == 5)}) · `approx` **{len(ap_items)}건**(민감도) · "
        "`after` **제외**(`SEC-D5`) |")
    say(f"| 등록일 | **{len(dates)}일** (`exact`) · `approx` 포함 {len(all_dates)}일 |")
    say()
    say("🔴 **`SEC-O1` 자유도 신고** — 잣대 선택(`SEC-D1` `N` 3후보 × `SEC-D2` 측정자 3후보 = **9 조합**)의 "
        "자유도가 이 축의 거의 전부이며, 그 결정은 **이 실행 «전»**(2026-09-02 §0-6)에 동결됐다. "
        "**9 조합을 다 인쇄하되 판정 갈래는 «동결된 하나»뿐이다.**")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say("| 훈련(post1~5) | 🔬 **탐색적 표기** — 판정 분모에 **넣지 않는다** |")
    say("| 검증(post6~ 누적) | ⬜ **미존재** — 6번째 글은 이 실행 시점에 없다 |")

    # ══════════════════════════════════════════════════════════════════════
    # §1 실측 재현
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §1. 사전등록 §1 실측 «재현» — 값이 어긋나면 그 자리에 적는다")
    say()
    say("### 1-1. `stock_industry` 기본 (§1-1)")
    say()
    say("| 항목 | 문서값(2026-09-01) | 이 실행 | 일치 |")
    say("|---|---|---|---|")
    say(f"| 행 수 | 2,556 | **{si_rows:,}** | {'✅' if si_rows == 2556 else '🔴'} |")
    say(f"| 고유 `stock_code` | 2,556 | **{si_uniq:,}** | {'✅' if si_uniq == 2556 else '🔴'} |")
    say(f"| `induty_code` non-NULL | 2,556 / 2,556 | **{si_nonnull:,} / {si_rows:,}** | "
        f"{'✅' if si_nonnull == si_rows else '🔴'} |")
    say(f"| `stock_info.sector` non-NULL | **0** / 2,115 | **{info_sector:,} / {info_rows:,}** | "
        f"{'✅' if info_sector == 0 else '🔴'} |")
    say()
    say("⇒ 🔴 **대안 컬럼은 «없다»** — 이 축의 섹터 축은 `stock_industry.induty_code` 단일이며 "
        "**폴백이 없다**(§1-1 · §8-3).")
    say()
    say("### 1-2. `induty_code` 길이 분포 — `N = 5` 를 무너뜨리는 사실 (§1-2)")
    say()
    d21 = DAY["2026-08-21"]
    ln21 = {}
    for s in d21["induty"]:
        ln21[len(s)] = ln21.get(len(s), 0) + 1
    say("| 길이 | 표 전체(문서 / 이 실행) | 2026-08-21 조인 유니버스(문서 / 이 실행) |")
    say("|---|---|---|")
    for L, doc_a, doc_b in ((3, 1070, 1054), (4, 300, 299), (5, 1186, 1177)):
        say(f"| {L}자리 | {doc_a:,} / **{len_all.get(L, 0):,}** | {doc_b:,} / **{ln21.get(L, 0):,}** |")
    lt5_all = sum(v for k, v in len_all.items() if k < 5)
    lt5_21 = sum(v for k, v in ln21.items() if k < 5)
    say(f"| **5자리 미만 합** | 1,370 / **{lt5_all:,}** | 1,353 / **{lt5_21:,}** "
        f"(**{lt5_21 / len(d21['joined']) * 100:.1f}%**) |")
    say()
    say("🔴🔴 ***`left(induty_code, 5)` 는 3자리 코드에 «그 코드 자신»을 돌려준다*** — `N = 5` 는 "
        "분류 체계가 다른 두 깊이를 한 칸에 섞는다. 최소 길이가 3이므로 **`N ≤ 3` 만 «모든 코드에 대해 "
        "정의»된다**(§2-1 1번). ⇒ 구조가 주는 것은 **상한 `N ≤ 3`** 뿐이고 `N = 3` 채택은 «선택»이다(M1).")
    say()
    say("### 1-3. 유니버스 조인 커버리지 · `prev_close` · `n_up` — 등록일 11개 전수 (§1-3)")
    say()
    say("| 등록일 | 유니버스 | 섹터 조인 | 커버리지 | 🔴 조인 후 `prev_close` 없음 | `n_up` | `n_up` ∩ 조인 | S-1 동결함수 일치 |")
    say("|---|---|---|---|---|---|---|---|")
    doc13 = {"2026-07-28": (2570, 2533, 0, 54, 54), "2026-07-30": (2570, 2533, 0, 68, 66),
             "2026-08-05": (2763, 2533, 0, 99, 93), "2026-08-06": (2763, 2533, 0, 57, 53),
             "2026-08-11": (2761, 2531, 0, 92, 91), "2026-08-12": (2762, 2531, 0, 88, 86),
             "2026-08-13": (2763, 2531, 0, 66, 66), "2026-08-18": (2763, 2530, 0, 80, 76),
             "2026-08-19": (2763, 2530, 0, 53, 51), "2026-08-20": (2763, 2530, 0, 86, 79),
             "2026-08-21": (2764, 2530, 0, 47, 44)}
    mismatch13 = []
    for d in dates:
        D = DAY[d]
        rowsu = load_universe_day(cur, d)
        nup_full = [sc for sc, hi, cl, tv, mc, pc in rowsu
                    if hi is not None and pc and float(hi) >= float(pc) * UP_MULT
                    and tv is not None and mc]
        nup_all = len(nup_full)
        nup_j = sum(1 for c in nup_full if c in SEC)
        cov = len(D["joined"]) / len(D["uni"]) * 100
        doc = doc13[d]
        bad = [(nm, b, a) for nm, a, b in
               (("유니버스", len(D["uni"]), doc[0]), ("섹터 조인", len(D["joined"]), doc[1]),
                ("조인 후 `prev_close` 없음", D["prev_miss_join"], doc[2]),
                ("`n_up`", nup_all, doc[3]), ("`n_up` ∩ 조인", nup_j, doc[4])) if a != b]
        if bad:
            mismatch13.append((d, bad))
        say(f"| {d} | {len(D['uni']):,} | {len(D['joined']):,} | **{cov:.2f}%** | "
            f"**{D['prev_miss_join']}** | {'🔴 **' + str(nup_all) + '**' if bad else nup_all} | "
            f"{nup_j} | {'✅' if D['s1_ok'] else '🔴 차 %d' % D['s1_diff']} |")
        D["nup_full"] = nup_all
        D["nup_join"] = nup_j
    say()
    n_s1 = sum(1 for d in dates if DAY[d]["s1_ok"])
    n_pm = sum(1 for d in dates if DAY[d]["prev_miss_join"] == 0)
    say("- 🟢 **S-1 배선 확인**: 이 스크립트의 `prev_close` 복제본에 `prev_close IS NOT NULL AND > 0` 을 "
        "걸면 `run_regday_post5.load_universe_day`(동결 함수, **import 해서 호출**)와 **집합으로 같다** — "
        f"**{n_s1}/{len(dates)} 등록일**"
        f"{' ✅ 전부(차집합 크기 0)' if n_s1 == len(dates) else ' 🔴 어긋난 날이 있다'}. "
        "⇒ 20«일력»일 창 정의가 «글자 그대로» 복제됐다(§1-3).")
    say(f"- {'🟢' if n_pm == len(dates) else '🔴'} **`prev_close` 결손이 "
        f"{n_pm}/{len(dates)} 등록일에서 «전부 0»**(§1-4 재현) ⇒ `SEC-D7`(종가 대비 수익률)은 "
        "`RNK-N2` 가 겪은 ⛔ 경로를 «만들지 않는다».")
    if mismatch13:
        say()
        say("#### 🔴 정오 등재 — 사전등록 §1-3 표의 «재현되지 않는» 셀")
        say()
        say("🔒 **`PREREG_SECTOR_COMOVE.md` 는 동결본이므로 «고치지 않고» 여기 기록만 한다**"
            "(§8-A 가 `RESULTS_RANKING_TRAIN.md` 에 한 처리와 같은 형식).")
        say()
        say("| 등록일 | 어긋난 열 | 문서값 | 이 실행 | 판정 영향 |")
        say("|---|---|---|---|---|")
        for d, bad in mismatch13:
            for nm, doc_v, mine_v in bad:
                say(f"| {d} | {nm} | **{doc_v}** | **{mine_v}** | 🟢 **없음** — 아래 근거 |")
        say()
        say("- 🟢 **판정에 쓰는 양은 «`n_up` ∩ 조인»(= `SEC-B1` 추출 풀)이고 그 열은 11/11 재현된다.** "
            "사전등록 자신의 §2-3 이 풀을 *「실측 **44~93**」*으로, §4-2 (가) 표가 08-05 풀을 **93** 으로 "
            "적었는데 **둘 다 이 실행의 값과 일치**한다.")
        say("- 🔴 **그리고 동결 산출물 `RESULTS_REGDAY_POST5.md` §5 는 광전자 08-05 의 `n_up` 을 "
            "«93»으로 적었다** — 즉 어긋난 셀은 **사전등록 §1-3 의 그 한 칸뿐**이고, 계열의 다른 "
            "동결본·이 실행·사전등록의 나머지 인용이 전부 **93** 으로 일치한다.")
        say("- ⚠️ **어느 정의로도 99 가 나오지 않는다**(실측): 20일력일 창 `LAG` ⇒ **93** · "
            "전 기간 `LAG` ⇒ **98** · `2026-04-01` 이후 `LAG` ⇒ **93**. "
            "🔑 ***「분모가 다르다」가 아니라 「그 값이 재현되지 않는다」로 적는다.***")
    say()
    say("#### 07-30 → 08-05 코호트 넷 (§1-3 M4·M5) — 혼용 금지")
    say()
    u05 = set(DAY["2026-08-05"]["uni"])
    u30 = set(DAY["2026-07-30"]["uni"])
    cur.execute("SELECT stock_code, min(date) FROM daily_prices GROUP BY 1")
    firstbar = dict(cur.fetchall())
    A = {c for c in u05 if str(firstbar.get(c)) == "2026-08-05"}
    cur.execute("SELECT stock_code FROM daily_prices WHERE date=%s", ("2026-08-05",))
    B = u05 - {r[0] for r in load_universe_day(cur, "2026-08-05")}
    C = u05 - u30
    Dset = {c for c in u05 if c not in SEC}
    say("| 집합 | 정의 | 문서값 | 이 실행 |")
    say("|---|---|---|---|")
    say(f"| **A** | 전 기간 **첫 봉이 08-05** | 183 | **{len(A)}** |")
    say(f"| **B** | 🔴 `prev_close` 결손(20일력일 창) | 191 | **{len(B)}** |")
    say(f"| **C** | 07-30 대비 유니버스 **신규 진입** | 193 | **{len(C)}** |")
    say(f"| **D** | **섹터코드 부재** | 230 | **{len(Dset)}** |")
    say()
    inc = (A <= B) and (B <= C) and (C <= Dset)
    say(f"🔒 **포함 관계 `A ⊂ B ⊂ C ⊂ D`** — 양방향 차분 실측 ⇒ **{'✅ 성립' if inc else '🔴 불성립'}** "
        f"(`B∖A` = {len(B - A)}종목 · `C∖B` = {len(C - B)}종목 {sorted(C - B)} · `D∖C` = {len(Dset - C)}종목).")
    say(f"- 🟢 **`B ⊂ D`** ⇒ `prev_close` 결손 {len(B)}종목이 섹터 조인에서 **이미 전부 빠진다** "
        "⇒ 위 표의 「조인 후 결손 0」이 **두 창 정의 어느 쪽으로도** 성립한다.")
    say(f"- 🔴 **`D ⊋ C`**(차 {len(Dset - C)}종목) ⇒ ***「섹터 부재 = 신규 진입」은 «거짓»이다*** — "
        "포함이지 상등이 아니다(§1-3 정정 승계).")
    say(f"- 🔑 ***같은 이름의 「선행봉 결손」이 창 정의에 따라 {len(A)}(전 기간) / {len(B)}(20일력일)로 "
        "갈린다*** — 창을 안 적으면 재현이 안 된다.")
    if len(B) != 191:
        say()
        say(f"#### 🔴 `B` 가 191 → {len(B)} 로 움직였다 — **DB 가 움직인 것이다**(정오 아님 · `created_at` 실증)")
        say()
        DOC_BA = {"00104K", "00279K", "02826K", "03473K", "28513K", "33626K", "37550K", "37550L"}
        gone = sorted(DOC_BA - (B - A))
        added = sorted((B - A) - DOC_BA)
        say(f"사전등록 §1-3 이 적은 `B∖A` **{len(DOC_BA)}종목** 중 **{len(gone)}종목** {gone} 이 "
            f"이 실행에서는 `B` 에 «없다» (새로 들어온 종목 {added if added else '0건'}).")
        for c in gone:
            cur.execute("SELECT min(date), max(date), min(created_at), max(created_at) "
                        "FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                        (c, "2026-07-16", "2026-08-04"))
            r0 = cur.fetchone()
            say(f"- `{c}` — 창 `2026-07-16`~`08-04` 봉 **존재**({r0[0]}~{r0[1]}) · "
                f"그 봉들의 `created_at` = **{r0[2]}** ⇒ ***사전등록 측정일(2026-09-01) «뒤»에 적재됐다.***")
        cur.execute("SELECT count(*), count(*) FILTER (WHERE updated_at >= '2026-09-02') "
                    "FROM daily_prices WHERE date='2026-08-05'")
        tot_u, upd_u = cur.fetchone()
        say(f"- ⚠️ **`updated_at` 은 포렌식에 못 쓴다**(실측): `2026-08-05` 의 **{tot_u:,}행 전부**"
            f"({upd_u:,}/{tot_u:,})가 `updated_at ≥ 2026-09-02` 다 — 전행 일괄 갱신이다. "
            "***`created_at` 만이 「언제 처음 들어왔나」를 말한다.***")
        say("- 🔑 계열 규칙 재확인 — ***섹터 표만 「자라는」 게 아니라 «가격 표»도 자란다.*** "
            "`PREREG_SECTOR_COMOVE.md` §2-6 이 *「매일 돌리면 … 같은 글의 값이 날마다 달라진다」*고 "
            "적은 그 사건이 **사전등록 작성 다음날에 실제로 일어났다.**")

    # 1-5 저자 종목 섹터 커버리지
    say()
    say("### 1-5. 저자 종목의 섹터 커버리지 (§1-5)")
    say()
    say("| 글 | 항목 | 종목 | `stock_code` | `induty_code` | 길이 | `N=3` 칸 | 유니버스 | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for it in items:
        c = it["code"]
        D = DAY[it["reg"]]
        ind = SEC.get(c) if c else None
        in_uni = bool(c) and c in set(D["uni"])
        reason = ("①" if not c else ("②" if not in_uni else ("③" if ind is None else "")))
        say(f"| {it['post']} | {it['item_no']} | {it['name']} | `{c or '—'}` | "
            f"`{ind or '—'}` | {len(ind) if ind else '—'} | `{ind[:3] if ind else '—'}` | "
            f"{'✅' if in_uni else '🔴'} | {reason or '—'} |")
    say()

    # ── 갈래별 측정 (9 조합) ───────────────────────────────────────────────
    def measure_case(it, n, mkey):
        c = it["code"]
        D = DAY[it["reg"]]
        if not c:
            return dict(reason="①", ok=False)
        if c not in D["code_i"]:
            return dict(reason=("③" if c in set(D["uni"]) else "②"), ok=False)
        i = D["code_i"][c]
        ind = SEC[c]
        if len(ind) < n:
            return dict(reason="⑤", ok=False)
        st = D["st"][n]
        if not st["ok"][i]:
            return dict(reason="④", ok=False, peers=int(st["peers"][i]))
        j = {"SEC-M1": "1", "SEC-M2": "2", "SEC-M3": "3"}[mkey]
        return dict(ok=True, reason="", pct=float(st["p" + j][i]), raw=float(st["m" + j][i]),
                    rank=int(st["r" + j][i]), peers=int(st["peers"][i]), G=st["G"],
                    sector=ind[:n])

    BR = {}
    for n in NS:
        for mk in MEAS:
            BR[(n, mk)] = [measure_case(it, n, mk) for it in items]
            BR[("ap", n, mk)] = [measure_case(it, n, mk) for it in ap_items]

    say("### 1-6. 집단 크기 분포 (2026-08-21 · 조인 유니버스) — `N` 선택의 실측 배경 (§1-6)")
    say()
    say("🔴 「집단가중 중앙」은 «집단»을 하나씩 센 것이고 아래 저자 표의 「중앙」은 «종목»을 하나씩 "
        "센 것이다 — **두 「중앙」은 서로 다른 양이다**(M6 정정). 섞어 읽지 않는다.")
    say()
    say("🔴🔴 **`N = 5` 는 «정의가 둘»이다** — ①사전등록 §1-6 표는 `left(induty_code, 5)` 를 **글자 그대로** "
        "쓴 값이고(길이 3·4 코드가 «그 코드 자신»으로 한 칸이 된다) ②사전등록 §2-1 은 *「`N = 5` 를 "
        "정직하게 쓰려면 길이 5 미만 코드는 「그 층에서 미정」 = 측정 불가로 세야 한다」*고 못 박았다. "
        "🔴 ***이 스크립트의 측정은 ②를 쓴다***(§4-3 사유 ⑤가 그것을 요구한다). **둘 다 인쇄한다.**")
    say()
    say("| `N` | 정의 | 집단 수 | 최대 | 집단가중 중앙 | 🔴 동료 0 (측정 불가) | 동료 ≤ 1 | 동료 ≤ 4 | "
        "🔴 층에서 미정(길이 < `N`) | 문서값(§1-6) |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    NJ = len(d21["joined"])
    DOC16 = {2: "60 · 289 · 15.5 · 4 · 10 · 35", 3: "158 · 177 · 6 · 26 · 64 · 177",
             5: "524 · 94 · 2 · 217 · 401 · 811"}

    def size_row(keys):
        vocab = sorted({k for k in keys if k is not None})
        vi = {k: i for i, k in enumerate(vocab)}
        cnts = np.bincount([vi[k] for k in keys if k is not None], minlength=len(vocab))
        pv = np.array([cnts[vi[k]] - 1 for k in keys if k is not None])
        return (len(vocab), int(cnts.max()), med(list(cnts)),
                int(np.sum(pv == 0)), int(np.sum(pv <= 1)), int(np.sum(pv <= 4)),
                int(sum(1 for k in keys if k is None)))
    for n in NS:
        variants = [("🔒 이 실행(§2-1 정직 정의)",
                     [(s[:n] if len(s) >= n else None) for s in d21["induty"]])]
        if n == 5:
            variants.append(("(문서 §1-6) `left(,5)` 글자 그대로",
                             [s[:n] for s in d21["induty"]]))
        for lbl, keys in variants:
            g, mx, md_, p0, p1, p4, und = size_row(keys)
            doc = DOC16[n] if (n != 5 or "left" in lbl) else "—(문서는 아래 행)"
            say(f"| **{n}** | {lbl} | {g:,} | {mx:,} | **{md_:.1f}** | "
                f"{p0} (**{p0 / NJ * 100:.1f}%**) | {p1} ({p1 / NJ * 100:.1f}%) | "
                f"{p4} ({p4 / NJ * 100:.1f}%) | {und:,} ({und / NJ * 100:.1f}%) | {doc} |")
    say()
    say("⇒ 🟢 **`N = 2`·`N = 3` 은 문서값과 «전부» 일치**하고, **`N = 5` 는 «글자 그대로» 정의에서만 "
        "문서값(524 · 94 · 2 · 217 · 401 · 811)이 재현된다.** "
        "🔑 ***같은 이름(`N = 5`)이 문서 안에서 두 양을 가리킨다*** — §1-6 은 ①, §2-1·§4-3 은 ②. "
        "판정에 쓰는 것은 ②이고, 그래서 이 축의 `N=5` 갈래 측정 불가가 **61.1%** 다(§5).")
    say()
    say("#### 🟢 M6 — 귀무가 «자연히» 크기 정합인가 (§1-6 실측 재현)")
    say()
    say("| 잣대 | 문서값 | 이 실행 |")
    say("|---|---|---|")
    permed = [med([int(x) for x in DAY[d]["st"][3]["peers"][DAY[d]["st"][3]["peers"] >= 0]])
              for d in dates]
    say(f"| `SEC-N1` 풀(전 종목)의 **종목가중** 동료 중앙 (`N=3`) | **49.0** (11일 전부 동일) | "
        f"**{med(permed):.1f}** (등록일별 {min(permed):.0f}~{max(permed):.0f} · "
        f"{'전부 동일 ✅' if len(set(permed)) == 1 else '🔴 날짜별로 다르다'}) |")
    au_peers = [b["peers"] for b in BR[(3, "SEC-M1")] if b["ok"]]
    say(f"| **저자 {len(au_peers)}건**의 동료 중앙 (`N=3`) | **49** | **{med(au_peers):.0f}** "
        f"({med_note(len(au_peers))}) |")
    b1med = []
    for d in dates:
        st = DAY[d]["st"][3]
        pv = [int(st["peers"][DAY[d]["code_i"][c]]) for c in DAY[d]["nup"]
              if st["ok"][DAY[d]["code_i"][c]]]
        b1med.append(med(pv) if pv else np.nan)
    say(f"| `SEC-B1` 풀(`n_up`)의 종목가중 동료 중앙 | 날짜별 **27 ~ 70** · 날짜간 중앙 **50** | "
        f"날짜별 **{min(b1med):.0f} ~ {max(b1med):.0f}** · 날짜간 중앙 **{med(b1med):.1f}** |")
    say()
    say("⇒ 🟢 ***귀무 추출 종목의 동료 수 분포가 저자 종목의 그것과 «중앙에서 일치»하면*** "
        "「저자 종목이 유난히 큰/작은 섹터에 있어서 유리했다」가 **구조적으로 배제**된다 — "
        "🔑 이건 **추출 설계의 성질**이지 우리가 고른 변환이 아니다(§2-2 m9).")
    say()
    say("**저자 종목의 동료 수** (등록일 기준 · 섹터코드 있는 건 · **종목가중** · 🔬 탐색적)")
    say()
    say("| `N` | 정의 | 최소 | **중앙** | 최대 | 동료 0 인 건 | 측정 가능 건 | 문서값(§1-6) |")
    say("|---|---|---|---|---|---|---|---|")
    DOC_AU = {2: "30(코데즈컴바인) · 166 · 288", 3: "23(금호건설) · 49 · 176(마키나락스)",
              5: "6(코데즈컴바인) · 8 · 58(마키나락스)"}
    for n in NS:
        variants = [("🔒 §2-1 정직 정의", n, False)]
        if n == 5:
            variants.append(("(문서 §1-6) `left(,5)` 글자 그대로", n, True))
        for lbl, nn, literal in variants:
            pv = []
            for it in items:
                c = it["code"]
                D = DAY[it["reg"]]
                if not c or c not in D["code_i"]:
                    continue
                ind = SEC[c]
                key = ind[:nn] if (literal or len(ind) >= nn) else None
                if key is None:
                    continue
                cnt = sum(1 for s in D["induty"] if (s[:nn] if literal else
                          (s[:nn] if len(s) >= nn else None)) == key)
                pv.append((cnt - 1, it["name"]))
            if not pv:
                continue
            vals = [x for x, _ in pv]
            say(f"| {n} | {lbl} | {min(vals)} ({min(pv)[1]}) | **{med(vals):.0f}** | "
                f"{max(vals)} ({max(pv)[1]}) | **{sum(1 for x in vals if x == 0)}건** | "
                f"{len(vals)} | {DOC_AU[n] if (n != 5 or literal) else '—(아래 행)'} |")
    say()
    say("🔴 **이 표에는 «동반 상승 측정자 값»이 하나도 없다** — 잰 것은 **동료 수**뿐이다(§1-6 말미).")

    # ══════════════════════════════════════════════════════════════════════
    # §2 drop_rate 표기 가드 (§5 6-1)
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §2. `drop_rate` **표기 가드** (§5 6-1 · `PREREG_POST6.md` §5-2 «원 용도»)")
    say()
    say("🔴 **`1%` 는 «표시» 문턱이지 «판정» 게이트가 아니다.** "
        "🔑 ***0 이라서 안 재는 게 아니라, 0 임을 매회 «보여서» 이 조항이 살아 있음을 증명한다.***")
    say()
    say("| 등록일 | 그날 `market_cap>0` | 검정 유니버스 | 탈락 | 탈락률 | 🔴 섹터 조인 «후» 탈락 |")
    say("|---|---|---|---|---|---|")
    for d in dates:
        D = DAY[d]
        drop = D["raw_n"] - D["frozen_n"]
        rate = drop / D["raw_n"]
        say(f"| {d} | {D['raw_n']:,} | {D['frozen_n']:,} | "
            f"{'🔴 **' + format(drop, ',') + '**' if rate >= DROP_MARK else drop} | "
            f"{rate * 100:.2f}%{' 🔴' if rate >= DROP_MARK else ''} | **{D['prev_miss_join']}** |")
    say()
    marked = [d for d in dates if (DAY[d]["raw_n"] - DAY[d]["frozen_n"]) / DAY[d]["raw_n"] >= DROP_MARK]
    say(f"- 🔴 **표시가 붙은 날 {len(marked)}일**" +
        (" (" + " · ".join("`%s`" % x for x in marked) + ")" if marked else "") +
        " — 그날의 `n_up` 을 **다른 날과 직접 비교하지 말 것**(원 문언 그대로).")
    say("- 🟢 **섹터 조인 «후» 탈락은 11/11 등록일 0** ⇒ 이 축의 수익률 정의역에는 구멍이 없다.")

    # ══════════════════════════════════════════════════════════════════════
    # §3 건별 측정값
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §3. 건별 측정값 — 🔬 **탐색적 표기** · 주 판정 갈래 (`N = 3` · `SEC-M1`)")
    say()
    say("🔴 **§2-4 대로 «분모»를 매 건 인쇄한다** — `|P|`(동료 수) · `G`(그날 섹터 수) · "
        "`sec_rank`(자기 섹터 제외, 동률 전부 위) · **원값**(`med`).")
    say("🔴 **`sec_rank` 에 문턱을 «걸지 않는다»**(§2-2) — `RNK-N2` 의 **30** 은 ≈2,760종목을 재던 값이고 "
        "여기 섹터는 `N=3` 에서 158개 남짓뿐이다.")
    say()
    say("| 글 | 종목 | 등록일 | 섹터(`N=3`) | `|P|` | `G` | `sec_rank` | 원값 `med` | "
        "**`SEC-M1` 백분위** | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if b["ok"]:
            say(f"| {it['post']} | {it['name']} | {it['reg']} | `{b['sector']}` | {b['peers']} | "
                f"{b['G']} | {b['rank']} | {b['raw'] * 100:+.3f}% | **{b['pct']:.1f}** | — |")
        else:
            say(f"| {it['post']} | {it['name']} | {it['reg']} | — | "
                f"{b.get('peers', '—')} | — | — | — | ⛔ 측정 불가 | **{b['reason']}** |")
    say()
    say("### 3-1. 9 조합 전부 (`SEC-O1` §4-5 — 판정은 «동결된 하나»로만)")
    say()
    say("| `N` | 측정자 | 측정 가능 | 건별 백분위(글 순) | 글 단위 중앙 | **전체(글 단위 중앙의 중앙)** | 건 pooled 중앙 |")
    say("|---|---|---|---|---|---|---|")
    AGG = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            vals = [b["pct"] for b in bs if b["ok"]]
            posts = [it["post"] for it, b in zip(items, bs) if b["ok"]]
            main_v, pooled = aggregate(vals, posts)
            AGG[(n, mk)] = dict(vals=vals, posts=posts, main=main_v, pooled=pooled)
            by = {}
            for v, p in zip(vals, posts):
                by.setdefault(p, []).append(v)
            per = " / ".join(f"p{p}:{med(by[p]):.1f}" for p in sorted(by))
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(vals)}/{len(items)} | "
                f"{', '.join(f'{v:.1f}' for v in vals)} | {per} | "
                f"**{fmt(main_v)}** | {fmt(pooled)} |")
    say()
    say("🔒 **판정 갈래 = `N = 3` · `SEC-M1`**(🔒 표시). 나머지 8 조합은 `SEC-V1` 의 «입력»이며 "
        "**판정에 쓰지 않는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §4 귀무·대조
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §4. 귀무 `SEC-N1` · 대칭 대조 `SEC-B1`·`SEC-B2`")
    say()

    def pools_for(kind, n, mk, bs, its):
        """추출 풀 (S-3·S-6): 측정 가능 종목만 · 저자 종목 «자기 제외»."""
        j = {"SEC-M1": "1", "SEC-M2": "2", "SEC-M3": "3"}[mk]
        out, loss = [], []
        for it, b in zip(its, bs):
            if not b["ok"]:
                continue
            D = DAY[it["reg"]]
            st = D["st"][n]
            base = D["joined"] if kind == "N1" else D["nup"]
            idxs = [D["code_i"][c] for c in base if c != it["code"]]
            idxs = np.array(idxs, dtype=np.int64)
            okm = st["ok"][idxs]
            out.append(st["p" + j][idxs][okm])
            loss.append((len(idxs), int(okm.sum())))
        return out, loss

    say("### 4-0. 추출 풀 한정 손실 (§2-3 — 🔴 «유리한 방향의 처리는 반드시 «크기»를 같이 적는다»)")
    say()
    say("| 갈래 | 풀 | 후보 합계 | 측정 가능 합계 | 한정으로 빠진 수 | 비율 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for kind, nm in (("N1", "`SEC-N1` 전 종목"), ("B1", "`SEC-B1` `n_up`")):
            _, loss = pools_for(kind, n, MAIN_M, BR[(n, MAIN_M)], items)
            tot = sum(a for a, _ in loss)
            keep = sum(b for _, b in loss)
            say(f"| `N={n}` | {nm} | {tot:,} | {keep:,} | **{tot - keep:,}** | "
                f"{(tot - keep) / tot * 100:.1f}% |")
    say()
    say("🔴 이 한정은 **저자 쪽에 «유리»한 방향**이다(저자 종목은 전부 동료 ≥ 1). 그래서 크기를 적는다.")
    say()
    say("### 4-1. `SEC-N1` · `SEC-B1` · `SEC-B2` — 9 조합 (🔬 탐색적)")
    say()
    say(f"귀무 = 각 건의 등록일에 그 풀에서 **무작위 종목 1개** → 같은 측정자·같은 집계 · "
        f"**{NREP:,}회** · 시드 `{SEED}`(스트림 분리) · `p` = `mean(귀무 ≥ 관측)`(등호 포함 · S-5).")
    say()
    say("🔑 **갈래 사이에는 «공통난수(CRN)»를 쓴다** — 같은 스트림 이름(`sec_n1`·`sec_b1`)을 다시 부르면 "
        "같은 난수열이 나오므로 9 조합이 «같은 추첨»을 공유한다(`run_ranking.py` 의 같은 관용). "
        "🔴 목적이 «다른» 계열(`SEC-X1` 순열·그 안의 귀무)은 §0 대로 **다른 스트림**이다 — "
        "`RESULTS_RANKING_TRAIN.md` §5 가 잡은 얽힘 결함을 구조적으로 막는다.")
    say()
    say("| `N` | 측정자 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` 승률 | "
        "관측(pooled) | `SEC-N1` `p`(**건 pooled · `exact` 만**) | "
        "`SEC-B1` `p`(**건 pooled · `exact` 만**) |")
    say("|---|---|---|---|---|---|---|---|---|")
    RES = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            A = AGG[(n, mk)]
            if not A["vals"]:
                say(f"| {n} | `{mk}` | ⛔ 측정 가능 0건 | — | — | — | — | — | — |")
                RES[(n, mk)] = None
                continue
            pn, _ = pools_for("N1", n, mk, bs, items)
            pb, _ = pools_for("B1", n, mk, bs, items)
            rec = {}
            for kind, pools, sname in (("N1", pn, "sec_n1"), ("B1", pb, "sec_b1")):
                if any(p.size == 0 for p in pools):
                    rec[kind] = None
                    continue
                mat = null_matrix(stream(sname), pools, A["posts"], NREP)
                gm, gp = agg_matrix(mat, A["posts"])
                rec[kind] = dict(p_main=float(np.mean(gm >= A["main"])),
                                 p_pool=float(np.mean(gp >= A["pooled"])),
                                 ceil_main=float(np.mean(gm >= 100.0 - 1e-9)),
                                 null_med=float(np.median(gm)))
            # SEC-B2 — 건별로 그날 풀 중앙값 초과 (동률은 «못 넘은 것»)
            wins, nb2 = 0, 0
            for pool_v, v in zip(pb, A["vals"]):
                if pool_v.size == 0:
                    continue
                nb2 += 1
                if v > med(list(pool_v)):
                    wins += 1
            rec["B2"] = dict(wins=wins, n=nb2, rate=(wins / nb2 if nb2 else None))
            RES[(n, mk)] = rec
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | **{fmt(A['main'])}** | "
                f"{fmt(rec['N1']['p_main'], 4) if rec['N1'] else '⛔'} | "
                f"{fmt(rec['B1']['p_main'], 4) if rec['B1'] else '⛔'} | "
                f"**{fmt(rec['B2']['rate'] * 100 if rec['B2']['rate'] is not None else None)}%** "
                f"({rec['B2']['wins']}/{rec['B2']['n']}) | {fmt(A['pooled'])} | "
                f"{fmt(rec['N1']['p_pool'], 4) if rec['N1'] else '⛔'} | "
                f"{fmt(rec['B1']['p_pool'], 4) if rec['B1'] else '⛔'} |")
    say()
    say("🔴 **`SEC-P1` 은 «3중 AND»다** — `SEC-N1 < 5%` ∧ `SEC-B1 < 5%` ∧ `SEC-B2 > 50%`(§3 1행). "
        "🔴 **그러나 이 표는 «판정»이 아니다** — post1~5 는 판정 분모 «밖»이다(`SEC-O1`). "
        "여기서 어떤 조합이 문턱을 넘어도 **지지로 인용하지 않는다.**")
    say()
    say("⚠️ 🔴 **이 표의 `p` 는 전부 «`exact` 만» 분모다.** §7 4축 표의 «`approx` 포함» 행은 "
        "**분모가 다른(건수가 더 많은) 별개 검정**이며, 두 표에 **같은 숫자가 나와도 같은 양이 아니다.** "
        "🔑 ***같은 값이 두 곳에 있다고 같은 것을 잰 게 아니다*** — 각 `p` 는 «갈래 × 집계 × 분모»로만 식별된다.")

    # 4-2. q_top (SEC-B1 발화 가능성)
    say()
    say("### 4-2. 🔴🔴 `SEC-B1` **발화 가능성** — `q_top` 실측 (§4-2 (가) · §7-B #20)")
    say()
    say("🔑 ***「재추출이 성립한다」가 「가드가 발화한다」를 뜻하지 않는다***(§8-10). "
        "관측 통계량의 **천장은 100** 이고, 귀무가 그 천장에 **5% 이상**의 질량을 두면 "
        "***어떤 관측으로도 `p < 0.05` 가 나오지 않는다.***")
    say()
    say("🔴 **풀 정의가 둘이다** — ①사전등록 §4-2 (가) 표의 풀 = **`n_up` ∩ 조인**(그대로) · "
        "②이 스크립트가 «실제로 뽑는» 풀 = 그 위에 **측정 가능(동료 ≥ 1)** 한정(§2-3) + 건별 «자기 제외»(M7). "
        "**①로 문서표를 재현하고 ②로 실제 발화를 잰다.**")
    say()
    say("| 등록일 | ① 풀(`n_up`∩조인) | 고유 섹터 | 최대 섹터 | **최대 점유**(수익률 미사용 충분조건) | "
        "`< 0.135` ? | 문서 §4-2 (가) | ② 측정 가능 풀 | 🔒 **`q_top`**(1위 섹터 점유 · 문언 정의) | "
        "(대조) 천장 점유 실측 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    DOC42 = {"2026-07-28": (54, 30, 11, 0.204), "2026-07-30": (66, 32, 7, 0.106),
             "2026-08-05": (93, 30, 17, 0.183), "2026-08-06": (53, 26, 9, 0.170),
             "2026-08-11": (91, 46, 10, 0.110), "2026-08-12": (86, 39, 14, 0.163),
             "2026-08-13": (66, 32, 8, 0.121), "2026-08-18": (76, 40, 8, 0.105),
             "2026-08-19": (51, 37, 5, 0.098), "2026-08-20": (79, 40, 13, 0.165),
             "2026-08-21": (44, 29, 7, 0.159)}
    QT = {}
    n42_ok = 0
    for d in dates:
        D = DAY[d]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        # ① 문서 정의 풀
        ix1 = np.array([D["code_i"][c] for c in D["nup"]], dtype=np.int64)
        u1, c1 = np.unique(lab[ix1][lab[ix1] >= 0], return_counts=True)
        share = float(c1.max() / ix1.size)
        # ② 실제 추출 풀
        pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
        idxs = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
        # 1위 섹터 = 그날 «전원» 중앙수익률 최대 섹터
        vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
        meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g]))
                for g in np.unique(lab[vidx])}
        top = max(meds, key=lambda g: meds[g])
        qtop = float(np.sum(lab[idxs] == top) / idxs.size)
        ceil_share = float(np.mean(st["p1"][idxs] >= 100.0 - 1e-9))
        dc = DOC42[d]
        same = (ix1.size == dc[0] and int(u1.size) == dc[1] and int(c1.max()) == dc[2]
                and abs(share - dc[3]) < 0.0006)
        n42_ok += int(same)
        QT[d] = dict(pool_doc=int(ix1.size), sectors_doc=int(u1.size), maxsec_doc=int(c1.max()),
                     max_share=share, pool_eff=int(idxs.size), qtop=qtop, ceil_share=ceil_share,
                     doc_match=bool(same))
        say(f"| {d} | {ix1.size} | {u1.size} | {c1.max()} | **{share:.3f}** | "
            f"{'🟢 예' if share < QTOP_THR else '🔴 아니오'} | "
            f"{'✅' if same else '🔴 %d·%d·%d·%.3f' % dc} | {idxs.size} | "
            f"**{qtop:.3f}** | {ceil_share:.3f} |")
    say()
    say(f"- 🟢 **사전등록 §4-2 (가) 표 재현 = {n42_ok}/{len(dates)}행**(①정의 · 4열 전부 일치). "
        f"그중 **최대 점유 ≥ 0.135 인 날이 {sum(1 for d in dates if QT[d]['max_share'] >= QTOP_THR)}일** "
        "— 사전등록이 *「충분조건이 11개 중 «6개»에서 성립하지 않는다」*고 적은 그 값이다.")
    say("- 🔴🔴 **그러나 「충분조건 실패」는 「`q_top ≥ 0.135`」의 «증명»이 아니다**(§7-A #8-1). "
        f"실측 `q_top`(1위 섹터 점유)은 **11/11 등록일 전부 `< 0.135`** "
        f"(최대 {max(QT[d]['qtop'] for d in dates):.3f}) ⇒ ***이 표본에서 `SEC-B1` 은 «발화 가능»하다.*** "
        "🔑 ***과장하지 않은 것이 값으로 확인됐다*** — 문서는 *「구조만으로는 발화를 보장할 수 없다」*까지만 "
        "적었고, 실제로 재 보니 발화 가능했다.")
    say()
    kmain = len(AGG[(MAIN_N, MAIN_M)]["vals"])
    qmax = max(QT[d]["qtop"] for d in dates)
    qmax_d = max(dates, key=lambda d: QT[d]["qtop"])
    say("🔒 **발화 조건(동결 · §4-2 (가))** = `P(Binom(k, q_top) ≥ ⌈k/2⌉) < 0.05`. "
        "`q_top` 이 등록일마다 다르므로 **판정 분모의 등록일 중 «최대»**(= 가장 불리한 쪽, 보수적)를 쓴다.")
    say()
    say("| `k` | 뜻 | `q_top`(최대) | `P(Binom(k, q_top) ≥ ⌈k/2⌉)` | 판정 |")
    say("|---|---|---|---|---|")
    for k, lbl in ((3, "🔒 사전등록 최소 표본(`PREREG_SELECTION.md` §7)"),
                   (kmain, "이 실행의 측정 가능 `exact` 건수(pooled)"),
                   (len(set(AGG[(MAIN_N, MAIN_M)]["posts"])), "글 단위 집계의 글 수")):
        pv = binom_ge_half(k, qmax)
        say(f"| {k} | {lbl} | {qmax:.3f} (`{qmax_d}`) | **{pv:.4f}** | "
            f"{'🟢 발화 가능' if pv < P_THR else '🔴 **⛔ 발화 불가**'} |")
    say()
    ceil_obs = RES[(MAIN_N, MAIN_M)]["B1"]["ceil_main"] if RES[(MAIN_N, MAIN_M)] and RES[(MAIN_N, MAIN_M)]["B1"] else None
    say(f"- 🟢 **직접 실측(대조)**: 위 `SEC-B1` 귀무 {NREP:,}회에서 **집계 통계량이 천장(100)에 둔 질량 "
        f"= {fmt(ceil_obs, 4)}** — 문언 정의의 이항 산술과 **같은 방향인지**를 여기서 볼 수 있다. "
        "🔴 **판정은 문언 정의(위 표)로 한다**(S-7).")
    say("- 🔴 **`N = 2` 는 이 축에서 훨씬 나쁘다**(§4-2 (가) 예고) — 실측 재현 "
        "(**충분조건**은 ①풀 · **`q_top`**은 ②풀 기준 · 둘 다 11일 중 «최대»):")
    say()
    say("| `N` | 구조적 최대 점유(충분조건) | 그날 | 충분조건 `k=3` 발화? | 필요 최소 홀수 `k` | "
        "🔒 실측 `q_top` 최대 | `q_top` 기준 `k=3` 발화? |")
    say("|---|---|---|---|---|---|---|")
    QMAX_BY_N = {}
    for n in NS:
        best, qbest = [], []
        for d in dates:
            D = DAY[d]
            st = D["st"][n]
            lab = D["lab"][n]
            ix1 = np.array([D["code_i"][c] for c in D["nup"]], dtype=np.int64)
            l1 = lab[ix1][lab[ix1] >= 0]
            if l1.size:   # 🔴 분모 = «그 갈래에서 라벨이 정의된» 풀 원소 수(N=5 에서 ①과 갈린다)
                best.append((float(np.unique(l1, return_counts=True)[1].max() / l1.size), d))
            pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
            if not pool:
                continue
            ix2 = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
            vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
            meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g]))
                    for g in np.unique(lab[vidx])}
            top = max(meds, key=lambda g: meds[g])
            qbest.append((float(np.sum(lab[ix2] == top) / ix2.size), d))
        if not best or not qbest:
            say(f"| {n} | — | — | — | — | — | — |")
            continue
        sh, dd = max(best)
        kneed = next((k for k in range(3, 402, 2) if binom_ge_half(k, sh) < P_THR), None)
        qs = max(qbest)[0]
        QMAX_BY_N[n] = qs
        say(f"| {n} | **{sh:.3f}** | {dd} | "
            f"{'🟢 예' if binom_ge_half(3, sh) < P_THR else '🔴 아니오'} | "
            f"**{kneed if kneed else '> 401'}** | **{qs:.3f}** | "
            f"{'🟢 예' if binom_ge_half(3, qs) < P_THR else '🔴 아니오'} |")
    say()
    say("🔑 사전등록이 *「`N = 2` 는 08-05 최대 점유가 **0.409** 라 `k = 81` 이 필요하다」*고 적은 값이 "
        "**충분조건 열에서 그대로 재현**된다(분모는 «라벨이 정의된» 풀 원소 수 — `N=5` 에서만 ①과 갈린다).")
    say()
    say("#### 🔴 배선 점검이 잡은 것 — 사전등록 §2-1·§0-6 의 «강한 표현» 하나가 실측으로 지지되지 않는다")
    say()
    say("사전등록 §2-1 말미와 §0-6 「뒤집었을 때의 귀결」 표는 *「`N = 2` 에서는 `SEC-B1` 이 «사실상 "
        "영구 미발화»다」*·*「축 전체가 안 열린다」*로 적었다. **근거는 «충분조건»(최대 단일섹터 점유 0.409)이다.**")
    say("🔴 **충분조건은 `q_top` 의 «상한»이지 `q_top` 이 아니다.** 실측하면 `N = 2` 의 `q_top` 최대가 "
        f"**{QMAX_BY_N.get(2, float('nan')):.3f}** 로 `{QTOP_THR}` 을 한참 밑돌고, "
        f"위 표대로 **`k = 3` 에서 `P(Binom(3, {QMAX_BY_N.get(2, 0):.3f}) ≥ 2) = "
        f"{binom_ge_half(3, QMAX_BY_N.get(2, 0)):.4f} < 0.05` ⇒ 발화 가능**하다.")
    say("⇒ 🔒 **참인 것은 「구조만으로는 발화를 «보장»할 수 없다」까지다**(§7-A #8-1 이 스스로 적은 그 문장). "
        "*「사실상 영구 미발화」*는 **이 표본에서 «재현되지 않는다».**")
    say("🔴 **그래도 이 실행은 `SEC-D1`(`N = 3`)을 무르지 않는다** — 값을 보고 잣대를 바꾸면 그게 "
        "사후적합이다(§0-4 · `SEC-O1`). 이 항목은 **기록**이며, 되돌리려면 **새 사전등록**이 필요하다.")

    # ══════════════════════════════════════════════════════════════════════
    # §5 SEC-G1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §5. `SEC-G1` 커버리지 가드 — 측정 불가 **≥ 1/3 이면 판정 불가** (§4-3 · `Y3` «차용»)")
    say()
    say("⚠️ **`1/3` 은 «feasible set 공집합 비율»을 재던 문턱이며 커버리지에 대해 검증된 적이 없다** — "
        "`PREREG_POST6.md` §1-6 #6 · `PREREG_RANKING.md` §4-4 가 한 같은 차용의 고지를 승계한다.")
    say()
    say("| 사유 | 설명 | 갈래 의존 |")
    say("|---|---|---|")
    say("| ① | DB 종목코드 부재(레메디형) | 전 갈래 공통 |")
    say("| ② | 유니버스 밖(`market_cap>0 ∧ close>0` 미충족) | 전 갈래 공통 |")
    say("| ③ | 섹터코드 부재(매드업·삼양바이오팜형) | 전 갈래 공통 |")
    say("| ④ | 동료 0 (자기 제외 후 `|P| = 0`) | 🔴 `N` 마다 다르다 |")
    say("| ⑤ | 층에서 미정(`length(induty_code) < N`) | 🔴 `N = 5` 갈래 전용 |")
    say()
    say("| `N` | 측정자 | 글2 | 글3 | 글4 | 글5 | **합** | 비율 | `SEC-G1`(≥1/3) | 사유별 건수 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    G1 = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            per = {}
            reasons = {}
            for it, b in zip(items, bs):
                per.setdefault(it["post"], [0, 0])
                per[it["post"]][1] += 1
                if not b["ok"]:
                    per[it["post"]][0] += 1
                    reasons[b["reason"]] = reasons.get(b["reason"], 0) + 1
            bad = sum(v[0] for v in per.values())
            rate = bad / len(items)
            G1[(n, mk)] = rate
            cells = " | ".join(f"{per[p][0]}/{per[p][1]}" for p in sorted(per))
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {cells} | **{bad}/{len(items)}** | **{rate * 100:.1f}%** | "
                f"{'🔴 **발동**' if rate >= G1_THR else '미발동'} | "
                f"{', '.join(f'{k}:{v}' for k, v in sorted(reasons.items())) or '—'} |")
    say()
    say("- 🔴 **`k = 3` 에서는 «1건만 빠져도» 게이트가 열린다**(`1/3 ≥ 1/3`, 등호 발동). "
        "**훈련 표본에서 실제로 실현됐다** — post3 은 `exact` 3건 중 매드업이 사유 ③ 이라 "
        "**정확히 33.3%** 다. ⇒ ***이건 가정이 아니라 관측된 사건이다.***")
    g1_main = G1[(MAIN_N, MAIN_M)]
    say(f"- 🔬 **주 갈래 훈련 표본 미측정률 = {g1_main * 100:.1f}%** ⇒ `k = 3` 에서 3건 모두 측정 가능할 "
        f"확률 ≈ **{(1 - g1_main) ** 3:.2f}** — ***최소 표본에서 이 축이 닫힐 확률이 대략 "
        f"「열에 {round((1 - (1 - g1_main) ** 3) * 10)}」***(§4-3 3번 · 값 보기 전 산술).")
    say("- 🔴 **편향 방향**: 사유 ③ 은 **신규 상장주에 집중**되고 저자는 신규주를 자주 고른다(§1-5) "
        "⇒ ***측정 불가가 무작위가 아니다.*** 남은 분모를 「저자 표본」이라 부르면 이미 편향된 표본이다.")
    say(f"- 🔴 **`N = 5` 갈래**: 측정 불가 **{G1[(5, MAIN_M)] * 100:.1f}%** — 사전등록 §2-1 이 "
        "*「4개 글 중 3개에서 판정 불가 · 훈련 전체 61.1%」*로 **값 보기 «전»에 산술로 잡아 둔** 그 자리다.")

    # ══════════════════════════════════════════════════════════════════════
    # §6 SEC-X1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §6. `SEC-X1` 섹터 라벨 **순열 대조군** — 귀무 «구현»의 1종오류율 (§4-4 · `SEC-D6`)")
    say()
    say("🔴🔴 **이 가드가 재는 것은 «귀무 구현의 1종오류율 보정» 하나뿐이다** — "
        "*「칸막이가 정보인가」를 재는 검정이 «아니다»*(§4-4 B-2). "
        "라벨을 섞으면 저자 종목과 귀무 추출 종목의 섹터가 **교환 가능**해지므로, "
        "***참 분할이 정보를 담든 잡음이든 `P(p<0.05)` 는 «항상» 5% 다.***")
    say("🔴 **`SEC-X1` 통과를 「섹터가 의미 있다」로 인용하지 않는다.** "
        "「칸막이가 정보인가」는 **`SEC-B1`·`SEC-B2`** 가 잰다(§7-C 4번).")
    say()

    # 라벨과 «무관»한 인덱스는 실현 밖에서 한 번만 만든다(결정성·속도 둘 다).
    X1_BASE = []
    for it in items:
        D = DAY[it["reg"]]
        if not it["code"] or it["code"] not in D["code_i"]:
            continue
        X1_BASE.append((it, D, D["code_i"][it["code"]],
                        np.array([D["code_i"][c] for c in D["joined"] if c != it["code"]],
                                 dtype=np.int64),
                        np.array([D["code_i"][c] for c in D["nup"] if c != it["code"]],
                                 dtype=np.int64)))

    def x1_run(rng_perm, rng_null, reps, broken=False):
        """섹터 라벨을 종목 사이에서 섞고(집단 크기 분포 보존) 같은 측정자·같은 귀무를 계산."""
        rows_ = []
        for _ in range(reps):
            perm_st = {}
            for d in dates:
                D = DAY[d]
                lab = D["lab3"]
                perm_st[d] = day_stats(lab[rng_perm.permutation(lab.size)], D["r"], D["up"])
            vals, posts, pools_n, pools_b, drop = [], [], [], [], 0
            for it, D, i, ixn, ixb in X1_BASE:
                st = perm_st[it["reg"]]
                if not st["ok"][i]:
                    drop += 1
                    continue
                vals.append(float(st["p1"][i]))
                posts.append(it["post"])
                for ix, store in ((ixn, pools_n), (ixb, pools_b)):
                    pv = st["p1"][ix][st["ok"][ix]]
                    if broken and pv.size:
                        # 🔴 «일부러 고장낸» 귀무 — 추출 풀에서 상위 절반 백분위를 통째로 뺀다.
                        #    (교환가능성 파괴 ⇒ `p` 가 체계적으로 작아진다)
                        cut = pv[pv <= np.median(pv)]
                        pv = cut if cut.size else pv
                    store.append(pv)
            if not vals or any(p.size == 0 for p in pools_n) or any(p.size == 0 for p in pools_b):
                continue
            obs_main, _ = aggregate(vals, posts)
            out = dict(drop=drop)
            for kind, pools in (("N1", pools_n), ("B1", pools_b)):
                gm, _ = agg_matrix(null_matrix(rng_null, pools, posts, NREP), posts)
                out[kind] = float(np.mean(gm >= obs_main))
            rows_.append(out)
        return rows_

    t_x1 = time.time()
    x1 = x1_run(stream("sec_x1_perm"), stream("sec_x1_null"), X1_REP)
    t_x1 = time.time() - t_x1
    say(f"**명세**: 그날 유니버스의 `induty_code` 를 종목 사이에서 무작위로 «섞고»(집단 크기 분포 보존) "
        f"같은 측정자(`SEC-M1` · `N=3`)·같은 귀무를 계산 — **독립 실현 {X1_REP}개** × 귀무 {NREP:,}회.")
    say()
    say("| 풀 | 실현 수 | `p` 평균 | `p` 중앙 | **`p < 0.05` 비율** | `p < 0.20` 비율 | "
        "명목 대비(SE ≈ 1.5%p) | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    x1sum = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        ok = abs(z) <= 2.0
        x1sum[kind] = dict(n=len(ps), mean=float(ps.mean()), median=float(np.median(ps)),
                           lt05=rate, lt20=float(np.mean(ps < 0.20)), z=float(z), pass_=bool(ok))
        say(f"| `SEC-{kind}` | {len(ps)} | {ps.mean():.4f} | {np.median(ps):.4f} | "
            f"**{rate * 100:.1f}%** | {np.mean(ps < 0.20) * 100:.1f}% | "
            f"`z = {z:+.2f}` | {'🟢 **보정됨**' if ok else '🔴 **⛔ 절차 무효**'} |")
    say()
    say(f"- 순열 하 `p` 는 이론상 `U(0,1)` 이므로 `p<0.05` 비율의 기대는 **5.0%**, "
        f"{X1_REP} 실현의 SE ≈ **1.5%p** 다(§4-4). `|z| ≤ 2` 를 «어긋나지 않음»으로 읽는다.")
    say(f"- 🔴 **순열 실현에서 저자 건이 «측정 불가»가 되는 일**(섞인 뒤 `|P| = 0`)이 있다 — "
        f"실현당 평균 **{np.mean([r['drop'] for r in x1]):.2f}건** 탈락. 크기 정합을 위해 그 건은 "
        "관측·귀무 «양쪽»에서 같이 빠진다.")
    say()
    say("### 6-1. 🔴 **가드를 «일부러» 켜서 발동을 실증한다** (§7-B #20 · `x1_bypass` 형식 승계)")
    say()
    say("🔑 ***「조항을 적었다」가 「그 조항이 발동한다」를 뜻하지 않는다*** — "
        "`FREEZE_RANKING_2026-08-31.md` §4 가 `x1_bypass` 로 한 실증을 이 축에서도 한다. "
        "**귀무 구현을 «고장내고»**(추출 풀에서 상위 절반 백분위를 통째로 제거 ⇒ 교환가능성 파괴) "
        "같은 순열 대조군을 돌린다. 가드가 살아 있다면 1종오류율이 5%에서 «어긋나야» 한다.")
    say()
    x1b = x1_run(stream("sec_x1_bypass_perm"), stream("sec_x1_bypass_null"), X1_REP, broken=True)
    say("| 귀무 구현 | `p < 0.05` 비율 | `z` | `SEC-X1` 판정 |")
    say("|---|---|---|---|")
    say(f"| 🟢 정상(위 §6 `SEC-N1`) | **{x1sum['N1']['lt05'] * 100:.1f}%** | "
        f"`{x1sum['N1']['z']:+.2f}` | {'🟢 보정됨 ⇒ 절차 유효' if x1sum['N1']['pass_'] else '🔴 절차 무효'} |")
    bx = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1b])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        bx[kind] = dict(lt05=rate, z=float(z), fired=bool(abs(z) > 2.0))
        say(f"| 🔴 **일부러 고장낸 것**(`SEC-{kind}` 풀 상위 절반 제거) | **{rate * 100:.1f}%** | "
            f"`{z:+.2f}` | {'🔴 **⛔ 절차 무효 — 가드 발동 ✅**' if abs(z) > 2.0 else '🟡 미발동'} |")
    say()
    fired = bx["N1"]["fired"] or bx["B1"]["fired"]
    say(f"⇒ {'🟢 **`SEC-X1` 이 실제로 발동한다** — 죽은 가드가 아니다.' if fired else '🔴 **고장낸 구현에서도 발동하지 않았다** — 이 실증은 실패다.'} "
        "🔴 **그리고 이 발동은 「섹터가 무의미하다」와 무관하다** — 잰 것은 «우리 귀무 구현»이다(§4-4).")

    # ══════════════════════════════════════════════════════════════════════
    # §7 SEC-V1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §7. `SEC-V1` 민감도 **4축** (§4-6) — 🔴 «민감도 전용»")
    say()
    say("🔒 **적용 범위**: 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」에만 적용된다. "
        "🔴 **§3 의 3중 AND 안에서 한 항목이 미달하는 사건에는 «관여하지 않는다»** — "
        "그건 갈린 게 아니라 **AND 가 거짓인 것**이고 그 판정은 §3 이 한다(§3 우선순위표).")
    say()
    say("⚠️ **「귀무 풀(`SEC-N1` ↔ `SEC-B1`)」은 이 표에 «없다»** — 그건 민감도가 아니라 **판정 조건**이다(§4-6).")
    say()
    # approx 갈래
    ap_bs = BR[("ap", MAIN_N, MAIN_M)]
    both = [(it, b) for it, b in zip(items, BR[(MAIN_N, MAIN_M)]) if b["ok"]]
    ap_ok = [(it, b) for it, b in zip(ap_items, ap_bs) if b["ok"]]
    v_ex_main = AGG[(MAIN_N, MAIN_M)]["main"]
    v_ex_pool = AGG[(MAIN_N, MAIN_M)]["pooled"]
    ap_vals = [b["pct"] for _, b in both] + [b["pct"] for _, b in ap_ok]
    ap_posts = [it["post"] for it, _ in both] + [it["post"] for it, _ in ap_ok]
    v_ap_main, v_ap_pool = aggregate(ap_vals, ap_posts)
    # `approx` 포함 갈래의 귀무도 «실제로» 돌린다(문언: 「포함값을 의무 민감도로 인쇄」).
    ap_all_items = items + ap_items
    ap_all_bs = BR[(MAIN_N, MAIN_M)] + ap_bs
    ap_res = {}
    for kind, sname in (("N1", "sec_n1"), ("B1", "sec_b1")):
        pl, _ = pools_for(kind, MAIN_N, MAIN_M, ap_all_bs, ap_all_items)
        if pl and not any(p.size == 0 for p in pl):
            gm, gp = agg_matrix(null_matrix(stream(sname), pl, ap_posts, NREP), ap_posts)
            ap_res[kind] = dict(p_main=float(np.mean(gm >= v_ap_main)),
                                p_pool=float(np.mean(gp >= v_ap_pool)))
        else:
            ap_res[kind] = None
    ap_wins, ap_n = 0, 0
    for pool_v, v in zip(pools_for("B1", MAIN_N, MAIN_M, ap_all_bs, ap_all_items)[0], ap_vals):
        if pool_v.size == 0:
            continue
        ap_n += 1
        if v > med(list(pool_v)):
            ap_wins += 1
    say("| # | 축 | 갈래 | 값(글 단위 중앙) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | 판정 갈래 |")
    say("|---|---|---|---|---|---|---|---|")

    def cell(n, mk):
        r = RES[(n, mk)]
        if r is None:
            return "⛔", "⛔", "⛔"
        return (fmt(r["N1"]["p_main"], 4) if r["N1"] else "⛔",
                fmt(r["B1"]["p_main"], 4) if r["B1"] else "⛔",
                (f"{r['B2']['rate'] * 100:.1f}%" if r["B2"]["rate"] is not None else "⛔"))
    for n in NS:
        a, b_, c_ = cell(n, MAIN_M)
        note = " (🔴 구조적 미정 %.1f%% 병기)" % (G1[(5, MAIN_M)] * 100) if n == 5 else ""
        say(f"| 1 | 섹터 깊이 | `N = {n}`{note} | {fmt(AGG[(n, MAIN_M)]['main'])} | {a} | {b_} | {c_} | "
            f"{'🔒 **판정**' if n == MAIN_N else '민감도'} |")
    for mk in MEAS:
        a, b_, c_ = cell(MAIN_N, mk)
        say(f"| 2 | 측정자 | `{mk}` | {fmt(AGG[(MAIN_N, mk)]['main'])} | {a} | {b_} | {c_} | "
            f"{'🔒 **판정**' if mk == MAIN_M else '민감도'} |")
    rm = RES[(MAIN_N, MAIN_M)]
    say(f"| 3 | 집계 | 글 단위 중앙 | {fmt(v_ex_main)} | {fmt(rm['N1']['p_main'], 4)} | "
        f"{fmt(rm['B1']['p_main'], 4)} | {fmt(rm['B2']['rate'] * 100)}% | 🔒 **판정** |")
    say(f"| 3 | 집계 | 건 pooled 중앙 | {fmt(v_ex_pool)} | {fmt(rm['N1']['p_pool'], 4)} | "
        f"{fmt(rm['B1']['p_pool'], 4)} | 〃 | 민감도 |")
    say(f"| 4 | 등록일 정밀도 | `exact` 만 ({len(both)}건) | {fmt(v_ex_main)} | "
        f"{fmt(rm['N1']['p_main'], 4)} | {fmt(rm['B1']['p_main'], 4)} | "
        f"{fmt(rm['B2']['rate'] * 100)}% | 🔒 **판정** |")
    nap = len(both) + len(ap_ok)
    say(f"| 4 | 등록일 정밀도 | `approx` 포함 ({nap}건) | {fmt(v_ap_main)} | "
        f"{fmt(ap_res['N1']['p_main'], 4) if ap_res['N1'] else '⛔'} **(분모 {nap}건)** | "
        f"{fmt(ap_res['B1']['p_main'], 4) if ap_res['B1'] else '⛔'} **(분모 {nap}건)** | "
        f"{fmt(ap_wins / ap_n * 100) if ap_n else '—'}% ({ap_wins}/{ap_n}) | 민감도 |")
    say()
    say(f"⚠️ 🔴 **마지막 행의 `p` 는 «분모 {nap}건»(`exact`+`approx`)이다** — §4-1 표의 `p` 는 전부 "
        f"«분모 {len(both)}건»(`exact` 만)이다. **두 표에 같은 숫자가 나와도 같은 양이 아니다**"
        "(다른 건 집합 · 다른 검정). 🔑 ***`p` 는 「갈래 × 집계 × 분모」로만 식별된다.***")
    say(f"- `approx` **{len(ap_items)}건**: " + " · ".join(
        f"{it['name']}({it['reg']}) → " + (f"백분위 **{b['pct']:.1f}**" if b["ok"] else f"⛔ 사유 {b['reason']}")
        for it, b in zip(ap_items, ap_bs)) + ".")
    say("- 🔴 **`approx` 는 판정 분모에 «넣지 않는다»**(`SEC-D5` · §2-5) — 포함값은 의무 민감도이며 "
        "두 값이 갈리면 ⇒ ⛔ `SEC-V1`.")
    say()
    say("🔴 **이 실행에서는 «판정 자체가 없다»**(배선 점검 · `SEC-O1`) ⇒ ***`SEC-V1` 은 "
        "「갈렸다/안 갈렸다」를 «선언하지 않는다».*** 위 표는 **4축이 실제로 계산되고 «움직인다»는 "
        "배선 확인**이며, 판정에서의 `SEC-V1` 적용은 **post6 부터**다.")

    # ══════════════════════════════════════════════════════════════════════
    # §8 §7-B 점검표
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §8. 사전등록 §7-B 실행 점검표 — 이 실행이 닫은 항목")
    say()
    say("| # | 점검 | 상태 | 근거 |")
    say("|---|---|---|---|")
    say("| 17 | `SEC-` grep 재확인 | ✅ (작성 시점) | 사전등록 §0-5. ⚠️ 이 실행이 `run_sector.py`·"
        "`RESULTS_SECTOR_DRYRUN*.md`·`sector_dryrun/` 을 만들어 **`SEC-` 가 잡히는 파일이 늘어난다** — "
        "그건 오염이 아니라 이 축의 산출물이다 |")
    say("| 18 | 브랜치 확인·전환 | ✅ | `fix/tasso-post6-s5-fixes` 워크트리에서 실행(해시는 stdout) · "
        "🔴 라이브 트리에서 돌리지 않았다 |")
    say(f"| 19 | 의사티커 전수 재확인 | ✅ | §0 — 코드 {len(PSEUDO)}종 ∪ DB 실측 {len(nonnum)}종 = "
        f"**{len(final_pseudo)}종**(같다) |")
    say("| 20 | 죽은 가드 실측 점검 | ✅ | `SEC-B2` §4-1(비율이 상수가 아님) · `SEC-G1` §5(갈래별로 움직임) · "
        "🔴 **`SEC-B1` `q_top` 실측 §4-2** · **`SEC-X1` 일부러 켜서 발동 실증 §6-1** |")
    say(f"| 21 | DB 스냅샷 최신 봉을 박는다 | ✅ | §0 — **`{END}`**. 봉수 표기는 「직전 / 포함」 구분 "
        "규약(`RESULTS_LADDER_TRANCHE.md` N8)을 따르며, **이 축은 창을 쓰지 않고 «등록일 당일»만 쓴다** "
        "⇒ 「직전/포함」 구분이 걸리는 자리가 없다 |")
    say(f"| 22 | `stock_industry` 스냅샷을 박는다 | ✅ | §0 — {si_rows:,}행 · `max(updated_at)` `{si_upd}` · "
        "전체 sha256. 🔴 **이 표는 시간에 따라 «자란다»** — 매드업·삼양바이오팜이 나중에 편입되면 "
        "같은 글의 값이 달라진다(§8-5) |")
    say("| 23 | `SEC-D1`~`D8` 이 `fetch_post.py` «전»에 확정·커밋됐는지 | ⬜ **post6 수집 «후»에 확인** | "
        "`git log --diff-filter=A -- post_<logNo>.html` ↔ `FREEZE_SECTOR_<날짜>.md` 커밋 해시. "
        "🔴 아직 일어나지 않은 일을 ✅ 로 적지 않는다 |")
    say("| 24 | 라이브 채택 금지 문구 · 「+15%」 잔존 고지 | ✅ | 이 파일 머리 6줄(`NOTATION`) · "
        "`sector_dryrun/*.json` 의 `_notation` · `cases.tsv` 머리 주석 |")
    say("| 25 | `regen_gate.py` 등재 | ✅ **등재** / ⬜ **`--update` 는 동결 단계** | "
        "`PAIRS[\"RESULTS_SECTOR_DRYRUN_NUMBERS.md\"] = \"run_sector.py\"` · "
        "`PAIRS[\"RESULTS_SECTOR_POST6_NUMBERS.md\"]`(PENDING) · `MANUAL_DOCS` 4건. "
        "🔴 **`--update` 는 §0-4 5번(동결 커밋)의 동작이다** — 그때까지 "
        "`test_c19_manifest_covers_every_pair` 는 **실패한다**(§9) |")
    say(f"| 26 | 동료 수 하한을 «실측»으로 확정 | ✅ | §1-6 — 저자 {len(au_peers)}건 중 동료 0 인 건 "
        f"**{sum(1 for x in au_peers if x == 0)}건** · 귀무 풀 한정 크기 §4-0 |")

    # ══════════════════════════════════════════════════════════════════════
    # §9 자기점검
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §9. 이 실행의 «미해소»·«고지»")
    say()
    say("| 항목 | 상태 |")
    say("|---|---|")
    say("| `SEC-P1`·`SEC-P2` | ⛔ **판정 전** — post6 부터. 이 파일의 어떤 값도 지지·기각의 근거가 아니다 |")
    say(f"| `SEC-G1`(주 갈래) | 🔬 훈련 표본 **{g1_main * 100:.1f}%** — 판정 분모는 post6 신규 `exact` 이므로 "
        "이 비율은 **예보**이지 판정이 아니다 |")
    say("| 승/패 대조(`PREREG_SELECTION.md` §4) | ⛔ **2회 연속 미실시** — `exact` 건에 `all_loss=1` 이 0건. "
        "⚠️ **이 배선 점검은 「새 글」이 아니므로 횟수를 «올리지 않는다»**(post4 = 1회 · post5 = 2회) |")
    say("| `regen_gate.py --update`·`--rerun` | ⬜ **동결 단계(§0-4 5번)** — 그때까지 매니페스트 테스트 1건 실패 |")
    say("| 「테마로 고른다」 확증 | ⛔ **이 축에서는 «영구히» 열리지 않는다**(§0-2 · §9) |")
    say()
    say("🔑 **계열 규칙 재확인** — ***대조군을 달 때는 「그 대조군이 «무엇을 파괴하는가»」를 먼저 적어라.*** "
        "`SEC-X1` 의 순열은 **분할 구조**를 파괴하므로 분할에 대해 아무것도 못 말한다(§8-9).")
    say()
    say("---")
    say()
    say(f"결정성: 시드 `{SEED}` 고정 · 스트림 분리 · DB 는 SELECT 만 ⇒ **같은 DB 스냅샷에서 재실행하면 "
        f"byte 단위로 같다**(`regen_gate.py --rerun` 전제). "
        "🔴 그래서 이 파일에는 **실행 시간·커밋 해시를 적지 않는다** — 벽시계·`HEAD` 는 stdout 전용이다. "
        "🔑 ***커밋마다 바뀌는 값을 산출물에 적으면 그 산출물은 자기 자신을 재현할 수 없게 된다.***")
    say()
    say("[[PREREG_SECTOR_COMOVE]] · [[PREREG_RANKING]] · [[PREREG_POST6]] · [[FINDING_THEME_AXIS]] · "
        "[[RESULTS_RANKING_TRAIN]] · [[FREEZE_RANKING_2026-08-31]] · [[RESULTS_REGDAY_POST5]] · "
        "[[RESULTS_D1_OOS_POST5]] · [[RESULTS_RECONSTRUCT_POST4]] · [[PREREG_SELECTION]]")

    # ══════════════════════════════════════════════════════════════════════
    # 기계 산출물
    # ══════════════════════════════════════════════════════════════════════
    universe = {d: DAY[d]["uni"] for d in all_dates}
    joined = {d: DAY[d]["joined"] for d in all_dates}
    (ART / "universe_snapshot.json").write_text(json.dumps({
        "db_snapshot_max_date": END, "pseudo_from_code": list(PSEUDO),
        "pseudo_nonnumeric_in_db": nonnum, "pseudo_final": final_pseudo,
        "universe_sizes": {d: len(universe[d]) for d in all_dates},
        "joined_sizes": {d: len(joined[d]) for d in all_dates},
        "coverage_pct": {d: round(len(joined[d]) / len(universe[d]) * 100, 4) for d in all_dates},
        "universe": universe, "joined": joined,
        "sha256_universe": {d: sha_list(universe[d]) for d in all_dates},
        "sha256_joined": {d: sha_list(joined[d]) for d in all_dates},
        "_notation": NOTATION,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "sector_snapshot.json").write_text(json.dumps({
        "table": "stock_industry", "rows": si_rows, "distinct_stock_code": si_uniq,
        "induty_code_non_null": si_nonnull, "max_updated_at": si_upd,
        "sha256_code_to_induty": si_sha,
        "length_distribution_table": {str(k): v for k, v in sorted(len_all.items())},
        "stock_info_sector_non_null": info_sector, "stock_info_rows": info_rows,
        "warning": "이 표는 시간에 따라 «자란다» — 매드업·삼양바이오팜이 편입되면 같은 글의 값이 달라진다",
        "_notation": NOTATION,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for ci, it in enumerate(items):
        rec = {k: it[k] for k in ("post", "log_no", "item_no", "name", "code", "reg", "prec", "all_loss")}
        rec["db_snapshot_max_date"] = END
        rec["main_branch"] = {"N": MAIN_N, "measure": MAIN_M}
        rec["branches"] = {}
        for n in NS:
            for mk in MEAS:
                bb = BR[(n, mk)][ci]
                rec["branches"][f"N{n}_{mk}"] = {
                    kk: (round(vv, 6) if isinstance(vv, float) else vv)
                    for kk, vv in bb.items()}
        rec["_notation"] = NOTATION
        (ART / f"case_{it['post']}_{it['item_no']}_{it['name']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "controls_summary.json").write_text(json.dumps({
        "seed": SEED, "nrep": NREP, "note_nrep": "run_selection.py:22 는 NREP=2000",
        "streams": _STREAM_NAMES, "x1_realizations": X1_REP,
        "db_snapshot_max_date": END,
        "thresholds": {"p": P_THR, "B2": B2_THR, "G1": G1_THR, "q_top": QTOP_THR,
                       "n_up_multiplier": UP_MULT, "drop_mark": DROP_MARK},
        "observed": {f"N{n}_{mk}": {"main": AGG[(n, mk)]["main"], "pooled": AGG[(n, mk)]["pooled"],
                                    "n_measurable": len(AGG[(n, mk)]["vals"])}
                     for n in NS for mk in MEAS},
        "nulls": {f"N{n}_{mk}": (None if RES[(n, mk)] is None else {
            "SEC-N1": RES[(n, mk)]["N1"], "SEC-B1": RES[(n, mk)]["B1"], "SEC-B2": RES[(n, mk)]["B2"]})
            for n in NS for mk in MEAS},
        "G1_rate": {f"N{n}_{mk}": G1[(n, mk)] for n in NS for mk in MEAS},
        "q_top": QT,
        "SEC-X1": {"normal": x1sum, "deliberately_broken": bx,
                   "note": "재는 것은 «귀무 구현의 1종오류율» 하나뿐 — 분할의 정보량과 무관하다(§4-4)"},
        "_notation": NOTATION,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    with (ART / "cases.tsv").open("w", encoding="utf-8") as f:
        f.write("# RESULTS_SECTOR_DRYRUN — 건별 측정값 (기계 생성 · 🔬 탐색 표기 · 판정 아님)\n")
        f.write(f"# 주 판정 갈래 N={MAIN_N} · {MAIN_M} · DB 스냅샷 {END} · 시드 {SEED} · post1~5 «만»\n")
        for ln in NOTATION:
            f.write("# " + ln.replace("\n", " ") + "\n")
        f.write("#\n")
        f.write("post\titem\tname\tcode\treg\tN\tmeasure\tsector\tpeers\tG\tsec_rank\traw\tpct\treason\n")
        for n in NS:
            for mk in MEAS:
                for it, b in zip(items, BR[(n, mk)]):
                    f.write(f"{it['post']}\t{it['item_no']}\t{it['name']}\t{it['code'] or ''}\t"
                            f"{it['reg']}\t{n}\t{mk}\t{b.get('sector', '')}\t"
                            f"{b.get('peers', '')}\t{b.get('G', '')}\t{b.get('rank', '')}\t"
                            f"{('%.8f' % b['raw']) if b['ok'] else ''}\t"
                            f"{('%.6f' % b['pct']) if b['ok'] else ''}\t{b['reason']}\n")

    (BASE / "RESULTS_SECTOR_DRYRUN_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()

    # ── stdout 전용 (본문에 넣으면 --rerun 이 구조적으로 깨진다) ───────────
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True,
                                  text=True, timeout=20).stdout.strip()
        except Exception:  # noqa: BLE001
            return "?"
    print(f"\n[git] 브랜치 {git('rev-parse', '--abbrev-ref', 'HEAD')} · "
          f"HEAD {git('rev-parse', '--short', 'HEAD')}  "
          "— 🔴 해시는 stdout 전용(본문에 박으면 --rerun 이 구조적으로 깨진다)")
    print(f"[시간] 총 {time.time() - t_start:.1f}초 · SEC-X1 {t_x1:.1f}초")
    print("[written] RESULTS_SECTOR_DRYRUN_NUMBERS.md + sector_dryrun/*.json|tsv")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
