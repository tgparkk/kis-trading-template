# -*- coding: utf-8 -*-
"""C-18 · 유니버스 `prev_close` 결손 공개 — `n_up` 을 쓰는 «모든» 산출물의 의무 인쇄 블록.

🔴 **결함**(`PREREG_POST6.md` §5-2 · `RESULTS_REGDAY_POST5.md` §5-0): `n_up` 은
   `고가 ≥ 전일종가 × 1.15` 라서 **직전 거래일 봉이 있어야** 판정된다. 선행봉이 없는 종목은
   「급등 아님」이 아니라 ***검정에서 조용히 빠진다.*** post5 실측은 **0.00% · 0.04% ↔ 6.91%** 로
   날마다 두 자릿수 배 갈렸다 — 그러면 `n_up` 은 **분모가 서로 다른 수열**이다.

**규약**(§5-2 그대로):

| 열 | 뜻 |
|---|---|
| `universe_mcap` | 그날 `market_cap > 0` 인 종목 수 |
| `universe_test` | 그중 **직전 거래일 봉이 있는** 종목 수(= `n_up` 판정 가능 분모) |
| `dropped` | 차 |
| `drop_rate` | 탈락률 |
| `prev_bar_date` | 실제로 쓴 직전 거래일 |

- **가드**: `drop_rate ≥ 1%` 인 날은 🔴 표시하고 *「그날의 `n_up` 을 다른 날과 직접 비교하지 말 것」*을
  **인쇄한다.** 🔴 **1% 는 `PREREG_POST6.md` 가 «처음» 선언하는 숫자다**(§7-1 목록) —
  근거는 post5 실측이 0.00%·0.04% ↔ 6.91% 로 두 자릿수 배 이상 갈린다는 것뿐이다
  (그 사이 어디를 잡아도 같은 분류가 된다). **관측값을 보고 정한 문턱이 아니다.**
- **편향 방향도 인쇄**: `RESULTS_REGDAY_POST5.md` §5-0 의 논증 그대로 —
  *「빼면 더 커질 뿐 작아지지 않는다」* ⇒ `n_up` **결론은 강건**하고 **순위 진술은 과대**일 수 있다.

🟡 `prev_bar_date` 는 유니버스 «전체»의 직전 거래일이다. 개별 종목의 `LAG` 는 그보다 «더 옛날»
   봉을 집을 수 있다(중간 결손). 그 건수도 `stale_prev` 로 함께 낸다 — **같은 결함의 다른 얼굴**이고
   탈락에 안 잡히기 때문이다(그 종목은 빠지지 않고 «틀린 전일종가»로 판정된다).

라이브 트리 import 0건. DB 는 SELECT 만.
"""
from __future__ import annotations

from collections import Counter
from datetime import date as _date
from datetime import timedelta

PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")

# 🔴 §5-2 가 «처음» 선언하는 문턱. 관측값을 보고 고르지 않았다.
DROP_RATE_GUARD = 0.01

# `LAG` 를 계산할 때 되돌아보는 달력일 수. `run_regday_post5.load_universe_day` 와 같은 값이라야
# «같은 것을 재는» 것이 된다 — 이 숫자를 바꾸면 `universe_test` 의 뜻이 바뀐다.
LOOKBACK_DAYS = 20

_SQL = (
    "WITH u AS (SELECT stock_code, date, close, market_cap, "
    "  LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close, "
    "  LAG(date)  OVER (PARTITION BY stock_code ORDER BY date) AS prev_date "
    "  FROM daily_prices WHERE date BETWEEN %s AND %s AND close > 0) "
    "SELECT stock_code, prev_close, prev_date FROM u "
    "WHERE date = %s AND market_cap IS NOT NULL AND market_cap > 0 "
    "AND NOT (stock_code = ANY(%s))"
)


