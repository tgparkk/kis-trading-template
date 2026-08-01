"""본문 HTML -> 텍스트 추출 + 매매 데이터가 텍스트인지 이미지인지 진단.

se-main-container 를 통째로 자르려던 첫 판본은 첫 문단에서 끊겼다
(중첩 div 라 non-greedy 가 조기 종료). 문단 단위로 전부 긁는 방식으로 교체.
"""
import glob
import html
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TAG = re.compile(r"<[^>]+>")
PARA = re.compile(r'<p[^>]*class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</p>', re.S)


def extract_text(html_src: str) -> str:
    parts = [html.unescape(TAG.sub(" ", p)) for p in PARA.findall(html_src)]
    txt = "\n".join(re.sub(r"[ \t​\xa0]+", " ", p).strip() for p in parts)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def main() -> int:
    files = sorted(glob.glob("posts/*.html"))
    os.makedirs("text", exist_ok=True)
    rows = []
    for f in files:
        src = open(f, encoding="utf-8").read()
        txt = extract_text(src)
        base = os.path.basename(f).replace(".html", ".txt")
        open(os.path.join("text", base), "w", encoding="utf-8").write(txt)
        rows.append((
            os.path.basename(f)[:8],
            len(txt),
            len(re.findall(r"[+-]?\d+\.\d+\s*%", txt)),      # 수익률 표기
            len(re.findall(r"\d{1,3},\d{3}", txt)),           # 가격 표기
            len(PARA.findall(src)),
        ))

    print(f"{'날짜':<10}{'텍스트B':>9}{'%표기':>7}{'가격표기':>9}{'문단':>6}")
    for r in rows:
        print(f"{r[0]:<10}{r[1]:>9,}{r[2]:>7}{r[3]:>9}{r[4]:>6}")

    tot = len(rows)
    print(f"\n합계 {tot}건 · 텍스트 평균 {sum(r[1] for r in rows)//tot:,}B "
          f"· %표기 총 {sum(r[2] for r in rows)} · 가격표기 총 {sum(r[3] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
