"""logscan8 — 실제 줄 픽스처(DB 없음): 매도 루프 🧾 제외 · `종목=` 없는 시장급락 줄 귀속 · 보유 중 무시 줄 ·
[캡]∩E6 · 체결 줄 귀속 · 시장방향성 시간선."""
from __future__ import annotations

from datetime import date

from backtest.concept_axes.ledger8 import logscan8 as L
from backtest.concept_axes.ledger8 import registry as R

D = date(2026, 9, 14)

LOG = """\
2026-09-14 07:40:25 | strategy.RSLeaderStrategy | INFO | [rs-corp-action] mode=shadow (startup)
2026-09-14 07:40:28 | bot.state_restorer | INFO | [진단] 런타임 포지션 엔트리 46건 / 고유 46종목 / 소유자별 {'rs_leader': 10, 'minervini_volume_dryup': 3} (DB 기준선)
2026-09-14 07:40:28 | core.virtual_trading_manager | INFO | 종목당 투자금액 재산정: book_pullback_ma20 1,000,000원 → 864,374원 (자본 8,643,742/10,000,000 = 0.8644, 기준 1,000,000원)
2026-09-14 09:00:48 | core.candidate_selector | INFO | [섹터뉴스] rs_leader mode=shadow reason=ok 이동 10종목(↑7 ↓3) 점수 as-of 09:00 섹터매핑 20/20
2026-09-14 09:00:50 | core.candidate_selector | INFO | 후보 제외: 006490(006490) — 관리종목
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] rs_leader: screener_snapshots 10건 확보 (스냅샷 20건, 목표 10건, D-1=2026-09-11)
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] rs_leader: 후보 10종목
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] deep_mr_dev20: screener_snapshots 0건 (D-1=2026-09-11) — 조건에 맞는 종목 없음, 금일 미진입
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] deep_mr_dev20: 후보 0종목
2026-09-14 09:01:42 | core.trading_decision_engine | INFO | [시장방향성필터] 관측 지수=KOSPI 코드=0001 등락률=-3.45% 임계값=-2.5% 판정=차단
2026-09-14 09:02:20 | core.trading_decision_engine | INFO | [시장방향성필터] 관측 지수=KOSDAQ 코드=1001 등락률=-2.44% 임계값=-3.0% 판정=허용
2026-09-14 09:04:48 | strategy.RSLeaderStrategy | INFO | 🧾 [PAPER] 매수 시그널: 060570 @ 5,040 (추천 595주) | 절대상승추세(종가>MA20·종가>MA60·MA20>MA60·60일수익>0)
2026-09-14 09:04:48 | strategy.RSLeaderStrategy | INFO | [on_tick] 매수신호: 060570(BUY, 신뢰도 60.0, 이유: 절대상승추세(종가>MA20·종가>MA60·MA20>MA60·60일수익>0))
2026-09-14 09:04:48 | trading_context | INFO | 매수 판단 스킵: 시장급락 (KOSPI -3.36% (임계값: -2.5%))
2026-09-14 09:04:50 | strategy.RSLeaderStrategy | INFO | 🧾 [PAPER] 매수 시그널: 111111 @ 1,000 (추천 3000주) | 절대상승추세(종가>MA20·종가>MA60·MA20>MA60·60일수익>0)
2026-09-14 09:04:51 | strategy.RSLeaderStrategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 1건 | 매도검토 44종목, 신호 0건
2026-09-14 09:05:10 | trading_context | INFO | 매수 판단 스킵: 시장급락 (KOSPI -3.36% (임계값: -2.5%))
2026-09-14 09:09:22 | strategy.MinerviniVolumeDryupStrategy | INFO | 🧾 [PAPER] 매수 시그널: 317400 @ 10,000 (추천 300주) | volume_dryup recent/base=0.64 ≤ 0.70
2026-09-14 09:09:22 | strategy.MinerviniVolumeDryupStrategy | INFO | [on_tick] 매수신호: 317400(BUY, 신뢰도 58.0, 이유: volume_dryup recent/base=0.64 ≤ 0.70)
2026-09-14 09:09:22 | core.trading_decision_engine | INFO | [시장방향성필터] 관측 지수=KOSPI 코드=0001 등락률=-2.17% 임계값=-2.5% 판정=허용
2026-09-14 09:09:22 | bot.trading_analyzer | INFO | 보유 중인 종목 매수 신호 무시: 317400(317400)
2026-09-14 09:09:30 | strategy.MinerviniVolumeDryupStrategy | INFO | [on_tick] 매수검토 6종목(스킵 0), 신호 1건 | 매도검토 45종목, 신호 0건
2026-09-14 09:10:13 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수신호: 209640(BUY, 신뢰도 68.0, 이유: breakout_prev_high close=3820.00 prior20_high=3245.00 vol=6496084/72684)
2026-09-14 09:10:13 | core.trading_decision_engine | INFO | 가상매수: 209640 177주 @3,695 (익절:10.0% 손절:10.0%)
2026-09-14 09:10:13 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수신호: 072990(BUY, 신뢰도 68.0, 이유: breakout_prev_high close=3210.00 prior20_high=3150.00 vol=1233796/16707)
2026-09-14 09:10:13 | trading_context | INFO | [진입억제] 072990 매수 스킵 — 쿨다운 59초 남음 (마지막 진입 0초 전)
2026-09-14 09:10:14 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 2건 | 매도검토 45종목, 신호 0건
2026-09-14 09:18:37 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수신호: 072990(BUY, 신뢰도 68.0, 이유: breakout_prev_high close=3210.00 prior20_high=3150.00 vol=1233796/16707)
2026-09-14 09:18:37 | bot.trading_analyzer | INFO | [매수거절] 072990 수량부족
2026-09-14 09:18:38 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 1건 | 매도검토 46종목, 신호 0건
2026-09-14 09:20:19 | strategy.BookPullbackMa5Strategy | INFO | [on_tick] 매수신호: 162300(BUY, 신뢰도 68.0, 이유: ma5_pullback ma5=2731.00 low=2770.00 close=2860.00)
2026-09-14 09:20:19 | core.virtual_trading_manager | WARNING | ⚠️ 전략 가상 잔고 부족 [book_pullback_ma5]: 1,543,108원 < 1,543,131원
2026-09-14 09:20:19 | bot.trading_analyzer | WARNING | 162300 가상 매수 미체결 — 예약 취소 (유령 체결 방지)
2026-09-14 09:20:20 | strategy.BookPullbackMa5Strategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 1건 | 매도검토 46종목, 신호 0건
2026-09-14 09:30:00 | trading_context | INFO | 매수 판단 스킵: 시장급락 (KOSPI -3.10% (임계값: -2.5%)) 종목=005930 전략=book_pullback_ma20 해석지수=KOSPI
2026-09-14 09:31:00 | strategy.BookPullbackMa20Strategy | INFO | [캡] book_pullback_ma20 317400 평가 스킵 사유=timeframe 보유=6/10 일일매수=1/5
2026-09-14 09:31:01 | strategy.BookPullbackMa20Strategy | INFO | [캡] book_pullback_ma20 232140 평가 스킵 사유=max_positions 보유=5/5 일일매수=0/5
2026-09-14 09:40:00 | strategy.ElderEmaPullbackStrategy | INFO | [on_tick] 매수신호: 000810(BUY, 신뢰도 60.0, 이유: triple_screen_ema_pullback low=1<=ema13*1.02 close=2>ema13=1)
2026-09-14 09:40:00 | trading_context | INFO | 매수스톱 미도달 스킵: 000810 (현재가 660,000 < 매수스톱 683,000)
2026-09-14 09:41:00 | strategy.ElderEmaPullbackStrategy | INFO | [on_tick] 매수신호: 012450(BUY, 신뢰도 60.0, 이유: triple_screen_ema_pullback low=1<=ema13*1.02 close=2>ema13=1)
2026-09-14 09:41:00 | trading_context | INFO | 매수 차단: 상한가 접근 (현재가 13,000 / 전일종가 10,000 = +30.0%)
2026-09-14 09:42:00 | strategy.ElderEmaPullbackStrategy | INFO | [on_tick] 매수신호: 005380(BUY, 신뢰도 60.0, 이유: triple_screen_ema_pullback low=1<=ema13*1.02 close=2>ema13=1)
2026-09-14 09:42:00 | trading_context | WARNING | 매수 차단: 일일 손실 한도 초과 (누적손실 1,000,000원 / 한도 10.0%)
"""


