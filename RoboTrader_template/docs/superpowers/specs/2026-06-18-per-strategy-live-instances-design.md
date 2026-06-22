# 전략별 실전 인스턴스 (다계좌·다인스턴스·전략별 매매테이블) — 설계

- 작성일: 2026-06-18
- 상태: 설계 합의 완료 (구현 계획 대기)
- 관련 메모리: `review-2026-06-10-paper-to-real-readiness` (실전 전환 BLOCKING 2건), `design-2026-06-16-strategy-independent-positions` (페이퍼 전략 독립 포지션)

## 1. 배경 / 목표

페이퍼 8전략 중 누적 실현 상위 전략(rs_leader +700K 등)을 **실계좌로 전환**하려 한다.
단일 계좌·단일 인스턴스에서 다전략을 실전 운영하려면 06-10 검토에서 확인된 BLOCKING 2건
(① 실전 경로가 전략별 자본격리 미지원 — `execute_real_buy`에 strategy_name 미전달 →
단일 공유풀로 한 전략이 실계좌 자금 독식 가능 ② 전역 `paper_trading` 단일 스위치 →
혼합운영 불가)을 풀어야 한다.

**선택한 해법은 소프트웨어 격리가 아니라 물리적 격리(모델 3)다.** 전략마다
별도 계좌·별도 프로세스 인스턴스·별도 매매 테이블을 부여한다. 각 인스턴스는 단일
전략만 실행하므로 기존 코드가 이미 자본을 완벽히 격리하며(단일 전략 = 계좌 전체),
06-10의 BLOCKING은 "코드 문제"가 아니라 "배포 구성 문제"로 환원된다.

### 목표
- 한 코드베이스에서 환경변수로 설정을 분리해, 전략당 1개 실전 인스턴스를 띄울 수 있게 한다.
- 격리 3중: **계좌(돈) · 프로세스(실행) · DB 매매테이블(기록)**.
- 기존 페이퍼 인스턴스(8전략)는 무변경으로 병행 운영(하위호환).

### 운영 구성 (페이퍼 8 + 실전 4 공존)
- **페이퍼 인스턴스 1개**: 기존 그대로(8전략, `config/`, `paper_trading=true`,
  `virtual_trading_records`, source=`kis_template`). 무변경.
- **실전 인스턴스 N개(최대 4)**: 8전략 중 선정한 전략을 각각 별도 인스턴스로 추가 기동.
- 같은 전략이 페이퍼·실전 양쪽에서 **동시 실행**된다(독립 프로세스·계좌·테이블이라
  무충돌, 오히려 페이퍼↔실전 체결 비교 가능).

### 비목표 (드롭)
- `execute_real_buy` strategy_name 배선, FundManager 전략별 % 상한/독립풀 — 단일전략 인스턴스라 불필요.
- 별도 DB 생성 — 기존 `robotrader` DB 안에서 테이블만 분리.
- 단일 인스턴스 혼합모드(일부 실전+일부 페이퍼) — 전용 실전 인스턴스로 우회.
- 한 프로세스에서 다계좌 라우팅(모델 2) — 채택 안 함.

## 2. 확정된 설계 결정

| 항목 | 결정 |
|---|---|
| 운영 모델 | 전용 실전 인스턴스 — 전략당 1봇, 전부 실전(`paper_trading=false`) |
| 자본 격리 | 모델 3 — 다계좌 + 다인스턴스 (물리적) |
| KIS 계좌 | 계좌마다 별도 앱키/시크릿/계좌번호 |
| 배포 | 단일 코드 + `KIS_INSTANCE_DIR` 환경변수로 설정파일 분리 |
| DB | 기존 `robotrader` DB 유지. 전략별 **매매 테이블** 분리(`real_trading_<strategy>`). 시세(분봉/일봉)·후보·스크리너는 공유 |
| 격리 수준 | 계좌 + 프로세스 + 매매테이블 (3중) |

## 3. 아키텍처 — 설정 디렉토리로 인스턴스 식별

환경변수 `KIS_INSTANCE_DIR` 하나가 모든 분리를 구동한다. 미설정 시 기존
`config/` 사용 → **현 페이퍼 봇 완전 무영향(하위호환)**.

