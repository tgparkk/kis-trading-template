"""
analyze_tick_trace.py 분석 CLI 테스트
======================================

TDD: 테스트 먼저 작성, 구현 후 PASS 확인
"""

import json
import sys
from pathlib import Path

import pytest

# scripts/ 디렉터리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from analyze_tick_trace import analyze


# ============================================================================
# Test 1: 빈 파일
# ============================================================================

class TestAnalyzeEmptyFile:
    """test_analyze_empty_file — 빈 JSONL → 총 이벤트 0 출력."""

    def test_analyze_empty_file(self, tmp_path):
        """
        Given: 빈 JSONL 파일 (2026-04-13.jsonl)
        When: analyze(tmp_path, date="2026-04-13", top=10) 호출
        Then: 결과 문자열에 "총 이벤트: 0" 포함
        """
        jsonl_file = tmp_path / "2026-04-13.jsonl"
        jsonl_file.write_text("", encoding="utf-8")

        result = analyze(tmp_path, date="2026-04-13", top=10)

        assert "총 이벤트: 0" in result


# ============================================================================
# Test 2: 스킵 사유 순위
# ============================================================================

class TestAnalyzeSkipReasonsRanking:
    """test_analyze_skip_reasons_ranking — 스킵 사유 Top N 순위 확인."""

    def test_analyze_skip_reasons_ranking(self, tmp_path):
        """
        Given: 10줄 JSONL
               - 5x skipped / no_daily_data
               - 3x skipped / insufficient_data
               - 2x skipped / no_signal
        When: analyze() 호출
        Then:
          - 스킵 사유 3개 포함
          - 1위 = no_daily_data (5건)
        """
        jsonl_file = tmp_path / "2026-04-13.jsonl"

        events = (
            [{"event_type": "skipped", "skip_reason": "no_daily_data"}] * 5
            + [{"event_type": "skipped", "skip_reason": "insufficient_data"}] * 3
            + [{"event_type": "skipped", "skip_reason": "no_signal"}] * 2
        )
        lines = [json.dumps({"ts": "2026-04-13T09:00:00+09:00", **e}) for e in events]
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = analyze(tmp_path, date="2026-04-13", top=10)

        # 스킵 사유 3개 모두 포함
        assert "no_daily_data" in result
        assert "insufficient_data" in result
        assert "no_signal" in result

        # no_daily_data가 1위 (문자열에서 가장 먼저 등장)
        pos_first = result.index("no_daily_data")
        pos_second = result.index("insufficient_data")
        assert pos_first < pos_second, "no_daily_data가 1위여야 함"

        # 5건 숫자도 포함
        assert "5" in result


# ============================================================================
# Test 3: 신호 목록
# ============================================================================

class TestAnalyzeSignalList:
    """test_analyze_signal_list — 신호 이벤트 2건 → 신호 섹션에 2개 항목."""

    def test_analyze_signal_list(self, tmp_path):
        """
        Given: signal_generated 이벤트 2건 (005930 BUY, 000660 BUY)
        When: analyze() 호출
        Then: 결과에 005930, 000660 종목코드 모두 포함
        """
        jsonl_file = tmp_path / "2026-04-13.jsonl"

        events = [
            {
                "ts": "2026-04-13T09:15:23+09:00",
                "event_type": "signal_generated",
                "stock_code": "005930",
                "signal_type": "BUY",
                "confidence": 0.75,
            },
            {
                "ts": "2026-04-13T10:02:11+09:00",
                "event_type": "signal_generated",
                "stock_code": "000660",
                "signal_type": "BUY",
                "confidence": 0.82,
            },
        ]
        lines = [json.dumps(e) for e in events]
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = analyze(tmp_path, date="2026-04-13", top=10)

        assert "005930" in result
        assert "000660" in result
        # 신호 섹션 헤더 존재 확인
        assert "신호" in result


# ============================================================================
# Test 4: 파일 없음
# ============================================================================

class TestAnalyzeMissingFile:
    """test_analyze_missing_file — 존재하지 않는 날짜 → 에러 반환."""

    def test_analyze_missing_file(self, tmp_path):
        """
        Given: 존재하지 않는 날짜 (2099-01-01)
        When: analyze() 호출
        Then:
          - 결과에 "파일 없음" 또는 "없음" 메시지 포함
          - 예외 발생 없음 (graceful 에러)
        """
        result = analyze(tmp_path, date="2099-01-01", top=10)

        assert "없음" in result or "not found" in result.lower()
