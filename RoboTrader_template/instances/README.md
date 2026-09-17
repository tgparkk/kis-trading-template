# 실전 인스턴스 셋업

> 🔴 **실전(실주문) 전환은 현재 보류 상태다.** 라이브는 페이퍼 8전략 봇 한 대뿐이며, 아래는 전환을 재개할 때의 절차다(감사·보류 근거 → [docs/audit_2026-09-14_real_trading_switch.md](../docs/audit_2026-09-14_real_trading_switch.md)).

전략당 1개 실전 인스턴스. `run_instance.bat <id>` 가 `KIS_INSTANCE_DIR=instances\<id>` 를 설정하면 `config/settings.py` 의 `resolve_instance_id()` 가 폴더 basename 을 소문자·`[a-z0-9_]` 로 정규화해 인스턴스 id 로 삼고, `resolve_config_dir()` 가 설정 디렉토리를 그 폴더로 바꾼다. 아래 **5중 분리**가 전부 이 id 로 결정된다.

## 5중 분리 (`run_instance.bat` 헤더 · `config/settings.py`)

| 항목 | 페이퍼(기본, id=`default`) | 실전 인스턴스 `<id>` | 결정 함수 |
|---|---|---|---|
| 계좌 키 · 거래 설정 | `config/key.ini` · `config/trading_config.json` | `instances/<id>/key.ini` · `instances/<id>/trading_config.json` | `resolve_config_dir()` |
| 프로세스 PID | `robotrader.pid` | `robotrader_<id>.pid` | `main.pid_file_name()` |
| KIS 토큰 캐시 | `token_info.json` | `token_info_<id>.json` | `token_file_name()` |
| 로그 | `logs/` | `logs/<id>/` (+ bat 콘솔 캡처 `robotrader_<id>_YYYYMMDD_HHMMSS.log`) | `log_dir_name()` · bat |
| 실거래 원장(DB 표) | `real_trading_records` | `real_trading_<id>` | `real_trading_table_name()` |

DB 는 페이퍼와 같은 **`kis_template`**(포트 5433) 하나다 — 분리되는 것은 표 이름이지 DB 가 아니다. 텔레그램 `[TELEGRAM]` 절도 인스턴스의 `key.ini` 에서 읽는다(`core/telegram_integration.py` 가 `settings.CONFIG_FILE` 을 쓴다).

## 필수 파일 (`instances/<id>/`)

| 파일 | 내용 | 없으면 |
|---|---|---|
| `key.ini` | `[KIS]` **그 계좌의** 앱키/시크릿/계좌번호/HTS ID + `[TELEGRAM]` | `run_instance.bat` 가 기동 전 중단 |
| `trading_config.json` | `"paper_trading": false` · `strategies[]` 에서 해당 전략 **1개만** `enabled: true` · **`"real_total_funds_cap": <원>`** | cap 이 없거나 0 이하면 `bot/initializer.py` 가 `LiveStartupAbort("실전 총자금 상한 미설정")` 로 기동 중단 |

예제는 `instances/rs_leader/` 의 `key.ini.example` · `trading_config.json.example` 두 개뿐이다. ⚠️ 예제 `trading_config.json.example` 에는 **`real_total_funds_cap` 줄이 없다** — 복사한 뒤 직접 추가해야 첫 기동이 된다. `paper_trading` 은 `false`, `rs_leader` 만 `enabled: true` 로 돼 있다.

## 절차

1. `instances/<id>/` 생성. `<id>` 는 `default` 금지(`resolve_instance_id()` 가 `ValueError`) — 전략 폴더키와 같게 두는 것이 관례(`rs_leader`).
2. `key.ini.example` → `key.ini`, `trading_config.json.example` → `trading_config.json` 복사 후 위 표대로 편집(`real_total_funds_cap` 추가 포함).
3. `run_instance.bat <id>` — 페이퍼 봇과 **같은 `venv`** 를 쓴다(없으면 먼저 `run_robotrader.bat` 로 생성). bat 는 `PYTHONIOENCODING=utf-8` 과 `SCREENER_SNAPSHOT_ENABLED=false` 로 기동한다: 스냅샷 «생성»은 페이퍼 봇 한 대가 맡고 실전 인스턴스는 «소비»만 한다(같은 날짜 스냅샷을 둘이 덮어쓰면 후보가 갈린다).
4. 첫 기동 시 `db/repositories/trading.py` 가 `CREATE TABLE IF NOT EXISTS real_trading_<id>` 로 원장 표를 만든다.

## 검증

- `robotrader_<id>.pid` 생성 · `logs/<id>/` 에 로그 · `token_info_<id>.json` 생성
- KIS 계좌 잔고 = 해당 전략 단독 운용
- `SELECT count(*) FROM real_trading_<id>` 로 원장 격리

## 보안 (`.gitignore`)

- `RoboTrader_template/.gitignore` 는 `instances/*` 를 제외하고 `instances/README.md` 와 `instances/*/*.example` 만 되살린다 — 실 `key.ini`·`trading_config.json` 은 커밋되지 않는다(레포 루트 `.gitignore` 도 같은 두 파일을 이중 제외). 추적 파일은 README + 예제 2개 = 3개뿐.
- 키 백업은 레포 밖(비밀번호 관리자/암호화 볼륨).
