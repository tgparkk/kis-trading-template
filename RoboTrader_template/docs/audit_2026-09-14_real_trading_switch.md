# 실매매 전환 사전 감사 — 고도화 3전략 (2026-09-14 · 읽기 전용 · rev.1)

> **성격** — 이 문서는 **조사 보고서**다. **코드 0줄 수정**, pytest 0회, git 편집 0건.
> 아래 「수정안」은 전부 **제안**이며 승인·실행이 아니다. **페이퍼 8전략 봇은 이 감사로 아무것도 바뀌지 않았다.**
>
> **방법** — 라이브 트리(`D:/GIT/kis-trading-template/RoboTrader_template`)를 **읽기 전용**으로 6축 병렬 감사(architect 6명)
> → **critic 적대 검증**(P1 24건 전수 반증 시도) → **관리자 원문 직접 확인**(아래 4건) → **DB SELECT**(kis_template).
> 운영 코드(`core/ bot/ framework/ api/ strategies/ config/ db/ utils/ main.py`)만 근거로 썼다.
> 연구 코드(`scripts/ multiverse/ backtest/ archive/ lib/ council/ books/`)는 근거에서 제외.
>
> **산출물 폴더** — `RoboTrader_template/scratchpad/real_trading_audit_20260914/`
> (`BRIEF.md` · `axis1_order_path.md` ~ `axis6_time_calendar.md` · `CRITIC_verify.md` · `DB_facts.md`)
>
> **축 산출물과 검수가 다르면 검수가 이긴다.** 이 문서는 검수(`CRITIC_verify.md`)를 척추로 삼는다.

### 이 문서가 «정정»하는 기존 인식 4건

| # | 기존 인식 | 정정 | 근거 |
|---|---|---|---|
| 1 | 「`instances/rs_leader/key.ini` 가 `enabled=true` 이므로 실전 텔레그램 경보는 간다」(축 6 백로그 표 6번) | ❌ **틀렸다.** `core/telegram_integration.py:56` 이 `Path("config/key.ini")` 를 **하드코딩**해 인스턴스 파일을 **읽지 않는다**. 루트는 `enabled=false` ⇒ **전 경보 무음** | 검수 §2-1 · 축 4-4 · 축 5-1 |
| 2 | 「추석 휴장 9/24~28 — 전환 창 5일」(MEMORY·계획서) | ❌ **틀렸다.** 휴장은 **9/24(목)~9/27(일)**. **9/28(월)은 정상 거래일**이다. `holiday_kis_cache.json`(synced 2026-09-14)에 `20260928` 없음(다음 항목이 `20261003`) + `holidays` 0.83 `KR(2026)` 도 9/28 은 휴일 아님. `utils/korean_holidays.py:72` 의 `"2026-09-28": "추석 대체공휴일"` 은 **오기재**(라이브러리 부재 시에만 발효). 설·추석 대체공휴일은 «일요일» 겹침만 대상인데 2026-09-26 은 토요일 | 축 6-3 · 검수 §2-5 · 관리자 확인 |
| 3 | 「`rebalancing_mode=true` 면 **분봉 전략** 시세가 None」(백로그 문구) | ⚠️ **표현 정정.** 활성 8전략에 **분봉 전략이 없다**(전부 `timeframe="daily"`). `daytrading_3methods_breakout` 도 이름과 달리 일봉이다(`strategies/daytrading_3methods_breakout/strategy.py:123,138,51`). 실제 영향은 「`get_cached_current_price()` 가 **영구 None**」이고, 그 결과 **손절·상한가 가드·EOD 매도가가 전부 API 단건 조회에 의존**한다 | 축 6-8·6 항목5 · 검수 §2-4 |
| 4 | 「수수료·세금 산식이 **두 벌**」 | ⚠️ **정정: 산식은 한 벌이다.** `core/orders/order_monitor.py:411-414` · `core/orders/order_timeout.py:229-232` · `db/repositories/trading.py:164-167` 세 곳이 **같은 상수·같은 식**. 갈라지는 것은 **리포트 도구**(`tools/daily_trading_summary.py` 가 gross)와 **체결 방식**(페이퍼 즉시 100% vs 실전 지정가/시장가) | 축 2-9 · 검수 §2-2 |

### 관리자가 원문을 직접 확인한 것 (에이전트 인용의 2차 검증)

- `api/kis_market_api.py:957-959` 의 `total_value` **덮어쓰기** · `bot/initializer.py:730` 의 `min(cap, total_balance)` — 원문 확인.
- `bot/candidate_loader.py:103` 단일전략 모드 owner = `self._bot.strategy.name`(**클래스명** `BookPullbackMa20Strategy` 등)
  vs `core/trading_context.py:285-297` `_strategy_key`(**폴더키**) — 원문 확인. `main.py:465-469` 라운드로빈 키도 폴더키.
- `api/kis_auth.py:326` `_CB_BYPASS_TR_IDS = {"TTTC0013U", "TTTC8036R"}` — 원문 확인(매수·매도 TR 둘 다 밖).
- 추석 휴장일 판정(위 정정 2) — `holiday_kis_cache.json` + `holidays` 0.83 양쪽 확인.

---

## 0. 한 줄 결론

> **판정: 현 코드로는 실매매 전환 불가.**
> 실탄을 넣어도 **첫날 매수가 0건**일 가능성이 높고(P1-2), 2일차부터는 **예수금이 자본에서 통째로 사라지며**(P1-3),
> 그 사이 어떤 사고가 나도 **경보가 아무데도 안 간다**(P1-1).
> **코드 6곳 8줄 + 설정 5건**을 먼저 넣으면 P1 10건 중 6건이 닫히고, **소액 실탄 전환이 가능해진다**(나머지 4건은 소액 상한 + 매일 계좌-DB 수동 대사로 노출을 억제).
> 그 8줄은 **전부 「실전/인스턴스 모드에서만」 분기**라 **페이퍼 8전략 동작은 물리적으로 0 변경**이다.

---

## 1. 쉽게 읽는 요약 — 예시로

페이퍼(모의 장부)에서는 X 였는데, 실전(실계좌)에서는 Y 가 된다. 아래 6개가 그 전부다.

**① 「첫날 후보 20개를 올려놓고, 하나도 못 산다」 — 이름표가 안 맞아서**
페이퍼는 전략이 8개라 「여러 전략 경로」를 탄다. 거기서는 후보에 **폴더 이름표**(`book_pullback_ma20`)를 붙인다.
실전은 전략이 1개라 **다른 경로**로 빠지는데, 그 경로만 **클래스 이름표**(`BookPullbackMa20Strategy`)를 붙인다(`bot/candidate_loader.py:103`).
그런데 전략이 후보를 꺼내 쓸 때는 **폴더 이름표**로 찾는다(`core/trading_context.py:285-297`). 두 이름이 다르니 **하나도 안 걸린다**.
로그에는 `후보 종목 N/M개 등록 완료` 가 정상으로 찍히고, 그 뒤로 매수 신호가 **0줄**. 에러도 경고도 없다.
→ 「실전 켰는데 조용하네, 오늘은 신호가 없었나 보다」로 읽힌다. **가장 위험한 실패 방식이다.**

**② 「1천만 넣고 첫날 주식 400만 어치 샀다. 둘째날 봇을 켜면 봇은 통장에 400만원만 있다고 믿는다」**
봇은 기동할 때 「총자금 = min(내가 정한 상한, 계좌 총평가)」로 잡는다(`bot/initializer.py:730`).
그런데 그 「계좌 총평가」를 만드는 함수가 **예수금을 포함한 값을 계산해 놓고, 마지막에 「주식 평가액 합계」로 덮어쓴다**(`api/kis_market_api.py:957-959`).
⇒ 현금 600만 + 주식 400만인 계좌인데 봇은 **총자금 400만**으로 시작한다. 이어 복원이 「이미 산 주식 원가 430만」을 빼면 **가용자금이 음수 → 0 으로 clamp**(`bot/state_restorer.py:241-247`).
그날 **신규 매수 0건**. 로그엔 `가용자금 음수 보정` **WARNING 한 줄**뿐이다.
🔑 **첫날(보유 0종목)에는 이 결함이 안 보인다** — 보유가 없으면 덮어쓰기 전에 return 하기 때문이다(`:904-906`).
**「소액 1일 리허설 성공」이 이 결함을 통과시킨다.**

**③ 「손절 주문이 30초 API 장애에 걸리면, 그 종목은 30분간 못 판다 — 그리고 로그에 아무 흔적이 없다」**
API 서킷브레이커가 열리면 **매도 주문 TR(`TTTC0011U`)이 차단**된다. 통과되는 건 「주문 취소」 TR 둘뿐이다(`api/kis_auth.py:326`).
매도가 몇 번 실패하면 그 종목에 **30분 자체 봉쇄**가 걸리고(`core/trading/position_monitor.py:23-24`), 그동안 봇이 남기는 유일한 흔적은 **`debug` 로그**(`:421`)다. 기본 로그 레벨이 INFO 라 **파일에도 콘솔에도 안 남는다**.
게다가 전환 후보 3전략은 전부 **swing** 이라 「장 끝나면 EOD 가 다 팔아준다」는 백스톱이 **없다**(`bot/liquidation_handler.py:267-270`).
⇒ 손절이 막힌 채 **오버나이트**로 넘어간다.

**④ 「기동 중단 경보가, 인스턴스 설정이 아니라 페이퍼 설정을 읽어서 아무데도 안 간다」**
운영자가 `instances/<id>/key.ini` 에 텔레그램을 `enabled=true` 로 켜 놨다(**지금 실제로 그렇게 돼 있다**).
그런데 텔레그램 코드는 그 파일을 안 읽는다 — `Path("config/key.ini")` 를 **하드코딩**해서 **페이퍼 봇 설정**(`enabled=false`)을 읽는다(`core/telegram_integration.py:56`, `api/kis_auth.py:600`).
더 나쁜 건, 꺼져 있어도 `initialize()` 가 **True 를 반환**한다(`:88-90`). 「켰다」는 오신뢰가 **이미 파일로 성립해 있다**.
⇒ 실전 기동 중단(`LiveStartupAbort`)도, API 장애도, 주문 타임아웃 CRITICAL 도 **전부 무음**.

**⑤ 「재기동 한 번 하면, 7거래일 지난 포지션은 전략 손절 8% 대신 5%/5% 로 강제 청산된다」**
실전 원장 표(`real_trading_records`)에는 **익절/손절 컬럼이 아예 없다**(`db/repositories/trading.py:480-481` 주석이 자인).
복원할 때 그 값을 못 읽으니 **항상 기본값**(익절 15% / 손절 10%)이 들어가고(`bot/state_restorer.py:848-859`),
「기본값 그대로이고 7거래일 넘었으면 조여라」는 안전장치가 **반드시 발화**해 **익절 5% / 손절 5%** 로 바뀐다(`:405-418`, 상수는 `config/constants.py:187-189`).
⇒ `book_pullback_ma20`(손절 8% / 익절 10% / 최대보유 50거래일) · `minervini_volume_dryup`(손절 8% / 최대보유 20거래일)의
**손익비 8:10 이 5:5 로 바뀐다.** 장중 패치·크래시 복구 재기동 한 번이면 그날 모든 포지션이 그렇게 된다.
🔑 페이퍼 원장은 그 컬럼이 있어서 **865행 전부 채워져 있다**(NULL 0건) — **이 분기가 페이퍼에서 발화한 적이 단 한 번도 없다.**

**⑥ 「앱키를 메모해 둔 파일 하나가 git 에 그대로 올라간다」**
`RoboTrader_template/.gitignore` 에는 `instances` 문자열이 **0건**이다. 보호는 **바깥 repo** `D:/GIT/kis-trading-template/.gitignore:45-48` 의
`instances/*/key.ini` · `instances/*/trading_config.json` **두 글롭뿐**.
⇒ `key_backup.ini` · `keys.txt` · `notes.md` 는 **추적 대상**이고, `RoboTrader_template` 을 단독 repo 로 떼면 **`key.ini` 자체가 추적**된다.
한 번 커밋되면 SHA 는 되돌릴 수 없다. **실계좌 탈취 경로다.**

---

## 2. P1 결함 10건 — 상세

> 형식: **제목** · 위치(파일:줄 + 인용) · 페이퍼에서 안 보인 이유 · 실매매에서 일어나는 일 · 검수 판정 · 재현 방법(**실행 안 함**) · 수정안(**제안만**) · 출처.
> 재조정 표기: 검수가 등급을 내린 건은 `~~P1~~ → P2` 로 흔적을 남긴다(이 절에는 **재조정 후에도 P1 인 10건만** 있다).

---

### P1-1. 텔레그램이 루트 `config/key.ini` 를 읽어, 인스턴스의 `enabled=true` 가 무효가 된다 — 전 경보 무음 + 「켰다」는 오신뢰

**위치** — `core/telegram_integration.py:47-56`

```python
    def _load_telegram_config(self) -> Dict[str, Any]:
        """key.ini 파일에서 텔레그램 설정 로드"""
        ...
            config_file = Path("config/key.ini")      # ← 하드코딩. _CONFIG_DIR 무시
```

같은 하드코딩 2번째 — `api/kis_auth.py:600`(`_send_failure_telegram`).
대조군: `config/settings.py:59-65` 는 `_CONFIG_DIR = resolve_config_dir(os.environ)` → `CONFIG_FILE = _CONFIG_DIR / "key.ini"`.
인스턴스 모드면 `instances/<id>/key.ini` 다. **텔레그램만 이 규칙 밖이다.**
실측(값 미출력): `config/key.ini:11` `enabled=false` / `instances/rs_leader/key.ini:11` `enabled=true`.
그리고 `_is_config_valid()`(`:79-83`)가 False 여도 `initialize()`(`:88-90`)는 **`is_enabled=False` 인 채 True 를 반환**한다.

**페이퍼에서 안 보인 이유** — 페이퍼 봇은 `KIS_INSTANCE_DIR` 미설정이라 `_CONFIG_DIR == config/` 다.
**경로 버그가 페이퍼에서는 «우연히» 정답을 낸다.** 두 경로가 갈라지는 것은 인스턴스 모드뿐이다.

**실매매에서 일어나는 일** — 운영자가 `instances/<id>/key.ini` 에 토큰·chat_id 를 넣고 `enabled=true` 로 켠다(현재 실제 상태).
봇은 그것을 **읽지 않고** 루트의 `false` 를 읽어 `텔레그램 설정 로드: enabled=False`(`:70`) 한 줄만 남긴다. 이후 전부 무음:
`LiveStartupAbort`(`main.py:709`) · API 장애(TIMEOUT/CONNECTION/SSL, `api/kis_auth.py:519,531,537,549`) ·
주문 타임아웃 CRITICAL(`core/orders/order_timeout.py:79,144,275,302`) · 계좌-DB 대사 불일치(`bot/state_restorer.py:1405`) · EOD 청산 3회 실패(`bot/liquidation_handler.py:544`).
반대로 루트를 `true` 로 켜면 **페이퍼 봇과 실전 인스턴스가 같은 chat_id 로 섞여** 오고, 발신 메시지 어디에도 `INSTANCE_ID` 가 없다.

**검수 판정** — **CONFIRMED. 전 축 통틀어 1순위.** 축 6 이 「실전은 닫힘」이라 쓴 것은 **REFUTED**(파일만 읽고 코드를 안 읽었다).
검수는 이 모순을 「가장 위험한 종류」로 분류했다 — 「경보는 켜져 있다」는 오신뢰가 **다른 축의 완화책 전제로 쓰이고 있었기 때문**이다.

**재현 방법(실행 안 함)** — `grep -rn 'Path("config/key.ini")' core/ api/` → 2건. `config/settings.py:59-65` 와 대조.

**수정안(제안)** — 두 자리를 `from config.settings import CONFIG_FILE` 참조로 교체(**2줄**). 추가(선택): 발신 메시지 머리에 `INSTANCE_ID` 접두.

**출처** — 축 4 발견 4 · 축 5 발견 1 (검수 병합 **M1**).

---

### P1-2. 단일전략 모드 후보 owner 가 «클래스명» 이라, 전략이 후보를 0건으로 본다 → **첫날 매수 0건**

**위치** — `bot/candidate_loader.py:71`, `:103`, `:110`, `:116`

```python
 71  if len(self._bot.strategies) > 1:
 72      await self._load_candidates_multi_strategy(max_candidates)   # ← 페이퍼(8전략)는 여기
 73      return
...
103  strategy_name = self._bot.strategy.name if self._bot.strategy else "unknown"   # ← 클래스명
110  ... owner_strategy=strategy_name ...
116  ts.strategy_name = strategy_name
```

소비자 — `strategies/base.py:612` `for stock in ctx.get_selected_stocks():` → `core/trading_context.py:285-297`

```python
target = owner if owner is not None else getattr(self, "_strategy_key", None)   # ← 폴더키
...
    if so == target or not so:
```

