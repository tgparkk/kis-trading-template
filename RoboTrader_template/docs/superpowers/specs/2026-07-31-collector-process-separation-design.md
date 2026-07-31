# EOD 데이터 수집 단일 실행 보장 (수집 프로세스 분리 1단계) — 설계

- 작성일: 2026-07-31 (독립 검증 2건 반영 재작성)
- 상태: 설계 합의 완료 (구현 계획 대기)
- 선행 설계: [`2026-06-18-per-strategy-live-instances-design.md`](2026-06-18-per-strategy-live-instances-design.md) — 계좌·프로세스·매매테이블 3중 격리 (구현 완료, `1bb073b`)
- 관련 메모리: `changelog-2026-07-31-eod-monitoring`, `changelog-2026-07-29-fund-manager-ledger-desync`

> **범위 주의**: 이 설계는 "수집 프로세스가 EOD 시장 데이터를 단독 수집한다"까지만 다룬다.
> 스크리너 스냅샷 생성 이관·정산(equity) 이관은 **§9에서 명시적으로 범위 밖**으로 분리했다.
> 초안은 이 셋을 함께 옮기려다 차단 결함 3건을 만들었고, 독립 검증에서 전부 반증됐다.

## 1. 배경

06-18 설계로 전략당 1계좌·1프로세스·1매매테이블 격리가 구현·머지됐다(`KIS_INSTANCE_DIR` 환경변수 하나로 key.ini·trading_config·토큰·로그·PID·매매테이블 분리). `instances/rs_leader/`는 설정까지 배치돼 있고 기동만 하지 않은 상태다.

그러나 **실전 인스턴스를 N개 띄우면 EOD 데이터 수집이 N중으로 실행된다.**

### 확인된 사실 (2026-07-31, 독립 검증 2건 교차 확인)

| 항목 | 확인 내용 | 근거 |
|---|---|---|
| EOD 수집에 게이트 없음 | `system_monitor.py:303`이 `_run_data_collection()`을 **조건 없이** 호출. 오케스트레이터 `run_data_collection`(`collectors/eod_collection.py:30`) 자체에도 게이트 없음 | 코드 |
| `SCREENER_SNAPSHOT_ENABLED` 게이트는 **두 곳**에 존재 | `system_monitor.py:520`(검증) + `liquidation_handler.py:582`(생성 훅 본체). **게이트가 없는 것은 `_run_data_collection` 하나뿐** | 코드 |
| 실전 런처가 그 env를 켬 | `run_instance.bat:54` → `SCREENER_SNAPSHOT_ENABLED=true` | 코드 |
| 분봉 수집이 destructive | `collectors/minute_writer.py:52-58` DELETE→INSERT. 단, **단일 트랜잭션 + `ON CONFLICT DO NOTHING`**(:15)이라 MVCC 하에서 "빈 데이터 읽힘"이나 중복행은 발생하지 않는다 | 코드 |
| N중 실행의 **실제** 위험 | ① 한쪽이 **부분 fetch**하면 완전한 하루를 DELETE하고 잘린 데이터를 넣는다 — **조용한 절단** ② KIS API 이중 부하(300종목 × N) ③ 동일 행 락 대기로 작업시간 증가 | 코드 분석 |
| 분봉은 **자가치유되지 않음** | `collectors/minute_collector.py:26-38` — `target_date` 하루만 fetch. 다음날 실행이 전날을 메우지 않는다. 반면 일봉은 `daily_collector.py:36` `lookback_days=7`로 자가치유 | 코드 |
| 수집 규모 | 일봉 2,592종목 18,060행 · 분봉 300종목 112,969행 · 지수 · 수급 2,592종목 24,080행 · **소요 25분** | 07-31 EOD 로그 |
| 후보 선정은 DB 기반 | `candidate_selector._fetch_candidates_for_strategy`가 `screener_snapshots`를 **D-1 날짜로** 조회 | 코드 + 07-31 09:00:16 로그 |

**결론**: 파괴적 쓰기(분봉)가 복구 불가능한 데이터에 가해지고, 그 실행에만 게이트가 없다. 여기에 단일 실행을 강제하는 것이 이 설계의 목표다.

### 초안에서 반증된 서술 (기록 보존)

