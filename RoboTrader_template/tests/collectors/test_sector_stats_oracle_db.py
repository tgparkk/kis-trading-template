"""T9 오라클 — 태쏘 SEC-M1 배선(run_sector.load_day + labels_for(N=3))과 대조.

🔴 연구 트리를 «테스트에서만» sys.path 로 끌어온다(운영 코드는 backtest import 0건).
   run_sector 는 패키지가 아니고 형제 모듈 5개와 run_tests.DSN 하드코딩을 끌어온다 —
   그 DSN 은 kis_template@5433 SELECT 전용이라 죽은 DB 가 아니다.
🔴 @pytest.mark.db — 기준선 실패 집합 비교에서 «제외»한다(워크트리 환경 차이).
🔴 허용 차집합 —
   ① market_cap NULL/≤0 (태쏘만 제외 · 이 날짜엔 0건 예상 · 건수를 인쇄한다)
   ② ksic_source IS DISTINCT FROM 'snapshot_20260807' (부모복사·DART 채움 — 우리만 라벨 있음)
   ③ 명부 행이 «아예 없음» — 별도로 재고(그날 «대상 행» 기준 — only_ours 로 재면 라벨이
      명부에서만 오므로 항상 ∅ 인 vacuous 단언이 된다) 인쇄하고 **실패시킨다**(②에 흡수 금지).
   그 밖의 차이가 1건이라도 있으면 실패한다.
🔴 섹터 집계는 «성적표 코드»(compute_day_stats)로 만든다 — 테스트 안에서 median 을
   다시 짜면 집계 버그가 통과한다.
⚠️ 2024-03-12 «이전»은 이 테스트가 재지 않는다 — 시총이 사실상 2024-03-13 부터라
   태쏘 유니버스가 거의 비기 때문이다(§3.2).

🔑 백분위 정의 — 태쏘 `rank_pct` 는 «종목별 자기제외(LOO)» 통계를 랭크하고, 성적표는
   섹터 «전원» 통계를 랭크한다(스펙 §3.6 · §3.5). 그래서 이 오라클은 태쏘의 LOO 백분위
   출력과는 대조하지 «않는다» — 종목별 r·라벨·멤버십·n_members·ret_median 만 잰다.
   비-LOO 순위·백분위는 아래 §3.5 재현 테스트가 동결값으로 고정한다.
"""
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # RoboTrader_template
sys.path.insert(0, REPO)
TASSO = os.path.join(REPO, "backtest", "tasso_program_journal")

ORACLE_DATE = date(2026, 8, 5)
# 태쏘 load_day 의 final_pseudo — 실측상 숫자로 시작하지 않는 코드는 이 넷뿐이라
# 우리 SQL_STOCK_ONLY 술어와 «집합으로» 같다.
PSEUDO = ["KOSPI", "KOSDAQ", "KS11", "KQ11"]

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import sector_collector as sc  # noqa: E402
from collectors import sector_writer as w  # noqa: E402

# 🔴 마커만 모듈 수준. importorskip·DB 프로브를 여기 두면 «수집 단계»에 돌아
#    `-m "not db"` 로도 못 막고, ImportError 가 아닌 예외(psycopg2.OperationalError 등)는
#    skip 이 아니라 ERROR 로 기준선 실패 집합에 들어간다.
pytestmark = [pytest.mark.db]


def _load_tasso():
    """run_sector 를 «테스트 실행 시점»에 끌어온다. 무엇이 터지든 skip 이다.

    🔴 sys.path 조작도 여기서 한다 — 모듈 최상위에 두면 이 파일이 «수집되기만» 해도
       연구 트리가 다른 테스트의 import 경로에 끼어든다(형제 모듈 이름 충돌 위험).
    """
    if not os.path.isdir(TASSO):
        pytest.skip("태쏘 트리가 없다 - 오라클 생략")
    if TASSO not in sys.path:
        sys.path.insert(0, TASSO)
    try:
        import run_sector as rs
        import run_selection as rsel
    except Exception as e:  # noqa: BLE001 — 형제 모듈 5개를 끌어온다
        pytest.skip("태쏘 run_sector import 실패: %s" % e)
    return rs, rsel


def _connect():
    try:
        cm = KisDbConnection.get_connection()
        c = cm.__enter__()
        with c.cursor() as cur:
            cur.execute("SELECT 1")
        return cm, c
    except Exception as e:  # noqa: BLE001
        pytest.skip("kis_template DB 접속 불가: %s" % e)


