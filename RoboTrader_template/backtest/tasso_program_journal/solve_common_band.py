# -*- coding: utf-8 -*-
"""공통 밴드 비율 b₁ 공동 해법 — 종목별로 안 풀리는 scale 을 「프리셋이 같다」로 묶는다.

착상: 8/14 글의 건들은 프리셋이 전부 `HDR 60% / 표준형` 이다. 밴드가 프리셋의 함수라면
      b₁ = 1 − P / H 가 **종목이 달라도 같아야** 한다. 종목별로는 scale 이 안 풀려도
      **공유 파라미터 하나**로 묶으면 과결정계가 된다.

🔴 귀무 실측을 반드시 함께 낸다 — 앵커를 **엇갈리게 짝지은** 순열에서도 같은 정도로
   겹치면 이 결과는 아무 의미가 없다. (`METHOD.md` 의 「귀무 실측 게이트」 관례)

라이브 트리 import 0건.
"""
from __future__ import annotations

import itertools
import math
import random
import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import TARGETS, grid_prices, gross_ret, tick
from run_tests import CODES, DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
TOL = 0.025      # 레그 수익률 허용 잔차(%p) — 최소잔차 진단에서 gross 가 0.010~0.022 였다
BAND_TOL = 0.0025  # b₁ 일치 허용폭 (±0.25%p)

N_NULL = 20000
# 🔴 시드 고정 = 산출물 재현 가능. 값을 바꾸면 백분위가 바뀌므로 바꾸지 말 것.
NULL_SEED = 20260815


def say(s=""):
    print(s)
    OUT.append(s)


