# elder_ema_pullback — Elder 삼중창 (Variant A)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
상승추세 종목의 단기 눌림을 사서 추세를 길게 먹는 정통 추세추종. 8전략 중 백테스트 최강 생존군.

## 출처 / 분류
Elder 삼중창 (Variant A) — 추세추종.

## 진입 (`rule_triple_screen_ema_pullback`)
1. **Screen1** = EMA65 상승 (5바 전 대비 기울기 > 0)
2. **Screen2** = `low[-1] ≤ EMA13×1.02` AND `close[-1] > EMA13` (눌림 회복)
3. **Screen3** = 전일고가 +1틱 매수스톱 (`entry_min_price`로 강제 — 현재가가 매수스톱 미만이면 진입 스킵 = 백테스트 `entry_mechanism="stop"` 돌파 진입과 정합, 2026-06-25)

## 청산
sl **-8%** / tp **+30%** / 수익 중 EMA13 하향이탈 trailing / EMA65 추세반전(5바 전 대비 하락) 청산 / max_hold **100일**.

## 유니버스 / regime / 사이징
- 유니버스: 대형 (시총 ≥ 5천억) · 거래대금 ≥ 50억
- regime: index **KOSPI** / gate **none** (증거기반 — elder는 게이트 무수혜)
- K = **20** / 종목당 **50만**

## 평판 (백테스트 / OOS)
정본 재측정 최강 — K20 Sharpe **1.55** / MaxDD **20%** / **+269%** / alpha **+22%**.
약세장 방어도 상대 양호 (단 깊은약세 2022 K3는 KOSPI 하회).

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/elder_triple_screen/rules.py::rule_triple_screen_ema_pullback`
