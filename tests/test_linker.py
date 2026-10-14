"""Тесты линкера (роль 5). Ссылки и законы задаём вручную, чтобы не зависеть от ролей 3–4."""
from app.linker import link
from app.schemas import LawMention, RefMention

GK, UPK, ZOZPP = 5, 12, 984
CODEX = frozenset({GK, UPK})


def ref(text, frag, art=None, pnt=None, sub=None, nth=0):
    start = -1
    for _ in range(nth + 1):
        start = text.index(frag, start + 1)
    return RefMention(start, start + len(frag), art or [], pnt or [], sub or [])


def law(text, frag, law_id, nth=0):
    start = -1
    for _ in range(nth + 1):
        start = text.index(frag, start + 1)
    return LawMention(start, start + len(frag), law_id)


def tuples(links):
    return [(l.law_id, l.article, l.point_article, l.subpoint_article) for l in links]


def test_simple_right():
    t = "согласно п. 2 ст. 10 ГК РФ"
    out = link([ref(t, "п. 2 ст. 10", ["10"], ["2"])], [law(t, "ГК РФ", GK)], t, CODEX)
    assert tuples(out) == [(GK, "10", "2", None)]


def test_long_chain_reaches_law():
    t = "ст.389.15, 389.18, 389.20, 389.28, 389.33, 389.35 УПК РФ"
    refs = [ref(t, "ст.389.15", ["389.15"])] + [ref(t, v, [v]) for v in
                                                 ["389.18", "389.20", "389.28", "389.33", "389.35"]]
    out = link(refs, [law(t, "УПК РФ", UPK)], t, CODEX)
    assert {x[0] for x in tuples(out)} == {UPK} and len(out) == 6


def test_anaphora_nastoyashchego_kodeksa():
    t = "по ГК РФ. Моральный вред определяется ст. 151 настоящего Кодекса."
    out = link([ref(t, "ст. 151", ["151"])], [law(t, "ГК РФ", GK)], t, CODEX)
    assert tuples(out) == [(GK, "151", None, None)]


def test_anaphora_ukazannogo_zakona_picks_law_not_codex():
    t = ("По ГК РФ и Закону «О защите прав потребителей». "
         "Согласно ч. 1 ст. 16 указанного Закона условия ничтожны.")
    laws = [law(t, "ГК РФ", GK), law(t, "Закону «О защите прав потребителей»", ZOZPP)]
    out = link([ref(t, "ч. 1 ст. 16", ["16"], ["1"])], laws, t, CODEX)
    assert tuples(out) == [(ZOZPP, "16", "1", None)]


def test_bare_kodeks():
    t = "Трудовой кодекс (ТК РФ). Выплаты по статье 139 Кодекса производятся"
    out = link([ref(t, "статье 139", ["139"])], [law(t, "ТК РФ", 10)], t, CODEX | {10})
    assert tuples(out) == [(10, "139", None, None)]


def test_period_after_number_and_i_dr():
    t = "статьи 28.2. КоАП РФ; см. ст.48 и др. ГК РФ"
    out = link([ref(t, "статьи 28.2", ["28.2"]), ref(t, "ст.48", ["48"])],
               [law(t, "КоАП РФ", 17), law(t, "ГК РФ", GK)], t, CODEX)
    assert tuples(out) == [(17, "28.2", None, None), (GK, "48", None, None)]


def test_no_law_across_sentence():
    t = "Смотри ст. 5 договора аренды. Гражданский кодекс тут ни при чём."
    out = link([ref(t, "ст. 5", ["5"])], [law(t, "Гражданский кодекс", GK)], t, CODEX)
    assert out == []


def test_article_must_start_with_digit():
    t = "соответствующей статьей Особенной части УК РФ"
    out = link([ref(t, "статьей О", ["й"])], [law(t, "УК РФ", 13)], t, CODEX)
    assert out == []


def test_dedup():
    t = "ст. 10 ГК РФ ... и снова ст. 10 ГК РФ"
    out = link([ref(t, "ст. 10", ["10"]), ref(t, "ст. 10", ["10"], nth=1)],
               [law(t, "ГК РФ", GK), law(t, "ГК РФ", GK, nth=1)], t, CODEX)
    assert tuples(out) == [(GK, "10", None, None)]


def test_cartesian_product():
    t = "пп. 1, 2 п. 3 ст. 4 ГК РФ"
    out = link([ref(t, "пп. 1, 2 п. 3 ст. 4", ["4"], ["3"], ["1", "2"])],
               [law(t, "ГК РФ", GK)], t, CODEX)
    assert tuples(out) == [(GK, "4", "3", "1"), (GK, "4", "3", "2")]


def test_near_does_not_jump_over_other_ref():
    t = "см. п. 3 договора, в ст. 10 ГК РФ"
    out = link([ref(t, "п. 3", None, ["3"]), ref(t, "ст. 10", ["10"])],
               [law(t, "ГК РФ", GK)], t, CODEX)
    assert tuples(out) == [(GK, "10", None, None)]
