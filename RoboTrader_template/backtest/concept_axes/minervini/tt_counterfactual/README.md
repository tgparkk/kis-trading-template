# TT 게이트 반사실 원장 (`run_ledger.py`)

> 사전등록 **`../PREREG_TT_COUNTERFACTUAL.md`** 의 실행부. 이 README 는 **쓰는 법**만 적는다 —
> 규칙의 정본은 사전등록이고, 아래 숫자는 전부 그쪽에서 동결된 값을 옮긴 것이다.
>
> 🔴 **아직 한 번도 실행하지 않았다.** 검증은 `python -m py_compile` 만 돌렸다.
> 실행 전에 아래 **§5 실행 전 확인 3건**을 사장님/관리자가 확정해야 한다.

## 1. 무엇을 만드나

2026-08-25 에 TT 게이트를 `shadow` → `on` 으로 올렸다(`86ff02d`). `on` 은 후보 명단을
**통째로 교체**한다 — 그래서 「버린 쪽이 실제로 나빴는가」를 매일 재는 원장이 필요하다.

매 거래일 **D**(= 진입일)마다 **D-1 일봉**으로 라이브 스크리너를 재현해 네 갈래를 만든다.

| arm | 정의 | 뜻 |
|---|---|---|
| `P` | dryup ∧ TT 통과 | `on` 이 **사는** 것 |
| `X` | U − P (dryup 통과했지만 TT 탈락) | `on` 이 **버린** 것 ← 반사실의 핵심 |
| `R` | U 에서 무작위 3종목 × 시드 0..19 | 귀무 — 「고르는 행위」 자체 |
| `L` | 그날 라이브가 실제로 산 것 (`virtual_trading_records`) | 참고 arm (체결가·시각 그대로) |

`U` = dryup 통과 전체 = `P ∪ X`. 별도 arm 으로 적재하지 않는다(합집합이라 중복이다).

## 2. 라이브 룰을 «다시 구현하지 않는다»

2026-08-25 교훈 — 룰이 두 벌이면 정합 논의가 헛돈다. 이 스크립트는 라이브 심볼을 그대로 import 한다.

| import | 어디서 | 무엇을 맡나 |
|---|---|---|
| `MinerviniVolumeDryupScreenerAdapter` | `strategies/minervini_volume_dryup/screener.py` | 유니버스 → `base_filter` → 일봉 적재 → 불가능봉 가드 → RS 백분위 → **dryup·TT 판정** 전부 |
| `QuantDailyReader` | `db/quant_daily_reader.py` | 일봉 로더(청산용). `volume × adj_factor` 는 **로더가 이미** 한다 — 재곱 금지 |
| `resolve_daily_source_db` · `resolve_minute_source_db` | `config/constants.py` | DB명 SSOT(하드코딩 금지) |
| `utils.logger` | `utils/logger.py` | **핸들러 슬롯을 NullHandler 로 선점하려고만** 읽는다 (§4 참조) |

`rule_volume_dryup` · `rule_trend_template` · `compute_rs_percentile_12w` 는 **직접 부르지 않는다.**
어댑터의 `match()` / `build_context()` 안에서 파라미터 기본값 그대로 돌아간다.

### U 를 통째로 받는 법 (재구현 회피의 핵심)

`scan()` 은 ①`max_candidates` 로 상위만 잘라 돌려주고 ②`mode="on"` 이면 TT 탈락을 버린다.
그래서 **`tt_filter_mode="shadow"` + `max_candidates=10**9`** 으로 부른다. 그러면

- 반환 `CandidateStock` 리스트 = **U 전체**,
- 각 원소의 `reason` 끝에 `screener.py:match()` 가 찍은 `tt=0|1` 이 붙어 있어
  **P/X 가 「라이브가 판정한 그 값」으로** 갈린다. 룰 재평가 0회.

`shadow` 로 강제하는 것은 «관측 장치»이지 라이브 설정 변경이 아니다 — 라이브 `TT_FILTER_MODE`
는 건드리지 않고, `params` 오버라이드는 이 프로세스 안에서만 산다.

### 유니버스

`scan()` 내부의 `_load_universe()` + `base_filter()` 경로가 곧
`backtest/screener_universe.py:load_screener_universe()` 가 감싸는 그 경로다
(`strategies/_rule_screener_base.py:_load_universe` ↔ `screener_universe.py:_snapshot_to_universe`).
따로 부르면 **같은 스냅샷을 두 번 조회할 뿐**이라 `scan()` 한 경로로 통일했다.

## 3. 성과 계산 (사전등록 동결값)

