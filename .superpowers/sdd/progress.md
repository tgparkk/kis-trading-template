# 장중 급락 후 반등 발굴 — 진행 원장

- 계획: docs/superpowers/plans/2026-07-09-intraday-rebound-discovery.md
- 브랜치: feat/intraday-rebound-discovery
- 워크트리: D:/tmp/wt-intraday-rebound  (라이브 트리 D:\GIT\kis-trading-template 접촉 금지)
- 게이트: Task 4 (스펙 2.2절 재현). 실패 시 중단·사용자 보고.

## 사전 검토 수정 (실행 전)
- Task 2: `_fallback_ohlcv` 중복 제거 → groupby(floor) 단일 구현 + 라이브 변환기 동등성 테스트 추가
- 전역: 계획서의 실행 경로 26곳을 라이브 트리 → 워크트리로 교체
- Global Constraints: 워크트리 격리·시스템 파이썬 명시

## 태스크
- Task 1: complete (commits 6c2e0f1..d143819, review clean)
  - 유니버스 199종목 독립 재확인. readonly 세션이 CREATE TEMP TABLE 거부 확인.
  - 리뷰 Important 1건(캐시 stale) → 사장님 결정으로 캐시 전면 제거(d143819).
  - Minor(미수정, 최종리뷰서 재검토): read_sql 커서 close 미보장(연결close로 무해),
    min_coverage float 경계비교, 캐시 원자성(N/A - 제거됨), SQL ORDER BY + python sorted 중복.
- Task 2: complete (commits d143819..8691e5e, review clean)
  - 11 passed. 드리프트 감시(tf=3/5/15)로 라이브 TimeFrameConverter와 OHLCV 동일 확인
    → 스펙 2.2절의 floor(epoch/180) 임시 SQL 버킷 경계도 같았다는 방증.
  - 리뷰 Important 2건 수정(8691e5e): ①정렬 안된 입력이 open/close를 행순서로 집계(라벨 뒤집힘)
    → mergesort 선행정렬 ②빈 입력 object dtype이 concat시 숫자컬럼 오염 → 명시 dtype.
  - Minor(미수정): test_partial_bucket이 open/close/low/volume/amount 미검증(cosmetic).
- Task 3: complete (commits 8691e5e..2cb1875, review clean — opus 리뷰, 인덱스 산술 독립 재현)
  - 21 passed. prior_high가 t 제외, mae가 첫 up-hit에서 절단(이후 저점 무시),
    hit_down이 hit_up과 독립, 잘린 창에서 hit_close만 NaN — 4개 핵심 semantics 전부 검증됨.
  - 리뷰어 ⚠️ 크로스태스크 항목(drop_pct=0.0이 전 봉을 안 잡는다) → 관리자가 해소:
    reproduce.py는 is_candidate를 쓰지 않고 drop_pct_actual로 사후 버킷팅하므로 무영향. 갭 아님.
  - Minor(미수정, 최종리뷰 재검토): ①출력이 입력 index 미보존(resample이 RangeIndex라 무해)
    ②mae의 close[t] 나눗셈 errstate 미가드 ③test_no_window_crosses_session_boundary가 길이만 검사(오명명).
- Task 4 (1차): FAIL — 게이트가 스펙 2.2절 최초 표의 오류를 잡아냄.
  임시 SQL이 워밍업 미제외+정규장 필터 부재로 표본 15% 부풀림. 진단 SQL(두 결함만 수정)이
  파이프라인과 12/12 일치 → 파이프라인이 맞고 스펙이 틀렸음 확정.
  사장님 결정: 개장 60분을 버리지 말되 절대 섞지 말 것 → Task 3b 신설.
  스펙 정정 커밋 20d3f56, 계획 갱신 커밋 아래.
- Task 3b: complete (commit 1c604f2) — 26 passed. min_lookback_min=15, lookback_bars_used/is_full_lookback.
  개장 60분 딥드롭 17,337건 회수. 기존 10테스트 무수정(공유 P의 min_lookback_min=6만 조정).
- Task 4: PASS (commits 7f31159 + spec) — 8셀 x 3지표 24/24 독립 진단 SQL과 소수점까지 일치.
  full: no_drop 1.100 / shallow 1.014 / mid 1.018 / deep 1.348 (얕은 둘 다 베이스라인 미만)
  partial: 1.083 -> 1.102 -> 1.214 -> 1.233 (단조증가)
  반올림 버그 수정 확인(no_drop 1.103 -> 1.100).
- Task 3b/4 fix (commit 31f110b): is_valid 컬럼 + inf 가드. 28 passed.
  게이트 재실행 → 24/24 동일 유지 확인 (is_valid 도입이 결과 불변).
  LOW 미수정(최종리뷰 재검토): reproduce 스킵가드가 짧은 종목-일 허용(전방창 절단, 진단SQL과 일치하므로 무영향).
