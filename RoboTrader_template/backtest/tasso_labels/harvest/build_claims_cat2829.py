# -*- coding: utf-8 -*-
"""정독 에이전트의 배치 JSONL → 주장 원장 CSV 2벌.

- claims_cat2829.csv        quote 제거 = 커밋본
- claims_cat2829_quoted.csv quote 포함 = 로컬 전용 (gitignore 재차단)
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cat2829_common as C          # noqa: E402
import claims_schema as S           # noqa: E402


def load_batches(batch_dir):
    """배치 디렉토리의 *.jsonl 을 전부 읽고 **행마다 스키마 검증**한다."""
    rows = []
    for path in sorted(os.listdir(str(batch_dir))):
        if not path.endswith(".jsonl"):
            continue
        full = os.path.join(str(batch_dir), path)
        with open(full, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                bad = S.validate_row(row)
                if bad:
                    raise ValueError(path + ":" + str(lineno) + " " + ";".join(bad))
                rows.append(row)
    return rows


def write_ledgers(rows, public_path, quoted_path):
    """두 벌을 쓴다. 열 순서는 claims_schema 가 정한다."""
    for path, cols in ((quoted_path, S.COLUMNS), (public_path, S.PUBLIC_COLUMNS)):
        with open(str(path), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cols), extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)


def main():
    rows = load_batches(C.CLAIMS_BATCH_DIR)
    write_ledgers(rows, C.CLAIMS_PUBLIC_CSV, C.CLAIMS_QUOTED_CSV)
    print("주장", len(rows), "행 · 글", len({r["log_no"] for r in rows}), "건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
