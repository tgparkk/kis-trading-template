"""
스크리너 → CandidateSelector → 전략 파이프라인 테스트
"""
import json
import sys
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_load_from_screener():
    """CandidateSelector.load_from_screener() 테스트"""
    from core.candidate_selector import CandidateSelector, CandidateStock
    from core.models import TradingConfig

    config = TradingConfig()
    selector = CandidateSelector(config, broker=None, db_manager=None)

    screener_path = Path(__file__).parent.parent / "data" / "screener_20260209.json"
    if not screener_path.exists():
        print(f"SKIP: {screener_path} 없음")
        return

    candidates = selector.load_from_screener(str(screener_path), max_candidates=10)

    assert len(candidates) > 0, "후보가 0개"
    assert len(candidates) <= 10, f"후보가 {len(candidates)}개 (max=10)"

    # ETF 필터 확인
    for c in candidates:
        name_upper = c.name.upper()
        assert not any(kw in name_upper for kw in ['KODEX', 'TIGER', 'KBSTAR', 'ETF', 'ETN']), \
            f"ETF가 포함됨: {c.name}"

    # 필수 필드
    for c in candidates:
        assert c.code, "code 비어있음"
        assert c.name, "name 비어있음"
        assert c.score > 0, f"score={c.score}"
        assert c.prev_close > 0, f"prev_close={c.prev_close}"

    print(f"✅ load_from_screener: {len(candidates)}개 후보")
    for c in candidates:
        print(f"   {c.code} {c.name} score={c.score} close={c.prev_close:,.0f}")


def test_auto_resolve_latest_screener():
    """최신 스크리너 파일 자동 탐색 테스트"""
    from core.candidate_selector import CandidateSelector
    from core.models import TradingConfig

    config = TradingConfig()
    selector = CandidateSelector(config, broker=None, db_manager=None)

    # json_path=None → 자동 탐색
    candidates = selector.load_from_screener(max_candidates=5)
    # 파일이 있으면 결과가 있어야 함
    screener_files = list(selector.screener_data_dir.glob("screener_*.json"))
    if screener_files:
        assert len(candidates) > 0, "스크리너 파일 존재하지만 후보 0개"
        print(f"✅ 자동 탐색: {len(candidates)}개 후보")
    else:
        print("SKIP: 스크리너 파일 없음")


def test_etf_filter_comprehensive():
    """ETF 필터가 다양한 브랜드를 걸러내는지"""
    from core.candidate_selector import CandidateSelector
    from core.models import TradingConfig

    selector = CandidateSelector(TradingConfig(), broker=None)

    etf_names = [
        "KODEX CD금리액티브(합성)", "TIGER 미국S&P500", "KBSTAR 200",
        "ACE 미국나스닥100", "SOL 미국배당다우존스", "ARIRANG 고배당주",
        "HANARO Fn K-POP&미디어", "삼성 ETF",
    ]
    for name in etf_names:
        assert selector._is_etf_or_etn_screener(name), f"ETF 미감지: {name}"

    normal_names = ["셀트리온", "삼성전자", "카카오", "HD현대에너지솔루션"]
    for name in normal_names:
        assert not selector._is_etf_or_etn_screener(name), f"일반종목 오감지: {name}"

    print("✅ ETF 필터 테스트 통과")


if __name__ == "__main__":
    test_etf_filter_comprehensive()
    test_load_from_screener()
    test_auto_resolve_latest_screener()
    print("\n🎉 모든 테스트 통과!")
