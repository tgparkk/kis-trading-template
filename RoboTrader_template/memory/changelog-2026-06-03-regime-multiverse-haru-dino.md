# 국면(장상황) 멀티버스 누락 2권 보완 — haru(14) · dino(16)

> 2026-06-03 · 드라이버 `scripts/book_portfolio_multiverse.py` (무수정, CLI 실행만). 국면 윈도우는 `_REtest_portfolio_daily.md`와 동일: BULL 2025-06-01~2026-05-27 / SIDE 2023-01-01~2024-12-31 / BEAR 2022-01-01~2022-12-31.

## 계기
전 책 국면(BULL/SIDE/BEAR) 분할이 끝났는데 2권만 포트폴리오 모델 기준 국면 분할이 누락된 채 추정값으로 남아 있었음:
- **haru(14) ma20_pullback**: 전구간 best는 있으나 국면칸 "(BULL추정)".
- **dino(16) pullback_rebound**: "국면분해는 시그널 도구 미산출".

## 결과 (maxdd<0.80 sane 필터 + n_trades>0, Sharpe desc)

### Book 14 강창권/haru `daily_ma20_pullback` (rules_daily, top_volume:50, K∈{3,5})
| 국면 | best | Sharpe | PnL% | MaxDD% | n |
|---|---|---|---|---|---|
| BULL | K5 surge0.20/touch0.03 sl0.10/tp0.15/mh20 | **1.366** | +102.13 | 33.86 | 77 |
| SIDE | K5 surge0.25/touch0.03 sl0.10/tp0.10/mh20 | 0.219 | +3.52 | 42.93 | 181 |
| BEAR | K5 surge0.25/touch0.03 sl0.05/tp0.10/mh20 | 0.046 | **−3.28** | 32.69 | 100 |
- **★ BULL 전용 확정** — "(BULL추정)"이 실측으로 확인. SIDE 미미, BEAR 음수익(약세장 방어 실패, 단 maxdd~33%로 계좌소멸은 아님). K=5가 전 국면 best(K 결속 약함=분산 가능). 판정 불변(❌).

### Book 16 dino_surge `pullback_rebound` (rules, surge:100, K∈{5,10})
| 국면 | best | Sharpe | PnL% | MaxDD% | n |
|---|---|---|---|---|---|
| BULL | K5 pb0.20/rsi45 sl0.05/tp0.10/mh20 | 0.973 | +4.23 | 1.73 | **1** |
| SIDE | K5 pb0.20/rsi40 sl0.05/tp0.10/mh20 | 0.218 | +2.60 | 10.87 | 16 |
| BEAR | K5 pb0.20/rsi45 sl0.05/tp0.10/mh20 | 0.132 | +0.79 | 8.01 | 7 |
- **★ 신호 극도 희소(n=1/16/7)로 국면 Sharpe는 표본부족 착시** — BULL 0.97은 1거래(무의미). K 비결속(K5=K10, 신호<K). surge:100 유니버스 정상작동. 전구간 per-stock Sharpe 0.078의 포트폴리오판 재확인. **국면판정 불가**(부적격 불변).

## 산출물 (TSV — 경로 backslash 손실로 cwd 하위 리터럴 폴더에 생성됨, 수치는 정상)
- haru: `RoboTrader_template/tmpmultiverseregime_haru{BULL,SIDE,BEAR}/book_portfolio_haru_silijeon_daily_ma20_pullback.tsv`
- dino: `RoboTrader_template/tmpmultiverseregime_dino{BULL,SIDE,BEAR}/book_portfolio_dino_surge_pullback_rebound.tsv`
- (정식 `D:/tmp/...` 재배치 필요 시 별도 지시)

## 결론
**두 권 모두 부적격 판정 불변**. haru는 명확한 BULL 전용(약세장 −3.3%), dino는 신호 희소로 국면 측정 자체가 무의미. 이로써 **전 책 국면 멀티버스 커버리지 완료** — 남은 미측정은 구조적 불가(weinstein 주봉 거래0, oneil rules.py 없음, 분봉 4책 BEAR 데이터 부재)뿐. 최종 생존은 여전히 **Elder·systrader79 2종**.