| 초안 서술 | 실제 | 영향 |
|---|---|---|
| 분봉 N중 실행 시 "경합 구간에서 빈 데이터가 읽힌다" | MVCC라 발생 안 함. 실제 위험은 부분 fetch 절단 | 결론(단일 실행 필요)은 유효, 논거 교체 |
| 인용한 테스트 주석이 N중 실행 위험을 말한다 | 그 주석은 **휴장일 T-1 응답** 시나리오 | 근거 철회 |
| `MAX_CANDIDATES_PER_STRATEGY` 상한 = 10 | **20** (`constants.py:143`). 실효 10은 `trading_config.json`의 `strategy.parameters.max_candidates` | 부하 계산 재산출 |
| 전략 부하 = 15종목/30초 = 제한의 2.5% | `interval_seconds`는 **죽은 설정** — 소비자 `data_collector.start_collection()`의 호출부가 0건. 라이브는 `main.py:402` `LOOP_INTERVAL = 3`초 루프 | §2 비목표 근거 수정 |
| `SCREENER_SNAPSHOT_ENABLED`가 검증에만 걸림 | 생성 훅에도 걸림 | §1 표 정정 |

전략 프로세스의 정확한 장중 부하는 실측 재산출이 필요하다(§10-⑩). 다만 **이 설계의 판단은 부하 수치에 의존하지 않는다** — 근거는 파괴적 쓰기의 복구 불가능성이다.

## 2. 목표 / 비목표

### 목표
- **EOD 시장 데이터 수집을 정확히 한 프로세스에서만 실행되게 한다.** 설정 실수가 있어도 강제되어야 한다.
- 실전 인스턴스가 안전하게 N개 뜰 수 있는 전제조건을 갖춘다.
- 기존 페이퍼 봇 동작은 무변경으로 보존한다.

### 비목표 (이번 범위 밖 — §9에 근거)
- **스크리너 스냅샷 생성 이관** — 생성 훅이 매매 루프 생명주기에 묶여 있어 배선 재설계가 선행돼야 한다.
- **정산(equity) 이관** — `run_daily_equity_snapshot`이 `virtual_trading_records` 전용이라 실계좌 replay 엔진 신설이 선행돼야 한다.
- **`_run_regime_index_refresh` 이관** — 호출부가 EOD와 장전 둘이라 게이팅 범위가 모호하다.
- 전략 프로세스가 시세를 공유 저장소에서 읽는 구조 — 매매 판단의 즉시성을 해친다.
- 페이퍼 봇을 전략별로 쪼개기 — 8전략이 한 원장을 공유하는 편이 비교·분석에 유리하다.
- 매매 테이블 통합(단일 테이블 + `strategy` 컬럼) — §9 참조.

## 3. 확정된 설계 결정

| 항목 | 결정 |
|---|---|
| 프로세스 구성 | 수집 1 + 페이퍼 1 + 실전 N |
| 역할 구분 | `trading_config.json`의 `role` — `"collector"` / `"trader"` / 미지정 |
| **`role` 기본값** | **`INSTANCE_ID == "default"`면 현행 동작, 그 외에는 `trader` 강제** (fail-safe) |
| **미지 값 처리** | `{None, "collector", "trader"}` 외의 값이면 **부팅 거부** |
| 게이트 대상 | **`_run_data_collection` 단독** (스크리너·정산·regime은 현행 위치 유지) |
| 최종 방어선 | `run_data_collection` 진입에 **PostgreSQL advisory lock** — 설정이 틀려도 DB가 단일 실행을 강제 |
| 수집 프로세스 진입점 | `main.py` 수집 전용 모드 |
| 수집 프로세스 계좌 | 전용 계좌·앱키 신설. **`paper_trading: false` 강제** |
| 매매 테이블 | 전략별 분리 유지 (`real_trading_<instance_id>`) |

### 진입점을 `main.py`로 하는 이유 (근거 교체)

초안은 "별도 진입점이 휴장일 게이트를 복제한다"를 근거로 들었으나 **이는 성립하지 않는다** — 게이트 없는 독립 수집 진입점이 이미 7개 존재한다(`collectors/{daily,minute,index,foreign_flow,corp_events,split_factor_infer}_collector.py`, `runners/screener_snapshot_collector.py`). 휴장일 게이트의 호출부는 `system_monitor.py:255` 단 하나이고, 위 7개는 지금도 무방비다.

