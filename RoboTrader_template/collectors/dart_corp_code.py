"""DART corp_code ↔ stock_code 매핑 테이블.

🔴 이 매핑이 예전엔 scratchpad/mcap_dart/a1_corpcode_map.json 파일에만 있었다.
   그 디렉토리는 gitignore 대상이라 `git clean -xdf` 한 번에 사라진다.
   운영 수집기가 의존하는 데이터는 DB 에 있어야 한다.
"""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS dart_corp_code (
    stock_code varchar(20) PRIMARY KEY,
    corp_code  varchar(8)  NOT NULL,
    corp_name  text,
    updated_at timestamp   NOT NULL DEFAULT now()
)
"""

_UPSERT = """
INSERT INTO dart_corp_code (stock_code, corp_code, corp_name, updated_at)
VALUES (%(stock_code)s, %(corp_code)s, %(corp_name)s, now())
ON CONFLICT (stock_code) DO UPDATE SET
    corp_code=EXCLUDED.corp_code, corp_name=EXCLUDED.corp_name, updated_at=now()
"""


def parse_corpcode_xml(xml_bytes: bytes) -> dict:
    """corpCode.xml → {stock_code: corp_code}. 비상장(stock_code 공백)은 제외.

    🔴 결과가 비면 ValueError. 빈 매핑을 «성공»으로 돌려주면 수집 대상이 0이 되고
       그게 «오늘은 받을 게 없었다»로 보인다.
    """
    root = ET.fromstring(xml_bytes)
    out = {}
    for node in root.iter("list"):
        sc = (node.findtext("stock_code") or "").strip()
        cc = (node.findtext("corp_code") or "").strip()
        if not sc or not cc:
            continue
        out[sc] = cc
    if not out:
        raise ValueError("corpCode.xml 파싱 결과가 0건 — 응답 형식이 바뀌었거나 빈 응답이다")
    return out


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def upsert_map(conn, mapping: dict, names: dict = None) -> int:
    names = names or {}
    with conn.cursor() as cur:
        for sc, cc in mapping.items():
            cur.execute(_UPSERT, {"stock_code": sc, "corp_code": cc,
                                  "corp_name": names.get(sc)})
    conn.commit()
    return len(mapping)


def load_map(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code, corp_code FROM dart_corp_code")
        return {r[0]: r[1] for r in cur.fetchall()}


def refresh_from_dart(conn, key: str) -> int:
    """corpCode.xml 1회 다운로드 → 적재. 호출 1건이라 한도 영향 미미."""
    import io
    import zipfile
    import requests
    r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                     params={"crtfc_key": key}, timeout=120)
    r.raise_for_status()
    body = r.content
    # 🔴 zip 이 아니면 즉시 실패. 에러 JSON 을 xml 로 파싱하면 0건이 «성공»이 된다.
    if body[:2] != b"PK":
        raise RuntimeError(f"corpCode.xml 이 zip 이 아님 (len={len(body)}): {body[:200]!r}")
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        xmls = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not xmls:
            raise RuntimeError(f"zip 안에 xml 없음: {z.namelist()}")
        data = z.read(xmls[0])
    mapping = parse_corpcode_xml(data)
    ensure_table(conn)
    n = upsert_map(conn, mapping)
    logger.info("[dart_corp_code] 매핑 갱신 %d건", n)
    return n
