"""Gen-1 러너 _load_daily_adj 회귀 테스트: adj_factor 곱셈으로 인한 가짜 분할 절벽 부재 검증.

배경: daily_prices.close 는 이미 분할조정된 연속 시세다. 여기에 adj_factor 를 곱하면
분할일(예: 카카오 035720 5:1, 2021-04-15)에 raw×5 → raw×1 로 튀며 하루 -80% 가짜 절벽이
생겨 MaxDD 가 거짓으로 부풀려진다. 수정 후에는 종가가 그대로 연속시세여야 하며, 한국
일일 가격제한(±30%)을 초과하는 종가-종가 변화가 단 하루도 없어야 한다.

RED/GREEN 근거: 수정 전 코드는 2021-04-14 close 112000×5=560000, 2021-04-15 120500×1
→ 하루 약 -78.5% (아래 참조). 수정 후 112000→120500 = 약 +7.6% 로 ±30% 이내.
"""
import os

# 이 러너들은 db.connection.DatabaseConnection 을 직접 사용 → 가격 SSOT = kis_template.
os.environ.setdefault("TIMESCALE_DB", "kis_template")

import pytest

# 5:1 분할(2021-04-15) 이력이 있는 카카오. 분할창을 감싸는 윈도우.
SPLIT_STOCK = "035720"
START = "2021-01-12"
END = "2021-12-30"
KR_DAILY_LIMIT = 0.30  # 한국 일일 가격제한 ±30% → 이를 넘는 종가변화는 물리적으로 불가.


def _max_abs_daily_return(df):
    ret = df["close"].pct_change().dropna().abs()
    if ret.empty:
        return None
    idx = ret.idxmax()
    return float(ret.loc[idx]), df.loc[idx, "datetime"]


@pytest.mark.parametrize("module_name", [
    "scripts.run_minervini_vcp",
    "scripts.run_daytrading_3methods",
])
def test_no_false_split_cliff(module_name):
    import importlib
    mod = importlib.import_module(module_name)
    data = mod._load_daily_adj([SPLIT_STOCK], START, END)
    assert SPLIT_STOCK in data, f"{module_name}: {SPLIT_STOCK} 미로드 (DB 접근/윈도우 확인)"
    df = data[SPLIT_STOCK]
    mx = _max_abs_daily_return(df)
    assert mx is not None, "종가 변화 계산 불가"
    max_ret, when = mx
    # 수정 전이라면 분할일에 약 0.785 → 실패. 수정 후에는 ±30% 이내.
    assert max_ret <= KR_DAILY_LIMIT, (
        f"{module_name}: {SPLIT_STOCK} 최대 종가변화 {max_ret:.4f} @ {when} "
        f"> {KR_DAILY_LIMIT} → adj_factor 가짜 절벽 잔존"
    )
    print(f"\n{module_name}: max |daily close return| = {max_ret:.4f} @ {when}")
