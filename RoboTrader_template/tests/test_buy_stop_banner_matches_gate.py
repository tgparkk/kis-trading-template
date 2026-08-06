"""기동 배너(`MarketHours.get_today_info`)가 실제 주문 게이트와 일치하는지 검증.

배경 (2026-08-06):
    배너가 "매수 중단: 12:00 이후"라고 출력하고 있었지만 그 컷오프를 실행하는
    프로덕션 호출자가 하나도 없었다(`should_stop_buying` / `is_new_buy_blocked` 는
    테스트에서만 호출). 실제 매수를 막는 유일한 시간 게이트는 `can_place_order()`
    이고 거기엔 12시 컷오프가 없어, 14거래일 166매수 중 8건이 12시 이후에
    체결됐다(최대 15:09:32). 반증이 매일 로그에 찍히고 있었는데 아무도 배너와
    대조하지 않았다.

이 파일이 막는 것:
    배너가 말하는 시간 제약과 `can_place_order()` 가 실제로 적용하는 시간 제약이
    **어느 방향으로든** 어긋나면 실패한다. 문자열을 하드코딩해 비교하지 않고,
    게이트를 분 단위로 실측한 결과와 배너가 스스로 밝힌 구간을 대조한다.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytz

from config.market_hours import MarketHours, get_circuit_breaker_state

KST = pytz.timezone('Asia/Seoul')

# 배너가 스스로 밝히는 주문 가능 구간을 뽑아낸다.
_ORDER_WINDOW_RE = re.compile(r"주문 가능:\s*(\d{2}:\d{2})\s*~\s*(\d{2}:\d{2})")


def kst_dt(year, month, day, hour, minute=0, second=0):
    return KST.localize(datetime(year, month, day, hour, minute, second))


@pytest.fixture(autouse=True)
def _clean_circuit_breaker():
    """전역 서킷브레이커 싱글턴이 다른 테스트에서 오염돼 있으면 실측이 왜곡된다."""
    cb = get_circuit_breaker_state()
    cb.clear_all()
    yield
    cb.clear_all()


def _banner_order_window(day: datetime):
    """배너가 주장하는 (시작, 종료) 'HH:MM' 튜플."""
    info = MarketHours.get_today_info('KRX', dt=day)
    m = _ORDER_WINDOW_RE.search(info)
    assert m is not None, (
        f"배너에서 '주문 가능: HH:MM~HH:MM' 구간을 찾지 못했다.\n"
        f"배너가 시간 제약을 더 이상 밝히지 않으면 실제 게이트와 대조할 수단이 사라진다.\n"
        f"--- 배너 원문 ---\n{info}"
    )
    return m.group(1), m.group(2)


def _measured_order_minutes(day: datetime, start_hour=6, end_hour=18):
    """`can_place_order()` 를 분 단위로 실측해 True 인 'HH:MM' 목록을 반환."""
    minutes = []
    cursor = kst_dt(day.year, day.month, day.day, start_hour, 0)
    stop = kst_dt(day.year, day.month, day.day, end_hour, 0)
    while cursor <= stop:
        if MarketHours.can_place_order(None, 'KRX', cursor):
            minutes.append(cursor.strftime('%H:%M'))
        cursor += timedelta(minutes=1)
    return minutes


def _assert_banner_matches_gate(day: datetime, label: str):
    banner_start, banner_end = _banner_order_window(day)
    measured = _measured_order_minutes(day)

    assert measured, (
        f"[{label}] 배너는 {banner_start}~{banner_end} 주문 가능이라고 하는데 "
        f"can_place_order() 는 하루 종일 False 였다."
    )

    # 배너 시작 == 실측 첫 허용 분
    assert measured[0] == banner_start, (
        f"[{label}] 배너 시작 {banner_start} != 실측 첫 주문가능 {measured[0]}. "
        f"게이트를 바꿨으면 get_today_info() 배너도 함께 고칠 것."
    )

    # 배너 종료 == 실측 마지막 허용 분의 1분 뒤 (배너 종료 시각부터 차단이라는 뜻)
    last = kst_dt(day.year, day.month, day.day,
                  int(measured[-1][:2]), int(measured[-1][3:]))
    expected_end = (last + timedelta(minutes=1)).strftime('%H:%M')
    assert expected_end == banner_end, (
        f"[{label}] 배너 종료 {banner_end} != 실측 마지막 주문가능 {measured[-1]}의 다음 분 "
        f"{expected_end}. 게이트를 바꿨으면 get_today_info() 배너도 함께 고칠 것."
    )

    # 구간이 연속인지 — 중간에 구멍이 있으면 배너의 "A~B" 표기 자체가 거짓이 된다.
    expected_all = []
    cursor = kst_dt(day.year, day.month, day.day, int(banner_start[:2]), int(banner_start[3:]))
    end_dt = kst_dt(day.year, day.month, day.day, int(banner_end[:2]), int(banner_end[3:]))
    while cursor < end_dt:
        expected_all.append(cursor.strftime('%H:%M'))
        cursor += timedelta(minutes=1)
    assert measured == expected_all, (
        f"[{label}] 배너가 말한 {banner_start}~{banner_end} 안에 주문 불가 구간이 있다: "
        f"{sorted(set(expected_all) - set(measured))[:10]}"
    )


class TestBannerMatchesOrderGate:
    """배너 문구 ↔ can_place_order() 실측 일치"""

    def test_normal_weekday(self):
        """평일: 배너가 말하는 주문 가능 구간 == can_place_order() 실측 구간"""
        _assert_banner_matches_gate(kst_dt(2026, 2, 9, 0, 0), "평일(2026-02-09 월)")

    def test_special_day_suneung(self):
        """특수일(수능일)에도 배너가 실제 게이트를 따라가는지.

        수능일은 개장/마감이 1시간 밀리지만 `closing_auction_start` 는 특수일 설정에
        없어 기본값(15:20)이 적용된다 — 배너는 그 **실제 동작**을 말해야 한다.
        """
        _assert_banner_matches_gate(kst_dt(2025, 11, 13, 0, 0), "수능일(2025-11-13)")

    def test_banner_does_not_promise_a_cutoff_the_gate_ignores(self):
        """배너가 주장한 주문 마감 시각에 게이트가 실제로 막는지 (양방향 확인).

        누군가 배너만 손대서 '매수 중단: 12:00' 류의 문구를 되돌려 놓으면,
        그 시각에 can_place_order() 가 여전히 True 라 여기서 실패한다.
        """
        day = kst_dt(2026, 2, 9, 0, 0)
        _, banner_end = _banner_order_window(day)
        cutoff = kst_dt(day.year, day.month, day.day,
                        int(banner_end[:2]), int(banner_end[3:]))

        assert MarketHours.can_place_order(None, 'KRX', cutoff) is False, (
            f"배너는 {banner_end} 부터 주문 불가라고 하는데 can_place_order() 는 True 다."
        )
        assert MarketHours.can_place_order(None, 'KRX', cutoff - timedelta(minutes=1)) is True, (
            f"배너는 {banner_end} 직전까지 주문 가능이라고 하는데 can_place_order() 는 False 다."
        )


class TestUnwiredBuyCutoffHelpers:
    """`should_stop_buying` / `is_new_buy_blocked` 가 여전히 미결선인지 확인.

    이 두 함수는 배너가 12시 컷오프를 주장하게 만든 근원이다. 프로덕션에 결선되는
    순간 라이브 매매 동작이 바뀌고 배너도 같이 고쳐야 하므로, 결선을 여기서 감지한다.
    """

    LIVE_PATH_DIRS = ('bot', 'core', 'api', 'strategies', 'framework', 'utils', 'config')
    HELPERS = ('should_stop_buying', 'is_new_buy_blocked')

    def _live_path_sources(self):
        root = Path(__file__).resolve().parent.parent  # RoboTrader_template/
        files = [root / 'main.py']
        for d in self.LIVE_PATH_DIRS:
            files.extend((root / d).rglob('*.py'))
        # 정의부 자신은 제외
        return [f for f in files if f.exists() and f.name != 'market_hours.py']

    def test_helpers_still_have_no_production_callers(self):
        hits = []
        for path in self._live_path_sources():
            try:
                text = path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            for helper in self.HELPERS:
                if helper in text:
                    hits.append(f"{path}: {helper}")

        assert not hits, (
            "미결선이던 매수 컷오프 헬퍼가 프로덕션 경로에서 참조되기 시작했다:\n  "
            + "\n  ".join(hits)
            + "\n\n결선했다면 (1) 라이브 매매 동작이 바뀌므로 승인 여부를 확인하고 "
              "(2) config/market_hours.get_today_info() 배너와 두 함수의 docstring "
              "('결선돼 있지 않다')을 함께 갱신한 뒤 이 테스트를 수정할 것."
        )