`_strategy_key` 가 폴더키인 근거: `main.py:466-470` `list(self.strategies.keys())` → `:484 ctx_for_strategy(name)` → `core/trading_context.py:68`.
`.name` 이 클래스명인 근거: `strategies/config.py:442-453` `load_strategies` 는 `enabled`·`max_capital_pct`·`regime_index`·`regime_gate` 만 주입하고 **`instance.name` 을 덮어쓰지 않는다**. 각 전략이 `name` 을 재선언한다(`strategies/book_pullback_ma20/strategy.py:48` `"BookPullbackMa20Strategy"` · `strategies/rs_leader/strategy.py:24` `"RSLeaderStrategy"`).
⇒ `"BookPullbackMa20Strategy" == "book_pullback_ma20"` 은 거짓이고, `not so` 공용 폴백도 `so` 가 비어 있지 않아 안 걸린다.

**페이퍼에서 안 보인 이유** — 페이퍼는 8전략이라 **항상 `:71` 다중 분기**를 탄다. 거기서는 `owner_strategy=strategy_name`(= **폴더키**, `:205`)로 등록한다. **이 줄(`:103`)에 도달한 적이 없다.**

**실매매에서 일어나는 일** — 실전 인스턴스가 09:00 에 후보를 정상 등록하고 `후보 종목 N/M개 등록 완료` 를 로그에 남긴 뒤,
**on_tick 이 매번 빈 리스트를 돌아 하루 종일 매수 시그널 0건.** 에러도 경고도 없다.
단일전략 경로에는 다중 경로의 안전장치 두 개도 없다 — `[E6] 전 전략 후보 0건` ERROR 경보(`:157-161`)와 폴백 풀에 전략 base_filter 재적용(`:177-190`).
⇒ **「실전 전환 검증 성공」이라는 거짓 확신**이 남는다. 최악은 손실이 아니라 **검증했다는 착각**이다.

**검수 판정** — **CONFIRMED · 최우선 2순위.** 축 6 은 자기 등급을 「강한 추정」으로 달았는데 검수는 **과소평가**로 본다:
레포가 **스스로 문서화한 확정 사실**이기 때문이다.
- `bot/system_monitor.py:124-148` 독스트링 — 「클래스명(`strategy.name`)으로 등록하면 어느 전략에게도 안 보이는 **유령 슬롯**이 된다(`65bf870` 유형의 매칭 0)」. **같은 버그를 다른 등록 지점에서는 이미 고쳤다**(`_resolve_strategy_key`).
- `bot/state_restorer.py:802-809` 독스트링 — 「`bot/candidate_loader.py:100` 은 **단일전략 모드**에서 `strategy.name`(클래스명)으로, `:186` 은 **다중전략 모드**에서 폴더키로 등록한다」.

**재현 방법(실행 안 함)** — 라이브 트리 **밖 사본**에서 `KIS_INSTANCE_DIR=instances/<id>` 로 후보 로드까지만 드라이런해 `ctx.get_selected_stocks()` 길이를 찍는다.
또는 실전 기동 후 로그에서 `후보 종목 .*등록 완료` 다음에 `매수 시그널` 이 **0줄**인지 확인.

**수정안(제안)** — `bot/candidate_loader.py:103` 을 `next(iter(self._bot.strategies.keys()), "unknown")`(폴더키)로 교체(**1줄**).
> **대안**(더 안전하나 회귀면적 큼): `:71` 을 `>= 1` 로 바꿔 1전략도 다중 경로를 태운다. `[E6]` 경보·base_filter·폴더키 owner 를 한꺼번에 얻고 페이퍼 동작도 불변이다.
> **단 실전 후보 소스가 「거래량 순위」에서 「스크리너 스냅샷」으로 바뀌므로 동작 변경 = 사장님 결재 대상.** 최소 집합에는 1줄만 넣고 대안은 별도 사전등록으로 분리할 것을 권한다.

**출처** — 축 6 발견 5 (검수 §1 6-5).

---

### P1-3. `total_balance` 가 「주식 평가금액 합계」다 — `real_total_funds_cap` 이 무의미해지고 예수금이 자본에서 사라진다

**위치** — `api/kis_market_api.py:892-906` 와 `:953-959`

```python
 892  base_info = {
 894      'total_value': account_summary.get('tot_evlu_amt', 0),
 896      'available_amount': account_summary.get('prvs_rcdl_excc_amt', 0),
 900      'deposit_total': account_summary.get('dnca_tot_amt', 0),
 904  if balance_data.empty:
 906      return base_info                 # ← 보유 0종목일 때만 tot_evlu_amt 가 살아남는다
 953          total_value += eval_amt      # 보유종목 evlu_amt 누적
 957  base_info.update({
 959      'total_value': total_value,      # 🔴 tot_evlu_amt 를 덮어쓴다 = 주식평가액만
```

→ `framework/broker.py:281` `'total_balance': balance_info.get('total_value', 0)`
→ `bot/initializer.py:721-731` `total_eval = balance_info['total_balance']` → `total_funds = min(cap, total_eval)`.

**페이퍼에서 안 보인 이유** — 가상 경로는 `bot/initializer.py:686-697` 의 `is_virtual_mode` 가지로 빠져 `VirtualTradingManager.get_virtual_balance()` 를 쓴다. **`total_balance` 를 한 번도 읽지 않는다.**
계약 테스트 `tests/test_live_p0_fund_init.py` 는 mock 값이라 이 결함을 **못 잡는다**(「맨 Mock 은 hasattr 이 항상 True」 계열).

**실매매에서 일어나는 일**
- **첫날(보유 0종목)**: `balance_data.empty` → `tot_evlu_amt` 가 그대로 나가 **정상 동작한다.** ⇒ **1일 소액 리허설로는 드러나지 않는다.**
- **2일차 이후**: cap 10,000,000 · 실계좌 = 현금 6,000,000 + 주식평가 4,000,000(원가 4,300,000)
  → `total_funds = min(10M, 4,000,000) = 4,000,000`
  → 복원이 `available -= 4,300,000`(`bot/state_restorer.py:238`) → **음수 → 0 clamp**(`:247`) → 그날 **신규 매수 0건**.
  로그는 `가용자금 음수 보정` **WARNING 한 줄**. 텔레그램은 안 간다(P1-1).
- 상승장이면 반대로 종목당 9% 의 **기준이 주식평가액을 따라 매일 흔들린다**.

**검수 판정** — **CONFIRMED**(덮어쓰기 사슬 3줄 전부 원문 확인). 단 **두 가지 정밀화**:
1. 축 2 가 코드블록에 붙인 `# 총평가금액(예수금+주식)` 주석은 **파일에 없다**(894행에 인라인 주석 없음). `tot_evlu_amt` 의 의미는 여전히 **TR 문서 기준 추정**이다(§8 미확정 질문).
2. 「2일차 매수 0」은 **장 시작 시점에만 참**이다. 매도가 나면 `release_investment` 가 매수원가를 되돌려 그만큼 재매수된다(`core/fund_manager.py:432-462`).
   ⇒ 정확한 증상은 **「예수금이 자본에서 통째로 사라져 `real_total_funds_cap` 이 사실상 무의미해지고, 봇이 이미 물린 금액만 재활용한다」**. 그래도 **P1**.

**재현 방법(실행 안 함)** — ① `rg -n "total_value" api/kis_market_api.py` 로 894/953/959 세 줄 대조
② 실기동 로그 `자금 관리자 초기화 완료(실전): min(상한 …, 총평가 …)` 의 「총평가」를 HTS 총평가금액과 비교
③ `tests/healthcheck/run_healthcheck.py:158` 이 같은 함수를 부르므로 계좌 연결 후 그 출력으로도 확인 가능.

**수정안(제안)** — `:957-959` update 에서 `'total_value'` 키를 빼고 **`'stock_eval_value'` 를 새로 실어** `tot_evlu_amt` 를 보존(**2줄**).
broker 계약 키 `total_balance` 의 의미를 D1 정의(`docs/superpowers/specs/2026-08-14-live-p0-blockers-design.md:154`)와 함께 문서로 못박을 것.

**출처** — 축 2 발견 1 (검수 §1 2-1).

---

### P1-4. 실전 tp/sl 이 영속되지 않는다 → 재기동 시 15%/10%, 7거래일 뒤 **5%/5%** 강제

**위치** — `db/repositories/trading.py:491-504`(실전 열린포지션 SELECT)

```sql
SELECT b.id, b.stock_code, b.stock_name,
       b.quantity - COALESCE(SUM(s.quantity), 0) AS quantity,
       b.price as buy_price, b.timestamp as buy_time,
       b.strategy, b.reason as buy_reason
```

→ `target_profit_rate`/`stop_loss_rate` **없음**. `:480-481` 주석이 「`real_trading_records` 는 두 컬럼이 없다」고 **자인**한다.
→ `bot/state_restorer.py:848-859` — `row.get(...)` = None → `DEFAULT_TARGET_PROFIT_RATE`(0.15) / `DEFAULT_STOP_LOSS_RATE`(0.10).
→ `bot/state_restorer.py:405-418`

```python
if days_held >= STALE_DEFAULT_APPLY_DAYS:            # 7 거래일
    if target_profit_rate == DEFAULT_TARGET_PROFIT_RATE and stop_loss_rate == DEFAULT_STOP_LOSS_RATE:
        target_profit_rate = STALE_DEFAULT_TARGET_PROFIT   # 0.05
        stop_loss_rate = STALE_DEFAULT_STOP_LOSS           # 0.05
```

상수 실측(`config/constants.py`): `:125` 0.15 · `:126` 0.10 · `:187` 7 · `:188` 0.05 · `:189` 0.05 · `:186` 30.
실전 경로가 이 함수를 탄다: `_apply_stale_position_check` 호출자 = `bot/state_restorer.py:708`(페이퍼) · **`:1263`(실전)**.

**상류 결함(같은 결함의 반대편)** — 종료 시 tp/sl flush 는 실전에서 **항상 no-op** 이다.
`bot/initializer.py:813-820` 이 `_real_buy_record_id` 를 읽는데 **그 필드에 대입하는 코드가 0건**이다
(검색: `grep -rn "_real_buy_record_id" --include=*.py .`, tests 제외 → 히트 1건 = 그 읽기 한 줄).
실전 매수는 `core/orders/order_db_handler.py:161-164` 가 `ts.set_virtual_buy_info(...)` 로 **`_virtual_buy_record_id`** 에 쓴다. 이름을 맞춰도 **대상 표에 컬럼이 없어** `UPDATE ... SET target_profit_rate=...` 는 UndefinedColumn 이 난다(지금은 도달하지 않아 조용하다).

**페이퍼에서 안 보인 이유** — 페이퍼 원장에는 두 컬럼이 **실재**하고 `save_virtual_buy`(`db/repositories/trading.py:272`)가 항상 채운다.
**DB 실측**: `virtual_trading_records` `action='BUY'` **총 865행 / tp NULL 0 / sl NULL 0 / (0.15, 0.10) 정확히 일치 0행**.
⇒ 이 stale 분기는 **페이퍼에서 구조적으로 단 한 번도 발화할 수 없다. 실전에서는 항상 발화한다.**

**실매매에서 일어나는 일** — `book_pullback_ma20`(손절 8% / 익절 10% / max_hold 50거래일, `strategies/book_pullback_ma20/strategy.py:76-86`)와
`minervini_volume_dryup`(손절 8% / max_hold 20거래일, `strategies/minervini_volume_dryup/strategy.py:97-105`)은 **설계상 7거래일을 훌쩍 넘겨 보유**한다.
재기동이 한 번이라도 있으면 그 다음 tick 부터 **프레임워크 백스톱**(`core/trading/position_monitor.py:314-334`)이 **+5% 익절 / −5% 손절**로 포지션을 대신 청산한다.
전략의 MA20 트레일링·max_hold 는 그 전에 잘려 **영영 발동하지 않는다**(손익비 8:10 → 5:5).
트레일링 최고가·`trailing_stop_activated` 도 DB 에 안 남는다. **경고 로그조차 없다**(`buy_record_id is None` → 조용히 스킵).
🟢 단, **전략 고유 청산은 정상**이다 — 3전략 모두 `positions[code] = {quantity, entry_price, entry_time}` 만 쓰고 그 shape 은 복원이 채운다(축 3 「재기동 후 3전략 청산 룰 동작 판정」). 깨지는 것은 **프레임워크 백스톱 쪽**이다.

**검수 판정** — **CONFIRMED. 가장 정확한 P1**(인용 5곳·상수 6개 전부 원문 확인).

**재현 방법(실행 안 함)** — `\d real_trading_records` 로 두 컬럼 부재 확인 + 위 페이퍼 SQL 재실행 + `bot/state_restorer.py:405-418` 코드 읽기.

**수정안(제안)** — 셋 중 택일(**결정 필요 — §7 C3 계열**):
① `real_trading_records`(+인스턴스 사본)에 `target_profit_rate`/`stop_loss_rate`/`highest_price_since_buy` 컬럼 추가 + `save_real_buy` 기록 + SELECT 확장(**마이그레이션 동반**)
② 임시책: stale 분기를 「DB 가 실제로 NULL 이었을 때만」으로 좁히는 플래그(`tp_from_db`)(**약 1줄 + 전달 경로**) — ⚠️ **의도된 안전장치를 끄는 것**이라 결재 필요
③ 실전 복원 시 owner 전략의 `_stop_loss_pct`/`_take_profit_pct` 를 폴백으로 사용
④ 최소 조치: 실전에서 flush 대상이 0건이면 **WARNING**(지금은 고장과 침묵이 구분되지 않는다).

**출처** — 축 3 발견 1 + 축 1 발견 7 (검수 병합 **M2**).

---

### P1-5. 체결 «오탐 복구» 가 장부 부작용을 역산하지 않는다 → 이중 기록

**위치** — `core/orders/order_monitor.py:183-223` (`_restore_false_positive_order`)

```python
order.status = OrderStatus.PENDING
self.pending_orders[order.order_id] = order
...
if order.order_type == OrderType.BUY and ... self.fund_manager:        # :207
    buy_amount = order.get_filled_price() * order.quantity
    self.fund_manager.reverse_confirm(order.order_id, buy_amount)      # :211
```

되돌리는 것은 **`reverse_confirm` 하나뿐**이고, 그나마 **`BUY` 분기 안**에 있다. `_handle_full_fill`(`:293-441`)이 이미 해 둔 나머지는 전부 남는다:
- `fund_manager.add_position(code, owner)`(`:380`) — 보유 레지스트리 잔류 → 슬롯 영구 점유
- `_save_real_trade_to_db`(`:424`) — **`real_trading_<id>` 매수행이 이미 들어갔다**(`core/orders/order_db_handler.py:147`)
- `trading_manager.on_order_filled`(`:429`) → `core/trading/order_completion_handler.py:420-450` 이 `set_position` + POSITIONED 전이 + 전략 콜백까지 끝냈다
- **매도 오탐은 아무것도 안 되돌린다** — `release_investment` + `adjust_pnl` 이 그대로 남는다

**페이퍼에서 안 보인 이유** — 페이퍼 주문 ID 는 `VT-BUY-...`(`core/orders/order_executor.py:173`)라 KIS 에 없고, 페이퍼는 broker 로 주문을 낸 적이 없어 이 루프가 실효적으로 돌지 않는다.

**실매매에서 일어나는 일** — 조회가 한 번 흔들려 「체결 → 미체결」 오탐이 뜨면, 복구된 주문이 나중에 진짜 체결될 때 `_handle_full_fill` 이 **처음부터 다시** 돈다
⇒ `real_trading_<id>` BUY 행 **2개** · `add_position` **2회** · 전략 콜백 2회 · `confirm_order` 2회.
중복 콜백 가드는 슬롯 단위 `order_processed` 플래그뿐이라(`order_completion_handler.py:400-404`) **DB INSERT 와 `add_position` 은 막지 못한다.**
손익 리포트 이중 계상 → 다음 기동 대사에서 DB 수량이 계좌의 2배 → **`LiveStartupAbort`**.

**검수 판정** — **CONFIRMED. 축이 오히려 «과소평가» 했다.**
축은 「오탐 발생 빈도는 추정」이라 썼는데, 검수가 도달성을 **크게 올렸다**:
`_check_false_positive_filled_orders`(`:161-176`)는 `status_data` 에서 `tot_ccld_qty`(없으면 0) · `cncl_yn`(없으면 'N')를 읽고 `filled_qty == 0 ... and cancelled != 'Y'` 면 오탐으로 본다.
그런데 `framework/broker.py:793` 의 `status_unknown` 행은 **`odno`·`_status`·`status_unknown`·`cncl_yn` 4키뿐**이라 `tot_ccld_qty` 가 **아예 없다** → `filled_qty = 0` → 조건 **항상 참**.
⇒ 체결 후 30분(매수)/10분(매도) 안에 **두 조회(TTTC8036R·TTTC0081R)가 한 번만 같이 흔들리면** 방금 체결된 주문이 오탐으로 복구된다.
레이트리밋·토큰 재발급 구간에서 **흔한 조건**이다. 검수는 **「P1-6(status_unknown) 보다 도달성이 높다」**고 판정했다.

