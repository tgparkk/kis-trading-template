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

## 특징 프로브 결과 (2026-07-10, 커밋 아래)
Task 6(ranking.py, dcdc994) + outcome_probe.py. 65 passed.
full 세그먼트에서 CI가 0을 넘지 않는 특징 2개(둘 다 음수 = 하락 예측):
  close_pos_in_day -0.075 (-0.175,-0.024) / lower_wick_ratio -0.043 (-0.076,-0.020)
=> "이미 반등한 흔적"을 사면 진다. 엣지는 pct_dn 감소(12.89->9.48)에서 옴 = 손실회피 필터.
close_pos bin0 net +0.066%, 교집합(둘 다 하위20%) n=1410 net +0.097%.
⚠️ 인샘플 21일, 18특징 스크리닝 후 선택, 분위 사후결정, 슬리피지 0. 매매 근거 아님.

다음: (a) 비대칭 배리어(SL -1.5%)와 결합 — 이 필터는 pct_dn 을 깎으므로 좁은 SL 에서 효과 증폭
      (b) OOS 검증(2026-02~05 또는 2025-04~2026-01) 필수. 이 순서 지킬 것.
이벤트 테이블 캐시: scripts/discovery/intraday_rebound/_cache/events_probe_202606.parquet

## 비대칭 배리어 격자 (IS 2026-06, 커밋 7e58470) — 가설 기각
full/filtered(n=1372, 21일) net_pct, TP별x SL별:
  SL 3.0%: TP4 +0.101 / TP3 +0.095 / TP2 +0.062
  SL 2.0%: TP4 +0.026 / TP3 +0.025 / TP2 -0.006
  SL 1.5%: TP3 -0.013 / TP4 -0.015 / TP2 -0.034
  SL 1.0%: TP4 -0.047 / TP3 -0.048 / TP2 -0.068
full/all 12셀 전부 net 음수 (최고 -0.120).

**손절을 조이면 단조롭게 나빠진다.** SL 3%->1.5% 시 pct_down 9.7->36.8% 폭증,
pct_up 은 17.7->15.8% 로 거의 안 줄음. 조인 손절이 먹은 것은 이기는 거래가 아니라
무접촉(72.6->47.4%). 창끝까지 가서 평균 +0.09% 로 끝났을 거래가 확정손실이 됨.

관리자 오판 기록: 근거로 든 "MAE 중앙값 -0.61%"는 **이긴 거래들의** MAE였다.
손절은 이긴 거래만이 아니라 흔들리는 모든 거래를 건드린다. 중앙값이 아니라 전체 분포를 봤어야 함.

결론: 손익비 조정 기여 = 0. 모든 엣지는 필터(close_pos_in_day, lower_wick_ratio)에서 나온다.
대칭 TP3/SL3 + 필터 = net +0.095% (인샘플).

## OOS 사전등록 (결과 보기 전에 기록)
설정: TP 3% / SL 3%, filter close_pos_in_day<=0.043 AND lower_wick_ratio<=0.083, segment=full
IS 기준값: net +0.095% (n=1372, 21일)
기간: 2026-02-01~2026-05-31 (한 번도 안 본 구간), 격자 없음, 단일 셀
통과 조건: net_pct > 0

## OOS 결과: FAIL (사전등록 조건 net>0)
2026-02-01~2026-05-31, TP3/SL3, filter close_pos<=0.043 & lower_wick<=0.083, full:
  all      n=52575 (82일)  up 18.78 / down 22.34  gross -0.170%  net -0.380%
  filtered n= 3950 (82일)  up 20.10 / down 20.99  gross -0.018%  net -0.228%
  partial/filtered gross +0.069% net -0.141%

**전제가 무너졌다.** 딥드롭 비대칭 자체가 뒤집힘: IS(6월) up>down (17.45/12.89),
OOS(2~5월) down>up (18.78/22.34). OOS 표본이 2.6배 크다(82일 vs 21일).
=> 스펙 2.2절의 1.348 은 "6월 한 달의 성질". 재현 게이트는 같은 달 안의 재현이었을 뿐.

필터 효과는 방향/크기 모두 재현됨(gross 를 IS +0.22%p, OOS +0.15%p 개선; pct_down 을 깎음).
그러나 바닥이 음수라 0을 못 넘는다.

시장방향으로 설명 안 됨: KOSPI(이 DB 기준) OOS 구간 +71%, IS 6월 -3.6%. 강세장에서
오히려 하락 선착이 많았다. 두 구간뿐이라 귀속 불가.

**최종 판정: 장중 급락 반등에 비용을 넘는 예측 가능한 엣지 없음.**
(스펙 12절이 미리 받아들인 결과. 멀티버스 착수는 확정적으로 부적격.)

다른 기간을 더 뒤져 통과하는 창을 찾는 것은 OOS 가 아니라 격자탐색 = 금지.

