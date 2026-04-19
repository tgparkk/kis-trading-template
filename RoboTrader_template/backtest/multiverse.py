"""
MultiverseEngine — 범용 파라미터 스윕 + 안정성 분석
=====================================================

BacktestEngine 위에서 파라미터 그리드 탐색을 수행합니다.
- itertools.product로 모든 조합 생성
- ThreadPoolExecutor로 병렬 실행 (numpy는 GIL 해제)
- 이웃 파라미터 기반 안정성(과적합) 분석
- Markdown 리포트 출력

Usage:
    from backtest import MultiverseEngine
    from strategies.sample.strategy import SampleStrategy

    mv = MultiverseEngine(
        strategy_class=SampleStrategy,
        daily_data=data,
        stock_codes=["005930", "000660"],
    )
    mv.add_param("parameters.ma_short_period", [3, 5, 10])
    mv.add_param("parameters.rsi_oversold", [25, 30, 35])
    results = mv.run(min_trades=20, n_jobs=4)
    results.to_markdown("output/multiverse.md")
"""

from __future__ import annotations

import copy
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Dict, List, Optional, Type

import numpy as np
import pandas as pd

from backtest.engine import BacktestEngine, BacktestResult
from strategies.base import BaseStrategy


# ============================================================================
# MultiverseResult — 전체 결과 컨테이너
# ============================================================================

