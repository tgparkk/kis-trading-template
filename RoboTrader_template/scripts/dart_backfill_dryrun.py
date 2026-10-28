"""DART 공시 과거 복원 dry-run (2024-03-13 ~ 2026-09-23) — 연구 전용 · 파일만 · DB 쓰기 0.

무엇을 재나: 호출 수·커버리지만(수익률 조인 0).
  (a) 창 전체를 list.json 으로 받을 때 필요한 호출 수(유형 B·I · 전체유형)
  (b) 표본 15거래일(2024-03·2025-03·2026-03 각 5일) 실제 list.json — 응답 건수·매핑률·유형 분포
  (c) 현 DB(corp_events·news source='dart') 월별 커버리지와 표본일 회수율
  (d) 전체 백필 예상(호출 수 · 일일 한도 대비 일수 · 행수)

안전장치:
  - 외부 호출 하드캡 60회(재시도 포함) · 이미 받은 응답 파일이 있으면 재호출하지 않는다.
  - 키는 라이브 트리 .env 에서 «읽기»만(복사·출력 금지) · 예외 메시지에서 키를 가린다.
  - DB 는 read-only 세션에서 SELECT 만.
  - 라이브 모듈은 import 만(collectors.corp_events_collector 상수·키 파서).

usage:
  python scripts/dart_backfill_dryrun.py --sample     # 표본 호출(≤60) → scratchpad/dart_dryrun_20260924/raw/
  python scripts/dart_backfill_dryrun.py --analyze    # 파일+DB SELECT → summary.json
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402
import requests  # noqa: E402

from collectors.corp_events_collector import (  # noqa: E402
    DART_BASE, DART_PBLNTF_TYPES, _PAGE_COUNT, _parse_dart_key_from_lines)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scratchpad", "dart_dryrun_20260924")
RAW = os.path.join(OUT, "raw")
LIVE_ENV = r"D:/GIT/kis-trading-template/RoboTrader_template/.env"
WIN_BGN, WIN_END = "2024-03-13", "2026-09-23"
SAMPLE_MONTHS = ("2024-03", "2025-03", "2026-03")
CALL_CAP = 60
PSEUDO = ["KOSPI", "KOSDAQ", "KS11", "KQ11", "KOSPI200", "KOSDAQ150"]
DB = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")

# report_nm 키워드 분류(유형 분포용 · 첫 매치)
KW = [
    ("공급계약", ["공급계약"]),
    ("잠정실적", ["잠정)실적", "잠정실적", "영업(잠정)"]),
    ("유상증자", ["유상증자"]),
    ("무상증자", ["무상증자"]),
    ("분할병합", ["주식분할", "액면분할", "주식병합", "액면병합"]),
    ("CB·BW·EB", ["전환사채", "신주인수권부사채", "교환사채"]),
    ("자기주식", ["자기주식"]),
    ("조회공시", ["조회공시"]),
    ("매매정지·시장조치", ["매매거래정지", "관리종목", "투자주의", "투자경고", "투자위험", "상장폐지", "불성실"]),
    ("지분·대량보유", ["대량보유", "최대주주", "주요주주"]),
    ("타법인·시설투자", ["타법인주식", "신규시설투자", "유형자산"]),
    ("소송·횡령", ["소송", "횡령", "배임"]),
    ("기업설명회", ["기업설명회"]),
]


def classify(nm):
    for lab, kws in KW:
        if any(k in nm for k in kws):
            return lab
    return "기타"


def load_key():
    with open(LIVE_ENV, encoding="utf-8") as f:
        return _parse_dart_key_from_lines(f)


def db():
    c = psycopg2.connect(**DB)
    c.set_session(readonly=True, autocommit=True)
    return c


def sample_days(cur):
    """표본 월별 거래일 5개(균등 간격). 2024-03 은 창 시작 03-13 이후만."""
    out = {}
    for m in SAMPLE_MONTHS:
        cur.execute(
            "select distinct date from daily_prices where stock_code='005930' "
            "and left(date,7)=%s and date>=%s order by 1", (m, WIN_BGN))  # date 는 text
        ds = [r[0].replace("-", "") for r in cur.fetchall()]
        idx = [round(i * (len(ds) - 1) / 4) for i in range(5)]
        out[m] = [ds[i] for i in idx]
    return out


class Caller:
    def __init__(self, key):
        self.key = key
        self.log_path = os.path.join(OUT, "call_log.json")
        self.log = []
        if os.path.exists(self.log_path):
            with open(self.log_path, encoding="utf-8") as f:
                self.log = json.load(f)

    @property
    def n(self):
        return len(self.log)

    def get(self, fname, params):
        path = os.path.join(RAW, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        if self.n >= CALL_CAP:
            raise RuntimeError(f"호출 상한 {CALL_CAP} 도달 — 중단")
        p = dict(params, crtfc_key=self.key, page_count=_PAGE_COUNT)
        try:
            r = requests.get(f"{DART_BASE}/list.json", params=p, timeout=20)
            r.encoding = "utf-8"
            data = r.json()
        except Exception as e:  # 키가 URL 에 실려 예외 문자열로 새지 않게 가린다
            raise RuntimeError(str(e).replace(self.key, "<KEY>")) from None
        self.log.append({"file": fname, "params": params, "status": data.get("status"),
                         "total_count": data.get("total_count"), "ts": time.strftime("%H:%M:%S")})
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.log, f, ensure_ascii=False, indent=1)
        if data.get("status") == "020":
            raise RuntimeError("status 020 (요청 제한 초과) — 중단")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        time.sleep(0.7)
        return data


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_sample():
    os.makedirs(RAW, exist_ok=True)
    key = load_key()
    if not key:
        sys.exit("OPENDART_API_KEY 없음")
    with db() as c, c.cursor() as cur:
        days = sample_days(cur)
    with open(os.path.join(OUT, "sample_days.json"), "w") as f:
        json.dump(days, f, indent=1)
    call = Caller(key)
    flat = [d for m in SAMPLE_MONTHS for d in days[m]]
    # 1순위: 날짜별 B p1 · I p1 · 전체유형 p1(총건수) = 45회
    for d in flat:
        for ty in ("B", "I", "ALL"):
            prm = {"bgn_de": d, "end_de": d, "page_no": 1}
            if ty != "ALL":
                prm["pblntf_ty"] = ty
            call.get(f"{d}_{ty}_p1.json", prm)
    # 2순위: 남은 예산으로 I·B 추가 페이지 — 페이지 적은 날부터(완결 표본 우선)
    need = []
    for d in flat:
        for ty in ("I", "B"):
            p1 = _read(os.path.join(RAW, f"{d}_{ty}_p1.json"))
            tp = int(p1.get("total_page") or 1)
            for pg in range(2, tp + 1):
                need.append((tp, d, ty, pg))
    need.sort()
    for _, d, ty, pg in need:
        if call.n >= CALL_CAP:
            break
        call.get(f"{d}_{ty}_p{pg}.json", {"bgn_de": d, "end_de": d, "pblntf_ty": ty, "page_no": pg})
    print(f"외부 호출 누계 {call.n}/{CALL_CAP}")


def load_items(d, ty):
    """(items, total_count, total_page, complete) — 받은 페이지 전부 합침."""
    p1 = os.path.join(RAW, f"{d}_{ty}_p1.json")
    if not os.path.exists(p1):
        return [], 0, 0, False
    first = _read(p1)
    ok = first.get("status") == "000"
    tp = int(first.get("total_page") or 1) if ok else 0
    items = list(first.get("list") or [])
    got = 1
    for pg in range(2, tp + 1):
        f = os.path.join(RAW, f"{d}_{ty}_p{pg}.json")
        if os.path.exists(f):
            items += _read(f).get("list") or []
            got += 1
    tc = int(first.get("total_count") or 0) if ok else 0
    return items, tc, tp, (got >= tp)


def run_analyze():
    days = _read(os.path.join(OUT, "sample_days.json"))
    flat = [d for m in SAMPLE_MONTHS for d in days[m]]
    with db() as c, c.cursor() as cur:
        cur.execute("select distinct stock_code from daily_prices where date between %s and %s "
                    "and stock_code <> all(%s)", (WIN_BGN, WIN_END, PSEUDO))
        uni = {r[0] for r in cur.fetchall()}
        cur.execute("select count(distinct date) from daily_prices where stock_code='005930' "
                    "and date between %s and %s", (WIN_BGN, WIN_END))
        n_td = cur.fetchone()[0]
        cur.execute("select to_char(event_date,'YYYY-MM'), count(*), "
                    "count(*) filter (where meta->>'source'='opendart') from corp_events "
                    "where event_date between %s and %s group by 1 order by 1", (WIN_BGN, WIN_END))
        ce_month = {m: {"all": a, "opendart": o} for m, a, o in cur.fetchall()}
        cur.execute("select left(substring(url from 'rcpNo=([0-9]{8})'),6), count(*), "
                    "count(*) filter (where coalesce(related_stocks,'')<>'') from news "
                    "where source='dart' group by 1 order by 1")
        news_month = {m: {"rows": a, "with_stock": s} for m, a, s in cur.fetchall()}
        cur.execute("select substring(url from 'rcpNo=([0-9]{14})') from news where source='dart' "
                    "and substring(url from 'rcpNo=([0-9]{8})') = any(%s)", (flat,))
        news_rcp = {r[0] for r in cur.fetchall()}
        cur.execute("select meta->>'rcept_no' from corp_events where meta ? 'rcept_no'")
        ce_rcp = {r[0] for r in cur.fetchall()}

    per_day, agg = [], defaultdict(Counter)
    for m in SAMPLE_MONTHS:
        for d in days[m]:
            row = {"month": m, "day": d}
            union = {}
            for ty in ("B", "I", "ALL"):
                items, tc, tp, comp = load_items(d, ty)
                row[f"{ty}_total"], row[f"{ty}_pages"], row[f"{ty}_complete"] = tc, tp, comp
                row[f"{ty}_got"] = len(items)
                if ty in ("B", "I"):
                    for it in items:
                        union.setdefault(it["rcept_no"], (ty, it))
            its = [v[1] for v in union.values()]
            sc = [it for it in its if (it.get("stock_code") or "").strip()]
            row["BI_got"] = len(its)
            row["with_stock_code"] = len(sc)
            row["in_universe"] = sum(1 for it in sc if it["stock_code"] in uni)
            row["distinct_codes_in_uni"] = len({it["stock_code"] for it in sc if it["stock_code"] in uni})
            row["correction"] = sum(1 for it in its if "정정" in it["report_nm"])
            row["news_hit"] = sum(1 for k in union if k in news_rcp)
            row["news_rows_that_day"] = sum(1 for k in news_rcp if k and k[:8] == d)
            all_items, *_ = load_items(d, "ALL")
            row["ALL_p1_news_hit"] = sum(1 for it in all_items if it["rcept_no"] in news_rcp)
            row["ce_hit"] = sum(1 for k in union if k in ce_rcp)
            for ty, it in union.values():
                agg[m][f"{ty}:{classify(it['report_nm'])}"] += 1
                agg[m][f"cls:{it.get('corp_cls')}"] += 1
            per_day.append(row)

    est = {}
    for ty in ("B", "I", "ALL"):
        avg = sum(r[f"{ty}_total"] for r in per_day) / len(per_day)
        per_m = {m: sum(r[f"{ty}_total"] for r in per_day if r["month"] == m) / 5 for m in SAMPLE_MONTHS}
        rows = avg * n_td
        est[ty] = {
            "daily_avg_total": round(avg, 1), "daily_avg_by_month": per_m,
            "rows_window_est": round(rows),
            "calls_daily_chunks": round(sum(r[f"{ty}_pages"] for r in per_day) / len(per_day) * n_td),
            "calls_min_pages": math.ceil(rows / _PAGE_COUNT),
        }
    summary = {"window": [WIN_BGN, WIN_END], "trading_days": n_td, "universe": len(uni),
               "collector_types": list(DART_PBLNTF_TYPES), "page_count": _PAGE_COUNT,
               "calls_used": len(_read(os.path.join(OUT, "call_log.json"))),
               "per_day": per_day, "type_dist": {m: dict(agg[m].most_common()) for m in agg},
               "estimate": est, "corp_events_month": ce_month, "news_dart_month": news_month}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: summary[k] for k in ("trading_days", "universe", "calls_used", "estimate")},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    a = ap.parse_args()
    if a.sample:
        run_sample()
    if a.analyze:
        run_analyze()
