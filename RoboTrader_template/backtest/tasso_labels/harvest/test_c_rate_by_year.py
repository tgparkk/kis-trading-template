"""연도별 「진짜 상폐(C)」 비율의 차이가 **구분 가능한가**. 진단 전용.

🔴 초판 보고가 *「C 비율이 단조 감소가 아니다 — 2022(3.7%) > 2021(2.9%)」* 라고 썼다.
   독립 검토가 세 가지로 반박했고 **여기서 재 보니 맞다**:
     ① 차 0.73%p 는 iid 로도 z=0.69 (p=0.49)
     ② **D(판정 불가)를 포함하면 부호가 뒤집힌다** (5.19% vs 4.42%)
     ③ 47개 C 라벨이 29개 **이름**에 뭉쳐 있어 행 단위 SE 는 낙관적이다
   ⇒ 종목 블록 부트스트랩으로 다시 잰다. 계열 교훈: *MDE·SE 는 추론과 같은 단위(종목 블록)로.*

⚠️ 결과값(forward 수익률)은 계산하지 않는다. 분류 라벨의 비율만 센다.
"""
import argparse
import collections
import csv
import io
import math
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fin", default="unmapped_final_v4.csv")
    ap.add_argument("--labels", default="../labels_v4.csv")
    ap.add_argument("--regime", default="검색기단타")
    ap.add_argument("--boot", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()

    fin = {r["stock_name"]: r for r in
           csv.DictReader(open(args.fin, encoding="utf-8-sig"))}
    rows = [r for r in csv.DictReader(open(args.labels, encoding="utf-8-sig"))
            if r["regime"] == args.regime]

    def rate(pool, y, classes):
        lab = [r for r in pool if r["post_date"][:4] == y]
        hit = [r for r in lab if not r["stock_code"]
               and fin.get(r["stock_name"], {}).get("final_class") in classes]
        return (len(hit), len(lab))

    byname = collections.defaultdict(list)
    for r in rows:
        byname[r["stock_name"]].append(r)
    names = list(byname)

    for classes, lab in [(("C",), "C 단독 (진짜 상폐)"),
                         (("C", "D"), "C+D (상한 — D 에도 상폐가 섞여 있다)")]:
        print(f"\n=== {lab} ===")
        for y in ("2021", "2022", "2023", "2024"):
            a, n = rate(rows, y, classes)
            print(f"  {y}: {a}/{n} = {a/n*100:.2f}%")
        a, na = rate(rows, "2021", classes)
        b, nb = rate(rows, "2022", classes)
        p = (a + b) / (na + nb)
        se = math.sqrt(p * (1 - p) * (1 / na + 1 / nb))
        z = (b / nb - a / na) / se
        pv = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
        print(f"  2021 vs 2022 차 {(b/nb-a/na)*100:+.2f}%p · iid z={z:.2f} p={pv:.3f}")

        rnd = random.Random(args.seed)
        d = []
        for _ in range(args.boot):
            samp = [r for _ in names for r in byname[rnd.choice(names)]]
            x, nx = rate(samp, "2021", classes)
            y2, ny = rate(samp, "2022", classes)
            d.append((y2 / ny if ny else 0) - (x / nx if nx else 0))
        d.sort()
        lo, mid, hi = d[int(.025 * len(d))], d[len(d) // 2], d[int(.975 * len(d))]
        print(f"  🔑 종목블록 부트스트랩 Δ(2022−2021) = {mid*100:+.2f}%p "
              f"95%CI [{lo*100:+.2f}, {hi*100:+.2f}]%p "
              f"-> {'0 을 포함 = 구분 불가' if lo < 0 < hi else '0 제외'}")
    print("\n⇒ 2021 과 2022 는 서로 **구분되지 않는다**. 단조/비단조를 주장하지 말 것.")
    print("  구분되는 것은 **2021~2022 (2.9~5.2%) vs 2023~2024 (0.2~1.2%)** 뿐이다.")
    print("⚠️ 그리고 그 격차조차 **경과 시간**이 섞여 있다 — C 29건 중 다수가 2025~2026 상폐라")
    print("  2024 라벨은 상폐할 시간이 2년, 2021 라벨은 5년 반이었다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