def test_oracle_matches_tasso_sec_m1():
    run_sector, run_selection = _load_tasso()
    # 경미 7 — PSEUDO 하드코딩이 태쏘 동결값과 갈리면 «인쇄»하고 태쏘 값을 쓴다
    tasso_pseudo = list(getattr(run_selection, "PSEUDO", []) or [])
    if tasso_pseudo and set(tasso_pseudo) != set(PSEUDO):
        print("[T9] ⚠️ PSEUDO 불일치 — 우리 %s vs 태쏘 %s (태쏘 값을 쓴다)"
              % (sorted(PSEUDO), sorted(tasso_pseudo)))
    pseudo = tasso_pseudo or PSEUDO
    cm, conn = _connect()
    try:
        mp = dict((r[0], (r[1], r[2])) for r in w.map_as_of(conn, ORACLE_DATE))
        if not mp:
            pytest.skip("stock_sector_map 이 비어 있다 - 부트스트랩 전")

        # ── 우리 계산 — 🔴 «성적표 코드 그 자체»(compute_day_stats)로 만든다.
        #    테스트 안에서 median 을 다시 짜면 집계 버그가 통과한다(M1).
        rows = sc.load_day_rows(conn, ORACLE_DATE)
        labels = dict((c, v[0]) for c, v in mp.items())
        stat_rows, undefined = sc.compute_day_stats(rows, labels)
        ob = dict((r["sector_key"], r) for r in stat_rows if r["taxonomy"] == "ksic3")

        ours_all = {}
        for code, high, close, prev in rows:
            if prev is None or float(prev) <= 0 or close is None:
                continue
            ours_all[code] = float(close) / float(prev) - 1.0
        our_lbl = dict((c, sc.sector_label(labels.get(c), 3)) for c in ours_all)
        ours = dict((c, v) for c, v in ours_all.items() if our_lbl.get(c))

        # ── 태쏘 계산 (동결 함수를 «그대로» 호출) ────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, induty_code FROM stock_industry "
                        "WHERE induty_code IS NOT NULL AND induty_code <> ''")
            sec = dict(cur.fetchall())
            rec = run_sector.load_day(cur, ORACLE_DATE.isoformat(), sec, pseudo)
        their_r = dict((c, float(v)) for c, v in zip(rec["joined"], list(rec["r"]))
                       if math.isfinite(float(v)))
        their_lbl = dict((c, (sec[c][:3] if len(sec.get(c) or "") >= 3 else None))
                         for c in their_r)
        theirs = dict((c, v) for c, v in their_r.items() if their_lbl.get(c))

        # ── 허용 차집합 ①② ──────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code FROM daily_prices WHERE date=%s "
                        "AND (market_cap IS NULL OR market_cap <= 0)",
                        (ORACLE_DATE.isoformat(),))
            no_mcap = set(r[0] for r in cur.fetchall())

        only_ours = set(ours) - set(theirs)
        only_theirs = set(theirs) - set(ours)
        class1 = only_ours & no_mcap
        class2 = set(c for c in only_ours if mp[c][1] != "snapshot_20260807")
        residual = only_ours - class1 - class2
        both = set(ours) & set(theirs)
        # 🔴 「명부 행이 아예 없음」은 «라벨 비교»가 아니라 «그날 대상 행» 기준으로 잰다 —
        #    only_ours 로 재면 라벨이 mp 에서만 오므로 «항상 ∅»인 vacuous 단언이 된다.
        #    이건 커버리지 결손의 직접 신호이고 undefined["no_label"] 과 같은 뿌리다.
        no_map_rows = set(ours_all) - set(mp)

        print("[T9] 교집합=%d · only_ours=%d (①market_cap %d · ②우리만 라벨 %d · 잔여 %d) "
              "· only_theirs=%d · ③명부행 없음(그날 대상 기준)=%d · 미정=%s"
              % (len(both), len(only_ours), len(class1), len(class2), len(residual),
                 len(only_theirs), len(no_map_rows), undefined))

        assert only_theirs == set(), "태쏘에만 있는 종목이 있다: %s" % sorted(only_theirs)[:10]
        assert no_map_rows == set(), \
            "그날 대상 행인데 명부에 열린 줄이 «아예 없는» 종목: %s" % sorted(no_map_rows)[:10]
        assert undefined["no_label"] == len(
            [c for c in ours_all if w.is_blank(labels.get(c))]), \
            "no_label 집계가 실제 «라벨 없음» 수와 다르다(무징후 절단 감지)"
        assert residual == set(), "허용 밖 차이: %s" % sorted(residual)[:10]

        # 교집합 종목의 r·ksic3 완전 일치
        for c in sorted(both):
            assert abs(ours[c] - theirs[c]) < 1e-12, \
                "%s r 불일치 %r vs %r" % (c, ours[c], theirs[c])
            assert our_lbl[c] == their_lbl[c], \
                "%s 라벨 불일치 %r vs %r" % (c, our_lbl[c], their_lbl[c])

        # ② 종목이 없는 업종의 ret_median·n_members 일치 · G 차이는 ②로만 생긴 업종
        members = defaultdict(set)
        tb = defaultdict(list)
        for c in ours:
            members[our_lbl[c]].add(c)
        for c, v in theirs.items():
            tb[their_lbl[c]].append(v)
        extra = class1 | class2
        for k in sorted(set(ob) & set(tb)):
            if members[k] & extra:
                continue
            assert ob[k]["n_members"] == len(tb[k]), \
                "%s n_members 불일치 %d vs %d" % (k, ob[k]["n_members"], len(tb[k]))
            assert abs(ob[k]["ret_median"] - statistics.median(tb[k])) < 1e-12, \
                "%s ret_median 불일치 %r vs %r" % (k, ob[k]["ret_median"],
                                                  statistics.median(tb[k]))
        only_our_sectors = set(ob) - set(tb)
        for k in sorted(only_our_sectors):
            assert members[k] <= extra, "우리만 있는 업종 %s 가 허용 차집합에서 오지 않았다" % k
        print("[T9] G ours=%d · theirs=%d · 우리만 있는 업종=%d(전부 ②)"
              % (len(ob), len(tb), len(only_our_sectors)))
    finally:
        cm.__exit__(None, None, None)


