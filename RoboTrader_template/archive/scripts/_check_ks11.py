import sys
sys.path.insert(0, '.')
from db.connection import DatabaseConnection
with DatabaseConnection.get_connection() as conn:
    cur = conn.cursor()
    # 컬럼명 확인
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='daily_candles' ORDER BY ordinal_position")
    cols = [r[0] for r in cur.fetchall()]
    print("columns:", cols)
    # KS11 행 수 확인
    cur.execute("SELECT COUNT(1) FROM daily_candles WHERE stock_code = 'KS11'")
    print("KS11 count:", cur.fetchone()[0])
