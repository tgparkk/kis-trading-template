"""
TickTracer — on_tick 이벤트 JSONL 로거
=======================================

매 이벤트(evaluated/skipped/signal_generated/buy_executed/sell_executed)를
날짜별 JSONL 파일에 기록. on_tick 루프 계측용 인프라.

사용 예:
    tracer = TickTracer(base_dir=Path("logs/tick_trace"))
    await tracer.emit({
        "stock_code": "005930",
        "event_type": "skipped",
        "skip_reason": "insufficient_data",
        "indicators": {"ma5": 70000.0, "rsi14": 45.2},
    })

출력 파일: logs/tick_trace/2026-04-12.jsonl
각 줄: {"ts": "2026-04-12T09:15:23.456+09:00", "stock_code": "005930", ...}
"""

import asyncio
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict


# KST: UTC+9
_KST = timezone(timedelta(hours=9))


class TickTracer:
    """on_tick 이벤트를 JSONL 파일로 기록하는 비동기 로거.

    Args:
        base_dir: JSONL 파일을 저장할 디렉터리 경로.
                  파일명은 날짜별 자동 결정 (YYYY-MM-DD.jsonl).
        enabled:  False 이면 모든 emit()이 즉시 no-op 반환.
    """

    def __init__(self, base_dir: Path, enabled: bool = True) -> None:
        self.base_dir = Path(base_dir)
        self.enabled = enabled
        self._lock = asyncio.Lock()

    async def emit(self, event: Dict[str, Any], strategy_name: str = "") -> None:
        """이벤트를 오늘 날짜 JSONL 파일에 한 줄 추가.

        ts 필드(KST ISO 8601)는 자동으로 맨 앞에 삽입된다.
        strategy_name이 제공되고 event에 없으면 자동 추가된다.
        event dict는 수정하지 않는다 (shallow copy 사용).

        Args:
            event: 기록할 이벤트 딕셔너리. 최소 필드 없음 — 호출자 책임.
            strategy_name: 이벤트를 발생시킨 전략 이름 (없으면 빈 문자열).
        """
        if not self.enabled:
            return

        extra: Dict[str, Any] = {}
        if strategy_name and "strategy_name" not in event:
            extra["strategy_name"] = strategy_name
        record = {"ts": self._now_iso(), **extra, **event}
        path = self.base_dir / f"{date.today().isoformat()}.jsonl"

        async with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _now_iso() -> str:
        """현재 KST 시각을 ISO 8601 문자열로 반환.

        예: "2026-04-12T09:15:23.456789+09:00"
        """
        return datetime.now(_KST).isoformat()
