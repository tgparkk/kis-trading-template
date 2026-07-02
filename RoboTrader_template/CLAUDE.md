# CLAUDE.md — AI 개발 협업 가이드

> Claude(AI 개발자)가 이 프로젝트에 빠르게 컨텍스트를 잡기 위한 **라우터 문서**입니다.
> 상세는 각 링크를 따라가세요. 이 파일은 매 세션 컨텍스트에 자동 주입되므로 의도적으로 얇게 유지합니다.

## 프로젝트 개요

**KIS Trading Template** — 한국투자증권(KIS) API 기반 **범용 자동매매 프레임워크 템플릿**

핵심 아이디어: 공통 인프라(API 연동, 주문 처리, DB, 텔레그램 알림 등)를 프레임워크로 제공하고, 개발자는 **전략 로직만 작성**하면 되는 구조.

```
kis-trading-template/
├── RoboTrader (전략 A)        ← 전략만 다름
├── RoboTrader_orb (전략 B)    ← 전략만 다름
└── RoboTrader_template (이 프로젝트) ← 프레임워크 + 샘플 전략
```

## 🧭 운영 vs 연구 코드 라우팅 (에이전트 필독)

이 repo는 운영(라이브 매매) 코드와 연구/일회성 코드가 한 트리에 섞여 있다.
**운영 동작을 찾을 때 연구 디렉토리를 근거로 삼지 말 것.**

- **운영(production)**: `core/` `bot/` `framework/` `api/` `strategies/`
  `collectors/` `db/` `runners/` `signals/` `lib/` `utils/` `tools/`
- **연구/일회성(research, 라이브 아님)**: `scripts/` `multiverse/` `books/` `council/` `archive/` `backtest/`
  → 검색 시 후순위. 죽은 실험 코드를 라이브로 오인하지 말 것. `archive/`는 무참조 확정분 보관소(검색 제외 권장).

**예외 없음 (2026-07-02 Phase1 완료 + Phase2 `backtest/` 분류 확정)**: `scripts/`·`multiverse/`·`backtest/`에 라이브 의존 엣지 0.
운영 도구는 `tools/`(EOD 리포트·equity 스냅샷). 승격 이력·드리프트 점검 명령은
[docs/CODE_MAP.md](docs/CODE_MAP.md), 연구 파일별 태깅은 [docs/INVENTORY.md](docs/INVENTORY.md).

## 아키텍처

### 레이어 구조

```
┌───────────────────────────────────────────┐
│  strategies/          전략 레이어          │
│  (BaseStrategy 상속 → generate_signal())  │
├───────────────────────────────────────────┤
│  bot/                 봇 위임 핸들러       │
│  (초기화, 분석, 모니터링, 청산, 동기화)     │
├───────────────────────────────────────────┤
│  framework/           추상화 레이어        │
│  (Broker, DataProvider, OrderExecutor)    │
├───────────────────────────────────────────┤
│  api/                 KIS API 래퍼        │
│  (인증, 주문, 차트, 계좌, 시장정보)        │
├───────────────────────────────────────────┤
│  core/                핵심 비즈니스 로직    │
│  (주문관리, 자금관리, 매매판단엔진)         │
├───────────────────────────────────────────┤
│  db/ config/ utils/   인프라              │
└───────────────────────────────────────────┘
```

### 데이터 흐름

```
[기본 경로] strategy.on_tick(ctx: TradingContext)
  → generate_signal() 호출 → Signal 반환
  → ctx.buy() / ctx.sell() (서킷브레이커·VI·시장방향 가드 내장)
  → TradingDecisionEngine이 Signal 해석 (target_price/stop_loss 활용)
  → OrderManager가 주문 실행 (KIS API)
  → 체결 모니터링 → on_order_filled 콜백
  → DB 저장 + 텔레그램 알림
```

> 모듈별 상세표(framework / api / core / bot / config / db / utils), `main.py` 동작 흐름, 테스트 구조는
> **→ [docs/code/MODULES.md](docs/code/MODULES.md)** 로 분리되어 있습니다.

## 전략 시스템

### 활성 페이퍼 전략 8종 (라이브 운영)

운영 한눈표·자본/regime 모델·데이터 소스(SSOT)는 **→ [docs/PAPER_STRATEGIES.md](docs/PAPER_STRATEGIES.md) (허브)**.
전략별 상세(의도·진입/청산 룰·평판)는 각 코드 폴더 README:

