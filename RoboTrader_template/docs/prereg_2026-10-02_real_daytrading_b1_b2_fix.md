# 사전등록 — 실전 daytrading 인스턴스 결함 B-1(후보 출처)·B-2(익절선) 수정 (2026-10-02)

> 상태: **구현 전 동결**(이 커밋이 코드 커밋보다 먼저) · 대상 = `instances/daytrading/` 실전 인스턴스(10-19 시작)
> 근거 결정 = 사장님 10-02 밤 「B-1·B-2 둘 다 10-19 전 수정」 · 결함 근거 = `D:/research-archive/real_daytrading_setup_20261002/SETUP_REPORT.md` §5·§8
> 원칙 = **페이퍼 8전략(INSTANCE_ID `default` · `paper_trading: true`) 동작 0 변경** — 6주 룰 동결 실험(~10-16) 중

## ① 무엇이·왜 (기준 = `main` `f7c3903`)

**B-1 후보 출처가 페이퍼와 다르다.** `bot/candidate_loader.py:71` `len(strategies) > 1` 일 때만 스냅샷 표(`screener_snapshots`) 경로.
1전략 인스턴스는 `:77` `load_from_screener`(`data/screener_*.json` · 최신 04-02 → 항상 없음) → `:99` 거래량 순위 폴백(시총 필터 없음 · 5,000원 이상).
페이퍼 daytrading 매수 56.9%(33/58)가 5,000원 미만이라 실전 후보에 구조적으로 못 든다.
그냥 `>= 1` 로 바꾸면 ⓐ 페이퍼가 D-1 스냅샷을 09:00 직후 쓰는데(아래 ③) 인스턴스 첫 로드도 09:00:0x 라 경합하고,
ⓑ 다중 경로의 「전 전략 0건 → 거래량 폴백」(`:186-228`)이 1전략에선 경합 한 번 = 폴백이 된다.
또 다중 경로는 섹터뉴스 재정렬 기록(`sector_news_rerank_log` · PK `(trade_date, strategy, stock_code)` UPSERT · `db/repositories/sector_news.py:30-42`)을 써서
**인스턴스가 페이퍼의 그날 daytrading 행을 덮어쓴다** ⇒ 그 경로를 그대로 탈 수 없다.

**B-2 익절선이 다르다.** 실전 매수 `core/trading_decision_engine.py:493-511` 는 tp/sl 을 `TradingStock` 에 안 넣는다
(넣는 3순위 블록 `:598-621` 은 가상 전용) → 기본값 `core/models.py:178-179` = `config/constants.py:125-126` **+15%/−10%**(페이퍼 +10%/−10%).
실원장엔 tp/sl 컬럼이 없어(`db/repositories/trading.py:486-501`) 복원(`bot/state_restorer.py:848-859`)도 기본값 →
`:405-418` 은 «둘 다 기본값일 때만» 보유 7거래일+ 를 **±5%** 로 조인다 ⇒ 실전만 조여진다.

## ② 목표 동작

**판별자 = `config.settings.INSTANCE_ID != "default"`**(`paper_trading` 아님). 근거: 경합은 «스냅샷을 만드는 프로세스(default·
`SCREENER_SNAPSHOT_ENABLED=true` `run_robotrader.bat:89`)» 와 «소비만 하는 프로세스(`run_instance.bat:55` false)» 사이에서 생긴다.
default 가 실전이어도 같은 호출 안에서 스스로 스냅샷을 먼저 만든다(`candidate_loader.py:56-60`) — 경합 없음. 기존 인스턴스 게이트
(`bot/system_monitor.py:286-316` · `candidate_loader.py:92`)도 같은 판별자. ⇒ 페이퍼 프로세스는 설정과 무관하게 새 분기에 못 들어온다.

- **B-1** 인스턴스는 전략 수와 무관하게 전략마다 «페이퍼와 같은» `CandidateSelector._fetch_candidates_for_strategy`(D-1 스냅샷 1~20위 → 안전필터 → 목표 `max_candidates`)로 읽는다.
  단 섹터뉴스 재정렬은 **건너뛴다**(DB 쓰기 0 · 현행 모드 `shadow` 는 원래 순서를 돌려주므로 결과 동일). 거래량 폴백·`load_from_screener`·`candidate_stocks` 저장 **호출 0**.
  - 대기·재시도: 첫 시도에 그 전략의 D-1 행이 없으면 **10초 간격 재확인 · 상한 15분**(첫 시도 기준). 대기는 **메인 루프를 막지 않는다** —
    `_candidates_loaded=True` 로 장시작 콜백은 1회만 부르고(daytrading `on_market_open` 이 `daily_trades=0` 리셋 · 매수·매도 체결 둘 다 센다
    `strategy.py:110-111,150-151` — 반복 호출하면 대기 중 매도 체결 카운트가 지워져 페이퍼와 캡이 갈린다), `main.py` 루프가 `elif` 한 줄로 재확인을 이어 간다. 보유 감시(손절·익절·max_hold)는 대기 중에도 매 반복.
  - **fail-closed**: 15분까지 없으면 그 전략은 그날 신규 후보 0 + ERROR `[B1-실전]` + 텔레그램 `notify_error`(기존 경보 경로). 폴백 없음. 보유 매도 감시는 계속.
