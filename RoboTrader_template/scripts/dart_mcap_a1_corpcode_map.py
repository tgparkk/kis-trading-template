"""A(1) DART corp_code ↔ stock_code 매핑 확보 + daily_prices 커버리지 실측.

읽기 전용. DB 는 SELECT 만. 산출물은 scratchpad/mcap_dart/ 아래.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_a1_corpcode_map.py
"""
import io
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests  # noqa: E402

from dart_mcap_common import DART_BASE, OUT_DIR, db_conn, load_dart_key  # noqa: E402

XML_CACHE = os.path.join(OUT_DIR, "corpCode.xml")
MAP_JSON = os.path.join(OUT_DIR, "a1_corpcode_map.json")
REPORT = os.path.join(OUT_DIR, "a1_report.txt")


def fetch_corp_code_xml(key: str) -> bytes:
    if os.path.exists(XML_CACHE) and os.path.getsize(XML_CACHE) > 1_000_000:
        with open(XML_CACHE, "rb") as f:
            return f.read()
    url = f"{DART_BASE}/corpCode.xml"
    r = requests.get(url, params={"crtfc_key": key}, timeout=120)
    r.raise_for_status()
    body = r.content
    # 🔴 빈/에러 응답을 성공으로 처리하지 말 것 — zip 이 아니면 즉시 실패.
    if not body[:2] == b"PK":
        raise RuntimeError(f"corpCode.xml 이 zip 이 아님 (len={len(body)}): {body[:400]!r}")
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = z.namelist()
        xml_names = [n for n in names if n.lower().endswith(".xml")]
        if not xml_names:
            raise RuntimeError(f"zip 안에 xml 없음: {names}")
        data = z.read(xml_names[0])
    with open(XML_CACHE, "wb") as f:
        f.write(data)
    return data


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    key = load_dart_key()
    if not key:
        raise SystemExit("OPENDART_API_KEY 없음")

    xml_bytes = fetch_corp_code_xml(key)
    root = ET.fromstring(xml_bytes)
    entries = root.findall("list")
    total_entries = len(entries)

    # stock_code → [corp_code,...] (중복 가능성 확인용)
    by_stock = {}
    listed = 0
    for e in entries:
        sc = (e.findtext("stock_code") or "").strip()
        cc = (e.findtext("corp_code") or "").strip()
        nm = (e.findtext("corp_name") or "").strip()
        mod = (e.findtext("modify_date") or "").strip()
        if not sc:  # 비상장 제외
            continue
        listed += 1
        by_stock.setdefault(sc, []).append({"corp_code": cc, "corp_name": nm, "modify_date": mod})

    dup = {k: v for k, v in by_stock.items() if len(v) > 1}

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM daily_prices")
    db_codes = sorted(r[0] for r in cur.fetchall())

    # 2021~2023 구간(백필 대상)에 실제 등장하는 종목
    cur.execute(
        "SELECT DISTINCT stock_code FROM daily_prices "
        "WHERE date >= '2021-01-01' AND date <= '2023-12-31'"
    )
    codes_2123 = sorted(r[0] for r in cur.fetchall())
    conn.close()

    matched = [c for c in db_codes if c in by_stock]
    unmatched = [c for c in db_codes if c not in by_stock]
    m2123 = [c for c in codes_2123 if c in by_stock]
    u2123 = [c for c in codes_2123 if c not in by_stock]

    mapping = {c: by_stock[c][0]["corp_code"] for c in matched}
    with open(MAP_JSON, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False)

    lines = []
    add = lines.append
    add("=== A(1) corp_code <-> stock_code 매핑 ===")
    add(f"corpCode.xml 총 항목      : {total_entries:,}")
    add(f"  그 중 상장(stock_code 有): {listed:,}")
    add(f"  고유 stock_code          : {len(by_stock):,}")
    add(f"  stock_code 중복 항목      : {len(dup):,}")
    if dup:
        for k in list(dup)[:10]:
            add(f"    {k}: {[d['corp_code'] + '/' + d['corp_name'] for d in dup[k]]}")
    add("")
    add(f"daily_prices 고유 stock_code : {len(db_codes):,}")
    add(f"  매핑됨                     : {len(matched):,} ({len(matched)/max(len(db_codes),1)*100:.2f}%)")
    add(f"  미매칭                     : {len(unmatched):,}")
    add(f"  미매칭 예시 10             : {unmatched[:10]}")
    add("")
    add(f"2021~2023 등장 stock_code    : {len(codes_2123):,}")
    add(f"  매핑됨                     : {len(m2123):,} ({len(m2123)/max(len(codes_2123),1)*100:.2f}%)")
    add(f"  미매칭                     : {len(u2123):,}")
    add(f"  미매칭 예시 10             : {u2123[:10]}")
    add("")
    add(f"매핑 저장: {MAP_JSON}")

    txt = "\n".join(lines)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    with open(os.path.join(OUT_DIR, "a1_unmatched.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(unmatched) + "\n")
    print(txt)


if __name__ == "__main__":
    main()