**재현 방법(실행 안 함)** — `grep -n "체결 오탐지 감지\|오탐지 주문 복구" logs/<id>/*`
+ `select stock_code, timestamp, quantity from real_trading_<id> where action='BUY' order by 1,2;` 에서 **초 단위 근접 중복행** 확인.

**수정안(제안)** — 「되돌리기」를 한 묶음으로 정의(`add_position` 해제 + DB 행 void + 전략 콜백 역통보 + 슬롯 원복)하거나,
불가능하면 **복구를 폐지하고 CRITICAL + 수동 개입**으로 정책 전환. 매도 오탐은 `release_investment`/`adjust_pnl` 역산 없이는 복구 금지.
**1줄로 안 닫힌다 — 장부 정합 로직 변경**(§6 D 참조).

**출처** — 축 1 발견 4 (검수 §1 1-4).

---

### P1-6. `status_unknown` 5분이면 «브로커 취소 없이» 장부만 닫는다 → 이중 포지션

**위치** — `core/orders/order_monitor.py:270-276`

```python
elif is_status_unknown:
    elapsed_time = (now_kst() - order.timestamp).total_seconds()
    if elapsed_time > 300:  # 5분 = 300초
        self.logger.warning(f"주문 상태 불명 5분 초과로 타임아웃 처리: {order_id} ...")
        order.status = OrderStatus.TIMEOUT
        self._move_to_completed(order_id)
```

`_move_to_completed`(`core/orders/order_base.py:142-179`)가 하는 일은 ①`pending_orders.pop` ②`completed_orders.append` ③`order_timeouts` 삭제 ④`_unregister_active_order` ⑤CANCELLED/TIMEOUT/FAILED 면 `fund_manager.cancel_order`.
**`broker.cancel_order` 호출이 없다 — 원문 확인.**
`status_unknown` 의 출처는 `framework/broker.py:793` — 정정취소가능목록·당일체결목록 **어디에도 안 보이면** 붙는다.
그런데 `get_inquire_psbl_rvsecncl_lst()` 는 **API 실패 시에도 `None`(기본 인자값)을 돌려주고**(`api/kis_order_api.py:190-192`),
`framework/broker.py:775` 는 `if pending is not None and not pending.empty` 로 **None 과 빈 DF 를 같이 흘려보낸다** ⇒ 「조회 실패」와 「주문 없음」이 같은 값이 된다.

**페이퍼에서 안 보인 이유** — 페이퍼 매수는 `_execute_paper_buy_order`(`order_executor.py:168-196`)에서 `status=FILLED, remaining_quantity=0` 로 끝나 **`pending_orders` 에 들어가지도 않는다**. 이 분기가 실행된 적이 없다.

**실매매에서 일어나는 일**
1. KIS 조회가 5분 연속 흔들리면(rate limit EGW00201·토큰 재발급) 봇이 주문을 TIMEOUT 으로 닫고 예약자금을 환불 → 가용자금 증가.
2. `_active_buy_stocks[code]` 소멸 → `has_active_buy_order` False.
3. 다음 틱에 같은 종목 **재매수**. 원주문은 KIS 에 살아 있어 **둘 다 체결 시 의도 수량 2배 + 예산 초과**.
4. 원주문이 나중에 체결되면 `pending_orders` 에 없어 `_handle_full_fill` 이 안 돈다 → DB 매수행 없음 / `add_position` 없음 / 전략 콜백 없음 → 다음 기동 대사에서 **`LiveStartupAbort`**.
5. TradingStockManager 에 알림도 없어(`handle_order_timeout` 미호출) 슬롯이 `BUY_PENDING` 고착.

**검수 판정** — **CONFIRMED**(인용·`_move_to_completed` 전문·None/빈DF 합류 전부 원문 확인).
검수 추가 관측: 「다음 틱에 같은 종목 재매수」에는 전략 신호 재생성이 필요한데, **P2-19(일봉 신호는 하루 종일 동일)가 그 조건을 충족시킨다 — 두 발견이 서로를 강화한다.**

**재현 방법(실행 안 함)** — ①`grep -n "주문 상태 불명 5분 초과로 타임아웃 처리" logs/<id>/*` ②같은 order_id 뒤 `"FundManager 예약 해제"` ③직후 같은 종목 「매수 주문 성공」
④`select stock_code, count(*) from real_trading_<id> where action='BUY' and timestamp::date=current_date group by 1 having count(*)>1;`

**수정안(제안)** — `_move_to_completed` **전에** `_cancel_with_retry(order_id)` 를 돌리고, 취소가 「취소가능목록에 없음」으로 실패하면 TIMEOUT 이 아니라 **재확인 + CRITICAL + pending 유지**.
겸해서 `framework/broker.py:774` 가 조회 실패(`None`)와 빈 목록을 갈라, 실패면 `status_unknown` 대신 `None` 을 돌려 **판정을 유보**하게 한다.
**1줄로 안 닫힌다 — 장부 정합 로직 변경**(§6 D).

**출처** — 축 1 발견 1 (검수 §1 1-1).

---

### P1-7. 매도 부분체결 타임아웃이 `cancel_success` 를 검사하지 않는다 (매수는 검사한다)

**위치** — `core/orders/order_timeout.py:205` vs `:210-258` vs `:264`

```python
205  cancel_success = await self._cancel_remaining_only(order_id)
210  if order.order_type == OrderType.SELL:
226      self.fund_manager.release_investment(buy_cost, stock_code=order.stock_code)
234      self.fund_manager.adjust_pnl(pnl)
249      order.status = OrderStatus.FILLED
250      self._move_to_completed(order_id)
251      await self._save_real_trade_to_db(order, filled_price)
258      return                                    # ← cancel_success 를 한 번도 읽지 않는다
264  if not cancel_success:                        # ← 매수 분기: CRITICAL + 텔레그램 + 「예약자금 유지」
```

`_cancel_remaining_only`(`:166-197`)는 3회 실패 후 `False` 만 돌려준다. **비대칭 확인.**

**페이퍼에서 안 보인 이유** — 페이퍼엔 **부분체결이 존재하지 않는다**(`_execute_paper_sell_order` 는 `remaining_quantity=0` FILLED 고정, `order_executor.py:366`). `_handle_partial_fill_timeout` 은 **실전 전용 함수**다.
보조: `_handle_partial_fill`(`order_monitor.py:443-469`)은 **로그만** 찍고 끝이라(자금·포지션·DB 부작용 0) 부분체결은 **타임아웃이 올 때까지 아무 일도 안 일어난다**.

**실매매에서 일어나는 일** — 100주 시장가 매도 중 40주 체결 → 3분 타임아웃 → 잔여 60주 취소가 3회 실패(장 마감 근처·VI·API 흔들림) →
1. 봇은 40주 기준으로 회수·손익 반영하고 **40주 SELL 행**을 쓴 뒤 주문을 닫는다.
2. 잔여 60주가 그 뒤 체결된다 — `pending_orders` 에 없으니 **두 번째 SELL 행도, 두 번째 회수도 없다.**
3. 장부: 보유 60주(실제 0주) + invested 60주분 잠김 → 다음 기동 대사 → **`LiveStartupAbort`**.

**검수 판정** — **CONFIRMED (정확).** 순수 코드 분기 비대칭이라 반증 여지 없음.

**재현 방법(실행 안 함)** — `grep "매도 부분 체결 타임아웃"` 주변에 `grep "잔여 주문 취소 API 실패"` 가 3회 찍혔는지 대조.
SQL: `select stock_code, sum(case when action='BUY' then quantity else -quantity end) from real_trading_<id> group by 1 having sum(...) <> 0;` 을 계좌 잔고와 대조.

**수정안(제안)** — 매도 분기도 매수와 같은 모양으로 `if not cancel_success:` 를 **먼저** 두고, 잔여가 살아있을 수 있으므로
**`release_investment`/`adjust_pnl`/DB INSERT 를 보류** + CRITICAL + 텔레그램 + `pending_orders` 유지(또는 잔여수량만 남긴 Order 로 계속 추적).
**1줄로 안 닫힌다 — 장부 정합 로직 변경**(§6 D).

**출처** — 축 1 발견 3 (검수 §1 1-3).

---

### P1-8. 매도 TR 이 API 서킷브레이커 bypass 밖 + 종목 CB 30분 봉쇄 + swing 이라 EOD 백스톱 없음 (**한 사슬**)

**위치 ①** — `api/kis_auth.py:325-332`

```python
    # H8 fix: 주문 취소/정정취소 관련 TR은 CB 상태와 무관하게 허용
    _CB_BYPASS_TR_IDS = {"TTTC0013U", "TTTC8036R"}     # 정정취소, 정정취소가능조회
    cb = get_circuit_breaker()
    if not cb.can_execute() and ptr_id not in _CB_BYPASS_TR_IDS:
        cb.record_blocked()
        logger.warning(f"CircuitBreaker OPEN - API 호출 차단: {ptr_id}")
        return None
```

매도 TR = `api/kis_order_api.py:50` `TTTC0011U`, 매수 = `:48` `TTTC0012U`. **둘 다 bypass 밖**(관리자 원문 확인).
CB 임계: `api/circuit_breaker.py:28-29` `failure_threshold=5`, `recovery_timeout=30.0`**초**.

**위치 ②** — `core/trading/position_monitor.py:23-24`, `:415-425`, `:589-608`

```python
CB_MAX_FAILURES = 3           # 종목별 매도 실패 임계
CB_COOLDOWN_MINUTES = 30      # 봉쇄 시간(분)
...
        if self._is_circuit_breaker_active(stock_code):
            self.logger.debug(f"{stock_code} Circuit Breaker 활성 중 - 매도 스킵 ")   # :421 ← debug. 무음.
```

**위치 ③** — `bot/liquidation_handler.py:267-270` — `should_liquidate_eod()` 거부 시 `continue`.
기본 구현은 `strategies/base.py:764-777` `return self.holding_period == "intraday"`.
**활성 8전략 전부 `swing`**(`rs_leader:28` · `book_pullback_ma20:52` · `minervini_volume_dryup:58` · `daytrading_3methods_breakout:50` · `elder_ema_pullback:67` · `book_envelope_200d:49` · `book_pullback_ma5:52` · `deep_mr_dev20:26`).
⇒ **EOD 일괄청산은 현재 구조적 no-op 이다.**

**페이퍼에서 안 보인 이유** — 페이퍼 매도는 `_execute_paper_sell_order`(`order_executor.py:353-380`)가 **API 를 한 번도 호출하지 않고** 즉시 FILLED 를 만든다. CB 가 OPEN 이어도 **100% 성공**한다. `_sell_fail_counts` 가 3에 도달할 경로가 **구조적으로 없다.**

**실매매에서 일어나는 일** — 손절 매도가 실패를 3회 쌓으면 그 종목은 **30분 매도 봉쇄**. 그동안 유일한 흔적은 **`debug` 한 줄**(LOG_LEVEL=INFO 라 파일에도 안 남는다).
그 사이 **EOD 백스톱이 없어**(swing) 그날 그 포지션을 닫는 코드 경로가 **남지 않는다** → 오버나이트 갭에 무방비.
⚠️ **비대칭**: `ctx.sell()`(`core/trading_context.py:538-605`)은 `_sell_fail_times` 를 **조회하지 않는다** — 「전략이 스스로 낸 매도신호」는 봉쇄를 뚫고, **「모니터의 손절」만 막힌다. 손절이 전략 신호보다 «약한» 보호를 받는 구조다.**

**검수 판정** — **CONFIRMED. 단 축 4 의 산수가 틀렸고, 근거를 교체해야 한다.**
- ❌ 축 4: 「2초·4초 백오프 3회 = 6초 → 3회 전부 실패 → `_sell_fail_counts=3`」
- ✅ 검수: `_record_sell_failure` 는 **`attempt == max_retries` 인 마지막 1회에만** 불린다(`:491`)이고 **+1** 한다(`:604-608`).
  ⇒ `_execute_sell` **한 번**이 만드는 실패 기록은 **1**. 3에 도달하려면 `_execute_sell` 을 **3번** 들어가야 하고, 모니터 주기 3초·회당 약 6초이므로 **약 24초**가 필요하다. API CB OPEN 창 30초라 **아슬아슬하게 가능하지만 「자동」은 아니다.**
  또한 API CB 를 OPEN 시키려면 타임아웃/연결/SSL **5연속**이 필요하고 `API_READ_TIMEOUT` 이 30초이므로 **앞단에만 약 150초**가 든다.
- 🔴 **그럼에도 P1 을 유지하는 이유는 «다른 줄»이다**: `_record_sell_failure(stock_code, error=e)` 가 `TypeError/ValueError` 를 받으면
  `:595-601` 이 카운터를 **즉시 `CB_MAX_FAILURES` 로 세우고 바로 활성화**한다. 그 `except` 는 `_execute_sell` 전체를 감싼다(`:493`).
  ⇒ **매도 경로의 사소한 타입 버그 1건 = 그 종목 30분 즉시 봉쇄**이고, 그동안의 유일한 흔적은 `:421` **debug** 다.
- 🔀 **축 1-6 과 상쇄 관계**(§4 모순 6): 실전 매도는 **접수만으로** `_record_sell_success` 가 불려 카운터를 지운다(`:610-616`) ⇒ 3-스트라이크는 **주문이 접수조차 안 되는 구간에서만** 쌓인다. 발생 확률은 축 4 서술보다 **낮다**.
- 축 4-3(swing 백스톱 없음)은 단독 결함이 아니라 이 사슬의 「백스톱 없음」 절이다 ⇒ **흡수**(단독 등급 `~~P1~~ → P2`).

**재현 방법(실행 안 함)** — `grep -n "API 호출 차단: TTTC0011U" logs/<id>/*` · `grep -n "Circuit Breaker" logs/<id>/*` · LOG_LEVEL 을 DEBUG 로 올린 **사본**에서 `:421` 발화 확인.

**수정안(제안)** — ① `api/kis_auth.py:326` `_CB_BYPASS_TR_IDS` 에 **`"TTTC0011U"`(매도) 추가**(**1줄**). **매수 `TTTC0012U` 는 넣지 않는다** — 「가드는 새 위험을 만드는 쪽에만 건다」가 이 코드베이스의 명시 원칙이다(`core/orders/order_executor.py:107-109` 주석).
② `core/trading/position_monitor.py:421` `debug` → `warning`(쓰로틀)(**1줄, 저비용 추가 후보**).
③ 이후: 「API CB 차단 실패」와 「거래소 거부 실패」를 구분해 전자는 미카운트 · `CB_COOLDOWN_MINUTES` 재검토(30분 = 장중 6.5시간의 7.7%).

**출처** — 축 4 발견 1·2·3 (검수 병합 **M7**).

---

### P1-9. 실전 인스턴스가 `minute_candles` 를 DELETE→INSERT 로 «이중 실행» 한다 → 조용한 절단 가능

**위치** — `bot/system_monitor.py:255-358` (`_handle_postmarket_tasks`) — **게이트는 `:263 if is_holiday(...)` 하나뿐. paper/real·INSTANCE_ID 분기 0건**(원문 확인).

```python
 277  print_today_trading_summary(...)          # 페이퍼 원장 리포트
 312  self._run_equity_snapshot()               # 1차
 322  await asyncio.to_thread(self._run_regime_index_refresh)
 328  await self._run_data_collection(current_time)
 337  self._run_equity_snapshot()               # 2차
 356  self._log_eod_benchmark(...)
```

**가장 위험한 조각** — `collectors/minute_writer.py:52-59` `replace_minute_day`:

```python
DELETE FROM minute_candles WHERE stock_code=%s AND trade_date=%s
# ... 행별 INSERT ...
conn.commit()
```

두 프로세스가 같은 `(code, date)` 에 동시 진입하면 **한쪽 DELETE 가 다른 쪽 INSERT 를 지울 수 있다.**
`bot/system_monitor.py:248-250` 이 휴장일 맥락에서 「최대 위험」이라 못박은 바로 그 유형이다.

**페이퍼에서 안 보인 이유** — 지금까지 이 블록을 도는 프로세스가 **하나뿐**이었다. 「덮어쓰기 = 멱등」은 writer 가 1개일 때만 성립한다.

**실매매에서 일어나는 일** — 15:35 무렵 실전 인스턴스와 페이퍼 봇이 **동시에** EOD 후속 블록을 돈다.
분봉 재적재가 겹치면 한쪽의 부분 fetch 가 완전본을 덮어 **조용히 절단**된다(로그엔 양쪽 다 「완료」).
나머지(리포트 오염·equity 이중쓰기·DART 한도 이중소모)는 **P2-16/17** 로 분리.