- **진입** = D 09:05 `minute_candles` **종가**. 🔴 PK 는 `trade_date`(`'YYYYMMDD'`) — `date` 로 묶지 말 것.
  없으면 **D 일봉 시가**로 떨어지고 `entry_src` 에 `daily_open` 이 찍힌다. 둘 다 없으면
  행을 버리지 않고 `exit_reason=no_entry` 로 **남긴다**(조용한 누락 금지).
  arm `L` 만 실제 체결가(`entry_src=live_fill`, `entry_ts` 에 체결시각).
- **청산** = 일봉 판정. `low ≤ entry×0.92` → `sl`(체결 `entry×0.92`) / `high ≥ entry×1.12` → `tp`
  (체결 `entry×1.12`) / **같은 봉에서 둘 다면 `sl` 우선** / 20거래일 경과 → 그 봉 **종가** `max_hold`
  / 아직 안 끝났으면 `is_open=1`, `ret_*` 는 **빈 칸**(0 으로 위장하지 않는다).
- **비용** 왕복 **0.21%p** → `ret_net = ret_gross − 0.0021`.
- **금액가중** — 균등 **3,333,333원**을 정수 주수로 내려 `qty × entry_price` 를 가중치로 쓴다.
  (주수 내림이 없으면 금액가중 = 거래당 평균이 되어 칸이 죽는다.)

## 4. 안전 (라이브 트리에서 돌리므로)

- **DB 는 SELECT 만.** 접속을 `set_session(readonly=True)` 로 열어 **서버가** 쓰기를 막는다.
- **KIS API 호출 0.** 어댑터를 `broker=None, db_manager=None` 으로 만든다.
- 🔴 **라이브 로그 파일을 열지 않는다.** `utils/logger.py` 의 공유 파일 핸들러는 첫
  `setup_logger()` 때 `logs/trading_YYYYMMDD.log` 를 `RotatingFileHandler` 로 «연다» —
  봇이 도는 중에 연구 스크립트가 그 파일을 rotate 하면 라이브 로그가 깨진다.
  그래서 import «전에» `_shared_file_handler` 슬롯을 `NullHandler` 로 채워
  생성 분기(`utils/logger.py:56`)를 통째로 건너뛴다. 콘솔로만 출력한다.
- **운영 디렉토리 0줄 수정.** 이 폴더 밖에 쓰는 파일은 없다(원장 CSV 도 기본값이 이 폴더).
- ⚠️ **장중 실행은 피하라** — 어댑터가 유니버스 전 종목의 260봉을 읽어 DB 를 수백 회 친다.
  16:00 EOD 수집과도 겹치지 말 것.

## 5. 🔴 실행 전 확인 3건 (사전등록과 대조)

1. **청산 판정에 진입일 D 를 넣는가.** 기본은 **D+1 부터** — D 의 일봉 low/high 에는
   09:05 진입 «이전» 구간(09:00~09:05)이 섞여 있어, 그 값으로 sl/tp 를 때리면
   **살 수 없었던 체결**이 원장에 들어온다. 사전등록이 「D 포함」으로 못박았으면
   `--include-entry-day` 를 켜라. **두 정의는 같은 원장에 섞으면 안 된다**(섞으려면 파일을 나눠라).
2. **`R` 의 풀이 `U` 가 맞는가.** 여기서는 지시대로 `U`(dryup 통과)에서 뽑는다.
   `../run.py` 의 `R` 은 풀이 **`base_filter` 통과 전체**이고 10종목이다 — **다른 귀무다.**
   「어느 귀무에 대한 p 인가」를 결과 문서에 반드시 적을 것.
3. **`repro_ok=0` 인 날을 집계에 넣는가.** 기본 집계는 **`repro_ok=1` 인 날만** 쓴다
   (`--all-days` 로 해제). 원장에는 불일치도 **그대로 적재**한다 — 거르는 건 집계 단계다.

## 6. 실행

```bash
cd RoboTrader_template/backtest/concept_axes/minervini/tt_counterfactual

# 0) 컴파일 확인 (지금까지 돌린 유일한 검증)
python -m py_compile run_ledger.py

# 1) 리허설 — DB 읽기만, 파일 쓰기 0
python run_ledger.py --date 2026-08-26 --dry-run

# 2) 소급 적재
python run_ledger.py --from 2026-08-18 --to 2026-08-26

# 3) 매일 1회 (EOD 이후)
python run_ledger.py --date 2026-08-27

# 4) 집계만
python run_ledger.py --summary            # repro_ok=1 인 날만
python run_ledger.py --summary --all-days # 전부
```

`--out <dir>` 로 원장 위치를 바꿀 수 있다(기본 = 이 폴더의 `ledger.csv`).
적재는 **append** 이고 중복 방지 키는 **`date + code + arm + seed`** 라
같은 날을 여러 번 돌려도 행이 늘지 않는다.

### env (워크트리·클린 체크아웃)

