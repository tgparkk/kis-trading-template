"""🔒 동결 상수 — 스펙 §3 그대로. 바꾸면 사전등록 개정 대상이다."""
from __future__ import annotations

from datetime import date
from pathlib import Path

PKG = Path(__file__).resolve().parent
RESULTS = PKG / "results"
PREREG = PKG / "PREREG.md"
FOLDER = "daytrading_3methods_breakout"

SCAN_START, SCAN_END = date(2021, 2, 1), date(2024, 3, 12)
PX_START, PATH_END = "2021-01-04", "2024-04-30"
FILING_START = date(2021, 1, 1)
BACKFILL_TYPES = ("A", "B", "I")      # 백필·완결 판정 유형(check-backfill 단계 출력 types 와 같아야 build 허용)
# build 멈춤 규칙(critic 사소): dart_disclosures 중 rcept_dt ∈ [FILING_START, SCAN_END] ∧ pblntf_ty ∈ BACKFILL_TYPES 행 수.
# = Task 11 적재 기록(2021 71,176 · 2022 70,095 · 2023 70,573 · 2024-01-01~03-12 14,631). 다르면 build 거부.
BACKFILL_ROWS_EXPECTED = 226_475
FIT_START, FIT_END = date(2024, 3, 13), date(2026, 9, 23)
FIT_PX_START = "2023-12-01"

TAGS_LAG0 = ("유상증자", "최대주주변경", "소송·횡령")
MGMT_TAG = "소송·횡령"

MIN_TV = 1_000_000_000
LARGE_CAP = 500_000_000_000
PL_CUT = 0.5
TV_AVG_BARS = 20
BAND_UP = 0.03

COST_PCT = 0.25
ALPHA = 0.05
DELTA_MAX = -0.4
N1_MIN = 100
BLOCK_TD = 20
SEED = 20261010
N_FAKE = 400
FAKE_P = 0.10
FAKE_LO, FAKE_HI = 0.07, 0.13
FAKE_VALID_FRAC = 0.95     # 유효 복제(p 유한) ≥ ceil(0.95·N_FAKE) = 380 이어야 게이트 판정 · 미만이면 "degenerate"(관리자 판단 · PREREG 명시)
Z_ALPHA, Z_POWER = 1.6448536269514722, 0.8416212335729143
TAIL_LOSS = -15.0

# 보유 창 기업행위 의심 표시 `ca_path`(critic B2 · open 에서 팔별 수 + 양 팔 대칭 제외 판 인쇄 — 라벨 불변).
# 고정 창 = 진입 다음 거래일부터 k=1..CA_WINDOW_TD 거래일(실제 청산과 무관) · 그 안 하루라도
# FD1 동결식 flag_cliff(`replayer/flags.py` · 문턱 −18%·갭 80%·거래량 2.0× 를 여기서 바꾸지 않음)
# ∨ |adj_factor_t − adj_factor_{t−1}| > CA_ADJ_EPS(NULL = 1) ∨ |시가 또는 종가 / 전 종가 − 1| > CA_JUMP(가격제한폭 밖 = 기업행위).
CA_WINDOW_TD = 10
CA_ADJ_EPS = 0.001
CA_JUMP = 0.30

# 라이브 어댑터(`Daytrading3MethodsBreakoutScreenerAdapter.default_params`)와 같아야 하는 룰 값 — 다르면 거부
# (`universe.check_adapter_params` · require_frozen · scan_window). 대형 기준 = 어댑터 max_market_cap.
HIGH_WINDOW, VOL_LOOKBACK, VOL_MULT = 15, 20, 2.0
LOOKBACK_BARS = 60

# PREREG_FROZEN_BLOB · PROXY_COEF_MD5 는 `frozen_consts.py` 로 옮겼다(pins 블록 순환 회피 · 최종 리뷰 I4).
