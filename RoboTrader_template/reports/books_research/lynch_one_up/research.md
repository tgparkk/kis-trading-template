# Peter Lynch — One Up on Wall Street — 조사 노트 (Book 8)

> Book: Peter Lynch — *One Up on Wall Street* (1989) / *Beating the Street* (1993)
> 조사 시작: 2026-05-29
> 설계: docs/superpowers/specs/2026-05-3x-lynch-one-up-design.md (Phase 2 예정)
> ⚠️ 본 책은 **펀더멘털 투자** — 기술적 6권과 달리 재무 데이터 가용성이 최대 제약. §7 데이터 실태 필독.

---

## 1. 핵심 철학

- **"아는 것에 투자하라" (Invest in what you know)**: 일반 투자자는 일상(소비자·직원·공급자)에서 유망 기업을 월스트리트보다 먼저 포착 가능 — "아마추어의 우위". 단 *우위는 단서일 뿐*, 반드시 펀더멘털 조사로 검증.
- **Tenbagger (10루타)**: 10배 오르는 종목. 커리어에서 몇 개만 잡아도 포트폴리오 성공. Fast Grower에서 10~40루타 가능.
- **Two-Minute Drill (2분 스토리)**: 매수 전 ① 왜 관심 있는지 ② 성공하려면 무엇이 필요한지 ③ 함정은 무엇인지를 2분 안에 설명할 수 있어야 함. 카테고리별로 스토리 내용 다름.
- **"보유한 것을 알라"**: 각 종목을 왜 보유하는지 설명할 수 있어야.

---

## 2. 6대 카테고리 (Lynch 프레임워크의 핵심)

> 분석 첫 단계 = 기업 분류. 카테고리마다 매수/매도 논리·기대수익이 완전히 다름.

| 카테고리 | 정의 | 이익성장률 | 핵심 관전 | 매수 | 매도 |
|---------|------|----------|----------|------|------|
| **Slow Grower** (둔재) | 성숙·노쇠, GNP 수준 성장 | 2~4% | 안정·인상되는 **배당**, 낮은 배당성향(쿠션) | 주로 배당 목적 | 배당/자사주만 매력일 때, 점유율 하락 |
| **Stalwart** (대형우량) | 수십억$ 안정 기업 (코카콜라·P&G) | **10~12%** | PEG·역사적 P/E, "diworseification"(엉뚱한 인수) 경계 | 밸류 눌림목, P/E≈성장률 | **+50% 상승 시 매도·교체**, 기대 ~30~50% |
| **Fast Grower** (고성장, Lynch 최애) | 소형·공격적 신생, 연 20~25%+ | **20~25%** (>25~30% 비지속 경계) | 강한 재무, P/E≤성장률, *검증된 반복가능 확장* | 확장 검증 후·기관 유입 전, P/E≤성장률 | **성장 둔화**, P/E≫성장률, 확장 포화 |
| **Cyclical** (경기순환) | 자동차·항공·철강·화학 | 가변 (타이밍 게임) | 사이클 위치, 재고·수급 | **저점**(이익 침체·P/E 高/음수·심리 최악) | **재고 증가·비용 상승·P/E 낮은데 정점**=천장 신호 |
| **Turnaround** (회생) | 파산 직전 무성장, 빠른 회복 가능 | N/A (회복 주도) | **채권자 공습 생존 가능?**(현금vs부채·만기), 위기 과장 여부 | 시장이 위기를 과대평가 + 재무 생존 가능할 때만 | 회생 완료·재평가 시 |
| **Asset Play** (자산주) | 시장이 간과한 자산(현금·부동산·자원·특허·브랜드) | N/A (가치 인식 주도) | **자산을 구체적으로 알라**, 부채 차감, 경영진 가치 창출/파괴 | 자산 대비 안전마진 확보, "무조건 보유 행복" | 자산가치 인식·해제(인수·분할) 시 |

**경기순환주 핵심 함정**: 낮은 P/E가 *정점*(곧 하강) 신호일 수 있음 — 저점에서는 오히려 P/E가 높음.

---

## 3. PEG 비율 (Lynch 시그니처)

### 기본 PEG
- 정의: **PEG = P/E ÷ 연간 EPS 성장률**
- 기본 원칙(원문): "공정가격 기업의 P/E는 성장률과 같다" → **PEG=1.0 공정**
- 방향(원문): "성장률의 절반 P/E는 매우 긍정, 2배는 매우 부정" → **PEG 0.5 = 바겐, PEG 2.0 = 고평가**
- 커뮤니티: PEG<1 매력 / ~0.5 매우매력 / >1.5~2 부진

### 배당조정 PEG (PEGY) — 방향 주의!
- **Lynch 원문 공식**: **(성장률% + 배당수익률%) ÷ P/E** — *클수록 좋음*
- 원문 임계값: "1 미만 부진, 1.5 양호, **2 이상이 목표**. 성장 15%+배당 3%+P/E 6 = 환상적인 3"
- ⚠️ 현대 교과서 PEGY = `P/E ÷ (성장+배당)`은 **역수**(작을수록 좋음). 코드화 시 방향 명시 필수.
- **본 프로젝트 데이터에서는 `dividend_yield` 100% NULL → PEGY 계산 불가** (§7).

