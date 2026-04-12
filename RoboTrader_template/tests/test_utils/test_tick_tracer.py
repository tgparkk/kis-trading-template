"""
TickTracer JSONL 로거 테스트
============================

TDD: 테스트 먼저 작성, 구현 후 PASS 확인
"""

import asyncio
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.tick_tracer import TickTracer


# ============================================================================
# Test 1: 기본 JSONL 쓰기
# ============================================================================

class TestTickTracerWritesJsonl:
    """test_tick_tracer_writes_jsonl — 기본 emit → JSONL 파일 생성 확인."""

    @pytest.mark.asyncio
    async def test_tick_tracer_writes_jsonl(self, tmp_path):
        """
        Given: TickTracer with base_dir=tmp_path/tick_trace
        When: emit() 3회 (skipped 이벤트)
        Then:
          - 오늘 날짜 파일 생성
          - 3줄
          - 각 줄 valid JSON
          - ts 필드 자동 추가
          - ts에 KST 오프셋(+09:00) 포함
        """
        base_dir = tmp_path / "tick_trace"
        tracer = TickTracer(base_dir=base_dir)

        event = {
            "stock_code": "005930",
            "event_type": "skipped",
            "skip_reason": "no_daily_data",
        }

        await tracer.emit(event)
        await tracer.emit(event)
        await tracer.emit(event)

        today_str = date.today().isoformat()
        out_file = base_dir / f"{today_str}.jsonl"
        assert out_file.exists(), f"파일이 생성되지 않음: {out_file}"

        lines = out_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3, f"줄 수 불일치: {len(lines)}"

        for line in lines:
            obj = json.loads(line)  # valid JSON 검증
            assert "ts" in obj, "ts 필드 없음"
            assert "+09:00" in obj["ts"], f"KST 오프셋 없음: {obj['ts']}"
            assert obj["stock_code"] == "005930"
            assert obj["event_type"] == "skipped"

    @pytest.mark.asyncio
    async def test_disabled_tracer_writes_nothing(self, tmp_path):
        """enabled=False 이면 파일을 생성하지 않는다."""
        base_dir = tmp_path / "tick_trace"
        tracer = TickTracer(base_dir=base_dir, enabled=False)
        await tracer.emit({"stock_code": "005930", "event_type": "skipped"})
        assert not any(base_dir.glob("*.jsonl"))


# ============================================================================
# Test 2: 날짜 롤오버
# ============================================================================

class TestTickTracerDayRollover:
    """test_tick_tracer_day_rollover — 자정 넘기면 파일 2개 생성."""

    @pytest.mark.asyncio
    async def test_tick_tracer_day_rollover(self, tmp_path):
        """
        datetime mock으로 두 날짜에 걸쳐 emit 시 JSONL 파일 2개 생성.
        """
        base_dir = tmp_path / "tick_trace"
        tracer = TickTracer(base_dir=base_dir)

        day1 = date(2026, 4, 12)
        day2 = date(2026, 4, 13)

        # day1 emit
        with patch("utils.tick_tracer.date") as mock_date:
            mock_date.today.return_value = day1
            await tracer.emit({"stock_code": "005930", "event_type": "evaluated"})

        # day2 emit
        with patch("utils.tick_tracer.date") as mock_date:
            mock_date.today.return_value = day2
            await tracer.emit({"stock_code": "005930", "event_type": "signal_generated"})

        file1 = base_dir / "2026-04-12.jsonl"
        file2 = base_dir / "2026-04-13.jsonl"
        assert file1.exists(), "day1 파일 없음"
        assert file2.exists(), "day2 파일 없음"

        lines1 = file1.read_text(encoding="utf-8").strip().splitlines()
        lines2 = file2.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines1) == 1
        assert len(lines2) == 1

        obj1 = json.loads(lines1[0])
        obj2 = json.loads(lines2[0])
        assert obj1["event_type"] == "evaluated"
        assert obj2["event_type"] == "signal_generated"


# ============================================================================
# Test 3: 동시성 100개 emit
# ============================================================================

class TestTickTracerConcurrentWrites:
    """test_tick_tracer_concurrent_writes — asyncio.gather 100개 동시 emit."""

    @pytest.mark.asyncio
    async def test_tick_tracer_concurrent_writes(self, tmp_path):
        """
        100개 코루틴 동시 emit → 행수 정확히 100, 각 줄 parseable.
        """
        base_dir = tmp_path / "tick_trace"
        tracer = TickTracer(base_dir=base_dir)

        events = [
            {"stock_code": f"{i:06d}", "event_type": "evaluated"}
            for i in range(100)
        ]

        await asyncio.gather(*(tracer.emit(e) for e in events))

        today_str = date.today().isoformat()
        out_file = base_dir / f"{today_str}.jsonl"
        assert out_file.exists()

        lines = out_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 100, f"행수 불일치: {len(lines)}"

        for line in lines:
            obj = json.loads(line)  # 파싱 가능해야 함
            assert "ts" in obj
            assert "stock_code" in obj
