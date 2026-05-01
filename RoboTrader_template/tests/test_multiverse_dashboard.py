"""
D3: Plotly 멀티버스 대시보드 단위 테스트
==========================================

테스트 항목:
- test_render_heatmap_basic: 히트맵 Figure 생성 및 데이터 검증
- test_render_equity_overlay_top10: 자산 곡선 오버레이 생성
- test_render_stability_grade: 등급 분포 차트 생성
- test_render_dashboard_combines_all: HTML 파일에 3 차트 모두 포함
- test_plotly_import_fallback: plotly 미설치 시 graceful skip
"""

import pytest
import sys
from dataclasses import dataclass, field
from typing import Dict, List
from unittest.mock import patch, MagicMock


# ============================================================================
# 테스트용 MultiverseResult / BacktestResult 스텁
# ============================================================================

@dataclass
class _BacktestResult:
    total_return: float = 0.05
    win_rate: float = 0.55
    avg_profit: float = 0.01
    max_drawdown: float = 0.08
    sharpe_ratio: float = 1.2
    calmar_ratio: float = 0.6
    sortino_ratio: float = 1.5
    profit_loss_ratio: float = 1.3
    total_trades: int = 20
    trades: List[Dict] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    sells_by_reason: Dict[str, int] = field(default_factory=dict)
    candidate_pool_hits: int = 0


@dataclass
class _MultiverseResult:
    results: List[Dict]
    total_combinations: int = 9
    filtered_count: int = 9
    elapsed_seconds: float = 1.23

    def top(self, n: int = 10, sort_by: str = "calmar_ratio"):
        import pandas as pd

        rows = []
        for item in self.results:
            row = {}
            for k, v in item["params"].items():
                col_name = k.split(".")[-1]
                row[col_name] = v
            r = item["result"]
            row["total_return"] = round(r.total_return, 4)
            row["win_rate"] = round(r.win_rate, 4)
            row["sharpe_ratio"] = round(r.sharpe_ratio, 4)
            row["calmar_ratio"] = round(r.calmar_ratio, 4)
            row["sortino_ratio"] = round(r.sortino_ratio, 4)
            row["max_drawdown"] = round(r.max_drawdown, 4)
            row["total_trades"] = r.total_trades
            row["stability_grade"] = item.get("stability_grade", "B")
            rows.append(row)

        df = pd.DataFrame(rows)
        if sort_by in df.columns:
            ascending = sort_by == "max_drawdown"
            df = df.sort_values(sort_by, ascending=ascending)
        return df.head(n).reset_index(drop=True)


def _make_multiverse_result(n_combos: int = 9) -> _MultiverseResult:
    """파라미터 3×3 그리드 테스트 결과 생성."""
    results = []
    ma_values = [3, 5, 10]
    rsi_values = [25, 30, 35]
    grades = ["S", "A", "B", "C", "D", "F", "A", "B", "C"]
    idx = 0
    for ma in ma_values:
        for rsi in rsi_values:
            r = _BacktestResult(
                calmar_ratio=0.3 + idx * 0.1,
                total_return=0.02 + idx * 0.005,
                equity_curve=[10_000_000 + i * 1000 for i in range(30)],
            )
            results.append({
                "params": {
                    "parameters.ma_short_period": ma,
                    "parameters.rsi_oversold": rsi,
                },
                "result": r,
                "stability_grade": grades[idx % len(grades)],
                "stability_score": 60 + idx * 3,
            })
            idx += 1
    return _MultiverseResult(results=results[:n_combos])


# ============================================================================
# plotly 사용 가능 여부 확인
# ============================================================================

try:
    import plotly
    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False

pytestmark_plotly = pytest.mark.skipif(
    not _HAS_PLOTLY,
    reason="plotly 미설치 — D3 차트 테스트 건너뜀 (test_plotly_import_fallback은 항상 실행)"
)


# ============================================================================
# 히트맵 테스트
# ============================================================================

