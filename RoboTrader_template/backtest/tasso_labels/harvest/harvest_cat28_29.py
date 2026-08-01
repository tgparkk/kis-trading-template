"""카테고리 28(주식기법 분석)·29(시황이슈 정리)의 최근 2년 글 수집.

기존 수집은 32(트레이딩 기록)만이었다 = 최근 2년 73건 중 44건(60%).
방법론 설명은 28 에 있을 공산이 크다.
"""
import datetime
import html
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
CUT = datetime.datetime(2024, 8, 1)
PARA = re.compile(r'<p[^>]*class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</p>', re.S)
TAG = re.compile(r"<[^>]+>")


def api(url, ref):
    r = subprocess.run(["curl", "-s", "-m", "30", "-A", UA, "-H", f"Referer: {ref}",
                        "-H", "Accept: application/json, text/plain, */*", url],
                       capture_output=True)
    try:
        return json.loads(r.stdout.decode("utf-8", "replace"))
    except Exception:
        return None


def main() -> int:
    os.makedirs("posts2", exist_ok=True)
    os.makedirs("text2", exist_ok=True)
    got = []
    for cat, name in ((28, "주식기법분석"), (29, "시황이슈정리")):
        ref = f"https://m.blog.naver.com/PostList.naver?blogId={BLOG}&categoryNo={cat}"
        seen, picked = set(), []
        for page in range(1, 40):
            d = api(f"https://m.blog.naver.com/api/blogs/{BLOG}/post-list"
                    f"?categoryNo={cat}&itemCount=30&page={page}", ref)
            its = (d or {}).get("result", {}).get("items", [])
            fresh = [x for x in its if x["logNo"] not in seen]
            if not fresh:
                break
            for x in fresh:
                seen.add(x["logNo"])
                dt = datetime.datetime.fromtimestamp(x["addDate"] / 1000)
                if dt >= CUT:
                    picked.append((dt, x))
            if min(datetime.datetime.fromtimestamp(x["addDate"] / 1000) for x in fresh) < CUT:
                break
            time.sleep(0.4)

        print(f"\n=== [{cat}] {name} — 최근 2년 {len(picked)}건 ===")
        for dt, x in sorted(picked):
            path = f"posts2/{cat}_{dt:%Y%m%d}_{x['logNo']}.html"
            if not (os.path.exists(path) and os.path.getsize(path) > 5000):
                r = subprocess.run(["curl", "-s", "-m", "40", "-A", UA,
                                    "-H", f"Referer: https://m.blog.naver.com/{BLOG}",
                                    f"https://m.blog.naver.com/PostView.naver"
                                    f"?blogId={BLOG}&logNo={x['logNo']}"], capture_output=True)
                open(path, "w", encoding="utf-8").write(r.stdout.decode("utf-8", "replace"))
                time.sleep(1.0)
            src = open(path, encoding="utf-8").read()
            txt = "\n".join(
                re.sub(r"[\s​\xa0]+", " ", html.unescape(TAG.sub(" ", p))).strip()
                for p in PARA.findall(src))
            open(f"text2/{cat}_{dt:%Y%m%d}_{x['logNo']}.txt", "w", encoding="utf-8").write(txt)
            imgs = len(re.findall(r"<img[^>]+", src))
            got.append((cat, dt, x["titleWithInspectMessage"], len(txt), imgs))
            print(f"  {dt:%Y-%m-%d}  텍스트 {len(txt):>6,}자  img {imgs:>3}  "
                  f"{x['titleWithInspectMessage'][:52]}")

    print(f"\n합계 {len(got)}건 수집 · 텍스트 {sum(g[3] for g in got):,}자 · 이미지 {sum(g[4] for g in got):,}장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
