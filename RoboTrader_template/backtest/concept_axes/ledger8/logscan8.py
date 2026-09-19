"""라이브 로그 읽기(읽기 전용 · 8전략 동시) — `robotrader_template_YYYYMMDD_*.log`.

콘솔 캡처 파일은 `trading_*.log` 의 **상위집합**이다. 파일 한 번 순회로 8전략 것을 전부 모은다.
봇은 전략을 «하나씩» 돈다(main.py:465-493 라운드로빈 · `await strat.on_tick(ctx)`) ⇒ 한 전략의
`[on_tick] 매수신호: CODE(` 줄(strategies/base.py:723-726) 바로 뒤의 매수 실행 경로 줄은 그 (전략, 종목)의 것이다.

뽑는 계기 (2026-09-19 로그·코드 실측)
────────────────────────────────
| 키 | 원본 줄 | 생산자 |
|---|---|---|
| `e6`·`e6_zero` | `[E6] <전략>: screener_snapshots N건 확보 (…)` · `… 0건 (D-1=…)` | core/candidate_selector.py:1098-1101·1137-1140 |
| `excluded` | `후보 제외: CODE(NAME) — 사유` — 다음 E6 확보 줄의 전략 몫 | candidate_selector 안전필터 |
| `sector_mode` | `[섹터뉴스] <전략> mode=shadow …` (shadow 면 순서 불변) | candidate_selector 재정렬 |
| `buysig` 🔑 | `[on_tick] 매수신호: CODE(BUY, 신뢰도 x, 이유: …)` — **매수 루프 전용 = 신호 기준** | base.py:723-726 |
| `ontick_times` | `[on_tick] 매수검토 N종목(스킵 k), 신호 m건 | …` 시각 — 그 전략 on_tick 1회 «완료»(빈자리 구간 판정) | base.py:763-766 |
| `receipt` | `🧾 [PAPER] 매수 시그널: CODE @ REF (…추천 Q주) | 사유` — 매도 루프 줄 섞임 ⇒ 기준가 대조용 | 각 전략 `_check_buy` |
| `cap` | `[캡] <전략> CODE 평가 스킵 사유=R 보유=n/K 일일매수=d/M` — `timeframe` 은 매수 차단 아님 | base.py:576-605 |
| `nosignal` | `[신호없음] CODE: …` | base.py on_tick · rs_leader corp_action |
| `gates` | 아래 매수 실행 경로 줄 — 직전 `[on_tick] 매수신호` 의 (전략, 종목)에 귀속 | trading_context · trading_analyzer · decision_engine · VTM |
| `fills` | `가상매수: CODE Q주 @P (익절:x% 손절:y%)` | core/trading_decision_engine.py:698-701 |
| `per_stock` | `종목당 투자금액 재산정: <전략> A원 → B원 (자본 …, 기준 …원)` | core/virtual_trading_manager.py:300-361 |
| `restore_n` | `[진단] 런타임 포지션 엔트리 … 소유자별 {…}` | bot/state_restorer.py |
| `market_dir` | `[시장방향성필터] 관측 지수=X … 판정=차단|허용` — 급락게이트 시간선 | core/trading_decision_engine.py:210-218 |
| `rs_mode` | `[rs-corp-action] mode=… (startup)` | strategies/rs_leader/strategy.py:85 |

매수 실행 경로 게이트 (core/trading_context.py:313-539 → bot/trading_analyzer.py:103-186 → 엔진 → VTM)
| 게이트 | 줄 | 종목 칸 |
|---|---|---|
| market_crash | `매수 판단 스킵: 시장급락 (…)` (+ `종목= 전략= 해석지수=` 는 2026-09-16~) | 09-15 이전 없음 → 직전 매수신호에 귀속 |
| regime_gate | `매수 판단 스킵: 국면게이트 (…)` | 없음 |
| owned_other | `매수 거부: CODE는 이미 OWNER 소유 …` | 있음 |
| buy_stop | `매수스톱 미도달 스킵: CODE (…)` | 있음 |
| limit_up | `매수 차단: 상한가 접근 (…)` | 없음 |
| daily_loss | `매수 차단: 일일 손실 한도 초과 (…)` (WARNING · core/trading_context.py:428-436) | 없음 |
| throttle | `[진입억제] CODE 매수 스킵 — 쿨다운|이번 사이클 …` | 있음 |
| held_any | `보유 중인 종목 매수 신호 무시: CODE(NAME)` — 어느 전략이든 보유 | 있음 |
| band_above·band_below·qty_short·no_price·reject_other | `[매수거절] CODE 사유` | 있음 |
| balance_short | VTM `전략 가상 잔고 부족 [전략]` | 없음(전략만) |
| unfilled | `CODE 가상 매수 미체결 — 예약 취소` | 있음 |

🔴 주의
1. 불가능봉(`strategies/_rule_screener_base.py:180`)·rs `— 후보 제외 (mode=live)`(rs_leader/screener.py:151) 줄은 콜론형
   `후보 제외:` 가 아니다. 스크리너 훅이 D 09:00 에 scan_date=D-1 스냅샷을 쓰면서 이미 뺀 종목이라 E6 목록을 다시
   줄일 필요가 없다(검증표 #17 — 이유 정정).
2. 귀속 못 한 게이트 줄은 버리지 않고 `DayLog.unattributed` 에 센다.
3. 봇 가동 중엔 콘솔 캡처가 블록 버퍼링돼 당일 파일이 덜 써져 있을 수 있다.
4. 창 안 0건이라 실측 표본이 없는 줄(`국면게이트`·`매수 거부`·`상한가 접근`·`이번 사이클`·`일일 손실 한도`)은 코드 문자열로 정규식을 적었다.
5. VI 매수 보류(`{code} 매수 스킵: VI 발동 중` · trading_context.py:424-426)와 25분 매수 쿨다운(trading_analyzer.py:132-136)은 DEBUG 라 로그 파일에 없다.

접기 — 행 단위는 «평가 1회»가 아니라 `(날짜, 전략, 종목, 계기)` 이고 `n`·`first`·`last` 로 접는다.
"""
from __future__ import annotations

