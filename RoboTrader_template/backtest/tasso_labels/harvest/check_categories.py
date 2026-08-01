"""블로그 전체 카테고리 목록 + 카테고리별 글 수·기간 확인.

지금까지 categoryNo=32(트레이딩 기록)만 수집했다. 전체 범위를 먼저 재고 답한다.
"""
import datetime
import io
import json
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BLOG = "mbc3110"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def get(url, ref):
    r = subprocess.run(["curl", "-s", "-m", "30", "-A", UA, "-H", f"Referer: {ref}",
                        "-H", "Accept: application/json, text/plain, */*", url],
                       capture_output=True)
    try:
        return json.loads(r.stdout.decode("utf-8", "replace"))
    except Exception:
        return None


def main() -> int:
    ref = f"https://m.blog.naver.com/PostList.naver?blogId={BLOG}"
    cats = get(f"https://m.blog.naver.com/api/blogs/{BLOG}/category-list", ref)
    items = []
    if cats and cats.get("isSuccess"):
        res = cats.get("result", {})
        items = (res.get("mylogCategoryList") or res.get("categories")
                 or res.get("categoryList") or [])
    if not items:
        print("카테고리 API 실패 — 응답:", str(cats)[:200])
        return 1

    print(f"{'No':>5} {'글수':>6}  카테고리")
    flat = []
    def walk(lst, depth=0):
        for c in lst:
            no = c.get("categoryNo")
            nm = c.get("categoryName", "")
            cnt = c.get("postCnt", c.get("count", "?"))
            print(f"{str(no):>5} {str(cnt):>6}  {'  '*depth}{nm}")
            flat.append((no, nm, cnt))
            for k in ("subCategoryList", "children", "subCategories"):
                if c.get(k):
                    walk(c[k], depth + 1)
    walk(items)

    print("\n=== 최근 2년(2024-08-01~) 글 수 ===")
    cut = datetime.datetime(2024, 8, 1)
    for no, nm, cnt in flat:
        if no in (None, 0):
            continue
        seen, recent, oldest, newest = set(), 0, None, None
        for page in range(1, 40):
            d = get(f"https://m.blog.naver.com/api/blogs/{BLOG}/post-list"
                    f"?categoryNo={no}&itemCount=30&page={page}",
                    f"https://m.blog.naver.com/PostList.naver?blogId={BLOG}&categoryNo={no}")
            its = (d or {}).get("result", {}).get("items", [])
            fresh = [x for x in its if x["logNo"] not in seen]
            if not fresh:
                break
            for x in fresh:
                seen.add(x["logNo"])
                dt = datetime.datetime.fromtimestamp(x["addDate"] / 1000)
                oldest = dt if oldest is None or dt < oldest else oldest
                newest = dt if newest is None or dt > newest else newest
                recent += dt >= cut
            time.sleep(0.5)
        rng = f"{oldest:%Y-%m-%d} ~ {newest:%Y-%m-%d}" if oldest else "-"
        print(f"  [{no}] {nm:<16} 전체 {len(seen):>4}건 · 최근2년 {recent:>3}건 · {rng}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
