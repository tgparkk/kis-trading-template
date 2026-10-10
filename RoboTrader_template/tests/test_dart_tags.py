"""DART 제목 태그 사전 — 사전등록 `docs/prereg_2026-09-26_dart_disclosure_events.md` §3 (V2)."""
import re
from pathlib import Path

import pytest

from backtest.concept_axes.candidate_ledger.dart_events import dart_tags as DT

T, F = True, False

# §3-4 손라벨 15제목 — 기대값 (태그, is_corr)
HAND_15 = [
    ("[기재정정]주요사항보고서(유상증자결정)", "유상증자", T),
    ("주요사항보고서(전환사채권발행결정)", "CB/BW/EB", F),
    ("[연장결정]주요사항보고서(자기주식취득신탁계약체결결정)", "기타", F),
    ("단일판매ㆍ공급계약체결(자율공시)", "공급계약", F),
    ("단일판매·공급계약체결", "공급계약", F),
    ("단일판매ㆍ공급계약체결(자회사의 주요경영사항)", "기타", F),
    ("[첨부추가]단일판매ㆍ공급계약체결", "공급계약", T),
    ("최대주주변경을수반하는주식담보제공계약체결", "기타", F),
    ("최대주주인명목회사ㆍ조합등의최대주주변경", "기타", F),
    ("연결재무제표기준영업(잠정)실적(공정공시)", "잠정실적", F),
    ("매출액또는손익구조30%(대규모법인은15%)이상변경", "잠정실적", F),
    ("매출액또는손익구조30%(대규모법인15%)미만변경(자율공시)", "기타", F),
    ("소송등의제기ㆍ신청(경영권분쟁소송)", "소송·횡령", F),
    ("소송등의판결ㆍ결정", "기타", F),
    ("유상증자최종발행가액확정", "기타", F),
]


def test_hand_labels_count():
    assert len(HAND_15) == 15


@pytest.mark.parametrize("title,tag,corr", HAND_15)
def test_hand_labels(title, tag, corr):
    got_tag, got_corr, _ = DT.tag_of(title)
    assert (got_tag, got_corr) == (tag, corr)


# 가운뎃점 6종 — ㆍ(U+318D) · ·(U+00B7) · ・(U+30FB) · ･(U+FF65) · ∙(U+2219) · ‧(U+2027)
@pytest.mark.parametrize("dot", ["ㆍ", "·", "・", "･", "∙", "‧"])
def test_middle_dot_variants(dot):
    assert DT.tag_of(f"단일판매{dot}공급계약체결")[0] == "공급계약"
    assert DT.tag_of(f"횡령{dot}배임혐의발생")[0] == "소송·횡령"
    assert DT.tag_of(f"횡령{dot}배임혐의진행사항")[0] == "기타"
    assert DT.normalize(f"단일판매{dot}공급계약체결")[1] == "단일판매·공급계약체결"


def test_middle_dot_list_is_six():
    assert len(DT.MIDDOTS) == 6 and len(set(DT.MIDDOTS)) == 6


