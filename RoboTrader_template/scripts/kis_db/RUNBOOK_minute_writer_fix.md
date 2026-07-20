# RUNBOOK — minute_candles 중복 봉 근본수정 배포

봉의 자연키를 `(stock_code, datetime)` 로 확정하고 재수집 중복을 DB 레벨에서
영구 차단하는 3-파트 변경의 **배포 절차**. 유지보수 창(수집기 정지)에서만 수행.

- **Part 1** `collectors/minute_writer.py` — INSERT 의 `ON CONFLICT` 대상을
  `(stock_code, trade_date, idx)` → `(stock_code, datetime)` 로 변경.
- **Part 2** `scripts/kis_db/dedup_minute_candles.sql` — 기존 중복 정리(무손실 보존).
- **Part 3** `scripts/kis_db/create_minute_candles_unique_index.sql` —
  `UNIQUE(stock_code, datetime)` 인덱스 생성.

접속 대상은 항상 **kis_template DATABASE** (`psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template`).
테이블은 public 스키마 — `kis_template.` 스키마 접두사를 붙이지 말 것("kis_template"=DB명).

---

## 왜 이 순서여야 하는가 (불변식)

1. 새 writer 의 `ON CONFLICT (stock_code, datetime)` 은 **정확히 그 컬럼들의
   UNIQUE/exclusion 제약이 런타임에 존재**해야 동작한다. 없으면 Postgres 가
   `there is no unique or exclusion constraint matching the ON CONFLICT specification`
   (SQLSTATE 42P10) 로 즉시 실패.
2. `UNIQUE(stock_code, datetime)` 인덱스는 **중복이 남아 있으면 생성 자체가 실패**한다.
3. UNIQUE 인덱스가 존재하는데 **옛 writer** 가 돌면, 재수집 봉이 인덱스를 위반해
   **collector 크래시**(2026-07-08 봇 사망과 동형).

∴ 유일하게 안전한 순서 = **정리 → 인덱스 → 새 writer → 재기동**. 아래 STEP 순서 고정.

---

## 사전 점검 (STEP 0)

- [ ] 유지보수 창 확보(장 마감 후, 다음 수집 사이클 이전).
- [ ] 배포 브랜치 `bugfix/minute-writer-datetime-key` 가 main 대비 3커밋(Part 1~3)임을 확인:
      `git log main..bugfix/minute-writer-datetime-key --oneline` → 3줄.
- [ ] DB 백업 여유 공간 확인(정리분은 `minute_candles_dupes` 로 복제 보존됨).
- [ ] 현재 중복 규모 파악(참고):
      ```sql
      SELECT count(*) FROM (
        SELECT 1 FROM minute_candles WHERE datetime IS NOT NULL
        GROUP BY stock_code, datetime HAVING count(*) > 1
      ) d;   -- 중복 키 수
      ```

## STEP 1 — 모든 write 경로 STOP (수집기 **및** 봇/EOD 스케줄러)

minute_candles 에 INSERT 하는 경로는 **둘**이다 — 둘 다 반드시 정지한다.
하나라도 옛 writer 로 남아 UNIQUE 인덱스(STEP 3) 존재 중에 돌면
재수집 봉이 인덱스를 위반해 **크래시**(2026-07-08 봇 사망 class).

- [ ] **분봉 수집기** (`collectors/minute_collector.py` → `df_to_minute_rows`/`replace_minute_day`)
      프로세스 정지(장중 실행 금지).
- [ ] **봇 프로세스 / system_monitor EOD 스케줄러** 정지 —
      `bot/system_monitor.py` 의 `_handle_postmarket_tasks` → `_run_data_collection`
      → `replace_minute_day` 가 **15:35 트리거**로 도는 **두 번째 insert 경로**다.
      "분봉 수집기만" 멈추고 봇/EOD 스케줄러를 켜둔 채로 두지 말 것.
- [ ] 정지 확인(위 두 프로세스 모두 없음). minute_candles 에 신규 write 가 없어야 함.
- **중단/롤백**: 여기서 중단하면 아무 변경도 없음. 프로세스 재기동으로 원복.

## STEP 2 — 중복 정리 (Part 2)

```
psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template \
     -f scripts/kis_db/dedup_minute_candles.sql
```

