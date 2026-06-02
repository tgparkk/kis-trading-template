# 데이트레이딩 시장국면 + 2-트랙 국면 체계 — 전문가 조사·설계

> 작성: 2026-06-02 · 범위: 인트라데이/데이트레이딩(분~시간, EOD청산) 전용 국면 + 스윙 트랙과의 통합
> 선행: [_EXPERT_regime_methods.md](_EXPERT_regime_methods.md)(스윙=일봉 장기 트랙, 트랙A 정의)
> **★절대조건: No Look-Ahead** — 장중 국면은 현재 봉(≤t)까지의 데이터로만. 미래 봉 금지.
> 원칙: **보유 지평 = 국면 측정 지평.** 데이트레이딩은 SMA120 부적합 → 당일·장중 단기 국면.

---

## 0. TL;DR

1. **스윙(트랙A)은 선행 보고서가 확정** — KOSPI 종가 SMA120 + 20일기울기 + %above MA120 breadth + 20일RV백분위, forward-only confirm, 6구간 라벨. 본 보고서는 그 위에 **트랙B(데이트레이딩 당일·장중)** 를 추가한다.
2. **데이터 현실(점검완료)**: `minute_candles`에 **지수 ETF가 사실상 없음**(069500 KODEX200 = 0행, 229200 = 291행/1일뿐). 대형주는 풀커버(005930·035420·035720·373220 각 ~115k행, 2025-02-24~2026-06-01). 1분봉, 09:00:00~15:30:00, **최근일 300종목/일**(당일 top-volume 유니버스), 총 1,373종목·328일. → **장중 지수 프록시는 ETF 불가, 대형주 바스켓 + 전종목 분봉 시장폭 합성으로 직접 구축해야 한다.**
3. **추천 트랙B 1안 = "장중 시장 프록시(대형주 등가중 합성지수)의 누적수익·VWAP위치 + 개장범위(OR) + 장중 시장폭(분봉 상승비율) + 갭" 4요소 진입게이트.** 모두 9시 이후 누적·현재봉까지로만 계산 → PIT-safe.
4. **2-트랙 공통 인터페이스**: `regime_at(timestamp, granularity, universe)` → `(direction, vol, trendiness)`. granularity='daily'면 트랙A(일봉), 'minute'면 트랙B(당일·장중). 전략은 자신의 보유지평에 맞는 트랙으로 매핑.
5. **전략 매핑**: A(스윙·일봉) = Elder·Minervini·가치책(문병로/홍용찬)·ma20/ma5·close_betting(종가매매)·weinstein. B(데이트레이딩·분봉) = surge_fade·aziz_day_trade·bellafiore_playbook·유지윤(daytrading_3methods)·haru_silijeon·raschke.
6. 웹조사 수행함(2026-06): VWAP기울기=trend/range 판별, 갭/ATR 분류, ORB 15~30분, 누적TICK·breadth 동조 = trend day 확인. 한국은 TICK 미보유 → **분봉 상승종목비율(합성 ADD/breadth)** 로 대체.

---

## 1. 데이트레이딩 국면 방법 카탈로그

각 방법의 입력·규칙·PIT위험. **"개장전 확정분"(전일종가·갭)과 "장중 갱신분"(현재봉까지 누적)** 을 구분 표기.

