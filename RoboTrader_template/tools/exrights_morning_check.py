"""보유 종목(실전+페이퍼) 기업행위 예고 점검 — 읽기 전용 · KIS/DART API 호출 0 (2026-10-10 사장님 (d))

왜: 보유 종목이 권리락·분할·병합·감자·합병·주식교환을 맞으면 ① 그날 09:05 가짜 손절(페이퍼 000500
2026-06-30 −37.52%), ② 신주·변경 수량이 계좌에 들어온 날 아침 계좌-DB 수량 대사에서
`LiveStartupAbort` 로 실전 기동이 멈춘다(`bot/state_restorer.py:1293-1301`). 봇은 이걸
막지 못하므로(조사 문서 INVESTIGATION_exrights.md) 매일 아침 사람이 보게 알린다.

무엇을 보나(종목마다):
  1. `dart_disclosures` 최근 90일 report_nm 이 CORP_ACTION_RE 에 걸리는지
     (공백 무시 · [기재정정]/[첨부정정] 접두 그대로 매칭 · «종속회사» 공시는 제외).
  2. 보조: `news` source='dart' 제목(같은 정규식) — dart_disclosures 적재(08:30) 밖 공시 보강.
  3. `daily_prices` 최근 2거래일 가격 불연속(저가 < 전일종가×0.695 또는 고가 > 전일종가×1.305
     = 하루 ±30% 한도 밖 = 기준가 조정).
그리고 종목과 별개로 1블록(2026-10-28 ⑪ · 출력 전용 · 매매 영향 0):
  4. «가격제한폭 초과» — `daily_prices` 직전 거래일(KOSPI 의사티커 날짜 기준 · 기준일 «전») 의
     |returns_1d| > 0.30 종목(의사티커 6 제외 · volume>0) ∩ 대상 종목 → `🔴 가격제한폭 밖 …` 줄.
     없으면 `가격제한폭 밖 보유 0` 1줄 + 전체 건수(그중 corp_events −15~+5일 0건 수).
     계기: 004415(10-21~ 연속 −34~−60%)는 corp_events·dart_disclosures 0행이라 1~3 으로는 못 잡는다.

대상: 기본 = ① 실전 daytrading 원장 `real_trading_daytrading` 의 미청산 보유
  (`bot/state_restorer.py:1276` 이 실전 복원에 쓰는 `get_real_open_positions`
   = `db/repositories/trading.py:497-510` 의 잔량 쿼리를 그대로 옮김 —
   저장소 클래스는 생성자가 CREATE TABLE 을 해서(`trading.py:41-42`) 쓰지 않는다)
  + ② 페이퍼 8전략 미청산 보유(`virtual_trading_records` is_test=true · BUY 수량 − 연결 SELL 수량 > 0 ·
   종목×전략별). 출력에 «실전/페이퍼·전략» 칸.
  ⚠️ 다음 거래일 후보(09:00 스크리너 스냅샷)는 넣지 않는다 — 이 점검은 08:40 에 돌고, 오늘 쓸 스냅샷
   (scan_date = 전일 행)은 오늘 09:00 에야 생기므로 08:40 시점엔 아직 없다(2026-10-28 ⑪).
  `--codes 000500,475460` 이면 원장 대신 그 종목들(점검 연습용).

사용:
  python tools/exrights_morning_check.py                       # 실전+페이퍼 보유 종목
  python tools/exrights_morning_check.py --codes 000500,475460 # 임의 종목
  python tools/exrights_morning_check.py --telegram            # 걸리면 텔레그램 1건
  옵션: --as-of YYYY-MM-DD (기본 오늘 KST) · --days 90 · --key-ini <경로>

종료 코드: 0 = 걸린 것 없음(보유 없음 포함) · 3 = 걸림 · 2 = 데이터 오류(DB 접속·조회 실패)
🔴 DB 는 SELECT 만(읽기 전용 세션). 텔레그램 토큰은 출력하지 않는다.
"""
import argparse
import configparser
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

