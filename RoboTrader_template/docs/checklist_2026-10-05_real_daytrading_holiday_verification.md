# 10-05(월 · 개천절 대체공휴일) 실전 daytrading 인스턴스 휴장일 검증 체크리스트

> **성격**: 사장님·관리자가 10-05 에 **순서대로** 할 일. 각 항목에 «성공 판정 줄/값» 과 «실패 시 중단 기준» 을 붙였다.
> **근거**: 워크트리 `D:/tmp/kis-wt-real-daytrading`(브랜치 `feat/real-daytrading-setup`, base `43d3450`)의 코드 파일:줄. 실행 0회·KIS 호출 0회로 쓴 문서다 — 로그 문구는 코드에서 옮겼고, 실제 출력과 글자가 조금 다를 수 있다.
> **계좌번호·앱키·시크릿·HTS ID 는 이 문서에 적지 않는다.** 아래 확인 명령도 값을 출력하지 않고 참/거짓만 찍는다.
> **실행 위치**: 기동은 **라이브 트리** `D:/GIT/kis-trading-template/RoboTrader_template` 에서만 한다(워크트리엔 venv 가 없다). 라이브 트리는 `main` 그대로 — 브랜치 전환 금지.
> **개정 2026-10-02(밤)**: B-1·B-2 수정(사장님 결정 · 사전등록 `docs/prereg_2026-10-02_real_daytrading_b1_b2_fix.md` · 브랜치 `fix/real-daytrading-b1-b2` `09c95c3` · 리뷰 반영 `581cff2`)에 맞춰 §0·§1·§4·§5·§6·§10 을 고쳤다. ⚠️ 아래 «수정 후» 문구는 **그 브랜치가 main 에 머지돼 라이브 트리가 재기동된 뒤**에만 맞다 — 기동 전 §1-10 으로 머지 여부부터 확인.
> **개정 2026-10-04**: 실매매 과정 코드 점검(`docs/audit_2026-10-04_real_daytrading_flow.md`)에서 확인된 결함 중 **NEW-B1**(취소가 성공해도 `cancel_order` 가 «실패»를 돌려준다)과 **NEW-C1**(텔레그램이 켜진 인스턴스는 Ctrl+C 뒤 종료 처리까지 가지 못한다)이 이 체크리스트의 기대값을 바꾼다. 🔒 사장님 결정(10-04): **10-05·10-06 시험은 지금 코드로 하고, 아래 «미수정 기대값»으로 판정한다**(버그가 실제로 재현되는지 확인). 6건 수정은 10-07 부터 진행하고, 반영 뒤 10-19 전에 장전 접수·취소 시험(§4-B)을 한 번 더 한다. 고친 곳 = §1-6 · §4-A·B · §4 결정 · §5-5 · §5 «멈출 줄» 표 · §7-1.

---

## 0. 먼저 읽을 것 — 휴장일에 «되는 것» 과 «안 되는 것»

10-05 는 봇이 휴장일로 판정한다(오프라인 실측: `holidays` 0.83 `KR(2026)` 에 `2026-10-05 = 개천절 대체 공휴일` · `MarketHours.get_market_status` = `holiday` · `is_market_open` = False).
그러면 **주문 코드는 한 줄도 실행되지 않는다** — 세 겹으로 막힌다:

1. `main.py:433-435` — `is_market_open()` 이 False 면 메인 루프가 30초 sleep 만 반복(후보 로드·on_tick·주문 확인 전부 안 돎)
2. `strategies/daytrading_3methods_breakout/strategy.py:260` — `_check_buy` 첫 줄이 `MarketHours.is_market_open("KRX")`
3. `core/orders/order_executor.py:87` · `:321` — 주문 직전 `MarketHours.can_place_order()`(첫 줄이 `is_market_open`)

| 10-05 에 **검증 가능** (기동 경로 · 읽기 TR 만) | 10-05 에 **검증 불가** (첫 거래일 이후 또는 §4 대안) |
|---|---|
| 5중 분리(설정 디렉토리·PID·토큰·로그·원장 표 이름) | 주문 접수 · 거부 응답 처리(주문을 «안 낸다») |
| KIS 인증·토큰 발급(실전 도메인 · 새 앱키) | 체결 · 부분체결 · 5분 타임아웃 취소 · 정정(정정은 코드상 꺼져 있음) |
| `real_total_funds_cap` 미설정 → `LiveStartupAbort` → 텔레그램 경보 | 체결조회 응답 필드(`avg_prvs`·`tot_ccld_qty`) 파싱 |
| 실계좌 총평가 조회 = `min(cap, 총평가)` 값 (HTS 와 대조) | OrderManager 첫 가동(미체결 감시·오탐 복구·타임아웃) |
| **휴장일 미체결 조회 TR(`TTTC8036R`) 응답** ← 유일하게 새로운 정보 | `real_trading_daytrading` 매수·매도 행 기록 |
| 계좌-DB 대사(보유 0 = DB 0) · `real_trading_daytrading` 표 생성 | 전략 체결 콜백(일일 캡 카운트) · 손절·익절 감시 |
| 설정 대조 줄 `[게이트설정대조]` · 전략 1개 로드 | 09:00 후보 로드 = `[B1-실전]` 스냅샷 경로(B-1 수정 · 첫 거래일 09:00 에 §5-1 로 확인) |
| 텔레그램 시작·경보 수신 · 휴장일 KIS 동기화 · 종료 경로 | 실계좌 대조(I5) — 보유가 생겨야 의미 있음 |

> 🟢 **B-1·B-2 = 10-19 전 수정**(사장님 10-02 밤 결정 · 사전등록 `docs/prereg_2026-10-02_real_daytrading_b1_b2_fix.md` · 수정 전 상세 = `SETUP_REPORT.md` §5·§8). 10-05 검증과는 독립이고 휴장일엔 보이지 않는다(첫 거래일 §5 에서 확인).
> **B-1(수정 후)** 실전 인스턴스(`INSTANCE_ID != "default"`)는 전략 수와 무관하게 **페이퍼가 09:00 직후 쓰는 D-1 스냅샷**(`screener_snapshots`)을 페이퍼와 같은 함수로 읽는다(1~20위 → 안전필터 → 목표 10 · 섹터뉴스 재정렬만 생략). 아직 없으면 **10초 간격 재확인 · 상한 15분**(메인 루프·보유 감시는 계속), 그래도 0건이면 그날 신규 후보 0 + ERROR `[B1-실전]` + 텔레그램 경보 — **거래량 순위·JSON 폴백은 없다**. (수정 전: 1전략 경로가 `data/screener_*.json` 을 못 찾고 09:00 거래량 순위 폴백으로 샀다.)
> **B-2(수정 후)** 실전 매수 주문 직전과 아침 복원 때 소유 전략 `config.yaml` 의 tp/sl(daytrading **+10%/−10%**)을 넣는다 ⇒ 7거래일+ ±5% 조임도 안 걸린다. (수정 전: `TradingStock` 기본값 +15%/−10% · 재기동 뒤 7거래일+ ±5%.)