def feasible_P(legs, ranges, lo, hi):
    """잔차 TOL 이내로 모든 레그를 설명하는 매수 평단 P 의 집합."""
    out = []
    step = max(1, tick(lo) // 4)
    P = lo
    while P <= hi:
        if any(a <= P <= b for a, b in ranges):
            worst = 0.0
            ok = True
            for r in legs:
                S_ideal = P * (1 + r / 100.0)
                t = tick(S_ideal)
                S = round(S_ideal / t) * t
                if not any(a <= S <= b for a, b in ranges):
                    ok = False
                    break
                worst = max(worst, abs(gross_ret(P, S) * 100 - r))
            if ok and worst <= TOL:
                out.append(P)
        P += step
    return out


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# 공통 밴드 비율 b₁ — 공동 해법 + 귀무 실측\n")
    say(f"잔차 허용 **{TOL}%p** (gross) · b₁ 일치 허용폭 **±{BAND_TOL*100:.2f}%p**\n")

    trades = []
    for name, d0, d1, legs, fill in TARGETS:
        code = CODES[name]
        cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        post = cur.fetchall()
        cur.execute("SELECT high FROM daily_prices WHERE stock_code=%s AND date<=%s "
                    "ORDER BY date DESC LIMIT 20", (code, d0))
        anchor = max(r[0] for r in cur.fetchall())      # v2 앵커 H6 (등록일 포함 20일 최고 고가)
        ranges = [(r[2], r[1]) for r in post]
        lo, hi = min(r[2] for r in post), max(r[1] for r in post)
        Ps = feasible_P(legs, ranges, lo, hi)
        trades.append((name, fill, anchor, Ps))
        say(f"- **{name}** ({fill}) · 앵커 {anchor:,.0f} · 가능한 평단 **{len(Ps)}개** "
            + (f"({min(Ps):,.0f}~{max(Ps):,.0f})" if Ps else "🔴 없음"))

    say()
    trades = [t for t in trades if t[3]]
    say(f"복원 가능한 건 **{len(trades)}/{len(TARGETS)}**\n")

    # 🔴 격자는 **음수까지** 덮어야 한다. 앵커를 「최댓값」으로 정의했으므로, 격자를 b₁≥0 으로
    #    자르면 더 낮은 대체 앵커(=음수 b₁ 다수)만 손해를 봐서 진짜 앵커가 구조적으로 유리해진다.
    B0 = -0.30        # 격자 하한
    NB = 901          # −0.30 ~ +0.60, 0.1%p 간격
    PAD = int(BAND_TOL / 0.001)
    MEANINGFUL = int((0.03 - B0) / 0.001)   # 「눌림목」이라 부를 만한 b₁ ≥ 3% 구간의 시작 bin

    def mask(anchor, Ps):
        """이 (앵커, P집합) 이 덮는 b₁ 격자 비트마스크."""
        m = 0
        for P in Ps:
            c = int(round(((1 - P / anchor) - B0) / 0.001))
            for k in range(c - PAD, c + PAD + 1):
                if 0 <= k < NB:
                    m |= 1 << k
        return m

    def cov_masks(ms, floor_bin=0):
        """어떤 b₁ 하나가 동시에 설명하는 최대 건수 (+ 그 bin). floor_bin 미만은 무시."""
        keep = ((1 << NB) - 1) ^ ((1 << floor_bin) - 1)
        ms = [m & keep for m in ms]
        for k in range(len(ms), 0, -1):
            for sub in itertools.combinations(range(len(ms)), k):
                acc = ms[sub[0]]
                for j in sub[1:]:
                    acc &= ms[j]
                    if not acc:
                        break
                if acc:
                    return k, (acc & -acc).bit_length() - 1
        return 0, None

    def coverage(pairs, floor_bin=0):
        return cov_masks([mask(a, P) for a, P in pairs], floor_bin)

    def b_of(bin_):
        return (bin_ * 0.001 + B0) * 100

    real = [(t[2], t[3]) for t in trades]
    hit, b_bin = coverage(real)
    say(f"## 관측: 하나의 b₁ 이 최대 **{hit}/{len(trades)}건**을 동시에 설명 "
        f"(b₁ ≈ **{b_of(b_bin):.1f}%**)\n")

    hit_m, b_m = coverage(real, MEANINGFUL)
    if b_m is None:
        say("🔑 **「눌림목」이라 부를 만한 구간(b₁ ≥ 3%)에는 공통해가 아예 없다.**\n")
    else:
        say(f"🔑 **b₁ ≥ 3% 로 한정하면 최대 {hit_m}/{len(trades)}건** "
            f"(b₁ ≈ {b_of(b_m):.1f}%)\n")
    say(f"⚠️ 무제한 최적해 b₁ ≈ {b_of(b_bin):.1f}% 는 *「정해둔 자리까지 내려오면 산다」* 는")
    say("서술과 크기가 안 맞는다 — 사실상 **고점 근처에서 산다**는 뜻이다.\n")

    # 🔴 귀무는 **스케일을 보존**해야 한다. 앵커를 종목 간에 섞으면 가격 수준이 어긋나
    #    b₁ 이 무의미해져 무조건 깨진다 — 밴드 구조가 아니라 스케일을 검정한 꼴이 된다.
    #    올바른 귀무 = 「같은 종목의 **다른 가격**을 앵커로 썼어도 이만큼 겹치는가」.
    say("## 귀무 실측 — 스케일 보존\n")
    say("각 건의 앵커를 **그 종목 자신의 창 안 다른 가격**(종가 격자)으로 바꿔 같은 계산을 반복한다.")
    say("«앵커를 종목 간에 섞는» 귀무는 스케일이 어긋나 무조건 깨지므로 쓰지 않는다.\n")

    alt = []          # 건별 대체 앵커 후보 (그 종목 자신의 고가들)
    for name, fill, anchor, Ps in trades:
        code = CODES[name]
        d0, d1 = next((t[1], t[2]) for t in TARGETS if t[0] == name)
        cur.execute("SELECT high FROM daily_prices WHERE stock_code=%s AND date<=%s "
                    "ORDER BY date DESC LIMIT 20", (code, d0))
        alt.append(sorted({r[0] for r in cur.fetchall()}))

    # (건, 대체앵커) 마스크를 미리 만들어 둔다 — 조합마다 다시 계산하지 않는다.
    pre = [[mask(a, trades[i][3]) for a in alt[i]] for i in range(len(trades))]

    # 🔴 결함 이력: 여기가 `itertools.product(...)` 을 20000 에서 **자르는** 코드였다.
    #    product 는 마지막 자리가 가장 빨리 변하므로, 전체 1억 조합 중 앞 2만 개만 쓰면
    #    앞자리 종목들의 앵커가 **인덱스 0(= 최저 고가)에 못 박힌다**. 실측: 에스피지 1/19종 ·
    #    솔트룩스 1/19종 · 마키나락스 2/19종. 못 박힌 값이 최저 고가라 그 종목들은 구조적으로
    #    공통해에 못 껴 귀무 커버리지가 낮아지고 ⇒ **관측 백분위가 과소평가**된다.
    #    (changelog 결함 ②「앵커가 최댓값이라 진짜가 유리」의 거울상 — 귀무 결함 4번째)
    #    ⇒ 격자 절단이 아니라 **시드 고정 무작위 표본**으로 전 조합에서 균등 추출한다.
    rng = random.Random(NULL_SEED)
    null, null_m = [], []
    drawn = [set() for _ in alt]
    while len(null) < N_NULL:
        combo = [rng.randrange(len(a)) for a in alt]
        if all(alt[i][combo[i]] == trades[i][2] for i in range(len(trades))):
            continue
        for i, c in enumerate(combo):
            drawn[i].add(c)
        ms = [pre[i][combo[i]] for i in range(len(trades))]
        null.append(cov_masks(ms)[0])
        null_m.append(cov_masks(ms, MEANINGFUL)[0])
    ge = sum(1 for x in null if x >= hit)
    ge_m = sum(1 for x in null_m if x >= hit_m)

    # 🔑 자리별 실제 표집 종수를 산출물이 스스로 인쇄한다 — 절단형 귀무가 재발하면
    #    이 표에서 「1/19」 같은 값이 눈에 띈다. 대조 작업 없이 결함이 드러나게 하는 장치.
    total_combos = math.prod(len(a) for a in alt)
    say(f"자리별 실제 표집 앵커 종수 (전체 조합 {total_combos:,}개 중 {len(null):,} 표본):\n")
    say("| 종목 | 표집/전체 앵커 |")
    say("|---|---|")
    for i, (name, _, _, _) in enumerate(trades):
        say(f"| {name} | {len(drawn[i])}/{len(alt[i])} |")
    say()

    say(f"- 대체 앵커 조합 **{len(null)}개** · 최대 커버리지 평균 **{sum(null)/len(null):.2f}** "
        f"· 최대 **{max(null)}**")
    say(f"- 관측({hit}) 이상인 조합 **{ge}/{len(null)}** ⇒ 백분위 **{ge/len(null)*100:.1f}%**")
    say(f"- **b₁ ≥ 3% 한정**: 관측 {hit_m} · 귀무 평균 {sum(null_m)/len(null_m):.2f} "
        f"· 이상인 조합 {ge_m}/{len(null_m)} ⇒ 백분위 **{ge_m/len(null_m)*100:.1f}%**")
    say()
    pct = ge / len(null)
    pct_m = ge_m / len(null_m)
    if pct > 0.10 or pct_m > 0.10:
        say(f"🔴 **판정: 판별력 없음.** 같은 종목의 아무 고가나 앵커로 써도 이만큼 겹친다 ⇒ "
            "이 「공통 b₁」은 자료구조가 만든 우연이지 규칙의 증거가 아니다.")
        # 🔴 마지막 값은 **계산값을 쓴다.** 하드코딩하면 DB 가 움직였을 때 스크립트 «안»에
        #    낡은 숫자가 남는다(2026-08-15 실측: 33.1 로 박아뒀는데 계산값은 31.2 였다).
        say(f"🔑 ***귀무를 고칠 때마다 백분위가 올라갔다 — "
            f"0.3% → 0.6% → 7.6% → {pct*100:.1f}%.*** "
            "앞의 세 값은 전부 **내 귀무의 결함**이었다:")
        say("① 앵커를 종목 간에 섞음(스케일을 검정한 꼴) ② 격자를 `b₁ ≥ 0` 으로 잘라 "
            "진짜 앵커가 구조적으로 유리 ③ **`itertools.product` 를 20000 에서 절단** — "
            "앞자리 3종목의 앵커가 최저 고가에 못 박혀 귀무가 구조적으로 불리했다.")
        say("⇒ 🔑 ***신호가 사라질 때까지 귀무를 의심하라. 「유의하다」는 귀무의 강도에 대한 진술이다.***")
        # 🔴 결정규칙이 OR 이라 «한쪽 다리»만으로도 판정이 선다. 두 다리가 갈리면 그 사실을 인쇄한다.
        #    규칙 자체는 «바꾸지 않는다** — 결과를 보고 바꾸면 사후 조정이다.
        if pct_m <= 0.10 < pct:
            say(f"\n⚠️ **판정의 두 다리가 갈렸다.** 무제한 {pct*100:.1f}% 는 문턱(10%) 위지만 "
                f"`b₁ ≥ 3%` 한정은 **{pct_m*100:.1f}%** 로 아래다. 결정규칙이 `OR` 이라 "
                "**무제한 쪽 하나로 판정이 섰다.**")
            say("🔑 ***이건 규칙의 약점이지 데이터의 진술이 아니다*** — 그러나 "
                "**결과를 보고 규칙을 바꾸면 사후 조정**이므로 판정은 그대로 둔다. "
                "다음 사전등록에서 두 다리를 어떻게 결합할지 «미리» 정할 것.")
    else:
        say("🟡 **판정: 귀무보다 낫다.** 단 n 이 작아 증거로 승격하지 않는다 — "
            "`PREREG_Q1_V2.md` §3 처럼 다음 글로 out-of-sample 검정할 것.")

    cur.close()
    conn.close()
    (BASE / "RESULTS_COMMON_BAND.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_COMMON_BAND.md")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
