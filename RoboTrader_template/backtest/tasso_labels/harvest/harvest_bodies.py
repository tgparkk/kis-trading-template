"""목록에서 뽑은 글의 본문을 내려받아 로컬 저장 (읽기 전용, 공개글, 1초 간격)."""
import datetime
import json
import os
import re
import subprocess
import sys
import time

BLOG = "mbc3110"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
OUTDIR = "posts"
CUTOFF = datetime.datetime(2024, 8, 1)


def fetch(log_no: int) -> str:
    url = f"https://m.blog.naver.com/PostView.naver?blogId={BLOG}&logNo={log_no}"
    r = subprocess.run(
        ["curl", "-s", "-m", "40", "-A", UA,
         "-H", f"Referer: https://m.blog.naver.com/{BLOG}", url],
        capture_output=True,
    )
    return r.stdout.decode("utf-8", "replace")


def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)
    posts = json.load(open("tasso_postlist.json", encoding="utf-8"))
    for p in posts:
        p["dt"] = datetime.datetime.fromtimestamp(p["addDate"] / 1000)
    recent = sorted((p for p in posts if p["dt"] >= CUTOFF), key=lambda p: p["dt"])

    print(f"대상 {len(recent)}건 ({recent[0]['dt'].date()} ~ {recent[-1]['dt'].date()})")
    for i, p in enumerate(recent, 1):
        path = os.path.join(OUTDIR, f"{p['dt']:%Y%m%d}_{p['logNo']}.html")
        if os.path.exists(path) and os.path.getsize(path) > 5000:
            continue
        html = fetch(p["logNo"])
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        imgs = len(re.findall(r'<img[^>]+', html))
        print(f"  [{i:2d}/{len(recent)}] {p['dt']:%Y-%m-%d} {len(html):>7,}B img={imgs:>3} "
              f"{p['titleWithInspectMessage'][:38]}")
        sys.stdout.flush()
        time.sleep(1.0)
    print("완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