| # | 전략 (폴더키) | 성격 | 상세 |
|---|---|---|---|
| 1 | `elder_ema_pullback` | 추세추종 (최강) | [README](strategies/elder_ema_pullback/README.md) |
| 2 | `book_envelope_200d` | 돌파 모멘텀 | [README](strategies/book_envelope_200d/README.md) |
| 3 | `daytrading_3methods_breakout` | 돌파 (탐색) | [README](strategies/daytrading_3methods_breakout/README.md) |
| 4 | `minervini_volume_dryup` | 매집/dry-up | [README](strategies/minervini_volume_dryup/README.md) |
| 5 | `book_pullback_ma20` | 눌림목 (MA20) | [README](strategies/book_pullback_ma20/README.md) |
| 6 | `book_pullback_ma5` | 눌림목 (MA5, 타이트) | [README](strategies/book_pullback_ma5/README.md) |
| 7 | `rs_leader` | RS 리더 (관찰) | [README](strategies/rs_leader/README.md) |
| 8 | `deep_mr_dev20` | 평균회귀 (폭락 저격) | [README](strategies/deep_mr_dev20/README.md) |

### 예제/템플릿 전략 (참고용, 비활성)

`sample` · `momentum` · `mean_reversion` · `volume_breakout` · `bb_reversion` · `lynch` · `sawkami`
— 목록·핵심 로직은 [docs/code/MODULES.md](docs/code/MODULES.md#예제템플릿-전략-참고용-비활성).

### 새 전략 추가

`generate_signal()` 하나만 구현하면 동작합니다. Step-by-step·BaseStrategy 인터페이스·`Signal`/`TradingContext` API·
테스트 작성·체크리스트는 **→ [docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md)**.

핵심 규칙만:
- `holding_period = "swing"` 선언 시 EOD 일괄청산을 건너뜀 (각 전략 청산 룰로만 빠짐).
- `exit_timeframe`는 미설정 시 `holding_period`에서 자동 유도(swing→"daily", intraday→"intraday").
  swing 전략에 `exit_timeframe="intraday"`를 명시하면 모순이라 `BaseStrategy.__init__`이 거부(분봉 whipsaw 방지, 2026-06-18).

## 개발 규칙 & 컨벤션

### 코드 스타일
- Python 3.8+ 호환
- 비동기: `asyncio` 기반 (`async/await`)
- 블로킹 API 호출은 `ThreadPoolExecutor`로 래핑 (`framework/executor.py` 참고)
- 로깅: `utils.logger.setup_logger(__name__)` 사용
- 시간: 항상 `utils.korean_time.now_kst()` 사용 (KST 기준)

### 설계 패턴
- **Facade**: `order_manager.py`는 `orders/` 서브모듈의 Facade
- **Strategy**: `BaseStrategy` 추상 클래스 + 동적 로딩
- **Repository**: `db/repositories/`
- **Mixin**: `OrderExecutorMixin`, `OrderMonitorMixin` 등

### 파일 네이밍
- 모듈: `snake_case.py` / 클래스: `PascalCase` / 상수: `UPPER_SNAKE_CASE` (`config/constants.py`) / 전략 폴더: `snake_case`

### 주의사항
- `.env`에 `APP_KEY`, `APP_SECRET` 등 API 키 설정 필수 (`.env.example` 참고)
- 가상매매 모드: `VIRTUAL_MODE=true`로 실제 주문 없이 테스트 가능
- 프로세스 중복 실행 방지: PID 파일 (`robotrader.pid`) 사용

## 문서 지도

| 문서 | 내용 |
|------|------|
| [README.md](README.md) | 프로젝트 소개 및 빠른 시작 |
| [SYSTEM_FLOW.md](SYSTEM_FLOW.md) | 시스템 동작 흐름 상세 |
| [docs/code/MODULES.md](docs/code/MODULES.md) | **코드 모듈별 상세** (main.py·framework·core·api·bot·db·utils·테스트) |
| [docs/PAPER_STRATEGIES.md](docs/PAPER_STRATEGIES.md) | **활성 전략 운영 허브** (한눈표·자본/regime·데이터 SSOT) |
| `strategies/{name}/README.md` | **전략별 상세** (활성 8전략) |
| [docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md) | 전략 추가 가이드 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 시스템 아키텍처, 모듈 관계도 |
| [docs/TRADING_FLOW.md](docs/TRADING_FLOW.md) | 매매 흐름 (초기화→루프→청산) |
| [docs/DATABASE.md](docs/DATABASE.md) | DB 스키마 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | 설정 가이드 |
| [docs/DATA_MANAGEMENT.md](docs/DATA_MANAGEMENT.md) · [docs/DYNAMIC_RISK_MANAGEMENT.md](docs/DYNAMIC_RISK_MANAGEMENT.md) | 데이터 관리 · 동적 리스크 관리 |

---

**마지막 업데이트**: 2026-07-02 (Phase1 완료 — 라이브→연구 엣지 0, `tools/` 운영 편입 / Phase2 — `backtest/` 연구 분류 확정, `runners/` 연구 러너 2본 `scripts/`로 강등)
