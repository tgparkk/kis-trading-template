"""
시스템 헬스체크 스크립트
운영 전 필수 점검 항목을 자동 검증합니다.
pytest 없이 독립 실행 가능.

실행:
    cd RoboTrader_template
    python tests/healthcheck/run_healthcheck.py
"""
import sys
import os
import time
import importlib
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class HealthChecker:
    """헬스체크 실행기"""

    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    def _check(self, name: str, func):
        """개별 체크 실행"""
        start = time.time()
        try:
            result = func()
            elapsed = (time.time() - start) * 1000
            if result is True or (isinstance(result, str) and result):
                self.results.append(('PASS', name, f"OK ({elapsed:.0f}ms)" if isinstance(result, bool) else result))
                self.passed += 1
            else:
                self.results.append(('FAIL', name, str(result)))
                self.failed += 1
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            self.results.append(('FAIL', name, str(e)))
            self.failed += 1

    def run_all(self):
        """전체 헬스체크 실행"""
        print("=" * 60)
        print("  RoboTrader 시스템 헬스체크")
        print("=" * 60)
        print()

        self._check("DB 연결", self._check_db_connection)
        self._check("TimescaleDB 확장", self._check_timescaledb)
        self._check("필수 테이블", self._check_tables)
        self._check("Hypertable 설정", self._check_hypertables)
        self._check("API 인증", self._check_api_auth)
        self._check("현재가 조회 (삼성전자)", self._check_current_price)
        self._check("계좌잔고 조회", self._check_account_balance)
        self._check("설정 파일", self._check_config)
        self._check("로그 디렉토리", self._check_log_dir)
        self._check("핵심 패키지", self._check_packages)

        self._print_results()

    def _check_db_connection(self):
        """DB 연결 테스트"""
        from db.connection import DatabaseConnection
        DatabaseConnection.initialize()
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                if result and result[0] == 1:
                    return True
        return "SELECT 1 실패"

    def _check_timescaledb(self):
        """TimescaleDB 확장 확인"""
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname='timescaledb'")
                result = cur.fetchone()
                if result:
                    return f"v{result[1]}"
                return False

    def _check_tables(self):
        """필수 테이블 존재 확인"""
        required_tables = [
            'daily_prices', 'minute_prices', 'candidate_stocks',
            'virtual_trading_records', 'real_trading_records',
            'financial_data', 'quant_factors', 'quant_portfolio'
        ]
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                existing = {row[0] for row in cur.fetchall()}

        missing = [t for t in required_tables if t not in existing]
        if missing:
            return f"누락: {', '.join(missing)}"
        return f"{len(required_tables)}개 확인"

    def _check_hypertables(self):
        """Hypertable 설정 확인"""
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT hypertable_name FROM timescaledb_information.hypertables
                    WHERE hypertable_schema = 'public'
                """)
                hypertables = [row[0] for row in cur.fetchall()]

        expected = ['daily_prices', 'minute_prices']
        found = [h for h in expected if h in hypertables]
        if len(found) == len(expected):
            return f"{', '.join(found)}"
        missing = [h for h in expected if h not in hypertables]
        return f"누락: {', '.join(missing)}"

    def _check_api_auth(self):
        """Broker 연결 테스트"""
        import asyncio
        from framework import KISBroker
        broker = KISBroker()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(broker.connect())
            if result:
                self._broker = broker
                return True
            return "Broker 연결 실패"
        finally:
            loop.close()

    def _check_current_price(self):
        """현재가 조회 테스트"""
        broker = getattr(self, '_broker', None)
        if broker is None:
            return "Broker 미연결"
        price = broker.get_current_price("005930")
        if price is not None:
            return f"{price:,.0f}원"
        return "조회 실패"

    def _check_account_balance(self):
        """계좌 잔고 조회"""
        broker = getattr(self, '_broker', None)
        if broker is None:
            return "Broker 미연결"
        balance = broker.get_account_balance()
        if balance:
            return f"{balance.get('total_balance', 0):,.0f}원"
        return "조회 실패"

    def _check_config(self):
        """설정 파일 확인"""
        from utils.price_utils import load_config
        config = load_config()
        if config:
            return True
        return "설정 로드 실패"

    def _check_log_dir(self):
        """로그 디렉토리 확인"""
        log_dir = PROJECT_ROOT / "logs"
        if log_dir.exists() and log_dir.is_dir():
            # 쓰기 가능 여부
            test_file = log_dir / ".healthcheck_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
                return True
            except Exception:
                return "쓰기 불가"
        else:
            try:
                log_dir.mkdir(exist_ok=True)
                return "생성됨"
            except Exception:
                return "디렉토리 생성 실패"

    def _check_packages(self):
        """핵심 패키지 import 확인"""
        packages = ['psycopg2', 'pandas', 'numpy', 'telegram']
        missing = []
        for pkg in packages:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing.append(pkg)

        if missing:
            return f"미설치: {', '.join(missing)}"
        return f"{len(packages)}개 확인"

    def _print_results(self):
        """결과 출력"""
        print()
        max_name_len = max(len(r[1]) for r in self.results)

        for status, name, detail in self.results:
            icon = "[PASS]" if status == "PASS" else "[FAIL]"
            dots = "." * (max_name_len - len(name) + 3)
            print(f"  {icon} {name} {dots} {detail}")

        print()
        print("-" * 60)
        total = self.passed + self.failed
        print(f"  결과: {self.passed}/{total} 통과", end="")
        if self.failed > 0:
            print(f", {self.failed} 실패")
        else:
            print(" - 모두 정상!")
        print()


def main():
    checker = HealthChecker()
    checker.run_all()
    sys.exit(1 if checker.failed > 0 else 0)


if __name__ == "__main__":
    main()
