"""멀티버스 드라이버 일봉 소스 SSOT 회귀 테스트.

데이터 소스 SSOT (사장님 확정 2026-06-05):
  - 일봉(daily OHLCV/유니버스/후보스크린/surge/breadth) = robotrader_quant.daily_prices (2601종목/2487행일)
  - 분봉(minute) = robotrader.minute_candles (quant 엔 minute_candles 테이블 없음)
  - KOSPI/KOSDAQ 지수 라인(레짐) = robotrader (전구간 2021~, quant KS11 은 2024+ 만)

배경: 멀티버스가 기본 robotrader DB(하루 ~125종목 sparse·stale 워치리스트)로 일봉을
읽어 top_volume:50 이 "정본 상위 50"이 아니라 "워치리스트 중 상위 50"이었다.
예: 000660(SK하이닉스)은 robotrader 에 2026-02-10 이후 데이터가 없어 누락됐었다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import book_param_multiverse as bpm  # noqa: E402
from scripts import book_portfolio_multiverse as bpf  # noqa: E402


# --- 일봉 = robotrader_quant ---

def test_quant_daily_connection_targets_quant_db():
    """_quant_daily_connection() 은 robotrader_quant 에 연결된다(일봉 SSOT)."""
    with bpm._quant_daily_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        assert cur.fetchone()[0] == "robotrader_quant"


def test_load_top_volume_daily_uses_full_quant_universe():
    """거래대금 상위 50 은 정본 유니버스에서 선정 → SK하이닉스(000660) 포함.

    sparse robotrader 워치리스트엔 최근 000660 데이터가 없어 누락됐었다.
    """
    uni = bpm._load_top_volume_daily("2026-04-01", "2026-05-31", 50)
    assert "000660" in uni, "정본 유니버스라면 거래대금 1~2위 SK하이닉스가 top50 에 있어야 함"
    assert len(uni) == 50


def test_load_daily_adj_returns_quant_data_for_recent_window():
    """000660 의 2026-04~05 일봉이 정본(quant)에서 로드된다.

    robotrader 는 000660 데이터가 2026-02-10 에 끊겨 이 구간 0행이었다.
    """
    data = bpm._load_daily_adj(["000660"], "2026-04-01", "2026-05-31")
    assert "000660" in data
    assert len(data["000660"]) >= 20


def test_load_daily_adj_loads_quant_only_stock_and_coerces_bad_dates():
    """001450(robotrader 부재, quant 보유·불량 date 행 포함) 로드 + 불량 date coerce.

    quant date 컬럼은 text 라 '2026--0-4-' 같은 불량 문자열이 섞여 있다.
    errors='coerce'+dropna 없이는 to_datetime 이 throw → 로드 실패한다.
    """
    data = bpm._load_daily_adj(["001450"], "2021-01-01", "2026-05-31")
    assert "001450" in data, "quant 보유 종목이므로 로드돼야 함(robotrader 엔 없음)"
    df = data["001450"]
    assert df["datetime"].notna().all(), "불량 date 행은 coerce→dropna 로 제거돼야 함"


def test_load_daily_adj_no_split_artifact_for_quant_adjusted_close():
    """quant close 는 이미 분할조정된 연속 시세 → adj_factor 를 또 곱하면 분할일에
    가짜 절벽이 생긴다(이중조정).

    035720(카카오, 2021-04-15 5:1분할, adj_factor 5→1)·049470(adj_factor 50→5→1)
    로드 시 일간수익률이 한국 가격제한(±30%)을 넘는 가짜 급락이 없어야 한다.
    (스크리너 QuantDailyReader 와 동일하게 raw close 사용.)
    """
    # adj_factor 곱셈 아티팩트는 계수 감소(50→5→1)일에 close 가 ~10× 줄어드는 *하방* 가짜절벽.
    # (049470 raw close 의 +254% 상방점프는 별개의 raw 데이터 이상 → 범위 외, 유니버스 미포함.)
    for code in ("035720", "049470"):
        data = bpm._load_daily_adj([code], "2021-01-01", "2026-05-31")
        assert code in data, f"{code} 로드 실패"
        close = data[code]["close"].astype(float).reset_index(drop=True)
        rets = close.pct_change().dropna()
        assert rets.min() > -0.5, f"{code}: 가짜 분할 절벽(min daily ret={rets.min():.3f})"


# --- book_portfolio_multiverse 일봉 함수 = robotrader_quant ---

def test_surge_smallcap_uses_full_quant_universe():
    """급등주 풀은 정본 2601종목 유니버스에서 산정 → +15% 급등이력 종목 수백.

    sparse robotrader(~125종목)로는 ~131 밖에 안 나온다(정본 ~753).
    """
    pool, diag = bpf._surge_smallcap_codes("2026-04-01", "2026-05-31")
    assert diag["n_surged"] > 400


def test_breadth_panel_uses_full_quant_universe():
    """레짐 breadth 패널은 정본 유니버스(quant) → 수백+ 종목 컬럼.

    robotrader breadth(~125종목)는 %above-MA120 가 대형주 편향이었다.
    """
    panel = bpf._load_breadth_panel("2026-04-01", "2026-05-31")
    assert panel.shape[1] > 500


# --- 분봉 = robotrader (회귀 가드) ---

def test_minute_loader_still_uses_robotrader():
    """분봉 로더는 robotrader.minute_candles 유지(quant 엔 minute_candles 없음)."""
    uni = bpm._load_top_volume_minute("2026-05-01", "2026-05-27", 10)
    assert len(uni) > 0


# --- KOSPI 지수 라인 = robotrader 전구간 (회귀 가드) ---

def test_kospi_close_retains_full_history_from_robotrader():
    """KOSPI 지수 라인은 robotrader(전구간) 유지 → 2021 이력 존재.

    quant 로 옮기면 KS11(2024-01~)만 있어 2021~2023 이 사라진다.
    """
    s = bpf._load_kospi_close("2021-06-01", "2021-06-30")
    assert len(s) > 0
    assert s.index.min().year == 2021