**검수 판정** — **CONFIRMED(이 조각만 P1).** 게이트 부재·표·DELETE/INSERT 전부 원문 확인. **절단의 실제 발생은 추정**(실전 인스턴스 미기동).
`_resave_paper_trading_state`(`:637`)만 `is_virtual_mode` 게이트가 있어 **현금 SSOT 는 안전한데 equity 는 안 안전**한 비대칭이 있다.

**재현 방법(실행 안 함)** — `grep -n "is_virtual_mode\|paper_trading" bot/system_monitor.py` → `_handle_postmarket_tasks` 안 **0건**.
전환 후: `logs/<id>/` 와 `logs/robotrader_template_*.log` 양쪽에서 `grep -n "EOD equity 스냅샷 적재 완료"` 시각 대조.

**수정안(제안)** — `bot/system_monitor.py:255` 직후에 `from config.settings import INSTANCE_ID` + `if INSTANCE_ID != "default": return`(**2줄**).
페이퍼는 `default` 라 **영향 0**. 실전은 자기 `real_trading_<id>` 기반 리포트만 돌리는 게 맞다(그 도구는 **아직 없다** — P2-17).

**출처** — 축 3 발견 5 + 축 1 발견 9 (검수 병합 **M3** 중 분봉 조각).

---

### P1-10. `instances/*` 보호가 «바깥 repo» `.gitignore` 에만 있다 — 백업/메모 파일·단독 repo 화 시 앱키 유출

**위치** — 실측(`git check-ignore -v`, 검수 재확인 `grep`):

```
.gitignore:47:RoboTrader_template/instances/*/key.ini              instances/ma20/key.ini
.gitignore:48:RoboTrader_template/instances/*/trading_config.json  instances/ma20/trading_config.json
(무출력, exit 1)                                                   instances/rs_leader/key_backup.ini
(무출력, exit 1)                                                   instances/rs_leader/keys.txt
(무출력, exit 1)                                                   instances/rs_leader/notes.md
```

`RoboTrader_template/.gitignore` 에 `instances` 문자열 **0건**(grep exit 1 — 검수 원문 확인).
보호는 상위 `D:/GIT/kis-trading-template/.gitignore:45-48` 의 **두 글롭뿐**이다.
`git ls-files instances` → `README.md`·`key.ini.example`·`trading_config.json.example` 3건만 추적(**현재는 정상**).
그리고 `instances/README.md:12` 는 「`instances/` **전체가** .gitignore됨 — 실 key.ini는 절대 커밋되지 않음」이라고 **거짓을 적고 있다**.

**페이퍼에서 안 보인 이유** — 페이퍼 봇은 `instances/` 를 안 쓴다. 루트 `config/key.ini` 는 `RoboTrader_template/.gitignore:2` 로 **별도 보호**돼 있어 문제가 드러나지 않았다.
(`key.ini.bak` 이 걸리는 것도 `*.bak`(`:249`) 때문 — **의도가 아니라 우연**이다.)

**실매매에서 일어나는 일**
1. 새 인스턴스 준비 중 `cp key.ini key_backup.ini` 하거나 앱키를 `keys.txt` 에 메모 → **둘 다 추적 대상** → `git add .` 한 번에 실계좌 앱키·시크릿이 **공개 이력에 박힌다. SHA 는 되돌릴 수 없다.**
2. 이 프로젝트의 선언된 목적이 **템플릿 복제**인데(`CLAUDE.md`), `RoboTrader_template/` 을 단독 repo 로 떼거나 형제 프로젝트로 복사하면 `.gitignore:47-48` 이 **따라가지 않아** `instances/*/key.ini` **자체가 추적된다.**

**검수 판정** — **CONFIRMED**(grep exit 1 재확인). P1 유지 — 「돈이 직접 나가진 않지만 **실계좌 탈취 경로**」.

**재현 방법(실행 안 함)** — `git check-ignore -v instances/rs_leader/keys.txt; echo $?` · `grep -n instances RoboTrader_template/.gitignore`.

**수정안(제안)** — `RoboTrader_template/.gitignore` 에 **3줄** 추가:
`instances/*` + `!instances/README.md` + `!instances/*/*.example`(바깥 repo 규칙과 **이중화**).
겸해서 `instances/README.md:12` 문구를 실제 규칙과 일치시키고 「백업 파일을 인스턴스 폴더에 두지 말 것」 명시.

**출처** — 축 5 발견 2 (검수 §1 5-2).

---

## 3. P2 22건 · P3 9건 — 표

### P2 — 운영 중단 · 성능 왜곡 · 계기 오염

| # | 제목 | 파일:줄 | 페이퍼에서 안 보인 이유 | 실매매 영향 | 판정 | 출처 |
|---|---|---|---|---|---|---|
| 11 | 손실 블랙리스트가 **페이퍼 원장만** 읽고 JSON 으로 끌 수 없다 | `core/candidate_selector.py:111,187,435-491` · `db/repositories/trading.py:656-667,687-702` · `core/models.py:383-420` | 봇이 하나일 땐 「자기 이력으로 자기 후보를 거른다」가 의도된 동작 | 실전 후보가 **페이퍼 봇 손절 이력의 함수**가 된다(09-11 6건/09-14 7건 규모면 매일 10여 종목 제외). 실전 자기 손절은 **영원히 블랙리스트에 안 오른다**. A/B 비교 불능 + 「페이퍼 봇 끄기」가 실전 동작 변경이 된다 | ~~P1~~ → **P2(최상위)** · CONFIRMED · **전환 전 결재 필요**(§7 참조) | 1-5 |
| 12 | 실전 사이징에 **전략·K·`max_per_stock_amount`·인스턴스 노브 전부 미결선**(9%/20 고정) | `core/trading_decision_engine.py:417-427` · `core/fund_manager.py:212,213,266,269,276` · `bot/initializer.py:456-459,484-485,506-508,571` · `main.py:118-119` | 페이퍼는 VTM 원장(전략당 1천만·자본/K·복리 재산정)이 SSOT라 이 경로를 안 탄다 | **검증한 것과 다른 것이 돈다.** cap 1천만이면 페이퍼 종목당 200만 vs 실전 90만(**2.2배 작고 종목 수 2배 많다**). K 는 `max(20, ΣK)=20` 으로 흡수되고, 실효 한도는 `0.90/0.09 = 10종목`. `rs_leader` 의 `max_position_ratio:0.3`·`max_position_count:20`·`buy_budget_ratio:0.05` **셋 다 무시** | ~~P1~~ → **P2(최상위)** · CONFIRMED | M6(2-2·2-5·2-6·1-12) |
| 13 | 매도 「성공」 = **접수**(손절 로그 오독 + 실패 카운터 조기 리셋) + `liquidate_all_positions_end_of_day` 는 **반환값조차 미검사** | `core/trading/order_execution.py:381-388` · `core/trading/position_monitor.py:470-473,610-616` · `bot/liquidation_handler.py:215-221`(신규) | 페이퍼 분기는 `execute_virtual_sell` = **체결 완료**를 본다 | 손절 로그가 체결처럼 보인다. `_record_sell_success` 가 **접수만으로** 실패 카운터를 지운다. `:215-221` 은 2026-08-14 D3 「반환값 검사」 수정이 **안 들어간 경로**로, 무조건 INFO 를 찍는다. ⚠️축 1 의 「EOD 미체결 오버나이트」는 **현 구성(8/8 swing)에서 발생 경로 없음** | ~~P1~~ → **P2** · CONFIRMED(영향 재해석) | M8(1-6 · 6-8 fail-open · 신규 줄) |
| 14 | 시장가 매도 체결가 fallback 부재(**탈출구가 없다**) | `core/orders/order_monitor.py:332-349` · `core/orders/order_executor.py:417,434` · `core/trading_decision_engine.py:771` · `bot/liquidation_handler.py:274` | 페이퍼 매도는 넘겨받은 가격으로 즉시 FILLED. 체결가를 API 에서 파싱하는 코드가 **페이퍼 경로에 없다** | 실전 시장가 매도의 `order.price` 는 **0** 이라 fallback 이 무의미. `avg_prvs` 가 비면 **영원히 보류**(재시도 상한도, `tot_ccld_amt/tot_ccld_qty` 역산도 없다). 부기: `avg_prvs` 가 문자열 `'0'` 이어도 같은 덫 | ~~P1~~ → **P2** · **OVERSTATED**: `_handle_full_fill` 은 KIS 가 **이미 「전량 체결」을 보고한 행**에서만 불리므로 `avg_prvs` 만 비는 것은 TR 계약 위반 = **일상적 발생 근거 없음**. 단 **수정 비용 1~3줄**이라 최소 집합 인접에 남긴다 | 1-2 |
| 15 | 인스턴스 config 가 루트와 **병합되지 않음** + 드리프트 검사 도구 0 | `config/settings.py:103-127` · `instances/rs_leader/trading_config.json` | 페이퍼는 `config/trading_config.json` 을 읽어 **항상 최신**. 인스턴스 사본은 2026-06-18 21:59 이후 미수정 | 06-18 이후 루트 변경 1건(`a57a607` 급락게이트 축 KOSDAQ→auto)이 **100% 미전파**. 인스턴스 사본을 템플릿으로 새 폴더를 만들면 **09-11 승인·머지한 수정이 실전에서만 되돌아간다.** 드리프트 검사 도구·테스트 **0개**(테스트 3건은 전부 루트 경로 하드코딩) | ~~P1~~ → **P2** · **OVERSTATED**: 그 항목은 이 파일에서 **`"enabled": false`** 다. 활성은 `rs_leader`(`regime_index:"KOSPI"`) 하나뿐 ⇒ **현재 파일 그대로 기동해도 09-11 개정이 실계좌에서 안 되돌아간다.** 위험은 **「템플릿으로 복사할 때」에 한정**. 코드 0줄 · 기동 전 diff 1회로 닫힘 | M4(4-7·5-3) |
| 16 | EOD 후속 블록(리포트·equity·수집·벤치마크) **게이트 부재** | `bot/system_monitor.py:255-358` · `tools/paper_strategy_equity.py:283-321` · `collectors/eod_collection.py:47-70` | 봇이 하나뿐일 때는 정상 동작 | 계기 오염 — `paper_strategy_equity` 이중 UPSERT(`updated_at` 2회 · 트랜잭션 교차), EOD 수집 2배(KIS·DART 한도 이중 소모), regime 지수 2회 | P2 · CONFIRMED | M3 나머지 |
| 17 | **실원장 EOD 리포트 도구가 없다** + `logs/<id>/` 를 읽는 도구 0 | `tools/daily_trading_summary.py:189,237,304,310,392`(전부 `virtual_trading_records`) · `tools/` 4파일에 로그 경로 참조 0건 | 페이퍼 도구가 페이퍼를 읽는 건 정상 | 실전 첫날 EOD 점검을 **평소 습관대로 하면 경보도 매매도 하나도 안 보인다** → **「조용하다 = 정상」 오독**. 게다가 실전 인스턴스가 도는 `print_today_trading_summary` 는 **페이퍼 매매를 자기 것처럼 출력**한다 | P2 · CONFIRMED | 3-5 · 4-6 |
| 18 | 일일 손실 한도가 **재기동에 리셋** + 분모가 줄어드는 `total_funds` | `core/fund_manager.py:236,472,504,535` · `bot/initializer.py:840`(write-only) · `core/trading_context.py:422` | 페이퍼는 재기동이 무해(손실이 전략 원장으로 복원)해서 눈에 안 띄었다 | **한도 10% 를 맞고 멈춘 봇을 장중 재기동하면 그날 또 10% 를 잃을 수 있다**(누적 20%+). 복원 독자 0건(grep 확인). 분모는 「그날 시작 자본」이 아니라 현재 총자금이라 **보수적 방향으로 일찍** 트립. 멈추는 것은 **신규 매수뿐**(유일 소비자 `trading_context.py:422`) | ~~P1~~ → **P2** · CONFIRMED | 2-7 · 4-10 |
| 19 | 미체결 타임아웃이 **쿨다운을 무장시키지 않아** 재발주 | `core/models.py:288-296` · `core/orders/order_executor.py:117-121` · `main.py:465-469` · `core/trading_context.py:518-519` | 페이퍼 매수는 즉시 FILLED → 곧바로 `set_buy_time` 이 걸려 25분 쿨다운 발효. **타임아웃→취소→재발주 경로가 페이퍼에서 단 한 번도 실행된 적 없다** | `set_buy_time` 운영 호출자 전수(grep) = `order_completion_handler.py:261,430` · `order_execution.py:553` · `trading_analyzer.py:305` — **전부 체결 경로. 취소 경로 0건.** 일봉 신호는 하루 종일 동일하므로 5분마다 재발주 → 종목당 하루 최대 **약 75회**(380분÷5분, 산술 상한). 1전략 인스턴스는 on_tick 주기가 **9초**(페이퍼 72초)라 **8배 증폭**. 직접 손실은 아니다(취소된 지정가엔 수수료 무). **진짜 비용은 API 예산**이고, 그것이 시세 폴링을 굶기면 「시세 결측 → 손절 스킵(debug)」과 연결된다. **P1-6 과 곱해지면 위험이 오른다** | ~~P1~~ → **P2** · CONFIRMED | 6-4 |
| 20 | 기동 시 미체결 **전량** 취소가 매도·수동주문까지 취소, 실패 1건이 기동 차단 | `bot/state_restorer.py:776-800` · `framework/broker.py:799-821,660-664` | 페이퍼는 `_restore_holdings_from_db` 만 탄다 | 독스트링(`:806`)이 `sll_buy_dvsn_cd 01매도/02매수` 를 적어 놓고 **코드는 그 필드를 안 쓴다**. 장중 크래시(손절 지정가 걸림) → 재기동 → **매도 미체결까지 취소** → 보호가 tp/sl 로 넘어가는데 그 값이 P1-4 때문에 DEFAULT/STALE. **사장님 HTS 수동 주문도 함께 취소**. 취소 1건 실패 시 그날 **봇 미기동** | P2 (P1-4 결합 시 실질 P1) · CONFIRMED | 3-4 |
| 21 | 종료 시 미체결 취소가 **인메모리 기준**(기동 경로와 비대칭) + 텔레그램을 **먼저** 닫음 + 포지션 미청산 | `bot/initializer.py:736-764,872-903` · `main.py:161-164` | 페이퍼는 미체결이 없다 | `kill -9`·창 X·정전이면 취소가 **아예 안 돈다** → 지정가 매수 미체결이 KIS 에 살아 있고, 그 사이 체결되면 봇이 모르는 포지션 → 다음 아침 **`LiveStartupAbort`**. 텔레그램을 취소 **앞**에서 닫아 취소 실패는 **구조적으로 통보 불가**. **종료 = 보유분 그대로 노출** | P2 · CONFIRMED | 4-9 |
| 22 | **킬스위치 부재** — 매수만 끄는 수단 0 | 전수 grep(`KILL_SWITCH|kill_switch|EMERGENCY|emergency_stop|STOP_FILE|halt.txt|liquidate_all|force_liquidate`) → EOD 스케줄 전용 2건뿐 | 페이퍼는 멈춰도 손해가 없다 | 운영자의 유일한 수단이 **프로세스 종료**이고, 그때 P2-21 이 따라온다. 텔레그램 명령 핸들러는 존재하나 **P1-1 때문에 초기화 자체가 안 된다** | P2 · CONFIRMED · **파일 플래그 1개면 해결** | 4-9 |
| 23 | **2026-11-19 수능일 미등록** + 15:30 이후 감시·EOD·미체결관리 **전면 정지** | `config/market_hours.py:207-219`(`special_days` = `2025-11-13` 단 하나) · `main.py:433-435,506` · `utils/holiday_kis_sync.py:93-99` | 그 날이 아직 안 왔고, 페이퍼는 틀려도 돈이 안 나간다 | KIS 휴장일 동기화는 **개장/마감 «시각»을 안 가져온다**(`bass_dt`·`opnd_yn` 2필드뿐) ⇒ 손으로 안 넣으면 영원히 없다. 그 날(10:00~16:30 가정) ①09:00~10:00 **개장 전 오발주** ②15:20~16:30 **주문 전멸** ③15:30 이후 **손절 감시·미체결 관리까지 전멸**(= 마지막 1시간 **무보호**). `can_place_order`(`:573-602`)는 CLOSING_* 만 차단하고 OPENING_PROTECTION 은 검사조차 안 한다 | ~~P1~~ → **P2(기한부 · 11월 전)** · CONFIRMED. 「감시 전멸」은 **새 사실** | 6-1 · 6-7 |
| 24 | 휴장일 캐시가 **cwd 단일 JSON** · 인스턴스 미분리 · `"w"` 직접 덮어쓰기 | `utils/holiday_kis_sync.py:18,36-44,24-34` · `run_robotrader.bat:8` · `run_instance.bat:18`(둘 다 같은 cwd) | 지금까지 이 파일의 writer 가 **하나뿐**이었다 | 07:40 에 두 봇이 동시에 `sync_today()` → 같은 파일을 `"w"` 로 덮어쓴다. 한쪽이 쓰는 중 다른 쪽이 읽으면 잘린 JSON → **예외가 삼켜져 `_runtime_closed` 가 빈 집합**(fail-open). 실측: **2026-12-31(연말휴장)은 `holidays.KR` 에 없고 KIS 캐시에만 있다** ⇒ 캐시가 비면 그날 실전 인스턴스가 **정상 기동해 매수를 시도한다** | P2 · CONFIRMED(경로·저장모드) / 절단 실현은 추정 — **2026-09-08 ARCHIVE_INDEX 0바이트 사고와 정확히 같은 결함 클래스** | 6-2 |
| 25 | **일일 리셋 경로 부재** (`reset_eod_state`·`clear_all` 호출자 0, `_candidates_loaded` 되돌리는 운영 경로 0) | `main.py:429-435,438` · `bot/candidate_loader.py:32-39` · `bot/liquidation_handler.py:665` · `config/market_hours.py:121` · `utils/price_utils.py:69-82` | 페이퍼는 스케줄러가 매일 07:40 에 새로 띄우고 전날 창을 닫는 **관행**이 있다 | 실전 인스턴스에는 **그 관행을 강제할 장치가 없다**(`D:\GIT\run_all_robotraders.bat:66-73` 에 `run_instance.bat` 항목 **없음**). 며칠 살려 두면 **어제 후보로 오늘 매매**하고, `_eod_retry_count` 가 이월돼 다음 EOD 첫 실패가 곧바로 `_force_complete_failed_stocks`(**실매도 없이 장부만 청산**)로 간다. `reload_candidates` 는 스스로 「TODO: 텔레그램 /reload 에서 호출하도록 연결」이라 적고 **호출자 0건** | P2 (P1-2 와 겹치면 P1) · CONFIRMED | 6-6 |
| 26 | 실전도 `screener_snapshots` 에 쓴다(인스턴스 컬럼 없음 · DELETE 없음 · 읽기는 전 해시 합산) | `run_instance.bat:62-64` · `db/repositories/candidate.py:143-153` · `core/screener_snapshot_provider.py:89-95` · `runners/screener_snapshot_collector.py:113-117` | writer 가 하나뿐이라 「덮어쓰기 = 멱등」이 성립했다 | 두 프로세스가 같은 `(strategy, scan_date, params_hash)` 에 쓰는데 **DELETE 가 없어** 결과가 갈리면 **합집합**이 남는다 → 다음날 두 봇이 **상한 초과 후보**를 읽는다. `params_hash` 는 전략 폴더 공유 상수라 **같다**(실측: 09-08~09-11 전 전략 `count(DISTINCT params_hash)=1`) | P2 · CONFIRMED(스키마·쿼리) / 결과 분기는 추정 · **bat 1줄로 닫힘** | 5-7 · 3-6 |
| 27 | `save_real_sell` 평단 쿼리만 **존재성 술어** → 짝 실패 시 `profit_loss=0` 을 성공처럼 기록 | `db/repositories/trading.py:141-171` | 페이퍼 손익은 `save_virtual_sell` 별도 산식 + 부분체결 0건 | 2026-08-14 에 같은 파일 두 쿼리(`:213-221`·`:491-504`)는 **잔량 술어로 고쳐졌는데 이 세 번째만 남았다**. 부분매도 후 두 번째 매도에서 avg NULL → 손익 0. `save_real_sell` 은 `return True` 라 호출자는 「실전 매도 기록 저장」 INFO — **실패가 성공처럼 보인다** | P2 · CONFIRMED | 3-3 |
| 28 | 분할매수 실포지션 전량매도 시 **유령 잔량** → 다음날 `LiveStartupAbort` | `core/orders/order_db_handler.py:181-197` · `db/repositories/trading.py:213-221` · `bot/state_restorer.py:867-876,1381-1385` | `get_virtual_open_positions`(`trading.py:445-448`)은 **존재성 술어**라 유령 잔량이 생길 수 없고, 페이퍼엔 계좌 대사가 없다 | 매도 1건당 `buy_record_id` 하나만 기록하는데 복원은 여러 BUY 행을 한 레그로 접는다 ⇒ BUY#5(5주)+BUY#8(5주) 를 10주 한 주문으로 청산하면 **BUY#5 가 열린 채 남는다** → 계좌 0주 vs DB 5주 → abort | P2 · 도달성은 **추정**(3전략 모두 `stock_code in self.positions` 로 재매수를 막아 정상 분할매수는 드물다) | 3-2 |
| 29 | abort 후 **복구 절차·도구 부재**(런북 0, 실원장 보정 도구 0) | `main.py:706-711` · `run_instance.bat:70`(`pause`) · `instances/README.md`(20줄, abort 절 없음) · `tools/` 4파일 | 페이퍼는 abort 가 없다 | `LiveStartupAbort` → CRITICAL + 텔레그램(꺼짐) → `sys.exit(2)`. `.bat` 은 `pause` 로 끝나 **콘솔을 보고 있어야만** 안다. 메시지가 지시하는 조치(「수동 확인 후 재기동」·「`strategy` 컬럼 UPDATE」)에 **어떤 SQL 인지 없다**. 07:40 에 조용히 죽고 15:30 EOD 점검 때 발견 → 그 사이 실포지션 **무보호** | ~~P1~~ → **P2**(P1-1 의 **하류** — 텔레그램을 고치면 「아무도 모른다」는 해소된다) · CONFIRMED | 3-7 |
| 30 | 인스턴스 `trading_config.json` **부재·파손 시 조용히 페이퍼로 강등**(런처 미검사) | `config/settings.py:111-127` · `run_instance.bat:21-25`(`key.ini` 존재만 검사) | 루트 파일은 항상 존재하고 테스트가 핀한다. 인스턴스 폴더는 **손으로 만든다** | 오타 폴더명·복사 누락·JSON 끝 쉼표 하나면 → 실계좌 키로 **인증은 되고** `paper_trading=True` 로 떨어져 **`real_total_funds_cap` abort 조차 안 걸린다**. 실계좌 앱키로 붙은 프로세스가 전략 0개로 하루 종일 돌고, 운영자는 「실전 기동 성공」으로 본다. 로그엔 WARNING 2줄 | P2 · CONFIRMED(코드 경로) / 「하루 종일 안 드러난다」는 추정 | 5-4 |
| 31 | 실전 로그에 **`[PAPER]` 접두**가 찍힌다(전략 dict 에 `paper_trading` 미전달) | `strategies/*/strategy.py:275-282,324-330`(8종 동일) · `core/models.py:415` · `strategies/*/config.yaml`(13개 전부 `paper_trading: true`) | 페이퍼에선 맞는 표기다 | `trading_config.json` 최상위 `paper_trading:false` 는 **전략 dict 에 들어가지 않는다**(`:415` 가 `strategies` 리스트를 원문 그대로 전달) ⇒ 실전 실주문 시그널이 전부 `🧾 [PAPER] 매수 시그널:` 로 로깅되고 `metadata["paper_only"]=True` 가 붙는다. **동작 영향 0**, 그러나 **이 프로젝트는 로그를 SSOT 로 쓴다** — EOD grep 점검이 실계좌 체결을 페이퍼로 오분류한다 | P2 · CONFIRMED | 5-8 · 1-R21 |
| 32 | **모의투자 경로 부재 확정**(TR 실전 고정, `svr='demo'` 죽은 코드) → 리허설 수단 없음 | `api/kis_auth.py:792-796,127-146,156-222` · `api/kis_order_api.py:48,50,110,172,223,275` · `api/kis_account_api.py:23,62,97,151,188,244` | 해당 없음(계획 전제) | 운영 `api/` TR **38개 전부 실전 고정**. `VTTC*` 는 `_NON_IDEMPOTENT_TR_IDS` 집합에만 등장하는 **미발행 값**. `auth(svr, ...)` 는 `svr` 을 **한 번도 안 쓴다**. ⇒ `KIS_BASE_URL` 만 모의로 바꾸면 **토큰은 발급되고 인증 성공 로그까지 찍힌 뒤** 주문·잔고가 전부 실패. **「모의에서 한 번 돌려보고 간다」가 불가능**함이 코드로 확정 | P2 · CONFIRMED | 5-6 |

