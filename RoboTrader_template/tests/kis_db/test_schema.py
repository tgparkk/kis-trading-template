from scripts.kis_db.schema import DDL_STATEMENTS, EXPECTED_TABLES


def test_expected_tables_present():
    assert EXPECTED_TABLES == {
        "minute_candles", "daily_prices", "index_daily",
        "corp_events", "collection_reconciliation", "foreign_flow",
        "virtual_trading_records", "real_trading_records",
        "paper_trading_state",
        "candidate_stocks", "screener_snapshots",
        "paper_strategy_equity",
    }


def test_foreign_flow_ddl_matches_legacy():
    # 레거시 robotrader_quant.foreign_flow 동일: PK(stock_code,date), date DATE, BIGINT
    ff = [s for s in DDL_STATEMENTS if "create table if not exists foreign_flow" in s.lower()][0].lower()
    assert "foreign_net_vol bigint" in ff
    assert "date date not null" in ff
    assert "primary key (stock_code, date)" in ff
    joined = "\n".join(DDL_STATEMENTS).lower()
    assert "ix_foreign_flow_date" in joined


def test_every_expected_table_has_ddl():
    joined = "\n".join(DDL_STATEMENTS).lower()
    for t in EXPECTED_TABLES:
        assert f"create table if not exists {t}" in joined, f"DDL 누락: {t}"


def test_daily_prices_date_is_text_not_date():
    # 레거시 동일: date 는 TEXT(YYYY-MM-DD)
    dp = [s for s in DDL_STATEMENTS if "daily_prices" in s.lower()][0].lower()
    assert "date text" in dp


def test_minute_candles_pk_matches_legacy():
    mc = [s for s in DDL_STATEMENTS if "minute_candles" in s.lower()][0].lower()
    assert "primary key (stock_code, trade_date, idx)" in mc


def test_virtual_trading_records_has_source_and_tpsl_columns():
    vtr = [s for s in DDL_STATEMENTS
           if "create table if not exists virtual_trading_records" in s.lower()][0].lower()
    assert "source varchar(50)" in vtr
    assert "target_profit_rate numeric(10, 6)" in vtr
    assert "stop_loss_rate numeric(10, 6)" in vtr
    assert "buy_record_id integer references virtual_trading_records(id)" in vtr
    assert "is_test boolean default true" in vtr
    joined = "\n".join(DDL_STATEMENTS).lower()
    # 중복 매도 방지 partial unique index (init-scripts/01-init.sql)
    assert "idx_virtual_trading_unique_sell" in joined
    assert "idx_virtual_trading_source" in joined


def test_real_trading_records_is_like_template_base():
    # 동적 real_trading_{instance} 는 CREATE TABLE ... (LIKE real_trading_records INCLUDING ALL)
    # 로 만들어지므로 base 테이블이 반드시 스키마에 존재해야 한다.
    rtr = [s for s in DDL_STATEMENTS
           if "create table if not exists real_trading_records" in s.lower()][0].lower()
    assert "buy_record_id integer references real_trading_records(id)" in rtr
    assert "id serial primary key" in rtr


def test_virtual_trading_records_has_is_overflow_column():
    # 드리프트 가드: 라이브 robotrader.virtual_trading_records 에 있는
    # is_overflow BOOLEAN (created_at 뒤, source 앞) 이 kis_template DDL 에 누락됐던 회귀 방지.
    vtr = [s for s in DDL_STATEMENTS
           if "create table if not exists virtual_trading_records" in s.lower()][0].lower()
    assert "is_overflow boolean" in vtr


def test_real_trading_records_strategy_is_text_and_has_fee_net_profit_columns():
    # 드리프트 가드: 라이브 robotrader.real_trading_records 는 strategy TEXT(51자 도달 확인됨,
    # varchar(50) 이면 StringDataRightTruncation) + fee_amount/net_profit/net_profit_rate
    # DOUBLE PRECISION 3컬럼(created_at 뒤)이 kis_template DDL 에 누락됐던 회귀 방지.
    rtr = [s for s in DDL_STATEMENTS
           if "create table if not exists real_trading_records" in s.lower()][0].lower()
    assert "strategy text" in rtr
    assert "strategy varchar(50)" not in rtr
    assert "fee_amount double precision" in rtr
    assert "net_profit double precision" in rtr
    assert "net_profit_rate double precision" in rtr


def test_paper_trading_state_and_candidate_and_screener_present():
    joined = "\n".join(DDL_STATEMENTS).lower()
    assert "create table if not exists paper_trading_state" in joined
    assert "trade_date  date primary key" in joined or "trade_date date primary key" in joined
    assert "create table if not exists candidate_stocks" in joined
    assert "create table if not exists screener_snapshots" in joined
    assert "params_json jsonb not null" in joined
    assert "unique (strategy, scan_date, params_hash, stock_code)" in joined


def test_paper_strategy_equity_ddl_is_shared_between_schema_and_tool():
    from scripts.kis_db.schema import PAPER_STRATEGY_EQUITY_DDL
    ddl = PAPER_STRATEGY_EQUITY_DDL.lower()
    assert "create table if not exists paper_strategy_equity" in ddl
    assert "primary key (trade_date, strategy, source)" in ddl
    assert "source varchar(50) not null default 'kis_template'" in ddl
    # schema.DDL_STATEMENTS 에도 포함(create_all 이 생성)
    joined = "\n".join(DDL_STATEMENTS).lower()
    assert "create table if not exists paper_strategy_equity" in joined
    # tools 의 _ensure_table 가 동일 상수를 실행하는지 (드리프트 방지)
    import tools.paper_strategy_equity as pse

    class _Cur:
        def __init__(self): self.sql = None
        def execute(self, sql): self.sql = sql
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def __init__(self): self.cur = _Cur()
        def cursor(self): return self.cur
        def commit(self): pass

    c = _Conn()
    pse._ensure_table(c)
    assert c.cur.sql.strip() == PAPER_STRATEGY_EQUITY_DDL.strip()
