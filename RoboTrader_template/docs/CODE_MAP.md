# CODE MAP — 운영 vs 연구 경계 (에이전트 라우팅)

> 목적: 에이전트가 "운영 동작"을 찾을 때 연구/일회성 코드에 오도되지 않도록.
> 최종 검증: 2026-07-02. 드리프트 의심 시 이 파일 하단의 검증 명령 재실행.

## 디렉토리 분류
- **운영(production, 라이브 매매 경로)**: `core/` `bot/` `framework/` `api/`
  `strategies/` `collectors/` `db/` `runners/` `signals/` `lib/` `utils/`
- **연구/일회성(research, 라이브 아님)**: `scripts/` `multiverse/` `books/` `council/`
  → 운영 동작을 여기서 추론하지 말 것. 단, 아래 **예외 엣지**는 라이브가 실제 의존.

## ⚠️ 라이브 → 연구 의존 엣지 (이동 시 라이브 깨짐, 총 9 = 정적 8 + 동적 1)

### 동적 import (정적 분석 불가 — 최우선 주의)
- `collectors/daily_adj.py:8` → `importlib.import_module("scripts.10pct_strategy.p0_apply_adj_factor")`
  - 폴더명이 숫자로 시작해 정상 import 불가. import-linter/IDE가 **못 본다**.
  - 옮기면 컴파일 경고 0으로 **라이브 조정계수 수집이 조용히 깨짐**.

### 정적 import (8)
| 라이브 파일 | 대상(연구) | 성격 |
|---|---|---|
| `bot/system_monitor.py:11` | `scripts.daily_trading_summary.print_today_trading_summary` | EOD 도구 |
| `bot/system_monitor.py:245` | `scripts.paper_strategy_equity.run_daily_equity_snapshot` | EOD 도구 |
| `collectors/daily_derived.py:3` | `scripts.etl_backfill_daily_prices.SQL_UPDATE_RETURNS` | SQL 상수 |
| `collectors/foreign_flow_collector.py:19` | `scripts.backfill_foreign_flow.fetch_foreign_naver` | 외인수급 수집 함수 (2026-07 추가) |
| `strategies/rs_leader/strategy.py:16` | `scripts.rs_leader.rule.RSLeaderRule` | 진입룰 |
| `strategies/rs_leader/screener.py:14` | `scripts.rs_leader.rule.RSLeaderRule` | 진입룰 |
| `strategies/deep_mr_dev20/strategy.py:18` | `scripts.discovery.rules.MeanReversionMA20Rule` | 진입룰 |
| `strategies/deep_mr_dev20/screener.py:15` | `scripts.discovery.rules.MeanReversionMA20Rule` | 진입룰 |

## .bat 엔트리포인트가 scripts 경로 하드코딩 (이동 시 동반 수정)
- `매일_분석_실행.bat:23` → `python scripts\daily_trading_summary.py`
- `장마감_자동분석.bat:14` → `python scripts/auto_analysis.py`

## 검증 명령 (드리프트 점검)
```bash
grep -rn "from scripts\|from multiverse" bot/ collectors/ strategies/ core/ framework/ api/ db/ runners/ signals/ lib/ utils/ | grep -v test
grep -rn "import_module\|__import__" bot/ collectors/ core/ framework/ api/ db/ runners/ signals/ | grep -v test
grep -rn "scripts" *.bat
```
관련 설계: `docs/superpowers/specs/2026-06-30-research-production-separation-design.md`