EXIT_OK = 0
EXIT_DATA_ERROR = 2
EXIT_HIT = 3

# = config.settings.real_trading_table_name("daytrading") (settings.py:38-41).
#   settings 를 import 하면 key.ini 경고가 stdout 에 섞여 상수로 둔다(테스트가 일치 확인).
REAL_TABLE = "real_trading_daytrading"
PAPER_TABLE = "virtual_trading_records"
DEFAULT_KEY_INI = _ROOT / "instances" / "daytrading" / "key.ini"
DEFAULT_LOOKBACK_DAYS = 90

CORP_ACTION_RE = re.compile(
    r"무상증자결정|주식배당결정|주식분할결정|주식병합결정|감자결정|유상증자결정"
    r"|권리락|배당락|변경상장|주권매매거래정지"
    r"|회사합병결정|회사분할(?:합병)?결정|주식교환.?이전결정"  # 10-10 사장님: 합병·분할·주식교환/이전 추가
    r"|상장폐지(?!우려)|정리매매|관리종목(?!지정우려)|감자"     # 10-28 ⑪: 상폐·정리매매·관리종목·감자(기존 낱말이 먼저)
)
# «지정우려»류 안내(예: 222420 「기타시장안내(관리종목지정우려종목)(주가 1,000원 미달)」)는 지정 «전» 예고라
#   걸림(rc 3)이 아니라 rc 0 «참고» 줄로만 보인다(10-28 리뷰 후속 · 매일 오경보 방지).
CONCERN_RE = re.compile(r"관리종목지정우려|상장폐지우려")
# 자회사 공시(KOSPI 「…(종속회사의주요경영사항)」 · KOSDAQ 「…(자회사의주요경영사항)」)는 보유 종목 기준가와 무관 → 제외.
#   안 빼면 대형주(예: 005930)가 매일 아침 오경보를 낸다.
_EXCLUDE_RE = re.compile(r"종속회사|자회사의주요경영사항")
_NEWS_COMPANY_PREFIX_RE = re.compile(r"^\[[^\]]*\]\s*")
LIMIT_DOWN_RATIO = 0.695   # 하루 −30% 한도 밖 (반올림 여유)
LIMIT_UP_RATIO = 1.305     # 하루 +30% 한도 밖
LIMIT_BAND_RETURN = 0.30   # «가격제한폭 초과» 블록 — 직전 거래일 |returns_1d| 문턱(제도 숫자 ±30%)
# daily_prices 의사티커(지수) — 가격제한 대상 아님 · 퀀트 ⑪ SQL(q2_quant_1029.py) 과 같은 6개
PSEUDO_TICKERS = ("KOSPI", "KOSDAQ", "KOSPI200", "KOSDAQ150", "KRX100", "KOSPI100")

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 순수 함수
# ---------------------------------------------------------------------------

def normalize_title(title: Any) -> str:
    """공백 전부 제거(report_nm 은 «권리락              (무상증자)» 처럼 공백이 들쭉날쭉)."""
    return re.sub(r"\s+", "", str(title or ""))


def classify_title(title: Any) -> Optional[str]:
    """기업행위 공시면 걸린 낱말(예: '권리락'), 아니면 None."""
    norm = normalize_title(title)
    if not norm or _EXCLUDE_RE.search(norm):
        return None
    m = CORP_ACTION_RE.search(norm)
    return m.group(0) if m else None


def classify_concern(title: Any) -> Optional[str]:
    """«우려» 안내 공시면 걸린 낱말 — 걸림(classify_title)이 아닐 때만 참고 줄로 쓴다."""
    norm = normalize_title(title)
    if not norm or _EXCLUDE_RE.search(norm) or CORP_ACTION_RE.search(norm):
        return None
    m = CONCERN_RE.search(norm)
    return m.group(0) if m else None


def strip_news_company(title: Any) -> str:
    """news 제목 «[회사명] report_nm» → report_nm (첫 대괄호 1개만)."""
    return _NEWS_COMPANY_PREFIX_RE.sub("", str(title or ""), count=1)


