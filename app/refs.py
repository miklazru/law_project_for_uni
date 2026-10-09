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


# ---------- Раскрытие диапазонов (ответ препода: «разворачивать») ----------
# Буквы подпунктов в юр. практике: без ё, й, ъ, ы, ь.
_LETTERS = "абвгдежзиклмнопрстуфхцчшщэюя"
_RANGE = re.compile(r"^\s*([0-9.]+|[а-я])\s*[-–—]\s*([0-9.]+|[а-я])\s*$", re.IGNORECASE)


def expand_range(value: str) -> List[str]:
    """«43.2-6» -> 43.2 … 43.6; «43.2-43.6» -> то же; «1-3» -> 1, 2, 3; «а-в» -> а, б, в.

    Если строка не похожа на диапазон или он некорректен — возвращает [value].
    """
    m = _RANGE.match(value)
    if not m:
        return [value]
    left, right = m.group(1).lower(), m.group(2).lower()
    if left in _LETTERS and right in _LETTERS:
        i, j = _LETTERS.index(left), _LETTERS.index(right)
        return list(_LETTERS[i:j + 1]) if i <= j else [value]
    if not (left.replace(".", "").isdigit() and right.replace(".", "").isdigit()):
        return [value]
    head, _, last = left.rpartition(".")
    # «43.2-6»: правая часть короче -> подставляем общий префикс; «43.2-43.6»: убираем префикс
    if right.startswith(head + ".") and head:
        right = right[len(head) + 1:]
    if "." in right or not last.isdigit() or not right.isdigit():
        return [value]
    a, b = int(last), int(right)
    if a > b or b - a > 50:  # защита от мусора вида «1-2024»
        return [value]
    prefix = head + "." if head else ""
    return [f"{prefix}{k}" for k in range(a, b + 1)]
