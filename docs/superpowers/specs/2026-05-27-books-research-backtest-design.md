---
title: 트레이딩 책 10권 조사 · 시그널화 · 백테스트
date: 2026-05-27
owner: kis-template
status: draft (awaiting boss review)
---

# 트레이딩 책 10권 조사 · 시그널화 · 백테스트 설계서

## 1. 목적

인터넷에 공개된 자료(요약·리뷰·블로그·원서 발췌)를 활용해 트레이딩/투자 책 10권의 매매 규칙을 모두 추출·코드화하고, 한국 시장 데이터(2025-10 · 2026-04 · 2026-05) 3개 윈도우 × 전종목 1,347개를 대상으로 백테스트하여 통합 리더보드로 비교한다.

## 2. 범위

### 2.1 대상 책 10권

| ID | 저자 — 책 | 카테고리 | 데이터 입도 | 예상 규칙 수 |
|---|---|---|---|---|
| 1 | 앤드류 아지즈 — How to Day Trade for a Living | 인트라데이 | 분봉 (1분/5분) | ~7 |
| 2 | 마이크 벨라피오레 — One Good Trade / The PlayBook | 인트라데이 | 분봉 (1분/5분) | ~5 |
| 3 | 린다 라쉬케 — Street Smarts | 인트라데이 | 분봉/일봉 | ~6 |
| 4 | 윌리엄 오닐 — 최고의 주식 최적의 타이밍 | 스윙 | 일봉 + 재무 (EPS) | ~8 |
| 5 | 마크 미너비니 — 초수익 성장주 투자 | 스윙 | 일봉 | ~10 |
| 6 | 스탠 와인스타인 — Secrets for Profiting in Bull and Bear Markets | 스윙 | 일봉 (주봉 환산) | ~6 |
| 7 | 알렉산더 엘더 — Trading for a Living | 스윙 | 일봉 + 주봉 | ~7 |
| 8 | 피터 린치 — 월가의 영웅 | 펀더 | 일봉 + 재무 | ~6 |
| 9 | 조엘 그린블라트 — 주식시장을 이기는 작은 책 | 펀더 | 일봉 + 재무 | ~3 |
| 10 | 제임스 오쇼너시 — What Works on Wall Street | 펀더·퀀트 | 일봉 + 재무 | ~12 |

**예상 총 시그널 수**: 약 70개.

### 2.2 백테스트 기간

| 윈도우 | 기간 | 거래일 수 |
|---|---|---|
| W1 | 2025-10-01 ~ 2025-10-31 | ~20 |
| W2 | 2026-04-01 ~ 2026-04-30 | ~21 |
| W3 | 2026-05-01 ~ 2026-05-27 | ~19 |

### 2.3 유니버스

minute_candles · daily_prices에 존재하는 전종목(약 1,347 종목). 각 책 규칙이 자체 스크리닝으로 필터링.

## 3. 아키텍처

```
RoboTrader_template/
├── strategies/books/
│   ├── __init__.py
│   ├── _base_book_strategy.py        # 공통 BaseStrategy 상속, 규칙 컴비네이션 인프라
│   ├── aziz_day_trade/
│   │   ├── strategy.py
│   │   ├── rules.py                  # rule_abcd, rule_bull_flag, rule_vwap_reversal, ...
│   │   └── README.md                 # 책 페이지 ↔ 함수 매핑
│   ├── bellafiore_playbook/
│   ├── raschke_street_smarts/
│   ├── oneil_canslim/
│   ├── minervini_vcp/
│   ├── weinstein_stages/
│   ├── elder_triple_screen/
│   ├── lynch_one_up/
│   ├── greenblatt_magic_formula/
│   └── osullivan_what_works/
├── backtest/
│   └── book_backtester.py             # 단일 + 조합 백테스트 통합 러너
└── scripts/
    └── run_books_research.py          # CLI 진입점

reports/books_research/
├── index.md                           # 통합 리더보드
├── leaderboard.parquet                # raw 메트릭
└── {book_id}/
    ├── report.md
    ├── rules_individual.parquet
    ├── rules_combo.parquet
    └── equity_curve.png
```

### 3.1 모듈 경계와 책임