@dataclass
class MultiverseResult:
    """멀티버스 전체 결과 컨테이너.

    Attributes:
        results: 모든 조합의 결과 리스트. 각 원소는
                 {"params": dict, "result": BacktestResult,
                  "stability_score": float|None, "stability_grade": str} 형태.
        total_combinations: 시도한 전체 파라미터 조합 수.
        filtered_count: min_trades 필터를 통과한 조합 수.
        elapsed_seconds: 전체 소요 시간 (초).
    """

    results: List[Dict]
    total_combinations: int
    filtered_count: int
    elapsed_seconds: float

    # -----------------------------------------------------------------------
    # top() — 상위 N개 DataFrame
    # -----------------------------------------------------------------------

    def top(self, n: int = 10, sort_by: str = "sharpe_ratio") -> pd.DataFrame:
        """상위 N개 결과를 DataFrame으로 반환.

        Args:
            n: 반환할 결과 수.
            sort_by: 정렬 기준 컬럼명.
                     BacktestResult 필드 이름 사용:
                     "sharpe_ratio", "total_return", "win_rate",
                     "max_drawdown", "total_trades" 등.
                     "stability_score"도 사용 가능.

        Returns:
            컬럼 구성:
            - 각 파라미터명 (예: ma_short_period, rsi_oversold)
            - total_return, win_rate, sharpe_ratio,
              max_drawdown, total_trades, stability_grade
        """
        if not self.results:
            return pd.DataFrame()

        rows = []
        for item in self.results:
            row: Dict[str, Any] = {}
            # 파라미터를 개별 컬럼으로 펼침 (점 구분 키에서 마지막 부분만 사용)
            for k, v in item["params"].items():
                col_name = k.split(".")[-1]
                row[col_name] = v
            # BacktestResult 주요 지표
            r: BacktestResult = item["result"]
            row["total_return"] = round(r.total_return, 4)
            row["win_rate"] = round(r.win_rate, 4)
            row["sharpe_ratio"] = round(r.sharpe_ratio, 4)
            row["max_drawdown"] = round(r.max_drawdown, 4)
            row["total_trades"] = r.total_trades
            # Sharpe/PnL 별도 안정성
            row["sharpe_stability_score"] = item.get("sharpe_stability_score")
            row["sharpe_stability_grade"] = item.get("sharpe_stability_grade", "")
            row["pnl_stability_score"] = item.get("pnl_stability_score")
            row["pnl_stability_grade"] = item.get("pnl_stability_grade", "")
            # 호환용 (기존 코드 경로)
            row["stability_score"] = item.get("stability_score")
            row["stability_grade"] = item.get("stability_grade", "")
            rows.append(row)

        df = pd.DataFrame(rows)

        # 정렬: max_drawdown은 오름차순(낮을수록 좋음), 나머지는 내림차순
        if sort_by in df.columns:
            ascending = sort_by == "max_drawdown"
            df = df.sort_values(sort_by, ascending=ascending)

        return df.head(n).reset_index(drop=True)

    # -----------------------------------------------------------------------
    # stability_report() — 텍스트 안정성 리포트
    # -----------------------------------------------------------------------

    def stability_report(self, top_n: int = 5, metric: str = "pnl") -> str:
        """상위 top_n 결과의 파라미터 안정성 리포트 (텍스트).

        Args:
            top_n: 리포트에 포함할 상위 결과 수.
            metric: "pnl" (기본, 수익률 기준) 또는 "sharpe" (Sharpe 기준).

        Returns:
            텍스트 형태의 안정성 리포트 문자열.
        """
        if metric not in ("pnl", "sharpe"):
            metric = "pnl"
        score_key = f"{metric}_stability_score"
        grade_key = f"{metric}_stability_grade"
        metric_label = "PnL(수익률)" if metric == "pnl" else "Sharpe"

        lines = [
            "=" * 60,
            f"파라미터 안정성 리포트 — {metric_label} 기준",
            "=" * 60,
        ]

        targets = self.results[:top_n]
        if not targets:
            lines.append("(결과 없음)")
            return "\n".join(lines)

        for i, item in enumerate(targets, start=1):
            r: BacktestResult = item["result"]
            lines.append(f"\n#{i} 파라미터:")
            for k, v in item["params"].items():
                col = k.split(".")[-1]
                lines.append(f"  {col}: {v}")

            lines.append(f"  샤프: {r.sharpe_ratio:.3f}")
            lines.append(f"  수익률: {r.total_return:+.2%}")
            lines.append(f"  거래수: {r.total_trades}건")

            score = item.get(score_key)
            grade = item.get(grade_key, "판정불가")

            if score is not None:
                lines.append(f"  이웃 {metric_label} 비율: {score:.3f} (원본 대비 {score*100:.1f}%)")
            else:
                lines.append(f"  이웃 {metric_label} 비율: -")
            lines.append(f"  판정: [{grade}]")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # to_markdown() — Markdown 파일 저장
    # -----------------------------------------------------------------------

    def to_markdown(self, path: str, top_n: int = 20) -> None:
        """결과를 Markdown 파일로 저장.

        Args:
            path: 저장할 파일 경로.
            top_n: 테이블에 포함할 상위 결과 수.
        """
        lines = []

        # --- 헤더 ---
        lines.append("# MultiverseEngine 결과 리포트")
        lines.append("")
        lines.append(f"- **전체 조합**: {self.total_combinations:,}개")
        lines.append(f"- **min_trades 통과**: {self.filtered_count:,}개")
        lines.append(f"- **소요 시간**: {self.elapsed_seconds:.1f}초")
        lines.append("")

        # --- Top N 테이블 ---
        lines.append(f"## Top {top_n} 결과 (Sharpe 기준)")
        lines.append("")

        df = self.top(n=top_n, sort_by="sharpe_ratio")
        if df.empty:
            lines.append("_(결과 없음)_")
        else:
            lines.append(df.to_markdown(index=True))

        lines.append("")

        # --- 안정성 리포트 ---
        lines.append("## 안정성 리포트")
        lines.append("")
        lines.append("```")
        lines.append(self.stability_report(top_n=5))
        lines.append("```")
        lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logging.getLogger("backtest.multiverse").info(f"Markdown 저장: {path}")


# ============================================================================
# MultiverseEngine — 파라미터 그리드 탐색 엔진
# ============================================================================