@pytestmark_plotly
class TestRenderParamHeatmap:
    def test_render_heatmap_basic(self, tmp_path):
        """알려진 그리드 결과로 히트맵 Figure 생성, 데이터 검증."""
        from output.multiverse_dashboard import render_param_heatmap

        mv = _make_multiverse_result()
        fig = render_param_heatmap(
            mv,
            x_param="ma_short_period",
            y_param="rsi_oversold",
            metric="calmar_ratio",
        )
        assert fig is not None
        # Heatmap trace가 존재해야 함
        assert len(fig.data) > 0
        heatmap_trace = fig.data[0]
        assert hasattr(heatmap_trace, "z")
        assert heatmap_trace.z is not None

    def test_render_heatmap_missing_param(self):
        """존재하지 않는 파라미터 컬럼 입력 시 None 반환."""
        from output.multiverse_dashboard import render_param_heatmap

        mv = _make_multiverse_result()
        fig = render_param_heatmap(mv, x_param="nonexistent_x", y_param="rsi_oversold")
        assert fig is None

    def test_render_heatmap_empty_result(self):
        """결과 없는 MultiverseResult 입력 시 None 반환."""
        from output.multiverse_dashboard import render_param_heatmap

        mv = _MultiverseResult(results=[])
        fig = render_param_heatmap(mv, x_param="ma_short_period", y_param="rsi_oversold")
        assert fig is None

    def test_render_heatmap_title_contains_metric(self):
        """히트맵 제목에 metric 이름이 포함된다."""
        from output.multiverse_dashboard import render_param_heatmap

        mv = _make_multiverse_result()
        fig = render_param_heatmap(mv, x_param="ma_short_period", y_param="rsi_oversold",
                                   metric="calmar_ratio")
        assert fig is not None
        assert "calmar_ratio" in fig.layout.title.text


# ============================================================================
# 자산 곡선 오버레이 테스트
# ============================================================================

@pytestmark_plotly
class TestRenderEquityOverlay:
    def test_render_equity_overlay_top10(self):
        """top10 equity_curve 오버레이 Figure 생성."""
        from output.multiverse_dashboard import render_equity_overlay

        mv = _make_multiverse_result(n_combos=9)
        fig = render_equity_overlay(mv, top_n=5)
        assert fig is not None
        # 5개 이하 trace (equity_curve 없는 항목 제외)
        assert len(fig.data) <= 5
        assert len(fig.data) > 0

    def test_render_equity_overlay_empty_result(self):
        """결과 없는 MultiverseResult 입력 시 None 반환."""
        from output.multiverse_dashboard import render_equity_overlay

        mv = _MultiverseResult(results=[])
        fig = render_equity_overlay(mv)
        assert fig is None

    def test_render_equity_overlay_trace_names(self):
        """각 trace 이름에 calmar 정보가 포함된다."""
        from output.multiverse_dashboard import render_equity_overlay

        mv = _make_multiverse_result(n_combos=3)
        fig = render_equity_overlay(mv, top_n=3)
        assert fig is not None
        for trace in fig.data:
            assert "calmar" in trace.name.lower()


# ============================================================================
# 안정성 등급 분포 테스트
# ============================================================================

@pytestmark_plotly
class TestRenderStabilityGradeDistribution:
    def test_render_stability_grade(self):
        """등급별 분포 Bar Figure 생성."""
        from output.multiverse_dashboard import render_stability_grade_distribution

        mv = _make_multiverse_result()
        fig = render_stability_grade_distribution(mv)
        assert fig is not None
        assert len(fig.data) > 0
        bar_trace = fig.data[0]
        # x축이 등급 문자열
        assert bar_trace.x is not None
        assert len(bar_trace.x) > 0

    def test_render_stability_grade_empty_result(self):
        """결과 없는 MultiverseResult 입력 시 None 반환."""
        from output.multiverse_dashboard import render_stability_grade_distribution

        mv = _MultiverseResult(results=[])
        fig = render_stability_grade_distribution(mv)
        assert fig is None

    def test_render_stability_grade_bar_values_sum(self):
        """등급 분포 bar y값 합계 = 전체 조합 수."""
        from output.multiverse_dashboard import render_stability_grade_distribution

        mv = _make_multiverse_result(n_combos=9)
        fig = render_stability_grade_distribution(mv)
        assert fig is not None
        total = sum(int(y) for y in fig.data[0].y)
        assert total == 9


# ============================================================================
# 통합 대시보드 HTML 출력 테스트
# ============================================================================

