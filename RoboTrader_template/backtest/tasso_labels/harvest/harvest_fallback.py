"""구(舊) 에디터 글 본문 보강 수집.

`m.blog.naver.com/PostView.naver` 는 **구 에디터(SmartEditor 2.x) 글의 본문을 아예 싣지 않는다**.
2017~2018 글 11건이 이 경우이며, 모바일 HTML 만 보면 본문 0자라 **조용히 라벨 0건**이 된다.
(제목에 종목이 있어 제목 파서로는 잡히므로, 대조를 안 했으면 못 봤을 결함이다.)

PC 엔드포인트(`blog.naver.com/PostView.naver?...&redirect=Dlog`)는 본문을 `#postViewArea` 에 싣는다.
본문이 비어 있는 파일만 골라 재수집한다. 읽기 전용·공개글·1초 간격.
"""
import glob
import io
import json
import os
import re
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BLOG = "mbc3110"
OUTDIR = "posts"
PARA = re.compile(r'<p[^>]*class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</p>', re.S)


def fetch_pc(log_no: str) -> str:
    url = (f"https://blog.naver.com/PostView.naver?blogId={BLOG}&logNo={log_no}"
           "&redirect=Dlog&widgetTypeCall=true&directAccess=false")
    r = subprocess.run(["curl", "-s", "-m", "40", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def main() -> int:
    targets = []
    for f in sorted(glob.glob(os.path.join(OUTDIR, "*.html"))):
        src = open(f, encoding="utf-8").read()
        if not PARA.findall(src) and "postViewArea" not in src:
            targets.append(f)

    print(f"본문 0자 파일 {len(targets)}건 -> PC 엔드포인트로 재수집")
    fixed, failed = 0, []
    for f in targets:
        log_no = os.path.basename(f).replace(".html", "").split("_")[1]
        html = fetch_pc(log_no)
        if "postViewArea" in html and len(html) > 20000:
            open(f, "w", encoding="utf-8").write(html)
            fixed += 1
            print(f"  ✓ {os.path.basename(f)} -> {len(html):,}B")
        else:
            failed.append((log_no, len(html)))
            print(f"  ✗ {os.path.basename(f)} len={len(html)}")
        sys.stdout.flush()
        time.sleep(1.0)

    print(f"\n보강 {fixed} · 실패 {len(failed)}")
    if failed:
        json.dump(failed, open("harvest_fallback_failures.json", "w",
                               encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
