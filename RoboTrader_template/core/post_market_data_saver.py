"""
장 마감 후 데이터 저장 전담 모듈
- 텍스트 파일 저장 (디버깅용)

🔴 `save_daily_data()`(선정 종목 × 최근 100봉을 **수정주가**로 daily_prices 에 UPSERT,
   사전등록의 `W4`)는 2026-09-03 제거됐다. 로그 전수에서 발화 0건인 죽은 경로였는데,
   규약이 W1·W2(원주가)와 **반대**라 되살아나면 한 종목 시계열 안에 두 규약이 섞이고
   (E′) 가드도 안 걸린다 — 사전등록
   docs/prereg_2026-09-03_write_path_rawprice_upsert.md D-3 · §1-5 · §4-4-2.
   ⚠️ 사전등록 §6-18 의 「호출자 없음」은 **직접 호출자**(realtime_updater.py:405)가
   실존해 부정확했으나, 그 사슬의 **머리** `batch_update_realtime_data` 는 프로덕션
   호출자 0건이라(유일 진입점 intraday_stock_manager.py:205 도 미호출 —
   bot/system_monitor.py:386-390 에 독립 기록) 경로는 «이중으로» 죽어 있었다.
   ⇒ 반대 규약의 「죽었지만 배선된」 경로이므로 제거가 맞다. 지운 것은 클래스가 아니라
   «DB 쓰기 경로»이고 분봉 텍스트 덤프는 그대로다. 일봉을 다시 저장해야 하면 규약을
   먼저 정하고 별도 승인으로 설계할 것.
"""
from typing import Dict, Optional

from utils.logger import setup_logger
from utils.korean_time import now_kst


class PostMarketDataSaver:
    """장 마감 후 데이터 저장 클래스 (분봉 텍스트 덤프 전용)"""

    def __init__(self) -> None:
        """초기화"""
        self.logger = setup_logger(__name__)

        self.logger.info("장 마감 후 데이터 저장기 초기화 완료")

    def save_minute_data_to_file(self, intraday_manager) -> Optional[str]:
        """
        메모리에 있는 모든 종목의 분봉 데이터를 텍스트 파일로 저장 (디버깅용)

        Args:
            intraday_manager: IntradayStockManager 인스턴스

        Returns:
            str: 저장된 파일명 또는 None
        """
        try:
            current_time = now_kst()
            filename = f"memory_minute_data_{current_time.strftime('%Y%m%d_%H%M%S')}.txt"

            with intraday_manager._lock:
                stock_codes = list(intraday_manager.selected_stocks.keys())

            if not stock_codes:
                self.logger.info("📝 텍스트 저장할 종목 없음")
                return None

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"=== 장 마감 후 분봉 데이터 덤프 ===\n")
                f.write(f"저장 시간: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"종목 수: {len(stock_codes)}\n")
                f.write("=" * 80 + "\n\n")

                for stock_code in stock_codes:
                    try:
                        combined_data = intraday_manager.get_combined_chart_data(stock_code)

                        if combined_data is None or combined_data.empty:
                            f.write(f"[{stock_code}] 데이터 없음\n\n")
                            continue

                        f.write(f"[{stock_code}] 분봉 데이터: {len(combined_data)}건\n")
                        f.write("-" * 80 + "\n")
                        f.write(combined_data.to_string())
                        f.write("\n\n")

                    except Exception as e:
                        f.write(f"[{stock_code}] 오류: {e}\n\n")

            self.logger.info(f"✅ 분봉 데이터 텍스트 파일 저장 완료: {filename}")
            return filename

        except Exception as e:
            self.logger.error(f"❌ 분봉 데이터 텍스트 파일 저장 실패: {e}")
            return None

    def save_all_data(self, intraday_manager) -> Dict[str, any]:
        """
        장 마감 후 데이터 저장 (분봉 → 텍스트 파일)

        🔴 일봉 DB 저장 단계(`W4`)는 제거됐다 — 모듈 docstring 참조(사전등록 D-3).
           일봉은 EOD 수집기(`collectors/eod_collection.py`, `W2`)가 전 종목으로 쓴다.

        Args:
            intraday_manager: IntradayStockManager 인스턴스

        Returns:
            Dict: 전체 저장 결과
        """
        try:
            self.logger.info("장 마감 후 데이터 저장 시작 (분봉 텍스트 덤프)")

            # 종목 목록 가져오기
            with intraday_manager._lock:
                stock_codes = list(intraday_manager.selected_stocks.keys())

            if not stock_codes:
                self.logger.warning("저장할 종목이 없습니다")
                return {
                    'success': False,
                    'message': '저장할 종목 없음',
                    'text_file': None
                }

            self.logger.info(f"대상 종목: {len(stock_codes)}개 - {', '.join(stock_codes)}")

            # 분봉 데이터 텍스트 파일 저장 (디버깅용, 선택적)
            text_file = self.save_minute_data_to_file(intraday_manager)

            # 결과 요약
            self.logger.info(f"장 마감 후 데이터 저장 완료 - 텍스트: {text_file if text_file else '없음'}")

            return {
                'success': True,
                'text_file': text_file
            }

        except Exception as e:
            self.logger.error(f"장 마감 후 데이터 저장 중 오류: {e}")
            return {
                'success': False,
                'error': str(e),
                'text_file': None
            }


# 독립 실행용 (테스트)
if __name__ == "__main__":
    import logging
    logging.getLogger(__name__).info("이 모듈은 직접 실행할 수 없습니다. main.py 또는 intraday_stock_manager.py에서 호출하여 사용하세요.")