def _dir(tmp_path, text=LOG):
    (tmp_path / "robotrader_template_20260914_074007.log").write_text(text, encoding="utf-8")
    return tmp_path


def _scan(tmp_path):
    return L.scan_day(_dir(tmp_path), D, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)


def test_startup_lines(tmp_path):
    dl = _scan(tmp_path)
    assert dl.found and dl.rs_mode == "shadow"
    assert dl.get("rs_leader").restore_n == 10 and dl.get("book_pullback_ma5").restore_n == 0
    assert dl.get("book_pullback_ma20").per_stock["new"] == 864_374


def test_candidate_block(tmp_path):
    rs = _scan(tmp_path).get("rs_leader")
    assert rs.e6 == dict(secured=10, snapshot=20, target=10, d1="2026-09-11", time="09:00:51")
    assert rs.excluded == ["006490"] and rs.sector_mode == "shadow"
    deep = _scan(tmp_path).get("deep_mr_dev20")
    assert deep.e6_zero and deep.e6["target"] == 0


def test_buy_signal_excludes_sell_loop_receipts(tmp_path):
    rs = _scan(tmp_path).get("rs_leader")
    assert set(rs.buysig) == {"060570"}                    # 매도 루프 🧾(111111)은 신호가 아니다
    assert set(rs.receipt) == {"060570", "111111"}          # 🧾 는 기준가 대조용으로만 모은다
    assert rs.buysig["060570"].detail["reasons"].startswith("절대상승추세(")
    assert rs.receipt["060570"].detail["ref"] == 5040.0 and rs.ontick_runs == 1
    assert rs.ontick_times == ["09:04:51"]                  # on_tick 1회 «완료» 시각(빈자리 구간 판정용)


