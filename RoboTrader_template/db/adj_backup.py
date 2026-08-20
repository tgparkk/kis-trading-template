# db/adj_backup.py
"""기업행위 가격 보정 전 원본 스냅샷. **백업 없이는 한 행도 고치지 않는다.**"""

DDL_SQL = """
CREATE TABLE IF NOT EXISTS daily_prices_preadj_backup (
    batch_id     text        NOT NULL,
    stock_code   text        NOT NULL,
    date         text        NOT NULL,
    open         double precision,
    high         double precision,
    low          double precision,
    close        double precision,
    volume       bigint,
    adj_factor   double precision,
    backed_up_at timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, stock_code, date)
)
"""

BACKUP_SQL = """
INSERT INTO daily_prices_preadj_backup
    (batch_id, stock_code, date, open, high, low, close, volume, adj_factor)
SELECT %(batch_id)s, stock_code, date, open, high, low, close, volume, adj_factor
FROM daily_prices
WHERE stock_code = %(code)s AND date = ANY(%(dates)s)
ON CONFLICT DO NOTHING
"""

RESTORE_SQL = """
UPDATE daily_prices dp SET
    open = b.open, high = b.high, low = b.low, close = b.close,
    volume = b.volume, adj_factor = b.adj_factor, updated_at = now()
FROM daily_prices_preadj_backup b
WHERE b.batch_id = %(batch_id)s
  AND dp.stock_code = b.stock_code AND dp.date = b.date
"""


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL_SQL)
    conn.commit()


def backup_rows(conn, code: str, dates: list, batch_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(BACKUP_SQL, dict(batch_id=batch_id, code=code, dates=dates))
        n = cur.rowcount
    conn.commit()
    return n


def restore_batch(conn, batch_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(RESTORE_SQL, dict(batch_id=batch_id))
        n = cur.rowcount
    conn.commit()
    return n