def coverage(cur, d: str, pseudo=PSEUDO) -> dict:
    """등록일 `d` 하루의 유니버스 결손. 🔑 `daily_prices.date` 는 **text** 컬럼이라
    날짜 산술은 파이썬에서 문자열로 만들어 넘긴다(SQL 에서 하면 `text >= timestamp` 로 죽는다)."""
    y, m, dd = (int(x) for x in d.split("-"))
    lo = (_date(y, m, dd) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    cur.execute(_SQL, (lo, d, d, list(pseudo)))
    rows = cur.fetchall()
    kept = [r for r in rows if r[1] is not None and float(r[1]) > 0]
    n_all, n_kept = len(rows), len(kept)
    prev_dates = Counter(str(r[2]) for r in kept if r[2] is not None)
    prev_bar = prev_dates.most_common(1)[0][0] if prev_dates else None
    return {
        "date": d,
        "universe_mcap": n_all,
        "universe_test": n_kept,
        "dropped": n_all - n_kept,
        "drop_rate": (n_all - n_kept) / n_all if n_all else float("nan"),
        "prev_bar_date": prev_bar,
        "stale_prev": sum(c for k, c in prev_dates.items() if k != prev_bar),
    }


def flagged(rows) -> list:
    """가드에 걸린 날 — `drop_rate ≥ 1%`."""
    return [r for r in rows if r["drop_rate"] >= DROP_RATE_GUARD]


def render(rows, title="유니버스 `prev_close` 결손 (C-18 · 의무 인쇄)") -> list:
    """§5-2 의 5열 표 + 가드 + 편향 방향. `say()` 로 흘려보낼 문자열 목록을 준다."""
    out = [f"### {title}", ""]
    out.append("`n_up` 은 `고가 ≥ 전일종가 × 1.15` 이므로 **직전 거래일 봉이 있어야** 판정된다. "
               "선행봉이 없는 종목은 「급등 아님」이 아니라 **검정에서 빠진다**.")
    out.append("")
    out.append("| 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | "
               "`prev_bar_date` | 🟡`stale_prev` |")
    out.append("|---|---|---|---|---|---|---|")
    for r in rows:
        hot = r["drop_rate"] >= DROP_RATE_GUARD
        out.append(
            "| {d} | {a:,} | {b:,} | {c} | {e} | {p} | {s} |".format(
                d=r["date"], a=r["universe_mcap"], b=r["universe_test"],
                c=("🔴 **{:,}**".format(r["dropped"]) if r["dropped"] else "0"),
                e=("🔴 **{:.2f}%**" if hot else "{:.2f}%").format(100 * r["drop_rate"]),
                p=r["prev_bar_date"] or "—",
                s=("🟡 **{:,}**".format(r["stale_prev"]) if r["stale_prev"] else "0")))
    out.append("")
    bad = flagged(rows)
    if bad:
        out.append("🔴 **가드 발동 — `drop_rate ≥ {:.0f}%` 인 날: {}**".format(
            100 * DROP_RATE_GUARD, " · ".join(r["date"] for r in bad)))
        out.append("⇒ ***그날의 `n_up` 을 다른 날과 «직접 비교하지 말 것».*** 분모가 다르다.")
    else:
        out.append("🟢 가드 미발동 — 전 등록일이 `drop_rate < {:.0f}%`.".format(100 * DROP_RATE_GUARD))
    out.append("🔴 **1% 는 `PREREG_POST6.md` §5-2 가 «처음» 선언하는 숫자다**(§7-1 목록) — "
               "post5 실측이 **0.00% · 0.04% ↔ 6.91%** 로 두 자릿수 배 갈리므로 그 사이 어디를 잡아도 "
               "같은 분류가 된다. **관측값을 보고 정하지 않았다.**")
    out.append("")
    out.append("**편향 방향**(`RESULTS_REGDAY_POST5.md` §5-0 논증 그대로): 탈락 종목이 검정에 들어오면 "
               "`n_up` 은 *「빼면 더 커질 뿐 작아지지 않는다」* ⇒ **`n_up` 결론(크다)은 강건**하고, "
               "**`n_up` 안 «순위» 진술은 과대**일 수 있다(분모가 작을수록 순위가 좋아 보인다).")
    out.append("🟡 `stale_prev` = 직전 거래일이 아니라 **더 옛날 봉**을 전일종가로 쓴 종목 수 — "
               "탈락에 «안 잡히는» 같은 결함이다.")
    return out
