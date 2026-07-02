"""
diag_trail_ab.py - trail_pct A/B 진단 실험 (임시 스크립트, 코드 수정 없음)

가설:
  H1: trail_pct=0.005(0.5%) 가 TP(2%)를 조기에 차단 -> 손실 비대칭 구조
  H2: SL이 TP보다 먼저 체크되는 구조적 비대칭
  H3: ma_trend 등 일부 전략이 하루 ~49종목 진입 (과매수)

실행:
  cd D:\\GIT\\kis-trading-template\\RoboTrader_template
  python scripts/diag_trail_ab.py
"""
from __future__ import annotations

import importlib
import sys
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional
from collections import defaultdict

# --- 경로 설정 ---
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --- 환경 변수 설정 (DB 연결용) ---
# .env 파일이 있으면 로드
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from backtest.engine import BacktestEngine
from utils.logger import setup_logger

logger = setup_logger("diag_trail_ab")

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
START_DATE = "20260401"
END_DATE   = "20260410"
INITIAL_CAPITAL = 10_000_000
MAX_POSITIONS   = 3
STOP_LOSS_PCT   = 0.01
TAKE_PROFIT_PCT = 0.02
SLIP_BPS        = 5.0
EOD_TIME        = "15:20"
DYNAMIC_TOP_N   = 50

STRATEGIES = ["orb", "ma_trend", "vwap_trade", "red_to_green"]

STRATEGY_REGISTRY: dict = {
    "orb":           "strategies.intraday.orb.strategy.OrbStrategy",
    "ma_trend":      "strategies.intraday.ma_trend.strategy.MaTrendStrategy",
    "vwap_trade":    "strategies.intraday.vwap_trade.strategy.VwapTradeStrategy",
    "red_to_green":  "strategies.intraday.red_to_green.strategy.RedToGreenStrategy",
}

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _load_strategy(key: str):
    dotpath = STRATEGY_REGISTRY[key]
    module_path, cls_name = dotpath.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)
    return cls({})


def _make_dynamic_provider(top_n: int = 50) -> Callable[[str], List[str]]:
    try:
        from utils.intraday_universe import build_universe_for_date as _build
        cache_path = ROOT / "cache" / "intraday_universe"
        cache_path.mkdir(parents=True, exist_ok=True)

        def _provider(trade_date: str) -> List[str]:
            try:
                return _build(trade_date, cache_dir=cache_path, top_n=top_n, rank_by="volatility_pct")
            except Exception as exc:
                logger.warning(f"dynamic universe 실패 [{trade_date}]: {exc}")
                return []
        return _provider
    except ImportError as e:
        logger.error(f"intraday_universe import 실패: {e}")
        def _stub(_: str) -> List[str]:
            return []
        return _stub


def _pct_bucket(pnl_pct: float) -> str:
    if pnl_pct < -0.01:
        return "<-1%"
    elif pnl_pct < -0.005:
        return "-1~-0.5%"
    elif pnl_pct < 0.0:
        return "-0.5~0%"
    elif pnl_pct < 0.005:
        return "0~0.5%"
    elif pnl_pct < 0.02:
        return "0.5~2%"
    else:
        return ">2%"


