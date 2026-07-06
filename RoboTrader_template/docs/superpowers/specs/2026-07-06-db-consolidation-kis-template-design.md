# DB 통일 설계 — 봇 영속성을 kis_template 단일 DB로 (2026-07-06)

## 목표

라이브(페이퍼) 봇이 사용하는 **모든 영속 데이터를 `kis_template` 단일 Postgres DB로 통일**한다.
현재 3개 DB(`robotrader`=기본/운영+분봉, `robotrader_quant`=일봉, `kis_template`=신규 시장데이터 수집)로
분산돼 있고, 지난 며칠 병행 수집으로 `kis_template`에 시장데이터가 안정 적재됐다. 이제 봇 관점에서
`robotrader`/`robotrader_quant`를 은퇴시키고 `kis_template`만 읽고 쓴다.

부수 효과(이득): virtual/real 테이블이 형제 `robotrader` 봇과 물리 공유되던 것에서 **격리**됨
(유령 macd 오염원 차단).

## 현재 상태 (footprint 요약)

- **기본 풀** `DatabaseConnection`(`db/connection.py`, `TIMESCALE_DB`=`robotrader`): 운영 상태 + 장중
  시장데이터 읽기 전부. `db/repositories/*`가 여기로.
- **`KisDbConnection`**(`KIS_DB_NAME`=`kis_template`): 시장데이터 수집 write + `signals/foreign_flow` read.
- **`QuantDailyReader`**(`resolve_daily_source_db()`): `KIS_DATA_SOURCE=legacy`면 `robotrader_quant`,
  `new`면 `kis_template`. 스크리너 유니버스 + 진입 일봉.
- **활성 운영 테이블**(기본 풀=robotrader): `virtual_trading_records`(source='kis_template') ·
  `real_trading_records`/`real_trading_{instance}` · `paper_trading_state` · `paper_strategy_equity` ·
  `candidate_stocks` · `screener_snapshots`.
- **비활성/dormant**(활성 8전략 미사용, 이관 대상 아님): `quant_factors` · `quant_portfolio` ·
  `financial_data` · `vkospi_daily` · `signals/vkospi` · `strategies/historical_data`(예제 전략 전용) ·
  `strategy_analysis` DB · `trading_records`(레거시) · `composable_*`(라이브 미존재).

## 목표 아키텍처

통일의 본질은 **경로별 코드 수술이 아니라 기본 연결 재지정**이다. 운영 상태 + 장중 시장데이터가 모두
기본 풀 하나를 타므로:

```
kis_template에 운영 테이블 신설(스키마) + 운영 데이터 이관  →  env 2개 플립  →  재기동
    TIMESCALE_DB=kis_template   (기본 풀이 kis_template을 봄: 운영 read/write + 장중 일/분봉 read)
    KIS_DATA_SOURCE=new         (QuantDailyReader도 kis_template, EOD 교차 reconcile는 자동 skip)
```

싱글턴 풀이 dbname을 최초 1회 바인딩하므로 env 변경은 **프로세스 재기동**으로 발효(다음 07:40 부팅).

## Phase A — 스키마 패리티 (저위험, 동작 무변경)

`kis_template`에 운영 테이블을 idempotent DDL(`CREATE TABLE IF NOT EXISTS`)로 신설. 원천 = robotrader의
`init-scripts/01-init.sql` + `tools/paper_strategy_equity._ensure_table`(현재 ad-hoc DDL을 스키마로 승격).

대상 테이블(컬럼·인덱스·제약 정확 복제):
- `virtual_trading_records` (`source`, `is_test`, `target_profit_rate`, `stop_loss_rate`, `buy_record_id` 포함)
- `real_trading_records` + 동적 `real_trading_{instance}` 생성 경로(`ensure_real_table`)
- `paper_trading_state`
- `paper_strategy_equity` (스키마로 승격)
- `candidate_stocks`
- `screener_snapshots` (jsonb `params_json`/`metadata`)

`scripts/kis_db/schema.py`의 `EXPECTED_TABLES`/`DDL_STATEMENTS`에 추가. **DELETE/retention 금지.**

## Phase B — 데이터 이관 + 검증 (중위험: 연속성)

### B1. 운영 데이터 복사 (우리 행만)
robotrader → kis_template. 형제 봇 데이터 오염 방지:
- `virtual_trading_records`: **`WHERE source='kis_template'`만** 복사.
- `real_trading_records`/`real_trading_{instance}`: 우리 인스턴스 테이블만.
- `paper_trading_state` · `candidate_stocks` · `screener_snapshots`: 전량(우리 봇 소유).
- `paper_strategy_equity`: 파생/멱등이므로 컷오버 후 재생성 가능(복사 선택).
- 멱등 UPSERT, PK/유니크 보존. **연속성 핵심** = 열린 포지션(open) + 현금 원장 재구성 근거(BUY/SELL gross) 무손실.