---

## 1. 기동 전 확인 (10-05 오전 · 사장님 + 관리자)

| # | 할 일 | 확인 방법 | 성공 판정 | 실패 시 |
|---|---|---|---|---|
| 1-1 | 라이브 트리 상태 | `git -C D:/GIT/kis-trading-template status --short --branch` | `## main` · 추적 파일 변경 0(미추적만) | 추적 파일이 바뀌어 있으면 **중단**·원인 확인 |
| 1-2 | `trading_config.json` 배치 | 워크트리 실사용본 `D:/tmp/kis-wt-real-daytrading/RoboTrader_template/instances/daytrading/trading_config.json` 을 라이브 트리 `instances/daytrading/` 로 **복사**(gitignore 파일이라 git 무관) | 파일 존재 | — |
| 1-3 | 페이퍼 설정과 차이 확인(감사 B5) | 라이브 트리에서 `diff -u config/trading_config.json instances/daytrading/trading_config.json` | 차이 = ① 7전략 `"enabled": true → false` 7줄 ② `"paper_trading": true → false` ③ `"rebalancing_mode": true` 줄 끝 쉼표(값 불변) ④ `"real_total_funds_cap": null` 1줄 추가 — **이것뿐**(daytrading 항목은 불변) | 다른 줄이 보이면 **중단**(루트가 바뀌었으면 워크트리에서 재파생) |
| 1-4 | `key.ini` 형식(값 미출력) | 아래 §1-A 명령 | `sections ['KIS','ANTHROPIC','TELEGRAM']` · 계좌 10자리 숫자(하이픈 없음) True · 실전 도메인 True · 텔레그램 enabled true | 하나라도 False → **중단**(하이픈 입력 시 인증은 되고 주문·잔고만 실패 — 감사 P3-33) |
| 1-5 | 🔴 앱키·계좌가 **다른 가동 봇과 겹치지 않는지** | §1-B 명령(SAME/DIFFERENT 만 출력) — 대상: 페이퍼 `config/key.ini` · 매일 07:40 같이 뜨는 `D:/GIT/RoboTrader_quant_mom/config/key.ini` | 전부 `APP_KEY DIFFERENT` · `ACCOUNT DIFFERENT` | **계좌 SAME = 즉시 중단**(다른 봇이 같은 계좌를 매매하면 아침 대사가 매일 abort 하거나 남의 포지션을 판다) · 앱키 SAME = 중단(전역 락이 프로세스 안에만 있어 두 봇 합산 20건/초 초과 위험 — `api/kis_auth.py:50`) |
| 1-6 | 🔴 실계좌 현황(HTS) | HTS 에서 예수금·총평가·보유 종목·미체결·예약주문 확인 | **보유 0 종목** · 미체결 0 | 보유가 있으면 → DB 원장(`real_trading_daytrading`)엔 0 이라 **계좌-DB 불일치 → `LiveStartupAbort`**(설계상 fail-closed, `bot/state_restorer.py:1197-1205`). 처리 방침(정리 매도 or 원장 수기 입력)을 사장님이 먼저 정할 것. 미체결이 있으면 기동이 **전량 취소**한다(`:776-800`, 감사 P2-20). ⚠️ (10-04) NEW-B1 미수정 동안은 취소가 실제로 성공해도 `cancel_order` 가 실패를 돌려줘 `🚨 실전 기동 중단: 미체결 취소 실패: <종목> 주문 <번호>` 로 **멈춘다**(`bot/state_restorer.py:787-794` · 점검 N-1) — 그때는 HTS 에서 미체결 0 을 확인한 뒤 다시 기동하면 통과한다 |
| 1-7 | PID 파일 | 라이브 트리에 `robotrader_daytrading.pid` 가 있는지 | 없음(또는 죽은 PID) | 살아 있는 `python main.py` PID 를 가리키면 기동이 «이미 실행 중» 으로 exit(1) — 그 프로세스를 먼저 확인 |
| 1-8 | DB | `kis_template`(5433) 접속 · `select to_regclass('real_trading_daytrading');` | `NULL`(아직 없음 — 첫 기동이 만든다) | 접속 불가면 중단 |
| 1-9 | 텔레그램 혼입 | 페이퍼 `config/key.ini` `[TELEGRAM] enabled` | `false`(현재 값) ⇒ 받는 메시지는 전부 실전 인스턴스 것 | 페이퍼가 true 면 메시지에 인스턴스 표기가 없어 구분 불가 |
| 1-10 | B-1·B-2 수정이 라이브 트리에 들어왔는가 | `git -C D:/GIT/kis-trading-template log --oneline -1 --grep="B-1" -- RoboTrader_template/bot/candidate_loader.py` · `grep -c "_load_candidates_real_instance" D:/GIT/kis-trading-template/RoboTrader_template/bot/candidate_loader.py` | 커밋 1줄 · 카운트 ≥ 1 | 0 이면 **수정 전 코드** — §5 의 «수정 후» 줄 대신 거래량 순위 폴백이 돈다. 10-19 전이면 머지 요청, 머지 전 실매매 가동 금지 |
| 1-11 | 🟡 인스턴스 텔레그램 경보 경로(리뷰 🟡2) | §1-A 명령의 `telegram enabled` · `telegram token set` · `telegram chat_id set` 3줄(값 미출력) | `true` · True · True | 하나라도 아니면 **중단** — B-1 fail-closed 경보(`후보로드[실전]`)·기동 중단 경보가 무음이 된다(`core/telegram_integration.py:69-88` `_is_config_valid` = enabled·token·chat_id 셋 다 필요) |
| 1-12 | 후보 목표 건수 대조(리뷰 ⚪6) | §1-C 명령 | 두 파일 모두 `max_candidates = 10` | 다르면 **중단** — 인스턴스가 스냅샷에서 페이퍼와 다른 건수를 고른다(`bot/candidate_loader.py` 가 `strategy.parameters.max_candidates` 를 목표로 쓴다) |

