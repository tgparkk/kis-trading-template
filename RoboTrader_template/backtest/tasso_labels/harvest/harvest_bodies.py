"""목록에서 뽑은 글의 본문을 내려받아 로컬 저장 (읽기 전용, 공개글, 1초 간격).

v2 (2026-08-02) — 카테고리 32 **전수 858건** 대상으로 확장. 고친 결함 2건:
  1) `p['titleWithInspectMessage']` 참조 -> 현재 목록 API 의 키는 **`title`** 이라 KeyError 로 죽었다.
  2) `CUTOFF = 2024-08-01` 이라 최근분만 받았다 -> 기본 전체, `--since` 로만 좁힌다.

⚠️ 날짜는 `datetime.fromtimestamp(addDate/1000)` = **로컬(KST)** 을 유지할 것.
   `addDate` 는 KST epoch 이며 UTC 로 바꾸면 858건 중 3건이 하루 밀린다(실측).
   라벨 날짜가 밀리면 진입 창이 통째로 밀린다.

⚠️ 받은 HTML 은 **커밋 금지**(타인 저작물). `posts/` 는 .gitignore 로 막아 두었다.
"""
import argparse
import datetime
import io
import json
import os
import re
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BLOG = "mbc3110"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
OUTDIR = "posts"
MIN_BYTES = 5000          # 이보다 작으면 본문이 안 실린 것으로 본다(에러 페이지·리다이렉트)
RETRIES = 3


def fetch(log_no: int) -> str:
    url = f"https://m.blog.naver.com/PostView.naver?blogId={BLOG}&logNo={log_no}"
    r = subprocess.run(
        ["curl", "-s", "-m", "40", "-A", UA,
         "-H", f"Referer: https://m.blog.naver.com/{BLOG}", url],
        capture_output=True,
    )
    return r.stdout.decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="YYYY-MM-DD 이후만 (기본: 전체)")
    ap.add_argument("--until", default=None, help="YYYY-MM-DD 이전만 (기본: 전체)")
    args = ap.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    posts = json.load(open("tasso_postlist.json", encoding="utf-8"))
    for p in posts:
        p["dt"] = datetime.datetime.fromtimestamp(p["addDate"] / 1000)   # KST 유지

    sel = posts
    if args.since:
        lo = datetime.datetime.strptime(args.since, "%Y-%m-%d")
        sel = [p for p in sel if p["dt"] >= lo]
    if args.until:
        hi = datetime.datetime.strptime(args.until, "%Y-%m-%d")
        sel = [p for p in sel if p["dt"] <= hi]
    sel = sorted(sel, key=lambda p: p["dt"])

    print(f"대상 {len(sel)}건 / 목록 전체 {len(posts)}건 "
          f"({sel[0]['dt'].date()} ~ {sel[-1]['dt'].date()})")
    sys.stdout.flush()

    failed, got, skipped = [], 0, 0
    for i, p in enumerate(sel, 1):
        path = os.path.join(OUTDIR, f"{p['dt']:%Y%m%d}_{p['logNo']}.html")
        if os.path.exists(path) and os.path.getsize(path) > MIN_BYTES:
            skipped += 1
            continue

        html = ""
        for attempt in range(1, RETRIES + 1):
            html = fetch(p["logNo"])
            if len(html) > MIN_BYTES:
                break
            print(f"  ! retry {attempt}/{RETRIES} logNo={p['logNo']} len={len(html)}")
            sys.stdout.flush()
            time.sleep(3.0)

        if len(html) <= MIN_BYTES:
            failed.append((p["logNo"], f"{p['dt']:%Y-%m-%d}", len(html), p["title"][:60]))
            print(f"  ✗ FAIL logNo={p['logNo']} {p['dt']:%Y-%m-%d} len={len(html)}")
            sys.stdout.flush()
            time.sleep(1.0)
            continue

        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        got += 1
        imgs = len(re.findall(r"<img[^>]+", html))
        if i % 10 == 0 or i <= 3:
            print(f"  [{i:3d}/{len(sel)}] {p['dt']:%Y-%m-%d} {len(html):>7,}B img={imgs:>3} "
                  f"{p['title'][:38]}")
            sys.stdout.flush()
        time.sleep(1.0)

    print(f"\n완료 — 신규 {got} · 기존 skip {skipped} · 실패 {len(failed)}")
    if failed:
        print("=== 실패 목록 (logNo, 날짜, 응답길이, 제목) ===")
        for row in failed:
            print("  ", row)
        json.dump([{"logNo": a, "date": b, "bytes": c, "title": d} for a, b, c, d in failed],
                  open("harvest_failures.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("-> harvest_failures.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
