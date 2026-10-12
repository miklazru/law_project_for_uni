"""РОЛЬ 5 — связывание ссылок с законами.

Для каждой RefMention (ст./п./пп., уже разобранные ролью 4) ищем закон, к которому
она относится, и раскрываем её в список LawLink.

Правила, по порядку:
  1. Закон справа, а между ссылкой и законом только «связки»: другие ссылки
     («ст. 389.15, 389.18, … 389.35 УПК РФ»), запятые, скобки, «и», «или», «а также»…
     Длина промежутка после вычёркивания других ссылок ограничена.
  2. Анафора справа: «ст. 151 настоящего Кодекса», «п. 2 ст. 6 указанного Федерального
     закона», «статьей 139 Кодекса» -> последний закон того же вида (кодекс / закон),
     упомянутый в тексте ДО ссылки.
  3. Запасной вариант: закон справа совсем рядом (≤ NEAR_GAP символов) и без конца
     предложения между ними.
  Иначе ссылка выбрасывается: метрика — accuracy по текстам, лишняя ссылка
  обнуляет текст, поэтому сомнительное лучше пропустить.

Дополнительно:
  - статья обязана начинаться с цифры (защита от мусора парсера: «статьей Особенной»);
  - одинаковые ссылки в ответе схлопываются (в разметке дублей нет).
"""
import re
from itertools import product
from typing import FrozenSet, List, Optional

from app.schemas import LawLink, LawMention, RefMention

MAX_GAP = 60     # макс. длина «связок» между ссылкой и законом после вычёркивания других ссылок
NEAR_GAP = 25    # запасной вариант: закон в пределах стольких символов справа

# Что может стоять между ссылкой и законом, кроме других ссылок
_GLUE = re.compile(
    r"^\.?"  # точка сразу после номера: «статьи 28.2. КоАП РФ»
    r"(?:[\s,;:()\-–—/\"«»]"
    r"|\b(?:и\s+др\.?|и\s+други\w*|и\s+след\w*\.?|и\s+далее"
    r"|и|или|а\s+также|также|либо|в|во|из|соответственно)(?!\w))*$",
    re.IGNORECASE,
)

# Анафора сразу после ссылки
_ANAPHORA = re.compile(
    r"^[\s,]*(?:(?:настоящ|указанн|названн|вышеуказанн|вышеназванн|приведенн|приведённ|упомянут"
    r"|данн|соответствующ)\w*|эт(?:ого|ой|им|ом)\s+же|того\s+же|той\s+же)\s+"
    r"(?:федеральн\w*\s+)?(?P<kind>кодекс|закон)\w*",
    re.IGNORECASE,
)
# «статьей 139 Кодекса» — голое «Кодекс» с большой буквы, которое роль 3 не распознала
_BARE_CODEX = re.compile(r"^[\s,]*Кодекс\w*\b")

# Конец предложения: точка/!/? и дальше заглавная буква
_SENT_END = re.compile(r"[.!?]\s+[А-ЯЁA-Z]")


def _art_ok(article: Optional[str]) -> bool:
    return article is None or (bool(article) and article[0].isdigit())


def _masked_gap(text: str, start: int, end: int, refs: List[RefMention]) -> str:
    """Текст между start и end, из которого вычеркнуты другие ссылки."""
    chars = list(text[start:end])
    for r in refs:
        a, b = max(r.start, start), min(r.end, end)
        for i in range(a - start, b - start):
            chars[i] = " "
    return "".join(chars)


def _resolve_right(ref, refs, laws, text) -> Optional[int]:
    nxt = next((l for l in laws if l.start >= ref.end), None)
    if nxt is None:
        return None
    gap = _masked_gap(text, ref.end, nxt.start, refs)
    if len(gap.strip()) <= MAX_GAP and _GLUE.match(gap):
        return nxt.law_id
    return None


def _resolve_anaphora(ref, refs, laws, text, codex_ids) -> Optional[int]:
    # пропускаем идущие подряд ссылки: «ст. 15, 16 настоящего Кодекса»
    pos = ref.end
    for r in refs:
        if r.start >= pos and _GLUE.match(text[pos:r.start]) and r.start - pos <= 5:
            pos = r.end
    tail = text[pos:pos + 80]
    m = _ANAPHORA.match(tail)
    if m:
        want_codex = m.group("kind").lower() == "кодекс"
    elif _BARE_CODEX.match(tail):
        want_codex = True
    else:
        return None
    before = [l for l in laws if l.end <= ref.start]
    for l in reversed(before):
        if (l.law_id in codex_ids) == want_codex:
            return l.law_id
    return None


def _resolve_near(ref, laws, text) -> Optional[int]:
    nxt = next((l for l in laws if l.start >= ref.end), None)
    if nxt is None or nxt.start - ref.end > NEAR_GAP:
        return None
    gap = text[ref.end:nxt.start + 1]
    if _SENT_END.search(gap[1:] if gap.startswith(".") else gap):
        return None
    return nxt.law_id


def link(refs: List[RefMention], laws: List[LawMention], text: str = "",
         codex_ids: FrozenSet[int] = frozenset()) -> List[LawLink]:
    refs = sorted(refs, key=lambda r: r.start)
    laws = sorted(laws, key=lambda l: l.start)
    links: List[LawLink] = []
    seen = set()
    for ref in refs:
        law_id = None
        if text:
            law_id = (_resolve_right(ref, refs, laws, text)
                      or _resolve_anaphora(ref, refs, laws, text, codex_ids)
                      or _resolve_near(ref, laws, text))
        else:  # обратная совместимость: без текста — ближайший закон справа
            nxt = next((l for l in laws if 0 <= l.start - ref.end <= MAX_GAP), None)
            law_id = nxt.law_id if nxt else None
        if law_id is None:
            continue
        # декартово произведение: пп. 1, 2 п. 3 -> две ссылки
        for art, pnt, sub in product(ref.articles or [None],
                                     ref.points or [None],
                                     ref.subpoints or [None]):
            if not _art_ok(art):
                continue
            key = (law_id, art, pnt, sub)
            if key in seen:
                continue
            seen.add(key)
            links.append(LawLink(law_id=law_id, article=art,
                                 point_article=pnt, subpoint_article=sub))
    return links