def detect_discontinuities(rows: Sequence[Tuple[Any, float, float, float, float]],
                           last_n: int = 2) -> List[Dict[str, Any]]:
    """rows = [(date, open, high, low, close)] 오름차순. 마지막 last_n 일 각각을 그 전날 종가와 비교."""
    out: List[Dict[str, Any]] = []
    if len(rows) < 2:
        return out
    start = max(1, len(rows) - last_n)
    for i in range(start, len(rows)):
        d, _o, high, low, _c = rows[i]
        prev_close = rows[i - 1][4]
        try:
            prev_close = float(prev_close)
            high = float(high)
            low = float(low)
        except (TypeError, ValueError):
            continue
        if prev_close <= 0:
            continue
        if low < prev_close * LIMIT_DOWN_RATIO or high > prev_close * LIMIT_UP_RATIO:
            out.append({"date": d, "prev_close": prev_close, "low": low, "high": high,
                        "low_ratio": low / prev_close, "high_ratio": high / prev_close})
    return out


# ---------------------------------------------------------------------------
# DB (SELECT 만)
# ---------------------------------------------------------------------------

def connect_readonly():
    """kis_template 읽기 전용 접속 — DB명은 resolver 경유(하드코딩 금지 규칙)."""
    import config.env_bootstrap  # noqa: F401  (.env → os.environ, OS env 우선)
    import psycopg2
    from config.constants import resolve_daily_source_db
    conn = psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "localhost"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        dbname=resolve_daily_source_db(),
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
        connect_timeout=10,
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
    row = cur.fetchone()
    return bool(row and row[0])


def load_open_holdings(cur, table: str = REAL_TABLE) -> List[Dict[str, Any]]:
    """미청산 보유(잔량>0) — db/repositories/trading.py:497-510 과 같은 모양. 종목별로 합친다."""
    if not re.fullmatch(r"real_trading_[a-z0-9_]+", table):
        raise ValueError(f"허용되지 않은 테이블명: {table}")
    cur.execute(f'''
        SELECT b.stock_code, MAX(b.stock_name) AS stock_name,
               SUM(t.qty)::bigint AS quantity,
               SUM(t.qty * b.price) / NULLIF(SUM(t.qty), 0) AS avg_price
        FROM (
            SELECT b.id, b.quantity - COALESCE(SUM(s.quantity), 0) AS qty
            FROM {table} b
            LEFT JOIN {table} s ON s.buy_record_id = b.id AND s.action = 'SELL'
            WHERE b.action = 'BUY'
            GROUP BY b.id, b.quantity
            HAVING b.quantity - COALESCE(SUM(s.quantity), 0) > 0
        ) t JOIN {table} b ON b.id = t.id
        GROUP BY b.stock_code
        ORDER BY b.stock_code
    ''')
    return [{"stock_code": r[0], "stock_name": r[1] or "", "quantity": int(r[2]),
             "avg_price": float(r[3]) if r[3] is not None else None}
            for r in cur.fetchall()]


def load_paper_holdings(cur, table: str = PAPER_TABLE) -> List[Dict[str, Any]]:
    """페이퍼 미청산 보유(is_test=true · BUY 수량 − 연결 SELL 수량 > 0) — 종목×전략별로 합친다."""
    if table != PAPER_TABLE:
        raise ValueError(f"허용되지 않은 테이블명: {table}")
    cur.execute(f'''
        SELECT b.stock_code, MAX(b.stock_name) AS stock_name, b.strategy,
               SUM(t.qty)::bigint AS quantity,
               SUM(t.qty * b.price) / NULLIF(SUM(t.qty), 0) AS avg_price
        FROM (
            SELECT b.id, b.quantity - COALESCE(SUM(s.quantity), 0) AS qty
            FROM {table} b
            LEFT JOIN {table} s ON s.buy_record_id = b.id AND s.action = 'SELL'
            WHERE b.action = 'BUY' AND b.is_test = true
            GROUP BY b.id, b.quantity
            HAVING b.quantity - COALESCE(SUM(s.quantity), 0) > 0
        ) t JOIN {table} b ON b.id = t.id
        GROUP BY b.stock_code, b.strategy
        ORDER BY b.stock_code, b.strategy
    ''')
    return [{"stock_code": r[0], "stock_name": r[1] or "", "strategy": r[2] or "?", "quantity": int(r[3]),
             "avg_price": float(r[4]) if r[4] is not None else None}
            for r in cur.fetchall()]