```
instances/rs_leader/
  ├── key.ini             # 이 계좌의 [KIS] APP_KEY/SECRET/ACCOUNT_NO + [TELEGRAM] token/chat_id
  └── trading_config.json # paper_trading=false, 활성전략 = rs_leader 단일
```

인스턴스 식별자(`instance_id`, 예: `rs_leader`)는 `KIS_INSTANCE_DIR`의 폴더명에서
도출한다. 이 식별자가 ① PID 파일명 ② 전략별 매매 테이블명 접미사를 결정한다.

데이터 흐름은 기존과 동일하다(`strategy.on_tick` → `ctx.buy/sell` →
`TradingDecisionEngine` → `OrderManager` → KIS API). 달라지는 것은 **어떤 설정·계좌·
테이블을 바라보는가**뿐이다.

## 4. 인스턴스별 주입 항목

| 자원 | 현재(전역/고정) | 변경 |
|---|---|---|
| 앱키·시크릿·계좌번호 | `config/key.ini` 고정경로 | `KIS_INSTANCE_DIR/key.ini` |
| 거래설정·활성전략·paper_trading | `config/trading_config.json` 고정경로 | `KIS_INSTANCE_DIR/trading_config.json` |
| 텔레그램 token/chat_id | `key.ini [TELEGRAM]` | 인스턴스 key.ini로 **자동 분리**(추가 작업 없음) |
| PID 파일 | `robotrader.pid` 고정(main.py:62) | `robotrader_<instance_id>.pid` |
| 매매 테이블 | `real_trading_records` 하드코딩(11곳) | `real_trading_<instance_id>` |
| 시세(분봉/일봉)·후보·스크리너 | `robotrader` / `robotrader_quant` 공유 | **공유 유지** |

## 5. 코드 변경 (최소)

### 5.1 `config/settings.py` — 설정 디렉토리 오버라이드
- `CONFIG_FILE`, `TRADING_CONFIG_FILE`를 `KIS_INSTANCE_DIR`(env) 있으면 그 디렉토리에서,
  없으면 기존 `config/`에서 로드.
- `instance_id`를 노출(예: `INSTANCE_ID = <KIS_INSTANCE_DIR basename> or "default"`).

### 5.2 `main.py:62` — PID 파라미터화
- `self.pid_file = Path(f"robotrader_{INSTANCE_ID}.pid")` (기본 인스턴스는 기존
  `robotrader.pid` 유지로 하위호환).

### 5.3 `db/repositories/trading.py` (+`db/database_manager.py`) — 매매 테이블명 파라미터화
- `TradingRepository.__init__`에 `real_table_name` 인자 추가(기본 `real_trading_records`).
- 하드코딩된 `real_trading_records` 11곳을 `self._real_table`로 치환(테이블명은 식별자
  화이트리스트 검증 후 SQL 조립 — SQL injection 방지, `^real_trading_[a-z0-9_]+$`).
- 부팅 시 `CREATE TABLE IF NOT EXISTS <real_table> (LIKE real_trading_records INCLUDING ALL)`로
  자기 테이블 보장(스키마는 기존 `real_trading_records` 복제).
- `virtual_trading_records`는 페이퍼 전용이라 **무변경**.

### 5.4 인스턴스 부팅 배선
- `DayTradingBot`/`BotInitializer`가 `INSTANCE_ID`를 `TradingRepository`에 전달해
  `real_trading_<instance_id>`를 쓰게 한다.

### 5.5 `.gitignore` — 실키 커밋 차단 (보안 BLOCKING)
- `instances/`(복수) 디렉토리를 `.gitignore`에 추가. 현재 `instance/`(단수)만 등록돼 있어
  `instances/<id>/key.ini`의 실계좌 앱키가 커밋될 수 있다. 코드 작업 전에 선반영한다.

## 6. DB 설계 — 전략별 매매 테이블

- 위치: 기존 `robotrader` DB(PostgreSQL 16.11 + TimescaleDB 2.24.0, :5433).
- 전략별 테이블: `real_trading_<instance_id>` (예: `real_trading_rs_leader`),
  스키마는 `real_trading_records`와 동일(`LIKE ... INCLUDING ALL`).
- 공유 유지: `minute_candles`(분봉), `robotrader_quant.daily_prices`(일봉, read-only),
  스크리너 스냅샷.
