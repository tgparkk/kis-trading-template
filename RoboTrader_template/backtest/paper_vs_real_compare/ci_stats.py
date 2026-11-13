# -*- coding: utf-8 -*-
"""페이퍼 vs 실전 daytrading 대조 — 통계 계층 (순수 함수 · DB/파일/네트워크 접근 0).

정본 = docs/prereg_2026-10-18_paper_vs_real_daytrading_compare.md (동결 21e9702).
이 모듈은 «이미 메모리에 올라온» 행·로그 사건(ci_data.py 가 만든 Dataset)만 받아
대응쌍 → 지표 단위 → 요약 · 거래일 군집 부트스트랩 CI → §8 요약 1장(Markdown) 을 만든다.

판정 언어(PASS/FAIL 등)는 쓰지 않는다 — 추정값 ± CI 와 «칸과의 거리» 만 (§5).
각 지표 함수는 두 단계로 나뉜다:
  eligible_* : 단위(쌍·청산·손절 건)와 제외 사유만 정한다 — 지표 값을 계산하지 않음(--dry-run 이 이것만 쓴다)
  values_*   : 단위에 지표 값을 붙인다 — 단일 실행에서만 호출
"""
import math
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# --------------------------------------------------------------------------
# 사전등록 상수 (§1 · §3 · §5 · §6) — 값은 동결 문서에서 그대로 옮김
# --------------------------------------------------------------------------
SEED = 20261113                 # §3 CI 방법(s6)
B = 10_000                      # §3 재표집 횟수
PCT_LO, PCT_HI = 2.5, 97.5      # §3 percentile
TRIM = 0.20                     # §3 20% 절사평균
MIN_N = {"pair": 15, "exit": 15, "stop": 10}   # §3 지표별 최소 n
MAX_DT_SEC = 600                # §3-2 |Δt| > 10분 쌍은 슬리피지에서 제외
FIRST_DAY = date(2026, 10, 19)  # §6 첫날 표식
MIN_COND_PAIRS, MIN_COND_DAYS = 30, 15   # §1 최소 조건
CELLS = {                       # §5-추가 사장님 결정(10-16 밤)
    "cost_cap_pct": 0.25,               # ① 지표4 실제 비용 점값(실전 전체 청산 평균)
    "slip_exec_median_cap_pct": 0.20,   # ② 지표2 집행 조각 중앙값
    "coverage_ci_lo_floor_pct": 55.0,   # ③ 지표1 신호 커버리지 CI 하한
}
ASSUMED_FEE = 0.00015           # config/constants.py:182 COMMISSION_RATE (편도)
ASSUMED_TAX = 0.0018            # config/constants.py:183 SECURITIES_TAX_RATE (매도)
CAP_REASONS = ("한도", "현금")    # §5 해석 금지(③): 사유별 커버리지에서 빼는 사유

# §3-1 사유 매핑표 (기계 판정 · 이 순서 · 사후 재분류 금지)
REASON_ORDER = ("한도", "현금", "차단", "API", "지연 취소", "실전 시도 없음", "기타")

PAPER_STOP_RE = re.compile(r"^손절 실행 \(([-\d.]+)% <= ([-\d.]+)%\)")


# --------------------------------------------------------------------------
# 입력 자료형 (ci_data.py 가 채운다 · 시각은 전부 KST naive datetime)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PaperBuy:
    id: int
    code: str
    ts: datetime
    price: float
    qty: int
    stop_loss_rate: Optional[float]


@dataclass(frozen=True)
class PaperSell:
    id: int
    code: str
    ts: datetime
    price: float
    qty: int
    buy_record_id: Optional[int]
    reason: str


@dataclass(frozen=True)
class RealBuy:
    id: int
    code: str
    ts: datetime
    price: float
    qty: int


@dataclass(frozen=True)
class RealSell:
    id: int
    code: str
    ts: datetime
    price: float
    qty: int
    buy_record_id: Optional[int]


@dataclass
class DayLog:
    """실전 trading_YYYYMMDD.log 하루치에서 뽑은 사건 (ts, code, ...)."""
    day: date
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None
    signals: List[Tuple[datetime, str]] = field(default_factory=list)           # 전달 매수신호 사용
    tries: List[Tuple[datetime, str, int, float]] = field(default_factory=list)  # 매수 주문 시도 (ts, code, qty, 로그 가격)
    stops: List[Tuple[datetime, str, float, float]] = field(default_factory=list)  # 손절 신호 (ts, code, 트리거 %, 문턱 %)
    caps: List[Tuple[datetime, str]] = field(default_factory=list)              # ① [캡]…사유= · [shadow]…캡사유=
    cash: List[Tuple[datetime, str]] = field(default_factory=list)              # ② 자금 부족
    blocks: List[Tuple[datetime, str]] = field(default_factory=list)            # ③ 매수 주문 차단:
    api_timeouts: List[Tuple[datetime, str]] = field(default_factory=list)      # ④ 매수 주문 API 타임아웃
    delayed_cancels: List[Tuple[datetime, str]] = field(default_factory=list)   # ⑤ 5분 타임아웃 처리 → 타임아웃 취소 성공 (매수 주문)
    b2_fail: List[Tuple[datetime, str]] = field(default_factory=list)           # §6 [B2-실전] 해소/주입 실패
    partial: List[Tuple[datetime, str]] = field(default_factory=list)           # 주문 부분 체결


@dataclass(frozen=True)
class CostDay:
    """비용 도구 CSV 의 하루 행(KIS TTTC8708R · 원 단위)."""
    day: date
    buy_amt: float
    sell_amt: float
    fee: float
    tax: float


@dataclass
class Dataset:
    start: date
    end: date
    paper_buys: List[PaperBuy]
    paper_sells: List[PaperSell]
    real_buys: List[RealBuy]
    real_sells: List[RealSell]
    logs: Dict[date, DayLog]
    cost_days: Dict[date, CostDay]
    cost_rows: Dict[Tuple[date, str, int], float]       # (날짜, 종목, 수량) → KIS 매도 체결금액
    kospi_sign: Dict[date, int]                         # +1 상승 / −1 하락 / 0 보합
    trading_days: List[date]
    restart_days: Dict[date, str] = field(default_factory=dict)          # §6 장중 재기동일 → 사유
    manual_exclusions: Dict[Tuple[date, str], str] = field(default_factory=dict)  # §8 EOD 대사 불일치 등
    struct_changes: List[Tuple[date, str, str]] = field(default_factory=list)     # §6 M6 (발효일, 라벨, sha)
    meta: Dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------
# 기초 함수
# --------------------------------------------------------------------------
def tick_size(price: float) -> int:
    """utils/price_utils.py:_get_tick_size 와 같은 표(시험에서 동일성 확인). 운영 모듈은 import 시
    로그 핸들러를 만들기 때문에 여기서 다시 적는다."""
    if price < 2000:
        return 1
    if price < 5000:
        return 5
    if price < 20000:
        return 10
    if price < 50000:
        return 50
    if price < 200000:
        return 100
    if price < 500000:
        return 500
    return 1000


def round_to_tick(price: float) -> float:
    """utils/price_utils.py:round_to_tick 과 같은 식 (order_executor.py:207 이 주문가에 적용)."""
    if price <= 0:
        return 0.0
    t = tick_size(price)
    return float(int(math.floor(price / t + 0.5)) * t)


def on_grid(price: float) -> bool:
    p = float(price)
    return abs(p - round(p)) < 1e-9 and int(round(p)) % tick_size(p) == 0


