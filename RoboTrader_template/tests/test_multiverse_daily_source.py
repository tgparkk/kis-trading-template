"""멀티버스 드라이버 가격 소스 SSOT 회귀 테스트.

데이터 소스 SSOT (2026-07-16 연구 소스 통일 — 사장님 지시):
  - 일봉(daily OHLCV/유니버스/후보스크린/surge/breadth) = kis_template.daily_prices
  - 분봉(minute) = kis_template.minute_candles
  - KOSPI/KOSDAQ 지수 라인(레짐) = kis_template.daily_prices (stock_code='KOSPI')
  → 셋 다 resolve_daily_source_db() / resolve_minute_source_db() 경유.
     롤백은 KIS_DATA_SOURCE=legacy 하나로.

이력:
  (1) 2026-06-05 이전 — 멀티버스가 기본 robotrader DB(하루 ~125종목 sparse·stale
      워치리스트)로 일봉을 읽어 top_volume:50 이 "정본 상위 50"이 아니라
      "워치리스트 중 상위 50"이었다. 예: 000660(SK하이닉스)은 robotrader 에
      2026-02-10 이후 데이터가 없어 누락됐었다.
      → 일봉을 robotrader_quant(정본)로 교정.
  (2) 2026-07-16 — 형제 봇 중단으로 robotrader/robotrader_quant 가 2026-07-10 동결.
      kis_template 이 양쪽의 상위집합(종목·기간·행수 모두 ≥)이고 유일하게 갱신 중.
      .env 없는 연구 프로세스가 동결된 레거시를 읽고 있었다 → 기본값을 kis_template 로.
      본 파일의 단언은 (1)의 보증(정본 유니버스·이력 완전성)을 그대로 유지한 채
      소스만 kis_template 로 옮긴 것이다 — 약화 없음.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import book_param_multiverse as bpm  # noqa: E402
from scripts import book_portfolio_multiverse as bpf  # noqa: E402


# --- 일봉 = kis_template ---

def test_quant_daily_connection_targets_kis_template():
    """_quant_daily_connection() 은 kis_template 에 연결된다(일봉 SSOT)."""
    with bpm._quant_daily_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        assert cur.fetchone()[0] == "kis_template"


def test_load_top_volume_daily_uses_full_quant_universe():
    """거래대금 상위 50 은 정본 유니버스에서 선정 → SK하이닉스(000660) 포함.

    sparse robotrader 워치리스트엔 최근 000660 데이터가 없어 누락됐었다.
    """
    uni = bpm._load_top_volume_daily("2026-04-01", "2026-05-31", 50)
    assert "000660" in uni, "정본 유니버스라면 거래대금 1~2위 SK하이닉스가 top50 에 있어야 함"
    assert len(uni) == 50


def test_load_daily_adj_returns_full_data_for_recent_window():
    """000660 의 2026-04~05 일봉이 정본(kis_template)에서 로드된다.

    robotrader 는 000660 데이터가 2026-02-10 에 끊겨 이 구간 0행이었다.
    """
    data = bpm._load_daily_adj(["000660"], "2026-04-01", "2026-05-31")
    assert "000660" in data
    assert len(data["000660"]) >= 20


def test_load_daily_adj_loads_quant_only_stock_and_coerces_bad_dates():
    """001450(레거시 robotrader 부재·불량 date 행 포함) 로드 + 불량 date coerce.

    date 컬럼은 text 라 '2026--0-4-' 같은 불량 문자열이 섞여 있다.
    errors='coerce'+dropna 없이는 to_datetime 이 throw → 로드 실패한다.
    """
    data = bpm._load_daily_adj(["001450"], "2021-01-01", "2026-05-31")
    assert "001450" in data, "정본 보유 종목이므로 로드돼야 함(레거시 robotrader 엔 없음)"
    df = data["001450"]
    assert df["datetime"].notna().all(), "불량 date 행은 coerce→dropna 로 제거돼야 함"


def test_load_daily_adj_no_split_artifact_for_adjusted_close():
    """close 는 이미 분할조정된 연속 시세 → adj_factor 를 또 곱하면 분할일에
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


# --- book_portfolio_multiverse 일봉 함수 = kis_template ---

def test_surge_smallcap_uses_full_quant_universe():
    """급등주 풀은 정본 2,600여 종목 유니버스에서 산정 → +15% 급등이력 종목 수백.

    sparse robotrader(~125종목)로는 ~131 밖에 안 나온다(정본 ~753).
    """
    pool, diag = bpf._surge_smallcap_codes("2026-04-01", "2026-05-31")
    assert diag["n_surged"] > 400


def test_breadth_panel_uses_full_quant_universe():
    """레짐 breadth 패널은 정본 유니버스 → 수백+ 종목 컬럼.

    robotrader breadth(~125종목)는 %above-MA120 가 대형주 편향이었다.
    """
    panel = bpf._load_breadth_panel("2026-04-01", "2026-05-31")
    assert panel.shape[1] > 500


# --- 분봉 = kis_template ---

def test_minute_connection_targets_kis_template():
    """분봉 연결은 kis_template.minute_candles(1,445종목·유일 갱신본)."""
    with bpm._minute_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        assert cur.fetchone()[0] == "kis_template"


def test_minute_loader_returns_data_from_kis_template():
    """분봉 로더가 실제로 종목을 반환한다(연결 전환 후 회귀 가드)."""
    uni = bpm._load_top_volume_minute("2026-05-01", "2026-05-27", 10)
    assert len(uni) > 0


def test_minute_loader_covers_dates_after_legacy_freeze():
    """레거시 동결일(2026-07-10) 이후 분봉이 보인다 — kis_template 만 가진 구간.

    robotrader.minute_candles 는 20260710 에서 멈췄으므로, 이 구간에 데이터가
    나온다는 것은 실제로 kis_template 을 읽고 있다는 행동 증거다.
    """
    uni = bpm._load_top_volume_minute("2026-07-14", "2026-07-16", 5)
    assert len(uni) > 0, "동결 이후 구간 분봉이 없다면 여전히 레거시를 읽는 것"


# --- KOSPI 지수 라인 = kis_template 전구간 (회귀 가드) ---

def test_kospi_close_retains_full_history():
    """KOSPI 지수 라인은 2021 이력을 유지한다.

    레거시 시절 이 가드가 robotrader 를 강제한 이유는 robotrader_quant 에
    'KOSPI' 코드가 없고 KS11 이 2024-01~ 만 있어 2021~2023 이 사라졌기 때문이다.
    kis_template 은 'KOSPI' 를 2021-01-04~ 전구간 보유(실측 1,357행 ≥ robotrader
    1,350행)하므로 이력 손실 없이 통일된다 — 원래 보증을 그대로 유지한다.
    """
    s = bpf._load_kospi_close("2021-06-01", "2021-06-30")
    assert len(s) > 0
    assert s.index.min().year == 2021
