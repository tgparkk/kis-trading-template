"""C(3) 수용 판정 — 「이 분류로 대장주를 가릴 수 있는가」.

읽기 전용. DB 쓰기 없음.

DART induty_code 는 표준산업분류(KSIC)다. 우리가 원하는 건 「같은 업종·테마 안의 1등」
이므로 **입도(granularity)** 가 맞는지가 수용 여부를 가른다:
  - 한 그룹에 수백 종목이면 "대장주"가 사실상 무의미
  - 대부분이 1~2종목이면 비교 대상이 없어 역시 무의미
통과시키는 게 목적이 아니다. 못 쓰면 못 쓴다고 보고한다.

교차검증: DART corp_cls(Y/K/N/E) vs 우리 stock_market.market(KOSPI/KOSDAQ).
매핑이 제대로 됐는지의 독립 신호다.

usage:
  PYTHONUTF8=1 python scripts/dart_industry_c3_report.py
"""
import os
import statistics as stx
import sys
from collections import Counter, defaultdict

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import OUT_DIR  # noqa: E402

REPORT_TXT = os.path.join(OUT_DIR, "c3_acceptance_report.txt")

CLS_LABEL = {"Y": "유가(KOSPI)", "K": "코스닥", "N": "코넥스", "E": "기타"}
CLS_TO_MARKET = {"Y": "KOSPI", "K": "KOSDAQ"}


def db():
    c = psycopg2.connect(host="127.0.0.1", port=5433, database="kis_template",
                         user="robotrader", password="1234")
    c.set_session(readonly=True, autocommit=True)
    return c


def pct(n, d):
    return f"{100.0*n/d:.1f}%" if d else "n/a"


def dist(sizes):
    s = sorted(sizes)
    if not s:
        return {}
    p90 = s[min(len(s) - 1, int(round(0.90 * (len(s) - 1))))]
    return {"groups": len(s), "median": stx.median(s), "mean": sum(s) / len(s),
            "min": s[0], "max": s[-1], "p90": p90}


def fmt_dist(d):
    return (f"그룹 {d['groups']}개 | 중앙값 {d['median']:.1f} | 평균 {d['mean']:.2f} "
            f"| 최소 {d['min']} | p90 {d['p90']} | 최대 {d['max']}")


