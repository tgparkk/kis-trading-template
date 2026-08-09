# -*- coding: utf-8 -*-
"""계좌 화면 **층화 표본**을 뽑아 내려받는다 (2026-08-09 · 전량 판독 착수 시 재사용).

`img_index_build.py` 가 만든 `img_index_early.csv` 를 입력으로 받아, 연도 × 파일명 패턴으로
층을 나누고 각 층에서 **바이트 큰 순**으로 뽑는다. 산출물은 `harvest/img_probe/`
(**타인 저작물이라 `.gitignore` 대상**)와 그 안의 `manifest.csv`.

## 🔑 왜 「바이트 큰 순」인가 — 이 스크립트의 유일한 비자명한 결정

계좌 화면 후보는 **작은 파일**(<20KB)이다. 그 안에서 **더 큰 것이 더 넓게 자른 크롭**이고,
`대출일`·`신용구분` 컬럼은 **넓은 크롭에서만** 살아 있다(실측: 727~740px 크롭 5개에서만
컬럼이 온전했다). 무작위로 뽑으면 잘린 크롭만 잡혀 함정 2(`일자` ↔ `대출일` 선후)가
판정 불가로 남는다. ⇒ **작은 풀 안에서 큰 것부터**가 규약이다.

🔴 ***해상도로는 못 푼다.*** `?type=w800` 이 **이미 원본**이고(실측 597×66),
`?type=original` 과 쿼리 없는 URL 은 **404** 다. ***잘린 컬럼은 렌더링이 아니라
저자의 크롭 자체다*** — 더 큰 해상도를 시도하지 말 것.

## 층화 축

연도 × 파일명 패턴 5종. 앞의 4종이 §6-C 가 정한 축이고, `기타` 는 **그 넷에 안 걸리는
13장을 버리지 않으려고** 둔 다섯째다 — 🔑 ***분류에 안 걸린 것을 표본에서 빼면
「분류가 틀렸다」와 「그런 화면이 없다」가 구별되지 않는다.***

    계좌    파일명에 `계좌`        · `제일모직_계좌.png`
    요약    `수익현황`·`수익률`     · `기간별수익현황.png`  → 화면 [0390]
    날짜형  `^\\d{4}-\\d`            · `2015-04-05_174416.png` → 대개 뉴스·관심종목
    종목N   끝이 숫자              · `제일모직3.png`  ← **계좌 화면의 실질 다수**
    기타    위 넷에 안 걸림        · `lg상사_수익.png`·`씨.png`

⚠️ **파일명은 화면 유형이 아니다.** 유형 판정은 화소를 보고 하는 것이고 그 규약은
`METHOD.md` §A.5 에 있다. 여기서 하는 것은 **표본 추출**뿐이다.

## 지키는 계약

1. 대상은 **`img_index_build.py --head` 산출물**이다. `bytes` 가 비어 있으면 층화가
   무의미하므로 **받지 않고 종료코드 2** 를 낸다(빈 값을 0 으로 접으면 조용히 뒤집힌다).
2. 다운로드는 `download_images_28_29.fetch_image` 를 그대로 쓴다 — 응답을 메모리에서
   검사한 뒤에만 파일을 만든다(0바이트 잔해가 재실행을 영구 스킵시키던 결함의 수정본).
3. 확장자는 **매직바이트**가 정한다. 파일명의 `.png` 를 믿지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cat2829_common as C  # noqa: E402
import download_images_28_29 as D  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

INDEX_CSV = C.HARVEST / "img_index_early.csv"
PROBE_DIR = C.HARVEST / "img_probe"
MANIFEST = PROBE_DIR / "manifest.csv"

SE2_SLOT = "span.thumburl"
# 계좌 화면 후보의 상한. §6-B 실측에서 <20KB 가 317장 / 77글이고 >=100KB 는 차트다.
ACCOUNT_MAX_BYTES = 20000

DATE_NAME = re.compile(r"^\d{4}-\d")
TRAILING_NUM = re.compile(r"\d+\.[A-Za-z]{3,4}$")
UNSAFE = re.compile(r'[\\/:*?"<>|]')

MANIFEST_COLUMNS = ("file", "log_no", "post_date", "slot_no", "name", "bytes",
                    "year", "pattern", "rank_in_cell", "url")


def pattern(name):
    """파일명 패턴 층. **순서가 규약이다** — `계좌수익률.png` 은 `계좌` 로 간다."""
    if "계좌" in name:
        return "계좌"
    if "수익현황" in name or "수익률" in name:
        return "요약"
    if DATE_NAME.match(name):
        return "날짜형"
    if TRAILING_NUM.search(name):
        return "종목N"
    return "기타"


def load_pool(max_bytes=ACCOUNT_MAX_BYTES):
    """계좌 화면 후보 풀. **(rows, bytes 결측 수)**.

    SE2 슬롯 · `photo` · 크기 < max_bytes 만 남긴다. 차트(>=100KB)와 링크카드 썸네일은
    판독 대상이 아니다.
    """
    rows, missing = [], 0
    for r in csv.DictReader(INDEX_CSV.open(encoding="utf-8")):
        if r["slot"] != SE2_SLOT or r["kind"] != "photo":
            continue
        if not r["bytes"]:
            missing += 1
            continue
        if int(r["bytes"]) < max_bytes:
            rows.append(r)
    return rows, missing


def stratify(rows, per_cell):
    """(연도, 패턴) 셀별 **바이트 내림차순 상위 per_cell**. **(선택 행, 셀 census)**."""
    cells = defaultdict(list)
    for r in rows:
        cells[(r["post_date"][:4], pattern(r["name"]))].append(r)
    picked = []
    for key in sorted(cells):
        ordered = sorted(cells[key], key=lambda r: -int(r["bytes"]))
        for rank, r in enumerate(ordered[:per_cell], 1):
            item = dict(r)
            item.update({"year": key[0], "pattern": key[1], "rank_in_cell": rank})
            picked.append(item)
    return picked, {k: len(v) for k, v in sorted(cells.items())}


def probe_path(row, ext):
    """`{post_date}_{log_no}_{slot:03d}_{이름}.{ext}` — 정렬하면 연도별로 모인다."""
    stem = UNSAFE.sub("_", row["name"]).rpartition(".")[0] or row["name"]
    return PROBE_DIR / ("%s_%s_%03d_%s.%s" % (row["post_date"], row["log_no"],
                                              int(row["slot_no"]), stem, ext))


def main(argv=None):
    ap = argparse.ArgumentParser(description="계좌 화면 층화 표본을 내려받는다")
    ap.add_argument("--per-cell", type=int, default=4,
                    help="셀당 장수(바이트 큰 순). 기본 4 — §6-C 표본 32장과 같은 규모")
    ap.add_argument("--max-bytes", type=int, default=ACCOUNT_MAX_BYTES,
                    help="계좌 화면 후보 상한 바이트")
    ap.add_argument("--dry-run", action="store_true", help="요청 없이 목록만 낸다")
    args = ap.parse_args(argv)

    if not INDEX_CSV.exists():
        print("🔴 인덱스가 없다 —", INDEX_CSV, "· 먼저 img_index_build.py --head 를 돌릴 것")
        return 2

    rows, missing = load_pool(args.max_bytes)
    if missing:
        # 🔑 크기를 모르는 행을 0 으로 접으면 「가장 넓은 크롭」 대신 아무거나 잡힌다.
        print("🔴 bytes 가 빈 SE2 행 %d 건 — 인덱스를 `--head` 없이 만들었다. "
              "층화가 무의미하므로 중단한다." % missing)
        return 2

    picked, census = stratify(rows, args.per_cell)
    print("후보 풀 %d 장(<%dB) · %d글 · 셀 %d개 · 표본 %d장"
          % (len(rows), args.max_bytes, len({r["log_no"] for r in rows}),
             len(census), len(picked)))
    for (year, pat), n in census.items():
        got = sum(1 for p in picked if p["year"] == year and p["pattern"] == pat)
        print("   %s %-6s 전체 %3d → 표본 %d" % (year, pat, n, got))
    print("  표본 정체:", dict(sorted(Counter(p["pattern"] for p in picked).items())))

    if args.dry_run:
        for p in picked:
            print("   %s %s %sB %s" % (p["post_date"], p["pattern"], p["bytes"], p["name"]))
        print("(dry-run — 요청 0회)")
        return 0

    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    got, failures, manifest = 0, [], []
    for p in picked:
        blob, ext, error = D.fetch_image(p["url"])
        if blob is None:
            failures.append((p["name"], error))
            continue
        path = probe_path(p, ext)
        path.write_bytes(blob)
        manifest.append(dict(p, file=path.name))
        got += 1
        time.sleep(D.IMAGE_SLEEP)

    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(manifest)
    print("받음 %d 장 · 실패 %d 장 -> %s" % (got, len(failures), PROBE_DIR))
    print("   목록:", MANIFEST)
    if failures:
        print("🔴 실패 — 「층화 표본을 다 받았다」를 주장할 수 없다:")
        for name, error in failures[:10]:
            print("   ", name, error)
        return 1
    print("⚠️ 받은 이미지·판독값은 커밋 대상이 아니다(타인 저작물 · 비공개 원장). "
          "공개 문서엔 통계량만 — METHOD.md §A.5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
