"""
분봉 데이터 Parquet 디스크 캐시 + LRU 메모리 캐시.

디스크 경로: cache/minute/{trade_date}/{stock_code}.parquet
빈 DataFrame은 캐시 저장 X (miss로 유지).
"""
from collections import OrderedDict
from pathlib import Path

import pandas as pd

from utils.logger import setup_logger

logger = setup_logger(__name__)


class MinuteCache:
    """분봉 데이터 Parquet 디스크 캐시 + LRU 메모리 캐시."""

    def __init__(self, root_dir: Path, mem_limit_mb: int = 200):
        """
        Args:
            root_dir: Parquet 파일 저장 루트 디렉토리
            mem_limit_mb: 메모리 캐시 상한 (MB)
        """
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.mem_limit_bytes = mem_limit_mb * 1024 * 1024
        self._mem: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
        self._mem_bytes = 0
        self._stats = {"hit_mem": 0, "hit_disk": 0, "miss": 0, "evict": 0}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, stock_code: str, trade_date: str) -> "pd.DataFrame | None":
        """캐시에서 분봉 데이터 조회.

        조회 순서: 메모리 → 디스크 → None(miss).

        Args:
            stock_code: 종목코드
            trade_date: 거래일 (YYYYMMDD 또는 YYYY-MM-DD)

        Returns:
            DataFrame 또는 None (miss)
        """
        trade_date = self._normalize_date(trade_date)
        key = (stock_code, trade_date)

        # 1) 메모리 hit
        if key in self._mem:
            self._mem.move_to_end(key)
            self._stats["hit_mem"] += 1
            return self._mem[key]

        # 2) 디스크 hit
        parquet_path = self._parquet_path(stock_code, trade_date)
        if parquet_path.exists():
            try:
                df = pd.read_parquet(parquet_path)
                self._put_mem(key, df)
                self._stats["hit_disk"] += 1
                return df
            except Exception as e:
                logger.warning(f"Parquet 읽기 실패 ({parquet_path}): {e}")

        # 3) miss
        self._stats["miss"] += 1
        return None

    def put(self, stock_code: str, trade_date: str, df: pd.DataFrame) -> None:
        """분봉 데이터를 디스크(Parquet) + 메모리에 저장.

        빈 DataFrame은 저장하지 않음.

        Args:
            stock_code: 종목코드
            trade_date: 거래일 (YYYYMMDD 또는 YYYY-MM-DD)
            df: 분봉 DataFrame
        """
        if df is None or df.empty:
            return

        trade_date = self._normalize_date(trade_date)
        key = (stock_code, trade_date)

        # 디스크 저장
        parquet_path = self._parquet_path(stock_code, trade_date)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception as e:
            logger.warning(f"Parquet 저장 실패 ({parquet_path}): {e}")

        # 메모리 LRU 추가
        self._put_mem(key, df)

    def stats(self) -> dict:
        """캐시 통계 반환."""
        return dict(self._stats)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _put_mem(self, key: tuple, df: pd.DataFrame) -> None:
        """메모리 LRU에 추가 (초과 시 가장 오래된 항목 evict)."""
        size = int(df.memory_usage(deep=True).sum())

        # 이미 존재하면 기존 크기 차감
        if key in self._mem:
            old = self._mem.pop(key)
            self._mem_bytes -= int(old.memory_usage(deep=True).sum())

        # 상한 초과 시 LRU 항목 evict
        while self._mem_bytes + size > self.mem_limit_bytes and self._mem:
            _, evicted = self._mem.popitem(last=False)
            self._mem_bytes -= int(evicted.memory_usage(deep=True).sum())
            self._stats["evict"] += 1

        self._mem[key] = df
        self._mem.move_to_end(key)
        self._mem_bytes += size

    def _parquet_path(self, stock_code: str, trade_date: str) -> Path:
        """Parquet 파일 경로: root_dir/cache/minute/{trade_date}/{stock_code}.parquet"""
        return self.root_dir / trade_date / f"{stock_code}.parquet"

    @staticmethod
    def _normalize_date(trade_date: str) -> str:
        """YYYYMMDD → YYYY-MM-DD 정규화."""
        if len(trade_date) == 8 and trade_date.isdigit():
            return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        return trade_date