# §3.5 실사례 — critic 2차가 독립 재현해 일치를 확인한 5행(2026-08-05 · ksic3 · G=159).
# 🔴 라벨은 «명부»가 아니라 stock_industry 다 — 실사례를 그렇게 계산했기 때문이다.
EXPECTED_20260805 = {
    #        n    ret_median(%)  up  pos_ratio  rank  pct
    "261": (71,   5.670,         11, 0.930,     1,    99.4),
    "311": (13,   5.029,         0,  0.923,     5,    96.8),
    "264": (60,   4.053,         10, 0.867,     7,    95.6),
    "641": (5,    0.998,         0,  0.600,     84,   46.8),
    "212": (103,  0.494,         2,  0.689,     112,  29.1),
}


def test_stats_reproduce_spec_worked_example():
    """§3.5 실사례 5행을 «성적표 코드»로 재현한다 — 집계·순위·백분위를 한 번에 고정한다.

    🔑 오라클(위)은 «종목별 r·라벨»을 재고, 이 테스트는 «섹터 집계»를 잰다.
       둘을 갈라 놓지 않으면 집계 버그가 종목 대조를 통과해 지나간다.

    🔑 여기 순위·백분위는 «비-LOO»다 — 섹터 전원 통계를 G 개 업종 안에서 랭크한 값이며
       (스펙 §3.5 「좋거나 같은 업종이 1개(자기 제외)」), 태쏘의 종목별 LOO 백분위가 아니다.

    🔴 **이 테스트는 «동결 데이터 오라클»이다** — 라이브 `daily_prices` 의
       2026-08-05 ±20일 구간과 `stock_industry` 스냅샷에 값이 묶여 있다.
       그 데이터가 바뀌면 코드가 옳아도 깨진다. 알려진 예정 작업 둘이 정확히 그렇다:
         · 일봉 결손 49,252행 복구(원인 수정 c6dc77c · 복구 미착수)
         · `adj_factor` 보정 도구 `--apply`
       깨지면 **먼저 데이터 변경 여부를 확인하고**, 데이터가 바뀐 것이면 기대값을
       재계산해 갱신한다(코드를 고치지 말 것). 완료 리포트에도 같은 문장을 적는다.
    """
    cm, conn = _connect()
    try:
        rows = sc.load_day_rows(conn, ORACLE_DATE)
        if not rows:
            pytest.skip("2026-08-05 일봉이 없다")
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, induty_code FROM stock_industry "
                        "WHERE induty_code IS NOT NULL AND induty_code <> ''")
            labels = dict(cur.fetchall())
    finally:
        cm.__exit__(None, None, None)

    stat_rows, undefined = sc.compute_day_stats(rows, labels)
    got = dict((r["sector_key"], r) for r in stat_rows if r["taxonomy"] == "ksic3")
    print("[T9-b] 대상 행=%d · G(ksic3)=%d · 미정=%s" % (len(rows), len(got), undefined))
    assert len(got) == 159, "G(ksic3) 가 실사례(159)와 다르다: %d" % len(got)
    for key, (n, med_pct, up, pos, rank, pct) in sorted(EXPECTED_20260805.items()):
        r = got.get(key)
        assert r is not None, "%s 업종이 없다" % key
        assert r["n_members"] == n, "%s n_members %d != %d" % (key, r["n_members"], n)
        assert abs(r["ret_median"] * 100.0 - med_pct) <= 0.001, \
            "%s ret_median %.5f%% != %.3f%%" % (key, r["ret_median"] * 100.0, med_pct)
        assert r["up_count"] == up, "%s up_count %d != %d" % (key, r["up_count"], up)
        assert abs(r["pos_ratio"] - pos) <= 0.0005, \
            "%s pos_ratio %.4f != %.3f" % (key, r["pos_ratio"], pos)
        assert r["rank_median"] == rank, "%s rank %d != %d" % (key, r["rank_median"], rank)
        assert abs(r["pct_median"] - pct) <= 0.05, \
            "%s pct %.2f != %.1f" % (key, r["pct_median"], pct)
        assert r["g_sectors"] == 159