def trimmed_mean(xs: Sequence[float], prop: float = TRIM) -> Optional[float]:
    """양 끝에서 floor(prop·n) 개씩 버린 평균 (scipy.stats.trim_mean 과 같은 규약)."""
    a = sorted(float(x) for x in xs)
    n = len(a)
    if n == 0:
        return None
    k = int(math.floor(prop * n))
    core = a[k:n - k]
    return float(sum(core) / len(core))


def daily_means(units: Sequence[Tuple[date, float]]) -> "OrderedDict[date, float]":
    """§3 «하루 안 쌍은 먼저 평균» — 거래일별 평균(날짜순)."""
    g: Dict[date, List[float]] = defaultdict(list)
    for d, v in units:
        g[d].append(float(v))
    return OrderedDict((d, sum(vs) / len(vs)) for d, vs in sorted(g.items()))


def cluster_bootstrap_ci(units: Sequence[Tuple[date, float]], b: int = B, seed: int = SEED) -> Tuple[float, float]:
    """§3 거래일 군집 부트스트랩: 일평균 D 개를 복원추출(B 회) → «일평균의 평균» 의 percentile 2.5/97.5.
    호출마다 seed 로 새 생성기를 만든다(지표 계산 순서가 CI 에 영향 주지 않게)."""
    m = np.array(list(daily_means(units).values()), dtype=float)
    if m.size == 0:
        raise ValueError("단위 0개")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, m.size, size=(b, m.size))
    stats = m[idx].mean(axis=1)
    lo, hi = np.percentile(stats, [PCT_LO, PCT_HI])
    return float(lo), float(hi)


def summarize(units: Sequence[Tuple[date, float]], min_n: int, with_ci: bool = True) -> Dict[str, object]:
    """§3 요약 = 중앙값 · 20% 절사평균 · 최대/최소 · 일평균의 평균 · (n ≥ 최소 n 이면) 95% CI."""
    vals = [float(v) for _, v in units]
    n = len(vals)
    days = sorted({d for d, _ in units})
    out: Dict[str, object] = {"n": n, "n_days": len(days), "min_n": min_n, "gate": n >= min_n}
    if n == 0:
        out.update(median=None, trim20=None, min=None, max=None, mean_daily=None, pooled=None, ci=None,
                   status="표본 없음")
        return out
    dm = daily_means(units)
    out.update(median=float(np.median(vals)), trim20=trimmed_mean(vals), min=min(vals), max=max(vals),
               mean_daily=float(sum(dm.values()) / len(dm)), pooled=float(sum(vals) / n))
    if n >= min_n and with_ci:
        out["ci"] = cluster_bootstrap_ci(units)
        out["status"] = "CI"
    else:
        out["ci"] = None
        out["status"] = "표본 부족 · 점값만" if n < min_n else "점값만"
    return out


def kst_day(ts: datetime) -> date:
    return ts.date()


# --------------------------------------------------------------------------
# 대응쌍 (§2)
# --------------------------------------------------------------------------
@dataclass
class RealFill:
    """실전 매수 1건 = 같은 «매수 주문 시도» 에 붙는 BUY 행 묶음(부분체결이면 수량가중 · 마지막 행 시각)."""
    code: str
    day: date
    ts: datetime                    # 마지막 행 시각
    price: float                    # 수량가중 체결가
    qty: int
    row_ids: Tuple[int, ...]
    rows_on_grid: bool              # 모든 행 체결가가 호가 격자 위
    try_ts: Optional[datetime]
    try_qty: Optional[int]
    order_price: Optional[float]    # round_to_tick(로그 가격)
    signal_ts: Optional[datetime]


@dataclass
class Pair:
    paper: PaperBuy
    real: RealFill

    @property
    def day(self) -> date:
        return kst_day(self.paper.ts)


@dataclass
class PairSet:
    pairs: List[Pair]                       # ㉮
    paper_only: List[PaperBuy]              # ㉯
    real_only: List[RealFill]               # ㉰
    not_running: List[PaperBuy]             # 실전 미가동 → 분모 제외 · 개수만
    excluded: List[Tuple[str, str, date, str]]   # (구분, 종목, 매수일, 사유) — 재기동일·수동 제외
    fills: List[RealFill]


def build_real_fills(real_buys: Sequence[RealBuy], logs: Dict[date, DayLog]) -> List[RealFill]:
    """실전 BUY 행 → 매수 1건. 각 행은 같은 날 같은 종목의 «그 행 시각 이전 마지막 시도» 에 붙인다.
    같은 시도에 붙은 행은 합친다(부분체결 대비). 시도 로그가 없는 행은 행마다 1건(주문가 결측)."""
    groups: "OrderedDict[Tuple[date, str, object], List[RealBuy]]" = OrderedDict()
    for r in sorted(real_buys, key=lambda x: (x.ts, x.id)):
        d = kst_day(r.ts)
        lg = logs.get(d)
        tries = sorted([t for t in (lg.tries if lg else []) if t[1] == r.code and t[0] <= r.ts], key=lambda t: t[0])
        key = (d, r.code, tries[-1] if tries else ("no-try", r.id))
        groups.setdefault(key, []).append(r)
    fills = []
    for (d, code, tkey), rows in groups.items():
        qty = sum(x.qty for x in rows)
        price = sum(x.price * x.qty for x in rows) / qty
        lg = logs.get(d)
        if isinstance(tkey, tuple) and tkey and tkey[0] == "no-try":
            try_ts = try_qty = order_price = None
            anchor = rows[0].ts
        else:
            try_ts, _, try_qty, logged = tkey
            order_price = round_to_tick(logged)
            anchor = try_ts
        sigs = sorted([s[0] for s in (lg.signals if lg else []) if s[1] == code and s[0] <= anchor])
        fills.append(RealFill(code=code, day=d, ts=rows[-1].ts, price=float(price), qty=qty,
                              row_ids=tuple(x.id for x in rows), rows_on_grid=all(on_grid(x.price) for x in rows),
                              try_ts=try_ts, try_qty=try_qty, order_price=order_price,
                              signal_ts=sigs[-1] if sigs else None))
    return sorted(fills, key=lambda f: (f.ts, f.row_ids))


def is_running(ts: datetime, logs: Dict[date, DayLog]) -> bool:
    """§3-1 가동 구간 = 실전 로그 첫 줄 ~ 마지막 줄."""
    lg = logs.get(kst_day(ts))
    if lg is None or lg.first_ts is None or lg.last_ts is None:
        return False
    return lg.first_ts <= ts <= lg.last_ts


def match_pairs(ds: Dataset) -> PairSet:
    """§2 키 = (KST 매수일, 종목) · 같은 키 양쪽 BUY 를 시간순 1:1 · 남는 것은 ㉯/㉰.
    실전 미가동 구간 페이퍼 BUY 는 짝짓기 전에 뺀다(개수만). 장중 재기동일·수동 제외 키는 짝짓기 뒤 뺀다."""
    fills = build_real_fills(ds.real_buys, ds.logs)
    pb_by: Dict[Tuple[date, str], List[PaperBuy]] = defaultdict(list)
    not_running = []
    for p in sorted(ds.paper_buys, key=lambda x: (x.ts, x.id)):
        if not is_running(p.ts, ds.logs):
            not_running.append(p)
            continue
        pb_by[(kst_day(p.ts), p.code)].append(p)
    rf_by: Dict[Tuple[date, str], List[RealFill]] = defaultdict(list)
    for f in fills:
        rf_by[(f.day, f.code)].append(f)
    pairs, paper_only, real_only, excluded = [], [], [], []
    for key in sorted(set(pb_by) | set(rf_by)):
        ps, rs = pb_by.get(key, []), rf_by.get(key, [])
        d, code = key
        why = ds.restart_days.get(d) or ds.manual_exclusions.get(key)
        k = min(len(ps), len(rs))
        if why:
            for p in ps:
                excluded.append(("페이퍼 BUY", code, d, why))
            for r in rs:
                excluded.append(("실전 BUY", code, d, why))
            continue
        pairs.extend(Pair(p, r) for p, r in zip(ps[:k], rs[:k]))
        paper_only.extend(ps[k:])
        real_only.extend(rs[k:])
    return PairSet(pairs=pairs, paper_only=paper_only, real_only=real_only, not_running=not_running,
                   excluded=excluded, fills=fills)


