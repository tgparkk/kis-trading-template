# kis-template — KIS API 페이퍼 트레이딩 봇

> 한국투자증권(KIS) Open API 로 국내 주식을 자동매매하는 봇. 현재는 **8전략 페이퍼(가상) 매매**로 매 거래일 운영 중이다. 출발점은 「전략만 갈아끼우는 프레임워크 템플릿」이었고, 코드 디렉토리명 `RoboTrader_template/` 은 그 흔적이다.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/) [![License](https://img.shields.io/badge/License-MIT-green.svg)](../pyproject.toml)

## 1. 지금 이 레포는

- 활성 전략 8종 = `config/trading_config.json` `strategies[]`(8개 전부 `enabled: true`, 최상위 `"paper_trading": true`). 목록·수치 → [docs/PAPER_STRATEGIES.md](docs/PAPER_STRATEGIES.md).
- 2026-09-05 부터 3전략(`book_pullback_ma20` · `minervini_volume_dryup` · `daytrading_3methods_breakout`)만 고도화하고 나머지 5종은 관측만 한다 → [docs/plan_2026-09-05_focus3_roadmap.md](docs/plan_2026-09-05_focus3_roadmap.md).
- 실전(실주문) 전환은 보류 중. 실전 인스턴스 구조는 [instances/README.md](instances/README.md).
- 봇은 월~금 07:40 Windows 작업 스케줄러가 `run_robotrader.bat` 로 자동 기동한다. 라이브 트리에서 테스트·브랜치 전환 금지 → [CLAUDE.md](CLAUDE.md).

## 2. 요구 사항

| 항목 | 값 | 근거 |
|---|---|---|
| Python | 3.9+ | 레포 루트 `pyproject.toml` `requires-python = ">=3.9"` |
| DB | PostgreSQL 16 + TimescaleDB · **포트 5433** · DB `kis_template` · user `robotrader` | `db/connection.py` 코드 기본값 · 상세 [docs/DATABASE.md](docs/DATABASE.md) |
| KIS Open API | `[KIS]` 키 5개 — BASE_URL · APP_KEY · APP_SECRET · 계좌번호 · HTS ID | `config/key.ini` `[KIS]` |
| OS | Windows(런처가 `.bat`) | `run_robotrader.bat` |

## 3. 설정 (한 번만)

```bat
copy config\key.ini.example config\key.ini
copy .env.example .env
```

- `config/key.ini` = `[KIS]` 키 5개(BASE_URL·APP_KEY·APP_SECRET·계좌번호·HTS ID) + `[TELEGRAM]` `enabled`/`token`/`chat_id`. **API 키는 `.env` 가 아니라 여기다** — `config/settings.py` 가 `configparser` 로 `[KIS]` 절을 읽고, `core/telegram_integration.py` 가 `[TELEGRAM]` 절을 읽는다. `key.ini` 가 없으면 `run_robotrader.bat` 가 기동 전에 멈춘다.
- `.env` 는 **선택**이다. `db/connection.py` 기본값이 이미 `localhost:5433/kis_template` 이라 없어도 붙는다. 쓰면 `config/env_bootstrap.py` 가 읽되 **인라인 `#` 주석이 값에 포함**되니 주석은 별도 줄에 둘 것. 변수 전수 → [docs/CONFIGURATION.md](docs/CONFIGURATION.md) §4.

## 4. 실행

```bat
run_robotrader.bat
```

`run_robotrader.bat` 가 하는 일(순서): `venv` 없으면 `python -m venv venv` → `venv\Scripts\activate.bat` → `pip install -r requirements.txt` → `config\key.ini` 존재 확인(없으면 `exit /b 1`) → `logs\` 생성 → `PYTHONIOENCODING=utf-8` · `SCREENER_SNAPSHOT_ENABLED=true` → `python -X utf8 main.py` 를 `logs\robotrader_template_YYYYMMDD_HHMMSS.log` 로 리다이렉트.

**`python main.py` 를 직접 치면 다르다:**

1. `bot/env_guard.py` 가 `sys.prefix` 가 프로젝트 `venv` 가 아니면 **exit 1** 한다(`ALLOW_FOREIGN_VENV=1` 이면 경고만). 시스템 파이썬·다른 venv 에서는 기동이 안 된다.
2. `SCREENER_SNAPSHOT_ENABLED` 가 없으면 `false`(`config/constants.py`) → 장 시작 후 최초 후보 로드 시(`bot/candidate_loader.py` → `liquidation_handler.run_screener_snapshot_hook`, scan_date=직전 거래일) 스냅샷이 생성되지 않아 **당일 후보가 없다**(소비자 `core/candidate_selector.py` 는 같은 직전 거래일 스냅샷을 DB 에서 읽을 뿐이라, 같은 날 다른 프로세스가 만든 스냅샷이 있으면 예외). 전 전략 0건이면 `bot/candidate_loader.py` 가 `[E6]` ERROR 를 찍고 거래량 순위 대체 풀로 떨어진다.
3. 콘솔 캡처 로그(`robotrader_template_*.log`)가 안 생긴다. `logs/trading_YYYYMMDD.log` 는 `utils/logger.py` 의 RotatingFileHandler(10MB × 7)가 따로 쓴다.

`main.py` 에 명령행 인자 처리(argparse)는 없다. 종료는 Ctrl+C(SIGINT/SIGTERM 핸들러).

## 5. 페이퍼 vs 실전

| | 페이퍼(현재) | 실전 |
|---|---|---|
| 스위치 | `config/trading_config.json` `"paper_trading": true` | `instances/<id>/trading_config.json` `"paper_trading": false` + **`"real_total_funds_cap"`(원) 필수** |
| 런처 | `run_robotrader.bat` | `run_instance.bat <id>`(`KIS_INSTANCE_DIR=instances\<id>`) |
| 주문 기록 | DB 시뮬레이션 `virtual_trading_records` | KIS 실주문 · `real_trading_<id>` |

`real_total_funds_cap` 이 없거나 0 이하면 `bot/initializer.py` 가 `LiveStartupAbort` 로 기동을 중단한다. 상세 → [instances/README.md](instances/README.md). 🔴 실전 전환은 현재 보류.

## 6. 전략 추가·교체

폴더를 복사하는 것만으로는 로드되지 않는다. `config/trading_config.json` `strategies[]` 에 `{name, enabled, max_capital_pct, regime_index, regime_gate}` 항목을 넣어야 `main._load_strategies()` 가 읽고, 후보 공급이 필요하면 `runners/_adapter_factory.py` 의 `if/elif` 에 어댑터를 등록해야 한다. 클래스명은 `Strategy` 로 끝나야 한다(`strategies/config.py`). Step-by-step → [docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md).

## 7. 문서 지도

| 문서 | 내용 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 개발 라우터 — 운영/연구 코드 경계, 데이터 SSOT, 규칙 |
| [docs/README.md](docs/README.md) | `docs/` 색인 + 명명·배치 규약 |
| [docs/PAPER_STRATEGIES.md](docs/PAPER_STRATEGIES.md) | 활성 8전략 허브 |
| [docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md) | 새 전략 작성·등록·테스트 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 레이어·모듈 관계 |
| [docs/TRADING_FLOW.md](docs/TRADING_FLOW.md) | 하루 타임라인(초기화 → 루프 → EOD) |
| [docs/DATABASE.md](docs/DATABASE.md) | 접속 · env · 표 인벤토리 · DDL 위치 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | key.ini · trading_config.json · config.yaml · env · 상수 |
| [docs/OWNERSHIP_MODEL.md](docs/OWNERSHIP_MODEL.md) | 포지션 소유권(전략 키잉) 모델 |
| [docs/code/MODULES.md](docs/code/MODULES.md) · [docs/CODE_MAP.md](docs/CODE_MAP.md) | 모듈 목록 · 운영/연구 경계 — 디렉토리 구조는 여기서 |

## ⚠️ 면책

교육·연구 목적의 소프트웨어다. 실제 투자 손실은 전적으로 사용자 책임이며, 과거 성과는 미래 수익을 보장하지 않는다.
