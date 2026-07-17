# 사전등록 스펙 — adj_factor MaxDD 오탈락 재검정 (PREREG)

> **동결 규칙**: 이 문서는 재측정 결과를 보기 **전에** 워크트리에서 커밋된다(해시=증거).
> 커밋 후에는 폴드·기간·비용·통과선·유니버스·청산을 결과 보고 **바꾸지 않는다.** "다른 각도 재시도"=goalpost 추격=금지.
> 근거: [[discovery-program-status]] 규율, [[feedback-writer-numbers-must-be-verified]].

## 0. 목적 (한 줄)
adj_factor 곱셈 버그로 MaxDD가 거짓 부풀림돼 탈락한 전략들의 **참 성능**을 재측정하고, 사전 고정된 바로 판정한다. **In-sample MaxDD 정정만으로는 부족**하다(2026-06-05 교훈: OOS가 진짜 심판, 가치책은 정정 후 Sharpe 1.0이어도 국면의존으로 탈락).

## 1. 대상 (진짜 갭 + 버그 잔존)
| # | 전략 | 재측정 경로 | 상태/기대 |
|---|---|---|---|
| 1 | **deep_mr_dev20** | `multiverse4_returns_export.py`(clean book_param) + `strategy_gate.py` G5 OOS. (선택) 수정된 pit_engine으로 99.9%→X before/after 귀속 | **진짜 갭** — pit_reader 99.9%는 정정 후 미측정 |
| 2 | **daytrading_3methods** | `run_daytrading_3methods.py` native(버그수정 후) | **진짜 갭** — 6월 기록에 없음 |
| 3 | **dino_surge** | `run_dino_surge.py` native(수정 후) | marginal·in-sample only → OOS 처음 |
| 4 | **minervini_vcp** | `run_minervini_vcp.py` native(수정 후) | 6월 △평범(alpha−7%) — 확인 |
| 5 | **weinstein_stages** | `run_weinstein_stages.py` native(수정 후) | 주봉ctx 0거래 이슈 확인 |
| 6 | **elder_triple_screen** | `run_elder_triple_screen.py` native(수정 후) | 6월 ✅유지(라이브) — 확인, 88%는 청산아티팩트 |
| 7 | **haru_silijeon_daily** | `run_haru_silijeon_daily.py` native(수정 후) | 6월 ❌82% 진짜파국 — 확인 |
| 8 | **trading_legends_daily** | `run_trading_legends_daily.py` native(수정 후) | 6월 ❌100% 파국 — 확인 |

## 2. 데이터 (고정)
- 소스: `kis_template`(resolver 경유, host 127.0.0.1 port 5433). **DB명 하드코딩 금지.** 읽기 전용.
- **adj_factor 곱하지 않음**(수정본 = book_param/pit_reader 정합). close는 이미 분할조정 연속시세.
- 기간: **2021-01-01 ~ 2026-06-30** 전구간.
- 유니버스: 각 전략 **native**(7종=top_volume:50, deep_mr=PIT screener union top~300). 그리드 재최적화·유니버스 교체 금지.

## 3. OOS 홀드아웃 (고정)
- 분기 경계 **2024-06-30**(코드 기존값 `strategy_gate.py:81`).
  - **train** = 2021-01-01 ~ 2024-06-30
  - **test**  = 2024-07-01 ~ 2026-06-30
- 설정(청산 A/B, K, warmup)은 **train 이전에 native 고정** — test 결과로 재선택 금지. native에 A/B 둘 다면 **A(충실청산)를 대표**로 사전지정, B는 부기.

## 4. 비용 (고정)
- **판정 바 = 왕복 0.21% net**(거래세 0.18% + 수수료 0.015%×2). 프로그램 SSOT·베타하니스(`hedge_bt.COST_LONG=0.0021`)와 정합 → 베타 잔차와 비교 가능.
- native 0.41%(슬리피지 0.1%×2 포함)는 **민감도로 병기**. 0.21%서 죽으면 확정 사망; 통과 시 0.41%도 본다.

## 5. 베타 검증 (고정) — 프로그램 핵심 교훈
- 팩터 = **동일가중 유니버스 일수익**(전 대상종목, 전구간 2021~2026). 지수(KS11/KQ11)는 2024-01+만 존재 → 전구간 커버 위해 동일가중 팩터 사용(프로그램 권장 경로).
- 방법 = `hedge_bt.rolling_oos_beta` 재사용: 주간(5거래일 비겹침) 리밸런스, **직전 26관측 OLS**(i 미포함=OOS), `resid = book − β·factor`, Sharpe ×√52.
- 산출: 각 전략 **베타헤지 잔차 Sharpe**(full·test).

## 6. 합격 바 (결과 전 고정) — **네 조건 전부(AND)**
전략이 **adopt 후보**가 되려면:
1. **정정 MaxDD ≤ 35%** (KOSPI 바이앤홀드 MaxDD ≈35% 기준선 이하).
2. **net Sharpe ≥ 0.6 (train AND test 양구간)** @ 0.21% 비용. 한 구간이라도 <0.6이면 탈락(국면의존 배제).
3. **alpha vs KOSPI > 0 (train AND test 양구간)**.
4. **베타헤지 잔차 Sharpe > 0** (full 기준; 순수 시장베타 배제).

- 판정 라벨: 네 조건 전부=**✅ adopt 후보** / MaxDD·비용 통과하나 OOS 또는 베타 실패=**△ 정정됐으나 미채택**(6월 가치책 유형) / 정정 후에도 파국=**❌ 진짜 사망**.
- ✅ adopt 후보가 나오면 **즉시 채택 아님** — 별도 라이브 페이퍼 관찰 제안(6월 envelope 선례). 이 재검정의 산출물은 **판정표**지 config 변경이 아니다.

## 7. 실행 규율
- 워크트리 `D:/tmp/wt-maxdd-reexamine`(브랜치 `research/maxdd-reexamine`, main 기반). **라이브 트리 무접촉**(브랜치전환·테스트·스모크 금지).
- 7종 버그수정은 **재측정 전** 커밋(수정=측정 전제). 회귀 GREEN 확인.
- **1회 실행** 후 §6로 판정. 재실행은 버그·환경오류 발견 시만, 사유 기록.
- 에이전트 자기보고를 판정 근거로 쓰지 않음 — 숫자 **독립 재현** 후 확정([[changelog-2026-07-16-research-data-source-unification]] 교훈).
- 7종 adj_factor 수정의 **main 머지는 사용자 승인 후**(라이브 코드 위생 별건).

## 8. 알려진 한계 (사전 명시)
- 베타 팩터=동일가중 유니버스는 지수와 다름(구성 근사). 지수 2024+ 제약 회피 위한 선택, 사전 고정.
- deep_mr native 유니버스(PIT screener)는 top_volume과 달라 7종과 직접 비교 불가 — 각자 native 기준 판정.
- native A/B 청산 중 A 대표 지정은 사전 선택(사후 유리한 것 고르기 금지).