# --------------------------------------------------------------------------
# 지표 1 — 커버리지 (§3-1)
# --------------------------------------------------------------------------
def coverage_reason(code: str, lg: Optional[DayLog], tried: bool) -> str:
    """§3-1 사유 매핑표 — 그 거래일 그 종목의 실전 로그 사건을 이 순서로 본다(첫 해당이 사유).
    ⑥ «실전 시도 없음» 은 이 페이퍼 BUY 에 배정된 실전 시도가 없을 때(같은 날 같은 종목 시도가 앞 BUY 에 쓰였으면 없음)."""
    if lg is None:
        return "실전 시도 없음"
    if any(c == code for _, c in lg.caps):
        return "한도"
    if any(c == code for _, c in lg.cash):
        return "현금"
    if any(c == code for _, c in lg.blocks):
        return "차단"
    if any(c == code for _, c in lg.api_timeouts):
        return "API"
    if any(c == code for _, c in lg.delayed_cancels):
        return "지연 취소"
    if not tried:
        return "실전 시도 없음"
    return "기타"


def all_reason_flags(code: str, lg: Optional[DayLog]) -> List[str]:
    """참고 표기용 — 그날 그 종목에 찍힌 사유 전부(사유 판정은 coverage_reason 의 첫 해당만)."""
    if lg is None:
        return []
    out = []
    for name, evs in (("한도", lg.caps), ("현금", lg.cash), ("차단", lg.blocks), ("API", lg.api_timeouts),
                      ("지연 취소", lg.delayed_cancels)):
        if any(c == code for _, c in evs):
            out.append(name)
    return out


@dataclass
class CoverageUnit:
    paper: PaperBuy
    tried: bool
    filled: bool
    reason: Optional[str]           # ㉯ 일 때만

    @property
    def day(self) -> date:
        return kst_day(self.paper.ts)


def coverage_units(ds: Dataset, ps: PairSet) -> List[CoverageUnit]:
    """페이퍼 BUY(㉮+㉯) 1건 = 1단위. 같은 키의 페이퍼 BUY 를 시간순으로 세워 앞에서부터
    min(페이퍼 수, max(실전 시도 수, ㉮ 수)) 개를 «시도됨», ㉮ 개수만큼을 «체결됨» 으로 둔다."""
    paired_ids = {p.paper.id for p in ps.pairs}
    by_key: Dict[Tuple[date, str], List[PaperBuy]] = defaultdict(list)
    for p in [x.paper for x in ps.pairs] + list(ps.paper_only):
        by_key[(kst_day(p.ts), p.code)].append(p)
    units = []
    for (d, code), plist in sorted(by_key.items()):
        plist = sorted(plist, key=lambda x: (x.ts, x.id))
        lg = ds.logs.get(d)
        n_try = sum(1 for t in (lg.tries if lg else []) if t[1] == code)
        n_pair = sum(1 for p in plist if p.id in paired_ids)
        n_tried = min(len(plist), max(n_try, n_pair))
        for i, p in enumerate(plist):
            filled = p.id in paired_ids
            tried = i < n_tried
            units.append(CoverageUnit(paper=p, tried=tried, filled=filled,
                                      reason=None if filled else coverage_reason(code, lg, tried)))
    return units


def values_coverage(units: Sequence[CoverageUnit]) -> Dict[str, List[Tuple[date, float]]]:
    """신호 커버리지(단위 = 페이퍼 BUY · 값 = 시도 100/0) · 집행 커버리지(단위 = 시도된 페이퍼 BUY · 값 = 체결 100/0)
    · 사유별 커버리지(분모에서 ㉯ 한도·현금 제외)."""
    sig = [(u.day, 100.0 if u.tried else 0.0) for u in units]
    exe = [(u.day, 100.0 if u.filled else 0.0) for u in units if u.tried]
    adj = [(u.day, 100.0 if u.tried else 0.0) for u in units if u.reason not in CAP_REASONS]
    return {"signal": sig, "exec": exe, "signal_ex_cap_cash": adj}


def values_fill_ratio(pairs: Sequence[Pair]) -> List[Tuple[date, float]]:
    """§3-1 수량 충족률 = 체결수량 ÷ 주문수량 (%) — ㉮ 중 시도 로그가 있는 것."""
    return [(p.day, 100.0 * p.real.qty / p.real.try_qty) for p in pairs if p.real.try_qty]


# --------------------------------------------------------------------------
# 지표 2 — 매수 슬리피지 (§3-2)
# --------------------------------------------------------------------------
def eligible_slippage(pairs: Sequence[Pair]) -> Tuple[List[Pair], Dict[str, List[Pair]]]:
    """제외(첫 해당만): 주문가 로그 없음 → |Δt| > 10분 → 체결가 격자 밖(«체결가 폴백» 표식). 커버리지엔 그대로 둔다."""
    keep, excl = [], {"주문가 로그 없음": [], "|Δt| > 10분": [], "체결가 폴백(격자 밖)": []}
    for p in pairs:
        if p.real.order_price is None:
            excl["주문가 로그 없음"].append(p)
        elif abs((p.real.ts - p.paper.ts).total_seconds()) > MAX_DT_SEC:
            excl["|Δt| > 10분"].append(p)
        elif not p.real.rows_on_grid:
            excl["체결가 폴백(격자 밖)"].append(p)
        else:
            keep.append(p)
    return keep, excl


def values_slippage(pairs: Sequence[Pair]) -> Dict[str, List[Tuple[date, float]]]:
    """타이밍 = (실전 주문가 − 페이퍼 체결가) ÷ 페이퍼 체결가 ×100 · 집행 = (실전 체결가 − 실전 주문가) ÷ 실전 주문가 ×100
    · 틱 = (실전 체결가 − 페이퍼 체결가) ÷ 페이퍼 체결가 가격대 호가 단위. 양수 = 실전 불리."""
    tim, exe, tot, ticks = [], [], [], []
    for p in pairs:
        pp, op, rp = p.paper.price, p.real.order_price, p.real.price
        tim.append((p.day, (op - pp) / pp * 100.0))
        exe.append((p.day, (rp - op) / op * 100.0))
        tot.append((p.day, (rp - pp) / pp * 100.0))
        ticks.append((p.day, (rp - pp) / tick_size(pp)))
    return {"timing": tim, "exec": exe, "total": tot, "ticks": ticks}


# --------------------------------------------------------------------------
# 지표 5 — 체결 지연 초 (§3-5)
# --------------------------------------------------------------------------
def eligible_latency(pairs: Sequence[Pair]) -> Tuple[List[Pair], List[Pair]]:
    keep = [p for p in pairs if p.real.signal_ts is not None]
    return keep, [p for p in pairs if p.real.signal_ts is None]


def values_latency(pairs: Sequence[Pair]) -> Dict[str, List[Tuple[date, float]]]:
    """(a) 실전 내부 = 실전 신호 로그 → 실전 BUY 행 timestamp · (b) 신호 시차 = 실전 신호 − 페이퍼 BUY timestamp."""
    a = [(p.day, (p.real.ts - p.real.signal_ts).total_seconds()) for p in pairs]
    b = [(p.day, (p.real.signal_ts - p.paper.ts).total_seconds()) for p in pairs]
    return {"a_internal": a, "b_signal_lag": b}


