"""rs_leader 배제 — 2026-09-09 «실측 스냅샷» 재현 핀 (스펙 §1-6 · §2 Q2).

합성 프레임은 「코드가 내가 시킨 대로 동작하는가」만 시험한다. 이 파일은 그와 «다른»
질문을 시험한다 — 「그 동작이 실제 라이브 데이터에서 스펙이 예측한 그 결과를 내는가」.

픽스처 `tests/fixtures/rs_leader_corp_action_20260909_bars.json` 은
`kis_template.daily_prices` 에서 **읽기 전용**으로 뽑은 값이다
(`db/quant_daily_reader.QuantDailyReader.get_daily_prices(code, end_date=2026-09-09, days=130)`
= 스크리너가 실제로 보는 그 프레임. volume 은 adj_factor 적용분).
대상 = `screener_snapshots(strategy='rs_leader', scan_date='2026-09-09')` 상위 20 종목 전부.

못박는 값:
  · 런타임 파생이 표시하는 종목 = **정확히 9개** (스냅샷 랭크 1·2·3·6·7·8·9·10·14)
  · 나머지 11 종목은 **표시되지 않는다** (위양성 0 — 이 20종목 한정)
  · 재개일·정지봉수·종가비가 §2 Q4 표 / §3-3 예시와 일치
  · 배제 후 새 상위 10 = §2 Q2 목록과 **순서까지** 일치
  · score(=120일 수익률) 가 DB 스냅샷 값과 일치 ⇒ 픽스처가 그 스냅샷과 같은 데이터다

⚠️ 이 파일은 DB 에 접속하지 않는다(픽스처 자족). 라이브 DB 는 픽스처 생성 시 SELECT 만 했다.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

import strategies.rs_leader.corp_action_guard as guard

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "rs_leader_corp_action_20260909_bars.json"

# screener_snapshots(rs_leader, 2026-09-09) rank 1~20 — 코드·순서·score
SNAPSHOT = [
    ("049080", 16.019607843137255), ("001210", 13.993788819875776),
    ("002780", 8.018633540372670), ("079650", 3.987261146496815),
    ("159010", 3.879032258064516), ("204840", 3.577981651376147),
    ("001290", 2.750000000000000), ("024850", 2.648058252427184),
    ("060230", 2.633152173913044), ("300120", 2.250239693192713),
    ("002990", 2.248182762201454), ("00088K", 1.794871794871795),
    ("024840", 1.596244131455399), ("032790", 1.584786053882726),
    ("069540", 1.472420506164828), ("020120", 1.337738619676946),
    ("131290", 1.334782608695652), ("091590", 1.011142061281337),
    ("134580", 1.003275109170306), ("198440", 0.985714285714286),
]

# §2 Q4 표 — 배제 대상 9종목의 재개일 (거래일 거리는 2026-09-10 기준)
EXPECTED_FLAGGED = {
    "049080": "2026-06-29", "001210": "2026-07-31", "002780": "2026-09-07",
    "204840": "2026-08-11", "001290": "2026-09-09", "024850": "2026-05-04",
    "060230": "2026-07-06", "300120": "2026-08-20", "032790": "2026-05-27",
}

# §2 Q2 산술 예측 — 배제 후 새 상위 10 (선정 10 → 10, 안전성 필터 통과 가정)
EXPECTED_NEW_TOP10 = ["079650", "159010", "002990", "00088K", "024840",
                      "069540", "020120", "131290", "091590", "134580"]

RS_LB = 120


@pytest.fixture(scope="module")
def frames():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = {}
    for code, bars in raw.items():
        out[code] = pd.DataFrame({
            "date": pd.to_datetime([b[0] for b in bars]),
            "close": [b[1] for b in bars],
            "volume": [b[2] for b in bars],
        })
    return out


def test_fixture_matches_live_snapshot_scores(frames):
    """픽스처가 그 스냅샷과 «같은 데이터»임을 먼저 못박는다.

    score 는 그 종목 «하나»의 120일 수익률(`screener.py:60`)이라 프레임만으로 재현된다.
    이게 어긋나면 아래 예측값 전부가 다른 데이터에 대한 주장이 된다.
    """
    assert set(frames) == {c for c, _ in SNAPSHOT}
    for code, score in SNAPSHOT:
        close = frames[code]["close"].astype(float)
        assert len(close) == 130, code
        rs = float(close.iloc[-1]) / float(close.iloc[-1 - RS_LB]) - 1.0
        assert rs == pytest.approx(score, rel=0, abs=1e-9), code


def test_runtime_detection_flags_exactly_nine(frames):
    """§1-6 재현 — 런타임 파생이 표시하는 종목은 «정확히» 9개다."""
    got = {code: guard.detect(code, df) for code, df in frames.items()}
    flagged = {c for c, hit in got.items() if hit is not None}
    assert flagged == set(EXPECTED_FLAGGED), {
        "missing": sorted(set(EXPECTED_FLAGGED) - flagged),
        "extra": sorted(flagged - set(EXPECTED_FLAGGED)),
    }
    for code, resume in EXPECTED_FLAGGED.items():
        assert got[code]["resumption_date"] == resume, code
        assert got[code]["direction"] == "merge", code
        assert got[code]["halt_bars"] >= 3, code


def test_non_flagged_eleven_are_untouched(frames):
    """대칭 단언 — 나머지 11 종목은 «표시되지 않는다»(이 20종목 한정 위양성 0)."""
    clean = [c for c, _ in SNAPSHOT if c not in EXPECTED_FLAGGED]
    assert len(clean) == 11
    for code in clean:
        assert guard.detect(code, frames[code]) is None, code


def test_001290_log_numbers_match_spec_example(frames):
    """§3-3 예시 줄의 숫자 — 001290: 정지 13봉 → 재개 2026-09-09, 종가비 4.455."""
    hit = guard.detect("001290", frames["001290"])
    assert hit is not None
    assert guard.describe(hit) == "미조정 병합 의심(정지 13봉 → 재개 2026-09-09, 종가비 4.455)"


def test_new_top10_matches_spec_prediction(frames):
    """§2 Q2 — 배제 후 새 상위 10 이 «순서까지» 예측대로다.

    상위 20 은 이미 score 내림차순이고 배제는 정렬 «앞»에서 일어나므로,
    남은 11 의 상대 순서는 원래 순서 그대로다(§2 Q2 「모집단을 줄여도 score 는 안 변한다」).
    """
    survivors = [c for c, _ in SNAPSHOT if guard.detect(c, frames[c]) is None]
    assert len(survivors) == 11
    assert survivors[:10] == EXPECTED_NEW_TOP10
    assert survivors[10] == "198440"     # 11번째 = 후보 20 백필로 밀려나는 자리
