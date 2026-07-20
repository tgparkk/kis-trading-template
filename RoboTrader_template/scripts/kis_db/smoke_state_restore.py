"""상태복원 스모크(격리 worktree 전용). StateRestorer 를 선택 DB 로 실행해
열린 포지션 / 전략별 현금원장 / 후보를 요약하고, kis_template 와 robotrader
기준(baseline)을 대조한다.

⚠️ 라이브 트리에서 실행 금지(메모리 규칙). 이 스크립트는 DB 를 읽기만 한다
(StateRestorer 는 fake trading_manager 로 주입되어 실주문/실쓰기 없음).

DB 격리: baseline(robotrader)/candidate(kis_template) 각각을 **별도 자식 프로세스**에서
읽는다. db.connection.DatabaseConnection 은 모듈 레벨 싱글턴 풀이라 한 프로세스 안에서
dbname 을 재바인딩하면(close_all + env 스왑) 취약(다른 스레드/이미 초기화된 풀 잔존)하다.
자식 프로세스는 풀이 초기화되기 전에 TIMESCALE_DB 를 세팅하므로 항상 pristine.

usage(worktree):
  python -m scripts.kis_db.smoke_state_restore --baseline-db robotrader --candidate-db kis_template
  # (내부적으로 각 DB 를 --emit-db 자식 프로세스로 실행해 JSON 요약을 대조)
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.constants import (  # noqa: E402
    COMMISSION_RATE,
    SECURITIES_TAX_RATE,
    VIRTUAL_CAPITAL_PER_STRATEGY,
)

DEFAULT_CAPITAL = VIRTUAL_CAPITAL_PER_STRATEGY


def build_restore_summary(open_positions, strategy_sums, candidate_codes,
                          capital: float = DEFAULT_CAPITAL) -> dict:
    """순수 요약. 현금식은 라이브(restore_strategy_ledger_from_records)와 동일:
        cash = capital - buy_gross*(1+comm) + sell_gross*(1-comm-tax)
    """
    codes = sorted({p["stock_code"] for p in open_positions})
    per_cash = {}
    for strat, s in strategy_sums.items():
        buy_g = float(s.get("buy_gross", 0.0))
        sell_g = float(s.get("sell_gross", 0.0))
        cash = capital - buy_g * (1 + COMMISSION_RATE) + sell_g * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE)
        per_cash[strat] = round(cash, 2)
    return {
        "open_position_codes": codes,
        "n_open": len(codes),
        "per_strategy_cash": per_cash,
        "candidate_codes": sorted(set(candidate_codes)),
    }


def compare_summaries(baseline: dict, candidate: dict) -> dict:
    """순수 대조. 현금은 전략별 절대차 최대치가 1원 미만이면 일치."""
    pos_match = baseline["open_position_codes"] == candidate["open_position_codes"]
    cand_match = baseline["candidate_codes"] == candidate["candidate_codes"]
    strategies = set(baseline["per_strategy_cash"]) | set(candidate["per_strategy_cash"])
    max_diff = 0.0
    for s in strategies:
        b = baseline["per_strategy_cash"].get(s, 0.0)
        c = candidate["per_strategy_cash"].get(s, 0.0)
        max_diff = max(max_diff, abs(b - c))
    cash_match = max_diff < 1.0
    verdict = "PASS" if (pos_match and cand_match and cash_match) else "FAIL"
    return {
        "open_positions_match": pos_match,
        "candidates_match": cand_match,
        "cash_max_abs_diff": max_diff,
        "cash_match": cash_match,
        "verdict": verdict,
    }


# ── 라이브 스모크 (DB 필요, worktree 전용) ──────────────────────────────────

class _FakeTradingManager:
    """add_selected_stock/get_trading_stock 를 받아 복원 포지션을 캡처하는 최소 fake."""
    def __init__(self):
        self.captured = {}  # stock_code -> {quantity, buy_price, strategy}

    async def add_selected_stock(self, stock_code, stock_name, selection_reason,
                                 prev_close=None, owner_strategy=None):
        self.captured[stock_code] = {"stock_code": stock_code, "quantity": 0,
                                     "buy_price": 0.0, "strategy": owner_strategy or ""}
        return True

    def get_trading_stock(self, stock_code, strategy=None):
        rec = self.captured.get(stock_code)
        if rec is None:
            return None
        return _FakeTradingStock(rec)

    def _change_stock_state(self, *a, **k):
        return None


class _FakeTradingStock:
    def __init__(self, rec):
        self._rec = rec
        self.stock_code = rec["stock_code"]
        self.stock_name = rec["stock_code"]
        self.owner_strategy_name = rec["strategy"]
        self.owner_strategy = None
        self.target_profit_rate = None
        self.stop_loss_rate = None
        self.is_stale = False
        self.days_held = 0

    def set_position(self, quantity, buy_price):
        self._rec["quantity"] = int(quantity)
        self._rec["buy_price"] = float(buy_price)

    def set_virtual_buy_info(self, *a, **k):
        return None


class _FakeConfig:
    paper_trading = True


def run_smoke(dbname: str, capital: float = DEFAULT_CAPITAL) -> dict:
    """현재 프로세스에서 TIMESCALE_DB=dbname 을 세팅하고 StateRestorer 를 fake 로 실행 → 요약.

    풀 초기화 전에 env 를 세팅해야 하므로 반드시 자식 프로세스(--emit-db)로 호출한다.
    부모 프로세스에서 직접 호출하면 이미 초기화된 싱글턴 풀이 남아 잘못된 DB 를 읽을 수 있다.
    """
    # ⚠️ TIMESCALE_DB 는 반드시 복원해야 한다. 인프로세스 테스트가 run_smoke() 를
    # 호출하면 이 env 스왑이 잔존해 이후 pytest 세션의 모든 DB 테스트가 없는 DB 로
    # 접속(psycopg2.OperationalError)해 연쇄 실패한다. try/finally 로 원복 보장.
    _prev_timescale_db = os.environ.get("TIMESCALE_DB")
    os.environ["TIMESCALE_DB"] = dbname
    try:
        from bot.state_restorer import StateRestorer
        from db.repositories.trading import TradingRepository
        from db.repositories.candidate import CandidateRepository
        from utils.korean_time import now_kst

        # real_table_name 을 기본값으로 명시 고정 → __init__ 의 ensure_real_table()
        # (CREATE TABLE ... LIKE ... INCLUDING ALL) DDL 분기를 절대 타지 않는다.
        # KIS_INSTANCE_DIR 가 세팅된 환경에서 인자 없이 생성하면 비-기본 테이블명이
        # 주입되어 DDL 이 발동한다 — 이 스모크는 read-only 여야 한다(가상 테이블만 읽음).
        trading_repo = TradingRepository(real_table_name="real_trading_records")
        candidate_repo = CandidateRepository()

        tm = _FakeTradingManager()
        restorer = StateRestorer(
            trading_manager=tm,
            db_manager=trading_repo,
            telegram_integration=None,
            config=_FakeConfig(),
            get_previous_close_callback=lambda code: None,
            broker=None,
            fund_manager=None,
            virtual_trading_manager=None,
            strategies={},
        )
        asyncio.run(restorer.restore_todays_candidates())

        # tm.captured 는 후보 스캔 종목(quantity=0)과 실보유 종목(set_position 으로
        # quantity>0 확정) 을 모두 담는다 — quantity>0 로 걸러야 진짜 보유만 남는다.
        # (걸러내지 않으면 유실된 실보유가 같은 종목이 후보로도 잡혀 있을 때 가짜 PASS)
        open_positions = [p for p in tm.captured.values() if p["quantity"] > 0]
        strategy_sums = trading_repo.get_strategy_trade_sums()
        today = now_kst().strftime("%Y-%m-%d")
        # _restore_candidates 와 동일하게 DATE(selection_date)=today 로 엄격 필터
        # (get_candidate_history(days=1) 의 24시간 롤링 윈도우는 복원 의미론과 다름)
        cand_df = candidate_repo.get_candidate_history(days=1)
        if not cand_df.empty and "stock_code" in cand_df.columns:
            same_day = cand_df["selection_date"].dt.strftime("%Y-%m-%d") == today
            cand_codes = list(cand_df.loc[same_day, "stock_code"])
        else:
            cand_codes = []
        return build_restore_summary(open_positions, strategy_sums, cand_codes, capital)
    finally:
        # 풀이 테스트 DB 에 바인딩된 채 남지 않도록 먼저 teardown(실패해도 무시).
        try:
            from db.connection import DatabaseConnection
            DatabaseConnection.close_all()
        except Exception:
            pass
        # env 복원: 이전 값이 없었으면 제거, 있었으면 원복.
        if _prev_timescale_db is None:
            os.environ.pop("TIMESCALE_DB", None)
        else:
            os.environ["TIMESCALE_DB"] = _prev_timescale_db


def _spawn_summary(dbname: str, capital: float) -> dict:
    """자식 프로세스로 run_smoke 를 실행하고 stdout 의 JSON 요약을 파싱(풀 격리 경계)."""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.kis_db.smoke_state_restore",
         "--emit-db", dbname, "--capital", str(capital)],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"smoke child failed for {dbname}: {proc.stderr.strip()}")
    # 마지막 비어있지 않은 줄이 JSON 요약(로깅 라인이 앞에 섞여도 안전)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return json.loads(lines[-1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="상태복원 스모크(worktree 전용, READ-only)")
    ap.add_argument("--baseline-db", default="robotrader")
    ap.add_argument("--candidate-db", default="kis_template")
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--emit-db", default=None,
                    help="자식 모드: 이 DB 로 run_smoke 후 JSON 요약만 출력하고 종료")
    args = ap.parse_args(argv)

    # 자식 모드: 단일 DB 요약을 JSON 으로 방출(부모가 파싱)
    if args.emit_db:
        summary = run_smoke(args.emit_db, args.capital)
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    # 부모 모드: 각 DB 를 별도 자식 프로세스로 격리 실행 후 대조
    baseline = _spawn_summary(args.baseline_db, args.capital)
    candidate = _spawn_summary(args.candidate_db, args.capital)
    result = compare_summaries(baseline, candidate)

    print(f"[baseline {args.baseline_db}] n_open={baseline['n_open']} "
          f"strategies={len(baseline['per_strategy_cash'])} candidates={len(baseline['candidate_codes'])}")
    print(f"[candidate {args.candidate_db}] n_open={candidate['n_open']} "
          f"strategies={len(candidate['per_strategy_cash'])} candidates={len(candidate['candidate_codes'])}")
    print(f"positions_match={result['open_positions_match']} "
          f"candidates_match={result['candidates_match']} "
          f"cash_max_abs_diff={result['cash_max_abs_diff']:.2f} "
          f"cash_match={result['cash_match']}")
    print(f"[SMOKE VERDICT] {result['verdict']}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