# --------------------------------------------------------------------------
# 청산 (§2 청산쌍 · §4 같은 날 규칙)
# --------------------------------------------------------------------------
@dataclass
class Exit:
    """매수 1건에 이어진 SELL 행 묶음 = 1 청산(수량가중 평균가 · 마지막 행 시각 · s4)."""
    side: str                       # "real" / "paper"
    code: str
    buy_ids: Tuple[int, ...]
    buy_price: float
    buy_ts: datetime
    ts: datetime
    price: Optional[float]          # None = 가격을 읽지 않은 청산(§4 «같은 날» 밖 페이퍼 쪽)
    qty: int
    sell_rows: Tuple[object, ...]

    @property
    def day(self) -> date:
        return kst_day(self.ts)


def _aggregate(side: str, code: str, buy_ids: Tuple[int, ...], buy_price: float, buy_ts: datetime,
               rows: Sequence, with_price: bool = True) -> Optional[Exit]:
    """with_price=False 면 SELL 행의 price 속성을 아예 읽지 않는다(시각·수량만)."""
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: (r.ts, r.id))
    qty = sum(r.qty for r in rows)
    price = float(sum(r.price * r.qty for r in rows) / qty) if with_price else None
    return Exit(side=side, code=code, buy_ids=buy_ids, buy_price=buy_price, buy_ts=buy_ts, ts=rows[-1].ts,
                price=price, qty=qty, sell_rows=tuple(rows))


def real_exits(ds: Dataset) -> List[Exit]:
    """실전 청산 전체(㉰ 포함) — buy_record_id 로 묶음."""
    buys = {b.id: b for b in ds.real_buys}
    by_buy: Dict[int, List[RealSell]] = defaultdict(list)
    for s in ds.real_sells:
        if s.buy_record_id in buys:
            by_buy[s.buy_record_id].append(s)
    out = []
    for bid, rows in sorted(by_buy.items()):
        b = buys[bid]
        out.append(_aggregate("real", b.code, (bid,), b.price, b.ts, rows))
    return sorted(out, key=lambda e: (e.ts, e.buy_ids))


def orphan_real_sells(ds: Dataset) -> List[RealSell]:
    buys = {b.id for b in ds.real_buys}
    return [s for s in ds.real_sells if s.buy_record_id not in buys]


@dataclass
class ExitPair:
    pair: Pair
    real: Optional[Exit]
    paper: Optional[Exit]
    category: str                   # 같은 날 / 청산일 다름 / 실전만 청산 / 페이퍼만 청산 / 둘 다 미청산


def exit_pairs(ds: Dataset, ps: PairSet) -> List[ExitPair]:
    """㉮ 쌍마다 양쪽 청산을 묶고 §4 분류. 분류는 시각만 쓴다. 페이퍼 청산가는 «같은 날» 쌍에서만 집계한다
    (청산일 다름·페이퍼만 청산 쌍은 집계 단계에서도 페이퍼 SELL price 를 읽지 않음 · SR1 보호)."""
    r_by: Dict[int, List[RealSell]] = defaultdict(list)
    for s in ds.real_sells:
        r_by[s.buy_record_id].append(s)
    p_by: Dict[int, List[PaperSell]] = defaultdict(list)
    for s in ds.paper_sells:
        p_by[s.buy_record_id].append(s)
    out = []
    for pr in ps.pairs:
        rrows = [s for bid in pr.real.row_ids for s in r_by.get(bid, [])]
        rex = _aggregate("real", pr.real.code, pr.real.row_ids, pr.real.price, pr.real.ts, rrows)
        prows = p_by.get(pr.paper.id, [])
        p_last = max(prows, key=lambda r: (r.ts, r.id)) if prows else None
        same_day = bool(rex) and p_last is not None and kst_day(p_last.ts) == rex.day
        pex = _aggregate("paper", pr.paper.code, (pr.paper.id,), pr.paper.price, pr.paper.ts, prows, with_price=same_day)
        if rex and pex:
            cat = "같은 날" if rex.day == pex.day else "청산일 다름"
        elif rex:
            cat = "실전만 청산"
        elif pex:
            cat = "페이퍼만 청산"
        else:
            cat = "둘 다 미청산"
        out.append(ExitPair(pair=pr, real=rex, paper=pex, category=cat))
    return out


# --------------------------------------------------------------------------
# 지표 3 — 손절 초과폭 (§3-3)
# --------------------------------------------------------------------------
@dataclass
class StopEvent:
    exit: Exit
    trig_ts: datetime
    trig_pct: float                 # 로그 −x%
    line_pct: float                 # 손절선 (양수 · %)
    line_source: str


def real_stop_map(ds: Dataset, exits: Sequence[Exit]) -> Tuple[Dict[Tuple[int, ...], StopEvent], List[Tuple[datetime, str]]]:
    """로그 `{code} 손절 신호: 손절 실행 (` 뒤 같은 종목 «첫» 실전 SELL 행 → 그 행이 속한 청산.
    같은 청산에 여러 신호가 붙으면(매도 재시도) 가장 이른 신호를 트리거로 쓴다. 손절선 = 로그 문턱(= 실전 config 값)."""
    row_to_exit = {}
    for e in exits:
        for r in e.sell_rows:
            row_to_exit[r.id] = e
    sells_by_code: Dict[str, List[RealSell]] = defaultdict(list)
    for s in ds.real_sells:
        sells_by_code[s.code].append(s)
    for v in sells_by_code.values():
        v.sort(key=lambda s: (s.ts, s.id))
    out: Dict[Tuple[int, ...], StopEvent] = {}
    unmapped = []
    events = sorted((ev for lg in ds.logs.values() for ev in lg.stops), key=lambda x: x[0])
    for ts, code, trig, thr in events:
        nxt = next((s for s in sells_by_code.get(code, []) if s.ts >= ts), None)
        e = row_to_exit.get(nxt.id) if nxt else None
        if e is None:
            unmapped.append((ts, code))
            continue
        if e.buy_ids not in out:
            out[e.buy_ids] = StopEvent(exit=e, trig_ts=ts, trig_pct=trig, line_pct=abs(thr), line_source="실전 로그 문턱")
    return out, unmapped


def paper_stop_event(ex: Exit, buy: PaperBuy) -> Optional[StopEvent]:
    """페이퍼 손절 = reason LIKE '손절 실행%' (SR1 과 같은 정의). 손절선 = 페이퍼 BUY 행 stop_loss_rate 열(NULL 이면 reason 문턱)."""
    last = ex.sell_rows[-1]
    m = PAPER_STOP_RE.match(last.reason or "")
    if not (last.reason or "").startswith("손절 실행"):
        return None
    if m is None:
        return None
    trig, thr = float(m.group(1)), float(m.group(2))
    if buy.stop_loss_rate is not None:
        line, src = float(buy.stop_loss_rate) * 100.0, "페이퍼 DB stop_loss_rate"
    else:
        line, src = abs(thr), "reason 문턱(열 NULL)"
    return StopEvent(exit=ex, trig_ts=ex.ts, trig_pct=trig, line_pct=line, line_source=src)


def stop_values(ev: StopEvent) -> Tuple[float, float, float]:
    """㉠ 감시·갭 몫 = 트리거 수익률 − (−손절선) · ㉡ 집행 몫 = (체결가 ÷ 트리거 시점 가격 − 1)×100 · 합."""
    a = ev.trig_pct + ev.line_pct
    trig_price = ev.exit.buy_price * (1.0 + ev.trig_pct / 100.0)
    b = (ev.exit.price / trig_price - 1.0) * 100.0
    return a, b, a + b


