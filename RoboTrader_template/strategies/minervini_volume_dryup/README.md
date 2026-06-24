# minervini_volume_dryup — Minervini VCP (Variant B)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
변동성 수축(거래량 dry-up) 후 매집 구간을 포착. Minervini의 알파 원천이 VCP가 아닌 dryup임이 확인됨.

## 출처 / 분류
Minervini VCP (Variant B) — 추세/매집.

## 진입 (`rule_volume_dryup`)
최근10봉 평균거래량 ≤ 직전30봉 평균의 **70%** (거래량 dry-up). confidence = 58.

## 청산
sl **-8%** / tp **+12%** / max_hold **20거래일**. **trail 없음, trend_flip 없음** (Variant A와 차이).

## 유니버스 / regime / 사이징
- 유니버스: 시총 ≥ 3천억 · 거래대금 ≥ 30억
- regime: index **KOSPI** / gate **none** (게이트 역효과)
- K = **3** / 종목당 **333만**

## 평판 (백테스트 / OOS)
정본상 평범 (KOSPI 하회 -7%). K 풀스윕서 **K3만 생존** (K10/20 MaxDD ≈ 100%).

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/minervini_vcp/rules.py::rule_volume_dryup`