### B2. 시장데이터 정합 검증 (플립 안전성 게이트)
kis_template vs 현 라이브 소스, **경로별**:
- 일봉: kis_template.daily_prices vs robotrader_quant.daily_prices (전종목, 최근 N일 + 룩백 200일);
  커버리지·컬럼(`market_cap`·`trading_value`) 존재/일치 확인.
- 분봉: kis_template.minute_candles vs robotrader.minute_candles (최근 거래일 표본).
- **게이트 기준 = "제로 diff"가 아니라 "모든 diff가 설명됨"**: 분할조정 차이(예: 001130)는 kis_template이
  더 정확한 개선이므로 통과 사유. 미설명·무작위 불일치 → 중단·조사.

### B3. 상태복원 스모크 (격리 worktree, 라이브 트리 금지)
`TIMESCALE_DB=kis_template`로 설정한 격리 환경에서 `StateRestorer` 경로 실행 → 열린 포지션·전략별 현금원장·
후보가 robotrader 기준과 동일 복원되는지 대조.

## Phase C — 숨은 갭 수정

1. **regime 지수**: `core/regime/index_refresh`가 KOSPI/KOSDAQ를 `daily_prices`(index_daily 아님)에서 R/W.
   kis_template.daily_prices에 지수행이 있는지 확인 → 없으면 regime write 경로가 kis_template에 지수를 쓰게
   보장(또는 index_daily 참조로 배선). 플립 후 regime 게이트가 stale 안 되도록.
2. **daily_prices 이중쓰기**: `PostMarketDataSaver.save_daily_data`(후보 일봉)와 collector(전종목)가 둘 다
   kis_template.daily_prices에 UPSERT하게 됨 → 멱등 확인, 충돌 없음 검증.
3. **하드코딩 DB 참조**: collector들의 `reconcile_*`가 robotrader/quant를 하드코딩(raw psycopg2). 컷오버 후
   reconcile은 `KIS_DATA_SOURCE=new`에서 skip되므로 무해하나, 코드/주석에 명시.

## Phase D — 컷오버 + 롤백

1. Phase A–C 브랜치 구현(격리 worktree, TDD) → 리뷰 → 머지(사장님 결재).
2. Phase B2/B3 검증 실행 → 게이트 통과 → 결재.
3. **장 마감 후** 프로덕션 `.env`: `TIMESCALE_DB=kis_template` + `KIS_DATA_SOURCE=new` 설정 →
   **다음 07:40 재기동 시 발효**(장중 전환 금지 규칙).
4. 첫날 부팅·매매·EOD 관찰(포지션 복원·자금정합·데이터수집·equity).
5. **롤백 = `.env` 두 줄 되돌림 + 재기동**(코드 롤백 불필요). 이관 데이터는 additive라 잔존.

## 리스크 & 완화

| 리스크 | 완화 |
|---|---|
| 열린 포지션/현금 연속성 유실 | B1 무손실 복사 + B3 상태복원 스모크로 사전 검증 |
| 형제봇 공유행 오염 | source='kis_template'/인스턴스 테이블만 이관 |
| regime 지수 stale | Phase C1에서 지수 경로 보장 |
| daily_prices 이중쓰기 충돌 | Phase C2 멱등 검증 |
| kis_template 시장데이터 커버리지 부족 | B2 게이트에서 커버리지·컬럼 확인 |
| 장중 전환 사고 | 장마감 후 env만 변경, 다음 부팅 발효 |

## 범위 밖 (이관하지 않음)
- dormant: quant_factors·quant_portfolio·financial_data·vkospi_daily·signals/vkospi·historical_data·
  strategy_analysis·trading_records. (비활성 확인됨. 필요 시 별도 후속.)
- 형제 `robotrader` 봇의 데이터·수집(우리 범위 아님).
- 옛 DB의 물리적 삭제(은퇴는 "봇이 안 씀"까지; drop은 안전기간 후 별도 결정).

## 테스트/작업 격리
모든 구현·테스트·스모크는 **git worktree**(`D:/GIT/kis-consolidate`)에서. 라이브 트리는 코드 읽기만.
(메모리 규칙: 라이브 트리에서 테스트/스모크 실행 금지, 장중 브랜치전환 금지.)

## 첫 구현 범위
writing-plans는 **Phase A + B**부터(선행·저위험). C/D는 후속 계획.
