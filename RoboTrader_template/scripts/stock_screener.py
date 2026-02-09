"""
모멘텀 스크리너 — N일 연속 종가 상승 종목 스캔

네이버금융 API를 사용하여 코스피+코스닥 전 종목을 스캔합니다.
2단계 접근:
  1단계: 네이버 모바일 API로 전 종목 당일 시세 (상승 종목만 필터)
  2단계: 상승 종목만 네이버 차트 API로 N일 일봉 조회 → 연속 상승 체크
"""
import logging
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ETF 이름 접두사 (스크리닝 제외)
ETF_PREFIXES = (
    "KODEX", "TIGER", "KBSTAR", "HANARO", "SOL ", "ARIRANG",
    "KOSEF", "ACE ", "PLUS ", "BNK ", "TIMEFOLIO", "WOORI",
)


class MomentumScreener:
    """N일 연속 종가 상승 종목을 찾는 스크리너"""

    def __init__(
        self,
        min_close: int = 1000,
        min_trading_amount: int = 100_000_000,  # 1억 (백만원 단위로 네이버에서 옴)
    ):
        self.min_close = min_close
        self.min_trading_amount = min_trading_amount

    def _fetch_all_stocks(self, market: str = "KOSPI") -> List[Dict]:
        """
        네이버 모바일 API로 전 종목 당일 시세 조회

        Returns: [{code, name, close, trading_amount, is_rising}]
        """
        market_name = market.upper()
        page = 1
        page_size = 100
        all_stocks = []

        while True:
            url = f"https://m.stock.naver.com/api/stocks/marketValue/{market_name}?page={page}&pageSize={page_size}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"{market_name} page {page} 조회 실패: {e}")
                break

            stocks = data.get("stocks", [])
            if not stocks:
                break

            for s in stocks:
                try:
                    close = int(s.get("closePrice", "0").replace(",", ""))
                    # accumulatedTradingValue는 백만원 단위
                    amount_raw = int(s.get("accumulatedTradingValue", "0").replace(",", ""))
                    amount = amount_raw * 1_000_000  # 원 단위로 변환
                    is_rising = s.get("compareToPreviousPrice", {}).get("name") == "RISING"

                    # 등락률 추출
                    change_rate = 0.0
                    try:
                        rate_str = s.get("fluctuationsRatio", "0").replace(",", "")
                        change_rate = float(rate_str)
                    except (ValueError, TypeError):
                        pass

                    all_stocks.append({
                        "code": s["itemCode"],
                        "name": s["stockName"],
                        "close": close,
                        "trading_amount": amount,
                        "is_rising": is_rising,
                        "change_rate": change_rate,
                    })
                except (ValueError, KeyError):
                    continue

            total = data.get("totalCount", 0)
            if page * page_size >= total:
                break
            page += 1
            time.sleep(0.1)  # rate limit

        logger.info(f"{market_name}: {len(all_stocks)}종목 조회")
        return all_stocks

    def _fetch_daily_closes(self, code: str, days: int = 10) -> List[Tuple[str, int]]:
        """
        네이버 모바일 API로 일봉 종가 조회 (빠름)

        Returns: [(date_str, close), ...] 과거→최신 순
        """
        url = f"https://m.stock.naver.com/api/stock/{code}/price?page=1&pageSize={days + 2}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            result = []
            for item in reversed(data):  # 최신→과거 순으로 오니까 reverse
                date_str = item["localTradedAt"].replace("-", "")
                close = int(item["closePrice"].replace(",", ""))
                result.append((date_str, close))
            return result[-days:]
        except Exception as e:
            logger.warning(f"{code} 일봉 조회 실패: {e}")
            return []

    def scan(
        self,
        date: Optional[str] = None,
        consecutive_days: int = 5,
    ) -> List[Dict]:
        """
        N일 연속 종가 상승 종목 스캔

        Args:
            date: 미사용 (네이버 API는 자동으로 최신일 기준)
            consecutive_days: 연속 상승 일수

        Returns:
            [{code, name, close, volume, trading_amount, consecutive_up_days}]
        """
        # 1단계: 전 종목 당일 시세 (KOSPI + KOSDAQ)
        all_stocks = []
        for market in ["KOSPI", "KOSDAQ"]:
            all_stocks.extend(self._fetch_all_stocks(market))

        logger.info(f"전체 {len(all_stocks)}종목 조회 완료")

        # 1차 필터: 종가, 거래대금, 당일 상승
        candidates = [
            s for s in all_stocks
            if s["close"] >= self.min_close
            and s["trading_amount"] >= self.min_trading_amount
            and s["is_rising"]
        ]
        logger.info(f"1차 필터 (종가≥{self.min_close}, 거래대금≥{self.min_trading_amount:,}, 당일상승): {len(candidates)}종목")

        # 2차 필터: ETF 제외 + 등락률 0.3% 미만 제거 (5일 연속 상승 가능성 낮음)
        candidates = [
            s for s in candidates
            if not any(s["name"].startswith(p) for p in ETF_PREFIXES)
            and s["change_rate"] >= 0.3
        ]
        logger.info(f"2차 필터 (ETF제외, 등락률≥0.3%): {len(candidates)}종목")

        # 3단계: 병렬로 일봉 데이터 조회하여 연속 상승 체크
        results = []

        def _check_consecutive(s: Dict) -> Optional[Dict]:
            closes_data = self._fetch_daily_closes(s["code"], days=consecutive_days + 2)
            if len(closes_data) < consecutive_days + 1:
                return None
            closes = [c for _, c in closes_data]
            up_days = 0
            for j in range(len(closes) - 1, 0, -1):
                if closes[j] > closes[j - 1]:
                    up_days += 1
                else:
                    break
            if up_days >= consecutive_days:
                return {
                    "code": s["code"],
                    "name": s["name"],
                    "close": s["close"],
                    "volume": 0,
                    "trading_amount": s["trading_amount"],
                    "consecutive_up_days": up_days,
                }
            return None

        max_workers = 10  # 동시 요청 수 제한
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check_consecutive, s): s for s in candidates}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                if done_count % 100 == 0:
                    logger.info(f"진행: {done_count}/{len(candidates)}...")
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    s = futures[future]
                    logger.warning(f"{s['code']} 체크 실패: {e}")

        # 거래대금 내림차순 정렬
        results.sort(key=lambda x: x["trading_amount"], reverse=True)
        logger.info(f"스캔 완료: {len(results)}종목 발견 (후보 {len(candidates)}종목 중)")
        return results

    def format_telegram_message(self, results: List[Dict], date: str, consecutive_days: int = 5) -> str:
        """텔레그램 알림 메시지 포맷"""
        display_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        lines = [
            f"📊 모멘텀 {consecutive_days}일 연속상승 매수후보 ({display_date})",
            "",
        ]

        if not results:
            lines.append("❌ 조건에 맞는 종목이 없습니다.")
        else:
            lines.append(f"🔥 총 {len(results)}종목 발견")
            lines.append("")
            for i, r in enumerate(results[:30], 1):  # 최대 30종목
                amount_str = self._format_amount(r["trading_amount"])
                lines.append(
                    f"{i}. {r['name']} ({r['code']}) — "
                    f"종가 {r['close']:,}원, 거래대금 {amount_str}"
                )
            if len(results) > 30:
                lines.append(f"... 외 {len(results) - 30}종목")

        lines.append("")
        lines.append(f"⚙️ 조건: {consecutive_days}일 연속 종가↑ + 거래대금 1억↑")
        lines.append("💡 전략: 익일 시가 매수 → TP +10% / SL -5% / 10일 보유")
        return "\n".join(lines)

    @staticmethod
    def _format_amount(amount: int) -> str:
        """거래대금 포맷 (억 단위)"""
        billions = amount / 100_000_000
        if billions >= 10000:
            return f"{billions / 10000:.1f}조"
        elif billions >= 1:
            return f"{billions:,.0f}억"
        else:
            return f"{amount:,}원"
