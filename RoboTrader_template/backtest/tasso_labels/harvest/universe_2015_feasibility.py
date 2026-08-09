# -*- coding: utf-8 -*-
"""2015~2016 백필 타당성 실측 — 시점 유니버스 복원 + 상폐 종목 일봉 취득률.

## 왜 이 스크립트가 생겼나

같은 날(2026-08-09) 오전에 `CLOSING.md` §2.3 에 *「백필해도 생존편향 벽이 먼저 있다」*고
적었다. **재지 않고 발굴 프로그램의 결론을 옮겨 적은 것**이었다. 재 보니 반대였다.
⇒ 그 문장은 취소선으로 남기고 이 스크립트를 근거로 정정했다.

## 재는 것 (섞지 않는다)

① **시점 유니버스** — 2015-01-02 에 상장돼 있던 종목이 몇 개인가.
   `KRX-DESC`(현재 상장 + ListingDate) ∪ `KRX-DELISTING`(상장·상폐일)로 만든다.
   **생존편향 크기 = 그때 있었고 지금 없는 것의 비율.**
② **가격 취득 가능성** — 그 「지금은 없는」 종목의 2015 일봉을 실제로 받을 수 있는가.
   무작위 표본으로 **취득률**을 재고, 빈 결과는 상장·상폐일과 대조해 **왜 비었는지** 가른다.
③ **원장 대조** — 초기 매매일지 원장의 종목명이 현재 상장 / 상폐 / 미매칭 중 무엇인가.

## 🔴 이 스크립트가 지키는 것

- ***빈 결과는 대칭으로 확인하기 전까지 데이터가 아니다.*** `pykrx.get_market_ticker_list` 는
  **오늘 날짜에서도 0** 을 내며 예외를 안 던진다(= 죽었다). 「2015 엔 종목이 없다」로 읽으면
  전제가 통째로 뒤집힌다. 그래서 `probe_ticker_list_liveness()` 를 **먼저** 돌리고,
  살아 있는 것으로 나오면 오히려 **경고**한다(그러면 이 스크립트의 우회로가 불필요해진 것).
- ***미매칭을 「상폐」로 접지 않는다.*** 사명 변경·원문 오타가 미매칭으로 떨어진다.
  상폐율은 **하한/상한 구간**으로 낸다.
- ***8자리 종목코드를 섞지 않는다.*** 신주인수권증서·투자신탁이라 주식 백테스트 대상이 아니고,
  이것을 섞으면 취득률이 100% → 88% 로 보인다.
"""
from __future__ import annotations

import csv
import io
import random
import re
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd  # noqa: E402
import FinanceDataReader as fdr  # noqa: E402
from pykrx import stock  # noqa: E402

import cat2829_common as C  # noqa: E402

CUT = pd.Timestamp("2015-01-02")
PROBE_FROM, PROBE_TO = "20150102", "20150228"
SAMPLE_N = 60
SEED = 20260809                      # 고정 — 표본이 실행마다 바뀌면 「실측」이 아니다
LEDGER = C.HARVEST / "journal_items_early.csv"
OUT_LOG = C.HARVEST / "universe_2015_feasibility.log"

_lines = []


def say(s=""):
    print(s)
    _lines.append(s)


def norm(s):
    return re.sub(r"[\s()\[\]·.,/-]", "", str(s)).upper()


def probe_ticker_list_liveness():
    """🔴 pykrx 종목목록 엔드포인트가 살아 있는가 — **오늘 날짜로** 먼저 묻는다."""
    say("=== 0) pykrx get_market_ticker_list 생존 확인 (대칭) ===")
    alive = False
    for d in ("20260807", "20200102", "20150102"):
        counts = []
        for m in ("KOSPI", "KOSDAQ"):
            try:
                counts.append(len(stock.get_market_ticker_list(d, market=m)))
            except Exception as e:
                counts.append(type(e).__name__)
        say(f"  {d}: KOSPI={counts[0]} KOSDAQ={counts[1]}")
        alive |= any(isinstance(c, int) and c > 0 for c in counts)
    if alive:
        say("  ⚠️ 살아 있다 — 엔드포인트가 복구됐다. 아래 FDR 우회로가 불필요한지 재검토할 것.")
    else:
        say("  🔴 모든 날짜에서 0 · 예외 없음 = **엔드포인트 사망**(빈 결과라 조용히 통과한다).")
        say("     ⇒ 시점 유니버스는 FDR 두 목록으로 만든다.")
    return alive


