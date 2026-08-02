"""매핑 실패 이름의 **사유 추정** — 보고 전용. 🔴 매핑에 쓰지 않는다.

README §생존편향이 `수산중공업` 으로 한 번 보여 준 절차다: 접두 조회로 후보를 보고
「상폐·사명변경」인지 「저자 오타」인지 성격만 적는다. **자동 해소하지 않는다** —
이런 매칭은 유사매칭이고, 7차 교훈대로 *최소오차 채점은 정답이 없어도 조용히 아무 후보나 매칭한다.*

⚠️ 이 구분이 필요한 이유: 매핑 실패율을 **생존편향의 상한**으로 읽는데,
   저자 오타가 섞여 있으면 그 상한이 과대평가된다.
"""
import csv
import io
import json
import subprocess
import sys
import time
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def probe(q):
    url = ("https://ac.stock.naver.com/ac?q=" + urllib.parse.quote(q) + "&target=stock")
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return []
    return [(it["name"], it["code"]) for it in items if it.get("nationCode") == "KOR"][:6]


def main() -> int:
    led = list(csv.DictReader(open("prose_incorporation.csv", encoding="utf-8-sig")))
    names = sorted({r["name"] for r in led
                    if r["role"] in ("entry", "order_placed") and not r["code"]})
    print(f"매핑 실패 고유 이름 {len(names)}개 — 접두 조회로 성격만 본다 (매핑 안 함)\n")
    for n in names:
        pre = n[:2] if len(n) > 2 else n
        hits = probe(pre)
        print(f"  {n:<14} 접두'{pre}' -> " +
              (", ".join(f"{a}({b})" for a, b in hits) if hits else "(후보 없음)"))
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
