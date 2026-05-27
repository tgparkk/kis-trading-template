# 앤드류 아지즈 — How to Day Trade for a Living (규칙맵)

데이터: 분봉 (minute_candles), 1분 기준 (5분봉은 윈도우 리샘플로 처리).
보유 기간: intraday — EOD 강제 청산.
조사 원본: `RULES_RESEARCH.md` (8셋업 정리).

## 규칙 목록 (8개)

| 함수명 | 한글명 | 진입 조건 요약 | 신호 방향 | 책 챕터 |
|---|---|---|---|---|
| `rule_abcd` | ABCD 패턴 | A 상승 → B 풀백 → C 재상승 → C 고가 돌파(D) | buy | Ch.7 |
| `rule_bull_flag` | 불 플래그 | 직전 +4% 급등 후 3봉 좁은 박스 → 박스 상단 돌파 | buy | Ch.7 |
| `rule_vwap_reversal` | VWAP 반등 | VWAP 하단 dip 후 마지막 봉 VWAP 위 회복 | buy | Ch.7 |
| `rule_opening_range_breakout` | 오프닝 레인지 돌파 | 첫 5봉 고가를 종가 돌파 | buy | Ch.7 |
| `rule_red_to_green` | 레드 투 그린 | 시가 < 전일종가 인 종목이 마지막 봉 종가 ≥ 전일종가 | buy | Ch.7 |
| `rule_top_reversal` | 상단 반전 (매도) | 마지막 봉 도지 + 직전봉 대비 거래량 50% 감소 | sell | Ch.7 |
| `rule_support_resistance` | 지지/저항 반등 | 직전 60봉 최저 ± 0.3% 근처 양봉 형성 | buy | Ch.7 |
| `rule_ma_trend` | 이동평균 추세 (9/20 EMA) | VWAP 위 + 9EMA 또는 20EMA 터치 후 양봉 반등 | buy | Ch.7 |

## 청산 룰 (공통 — 백테스터 기본값 사용)

- 손절: -2% (`stop_loss_pct=0.02`)
- 익절: +3% (`take_profit_pct=0.03`)
- 최대 보유: 60봉 (`max_hold_bars=60`)
- EOD: 마지막 봉 시가 강제 청산 (`eod_liquidate=True`)

## 코드 매핑

- 함수: `rules.py::rule_xxx` 클래스 (callable factory) — `evaluate(df, ctx) -> RuleResult`
- 입력 df: minute_candles 1종목 시계열, 직전 최소 20봉 (warmup_bars 기본값) 필요
  - 컬럼: datetime, open, high, low, close, volume
- 출력: `RuleResult(triggered, side, confidence, reasons, metadata)`
- `ALL_RULES`: 8개 클래스 리스트 — strategy.py가 인스턴스화

## 한국 시장 적응 노트

- 책의 PreMkt(프리마켓) 개념은 한국에서 동시호가에 해당. `rule_red_to_green`의 "전일종가" 비교는 그대로 사용. `prev_close` 컨텍스트가 없으면 첫 봉 시가의 1.01배로 폴백 (갭다운 시뮬).
- 책의 VWAP는 NY 09:30 시작 기준. 한국은 09:00 시작이므로 minute_candles 데이터의 09:00 부터 누적 VWAP 계산.
- Float / RVOL 같은 외부 메타데이터는 사용 안 함 (한국 시장 가용성 불확실). Bull Flag의 "직전 +4% 급등" 조건은 분봉 내 모멘텀으로 대체.
- 9EMA / 20EMA / 200SMA는 분봉 내에서 직접 계산. 길이가 부족하면 규칙은 triggered=False 반환.
- 공매도 제약 — Top Reversal(매도 신호)은 보유 중 청산 신호로 활용. 백테스터는 단방향 long만 지원하므로 매도 신호는 보유 종목 청산 트리거로만 의미 있음.

## 출처

- 원서: Andrew Aziz, *How to Day Trade for a Living* (2015, updated editions).
- 보조: Bear Bull Traders 공식 블로그, 책 챕터 요약.
- 상세 조사 원본: `RULES_RESEARCH.md`
