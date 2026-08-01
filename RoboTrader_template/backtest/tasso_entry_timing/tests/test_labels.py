import json
from pathlib import Path

LABELS = json.loads((Path(__file__).parent.parent / "labels" / "labels.json").read_text(encoding="utf-8"))


def test_grade1_samsung_levels_are_evenly_spaced():
    s = [g for g in LABELS["grade1"] if g["name"] == "삼성전자"][0]
    lv = s["levels"]
    gaps = [lv[i] - lv[i + 1] for i in range(4)]
    assert max(gaps) - min(gaps) < 5, gaps


def test_grade1_danal_start_is_not_the_low():
    d = [g for g in LABELS["grade1"] if g["name"] == "다날"][0]
    assert d["start"] == 3930          # 최저 3805 와 다름 — (a)변형 반증 근거


def test_reported_returns_are_net_of_cost():
    """그의 표기 수익률은 gross 보다 0.2~0.35%p 낮다 = 비용 차감 후."""
    gaps = []
    for stock in LABELS["grade2"]:
        for f in stock.get("fills", []):
            if not f.get("buy") or not f.get("sell") or f.get("pct") is None:
                continue
            gross = (f["sell"] - f["buy"]) / f["buy"] * 100
            gaps.append(gross - f["pct"])
    assert len(gaps) >= 20, f"판독된 체결이 너무 적다: {len(gaps)}"
    assert 0.15 < sum(gaps) / len(gaps) < 0.40, sum(gaps) / len(gaps)
