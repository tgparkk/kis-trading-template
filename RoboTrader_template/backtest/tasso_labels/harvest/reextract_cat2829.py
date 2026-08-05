# -*- coding: utf-8 -*-
"""[28]·[29] 본문 **재추출** — 이미 받아 둔 HTML 에서 텍스트와 메타를 다시 만든다.

🔴 왜 재수집이 아니라 재추출인가 (2026-08-05 실측이 뒤집은 전제):
   Task 9 수집 뒤 195건이 `text_len=0` 이라 「모바일이 구 에디터 본문을 안 준다」는
   선행 기록(harvest_fallback.py:3-5)이 재현된 것으로 보였다. **틀렸다.**
   본문은 `posts28/` 에 **이미 다 들어 있었다.** 못 읽은 이유는 추출기가 SmartEditor
   ONE 문단(`se-text-paragraph`)만 읽었기 때문이다. 이 블로그는 세 세대를 쓴다.

   같은 글(logNo=220000968295)을 두 경로에서 뽑아 대조한 결과:
       모바일 저장본 컨테이너 → 4,192자 / 88줄
       PC `postViewArea`      → 4,192자 / 88줄   ← **줄 단위 완전일치, 차이 0줄**
   ⇒ PC 재수집으로 얻을 것이 **없다.** 네트워크 0회로 197건을 되살린다.

   그래도 `--refetch-pc` 를 남겨 둔다: 재추출 후에도 `body_missing` 인 글은 응답에
   진짜로 본문이 없는 것이고, 그때의 정답이 PC 엔드포인트다. **대상이 0건이면
   요청도 0건**이다(2026-08-05 현재 0건).

⚠️ 이 스크립트는 네트워크를 **기본적으로 안 쓴다**. `--refetch-pc` 를 줄 때만 쓴다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import json
import subprocess
import time

import cat2829_common as C
import harvest_cat28_29_full as H

# PC 엔드포인트 — harvest_fallback.py:27-28 의 URL 형태를 그대로 승계한다(추측 아님).
PC_URL = ("https://blog.naver.com/PostView.naver?blogId=" + C.BLOG + "&logNo={log_no}"
          "&redirect=Dlog&widgetTypeCall=true&directAccess=false")
PC_SLEEP = 1.0            # harvest_fallback.py:54 의 1초 간격을 승계
PC_MIN_BYTES = 20000      # harvest_fallback.py:46 의 성공 판정 하한을 승계

# 🔑 PC 재수집본은 **다른 이름**으로 둔다(모바일 원본을 덮지 않는다).
#    이유: 모바일 원본은 「모바일이 무엇을 줬는가」의 유일한 증거다. 덮어쓰면
#    ① 이번 결함의 재현이 불가능해지고 ② "이 글은 어디서 왔나" 를 파일로 답할 수
#    없어진다. 재현성은 최신본이 아니라 **받은 것을 그대로 남기는 것**에서 나온다.
PC_SUFFIX = ".pc.html"


def saved_html_path(stem):
    """이 글의 본문 HTML 경로. PC 재수집본이 있으면 **그쪽이 우선**한다."""
    pc = C.POSTS_DIR / (stem + PC_SUFFIX)
    return pc if pc.exists() else C.POSTS_DIR / (stem + ".html")


def fetch_pc(log_no, timeout=40):
    r = subprocess.run(["curl", "-s", "-m", str(timeout), "-A", C.UA,
                        PC_URL.format(log_no=C.norm_log_no(log_no))],
                       capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def reextract_one(entry):
    """저장된 HTML 에서 메타를 다시 만든다. 텍스트 파일도 다시 쓴다.

    🔑 `harvest_one` 과 **같은 메타 계약**을 낸다 — 두 경로가 다른 모양의 메타를
       내면 하류가 어느 쪽을 보느냐에 따라 조용히 갈린다.
    """
    stem = H._stem(entry)
    path = saved_html_path(stem)
    if not path.exists():
        raise RuntimeError("HTML_NOT_SAVED:" + C.norm_log_no(entry["log_no"]))
    src = path.read_text(encoding="utf-8")
    text = C.html_to_text(src)
    (C.TEXT_DIR / (stem + ".txt")).write_text(text, encoding="utf-8")
    meta = {
        "log_no": C.norm_log_no(entry["log_no"]),
        "category": entry["category"],
        "post_date": entry["post_date"],
        "title": entry.get("title", ""),
        "html_bytes": len(src.encode("utf-8")),
        "text_len": len(text),
        "text_file": stem + ".txt",
        "img_count": C.count_images(src),
        "body_img_count": C.count_images(src, body_only=True),
        "from_cache": True,
        "source": C.detect_source(src),
        "page_editor_version": C.page_editor_version(src),
    }
    meta.update(C.classify_body(src, text))
    return meta


def refetch_pc(entries, sleep=None, fetch=None):
    """본문이 진짜로 없는 글만 PC 엔드포인트에서 다시 받는다. (받은 수, 실패목록).

    존재-스킵 + 개별 실패를 모아 끝까지 진행 + 실패를 시끄럽게 —
    `harvest_one`/`harvest_bodies` 의 방식을 그대로 따른다.
    """
    sleep = sleep if sleep is not None else time.sleep
    fetch = fetch or fetch_pc
    got, failures = 0, []
    for entry in entries:
        stem = H._stem(entry)
        out = C.POSTS_DIR / (stem + PC_SUFFIX)
        if out.exists() and out.stat().st_size >= PC_MIN_BYTES:
            continue                      # 이미 받아 뒀다
        src = fetch(entry["log_no"])
        if C.detect_source(src) == "pc" and len(src.encode("utf-8")) >= PC_MIN_BYTES:
            out.write_text(src, encoding="utf-8")
            got += 1
        else:
            failures.append({"log_no": C.norm_log_no(entry["log_no"]),
                             "post_date": entry.get("post_date"),
                             "error": "PC_FETCH_FAILED bytes=" + str(len(src))})
        sleep(PC_SLEEP)
    return got, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch-pc", action="store_true",
                    help="재추출 후에도 본문이 없는 글만 PC 엔드포인트에서 재수집한다")
    args = ap.parse_args()

    C.ensure_dirs()
    catalog = json.loads(C.CATLIST_JSON.read_text(encoding="utf-8"))
    metas, failures = [], []
    for log_no in sorted(catalog["posts"]):
        try:
            metas.append(reextract_one(catalog["posts"][log_no]))
        except Exception as exc:
            failures.append({"log_no": log_no,
                             "post_date": catalog["posts"][log_no].get("post_date"),
                             "error": type(exc).__name__ + ": " + str(exc)})

    if args.refetch_pc:
        targets = [catalog["posts"][m["log_no"]] for m in metas if m["body_missing"]]
        print("PC 재수집 대상", len(targets), "건")
        if targets:
            got, pc_fail = refetch_pc(targets)
            print("   받음", got, "건 · 실패", len(pc_fail), "건")
            failures.extend(pc_fail)
            by_log = {m["log_no"]: i for i, m in enumerate(metas)}
            for entry in targets:                     # 받은 것만 다시 판정한다
                try:
                    metas[by_log[C.norm_log_no(entry["log_no"])]] = reextract_one(entry)
                except Exception as exc:
                    failures.append({"log_no": C.norm_log_no(entry["log_no"]),
                                     "error": type(exc).__name__ + ": " + str(exc)})

    C.POSTMETA_JSON.write_text(json.dumps(metas, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    C.HARVEST_FAIL_JSON.write_text(json.dumps(failures, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    total = sum(m["text_len"] for m in metas)
    print("재추출", len(metas), "건 · 총 텍스트", format(total, ","), "자")
    print(H.summarize_bodies(metas, catalog))
    if failures:
        print("🔴 실패", len(failures), "건 — 「전수」를 주장할 수 없다:")
        for f in failures:
            print("   ", f["log_no"], f.get("error"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