### P3 — 불편 · 관측

| # | 제목 | 파일:줄 | 페이퍼에서 안 보인 이유 | 실매매 영향 | 판정 | 출처 |
|---|---|---|---|---|---|---|
| 33 | 계좌번호 **생짜 슬라이싱**(하이픈 입력 시 `my_prod="-0"`) | `api/kis_auth.py:136-142,756-760` | 루트 값이 8자리라 항상 `else` 분기(`my_prod='01'`) — 하이픈 경로가 실행된 적 없다 | HTS 표기 그대로 `12345678-01` 을 붙여넣으면 **인증은 성공**하고 「✅ 인증 헤더 설정 완료」가 찍힌 뒤 모든 주문·잔고 TR 이 `ACNT_PRDT_CD="-0"` 로 실패. 검증·정규화·경고 **전무** | P3 · CONFIRMED(코드) / 「흔한 입력」은 추정 | 5-5 |
| 34 | `paper_trading` **기본값 비대칭**(주문=False / 원장=True) | `core/orders/order_executor.py:150,341` vs `core/orders/order_db_handler.py:127` (+`bot/state_restorer.py:67`·`core/trading_decision_engine.py:49` 은 True) | 정상 배선에서는 안 드러난다 | `config` 가 None/속성 부재면 **실주문은 나가고(False→실전) 실원장에는 안 쓰인다(True→return)** = 「체결은 있는데 DB 행이 없는」 조합이 한 줄 기본값 차이로 만들어진다. 현재 트리거 가능성은 낮다(`core/order_manager.py:59` 가 config 를 필수 위치인자로 받음) | P3 · 비대칭은 CONFIRMED / 트리거는 추정 | 5-9 |
| 35 | cap 우회 fallback(`min(5000000, available*0.1)`) | `core/trading_decision_engine.py:119-131`(`:128`) | 가상 경로는 `:417` 에서 갈라져 안 탄다 | — | ~~P2~~ → **P3 · REFUTED(라이브에서 발화 못 한다)**: 엔진이 fallback 으로 수량을 만들어도 `bot/trading_analyzer.py:202` 가 `fund_manager.get_max_buy_amount()` 로 **재검증**하고, 0 이면 `:211-213` 이 `int(0/price)=0` → 「매수 포기」 return ⇒ **cap 우회 주문은 나가지 않는다.** 남는 것은 죽은 경로·오독 위험뿐 | 2-3③ |
| 36 | 매수 수수료가 예약에 미반영(`calculate_buy_cost` 호출자 0) | `bot/trading_analyzer.py:188,251` · `core/fund_manager.py:337-360,546-556` | 페이퍼는 VTM 산식이 따로 있다 | **의도된 설계**다 — `confirm_order` Note 가 「매수 수수료는 매도 시 1회 인식」이라 못박고 정합성 등식을 지킨다. 가용이 정확히 0 일 때만 KIS 필요현금이 모자란다(90만 주문 시 135원) | P3 · CONFIRMED · **손대지 말 것**(`fund_manager.py:351` 「⚠️ 되돌리지 말 것」) | 2-4 |
| 37 | `SECURITIES_TAX_RATE=0.0018` 이 2024년 값 | `config/constants.py:175-176` | 페이퍼·실전이 같은 상수를 쓴다 | 매도 1건당 0.03%p 과대 비용(추정) ⇒ 페이퍼 성과가 **체계적으로 과소평가**. 농특세 분리 표현 없고 KOSPI/KOSDAQ·ETF 가 같은 상수 | P3 · **UNVERIFIABLE(코드로 판정 불가 — 세법 확인 필요)**. ⚠️바꾸면 **페이퍼 과거 손익이 전부 흔들린다** | 2-9 |
| 38 | 부분체결 타임아웃 **owner 누락** | `core/orders/order_timeout.py:219-226`(매도 leg) · `:294`(매수 leg) | 페이퍼는 `can_add_position` 이 매수경로에 결선돼 있지 않아 **구조적으로 관측 불가**였다 | 전량체결 경로(`order_monitor.py:373-376,408-409`)는 `_owner_slot` 에서 owner 를 읽어 넘기고 그 자리 주석이 「owner 를 안 넘기면 `[모호제거]` 로 영구 보류」라 명시하는데, **부분체결 타임아웃 경로만 그 수정이 안 들어갔다**. 1전략이면 대개 무해(엔트리 1개) | P3(2전략 전환 시 P2) · CONFIRMED · **축 1·2 가 같은 함수의 두 leg 를 따로 셌다 → 한 항목으로 병합** | M5(2-10 · 축1 백로그표) |
| 39 | `framework/executor.py` **인스턴스화 0건**(감사 함정) + 정정 경로 주석 처리 | `framework/executor.py:178`(자기 독스트링 예제뿐) · `core/orders/order_monitor.py:116-117` | 페이퍼는 정정할 미체결이 없다 | 그 파일엔 `_call_kis_modify`·부분체결 추적·상태 폴링·미체결 조회가 **잘 구현돼 있는데 한 줄도 안 돈다.** ⇒ 「미체결 관리가 잘 돼 있나」를 그 파일로 확인하면 **통과 판정이 나온다**. 살아있는 `framework/broker.py:720-721` 은 항상 `"02"`(취소) 고정이고, `max_adjustments`·`adjustment_threshold_percent` 설정은 **아무 것도 하지 않는다** | P3(기능) / P2(감사 오판) · CONFIRMED | 1-11 |
| 40 | `real_trading_<id>` 가 `real_trading_records` **시퀀스 공유** · FK 없음 | `db/repositories/trading.py:49-52`(`LIKE ... INCLUDING ALL` 이 nextval 식을 문자 그대로 복사) | 해당 없음 | `real_trading_records` DROP 시 모든 인스턴스 표 INSERT 사망 · 고아 참조를 DB 가 못 막는다. DB 실측: `real_trading_rs_leader` **0행** / `real_trading_records` **224행**(2026-03-05~06-08, 열린 포지션 0, 그중 11행은 죽은 함수가 남긴 오염) | P3 · **검수 미재현(DB)** — SELECT 재확인 권장 | 3-9 · 3-10 |
| 41 | **문서 허위** — `VIRTUAL_MODE` · `.env` 키 출처 · `instances/README.md` 의 robotrader DB · `real_total_funds_cap` 미기재 | `RoboTrader_template/CLAUDE.md`(주의사항 절) · `instances/README.md:12,16` · `instances/*/trading_config.json.example` | 해당 없음 | `grep -rn "VIRTUAL_MODE" --include=*.py .` → **0건**(존재하지 않는 안전장치를 문서가 약속한다). 키는 `.env` 가 아니라 `key.ini` 에서만 읽힌다. README 가 **삭제 예정 DB**(`robotrader`)를 가리킨다. 실전 기동의 **유일한 필수 키** `real_total_funds_cap` 이 `.example` 에도 README 에도 **없다** ⇒ README 대로 따라 하면 **반드시 첫 기동에서 abort** | P3 · CONFIRMED | 5-10 · 5-11 |

---

## 4. 검수가 «정정» 한 것

### 4-1. 축 간 모순 8건 (검수 §2)

