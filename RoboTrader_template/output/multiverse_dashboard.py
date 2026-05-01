"""
Plotly 기반 멀티버스 시각화 대시보드 (D3)
==========================================

MultiverseResult를 받아 3종 차트를 생성하고 단일 HTML 파일로 출력합니다.

함수:
    render_param_heatmap  — 파라미터 그리드 히트맵
    render_equity_overlay — 상위 N개 자산곡선 오버레이
    render_stability_grade_distribution — 안정성 등급 분포
    render_dashboard      — 위 3개를 HTML 단일 페이지로 통합

plotly 미설치 환경에서는 graceful import skip (ImportError 무시).

Usage:
    from output.multiverse_dashboard import render_dashboard
    render_dashboard(mv_result, output_path="output/dashboard.html")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# plotly optional import — 미설치 환경에서 graceful skip
try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False
    go = None  # type: ignore[assignment]
    px = None  # type: ignore[assignment]
    make_subplots = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from backtest.multiverse import MultiverseResult


def _check_plotly() -> bool:
    """plotly 사용 가능 여부 반환. 없으면 경고 로그."""
    if not _PLOTLY_AVAILABLE:
        logger.warning(
            "plotly가 설치되지 않아 대시보드를 생성할 수 없습니다. "
            "pip install plotly 를 실행하세요."
        )
        return False
    return True


# ============================================================================
# 차트 1: 파라미터 히트맵
# ============================================================================

def render_param_heatmap(
    multiverse_result: "MultiverseResult",
    x_param: str,
    y_param: str,
    metric: str = "calmar_ratio",
) -> Optional["go.Figure"]:
    """파라미터 그리드 결과를 2D 히트맵으로 시각화.

    Args:
        multiverse_result: MultiverseEngine.run() 반환 결과.
        x_param: X축 파라미터명 (파라미터 키의 마지막 부분, e.g. "ma_short_period").
        y_param: Y축 파라미터명.
        metric: 색상으로 표현할 성능 지표 컬럼명 (기본 "calmar_ratio").

    Returns:
        plotly Figure 또는 None (plotly 미설치 / 데이터 없음).
    """
    if not _check_plotly():
        return None

    df = multiverse_result.top(n=len(multiverse_result.results), sort_by=metric)
    if df.empty:
        logger.warning("render_param_heatmap: 결과 없음")
        return None

    # x_param / y_param 컬럼 존재 확인
    missing = [p for p in (x_param, y_param) if p not in df.columns]
    if missing:
        logger.warning(f"render_param_heatmap: 파라미터 컬럼 없음 — {missing}")
        return None
    if metric not in df.columns:
        logger.warning(f"render_param_heatmap: 메트릭 컬럼 없음 — {metric}")
        return None

    pivot = df.pivot_table(index=y_param, columns=x_param, values=metric, aggfunc="mean")

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values.tolist(),
            x=[str(v) for v in pivot.columns.tolist()],
            y=[str(v) for v in pivot.index.tolist()],
            colorscale="RdYlGn",
            colorbar=dict(title=metric),
            hoverongaps=False,
        )
    )
    fig.update_layout(
        title=f"파라미터 히트맵 — {metric}",
        xaxis_title=x_param,
        yaxis_title=y_param,
        template="plotly_white",
    )
    return fig


# ============================================================================
# 차트 2: 자산 곡선 오버레이
# ============================================================================

def render_equity_overlay(
    multiverse_result: "MultiverseResult",
    top_n: int = 10,
) -> Optional["go.Figure"]:
    """상위 N개 파라미터 조합의 자산 곡선을 하나의 차트에 오버레이.

    Args:
        multiverse_result: MultiverseEngine.run() 반환 결과.
        top_n: 표시할 상위 조합 수 (기본 10).

    Returns:
        plotly Figure 또는 None.
    """
    if not _check_plotly():
        return None

    if not multiverse_result.results:
        logger.warning("render_equity_overlay: 결과 없음")
        return None

    # calmar_ratio 기준 상위 top_n 선택
    df_top = multiverse_result.top(n=top_n, sort_by="calmar_ratio")
    if df_top.empty:
        return None

    # top() 결과의 인덱스를 results 리스트와 매칭하기 위해
    # 다시 results를 calmar_ratio 내림차순 정렬
    from backtest.engine import BacktestResult as _BR
    sorted_items = sorted(
        multiverse_result.results,
        key=lambda item: item["result"].calmar_ratio,
        reverse=True,
    )[:top_n]

    fig = go.Figure()

    for rank, item in enumerate(sorted_items, start=1):
        result: "_BR" = item["result"]
        equity = result.equity_curve
        if not equity:
            continue

        # 파라미터 라벨 생성 (짧게)
        param_parts = [f"{k.split('.')[-1]}={v}" for k, v in item["params"].items()]
        label = ", ".join(param_parts) if param_parts else f"조합{rank}"
        # Calmar 표기
        calmar = result.calmar_ratio
        trace_name = f"#{rank} {label} (calmar={calmar:.2f})"

        fig.add_trace(
            go.Scatter(
                y=equity,
                mode="lines",
                name=trace_name,
                line=dict(width=1.5),
                hovertemplate=f"{trace_name}<br>날짜인덱스=%{{x}}<br>자산=%{{y:,.0f}}<extra></extra>",
            )
        )

    fig.update_layout(
        title=f"자산 곡선 오버레이 — 상위 {top_n}개",
        xaxis_title="날짜 인덱스",
        yaxis_title="자산 (원)",
        template="plotly_white",
        legend=dict(orientation="v", x=1.01, y=1),
    )
    return fig


# ============================================================================
# 차트 3: 안정성 등급 분포
# ============================================================================

def render_stability_grade_distribution(
    multiverse_result: "MultiverseResult",
) -> Optional["go.Figure"]:
    """안정성 등급(stability_grade) 분포를 막대 차트로 시각화.

    Args:
        multiverse_result: MultiverseEngine.run() 반환 결과.

    Returns:
        plotly Figure 또는 None.
    """
    if not _check_plotly():
        return None

    if not multiverse_result.results:
        logger.warning("render_stability_grade_distribution: 결과 없음")
        return None

    df = multiverse_result.top(n=len(multiverse_result.results), sort_by="calmar_ratio")
    if df.empty or "stability_grade" not in df.columns:
        logger.warning("render_stability_grade_distribution: stability_grade 컬럼 없음")
        return None

    grade_counts = df["stability_grade"].value_counts().reset_index()
    grade_counts.columns = ["grade", "count"]

    # 등급 순서 정의 (S > A > B > C > D > F > 미분류)
    grade_order = ["S", "A", "B", "C", "D", "F"]
    grade_colors = {
        "S": "#2ecc71",
        "A": "#27ae60",
        "B": "#f1c40f",
        "C": "#e67e22",
        "D": "#e74c3c",
        "F": "#c0392b",
    }

    ordered_grades: List[str] = []
    ordered_counts: List[int] = []
    ordered_colors: List[str] = []

    for g in grade_order:
        row = grade_counts[grade_counts["grade"] == g]
        cnt = int(row["count"].values[0]) if not row.empty else 0
        ordered_grades.append(g)
        ordered_counts.append(cnt)
        ordered_colors.append(grade_colors.get(g, "#95a5a6"))

    # 기타 등급 추가
    known = set(grade_order)
    for _, row in grade_counts.iterrows():
        g = str(row["grade"])
        if g not in known:
            ordered_grades.append(g)
            ordered_counts.append(int(row["count"]))
            ordered_colors.append("#95a5a6")

    fig = go.Figure(
        data=go.Bar(
            x=ordered_grades,
            y=ordered_counts,
            marker_color=ordered_colors,
            text=ordered_counts,
            textposition="auto",
        )
    )
    fig.update_layout(
        title="파라미터 안정성 등급 분포",
        xaxis_title="안정성 등급",
        yaxis_title="조합 수",
        template="plotly_white",
    )
    return fig


# ============================================================================
# 통합 대시보드 — HTML 단일 페이지
# ============================================================================

def render_dashboard(
    multiverse_result: "MultiverseResult",
    output_path: str = "output/multiverse_dashboard.html",
    x_param: Optional[str] = None,
    y_param: Optional[str] = None,
    metric: str = "calmar_ratio",
    top_n: int = 10,
) -> Optional[str]:
    """3개 차트를 HTML 단일 페이지로 통합 출력.

    Args:
        multiverse_result: MultiverseEngine.run() 반환 결과.
        output_path: 저장할 HTML 파일 경로.
        x_param: 히트맵 X축 파라미터명. None이면 첫 번째 파라미터 자동 선택.
        y_param: 히트맵 Y축 파라미터명. None이면 두 번째 파라미터 자동 선택.
        metric: 히트맵 색상 지표 (기본 "calmar_ratio").
        top_n: 자산 곡선 오버레이 상위 N개.

    Returns:
        저장된 파일 경로 문자열 또는 None (실패 시).
    """
    if not _check_plotly():
        return None

    if not multiverse_result.results:
        logger.warning("render_dashboard: 결과 없음")
        return None

    # x_param / y_param 자동 선택
    sample_params = list(multiverse_result.results[0]["params"].keys())
    param_short = [k.split(".")[-1] for k in sample_params]

    resolved_x = x_param or (param_short[0] if len(param_short) > 0 else None)
    resolved_y = y_param or (param_short[1] if len(param_short) > 1 else resolved_x)

    figures = []

    # 차트 1: 히트맵 (파라미터 2개 이상일 때만)
    if resolved_x and resolved_y and resolved_x != resolved_y:
        fig_heatmap = render_param_heatmap(
            multiverse_result, x_param=resolved_x, y_param=resolved_y, metric=metric
        )
        if fig_heatmap is not None:
            figures.append(("파라미터 히트맵", fig_heatmap))

    # 차트 2: 자산 곡선 오버레이
    fig_equity = render_equity_overlay(multiverse_result, top_n=top_n)
    if fig_equity is not None:
        figures.append(("자산 곡선 오버레이", fig_equity))

    # 차트 3: 등급 분포
    fig_grade = render_stability_grade_distribution(multiverse_result)
    if fig_grade is not None:
        figures.append(("안정성 등급 분포", fig_grade))

    if not figures:
        logger.warning("render_dashboard: 생성된 차트 없음")
        return None

    # HTML 조합
    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='ko'><head>",
        "<meta charset='utf-8'>",
        "<title>Multiverse Dashboard</title>",
        "<style>body{font-family:sans-serif;margin:20px;background:#f8f9fa;}"
        "h1{color:#2c3e50;}h2{color:#34495e;border-bottom:2px solid #3498db;padding-bottom:4px;}"
        ".chart-section{background:#fff;border-radius:8px;padding:16px;margin-bottom:24px;"
        "box-shadow:0 2px 8px rgba(0,0,0,0.08);}</style>",
        "</head><body>",
        "<h1>멀티버스 파라미터 최적화 대시보드</h1>",
        f"<p>총 조합: {multiverse_result.total_combinations} | "
        f"필터 통과: {multiverse_result.filtered_count} | "
        f"소요 시간: {multiverse_result.elapsed_seconds:.1f}초</p>",
    ]

    for title, fig in figures:
        html_parts.append(f"<div class='chart-section'><h2>{title}</h2>")
        html_parts.append(fig.to_html(full_html=False, include_plotlyjs="cdn"))
        html_parts.append("</div>")

    html_parts.append("</body></html>")
    html_content = "\n".join(html_parts)

    # 파일 저장
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    logger.info(f"대시보드 저장: {out_path}")
    return str(out_path)