# --------------------------------------------------------------------------
# 지표 4 — 라운드트립 비용 (§3-4)
# --------------------------------------------------------------------------
def eligible_cost(ds: Dataset, exits: Sequence[Exit]) -> Tuple[List[Exit], List[Tuple[Exit, str]]]:
    """실제 비용 = KIS 하루 수수료·제세금(TTTC8708R) + 건별 매도 체결금액(대조 키 = (날짜, 종목, 수량)).
    매수일·매도일 하루 행이 없거나 매도 행 대조 실패면 «미측정» (가정값으로 메우지 않음)."""
    keep, miss = [], []
    for e in exits:
        bd = kst_day(e.buy_ts)
        if e.day not in ds.cost_days:
            miss.append((e, "매도일 KIS 행 없음"))
        elif bd not in ds.cost_days:
            miss.append((e, "매수일 KIS 행 없음"))
        elif any((kst_day(r.ts), r.code, r.qty) not in ds.cost_rows for r in e.sell_rows):
            miss.append((e, "매도 행 KIS 대조 실패"))
        else:
            keep.append(e)
    return keep, miss


def cost_values(ds: Dataset, e: Exit) -> Tuple[float, float]:
    """(실제 %, 가정 %). 하루 수수료는 그날 KIS 매수+매도 체결금액에 비례 배분, 제세금은 매도금액에 비례 배분.
    분모 = 매수금액(실전 BUY 체결가 × 청산 수량)."""
    bd = ds.cost_days[kst_day(e.buy_ts)]
    sd = ds.cost_days[e.day]
    buy_amt = e.buy_price * e.qty
    sell_kis = sum(ds.cost_rows[(kst_day(r.ts), r.code, r.qty)] for r in e.sell_rows)
    fee_b = bd.fee / (bd.buy_amt + bd.sell_amt) if (bd.buy_amt + bd.sell_amt) > 0 else 0.0
    fee_s = sd.fee / (sd.buy_amt + sd.sell_amt) if (sd.buy_amt + sd.sell_amt) > 0 else 0.0
    tax_s = sd.tax / sd.sell_amt if sd.sell_amt > 0 else 0.0
    actual = fee_b * buy_amt + fee_s * sell_kis + tax_s * sell_kis
    sell_int = e.price * e.qty
    assumed = ASSUMED_FEE * buy_amt + ASSUMED_FEE * sell_int + ASSUMED_TAX * sell_int
    return actual / buy_amt * 100.0, assumed / buy_amt * 100.0


# --------------------------------------------------------------------------
# 줄 나누기 (§6 첫날 · §3 상승/하락일)
# --------------------------------------------------------------------------
def split_lines(units: Sequence[Tuple[date, float]], kospi_sign: Dict[date, int], min_n: int,
                with_ci: bool = True) -> "OrderedDict[str, Dict[str, object]]":
    """«첫날 포함»(11-13 주 수치) · «첫날 제외» · «첫날만»(점값) · «상승일» · «하락일»(첫날 포함 기준)."""
    lines: "OrderedDict[str, Dict[str, object]]" = OrderedDict()
    lines["첫날 포함"] = summarize(units, min_n, with_ci)
    lines["첫날 제외"] = summarize([u for u in units if u[0] != FIRST_DAY], min_n, with_ci)
    lines["첫날만"] = summarize([u for u in units if u[0] == FIRST_DAY], min_n, with_ci=False)
    lines["상승일"] = summarize([u for u in units if kospi_sign.get(u[0], 0) > 0], min_n, with_ci)
    lines["하락일"] = summarize([u for u in units if kospi_sign.get(u[0], 0) < 0], min_n, with_ci)
    flat = [u for u in units if kospi_sign.get(u[0], 0) == 0]
    if flat:
        lines["보합·지수 없음"] = summarize(flat, min_n, with_ci=False)
    return lines


def last_struct_change(d: date, changes: Sequence[Tuple[date, str, str]]) -> str:
    """§6 M6 — 쌍마다 «마지막 구조 변화일 이후» 열."""
    lab = "-"
    for eff, label, _sha in sorted(changes):
        if eff <= d:
            lab = f"{label}({eff:%m-%d}~)"
    return lab


# --------------------------------------------------------------------------
# 전체 조립
# --------------------------------------------------------------------------
def build_counts(ds: Dataset) -> Dict[str, object]:
    """--dry-run 용: 행 수 · 쌍 수 · 거래일 수 · 지표별 단위 n · 최소 n 충족 여부만. 지표 값·CI 는 계산하지 않는다."""
    ps = match_pairs(ds)
    rex = real_exits(ds)
    stop_map, unmapped = real_stop_map(ds, rex)
    slip_keep, slip_excl = eligible_slippage(ps.pairs)
    lat_keep, lat_miss = eligible_latency(ps.pairs)
    eps = exit_pairs(ds, ps)
    same = [x for x in eps if x.category == "같은 날"]
    pair_real_stop = [x for x in same if x.real.buy_ids in stop_map]
    pair_paper_stop = [x for x in same if _is_paper_stop_reason(x.paper)]
    cost_keep, cost_miss = eligible_cost(ds, rex)
    pair_exit_ids = {x.real.buy_ids for x in eps if x.real}
    pair_days = sorted({p.day for p in ps.pairs})

    def g(items, key, dayf):
        n = len(items)
        return {"n": n, "거래일(군집)": len({dayf(x) for x in items}), "min_n": MIN_N[key], "충족": n >= MIN_N[key]}

    def pday(p):
        return p.day

    def eday(x):
        return x.day

    den_units = [p.paper for p in ps.pairs] + list(ps.paper_only)
    stop_events = [ev for lg in ds.logs.values() for ev in lg.stops]
    p_stop_sw = [s for s in ds.paper_sells if (s.reason or "").startswith("손절 실행")]
    pair_cost = [e for e in cost_keep if e.buy_ids in pair_exit_ids]
    return {
        "rows": {"paper_buy": len(ds.paper_buys), "paper_sell": len(ds.paper_sells),
                 "real_buy": len(ds.real_buys), "real_sell": len(ds.real_sells),
                 "real_fill(묶은 매수)": len(ps.fills), "log_days": len(ds.logs), "cost_days": len(ds.cost_days),
                 "cost_rows": len(ds.cost_rows), "kospi_days": len(ds.kospi_sign)},
        "trading_days_in_period": len(ds.trading_days),
        "pairs": {"㉮ 짝": len(ps.pairs), "㉯ 페이퍼만": len(ps.paper_only), "㉰ 실전만": len(ps.real_only),
                  "실전 미가동(분모 제외)": len(ps.not_running), "재기동·수동 제외 행": len(ps.excluded),
                  "㉮ 있는 거래일": len(pair_days)},
        "min_condition_§1": {"짝 n": len(ps.pairs), "기준 짝": MIN_COND_PAIRS, "거래일": len(ds.trading_days),
                             "기준 거래일": MIN_COND_DAYS,
                             "충족": len(ps.pairs) >= MIN_COND_PAIRS and len(ds.trading_days) >= MIN_COND_DAYS},
        "metric_n": {
            "1 신호 커버리지(분모 = 페이퍼 BUY ㉮+㉯)": g(den_units, "pair", lambda p: kst_day(p.ts)),
            "2 매수 슬리피지(제외 뒤 ㉮)": dict(g(slip_keep, "pair", pday),
                                         제외={k: len(v) for k, v in slip_excl.items()}),
            "3 손절 초과 · 실전 전체": dict(g(list(stop_map.values()), "stop", lambda ev: ev.exit.day),
                                      짝_못_찾은_신호=len(unmapped)),
            "3 손절 초과 · 짝 줄 실전(같은 날 청산쌍 중 실전 손절)": g(pair_real_stop, "stop", lambda x: x.real.day),
            "3 손절 초과 · 짝 줄 페이퍼(같은 날 청산쌍 중 페이퍼 손절)": g(pair_paper_stop, "stop", lambda x: x.paper.day),
            "4 비용 · 실전 전체(측정 청산)": dict(g(cost_keep, "exit", eday), 미측정=len(cost_miss), 청산=len(rex)),
            "4 비용 · 짝 줄(㉮ 의 실전 청산 · 측정)": g(pair_cost, "exit", eday),
            "5 지연(신호 로그 있는 ㉮)": dict(g(lat_keep, "pair", pday), 신호_로그_없음=len(lat_miss)),
        },
        "format_checks": {
            "실전 손절 로그 문턱 ≠ -10.00% 건수": sum(1 for ev in stop_events if abs(ev[3] - (-10.0)) > 1e-9),
            "실전 손절 로그 줄 수(반복 포함)": len(stop_events),
            "페이퍼 SELL reason startswith '손절 실행'": len(p_stop_sw),
            "그중 정규식 불일치(startswith − 정규식 일치)":
                len(p_stop_sw) - sum(1 for s in p_stop_sw if PAPER_STOP_RE.match(s.reason or "")),
        },
        "exit_pair_categories": _count_by(eps, lambda x: x.category),
        "restart_days": {str(k): v for k, v in ds.restart_days.items()},
        "first_day_units(㉮)": sum(1 for p in ps.pairs if p.day == FIRST_DAY),
    }