| # | 모순 | 판정 | 왜 중요한가 |
|---|---|---|---|
| 1 | **텔레그램** — 축 6 백로그 표 6번은 「실전 인스턴스는 «닫힘»(정정) — `instances/rs_leader/key.ini:11 enabled=true` 이므로 실전 경보는 간다」 | **축 6 이 틀렸다 · REFUTED.** `core/telegram_integration.py:56` 이 `Path("config/key.ini")` 를 하드코딩하므로 인스턴스 파일은 **읽히지 않는다**(축 4-4·5-1 이 맞다) | **가장 위험한 종류의 모순.** 「경보는 켜져 있다」는 오신뢰가 **다른 축의 완화책 전제**로 쓰이고 있었다. 축 6 은 **파일을 읽고 코드를 안 읽었다** |
| 2 | **수수료·세금 「두 벌」** — 축 3 은 「두 벌(열림)」, 축 2 는 「산식은 한 벌(정정)」 | **축 2 가 맞다.** `order_monitor.py:411-414` · `order_timeout.py:229-232` · `db/repositories/trading.py:164-167` 세 곳이 **같은 상수·같은 식** | 갈라지는 건 산식이 아니라 **리포트 도구**(`tools/daily_trading_summary.py` 가 gross)와 **체결 방식**이다. 축 3 표기를 축 2 쪽으로 통일 |
| 3 | **일일 손실 한도 분모** — 축 4 가드표 9번 「`total_funds` 가 `min(cap, 실계좌 total_balance)` 라 실계좌 값 맞다」 | **축 2 가 맞다.** P1-3 이 그 `total_balance` 가 **주식평가액뿐**임을 보였다 | 한도의 분모가 실계좌 총자산이 아니라 「주식평가액(또는 cap)」이고, **예수금 비중만큼 한도가 조기 발동**한다. 축 4 가드표 9번의 「실전 유효성 OK」를 **「주의」로 내릴 것** |
| 4 | **daytrading 과 분봉** — 브리프·백로그는 「`rebalancing_mode=true` 면 분봉 전략 시세 None」, 축 6 은 「daytrading 은 분봉을 안 쓴다」 | **축 6 이 맞다.** 파일을 직접 읽었고, 8전략 전부 `timeframe="daily"` 라는 축 6-8 표와 정합 | 브리프 문구를 **「분봉 전략 없음 · 영향은 `get_cached_current_price()` 영구 None」**으로 정정. ⚠️ 축 6 의 「현행 `true` 유지가 안전」 결론은 **「손절·상한가 가드·EOD 매도가가 API 단건 조회에 의존」과 긴장 관계** — §7 에 남긴다 |
| 5 | **추석 창** — 계획 전제 「9/24~28」 | **축 6 이 맞다. 계획 전제가 틀렸다.** `holiday_kis_cache.json`(synced 2026-09-14): `20260924,20260925,20260926,20260927` 다음이 **`20261003`** — **`20260928` 없음** | 전환 창은 **9/24(목)·9/25(금) + 주말**이고 **9/28(월)은 정상 거래일**이다. `utils/korean_holidays.py:72` 가 틀린 값이고, `holidays` 라이브러리가 설치돼 있으면 `is_lunar_holiday`(`:146-148`)가 항상 False 라 **현재는 무해**. MEMORY·계획서 문구를 정정할 것 |
| 6 | **축 1 과 축 4 가 서로를 상쇄한다** (어느 축도 안 봄) | 실전 매도는 **접수만으로** `_record_sell_success`(`position_monitor.py:610-616`)가 불려 `_sell_fail_counts` 를 지운다 | ⇒ 축 4-2 의 3-스트라이크는 **주문이 접수조차 안 되는 구간에서만** 쌓인다. 두 축을 합치면 **4-2 의 발생 확률은 축 4 서술보다 낮고**, 대신 **1-6 의 「손절이 성공으로 보인다」가 더 오래 지속**된다 |
| 7 | **부분체결 owner** — 축 1 은 `order_timeout.py:294`, 축 2 는 `:219-226` | **둘 다 맞다**(같은 함수의 매도 leg `:226` 과 매수 leg `:294`) | **한 항목으로 합칠 것**(→ P3-38, 병합 M5) |
| 8 | **`reserve_funds` 호출자 수** — 축 2 는 「호출 2곳」 | **실제는 3곳**: `bot/trading_analyzer.py:251` · `core/orders/order_executor.py:143` · `core/fund_manager.py:777`(프로토콜 위임) | 셋 다 `strategy_name` 미전달이라 **결론은 불변**이지만, **「전수」라고 쓴 열거가 틀렸다** — 이 계열의 오류는 반복되므로 기록 |

### 4-2. 반박 2건 (REFUTED)

| # | 원래 주장 | 반박 근거 | 결과 |
|---|---|---|---|
| R1 | 축 6: 「실전 인스턴스 텔레그램은 **닫힘**(정정) — 경보가 간다」 | `core/telegram_integration.py:56` · `api/kis_auth.py:600` 이 루트 경로를 **하드코딩**. 인스턴스 `key.ini` 는 읽히지 않는다 | **반박됨.** 등급은 오히려 **P1 1순위**로 올라갔다(P1-1) |
| R2 | 축 2-3③: 「fallback `min(5000000, available*0.1)` 이 **cap 을 우회해 주문을 낸다**」 | `bot/trading_analyzer.py:202` 가 `fund_manager.get_max_buy_amount()` 로 **재검증**하고, 0 이면 `:211-213` 이 `adjusted_quantity = int(0/price) = 0` → 「매수 포기」 return | **반박됨.** ~~P2~~ → **P3**(죽은 경로·오독 위험만) |

### 4-3. 과소평가 1건 (등급 상향)

| 항목 | 축의 자기 판정 | 검수 판정 | 근거 |
|---|---|---|---|
| **체결 오탐 복구**(P1-5) | 「코드는 확인, **오탐 발생 빈도는 추정**」 | **CONFIRMED — 축이 오히려 과소평가.** 도달성이 훨씬 높다. **P1-6 보다 도달성이 높다** | `framework/broker.py:793` 의 `status_unknown` 행은 **4키뿐**이라 `tot_ccld_qty` 가 **아예 없다** → `filled_qty=0` → 오탐 판정 조건이 **항상 참**. 레이트리밋·토큰 재발급 구간에서 흔한 조건 |

> 참고 — **또 하나의 과소평가**: 축 6 은 P1-2(owner 불일치)의 자기 등급을 「강한 추정」으로 달았으나,
> 검수는 `bot/system_monitor.py:124-148` 과 `bot/state_restorer.py:802-809` **두 독스트링**이 같은 버그를 명시적으로 문서화하고 있음을 근거로
> **「강한 추정이 아니라 레포가 스스로 문서화한 확정 사실」**로 판정했다.

### 4-4. 신규 1건 (어느 축도 안 본 것)

| 항목 | 위치 | 내용 |
|---|---|---|
| `liquidate_all_positions_end_of_day` 가 **매도 반환값을 아예 받지 않는다** | `bot/liquidation_handler.py:215-221` | `execute_sell_order` 반환을 **받지 않고** 「장마감 청산 주문」을 **무조건 INFO** 로 찍는다. **2026-08-14 D3 수정(「EOD 실매도 반환값 검사」)이 이 경로엔 안 들어갔다.** → P2-13(M8)에 편입 |

### 4-5. 등급 재조정 전수 (P1 24 → P1 10)

| 축·번호 | 한 줄 | 재조정 |
|---|---|---|
| 4-4 / 5-1 | 텔레그램 루트 하드코딩 | P1 유지 → **1순위** |
| 6-5 | 단일전략 후보 owner = 클래스명 | P1 유지 → **2순위**(자기 등급 상향) |
| 2-1 | `total_balance` = 주식평가합계 | P1 유지 |
| 3-1 / 1-7 | 실전 tp/sl 미영속 | P1 유지 |
| 1-4 | 체결 오탐 복구 | P1 유지(**도달성 상향**) |
| 1-1 | `status_unknown` 5분 | P1 유지 |
| 1-3 | 매도 부분체결 `cancel_success` | P1 유지 |
| 4-1 | 매도 TR CB bypass 밖 | P1 유지(4-2 산수 교정 · 4-3 흡수) |
| 3-5(분봉 조각) | `minute_candles` DELETE→INSERT | P1 유지(**이 조각만**) |
| 5-2 | `instances` gitignore | P1 유지 |
| 1-2 | 시장가 매도 체결가 0 | ~~P1~~ → **P2** (OVERSTATED — 진입 확률 과대) |
| 1-5 | 손실 블랙리스트 | ~~P1~~ → **P2(최상위)** |
| 1-6 | 매도 「성공」 = 접수 | ~~P1~~ → **P2** (영향 재해석) |
| 2-2 | 실전 사이징 미결선 | ~~P1~~ → **P2(최상위)** |
| 2-5 | 인스턴스 자금 노브 3개 사문화 | ~~P1~~ → **P2** |
| 2-7-2 | 일일손실한도 재기동 리셋 | ~~P1~~ → **P2** |
| 3-7 | abort 후 복구 절차 없음 | ~~P1~~ → **P2** (P1-1 하류) |
| 4-3 | 전환 후보 전부 swing | ~~P1~~ → **P2** (P1-8 에 흡수) |
| 4-7 / 5-3 | 인스턴스 config 화석 | ~~P1~~ → **P2** (OVERSTATED — 그 항목은 `enabled:false`) |
| 6-1 | 수능일 + 15:30 정지 | ~~P1~~ → **P2(기한부 11월)** |
| 6-4 | 쿨다운 미무장 → 재발주 | ~~P1~~ → **P2** |
| 2-3③ | cap 우회 fallback | ~~P2~~ → **P3 (REFUTED)** |

---

## 5. 기존 백로그 재확인 (열림 / 닫힘 / 승격)

> 4개 축의 재확인 표를 합쳐 중복 제거. 「신규 정보」 열은 **이번 감사로 추가된 것만** 적는다.

| 백로그 항목(브리프) | 상태 | 근거 줄 | 이번 감사의 신규 정보 |
|---|---|---|---|
| 실탄 경로 9% 룰 | 🔴 **열림** | `core/trading_decision_engine.py:426` → `core/fund_manager.py:212,266` | **전략·K·`max_per_stock_amount` 도 함께 미결선**. `fe02983` 는 **페이퍼 전용**(`bot/initializer.py:457` `is_virtual` 게이트). 실효 동시보유 한도 = `0.90/0.09 = 10종목` (P2-12) |
| `max_capital_pct` 이중 미결선 | 🔴 **열림** | `main.py:119`(provider 미주입) · `bot/trading_analyzer.py:251`(strategy_name 미전달) · `core/fund_manager.py:297` | 1계좌1전략에선 상한보다 **`_invested_by_strategy` 집계 자체가 죽는 것**이 남는다. `reserve_funds` 호출자는 **2곳이 아니라 3곳**(§4 모순 8) |
| `is_opening_protection` 호출자 0 (09:00~09:05 주문 나감) | 🔴 **열림** | `config/market_hours.py:556-559` 정의만. `can_place_order()`(`:573-602`)에 미포함 | 「시간대 위반 주문이 실제로 나가는 경우」는 **09:00~09:05 와 수능일 09:00~10:00 둘뿐**(축 6 시간표) |
| 수능일 15:20~16:30 일반주문 전멸 | 🔴 **열림 + 확대 → P2(기한부)** | `config/market_hours.py:207-219` 에 **2026-11-19 없음** | **15:30 이후 감시·EOD·미체결관리도 전멸**(`main.py:433-435`, `_check_eod_liquidation` 은 `:506` 으로 루프 **안**). KIS 동기화가 **시각을 안 가져온다**(`utils/holiday_kis_sync.py:93-99`) ⇒ 손으로 안 넣으면 영원히 없다 |
| 시장 CB `trigger_market_halt` 호출자 0 → `is_market_halted()` 영구 False | 🔴 **열림** | `config/market_hours.py:79-85` 정의 1줄뿐 | **죽은 가드 7곳** 열거: `trading_context.py:333` · `main.py:538` · `order_executor.py:96,329` · `order_monitor.py:60` · `market_hours.py:550,596` |
| VI arm 은 매수 직전 1회뿐 | 🔴 **열림** | `core/trading_context.py:403` 유일 호출자 | **미체결 매수 VI 즉시취소 가드(`order_monitor.py:73-94`)는 사실상 발동 경로가 없다** — arm 됐다면 `trading_context.py:417` 에서 이미 매수가 막혔을 것이므로(1계좌1전략에선 더욱) |
| 주문 API 와 시세 API 가 같은 전역 락·0.1s(주문 레인 없음) | 🔴 **열림** | `api/kis_auth.py:50,52,318,353,629-646` | 프로세스 간 조율 코드 **0건**(`_api_lock` 은 모듈 전역 = 프로세스 로컬). **같은 앱키면 합산 20/s = 헤드룸 0.** 현재 두 `key.ini` 의 APP_KEY 해시가 **다르다**(별도 버킷)이나 **강제·검사하는 코드는 없다**. 비멱등 주문 TR 은 `effective_max_retries=0` 이라 EGW00201 을 맞으면 **재시도 없이 실패** |
| 미체결 1건당 3초마다 목록 API 2콜 | 🔴 **열림 · 악화** | `config/constants.py:118` · `framework/broker.py:774,784` | **P2-19 가 이 부하를 곱한다**(종목당 최대 ~75회/일 재발주) |
| T+2 예수금 모델링 전무 · `get_inquire_psbl_order` 운영 호출 0 | 🔴 **열림 · 성격 정정** | `framework/broker.py:399-427` · `api/kis_api_manager.py:267-279` 둘 다 호출자 0 | **「매도 후 당일 매수 = 즉시 거부」는 성립하지 않는다**(증거금 100% 계좌는 매도 당일 재매수 가능, 결제만 D+2). 진짜 노출은 ①**주문가능금액을 한 번도 안 읽는다** ②**장중 입출금이 절대 반영되지 않는다**(`sync_with_account` 호출자 0). 페이퍼 실측: **ma20 매수의 85.7%(매수일 18/21)가 당일 매도 대금에 의존** |
| `cancel_order` `ord_dvsn` "00" 고정 | 🟡 **부분 닫힘 + 승격** | `order_executor.py:481-483` · `order_timeout.py:180` 이 `price==0` 이면 `"01"` 로 **추론**한다 | 실전 매도는 price=0 이라 `"01"` 이 정확히 나간다. **단 `bot/liquidation_handler.py:196,219` 는 0 이 아닌 `sell_price` 로 시장가 주문**을 내므로 그 경로만 `"00"` 오분류 — **두 EOD 경로의 price 관례가 다르다**(신규). 또 기동 시 전량 취소가 `"00"` 고정이라 **기동 차단 사유로 승격**(P2-20) |
| `_force_complete_failed_stocks` 실전에서 장부만 청산 | 🔴 **열림 + 새 경로** | `bot/liquidation_handler.py:450-462` 독스트링 자인 | **`_eod_retry_count` 리셋 호출자가 없어**(P2-25) 다음 날 첫 실패가 **곧바로** 이 경로로 간다 |
| 주문 정정 호출 주석처리(죽음) | 🔴 **열림 + 확대** | `core/orders/order_monitor.py:116-117` | **`framework/executor.py` 인스턴스화 0건**(P3-39) — 잘 구현된 정정·부분체결 추적 코드가 **한 줄도 안 돈다**. 감사 함정 |
| 체결 오탐지 복구 루프 원장 오염 가능(테스트 0) | 🔴 **열림 + 도달성 상향** | `order_monitor.py:183-223` · `:161-176` | **P1-5** 참조 — `status_unknown` 행에 `tot_ccld_qty` 가 없어 오탐 조건이 **항상 참** |
| `real_trading_records` tp/sl 컬럼 없음 → 손절선 재기동마다 리셋 | 🔴 **열림 + 악화 + 새 원인** | `db/repositories/trading.py:480-481,491-504` · `init-scripts/01-init.sql:96-110` | **7거래일 뒤 5%/5% 강제**(`bot/state_restorer.py:405-418`) + **`_real_buy_record_id` 대입 코드 0건**(flush 가 항상 no-op) = **한 결함의 상·하류**(P1-4) |
| 트레일링 최고가 · `daily_realized_loss` JSON write-only | 🔴 **열림** | `bot/initializer.py:805-808,840` · `bot/state_restorer.py:947-948` · `core/fund_manager.py:236` | 트레일링 최고가는 **3전략에 무영향**(ma20 trail 은 매번 재계산 `strategy.py:237-244` · minervini·daytrading 은 trail 없음). `daily_realized_loss` 는 **복원 독자 0** ⇒ 장중 재기동이 한도를 리셋(P2-18) |
| 텔레그램 `enabled=false` → 경보가 아무데도 안 감 | 🔴 **열림 + 악화 · 전환 최대 단일 위험** | `core/telegram_integration.py:56` · `api/kis_auth.py:600` | **인스턴스 파일을 `true` 로 해도 무효**(P1-1). 게다가 `notify_*` 는 `is_enabled=False` 면 **로그 한 줄 없이 return** — 경보 본문을 파일에 남기는 책임이 전적으로 호출자에게 있다(전수표는 축 4 발견 5) |
| `rebalancing_mode=true` 채로 실매매 | 🟡 **열림 · 표현 정정** | `instances/rs_leader/trading_config.json` `rebalancing_mode: true` | **분봉 전략이 없다**(8/8 daily). 실제 영향은 `get_cached_current_price()` **영구 None** → 손절·상한가 가드·EOD 매도가가 **API 단건 조회에 의존**. 축 6 은 「현행 `true` 유지가 안전」이라 결론(분봉 수집 부하만 늘고 얻는 것 없음) — §7 긴장 관계 |
| 페이퍼 체결=즉시 / 실전 매수=지정가 5분 / 실전 매도=시장가 | 🟢 **열림(설계) + 새 파생** | `core/orders/order_executor.py:150,158,341,417` · 타임아웃 `buy 300s` / `sell 180s` | **시장가 «매수» 경로는 존재하지 않는다**(매수는 항상 `"00"` 지정가). 새 파생 = **P2-19**(쿨다운 미무장 → 5분마다 재발주) |
| 수수료·세금 산식 두 벌 | 🟢 **정정: 산식은 한 벌** | `order_monitor.py:411-414` · `order_timeout.py:229-232` · `db/repositories/trading.py:164-167` | 갈라지는 건 **리포트 도구**(`tools/daily_trading_summary.py` gross)와 체결 방식. 별건으로 **실수수료를 읽는 코드가 없어** 실전 `profit_loss` 는 계좌 실현손익과 **반드시 어긋난다** |
| 현금 원장 이중화 = 결함 아님 | 🟢 **재확인(닫힘)** | `bot/state_restorer.py:293,312-360` | 변동 없음 |
| 급락게이트 65~68% 차단 — 실전에서도 같은 코드 | 🔴 **열림 · 「같은 코드, 다른 축」** | `main.py:543-547` · `core/trading_decision_engine.py:184-187`(KIS 실시간 지수 API) | 게이트는 `index_daily`·`INDEX_DAILY_SOURCE` 와 **무관**(09-10 지수 KIS 전환은 영향 0). **소액 검증 창이 차단창과 겹치면 주문이 안 나간다**(§7④) |
| `real_total_funds_cap` 키 없음 → 의도된 abort | 🟢 **가드 살아 있음** | `bot/initializer.py:711-720` · `instances/rs_leader/trading_config.json` 에 키 없음 | 단 `.example`·README 에 **키가 없다**(P3-41) ⇒ README 대로 따라 하면 **반드시 abort**, 그리고 그 abort 가 **아무에게도 안 간다** |
| D1 실전 총자금 min(cap, total_balance) + abort | ✅ **코드는 닫힘** | `bot/initializer.py:711-734` | **단 `total_balance` 의 의미가 틀렸다**(P1-3). 계약 테스트는 mock 이라 못 잡는다 |
| D2 실전 재기동 복원 + fail-closed 대사 | ✅ **닫힘** | `bot/state_restorer.py:1360-1405` | **평단 불일치는 검사하지 않는다**(수량만). 분할매수 유령 잔량이 abort 로 수렴(P2-28) |
| D3 EOD 실매도 반환값 검사 | 🟡 **부분 닫힘** | `bot/liquidation_handler.py:311-328,424-441` 은 검사 | **`:215-221` 은 반환값을 아예 안 받는다**(신규, §4-4) |
| D4 기동 시 미체결 전량 취소 | 🟢 **살아 있음** | `bot/state_restorer.py:1157,776-798` — 잔고 조회보다 **먼저** 실행 | **매도·수동주문까지 무차별 취소 + 실패 1건이 기동 차단**(P2-20). 휴장일 `TTTC8036R` 응답이 에러면 **기동이 통째로 막힌다**(§8) |
| `get_sellable_quantity` clamp | 🟢 **닫힘** | `core/orders/order_executor.py:394-411` | 변동 없음 |
| `fe02983` `max_per_stock_amount` 결선 | ⚠️ **페이퍼 한정** | `bot/initializer.py:457,484-485,500-510` | 실전 경로는 **미결선**(P2-12) |
| 포지션 사이징 먼지 거래(08-30 페이퍼 종결) | 🟢 페이퍼 종결 | `core/trading_decision_engine.py:427` | **실전은 다른 산식이라 재측정 필요** |
| 모의투자 TR 하드코딩으로 리허설 불가 | 🔴 **확정** | TR 38개 전부 실전 · `svr='demo'` 죽은 코드 | **코드로 확정**(P2-32) |
| `verify_fund_integrity` 가 계좌 괴리를 잡아주나 | ❌ **아니다** | `core/fund_manager.py:734-766` · `bot/system_monitor.py:786,794` | **내부 등식(total == avail+reserved+invested)만** 본다 |

