from __future__ import annotations

from backtest.concept_axes.theme_rank import membership as MB

NAMES = {10: "반도체 장비", 20: "밸류업(기업가치 제고)", 30: "SPAC(스팩)", 40: "코로나19(진단키트)",
         50: "여름", 546: "마이코플라스마 폐렴", 547: "새 테마", 600: "지주사"}


def test_excluded_themes_by_name_patterns():
    assert MB.excluded_themes(NAMES) == {20, 30, 40, 50, 600}


def test_eligible_applies_cut_and_exclusion():
    assert MB.eligible_themes(NAMES, n_cut=547) == {10, 546}


def test_full_variant_has_no_cut_and_no_exclusion():
    assert MB.eligible_themes(NAMES, n_cut=None, patterns=()) == set(NAMES)


def test_restrict_keeps_only_given_themes():
    mem = {10: frozenset({"000001"}), 20: frozenset({"000002"})}
    assert MB.restrict(mem, {10}) == {10: frozenset({"000001"})}
