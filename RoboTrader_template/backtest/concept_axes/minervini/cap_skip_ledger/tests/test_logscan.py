"""라이브 로그 파싱 — E6 목록·안전필터 제외·[캡]·매수 시그널·복원 수 (합성 로그 · DB 없음)."""
from datetime import date

from backtest.concept_axes.minervini.cap_skip_ledger import logscan as L

D = date(2026, 9, 16)

LOG = """\
2026-09-16 07:40:22 | bot.state_restorer | INFO | [진단] 런타임 포지션 엔트리 32건 / 고유 32종목 / 소유자별 {'rs_leader': 7, 'minervini_volume_dryup': 3} (DB 기준선)
2026-09-16 09:00:45 | core.candidate_selector | INFO | [E6] daytrading_3methods_breakout: 후보 10종목
2026-09-16 09:00:45 | core.candidate_selector | INFO | 후보 제외: 999999(999999) — 거래정지
2026-09-16 09:00:46 | core.candidate_selector | INFO | 안전성 필터: 10건 조회 → 9건 통과 (1건 제외)
2026-09-16 09:00:46 | core.candidate_selector | INFO | [E6] minervini_volume_dryup: screener_snapshots 9건 확보 (스냅샷 10건, 목표 10건, D-1=2026-09-15)
2026-09-16 09:00:46 | core.candidate_selector | INFO | [E6] minervini_volume_dryup: 후보 9종목
2026-09-16 09:00:47 | core.candidate_selector | INFO | 후보 제외: 888888(888888) — 관리종목
2026-09-16 09:02:52 | strategy.MinerviniVolumeDryupStrategy | INFO | [캡] minervini_volume_dryup 002990 평가 스킵 사유=max_positions 보유=3/3 일일매수=0/5
2026-09-16 09:02:53 | strategy.MinerviniVolumeDryupStrategy | INFO | [캡] minervini_volume_dryup 002990 평가 스킵 사유=max_positions 보유=3/3 일일매수=0/5
2026-09-16 09:03:00 | strategy.MinerviniVolumeDryupStrategy | INFO | 🧾 [PAPER] 매수 시그널: 119850 @ 48,300 (추천 62주) | volume_dryup recent/base=0.61 ≤ 0.70
2026-09-16 09:03:00 | trading_context | INFO | [진입억제] 119850 매수 스킵 — 쿨다운 59초 남음 (마지막 진입 0초 전)
2026-09-16 09:03:01 | strategy.RSLeaderStrategy | INFO | 🧾 [PAPER] 매수 시그널: 777777 @ 1,000 (추천 1주) | 절대상승추세
2026-09-16 09:03:01 | bot.trading_analyzer | INFO | [매수거절] 777777 진입가 밴드 이탈 — 스킵 (현재가 1,100 > 상한 1,030)
2026-09-16 09:04:00 | strategy.MinerviniVolumeDryupStrategy | INFO | [신호없음] 041830: generate_signal None 반환 (일봉 82건)
"""


def _write(tmp_path, text=LOG, name="robotrader_template_20260916_074007.log"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return tmp_path


def test_scan_day_extracts_instruments(tmp_path):
    dl = L.scan_day(_write(tmp_path), D)
    assert dl.found and dl.restore_minervini == 3
    assert dl.e6 == dict(secured=9, snapshot=10, target=10, d1="2026-09-15", time="09:00:46")
    # 제외는 «직전 전략 경계 뒤 ~ minervini 확보 줄» 사이만 — 뒤에 나온 888888 은 다음 전략 몫
    assert dl.excluded == ["999999"]
    assert dl.cap["002990"]["k"] == 3 and dl.cap["002990"]["time"] == "09:02:52"
    assert dl.signals["119850"] == dict(ref=48300.0, ratio="0.61", time="09:03:00")
    assert "777777" not in dl.signals                      # 다른 전략의 시그널은 안 센다
    assert dl.notes.get("119850") and "[진입억제]" in dl.notes["119850"][0]
    assert "777777" not in dl.notes                        # 다른 전략 신호 직후의 거절은 minervini 몫이 아니다
    assert dl.nosignal["041830"].startswith("09:04:00")


def test_scan_day_missing_file(tmp_path):
    dl = L.scan_day(tmp_path, D)
    assert not dl.found and dl.e6 is None


def test_live_candidate_list_applies_exclusion_and_target(tmp_path):
    dl = L.scan_day(_write(tmp_path), D)
    snap = ["002990", "999999", "073240", "006360", "119850", "001450",
            "090430", "089860", "041830", "282330"]
    codes, src = L.live_candidate_list(snap, dl)
    assert "999999" not in codes and len(codes) == 9 and src == "log"
    dl.e6["target"] = 3
    codes3, _ = L.live_candidate_list(snap, dl)
    assert codes3 == ["002990", "073240", "006360"]


def test_live_candidate_list_without_log_uses_default(tmp_path):
    dl = L.scan_day(tmp_path, D)
    codes, src = L.live_candidate_list([str(i).zfill(6) for i in range(12)], dl, default_target=10)
    assert len(codes) == 10 and src.startswith("no_e6_log")
