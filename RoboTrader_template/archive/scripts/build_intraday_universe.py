"""
분봉 데이트레이딩 universe 사전 빌드 스크립트.

사용 예:
    python scripts/build_intraday_universe.py \\
        --start 20250901 --end 20260515 \\
        --out RoboTrader_template/cache/intraday_universe

    # 특정 월 제외:
    python scripts/build_intraday_universe.py \\
        --start 20250901 --end 20260515 --skip 202603 \\
        --out cache/intraday_universe
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 하위에서 직접 실행 지원)
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.intraday_universe import build_universe_range


def main() -> None:
    parser = argparse.ArgumentParser(
        description="분봉 데이트레이딩 universe 사전 빌드"
    )
    parser.add_argument('--start', required=True, help='시작 거래일 YYYYMMDD')
    parser.add_argument('--end', required=True, help='종료 거래일 YYYYMMDD')
    parser.add_argument(
        '--skip', nargs='*', default=[],
        help='제외할 일자 또는 prefix (예: 202603 20260315)'
    )
    parser.add_argument(
        '--out', default='cache/intraday_universe',
        help='캐시 저장 디렉토리 (기본: cache/intraday_universe)'
    )
    parser.add_argument(
        '--min-amount', type=float, default=10_000_000_000,
        help='최소 일별 거래대금 (원, 기본 100억)'
    )
    parser.add_argument(
        '--min-vol-pct', type=float, default=0.03,
        help='최소 변동성 비율 (기본 0.03 = 3%%)'
    )
    parser.add_argument(
        '--min-price', type=float, default=5_000.0,
        help='최소 종가 (원, 기본 5,000원)'
    )
    args = parser.parse_args()

    skip: set[str] = set(args.skip)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    result = build_universe_range(
        args.start,
        args.end,
        skip_dates=skip,
        min_amount=args.min_amount,
        min_volatility_pct=args.min_vol_pct,
        min_price=args.min_price,
        cache_dir=out,
    )

    total_slots = sum(len(v) for v in result.values())
    days = len(result)
    avg = total_slots / max(days, 1)
    print(
        f"Built universe: {days} dates, {total_slots} total slots, "
        f"avg {avg:.1f} codes/day"
    )

    # 일자별 카운트 상위 5
    sorted_dates = sorted(result.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    for d, codes in sorted_dates:
        print(f"  {d}: {len(codes)} codes")


if __name__ == '__main__':
    main()