- 포지션·잔고의 권위 소스는 **KIS 계좌 직접조회**. DB 매매테이블은 기록·정산 보조.

### 공유 쓰기 지점 — `screener_snapshots` (수용, 무작업)
- 유니크 키 `(strategy, scan_date, params_hash, stock_code)` — 인스턴스 차원 없음.
- 같은 전략이 페이퍼·실전에서 동시 실행되면 같은 스냅샷 행을 쓰지만, **동일 로직 +
  동일 공유 유니버스라 내용이 동일** → 멱등적 덮어쓰기로 무해. config params가 다르면
  `params_hash`가 갈려 별도 행.
- 결론: 스키마에 instance 차원 추가는 과함. **현 스키마 그대로 수용.**

## 6-bis. 키 관리 / 보안 (인스턴스별 key.ini — 분산)

- 각 인스턴스가 자기 `key.ini`를 가진다: `instances/<instance_id>/key.ini`
  (`[KIS]` APP_KEY/SECRET/ACCOUNT_NO/HTS_ID + `[TELEGRAM]` token/chat_id).
  형식은 기존 `config/key.ini`와 동일 → `KIS_INSTANCE_DIR`로 자동 선택, 코드 무변경.
- **격리 이점**: 키 파일이 인스턴스와 함께 격리 → 한 키 유출/교체가 해당 계좌 1개에만 영향.
- **gitignore (필수)**: 현재 `.gitignore`는 `instance/`(단수)만 무시. **`instances/`(복수)
  디렉토리를 `.gitignore`에 추가**해 실키 커밋을 원천 차단한다. (이 한 줄 누락 시 실계좌
  앱키가 git에 올라갈 수 있음 — 보안 BLOCKING.)
- 키 백업은 repo 밖 안전한 곳(비밀번호 관리자/암호화 볼륨).
- `instances/<id>/key.ini.example` 템플릿 + 인스턴스 셋업 체크리스트 제공.

## 7. 검증 / 롤아웃 (실제 돈 — 보수적)

1. **실전 경로 e2e 사전검증**: `real_trading_records` 224행의 출처 확인(이 템플릿
   실거래분인지 형제 RoboTrader 것인지). 실주문 코드가 라이브로 안 돌았다면 검증을
   두껍게 — 모의계좌 또는 최소금액 실계좌로 매수→체결→손익절→EOD 전 경로 1회 통과.
2. **소액 1전략 먼저**: rs_leader(누적 1등 +700K) 단일 인스턴스로 시작 → 안정 확인 후 확대.
3. **점진 확대**: 검증된 패턴을 나머지 전략에 복제.

### 실전 대상 4개 전략 (확정)
누적 실현손익 상위 4개:
1. `rs_leader` (+700K) — 1순위, 소액 검증 시작
2. `book_pullback_ma5` (+344K)
3. `book_envelope_200d` (+344K)
4. `deep_mr_dev20` (+83K)

페이퍼는 8전략 전부 무변경 유지. 위 4개만 실전 인스턴스 추가.

## 8. 테스트 전략 (TDD)

- `settings`: `KIS_INSTANCE_DIR` 설정 시 해당 경로 로드 / 미설정 시 기존 `config/` (하위호환 회귀).
- `pid`: `INSTANCE_ID`별 PID 파일명 도출, 기본 인스턴스는 `robotrader.pid` 유지.
- `TradingRepository`: 커스텀 테이블명 주입 시 모든 쿼리가 그 테이블 사용 / 기본값 회귀 /
  테이블명 화이트리스트 거부 케이스 / `CREATE TABLE IF NOT EXISTS` 멱등성.
- 회귀: 기존 페이퍼 경로(`virtual_trading_records`, source='kis_template') 무영향 확인.

## 9. 리스크 / 미해결

- **실주문 경로 성숙도 미확정** — 가장 큰 리스크. 검증 1번으로 게이트.
- 다인스턴스 동시 가동 시 KIS rate-limit — 현 단일봇 0.08%로 여유 크나 N배 부하 모니터 필요.
- 스크리너 스냅샷/후보 테이블을 공유할 때 인스턴스 간 쓰기 충돌 여부(전략키로 분리되나
  동시성 확인 필요).
- 첫 실전 전략 선정은 사장님 확정 대기(권고: rs_leader).