import ast
import glob
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TS = r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \| (\S+) \| (\w+) \| "
RE_LINE = re.compile(_TS + r"(.*)$")

# ── 후보 블록 ──
RE_E6_BOUNDARY = re.compile(r"\[E6\] (\S+): 후보 \d+종목")
RE_E6_OK = re.compile(r"\[E6\] (\S+): screener_snapshots (\d+)건 확보 "
                      r"\(스냅샷 (\d+)건, 목표 (\d+)건, D-1=(\d{4}-\d{2}-\d{2})\)")
RE_E6_ZERO = re.compile(r"\[E6\] (\S+): screener_snapshots 0건 \(D-1=(\d{4}-\d{2}-\d{2})\)")
RE_EXCLUDED = re.compile(r"후보 제외: (\w{6})\(")
RE_SECTOR = re.compile(r"\[섹터뉴스\] (\S+) mode=(\w+)")
# ── 기동 ──
RE_RESTORE = re.compile(r"\[진단\] 런타임 포지션 엔트리 .*?소유자별 (\{.*?\})")
RE_RECALC = re.compile(r"종목당 투자금액 재산정: (\S+) ([\d,]+)원 → ([\d,]+)원 "
                       r"\(자본 ([\d,]+)/([\d,]+) = ([\d.]+), 기준 ([\d,]+)원\)")
RE_RS_MODE = re.compile(r"\[rs-corp-action\] mode=(\w+) \(startup\)")
RE_MKT_DIR = re.compile(r"\[시장방향성필터\] 관측 지수=(\w+) 코드=\w+ 등락률=([+-]?[\d.]+)% "
                        r"임계값=([+-]?[\d.]+)% 판정=(\S+)")
