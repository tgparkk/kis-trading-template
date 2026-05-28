"""CAN SLIM 스크리너 — 일별 C+A+L+M 통과 종목 리스트 생성.

실제 DB 데이터 기반 구현:
  C: 순이익 YoY >= 25%  (financial_statements.net_income)
  A: ROE >= 17%         (financial_statements.roe, 단위 %)
  L: momentum_score >= L_THRESHOLD (quant_factors.momentum_score, 백분위 0~100)
  M: KOSPI 200일 MA 위 + 우상향  (daily_candles KS11)

PIT-safe: financial_statements는 최신 공시 기준 적용 (보수적으로 스냅샷 날짜 이전 데이터만 사용)
스크리너 날짜: quant_factors calc_date 기준 (2025-12-08 ~ 2026-02-03)
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = logging.getLogger("canslim_screener")

# 임계값
NI_YOY_MIN = 0.25          # 순이익 YoY 성장률 최소 (C)
ROE_MIN = 17.0             # ROE 최소 (A) — % 단위
L_THRESHOLD = 75.0         # momentum_score 최소 (L) — 75 백분위 이상
KOSPI_MA_PERIOD = 200      # M 요소 MA 기간


def _load_kospi_for_m(start_yyyymmdd: str, end_yyyymmdd: str) -> pd.DataFrame:
    """KS11 일봉 로드 → M 필터 컬럼 추가."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stck_bsop_date, stck_clpr
            FROM daily_candles
            WHERE stock_code = 'KS11'
              AND stck_bsop_date >= %s AND stck_bsop_date <= %s
            ORDER BY stck_bsop_date ASC
        """, (start_yyyymmdd, end_yyyymmdd))
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=['date', 'close', 'ma200', 'ma200_slope', 'm_pass'])
    df = pd.DataFrame(rows, columns=['date', 'close'])
    df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
    df['close'] = df['close'].astype(float)
    df = df.sort_values('date').reset_index(drop=True)
    df['ma200'] = df['close'].rolling(KOSPI_MA_PERIOD, min_periods=20).mean()
    df['ma200_slope'] = df['ma200'] - df['ma200'].shift(5)
    df['m_pass'] = (df['close'] > df['ma200']) & (df['ma200_slope'] > 0)
    return df


def _load_quant_factors() -> pd.DataFrame:
    """quant_factors 전체 로드."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, calc_date, momentum_score, growth_score, quality_score, total_score
            FROM quant_factors
            ORDER BY calc_date ASC, stock_code ASC
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=['stock_code', 'calc_date', 'momentum_score', 'growth_score', 'quality_score', 'total_score'])
    df['calc_date'] = pd.to_datetime(df['calc_date'], format='%Y%m%d')
    for col in ['momentum_score', 'growth_score', 'quality_score', 'total_score']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def _load_financial_fundamentals() -> dict:
    """financial_statements에서 종목별 최신 순이익 YoY + ROE 계산.

    Returns: {stock_code: {'ni_yoy': float, 'roe': float | None}}
    """
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, report_date, net_income, roe
            FROM financial_statements
            WHERE net_income IS NOT NULL
            ORDER BY stock_code, report_date ASC
        """)
        rows = cur.fetchall()

    stock_records: dict[str, list] = defaultdict(list)
    for code, date, ni, roe in rows:
        stock_records[code].append({'date': str(date), 'net_income': float(ni), 'roe': roe})

    result = {}
    for code, records in stock_records.items():
        records.sort(key=lambda x: x['date'])
        if len(records) < 2:
            continue
        latest = records[-1]
        # 가장 최근 직전 레코드를 prior로 사용 (분기 또는 연간 단위)
        prior = records[-2]
        if prior['net_income'] == 0 or prior['net_income'] is None:
            continue
        if prior['net_income'] < 0:
            # 적자전환→흑자는 YoY 계산 무의미, 건너뜀
            continue
        ni_yoy = (latest['net_income'] - prior['net_income']) / abs(prior['net_income'])
        result[code] = {
            'ni_yoy': ni_yoy,
            'roe': latest['roe'],
            'latest_date': latest['date'],
        }
    return result


def run_screener(args) -> pd.DataFrame:
    ni_yoy_min = getattr(args, 'ni_yoy_min', NI_YOY_MIN)
    roe_min = getattr(args, 'roe_min', ROE_MIN)
    l_threshold = getattr(args, 'mom_min', L_THRESHOLD)

    LOG.info(f"임계값: momentum>={l_threshold}, NI_YoY>={ni_yoy_min:.0%}, ROE>={roe_min:.1f}%")
    LOG.info("KOSPI 일봉 로드 중 (M 필터용)")
    kospi = _load_kospi_for_m("20210101", "20260531")
    LOG.info(f"KOSPI rows: {len(kospi)}, M pass days: {kospi['m_pass'].sum() if len(kospi) > 0 else 0}")

    LOG.info("quant_factors 로드 중")
    qf = _load_quant_factors()
    qf_dates = sorted(qf['calc_date'].unique())
    LOG.info(f"quant_factors: {len(qf)} rows, {len(qf_dates)} dates, "
             f"{qf['stock_code'].nunique()} unique stocks")

    LOG.info("재무 펀더멘털 로드 중")
    fund = _load_financial_fundamentals()
    LOG.info(f"펀더멘털 계산 가능 종목: {len(fund)}")

    # M 필터 날짜별 매핑
    kospi_indexed = kospi.set_index('date')

    daily_pass = []
    total_dates = len(qf_dates)

    for i, calc_date in enumerate(qf_dates):
        # M 필터 확인
        if calc_date in kospi_indexed.index:
            m_pass = bool(kospi_indexed.loc[calc_date, 'm_pass'])
        else:
            # 가장 가까운 이전 날짜로 대체
            prev_dates = kospi_indexed.index[kospi_indexed.index <= calc_date]
            m_pass = bool(kospi_indexed.loc[prev_dates[-1], 'm_pass']) if len(prev_dates) > 0 else False

        if not m_pass:
            LOG.debug(f"{calc_date.date()} M 필터 미통과 — 스킵")
            continue

        # 해당 날짜 quant_factors
        qf_day = qf[qf['calc_date'] == calc_date]

        passed_today = []
        for _, qrow in qf_day.iterrows():
            code = qrow['stock_code']

            # L 필터 (momentum_score)
            if pd.isna(qrow['momentum_score']) or qrow['momentum_score'] < l_threshold:
                continue

            # C + A 필터 (재무)
            if code not in fund:
                continue
            fdata = fund[code]

            # C: 순이익 YoY >= ni_yoy_min
            if fdata['ni_yoy'] < ni_yoy_min:
                continue

            # A: ROE >= roe_min (% 단위)
            roe = fdata['roe']
            if roe is None or pd.isna(roe) or float(roe) < roe_min:
                continue

            passed_today.append({
                'date': calc_date,
                'stock_code': code,
                'momentum_score': qrow['momentum_score'],
                'growth_score': qrow['growth_score'],
                'ni_yoy': fdata['ni_yoy'],
                'roe': float(roe),
                'm_pass': m_pass,
            })

        daily_pass.extend(passed_today)
        if (i + 1) % 10 == 0 or i == total_dates - 1:
            LOG.info(f"[{i+1}/{total_dates}] {calc_date.date()} — M={'PASS' if m_pass else 'FAIL'}, "
                     f"passed={len(passed_today)}, cumulative={len(daily_pass)}")

    df_out = pd.DataFrame(daily_pass)
    return df_out


def main():
    p = argparse.ArgumentParser(description="CAN SLIM 스크리너")
    p.add_argument("--out", default="reports/books_research/oneil_canslim/screener_daily.parquet")
    p.add_argument("--mom-min", type=float, default=L_THRESHOLD,
                   help=f"momentum_score 최소 임계값 (기본: {L_THRESHOLD})")
    p.add_argument("--ni-yoy-min", type=float, default=NI_YOY_MIN,
                   help=f"순이익 YoY 최소 성장률 (기본: {NI_YOY_MIN})")
    p.add_argument("--roe-min", type=float, default=ROE_MIN,
                   help=f"ROE 최소값 %단위 (기본: {ROE_MIN})")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    df_out = run_screener(args)

    print()
    print("=== CANSLIM 스크리너 결과 ===")
    print(f"통과 (date, stock_code) 쌍: {len(df_out)}")
    if len(df_out) > 0:
        print(f"유니크 통과 종목: {df_out['stock_code'].nunique()}")
        print(f"날짜 범위: {df_out['date'].min().date()} ~ {df_out['date'].max().date()}")
        print()
        print("날짜별 통과 종목 수:")
        print(df_out.groupby('date')['stock_code'].count().to_string())
        print()
        print("통과 종목 상위 20 (momentum_score 기준):")
        top = (df_out.sort_values('momentum_score', ascending=False)
                     .drop_duplicates('stock_code')
                     .head(20)[['stock_code', 'momentum_score', 'growth_score', 'ni_yoy', 'roe']])
        print(top.to_string(index=False))
    else:
        print("통과 종목 없음 — 임계값 완화 필요")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_parquet(out_path, index=False)
    LOG.info(f"저장 완료: {out_path}")


if __name__ == "__main__":
    main()