def _is_paper_stop_reason(ex: Optional[Exit]) -> bool:
    return bool(ex) and (ex.sell_rows[-1].reason or "").startswith("손절 실행")


def _count_by(items, keyf) -> Dict[str, int]:
    out: Dict[str, int] = OrderedDict()
    for x in items:
        k = keyf(x)
        out[k] = out.get(k, 0) + 1
    return dict(out)


COST_SOURCES = ("allocated", "strict")


def build_summary(ds: Dataset, cost_source: str = "allocated") -> Dict[str, object]:
    """단일 실행용 전체 계산 — 지표 5개 요약 · CI · 칸과의 거리 · 제외 목록.
    cost_source: "allocated" = KIS 8708R 하루 합계를 금액 비례 배분한 값을 지표4·① 칸에 씀(«건별 아님» 표기) ·
                 "strict" = 사전등록 문구대로 «건별 수수료·제세금» 이 없으므로 전부 «미측정» · ① 칸 빈칸 · 배분값은 «참고» 절에만."""
    if cost_source not in COST_SOURCES:
        raise ValueError(f"cost_source 는 {COST_SOURCES} 중 하나")
    ps = match_pairs(ds)
    ks = ds.kospi_sign
    res: Dict[str, object] = {"counts": build_counts(ds), "cost_source": cost_source}

    # 1 커버리지
    cu = coverage_units(ds, ps)
    cv = values_coverage(cu)
    res["m1"] = {k: split_lines(v, ks, MIN_N["pair"]) for k, v in cv.items()}
    res["m1_fill_ratio"] = split_lines(values_fill_ratio(ps.pairs), ks, MIN_N["pair"])
    res["m1_reasons"] = _count_by([u for u in cu if not u.filled], lambda u: u.reason)
    res["m1_pooled"] = {
        "신호": (sum(1 for u in cu if u.tried), len(cu)),
        "집행": (sum(1 for u in cu if u.filled), sum(1 for u in cu if u.tried)),
        "실전 전체 집행(매수 건 ÷ 시도 로그)": (len(ps.fills), sum(len(lg.tries) for lg in ds.logs.values())),
    }
    res["m1_paper_only"] = [(u.day, u.paper.code, u.reason, all_reason_flags(u.paper.code, ds.logs.get(u.day)))
                            for u in cu if not u.filled]

    # 2 슬리피지
    keep, excl = eligible_slippage(ps.pairs)
    res["m2"] = {k: split_lines(v, ks, MIN_N["pair"]) for k, v in values_slippage(keep).items()}
    res["m2_excluded"] = {k: [(p.day, p.paper.code) for p in v] for k, v in excl.items()}

    # 3 손절 초과
    rex = real_exits(ds)
    stop_map, unmapped = real_stop_map(ds, rex)
    allv = [(ev.exit.day, stop_values(ev)) for ev in stop_map.values()]
    res["m3_all"] = {nm: split_lines([(d, v[i]) for d, v in allv], ks, MIN_N["stop"])
                     for i, nm in enumerate(("㉠ 감시·갭", "㉡ 집행", "합"))}
    res["m3_unmapped"] = unmapped
    res["m3_line_sources"] = _count_by(stop_map.values(), lambda ev: ev.line_source)
    eps = exit_pairs(ds, ps)
    same = [x for x in eps if x.category == "같은 날"]       # §4 — 이 목록 밖 쌍은 가격을 읽지 않는다
    pr_real, pr_paper, pr_diff = [], [], []
    paper_src = []
    for x in same:
        r_ev = stop_map.get(x.real.buy_ids)
        p_ev = paper_stop_event(x.paper, x.pair.paper)
        if r_ev:
            pr_real.append((x.real.day, stop_values(r_ev)))
        if p_ev:
            pr_paper.append((x.paper.day, stop_values(p_ev)))
            paper_src.append(p_ev.line_source)
        if r_ev and p_ev:
            pr_diff.append((x.real.day, stop_values(r_ev)[2] - stop_values(p_ev)[2]))
    res["m3_pair"] = {
        "실전": {nm: split_lines([(d, v[i]) for d, v in pr_real], ks, MIN_N["stop"])
                 for i, nm in enumerate(("㉠ 감시·갭", "㉡ 집행", "합"))},
        "페이퍼": {nm: split_lines([(d, v[i]) for d, v in pr_paper], ks, MIN_N["stop"])
                  for i, nm in enumerate(("㉠ 감시·갭", "㉡ 집행", "합"))},
        "차(실전 합 − 페이퍼 합 · 둘 다 손절)": split_lines(pr_diff, ks, MIN_N["stop"]),
    }
    res["m3_paper_line_sources"] = _count_by(paper_src, lambda s: s)
    res["exit_pair_categories"] = _count_by(eps, lambda x: x.category)

    # 4 비용
    ck, cmiss = eligible_cost(ds, rex)
    cvals = [(e, cost_values(ds, e)) for e in ck]
    pair_exit_ids = {x.real.buy_ids for x in eps if x.real}
    alloc_all = split_lines([(e.day, v[0]) for e, v in cvals], ks, MIN_N["exit"])
    alloc_pair = split_lines([(e.day, v[0]) for e, v in cvals if e.buy_ids in pair_exit_ids], ks, MIN_N["exit"])
    alloc_mean = (sum(v[0] for _, v in cvals) / len(cvals)) if cvals else None
    res["m4_all_assumed"] = split_lines([(e.day, v[1]) for e, v in cvals], ks, MIN_N["exit"], with_ci=False)
    if cost_source == "allocated":
        res["m4_all"], res["m4_pair"], res["m4_point_mean_all"] = alloc_all, alloc_pair, alloc_mean
        res["m4_unmeasured"] = [(e.day, e.code, why) for e, why in cmiss]
        res["m4_ref_allocated"] = None
    else:
        empty = split_lines([], ks, MIN_N["exit"])
        res["m4_all"], res["m4_pair"], res["m4_point_mean_all"] = empty, empty, None
        res["m4_unmeasured"] = [(e.day, e.code, "건별 KIS 수수료·제세금 없음(strict)") for e in rex]
        res["m4_ref_allocated"] = {"실전 전체": alloc_all, "짝 줄": alloc_pair, "측정된 청산의 단순 평균": alloc_mean,
                                   "배분 불가": [(e.day, e.code, why) for e, why in cmiss]}

    # 5 지연
    lk, lmiss = eligible_latency(ps.pairs)
    res["m5"] = {k: split_lines(v, ks, MIN_N["pair"]) for k, v in values_latency(lk).items()}
    res["m5_missing_signal"] = [(p.day, p.paper.code) for p in lmiss]

    # §5 칸과의 거리 (판정 아님)
    exec_med = res["m2"]["exec"]["첫날 포함"]["median"]
    sig_ci = res["m1"]["signal"]["첫날 포함"]["ci"]
    res["cells"] = {
        "① 비용(지표4 실제 · 측정된 청산의 단순 평균 · " + ("하루 합계 배분 · 건별 아님)" if cost_source == "allocated"
                                                       else "strict · 건별 없음 → 빈칸)"):
            {"통계량": res["m4_point_mean_all"], "칸": CELLS["cost_cap_pct"],
                  "거리": None if res["m4_point_mean_all"] is None else res["m4_point_mean_all"] - CELLS["cost_cap_pct"]},
        "② 슬리피지(지표2 집행 조각 · 쌍 단위 중앙값)": {"통계량": exec_med, "칸": CELLS["slip_exec_median_cap_pct"],
                              "거리": None if exec_med is None else exec_med - CELLS["slip_exec_median_cap_pct"]},
        "③ 신호 커버리지(일평균의 평균의 95% CI 하한)": {"통계량": None if sig_ci is None else sig_ci[0], "칸": CELLS["coverage_ci_lo_floor_pct"],
                              "거리": None if sig_ci is None else sig_ci[0] - CELLS["coverage_ci_lo_floor_pct"]},
    }

    # §6 제외·표식 목록
    res["exclusions"] = {
        "실전 미가동(페이퍼 BUY · 분모 제외)": [(kst_day(p.ts), p.code, f"{p.ts:%H:%M:%S}") for p in ps.not_running],
        "장중 재기동일·수동 제외": ps.excluded,
        "㉰ 실전만(표본 제외 · 건수만)": [(f.day, f.code) for f in ps.real_only],
        "슬리피지 제외": res["m2_excluded"],
        "지연: 신호 로그 없음": res["m5_missing_signal"],
        "손절: 매도 행 못 찾은 신호": [(t.date(), c) for t, c in unmapped],
        "비용 미측정": res["m4_unmeasured"],
        "짝 없는 실전 SELL(buy_record_id 밖)": [(kst_day(s.ts), s.code) for s in orphan_real_sells(ds)],
    }
    b2 = {(lg.day, c) for lg in ds.logs.values() for _, c in lg.b2_fail}
    res["markers"] = {
        "첫날 표식 ㉮": sum(1 for p in ps.pairs if p.day == FIRST_DAY),
        "tp/sl 해소 실패 표식([B2-실전] 실패 경고)": sorted(b2),
        "부분 체결 로그": sorted({(lg.day, c) for lg in ds.logs.values() for _, c in lg.partial}),
        "구조 변화 구간별 ㉮": _count_by(ps.pairs, lambda p: last_struct_change(p.day, ds.struct_changes)),
    }
    # §6 M6 «쌍마다 마지막 구조 변화일 이후 열» — 값 없이 식별·표식만
    ep_by = {id(x.pair): x for x in eps}
    res["pair_table"] = [(p.day, p.paper.code, last_struct_change(p.day, ds.struct_changes), ep_by[id(p)].category,
                          "첫날" if p.day == FIRST_DAY else "", "B2 실패" if (p.day, p.paper.code) in b2 else "")
                         for p in ps.pairs]
    res["checks"] = ds.meta.get("checks", {})
    return res