# ── 전략 로거(strategy.<Cls>) ──
RE_BUYSIG = re.compile(r"\[on_tick\] 매수신호: (\w{6})\((\w+), 신뢰도 ([\d.]+), 이유: (.*)\)$")
RE_ONTICK_SUMMARY = re.compile(r"\[on_tick\] 매수검토 (\d+)종목\(스킵 (\d+)\), 신호 (\d+)건")
# 두 형식:  "… @ 12,345 (추천 8주)"  ·  "… @ 12,345 (매수스톱 12,900, 추천 7주)"
RE_RECEIPT = re.compile(r"매수 시그널: (\w{6}) @ ([\d,]+) \(.*?추천 (\d+)주\)(?: \| (.*))?$")
RE_CAP = re.compile(r"\[캡\] (\S+) (\w{6}) 평가 스킵 사유=(\w+) 보유=(\d+)/(\d+) 일일매수=(\d+)/(\d+)")
RE_NOSIG = re.compile(r"\[신호없음\] (\w{6}): (.*)$")
# ── 매수 실행 경로 ──
RE_CRASH = re.compile(r"매수 판단 스킵: 시장급락 \((.*)\)(?: 종목=(\w{6}) 전략=(\S+) 해석지수=(\S+))?$")
RE_HELD_ANY = re.compile(r"보유 중인 종목 매수 신호 무시: (\w{6})\(")
RE_OWNED = re.compile(r"매수 거부: (\w{6})는 이미 (\S+) 소유")
RE_BUYSTOP = re.compile(r"매수스톱 미도달 스킵: (\w{6}) ")
RE_LIMITUP = re.compile(r"매수 차단: 상한가 접근")
RE_DAILY_LOSS = re.compile(r"매수 차단: 일일 손실 한도 초과")
RE_THROTTLE = re.compile(r"\[진입억제\] (\w{6}) 매수 스킵 — (?:쿨다운|이번 사이클)")
RE_REJECT = re.compile(r"\[매수거절\] (\w{6}) (.*)$")
RE_BAL_SHORT = re.compile(r"전략 가상 잔고 부족 \[(\S+)\]")
RE_UNFILLED = re.compile(r"(\w{6}) 가상 매수 미체결")
RE_FILL = re.compile(r"가상매수: (\w{6}) (\d+)주 @([\d,]+) \(익절:([\d.]+)% 손절:([\d.]+)%\)")

G_CRASH = "market_crash"
G_REGIME = "regime_gate"
G_HELD_ANY = "held_any"
G_OWNED = "owned_other"
G_BUYSTOP = "buy_stop"
G_LIMITUP = "limit_up"
G_THROTTLE = "throttle"
G_BAND_ABOVE = "band_above"
G_BAND_BELOW = "band_below"
G_QTY = "qty_short"
G_BALANCE = "balance_short"
G_NO_PRICE = "no_price"
G_UNFILLED = "unfilled"
G_REJECT_OTHER = "reject_other"
G_DAILY_LOSS = "daily_loss"
G_FILL = "fill"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass
class Fold:
    """(전략, 종목, 계기) 하나에 대한 접힌 관측."""
    n: int = 0
    first: str = ""
    last: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def hit(self, hhmmss: str, **detail: Any) -> None:
        self.n += 1
        if not self.first:
            self.first = hhmmss
            self.detail.update(detail)     # 첫 줄의 값을 대표로 둔다
        self.last = hhmmss


@dataclass
class StratDay:
    """한 전략의 하루치 로그 관측."""
    e6: Optional[Dict[str, Any]] = None
    e6_zero: bool = False
    excluded: List[str] = field(default_factory=list)
    sector_mode: str = ""
    buysig: Dict[str, Fold] = field(default_factory=dict)
    receipt: Dict[str, Fold] = field(default_factory=dict)
    cap: Dict[Tuple[str, str], Fold] = field(default_factory=dict)
    nosignal: Dict[str, Fold] = field(default_factory=dict)
    gates: Dict[Tuple[str, str], Fold] = field(default_factory=dict)
    fills: Dict[str, Fold] = field(default_factory=dict)
    ontick_times: List[str] = field(default_factory=list)   # `[on_tick] 매수검토` 줄 시각 = on_tick 1회 «완료»
    restore_n: Optional[int] = None
    per_stock: Optional[Dict[str, Any]] = None

    @property
    def ontick_runs(self) -> int:
        return len(self.ontick_times)

    def cap_blocking(self, code: str) -> Dict[str, Fold]:
        """«매수 차단» `[캡]` 사유만 — `timeframe` 은 position_monitor 분봉 경로라 뺀다."""
        return {r: f for (c, r), f in self.cap.items() if c == code and r != "timeframe"}

    def gates_for(self, code: str) -> Dict[str, Fold]:
        return {g: f for (c, g), f in self.gates.items() if c == code}