- `_base_book_strategy.BookStrategy`: BaseStrategy(`strategies/base.py`) 상속. 규칙 리스트를 받아 컴비네이션 신호 생성.
- `{book_id}/rules.py`: 순수 함수 모음. 시그니처 `rule_xxx(df: DataFrame, ctx: dict) -> bool | float`. 룩어헤드 금지.
- `{book_id}/strategy.py`: rules.py의 함수를 enum/리스트로 등록 + 책 고유의 진입·청산·포지션 사이징 규칙 구현.
- `book_backtester.py`: 모든 책에 공통인 백테스트 실행기. 책 strategy를 받아 단독·조합 모드 실행, 메트릭 집계.
- `scripts/run_books_research.py`: `--book aziz --period 2025-10 --mode combo` 같은 CLI.

### 3.2 데이터 흐름

```
[전종목 1,347] ──[period filter]──> 데이터 로더
                                         │
                                         ▼
                              [minute_candles | daily_prices | financial_data]
                                         │
                                         ▼ (per stock, per day)
                              rules.py 의 rule_xxx 함수들 실행
                                         │
                                         ▼ 조합기 (AND/OR/weighted)
                              진입 시그널 발생 → 다음 봉 시가 체결
                                         │
                                         ▼
                              포지션 보유 → 청산조건/EOD/시간초과 → exit
                                         │
                                         ▼
                              trades.parquet + equity_curve
                                         │
                                         ▼ 메트릭 계산
                              {book_id}/rules_individual.parquet + rules_combo.parquet
                                         │
                                         ▼
                              leaderboard.parquet (append)
                                         │
                                         ▼
                              index.md (regen) + {book_id}/report.md
```

## 4. 책 1권당 워크플로우 (순차 처리)

| Step | 작업 | 산출 | 담당 |
|---|---|---|---|
| 1 | 웹 조사로 책의 매매 규칙 전체 추출 | rules.md 초안 | document-specialist 에이전트 (WebSearch + WebFetch) |
| 2 | 규칙맵 작성: 한글 명세 + 입력 데이터 + 출력 시그널 구조화 | README.md | 직접 |
| 3 | 시그널 함수 코드화 + 단위 테스트 | rules.py + tests | executor 에이전트 (sonnet) |
| 4 | 백테스트: 규칙별 단독 + AND 전체결합 + 인기 OR 조합 — 3기간 × 전종목 | results.parquet | book_backtester.py |
| 5 | 책별 리포트 작성 | report.md | writer 에이전트 (haiku) |
| 6 | 리더보드 업데이트 | index.md / leaderboard.parquet append | 직접 |

**진행 순서**: 책1 → 책2 → … → 책10. 중간 점검 가능, 학습 효과 누적.

## 5. 백테스트 엔진 사양

### 5.1 공통 가정 (전 책 동일)

- **체결**: 신호 발생 봉 다음 봉의 시가에 시장가 체결.
- **거래비용**: 매수 0.015% + 매도 0.015% + 거래세 0.18% = 왕복 약 0.21%.
- **슬리피지**: 0.10% 단방향.
- **adj_factor**: corp_events 테이블의 split/merge 반영 (e057456에서 5.4년치 백필 완료).
- **포지션 사이징**: 책마다 다름. 명시 없으면 균등 자본 1/N (N=동시 보유 종목 수, 책별 정의).

### 5.2 룩어헤드 금지 (No-Lookahead Lock)

- 신호 함수는 t 시점 데이터만 사용, t+1 이후 데이터 접근 시 명시적 raise.
- 기존 `phase0_no_lookahead_lock` 컨벤션을 그대로 준수 (D-1 universe도 동일 룰).

### 5.3 규칙 조합 모드

각 책마다 다음 3개 모드를 실행:

- **single**: 규칙 1개만 사용 (각 규칙 단독 백테스트)
- **all_AND**: 책의 모든 규칙을 AND 결합 (책 충실)
- **top_K_OR**: single 결과 PnL 상위 K개를 OR 결합 (책의 핵심 강점만)

조합 폭발 방지를 위해 전체 부분집합 brute force는 하지 않는다.

### 5.4 청산 규칙

책에 명시된 청산조건이 있으면 그것을 사용. 없으면 책 카테고리별 기본값 적용:

- 인트라데이: EOD 강제 청산, 손절 -2%, 익절 +3%, 분봉 트레일링 -0.5%
- 스윙: 보유 5~20일, 손절 -7%, 익절 +20%, MA20 이탈 시 청산
- 펀더: 분기 리밸런싱 (또는 윈도우 종료 시 청산)

### 5.5 평가지표

