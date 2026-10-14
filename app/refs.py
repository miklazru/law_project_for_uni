"""РОЛЬ 4 — парсер структуры ссылки (статья / пункт / подпункт / часть)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.laws import normalize_chars
from app.schemas import RefMention

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


# ---------------------------------------------------------------- markers / values

Kind = str  # 'art' | 'pnt' | 'part' | 'sub'

_ORDINALS = {
    "перв": "1", "первая": "1", "первой": "1", "первую": "1", "первое": "1",
    "первым": "1", "первом": "1", "первый": "1", "первою": "1",
    "втор": "2", "вторая": "2", "второй": "2", "вторую": "2", "второе": "2",
    "вторым": "2", "втором": "2", "второю": "2",
    "трет": "3", "третья": "3", "третьей": "3", "третью": "3", "третье": "3",
    "третьим": "3", "третьем": "3", "третий": "3", "третьею": "3",
    "четверт": "4", "четвертая": "4", "четвертой": "4", "четвертую": "4",
    "четвертое": "4", "четвертым": "4", "четвертом": "4", "четвертый": "4",
    "пят": "5", "пятая": "5", "пятой": "5", "пятую": "5", "пятое": "5",
    "пятым": "5", "пятом": "5", "пятый": "5",
    "шест": "6", "шестая": "6", "шестой": "6", "шестую": "6", "шестое": "6",
    "шестым": "6", "шестом": "6", "шестой": "6", "шестый": "6",
    "седьм": "7", "седьмая": "7", "седьмой": "7", "седьмую": "7", "седьмое": "7",
    "седьмым": "7", "седьмом": "7",
    "восьм": "8", "восьмая": "8", "восьмой": "8", "восьмую": "8", "восьмое": "8",
    "восьмым": "8", "восьмом": "8",
    "девят": "9", "девятая": "9", "девятой": "9", "девятую": "9", "девятое": "9",
    "девятым": "9", "девятом": "9", "девятый": "9",
    "десят": "10", "десятая": "10", "десятой": "10", "десятую": "10",
    "десятое": "10", "десятым": "10", "десятом": "10", "десятый": "10",
}

# Стем-подобные ключи (начало слова) для склонений «первой/первую/…»
_ORDINAL_STEMS = (
    ("перв", "1"), ("втор", "2"), ("трет", "3"), ("четверт", "4"),
    ("пят", "5"), ("шест", "6"), ("седьм", "7"), ("восьм", "8"),
    ("девят", "9"), ("десят", "10"),
)


def _ordinal_to_num(word: str) -> Optional[str]:
    w = word.lower()
    if w in _ORDINALS:
        return _ORDINALS[w]
    for stem, num in _ORDINAL_STEMS:
        if w.startswith(stem) and len(w) <= len(stem) + 4:
            return num
    return None


# Маркеры: длинные/опечатки раньше коротких аббревиатур.
# art: ст.ст / ст / статья… / опечатки стаья/стаей
# sub: пп / п.п / подпункт… / подпукт
# part: ч.ч / ч. / часть… / чсат  (часть → points в схеме)
# pnt: пункт… / опечатки / п. / голый п перед цифрой
# После цифры тоже можно (склейка «п.2ст.10»); внутри слова — нельзя.
_MARKER_RE = re.compile(
    r"(?<![а-яё])(?:"
    r"(?P<sub>"
    r"подпунк[т]?[а-я]*|подпукт[а-я]*|"
    r"п\s*\.\s*п\s*\.?|пп\.?"
    r")"
    r"|(?P<art>"
    r"стать[а-я]*|статей|стаья[а-я]*|стаей[а-я]*|статьями|статьям|статьях|"
    r"ст\s*\.\s*ст\s*\.?|ст\.ст\.?|ст\s*\.\s*|ст(?=[\d.«\"])"
    r")"
    r"|(?P<part>"
    r"част[а-я]*|чсат[а-я]*|"
    r"ч\s*\.\s*ч\s*\.?|ч\.ч\.?|ч\s*\.(?!\s*[а-я]{2})|ч(?=\d)"
    r")"
    r"|(?P<pnt>"
    r"пункт[а-я]*|пунта[а-я]*|пнукт[а-я]*|пунк[а-я]*|"
    r"п\s*\.(?!\s*[а-я]{2})|п(?=\d)"
    r")"
    r")",
    re.IGNORECASE,
)

_NUM = r"[0-9]+(?:\.[0-9]+)*"
_LETTER = r"[а-яё]"
_QUOTED_LETTER = rf"[«\"„]\s*{_LETTER}\s*[»\"“]"
_QUOTED_LIST = rf"[«\"„]\s*{_LETTER}\s*(?:[,;]\s*{_LETTER}\s*)+[»\"“]"
_ORD_WORD = (
    r"(?:перв|втор|трет|четверт|пят|шест|седьм|восьм|девят|десят)[а-я]*"
)

# Одно значение (число / буква / порядковое / диапазон).
# Голая буква НЕ берётся, если дальше «.» — это начало маркера (п. / ч.).
_ATOM = re.compile(
    rf"(?:"
    rf"{_QUOTED_LIST}"
    rf"|{_QUOTED_LETTER}"
    rf"|{_NUM}\s*[-–—]\s*{_NUM}"
    rf"|{_LETTER}\s*[-–—]\s*{_LETTER}"
    rf"|{_NUM}"
    rf"|{_ORD_WORD}"
    rf"|{_LETTER}(?![а-яё.])"
    rf")",
    re.IGNORECASE,
)

# Разделители внутри списка значений
_SEP = re.compile(r"\s*[,;]\s*|\s+и\s+|\s*", re.IGNORECASE)

# Между сегментами одной ссылки: пробелы/точки/запятые и «каждой из»
# (точка — для склейки «п.2 ч.1. ст. 81»)
_BETWEEN_OK = re.compile(
    r"^[\s.,;]*(?:(?:каждой\s+из|во?)[\s.,;]+)?$",  # «пункта 3 в статье 66»
    re.IGNORECASE,
)

# «пунктом 3 настоящей статьи» / «частью 1.1 этой статьи»
_INHERIT_ART = re.compile(
    r"^\s*(?:настоящей|этой(?:\s+же)?)\s+статьи\b",
    re.IGNORECASE,
)

# «части второй Гражданского кодекса» — не структурная «часть» статьи
_CODE_PART = re.compile(
    r"^\s*(?:гражданского|уголовного|налогового|семейного|трудового|"
    r"земельного|жилищного|водного|воздушного|лесного|градостроительного|"
    r"настоящего|особенной|общей)\s+кодекс",
    re.IGNORECASE,
)


@dataclass
class Segment:
    kind: Kind
    values: List[str]
    start: int
    end: int


@dataclass
class _Citation:
    start: int
    end: int
    arts: List[str] = field(default_factory=list)
    pnts: List[str] = field(default_factory=list)   # пункт
    parts: List[str] = field(default_factory=list)  # часть
    subs: List[str] = field(default_factory=list)


def _expand_atom(raw: str) -> List[str]:
    s = raw.strip().lower()
    # «а,в,г» / "а, в, г"
    qm = re.match(r"[«\"„]\s*([а-яё](?:\s*[,;]\s*[а-яё])+)\s*[»\"“]$", s)
    if qm:
        parts = re.split(r"\s*[,;]\s*", qm.group(1))
        return [p for p in parts if len(p) == 1 and p in _LETTERS]
    # «б» / "о"
    qm = re.match(r"[«\"„]\s*([а-яё])\s*[»\"“]$", s)
    if qm:
        ch = qm.group(1)
        return [ch] if ch in _LETTERS or ch.isalpha() else []
    # диапазон
    if re.search(r"[-–—]", s):
        compact = re.sub(r"\s+", "", s)
        return expand_range(compact)
    # порядковое
    ord_n = _ordinal_to_num(s)
    if ord_n:
        return [ord_n]
    # число
    if re.fullmatch(_NUM, s):
        return [s]
    # одна буква (только для п/пп; статья отфильтрует)
    if len(s) == 1 and s.isalpha():
        # «й» из окончаний не считаем валидной буквой подпункта в юр. практике
        if s in _LETTERS:
            return [s]
        return []
    return []


def _parse_values(text: str, pos: int, *, allow_letters: bool) -> Tuple[List[str], int]:
    """С позиции pos читает список значений. Возвращает (values, end_pos)."""
    n = len(text)
    # пропуск пробелов/точек после маркера (ст.374 / п.2)
    i = pos
    while i < n and text[i] in " \t\n\r.:":
        # точка после маркера уже съедена; лишние точки перед числом (п.1.1.) — часть числа
        if text[i] == "." and i + 1 < n and text[i + 1].isdigit():
            break
        if text[i] == "." and i + 1 < n and text[i + 1] in "«\"„":
            i += 1
            break
        if text[i] == ".":
            i += 1
            continue
        if text[i] in " \t\n\r:":
            i += 1
            continue
        break

    values: List[str] = []
    last_end = i
    expect_sep = False

    while i < n:
        if expect_sep:
            # запятая / «и» / пробел перед следующим атомом
            msep = re.match(
                r"(?:\s*[,;]\s*|\s+и\s+(?:\(\s*или\s*\)\s*)?|\s+)",
                text[i:],
            )
            if not msep:
                break
            sep = msep.group(0)
            j = i + len(sep)
            if not _ATOM.match(text, j):
                break
            i = j
            expect_sep = False
            continue

        m = _ATOM.match(text, i)
        if not m:
            break
        raw = m.group(0)
        # одиночная буква без кавычек — только если allow_letters и не начало слова длиннее
        if re.fullmatch(r"[а-яё]", raw.lower()):
            if not allow_letters:
                break
            # не «о» из «по» и т.п. — атом уже с (?![а-яё])
        expanded = _expand_atom(raw)
        if not expanded:
            break
        if not allow_letters:
            expanded = [v for v in expanded if re.fullmatch(_NUM, v)]
            if not expanded:
                break
        else:
            cleaned = []
            for v in expanded:
                if re.fullmatch(_NUM, v):
                    cleaned.append(v)
                elif len(v) == 1 and v.isalpha() and v in _LETTERS:
                    cleaned.append(v)
            if not cleaned:
                break
            expanded = cleaned
            # не смешиваем цифры и голые буквы в одном списке
            # (иначе «пп. 1, 2 п. 3» съедает «п» как значение)
            bare_letter = bool(re.fullmatch(r"[а-яё]", raw.lower()))
            if values:
                prev_num = all(re.fullmatch(_NUM, v) for v in values)
                prev_let = all(len(v) == 1 and v.isalpha() for v in values)
                now_num = all(re.fullmatch(_NUM, v) for v in expanded)
                now_let = all(len(v) == 1 and v.isalpha() for v in expanded)
                if prev_num and now_let and bare_letter:
                    break
                if prev_let and now_num:
                    break
                if prev_num and now_let and not bare_letter:
                    # «а,в» в кавычках после чисел — крайне редко; не берём
                    break
        values.extend(expanded)
        last_end = m.end()
        i = last_end
        expect_sep = True

    if not values:
        return [], pos
    return values, last_end


def _kind_of(m: re.Match) -> Kind:
    if m.group("sub"):
        return "sub"
    if m.group("art"):
        return "art"
    if m.group("part"):
        return "part"
    return "pnt"


def _find_segments(text: str) -> List[Segment]:
    out: List[Segment] = []
    for m in _MARKER_RE.finditer(text):
        kind = _kind_of(m)
        allow_letters = kind in ("pnt", "part", "sub")
        # для статьи буквы запрещены; для части порядковые — числа через ordinal
        values, end = _parse_values(text, m.end(), allow_letters=allow_letters)
        if not values:
            continue
        # статья: только числа
        if kind == "art":
            values = [v for v in values if re.fullmatch(_NUM, v)]
            if not values:
                continue
        # часть: только числа (порядковые уже раскрыты)
        if kind == "part":
            values = [v for v in values if re.fullmatch(_NUM, v)]
            if not values:
                continue
        out.append(Segment(kind=kind, values=values, start=m.start(), end=end))
    return out


def _gap_ok(text: str, a_end: int, b_start: int) -> bool:
    if b_start < a_end:
        return False
    gap = text[a_end:b_start]
    return bool(_BETWEEN_OK.match(gap))


def _group_segments(segments: List[Segment], text: str) -> List[_Citation]:
    if not segments:
        return []
    cits: List[_Citation] = []
    cur: Optional[_Citation] = None
    seen: set = set()

    def flush():
        nonlocal cur, seen
        if cur is not None and (cur.arts or cur.pnts or cur.parts or cur.subs):
            cits.append(cur)
        cur = None
        seen = set()

    for seg in segments:
        if cur is None:
            cur = _Citation(start=seg.start, end=seg.end)
            seen = set()
            _apply_seg(cur, seg)
            seen.add(seg.kind)
            continue

        # новый сегмент того же типа → отдельная ссылка (кроме продолжения списка — уже в одном Segment)
        gap = text[cur.end:seg.start]

        if seg.kind in seen:
            # «ч.1,ч.3 ст.80» — повтор part/pnt/sub через запятую до статьи
            if (
                seg.kind in ("part", "pnt", "sub")
                and "art" not in seen
                and re.fullmatch(r"\s*,\s*", gap or "")
            ):
                _apply_seg(cur, seg)
                cur.end = seg.end
                continue
            flush()
            cur = _Citation(start=seg.start, end=seg.end)
            seen = set()
            _apply_seg(cur, seg)
            seen.add(seg.kind)
            continue

        if not _gap_ok(text, cur.end, seg.start):
            flush()
            cur = _Citation(start=seg.start, end=seg.end)
            seen = set()
            _apply_seg(cur, seg)
            seen.add(seg.kind)
            continue

        # «ч. 2 ст. 126, ч. 2 ст. 162» — после статьи запятая начинает новую ссылку.
        # Запятая до статьи («п. 1.1 ч. 10, ст. 109») допустима.
        if cur.arts and re.search(r"[,;]", gap):
            flush()
            cur = _Citation(start=seg.start, end=seg.end)
            seen = set()
            _apply_seg(cur, seg)
            seen.add(seg.kind)
            continue

        _apply_seg(cur, seg)
        cur.end = seg.end
        seen.add(seg.kind)

    flush()
    return cits


def _apply_seg(cit: _Citation, seg: Segment) -> None:
    if seg.kind == "art":
        cit.arts.extend(seg.values)
    elif seg.kind == "pnt":
        cit.pnts.extend(seg.values)
    elif seg.kind == "part":
        cit.parts.extend(seg.values)
    elif seg.kind == "sub":
        cit.subs.extend(seg.values)


def _map_hierarchy(cit: _Citation) -> RefMention:
    """4 юр. уровня → 3 поля схемы (см. ТЗ)."""
    articles = list(cit.arts)
    points: List[str] = []
    subpoints: List[str] = []

    has_sub = bool(cit.subs)
    has_pnt = bool(cit.pnts)
    has_part = bool(cit.parts)

    if has_sub:
        subpoints = list(cit.subs)
        if has_pnt:
            points = list(cit.pnts)
            # DROP часть
        elif has_part:
            points = list(cit.parts)
        # иначе points пусто
    elif has_pnt and has_part:
        points = list(cit.parts)
        subpoints = list(cit.pnts)
    elif has_pnt:
        points = list(cit.pnts)
    elif has_part:
        points = list(cit.parts)

    return RefMention(
        start=cit.start,
        end=cit.end,
        articles=articles,
        points=points,
        subpoints=subpoints,
    )


def _should_skip(cit: _Citation, text: str) -> bool:
    """Отбрасывает заведомо ложные срабатывания (точность важнее полноты)."""
    # «части второй Гражданского кодекса» — часть кодекса, не статьи
    if cit.parts and not cit.arts and not cit.pnts and not cit.subs:
        return True
    # «статья 71 Конституции …» — в бенче Конституция не линкуется, а ложно
    # цепляется к следующему ГК в пределах MAX_GAP
    if cit.arts:
        tail = text[cit.end:cit.end + 40]
        if re.match(r"\s*конституци", tail, re.IGNORECASE):
            return True
        if _CODE_PART.match(tail) and not cit.pnts and not cit.subs and not cit.parts:
            # «статьи Особенной части» уже отсекается отсутствием числа;
            # на всякий случай
            pass
    return False


def _inherit_articles(cits: List[_Citation], text: str) -> None:
    """«пунктом 3 настоящей статьи» берёт articles из предыдущей ссылки."""
    last_arts: List[str] = []
    for cit in cits:
        if cit.arts:
            last_arts = list(cit.arts)
            continue
        if not last_arts:
            continue
        if not (cit.pnts or cit.parts or cit.subs):
            continue
        if _INHERIT_ART.match(text[cit.end:cit.end + 40]):
            cit.arts = list(last_arts)


def find_refs(text: str) -> List[RefMention]:
    """Находит структурные упоминания ст./п./пп./ч. в уже нормализуемом тексте.

    Позиции считаются по нормализованной строке (длина = оригиналу).
    """
    low = normalize_chars(text)
    segments = _find_segments(low)
    citations = _group_segments(segments, low)
    _inherit_articles(citations, low)
    citations = [c for c in citations if not _should_skip(c, low)]
    return [_map_hierarchy(c) for c in citations]
