"""
analyze_tick_trace.py — tick_trace JSONL 분석 CLI
==================================================

사용법:
    python scripts/analyze_tick_trace.py [--date YYYY-MM-DD] [--top N]

기본값: --date=오늘, --top=10
입력:   logs/tick_trace/{date}.jsonl

출력 예:
    ===== TICK TRACE 분석: 2026-04-13 =====
    총 이벤트: 12345 / 종목 수: 87

    [스킵 사유 Top 10]
      1. no_daily_data          5678 (46.0%)
      ...

    [이벤트 타입별 분포]
      skipped          9876 (80.0%)
      ...

    [종목별 평가 횟수 Top 10]
      005930  (평가=150, 신호=3, 스킵=12)
      ...

    [신호 발생 종목]
      005930  BUY  conf=0.75  @09:15:23
      ...
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


def analyze(base_dir: Path, date: str, top: int = 10) -> str:
    """JSONL 파일을 읽고 분석 결과 문자열을 반환.

    Args:
        base_dir: logs/tick_trace/ 디렉터리 경로.
        date:     분석할 날짜 (YYYY-MM-DD 문자열).
        top:      Top N 개수.

    Returns:
        분석 결과 문자열. 파일이 없으면 "파일 없음" 메시지 반환.
    """
    path = Path(base_dir) / f"{date}.jsonl"

    if not path.exists():
        return f"[오류] 파일 없음: {path}"

    # 파일 파싱
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    total = len(events)

    # 집계
    event_type_counter: Counter = Counter()
    skip_reason_counter: Counter = Counter()
    # stock_code → {"evaluated": N, "signal": N, "skipped": N}
    stock_stats: dict = defaultdict(lambda: {"evaluated": 0, "signal": 0, "skipped": 0})
    signals = []
    stock_codes: set = set()

    for ev in events:
        etype = ev.get("event_type", "unknown")
        event_type_counter[etype] += 1

        code = ev.get("stock_code", "")
        if code:
            stock_codes.add(code)

        if etype == "skipped":
            reason = ev.get("skip_reason", "unknown")
            skip_reason_counter[reason] += 1
            if code:
                stock_stats[code]["skipped"] += 1

        elif etype == "evaluated":
            if code:
                stock_stats[code]["evaluated"] += 1

        elif etype == "signal_generated":
            if code:
                stock_stats[code]["signal"] += 1
            # 신호 시각: ts 필드에서 시분초만 추출
            ts_raw = ev.get("ts", "")
            time_str = ""
            if "T" in ts_raw:
                time_part = ts_raw.split("T")[1]
                # +09:00 또는 .microsecond 제거
                time_str = time_part[:8]  # HH:MM:SS
            signals.append({
                "stock_code": code,
                "signal_type": ev.get("signal_type", ev.get("signal", "?")),
                "confidence": ev.get("confidence", None),
                "time": time_str,
            })

    # 렌더링
    lines = []
    lines.append(f"===== TICK TRACE 분석: {date} =====")
    lines.append(f"총 이벤트: {total} / 종목 수: {len(stock_codes)}")
    lines.append("")

    # 스킵 사유 Top N
    lines.append(f"[스킵 사유 Top {top}]")
    if skip_reason_counter:
        skip_total = sum(skip_reason_counter.values())
        for rank, (reason, count) in enumerate(skip_reason_counter.most_common(top), 1):
            pct = count / skip_total * 100 if skip_total else 0
            lines.append(f"  {rank:2d}. {reason:<30s} {count:6d} ({pct:5.1f}%)")
    else:
        lines.append("  (없음)")
    lines.append("")

    # 이벤트 타입별 분포
    lines.append("[이벤트 타입별 분포]")
    if event_type_counter:
        for etype, count in event_type_counter.most_common():
            pct = count / total * 100 if total else 0
            lines.append(f"  {etype:<20s} {count:6d} ({pct:5.1f}%)")
    else:
        lines.append("  (없음)")
    lines.append("")

    # 종목별 평가 횟수 Top N (evaluated 기준 정렬)
    lines.append(f"[종목별 평가 횟수 Top {top}]")
    sorted_stocks = sorted(
        stock_stats.items(),
        key=lambda kv: kv[1]["evaluated"],
        reverse=True,
    )[:top]
    if sorted_stocks:
        for code, stats in sorted_stocks:
            lines.append(
                f"  {code}  "
                f"(평가={stats['evaluated']}, "
                f"신호={stats['signal']}, "
                f"스킵={stats['skipped']})"
            )
    else:
        lines.append("  (없음)")
    lines.append("")

    # 신호 발생 종목
    lines.append("[신호 발생 종목]")
    if signals:
        for sig in signals:
            conf_str = f"conf={sig['confidence']:.2f}" if sig["confidence"] is not None else ""
            time_str = f"@{sig['time']}" if sig["time"] else ""
            parts = [f"  {sig['stock_code']}", sig["signal_type"], conf_str, time_str]
            lines.append("  ".join(p for p in parts if p))
    else:
        lines.append("  (없음)")

    return "\n".join(lines)


def main() -> None:
    """argparse CLI 진입점."""
    parser = argparse.ArgumentParser(
        description="tick_trace JSONL 파일 분석 도구",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="분석할 날짜 (YYYY-MM-DD). 기본값: 오늘",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Top N 개수. 기본값: 10",
    )
    parser.add_argument(
        "--dir",
        default=None,
        help="tick_trace 디렉터리 경로. 기본값: logs/tick_trace (스크립트 기준)",
    )
    args = parser.parse_args()

    if args.dir:
        base_dir = Path(args.dir)
    else:
        # scripts/ 기준으로 상위 디렉터리 → logs/tick_trace/
        base_dir = Path(__file__).parent.parent / "logs" / "tick_trace"

    result = analyze(base_dir, date=args.date, top=args.top)
    print(result)

    # 파일 없음이면 exit code 1
    if "파일 없음" in result or "오류" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