@pytestmark_plotly
class TestRenderDashboard:
    def test_render_dashboard_combines_all(self, tmp_path):
        """HTML 파일에 3 차트가 모두 포함된다."""
        from output.multiverse_dashboard import render_dashboard

        mv = _make_multiverse_result()
        out_file = str(tmp_path / "dashboard.html")
        result_path = render_dashboard(
            mv,
            output_path=out_file,
            x_param="ma_short_period",
            y_param="rsi_oversold",
        )
        assert result_path is not None
        import os
        assert os.path.exists(result_path)

        content = open(result_path, encoding="utf-8").read()
        assert "파라미터 히트맵" in content
        assert "자산 곡선 오버레이" in content
        assert "안정성 등급 분포" in content

    def test_render_dashboard_html_structure(self, tmp_path):
        """생성된 HTML이 기본 구조(DOCTYPE, html, head, body)를 포함한다."""
        from output.multiverse_dashboard import render_dashboard

        mv = _make_multiverse_result()
        out_file = str(tmp_path / "dashboard2.html")
        render_dashboard(mv, output_path=out_file,
                         x_param="ma_short_period", y_param="rsi_oversold")

        content = open(out_file, encoding="utf-8").read()
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

    def test_render_dashboard_summary_stats(self, tmp_path):
        """HTML에 total_combinations / filtered_count 수치가 포함된다."""
        from output.multiverse_dashboard import render_dashboard

        mv = _make_multiverse_result()
        out_file = str(tmp_path / "dashboard3.html")
        render_dashboard(mv, output_path=out_file,
                         x_param="ma_short_period", y_param="rsi_oversold")

        content = open(out_file, encoding="utf-8").read()
        assert str(mv.total_combinations) in content
        assert str(mv.filtered_count) in content

    def test_render_dashboard_empty_result(self, tmp_path):
        """결과 없는 MultiverseResult 입력 시 None 반환 (파일 미생성)."""
        from output.multiverse_dashboard import render_dashboard

        mv = _MultiverseResult(results=[])
        out_file = str(tmp_path / "empty.html")
        result = render_dashboard(mv, output_path=out_file)
        assert result is None

    def test_render_dashboard_auto_param_selection(self, tmp_path):
        """x_param/y_param 미지정 시 자동 선택으로 정상 동작."""
        from output.multiverse_dashboard import render_dashboard

        mv = _make_multiverse_result()
        out_file = str(tmp_path / "auto.html")
        result_path = render_dashboard(mv, output_path=out_file)
        # 파라미터가 2개 있으므로 자동 선택 후 파일 생성
        assert result_path is not None
        import os
        assert os.path.exists(result_path)


# ============================================================================
# plotly 미설치 graceful fallback 테스트 (항상 실행)
# ============================================================================

class TestPlotlyImportFallback:
    def test_plotly_import_fallback(self):
        """plotly 미설치 환경에서 render_* 함수들이 None을 반환한다."""
        # plotly를 sys.modules에서 임시로 제거하여 미설치 환경 시뮬레이션
        plotly_modules = {k: v for k, v in sys.modules.items() if k.startswith("plotly")}
        dashboard_module_key = "output.multiverse_dashboard"

        for mod in list(plotly_modules.keys()):
            sys.modules.pop(mod, None)
        sys.modules.pop(dashboard_module_key, None)

        # _PLOTLY_AVAILABLE=False 패치
        with patch.dict("sys.modules", {"plotly": None, "plotly.graph_objects": None,
                                        "plotly.express": None,
                                        "plotly.subplots": None}):
            # 모듈 재임포트
            import importlib
            try:
                import output.multiverse_dashboard as dashboard_mod
                importlib.reload(dashboard_mod)

                # 패치된 상태에서 _PLOTLY_AVAILABLE은 False가 되어야 함
                # (이미 import된 모듈이라 reload가 필요하지만 sys.modules 패치로 충분)
                # 실제로는 None 반환 로직 확인
                mv = _make_multiverse_result(n_combos=1)
                with patch.object(dashboard_mod, "_PLOTLY_AVAILABLE", False):
                    result1 = dashboard_mod.render_param_heatmap(
                        mv, x_param="ma_short_period", y_param="rsi_oversold"
                    )
                    result2 = dashboard_mod.render_equity_overlay(mv)
                    result3 = dashboard_mod.render_stability_grade_distribution(mv)
                    result4 = dashboard_mod.render_dashboard(mv, output_path="/tmp/test.html")

                assert result1 is None
                assert result2 is None
                assert result3 is None
                assert result4 is None
            finally:
                # 원래 plotly 모듈 복원
                for mod_name, mod in plotly_modules.items():
                    sys.modules[mod_name] = mod
