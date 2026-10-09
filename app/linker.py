"""РОЛЬ 5 — связывание ссылок с законами.

Сейчас НАИВНАЯ заглушка: ссылке достаётся ближайший закон, начинающийся
справа не дальше MAX_GAP символов. Ссылки без закона выбрасываются
(TODO: уточнить у препода, не нужен ли law_id=None).
"""
from itertools import product
from typing import List

from app.schemas import LawLink, LawMention, RefMention

MAX_GAP = 40


def link(refs: List[RefMention], laws: List[LawMention]) -> List[LawLink]:
    links: List[LawLink] = []
    for ref in refs:
        law = next((l for l in laws if 0 <= l.start - ref.end <= MAX_GAP), None)
        if law is None:
            continue
        # декартово произведение: пп. 1, 2 п. 3 -> две ссылки
        for art, pnt, sub in product(ref.articles or [None],
                                     ref.points or [None],
                                     ref.subpoints or [None]):
            links.append(LawLink(law_id=law.law_id, article=art,
                                 point_article=pnt, subpoint_article=sub))
    return links
