"""본문 HTML -> 텍스트 추출.

se-main-container 를 통째로 자르려던 첫 판본은 첫 문단에서 끊겼다
(중첩 div 라 non-greedy 가 조기 종료). 문단 단위로 전부 긁는 방식으로 교체.

v2 (2026-08-02, 전수 확장):
  블로그가 **에디터 두 세대**를 쓴다. SE3(2019~) 는 `p.se-text-paragraph`,
  구 SE2(2017~2018) 는 `#postViewArea` 안에 `<br>` 로만 줄을 나눈다.
  SE3 만 보던 v1 을 2017~2018 글에 그대로 돌리면 **본문 0자 = 라벨 0건**인데
  예외도 경고도 안 난다. 두 경로를 모두 지원하고, 결과가 0자면 명시적으로 센다.
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
PVA = re.compile(r'<div[^>]+id="postViewArea"[^>]*>(.*?)<!-- // \s*컨텐츠', re.S)
PVA2 = re.compile(r'<div[^>]+id="postViewArea"[^>]*>(.*)', re.S)
BRK = re.compile(r"(?:<br\s*/?>|</p>|</div>|</td>|</tr>)", re.I)


def _clean(parts):
    txt = "\n".join(re.sub(r"[ \t​\xa0]+", " ", p).strip() for p in parts)
    txt = "\n".join(l for l in txt.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def _inline(chunk: str) -> str:
    """인라인 태그는 **공백이 아니라 빈 문자열**로 지운다.

    🔴 태그를 공백으로 치환하면 한 단어가 두 스팬에 걸쳐 있을 때 단어가 쪼개진다.
       실제로 2024-04-18 글은 저자가 「수」와 「익률」을 다른 색으로 칠해
       `…돌파 / 수</span><span…>익률 3.53%…` 이었고, 공백 치환 결과 `수 익률` 이 되어
       항목 정규식이 그 글 **전체**를 놓쳤다(라벨 0건). 예외도 경고도 나지 않는다.
       줄바꿈은 <br> 만 담당하므로 나머지는 지우는 것이 맞다.
    """
    chunk = re.sub(r"<br\s*/?>", "\n", chunk, flags=re.I)
    return html.unescape(TAG.sub("", chunk))


def extract_text(html_src: str) -> str:
    """SE3 문단 우선, 없으면 구 에디터 #postViewArea 를 <br> 단위로."""
    parts = [_inline(p) for p in PARA.findall(html_src)]
    if parts:
        return _clean(parts)

    m = PVA.search(html_src) or PVA2.search(html_src)
    if not m:
        return ""
    body = m.group(1)
    # 스크립트/스타일 제거 후 줄바꿈 태그를 개행으로
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    body = BRK.sub("\n", body)
    lines = [html.unescape(TAG.sub("", l)) for l in body.split("\n")]
    return _clean(lines)


def main() -> int:
    files = sorted(glob.glob("posts/*.html"))
    os.makedirs("text", exist_ok=True)
    rows, empty = [], []
    for f in files:
        src = open(f, encoding="utf-8").read()
        txt = extract_text(src)
        base = os.path.basename(f).replace(".html", ".txt")
        open(os.path.join("text", base), "w", encoding="utf-8").write(txt)
        if len(txt) < 200:
            empty.append((base, len(txt)))
        rows.append((
            os.path.basename(f)[:8],
            len(txt),
            len(re.findall(r"[+-]?\d+\.\d+\s*%", txt)),      # 수익률 표기
            len(re.findall(r"\d{1,3},\d{3}", txt)),           # 가격 표기
            len(PARA.findall(src)),
        ))

    tot = len(rows)
    print(f"{tot}건 · 텍스트 평균 {sum(r[1] for r in rows)//max(tot,1):,}B "
          f"· %표기 총 {sum(r[2] for r in rows)} · 가격표기 총 {sum(r[3] for r in rows)}")
    print(f"\n🔴 본문 200자 미만 {len(empty)}건 (이 글들은 본문 라벨이 구조적으로 0이다)")
    for b, n in empty:
        print(f"   {b} {n}자")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