1급 (정렬·필터링용): `PnL_pct`, `Sharpe`
2급 (해석용): `Calmar`, `MaxDD_pct`, `Sortino`, `HitRate`, `n_trades`, `avg_hold_days`

## 6. 산출물 상세

### 6.1 `reports/books_research/index.md`

```markdown
# 트레이딩 책 10권 리더보드 (2026-05-27)

## 통합 순위 (전 책 × 전 기간 × 전 조합)
| Rank | Book | Rule | Period | PnL% | Sharpe | Calmar | MaxDD% | Trades |
| ... |
| 1    | minervini_vcp | all_AND | 2026-04 | +12.3 | 2.1 | 4.5 | -3.2 | 18 |
| 2    | ...

## 책별 베스트 1개 비교
(equity curve 차트 10개 오버레이)

## 책별 상세 리포트
- [aziz_day_trade](aziz_day_trade/report.md)
- [bellafiore_playbook](bellafiore_playbook/report.md)
- ...
```

### 6.2 `leaderboard.parquet` 스키마

```
book_id : str
book_name : str
period : str            # "2025-10" | "2026-04" | "2026-05"
rule_combo : str        # rule 이름 or "all_AND" or "top3_OR" 등
mode : str              # single | all_AND | top_K_OR
n_trades : int
pnl_pct : float
sharpe : float
calmar : float
sortino : float
max_dd_pct : float
hit_rate : float
avg_hold_days : float
run_at : timestamp
```

### 6.3 `{book_id}/report.md` 구성

1. 책 요약 (1단락)
2. 규칙맵 표 (책 페이지/장 → 함수명 → 한 줄 설명)
3. 단독 백테스트 결과 (전 규칙 × 3기간 표)
4. 조합 백테스트 결과 (all_AND, top_K_OR × 3기간 표)
5. 자산곡선 차트 (책 베스트 조합)
6. 해석: 어떤 규칙이 한국 시장 25-26년에서 작동했는가, 책의 핵심 가정이 검증됐는가
7. 한계·의문점

## 7. 품질 게이트

- [ ] 룩어헤드 금지 (자동 검증 — t+1 접근 시 raise)
- [ ] 거래비용·슬리피지 반영
- [ ] adj_factor 적용 (split/merge)
- [ ] 분봉 신호는 다음 봉 시가 체결
- [ ] 책 1권 완료 시 회귀 테스트 통과 (`pytest tests/strategies/books/{book_id}/`)
- [ ] 책별 report.md에 작동/미작동 규칙의 가설 명시

## 8. 비범위 (이번 라운드에서 안 함)

- regime 분해 (BULL/BEAR/SIDEWAYS) — 3개월 윈도우 짧아서 통계 불안정
- paper trading / live 시그널 — 백테스트만
- 실전 종목 후보 추출 — 별도 세션
- 파라미터 그리드 탐색 (multiverse) — 일단 책의 디폴트 파라미터로 고정. 추후 확장

## 9. 리스크와 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| 분봉 백테스트 시 1,347 종목 × 30분 = OOM | 대 | 종목 단위 streaming + chunked, intermediate parquet flush |
| 책 규칙이 한국 시장과 정의 다름 (예: 미국 RS Rating) | 중 | 한국형 대체 정의 명시 (예: KOSPI 200 종목 상대강도 252일 percentile) |
| 펀더 책의 재무 데이터 부족 | 중 | financial_data 가용 컬럼 사전 점검, 부족 시 해당 규칙 skip + report에 기록 |
| 책마다 청산 규칙 미명시 → 결과 편향 | 중 | 카테고리별 기본 청산값 통일 + report에 "기본값 사용" 명시 |
| 70개 시그널 코드화 분량 | 대 | 책 1권씩 순차 진행 (사장님 결정 — Approach A) |

## 10. 다음 단계

1. **사장님 설계서 리뷰** — 본 문서.
2. **writing-plans 스킬 호출** — 책 1권부터 단계별 실행 계획 작성.
3. **첫 책 (제안: 아지즈 = 분봉 가장 명확) 부터 워크플로우 시작**.

---

*변경 이력*
- 2026-05-27: 초기 작성. 사장님 브레인스토밍 응답 7건 반영 (혼합 카테고리 / 제가 10권 추천 / 전체 규칙 시그널화 + 조합 백테스트 / 통합 리더보드 + 책별 / 책 성격별 데이터 입도 / 전종목 1,347 / 순차 처리).