@dataclass
class DayLog:
    d: date
    files: List[str] = field(default_factory=list)
    by_strategy: Dict[str, StratDay] = field(default_factory=lambda: OrderedDict())
    owner_counts: Dict[str, int] = field(default_factory=dict)
    rs_mode: str = ""
    market_dir: List[Tuple[str, str, str]] = field(default_factory=list)   # (hhmmss, 지수, 판정)
    unattributed: Dict[str, int] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return bool(self.files)

    def get(self, folder: str) -> StratDay:
        return self.by_strategy.setdefault(folder, StratDay())

    def index_state(self, index: str, hhmmss: str) -> str:
        """그 시각 `index` 급락게이트 판정 — 그 시각 이전 마지막 관측, 없으면 그날 첫 관측. 관측 0 이면 ''."""
        obs = [(t, v) for t, i, v in self.market_dir if i == index]
        if not obs:
            return ""
        before = [v for t, v in obs if t <= hhmmss]
        return before[-1] if before else obs[0][1]

    def first_verdict_after(self, index: str, hhmmss: str, verdict: str) -> str:
        for t, i, v in self.market_dir:
            if i == index and t > hhmmss and v == verdict:
                return t
        return ""


@dataclass
class GateHit:
    gate: str
    code: Optional[str] = None
    owner: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


def reject_gate(text: str) -> str:
    """`[매수거절] CODE 사유` 의 사유 → 게이트(엔진 문자열 core/trading_decision_engine.py:356-430)."""
    t = text.strip()
    if t.startswith("수량부족"):
        return G_QTY
    if "밴드 이탈" in t:
        return G_BAND_ABOVE
    if "밴드 하회" in t:
        return G_BAND_BELOW
    if "시장급락" in t:
        return G_CRASH
    if "현재가 미확보" in t:
        return G_NO_PRICE
    return G_REJECT_OTHER


def parse_gate(msg: str) -> Optional[GateHit]:
    """매수 실행 경로 줄이면 GateHit, 아니면 None."""
    if "매수 판단 스킵: 시장급락" in msg:
        mc = RE_CRASH.search(msg)
        return GateHit(G_CRASH, mc.group(2) if mc else None, mc.group(3) if mc else None)
    if "매수 판단 스킵: 국면게이트" in msg:
        return GateHit(G_REGIME)
    for rx, gate in ((RE_HELD_ANY, G_HELD_ANY), (RE_OWNED, G_OWNED), (RE_BUYSTOP, G_BUYSTOP),
                     (RE_THROTTLE, G_THROTTLE), (RE_UNFILLED, G_UNFILLED)):
        mm = rx.search(msg)
        if mm:
            return GateHit(gate, mm.group(1))
    if RE_LIMITUP.search(msg):
        return GateHit(G_LIMITUP)
    if RE_DAILY_LOSS.search(msg):
        return GateHit(G_DAILY_LOSS)
    mr = RE_REJECT.search(msg)
    if mr:
        return GateHit(reject_gate(mr.group(2)), mr.group(1))
    mb = RE_BAL_SHORT.search(msg)
    if mb:
        return GateHit(G_BALANCE, None, mb.group(1))
    mf = RE_FILL.search(msg)
    if mf:
        return GateHit(G_FILL, mf.group(1), None, dict(qty=int(mf.group(2)), price=_num(mf.group(3)),
                                                      tp_pct=float(mf.group(4)), sl_pct=float(mf.group(5))))
    return None