## 안정성 스캔 사전등록 (2026-07-10, 결과 보기 전)
코드: stability_scan.py (커밋 b8571c3, 89 passed, 브루트포스 대조 테스트 1회 통과)
격자 108셀 = TF{3,5,15} x N{30,60,120} x D{2.5,4,6,8%} x M{30,60,120}, theta=3% 고정, full 세그먼트만.
기간 4개(겹침 없음): W1 2025-04~09 / W2 2025-10~2026-01 / W3 2026-02~05 / W4 2026-06.

측정: 무조건 진입(필터 없음)의 edge_pp = pct_up - pct_down (선착 기준).
**판정은 수익이 아니라 부호 안정성.**

사전 정의:
- stable_positive = 4개 기간 전부 edge_pp > 0 인 셀
- 우연 기대치: 셀이 독립이고 부호가 동전던지기라면 108 x (1/16) = 6.75셀.
  단 셀끼리 강상관이므로 이 6.75는 상한이 아니라 참고치일 뿐이다.
- 따라서 개수만으로 판정하지 않는다. 반드시 함께 볼 것:
  (1) per_window_median_edge — 기간별 108셀 중앙값. 기간마다 부호가 통째로 바뀌면
      국면이 전부를 밀고 있다는 뜻이고, 그 경우 stable_positive 는 상관구조의 잔재다.
  (2) stable_positive 셀들이 격자에서 인접한 덩어리인지(=하나의 상관된 영역) 흩어져 있는지.
  (3) min_n_across_windows — 표본 작은 셀의 "안정성"은 무의미.

결론 규칙(사전 확정):
- per_window_median_edge 의 부호가 기간마다 뒤집히고 stable_positive 가 우연 기대치 근방이면
  → 주제 확정 종료. 추가 탐색 금지.
- stable_positive 가 우연 기대치를 크게 넘고, 인접 덩어리를 이루며, 표본이 충분하면
  → 그 영역에서만 재시작. 단 다시 별도 OOS 필요.

## 🔴 안정성 스캔 결과 — 앞선 "연구 종료" 판정을 철회한다 (2026-07-10)
기간별 108셀 edge_pp 중앙값:
  W1 2025-04~09  +2.042 (pos 102 / neg 6)
  W2 2025-10~26-01 +4.995 (pos 108 / neg 0)
  W3 2026-02~05  -1.127 (pos 28 / neg 80)   <-- 내가 "OOS"로 고른 유일한 음수 구간
  W4 2026-06     +3.753 (pos 99 / neg 9)

**4기간 중 3기간 양수.** 나는 유일한 음수 구간 하나로 주제 전체를 사망선고했다.
게다가 검증에 쓴 셀(TF3,N60,D4%,M60)은 생존 28셀에 들어 있지도 않다.

정직한 한계: stable_positive=28 == W3에서 양수인 셀 수 28. 즉 "4기간 안정"은
"W3에서 살아남았나"와 동어반복. 나머지 3기간이 거의 만장일치 양수라서.
=> 사전등록에서 경계한 "상관구조의 잔재"가 실제로 발생. 안정성 개수는 정보를 못 준다.

**그러나 구조는 실재한다: 생존이 하락폭 D에 단조.**
  D=8%: 전 조합 생존 (W3에서도 +0.74~+7.00pp)
  D=6%: 대부분 생존 / D=4%: N30,M30 만 / D=2.5%: 2개만
나쁜 국면에서도 깊은 급락일수록 비대칭이 버틴다. 6월 단독분석의 방향과 일치, 15개월 규모.

미확정: edge_pp 는 무접촉 드리프트 제외값. 비용(0.21%) 넘으려면 theta=3% 기준 edge>~7pp 필요.
D=8% 셀도 W3 에서 0.74~7.00pp 로 상당수 미달. 표본도 얇다(기간당 200~500건).

## 오염 경고 (다음 실험 설계 시 필수)
4개 기간을 **전부** 셀 선택에 써버렸다. 남은 미사용 데이터 = 2026-07(부분월) 뿐.
따라서 "D>=6% 영역"을 새 OOS로 검증할 깨끗한 구간이 없다.
가능한 경로: (a) walk-forward (b) 2026-07 관찰 (c) 향후 데이터 축적 대기.
단순히 D>=6% 로 좁혀 같은 4기간에서 net 을 재는 것은 **검증이 아니라 선택 후 재측정**이다.

## Task 7 모양 프로브 결과 (2026-07-10) — 모양에 정보 있음 (인샘플)
D>=6% 급락 4323건 / 309거래일. 20봉 z-정규화 궤적 KMeans k=8.
- 평균 궤적: 상승선착 vs 하락선착 사실상 동일 (직전봉 0.017 sd, 20봉평균 0.043 sd)
- 옴니버스 순열(블록=거래일 x 사전변동성5분위, 3000회): T=26.26, 귀무중앙값 7.16, p=0.0027
  (날짜만: p<0.0001 / 변동성만: p=0.028) => 변동성 대리변수 아님