---

## 6. 최소 수정 집합 (제안만)

> **원칙** — 페이퍼 8전략 동작 **0 변경** · 전략 룰 파일(`strategies/*/config.yaml`) **무수정**(6주 동결 준수) ·
> 분기는 전부 「실전/인스턴스 모드에서만」이라 **페이퍼 경로가 물리적으로 안 바뀐다**.
> **작업 장소** — 라이브 트리가 아니라 **별도 워크트리**에서. 리뷰 1회 후 머지(장 마감 후). 라이브 트리에서 테스트·브랜치 전환 금지.

### A. 코드 — **6곳 · 실질 8줄**

| # | 파일:줄 | 수정 | 닫히는 P1 | 줄 수 | **페이퍼 영향 0 인 이유** |
|---|---|---|---|---|---|
| A1 | `core/telegram_integration.py:56` | `Path("config/key.ini")` → `from config.settings import CONFIG_FILE` | **P1-1** | 1 | 페이퍼는 `_CONFIG_DIR == config/` 라 **같은 파일**을 연다 |
| A2 | `api/kis_auth.py:600` | 동일 | **P1-1** | 1 | 동상 |
| A3 | `bot/candidate_loader.py:103` | `self._bot.strategy.name` → `next(iter(self._bot.strategies.keys()), "unknown")` | **P1-2** | 1 | 페이퍼는 8전략 → `:71` 다중 분기라 **이 줄에 도달하지 않는다** |
| A4 | `api/kis_market_api.py:957-959` | update 에서 `'total_value'` 키를 빼고 **`'stock_eval_value'`** 를 새로 실어 `tot_evlu_amt` 를 보존 | **P1-3** | 2 | 페이퍼는 `bot/initializer.py:686-697` 가상 분기라 **이 함수를 안 부른다** |
| A5 | `api/kis_auth.py:326` | `_CB_BYPASS_TR_IDS` 에 **`"TTTC0011U"`(매도) 추가**. **매수 `TTTC0012U` 는 넣지 않는다** | **P1-8 절반** | 1 | 페이퍼는 주문 API 를 **호출하지 않는다** |
| A6 | `bot/system_monitor.py:255` 직후 | `from config.settings import INSTANCE_ID` + `if INSTANCE_ID != "default": return`(EOD 후속 블록 진입 전) | **P1-9**, P2-16 | 2 | 페이퍼는 `INSTANCE_ID == "default"` 라 **return 하지 않는다** |

> **A3 의 대안**(더 안전하나 회귀면적이 큼): `bot/candidate_loader.py:71` 을 `>= 1` 로 바꿔 1전략도 다중 경로를 태운다.
> `[E6]` 경보·base_filter·폴더키 owner 를 한꺼번에 얻고 페이퍼 동작도 불변이지만,
> **실전 후보 소스가 「거래량 순위」에서 「스크리너 스냅샷」으로 바뀌므로 동작 변경 = 사장님 결재 대상.**
> ⇒ 최소 집합에는 **A3(1줄)만** 넣고, 대안은 **별도 사전등록**으로 분리할 것을 권한다.

> **저비용 추가 후보 2줄**(최소 집합 «밖» · 비용 대비 효과 큼):
> - `core/trading/position_monitor.py:421` `debug` → `warning`(쓰로틀) — **P1-8 의 「30분 무음」을 없앤다.**
> - `bot/state_restorer.py:411` 의 stale 조건에 「DB 가 실제로 NULL 이었나」 플래그를 더해 실전에서만 5%/5% 조임을 막는다.
>   ⚠️ **의도된 안전장치를 끄는 것이라 결재 필요**(§7 C3 계열).

### B. 설정·파일 — **코드 0줄 · 5건**

| # | 조치 | 닫히는 발견 |
|---|---|---|
| B1 | `instances/<id>/trading_config.json` 을 **루트에서 새로 파생**(활성 전략 1개 + `paper_trading:false` + `real_total_funds_cap` 만 덮어씀). `rebalancing_mode` 는 **현행 `true` 유지**(축 6 결론 — §7 에 긴장 관계 기재) | P2-15, P3-41 |
| B2 | `run_instance.bat:63` `SCREENER_SNAPSHOT_ENABLED=true` → **`false`** + 「스냅샷 **소비 전용**」 로그 1줄(「off 와 미가동이 구별 안 된다」 보완) | P2-26 |
| B3 | `RoboTrader_template/.gitignore` 에 `instances/*` + `!instances/README.md` + `!instances/*/*.example` **3줄** | **P1-10** |
| B4 | `utils/korean_holidays.py:72` 의 `"2026-09-28"` 줄 삭제 + 계획서·MEMORY 의 「추석 9/24~28」을 **「9/24~27 휴장 · 9/28 은 거래일」**로 정정 | §4-1 모순 5 |
| B5 | 기동 전 `diff -u config/trading_config.json instances/<id>/trading_config.json` **1회**를 체크리스트에 명문화 | P2-15 |

### C. 최소 집합에 **넣지 않은** P1 과 그 이유

- **P1-5**(오탐 복구) · **P1-6**(`status_unknown`) · **P1-7**(매도 부분체결 분기) — 셋 다 **장부 정합 로직 변경**이라 1줄로 안 닫힌다.
  전환 전 필수는 아니지만, **소액 실탄 + 상한**으로 노출을 막고 **첫 주는 매일 계좌-DB 수동 대사**를 권한다.
- **P1-8 의 나머지 절반**(종목 CB 30분) — A5 로 「API CB 가 매도를 막는」 **입구**는 닫힌다.
  남은 위험은 **코드버그 즉시 활성화**(`position_monitor.py:595-601`)와 `:421` **debug 무음**이다(위 저비용 추가 후보 ①이 후자를 없앤다).
- **P1-4**(tp/sl 영속화) — 컬럼 추가(마이그레이션)까지 갈지, stale 분기를 실전에서만 좁힐지(1줄)가 **결재 사항**이라 §7 로 넘긴다.

### D. 선행 조건 (수정과 별개로 반드시)

1. **워크트리 신설 → 수정 → 리뷰 1회 → 머지**(장 마감 후 · 라이브 트리 테스트 금지 · 장중 브랜치 전환 금지).
2. **인스턴스 폴더 신설** — 현재 `instances/rs_leader/` **하나뿐**이고 **대상 전략 폴더가 없다.**
3. `real_total_funds_cap` **기입**(없으면 의도된 abort — 그리고 그 abort 는 A1·A2 전까지 아무에게도 안 간다).
4. 인스턴스 `trading_config.json` 을 **루트에서 재파생**(B1) + 기동 전 diff(B5).

---

## 7. 🔒 사장님이 정할 것 — 결정 후보

### ① 실전 전략 «2개» 를 무엇으로 할 것인가

**근거 숫자 (전부 실측)**

| 전략 | 페이퍼 equity 09-14 | 현금 | 보유 | 중앙 매수금 | W1 누적(기준 09-04) | P1 직격도 |
|---|---:|---:|---:|---:|---:|---|
| `book_pullback_ma20` | 7,943,183 | 207,413 | 5 | **1,557,475** | **+3.96%** | 스윙 ⇒ **P1-4(tp/sl 5%/5%) 직격** |
| `minervini_volume_dryup` | 10,310,766 | 1,059,306 | 3 | **2,999,040** | **+2.04%** | 스윙 ⇒ **P1-4 직격** · 🔴**9/22 TT 판정 전 「룰」 변경 금지** |
| `daytrading_3methods_breakout` | 9,410,209 | 258,739 | 5 | **1,908,400** | **−5.20%** | 급락게이트 **09-11·09-14 장의 65~68% 차단** · 인스턴스 config 의 `regime_index:"KOSDAQ"` **화석 위험**(P2-15) |

> 출처: `DB_facts.md`(`paper_strategy_equity` · `virtual_trading_records` is_test=true 2026-08-14 이후) · W1 수치는 관리자 제공.
> ⚠️ `daytrading` 의 `regime_index` 화석은 **현 인스턴스 파일에서 그 항목이 `enabled:false`** 라 **지금 당장 발효되지는 않는다**.
> 위험은 **그 파일을 템플릿으로 `instances/daytrading/` 을 만들 때**에 한정된다(검수 OVERSTATED 판정). ⇒ **B1(루트에서 재파생)로 닫힌다.**

| 옵션 | 장 | 단 |
|---|---|---|
| **(a) ma20 + minervini** | W1 양수 2개. 급락게이트 차단 이슈에서 상대적으로 자유. 둘 다 일봉 스윙이라 **운영 패턴이 동일**(관측 단순) | **둘 다 P1-4 직격**(재기동 1회면 손익비 8:10 → 5:5) ⇒ P1-4 를 **어떤 형태로든 처리해야 한다**. minervini 는 중앙 매수금이 300만이라 **§② 사이징 괴리가 가장 크다**(10M 기준 종목당 90만 = 페이퍼의 30.0%). 🔴 **9/22 TT 판정을 실전 표본이 흐릴 수 있다**(아래 주) |
| **(b) ma20 + daytrading** | ma20 은 W1 최고. daytrading 은 페이퍼 보유·매수 빈도가 높아 **실주문 경로를 빨리 검증**할 수 있다 | daytrading W1 **−5.20%** 로 실탄을 붙이기엔 이르다. **급락게이트 65~68% 차단**이 실전에도 그대로 돌아 **검증 창이 차단창과 겹치면 주문 자체가 안 나간다**. 인스턴스 config 화석 위험(B1 로 닫히나 절차 의존) |
| **(c) minervini + daytrading** | 두 축(매집/돌파)이 달라 분산 | ma20(W1 최고)을 뺀다. daytrading 의 단점 전부 + minervini 의 9/22 제약 전부. **권고하지 않음** |

**🔴 minervini 의 9/22 제약에 대한 정확한 판정**
- 「9/22 TT 판정 전 **minervini 라이브 «룰» 변경 금지**」는 유효하다. **실전 투입은 「룰 변경」이 아니다**(전략 파일·파라미터 무수정).
- **단**, 실전 인스턴스가 `strategies/minervini_volume_dryup/config.yaml` 을 **페이퍼와 공유**하므로(축 5 §3: 오버라이드 자리 없음),
  그 파일을 건드리는 순간 **페이퍼와 실전이 같은 순간 같이 바뀐다**. 9/22 까지는 어차피 못 건드린다 — **제약은 그대로 지켜진다.**
- ⚠️ **실전 첫 표본이 TT 판정을 흐릴 수 있다**: 실전은 사이징(9% 고정)·체결(지정가 5분)·tp/sl(P1-4)이 페이퍼와 달라
  **같은 전략의 「다른 실행」**이다. 9/22 판정을 **페이퍼 표본으로만** 하기로 사전에 못박지 않으면 혼입 위험이 있다.

**관리자 권고 — (a) ma20 + minervini.** 단 **조건부**:
1. **P1-4 처리 방향을 먼저 정한다**(§C3). 스윙 2전략을 고르면 P1-4 는 **선택이 아니라 전제**다.
2. 9/22 minervini TT 판정은 **페이퍼 표본으로만 한다**고 문서에 못박는다.
3. daytrading 은 **관측 유지** — W1 −5.20% 와 급락게이트 65~68% 차단이 동시에 해소되는 것을 보고 재검토.

---

### ② `real_total_funds_cap` 을 얼마로 할 것인가

**실전 사이징의 실제 산식(확인)** — 종목당 = `total_funds × 0.09`(`core/fund_manager.py:212`), 총투자 상한 = `total_funds × 0.90`(`:213`).
**둘 다 하드코딩이고, 전략 K·yaml `max_per_stock_amount`·인스턴스 `max_position_ratio` 는 전부 미반영이다**(P2-12).
⇒ 실효 동시보유 한도 = `0.90 / 0.09 = **10종목**`.

| cap | 종목당 금액 | vs ma20 중앙 1,557,475 | vs minervini 중앙 2,999,040 | vs daytrading 중앙 1,908,400 | 총투자 상한(90%) |
|---:|---:|---:|---:|---:|---:|
| **5,000,000** | **450,000** | 28.9% | 15.0% | 23.6% | 4,500,000 |
| **10,000,000** | **900,000** | **57.8%** | **30.0%** | **47.2%** | 9,000,000 |
| **20,000,000** | **1,800,000** | 115.6% | 60.0% | 94.3% | 18,000,000 |

**「90만으로 못 사는 고가주」 문제** — 종목당 금액이 주가보다 작으면 **수량 0 → 매수 포기**다.
`qty = int(max_amt / price)`(`core/trading_decision_engine.py:427`)이므로 **주가 > 900,000 인 종목은 cap 10M 에서 구조적으로 못 산다**.
실제로는 훨씬 먼저 문제가 된다 — 주가 30만원이면 **3주**, 45만원이면 **2주**, 90만원이면 **1주**로 **수량 이산화 오차**가 커지고,
페이퍼가 156만~300만으로 잡던 포지션이 실전에서 **다른 종목 구성**이 된다(비싼 종목이 조용히 빠진다).
⇒ **A/B 비교가 이 축에서도 한 번 더 깨진다.** (페이퍼 중앙 매수금 기준으로 역산하면 「페이퍼와 같은 종목당 금액」을 내려면
ma20 은 cap 약 1,730만, minervini 는 약 3,330만, daytrading 은 약 2,120만이 필요하다 — **총액이 페이퍼의 2~3배가 된다.**)