**진짜 복제 비용은 부팅 배선이다**:
- `.env → os.environ` 부트스트랩 순서 제약 (`main.py:22-26`, "반드시 config/db import 보다 먼저")
- `env_guard.assert_correct_environment` (`main.py:680-681`) — 2026-06-30 sibling venv 사고 방어
- `KIS_INSTANCE_DIR` → 토큰/PID/로그/테이블 규약 (`config/settings.py:58-65`)
- `broker.connect()` + KIS 휴장일 동기화 (`main.py:689-694`)

이 중 하나라도 빠지면 06-30 계열 사고가 재발한다. 별도 진입점의 비용은 게이트 1줄이 아니라 이 배선 전체다.

**대가**: `main.py` 경로는 전략·매매·주문 컴포넌트를 전부 끌고 온다. 이 대가는 §3의 `paper_trading: false` 강제와 §7.5 가드로 방어한다.

## 4. 아키텍처

```
┌──────────────────────────────────────────────────────┐
│ 수집 프로세스 ×1   role=collector, paper_trading=false │
│  · EOD 일봉·분봉·지수·수급 수집       15:35~16:00     │
│    (advisory lock 보유 — 단일 실행 강제)               │
└──────────────────────────────────────────────────────┘
                        ↓ 쓰기
┌──────────────────────────────────────────────────────┐
│ 공유 저장소  PostgreSQL :5433 / kis_template          │
│  daily_prices · minute_candles · index_daily          │
│  foreign_flow · screener_snapshots                    │
└──────────────────────────────────────────────────────┘
                        ↓ D-1 후보 읽기
┌───────────────┬───────────────┬──────────────────────┐
│ 페이퍼 봇      │ rs_leader     │ …                    │
│ role=trader   │ role=trader   │ role=trader          │
│ 8전략·공용계좌 │ 계좌 A        │ 계좌 N               │
│ · 매매 · 스크리너 스냅샷 생성 · 정산 · 자금검증        │
│ · EOD 시장데이터 수집만 하지 않음                      │
└───────────────┴───────────────┴──────────────────────┘
```

전략 프로세스는 서로를 모른다. 수집↔전략의 유일한 인터페이스는 `screener_snapshots`를 **D-1 날짜로** 읽는 것이며(`candidate_selector`), 하루 단위 비동기 결합이라 **기동 순서 제약이 없다**. 수집이 늦어도 전략은 D-1 데이터로 정상 동작한다.

## 5. 역할별 책임

| 하는 일 | collector | trader | 근거 |
|---|---|---|---|
| EOD 일봉·분봉·지수·수급 수집 | **O** | X | 파괴적 쓰기 — 단일 실행 필수 |
| 스크리너 스냅샷 생성 | X | **O** | 훅이 매매 루프 안(`candidate_loader.py:48`)에 있어 collector는 도달 불가 |
| `_run_regime_index_refresh` | X | **O** | 호출부가 EOD와 장전 둘. 장전 갱신은 regime 게이트 stale 방지에 필수 |
| equity 정산 (`_run_equity_snapshot`) | X | **O** | `_resave_paper_trading_state`가 in-process 잔고를 요구 — §9 참조 |
| 자금 정합성 검증 · 일일 리포트 | X | **O** | 자기 계좌 기준 |
| 매수·매도·손절·청산 주문 | X | **O** | 계좌를 가진 쪽만 |
| 매매기록 DB 저장 | X | **O** | 자기 `real_trading_<id>`만 |

collector가 하는 일은 **EOD 시장 데이터 수집 하나뿐**이다. 이것이 초안 대비 가장 큰 변경이며, 차단 결함 3건이 여기서 해소된다.

## 6. 코드 변경

### 6.1 역할 스위치 — `config/settings.py` + `core/models.py`
- `trading_config.json`에 `role` 키. 값: `"collector"` | `"trader"` | 미지정.
- **기본값**: `INSTANCE_ID == "default"` → 현행 동작(하위호환, 대상은 페이퍼 봇 1개) / 그 외 → **`trader` 강제**.
- **미지 값이면 부팅 거부.** `core/models.py:369-375` `TradingConfig.from_json`이 미지의 키를 **조용히 버리므로**(`"roles"` 오타 등이 무경고로 "미지정"이 된다) 값 검증을 명시적으로 넣는다.
- `role == "collector"`인데 `paper_trading == true`이면 **부팅 거부**.

### 6.2 수집 전용 모드 — `main.py`
- `role == "collector"`이면 `_load_strategies`(`main.py:134`)·`_allocate_strategy_capital`(:135)을 건너뛰고, `run_daily_cycle`의 3개 태스크 중 `_main_trading_loop`을 기동하지 않는다.
- 분기는 3곳 이내로 제한한다.