- cl5 +9.97%p (n=291, z=+2.83, pre_vol 1.425) : 저점→반등→꺾임→급락
  cl3 +3.92%p (n=995, z=+2.28, pre_vol 0.793) : 꾸준한 하락 후 급락
  cl2 -6.54%p (n=306, z=-2.75, pre_vol 1.732) : 직전까지 상승하다 붕괴
  => "흘러내리던 것의 추가 급락은 반등, 오르던 것의 붕괴는 계속 하락"
     봉 하나(close_pos_in_day/lower_wick_ratio) 결론과 동일 방향.

관리자 오판 기록: 1차 검정(클러스터 log-ratio 퍼짐의 SD, p=0.223)은 클러스터마다
귀무 평균이 다름을 무시 → 검정력 없음. 옴니버스(표준화 편차 제곱합)로 교체하니 p=0.0027.

⚠️ 전부 인샘플. k=8/시드 선택값. cl5 총기대값 ~0.30% vs 비용 0.21% (슬리피지에 사라짐).
차트: https://claude.ai/code/artifact/e2734ec1-6384-4c57-90a0-ecaa7b99cf12
다음: 워크포워드(앞 구간서 클러스터 학습 → 다음 구간서만 평가).

## 모양 거리 비교: 유클리드 vs k-Shape vs DTW (2026-07-10, 커밋 ba5442e)
동일 채점(옴니버스 순열, 블록=거래일 x 사전변동성5분위, B=3000), k=8, n=4323:
  method   T_obs   null_med   p        best_edge_pp  best_n  |z|>1.96 클러스터
  euclid   27.68   7.23       0.0020   +9.97         291     3
  kshape    5.89   7.26       0.6277   +4.64         603     0     (위상불변 ±5봉)
  dtw      13.54   7.16       0.1053   +3.67         655     1     (Sakoe-Chiba r=3)

**시간축을 풀면 신호가 사라진다.** 위상/속도는 잡음이 아니라 정보.
z-정규화(수준·크기 제거)는 유지해야 하고, 시간 정렬은 고정해야 한다.

⚠️ 관리자 과장 정정: "답이 peak_pos 한 줄로 줄어든다"고 말했으나 검정 결과 아님.
  peak_pos 4구간 옴니버스 T=9.43 (귀무중앙값 3.19, 95%=10.19) p=0.0633
  peak_pos vs 상승선착 Spearman rho=-0.0735, 순열 양측 p=0.0800
  방향은 일관(peak 5-9 z=+2.33 / peak 15-19 z=-1.88)이나 단독 유의 아님.
  => 8클러스터의 p=0.002 는 고점위치 외에 봉별 높이/기울기/곡률의 약한 조각들이
     합쳐진 결과. 단일 지표로 뽑으면 흩어진다.
  (승패차 표 +6.13/+10.73/-3.37/-9.09%p 는 눈으로 본 패턴이며 통제 후엔 우연 배제 못함.)

여전히 인샘플. 워크포워드 미실시.

## DB 이관: robotrader -> kis_template (2026-07-10 18:42~19:51)
사장님 지시: "kis_template 에 없는 데이터를 전부 rt/rt_quant 에서 가져오고, 연구는 kis 를 보도록."
(rt_quant 에는 분봉 테이블 자체가 없음 -> 대상은 robotrader.minute_candles 뿐)

수행 (장 마감 후, 봇 미가동):
1. trade_date < 20260623 : 53,844,086행 적재 (중복제거: (stock,trade_date,datetime) 당 min(idx))
   - 버린 54,688행은 kis_template.minute_candles_dupes 에 전량 보존
2. 20260623~20260710 중 kis 에 아예 없던 종목-일 518건 : 196,745행 보강
   - kis 가 이미 가진 3,692 종목-일은 무접촉 (라이브 SSOT)
3. kis 자체 중복 3건(091590, 값 동일) 격리 후 제거
최종: 55,494,653행 / 1,438종목 / 356일 / 중복키 0 / 격리 54,691행 / DB 12GB
검증: 5개 표본일 (rows, sum(close), sum(volume)) 체크섬 rt(dedup) 와 완전 일치
롤백: DELETE FROM minute_candles WHERE trade_date < '20260623'  (kis 에 원래 없던 구간)

