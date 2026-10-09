"""РОЛЬ 4 — парсер структуры ссылки (статья / пункт / подпункт).

Сейчас НАИВНАЯ заглушка: ловит цепочки вида «пп. 1 п. 2 ст. 3» с одиночными
значениями. Не умеет перечисления, диапазоны, «часть», обратный порядок,
опечатки. Заменить своей реализацией, сохранив сигнатуру.
"""
import re
from typing import List

from app.schemas import RefMention

_VAL = r"([0-9]+(?:\.[0-9]+)*|[а-я](?![а-яё]))"
_SUB = rf"(?<![а-яё])(?:пп\.?|подпункт[а-я]*)\s*{_VAL}"
_PNT = rf"(?<![а-яё])(?:п\.?|пункт[а-я]*)\s*{_VAL}"
_ART = rf"(?<![а-яё])(?:ст\.?|стать[а-я]*)\s*{_VAL}"

_CHAIN = re.compile(
    rf"(?:{_SUB}\s*,?\s*)?(?:{_PNT}\s*,?\s*)?{_ART}",
    re.IGNORECASE,
)


def find_refs(text: str) -> List[RefMention]:
    out: List[RefMention] = []
    for m in _CHAIN.finditer(text):
        sub, pnt, art = m.group(1), m.group(2), m.group(3)
        out.append(RefMention(
            start=m.start(), end=m.end(),
            articles=[art] if art else [],
            points=[pnt] if pnt else [],
            subpoints=[sub] if sub else [],
        ))
    return out