라이브 트리에서는 `RoboTrader_template/.env` 를 `setdefault` 로 읽으므로 아무것도 안 해도 된다.
`.env` 가 없는 워크트리/CI 에서는 아래만 있으면 된다(전부 **읽기 전용** 접속).

```bash
export TIMESCALE_HOST=127.0.0.1     # WSL→Windows 면 172.23.208.1
export TIMESCALE_PORT=5433          # 🔴 5432 아님
export TIMESCALE_USER=robotrader
export TIMESCALE_PASSWORD=1234
# DB명은 env 로 주지 않는다 — resolver 가 정한다(항상 kis_template).
# 🔴 KIS_DATA_SOURCE·QUANT_DB·MINUTE_DB 는 2026-08-17 폐지 — 설정해도 무시된다.
```

## 7. 재현성 게이트 (`repro_ok`)

🔑 **스캔은 D 아침 09:00 에 D-1 일봉으로 돈다** — 그러니 진입일 D 의 계기는 **D 날짜 로그 파일**에 있다.

```
logs/robotrader_template_<YYYYMMDD>_*.log
  → "[minervini_volume_dryup] TT게이트 mode=… · dryup N · TT통과 M · 최종후보 K"
```

- `repro_ok=1` — 재현한 `dryup` 수 = N **이고** `TT통과` 수 = M.
- `repro_ok=0` — 하나라도 다르다. **행은 그대로 적재**하고 집계에서 뺀다.
  (원인 후보: 그 뒤 `daily_prices` 가 갱신됐다 / `market_cap` 채움 시점이 달라졌다 / 불가능봉 가드 대상이 바뀌었다.)
- `repro_ok=no_log` — 그날 로그에 `TT게이트` 줄이 없다. **2026-08-18 이전이 여기 해당**한다
  (TT 배선 `411ac9e` 는 8/18 저녁 발효 → 첫 줄은 8/19 09:00). 계기가 없을 뿐 스캔 재현은 된다.
- ⚠️ `trading_*.log` 는 `robotrader_template_*.log` 의 **부분집합**이라 쓰지 않는다.
- ⚠️ `rt` 로그는 콘솔 캡처라 **봇이 도는 중엔 0바이트로 보일 수 있다** — 당일치를 파싱하려면 EOD 이후에.

## 8. 원장 컬럼

| 컬럼 | 뜻 |
|---|---|
| `date` / `scan_date` | 진입일 D / 스캔에 쓴 D-1(직전 **거래일**) |
| `arm` / `seed` / `code` | arm(P·X·R·L) / R 만 0..19 / 종목코드 |
| `tt` | 라이브 `match()` 가 찍은 TT 판정(1·0). L 이 U 밖이면 빈 칸 |
| `entry_price` / `entry_src` / `entry_ts` | 체결가 / `minute_0905`·`daily_open`·`live_fill`·`none` / L 의 체결시각 |
| `exit_date` / `exit_price` / `exit_reason` | 청산일 / 청산가 / `sl`·`tp`·`max_hold`·`open`·`no_entry` |
| `bars_held` / `is_open` | 보유 거래일 / 1 이면 미종료(수익률 **빈 칸**) |
| `ret_gross` / `ret_net` | 총수익률 / 비용 0.21%p 차감 |
| `qty` / `notional` | 3,333,333원 내림 주수 / 금액가중 가중치 |
| `score` / `prev_close` | 라이브 랭킹 점수(`volume[-30:].mean()`) / D-1 종가 |
| `n_dry` / `n_tt` | **재현** 값 |
| `log_dry` / `log_tt` / `log_final` | **로그** 값 |
| `repro_ok` | `1` · `0` · `no_log` |
| `run_ts` | 적재 시각(중복키에는 안 들어간다) |

## 9. 알려진 한계 (결과 문서에 전재할 것)

- **표본이 며칠뿐이다.** 8/19 부터 계기가 있고, 20거래일 `max_hold` 라 **초기 며칠은 전부 `open`** 이다.
  진행중 건수를 반드시 병기하고, 종료 포지션만으로 낸 평균을 「성과」라고 부르지 말 것.
- **`P` 가 하루 1~3건이다**(실측 8/19~8/26: TT통과 3·3·3·1·1·2). 거래당 평균의 분산이 크다.
- **포트폴리오가 아니다** — K 한도·자금 배분·「이미 보유 중」 폐기를 재현하지 않는다.
  실제 라이브는 `L` 뿐이고 `P`/`X`/`R` 은 전부 반사실이다.
- **생존편향·`adj_factor` 계열 결함**(N-1 병합·감자 미조정, 정지 패딩)은 그대로 남아 있다.
  arm 비교엔 대칭이지만 **절대 수준을 인용하지 말 것.**
- **순열 p 는 시드 20개 = 순열 20회**라 최소 달성 가능 p 가 `1/21 ≈ 0.0476` 이다.