## 유니버스 드리프트 발견·수정 (커밋 3a40685)
load_universe 가 trade_date >= start_date (끝날짜 없음) 로 커버리지 계산
=> 데이터가 쌓일 때마다 멤버십이 변함. rt 199 / kis 201.
연구 창(20250401~20260630) 고정 시 rt=kis=207 로 완전 일치 (이관 충실성 증명).
조치: end_date 파라미터 추가 + universe_snapshot.json(u199_20260710, 199코드) 커밋,
      모든 연구 모듈이 load_frozen_universe() 사용. verify_frozen_universe: missing=[].

## 재현 게이트: 중복 제거 효과 (kis_template vs robotrader)
  full  no_drop   1.100 -> 1.100
  full  1.5-2.5%  1.014 -> 1.007
  full  2.5-4.0%  1.018 -> 1.004
  full  >=4.0%    1.348 -> 1.346
  partial >=4.0%  1.233 -> 1.233
결론 불변. 얕은 하락은 오히려 베이스라인에서 더 멀어짐(엣지 없음이 더 선명).
shape_events: 4,323 -> 4,316건 (7건이 중복 산물).

커밋: b9b25ab(MINUTE_DB=kis_template) 3a40685(유니버스 고정) 29e338d(샘플/거래량 프로브)
블라인드 테스트 재발행: https://claude.ai/code/artifact/eea42e13-0f21-4767-bd7b-e2ddbe9df60f

## 거래량 궤적 검정 결과 (2026-07-10, kis_template n=4316, 309일)
동일 채점(옴니버스 순열, 블록=거래일 x 사전변동성5분위, B=3000, k=8, seed 고정):
  method         T_obs  null_med   p        best_edge_pp  best_n  n_sig(|z|>1.96)
  price          28.43  7.20       0.0013   +10.00        290     4
  volume         12.91  7.30       0.1277   -0.59         673     0
  price_volume   26.57  7.29       0.0027   +6.33         648     1
vol_slope 5분위:  T=7.27 null_med=4.21 p=0.2170
  q0(가장 마름) edge +2.55 z-0.94 / q4(가장 불어남) edge +2.67 z+2.15
  단 q4 는 pct_up 29.32 / pct_dn 26.65 로 둘 다 상승 → 비율 1.10 (전체 1.084) = 변동성.

**거래량 궤적 단독 무신호. 합치면 오히려 희석**(승패차 10.00→6.33, 유의클러스터 4→1).
관리자 사전 예측(거래량 단독 무신호 + 결합 시 차원 증가로 희석)이 맞았음.

부수 확인: price 기준선이 robotrader(중복포함) T=27.68/p=0.0020/+9.97 →
kis_template(중복제거) T=28.43/p=0.0013/+10.00 으로 **소폭 강화**. 데이터 정리가 신호를 깎지 않음.

한계: 이 검정은 z-정규화 20차원 유클리드 클러스터링. 사람 눈은 "급락봉 거래량 x 가격모양"을
곱해서 본다 — 선형 클러스터링이 못 하는 일. 블라인드 테스트 적중률이 60% 넘으면 재조사.

## 🔴 워크포워드 최종 판정 (2026-07-10) — 사전등록 조건 미달, 주제 종료
사전등록: .superpowers/sdd/walkforward-preregistration.md (커밋 c4851f2, 결과 전)
확장창 8폴드, 평가 7회, 평가구간은 선택에 미사용. 탐색(tf/D/TP/SL/F/필터/클러스터)은 학습구간에서만.

fold net_pct: -0.466 / +0.638 / +0.137 / -0.201 / +0.394 / -0.552 / +0.073
pooled: 401거래, 273일, 1.47건/일, pct_up 9.23 / pct_dn 13.22 / none 77.56
        gross +0.168%  net -0.042%
판정: (1) 4/7 FAIL  (2) -0.042% FAIL  (3) 1.47건/일 PASS  => 2/3 미달, 종료.

핵심: gross 는 양수(+0.168%). 신호는 있으나 왕복비용 0.21% 에 0.042%p 모자람.
      아침 first-touch(+0.09% vs 0.21%) 와 동형. "엣지의 존재"가 아니라 "크기"가 문제.
선택 불안정: 폴드마다 D/filter/tf 가 바뀜 = 최적이 대체로 잡음.
유일한 안정 요소: lower_wick_ratio<=q20 이 7폴드 중 4폴드에서 선택.

블라인드 테스트는 검출력 부족(n=120에서 55% 적중률 검출력 15.7%, 790문항 필요)으로
의사결정 근거 아님. 자기관찰용으로만 남긴다.

## 이월 자산 (다른 전략에 붙일 것)
close_pos_in_day / lower_wick_ratio 손실회피 필터.
"이미 반등이 시작된 흔적(종가가 당일 고가쪽, 긴 아랫꼬리)을 보고 사면 진다."
IS +0.22%p, OOS +0.15%p 로 총기대값 개선, 워크포워드에서도 4/7 폴드 선택.
반등 예측기가 아니라 손실 회피기임에 주의.