def test_codeless_crash_line_goes_to_preceding_signal(tmp_path):
    dl = _scan(tmp_path)
    assert dl.get("rs_leader").gates_for("060570") == {L.G_CRASH: dl.get("rs_leader").gates[("060570", L.G_CRASH)]}
    assert dl.unattributed.get(L.G_CRASH) == 1               # 매수검토 줄 뒤(09:05:10)의 줄은 귀속 불가
    three_field = dl.get("book_pullback_ma20").gates[("005930", L.G_CRASH)]
    assert three_field.n == 1                                 # 09-16~ 3필드 줄은 줄 안의 전략·종목으로


def test_held_any_throttle_qty_balance_buystop_limitup(tmp_path):
    dl = _scan(tmp_path)
    assert ("317400", L.G_HELD_ANY) in dl.get("minervini_volume_dryup").gates
    day = dl.get("daytrading_3methods_breakout")
    assert ("072990", L.G_THROTTLE) in day.gates and ("072990", L.G_QTY) in day.gates
    assert day.buysig["072990"].n == 2 and day.buysig["072990"].first == "09:10:13"
    ma5 = dl.get("book_pullback_ma5")
    assert ("162300", L.G_BALANCE) in ma5.gates and ("162300", L.G_UNFILLED) in ma5.gates
    elder = dl.get("elder_ema_pullback")
    assert ("000810", L.G_BUYSTOP) in elder.gates and ("012450", L.G_LIMITUP) in elder.gates
    assert ("005380", L.G_DAILY_LOSS) in elder.gates          # [합성] 종목 칸 없는 WARNING → 직전 매수신호


