# -*- coding: utf-8 -*-
"""Юнит-тесты find_refs: структура ст./п./пп./ч. без привязки к закону."""
from app.refs import find_refs


def _refs(text):
    return [
        (r.articles, r.points, r.subpoints)
        for r in find_refs(text)
    ]


def test_parts_go_into_points():
    assert _refs("ч. 1 ст. 56 ГПК") == [(["56"], ["1"], [])]
    assert _refs("части 2 статьи 4 закона") == [(["4"], ["2"], [])]
    assert _refs("ч.1 ст.20.25 КоАП") == [(["20.25"], ["1"], [])]


def test_enumerations():
    assert _refs("ст. 15, 1064 ГК") == [(["15", "1064"], [], [])]
    assert _refs("ст.ст. 303, 304 УПК") == [(["303", "304"], [], [])]
    assert _refs("статей 284, 286 ГК") == [(["284", "286"], [], [])]
    assert _refs("пп. 1, 2 и 3 п. 2 ст. 3 НК") == [(["3"], ["2"], ["1", "2", "3"])]
    assert _refs("п.п. «а,в,г» ч. 2 ст. 126 УК") == [
        (["126"], ["2"], ["а", "в", "г"])
    ]
    assert _refs("ч.ч. 1 и 2 ст. 255 УПК") == [(["255"], ["1", "2"], [])]


def test_ranges():
    assert _refs("ст. 307-309 УПК") == [(["307", "308", "309"], [], [])]
    assert _refs("статьями 390.14-390.16 ГПК") == [
        (["390.14", "390.15", "390.16"], [], [])
    ]
    assert _refs("пп. а-в п. 1 ст. 5") == [(["5"], ["1"], ["а", "б", "в"])]


def test_refs_without_article():
    assert _refs("п. 10 АПК РФ") == [([], ["10"], [])]
    assert _refs("пункты 1 и 2 Указа Президента") == [([], ["1", "2"], [])]


def test_reverse_order():
    assert _refs("статья 5 пункт 3 ГК") == [(["5"], ["3"], [])]
    assert _refs("ст. 10 п. 2 ГК") == [(["10"], ["2"], [])]


def test_quoted_letters():
    assert _refs("пп. «б» п. 1 ст. 5") == [(["5"], ["1"], ["б"])]
    assert _refs('пункт "о" статьи 71') == [(["71"], ["о"], [])]


def test_typos_and_sticky():
    assert _refs("стаья 12 ТК") == [(["12"], [], [])]
    assert _refs("ст.374 НК") == [(["374"], [], [])]
    assert _refs("п.2ст.10 ГК") == [(["10"], ["2"], [])]


def test_bug_po_st_no_point_o():
    """«по ст. 151» не должно давать пункт «о»."""
    refs = find_refs("по ст. 151 ГК")
    assert len(refs) == 1
    assert refs[0].articles == ["151"]
    assert refs[0].points == []
    assert refs[0].subpoints == []


def test_bug_statey_osobennoy_no_article_y():
    """«статьей Особенной части» не должно давать статью «й»."""
    assert _refs("статьей Особенной части УК РФ") == []


def test_hierarchy_punkt_chast_statya():
    assert _refs("пунктом 2 части первой статьи 81 ТК") == [
        (["81"], ["1"], ["2"])
    ]
    assert _refs("пунктами 2, 11 части 1 статьи 12") == [
        (["12"], ["1"], ["2", "11"])
    ]
    assert _refs("п. 1.1 ч. 10 ст. 109 УПК") == [
        (["109"], ["10"], ["1.1"])
    ]


def test_hierarchy_subpunkt_drops_chast():
    assert _refs("подпункт «д» пункта 6 части первой статьи 81 ТК") == [
        (["81"], ["6"], ["д"])
    ]


def test_combined_list_each_of_articles():
    assert _refs("пункты 1 и 2 каждой из статей 5 и 6 НК") == [
        (["5", "6"], ["1", "2"], [])
    ]


def test_multiple_citations_in_sentence():
    text = (
        "п.п. «а,в,г,з» ч. 2 ст. 126, ч. 2 ст. 162, "
        "п. «б» ч. 3 ст. 163 УК РФ"
    )
    assert _refs(text) == [
        (["126"], ["2"], ["а", "в", "г", "з"]),
        (["162"], ["2"], []),
        (["163"], ["3"], ["б"]),
    ]


def test_preposition_v_between_segments():
    from app.pipeline import detect
    t = "в подпунктах а, б и с пункта 3.345, 23 в статье 66 НК РФ"
    got = {(l.article, l.point_article, l.subpoint_article) for l in detect(t)}
    assert got == {("66", p, s) for p in ("3.345", "23") for s in ("а", "б", "с")}