- Task 3b + Task 4: complete, review clean (opus). 게이트 PASS.
- Task 5: complete (commits f713af5..647fec3) — 36 passed.
  누수 가드 실증됨(리뷰어가 close.shift(-1) 주입 → 테스트가 잡음).
  계획서 자기모순(consec_down: 구현 close<open vs 테스트 close<prev_close) → 테스트 채택, 문서 정정.
  리뷰 Important 1건 수정(647fec3): _bars_since_prior_high 의 np.argmax 가 shift(1) NaN 을
  최대값으로 골라 drop_speed 를 drop_pct/(t+1) 시간대 아티팩트로 오염. 개장 구간 전체 영향.
  → nanargmax + -inf 마스크. 정답 [nan,1,1,1,2,3,1,2] 재현 테스트 2개 추가.

## 중단 지점 (2026-07-10, 사장님 지시로 다음 세션 이어서)

**완료:** Task 1, 2, 3, 3b, 4(게이트 PASS), 5. 36 passed. 커밋 647fec3 (+ledger 8762b1e).
**미착수:** Task 6(랭킹), Task 7(모양 프로브), Task 8(데이터셋 빌드+리포트).

### 재개 절차
1. `cd D:/tmp/wt-intraday-rebound` (워크트리 살아 있음, 브랜치 feat/intraday-rebound-discovery)
   라이브 트리 D:\GIT\kis-trading-template 는 main. 절대 건드리지 말 것.
2. `python -m pytest tests/discovery/intraday_rebound/ -q` → 36 passed 확인
3. Task 6부터. brief: scripts/task-brief docs/superpowers/plans/2026-07-09-*.md 6

### Task 8 착수 전 반드시 해결할 것 (미해결 블로커)
실측: 라벨러만 10.7시간 (144격자 x 65,670 종목-일 x 3 TF). 특징/DB/parquet 포함 20시간+.
07:40 라이브 봇과 CPU 경쟁 → 그대로 돌리면 안 됨.

구조적 낭비 2건 (계획서 Task 8 코드에 있음):
- compute_features 는 (TF, N) 에만 의존하는데 격자점마다(144회) 재계산됨 → 종목-일당 9회면 충분
- compute_labels 가 prior_high 를 매 격자점 재계산 (역시 (TF,N) 의존)
- D(하락폭)는 순수 필터라 라벨 재계산 불필요. 실제 window pass 는 TF x N x M x theta = 108

권장: (a) (TF,N) 루프 바깥에서 prior_high/features 1회 계산 (b) 격자를 N=60 고정,
theta={fixed 3%, 1.5xATR} 로 축소(432 -> 72) (c) 1차 결과 보고 필요한 격자만 확장.
사장님 미결정 상태. 다음 세션 첫 질문으로 올릴 것.

### 최종 리뷰 때 재검토할 미수정 Minor
- read_sql 커서 close 미보장(연결 close 로 무해)
- reproduce 스킵가드가 짧은 종목-일 허용(전방창 절단; 진단 SQL 과 일치하므로 무영향)
- labeler 출력이 입력 index 미보존(resample 이 RangeIndex 라 무해)
- mae 의 close[t] 나눗셈 errstate 미가드
- test_no_window_crosses_session_boundary 가 길이만 검사(오명명)
- test_partial_bucket 이 open/close/low/volume/amount 미검증
- _bars_since_prior_high 동점 시 가장 오래된 고점 선택(의도적, docstring 기재됨)

## first-touch (삼중배리어) 분석 — 멀티버스 착수 판정 (2026-07-10)
커밋 06d5c32 (분석) + 850562d (리뷰수정). 49 passed. opus 리뷰 APPROVE.

2026-06, 199종목, TF=3, N=60, D=4%, M=60, TP/SL ±3%:
  full    n=20286  up 17.45 / down 12.89 / ambiguous 0(raw) / none 69.66(평균 -0.07%)
                   gross +0.09%  breakeven 0.09%
  partial n=17337  up 21.76 / down 17.46 / ambiguous 0(raw) / none 60.78(평균 -0.23%)
                   gross -0.01%  (비용 전에 이미 음수)

- 독립측정(17.76/13.18) vs 선착측정(17.45/12.89) 차이 0.3%p, 전부 재분류로 설명(24건).
  → 1.348 비대칭은 실재. double-touch 아티팩트 아님. ambiguous raw count = 0 (독립검증).
- 왕복비용 0.21% (config/constants.py:118-119: 수수료 0.015%x2 + 거래세 0.18%).
  총기대값 0.09% < 0.21% → 순 -0.12%/거래.
- 게다가 gross 는 상한: 진입가 close[t](실제는 다음봉 시가), TP/SL 정확체결 가정(SL 갭쓰루 무시),
  슬리피지 0. 실제는 더 나쁨.

**판정: 대칭 배리어로는 엣지 없음. 멀티버스 착수 부적격.**
다음 후보 2개(둘 다 멀티버스보다 훨씬 쌈):
  (a) 비대칭 배리어: theta_up/theta_dn 분리. MAE 근거 — +3% 친 건들의 MAE 중앙값 -0.61%,
      p10 -2.22% → SL -1.5%로 조여도 이기는 거래 대부분 생존.
  (b) 특징 필터로 p_up-p_down 확대 (현재 4.6%p → 비용 넘기려면 ~12%p 필요). = Task 6.
partial(개장60분)은 gross 부터 음수 → 우선순위 낮음.

리뷰 미수정 Minor: none 버킷 창 절단 편향(절단 3.6%, mean_terminal_none 을 0쪽으로 약 0.014%p 낙관).
