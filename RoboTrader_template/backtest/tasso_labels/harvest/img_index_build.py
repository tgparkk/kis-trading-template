# -*- coding: utf-8 -*-
"""초기 매매일지([1]/[35]) 90글의 **이미지 슬롯 인덱스**를 만든다 (2026-08-09).

## 왜 이 인덱스가 필요한가

`journal_items_early.csv` 309항목의 시간 해상도는 본문 텍스트만으로는 **12.9~19.2%**
(일 단위 특정)에 그친다. 그런데 저자는 본문에 **HTS 실현손익 화면**을 붙여 뒀고,
그 화면에는 `일자·매입가·매도체결가·수익률`이 **행 단위로** 들어 있다.

🔑 ***저자가 이미지 파일명에 종목명을 적어 뒀다*** — `제일모직_계좌.png`·`종목명3.png`.
   ⇒ **항목 ↔ 이미지 연결이 OCR 없이 파일명으로 된다.** 이 인덱스가 그 연결의 기반이고,
   항목↔파일명 매칭은 단순 정규화만으로 **283/309 = 91.6%(하한)** 이 붙는다.

## 이 스크립트가 하는 것과 하지 않는 것

- 한다: 슬롯 열거 · 파일명 디코드 · (옵션) 원격 `Content-Length` 수집 → CSV 한 장.
- 안 한다: 다운로드·판독·화면 유형 분류. 다운로드는 `img_probe_sample.py`,
  판독 규약은 `METHOD.md` §A.5 다. 여기서 판독을 섞으면 「슬롯이 없다」와
  「판독을 못 했다」가 한 숫자에 섞인다.

## 지키는 계약 (선행 사고에서 온 것들)

1. 슬롯 추출은 **`cat2829_common.body_images()` 하나뿐**이다. 정규식을 새로 쓰지 않는다 —
   페이지 전체를 훑으면 프로필 썸네일이 글당 4장 섞이고, SE2 의 그림은 `<img>` 가 아니라
   `<span thumburl>` 이라 **한 장도 안 잡힌다**(`download_images_28_29.py:15-18` 의 결함 ③).
2. 🔴 **URL 은 `?type=w800`** 이다. **쿼리 없는 원본 URL 은 404**이고(`cat2829_common`
   TYPE_REWRITE_HOSTS 주석의 호스트별 실측), `?type=original` 도 404 다.
   ⚠️ **w800 이 이미 원본이다**(실측 597×66). 더 큰 해상도는 없다 —
   ***잘린 컬럼은 렌더링이 아니라 저자의 크롭 자체다.***
3. 🔴 파일명은 **EUC-KR percent-encoding** 이다. `unquote_to_bytes` → `euc-kr`.
   퍼센트 문자열을 그대로 두면 종목명이 안 보여 위 91.6% 매칭 경로가 통째로 닫힌다.
4. 🔴 **게이트**: SE2 슬롯 955 · 디코드 실패 0. 어느 하나라도 어긋나면 **종료코드 1**.
   ***조용히 다른 수를 내면 다음 사람이 못 잡는다*** — 이 저장소에서 「빈 결과가 정상으로
   읽힌」 사고가 반복됐다(pykrx 시총·ticker_list).

## 🔴 이 스크립트가 첫 실행에서 정정한 것 — **955 는 총계가 아니다**

08-09 탐침 기록(§6-B)은 *「이미지 슬롯 955 · 90글」* 로 적혀 있고 괄호에 정의가 붙어 있다:
*「SE2 `<span class=_img>` 의 `thumburl`」*. **정의가 곧 한정이었는데 숫자만 인용되면
총계로 읽힌다.** 실측 총계는 **993**(87글 — 3글은 이미지 0장)이고 차이 38 은 전부
SE2 thumburl 이 아닌 슬롯이다:

    span.thumburl       955  (83글, 2009-08-03 ~ 2017-03-07)  ← §6-B 의 955
    img.data-lazy-src    21  (2글: 2019-05-07 출간공지 · 2026-08-07 [32] 증분)
    img.src              15  (4글: 2009 잡담 2글 + 위 2글)
    video.data-gif-url    2  (1글: 2016-10-09 매매일지의 GIF)

⇒ **행은 993 전부 남긴다**(빼면 그 사실이 산출물에 흔적을 안 남긴다) 대신
**게이트는 955 를 SE2 부분집합에 건다**. 총계로 게이트를 걸면 영구히 빨간불이고,
슬롯을 걸러 955 를 맞추면 **거른 사실이 사라진다.** `slot` 열이 그 재현 경로다 —
🔑 ***헤드라인 수치를 산출물 자신에서 다시 셀 수 없으면 그건 자기보고다.***
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote_to_bytes, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cat2829_common as C  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

POSTS_DIR = C.HARVEST / "posts_early"
POSTMETA = C.HARVEST / "postmeta_early.json"
INDEX_CSV = C.HARVEST / "img_index_early.csv"

# 🔑 마지막 `slot` 열은 §6-B 의 955 를 **CSV 자신에서 다시 셀 수 있게** 하려고 있다
#    (`slot == "span.thumburl"` 인 행의 수). 나머지 7 열이 요청받은 스키마다.
COLUMNS = ("log_no", "post_date", "slot_no", "name", "kind", "url", "bytes", "slot")

# `body_images()` 가 SE2 그림에 붙이는 slot 이름. 이 코퍼스의 계좌 화면은 전부 여기 있다.
SE2_SLOT = "span.thumburl"

# 🔴 2026-08-09 실측(§6-B). 이 수는 **가정이 아니라 게이트**이고, **SE2 부분집합**에 건다 —
#    총계는 993 이다(위 docstring). 바뀌었다면 재수집으로 글이 늘었거나 추출기가 조용히
#    달라진 것이고, 둘 다 사람이 볼 일이다.
EXPECT_SE2_SLOTS = 955

# 썸네일 서버가 실제로 주는 크기. `w966` 은 [28]·[29] 트랙의 기본값이고, 이 코퍼스의
# 계좌 화면은 원본 자체가 작아 **w800 이 원본**이다(597×66 등 실측).
TYPE_PARAM = "w800"

# 🔑 순서가 곧 규약이다. `cp949 ⊃ euc-kr` 이므로 cp949 를 앞에 두면 어떤 바이트열이
#    euc-kr 로 읽혔는지 알 수 없어진다. utf-8 은 **거의 안 쓰이지만 있으면 확실히 다르다**.
CODECS = ("euc-kr", "utf-8", "cp949")

HEAD_WORKERS = 6
HEAD_TIMEOUT = 20


def decode_name(url):
    """URL 경로 끝의 파일명을 사람이 읽는 문자열로. **(이름, 코덱)** · 실패면 (원문, None).

    네이버 SE2 는 업로드 당시 파일명을 **EUC-KR 로 퍼센트 인코딩**해 경로에 박아 둔다
    (`%C1%A6%C0%CF%B8%F0%C1%F71.png` = `제일모직1.png`). 실측 955/955 가 euc-kr 로 풀린다.
    """
    seg = urlsplit(url).path.rpartition("/")[2]
    raw = unquote_to_bytes(seg)
    for codec in CODECS:
        try:
            return raw.decode(codec), codec
        except UnicodeDecodeError:
            continue
    return seg, None


def ambiguous(url):
    """euc-kr 로도 utf-8 로도 읽히면서 **결과가 다른** 이름인가.

    🔑 mojibake 는 예외를 안 던진다. 「euc-kr 로 성공했다」만 세면 utf-8 이름을
       조용히 깨뜨린 경우가 성공으로 집계된다 — 그래서 성공 수와 별도로 이것을 센다.
    """
    raw = unquote_to_bytes(urlsplit(url).path.rpartition("/")[2])
    try:
        return raw.decode("euc-kr") != raw.decode("utf-8")
    except UnicodeDecodeError:
        return False


def build_rows():
    """`posts_early/*.html` 전건의 슬롯 행. **(rows, 디코드 실패 행)**.

    slot_no 는 `body_images()` 반환 순서의 **0-based 인덱스**이고 **kind 필터 전** 값이다
    (`download_images_28_29.plan_jobs` 의 index 는 필터 «후» 라 서로 다른 축이다).
    `_codec` 은 진단용 내부 열이라 CSV 에 안 나간다(`extrasaction="ignore"`).
    """
    meta = json.loads(POSTMETA.read_text(encoding="utf-8"))
    rows, fails = [], []
    for path in sorted(POSTS_DIR.glob("*.html")):
        log_no = path.stem
        post_date = (meta.get(log_no) or {}).get("date", "")
        src = path.read_text(encoding="utf-8")
        for slot_no, item in enumerate(C.body_images(src)):
            url = C.normalize_image_url(item["url"], TYPE_PARAM)
            name, codec = decode_name(url)
            if codec is None:
                fails.append({"log_no": log_no, "slot_no": slot_no, "url": url})
            rows.append({"log_no": log_no, "post_date": post_date, "slot_no": slot_no,
                         "name": name, "kind": item["kind"], "url": url, "bytes": "",
                         "slot": item["slot"], "_codec": codec or "FAIL"})
    return rows, fails


def head_length(url):
    """원격 `Content-Length`. 실패면 None.

    🔑 헤더 두 개가 **필수**다 — `User-Agent` 없이는 봇으로 걸리고, `Referer` 없이는
       핫링크 차단에 걸린다. 둘 다 `cat2829_common._curl` 의 본문 수집 규약을 승계한다.
    ⚠️ `-L` 로 리다이렉트를 따라가면 헤더 블록이 여러 개 오므로 **마지막 값**을 쓴다.
    """
    r = subprocess.run(
        ["curl", "-s", "-f", "-I", "-L", "-m", str(HEAD_TIMEOUT), "-A", C.UA,
         "-H", "Referer: https://m.blog.naver.com/" + C.BLOG, url],
        capture_output=True)
    if r.returncode != 0:
        return None
    got = None
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        key, sep, val = line.partition(":")
        if sep and key.strip().lower() == "content-length":
            got = val.strip()
    return int(got) if (got or "").isdigit() else None


def fill_bytes(rows):
    """`bytes` 열을 원격 HEAD 로 채운다. **실패 행 목록**을 낸다.

    같은 URL 이 두 번 나오면 한 번만 묻는다(요청 수 = 고유 URL 수).
    """
    urls = sorted({r["url"] for r in rows})
    with ThreadPoolExecutor(max_workers=HEAD_WORKERS) as pool:
        sizes = dict(zip(urls, pool.map(head_length, urls)))
    for r in rows:
        r["bytes"] = "" if sizes[r["url"]] is None else sizes[r["url"]]
    return [r for r in rows if sizes[r["url"]] is None]


def main(argv=None):
    ap = argparse.ArgumentParser(description="초기 매매일지 90글의 이미지 슬롯 인덱스")
    ap.add_argument("--head", action="store_true",
                    help="원격 HEAD 로 Content-Length 를 채운다(동시 %d)" % HEAD_WORKERS)
    args = ap.parse_args(argv)

    rows, fails = build_rows()
    se2 = [r for r in rows if r["slot"] == SE2_SLOT]
    amb = sum(1 for r in rows if ambiguous(r["url"]))
    print("글 %d(이미지 있는 글) · 슬롯 총계 %d · 그중 SE2(%s) %d · %d글"
          % (len({r["log_no"] for r in rows}), len(rows), SE2_SLOT,
             len(se2), len({r["log_no"] for r in se2})))
    print("  슬롯 출처:", dict(sorted(Counter(r["slot"] for r in rows).items())))
    print("  정체:", dict(sorted(Counter(r["kind"] for r in rows).items())))
    print("  파일명 코덱(SE2):", dict(sorted(Counter(r["_codec"] for r in se2).items())))
    print("  파일명 코덱(전체):", dict(sorted(Counter(r["_codec"] for r in rows).items())))
    print("  euc-kr/utf-8 양쪽으로 읽히며 결과가 다른 이름:", amb, "건")

    head_fail = []
    if args.head:
        head_fail = fill_bytes(rows)
        got = [r for r in se2 if r["bytes"] != ""]
        print("  HEAD: 고유 URL %d · SE2 크기 확보 %d 행 · 전체 실패 %d 행"
              % (len({r["url"] for r in rows}), len(got), len(head_fail)))
        if got:
            sizes = sorted(int(r["bytes"]) for r in got)
            print("  SE2 바이트 중앙 %d · <20KB %d 장(계좌 화면 후보, %d글) · >=100KB %d 장(차트, %d글)"
                  % (sizes[len(sizes) // 2],
                     sum(1 for s in sizes if s < 20000),
                     len({r["log_no"] for r in got if int(r["bytes"]) < 20000}),
                     sum(1 for s in sizes if s >= 100000),
                     len({r["log_no"] for r in got if int(r["bytes"]) >= 100000})))
    else:
        print("  (--head 없음 — bytes 열은 빈칸)")

    with INDEX_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("->", INDEX_CSV)

    # ── 게이트 ────────────────────────────────────────────────────────────────
    bad = []
    if len(se2) != EXPECT_SE2_SLOTS:
        bad.append("SE2 슬롯 %d != 실측 기준 %d — 재수집으로 글이 늘었거나 추출기가 "
                   "달라졌다. 어느 쪽인지 사람이 판정할 것." % (len(se2), EXPECT_SE2_SLOTS))
    if fails:
        bad.append("파일명 디코드 실패 %d 건 — %s" % (len(fails), fails[:3]))
    if bad:
        print("\n🔴 게이트 불통과:")
        for b in bad:
            print("  ", b)
        return 1
    print("\n🟢 게이트 통과 — SE2 슬롯 %d · 디코드 실패 0 (총계 %d)"
          % (EXPECT_SE2_SLOTS, len(rows)))
    if head_fail:
        # 🔑 HEAD 실패는 게이트가 아니다(원격·일시적). 다만 「955/955 생존」을 주장하려면
        #    SE2 실패가 0 이어야 하므로 눈에 띄게 남긴다.
        print("⚠️ HEAD 실패 %d 행(SE2 %d) — 「원격 생존 955/955」를 주장하지 말 것"
              % (len(head_fail), sum(1 for r in head_fail if r["slot"] == SE2_SLOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