def test_fill_line_attributed_with_tp_sl(tmp_path):
    f = _scan(tmp_path).get("daytrading_3methods_breakout").fills["209640"]
    assert f.detail == dict(qty=177, price=3695.0, tp_pct=10.0, sl_pct=10.0)


def test_cap_blocking_drops_timeframe(tmp_path):
    ma20 = _scan(tmp_path).get("book_pullback_ma20")
    assert ma20.cap_blocking("317400") == {}
    assert set(ma20.cap_blocking("232140")) == {"max_positions"}


def test_market_direction_series(tmp_path):
    dl = _scan(tmp_path)
    assert dl.index_state("KOSPI", "09:02:00") == "차단"
    assert dl.index_state("KOSPI", "09:00:30") == "차단"     # 첫 관측 전이면 그날 첫 관측
    assert dl.index_state("KOSDAQ", "09:02:00") == "허용"
    assert dl.first_verdict_after("KOSPI", "09:02:00", "허용") == "09:09:22"
    assert dl.index_state("NONE", "09:02:00") == ""


def test_parse_gate_crash_forms():
    old = L.parse_gate("매수 판단 스킵: 시장급락 (KOSPI -3.45% (임계값: -2.5%))")
    new = L.parse_gate("매수 판단 스킵: 시장급락 (KOSPI -3.1% (임계값: -2.5%)) 종목=005930 전략=rs_leader 해석지수=KOSPI")
    assert (old.gate, old.code, old.owner) == (L.G_CRASH, None, None)
    assert (new.gate, new.code, new.owner) == (L.G_CRASH, "005930", "rs_leader")


def test_reject_gate_mapping():
    assert L.reject_gate("수량부족") == L.G_QTY
    assert L.reject_gate("진입가 밴드 이탈 — 스킵 (현재가 1 > 상한 0)") == L.G_BAND_ABOVE
    assert L.reject_gate("진입가 밴드 하회 — 스킵 (현재가 0 < 하한 1)") == L.G_BAND_BELOW
    assert L.reject_gate("현재가 미확보 — 진입 보류") == L.G_NO_PRICE
    assert L.reject_gate("데이터부족") == L.G_REJECT_OTHER


def test_live_candidate_list_main_ext(tmp_path):
    rs = _scan(tmp_path).get("rs_leader")
    snap = ["006490"] + [f"{i:06d}" for i in range(1, 20)]
    cl = L.live_candidate_list(snap, rs)
    assert cl.main == [f"{i:06d}" for i in range(1, 11)] and cl.ext == [f"{i:06d}" for i in range(11, 20)]
    assert cl.src == "log" and cl.target == 10


def test_missing_file(tmp_path):
    dl = L.scan_day(tmp_path, D, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)
    assert not dl.found and dl.get("rs_leader").e6 is None


def test_ambiguous_lookup_lines_are_kept_by_code(tmp_path):
    """`[모호조회]`(core/trading/stock_state_manager.py:347-351 · 코드 단독 폴백이 슬롯 여럿 중 첫째를 돌려줌) — 25분 매수
    쿨다운이 다른 전략 객체에서 올 수 있었는지 가르는 유일한 흔적(run.cooldown_flag)."""
    text = LOG + (
        "2026-09-14 09:50:00 | core.trading.stock_state_manager | WARNING | [모호조회] 005930 다중 소유(2) — "
        "strategy 인자 필요. 첫 소유자 반환: rs_leader\n"
        "2026-09-14 10:05:00 | core.trading.stock_state_manager | WARNING | [모호조회] 005930 다중 소유(2) — "
        "strategy 인자 필요. 첫 소유자 반환: BookPullbackMa20Strategy\n")
    dl = L.scan_day(_dir(tmp_path, text), D, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)
    assert dl.ambiguous == {"005930": ["09:50:00", "10:05:00"]}
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _scan(plain).ambiguous == {}