def main():
    out = []

    def w(s=""):
        out.append(s)
        print(s)

    c = db()
    cur = c.cursor()
    cur.execute("""SELECT stock_code, induty_code, corp_cls, corp_name, stock_name
                   FROM stock_industry""")
    rows = cur.fetchall()
    cur.execute("SELECT stock_code, market FROM stock_market")
    market = dict(cur.fetchall())
    # 최근 실제 거래된 종목(살아있는 유니버스) — 죽은 종목이 분포를 흐리지 않게 대조군으로 쓴다
    # daily_prices.date 는 text('YYYY-MM-DD'). ISO 문자열이라 사전순 비교가 곧 날짜순이고
    # 인덱스도 탄다 — 컬럼을 캐스팅하면 풀스캔이 되므로 경계값만 계산해 text 로 비교한다.
    cur.execute("""SELECT DISTINCT stock_code FROM daily_prices
                   WHERE date >= (SELECT to_char(to_date(max(date),'YYYY-MM-DD')
                                                 - INTERVAL '30 days', 'YYYY-MM-DD')
                                  FROM daily_prices)""")
    active = {r[0] for r in cur.fetchall()}
    c.close()

    total = len(rows)
    w("=" * 78)
    w("stock_industry 수용 판정 리포트 — 「이 분류로 대장주를 가릴 수 있는가」")
    w("=" * 78)
    w()
    w(f"[0] 적재 {total}종목")

    # ---------------- 커버리지 ----------------
    has = [r for r in rows if r[1]]
    w(f"[1] induty_code 커버리지: {len(has)}/{total} ({pct(len(has), total)}) "
      f"— 결측 {total-len(has)}")

    lens = Counter(len(r[1]) for r in has)
    w(f"    ⚠️ 코드 자릿수 분포(=KSIC 계층 깊이가 종목마다 다름): "
      f"{dict(sorted(lens.items()))}")
    w(f"       KSIC: 2자리=중분류 3자리=소분류 4자리=세분류 5자리=세세분류")
    w(f"    ⚠️ 업종'명'은 응답에 없다 — induty_code 코드값만 온다(이름 필드 자체가 부재).")

    # ---------------- 그룹 크기 분포 ----------------
    def group_by(keyfn, subset=None):
        g = defaultdict(list)
        for r in (subset if subset is not None else has):
            k = keyfn(r[1])
            if k:
                g[k].append(r)
        return g

    w()
    w("[2] 업종 그룹 크기 분포")
    w("-" * 78)

    raw = group_by(lambda x: x)
    d = dist([len(v) for v in raw.values()])
    w(f"  (a) 원본 코드 그대로:        {fmt_dist(d)}")
    for depth in (2, 3):
        g = group_by(lambda x, dp=depth: x[:dp] if len(x) >= dp else None)
        dd = dist([len(v) for v in g.values()])
        name = {2: "중분류", 3: "소분류"}[depth]
        w(f"  (b) 앞 {depth}자리({name})로 정규화: {fmt_dist(dd)}")

    sizes = [len(v) for v in raw.values()]
    singles = sum(1 for s in sizes if s == 1)
    le2 = sum(1 for s in sizes if s <= 2)
    st_in_le2 = sum(s for s in sizes if s <= 2)
    st_in_ge50 = sum(s for s in sizes if s >= 50)
    ge50 = sum(1 for s in sizes if s >= 50)
    usable = sum(1 for s in sizes if 3 <= s <= 30)
    st_usable = sum(s for s in sizes if 3 <= s <= 30)
    w()
    w(f"  종목 1개짜리 그룹: {singles}개 / {len(sizes)}그룹 ({pct(singles, len(sizes))})")
    w(f"  종목 ≤2 그룹:      {le2}개 → 해당 종목 {st_in_le2}개 ({pct(st_in_le2, len(has))}) "
      f"= 비교 대상이 없어 '1등' 판정 불가")
    w(f"  종목 ≥50 그룹:     {ge50}개 → 해당 종목 {st_in_ge50}개 ({pct(st_in_ge50, len(has))}) "
      f"= '1등'이 수십분의 1이라 의미 희박")
    w(f"  3~30 종목 그룹:    {usable}개 → 해당 종목 {st_usable}개 ({pct(st_usable, len(has))}) "
      f"= 대장주 판정이 그나마 성립하는 구간")

    # ---------------- 계층 깊이 혼재로 인한 분단 ----------------
    # KSIC 는 계층코드다. 어떤 종목은 '282'(3자리), 어떤 종목은 '28202'(5자리)로 온다.
    # 같은 산업인데 깊이가 달라 raw 코드로는 **다른 그룹**이 된다 — 대장주 비교가 끊긴다.
    # 이 절은 그 분단이 실제로 몇 종목에서 일어나는지 센다(추정 아님, 접두 관계 실측).
    codeset = set(raw)
    split_codes = []
    affected = set()            # 🔑 종목 단위 집합 — 접두 사슬(582→5822→58221)이 겹쳐
                                #    쌍마다 더하면 같은 종목을 여러 번 세어 100%를 넘는다
    for code in codeset:
        deeper = [o for o in codeset if o != code and o.startswith(code)]
        if deeper:
            n_here = len(raw[code])
            n_deep = sum(len(raw[o]) for o in deeper)
            split_codes.append((code, n_here, len(deeper), n_deep))
            affected.update(m[0] for m in raw[code])
            for o in deeper:
                affected.update(m[0] for m in raw[o])
    w()
    w("[2c] 계층 깊이 혼재로 인한 그룹 분단 (같은 산업이 코드 깊이 차이로 갈라진 건수)")
    w("-" * 78)
    w(f"  상위코드가 하위코드의 접두인 경우: {len(split_codes)}개 상위코드, "
      f"영향 받는 **고유 종목** {len(affected)}개 ({pct(len(affected), len(has))})")
    for code, nh, nd_c, nd_s in sorted(split_codes, key=lambda x: -(x[1] + x[3]))[:8]:
        w(f"    {code:>6s}({nh}종목) ↔ 하위코드 {nd_c}개({nd_s}종목) "
          f"= 실제론 같은 산업인데 {nh + nd_s}종목이 분단")

    # ---------------- 상위 그룹 ----------------
    w()
    w("[3] 가장 큰 그룹 상위 10개 (코드 / 종목수 / 구성 예시)")
    w("-" * 78)
    for code, members in sorted(raw.items(), key=lambda kv: -len(kv[1]))[:10]:
        names = [m[4] or m[3] for m in members[:6]]
        w(f"  {code:>6s}  {len(members):>4d}종목  예: {', '.join(names)}")

    # ---------------- 활성 종목 한정 ----------------
    act = [r for r in has if r[0] in active]
    ga = defaultdict(list)
    for r in act:
        ga[r[1]].append(r)
    da = dist([len(v) for v in ga.values()])
    sa = [len(v) for v in ga.values()]
    w()
    w(f"[4] 대조군 — 최근 30일 거래된 종목만 ({len(act)}종목)")
    w(f"    {fmt_dist(da)}")
    w(f"    1종목 그룹 {sum(1 for s in sa if s==1)}개, "
      f"≤2 그룹 종목수 {sum(s for s in sa if s<=2)} ({pct(sum(s for s in sa if s<=2), len(act))})")

    # ---------------- corp_cls 교차검증 ----------------
    w()
    w("[5] 교차검증 — DART corp_cls vs stock_market.market")
    w("-" * 78)
    cls_counts = Counter(r[2] for r in rows)
    w(f"    corp_cls 분포: " +
      ", ".join(f"{k}={v}({CLS_LABEL.get(k, '?')})" for k, v in sorted(cls_counts.items(),
                                                                      key=lambda x: str(x[0]))))
    cmp_n = agree = 0
    mismatches = []
    no_market = 0
    for sc, _, cls, cname, sname in rows:
        mk = market.get(sc)
        if mk is None:
            no_market += 1
            continue
        exp = CLS_TO_MARKET.get(cls)
        if exp is None:      # N(코넥스)·E(기타)는 KOSPI/KOSDAQ 어느 쪽도 아님 → 별도 집계
            mismatches.append((sc, sname or cname, cls, mk, "cls=N/E"))
            continue
        cmp_n += 1
        if exp == mk:
            agree += 1
        else:
            mismatches.append((sc, sname or cname, cls, mk, "불일치"))
    w(f"    stock_market 에 없는 종목: {no_market}")
    w(f"    Y/K 비교가능 {cmp_n}건 중 일치 {agree} ({pct(agree, cmp_n)}), "
      f"불일치 {cmp_n-agree}")
    ne = [m for m in mismatches if m[4] == "cls=N/E"]
    real = [m for m in mismatches if m[4] == "불일치"]
    w(f"    corp_cls=N/E 인데 우리 DB 는 KOSPI/KOSDAQ: {len(ne)}건")
    for m in ne[:10]:
        w(f"      - {m[0]} {m[1]} cls={m[2]} ours={m[3]}")
    w(f"    실제 Y/K 불일치: {len(real)}건")
    for m in real[:20]:
        w(f"      - {m[0]} {m[1]} cls={m[2]}({CLS_LABEL.get(m[2])}) ours={m[3]}")

    # ---------------- 테마 대장주 실증 프로브 ----------------
    # KSIC 는 「무엇을 생산하는가」로 나눈 산업분류다. 우리가 원하는 「테마 대장주」는
    # 서사(2차전지·AI·원전)로 묶인다. 둘이 같은 축인지 **실제 데이터로** 확인한다.
    # 종목코드 옆에 수집된 실제 사명을 함께 찍어 코드→종목 매핑을 독자가 검증할 수 있게 한다.
    probes = {
        "2차전지": ["247540", "086520", "003670", "373220", "006400", "066970"],
        "반도체": ["005930", "000660", "042700", "058470", "039030"],
        "원전·방산": ["034020", "012450", "064350", "079550", "047810"],
    }
    byc = {r[0]: r for r in rows}
    w()
    w("[6] 테마 대장주 실증 프로브 — 같은 테마가 같은 induty_code 로 묶이는가")
    w("-" * 78)
    for theme, codes in probes.items():
        w(f"  [{theme}]")
        seen_codes = []
        for sc in codes:
            r = byc.get(sc)
            if not r:
                w(f"    {sc}  (미수집)")
                continue
            w(f"    {sc}  {(r[4] or r[3]):<16s} induty_code={r[1] or '(없음)'}  "
              f"같은코드 총 {len(raw.get(r[1], [])):>3d}종목")
            if r[1]:
                seen_codes.append(r[1])
        u = len(set(seen_codes))
        if len(seen_codes) < 2:
            verdict = "  (수집 종목 부족 — 판정 보류)"
        elif u == 1:
            verdict = "  ✅ 한 그룹"
        else:
            verdict = "  🔴 테마가 한 그룹으로 안 묶임"
        w(f"    → {len(seen_codes)}종목이 서로 다른 코드 {u}개로 흩어짐{verdict}")

    # ---------------- 종합 판정 ----------------
    holdco = len(raw.get("64992", [])) + len(raw.get("649", []))
    theme_ok = 0
    for theme, codes in probes.items():
        cs = [byc[sc][1] for sc in codes if byc.get(sc) and byc[sc][1]]
        if len(cs) >= 2 and len(set(cs)) == 1:
            theme_ok += 1
    w()
    w("=" * 78)
    w("[7] 판정")
    w("=" * 78)
    w(f"  근거1 커버리지    : {pct(len(has), total)} — 수집 자체는 성공(결측 0)")
    w(f"  근거2 코드깊이 혼재: 3/4/5자리 혼재, 접두 분단 영향 고유종목 "
      f"{len(affected)} ({pct(len(affected), len(has))})")
    w(f"  근거3 양끝 무의미  : ≤2종목 그룹에 {pct(st_in_le2, len(has))}, "
      f"≥50종목 그룹에 {pct(st_in_ge50, len(has))}")
    w(f"  근거4 지주회사 붕괴: 64992+649 = {holdco}종목이 실제 사업과 무관하게 한 덩어리")
    w(f"  근거5 테마 정합    : 프로브 {len(probes)}개 중 한 그룹으로 묶인 테마 {theme_ok}개")
    w()
    w("  ⇒ 「같은 업종 내 1등」을 KSIC induty_code 원본 코드로 가리는 것은 **부적합**.")
    w("     이유는 그룹 크기가 아니라 **축이 다르기 때문**이다 — KSIC 는 「무엇을")
    w("     생산하는가」로 나누고, 대장주는 「어떤 서사로 같이 움직이는가」로 묶인다.")
    w("     결정적 반례: 에코프로(2차전지 대장주 계열)가 induty_code 상 **지주회사**로")
    w("     분류돼 2차전지 종목들과 애초에 같은 그룹에 있지도 않다. 그룹 크기를 아무리")
    w("     조정해도(접두 정규화 등) 이 오분류는 사라지지 않는다.")
    w()
    w("  ⇒ 쓸 수 있는 좁은 용도: 「동일 산업 내 상대강도(RS) 정규화」처럼 산업 축이")
    w("     그대로 의미를 갖는 경우. 이때도 접두 깊이 정규화가 선행돼야 한다.")
    w("  ⇒ 업종'명'이 없으므로 사람이 읽는 리포트에 쓰려면 KSIC 분류표(통계청)를")
    w("     외부에서 확보해 코드→명 매핑을 별도로 만들어야 한다. 지어내지 말 것.")

    txt = "\n".join(out)
    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(f"\n→ {REPORT_TXT}")


if __name__ == "__main__":
    main()