### 6.3 수집 게이트 — `bot/system_monitor.py`
- **`_run_data_collection` 호출(:303)만** `role != "collector"`이면 skip.
- 나머지 EOD 단계(리포트·자금검증·스크리너 검증·regime·equity)는 **손대지 않는다.**
- collector에서는 이 단계들이 빈 결과로 돌게 되므로(§10-⑪ 노이즈), 로그 레벨만 조정한다.

### 6.4 최종 방어선 — advisory lock
- `collectors/eod_collection.py:30` `run_data_collection` 진입에서 `pg_try_advisory_lock(<고정키>, <trade_date>)`.
- 획득 실패 시 **수집을 건너뛰고 WARNING**. 설정이 잘못돼 두 프로세스가 동시에 도달해도 **DB가 단일 실행을 강제**한다.
- 이것이 §2 목표("설정 실수가 있어도 강제")의 실질 보증이다. `role` 게이트는 1차 방어, lock이 2차.

### 6.5 실전 다전략 부팅 거부 가드
2026-07-31 확인: 1계좌 1전략은 json 설정 관례일 뿐 코드가 강제하지 않는다. `_allocate_strategy_capital`의 `can_allocate`가 `is_virtual` 게이트 안에 있어(`initializer.py:71-74`) **실전 모드에서는 전략별 자금 격리가 아예 작동하지 않는다**.

실전 인스턴스에서 활성 전략이 2개 이상이면 **부팅을 거부**한다.

⚠️ **위치 주의**: `_allocate_strategy_capital` 전체가 `try/except Exception → warning + return`으로 감싸여 있어(`initializer.py:65, 121-123`) 그 안에서 raise하면 **부팅 거부가 아니라 경고 1줄**이 된다. `main._load_strategies`도 광범위 흡수하며 `StrategyConfigError`만 재전파한다(`main.py:198-204`). 따라서 가드는 **`StrategyConfigError`를 던지거나** 이 try 블록 **바깥**에 놓아야 한다.

### 6.6 인스턴스 스코프 누락 보정 (프로세스 N개 이전 필수)
`config/settings.py:51-55 log_dir_name`이 인스턴스별 로그 디렉토리를 제공하는데 두 곳이 이를 쓰지 않는다:
- `bot/initializer.py:362-365` — `logs/state/fund_state_<date>.json` (인스턴스 접두사 없음). `daily_realized_loss`·`total_funds`·포지션 런타임 상태를 담으므로 N개 인스턴스가 종료 시 **서로 덮어쓴다.**
- `main.py:369` — `TickTracer(base_dir=Path("logs/tick_trace"))` 하드코딩.

06-18의 "3중 격리"에 난 구멍이며, 프로세스를 늘리기 전에 막는다.

### 6.7 배포 자산
- `instances/collector/key.ini.example`, `instances/collector/trading_config.json.example` (`role: "collector"`, `paper_trading: false`, 전략 전부 `enabled: false`).
- `instances/README.md`에 수집 인스턴스 셋업 절차 추가.
- ⚠️ 루트 `.gitignore:47-48`이 `instances/*/key.ini`와 **`instances/*/trading_config.json`을 함께** 무시한다. `role` 키가 미추적 파일에 사는 셈이므로 **§11 회귀 테스트가 실제 배포 설정을 검증할 수 없다** — example 파일 기준으로만 검증 가능함을 명시한다.

## 7. 전환 순서 / 롤백

**전환은 휴장일 또는 주말에 수행한다.**

거래일 전환은 창이 15:00 청산 후 ~ 15:35 EOD 전 **35분뿐**이고, 실패하면 §10-⑧에 걸려 그날 분봉을 영구히 잃는다. 휴장일에는 EOD 게이트(`system_monitor.py:255`)가 전 항목을 스킵하므로 **겹침(→절단)과 틈(→누락) 리스크가 둘 다 0**이고 창이 이틀로 늘어난다.