| # | 방법 | 입력 | 규칙(요지) | 분류축 | 개장전/장중 | PIT위험 |
|---|---|---|---|---|---|---|
| 1 | **개장갭(Opening Gap)** | 전일 일봉 종가, 당일 시가 | `gap = (open − prev_close)/prev_close`. ATR정규화: `gap/ATR14`. <0.5common·0.5~1 standard·>1 breakaway | 방향(상/하) + 위험 | **개장전 확정**(09:00 시가) | 낮음(전일종가는 EOD확정, 시가는 09:00 단일봉) |
| 2 | **개장범위(Opening Range, OR)** | 첫 N분(5/15/30) 분봉 H/L | `ORH=max(high[09:00..09:N])`, `ORL=min(low)`. 종가>ORH=상방추세 단서, <ORL=하방, 내부=박스 | trend vs range + 방향 | **09:N 시점 확정 후 장중 고정** | 낮음(N분 경과 후에만 사용 → 그 전엔 미정) |
| 3 | **지수 장중 VWAP 상/하회** | 프록시 분봉 OHLCV | 합성지수 `VWAP_t = Σ(price·vol)/Σvol`(09:00부터 누적). price>VWAP & VWAP기울기>0 = 강세추세일, 횡보=VWAP평탄·반복교차 | 방향 + trendiness | **장중 누적**(현재봉까지) | 낮음(누적은 과거봉만) |
| 4 | **장중 추세(누적수익·단기MA)** | 프록시 분봉 | `cum_ret_t = px_t/open − 1`(당일 누적). 단기MA(분봉 SMA20/60) 정렬. \|cum_ret\|·일관성 高 = trend day | 방향 + trendiness | **장중 누적** | 낮음 |
| 5 | **장중 실현변동성/ATR** | 프록시 분봉 | 당일 분봉수익 std(누적) 또는 분봉 ATR. 과거 동일시각 분포 대비 백분위 → HIGH/LOW vol | 위험(리스크오프) | **장중 누적**(시각정규화 필수) | 중(시각효과 — 아래 §5, U자형 변동성. 동일 분-of-day 트레일링 분포로 정규화) |
| 6 | **장중 시장폭(분봉 breadth)** | 전종목(유니버스) 분봉 | `adv_ratio_t = (당일 양봉/상승 종목수)/(전체)`. 또는 합성 ADD = 상승−하락 누적. >0.6 광범위강세, <0.4 약세, 0.5±=혼조 | 방향 확정 + trendiness | **장중 누적·단면** | 낮음(현재봉 단면) |
| 7 | **gap-and-go vs fade day** | 갭 + OR + 장중추세 | 갭방향으로 OR돌파+VWAP유지=gap-and-go(추세); 갭메우기·VWAP회귀=fade. 조합 라벨 | day type | **09:N~30분 확정** | 낮음 |
| 8 | **전일 추세 캐리** | 전일 일봉 | 전일 종가위치(고가권/저가권), 전일 방향 — 익일 갭·초반 편향 | 방향 보조 | **개장전 확정** | 낮음 |
| 9 | **요일/시간대 효과** | 시계열 통계 | 시초·마감 변동성↑, 점심대 둔화(한국은 점심휴장 無, 연속). 요일 편향(월요일 갭) | 메타(사이징·게이트) | 개장전 | 낮음(달력) |
| 10 | **변동성 레짐 게이트(VKOSPI류)** | VKOSPI 일봉 | 전일 VKOSPI>30=공포·z>2 스파이크 → 데이트레이딩 노출축소/페이드편향. **일봉이라도 개장전 게이트로 유효** | 위험(직교) | **개장전 확정**(전일 종가) | 낮음(`signals/vkospi.vkospi_at`이 이미 PIT-safe T-1 반환) |

