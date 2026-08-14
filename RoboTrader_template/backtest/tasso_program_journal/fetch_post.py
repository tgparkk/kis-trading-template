# -*- coding: utf-8 -*-
"""새 태쏘 글 1건만 수집한다. 기존 harvest 모듈(cat2829_common)의 fetch/parse 를 재사용.
라이브 트리 import 0건(cat2829_common 은 표준 라이브러리만 씀)."""
import sys, json, io
from pathlib import Path

H = Path(r"D:/GIT/kis-trading-template/RoboTrader_template/backtest/tasso_labels/harvest")
sys.path.insert(0, str(H))
import cat2829_common as C

OUT = Path(__file__).parent
LOG_NO = sys.argv[1] if len(sys.argv) > 1 else "224378680510"

src = C.fetch_html(LOG_NO)
(OUT / f"post_{LOG_NO}.html").write_text(src, encoding="utf-8")
print("html_bytes:", len(src))
print("source:", C.detect_source(src))
print("editor_ver:", C.page_editor_version(src))

txt = C.html_to_text(src)
(OUT / f"post_{LOG_NO}.txt").write_text(txt, encoding="utf-8")
print("text_len:", len(txt))

try:
    imgs = C.body_images(src)
    (OUT / f"post_{LOG_NO}_images.json").write_text(
        json.dumps(imgs, ensure_ascii=False, indent=1), encoding="utf-8")
    print("images:", len(imgs))
except Exception as e:
    print("images_err:", e)

print("---- first 3000 chars ----")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(txt[:3000])