| 단계 | 작업 | 게이트 |
|---|---|---|
| 0 | 수집용 계좌 개설 · 앱키 발급 | **사장님 실물 작업 (선행조건)** |
| 1 | `paper_trading_state` · `paper_strategy_equity` **백업** | 롤백을 설정 되돌림이 아니라 상태 복구로 만든다 |
| 2 | 코드 배포 (`role` 스위치 · advisory lock · 가드 · 6.6 보정) | 배포만으로는 동작 무변경(페이퍼 봇은 `INSTANCE_ID=default`) |
| 3 | `instances/collector/` 구성 — **`role: "collector"` 명시 후** 단독 기동 검증 | 주문 API 호출 0건 · 전략 로드 0건 |
| 4 | 페이퍼 봇에 `role: "trader"` 지정 → 페이퍼 봇과 수집 프로세스 함께 기동 | **휴장일 수행** |
| 5 | 첫 거래일 EOD 검증 | 수집 로그가 collector에서만 1회 · 중복봉 0 · 분봉 행수 정상 · advisory lock 경합 로그 0 |
| 6 | rs_leader 실전 인스턴스 투입 | §10-① 실주문 경로 검증 통과 후 |

**롤백**: 페이퍼 봇의 `role` 키 제거 + 수집 프로세스 정지. 단계 1의 백업이 있어야 상태까지 복구된다.

⚠️ **롤백 데드라인**: 거래일에 롤백하는 경우 15:35 이전에 완료해야 한다. 15:35~15:59 창을 넘기면 그날 수집이 양쪽 모두에서 누락된다(§10-⑧).

## 8. 검토했으나 채택하지 않은 것

### 8.1 매매 테이블 통합 (단일 테이블 + `strategy` 컬럼)
`real_trading_records`에 `strategy` 컬럼이 이미 있고, 페이퍼는 `virtual_trading_records` 단일 테이블로 8전략을 정상 운영 중이다. 통합하면 페이퍼↔실전 비교가 같은 쿼리로 가능해진다.

**현행 분리를 유지한다** — 이미 구현·테스트(5개 파일) 완료된 구조를 되돌리는 비용 대비 이득이 작다. `real_trading_rs_leader`가 0행이라 **지금이 뒤집기 가장 싼 시점**이라는 점은 기록해 둔다. **페이퍼↔실전 비교를 상시 운영 지표로 쓰게 되면 재검토 대상.**

### 8.2 스크리너 스냅샷 생성 이관 (초안에서 철회)
생성 훅의 실제 경로는 `main.py:419`(매매 루프) → `candidate_loader.py:48` → `liquidation_handler.py:575`다. `liquidation_handler.py:341-343` 주석에 이유가 있다 — *"스냅샷 생성은 EOD가 아니라 장전 최초 후보 로드 시점으로 이전됨: 당일 일봉이 ~15:35 적재되므로 15:00 EOD 시점엔 빈 유니버스가 된다"*.

수집 프로세스는 매매 루프를 켜지 않으므로 **훅 도달 경로가 0**이다. 초안대로 게이팅했다면 생성 주체가 사라져 전 전략 후보 0건 → 매수 정지로 이어졌다.

**이관하려면** `run_screener_snapshot_hook`을 매매 루프에서 떼어 장전(08:40경) 태스크로 재배치하는 별도 작업이 선행돼야 한다. `runners/screener_snapshot_collector.py:62`의 `out or list(ALL_STRATEGIES)` 폴백 덕분에 수집 config에서 전략을 전부 꺼도 전 전략 스냅샷이 생성되므로, **배선만 하면 동작은 한다.** 별도 설계로 분리한다.

### 8.3 정산(equity) 이관 (초안에서 철회)
`_run_equity_snapshot`(`system_monitor.py:316-350`)은 두 조각이 한 함수에 묶여 있다:
- `_resave_paper_trading_state()`(:332) — **in-process `virtual_balance`를 읽는다**(전략 프로세스 소유)
- `run_daily_equity_snapshot(conn)`(:335) — DB만 읽는다

통째로 이관하면 두 갈래로 깨진다:
- 수집이 `paper_trading=true`면 자기 D-1 이월 잔고(`virtual_trading_manager.py:87-90`)로 `paper_trading_state`를 덮어쓴다. 이 테이블은 **`trade_date` 단일 키**(`db/repositories/trading.py:690-701`)라 인스턴스 차원이 없어 **당일 손익이 이월에서 증발**한다 — 2026-07-29 `fund_manager` desync와 같은 클래스.
- `paper_trading=false`면 재저장이 조기 return되어 **2026-06-23 stale-cash 버그가 회귀**한다. 존재 이유가 `system_monitor.py:327-331` 주석에 명시돼 있다 — *"15:00~15:30 position_monitor 손절이 virtual_balance를 갱신해도 재저장되지 않아 stale → equity 리플레이와 현금 불일치(2026-06-23 033780 손절 +344,726)"*.

