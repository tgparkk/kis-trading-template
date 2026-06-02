# 멀티버스 정본 검증 완주 + 드라이버 병렬화 + Elder 1.02 적용 (2026-06-02)

## 개요
페이퍼 첫날(2026-06-01) 가동 중, 책전략 파라미터 멀티버스를 **정본 top_volume:50**으로 마무리하고, 살아있는 일봉 전략을 **3국면 정본**으로 교차검증. 드라이버를 **멀티프로세스 병렬화**해 분봉 작업을 수 시간→수십 분으로 단축. 최종적으로 17권 통틀어 유일한 강건 개선 **Elder touch_band 1.01→1.02**를 라이브 페이퍼에 적용.

## 1. 분봉 책 정본 (top_volume:50, limit15 착시 정정)
- **Book2 Bellafiore fade_vwap**: 정본 50서 top16 전부 **2/3 유지**(전멸 아님) — 분봉 3책 중 유일 부분강건. best dev0.015/sl5/tp10 mSharpe **0.566**(baseline=책기본 dev0.02/sl3/tp5 = 0.367 ≈ 예측 +0.37). **limit15 착시 = "전멸 아닌 과대"**(Sharpe 0.9→0.57).
  - **@100 검증서 정정**: 유니버스 2×서 mSharpe **0.57→0.05 거의 소멸**, dev0.015는 @100서 1/3 OVERFIT 붕괴. **유니버스 강건 deviation = 책기본 0.02**(50·100 둘 다 2/3), dev0.015 우위는 소유니버스 착시. 실거래 부적합.
- **Book3 Raschke anti**: 정본 50서 **36조합 전부 [OVERFIT] 1/3**, best mSharpe **−1.27**. @100선 −1.82로 더 악화(완전붕괴). **index.md "anti +10.24%/2025-10 +59%/Calmar7.59 ⭐"는 단일기간·소표본 착시 → ⭐ 철회 권고**. n_trades 6천~7천 = 거래비용 지배(aziz와 동일).
- 결론: 분봉 3책(아지즈·Bellafiore·anti) 모두 정본서 무너짐 = **분봉 단타 구조적 부적격** 재확인. fade_vwap만 완전붕괴는 면함(니치).

## 2. 일봉 생존전략 3국면 정본 (BULL 25.6~26.5 / SIDEWAYS 23~24 / BEAR 22)
드라이버 daily 경로는 OOS pos_periods 게이트가 없어 **연속 캘린더 3창**으로 국면 민감도 진단. 단순 sl/tp/mh라 실전 EMA/MA 트레일 방어 미반영(절대 BEAR 생존성은 별도).

| 전략 | 진입 파라미터 강건성 | BULL/SIDE/BEAR best Sharpe | 판정 |
|---|---|---|---|
| **Elder** touch_band | ✅ **국면 불변** (넓을수록 1.01→1.03 전 국면 우세) | 1.39 / −0.12 / −0.80 | 채택(1.02) |
| **유지윤** high_window | ✅ **국면 불변** (hw15 3국면 전부 rank1) | 0.81 / −0.02(본전) / −0.33 | hw15 검토 |
| Minervini recent/ratio | ❌ 국면 반전 (BULL best가 BEAR 바닥) | 1.38 / −0.08 / −0.33 | 페이퍼값 유지 |
| ma5 surge_pct | ❌ 국면 반전 (0.15→0.20→0.25 미끄러짐) | 1.15 / −0.15 / −0.14 | 기본값 유지 |

- **두 그룹**: Elder·유지윤은 진입에 국면불변 방향성 → in-sample 튜닝 안전. Minervini·ma5는 국면별 최적 정반대(폭등장 과적합 함정).
- **@200 유니버스 4× 검증**: 유지윤 hw15 = 3국면 전부 rank1 유지(완전 견고). Elder = 넓은 band>1.01 유지하나 @200 BEAR/SIDE best는 1.02(1.03보다 보수적) → **1.02가 유니버스·국면 양쪽 최적**. 절대 Sharpe는 유니버스 커지며 희석되나 파라미터 방향 불변.

## 3. 드라이버 멀티프로세스 병렬화 (scripts/book_param_multiverse.py)
- combo끼리 독립(시계열 순차 제약은 한 combo 내부만) → `multiprocessing.Pool`로 combo 루프 병렬화. Windows spawn 안전(top-level worker + initializer로 데이터 1회 전달), `--workers N`(기본 cpu-1, N=1=순차).
- **결과 바이트 동일 검증**(순차 vs 병렬 TSV diff 0), 가속 2.4×(소그리드)~near-linear(무거운 분봉). 분봉 @50이 순차 3h+ 미완 → 병렬 16워커로 완료.

## 4. 라이브 페이퍼 적용
- **Elder ema_pullback touch_band 1.01 → 1.02** 적용 완료(config.yaml + strategy.py fallback·기본인자·docstring + 일치검증 테스트). 로더 검증 1.02 확인, Elder 테스트 20 passed. **봇 재시작 필요**(day-1 데이터수정 3건과 함께 반영).
- **유지윤 high_window 20→15**: 후보(관찰용 전략, 코드 변경 필요=rule 하드코딩). 적용 여부 결정 대기.
- 변경 없음: Minervini/ma5/ma20 (멀티버스가 기존값 유지 확인).

## 5. 멀티버스 불가 확정
- **Book4 O'Neil**: rules.py 없음(CANSLIM 펀더멘털 스크리너, 전용 인프라 필요).
- **Book6 Weinstein**: ma30w_bounce가 주봉 ctx 시리즈(ma30w/mrs/stage) 의존 → 드라이버가 미주입 → 거래 0.
- ma20(haru_silijeon): 분봉 480선 기반, 이미 OOS ❌.

## 결론
17권 통틀어 OOS+3국면+유니버스 전부에서 강건한 개선은 **Elder touch_band 1.02 단 1건**(적용 완료). 유지윤 hw15는 저위험 관찰 후보. 나머지는 현행 유지. 분봉 단타는 정본서 전멸(fade_vwap만 니치). 상세: `reports/books_research/PARAM_TUNING_17.md`.

## 미커밋 (사장님 승인 대기)
PARAM_TUNING_17.md · book_param_multiverse.py(병렬화) · elder_ema_pullback/{config.yaml,strategy.py} · test_elder_ema_pullback_consistency.py