def main() -> int:
    probe_ticker_list_liveness()

    desc = fdr.StockListing("KRX-DESC")
    dead = fdr.StockListing("KRX-DELISTING")
    desc["ld"] = pd.to_datetime(desc["ListingDate"], errors="coerce")
    dead["ld"] = pd.to_datetime(dead["ListingDate"], errors="coerce")
    dead["dd"] = pd.to_datetime(dead["DelistingDate"], errors="coerce")

    cur_then = desc[desc["ld"] <= CUT]
    dead_then = dead[(dead["ld"] <= CUT) & (dead["dd"] > CUT)]
    total = len(cur_then) + len(dead_then)

    say("\n=== ① 2015-01-02 시점 유니버스 복원 ===")
    say(f"  현재도 상장 + 2015 이전 상장 : {len(cur_then):>5}")
    say(f"  🔴 그때 있었고 지금은 없음    : {len(dead_then):>5}")
    say(f"  복원 유니버스                : {total:>5}")
    say(f"  ⇒ **생존편향 크기 = {len(dead_then)/total:.1%}**  "
        f"(현재 상장 목록만 쓰면 이만큼이 통째로 빠진다)")
    say(f"  참고: 현재 상장 전체 {len(desc)} · ListingDate 결측 {int(desc['ld'].isna().sum())}")
    say("  상폐 사유 상위:")
    for why, c in dead_then["Reason"].fillna("(없음)").str[:26].value_counts().head(6).items():
        say(f"    {c:>4}  {why}")

    sym = dead_then["Symbol"].astype(str)
    ord_codes = sorted(sym[sym.str.len() == 6].tolist())
    say(f"\n  상폐 {len(sym)} 중 6자리(보통주 등) {len(ord_codes)} · "
        f"8자리(신주인수권·투자신탁) {len(sym) - len(ord_codes)}")

    # ── ② 취득률 ─────────────────────────────────────────────────────────────
    rng = random.Random(SEED)
    pool = sorted(sym.tolist())
    sample = rng.sample(pool, min(SAMPLE_N, len(pool)))
    say(f"\n=== ② 상폐 종목 {PROBE_FROM}~{PROBE_TO} 일봉 취득 "
        f"(무작위 {len(sample)} · seed {SEED}) ===")
    ok, empty, err = [], [], []
    for code in sample:
        try:
            df = stock.get_market_ohlcv_by_date(PROBE_FROM, PROBE_TO, code)
            (ok if len(df) else empty).append(code)
        except Exception as e:
            err.append((code, type(e).__name__))
    ok6 = [c for c in ok if len(c) == 6]
    s6 = [c for c in sample if len(c) == 6]
    say(f"  전체    : 취득 {len(ok)}/{len(sample)} · 빈결과 {len(empty)} · 예외 {len(err)}")
    say(f"  6자리만 : 취득 {len(ok6)}/{len(s6)} = "
        f"{(len(ok6)/len(s6) if s6 else 0):.1%}   ← **이 값이 백필 타당성**")
    say(f"  8자리   : 표본 {len(sample)-len(s6)} · 취득 {len(ok)-len(ok6)} "
        f"(신주인수권·투자신탁이라 일봉이 없다 = 정상)")
    if empty:
        sub = dead_then[dead_then["Symbol"].astype(str).isin(empty)]
        say("  빈 결과의 상장·상폐일 (그 시점에 정말 있었나):")
        for _, r in sub.head(8).iterrows():
            say(f"    {r['Symbol']} {str(r['Name'])[:16]:<16} "
                f"상장 {str(r['ListingDate'])[:10]} 상폐 {str(r['DelistingDate'])[:10]}")

    # ── ③ 원장 대조 ──────────────────────────────────────────────────────────
    rows = [r for r in csv.DictReader(LEDGER.open(encoding="utf-8"))
            if r["post_date"][:4] in ("2015", "2016")]
    names = Counter(r["stock_name"] for r in rows)
    cur_map, dead_map = defaultdict(list), defaultdict(list)
    for _, r in desc.iterrows():
        cur_map[norm(r["Name"])].append(str(r["Code"]))
    for _, r in dead.iterrows():
        dead_map[norm(r["Name"])].append(str(r["Symbol"]))
    n_alive = sum(1 for nm in names if norm(nm) in cur_map)
    n_dead = sum(1 for nm in names if norm(nm) not in cur_map and norm(nm) in dead_map)
    n_unk = len(names) - n_alive - n_dead
    say(f"\n=== ③ 초기 매매일지 원장 대조 (2015~16 {len(rows)}항목 · 고유 종목명 {len(names)}) ===")
    say(f"  현재 상장 {n_alive} ({n_alive/len(names):.1%}) · "
        f"상폐 확인 {n_dead} ({n_dead/len(names):.1%}) · 미매칭 {n_unk} ({n_unk/len(names):.1%})")
    say("  🔴 미매칭을 「상폐」로 접지 말 것 — 대부분 사명 변경·원문 오타다.")
    say(f"     ⇒ 상폐율은 단일값이 아니라 **하한 {n_dead/len(names):.1%} · "
        f"상한 {(n_dead+n_unk)/len(names):.1%}** 로 인용할 것.")

    OUT_LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