| 옵션 | 장 | 단 |
|---|---|---|
| **5M** | 최소 노출. P1-5/6/7(미수정 잔여)의 실탄 피해를 최소화 | 종목당 45만 ⇒ **10만원대 이상 종목에서 수량 이산화가 심각**. 페이퍼 대비 15~29% 라 **성과 비교 의미가 거의 없다** |
| **10M (권고)** | **페이퍼 전략 자본(전략당 1천만 격리 원장)과 총액이 같다** ⇒ 「같은 총액, 다른 사이징」으로 차이의 원인을 **사이징 축 하나로 좁힐 수 있다** | 종목당은 페이퍼의 **47~58%**(ma20 57.8% · daytrading 47.2%)이고 **minervini 는 30.0%** 로 더 벌어진다. 종목 수는 최대 10 vs 페이퍼 3~5 |
| **20M** | 종목당 180만으로 페이퍼(ma20 116% · daytrading 94%)에 가장 근접 | **노출 2배.** 미수정 P1 3건(장부 파괴 계열)이 살아 있는 상태에서 첫 전환에 쓸 금액이 아니다 |

**관리자 권고 — 10,000,000.**
근거: 페이퍼 전략 자본과 **총액이 같아** 비교 축이 하나로 줄고, 종목당은 페이퍼의 **45~58%**(minervini 만 30%)로 **보수적 방향**이다.
🔑 **cap 을 낮추는 것이 「소액화」의 유일한 수단**이다 — 「1주만」을 강제하는 스위치가 **코드에 없다**(cap 1,000,000 → 종목당 90,000).

---

### ③ 텔레그램을 어떻게 할 것인가

| 옵션 | 내용 | 장 | 단 | 비용 |
|---|---|---|---|---|
| **(a) 코드 2줄로 인스턴스 `key.ini` 채택 — 권고** | A1·A2 (`Path("config/key.ini")` → `CONFIG_FILE`) | **인스턴스가 이미 `enabled=true`** 이고 토큰·chat_id 가 들어 있다 ⇒ **고치는 즉시 경보가 살아난다.** 페이퍼는 같은 파일을 열어 **영향 0**. 봇 토큰이 서로 달라 **발신자로 구분 가능** | 두 봇의 chat_id 가 **동일**해 같은 방으로 온다(메시지 본문에 인스턴스 표기 없음 — 접두 1줄 추가 권장) | **2줄** |
| (b) 루트 `config/key.ini` 를 켠다 | `enabled=true` 로 변경 | 코드 0줄 | **페이퍼 알림이 혼입**된다(페이퍼 8전략 체결 알림이 전부 날아온다). 인스턴스 라벨이 없어 **어느 봇의 경보인지 구분 불가** — 「경보 피로」로 진짜 CRITICAL 이 묻힌다 | 0줄 |
| (c) 미채택 유지 + abort 파일 폴백 **필수** | 텔레그램 없이 가되, `logs/<id>/ABORT_<date>.txt` 같은 파일 플래그를 신설 | 텔레그램 의존 없음 | **P1 10건 중 최소 6건이 무음으로 일어난다.** 사람이 알 수 있는 최소 경로는 ①`logs/<id>/trading_YYYYMMDD.log` ②콘솔 캡처 로그(**블록 버퍼링이라 도는 중엔 0바이트로 보인다**) ③`pause` 로 남은 콘솔 창 ④DB 표(경보가 아니라 결과) — **푸시·메일·HTTP 헬스체크 어느 것도 없다.** 그리고 **P1-8 의 30분 봉쇄는 `debug` 라 ① 에도 안 남는다** | 파일 폴백 신설분 |

**관리자 권고 — (a).** 이유: **다른 모든 조치의 전제조건**이다. 검수가 전 축 통틀어 1순위로 올린 유일한 항목이고,
「경보가 켜져 있다」는 **오신뢰가 이미 파일로 성립**해 있어 **안 켠 것보다 나쁜 상태**다.
겸해서 `notify_*` 의 `if not self.is_enabled: return` 앞에 `logger.warning(f"[경보-미발송] {message}")` 1줄 × 9곳을 두면
**앞으로 어떤 이유로 꺼져 있어도 경보 본문이 파일에 남는다**(선택 · 최소 집합 밖).

---

### ④ 전환 창을 언제로 할 것인가

**🔴 먼저 — 휴장 창 정정**: 추석 휴장은 **2026-09-24(목) ~ 09-27(일)** 이고 **09-28(월)은 정상 거래일**이다(§4-1 모순 5).
「9/24~28 5일 창」이라는 기존 전제는 **틀렸다.**

**휴장 4일(9/24~27)에 «실제로» 검증되는 것 — 주문 코드는 0줄 실행된다**
`is_market_open()` **3중 게이트**가 주문을 원천 차단한다:
① `main.py:433` 루프 자체가 30초 sleep 으로 돈다 · ② 각 전략 `_check_buy` 첫 줄이 `MarketHours.is_market_open("KRX")` · ③ `core/orders/order_executor.py:87` `can_place_order()` 첫 줄이 또 `is_market_open()`.
⇒ **「거부 응답을 어떻게 처리하나」조차 확인할 수 없다** — 거부를 받으려면 주문을 내야 하는데 안 낸다.

| 휴장 창에서 검증 **가능** | 휴장 창에서 검증 **불가** |
|---|---|
| KIS 인증·토큰 발급(인스턴스 분리 `token_info_<id>.json`) | 주문 접수 · 부분체결 · 5분 타임아웃 취소 · `_cancel_with_retry` |
| D1 실전 총자금 + `real_total_funds_cap` **의도된 abort** | 체결 콜백 · `real_trading_<id>` 매매행 기록 |
| D2 `get_holdings()` 복원·교차검증·fail-closed 대사 | `FundManager` 예약 → 확정 전이 |
| **D4 기동 시 미체결 조회·전량 취소** ← 🔑 **유일하게 «새로운» 정보** | VI arm(매수 직전에만 호출) |
| `real_trading_<id>` 표 생성 · 로그·PID 분리 | **P1-2(후보 owner)의 실제 발현** — 후보 로드는 되나 매수 신호 관측 불가 |
| 텔레그램 경보 경로(A1·A2 적용 후) | P1-3(2일차 예수금 소멸 — 보유가 있어야 발현) |

🔑 **D4 에 함정이 있다**: `bot/state_restorer.py:781` 은 `get_pending_orders()` 가 None 이면 **`LiveStartupAbort("미체결 주문 조회 실패")`** 를 던지고,
`framework/broker.py:813-815` 는 KIS `TTTC8036R` 이 `isOK()` 아니면 None 을 돌린다.
⇒ **휴장일에 이 TR 이 에러를 주면 실전 기동이 통째로 막힌다.** 9/24 전에 **읽기 전용 1회 조회**로 먼저 확인하는 것이 가장 싸다.

| 옵션 | 내용 | 장 | 단 |
|---|---|---|---|
| **(a) 9/24 기동 리허설 → 9/28(월) 소액 1종목** | 휴장 창엔 기동·복원·abort·D4 만, 주문은 첫 거래일에 | 창을 낭비하지 않는다. 실패해도 휴장일이라 **되돌릴 시간이 3일 있다** | **9/28 은 장중**이라 「휴장일 작업」 규칙이 적용되지 않는다. 그날 최소 수정이 **이미 머지돼 있어야** 한다(장중 브랜치 전환 금지) ⇒ **9/23(수) 장 마감까지 머지 완료**가 전제 |
| **(b) 최소 수정 머지 후 10/3~5 창** | 10/3(토)·10/5(월, 개천절 대체) 휴장 활용 | 준비 기간이 2주 이상 — P1-4 처리·워크트리 리뷰·인스턴스 폴더 신설을 여유 있게 | 실전 전환이 **약 3주 늦어진다**. 그 사이 P1 은 그대로 열려 있다(단 실탄이 없으니 손실도 없다) |
| (c) 연기 | 최소 수정 + P1-4 + 장부 정합 3건(P1-5/6/7)까지 처리 후 재검토 | 가장 안전 | 「언제 하는가」가 미정으로 남는다 |

**선행 조건(옵션 무관 · 전부 필수)**
1. **워크트리에서 A1~A6 수정 → 리뷰 1회 → 머지**(장 마감 후).
2. **인스턴스 폴더 신설** — 현재 `instances/rs_leader/` **하나뿐**이고 **대상 전략 폴더가 없다.**
3. `real_total_funds_cap` 기입(§②).
4. 인스턴스 `trading_config.json` 을 **루트에서 재파생**(B1) + 기동 전 `diff` 1회(B5).
5. `.gitignore` 3줄(B3) — **인스턴스 폴더를 만들기 «전»에**.
6. 소액 실주문 검증은 **코드 변경 없이 설정만으로** 할 것(장중 브랜치 전환 금지).
7. 검증 시각을 **급락게이트 허용창**에 맞출 것 — 09-11·09-14 에 장의 65~68% 가 차단창이었다.

**관리자 권고 — (a) 조건부.** 9/23(수) 장 마감까지 A1~A6 + B1~B5 가 머지돼 있으면 (a),
그 일정이 빠듯하면 **무리하지 말고 (b)**. 「최소 수정이 안 들어간 채 9/28 에 실탄을 넣는 것」은 **선택지가 아니다**(P1-2 때문에 매수 0건이거나, P1-1 때문에 무음이거나 둘 중 하나다).

---

## 8. 미확정 질문 (검수 Open Questions)

> 「코드만으로는 못 정한 것」 전수. **무엇으로 확정하는가**를 함께 적는다.

| # | 질문 | 왜 중요한가 | 무엇으로 확정하나 |
|---|---|---|---|
| 1 | **`tot_evlu_amt` 의 KIS 의미** — 「예수금 + 주식평가」가 맞나 | **P1-3 의 유일한 추정 축.** 여기서 확인한 것은 「코드가 그 값을 덮어쓴다」까지다 | KIS TR 문서 확인 + **실계좌 1회 조회**(읽기 전용). 또는 `tests/healthcheck/run_healthcheck.py:158` 출력과 HTS 총평가금액 대조 |
| 2 | **`TTTC0081R` output1 의 `avg_prvs` 채움 규칙** | **P2-14 의 진입 조건.** 「전량 체결」을 보고한 행이 평균가를 비워 보내는가 | **실계좌 1건 조회**로 판정 가능 |
| 3 | **휴장일 `TTTC8036R`(미체결 조회) 응답** | 에러면 `bot/state_restorer.py:781` 이 **실전 기동을 통째로 막는다**(§7④) | **9/24 «전»에 읽기 전용 1회 조회** |
| 4 | **P1-8 의 실제 발생 빈도** — 「3회 `_execute_sell` 이 24초 안에 실제로 도는가」 | 산수는 교정했으나 상태 전이(`_restore_to_positioned` → POSITIONED → 재진입)는 런타임을 봐야 안다 | 실전 기동 후 모니터 루프 로그(LOG_LEVEL DEBUG 사본) |
| 5 | **P1-2 의 실측 확인** — 「후보 등록 N건 뒤 매수 시그널 0줄」 | 코드·독스트링 2건으로 **확정**했지만 실측 로그로 한 번 더 못박을 것 | 라이브 트리 **밖 사본**에서 드라이런, 또는 실전 첫날 로그 grep |
| 6 | **증권거래세율**(P3-37) | 코드로 판정 불가. 바꾸면 **페이퍼 과거 손익이 전부 흔들린다** | 세법 확인 → `paper_strategy_equity` 재계산 범위를 **먼저** 정할 것 |
| 7 | **DB 재현 3건** — `real_trading_rs_leader` 0행 · `real_trading_records` 224행(오염 11행) · 페이퍼 tp/sl NULL 0/865 | 검수는 **DB 를 조회하지 않았다**(축 3 의 값을 그대로 두었다) | `psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template` SELECT 재확인 |
| 8 | **P2-24 의 동시쓰기 truncate 실현 여부** | 2026-09-08 ARCHIVE_INDEX 0바이트 사고와 **같은 결함 클래스** | 캐시를 빈 파일로 만든 **사본 트리**에서 `_runtime_closed` 가 `set()` 인지 확인. **라이브 트리에서 하지 말 것** |
| 9 | **수능일 09:00~10:00 에 KIS 가 주문을 «접수» 하는가** | 게이트가 열린다는 것만 확인했다(P2-23) | 11월 전 TR 문서 확인 또는 그 날 읽기 전용 관측 |

---

## 9. 출처 · 산출물

### 9-1. scratchpad 산출물 (`RoboTrader_template/scratchpad/real_trading_audit_20260914/`)

| 파일 | 내용 |
|---|---|
| `BRIEF.md` | 공통 브리프 — 절대 규칙 · 실매매 운영 모델(1인스턴스=1계좌=1전략) · 「이미 알려진 것」(고쳐진 것 / 아직 열린 것) · 산출 형식 |
| `axis1_order_path.md` | **축 ① 주문 경로** — 플래그 전수표(S1~S7 / R1~R21 / U1~U6) · 발견 12건 · 실주문 경로 최종 결선도 · 체결 후 순서와 예외 격리표 |
| `axis2_funds_sizing.md` | **축 ② 자금·사이징** — 실전 자금 사슬 요약 · 발견 10건 · 페이퍼 vs 실전 함수 단위 대조표 · 「매도 대금 당일 재사용」 SQL 실측 3본 |
| `axis3_state_restore.md` | **축 ③ 상태 복원·중복·원장 분리** — 발견 10건 · 「누가 쓰고 누가 읽나」 표 · 대사 규칙 요약 · 재기동 후 3전략 청산 룰 판정 |
| `axis4_guards_alerts.md` | **축 ④ 가드·경보** — 가드 사슬 14단계 표 · 발견 11건 · 경보 전달 경로 전수표 · rate limit 상수 계산 |
| `axis5_config_secrets.md` | **축 ⑤ 설정·비밀·엔드포인트** — 설정 해석 순서 10단계 · 발견 11건 · 새 인스턴스 체크리스트(🟥 6 / 🟨 10) · 기동 스크립트 비교 · 드리프트 위험 종합 |
| `axis6_time_calendar.md` | **축 ⑥ 시간·달력** — 발견 9건 · 장중 시간 구간별 실전 주문 동작 표 · 09:00 후보 로드 타임라인 · 휴장일 검증 범위 |
| **`CRITIC_verify.md`** | **검수(척추)** — P1 24건 전수 반증 · 축 간 모순 8건 · 병합 M1~M8 · 통합 재조정(P1 10 / P2 22 / P3 9) · 최소 수정 집합 · 「이 검수가 못 한 것」 |
| `DB_facts.md` | DB 실측 — `paper_strategy_equity` 3전략(09-11·09-14) · `virtual_trading_records` 매수 건수·평균/중앙 매수금 |

### 9-2. 이 문서가 쓴 DB SQL (SELECT only · `kis_template` · port 5433)

```sql
-- 페이퍼 3전략 equity (§7 ①)
select strategy, trade_date, cash, position_value, equity, n_open
  from paper_strategy_equity
 where strategy in ('book_pullback_ma20','minervini_volume_dryup','daytrading_3methods_breakout')
   and trade_date >= '2026-09-11' order by 1,2;

-- 페이퍼 3전략 매수금 분포 (§7 ②)
select strategy,
       count(*) filter (where action='BUY')  as buys,
       count(*) filter (where action='SELL') as sells,
       round(avg(quantity*price) filter (where action='BUY'))                                  as avg_notional,
       round(percentile_cont(0.5) within group (order by quantity*price)
             filter (where action='BUY'))                                                      as median_notional
  from virtual_trading_records
 where is_test=true
   and strategy in ('book_pullback_ma20','minervini_volume_dryup','daytrading_3methods_breakout')
   and timestamp >= '2026-08-14'
 group by 1;

-- 페이퍼 tp/sl NULL 판정 (P1-4 · 검수 §6 재현 권장)
select count(*) as total,
       count(*) filter (where target_profit_rate is null) as tp_null,
       count(*) filter (where stop_loss_rate     is null) as sl_null,
       count(*) filter (where target_profit_rate = 0.15
                          and stop_loss_rate     = 0.10)  as exactly_default
  from virtual_trading_records where action='BUY';

-- 실원장 현황 (P3-40 · 검수 §6 미재현분)
select 'real_trading_records' t, count(*) from real_trading_records
union all
select 'real_trading_rs_leader', count(*) from real_trading_rs_leader;
```

### 9-3. 이 문서를 쓸 때 지킨 규칙

- 라이브 트리에서 **코드 수정 0 · pytest 0 · git 편집 0**. 유일한 산출물은 이 문서다.
- 모든 숫자는 **출처(파일:줄 / SQL / 축-번호)** 를 달았다. 출처 없는 숫자는 쓰지 않았다.
- 「확인」과 「추정」을 구분했다. 추정은 본문에 **(추정)** 또는 「~는 추정」으로 명시했다.
- 「수정안」은 전부 **제안**이다. 실행·승인이 아니다.
- 검수가 강등·반박한 건은 원래 등급을 **취소선**(`~~P1~~ → P2`)으로 남겨 흔적을 유지했다.

*(감사 종료. 라이브 트리 코드 변경 0줄 · 페이퍼 8전략 무영향.)*
