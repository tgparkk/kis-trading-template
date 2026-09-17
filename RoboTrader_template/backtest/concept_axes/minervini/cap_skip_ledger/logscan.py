"""라이브 로그 읽기(읽기 전용) — `robotrader_template_YYYYMMDD_*.log` (콘솔 캡처 = `trading_*.log` 의 상위집합).

뽑는 계기:
  e6        `[E6] minervini_volume_dryup: screener_snapshots N건 확보 (스냅샷 M건, 목표 T건, D-1=…)`
  excluded  그 줄 «직전 전략 블록»의 `후보 제외: CODE(…)` (안전성 필터 · 거래정지/관리/정리매매)
  cap       `[캡] minervini_volume_dryup CODE 평가 스킵 사유=R 보유=n/K 일일매수=d/5` (2026-09-16~)
  signal    `strategy.MinerviniVolumeDryupStrategy … 매수 시그널: CODE @ REF … recent/base=R` (라이브 «샀을 신호» 원본)
  nosignal  `strategy.MinerviniVolumeDryupStrategy … [신호없음] CODE: …` (일봉 N건 등)
  restore   `[진단] 런타임 포지션 엔트리 … 소유자별 {…}` 의 minervini 수 (07:40 기동 시 복원 포지션)
  notes     minervini 신호 «직후» 같은 종목의 `[진입억제]`·`[매수거절]`·`매수 판단 스킵` 줄

⚠️ 봇 가동 중엔 콘솔 캡처가 블록 버퍼링돼 당일 파일이 덜 써져 있을 수 있다 — 당일치는 봇 종료 후에 읽을 것.
"""
from __future__ import annotations

import ast
import glob
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_TS = r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \| (\S+) \| (\w+) \| "
RE_LINE = re.compile(_TS + r"(.*)$")
RE_E6_BOUNDARY = re.compile(r"\[E6\] (\S+): 후보 \d+종목")
RE_E6_MINERVINI = re.compile(
    r"\[E6\] minervini_volume_dryup: screener_snapshots (\d+)건 확보 "
    r"\(스냅샷 (\d+)건, 목표 (\d+)건, D-1=(\d{4}-\d{2}-\d{2})\)")
RE_E6_ZERO = re.compile(r"\[E6\] minervini_volume_dryup: screener_snapshots 0건")
RE_EXCLUDED = re.compile(r"후보 제외: (\w{6})\(")
RE_CAP = re.compile(r"\[캡\] minervini_volume_dryup (\w{6}) 평가 스킵 사유=(\w+) 보유=(\d+)/(\d+) "
                    r"일일매수=(\d+)/(\d+)")
RE_SIGNAL = re.compile(r"매수 시그널: (\w{6}) @ ([\d,]+) .*?recent/base=([0-9.]+)")
RE_NOSIG = re.compile(r"\[신호없음\] (\w{6}): (.*)$")
RE_RESTORE = re.compile(r"\[진단\] 런타임 포지션 엔트리 .*?소유자별 (\{.*?\})")
RE_NOTE = re.compile(r"(\[진입억제\] (\w{6}) .*|\[매수거절\] (\w{6}) .*|매수 판단 스킵: .*종목=(\w{6}).*)")
RE_ANY_SIGNAL = re.compile(r"매수 시그널: (\w{6}) @")

STRAT_LOGGER = "strategy.MinerviniVolumeDryupStrategy"
FOLDER = "minervini_volume_dryup"


@dataclass
class DayLog:
    d: date
    files: List[str] = field(default_factory=list)
    e6: Optional[Dict] = None
    e6_zero: bool = False
    excluded: List[str] = field(default_factory=list)
    cap: Dict[str, Dict] = field(default_factory=dict)          # 첫 줄만
    signals: Dict[str, Dict] = field(default_factory=dict)      # 첫 줄만
    nosignal: Dict[str, str] = field(default_factory=dict)      # 첫 줄만
    notes: Dict[str, List[str]] = field(default_factory=dict)
    restore_minervini: Optional[int] = None

    @property
    def found(self) -> bool:
        return bool(self.files)