# --------------------------------------------------------------------------
# §8 요약 1장 (Markdown)
# --------------------------------------------------------------------------
def _f(x, nd=3, unit=""):
    if x is None:
        return "—"
    return f"{x:+.{nd}f}{unit}"


FEW_CLUSTERS = 10   # 거래일(군집) 이 이보다 적은 줄은 «군집 적음 · CI 신뢰 낮음» 표기
TABLE_HEAD = ("| 지표 | 줄 | n | 거래일 | 최소 n | 충족 | 일평균의 평균 | 일평균의 평균의 95% CI | 중앙값(쌍 단위) | "
              "20% 절사(쌍 단위) | 최소 ~ 최대 |")
TABLE_RULE = "|---|---|--:|--:|--:|---|--:|---|--:|--:|---|"

# «위반된 규칙» 절 고정 문구 — 값과 무관한 사실(독립 검토 11-13 반영)
FIXED_VIOLATIONS = (
    "§8 s7 — 분석 스크립트가 «10-19 16:30 전» 이 아니라 11-13 에 작성됨.",
    "§3-4 — 실제 비용이 KIS «건별» 수수료·제세금이 아니라 TTTC8708R 하루 합계를 금액 비례 배분한 값(allocated) · "
    "첫 2주(10-19~10-30) HTS/MTS 내보내기 자료는 수집되지 않음.",
    "§2 — ㉰(실전만) 사유 미판정(건수·종목만).",
    "dry-run 으로 개수(짝·제외 수 등)가 CI 계산 전에 열람됨.",
    "§5 ② 구조 메모 — 실전 매수는 `round_to_tick(현재가)` 지정가라 «집행» 조각(체결가 − 주문가)이 0 이하일 수밖에 없음 → "
    "「② 미초과는 구조상 필연이며 집행 품질 판단 근거가 아님」.",
)


def _line_row(name: str, line: str, s: Dict[str, object], nd: int = 3) -> str:
    ci = s["ci"]
    ci_txt = f"[{ci[0]:+.{nd}f}, {ci[1]:+.{nd}f}]" if ci else s["status"]
    if s["n"] and s["n_days"] < FEW_CLUSTERS:
        ci_txt += " · 군집 적음 · CI 신뢰 낮음"
    return (f"| {name} | {line} | {s['n']} | {s['n_days']} | {s['min_n']} | {'예' if s['gate'] else '아니오'} | "
            f"{_f(s['mean_daily'], nd)} | {ci_txt} | {_f(s['median'], nd)} | {_f(s['trim20'], nd)} | "
            f"{_f(s['min'], nd)} ~ {_f(s['max'], nd)} |")