---

## 4. "완벽한 주식" 13속성 (Ch.8)

1. 이름이 따분하거나 우스꽝스럽다 2. 따분한 사업을 한다 3. 불쾌한 사업을 한다 4. 분사(spin-off)다 5. 기관 미보유·애널리스트 미추종 6. 유해폐기물/마피아 소문 7. 우울한 구석 8. 무성장 산업 9. 틈새(niche·해자) 10. 계속 사야 하는 소모품 11. 기술 *사용자*(생산자 아님) 12. **내부자 매수** 13. **자사주 매입**

> 코드화 가능 속성: #12 내부자 매수·#13 자사주(데이터 부재로 본 백테스트 제외), #8/#9는 정성적. 13속성은 대부분 정성 — 본 백테스트는 §5 정량 지표 위주.

---

## 5. Lynch가 점검하는 숫자 (Ch.13/15 체크리스트)

- **P/E**: 자기 역사·동종 대비, 그리고 **성장률 대비**(PEG)
- **매출 비중(% of sales)**: 관심 제품이 실제 매출/이익의 몇 %인지
- **순현금/주(net cash per share)**: 현금+유가증권−장기부채 ÷ 주식수. Ford 예: 순현금 $16/주 → "주가 $16 밑으로 안 감"(바닥)
- **부채/자본**: 강한 재무(낮은 장기부채). 정상 ≈ 자본75/부채25. 부채 *종류*(은행부채 위험 vs 장기조달 안전)·만기
- **배당·배당성향**: 저성향=쿠션, 고성향=위험. Lynch는 대체로 무배당(재투자/자사주) 선호 — Slow Grower 제외
- **장부가치/숨은자산**: 장부가가 과대(불량재고)/과소(부동산·자원 원가 계상)일 수 있음 — 후자가 자산주
- **현금흐름**: FCF 선호, 저capex 기업
- **재고**: "재고가 매출보다 빨리 쌓이면 적신호"(제조업). 반대로 침체기업 재고 소진 = 조기 긍정
- **이익성장률**: 일관성 vs 산발성, P/E를 정당화하는 핵심 숫자 (>25~30% 비지속 경계)

---

## 6. 카테고리별 매수/매도 타이밍 요약

(§2 표 참조) — Stalwart: +50% 익절·교체 / Fast Grower: 성장둔화 시 매도 / Cyclical: 저점 매수·재고증가 시 매도 / Turnaround: 시장 오판+생존가능 시만 / Asset Play: 자산 인식 시 매도.

---

## 7. ⚠️ 한국 시장 데이터 실태 (라이브 DB 조회 2026-05-29 — 설계 결정 좌우)

> 직원이 `robotrader` DB(port 5433)를 직접 조회한 결과. 이 수치들이 모든 설계를 강제함.

| 사실 | 값 | 영향 |
|------|-----|------|
| financial_statements 행/종목 | 2,678 / **131** | 소형 펀더멘털 universe |
| report_date 범위 | 2004-03 ~ 2025-09 | 장기지만 대부분 가격데이터 이전 |
| report_date 월 분포 | **12월 91%(2,445)**, 9월 137, 3월 75 | **데이터 사실상 연간**(분기 아님) |
| fiscal_quarter 컬럼 | **전 행 공란** | 분기 키 불가 |
| 2021+ 보고서(가격시대) | 641행 | 가격과 조인 가능한 건만 |
| **psr NULL** | **100%** | 자산주(psr<1) 룰 불가 |
| **dividend_yield NULL** | **100%** | PEGY·배당 룰 불가 |
| per NULL | 46% | PEG 분모 절반 손실 |
| roe / pbr / debt_ratio NULL | 45% / 39% / 39% | 룰별 universe 축소 |
| net_income/operating_profit/revenue NULL | ≈0% | **성장률은 raw NI/OP/매출로 계산**(PER 아님) |
| PEG 가능 행(per&NI, 2020+) | **412** (per 보유 79종목) | |
| 2021+ NI ≤ 0 | **18%** | PEG/성장 불안정 빈번 |
| **top_volume:50 ∩ 재무** | **10종목** | **표준 universe 사용 불가** |
| top_volume:100 / :200 ∩ 재무 | 27 / 66 | 여전히 얇음 |
| 재무종목 중 일봉 ≥120봉 | **46** | 거래 가능 기간 짧음 |
| per 보유 79종목 평균 일봉 | **124봉(~6개월)** | 종목당 가격 이력 6개월 |

**결정적 귀결**:
1. **universe = top_volume:50 사용 불가** (교집합 10). → **재무 보유 종목(131, per 보유 79)을 universe로** 사용. 단 **책간 비교성 깨짐**(이전 7권은 top_volume:50).
2. 성장률 = **YoY net_income**(연간, ~365일 전 보고서 대비), operating_profit fallback.
3. **no-lookahead**: report_date=기말 → 한국 사업보고서 90일 내 공시 → **LAG 105일** 후에야 "알려진" 데이터로 사용.
4. **PEG 가드**: prior/curr NI ≤0 제외, |성장률|>300% 캡, per≤0/NULL 제외.

