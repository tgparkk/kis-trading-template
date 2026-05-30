# Book 14 — 강창권 『주식투자 단기 트레이딩의 정석』 (2026-05-30)

> 트레이딩 책 조사 시리즈 14권째. 한국 토착 단기 트레이딩(단타/스윙) 전문서.
> book_id: `haru_silijeon`(분봉) / `haru_silijeon_daily`(일봉). universe top_volume:50.
> 상세 리포트: [../reports/books_research/haru_silijeon/report.md](../reports/books_research/haru_silijeon/report.md)

## 1. 전자책 실물 판독 (이 책의 특기)

- 종이책/PDF가 아닌 **Google Play 전자책** → 텍스트 직접 추출 불가.
- **화면 자동 캡처 파이프라인**: PowerShell 화면캡처 → 2x 크롭 확대 → 직원 분담 이미지 판독(OCR 아님).
- Chrome 활성화 + SendKeys RIGHT **자동 페이지 넘김**, 배치(b1_xx)·세그(A~D) 분담.
- 추정이 아니라 **원문 차트·박스 기준** 코드화. 흐림 구간은 카탈로그에 불확실 표기.
- 산출물: 판독노트(reading_notes.md, notes_seg_A~D.md) + **A등급 14전략 카탈로그**(strategy_catalog.md).

## 2. 코드화 (분봉 6 + 일봉 7)

A등급 14전략 중 minute_candles/daily_prices만으로 구현 가능한 것을 코드화:
- **분봉 6룰**: ck480(시그니처), open_two_red_then_green, prev_high_break, ma_5_10_pullback, ma_240_480_support, ma20_pullback (+ all_AND).
- **일봉 7룰**: daily_ma5_10_follow, daily_ma20_pullback, daily_ma60_doji_rebound, daily_trend_filter_240_480, daily_swing_pullback, daily_new_high_breakout, daily_vol300_longma_break (+ all_AND). variant A(trail MA)/B(sl8%/tp12%/mh20).
- 수급(외국인/기관/프로그램)·뉴스/테마·시간외/NXT 의존 전략(B/C등급)은 데이터 부재로 제외.
- **pytest 139개 통과**(진입/청산 규칙 단위 검증).

## 3. 백테스트 결과

### 분봉 6룰 (top_volume:50, 3기간 2025-10/2026-04/2026-05 — 전부 음수)
| 룰 | 거래 | PnL 범위 | 판정 |
|---|---|---|---|
| ck480 (시그니처) | 7~44 | −0.12~−0.57% | 표본 부족(조건 빡빡) |
| open_two_red_then_green | 89~222 | +0.10~−1.55% | 그나마 중립 |
| prev_high_break | 468~559 | −2~−3% | 손실 |
| ma_5_10_pullback | 1.6~3천 | −6.75~−26.55% | 과매매 |
| ma_240_480_support | 3~5천 | −18~−30% | 무력 |
| ma20_pullback | 1~1.2만 | **−50%대** | 과매매 참사 |
| all_AND | 0 | 0% | 동시충족 불가 |

### 일봉 7룰 (top_volume:50, daily_full 2021~2026)
**Variant B 베스트**: ma5_10_follow 1000T **+46.15%** Sh0.34 / ma20_pullback(tp10%) 695T +16.00% **Sh0.44** hit51.8% / new_high_breakout 285T +19.99% Sh0.32 / swing_pullback 482T +11.55% Sh0.35 / trend_filter_240_480 +8.64%.
**Variant A**: new_high_breakout 177T +22.29% Sh0.33 / trend_filter_240_480 +22.40% / ma5_10_follow +13.06% / ma20_pullback +5.75%.
all_AND 0거래.

## 4. 결론

1. **분봉 단타 전멸 = 미국 분봉 3책과 동일 운명**: 강창권 베스트 분봉(open_two_red_then_green ±0%)은 Bellafiore fade_vwap(+1.74%)·Raschke anti(+10.24%)에 못 미침. ck480 표본부족, ma20_pullback −50% 과매매. "분봉 단타는 한국 시장에서 어렵다" 14권째 재확인.
2. **강창권의 가치는 분봉이 아니라 일봉 이평/돌파 매매**: 같은 룰셋을 일봉으로 옮기면 6/7이 양 PnL. ma5_10 +46%, ma20눌림 Sh0.44/hit51.8%, 신고가 +20%대.
3. **Sharpe 0.44 = 중간**: 기술적 베스트(Elder 0.68)보다 낮고 펀더멘털(~0.1)보다 높음. **CANDIDATE 부적격**. 단 일봉 룰은 국면 분해·walk-forward 추가 검증 가치.

## 5. 한계
ck480 표본부족(3기간 91거래) / 분봉 데이터 1년3개월(전부 폭등장) / VI·수급 데이터 부재로 일부 룰 근사 / 익절% 미명시(ck480·20일선눌림만 명시) → 나머지 variant A/B 자체 설정.

## 6. 미커밋
git commit 미실행(사장님 승인 후 매니저가 선별 커밋). 신규/변경 파일:
- `reports/books_research/haru_silijeon/report.md` (신규)
- `reports/books_research/index.md` (Book 14 행 + 결과 섹션 추가)
- `memory/changelog-2026-05-30-book14-kang-changgwon.md` (신규, 이 파일)
- `reports/books_research/haru_silijeon/` (카탈로그·판독노트·분봉 results 21파일)
- `reports/books_research/haru_silijeon_daily/` (일봉 results 14파일)
- `reports/books_research/leaderboard.parquet` (haru 38행 추가)
- (코드) 강창권 전략 구현 + pytest 139 — 별도 디렉토리