def render_markdown(res: Dict[str, object], title_suffix: str = "") -> str:
    c = res["counts"]
    L = []
    L.append(f"# 페이퍼 vs 실전 daytrading 대조 — §8 요약 1장{title_suffix}")
    L.append("")
    L.append("> 🔎 **관측 · 판정 아님**. 정의 = `docs/prereg_2026-10-18_paper_vs_real_daytrading_compare.md`(동결 21e9702). "
             "CI = «일평균의 평균» 의 95% 구간(거래일 군집 부트스트랩 · B=10,000 · percentile 2.5/97.5 · seed=20261113 · "
             "하루 안 단위 먼저 평균) — 중앙값·절사평균(쌍 단위)의 구간이 아님. 주 수치 = «첫날 포함» 줄(§6). "
             "수익률 비교 없음(§4). 비용 출처 = "
             + ("allocated(하루 합계 배분 · 건별 아님)" if res.get("cost_source", "allocated") == "allocated"
                else "strict(건별 없음 → 지표4 미측정 · 배분값은 참고 절)") + ".")
    L.append("")
    L.append("## 1. 표본")
    p = c["pairs"]
    L.append(f"- 기간 거래일 {c['trading_days_in_period']} · ㉮ 짝 {p['㉮ 짝']}(㉮ 있는 거래일 {p['㉮ 있는 거래일']}) · "
             f"㉯ 페이퍼만 {p['㉯ 페이퍼만']} · ㉰ 실전만 {p['㉰ 실전만']} · 실전 미가동 {p['실전 미가동(분모 제외)']} · "
             f"재기동·수동 제외 행 {p['재기동·수동 제외 행']}")
    mc = c["min_condition_§1"]
    L.append(f"- §1 최소 조건(짝 ≥{mc['기준 짝']} 그리고 거래일 ≥{mc['기준 거래일']}): 짝 {mc['짝 n']} · 거래일 {mc['거래일']} → "
             f"{'둘 다 참' if mc['충족'] else '미달(표본 부족 · 계속)'}")
    L.append("- 청산쌍 분류(§4 · 건수만): " + " · ".join(f"{k} {v}" for k, v in res["exit_pair_categories"].items()))
    L.append("")
    L.append("## 2. 지표 5개 (첫날 포함 = 주 수치)")
    L.append(TABLE_HEAD)
    L.append(TABLE_RULE)
    rows = [
        ("1 신호 커버리지 %", res["m1"]["signal"]),
        ("1 집행 커버리지 %", res["m1"]["exec"]),
        ("1 사유별 커버리지 %(한도·현금 뺀 분모)", res["m1"]["signal_ex_cap_cash"]),
        ("1 수량 충족률 %", res["m1_fill_ratio"]),
        ("2 슬리피지 타이밍 %", res["m2"]["timing"]),
        ("2 슬리피지 집행 %", res["m2"]["exec"]),
        ("2 슬리피지 합 %", res["m2"]["total"]),
        ("2 슬리피지 틱", res["m2"]["ticks"]),
        ("3 손절 ㉠ %p · 실전 전체", res["m3_all"]["㉠ 감시·갭"]),
        ("3 손절 ㉡ % · 실전 전체", res["m3_all"]["㉡ 집행"]),
        ("3 손절 합 · 실전 전체", res["m3_all"]["합"]),
        ("3 손절 합 · 짝 줄 실전", res["m3_pair"]["실전"]["합"]),
        ("3 손절 합 · 짝 줄 페이퍼", res["m3_pair"]["페이퍼"]["합"]),
        ("3 손절 합 차 · 짝 줄(둘 다 손절)", res["m3_pair"]["차(실전 합 − 페이퍼 합 · 둘 다 손절)"]),
        ("4 비용 실제 % · 실전 전체", res["m4_all"]),
        ("4 비용 실제 % · 짝 줄", res["m4_pair"]),
        ("4 비용 가정 % · 실전 전체(참고)", res["m4_all_assumed"]),
        ("5 지연 (a) 실전 내부 초", res["m5"]["a_internal"]),
        ("5 지연 (b) 신호 시차 초", res["m5"]["b_signal_lag"]),
    ]
    for name, lines in rows:
        L.append(_line_row(name, "첫날 포함", lines["첫날 포함"]))
    L.append("")
    L.append("### 2-1. 첫날 제외 · 첫날만 · 상승일 · 하락일 (같은 지표 · 보조 줄)")
    L.append(TABLE_HEAD)
    L.append(TABLE_RULE)
    for name, lines in rows:
        for ln, s in lines.items():
            if ln != "첫날 포함":
                L.append(_line_row(name, ln, s))
    L.append("")
    L.append("## 3. §5 칸 값과의 거리 (거리 = 통계량 − 칸 값 · 판정 아님)")
    L.append("| 칸 | 통계량 | 칸 값 | 거리 |")
    L.append("|---|--:|--:|--:|")
    for k, v in res["cells"].items():
        L.append(f"| {k} | {_f(v['통계량'])} | {v['칸']} | {_f(v['거리'])} |")
    L.append("")
    L.append("## 4. 커버리지 사유 (㉯ · §3-1 매핑표 첫 해당 · 기계 판정)")
    L.append("- " + " · ".join(f"{k} {v}" for k, v in res["m1_reasons"].items()) if res["m1_reasons"] else "- ㉯ 0")
    for k, (a, b) in res["m1_pooled"].items():
        L.append(f"- {k}: {a}/{b}")
    for d, code, reason, flags in res["m1_paper_only"]:
        L.append(f"  - {d:%m-%d} {code}: {reason}" + (f" (그날 찍힌 사유 전부: {'·'.join(flags)})" if flags else ""))
    L.append("- 해석 금지(§3-1): «한도·현금» 비율은 사이징 구조값 — 양쪽 비율을 각각 적기만.")
    L.append("")
    L.append("## 5. 제외 목록 · 표식 (§6)")
    for k, v in res["exclusions"].items():
        if isinstance(v, dict):
            L.append(f"- {k}: " + " · ".join(f"{kk} {len(vv)}" for kk, vv in v.items()))
            for kk, vv in v.items():
                if vv:
                    L.append(f"  - {kk}: " + ", ".join(f"{d:%m-%d} {cd}" for d, cd in vv))
        else:
            L.append(f"- {k}: {len(v)}" + (" — " + ", ".join(_fmt_item(x) for x in v) if v else ""))
    for k, v in res["markers"].items():
        if isinstance(v, dict):
            L.append(f"- {k}: " + " · ".join(f"{kk} {vv}" for kk, vv in v.items()))
        elif isinstance(v, list):
            L.append(f"- {k}: {len(v)}" + (" — " + ", ".join(_fmt_item(x) for x in v) if v else ""))
        else:
            L.append(f"- {k}: {v}")
    L.append("")
    if res.get("m4_ref_allocated"):
        ref = res["m4_ref_allocated"]
        L.append("## 5-1. 참고 — 비용 배분값(strict 모드 · ① 칸에 쓰지 않음 · 건별 아님)")
        L.append(TABLE_HEAD)
        L.append(TABLE_RULE)
        for nm in ("실전 전체", "짝 줄"):
            for ln, s in ref[nm].items():
                L.append(_line_row(f"4 비용 배분 % · {nm}(참고)", ln, s))
        L.append(f"- 측정된 청산의 단순 평균(참고): {_f(ref['측정된 청산의 단순 평균'])} · 배분 불가 {len(ref['배분 불가'])}건")
        L.append("")
    L.append("## 6. 위반된 규칙 · 기계 점검")
    for t in FIXED_VIOLATIONS:
        L.append(f"- {t}")
    if res["checks"]:
        for k, v in res["checks"].items():
            L.append(f"- {k}: {v}")
    else:
        L.append("- 기계 점검 항목 없음(합성 자료)")
    L.append("- 사람 확인 칸(기계로 못 봄): 데이터 열람 뒤 규칙 변경 여부(§6 끝) · HTS/MTS 수동 개입(§7 ⑪) · 다른 측정과의 반복 열람(§7 ⑫).")
    L.append("")
    L.append("## 7. 미측정 비용 건수")
    L.append(f"- 미측정 {len(res['m4_unmeasured'])}건" + (" — " + ", ".join(_fmt_item(x) for x in res["m4_unmeasured"])
                                                    if res["m4_unmeasured"] else ""))
    L.append("")
    L.append("## 부록. 쌍 목록 (§6 M6 «마지막 구조 변화일 이후» 열 · 값 없음)")
    L.append("| 매수일 | 종목 | 마지막 구조 변화 | 청산쌍 분류(§4) | 첫날 | tp/sl 표식 |")
    L.append("|---|---|---|---|---|---|")
    for d, code, sc, cat, fd, b2 in res["pair_table"]:
        L.append(f"| {d:%m-%d} | {code} | {sc} | {cat} | {fd} | {b2} |")
    L.append("")
    return "\n".join(L)


def _fmt_item(x) -> str:
    if isinstance(x, tuple):
        return " ".join(f"{y:%m-%d}" if isinstance(y, date) else str(y) for y in x)
    return str(x)
