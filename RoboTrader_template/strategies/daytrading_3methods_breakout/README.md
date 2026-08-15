# daytrading_3methods_breakout — 유지윤 데이트레이딩 3대 타법 (Variant B)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
거래량 동반 전고점 돌파를 빠르게 먹고 빠지는 돌파 타법. 약한 Sharpe라 탐색·관찰용.

## 출처 / 분류
유지윤 『데이트레이딩 3대 타법』 (Variant B) — 돌파.

## 진입 (`rule_breakout_prev_high`, high_window=15)
종가 ≥ 직전**15**봉 전고점 + 당일거래량 ≥ 직전**20**봉 평균 × 2.0 + 양봉.

⚠️ **두 창의 길이가 다르다.** `high_window` 만 config 에서 15 로 오버라이드되고, 거래량 창 `vol_lookback` 은
**배선이 없어 룰 기본값 20 그대로** 돈다. (2026-08-15 감사 정정 — 종전 README 는 거래량도 15봉이라 적었으나 틀렸다.)

## 청산
sl **-10%** / tp **+10%** / max_hold **10거래일** / trailing 없음 (돌파 타법 = 고정 손익절).

## 유니버스 / regime / 사이징
- 유니버스: 중소형 (시총 < 5천억) · 거래량 배수순
- regime: index **KOSDAQ** / gate **none** (일봉 게이트는 분봉 성격이라 부적합)
- K = **5** / 종목당 **200만**

## 평판 (백테스트)

🔴 **이 숫자는 검증 러너 유니버스(`top_volume:50`)에서 나왔다 — 라이브 유니버스와 다르다.**
라이브 매수의 97%가 그 밖이다(실측). 라이브 기대치로 인용하지 말 것 → [PAPER_STRATEGIES §0.7](../../docs/PAPER_STRATEGIES.md#07--백테스트-평판-숫자와-라이브는-다른-모집단이다-2026-08-15-감사)
706T / **+5.90%** / Sharpe **0.17** / hit 46.7% — 약함. 탐색·관찰 목적으로 유지.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/daytrading_3methods/rules.py::rule_breakout_prev_high`