**추가로**, 정산 엔진이 실계좌를 읽지 못한다. `tools/paper_strategy_equity.py:146-151`의 유일한 소스는 `virtual_trading_records`이고, 자본 기준선이 `DEFAULT_CAPITAL = 10_000_000`(:33) 고정이며, UPSERT 키가 `(trade_date, strategy, source)`(:263)라 실전 행이 **페이퍼 곡선을 덮어쓴다**.

**이관하려면** ① 함수를 소유권 축으로 분해(resave는 trader, replay는 collector) ② replay 엔진의 실계좌 확장 ③ `source` 축을 인스턴스별로 분기 — 세 가지가 선행돼야 한다. 별도 설계로 분리한다.

## 9. 미해결 / 리스크

### 우선순위 1 — 실전 투입 전 반드시 해소

**① 실주문 경로가 라이브로 검증된 적 없음** (06-18 §9-1 승계, 최대 리스크)
`real_trading_records` 224행(2026-03-05~06-08)은 출처 미확인이며, `strategy` distinct 값이 **123개**로 상위값이 `스크리너: 시가+3.9%, 등락+3.9%, 점수65` 같은 **선정 사유 문자열**이다 — 전략명이 아니다. 이 템플릿 실거래분인지 형제 프로젝트 것인지 확인이 선행돼야 한다. 검증은 모의계좌 또는 최소금액 실계좌로 매수→체결→손익절→EOD 전 경로 1회 통과.

**② KIS 유량 제한의 단위 미확인**
`config/constants.py:28` 주석은 "1초당 20건"이라고만 적고 단위(앱키/계좌/IP)를 명시하지 않는다. **공식 문서 확인 필요.** 참고: `config/settings.py:44-48 token_file_name`이 이미 인스턴스별 토큰 캐시를 분리하므로, 앱키가 다르면 07-31에 겪은 EGW00133(동시 재발급 경합) 재발 가능성은 낮다. 남는 미지는 IP 단위 여부다.

### 우선순위 2 — 이 설계로 해결되지 않는 것

**③ 종목 합산 노출을 아무도 집계하지 않음**
2026-07-31 실측: `319400`을 두 전략이 합계 2,910,150원 보유하다 같은 날 같은 가격에 손절(합 −273,350원). 계좌 분리 후에는 총 노출을 보는 주체가 없다. **계좌 분리는 이 문제를 해결하는 것이 아니라 은폐한다.**

**④ 같은 명의 다계좌 동시 반대매매의 자전거래 소지**
2026-07-31 `319400` 두 슬롯이 `09:05:10` **같은 초에** 체결된 사례가 있어 실제 발생 가능하다. **증권사·거래소 확인 필요.**

**⑤ 일일 리포트가 인스턴스 스코프가 아님**
`tools/daily_trading_summary.py`는 `virtual_trading_records`만 읽는다. 실전 인스턴스 N개가 각자 **페이퍼 봇의 매매 요약**을 출력한다. 돈이 새지는 않으나 **실전 인스턴스가 아무것도 못 하고 있어도 리포트는 정상으로 보인다** — 침묵을 은폐한다. 실전 투입 전 정정 필요.

### 우선순위 3 — 이번 설계에 반영하되 완전 해소는 아님

**⑥ 수집 프로세스의 단일 실패점**
수집이 죽으면 그날 시장 데이터가 빈다. 완화: 일봉·수급·equity는 자가치유되나 **분봉만 영구 손실**이다(`minute_collector.py:26-38`).

**⑦ EOD 실행 창이 15:35~15:59뿐이고 캐치업이 없음** — 초안의 완화 논거 정정
`system_monitor.py:235`가 `if current_time.hour == 15 and current_time.minute >= 35:`이므로 **16:00 이후 기동한 프로세스는 그날 아무것도 하지 않는다.** 래치 `_last_daily_report_date`는 리포트 성공 직후 설정되고(:270) 그 **이후** 수집이 실패하면(:303-305 예외 흡수) 같은 날 재시도가 없다. 래치가 in-memory라 재기동이 유일한 재시도 수단인데 그 창이 25분이고 수집 자체가 25분이다.