@pytest.mark.parametrize("title,tag,corr", [
    (" 주요사항보고서 ( 유상증자결정 ) ", "유상증자", F),
    ("주요사항보고서(유상증자결정)　", "유상증자", F),
    ("단일판매 ㆍ 공급계약체결", "공급계약", F),
    ("[기재정정] [첨부추가] 단일판매ㆍ공급계약체결", "공급계약", T),
    ("[정정]주요사항보고서(자기주식취득결정)", "자기주식취득", T),
    ("[첨부정정]주요사항보고서(교환사채권발행결정)", "CB/BW/EB", T),
    ("[기재정정][연장결정]주요사항보고서(자기주식취득신탁계약체결결정)", "기타", T),
    ("[정정명령부과]주요사항보고서(유상증자결정)", "기타", F),
    ("단일판매ㆍ공급계약체결(종속회사의 주요경영사항)", "기타", F),
    ("[기재정정]단일판매ㆍ공급계약체결(자회사의주요경영사항)", "기타", T),
    ("주요사항보고서(무상증자결정)", "기타", F),
    ("주요사항보고서(유무상증자결정)", "유상증자", F),
    ("유상증자결정(종속회사의주요경영사항)", "기타", F),
    ("주요사항보고서(신주인수권부사채권발행결정)", "CB/BW/EB", F),
    ("전환가액의조정", "기타", F),
    ("주요사항보고서(자기주식처분결정)", "기타", F),
    ("주요사항보고서(자기주식취득신탁계약해지결정)", "기타", F),
    ("단일판매ㆍ공급계약해지", "기타", F),
    ("최대주주변경", "최대주주변경", F),
    ("최대주주변경(최대주주의주식양수도)", "최대주주변경", F),
    ("최대주주변경을수반하는주식양수도계약체결", "최대주주변경", F),
    ("최대주주등소유주식변동신고서(최대주주변경시)", "최대주주변경", F),
    ("최대주주등소유주식변동신고서(일반)", "기타", F),
    ("경영권변경등에관한계약체결", "최대주주변경", F),
    ("최대주주인명목회사의최대주주변경", "기타", F),
    ("투자판단관련주요경영사항(최대주주변경)", "기타", F),
    ("영업(잠정)실적(공정공시)", "잠정실적", F),
    ("매출액또는손익구조30%(대규모법인15%)이상변동", "잠정실적", F),
    ("매출액또는손익구조20%(대규모법인은10%)이상변경", "잠정실적", F),
    ("매출액또는손익구조30%(대규모법인은15%)미만변동(자율공시)", "기타", F),
    ("영업실적등에대한전망(공정공시)", "기타", F),
    ("주요사항보고서(소송등의제기)", "소송·횡령", F),
    ("횡령ㆍ배임사실확인", "소송·횡령", F),
    ("횡령ㆍ배임혐의진행사항", "기타", F),
    ("소송등의제기ㆍ신청(일정금액이상의청구)", "소송·횡령", F),
    ("감사보고서제출", "기타", F),
    ("", "기타", F),
])
def test_spacing_prefix_variants(title, tag, corr):
    got_tag, got_corr, _ = DT.tag_of(title)
    assert (got_tag, got_corr) == (tag, corr)


def test_normalize_prefixes_and_body():
    pre, body = DT.normalize("[기재정정] [첨부추가] 단일판매 ㆍ 공급계약체결")
    assert pre == ["기재정정", "첨부추가"]
    assert body == "단일판매·공급계약체결"


def test_mgmt_dispute_flag():
    assert DT.tag_of("소송등의제기ㆍ신청(경영권분쟁소송)")[2]["mgmt_dispute"] is True
    assert DT.tag_of("소송등의제기ㆍ신청(일정금액이상의청구)")[2]["mgmt_dispute"] is False


# §3-3 표 순서 = 코드 순서(t = 1..7)
PREREG = Path(__file__).resolve().parents[1] / "docs" / "prereg_2026-09-26_dart_disclosure_events.md"


def test_tag_order_matches_prereg_table():
    assert [t for t, _, _ in DT.TAG_TABLE] == list(range(1, 8))
    assert DT.TAGS == ["유상증자", "CB/BW/EB", "자기주식취득", "공급계약", "최대주주변경", "잠정실적", "소송·횡령"]
    if not PREREG.exists():
        pytest.skip("사전등록 문서 없음")
    rows = []
    for line in PREREG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (\d) \| ([^|]+?) \| `(.+?)` \|", line)
        if m:
            rows.append((int(m.group(1)), m.group(2).strip(), m.group(3).replace("\\|", "|")))
    rows = [r for r in rows if r[0] in range(1, 8)][:7]
    assert [r[0] for r in rows] == list(range(1, 8))
    for (t, name, rx), (t2, name2, rx2) in zip(DT.TAG_TABLE, rows):
        assert t == t2
        assert rx == rx2, f"t={t} 정규식이 사전등록 표와 다르다"
        assert name2.startswith(name.split("·")[0].split("/")[0])
