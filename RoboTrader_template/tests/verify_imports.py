"""
dev-C 최종 검증 스크립트
- 모든 모듈 import 검증
- quant 전용 키워드 잔존 확인
"""
import sys
import os
import importlib
import re

# 프로젝트 루트 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

results = {"pass": 0, "fail": 0, "warnings": []}

def check(label, fn):
    try:
        fn()
        print(f"  ✅ {label}")
        results["pass"] += 1
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        results["fail"] += 1

# === 1. main.py DayTradingBot import ===
print("\n=== 1. main.py DayTradingBot import ===")
check("from main import DayTradingBot", lambda: __import__("main").DayTradingBot)

# === 2. 모듈별 import 검증 ===
MODULES = {
    "core": [
        "core.models", "core.data_collector", "core.order_manager",
        "core.telegram_integration", "core.intraday_stock_manager",
        "core.trading_stock_manager", "core.trading_decision_engine",
        "core.fund_manager", "core.candidate_selector",
        "core.dynamic_batch_calculator", "core.price_calculator",
        "core.realtime_candle_builder", "core.realtime_data_logger",
        "core.timeframe_converter", "core.trend_momentum_analyzer",
        "core.virtual_trading_manager", "core.post_market_data_saver",
        "core.intraday_data_utils",
    ],
    "core.orders": [
        "core.orders", "core.orders.order_base", "core.orders.order_db_handler",
        "core.orders.order_executor", "core.orders.order_monitor", "core.orders.order_timeout",
    ],
    "core.trading": [
        "core.trading", "core.trading.order_completion_handler",
        "core.trading.order_execution", "core.trading.position_monitor",
        "core.trading.stock_state_manager",
    ],
    "core.intraday": [
        "core.intraday", "core.intraday.data_collector",
        "core.intraday.data_quality", "core.intraday.models",
        "core.intraday.price_service", "core.intraday.realtime_updater",
    ],
    "bot": [
        "bot", "bot.initializer", "bot.trading_analyzer",
        "bot.system_monitor", "bot.liquidation_handler", "bot.position_sync",
    ],
    "strategies": [
        "strategies", "strategies.base", "strategies.config",
        "strategies.sample", "strategies.sample.strategy",
    ],
    "framework": [
        "framework", "framework.broker", "framework.data", "framework.executor",
        "framework.utils", "framework.data_providers",
    ],
    "api": [
        "api", "api.kis_auth", "api.kis_api_manager",
        "api.kis_account_api", "api.kis_chart_api",
        "api.kis_financial_api", "api.kis_market_api", "api.kis_order_api",
    ],
    "db": [
        "db", "db.config", "db.connection", "db.database_manager",
        "db.repositories",
    ],
    "config": [
        "config.constants", "config.market_hours", "config.settings",
    ],
    "utils": [
        "utils", "utils.logger", "utils.korean_time", "utils.price_utils",
        "utils.async_helpers", "utils.data_cache", "utils.korean_holidays",
    ],
}

for group, modules in MODULES.items():
    print(f"\n=== 2. {group} modules ===")
    for mod in modules:
        check(mod, lambda m=mod: importlib.import_module(m))

# === 3. quant 전용 키워드 잔존 확인 ===
print("\n=== 3. quant 전용 키워드 잔존 확인 (main.py) ===")
QUANT_KEYWORDS = ["KISAPIManager", "QuantScreeningService", "quant_screening", "QuantStrategy"]
with open(os.path.join(PROJECT_ROOT, "main.py"), "r", encoding="utf-8") as f:
    main_content = f.read()

found_any = False
for kw in QUANT_KEYWORDS:
    if kw in main_content:
        print(f"  ⚠️ main.py에 '{kw}' 발견!")
        results["warnings"].append(f"main.py contains '{kw}'")
        found_any = True
if not found_any:
    print("  ✅ quant 전용 키워드 없음")
    results["pass"] += 1

# === Summary ===
print(f"\n{'='*50}")
print(f"결과: ✅ {results['pass']} passed, ❌ {results['fail']} failed")
if results["warnings"]:
    print(f"⚠️ Warnings: {results['warnings']}")
if results["fail"] == 0 and not results["warnings"]:
    print("🎉 모든 검증 통과!")
sys.exit(results["fail"])