def scan_day(log_dir: Path, d: date) -> DayLog:
    out = DayLog(d)
    paths = sorted(glob.glob(str(Path(log_dir) / f"robotrader_template_{d:%Y%m%d}_*.log")))
    out.files = [Path(p).name for p in paths]
    pending_excl: List[str] = []
    last_signal_owner: Dict[str, str] = {}
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.startswith(f"{d:%Y-%m-%d}"):
                    continue
                m = RE_LINE.match(line.rstrip("\n"))
                if not m:
                    continue
                _, hhmmss, logger, _lvl, msg = m.groups()
                if "[E6]" in msg:
                    if RE_E6_BOUNDARY.search(msg):
                        pending_excl = []
                    me = RE_E6_MINERVINI.search(msg)
                    if me and out.e6 is None:
                        out.e6 = dict(secured=int(me.group(1)), snapshot=int(me.group(2)),
                                      target=int(me.group(3)), d1=me.group(4), time=hhmmss)
                        out.excluded = list(pending_excl)
                    if RE_E6_ZERO.search(msg):
                        out.e6_zero = True
                    continue
                if "후보 제외" in msg:
                    mx = RE_EXCLUDED.search(msg)
                    if mx:
                        pending_excl.append(mx.group(1))
                    continue
                if "[캡] minervini_volume_dryup" in msg:
                    mc = RE_CAP.search(msg)
                    if mc and mc.group(1) not in out.cap:
                        out.cap[mc.group(1)] = dict(reason=mc.group(2), held=int(mc.group(3)),
                                                    k=int(mc.group(4)), daily=int(mc.group(5)), time=hhmmss)
                    continue
                if out.restore_minervini is None and "런타임 포지션 엔트리" in msg:
                    mr = RE_RESTORE.search(msg)
                    if mr:
                        try:
                            out.restore_minervini = int(ast.literal_eval(mr.group(1)).get(FOLDER, 0))
                        except (ValueError, SyntaxError):
                            pass
                    continue
                if "매수 시그널" in msg:
                    ma = RE_ANY_SIGNAL.search(msg)
                    if ma:
                        last_signal_owner[ma.group(1)] = logger
                    if logger == STRAT_LOGGER:
                        ms = RE_SIGNAL.search(msg)
                        if ms and ms.group(1) not in out.signals:
                            out.signals[ms.group(1)] = dict(ref=float(ms.group(2).replace(",", "")),
                                                            ratio=ms.group(3), time=hhmmss)
                    continue
                if logger == STRAT_LOGGER and "[신호없음]" in msg:
                    mn = RE_NOSIG.search(msg)
                    if mn and mn.group(1) not in out.nosignal:
                        out.nosignal[mn.group(1)] = f"{hhmmss} {mn.group(2)}"
                    continue
                mnote = RE_NOTE.search(msg)
                if mnote:
                    code = mnote.group(2) or mnote.group(3) or mnote.group(4)
                    owned = (FOLDER in msg) or (last_signal_owner.get(code) == STRAT_LOGGER)
                    if code and owned:
                        lst = out.notes.setdefault(code, [])
                        if len(lst) < 3:
                            lst.append(f"{hhmmss} {mnote.group(1)[:90]}")
    return out


def live_candidate_list(snapshot_codes: List[str], daylog: DayLog, default_target: int = 10
                        ) -> Tuple[List[str], str]:
    """라이브 E6 목록 재구성 = 스냅샷 순서 − 안전필터 제외 → 앞에서 «목표» 개수.

    (core/candidate_selector.py:1110-1141 — 섹터뉴스 재정렬은 기본 shadow 라 순서 불변.)
    """
    if daylog.e6 is not None:
        target = daylog.e6["target"]
        src = "log"
    else:
        target = default_target
        src = "no_e6_log(default)"
    excl = set(daylog.excluded)
    kept = [c for c in snapshot_codes if c not in excl][:target]
    if daylog.e6 is not None and len(kept) != daylog.e6["secured"]:
        src += f"·count_mismatch(recon {len(kept)} vs log {daylog.e6['secured']})"
    return kept, src