- **B-2** 실전 매수 직전 `TradingStock` 에 소유 전략 `config.yaml` 의 tp/sl(가상 3순위와 같은 해소 `_pct` 우선 · `_ratio` 폴백)을 넣는다.
  실전 복원은 실원장 tp/sl 이 NULL 일 때 소유 전략 config 값 → 없으면 종전 기본값. 실원장 **스키마 변경 0**.
  daytrading 은 0.10/0.10 ≠ 기본값(0.15/0.10) ⇒ 7거래일+ ±5% 조임이 **안 걸린다**(페이퍼와 같은 조건식).

## ③ 수치 고정 근거 (DB SELECT · 10-02)

`screener_snapshots` daytrading 행 생성 시각, scan_date 08-03~10-01 **41거래일 전부 09:00:05~09:00:35**(09:01 넘은 날 0 · 행 수 8~46 · 0행인 날 0).
인스턴스 첫 로드는 장 열림 감지(장전 30초 슬립) 뒤 09:00:00~09:00:30 ⇒ 정상 대기 ≲ 65초. **10초** = 출현 뒤 지연 ≤10초 · 로컬 SELECT 1건(KIS 호출 0).
**15분** = 정상 최악의 약 14배 + 페이퍼 늦은 기동·재기동 흡수 · 페이퍼 daytrading 첫 on_tick 도 09:02~09:10(틱 희석)이라 그 안의 진입은 페이퍼와 같은 창.
그 이상은 고장(페이퍼 다운·DB·훅 실패) — 사람에게 알리는 쪽이 낫다.
⚠️ 「0행」은 「페이퍼 미생성·지연」과 「그날 통과 0건」(0건이면 페이퍼는 행을 안 쓴다 `runners/screener_snapshot_collector.py:137-146`)을 못 가른다 → 진짜 0건 날은 15분 뒤 경보가 «오경보»지만 결과(후보 0)는 페이퍼와 같다.

## ④ 페이퍼 영향 0 — 판정 기준 (전부 충족해야 머지 권고)

1. **정적**: 새 동작은 ⓐ `INSTANCE_ID != "default"` 분기 안, ⓑ 가상 모드가 도달하지 않는 호출부(`execute_real_buy` ← `bot/trading_analyzer.py` 실전 else ·
   `_build_db_holdings_by_owner` ← `_restore_holdings_from_real_account` ← `paper_trading=false`)에만 있다. 공용 함수의 새 인자는 기본값이 종전 동작.
2. **테스트(신규)**: (i) 1전략+인스턴스 → 스냅샷 경로 · 늦게 생김 → 재시도 성공 · 끝내 없음 → 후보 0 + 경보 1 + 폴백·JSON 호출 0 · 재정렬 호출 0
   (ii) 8전략 default → `select_candidates_per_strategy` 1회 · 종전 인자 · 대기 상태 False · 새 메서드 호출 0
   (iii) 실전 매수 → tp 0.10/sl 0.10 · 실전 복원 → 같은 값 · 7거래일+ 조임 미적용 (iv) 가상 매수·가상 복원 → 종전 값(조임 조건 포함) 그대로.
3. **회귀**: `f7c3903` 기준선 대비 실패 «집합» 양방향 차분 = 새 실패 0. 예외로 미리 적는 것 = `tests/test_live_min_fix_set_20260915.py`
   `TestI3…::test_instance_logs_error_on_volume_fallback`(「인스턴스 폴백 유지」를 고정한 테스트 — 이번 결정이 그 전제를 뒤집으므로 «폴백 0» 단언으로 바꾼다 · 대칭 default 테스트는 그대로).
4. `ruff check .` 0 · 기존 `tests/test_main_loop.py` 무수정 통과.

## ⑤ 롤백·발효·하지 않는 것

- 롤백 = 코드 커밋 `git revert`(이 문서는 남김) · 다음 07:40 재기동부터. 페이퍼는 어느 쪽이든 무영향.
- 발효 = 사장님 머지 승인 → 머지 뒤 다음 07:40(봇 가동 중 머지는 재기동 때 발효). 실전 첫 적용 = 10-19(10-05·10-06 검증 체크리스트 수정 목록은 구현 보고서).
- 하지 않는 것: 전략 룰·`config.yaml` 값 · 실원장 컬럼 추가 · 감사 P1-5/6/7 · P2-19 · `tick_trace`/`holiday_kis_cache.json` 공유 ·
  「[PAPER]」 오표기 · LOOP_INTERVAL · 페이퍼 경로의 리팩터. 인스턴스에서 도달 불가가 되는 `[E6-실전]` 블록(`candidate_loader.py:83-97`)은 지우지 않는다.
- 남는 위험(미리 적음): `SECTOR_NEWS_BOOST_MODE=live` 로 바꾸면 인스턴스(재정렬 생략)와 페이퍼 후보 «순서»가 갈린다 — 그때 재검토.
  페이퍼가 그날 안 뜨면 실전도 신규 매수 0(의도된 fail-closed · 종전엔 거래량 순위로 샀다).