---

## 8. 코드화 대상 룰 4종 (가용 컬럼 한정 — psr/dividend_yield 제외)

> 모두 point-in-time fs_curr/fs_prior 조인 결과를 ctx로 주입(Minervini rs_value 방식). side="buy".

### rule_fast_grower (Lynch 최애, conf 78)
```
PEG < 1.0  AND  g_ni in [20,50]  AND  debt_ratio < 80  AND  roe > 10
AND net_income>0 AND prior_net_income>0
(옵션 타이밍: RSI(14) < 50)
```

### rule_stalwart (10~20% 성장 안정, conf 70)
```
g_ni in [10,20]  AND  PEG < 1.5  AND  roe > 10  AND  debt_ratio < 100  AND  net_margin > 0
(dividend_yield>0 원의도였으나 100% NULL → net_margin>0 대체)
```

### rule_value_balance_sheet (자산주 대체 — psr 사망, conf 65)
```
pbr < 1.0  AND  debt_ratio < 50  AND  0 < per < 12  AND  net_income > 0
(psr<1 불가 → pbr<1 + 저per + 저부채로 자산주 발상 표현)
```

### rule_garp_combo (PEGY 대체 — dividend_yield 사망, conf 72)
```
PEG < 1.2  AND  g_ni > 15  AND  roe > 12  AND  debt_ratio < 120  AND  operating_margin > 5
```

```
ALL_RULES = [rule_fast_grower, rule_stalwart, rule_value_balance_sheet, rule_garp_combo]
```

---

## 9. 청산 Variant

| 항목 | Variant A (Lynch 의도) | Variant B (획일) |
|------|----------------------|------------------|
| sl | 0.12 (운영 lynch 0.15보다 약간 타이트) | 0.08 |
| tp | 0.50 (멀티배거 허용) | 0.12 |
| trail | 없음 | 없음 |
| mh | 120 (운영 lynch 일치) | 20 |

- warmup_bars=20 (재무가 논지, RSI만 warmup). forced_close 비중이 높을 것 → 리포트에 명시.

---

## 10. 기존 운영 전략과 구분

- 운영 `strategies/lynch/`: PEG≤1.3 단일 룰(영업이익성장+RSI<35). Fast Grower 한 측면만.
- 연구판 `strategies/books/lynch_one_up/`: 4룰(6카테고리 매핑), 별도 위치. **혼동 금지.**

---

## 11. 리스크

1. **universe 붕괴/극소 N**: top_volume:50∩재무=10, 전체 재무 131(per 79, ≥120봉 46). 고분산 → PnL 과해석 금지, n_trades≥15 전 순위화 금지
2. **연간 데이터**: 12월 91%, 분기 불가 → 신호 최대 ~15개월 stale
3. **짧은 가격 이력**: 종목당 ~124봉(6개월) + 105일 lag + YoY warmup → live 적격 창 수개월. forced_close 지배
4. **고 NULL**: psr/dividend_yield 100%, per/roe ~45%
5. **PEG 불안정**: NI≤0 18% → 부호반전·폭발 성장 (예: 000050 −135→+236). 가드 필수
6. **생존편향**: 131종목은 관심종목 위주 적재 추정 → 상폐 누락 → PnL 낙관
7. **BULL 편향**: 2021~2026 랠리 포함

---

## 12. 참고 자료

### 1차
- Lynch, Peter. *One Up on Wall Street*. 1989. (Ch.8 13속성, Ch.11 2분드릴, Ch.13/15 숫자 체크리스트, Ch.17 매수/매도 타이밍)
- Lynch, Peter. *Beating the Street*. 1993.

### 2차
| 제목 | URL |
|------|-----|
| PEG ratio — Wikipedia | https://en.wikipedia.org/wiki/PEG_ratio |
| StableBread — Lynch Valuation | https://stablebread.com/peter-lynch-stock-valuation/ |
| The Balance — Lynch's secret formula | https://www.thebalancemoney.com/peter-lynch-s-secret-formula-for-valuing-a-stock-s-growth-3973486 |
| Cabot — 13 attributes | https://www.cabotwealth.com/daily/stock-market/ingredients-perfect-stock-according-peter-lynch |
| Sven Carlin — 6 categories buy/sell | https://svencarlin.com/when-to-buy-stocks-when-to-sell-stocks/ |
| Dr Wealth — Lynch playbook | https://drwealth.com/the-peter-lynch-investing-playbook/ |
| Dividend.com — PEGY | https://www.dividend.com/dividend-investing-101/understanding-the-dividend-adjusted-peg-ratio/ |
| Quantamental Trader — PEGY 상세 | https://quantamentaltrader.substack.com/p/peter-lynchs-pegy-method-a-detailed |

---

*Phase 1 (조사) 완료. 다음: 데이터 제약(특히 universe 교체로 인한 책간 비교성 문제)에 대한 사장님 결정 후 Phase 2 설계.*