- [ ] 검증 (1): `losers_identified == backup_rows` (무손실).
- [ ] 검증 (2): `remaining_dup_keys = 0`.
- [ ] 두 조건 만족 시에만 스크립트 말미의 `COMMIT;` 주석을 해제하여 커밋
      (혹은 psql 세션에서 직접 `COMMIT;`). 불만족이면 `ROLLBACK;`.
- **중단/롤백**:
  - COMMIT 전이면 `ROLLBACK;` — 변경 없음.
  - COMMIT 후 되돌리려면(예: STEP 3 실패로 전체 취소 결정):
    ```sql
    INSERT INTO minute_candles SELECT * FROM minute_candles_dupes
      ON CONFLICT DO NOTHING;   -- 아직 UNIQUE 인덱스 생성 전이어야 안전
    ```
    그 후 `TRUNCATE minute_candles_dupes;` (원한다면).

## STEP 3 — UNIQUE 인덱스 생성 (Part 3)

```
psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template \
     -f scripts/kis_db/create_minute_candles_unique_index.sql
```

- [ ] CONCURRENTLY 이므로 **단독 실행**(트랜잭션 블록 밖 — 파일에 BEGIN 없음).
- [ ] 검증:
      ```sql
      SELECT indisvalid, indisunique
      FROM pg_index WHERE indexrelid = 'idx_minute_candles_code_datetime'::regclass;
      -- 기대: indisvalid = t, indisunique = t
      ```
- **중단/롤백**:
  - 실패(대개 STEP 2 미완으로 잔여 중복) 시 인덱스가 INVALID 로 남을 수 있음 →
    `DROP INDEX CONCURRENTLY IF EXISTS idx_minute_candles_code_datetime;`
    후 STEP 2 재점검 → 재시도.
  - ⚠️ **이 시점(인덱스 존재) 이후에는 절대 옛 writer 로 수집기를 켜지 말 것** —
    재수집 봉이 인덱스를 위반해 크래시. 반드시 STEP 4 를 먼저 완료.

## STEP 4 — 새 writer 코드 배포 (Part 1)

- [ ] `bugfix/minute-writer-datetime-key` 를 main 에 merge(또는 FF) 하고 라이브
      트리에 반영. `collectors/minute_writer.py` 의 `_INSERT` 가
      `ON CONFLICT (stock_code, datetime) DO NOTHING` 인지 라이브 트리에서 최종 확인.
- [ ] (라이브 트리에서 테스트 실행 금지 규칙 준수 — 코드 배치만.)
- **중단/롤백**: writer 를 옛 버전으로 되돌리려면, 반드시 **먼저** STEP 3 인덱스를
  DROP 한 뒤 되돌린다(인덱스+옛 writer 조합은 크래시 위험).

## STEP 5 — 수집기 재기동

- [ ] 새 writer 가 배치된 상태에서 수집기 재기동.
- **중단/롤백**: 이상 시 수집기 STOP → (필요하면) STEP 4→3 역순으로 롤백.

## STEP 6 — 사후 점검 (post-check)

- [ ] 재수집 무중복 확인 — 임의 종목 하루치를 강제 재수집시킨 뒤:
      ```sql
      SELECT stock_code, datetime, count(*)
      FROM minute_candles WHERE datetime IS NOT NULL
      GROUP BY stock_code, datetime HAVING count(*) > 1 LIMIT 5;
      -- 기대: 0 행
      ```
- [ ] collector 로그에 `ON CONFLICT` / unique 위반 에러가 없는지 확인.
- [ ] 정상 세션(수집 사이클 1회)이 에러 없이 완주하는지 확인.
- [ ] 며칠 관찰 후 이상 없으면 `minute_candles_dupes` 백업 처리 방침 결정
      (즉시 삭제 금지 — 어느 행이 "참"인지 미판정이므로 최소 관찰기간 보존).

---

## 빠른 롤백 매트릭스

| 도달 단계 | 되돌리는 법 |
|---|---|
| STEP 1 후 | 수집기 재기동(변경 없음) |
| STEP 2 COMMIT 전 | `ROLLBACK;` |
| STEP 2 COMMIT 후 | `minute_candles_dupes` 에서 원복(INSERT ... ON CONFLICT DO NOTHING) |
| STEP 3 후 | `DROP INDEX CONCURRENTLY ... idx_minute_candles_code_datetime` |
| STEP 4 후 | **먼저** 인덱스 DROP → 그 다음 writer 원복 |
| STEP 5 후 이상 | 수집기 STOP → STEP 4→3 역순 롤백 |
