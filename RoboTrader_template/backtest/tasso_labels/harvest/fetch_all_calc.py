"""계산기 이미지 52장 전부 수집 + **소속 종목** 연결.

캡션에는 종목명이 없다. 문서 순서를 훑어 「N. 종목 / 방법 / 수익률」 헤더를 상태로 들고 가며
그 뒤에 나오는 계산기 캡션 이미지에 종목을 귀속시킨다. (레벨만 있고 종목이 없으면 앵커 역산 불가)
"""
import glob
import html
import io
import json
import os
import re
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

IMG = re.compile(r'<img[^>]+?(?:data-lazy-src|src)="(https://[^"]+?(?:pstatic|naver)[^"]*)"', re.I)
PARA = re.compile(r'<p[^>]*class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</p>', re.S)
HEAD = re.compile(r"^\s*(?:\d+\s*[.,]?\s*)?([^/\n]{2,24}?)\s*/\s*([^/\n]{2,40}?)\s*/\s*수익률")
TAG = re.compile(r"<[^>]+>")


def main() -> int:
    os.makedirs("calcimg", exist_ok=True)
    rows = []
    for f in sorted(glob.glob("posts/*.html")):
        date = os.path.basename(f)[:8]
        body = open(f, encoding="utf-8").read().split('class="se-main-container"', 1)[-1]

        toks = [(m.start(), "img", m.group(1)) for m in IMG.finditer(body)]
        for m in PARA.finditer(body):
            t = re.sub(r"[\s​\xa0]+", " ", html.unescape(TAG.sub(" ", m.group(1)))).strip()
            if t:
                toks.append((m.start(), "para", t))
        toks.sort()

        last_img, stock = None, ""
        for _, kind, val in toks:
            if kind == "img":
                last_img = val
                continue
            hm = HEAD.match(val)
            if hm:
                stock = re.sub(r"^\d+\s*[.,]?\s*", "", hm.group(1).strip()).strip()
            elif val.startswith("▲") and "계산기" in val and last_img:
                rows.append({"date": date, "stock": stock, "caption": val[:80],
                             "url": re.sub(r"\?type=w\d+", "", last_img) + "?type=w966"})
                last_img = None

    for i, r in enumerate(rows):
        cap = r["caption"]
        ver = "1.4" if "1.4" in cap else ("1.3" if "1.3" in cap else "?")
        pre = next((p for p in ("하이브리드", "안정형", "표준형", "공격형", "반등폭")
                    if p in cap), "?")
        r["idx"], r["ver"], r["preset"] = i, ver, pre
        r["file"] = f"calcimg/{i:02d}_{r['date']}_{pre}.png"
        if not (os.path.exists(r["file"]) and os.path.getsize(r["file"]) > 3000):
            subprocess.run(["curl", "-s", "-m", "40", "-A", "Mozilla/5.0",
                            "-H", "Referer: https://m.blog.naver.com/mbc3110",
                            r["url"], "-o", r["file"]])
            time.sleep(0.35)

    json.dump(rows, open("calc_images.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for r in rows if os.path.exists(r["file"]) and os.path.getsize(r["file"]) > 3000)
    print(f"이미지 {len(rows)}장 · 다운로드 성공 {ok}장 · 종목 미귀속 "
          f"{sum(1 for r in rows if not r['stock'])}장\n")
    print(f"{'#':>3} {'날짜':<10}{'종목':<16}{'ver':<5}{'프리셋':<8}{'크기':>9}")
    for r in rows:
        sz = os.path.getsize(r["file"]) if os.path.exists(r["file"]) else 0
        print(f"{r['idx']:>3} {r['date']:<10}{r['stock'][:14]:<16}{r['ver']:<5}"
              f"{r['preset']:<8}{sz:>9,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