class MultiverseEngine:
    """
    BacktestEngine 위에서 파라미터 그리드 탐색 + 병렬 실행 + 안정성 분석.

    사용 예:
        mv = MultiverseEngine(
            strategy_class=SampleStrategy,
            daily_data=data,
            stock_codes=["005930", "000660"],
        )
        mv.add_param("parameters.ma_short_period", [3, 5, 10])
        mv.add_param("parameters.rsi_oversold", [25, 30, 35])
        mv.add_param("risk_management.stop_loss_pct", [0.05, 0.10])
        results = mv.run(min_trades=20, n_jobs=4)
        print(results.top(10))
        results.to_markdown("output/multiverse.md")
    """

    def __init__(
        self,
        strategy_class: Type[BaseStrategy],
        daily_data: Dict[str, pd.DataFrame],
        stock_codes: List[str],
        initial_capital: float = 10_000_000,
        max_positions: int = 5,
        position_size_pct: float = 0.2,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """
        Args:
            strategy_class: BaseStrategy 서브클래스 (인스턴스가 아닌 클래스).
            daily_data: {종목코드: OHLCV DataFrame} 딕셔너리.
            stock_codes: 백테스트 대상 종목 코드 리스트.
            initial_capital: 초기 자본금 (원).
            max_positions: 동시 최대 보유 종목 수.
            position_size_pct: 종목당 투자 비율 (0.0~1.0).
            start_date: 백테스트 시작일 ("YYYY-MM-DD"), None이면 전체.
            end_date: 백테스트 종료일 ("YYYY-MM-DD"), None이면 전체.
        """
        self.strategy_class = strategy_class
        self.daily_data = daily_data
        self.stock_codes = stock_codes
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct
        self.start_date = start_date
        self.end_date = end_date
        # "parameters.rsi_oversold" -> [25, 30, 35] 형태로 저장
        self._param_grid: Dict[str, List[Any]] = {}
        self.logger = logging.getLogger("backtest.multiverse")

    # -----------------------------------------------------------------------
    # add_param() — 파라미터 범위 추가 (체이닝 지원)
    # -----------------------------------------------------------------------

    def add_param(self, key: str, values: List[Any]) -> "MultiverseEngine":
        """파라미터 범위 추가.

        Args:
            key: 점(.) 구분 경로. 예: "parameters.rsi_oversold",
                 "risk_management.stop_loss_pct"
            values: 탐색할 값 리스트. 예: [25, 30, 35]

        Returns:
            self — 체이닝 지원.
        """
        self._param_grid[key] = values
        return self

    # -----------------------------------------------------------------------
    # run() — 그리드 탐색 메인
    # -----------------------------------------------------------------------

    def run(
        self,
        min_trades: int = 20,
        n_jobs: int = 1,
        stability_threshold: float = 0.7,
    ) -> MultiverseResult:
        """파라미터 그리드 탐색 실행.

        Args:
            min_trades: 최소 거래 수 필터. 미달 시 결과에서 제외.
            n_jobs: 병렬 스레드 수. 1이면 순차 실행.
            stability_threshold: 안정성 판정 기준.
                                 이웃 평균 sharpe / 원본 sharpe >= 이 값이면 "안정".

        Returns:
            MultiverseResult: 필터링 + 정렬 + 안정성 분석 완료된 결과.
        """
        if not self._param_grid:
            self.logger.warning("파라미터 그리드가 비어있습니다. add_param()을 먼저 호출하세요.")
            return MultiverseResult(
                results=[], total_combinations=0,
                filtered_count=0, elapsed_seconds=0.0,
            )

        # 1. 파라미터 조합 생성
        keys = list(self._param_grid.keys())
        value_lists = [self._param_grid[k] for k in keys]
        combinations = list(product(*value_lists))
        total = len(combinations)
        self.logger.info(f"멀티버스 시작: {total}개 조합, {n_jobs} 스레드")

        start_time = time.time()

        # 2. 실행 (순차 또는 병렬)
        if n_jobs <= 1:
            raw_results = [self._run_single(keys, combo) for combo in combinations]
        else:
            raw_results = self._run_parallel(keys, combinations, n_jobs)

        # 3. min_trades 필터 + None 제거
        filtered = [
            r for r in raw_results
            if r is not None and r["result"].total_trades >= min_trades
        ]

        # 4. PnL(=total_return) 기준 내림차순 정렬 — 사장님 지침: PnL 1급 지표
        filtered.sort(key=lambda x: x["result"].total_return, reverse=True)

        # 5. 안정성 분석 — Sharpe/PnL 양쪽 계산
        self._analyze_stability(filtered, raw_results, keys, stability_threshold,
                                metric="sharpe_ratio", prefix="sharpe_")
        self._analyze_stability(filtered, raw_results, keys, stability_threshold,
                                metric="total_return", prefix="pnl_")
        # 호환용: 기존 stability_* 는 sharpe_* 와 동일
        for item in filtered:
            item["stability_score"] = item.get("sharpe_stability_score")
            item["stability_grade"] = item.get("sharpe_stability_grade", "")

        elapsed = time.time() - start_time
        self.logger.info(
            f"멀티버스 완료: {len(filtered)}/{total}개 조합 통과, {elapsed:.1f}초"
        )

        return MultiverseResult(
            results=filtered,
            total_combinations=total,
            filtered_count=len(filtered),
            elapsed_seconds=elapsed,
        )

    # -----------------------------------------------------------------------
    # _run_single() — 단일 조합 실행
    # -----------------------------------------------------------------------

    def _run_single(self, keys: List[str], combo: tuple) -> Optional[Dict]:
        """단일 파라미터 조합 백테스트 실행.

        전략 인스턴스를 새로 생성하여 상태 오염을 방지합니다.

        Args:
            keys: 파라미터 키 리스트. 예: ["parameters.ma_short_period", ...]
            combo: 해당 조합의 값 튜플. 예: (5, 30)

        Returns:
            {"params": dict, "result": BacktestResult, ...} 또는 None (실패 시).
        """
        # 전략 인스턴스 새로 생성 (상태 오염 방지)
        strategy = self.strategy_class()

        # config에 파라미터 주입 (점 구분 경로 → 중첩 dict)
        config = copy.deepcopy(strategy.config)
        params_dict = dict(zip(keys, combo))
        for key, value in params_dict.items():
            self._set_nested(config, key, value)
        strategy.config = config

        # BacktestEngine 생성 + 실행
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=self.initial_capital,
            max_positions=self.max_positions,
            position_size_pct=self.position_size_pct,
        )

        try:
            result = engine.run(
                stock_codes=self.stock_codes,
                daily_data=self.daily_data,
                start_date=self.start_date,
                end_date=self.end_date,
            )
            return {
                "params": params_dict,
                "result": result,
                # 호환용 (= sharpe_*)
                "stability_score": None,
                "stability_grade": "",
                # Sharpe/PnL 별도 저장 (PnL 1급 승격)
                "sharpe_stability_score": None,
                "sharpe_stability_grade": "",
                "pnl_stability_score": None,
                "pnl_stability_grade": "",
            }
        except Exception as e:
            self.logger.debug(f"조합 실패: {params_dict} — {e}")
            return None

    # -----------------------------------------------------------------------
    # _run_parallel() — ThreadPoolExecutor 병렬 실행
    # -----------------------------------------------------------------------

    def _run_parallel(
        self,
        keys: List[str],
        combinations: List[tuple],
        n_jobs: int,
    ) -> List[Optional[Dict]]:
        """ThreadPoolExecutor로 병렬 실행.

        ProcessPoolExecutor는 lambda/self 메서드 pickle 문제가 있으므로
        ThreadPoolExecutor를 사용합니다. numpy 연산은 GIL을 해제하므로
        CPU-bound 작업에서도 실질적인 병렬화 효과가 있습니다.

        Args:
            keys: 파라미터 키 리스트.
            combinations: 전체 파라미터 조합 리스트.
            n_jobs: 병렬 스레드 수.

        Returns:
            결과 리스트 (순서 보장 안 됨).
        """
        results: List[Optional[Dict]] = []
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            futures = {
                executor.submit(self._run_single, keys, combo): i
                for i, combo in enumerate(combinations)
            }
            done_count = 0
            total = len(futures)
            for future in as_completed(futures):
                done_count += 1
                if done_count % max(1, total // 10) == 0:
                    self.logger.info(f"  진행: {done_count}/{total}...")
                try:
                    results.append(future.result())
                except Exception:
                    results.append(None)
        return results

    # -----------------------------------------------------------------------
    # _set_nested() — 중첩 dict 값 설정 (정적 메서드)
    # -----------------------------------------------------------------------

    @staticmethod
    def _set_nested(d: dict, key: str, value: Any) -> None:
        """점(.) 구분 키로 중첩 dict에 값 설정.

        예: "parameters.rsi_oversold" → d["parameters"]["rsi_oversold"] = value
        중간 키가 없으면 빈 dict를 생성합니다.

        Args:
            d: 대상 dict.
            key: 점(.) 구분 경로 문자열.
            value: 설정할 값.
        """
        parts = key.split(".")
        cur = d
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value

    # -----------------------------------------------------------------------
    # _analyze_stability() — 파라미터 안정성 분석
    # -----------------------------------------------------------------------

    def _analyze_stability(
        self,
        filtered: List[Dict],
        all_results: List[Optional[Dict]],
        keys: List[str],
        threshold: float,
        metric: str = "sharpe_ratio",
        prefix: str = "sharpe_",
    ) -> None:
        """파라미터 안정성 분석 (메트릭 선택 가능).

        각 결과의 이웃 파라미터(±1 스텝)들의 metric 평균을 계산하여
        원본 대비 비율로 안정성 등급을 부여합니다. metric 은 BacktestResult
        필드명(예: "sharpe_ratio", "total_return")을 지정합니다. 결과는
        `{prefix}stability_score`, `{prefix}stability_grade` 필드에 저장됩니다.

        - 이웃 평균 / 원본 >= threshold → "안정"
        - 이웃 평균 / 원본 < threshold  → "과적합 의심"
        - 이웃 없음 또는 원본 <= 0      → "판정불가"

        Args:
            filtered: min_trades 통과 결과 리스트 (in-place 수정).
            all_results: 전체 결과 리스트 (이웃 조회용).
            keys: 파라미터 키 리스트.
            threshold: 안정 판정 기준 비율.
            metric: BacktestResult 필드명 (기본 "sharpe_ratio").
            prefix: 저장 필드 prefix (기본 "sharpe_").
        """
        score_key = f"{prefix}stability_score"
        grade_key = f"{prefix}stability_grade"

        # params → metric 룩업 테이블 구축
        lookup: Dict[tuple, float] = {}
        for r in all_results:
            if r is not None and r["result"].total_trades > 0:
                param_key = tuple(sorted(r["params"].items()))
                lookup[param_key] = float(getattr(r["result"], metric))

        for item in filtered:
            neighbors: List[float] = []

            for key in keys:
                current_val = item["params"][key]
                grid_values = self._param_grid[key]

                try:
                    idx = grid_values.index(current_val)
                except ValueError:
                    continue

                for offset in (-1, 1):
                    ni = idx + offset
                    if 0 <= ni < len(grid_values):
                        neighbor_params = dict(item["params"])
                        neighbor_params[key] = grid_values[ni]
                        neighbor_key = tuple(sorted(neighbor_params.items()))
                        if neighbor_key in lookup:
                            neighbors.append(lookup[neighbor_key])

            origin = float(getattr(item["result"], metric))
            if neighbors and origin > 0:
                avg_neighbor = float(np.mean(neighbors))
                ratio = avg_neighbor / origin
                item[score_key] = round(ratio, 3)
                item[grade_key] = "안정" if ratio >= threshold else "과적합 의심"
            else:
                item[score_key] = None
                item[grade_key] = "판정불가"
