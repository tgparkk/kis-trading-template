"""KOSPI 분봉 데이터 소스 1회성 점검."""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from db.connection import DatabaseConnection


CANDIDATES = ["0001", "KS11", "KOSPI", "001", "U001", "069500"]


def main() -> None:
    with DatabaseConnection.get_connection() as conn:
        cursor = conn.cursor()
        for code in CANDIDATES:
            cursor.execute(
                "SELECT COUNT(*), MIN(datetime), MAX(datetime) "
                "FROM minute_candles WHERE stock_code = %s",
                (code,),
            )
            cnt, dt_min, dt_max = cursor.fetchone()
            print(f"  code={code!s:8s}  rows={cnt:>10,}  range={dt_min} .. {dt_max}")

        cursor.execute(
            "SELECT DISTINCT stock_code FROM minute_candles "
            "WHERE stock_code IN ('0001','KS11','KOSPI','001','U001','069500')"
        )
        present = [r[0] for r in cursor.fetchall()]
        print(f"\nFound in minute_candles: {present}")

        if not present:
            print("\n[FALLBACK] 후보 6개 모두 0건. 추가 탐색...")
            cursor.execute(
                "SELECT DISTINCT stock_code FROM minute_candles "
                "WHERE stock_code LIKE '%KS%' OR stock_code LIKE '%KOSPI%' "
                "OR stock_code LIKE '%kospi%' OR stock_code LIKE '%index%' "
                "LIMIT 20"
            )
            fallback = [r[0] for r in cursor.fetchall()]
            print(f"  유사 코드 탐색 결과: {fallback}")

        cursor.close()


if __name__ == "__main__":
    main()
