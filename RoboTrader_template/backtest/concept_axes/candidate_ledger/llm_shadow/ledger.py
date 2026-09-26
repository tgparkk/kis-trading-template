"""§4 원장 해시 🔒 — 매 실행 끝: 그날 D 의 `llm_shadow` 모든 표 행을 정렬 CSV 로 내보내고 sha256 을 append.

- 파일 = `<archive>/<D>/<table>.<실행시각>.csv`(같은 D 재실행도 옛 파일을 덮지 않는다).
- 원장 = `<archive>/ledger_sha256.txt` 에 `D<TAB>table<TAB>n_rows<TAB>sha256<TAB>file<TAB>written_at` 한 줄씩 **append**.
- CSV 는 봉인 열(output_json·raw_result)을 담는다 — 보관용 복사일 뿐 열람 금지(§13-1). 콘솔에는 건수·해시만.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import settings as S
from . import state as ST


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def to_csv(rows: List[Dict[str, Any]], table: str) -> bytes:
    cols = sorted({k for r in rows for k in r}) if rows else list(ST.PK[table])
    rows = sorted(rows, key=lambda r: tuple(_cell(r.get(k)) for k in ST.PK[table]))
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_cell(r.get(c)) for c in cols])
    return buf.getvalue().encode("utf-8")


def export_day(store: Any, D: date, family_filter: Optional[Sequence[str]] = None,
               tables: Sequence[str] = ST.TABLES, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = Path(root or S.archive_dir())
    day_dir = root / D.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    out = []
    for t in tables:
        rows = store.select(t, {"scan_date": D})
        if family_filter:
            rows = [r for r in rows if r.get("family") in family_filter]
        data = to_csv(rows, t)
        f = day_dir / f"{t}.{stamp}.csv"
        f.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        out.append(dict(D=D.isoformat(), table=t, n_rows=len(rows), sha256=sha, file=f.name))
    with open(root / "ledger_sha256.txt", "a", encoding="utf-8", newline="\n") as fh:
        for e in out:
            fh.write(f"{e['D']}\t{e['table']}\t{e['n_rows']}\t{e['sha256']}\t{e['file']}\t"
                     f"{datetime.now().isoformat(timespec='seconds')}\n")
    return out