def load_prev_trading_day(cur, as_of: date) -> Optional[str]:
    """기준일 «전» 마지막 거래일(daily_prices KOSPI 의사티커 날짜 · 'YYYY-MM-DD' 텍스트)."""
    cur.execute("SELECT MAX(date) FROM daily_prices WHERE stock_code = 'KOSPI' AND date < %s",
                (as_of.isoformat(),))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def load_limit_band_breaches(cur, day: str) -> List[Dict[str, Any]]:
    """그날 |returns_1d| > 0.30 종목(의사티커 제외 · volume>0) + corp_events(−15~+5일) 건수."""
    cur.execute(
        "SELECT p.stock_code, p.returns_1d, p.close, "
        "(SELECT COUNT(*) FROM corp_events e WHERE e.stock_code = p.stock_code "
        " AND e.event_date BETWEEN (p.date::date - 15) AND (p.date::date + 5)) AS n_corp "
        "FROM daily_prices p "
        "WHERE p.date = %s AND ABS(p.returns_1d) > %s AND p.volume > 0 AND p.stock_code NOT IN %s "
        "ORDER BY p.stock_code",
        (day, LIMIT_BAND_RETURN, PSEUDO_TICKERS))
    return [{"code": r[0], "ret": float(r[1]), "close": float(r[2]) if r[2] is not None else None,
             "n_corp": int(r[3] or 0)} for r in cur.fetchall()]


def load_disclosures(cur, code: str, since: date, as_of: date) -> List[Tuple[date, str]]:
    cur.execute(
        "SELECT rcept_dt, report_nm FROM dart_disclosures "
        "WHERE stock_code = %s AND rcept_dt >= %s AND rcept_dt <= %s ORDER BY rcept_dt",
        (code, since, as_of))
    return [(r[0], r[1]) for r in cur.fetchall()]


def load_dart_news(cur, code: str, since: date, as_of: date) -> List[Tuple[Any, str]]:
    cur.execute(
        "SELECT published_at, title FROM news "
        "WHERE source = 'dart' AND related_stocks LIKE %s "
        "AND published_at >= %s AND published_at < %s ORDER BY published_at",
        (f"%{code}%", since, as_of + timedelta(days=1)))
    return [(r[0], r[1]) for r in cur.fetchall()]


def load_recent_daily(cur, code: str, as_of: date, n: int = 3) -> List[Tuple[str, float, float, float, float]]:
    """daily_prices 최근 n행(오름차순). date 컬럼은 'YYYY-MM-DD' 텍스트."""
    cur.execute(
        "SELECT date, open, high, low, close FROM daily_prices "
        "WHERE stock_code = %s AND date <= %s ORDER BY date DESC LIMIT %s",
        (code, as_of.isoformat(), n))
    return list(reversed([tuple(r) for r in cur.fetchall()]))


# ---------------------------------------------------------------------------
# 점검 · 보고
# ---------------------------------------------------------------------------

