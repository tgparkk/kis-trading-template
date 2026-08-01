"""태쏘 블로그 '트레이딩 기록' 카테고리 글 목록 수집 (읽기 전용, 공개글).

목록 API만 호출한다. 본문은 별도 단계.
"""
import json
import subprocess
import sys
import time

BLOG = "mbc3110"
CATEGORY = 32
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
REFERER = f"https://m.blog.naver.com/PostList.naver?blogId={BLOG}&categoryNo={CATEGORY}"


def fetch_page(page: int) -> dict:
    url = (f"https://m.blog.naver.com/api/blogs/{BLOG}/post-list"
           f"?categoryNo={CATEGORY}&itemCount=30&page={page}")
    out = subprocess.run(
        ["curl", "-s", "-m", "30", "-A", UA, "-H", f"Referer: {REFERER}",
         "-H", "Accept: application/json, text/plain, */*", url],
        capture_output=True, check=True,
    ).stdout.decode("utf-8", "replace")
    return json.loads(out)


def main() -> int:
    all_items = []
    seen = set()
    for page in range(1, 30):
        data = fetch_page(page)
        if not data.get("isSuccess"):
            print(f"page {page}: API 실패 -> 중단", file=sys.stderr)
            break
        items = data.get("result", {}).get("items", [])
        if not items:
            print(f"page {page}: 항목 0 -> 종료")
            break
        fresh = [it for it in items if it["logNo"] not in seen]
        for it in fresh:
            seen.add(it["logNo"])
        all_items.extend(fresh)
        print(f"page {page}: {len(items)}건 (신규 {len(fresh)}) 누적 {len(all_items)}")
        if not fresh:
            break
        time.sleep(1.0)  # 예의상 간격

    with open("tasso_postlist.json", "w", encoding="utf-8") as fh:
        json.dump(all_items, fh, ensure_ascii=False, indent=1)

    print(f"\n총 {len(all_items)}건 저장 -> tasso_postlist.json")
    if all_items:
        print("\n--- 필드 키 ---")
        print(sorted(all_items[0].keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
