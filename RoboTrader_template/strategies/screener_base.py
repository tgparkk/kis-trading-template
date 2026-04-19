"""
ScreenerBase ABC — 스크리너 스냅샷 파이프라인의 공통 인터페이스.
모든 스크리너는 이 클래스를 상속하고 scan() 을 구현한다.
"""
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List

# 기존 CandidateStock 재활용 (재정의 금지)
from core.candidate_selector import CandidateStock


class ScreenerBase(ABC):
    """스크리너 공통 ABC. 서브클래스는 strategy_name 과 scan() 을 반드시 정의."""

    strategy_name: str  # 서브클래스가 클래스 변수로 설정

    @abstractmethod
    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        """주어진 날짜·파라미터로 후보 종목 리스트 반환."""

    @staticmethod
    def compute_params_hash(params: Dict[str, Any]) -> str:
        """키 정렬 후 SHA1 — 같은 파라미터는 항상 같은 해시를 보장."""
        serialized = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(serialized.encode()).hexdigest()[:40]

    def default_params(self) -> Dict[str, Any]:
        """기본 파라미터 반환. 서브클래스가 오버라이드."""
        return {}