**→ 15:40에 수집이 죽으면 그날 분봉은 사실상 회수 불가.** 초안의 *"멱등이라 다음 거래일에 재계산된다"* 는 **equity에만 참이고 시장 데이터에는 거짓**이다.

필요 조치(이번 범위에 포함): 수집 미실행 탐지 경보 + **수동 백필 절차 문서화**. 근본 해소(EOD 진행상태 DB 영속화 `eod_run_log(trade_date, step, status)` + 진입 창을 시간 범위로 확대)는 별도 작업.

**⑧ 휴장일 게이트가 파괴적 연산에서 먼 곳에 있음**
게이트 호출부는 `system_monitor.py:255` 하나뿐이고, 게이트 없는 독립 수집 진입점이 7개 존재한다. 게이트를 `run_data_collection` 또는 `replace_minute_day` 진입으로 **하강**시키면 진입점 개수와 무관해지고 기존 7개 CLI도 함께 보호된다(수동 백필용 override 플래그 필요). advisory lock과 같은 자리에 두면 함께 구현 가능하다. **이번 범위에 포함 권장.**

**⑨ EOD 스크리너 스냅샷 "3일 연속 0건"은 결함이 아님** (초안 §10-⑨ 철회)
두 층위 모두 사실로 확인됐다:
- 생성이 EOD가 아니라 장전으로 이전됨 (`liquidation_handler.py:341-343`) — **의도된 동작**
- 검증 쿼리가 `scan_date = CURRENT_DATE`인데 훅은 D-1로 저장(`system_monitor.py:535` vs `liquidation_handler.py:595`) — **구조적으로 항상 0건**

실행 항목은 "실패 원인 조사"가 아니라 **"검증 쿼리를 D-1 기준으로 정정"**이다.

**⑩ 전략 프로세스 장중 부하 미측정**
`interval_seconds`가 죽은 설정이므로 초안의 2.5% 계산은 무효. `_log_system_status`의 `total_calls` 실측으로 재산출한다. 이 설계의 판단에는 영향 없으나 §2 비목표 근거와 N 확장 판단에 필요하다.

**⑪ collector의 EOD 노이즈**
§6.3이 `_run_data_collection`만 게이팅하므로 collector에서도 리포트·자금검증·스크리너 검증이 돈다. 거래 0건 계좌의 빈 리포트가 매일 발생하고, `_verify_screener_snapshot`은 `_snapshot_done_date=None`이라 매일 WARNING을 낸다. **자금 경보의 신호대잡음비를 해치므로 로그 레벨 조정 필요.**

## 10. 테스트 전략

- **역할 분기 진리표**: `collector` → 전략 로드 0·매매 루프 미기동·수집 실행 / `trader` → 전략 로드·수집 skip / 미지정 + `INSTANCE_ID=default` → 현행 무변경(회귀) / 미지정 + 비default → `trader`로 강제 / **미지 값 → 부팅 거부**.
- **`role=collector` + `paper_trading=true` → 부팅 거부.**
- **advisory lock**: 두 프로세스가 동시 진입 시 한쪽만 수집 수행, 다른 쪽은 WARNING 후 skip. 락 해제 후 재획득 가능.
- **다전략 가드**: 실전 + 활성 2전략 → 부팅 거부 / 실전 + 1전략 → 통과 / 페이퍼 + 8전략 → 통과(회귀).
- **인스턴스 스코프**: `fund_state_*.json`·`tick_trace`가 인스턴스별 경로로 분리되는지.
- **회귀**: 페이퍼 경로(`virtual_trading_records`, source=`kis_template`, 8전략 자금 할당, 스크리너 생성, equity 적재) 무영향.

⚠️ **가드의 판별력은 변이 주입으로 실측한다** — 2026-07-29 교훈: 회귀 방지 가드가 baseline에서 공허참이라 판별력이 0이었던 사례가 있다. 다전략 가드와 role 검증은 **가드를 제거했을 때 실제로 실패하는지** 확인한다. 특히 §6.5의 위치 문제(try/except 흡수) 때문에 이 검증이 필수다.

⚠️ **실전 경로는 페이퍼에서 회귀 검증이 불가능하다** — 실전 분기가 휴면이라 "판별력 없는 통과"가 된다. §9-① 실주문 검증이 실질 게이트다.

⚠️ **`.gitignore`가 `instances/*/trading_config.json`을 무시**하므로 테스트는 example 파일 기준으로만 실제 배포 설정을 검증할 수 있다(§6.7).
