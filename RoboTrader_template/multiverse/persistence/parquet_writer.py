"""Parquet 결과 영속성 모듈.

write_cell_result: 단일 셀 결과를 dict row로 변환 (caller가 list에 누적).
flush_results_to_parquet: 누적된 row 리스트를 Parquet(또는 CSV 폴백)으로 저장.
"""
from __future__ import annotations

import dataclasses
import logging
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def write_cell_result(
    output_dir: Path,
    paramset_id: str,
    config_hash: str,
    mode: str,
    window_idx: int,
    start_date: Any,
    end_date: Any,
    metrics: Any,
    runtime_seconds: float,
    extra: Optional[Dict] = None,
) -> Dict:
    """단일 셀 결과를 dict row로 변환.

    반환된 dict를 caller가 list에 누적한 뒤
    flush_results_to_parquet()로 일괄 저장.

    Parameters
    ----------
    output_dir:
        저장 디렉토리 (flush 시 사용).
    paramset_id:
        파라미터 세트 식별자.
    config_hash:
        설정 해시 (중복 감지용).
    mode:
        실행 모드 ("plain" / "oos_split" / "walkforward").
    window_idx:
        WF 윈도우 인덱스 (plain은 0).
    start_date:
        백테스트 시작일.
    end_date:
        백테스트 종료일.
    metrics:
        Metrics dataclass 인스턴스 또는 dict.
    runtime_seconds:
        셀 실행 소요 시간 (초).
    extra:
        추가 메타데이터 (선택).

    Returns
    -------
    dict
        단일 row dict.
    """
    # Metrics dataclass → dict 변환
    if dataclasses.is_dataclass(metrics) and not isinstance(metrics, type):
        metrics_dict = dataclasses.asdict(metrics)
    elif isinstance(metrics, dict):
        metrics_dict = dict(metrics)
    else:
        metrics_dict = {}

    row: Dict[str, Any] = {
        "paramset_id": paramset_id,
        "config_hash": config_hash,
        "mode": mode,
        "window_idx": window_idx,
        "start_date": start_date,
        "end_date": end_date,
        "runtime_seconds": runtime_seconds,
        **{f"m_{k}": v for k, v in metrics_dict.items()},
    }

    if extra:
        row.update(extra)

    return row


def flush_results_to_parquet(
    output_dir: Path,
    rows: List[Dict],
    mode: str,
    timestamp: Optional[datetime] = None,
) -> Path:
    """누적된 row 리스트를 Parquet 파일로 한 번에 저장.

    pyarrow가 없으면 CSV 폴백 + 경고 로그.

    Parameters
    ----------
    output_dir:
        저장 디렉토리. 없으면 자동 생성.
    rows:
        write_cell_result() 반환값의 list.
    mode:
        파일명 구성에 사용하는 모드 문자열.
    timestamp:
        파일명에 포함할 타임스탬프 (기본: 현재 시각).

    Returns
    -------
    Path
        저장된 파일 경로.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now()

    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
    base_name = f"multiverse_{mode}_{ts_str}"

    df = pd.DataFrame(rows)

    # date 컬럼 타입 정리 (date → string, datetime 유지)
    for col in ("start_date", "end_date"):
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: v.isoformat() if isinstance(v, (date, datetime)) else str(v) if v is not None else None
            )

    # pyarrow 사용 가능 여부 확인
    _use_parquet = True
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        _use_parquet = False

    if _use_parquet:
        parquet_path = output_dir / f"{base_name}.parquet"
        df.to_parquet(parquet_path, engine="pyarrow", index=False)
        logger.info("[parquet_writer] 저장 완료: %s (%d rows)", parquet_path, len(df))
        return parquet_path
    else:
        warnings.warn(
            "pyarrow가 설치되지 않아 CSV로 폴백합니다. "
            "`pip install pyarrow`로 Parquet 지원을 활성화하세요.",
            ImportWarning,
            stacklevel=2,
        )
        csv_path = output_dir / f"{base_name}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.warning("[parquet_writer] pyarrow 미설치 — CSV 폴백: %s (%d rows)", csv_path, len(df))
        return csv_path