def _to_day(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def check_code(cur, code: str, as_of: date, days: int) -> Dict[str, Any]:
    since = as_of - timedelta(days=days)
    hits: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    seen = set()
    for d, name in load_disclosures(cur, code, since, as_of):
        kw = classify_title(name) or classify_concern(name)
        if kw:
            seen.add((_to_day(d), normalize_title(name)))
            (hits if classify_title(name) else notes).append(
                {"date": _to_day(d), "source": "DART", "keyword": kw,
                 "title": re.sub(r"\s+", " ", str(name)).strip()})
    for ts, title in load_dart_news(cur, code, since, as_of):
        body = strip_news_company(title)
        kw = classify_title(body) or classify_concern(body)
        key = (_to_day(ts), normalize_title(body))
        if kw and key not in seen:
            seen.add(key)
            (hits if classify_title(body) else notes).append(
                {"date": _to_day(ts), "source": "뉴스(dart)", "keyword": kw,
                 "title": re.sub(r"\s+", " ", body).strip()})
    hits.sort(key=lambda h: h["date"])
    notes.sort(key=lambda h: h["date"])
    daily = load_recent_daily(cur, code, as_of)
    jumps = detect_discontinuities(daily)
    return {"code": code, "disclosures": hits, "notes": notes, "jumps": jumps, "daily_rows": len(daily)}


def _holding_label(h: Dict[str, Any]) -> str:
    return "실전" if h.get("kind") == "real" else f"페이퍼·{h.get('strategy', '?')}"


def _held_text(hs: Sequence[Dict[str, Any]]) -> str:
    """« 이름 보유 3주 평단 8,200원 [실전] · 보유 5주 평단 8,100원 [페이퍼·rs_leader]»."""
    if not hs:
        return ""
    parts = []
    for h in hs:
        avg = f"{h['avg_price']:,.0f}원" if h.get("avg_price") else "?"
        parts.append(f"보유 {h['quantity']}주 평단 {avg} [{_holding_label(h)}]")
    name = next((h.get("stock_name") for h in hs if h.get("stock_name")), "")
    return (f" {name} " if name else " ") + " · ".join(parts)


def format_limit_block(limit: Dict[str, Any], holdings: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """«가격제한폭 초과» 블록 줄 — limit = {"day", "rows", "hits"}(hits = 대상 종목에 걸린 rows)."""
    if not limit.get("day"):
        return ["가격제한폭 점검 못 함(직전 거래일 없음)"]
    rows = limit.get("rows", [])
    n_no_corp = sum(1 for r in rows if r["n_corp"] == 0)
    summary = f"어제({limit['day']}) ±30% 밖 종목 {len(rows)}개 · 그중 corp_events 없는 {n_no_corp}개"
    hits = limit.get("hits", [])
    if not hits:
        return [f"가격제한폭 밖 보유 0 · {summary}"]
    out = [summary]
    for r in hits:
        labels = ",".join(_holding_label(h) for h in holdings.get(r["code"], [])) or "--codes"
        close = f"{r['close']:,.0f}" if r.get("close") is not None else "?"
        out.append(f"🔴 가격제한폭 밖 {r['code']} [{labels}]: {limit['day']} 수익률 {r['ret'] * 100:+.2f}% · "
                   f"종가 {close} · corp_events {r['n_corp']}건")
    return out


def format_report(as_of: date, days: int, target_label: str,
                  holdings: Dict[str, List[Dict[str, Any]]], results: List[Dict[str, Any]],
                  limit: Optional[Dict[str, Any]] = None) -> str:
    since = as_of - timedelta(days=days)
    lines = [f"[보유 종목 기업행위 예고 점검(실전+페이퍼)] 기준일 {as_of} · 실행 {datetime.now(KST):%H:%M:%S} · "
             f"대상 {len(results)}종목({target_label}) · 공시 창 {days}일({since}~)"]
    n_hit = 0
    for r in results:
        held = _held_text(holdings.get(r["code"], []))
        refs = r.get("notes", [])
        if not r["disclosures"] and not r["jumps"]:
            note = " (일봉 없음 — 불연속 점검 못 함)" if r["daily_rows"] < 2 else ""
            ref = f" (참고 {len(refs)}건)" if refs else ""
            lines.append(f"- {r['code']}{held}: 걸린 것 없음{note}{ref}")
            for n in refs:
                lines.append(f"    · 참고 {n['date']} {n['source']} {n['title']}")
            continue
        n_hit += 1
        lines.append(f"- {r['code']}{held}: ⚠️ 공시 {len(r['disclosures'])}건 · 가격 불연속 {len(r['jumps'])}건")
        for d in r["disclosures"]:
            lines.append(f"    · {d['date']} {d['source']} {d['title']}")
        for n in refs:
            lines.append(f"    · 참고 {n['date']} {n['source']} {n['title']}")
        for j in r["jumps"]:
            lines.append(f"    · {j['date']} 가격 불연속: 전일종가 {j['prev_close']:,.0f} · "
                         f"저가 {j['low']:,.0f}({j['low_ratio']:.3f}) · 고가 {j['high']:,.0f}({j['high_ratio']:.3f})")
    if limit is not None:
        lines.extend(format_limit_block(limit, holdings))
        flagged = {r["code"] for r in results if r["disclosures"] or r["jumps"]}
        n_hit += len({r["code"] for r in limit.get("hits", [])} - flagged)
    if n_hit:
        lines.append(f"결과: 걸림 {n_hit}종목 → 오늘 보유분(실전·페이퍼) 수동 확인 "
                     f"(권리락·분할·병합·감자·합병·주식교환이면 가짜 손절·다음날 기동 중단 위험 — 판단은 사람)")
        lines.append("참고: 합병은 보유 종목이 존속(흡수하는) 회사면 대개 영향 없음 · 물적분할도 보유분엔 대개 영향 없음")
    else:
        lines.append("결과: 걸린 것 없음")
    return "\n".join(lines)


def read_telegram_config(key_ini: Path) -> Optional[Dict[str, str]]:
    """[TELEGRAM] enabled/token/chat_id — 읽기만. 비활성·누락이면 None."""
    try:
        if not key_ini.exists():
            return None
        parser = configparser.RawConfigParser()
        parser.read(key_ini, encoding="utf-8")
        if "TELEGRAM" not in parser:
            return None
        sec = parser["TELEGRAM"]
        token = sec.get("token", "").strip()
        chat_id = sec.get("chat_id", "").strip()
        if not sec.getboolean("enabled", False) or not token or not chat_id:
            return None
        return {"token": token, "chat_id": chat_id}
    except Exception as e:  # ParsingError 메시지는 key.ini 줄을 그대로 싣는다 → 형식명만
        print(f"key.ini 읽기 실패: {type(e).__name__}")
        return None


def send_telegram(cfg: Dict[str, str], text: str) -> bool:
    """Bot API sendMessage 1건(평문). 예외는 삼키고 False — 토큰이 섞인 URL 은 출력하지 않는다."""
    data = urllib.parse.urlencode({"chat_id": cfg["chat_id"], "text": text[:4000]}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{cfg['token']}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception as e:  # HTTPError/URLError 메시지에도 URL 이 들어갈 수 있어 형식명만
        print(f"텔레그램 전송 실패: {type(e).__name__}")
        return False


def parse_codes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    codes = [c.strip() for c in raw.split(",") if c.strip()]
    bad = [c for c in codes if not re.fullmatch(r"[0-9A-Z]{6}", c)]
    if bad:
        raise ValueError(f"종목코드 형식 오류: {bad}")
    return list(dict.fromkeys(codes))


def notify_failure(args: argparse.Namespace, exc_name: str, sender=send_telegram) -> None:
    """점검 자체가 실패했을 때 짧은 평문 1건 — 「조용함 = 이상 없음」 오해 방지. 예외 본문은 싣지 않는다."""
    try:
        cfg = read_telegram_config(Path(args.key_ini))
        if cfg is None:
            print("실패 알림 생략: key.ini [TELEGRAM] 비활성·누락")
            return
        sender(cfg, f"[기업행위 점검 실패] 데이터 오류({exc_name}) — 수동 확인")
    except Exception as e:
        print(f"실패 알림 전송 실패: {type(e).__name__}")


def run(argv: Optional[Sequence[str]] = None, connect=connect_readonly,
        sender=send_telegram) -> int:
    """종료 코드 0/2/3. `--telegram` 이면 데이터 오류(2)·예상 못 한 예외에도 «점검 실패» 1건(보유 없음은 조용)."""
    ap = argparse.ArgumentParser(description="보유 종목(실전+페이퍼) 기업행위 예고 점검(읽기 전용)")
    ap.add_argument("--codes", help="쉼표로 구분한 종목코드(원장 대신 점검)")
    ap.add_argument("--telegram", action="store_true", help="걸린 게 있으면 텔레그램 1건")
    ap.add_argument("--as-of", help="기준일 YYYY-MM-DD (기본 오늘 KST)")
    ap.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="공시 창(달력일)")
    ap.add_argument("--key-ini", default=str(DEFAULT_KEY_INI), help="[TELEGRAM] 읽을 key.ini")
    args = ap.parse_args(argv)
    try:
        code, failure = _execute(args, connect, sender)
    except Exception as e:
        print(f"데이터 오류: 예상 못 한 예외 ({type(e).__name__})")
        code, failure = EXIT_DATA_ERROR, type(e).__name__
    if failure and args.telegram:
        notify_failure(args, failure, sender)
    return code


def _execute(args: argparse.Namespace, connect, sender) -> Tuple[int, Optional[str]]:
    """(종료 코드, 실패 예외 형식명 — 데이터 오류일 때만)."""
    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(KST).date()
        codes = parse_codes(args.codes)
    except ValueError as e:
        print(f"인자 오류: {e}")
        return EXIT_DATA_ERROR, type(e).__name__

    try:
        conn = connect()
    except Exception as e:
        print(f"데이터 오류: DB 접속 실패 ({type(e).__name__}: {e})")
        return EXIT_DATA_ERROR, type(e).__name__

    try:
        cur = conn.cursor()
        holdings: Dict[str, List[Dict[str, Any]]] = {}
        if codes:
            target_label = "--codes"
        else:
            real_ok = table_exists(cur, REAL_TABLE)
            paper_ok = table_exists(cur, PAPER_TABLE)
            real = load_open_holdings(cur, REAL_TABLE) if real_ok else []
            paper = load_paper_holdings(cur, PAPER_TABLE) if paper_ok else []
            for h in real:
                holdings.setdefault(h["stock_code"], []).append(dict(h, kind="real"))
            for h in paper:
                holdings.setdefault(h["stock_code"], []).append(dict(h, kind="paper"))
            real_note = (f"실전 {REAL_TABLE} 미청산 {len(real)}건" if real_ok
                         else f"실전 원장 없음({REAL_TABLE} 테이블 없음 — 실전 미시작)")
            paper_note = (f"페이퍼 {PAPER_TABLE} 미청산 {len(paper)}건" if paper_ok
                          else f"페이퍼 원장 없음({PAPER_TABLE} 테이블 없음)")
            target_label = f"{real_note} · {paper_note}"
            codes = sorted(holdings)
            if not codes:
                print(f"[보유 종목 기업행위 예고 점검(실전+페이퍼)] 기준일 {as_of} · 보유 없음 ({target_label})")
                return EXIT_OK, None
        results = [check_code(cur, c, as_of, args.days) for c in codes]
        limit_day = load_prev_trading_day(cur, as_of)
        limit_rows = load_limit_band_breaches(cur, limit_day) if limit_day else []
        targets = set(codes)
        limit = {"day": limit_day, "rows": limit_rows,
                 "hits": [r for r in limit_rows if r["code"] in targets]}
    except Exception as e:
        print(f"데이터 오류: 조회 실패 ({type(e).__name__}: {e})")
        return EXIT_DATA_ERROR, type(e).__name__
    finally:
        try:
            conn.close()
        except Exception:
            pass

    report = format_report(as_of, args.days, target_label, holdings, results, limit)
    print(report)
    hit = any(r["disclosures"] or r["jumps"] for r in results) or bool(limit["hits"])
    if hit and args.telegram:
        cfg = read_telegram_config(Path(args.key_ini))
        if cfg is None:
            print("텔레그램 생략: key.ini [TELEGRAM] 비활성·누락")
        elif sender(cfg, report):
            print("텔레그램 전송 완료")
    return (EXIT_HIT if hit else EXIT_OK), None


if __name__ == "__main__":
    sys.exit(run())
