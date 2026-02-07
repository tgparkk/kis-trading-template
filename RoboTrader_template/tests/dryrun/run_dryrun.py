"""
드라이런 실행 스크립트

실행:
    cd RoboTrader_template
    python tests/dryrun/run_dryrun.py
"""
import sys
import asyncio
from pathlib import Path

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.dryrun.dry_run_bot import DryRunBot


async def main():
    print("RoboTrader 드라이런 모드")
    print("주문은 실행되지 않으며, 전체 흐름만 시뮬레이션합니다.\n")

    bot = DryRunBot()
    success = await bot.run()

    if success:
        print("드라이런 완료.")
    else:
        print("드라이런 실패.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
