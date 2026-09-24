"""8전략 명세 — 라이브 소스에서 실측한 값만 적는다(순수 데이터 · import 부수효과 0).

🔴 여기 적힌 것은 «라이브가 실제로 하는 일»이다. 코드와 어긋나면 코드가 맞다.
   `tests/test_registry_gate_order.py` 가 8전략 `strategy.py` 를 AST 로 읽어 게이트 순서 · `_log_cap_skip`
   유무 · 클래스 `name` · `exit_timeframe` · `evaluate_entry` 반환 길이 · `on_tick` 미재정의를 대조하고,
   `config/trading_config.json`·각 `config.yaml` 과 최신 K·max_daily_trades·regime_index 를 대조한다.

게이트 순서 3패턴 (2026-09-19 실측 · 커밋 14a9b7a)
────────────────────────────────────────────────
`BaseStrategy.on_tick` 매수 루프(strategies/base.py:660-734)는 8전략 공통이다:

    data 없음/len < get_min_data_length()  → 스킵      (base.py:662-687)
    describe_impossible_drop(data)         → 스킵      (base.py:693-707)
    generate_signal(code, data, 'daily')               (base.py:708)
    BUY 면 `[on_tick] 매수신호: CODE(…)` 한 줄 → ctx.buy (base.py:720-734)

| 패턴 | generate_signal 안 순서 | 전략 |
|---|---|---|
| **P1** | `min_len` → `timeframe` → 보유(매도분기) → `daily_trades` → `max_positions` → `_check_buy` | ma20 · ma5 · elder · rs_leader · deep_mr |
| **P2** | `min_len` → 보유(매도분기) → `daily_trades` → `max_positions` → `timeframe` → `_check_buy` | daytrading · minervini |
| **P3** | (`min_len` **없음**) → 보유(매도분기) → `daily_trades` → `max_positions` → `timeframe` → `_check_buy` | envelope |

🔑 매수·매도 경로와 이 원장 (검증표 #2~#4 정정)
   - 매수 루프는 언제나 `timeframe='daily'` ⇒ `timeframe` 게이트는 매수에서 발화하지 않는다.
   - 매도는 두 경로다. ① `on_tick` 매도 루프(base.py:739-761)가 `exit_timeframe`(8전략 전부 'daily')으로
     `generate_signal` → 보유 분기 → `_check_sell` — 틱마다 **D-1 확정봉**. ② `position_monitor`
     (core/trading/position_monitor.py:359-361)는 `timeframe='intraday'` 인데 P1 은 게이트에서 None,
     P2·P3 의 `evaluate_sell_conditions` 는 보유기간만 본다 ⇒ **매도 재현은 8전략 공통 1벌**(exitsim8).
   - `[캡] … 사유=timeframe` 은 ② 경로(P1 의 ma20)에서만 찍힌다 — 매수 차단이 아니다.
     2026-09-28 07:40 부터 `[캡]` 줄 끝에 `경로={매수루프|매도루프|루프밖}` 이 붙는다
     (docs/prereg_2026-09-24_gate_observability_bundle.md ③) ⇒ 이 줄은 `경로=루프밖` 으로 읽는다.
     같은 (종목, 사유)가 매수·매도 루프 둘 다에서 찍힐 수 있어 `Fold.n`·`last` 가 늘 수 있다.
   - 매도 루프는 «다른 전략» 보유 종목까지 돈다(core/trading_context.py:300-307). 자기 보유가 아니면 매수
     분기로 떨어져 🧾·`[캡]` 줄이 찍히고 BUY 는 버려진다(base.py:750) ⇒ **신호 기준 줄은 매수 루프 전용
     `[on_tick] 매수신호: CODE(`**(base.py:723-726)이고 `[캡]` 은 E6 목록과 교집합으로만 읽는다.
   - **P3(envelope)만 진짜로 다르다**: `min_len` 가드가 없고(on_tick 게이트는 `min_gate_bars`=5,
     strategy.py:57-63), `_check_buy` 가 인자 `data` 를 안 쓰고 `_fetch_entry_history` 로 QuantDailyReader 에서
     `entry_lookback_bars`=230봉(config.yaml:35)을 다시 읽는다(strategy.py:225-266). `_entry_df_cache`·`_quant` 는
     캐시라 상태 무변경 검사 대상이 아니다.

`_log_cap_skip` 계기는 3전략(ma20 · daytrading · minervini)에만 있다 ⇒ 나머지 5전략의 `[캡]` 칸은 언제나 NA.
「[캡] 줄이 없다」를 「막히지 않았다」로 읽지 말 것.

`max_daily_trades` 는 «일일 체결»(매수+매도) 한도다 — 8전략 `on_order_filled` 첫 줄이 매수·매도 모두
`daily_trades += 1`(예: book_pullback_ma20/strategy.py:151)이고 매도도 통보된다(core/trading_decision_engine.py:935).

금액 값(`max_per_stock_amount` · deep_mr `paper_investment_per_stock` · 복리 per_stock)은 여기 적지 않는다 —
라이브 인스턴스·config·로그(`종목당 투자금액 재산정`)에서 실행 때 읽는다(복제본이 어긋날 위험 제거).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Sequence, Tuple

# 게이트 토큰 — 테스트가 소스에서 찾아내는 표지와 같은 이름
G_MIN_LEN = "min_len"
G_TIMEFRAME = "timeframe"
G_HELD = "held"
G_DAILY_TRADES = "daily_trades"
G_MAX_POSITIONS = "max_positions"
G_CHECK_BUY = "check_buy"

P1 = (G_MIN_LEN, G_TIMEFRAME, G_HELD, G_DAILY_TRADES, G_MAX_POSITIONS, G_CHECK_BUY)
P2 = (G_MIN_LEN, G_HELD, G_DAILY_TRADES, G_MAX_POSITIONS, G_TIMEFRAME, G_CHECK_BUY)
P3 = (G_HELD, G_DAILY_TRADES, G_MAX_POSITIONS, G_TIMEFRAME, G_CHECK_BUY)
PATTERN_NAME = {P1: "P1", P2: "P2", P3: "P3"}

FRAME_ONTICK = "ontick_daily"      # on_tick 이 넘긴 일봉(PriceRepository · 120 달력일 · ~80~85봉)
FRAME_QUANT = "quant_entry_hist"   # envelope `_check_buy` 가 스스로 읽는 프레임(QuantDailyReader 230봉)

TIER_MAIN = "main"        # 라이브 E6 상위 T(목표 10) — D1 본 결과
TIER_EXT = "ext"          # 스냅샷 T+1~20위 — 라이브가 후보로 본 적 없음(안전필터 미검사) · 별도 칸
TIER_OFFLIST = "offlist"  # 실제 매수인데 그날 E6 목록 밖(소유자 미지정 SELECTED) — A 에만 있다
TIER_LIFT_UB = "lift_ub"  # A3 상한 민감도 — D3′ 분봉 없는 main 행을 D 일봉으로 «체결로 본» 것 · 본 집계에 넣지 않는다

Hist = Tuple[Tuple[date, Any, str], ...]


@dataclass(frozen=True)
class StrategySpec:
    folder: str                 # 폴더키 = trading_config.json strategies[].name = vtr.strategy
    cls: str                    # 클래스 `name` → 로거 이름 `strategy.<cls>`
    gate_order: Tuple[str, ...]
    has_cap_log: bool           # generate_signal 에 _log_cap_skip 호출부가 있나
    ref_key: str                # Signal.metadata 의 기준가 키
    frame: str
    entry_eval_arity: int       # evaluate_entry 반환 튜플 길이(강제 밴드 패치용)
    k_history: Hist
    mdt_history: Hist
    regime_history: Hist        # trading_config.json regime_index(급락게이트 지수축)
    note: str = ""

    @property
    def logger_name(self) -> str:
        return f"strategy.{self.cls}"

    @property
    def pattern(self) -> str:
        return PATTERN_NAME.get(self.gate_order, "?")


_MDT5: Hist = ((date(2026, 6, 1), 5, "8전략 공통 max_daily_trades=5(일일 «체결») · 변경 이력 없음"),)
_KOSPI: Hist = ((date(2026, 6, 2), "KOSPI",
                 "trading_config.json regime_index · 창 안 변경 없음(git log -G regime_index)"),)

SPECS: Tuple[StrategySpec, ...] = (
    StrategySpec(
        folder="elder_ema_pullback", cls="ElderEmaPullbackStrategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 2), 5, "초기값(도입 커밋 4d0e941 · 32b42ee 표기 무해 — 검증표 #8)"),
                   (date(2026, 6, 4), 20, "689792a K 5→20(2026-06-03 커밋 · 다음 기동 발효)")),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="min_daily_bars=70 · 진입 기준 = 매수스톱(D-1 고가 + 1틱) · 밴드 [스톱, 스톱×1.02]",
    ),
    StrategySpec(
        folder="book_envelope_200d", cls="BookEnvelope200dStrategy",
        gate_order=P3, has_cap_log=False, ref_key="ref_close", frame=FRAME_QUANT, entry_eval_arity=3,
        k_history=((date(2026, 6, 5), 5, "16114b5/ad4cc12 신설"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="🔴 스냅샷이 창 안 1~2행(09-09~09-15 스캔) 뒤 0행 ⇒ 신호 판정 표본이 작고, 판정 가능 행이 "
             "실제 체결(bought)뿐이면 자명한 Y/Y 다(보고서가 표에서 문장을 만든다). 자체 프레임이 «지금 DB» 라 빈티지 위험.",
    ),
    StrategySpec(
        folder="daytrading_3methods_breakout", cls="DayTrading3MethodsBreakoutStrategy",
        gate_order=P2, has_cap_log=True, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 2), 5, "초기값(근거 주석 없음)"),
                   (date(2026, 9, 18), 10, "bc7df66/c565256 K 5→10 · docs/prereg_2026-09-15_focus3_K_raise.md")),
        mdt_history=_MDT5,
        regime_history=((date(2026, 6, 2), "KOSDAQ", "044a20e 전략별 지수 도입"),
                        (date(2026, 9, 14), "auto", "a57a607 KOSDAQ→auto(09-11 18:50 커밋 · 09-14 07:40 발효)")),
        note="거래량 룰 — 빈티지 위험. `[on_tick] 매수신호` 이유 문자열의 vol=a/b 로 건별 대조 가능",
    ),
    StrategySpec(
        folder="minervini_volume_dryup", cls="MinerviniVolumeDryupStrategy",
        gate_order=P2, has_cap_log=True, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 2), 3, "821fb80 Minervini K=3 집중"),
                   (date(2026, 9, 18), 6, "bc7df66/c565256 K 3→6 · docs/prereg_2026-09-15_focus3_K_raise.md")),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="cap_skip_ledger(48b2fe1)가 이 전략만 다루던 원장의 원본",
    ),
    StrategySpec(
        folder="book_pullback_ma20", cls="BookPullbackMa20Strategy",
        gate_order=P1, has_cap_log=True, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 5), 5, "초기값(근거 주석 없음)"),
                   (date(2026, 9, 18), 10, "bc7df66/c565256 K 5→10 · docs/prereg_2026-09-15_focus3_K_raise.md")),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="P1 인데 _log_cap_skip 이 있다 ⇒ [캡] 사유=timeframe 줄은 position_monitor 분봉 경로(매수 차단 아님)"
             " · 09-28 부터 그 줄은 `경로=루프밖`(prereg_2026-09-24_gate_observability_bundle ③)",
    ),
    StrategySpec(
        folder="book_pullback_ma5", cls="BookPullbackMa5Strategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 5), 5, "초기값(근거 주석 없음)"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
    ),
    StrategySpec(
        folder="rs_leader", cls="RSLeaderStrategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=2,
        k_history=((date(2026, 6, 6), 10, "7fd20d4 신설"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="🔴 _check_buy 첫머리 corp_action 배제(모드 = config.constants.RS_LEADER_CORP_ACTION_MODE · "
             "2026-09-17 07:40 부터 live, 가드 코드 자체는 9811d42 · 09-10 23:49 머지 ⇒ 09-10 은 가드 없음 = shadow 와 동치). "
             "_should_log_ontick 이 _ontick_skip_log 를 바꾸므로 상태 무변경 검사에서 제외. 신호가 매일 반복될 수 있다.",
    ),
    StrategySpec(
        folder="deep_mr_dev20", cls="DeepMrDev20Strategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=2,
        k_history=((date(2026, 6, 12), 5, "938ceeb 신설"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="창 안 스냅샷 0건(매일 `[E6] deep_mr_dev20: screener_snapshots 0건`) ⇒ 후보 0",
    ),
)

BY_FOLDER: Dict[str, StrategySpec] = {s.folder: s for s in SPECS}
ALL_FOLDERS: Tuple[str, ...] = tuple(s.folder for s in SPECS)
LOGGER_TO_FOLDER: Dict[str, str] = {s.logger_name: s.folder for s in SPECS}

RS_LEADER_LIVE_SINCE = date(2026, 9, 17)   # docs/prereg_2026-09-16_rsleader_exclusion_live.md · 로그 09-17 07:40:26 mode=live
CAP_LOG_SINCE = date(2026, 9, 16)          # [캡] 계기 e597c33(머지 36fe61c) · 09-16 07:40
VIRTUAL_CAPITAL_PER_STRATEGY = 10_000_000  # config/constants.py:181
LEDGER_START = date(2026, 9, 10)
LEDGER_END = date(2026, 9, 18)             # 7거래일(검증표 #19)
EXIT_FID_SINCE = date(2026, 8, 26)         # 1810cd2(2026-08-25 21:19) 전략 고유 sl/tp 제거 → 다음 기동부터

# 상태 무변경 검사(livesignal8) — 호출 전후 deepcopy 비교
STATE_CHECKED: Tuple[str, ...] = ("positions", "daily_trades", "_cap_skip_logged", "_cap_skip_log_date",
                                  "config", "_ontick_skip_log")
STATE_EXEMPT: Dict[str, Tuple[str, ...]] = {"rs_leader": ("_ontick_skip_log",)}


def spec(folder: str) -> StrategySpec:
    try:
        return BY_FOLDER[folder]
    except KeyError:
        raise KeyError(f"등록되지 않은 전략 폴더키: {folder!r} (등록: {', '.join(ALL_FOLDERS)})")


def _at(history: Sequence[Tuple[date, Any, str]], d: date, what: str) -> Tuple[Any, str]:
    best: Optional[Tuple[Any, str]] = None
    for eff, v, why in sorted(history, key=lambda h: h[0]):
        if eff <= d:
            best = (v, why)
    if best is None:
        raise ValueError(f"{what} 이력에 {d} 이전 항목이 없다")
    return best


def k_for(folder: str, d: date) -> Tuple[int, str]:
    """날짜 d 에 유효한 (K=max_positions, 근거)."""
    v, why = _at(spec(folder).k_history, d, f"{folder} K")
    return int(v), why


def mdt_for(folder: str, d: date) -> Tuple[int, str]:
    """날짜 d 에 유효한 (max_daily_trades — 일일 «체결», 근거)."""
    v, why = _at(spec(folder).mdt_history, d, f"{folder} max_daily_trades")
    return int(v), why


def regime_index_for(folder: str, d: date) -> Tuple[str, str]:
    """날짜 d 에 그 전략이 급락게이트에 넘긴 설정값(`KOSPI`·`KOSDAQ`·`auto`·`both`·`none`)."""
    v, why = _at(spec(folder).regime_history, d, f"{folder} regime_index")
    return str(v), why


def corp_action_mode_for(folder: str, d: date) -> Optional[str]:
    """그날 라이브가 쓰던 `RS_LEADER_CORP_ACTION_MODE`. rs_leader 가 아니면 None."""
    if folder != "rs_leader":
        return None
    return "live" if d >= RS_LEADER_LIVE_SINCE else "shadow"


def state_attrs(folder: str) -> Tuple[str, ...]:
    exempt = STATE_EXEMPT.get(folder, ())
    return tuple(a for a in STATE_CHECKED if a not in exempt)