def _analyze_result(result, label: str) -> dict:
    """BacktestResult에서 핵심 지표 추출."""
    trades = result.trades or []
    total = len(trades)

    wins   = [t for t in trades if t.get("pnl_pct", 0) > 0]
    losses = [t for t in trades if t.get("pnl_pct", 0) <= 0]

    win_rate    = len(wins) / total if total else 0.0
    avg_win     = sum(t["pnl_pct"] for t in wins)   / len(wins)   if wins   else 0.0
    avg_loss    = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0.0

    # pnl 분포
    buckets: Dict[str, int] = defaultdict(int)
    for t in trades:
        buckets[_pct_bucket(t.get("pnl_pct", 0))] += 1

    # 보유시간 (분)
    hold_mins = []
    for t in trades:
        et = t.get("entry_time")
        xt = t.get("exit_time")
        if et is not None and xt is not None:
            try:
                delta = (xt - et).total_seconds() / 60.0
                hold_mins.append(delta)
            except Exception:
                pass

    avg_hold  = sum(hold_mins) / len(hold_mins) if hold_mins else 0.0
    med_hold  = sorted(hold_mins)[len(hold_mins)//2] if hold_mins else 0.0

    # sells_by_reason
    sbr = result.sells_by_reason or {}
    tp_cnt    = sbr.get("intraday_tp", 0)
    trail_cnt = sbr.get("intraday_trail", 0)
    sl_cnt    = sbr.get("intraday_sl", 0)
    eod_cnt   = sbr.get("eod_t0", 0)
    sig_cnt   = sbr.get("signal_sell", 0)

    # H3: 하루당 진입 종목 수
    by_date: Dict[str, set] = defaultdict(set)
    for t in trades:
        d = t.get("entry_date", "")
        c = t.get("stock_code", "")
        if d and c:
            by_date[str(d)].add(c)
    daily_counts = [len(v) for v in by_date.values()]
    avg_daily_entries = sum(daily_counts) / len(daily_counts) if daily_counts else 0.0
    max_daily_entries = max(daily_counts) if daily_counts else 0

    return {
        "label":            label,
        "total_return":     result.total_return,
        "total_trades":     total,
        "win_rate":         win_rate,
        "avg_win_pct":      avg_win,
        "avg_loss_pct":     avg_loss,
        "tp_cnt":           tp_cnt,
        "tp_pct":           tp_cnt / total if total else 0.0,
        "trail_cnt":        trail_cnt,
        "trail_pct_ratio":  trail_cnt / total if total else 0.0,
        "sl_cnt":           sl_cnt,
        "sl_pct_ratio":     sl_cnt / total if total else 0.0,
        "eod_cnt":          eod_cnt,
        "sig_cnt":          sig_cnt,
        "avg_hold_min":     avg_hold,
        "med_hold_min":     med_hold,
        "avg_daily_entries": avg_daily_entries,
        "max_daily_entries": max_daily_entries,
        "pnl_dist":         dict(buckets),
    }


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    provider = _make_dynamic_provider(top_n=DYNAMIC_TOP_N)

    # 결과 저장: {strat_key: {"A": metrics, "B": metrics}}
    all_results: Dict[str, Dict[str, dict]] = {}

    for strat_key in STRATEGIES:
        logger.info(f"\n{'='*60}")
        logger.info(f"전략: {strat_key}")
        logger.info(f"{'='*60}")

        pair: Dict[str, dict] = {}

        for config_label, trail_val in [("A_no_trail", None), ("B_trail005", 0.005)]:
            logger.info(f"  설정 {config_label} (trail_pct={trail_val}) 실행 중...")

            strategy = _load_strategy(strat_key)
            strategy.stop_loss_pct   = STOP_LOSS_PCT
            strategy.take_profit_pct = TAKE_PROFIT_PCT

            engine = BacktestEngine(
                strategy=strategy,
                initial_capital=INITIAL_CAPITAL,
                max_positions=MAX_POSITIONS,
            )

            run_kwargs = dict(
                stock_codes=[],
                start_date=START_DATE,
                end_date=END_DATE,
                candidate_provider=provider,
                initial_capital=INITIAL_CAPITAL,
                max_positions=MAX_POSITIONS,
                slip_bps=SLIP_BPS,
                eod_time=EOD_TIME,
                stop_loss_pct=STOP_LOSS_PCT,
                take_profit_pct=TAKE_PROFIT_PCT,
                trail_pct=trail_val,
                verbose=False,
            )

            try:
                result = engine.run_minute(**run_kwargs)
                metrics = _analyze_result(result, config_label)
                pair[config_label] = metrics
                logger.info(
                    f"    완료: total_return={metrics['total_return']:+.2%}, "
                    f"trades={metrics['total_trades']}, "
                    f"win={metrics['win_rate']:.1%}, "
                    f"tp={metrics['tp_cnt']}건, trail={metrics['trail_cnt']}건"
                )
            except Exception as exc:
                logger.error(f"    실행 오류: {exc}", exc_info=True)
                pair[config_label] = {"label": config_label, "error": str(exc)}

        all_results[strat_key] = pair

    # ---------------------------------------------------------------------------
    # 보고서 출력
    # ---------------------------------------------------------------------------
    BUCKET_ORDER = ["<-1%", "-1~-0.5%", "-0.5~0%", "0~0.5%", "0.5~2%", ">2%"]

    sep = "=" * 80
    print(f"\n{sep}")
    print("  A/B 비교표 (설정A=trail off, 설정B=trail on 0.5%)")
    print(f"{sep}")

    header = f"{'전략':15s} {'설정':14s} {'총수익률':>9s} {'거래수':>6s} {'승률':>7s} " \
             f"{'tp건/비율':>12s} {'trail건/비율':>14s} {'sl건/비율':>12s} " \
             f"{'eod건':>6s} {'avg보유분':>9s} {'avg일진입':>9s}"
    print(header)
    print("-" * len(header))

    for strat_key in STRATEGIES:
        pair = all_results.get(strat_key, {})
        for cfg_label in ["A_no_trail", "B_trail005"]:
            m = pair.get(cfg_label, {})
            if "error" in m:
                print(f"  {strat_key:13s} {cfg_label:14s}  ERROR: {m['error']}")
                continue
            tp_str    = f"{m['tp_cnt']:3d} ({m['tp_pct']:5.1%})"
            trail_str = f"{m['trail_cnt']:3d} ({m['trail_pct_ratio']:5.1%})"
            sl_str    = f"{m['sl_cnt']:3d} ({m['sl_pct_ratio']:5.1%})"
            print(
                f"  {strat_key:13s} {cfg_label:14s} "
                f"{m['total_return']:+8.2%} "
                f"{m['total_trades']:6d} "
                f"{m['win_rate']:7.1%} "
                f"{tp_str:>12s} "
                f"{trail_str:>14s} "
                f"{sl_str:>12s} "
                f"{m['eod_cnt']:6d} "
                f"{m['avg_hold_min']:9.1f} "
                f"{m['avg_daily_entries']:9.1f}"
            )
        print()

    # --- H1 판정 ---
    print(f"\n{sep}")
    print("  [H1 판정] trail off vs trail on 수익률 차이 + TP 건수 변화")
    print(f"{sep}")
    for strat_key in STRATEGIES:
        pair = all_results.get(strat_key, {})
        mA = pair.get("A_no_trail", {})
        mB = pair.get("B_trail005", {})
        if "error" in mA or "error" in mB:
            print(f"  {strat_key}: 데이터 없음 (오류)")
            continue
        diff = mA["total_return"] - mB["total_return"]
        tp_diff = mA["tp_cnt"] - mB["tp_cnt"]
        trail_b = mB["trail_cnt"]
        verdict = ""
        if diff > 0.05 and tp_diff > 0:
            verdict = "[강력 확증] trail이 수익률 훼손 + TP 억제 확인"
        elif diff > 0.02:
            verdict = "[확증] trail off가 유의미하게 개선"
        elif diff > 0:
            verdict = "[약한 확증] trail off가 소폭 개선"
        else:
            verdict = "[반증] trail off가 개선하지 않음"
        print(
            f"  {strat_key:15s}: "
            f"수익률차이(A-B)={diff:+.2%}  "
            f"TP건차이(A-B)={tp_diff:+d}  "
            f"trail청산(B)={trail_b}건  "
            f"-> {verdict}"
        )

    # --- H2 판정 ---
    print(f"\n{sep}")
    print("  [H2 판정] SL+TP 동시 충족 추정 (단일봉 변동폭 vs SL+TP 합계)")
    print(f"  ※ 직접 계측 불가 (engine 내부 데이터). 간접 추정만 가능.")
    print(f"  SL=1%, TP=2%, trail=0.5% -> 1봉에서 둘 다 닿으려면 봉폭>=3%")
    print(f"  dynamic universe 필터 조건: 일 변동성>=3%, 거래대금>=100억")
    print(f"  분봉 평균 변동폭 ~= 일변동폭/390 ~= 0.23%  ->  1봉 SL+TP 동시 충족은 극히 드물 것 [추정]")
    print(f"  따라서 SL vs TP 우선순위(elif) 영향 < trail_pct 영향 [추정]")
    print(f"{sep}")

    # --- H3 판정 ---
    print(f"\n{sep}")
    print("  [H3 판정] 하루 진입 종목수 (max_positions=3 설정)")
    print(f"{sep}")
    for strat_key in STRATEGIES:
        pair = all_results.get(strat_key, {})
        mA = pair.get("A_no_trail", {})
        if "error" in mA:
            continue
        avg_d = mA.get("avg_daily_entries", 0)
        max_d = mA.get("max_daily_entries", 0)
        total_t = mA.get("total_trades", 0)
        days = 8  # 약 8거래일
        verdict_h3 = ""
        if avg_d >= 2.5:
            verdict_h3 = "[확증] max_positions=3 포화 수준 진입"
        elif avg_d >= 1.5:
            verdict_h3 = "[부분] 중간 수준 진입"
        else:
            verdict_h3 = "[미확증] 선별적 진입"
        print(
            f"  {strat_key:15s}: avg={avg_d:.1f}종목/일, max={max_d}종목/일, "
            f"총{total_t}거래  -> {verdict_h3}"
        )

    # --- pnl 분포 상세 ---
    print(f"\n{sep}")
    print("  PnL 분포 상세 (A=trail off, B=trail on)")
    print(f"{sep}")
    for strat_key in STRATEGIES:
        pair = all_results.get(strat_key, {})
        print(f"\n  [{strat_key}]")
        for cfg_label in ["A_no_trail", "B_trail005"]:
            m = pair.get(cfg_label, {})
            if "error" in m:
                continue
            dist = m.get("pnl_dist", {})
            row = "  ".join(f"{b}:{dist.get(b,0)}건" for b in BUCKET_ORDER)
            print(f"    {cfg_label}: {row}")
            print(
                f"           avg수익={m['avg_win_pct']:+.3%}  "
                f"avg손실={m['avg_loss_pct']:+.3%}  "
                f"보유중앙={m['med_hold_min']:.0f}분"
            )

    # --- 결론 ---
    print(f"\n{sep}")
    print("  [종합 결론]")
    print(f"{sep}")
    h1_confirmed = 0
    for strat_key in STRATEGIES:
        pair = all_results.get(strat_key, {})
        mA = pair.get("A_no_trail", {})
        mB = pair.get("B_trail005", {})
        if "error" not in mA and "error" not in mB:
            if mA.get("total_return", -99) > mB.get("total_return", -99):
                h1_confirmed += 1
    print(
        f"  H1 확증 전략 수: {h1_confirmed}/{len(STRATEGIES)} "
        f"({'강력 확증' if h1_confirmed >= 3 else '부분 확증' if h1_confirmed >= 2 else '미확증'})"
    )
    print(
        f"  H2: 분봉 변동폭 <<  SL+TP 합계(3%) - elif 순서 영향 미미 [구조적 추정, 별도 계측 불가]"
    )
    print(
        f"  H3: 위 표 참조. max_positions=3 제한이 있어 토너먼트 설정(n_pos 그리드)과 다름."
    )
    print(f"\n  ※ 진단 스크립트 경로: scripts/diag_trail_ab.py")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