### 1-A. `key.ini` 형식 확인 (값을 출력하지 않는다)

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
venv/Scripts/python.exe - <<'EOF'
import configparser, re
c = configparser.ConfigParser(); c.read('instances/daytrading/key.ini', encoding='utf-8')
v = lambda n: c['KIS'].get(n, '').strip('"')
print("sections:", c.sections())
print("ACCOUNT 10 digits, no hyphen:", bool(re.fullmatch(r'\d{10}', v('KIS_ACCOUNT_NO'))))
print("APP_KEY/SECRET/HTS_ID set:", all(v(n) for n in ('KIS_APP_KEY', 'KIS_APP_SECRET', 'KIS_HTS_ID')))
print("real domain:", v('KIS_BASE_URL') == 'https://openapi.koreainvestment.com:9443')
print("telegram enabled:", c['TELEGRAM'].get('enabled'))
t = lambda n: c['TELEGRAM'].get(n, '').strip()
print("telegram token set:", bool(t('token')) and 'YOUR_' not in t('token'))
print("telegram chat_id set:", bool(t('chat_id')) and 'YOUR_' not in t('chat_id'))
EOF
```

> 관리자 사전 확인(10-02, 같은 명령의 앞 5줄): 전 항목 True · `enabled=true`. 10-05 에 한 번 더(파일이 바뀌지 않았는지) — `token set`·`chat_id set` 2줄은 10-02 개정에서 추가(1-11).

### 1-B. 앱키·계좌 겹침 확인 (SAME/DIFFERENT 만 출력)

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
venv/Scripts/python.exe - <<'EOF'
import configparser
def kis(p):
    c = configparser.ConfigParser(); c.read(p, encoding='utf-8')
    k = c['KIS']; return k.get('KIS_APP_KEY', '').strip('"'), k.get('KIS_ACCOUNT_NO', '').strip('"')
me = kis('instances/daytrading/key.ini')
for other in ['config/key.ini', 'D:/GIT/RoboTrader_quant_mom/config/key.ini']:
    o = kis(other)
    print(other, "| APP_KEY", "SAME" if o[0] == me[0] else "DIFFERENT", "| ACCOUNT", "SAME" if o[1] == me[1] else "DIFFERENT")
EOF
```

> ⚠️ 이 확인은 관리자 직원(이 문서 작성자)이 **하지 않았다** — 지시 범위(존재·섹션·파싱 여부만)를 지켰다. 09-30 메모에는 「원본 앱키는 RoboTrader_quant(가동 중단) 것」이라 적혀 있으나, **매일 07:40 에 뜨는 `RoboTrader_quant_mom` 이 어떤 키·계좌를 쓰는지는 확인된 적이 없다**(10-02 프로세스 목록: 07:40:03~04 에 template 외 `main.py` 프로세스가 함께 떠 있음 — `D:\GIT\run_all_robotraders.bat` 가 quant_mom·NewsQuant 를 같이 띄운다).

### 1-C. 후보 목표 건수 대조 (비밀값 없음)

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
venv/Scripts/python.exe - <<'EOF'
import json
for p in ['config/trading_config.json', 'instances/daytrading/trading_config.json']:
    cfg = json.load(open(p, encoding='utf-8'))
    print(p, "| max_candidates =", cfg.get('strategy', {}).get('parameters', {}).get('max_candidates'))
