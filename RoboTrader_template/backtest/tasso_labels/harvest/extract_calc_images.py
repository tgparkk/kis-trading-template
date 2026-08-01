"""캡션이 「계산기」인 이미지만 골라 URL 추출.

캡션은 se-caption div 가 아니라 **「▲ …」 로 시작하는 일반 텍스트 문단**이다.
따라서 문서 순서대로 (이미지 | 문단) 토큰을 훑어 캡션 바로 앞 이미지를 짝짓는다.
"""
import glob
import html
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

IMG = re.compile(r'<img[^>]+?(?:data-lazy-src|src)="(https://[^"]+?(?:pstatic|naver)[^"]*)"', re.I)
PARA = re.compile(r'<p[^>]*class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</p>', re.S)
TAG = re.compile(r"<[^>]+>")


def main() -> int:
    out = []
    for f in sorted(glob.glob("posts/*.html")):
        date = os.path.basename(f)[:8]
        src = open(f, encoding="utf-8").read()
        body = src.split('class="se-main-container"', 1)[-1]

        toks = []
        for m in IMG.finditer(body):
            toks.append((m.start(), "img", m.group(1)))
        for m in PARA.finditer(body):
            t = re.sub(r"[\s​\xa0]+", " ",
                       html.unescape(TAG.sub(" ", m.group(1)))).strip()
            if t:
                toks.append((m.start(), "para", t))
        toks.sort()

        last_img = None
        for _, kind, val in toks:
            if kind == "img":
                last_img = val
            elif val.startswith("▲") and "계산기" in val and last_img:
                url = re.sub(r"\?type=w\d+", "", last_img) + "?type=w966"
                out.append({"date": date, "caption": val[:70], "url": url})
                last_img = None

    json.dump(out, open("calc_images.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"계산기 캡션 이미지 {len(out)}장 "
          f"({len({r['date'] for r in out})}개 글)")
    for r in out:
        print(f"  {r['date']}  {r['caption']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
