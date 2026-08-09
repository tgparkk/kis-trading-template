# -*- coding: utf-8 -*-
"""317장 계좌 화면 후보 **전량** 다운로드 (2026-08-09 · 전량 판독 착수).

풀은 `img_index_early.csv` 에서 `slot=="span.thumburl"` · `kind=="photo"` ·
`bytes` 가 숫자열이고 `int(bytes) < 20000` 인 행 **전부** — `img_probe_sample.load_pool`
과 같은 상한을 쓰지만 여기서는 층화 표본이 아니라 **전량**이다. 실측 317행 / 77 log_no.
이 두 숫자가 어긋나면 풀 정의가 조용히 바뀐 것이므로 한 장도 받지 않고 중단한다
(아래 `EXPECT_ROWS`/`EXPECT_LOGNOS`).

산출: `D:/archive/tasso-account-images-20260809/`(레포 밖 · 영구 · 커밋 금지).
파일명: `{post_date}_{log_no}_{slot_no:03d}_{안전화한 이름 stem}.{매직바이트 확장자}` —
   원본 `name` 의 확장자는 버리고 실제로 받은 바이트의 매직바이트로 정한다
   (`download_images_28_29.image_ext`) — URL 확장자·파일명 확장자 둘 다 못 믿는다는
   원 스크립트의 근거를 그대로 승계.

재사용(있는 것을 다시 만들지 않는다):
  `download_images_28_29.fetch_image`  — 이 CDN 에 맞는 헤더/Referer, 매직바이트 판정,
                                          0바이트·HTML 오류응답을 파일로 안 남기는 계약
  `img_probe_sample.pattern`           — 파일명 → 화면 패턴 층(계좌/요약/날짜형/종목N/기타),
                                          계좌수익률.png 이 계좌로 가는 우선순위 포함
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import download_images_28_29 as D  # noqa: E402
import img_probe_sample as P  # noqa: E402
# img_probe_sample 이 import 시점에 sys.stdout 을 utf-8 TextIOWrapper 로 이미 바꿔
# 둔다 — 여기서 다시 감싸면 이전 래퍼가 GC 될 때 공유 버퍼를 닫아 버려
# "I/O operation on closed file" 로 죽는다(실측). 다시 감싸지 않는다.

INDEX_CSV = Path(__file__).resolve().parent / "img_index_early.csv"
OUT_DIR = Path("D:/archive/tasso-account-images-20260809")
MANIFEST = OUT_DIR / "manifest.csv"

SLOT = "span.thumburl"
KIND = "photo"
MAX_BYTES = 20000
EXPECT_ROWS = 317
EXPECT_LOGNOS = 77
SLEEP = 0.2

UNSAFE = re.compile(r'[\\/:*?"<>|]')

MANIFEST_COLUMNS = ("file", "log_no", "post_date", "slot_no", "name",
                     "bytes_index", "bytes_actual", "ext", "year", "pattern",
                     "url", "status")


def load_pool():
    """풀을 재구성한다. **(rows)** — 필터는 위 docstring 과 정확히 같아야 한다."""
    rows = []
    with INDEX_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["slot"] != SLOT or r["kind"] != KIND:
                continue
            b = r["bytes"]
            if not b.isdigit():
                continue
            if int(b) < MAX_BYTES:
                rows.append(r)
    return rows


def safe_stem(name):
    """`name` 에서 확장자를 떼고 위험 문자를 지운 stem. 확장자는 나중에 매직바이트가 정한다."""
    cleaned = UNSAFE.sub("_", name)
    stem = cleaned.rpartition(".")[0]
    return stem or cleaned


def out_prefix(row):
    return "%s_%s_%03d_%s" % (row["post_date"], row["log_no"],
                               int(row["slot_no"]), safe_stem(row["name"]))


def existing_valid(prefix):
    """이미 받아 둔 **유효한** 파일. (path, ext) 아니면 (None, None).

    🔑 존재가 아니라 유효로 판정한다 — download_images_28_29.existing_image() 와 같은 계약.
       0바이트·비이미지 잔해는 지운다. 남겨 두면 「존재=스킵」이 영구 스킵이 된다.
    """
    for path in sorted(OUT_DIR.glob(prefix + ".*")):
        try:
            head = path.read_bytes()[:16]
        except OSError:
            continue
        ext = D.image_ext(head)
        if ext:
            return path, ext
        path.unlink()
    return None, None


def main():
    rows = load_pool()
    n_lognos = len({r["log_no"] for r in rows})
    if len(rows) != EXPECT_ROWS or n_lognos != EXPECT_LOGNOS:
        print("ABORT: 풀이 어긋났다 — rows=%d log_no=%d (기대 %d/%d) — "
              "정의가 조용히 바뀐 것이므로 한 장도 받지 않는다."
              % (len(rows), n_lognos, EXPECT_ROWS, EXPECT_LOGNOS))
        return 2
    print("풀 확인: %d행 / %d log_no (기대와 일치)" % (len(rows), n_lognos))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    ok = skipped = failed = 0
    mismatches = []
    failures = []

    for row in rows:
        prefix = out_prefix(row)
        idx_bytes = int(row["bytes"])
        pat = P.pattern(row["name"])
        year = row["post_date"][:4]

        path, ext = existing_valid(prefix)
        if path is not None:
            actual = path.stat().st_size
            status = "skipped-valid"
            fname = path.name
        else:
            blob, ext, error = D.fetch_image(row["url"])
            time.sleep(SLEEP)
            if blob is None:
                failed += 1
                failures.append((row["log_no"], row["name"], error))
                manifest.append({
                    "file": "", "log_no": row["log_no"], "post_date": row["post_date"],
                    "slot_no": row["slot_no"], "name": row["name"],
                    "bytes_index": idx_bytes, "bytes_actual": "", "ext": "",
                    "year": year, "pattern": pat, "url": row["url"], "status": "failed",
                })
                continue
            out_path = OUT_DIR / (prefix + "." + ext)
            out_path.write_bytes(blob)
            actual = len(blob)
            status = "ok"
            fname = out_path.name

        if status == "ok":
            ok += 1
        else:
            skipped += 1
        if actual != idx_bytes:
            mismatches.append((fname, idx_bytes, actual))
        manifest.append({
            "file": fname, "log_no": row["log_no"], "post_date": row["post_date"],
            "slot_no": row["slot_no"], "name": row["name"], "bytes_index": idx_bytes,
            "bytes_actual": actual, "ext": ext, "year": year, "pattern": pat,
            "url": row["url"], "status": status,
        })

    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        w.writerows(manifest)

    print("받음(ok) %d · 이미 있어 건너뜀(skipped-valid) %d · 실패(failed) %d · 합계 %d"
          % (ok, skipped, failed, len(rows)))
    print("목록 ->", MANIFEST)
    if mismatches:
        print("🔴 bytes_actual 이 bytes_index 와 다른 행 %d건 — CDN 이 인덱스와 다른 걸 줬다:"
              % len(mismatches))
        for name, idx_b, act_b in mismatches[:30]:
            print("   ", name, "index=%d actual=%d" % (idx_b, act_b))
    else:
        print("bytes_actual 이 bytes_index 와 전부 일치")
    if failures:
        print("🔴 실패 %d건 — 「전량」을 주장할 수 없다:" % len(failures))
        for log_no, name, error in failures:
            print("   ", log_no, name, error)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