EOF
```

---

## 2. 기동 ① — `real_total_funds_cap = null` 로 «의도된 중단» 확인 (5분)

목적: 감사 P1-1(텔레그램이 인스턴스 `key.ini` 를 안 읽던 결함, `135b712` 로 수정) 이후 **실전 기동 중단 경보가 실제로 도착하는지**를 돈 한 푼 안 쓰고 확인한다.

| # | 할 일 | 성공 판정 | 실패 시 |
|---|---|---|---|
| 2-1 | 라이브 트리에서 `run_instance.bat daytrading` | 콘솔에 `[실전 인스턴스] daytrading 시작 중... (KIS_INSTANCE_DIR=instances\daytrading)` · `logs\daytrading\` 폴더 생성 | venv/key.ini 오류 문구 → 그 문구대로 조치 |
| 2-2 | 로그 확인: `logs/daytrading/trading_20261005.log` | ① `프로세스 PID 등록: <pid>` ② `다중 전략 로드: ['daytrading_3methods_breakout']` ③ `✅ 토큰 발급 완료` · `✅ KIS API 인증 헤더 설정 완료` ④ `현재 시장 상태: holiday` ⑤ `텔레그램 설정 로드: enabled=True` · `✅ 텔레그램 통합 초기화 완료` ⑥ `🚨 실전 기동 중단: 실전 총자금 상한 미설정 \| trading_config.json 에 real_total_funds_cap(원)을 설정해야 실전 기동이 가능합니다` | ③ 실패 = 앱키/시크릿/도메인 오류 → **중단**. ⑤ `enabled=False` = 텔레그램이 다른 파일을 읽음 → **중단**(P1-1 재발) |
| 2-3 | 텔레그램 수신 | 시작 메시지 1건 + `🚨 실전 기동 중단` 경보 1건 | 경보 미수신 = 10-19 이후 모든 사고가 무음 → **중단**(텔레그램부터 해결) |
| 2-4 | 프로세스 종료 확인 | 콘솔이 `[실전 인스턴스] daytrading 종료됨` 후 `pause` 대기 · `token_info_daytrading.json` 생성됨 | 프로세스가 계속 돌면 cap 가드가 안 걸린 것 → **중단** |

> ⓘ 오프라인 재현(10-02): 워크트리 실사용본으로 `BotInitializer._initialize_fund_manager()` 를 broker 스텁(호출되면 실패)과 돌려 **broker 호출 «전»** 에 위 ⑥ 문구로 `LiveStartupAbort` 가 나는 것을 확인했다. ⚠️ 단 실제 기동에서는 그 앞의 `broker.connect()`(토큰 발급)는 실행된다 — 읽기 전용.
> ⓘ 기동 초기에 `Broker not connected` · `⚠️ 실제 잔고 조회 실패 - 기본값 사용` · `⚠️ 기본 잔고 사용: 10,000,000원` WARNING 이 찍힐 수 있다 — `VirtualTradingManager` 가 broker 연결 «전»(`main.py:104`)에 만들어지며 실전 사이징엔 쓰이지 않는다(추정·무해). **중단 기준 아님.**

---

## 3. 기동 ② — cap 기입 후 정상 기동 (30분 이상 관찰)

| # | 할 일 | 성공 판정 줄/값 | 실패 시 중단 기준 |
|---|---|---|---|
| 3-1 | 사장님이 cap 결정 → 라이브 트리 `instances/daytrading/trading_config.json` 의 `"real_total_funds_cap": null` 을 숫자(원, 따옴표 없이)로 | `diff` 차이 = §1-3 + cap 값 1줄 | 따옴표·쉼표 실수 → JSON 파손 시 **조용히 페이퍼로 강등**(감사 P2-30) — 아래 3-3 의 `(실전)` 문구로 반드시 확인 |
| 3-2 | `run_instance.bat daytrading` 재실행 | 2-2 의 ①~⑤ 동일 | — |
| 3-3 | 자금 초기화 | `자금 관리자 초기화 완료(실전): min(상한 X, 총평가 Y) = Z원` — **Y 를 HTS 총평가금액과 대조**(감사 §8 Q1 첫 실측 · A4 `3e532df` 수정 확인) | `(가상매매 모드)` 문구가 나오면 **즉시 Ctrl+C**(실계좌 키로 페이퍼 동작). Y ≠ HTS(예수금 빠짐 등)면 중단·기록 |
| 3-4 | 🔑 **휴장일 미체결 조회** | `🔄 [실전매매] 실제 계좌에서 보유 종목 조회 중...` → `✅ [실전매매] 미체결 주문 없음` | `🚨 실전 기동 중단: 미체결 주문 조회 실패 \| get_pending_orders() = None` = 휴장일엔 `TTTC8036R` 이 오류를 준다는 뜻(감사 §8 Q3). **거래일엔 무관**하지만 ⇒ 스케줄러가 평일 휴장일(10-09 등)마다 abort + 경보를 낸다(무해·소음). 기록하고 §3 나머지는 첫 거래일 07:45 기동으로 이월 |
| 3-5 | 대사 | `📊 [실전매매] 실제 계좌 보유 종목: 0개` · `📊 [실전매매] DB 보유 종목: 0개 (소유자 단위 0건)` | 보유 ≠ 0 → `계좌-DB 불일치` abort(§1-6) |
| 3-6 | 설정 대조 | `[게이트설정대조] 선언 auto 1건 · 실효 auto 1건 · 결함 0건(미반영 0/로드실패 0/구조이상 0/인식불가 0) · 정상 1건 · 파일미선언 0건 · 비활성 7건 · 인스턴스에만 0건 · 파일 instances\daytrading\trading_config.json (로더기록·load_ok=True)` (10-02 오프라인 재현과 같은 문구여야 한다) | `결함 N건`(N>0) 또는 `load_ok=False` → **중단** |
| 3-7 | 시장 매핑(auto) | `[시장매핑] ... 매핑이 0종목이다` WARNING 이 **없을 것** | 있으면 급락게이트가 전 종목 both 로 동작(보호 과잉) — 기록 |
| 3-8 | 전략 초기화 | `전략 초기화 완료: DayTrading3MethodsBreakoutStrategy` · `시스템 초기화 완료` | 실패면 중단 |
| 3-9 | ⚠️ 예상된 오표기 | `⚠️ Paper Trading 모드 활성화` 1줄 — 전략 `config.yaml` 의 `paper_trading: true` 라벨일 뿐 주문을 막지 않는다(`metadata["paper_only"]` 를 읽는 코드 0곳 · 감사 P2-31). 실전 매수·매도 시그널 로그에도 `🧾 [PAPER]` 접두가 붙는다 | **중단 기준 아님** — EOD grep 때 `[PAPER]` 로 실전을 걸러내지 말 것 |
| 3-10 | 휴장일 동기화 | `휴장일 동기화 완료: 2026-10-05 휴장 N건 (누적 M건)` | 실패 WARNING 은 무해(캐시 유지) |
| 3-11 | 원장 표 — DB: `select to_regclass('real_trading_daytrading'), (select count(*) from real_trading_daytrading);` | 표 존재 · 0행 | 없으면 `실거래 테이블 생성 실패` 로그 확인 → 중단 |
| 3-12 | 실원장 제약(감사 잔여 「UNIQUE 0」) — `select conname, contype from pg_constraint where conrelid='real_trading_daytrading'::regclass;` | **PK(id) 1개뿐**이 정상(= 「UNIQUE 0」 재확인 · `LIKE real_trading_records INCLUDING ALL` 이 FK 는 안 복사 — 기존 `real_trading_rs_leader` 도 PK 1개(10-02 SELECT) · id 시퀀스는 `real_trading_records_id_seq` 공유 — 감사 P3-40). 주문번호 컬럼 자체가 없어 **중복 행을 DB 가 못 막는다** ⇒ §8 일일 중복 점검 SQL 로 대신한다 | — (정보) |
| 3-13 | 메인 루프 | `[메인트레이딩루프] 태스크 시작` · `메인 트레이딩 루프 시작` 이후 **주문·후보 관련 줄 0** | 휴장일에 `매수 주문 시도`·`후보 종목` 줄이 보이면 휴장 판정 실패 → **즉시 Ctrl+C** |
| 3-14 | 30분 상태 로그 | `시스템 상태 [...]` · `- 시장 상태: holiday` · `- API 통계: 총 N회 호출, ... 속도제한 0회` | 속도제한 > 0 이면 앱키 공유 의심(§1-5) |
| 3-15 | 텔레그램 폴링 충돌 — `grep -n "terminated by other getUpdates\|Conflict" logs/daytrading/trading_20261005.log` | 0건 | 있으면 같은 텔레그램 봇 토큰을 다른 프로세스가 폴링 중 — 경보 수신 자체는 되지만 명령 수신 불안정. 기록 |
| 3-16 | 콘솔 캡처 로그 `logs/daytrading/robotrader_daytrading_20261005_*.log` | 존재(⚠️ 블록 버퍼링 — 도는 중엔 0바이트일 수 있고 이상 아님) | — |

---

## 4. 실주문 경로(주문·정정·취소·체결조회) — 휴장일 대안

봇은 휴장일에 주문을 «시도조차» 하지 않으므로(§0), 아래 중 하나 이상을 **사장님이 골라야** 한다. 모의투자 도메인은 **불가**다 — TR ID 가 실전 값으로 고정돼 있다(`api/kis_order_api.py:48,50,110,172,223,275` · 감사 P2-32 재확인).
아래 «스크립트» 는 봇과 별개의 1회성 파이썬(라이브 트리 venv · 인스턴스 key.ini)이며, **이 문서 작성자는 만들지도 돌리지도 않았다**(지시: KIS 호출·주문 금지). 쓰는 함수는 봇과 같은 것: `framework.broker.KISBroker.connect()` · `place_buy_order(code, 1, price)` · `get_pending_orders()` · `cancel_order(order_id, code)` · `api.kis_order_api.get_inquire_daily_ccld_lst("01", 오늘, 오늘)`.

| 안 | 언제 | 무엇을 | 검증되는 것 | 성공 판정 | 위험·비용 | 중단 기준 |
|---|---|---|---|---|---|---|
| **A** | 10-05(휴장) | 스크립트: 저가 종목 1주를 전일 종가 −25% 지정가로 매수 주문 1건 | 주문 TR 인증·전송·**거부 응답 처리** | `kis_order_api` 로그에 KIS 오류코드·메시지 1줄(문구는 모름 — 「영업일/주문가능시간 아님」 류 추정) · `_place_order` 가 `success=False` | 🟡 KIS 가 휴장일 주문을 «다음 영업일 주문» 으로 **접수할 가능성**(모름). 접수되면 그대로 B 의 취소 절차로 이어 검증 · 체결 가능성은 −25% 지정가라 사실상 0 | ODNO 를 받았는데 취소 뒤 **재조회(`get_pending_orders()`)에 그 주문이 남아 있으면** HTS 로 즉시 수동 취소 후 중단. (10-04) `cancel_order` 의 `success=False` 만으로는 판단하지 말 것 — NEW-B1 미수정 동안은 성공한 취소도 실패로 찍힌다 |
| **B** ✅ **확정**(사장님 10-02 결정) | 10-06(첫 거래일) 08:30~08:55 (장전 동시호가 접수 시간 — 추정, KIS 문서 확인 필요) | 스크립트: 1주 지정가(전일 종가 −25% = 체결 불가 가격) 매수 → 미체결 조회 → 취소 → 재조회 | **주문 접수 · 미체결 조회(TTTC8036R) · 취소(TTTC0013U) · 당일 주문조회(TTTC0081R)** | ODNO 수신 → `get_pending_orders()` 에 그 주문 → `cancel_order` → 재조회 0건 → 당일 조회에 취소 기록. **(10-04 · NEW-B1 미수정 기대값)** `cancel_order` = `success=False` · `message='Cancel failed: Unknown error'` · `data` 에 새 주문번호(`ODNO`) — 이어서 재조회 0건 + 당일 조회에 취소 행이면 **«취소 TR 정상 + NEW-B1 재현»**으로 판정(성공). 원주문 행의 `cncl_yn` · `rmn_qty` · `cncl_cfrm_qty`(10-08 실측 이름 · 옛 표기 `cnc_` 는 오기) 값을 기록할 것(P2-19 예외 경로 확정용). 수정 반영 뒤 재시험 기대값 = `success=True` | 🟢 체결 위험 ≈ 0(시가가 −25% 이하로 열리지 않는 한) · 비용 0 · ⚠️ 09:00 전에 끝낼 것 · (추정) 장전 시간대 취소 허용 여부는 KIS 문서 확인 | 재조회에 그 주문이 **남아 있으면** HTS 수동 취소 · 08:59 까지 미완료면 HTS 취소 |
| **C** | 10-06~10-16 장중 | 스크립트: 유동성 큰 저가 종목 1주 현재가 지정가 매수 → 체결 확인 → 1주 시장가 매도 | **체결조회 응답 필드 실측**(`avg_prvs`·`tot_ccld_qty`·`ccld_unpr` — 감사 §8 Q2) · 시장가 매도 체결가 파싱(감사 P2-14) | 매수·매도 각각 당일 체결조회 행에 수량·평균가가 채워짐 | 🟡 실비용 수백 원(수수료·세금·스프레드) · 봇 원장(`real_trading_daytrading`)엔 기록 안 됨 → **10-19 첫 기동 전 계좌 보유 0 으로 되돌려 둘 것**(안 그러면 대사 abort) | 미체결 잔존·보유 잔존 시 HTS 정리 |
| **D** | 10-06~10-16 장중 | 실전 인스턴스를 **초소액 cap**(예: 300,000원 → 종목당 27,000원)으로 실제 가동 | **OrderManager 첫 가동 전체**: 신호 → 지정가 주문 → 미체결 감시 → 체결 확정 → 실원장 행 → 전략 콜백(일일 캡) → 손절·익절 감시 · 재기동 대사 | §5 의 줄들이 순서대로 나옴 | 🔴 사실상 **10-19 이전 실매매 시작** = 사장님 결정(09-30 「10-19 시작」)과 충돌 · B-1·B-2 수정이 main 에 머지·재기동돼 있어야 페이퍼와 같은 후보·익절선으로 돈다(머지 전이면 «다른 후보·다른 익절선» — §1-10) | — |
| (E) | 10-19 당일 | D 를 안 하면 **10-19 첫날이 곧 OrderManager 첫 가동** | — | — | 첫날 cap 을 낮게(예: 결정 cap 의 1/3) 시작하는 안을 함께 결정 | — |

> **결정(사장님 10-02)**: **B = 확정** — 10-06 장전 접수·취소(체결 불가 가격 1주). C·D·E 는 이 문서 기준 미결정(작성자 권고였던 「B + C(선택)」 중 C 는 선택으로 남음). D 의 「B-1·B-2 수정 여부」 조건은 수정 브랜치가 머지되면 해소된다.
> **추가 결정(사장님 10-04)**: 10-04 점검의 필수 6건(NEW-B1·C1·B3·B2·C2·A1) 수정이 main 에 반영되면, 10-19 전 거래일 장전에 **B 를 한 번 더** 한다(기대값 `success=True`).

---

## 5. OrderManager 첫 가동 때 볼 줄 (10-19 또는 §4-D 첫날)

**정상 시퀀스**(파일 = `logs/daytrading/trading_YYYYMMDD.log`)

1. 09:00:0x~09:01 후보 로드(B-1 수정 후):
   - (페이퍼가 아직 안 썼으면 · 정상) `[B1-실전] D-1 스냅샷 아직 없음 ['daytrading_3methods_breakout'] — 10초 간격 재확인 · 상한 15분 (그동안 신규 매수 없음 · 보유 감시는 계속)` WARNING 1줄
   - `[E6] daytrading_3methods_breakout: screener_snapshots N건 확보 (스냅샷 M건, 목표 10건, D-1=YYYY-MM-DD)` → `[B1-실전] 스냅샷 후보 등록 완료: N종목 (daytrading_3methods_breakout N · 대기 X초)`
   - 대조: 같은 날 페이퍼 로그(`logs/trading_YYYYMMDD.log`)의 같은 `[E6] daytrading_3methods_breakout: … 확보` 줄과 «스냅샷 M건»·D-1 이 같아야 한다
   - ⚠️ `당일 스크리너 없음 … 자동 수집 fallback` · `[E6-실전] 🔴 스크리너 스냅샷 없음 → 거래량 순위 폴백` 줄은 이제 **나오면 이상**(= 수정 전 코드가 돈다 → §1-10)
2. 약 9~15초마다 `[on_tick] 매수검토 N종목(스킵 s), 신호 k건 | 자리 a/10·일일 d/5 | 매도검토 …` (틱 주기 산정 = `SETUP_REPORT.md` §(e))
3. 신호 시: `[on_tick] 매수신호: CODE(...)` → `[B2-실전] CODE 익절 10.0% 손절 10.0% (소유 전략 '…' config)`(B-2 · 매수마다 1줄) → `매수 주문 시도: CODE q주 @p원 (타임아웃: 300초)` → `매수 주문 성공: <ODNO> - CODE(...)` → `실전 매수 주문 접수: CODE(...)`
4. 체결 시: `주문 완전 체결 확정: <ODNO> (CODE) - q주 @p원` → `실전 매수 기록 저장: CODE q주 @p원 (ID: n)` → `주문 체결 콜백 수신: <ODNO> - CODE (buy)` → `📥 매수 체결: CODE @ p x q주` → 다음 on_tick 의 `일일 1/5`
5. 미체결 5분: (10-04 정정) 정상 경로는 `타임아웃 취소 성공` → `BUY_PENDING -> COMPLETED` → **그날 그 종목 재주문 없음**(`core/trading/order_execution.py:479-487` · on_tick 은 SELECTED 만 본다 — 기존 문구 「다음 틱에 다시 주문될 수 있다」는 틀렸다 · 09-14 시니어 리뷰 판단이 맞음). ⚠️ NEW-B1 미수정 동안의 실제 줄: `주문 취소 실패 … Unknown error` → `not found`/`No cancellable orders` ×2 → `타임아웃 취소 최종 실패` → (b) `강제 상태 정리 (PENDING -> TIMEOUT)` + 텔레그램 `주문 취소 실패 - 수동 확인 필요`, 또는 (a) `주문 취소 확인` 뒤 SELECTED 복귀 → **1회 재주문**. 어느 쪽이든 HTS 에서 그 주문이 실제로 취소됐는지 확인
6. 보유가 생긴 다음날 아침 복원(B-2): `[실전] CODE(…) 복원(POSITIONED): q주 @p원, 익절가 (p×1.10)원, 손절가 (p×0.90)원, 보유 N일` — 보유 7거래일 이상이어도 같은 ±10%. daytrading 보유에 `⚠️ CODE 익절/손절 미설정 - 기본값 적용 (익절 5%, 손절 5%)` 가 나오면 **이상**(아래 표)

**나오면 그날 매매를 멈추고(Ctrl+C) 계좌 대조할 줄** — (10-04) NEW-C1 미수정 동안 Ctrl+C 는 매매 루프만 멈추고 프로세스는 남는다 → §7-1 절차(작업관리자 확인 → 창 X)까지 할 것

| 줄 | 뜻 | 근거 |
|---|---|---|
| `[B2-실전] CODE 소유 전략(…) config tp/sl 해소 실패` WARNING · 아침 복원의 `익절/손절 미설정 - 기본값 적용 (익절 5%, 손절 5%)` | 그 보유가 전략 값(+10%/−10%) 대신 기본값(+15%/−10% · 7거래일+ ±5%)으로 감시된다 = B-2 미적용 | B-2 · `core/trading_decision_engine.py` `_apply_owner_tp_sl_for_real_buy` · `bot/state_restorer.py` `_build_db_holdings_by_owner` |
| `당일 스크리너 없음 … 자동 수집 fallback` · `[E6-실전] 🔴 … 거래량 순위 폴백` | 수정 전 후보 경로가 돈다(B-1 미반영) — 페이퍼와 다른 후보로 산다 | §1-10 |
| `체결 오탐지 감지` · `오탐지 주문 복구` | 체결된 주문을 미체결로 오판해 되살림 → 나중에 **이중 기록** · (10-04) 체결조회 «실패»·서킷브레이커 30초 차단만으로도 생긴다 | 감사 P1-5 · 점검 NEW-B3(미해결) |
| `주문 상태 불명 5분 초과로 타임아웃 처리` | (10-04 정정) 브로커 취소 없이 장부만 닫음 → 그 종목 슬롯이 BUY_PENDING 에 묶임(재매수 없음) · 나중에 체결되면 **손절 감시 없는 보유** → 다음날 아침 대사 abort | 감사 P1-6(미해결) |
| `매도 부분 체결 타임아웃` 뒤 `잔여 주문 취소 API 실패` 3회 | 잔여분이 나중에 체결돼도 장부에 안 잡힘 · (10-04) NEW-B1 미수정 동안은 성공한 취소도 이 줄을 찍는다 → 줄만으로 판단 말고 **HTS 미체결 확인** | 감사 P1-7(미해결) |
| `체결가 비정상(0원)` 반복 | 시장가 매도 체결가 파싱 실패 → 영원히 보류 | 감사 P2-14 |
| `CircuitBreaker OPEN - API 호출 차단` · `Circuit Breaker 활성 중 - 매도 스킵`(이제 WARNING) | API 장애로 손절 매도 봉쇄(30분) · (10-04 정정) 「매도 TR 은 `951594f` 로 통과」는 실질 무효 — 매도 직전 잔고 조회(TTTC8434R)가 차단돼 «매도가능 0주»로 끝나 매도 주문까지 못 간다(NEW-B2) | 감사 P1-8 · 점검 NEW-B2 |
| (10-04 추가) `매도 불가: … 매도가능수량 0` | 잔고 조회 실패를 0주로 읽어 손절 주문 미발송 | 점검 NEW-B2 |
| (10-04 추가) `매수 부분체결 잔여취소 실패 - 수동 확인 필요` | 부분체결 매수의 자금 예약 고착·포지션 장부 누락 | 점검 NEW-B1 → 감사 C-N1 |
| (10-04 추가) `타임아웃 처리 중 완전 체결 확인`(앞에 `주문 완전 체결 확정` 이 없을 때) | 상태 불명 주문을 장부만 닫은 경우 — 문구가 «체결 확인»처럼 보여 오해 소지(`core/orders/order_timeout.py:40-45`) | 감사 P1-6 |
| (10-04 추가) `on_tick 타임아웃`(전략 이름 포함) | 주문 대기 중 30초 초과로 작업이 취소됨 → KIS 에 나간 주문을 봇이 모를 수 있다 · 해당 종목이 BUY/SELL_PENDING 에 묶였는지 확인 | 점검 NEW-A1 |
| (10-04 추가) 아침 `[실전매매] 보유 종목 N/M개 복원` 에서 **N < M** | 한 종목이 조용히 복원에서 빠짐 → 그 종목 손절 감시 없음 | 점검 NEW-C2 |
| `가용자금 음수 보정` | 자금 장부 이상 | 감사 P1-3 계열 |
| `매수 차단: 일일 손실 한도 초과` | 실현손실이 총자금 10% 도달(신규 매수만 멈춤 · 재기동하면 리셋 — 감사 P2-18) | 정보 |

**멈출 필요는 없지만 확인할 줄(B-1 fail-closed)**: `[B1-실전] 🔴 N초 대기 후에도 후보 0 → ['daytrading_3methods_breakout'] 금일 신규 후보 0 (fail-closed · 거래량 폴백 없음 · 보유 매도 감시는 계속). D-1 스냅샷 없음 […] … 스냅샷은 있으나 조회 결과 0건 […] …` ERROR + 텔레그램 경보 — 첫 시도부터 약 15분 뒤(09:15 전후) 1회. 그날 신규 매수만 0 이고 보유 손절·익절·max_hold 감시는 계속 돈다. 할 일: «스냅샷 없음» 쪽이면 페이퍼 로그의 `스크리너 스냅샷 수집 완료` 와 DB `select count(*) from screener_snapshots where strategy='daytrading_3methods_breakout' and scan_date = <D-1>` 확인(그날 룰 통과 0건이면 0 이 정상) · «조회 결과 0건» 쪽이면 같은 시각 `screener_snapshots 기간 조회 실패`(DB) · `안전성 필터 «실패»` 줄 확인. 인스턴스를 재기동하면 다시 15분 기다린다(스냅샷이 이미 있으면 즉시 등록).

---

## 6. 텔레그램 — 받아야 하는 것

| 상황 | 메시지 | 언제 확인 |
|---|---|---|
| 기동 | 시스템 시작 알림(`notify_system_start`) | 10-05 §2·§3 |
| 기동 중단 | `🚨 실전 기동 중단` + 사유 | 10-05 §2 |
| 후보 등록 | `후보 종목 등록: N종목` + `[daytrading_3methods_breakout] CODE(CODE), …`(스냅샷 경로는 종목명 대신 코드 — 페이퍼와 같은 표기) | 첫 거래일 09:00~09:01(스냅샷 대기만큼 늦을 수 있음) |
| 후보 0 경보(B-1 fail-closed) | 오류 경보 · 모듈 `후보로드[실전]` · 본문 `[B1-실전] 🔴 …초 대기 후에도 후보 0 …` | 있을 때만 · 첫 시도 +15분(09:15 전후) — §5 끝 «확인할 줄» |
| 체결 | 체결 알림(종목·매수/매도·수량·가격) | 첫 체결 |
| 태스크 오류 | 태스크명 + 오류 | 상시 |

⚠️ 메시지 본문에 인스턴스 표기가 없다(`core/telegram_integration.py`). 페이퍼 텔레그램이 꺼져 있는 동안은 문제없지만, 같은 봇·채팅을 다른 봇(quant_mom 등)이 쓰면 섞인다.

---

## 7. 종료·정리 (10-05 마지막)

| # | 할 일 | 성공 판정 | 주의 |
|---|---|---|---|
| 7-1 | 콘솔에서 **Ctrl+C** · 배치가 「일괄 작업을 끝내시겠습니까 (Y/N)?」 를 물으면 **N**(파이썬 종료 처리가 끝나게 둔다 — 추정) | (수정 뒤 기대값) `종료 신호 수신: 2` → `시스템 종료 시작` → `미체결 주문 없음 - 취소 스킵` → `PID 파일 삭제 완료` → `시스템 종료 완료`. **(10-04 · NEW-C1 미수정 기대값)** `종료 신호 수신: 2` → (최대 30초) `메인 트레이딩 루프 종료` → `[메인트레이딩루프]`·`[시스템모니터링] 태스크 정상 종료` 까지만 찍히고 **그 뒤 무출력 · 창이 안 닫힌다**(`시스템 종료 시작` 없음 — 텔레그램 상태알림·폴링 루프가 끝나지 않아 종료 처리 미도달). 이렇게 나오면 = «NEW-C1 재현»(성공 판정). 이어서 ① 1~2분 기다려도 그대로면 ② 작업관리자/`tasklist` 에서 그 python 프로세스 확인 ③ **창 X**(또는 Ctrl+Break)로 닫기 ④ 프로세스 0 확인 ⑤ HTS 미체결 0 확인 | 창 X·`kill` 은 종료 경로를 안 타 미체결 취소가 **안 돈다**(감사 P2-21) — NEW-C1 미수정 동안은 Ctrl+C 도 같다 ⇒ 장중 종료는 HTS 미체결 확인이 필수. 남은 PID 파일은 프로세스가 죽어 있으면 다음 기동이 덮어쓰므로 무해. 두 번째 Ctrl+C 도 효과 없음. 킬스위치는 따로 없다(P2-22) |
| 7-2 | 남는 파일 | `token_info_daytrading.json`(유지) · `logs/daytrading/*` · ⚠️ `logs/state/fund_state_2026-10-05.json` 은 **페이퍼와 같은 경로**(인스턴스 미분리 · 덮어씀 · 읽는 코드 0 = 무해) | — |
| 7-3 | 🔴 밤새 띄워 두지 말 것 | 프로세스 0 | 일일 리셋 경로가 없다(감사 P2-25): 전날 프로세스가 살아 있으면 다음날 07:45 기동이 `이미 봇이 실행 중` 으로 exit(1) 하고, 살아남은 프로세스는 **어제 후보·어제 대사**로 계속 돈다 |
| 7-4 | 결과 기록 | §3-3 의 Y 값 vs HTS · §3-4 휴장일 TR 결과 · §1-5 SAME/DIFFERENT · §4 선택 | 관리자 메모리(changelog) |

---

## 8. 첫 주 매일 — I5 실계좌 대조 (장 마감 후)

I5 = 「부분매도 원장 비대칭이 아침 기동을 오탐 중단시킬 수 있다」(2026-08-14 P0 구현 I5 · 근본 수정 백로그). 감사 P1-5/6/7(장부 정합 결함 3건, 미해결)도 같은 대조로 조기에 잡힌다.

```sql
-- ① DB 가 믿는 열린 포지션(봇의 아침 복원과 같은 잔량 식 — db/repositories/trading.py:497-510 를 종목 단위로 합산)
SELECT stock_code, stock_name, SUM(rem) AS qty_open,
       ROUND(SUM(rem * price) / NULLIF(SUM(rem), 0)) AS avg_buy
FROM (SELECT b.stock_code, b.stock_name, b.price,
             b.quantity - COALESCE(s.sold, 0) AS rem
      FROM real_trading_daytrading b
      LEFT JOIN (SELECT buy_record_id, SUM(quantity) AS sold FROM real_trading_daytrading
                 WHERE action = 'SELL' GROUP BY 1) s ON s.buy_record_id = b.id
      WHERE b.action = 'BUY') t
WHERE rem > 0
GROUP BY 1, 2 ORDER BY 1;

-- ② 이중 기록 의심(같은 종목·같은 방향·60초 안 2행 — 감사 P1-5)
SELECT a.stock_code, a.action, a.timestamp, b.timestamp
FROM real_trading_daytrading a JOIN real_trading_daytrading b
  ON a.stock_code = b.stock_code AND a.action = b.action AND a.id < b.id
 AND abs(extract(epoch FROM b.timestamp - a.timestamp)) < 60;
```

| 대조 | 성공 판정 | 실패 시 |
|---|---|---|
| ① 의 종목·수량 = HTS 잔고 | 완전 일치 | 불일치 = 다음날 07:45 기동이 **자동으로 abort**(fail-closed) — 그날 밤 원인 확인·원장 보정 방침을 정할 것 |
| ① 의 평단 ≈ HTS 평단 | ±1틱 | 대사는 «수량만» 본다(감사 §5 D2) — 평단 차이는 기록 |
| ② 0행 | 0 | 1행 이상 = P1-5 발현 → 다음날 기동 전 보정 |
| 실현손익 | 봇 `profit_loss`(gross)·로그 net 과 HTS 실현손익 비교 | 실수수료를 읽는 코드가 없어 **반드시 어긋난다**(감사 §5) — 차이 크기만 기록 |

---

## 9. 작업 스케줄러 ④ 등록 (사장님이 직접 · 10-05 검증 통과 후)

현재 페이퍼: 작업 `RoboTrader_AutoStart` = 월~금 07:40 · `cmd /c D:\GIT\run_all_robotraders.bat` · Interactive · `IgnoreNew` · 실행 제한 72시간 · `StartWhenAvailable=False`(10-02 조회).
실전은 **별도 작업**으로 둘 것을 권한다 — 끄고 켜기(`Disable-ScheduledTask`)가 실전만의 «매수 중단 스위치» 역할을 한다(코드 킬스위치 없음 · 감사 P2-22).

```powershell
# 관리자 권한 불필요(페이퍼 작업과 같은 사용자·Interactive). 10-19 이전엔 등록만 하고 Disable 상태로 둘 수 있다.
$action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c start "RT_daytrading" /D "D:\GIT\kis-trading-template\RoboTrader_template" cmd /k run_instance.bat daytrading'
$trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 07:45
$settings  = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 72)
$principal = New-ScheduledTaskPrincipal -UserId 'sttgp' -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'KisTemplate_RealDaytrading' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'kis-template 실전 daytrading 인스턴스 (run_instance.bat daytrading)'
# 10-19 전까지 잠가 두기:  Disable-ScheduledTask -TaskName 'KisTemplate_RealDaytrading'
# 10-19 직전 켜기:          Enable-ScheduledTask  -TaskName 'KisTemplate_RealDaytrading'
```

| 결정·주의 | 내용 |
|---|---|
| 시각 07:45(페이퍼 +5분) | 두 봇이 같은 폴더(cwd)의 `holiday_kis_cache.json` 을 기동 직후 `"w"` 로 덮어쓴다(인스턴스 미분리 · 감사 P2-24) — 동시 기동을 피한다 |
| 평일 휴장일(10-09 한글날 등) | 그날도 07:45 에 뜬다. §3-4 결과에 따라 «조용히 대기» 또는 «abort + 경보» |
| `StartWhenAvailable` | 페이퍼는 False(07:45 에 PC 가 꺼져 있으면 그날 안 뜬다). 실전은 **보유 종목 손절 감시가 그날 통째로 없다**는 뜻 → True 로 둘지 **사장님 결정** |
| 창 | `cmd /k` 로 창이 남는다. 매일 장 마감 후 Ctrl+C 로 닫는 운영(§7-3) — 안 닫으면 다음날 기동이 중복으로 거부된다 |
| 실행 파일 | `run_instance.bat` 는 끝에 `pause` 가 있다 — 비정상 종료 시 창이 열린 채 남는 것이 정상 |

---

## 10. 알려진 리스크 — 이 체크리스트와 관련된 것만 한 줄씩

- 🟢 **B-1 후보 출처 — 수정**(머지 전이면 미적용 · §1-10): 실전은 페이퍼의 D-1 스냅샷을 페이퍼와 같은 함수로 읽는다(10초 간격 · 상한 15분 대기 → 없으면 그날 신규 0 + 경보 · 거래량 폴백 없음 · 설계 = 사전등록 §②). 남는 것: ⓐ 페이퍼가 그날 안 뜨면 실전 신규 매수도 0(의도된 fail-closed) ⓑ 그날 룰 통과가 진짜 0건이면 15분 뒤 경보가 «오경보»(결과는 페이퍼와 같은 후보 0) ⓒ `SECTOR_NEWS_BOOST_MODE=live` 로 바꾸면 실전(재정렬 생략)과 페이퍼 후보 순서가 갈린다(현행 shadow = 같음) ⓓ 안전필터(KIS 조회) 시각·키가 페이퍼와 달라 VI·정지가 그 사이 바뀐 종목은 갈릴 수 있다. (수정 전: 09:00 거래량 순위 · 페이퍼 daytrading 매수 56.9% 가 5,000원 미만이라 구조적으로 후보에 못 들었다 — `SETUP_REPORT.md` §5.)
- 🟢 **B-2 익절선 — 수정**(머지 전이면 미적용): 실전 매수·아침 복원 모두 소유 전략 config +10%/−10% · 7거래일+ ±5% 조임 미적용. (수정 전: +15%(기본값) · 재기동 후 7거래일+ ±5% — 감사 P1-4 의 실원장 tp/sl 컬럼 부재는 그대로지만 복원이 전략 config 로 메운다.)
- 감사 P1-5/6/7(오탐 복구·상태불명 5분·매도 부분체결) **미해결** — 소액 cap + §8 매일 대조로 노출을 억제한다는 감사 C 절 방침 그대로.
- 감사 P2-19 쿨다운 미무장 재주문 · P2-20 기동 시 미체결 «전량» 취소(HTS 수동 주문 포함) · P2-21/22 종료·킬스위치 · P2-25 일일 리셋 부재.
- `config/constants.py:58` 주석 「다가오는 추석 9/24~28」 은 틀렸다(9/28 은 거래일) — **주석뿐, 동작 영향 0**. 휴장 판정은 `holidays` 라이브러리 + KIS 동기화가 한다(10-05 는 오프라인에서 휴장 판정 확인).
- **수능일**(감사 P2-23 기준 2026-11-19 · 날짜는 감사 문서 인용) `config/market_hours.py:207-219` `special_days` 에 2025-11-13 만 있다 — 실전 가동 중 맞는 첫 특수일. 그날 ① 09:00~10:00 개장 전 주문 ② 15:20~16:30 주문 차단 ③ 15:30 이후 손절 감시 정지. **11-19 전 등록 필요**(코드·설정 변경 = 별도 결재).
- 감사 P2-11(실전 후보의 손실 블랙리스트가 **페이퍼 원장**을 읽는다 · `db/repositories/trading.py:664,694`): B-1 수정 후 실전 후보 경로는 블랙리스트를 **쓰지 않는다**(페이퍼 E6 스냅샷 경로와 동일 — 사장님 보류 결정) ⇒ 실전 인스턴스에선 해당 없음(머지 전이면 종전대로 해당).
- 전략 `config.yaml` 은 페이퍼와 **공유**한다 — 10-17 안건 등으로 daytrading `config.yaml` 이 바뀌면 실전도 같은 순간 바뀐다.
