import pytest
from collectors import dart_corp_code as m

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list><corp_code>00126380</corp_code><corp_name>samsung</corp_name>
        <stock_code>005930</stock_code><modify_date>20260101</modify_date></list>
  <list><corp_code>00164779</corp_code><corp_name>sk</corp_name>
        <stock_code>000660</stock_code><modify_date>20260101</modify_date></list>
  <list><corp_code>00999999</corp_code><corp_name>nonlisted</corp_name>
        <stock_code>     </stock_code><modify_date>20260101</modify_date></list>
</result>"""


def test_parse_skips_nonlisted():
    """stock_code 가 공백인 비상장사는 매핑에서 빠져야 한다."""
    out = m.parse_corpcode_xml(SAMPLE_XML)
    assert out == {"005930": "00126380", "000660": "00164779"}


def test_parse_rejects_empty_result():
    """빈 결과를 «성공»으로 돌려주면 안 된다 — 매핑 전멸이 조용히 통과한다."""
    with pytest.raises(ValueError):
        m.parse_corpcode_xml(b"<?xml version='1.0'?><result></result>")