### 웹 출처(2026-06)
- VWAP기울기로 trend day(추세, 눌림매수) vs range day(평탄, 페이드) 구분; 갭=`(open−prev_close)/ATR14` <0.5/0.5–1/>1 분류; gap-and-go=첫 20분내 OR고가 5분봉 돌파; VWAP 2σ 이탈 페이드는 range day에서만: [Tradewink VWAP](https://tradewink.com/learn/vwap-trading-strategy), [JournalPlus Opening Gap](https://journalplus.co/strategies/opening-gap-strategy/), [TrendSpider Anchored VWAP](https://trendspider.com/learning-center/anchored-vwap-trading-strategies/)
- ORB 첫 5/15/30분 정의·돌파 후 무회귀=trend day; 30분내 VWAP 0.3%+ 이격·첫 되돌림 50%미만이면 추세 지속확률↑: [HighStrike ORB](https://highstrike.com/opening-range/), [TradersMastermind ORB](https://tradersmastermind.com/trading-strategy-opening-range-breakout/), [FXOpen ORB](https://fxopen.com/blog/en/opening-range-breakout-strategy/)
- 시장내부(TICK·ADD·VOLD) **동조 + 극단 + 매끄러운 누적기울기** = 신뢰성 높은 trend day; TICK 한방향 30분 지속=조기 추세일 신호: [TOS NYSE TICK](https://tosindicators.com/research/nyse-tick-spot-trend-days-thinkorswim), [TOS Recognize Trend Days](https://tosindicators.com/research/recognize-trend-days-thinkorswim-indicators)

---

## 2. 당일(개장전) 국면 vs 장중(동적) 국면

데이트레이딩 국면은 **두 시제**로 나뉘며 진입게이트는 진입봉 시점까지의 정보만 본다.

- **당일 국면(개장전 확정, 09:00 고정)**: 전일종가·갭(#1)·전일추세캐리(#8)·요일(#9)·전일 VKOSPI 게이트(#10). 그날의 *편향(bias)* 설정. 라이브에선 09:00 시가 확정 후 한 번 계산하고 고정.
- **장중 동적 국면(현재봉까지 누적, 봉마다 갱신)**: OR(#2, 09:N 이후)·VWAP위치(#3)·누적수익/단기MA(#4)·장중RV(#5)·분봉breadth(#6)·day-type(#7). 진입 시점(예 09:15·09:30·매 분봉)마다 **그 시점까지의 누적**으로 재판정.

**진입게이트 형태 정의** — 전략이 t분봉에서 진입신호를 낼 때 호출:
```
regime_intraday(t) = (
    bias        = {GAP_UP, GAP_DOWN, FLAT}            # 개장전 확정
    direction   = {UP, DOWN, NEUTRAL}                 # 프록시 누적수익·VWAP위치(≤t)
    trendiness  = {TREND, RANGE}                      # OR돌파·VWAP기울기·breadth동조(≤t)
    vol         = {HIGH, LOW}                         # 장중RV 시각정규화 백분위(≤t) + VKOSPI게이트
)
```
전략은 자기 성격에 맞는 조합만 통과:
- **추세추종형(gap-and-go, ORB, surge 돌파)**: `trendiness==TREND` & `direction`이 신호방향과 일치할 때만 진입.
- **역추세/페이드형(fade_vwap, surge_fade)**: `trendiness==RANGE` & `vol!=HIGH`(고변동 추세일엔 페이드 금지)일 때만.
- **공통 리스크오프 차단**: `vol==HIGH` & 전일 VKOSPI 스파이크면 신규진입 축소/금지.

---

## 3. 2-트랙 통합 스펙

### 공통 인터페이스
```python
def regime_at(ts, granularity, universe="top_volume:50", proxy_basket=None):
    """
    ts          : 판정 시점 (date면 일봉 EOD, datetime이면 장중 분봉 시점)
    granularity : 'daily' → 트랙A(스윙),  'minute' → 트랙B(데이트레이딩)
    반환         : Regime(direction∈{BULL/UP, BEAR/DOWN, SIDEWAYS/NEUTRAL},
                          vol∈{HIGH,LOW}, trendiness∈{TREND,RANGE} [B만 의미], asof=ts)
    PIT 불변식   : 반환은 ts 이하 데이터로만 (트랙A=≤T일 종가, 트랙B=≤ts 분봉)
    """
```
- **트랙A(스윙=일봉 장기)** = 선행 보고서 §5 채택안 그대로. KOSPI(`daily_prices stock_code='KOSPI'`) SMA120+20일기울기, 전종목 %above MA120 breadth, 20일RV 252일백분위, confirm_days=3 forward-only 디바운스. 6구간 {BULL/BEAR/SIDEWAYS}×{HIGH/LOW_VOL}.
- **트랙B(데이트레이딩=당일·장중)** = 본 보고서 §4. 장중 합성 프록시 기반, 진입봉 시점까지 누적.

### 전략 → 트랙 매핑표

| 전략(폴더) | 보유지평 | 트랙 | 국면 사용법 |
|---|---|---|---|
| `elder_ema_pullback` / books/elder_triple_screen | 스윙(일봉) | **A** | 주봉·일봉 추세필터, BEAR게이트 |
| `minervini_volume_dryup` / books/minervini_vcp | 스윙 | **A** | BULL확정 진입 |
| books/moonbyungro_metric, books/hongyongchan, oshaughnessy_value, greenblatt_magic, lynch | 스윙(가치/펀더) | **A** | 국면 분해·BEAR방어 |
| `book_pullback_ma20` / `book_pullback_ma5` | 스윙(눌림) | **A** | BULL/SIDEWAYS 적합 |
| books/close_betting(종가매매) | 익일 갭 목표(일봉) | **A** | 일봉 국면(장막판→익일) |
| books/weinstein_stages | 스윙(주봉 stage) | **A** | 주봉 stage |
| `daytrading_3methods`/`_breakout`(유지윤) | **데이트레이딩(분봉, EOD청산)** | **B** | 진입봉 trendiness=TREND·direction 일치 게이트 |
| books/surge_fade | **데이트레이딩(급등주 분봉)** | **B** | fade=RANGE&저변동 / surge돌파=TREND |
| books/aziz_day_trade | **데이트레이딩** | **B** | gap-and-go(갭·OR·VWAP) |
| books/bellafiore_playbook(fade_vwap 등) | **데이트레이딩** | **B** | fade_vwap=RANGE 게이트 |
| books/haru_silijeon | **데이트레이딩(분봉)** | **B** | 장중 추세·breadth |
| books/raschke_street_smarts | **데이트레이딩/스윙혼합** | **B**(분봉룰)/A(일봉룰) | 룰별 |

> 경계 케이스: **close_betting(종가매매)** 은 분봉으로 진입 타이밍을 잡아도 *보유지평이 익일 갭(오버나잇)* 이므로 국면은 일봉(A)으로 판정 — "보유=측정" 원칙 적용. raschke처럼 분/일 혼합 룰은 룰 단위로 트랙 지정.

---

## 4. ★추천 PIT 데이트레이딩 국면 1안 (트랙B)

### 4.1 장중 시장 프록시 — 우리 데이터 실현안

ETF 부재 → **2종 합성**(둘 다 `minute_candles`만으로 PIT 계산):

**(a) 합성 시장지수 = 대형주 등가중 누적수익 바스켓** (방향·VWAP·추세·변동성 산출용)
- 바스켓 = `minute_candles` 풀커버 대형주: **005930(삼성전자)·035420(NAVER)·035720(카카오)·373220(LG엔솔)** + 가용시 000660(SK하이닉스, 2026-04까지). KOSPI200 대표 + 풀커버 4종 핵심.
- 각 종목 당일 누적수익 `r_i,t = close_i,t/open_i,09:00 − 1`, **등가중 평균** `Mkt_t = mean_i(r_i,t)`. (가격수준 차이 제거 위해 종목별 정규화 후 평균 — 시총가중도 옵션이나 005930 지배 → 등가중 권장.)
- 합성 VWAP: 종목별 `vwap_i,t = Σ(close·vol)/Σvol`(09:00 누적), 시장 VWAP위치 = `mean_i(close_i,t/vwap_i,t − 1)` 부호.
- **장점**: 코스피200 대형주 = 외국인·기관 주도, 시장방향 대표성 높음. **한계**: 코스닥/중소형 급등주 국면은 약하게 반영 → 급등주 전략(surge)엔 (b) 병행.

**(b) 합성 시장폭(breadth/ADD) = 당일 유니버스 분봉 단면** (광범위성·동조 확정용)
- 매 t분: 그 시점 유니버스(당일 ~300종목) 중 `r_i,t = close_i,t/open_i,09:00 − 1 > 0`인 비율 = `adv_ratio_t`.
- 합성 ADD = `Σ(상승) − Σ(하락)` 누적 또는 `2·adv_ratio − 1`. **>0.6 광범위강세 / <0.4 약세 / 중간 혼조.**
- **장점**: 전종목 단면 = TICK/ADD의 한국판 대체(한국은 NYSE TICK 없음). 소수 대형주 착시 차단.

> 두 프록시 모두 **현재봉까지 누적** → No Look-Ahead 자동 충족. 라이브에선 데이터수집 루프가 이미 유니버스 분봉을 수집하므로 추가 조달 불필요.

### 4.2 추천 국면 정의 (지표·기간·임계값)

진입봉 시점 t(예 09:15 이후 매 분봉)에서:

| 축 | 지표 | 기본 임계값 | 시제 |
|---|---|---|---|
| **bias** | `gap = (open_idx − prev_close_idx)/prev_close_idx`, ATR14정규화 | \|gap/ATR\|≥1.0 → GAP_UP/DOWN, else FLAT | 개장전 |
| **OR** | 첫 **15분** OR: ORH/ORL (09:00~09:15) | t≥09:15에만 유효; 프록시>ORH=상방, <ORL=하방 | 09:15 고정 |
| **direction** | 프록시 누적수익 `Mkt_t` + VWAP위치 | `Mkt_t>+0.3%` & price>VWAP → UP; `<−0.3%` & price<VWAP → DOWN; else NEUTRAL | 장중 누적 |
| **trendiness** | OR돌파 유지 + VWAP기울기(최근30분) + breadth동조 | **TREND**: OR한쪽돌파 & VWAP기울기 방향일치 & adv_ratio가 같은방향 극단(>0.6 or <0.4); **RANGE**: 그 외(VWAP반복교차·breadth 0.5±) | 장중 누적 |
| **vol** | 장중RV = 프록시 분봉수익 std(09:00~t) **시각정규화 백분위**(과거 N일 동일 분-of-day 분포 대비) | 백분위≥0.67 → HIGH, + 전일 VKOSPI z>2 스파이크면 HIGH 강제 | 장중 누적 + 개장전 |

**최종 라벨**: `(bias, direction, trendiness, vol)`. 게이트 적용은 §2 형태.

**디바운스(장중판)**: 라벨 깜빡임 억제 위해 trendiness/direction은 **연속 K분봉(기본 3) 동일 시 전환** — 과거봉만 사용, forward-only(스윙 confirm_days의 분봉판).

### 4.3 멀티버스 스윕 파라미터 (트랙B 국면정의 자체 탐색)

| 파라미터 | 후보 | 의미 |
|---|---|---|
| `or_minutes` | 5, 15, 30 | 개장범위 길이 |
| `proxy_basket` | bigcap4(005930·035420·035720·373220), bigcap+000660, top_volume:20 등가중 | 합성지수 구성 |
| `proxy_weight` | equal, mcap | 등가중 vs 시총가중 |
| `dir_thresh` | 0.2%, 0.3%, 0.5% | UP/DOWN 누적수익 컷 |
| `breadth_hi/lo` | 0.60/0.40, 0.65/0.35, 0.55/0.45 | breadth 동조 극단 |
| `vwap_slope_lb` | 15, 30, 60 (분) | VWAP기울기 측정창 |
| `vol_pct_hi` | 0.60, 0.67, 0.75 | HIGH_VOL 컷(시각정규화 백분위) |
| `intraday_confirm_bars` | 0, 3, 5 (분봉) | 장중 디바운스 |
| `gap_atr_thr` | 0.5, 1.0, 1.5 | 갭 분류 컷 |
| `index_for_gap` | bigcap합성, KOSPI일봉(전일) | 갭 기준 |

> 스윕 목적함수 = **라벨 자체가 아니라 트랙B 전략들의 OOS 성과 분리도**(TREND게이트 시 추세전략 Sharpe↑·RANGE게이트 시 페이드 Sharpe↑). 선행 보고서·MEMORY 교훈대로 **정본 유니버스(top_volume:50) + 약세장 포함 OOS**로 재확인(소유니버스·단일국면 in-sample 최적화 함정 회피).

### 4.4 구현 스케치
```python
# regime_intraday.py (신규 제안) — 전부 PIT-safe, minute_candles SSOT
import numpy as np, pandas as pd

BIGCAP4 = ["005930","035420","035720","373220"]

def synth_index(minute_df, basket=BIGCAP4):
    # minute_df: 당일 분봉 (code,time,open,high,low,close,volume), 09:00부터
    # 종목별 당일 누적수익 등가중 → 합성 시장수익 Mkt_t (현재봉까지만)
    out = {}
    for code, g in minute_df[minute_df.code.isin(basket)].groupby("code"):
        g = g.sort_values("time"); op = g.close.iloc[0]  # 09:00 봉 사용 시 open
        out[code] = (g.set_index("time").close / op - 1.0)
    mkt = pd.DataFrame(out).mean(axis=1)        # 등가중, index=time
    return mkt  # cum return, 각 time은 그 시점까지

def synth_vwap_pos(minute_df, basket=BIGCAP4):
    pos = {}
    for code, g in minute_df[minute_df.code.isin(basket)].groupby("code"):
        g = g.sort_values("time")
        cum_pv = (g.close * g.volume).cumsum()
        cum_v  = g.volume.cumsum().replace(0, np.nan)
        vwap = cum_pv / cum_v
        pos[code] = (g.set_index("time").close / vwap - 1.0)
    return pd.DataFrame(pos).mean(axis=1)        # >0 = 평균 VWAP 위

def adv_ratio(minute_df_universe):
    # 전 유니버스 분봉: 각 time별 (당일누적수익>0 종목수)/(전체)
    g = minute_df_universe.sort_values(["code","time"])
    op = g.groupby("code").close.transform("first")
    g["ret"] = g.close / op - 1.0
    return g.groupby("time").ret.apply(lambda s: (s > 0).mean())  # adv_ratio_t

def opening_range(minute_df_idx, or_min=15):
    first = minute_df_idx[minute_df_idx.time <= add_min("090000", or_min)]
    return first.high.max(), first.low.min()    # ORH, ORL (09:0N 이후에만 사용)

def regime_intraday(t, mkt, vwap_pos, advr, orh, orl, gap_atr,
                    dir_thr=0.003, br_hi=0.6, br_lo=0.4, conf=3):
    m = mkt.loc[:t].iloc[-1]; vp = vwap_pos.loc[:t].iloc[-1]; ar = advr.loc[:t].iloc[-1]
    direction = "UP" if (m> dir_thr and vp>0) else ("DOWN" if (m<-dir_thr and vp<0) else "NEUTRAL")
    or_break  = (mkt.loc[:t].iloc[-1] is not None)  # 의사코드: px>ORH/ <ORL 판정
    trend = "TREND" if ((direction!="NEUTRAL") and (ar>br_hi or ar<br_lo)) else "RANGE"
    # vol/bias/디바운스(conf분 연속)·VKOSPI 게이트는 외부 결합
    return direction, trend
```
**통합 지점**
- `signals/`에 `regime_intraday.py` 신규(스윙 `regime_pit.py`와 병렬). 공통 `regime_at(ts, granularity,...)` 디스패처가 granularity로 A/B 라우팅.
- 라이브: 진입 전 `ctx`에서 당일 유니버스 분봉(이미 수집됨)으로 호출 → 게이트. 백테스트: `book_backtester`/멀티버스가 분봉 슬라이스(≤t)로 동일 함수 호출(동등성 보장).
- 전일 VKOSPI 게이트는 기존 `signals/vkospi.vkospi_at(scan_date)`(PIT-safe T-1) 재사용.

---

## 5. 한국 데이트레이딩 특수성

1. **연속 거래·점심휴장 없음**: 09:00~15:30 단절 없음(美 ORB 그대로 적용 가능). **변동성 U자형**(시초·마감 高, 점심대 둔화) → 장중RV/breadth는 **분-of-day 정규화 필수**(절대값 비교 금지, §4.2 vol축). 14:50 단일가·15:20 동시호가 직전 변동 급증.
2. **상하한가 ±30%**: 급등주(surge) 전략은 상한가 근접 시 유동성·체결 왜곡 → trendiness=TREND이라도 상한가벽 게이트 필요. 갭/누적수익이 ±30%에 눌려 분포 절단.
3. **동시호가**: 시가(08:30~09:00 단일가)·종가(15:20~15:30) 동시호가 봉은 연속체결과 성격 다름 → OR은 09:00 연속봉부터, EOD청산은 15:20 전 권장.
4. **개장갭 잦음·외국인 야간 영향**: 미국장·환율 야간 변동이 한국 시초 갭에 직결 → bias(개장전) 비중 큼. 전일 추세 캐리(#8)와 결합.
5. **지수 장중 부재(우리 데이터)**: NYSE TICK·실시간 지수 없음 → **합성 프록시가 유일 경로**(§4.1). 라이브 KIS는 업종지수 현재가 API가 있으나 백테스트 일관성 위해 합성 프록시로 통일 권장(동일 함수 라이브·백테스트 공용).
6. **코스피/코스닥 디커플링**: 급등주·중소형(surge·유지윤)은 코스닥 성격 → 합성 프록시 바스켓에 코스닥 대표 추가 검토(현재 minute_candles 코스닥 대형주 커버 점검 필요; 없으면 유니버스 breadth가 대체).

---

## 6. 조달/후속 과제
- minute_candles **코스닥 대표주 커버리지** 점검(중소형 급등 국면 프록시 보강). 현재 풀커버 확인된 건 KOSPI 대형주 위주.
- 업종지수/실시간 코스피 장중값(KIS API)을 **선택적 검증축**으로 백필 가능하나, 백테스트-라이브 동등성 위해 1차안은 합성 프록시 단일 SSOT 유지.
- 트랙B 라벨을 일자별로 사후 저장 시 `market_regime` 테이블에 `method='intraday_synth'`로 분리(스윙 라벨과 혼동 금지).