def attribute(g: GateHit, pending: Optional[Tuple[str, str]],
              last_owner: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """(전략, 종목). 3필드 줄은 줄 안 값 · 종목 없는 줄은 직전 매수신호 · 종목 있는 줄은 직전 매수신호가
    같은 종목이면 그 전략, 아니면 그 종목의 마지막 매수신호 전략."""
    if g.code is not None and g.owner is not None:
        return g.owner, g.code
    if g.code is None:
        if pending is None:
            return None, None
        if g.owner is not None and g.owner != pending[0]:
            return None, None
        return pending
    if pending is not None and pending[1] == g.code:
        return pending[0], g.code
    return last_owner.get(g.code), g.code


def _scan_candidate_block(out: DayLog, known: set, msg: str, t: str, pending_excl: List[str]) -> bool:
    if "[E6]" in msg:
        if RE_E6_BOUNDARY.search(msg):
            pending_excl.clear()
            return True
        mo = RE_E6_OK.search(msg)
        if mo and mo.group(1) in known:
            sd = out.get(mo.group(1))
            if sd.e6 is None:
                sd.e6 = dict(secured=int(mo.group(2)), snapshot=int(mo.group(3)), target=int(mo.group(4)),
                             d1=mo.group(5), time=t)
                sd.excluded = list(pending_excl)
            return True
        mz = RE_E6_ZERO.search(msg)
        if mz and mz.group(1) in known:
            sd = out.get(mz.group(1))
            sd.e6_zero = True
            if sd.e6 is None:
                sd.e6 = dict(secured=0, snapshot=0, target=0, d1=mz.group(2), time=t)
                sd.excluded = list(pending_excl)
        return True
    if "후보 제외:" in msg:
        mx = RE_EXCLUDED.search(msg)
        if mx:
            pending_excl.append(mx.group(1))
        return True
    if "[섹터뉴스]" in msg:
        ms = RE_SECTOR.search(msg)
        if ms and ms.group(1) in known and not out.get(ms.group(1)).sector_mode:
            out.get(ms.group(1)).sector_mode = ms.group(2)
        return True
    return False


def _scan_startup(out: DayLog, known: set, msg: str, t: str) -> bool:
    if "런타임 포지션 엔트리" in msg:
        mr = RE_RESTORE.search(msg)
        if mr and not out.owner_counts:
            try:
                owners = ast.literal_eval(mr.group(1))
                out.owner_counts = {str(k): int(v) for k, v in owners.items()}
                for f_ in known:
                    out.get(f_).restore_n = out.owner_counts.get(f_, 0)
            except (ValueError, SyntaxError):
                pass
        return True
    if "종목당 투자금액 재산정" in msg:
        mr = RE_RECALC.search(msg)
        if mr and mr.group(1) in known:
            out.get(mr.group(1)).per_stock = dict(
                old=_num(mr.group(2)), new=_num(mr.group(3)), capital=_num(mr.group(4)),
                initial=_num(mr.group(5)), ratio=float(mr.group(6)), base=_num(mr.group(7)), time=t)
        return True
    if "[rs-corp-action] mode=" in msg:
        mm = RE_RS_MODE.search(msg)
        if mm and not out.rs_mode:
            out.rs_mode = mm.group(1)
        return True
    if "[시장방향성필터] 관측 지수" in msg:
        md = RE_MKT_DIR.search(msg)
        if md:
            out.market_dir.append((t, md.group(1), md.group(4)))
        return True
    return False


def _scan_strategy_line(sd: StratDay, folder: str, msg: str, t: str,
                        pending: Optional[Tuple[str, str]], last_owner: Dict[str, str]
                        ) -> Optional[Tuple[str, str]]:
    """전략 로거 줄 하나를 반영하고 새 pending 을 돌려준다."""
    if "[on_tick] 매수신호" in msg:
        mb = RE_BUYSIG.search(msg)
        if mb:
            code = mb.group(1)
            sd.buysig.setdefault(code, Fold()).hit(t, signal_type=mb.group(2), confidence=float(mb.group(3)),
                                                   reasons=mb.group(4))
            last_owner[code] = folder
            return (folder, code)
        return pending
    if "[on_tick] 매수검토" in msg:
        if RE_ONTICK_SUMMARY.search(msg):
            sd.ontick_times.append(t)
        return None
    if "매수 시그널:" in msg:
        ms = RE_RECEIPT.search(msg)
        if ms:
            sd.receipt.setdefault(ms.group(1), Fold()).hit(t, ref=_num(ms.group(2)), qty=int(ms.group(3)),
                                                           reasons=(ms.group(4) or "")[:200])
    elif "[캡]" in msg:
        mc = RE_CAP.search(msg)
        if mc and mc.group(1) == folder:
            sd.cap.setdefault((mc.group(2), mc.group(3)), Fold()).hit(
                t, held=int(mc.group(4)), k=int(mc.group(5)), daily=int(mc.group(6)), mdt=int(mc.group(7)))
    elif "[신호없음]" in msg:
        mn = RE_NOSIG.search(msg)
        if mn:
            sd.nosignal.setdefault(mn.group(1), Fold()).hit(t, msg=mn.group(2)[:120])
    return pending


def scan_day(log_dir: Path, d: date, folders: Sequence[str], logger_to_folder: Dict[str, str]) -> DayLog:
    """하루치 로그를 한 번 순회해 전 전략 관측을 모은다."""
    out = DayLog(d)
    for f in folders:
        out.get(f)
    paths = sorted(glob.glob(str(Path(log_dir) / f"robotrader_template_{d:%Y%m%d}_*.log")))
    out.files = [Path(p).name for p in paths]
    known = set(folders)
    day_prefix = f"{d:%Y-%m-%d}"
    for p in paths:
        pending_excl: List[str] = []
        pending: Optional[Tuple[str, str]] = None
        last_owner: Dict[str, str] = {}
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.startswith(day_prefix):
                    continue
                m = RE_LINE.match(line.rstrip("\n"))
                if not m:
                    continue
                _, t, logger, _lvl, msg = m.groups()
                if _scan_candidate_block(out, known, msg, t, pending_excl):
                    continue
                if _scan_startup(out, known, msg, t):
                    continue
                folder = logger_to_folder.get(logger)
                if folder in known:
                    pending = _scan_strategy_line(out.get(folder), folder, msg, t, pending, last_owner)
                    continue
                g = parse_gate(msg)
                if g is None:
                    continue
                owner, code = attribute(g, pending, last_owner)
                if owner in known and code:
                    sd = out.get(owner)
                    if g.gate == G_FILL:
                        sd.fills.setdefault(code, Fold()).hit(t, **g.detail)
                    else:
                        sd.gates.setdefault((code, g.gate), Fold()).hit(t, text=msg[:120])
                else:
                    out.unattributed[g.gate] = out.unattributed.get(g.gate, 0) + 1
    return out


@dataclass
class CandList:
    main: List[str]
    ext: List[str]
    target: int
    src: str


def live_candidate_list(snapshot_codes: Sequence[str], sd: StratDay, default_target: int = 10) -> CandList:
    """라이브 E6 목록 재구성 = 스냅샷 순위순 − 안전필터 제외 → 앞에서 «목표» 개수
    (core/candidate_selector.py:1104-1141). 안전필터는 «지연»이다(limit=max_candidates) — 목표만큼 모이면
    멈추므로 제외 줄은 main 구간에서만 나온다 ⇒ ext(나머지 = 스냅샷 T+1~20위)는 안전필터 미검사.
    """
    if sd.e6 is not None:
        target, src = int(sd.e6["target"]), "log"
    else:
        target, src = default_target, "no_e6_log(default)"
    excl = set(sd.excluded)
    kept = [c for c in snapshot_codes if c not in excl]
    main, ext = kept[:target], kept[target:]
    if sd.e6 is not None and len(main) != sd.e6["secured"]:
        src += f"·count_mismatch(recon {len(main)} vs log {sd.e6['secured']})"
    if sd.sector_mode and sd.sector_mode != "shadow":
        src += f"·sector_mode={sd.sector_mode}(순서 재정렬 가능)"
    return CandList(main, ext, target, src)
