"""프리셋 추출을 **독립 정답**으로 채점한다.

정답 = `../calc_table.csv` — 계산기 캡처 51장을 **사람이 직접 판독**한 표. 텍스트 추출기와
완전히 다른 경로(이미지·캡션)로 얻은 것이라 추출기 자신의 회수율 착시가 끼어들 수 없다.

⚠️ 7차 교훈("정답 라벨이 후보 집합에 실제로 존재하는가를 먼저 단언하라")에 따라,
   정답이 없는 행은 채점에서 **제외**하고 그 수를 함께 출력한다.

🔴 **채점 기준이 결함을 가린 사례 — 이 파일 자신이 그랬다.**
   v4 초판 보고는 「접두무시 50/51(98%)」를 함께 실었다. 그 기준은 `사분위 하이브리드` 와
   `하이브리드` 를 **같다고 채점한다.** 그런데 둘의 차이가 바로 이 트랙이 원하는 것 —
   깊이 분포 규격 `Q` 를 어느 모드로 계산했는가(`ANCHOR_STRATEGY.md` §3) — 이다.
   즉 **관대한 기준이 「정보 손실」을 「표기 흔들림」으로 오분류**했고, 98% 라는 수치가
   결함을 가렸다. ⇒ 주 지표는 **정확일치**. 접두무시는 *무엇을 가리는지 함께 적을 때만* 참고치다.

⚠️ 정확일치의 잔여를 「추출 실패」로 읽지 말 것 — 정답 쪽 전사(轉寫)가 더 짧을 수 있다.
   실제로 2026-03-20 폴라리스AI 는 본문 캡션이 `사분위수(Q1~Q3) 하이브리드` 인데
   `calc_table` 전사는 `사분위 하이브리드` 로 줄여 적혀 있다. 정보는 v4 쪽이 **더 많다.**
   그래서 **(base, mode) 쌍 일치**를 함께 낸다 — 이게 층화에 실제로 쓰이는 단위다.
   `calc_table.csv` 는 독립 정답이므로 **맞추려고 고치지 않는다**(고치면 독립성이 사라진다).
"""
import csv
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = ("하이브리드", "안정형", "공격형", "표준형")


def norm(s):
    return re.sub(r"\s+", "", s)


def base_preset(s):
    for p in BASE:
        if p in s:
            return p
    return ""


def mode_preset(s):
    """정답·추출 양쪽에 같은 규칙을 적용한다(정답만 관대하게 읽으면 채점이 무너진다)."""
    if re.search(r"(?:사|4)\s*분위", s):
        return "사분위"
    m = re.search(r"HDR\s*(\d{1,3})", s)
    if m:
        return "HDR" + m.group(1)
    if "HDR" in s:
        return "HDR"
    return "미표기"


def load(path, col="preset"):
    return {(r["post_date"], norm(r["stock_name"])): r.get(col, "")
            for r in csv.DictReader(open(path, encoding="utf-8-sig"))}


def main() -> int:
    v3 = load("../labels_final.csv")
    v4 = load("../labels_v4.csv")
    scored, skipped = [], 0
    for c in csv.DictReader(open("../calc_table.csv", encoding="utf-8-sig")):
        truth = c["preset"].strip()
        d = c["date"]
        key = (f"{d[:4]}-{d[4:6]}-{d[6:8]}", norm(c["stock"]))
        if not truth or truth == "?":
            skipped += 1
            continue
        scored.append((key, truth, v3.get(key, "<라벨없음>"), v4.get(key, "<라벨없음>")))

    n = len(scored)
    print("=== 주 지표 ===")
    for tag, fn in (("정확일치(원문)", lambda x: x),
                    ("(base,mode) 쌍", lambda x: (base_preset(x), mode_preset(x)))):
        a = sum(1 for _, t, x, _ in scored if fn(x) == fn(t))
        b = sum(1 for _, t, _, y in scored if fn(y) == fn(t))
        print(f"  {tag:<16}: v3 {a}/{n} ({a/n*100:.0f}%)  →  v4 {b}/{n} ({b/n*100:.0f}%)")

    a = sum(1 for _, t, x, _ in scored if base_preset(x) == base_preset(t))
    b = sum(1 for _, t, _, y in scored if base_preset(y) == base_preset(t))
    hidden = sum(1 for _, t, _, _ in scored if mode_preset(t) != "미표기")
    print(f"\n=== 참고치(주 지표로 쓰지 말 것) ===")
    print(f"  접두무시(base만)  : v3 {a}/{n} ({a/n*100:.0f}%)  →  v4 {b}/{n} ({b/n*100:.0f}%)")
    print(f"  ⚠️ 이 기준이 가리는 것: 정답 {n}건 중 **{hidden}건이 모드 수식어를 달고 있고**, "
          f"base 만 보면 그 {hidden}건의 모드가 맞든 틀리든 전부 정답 처리된다.")
    print(f"정답 없는 행 제외 {skipped}건")

    print("\n=== v4 잔여 불일치 (정확일치 기준) ===")
    bad = [(k, t, y) for k, t, _, y in scored if y != t]
    for k, t, y in bad:
        same = "  (모드·base 는 일치)" if (base_preset(y), mode_preset(y)) == \
                                        (base_preset(t), mode_preset(t)) else ""
        print(f"   {k[0]} {k[1]:<16} 정답={t:<22} v4={y}{same}")
    if not bad:
        print("   없음")

    print("\n=== 모드 수식어가 붙은 정답 전수 ===")
    for k, t, _, y in scored:
        if mode_preset(t) != "미표기":
            print(f"   {k[0]} {k[1]:<16} 정답={t:<22} v4={y:<24} mode={mode_preset(y)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
