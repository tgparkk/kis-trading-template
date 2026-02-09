#!/usr/bin/env python3
"""
모멘텀 스크리너 실행 스크립트

Usage:
    python scripts/run_screener.py
    python scripts/run_screener.py --days 5 --min-amount 100000000
    python scripts/run_screener.py --date 20260209 --no-telegram
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

# 프로젝트 루트를 path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from scripts.stock_screener import MomentumScreener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def send_telegram(message: str) -> bool:
    """텔레그램 메시지 전송 (프로젝트의 기존 텔레그램 설정 사용)"""
    try:
        from config.settings import load_config
        config = load_config()
        bot_token = config.get("telegram", {}).get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = config.get("telegram", {}).get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            logger.warning("텔레그램 설정 없음 (bot_token/chat_id)")
            return False

        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        resp.raise_for_status()
        logger.info("텔레그램 전송 성공")
        return True
    except Exception as e:
        logger.error(f"텔레그램 전송 실패: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="모멘텀 스크리너 — N일 연속 종가 상승 종목 스캔")
    parser.add_argument("--days", type=int, default=5, help="연속 상승 일수 (기본: 5)")
    parser.add_argument("--min-amount", type=int, default=100_000_000, help="최소 거래대금 (기본: 1억)")
    parser.add_argument("--min-close", type=int, default=1000, help="최소 종가 (기본: 1000원)")
    parser.add_argument("--date", type=str, default=None, help="기준일 YYYYMMDD (기본: 오늘)")
    parser.add_argument("--no-telegram", action="store_true", help="텔레그램 전송 안 함")
    parser.add_argument("--output", type=str, default=None, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    date = args.date or datetime.now().strftime("%Y%m%d")
    logger.info(f"모멘텀 스크리너 시작 — 기준일: {date}, 연속 {args.days}일")

    screener = MomentumScreener(
        min_close=args.min_close,
        min_trading_amount=args.min_amount,
    )

    results = screener.scan(date=date, consecutive_days=args.days)

    # 콘솔 출력
    msg = screener.format_telegram_message(results, date, args.days)
    print()
    print(msg)
    print()

    # JSON 저장
    output_path = args.output or os.path.join(project_root, "data", f"screener_{date}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": date,
            "consecutive_days": args.days,
            "min_trading_amount": args.min_amount,
            "min_close": args.min_close,
            "count": len(results),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"결과 저장: {output_path}")

    # 텔레그램 전송
    if not args.no_telegram:
        send_telegram(msg)

    return results


if __name__ == "__main__":
    main()
