"""РОЛЬ 3 — распознавание закона (law_id).

Как устроено:
  1. Нормализация символов без сдвига позиций: латиница-двойник -> кириллица
     (c/с, p/р, H/Н …), ё -> е, «Ф3» -> «ФЗ», нижний регистр.
  2. Токенизация: слова и числа; даты («07.06.2025», «7 июня 2025 г.») -> один токен.
     Слова стеммятся (Snowball), поэтому склонения совпадают: «Налогового кодекса» ==
     «Налоговый кодекс». «РФ / России / Российской Федерации» -> один токен «рф».
     Слова не из словаря алиасов исправляются нечётким поиском (опечатки).
  3. Поиск, на каждой позиции берём самое длинное совпадение из:
     - trie по всем алиасам из law_aliases.json (+ ручные сокращения: КоАП, ГрК, КАС …);
     - «шапка» акта: <вид акта> + любые из [от <дата>] [№ <номер>] [«название»]
       в любом порядке. Кандидаты пересекаются — так снимается неоднозначность
       «ФЗ №127-ФЗ» (5 законов) по дате или названию;
     - «Закон о банкротстве»: слова после «закон о/об» — подпоследовательность названия;
     - определения из текста: «… (далее — Закон о связи)» и дальше просто «Закон о связи».
  4. Если кандидатов несколько: берём тот, что уже встречался в тексте, иначе
     один из самых цитируемых (_FAMOUS_TITLES), иначе закон с самым коротким названием
     (базовый закон, а не «О внесении изменений»).
  5. Защита от ложных срабатываний: номер/дата, противоречащие базе («ФЗ №20-456»,
     15-ФЗ не той даты) -> закона нет в базе; «№127-ФЗ» без вида акта, «ЖК «Речной»»,
     одиночное «АРЕНДА» в кавычках — не законы.
"""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

import snowballstemmer

from app.schemas import LawMention

# ---------------------------------------------------------------- нормализация символов

# Латиница, похожая на кириллицу. Замена 1:1, длина строки не меняется.
_HOMOGLYPHS = str.maketrans({
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М", "O": "О",
    "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у", "k": "к",
    "Ё": "Е", "ё": "е",
})
_F3 = re.compile(r"(?<![0-9а-яa-z])ф3(?![0-9])")  # «Ф3» с цифрой вместо «ФЗ»


def normalize_chars(text: str) -> str:
    """Нормализует символы, сохраняя длину строки (позиции совпадают с оригиналом)."""
    out = text.translate(_HOMOGLYPHS)
    low = out.lower()
    if len(low) != len(out):  # экзотический юникод, у которого lower() меняет длину
        low = "".join(ch.lower() if len(ch.lower()) == 1 else ch for ch in out)
    return _F3.sub("фз", low)


# ---------------------------------------------------------------- токенизация

_MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
           "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
_YEAR_TAIL = r"(?:\s*(?:г\.|года|г|год)(?![а-я]))?"
_DATE_NUM = re.compile(
    r"(?<![0-9])([0-3]?\d)\s?[./]\s?([01]?\d)\s?[./]\s?((?:19|20)\d\d)(?![0-9])" + _YEAR_TAIL)
_DATE_TXT = re.compile(
    r"(?<![0-9])([0-3]?\d)\s+(январ|феврал|март|апрел|ма|июн|июл|август|сентябр|октябр|ноябр|декабр)"
    r"(?:я|а|ая|е|ь)?\s+((?:19|20)\d\d)(?![0-9])" + _YEAR_TAIL)
_TOKEN = re.compile(r"[a-zа-я]+|[0-9]+")

_stemmer = snowballstemmer.stemmer("russian")


@dataclass
class Token:
    norm: str     # стем слова / число / «@ГГГГ-ММ-ДД» для даты / «рф»
    start: int
    end: int
    raw: str      # слово после normalize_chars, до стемминга


@lru_cache(maxsize=200_000)
def _stem(word: str) -> str:
    if word.isdigit():
        return str(int(word)) if len(word) < 6 else word
    if word == "i":  # римская I в номерах «№2300-I» пишут и как «2300-1»
        return "1"
    if len(word) <= 3:
        return word
    return _stemmer.stemWord(word)


def _find_dates(low: str) -> List[Tuple[int, int, str]]:
    spans = []
    for rx, textual in ((_DATE_NUM, False), (_DATE_TXT, True)):
        for m in rx.finditer(low):
            day = int(m.group(1))
            month = _MONTHS[m.group(2)] if textual else int(m.group(2))
            if 1 <= day <= 31 and 1 <= month <= 12:
                spans.append((m.start(), m.end(), f"@{m.group(3)}-{month:02d}-{day:02d}"))
    spans.sort()
    return spans


def tokenize(low: str, fix=None) -> List[Token]:
    """low — результат normalize_chars. fix(word, stem) -> исправленный стем (нечёткий поиск)."""
    dates = _find_dates(low)
    toks: List[Token] = []
    di = 0
    for m in _TOKEN.finditer(low):
        s = m.start()
        while di < len(dates) and dates[di][1] <= s:
            di += 1
        if di < len(dates) and dates[di][0] <= s < dates[di][1]:
            ds, de, dn = dates[di]
            if not toks or toks[-1].start != ds:
                toks.append(Token(dn, ds, de, low[ds:de]))
            continue
        word = m.group()
        norm = _stem(word)
        if fix is not None and word.isalpha() and len(word) >= 5:
            norm = fix(word, norm)
        toks.append(Token(norm, s, m.end(), word))
    return _canonize(toks, low)


def _canonize(toks: List[Token], low: str) -> List[Token]:
    out: List[Token] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if t.norm == "российск" and nxt is not None and nxt.norm == "федерац":
            out.append(Token("рф", t.start, nxt.end, low[t.start:nxt.end]))
            i += 2
            continue
        if t.norm in ("росс", "россия"):
            out.append(Token("рф", t.start, t.end, t.raw))
        elif t.norm == "основ":  # Snowball: «Основы» -> «осн», но «Основ» -> «основ»
            out.append(Token("осн", t.start, t.end, t.raw))
        elif t.norm in ("n", "no", "номер") and nxt is not None and nxt.norm.isdigit():
            pass  # «N 127-ФЗ», «No 5» — знак номера, как «№»
        else:
            out.append(t)
        i += 1
    return out


# ---------------------------------------------------------------- нечёткий поиск (опечатки)

def _deletes(word: str, depth: int) -> Set[str]:
    res = {word}
    frontier = {word}
    for _ in range(depth):
        frontier = {w[:k] + w[k + 1:] for w in frontier for k in range(len(w))}
        res |= frontier
    return res


def _damerau(a: str, b: str, limit: int) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: List[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


class _Fuzzy:
    """SymSpell: индекс удалений по словарю стемов. Расстояние 1 для стемов от 5 букв,
    2 — от 8 букв. Из равноудалённых кандидатов берём не короче исходного и самый
    частый в алиасах («трудв» -> «трудов», а не «труд»); при полном равенстве не исправляем."""

    def __init__(self, stems: Dict[str, int], words: Dict[str, int]):
        self.vocab = set(stems)
        self.stems = _Speller(stems)
        self.words = _Speller(words)  # целые слова: стеммер режет опечатку слишком коротко
        self.cache: Dict[Tuple[str, str], str] = {}

    def __call__(self, word: str, stem: str) -> str:
        if stem in self.vocab or len(stem) < 5:
            return stem
        hit = self.cache.get((word, stem))
        if hit is not None:
            return hit
        res = self.stems.correct(stem)
        if res is None:
            fixed = self.words.correct(word)
            res = _stem(fixed) if fixed is not None else stem
        if len(self.cache) < 100_000:
            self.cache[word, stem] = res
        return res


class _Speller:
    def __init__(self, freq: Dict[str, int]):
        self.freq = freq
        self.index: Dict[str, Set[str]] = {}
        for w in freq:
            if len(w) < 4 or not w.isalpha():
                continue
            for d in _deletes(w, 2 if len(w) >= 8 else 1):
                self.index.setdefault(d, set()).add(w)

    def correct(self, stem: str) -> Optional[str]:  # stem — стем или целое слово
        if len(stem) < 5:
            return None
        limit = 2 if len(stem) >= 8 else 1
        cands: Set[str] = set()
        for d in _deletes(stem, limit):
            cands |= self.index.get(d, set())
        best, best_key, tie = stem, (limit + 1, False, 0), False
        for c in cands:
            if abs(len(c) - len(stem)) > limit or c[0] != stem[0]:  # первая буква — без опечаток
                continue
            # опечатка чаще съедает букву: кандидат короче стема — в последнюю очередь
            key = (_damerau(stem, c, limit), len(c) < len(stem), -self.freq[c])
            if key < best_key:
                best, best_key, tie = c, key, False
            elif key == best_key:
                tie = True
        return None if tie or best_key[0] > limit else best


# ---------------------------------------------------------------- структура алиасов

FZ, ZRF, UKAZ, RASP, OSN, OTHER = "fz", "zrf", "ukaz", "rasp", "osn", "other"

# Вид акта в тексте (стемы) -> какие виды из базы под него подходят.
_TYPE_PHRASES: Dict[Tuple[str, ...], FrozenSet[str]] = {
    ("федеральн", "закон"): frozenset({FZ}),
    ("фз",): frozenset({FZ}),
    ("закон",): frozenset({FZ, ZRF}),
    ("указ", "президент"): frozenset({UKAZ}),
    ("указ",): frozenset({UKAZ}),
    ("распоряжен", "президент"): frozenset({RASP}),
    ("распоряжен",): frozenset({RASP}),
    ("осн", "законодательств"): frozenset({OSN}),
}
_TYPE_BY_PREFIX = [("федеральный закон", FZ), ("указ президента", UKAZ),
                   ("распоряжение президента", RASP), ("закон российской федерации", ZRF),
                   ("основы законодательства", OSN)]

# Сокращения, которых нет в law_aliases.json. Закон ищется по началу первого алиаса.
_EXTRA_ALIASES = {
    "Кодекс Российской Федерации об административных правонарушениях": [
        "КоАП", "КРФоАП", "КРФобАП", "КРФ об АП", "КоАП РФ", "КоПА РФ", "КоПА"],
    "Градостроительный кодекс": ["ГрК РФ", "ГрК России", "ГрК"],
    "Кодекс административного судопроизводства": ["КАС РФ", "КАС России", "КАС"],
    "Кодекс торгового мореплавания": ["КТМ РФ", "КТМ"],
    "Кодекс внутреннего водного транспорта": ["КВВТ РФ", "КВВТ"],
    "Водный кодекс": ["ВК РФ"],
    "Воздушный кодекс": ["ВзК РФ"],
    "Уголовно-исполнительный кодекс": ["УИК"],
    "Федеральный закон №40-ФЗ": ["Закон об ОСАГО", "ФЗ об ОСАГО"],
    "Федеральный закон №14-ФЗ": ["Закон об ООО", "ФЗ об ООО"],
    "Федеральный закон №208-ФЗ": ["Закон об АО", "ФЗ об АО"],
    "Закон Российской Федерации №2300-I": ["Закон о ЗПП"],
}

# Самые цитируемые законы: при неоднозначном номере («44-ФЗ» — 4 закона в базе) и без
# подсказок в тексте выбираем их. Остальные — по самому короткому названию.
_FAMOUS_TITLES = (
    "о несостоятельности (банкротстве)", "о контрактной системе в сфере закупок",
    "о закупках товаров, работ, услуг отдельными видами",
    "об обязательном страховании гражданской ответственности владельцев транспортных",
    "об акционерных обществах", "об обществах с ограниченной", "о персональных данных",
    "об исполнительном производстве", "о защите конкуренции", "о противодействии легализации",
    "о государственной регистрации недвижимости", "о государственной гражданской службе",
    "об основах охраны здоровья", "о потребительском кредите", "об ипотеке",
    "об участии в долевом строительстве", "о национальной платежной системе", "о рекламе",
    "о лицензировании", "о валютном регулировании", "о рынке ценных бумаг",
    "о государственных пособиях гражданам", "об обязательном социальном страховании",
    "о полиции", "о безопасности дорожного движения", "об охране окружающей среды",
    "о санитарно-эпидемиологическом", "о центральном банке", "о теплоснабжении",
    "о государственном регулировании производства и оборота этилового",
)

_ALIAS_HEAD = re.compile(r"^(?P<type>[^№«\"]*?)\s*(?:№\s*(?P<num>[^\s«\"]+))?\s*"
                         r"(?:от\s+(?P<date>\d\d\.\d\d\.\d{4}))?\s*(?:[«\"](?P<title>.*)[»\"])?\s*$")
# Слова, после которых название в кавычках точно относится к акту.
_ACT_WORDS = frozenset({p[-1] for p in _TYPE_PHRASES} | {"фсбу", "пбу", "стандарт", "учет", "рп", "кодекс"})
_STOP = frozenset({"о", "об", "и", "в", "на", "по", "с", "для", "за", "к", "от", "при", "или"})
_QUOTES = "«\"“„'"


class _Trie:
    END = "\0"

    def __init__(self):
        self.root: dict = {}

    def add(self, seq: Sequence[str], law_id: int, bare: bool = False):
        node = self.root
        for t in seq:
            node = node.setdefault(t, {})
        ids, was_bare = node.get(self.END, (frozenset(), True))
        node[self.END] = (ids | {law_id}, was_bare and bare)

    def longest(self, toks: List[Token], i: int) -> Tuple[int, FrozenSet[int], bool]:
        """-> (длина совпадения в токенах, law_ids, только «голое» название?)"""
        node, best = self.root, (0, frozenset(), False)
        for j in range(i, len(toks)):
            node = node.get(toks[j].norm)
            if node is None:
                break
            if self.END in node:
                ids, bare = node[self.END]
                best = (j - i + 1, ids, bare)
        return best


@dataclass
class _Match:
    i: int                      # первый токен
    j: int                      # токен после последнего
    ids: FrozenSet[int]
    number: Optional[Tuple[str, ...]] = None
    define: bool = True         # можно ли привязывать к нему «(далее — …)»


class LawIndex:
    def __init__(self, aliases: Dict[str, List[str]]):
        self.law_type: Dict[int, str] = {}
        self.prior: Dict[int, Tuple[int, int, int]] = {}  # меньше — вероятнее
        self.by_number: Dict[Tuple[str, ...], Set[int]] = {}
        self.by_date: Dict[str, Set[int]] = {}
        self.title_stems: Dict[int, Tuple[str, ...]] = {}

        parsed = {int(k): v for k, v in aliases.items()}
        for law_id, names in parsed.items():
            self._parse_law(law_id, names)
        for head, extra in _EXTRA_ALIASES.items():
            law_id = next((k for k, v in parsed.items() if v and v[0].startswith(head)), None)
            if law_id is not None:
                parsed[law_id] = list(parsed[law_id]) + extra

        # Словарь стемов собираем до построения trie, чтобы алиасы не «исправлялись».
        vocab: Dict[str, int] = {w: 1 for p in _TYPE_PHRASES for w in p}
        words: Dict[str, int] = {}
        alias_toks: List[Tuple[int, str, List[Token]]] = []
        for law_id, names in parsed.items():
            for name in names:
                toks = tokenize(normalize_chars(name))
                if toks:
                    alias_toks.append((law_id, name, toks))
                    for t in toks:
                        vocab[t.norm] = vocab.get(t.norm, 0) + 1
                        if len(t.raw) >= 6 and t.raw.isalpha():
                            words[t.raw] = words.get(t.raw, 0) + 1
        self.fuzzy = _Fuzzy(vocab, words)

        self.trie = _Trie()
        self.title_trie = _Trie()
        for law_id, name, toks in alias_toks:
            seq = [t.norm for t in toks]
            bare = name.lstrip()[:1] in _QUOTES
            self.trie.add(seq, law_id, bare)
            # «ГК РФ» без пробела: «ГКРФ»
            if len(seq) == 2 and seq[1] == "рф" and len(seq[0]) <= 5:
                self.trie.add([seq[0] + "рф"], law_id)
        for law_id, title in self.title_stems.items():
            self.title_trie.add(title, law_id)

        # Обратный индекс для «Закон о банкротстве»: стем -> законы, в названии которых он есть.
        self.title_word: Dict[str, Set[int]] = {}
        for law_id, title in self.title_stems.items():
            if title and title[0] in ("о", "об") and self.law_type[law_id] in (FZ, ZRF):
                for w in set(title) - _STOP:
                    self.title_word.setdefault(w, set()).add(law_id)

    def _parse_law(self, law_id: int, names: List[str]):
        full = max(names, key=len) if names else ""
        first = names[0] if names else ""
        low = first.lower()
        self.law_type[law_id] = next((t for p, t in _TYPE_BY_PREFIX if low.startswith(p)), OTHER)
        m = _ALIAS_HEAD.match(first) if self.law_type[law_id] != OTHER else None
        title = None
        if m:
            if m.group("num"):
                key = tuple(t.norm for t in tokenize(normalize_chars(m.group("num"))))
                self.by_number.setdefault(key, set()).add(law_id)
                self.by_number.setdefault(key[:1], set()).add(law_id)
            if m.group("date"):
                d = tokenize(normalize_chars(m.group("date")))
                if d:
                    self.by_date.setdefault(d[0].norm, set()).add(law_id)
            title = m.group("title")
        if title is None:
            q = re.search(r"[«\"](.+)[»\"]", full)
            title = q.group(1) if q else full
        stems = tuple(t.norm for t in tokenize(normalize_chars(title)))
        self.title_stems[law_id] = stems
        famous = title.lower().replace("ё", "е").startswith(_FAMOUS_TITLES)
        self.prior[law_id] = (0 if famous else 1, len(title), law_id)

    @classmethod
    def from_file(cls, path: str) -> "LawIndex":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    # ------------------------------------------------------------ поиск

    def find_laws(self, text: str) -> List[LawMention]:
        low = normalize_chars(text)
        toks = tokenize(low, self.fuzzy)
        found: List[LawMention] = []
        seen_number: Dict[Tuple[str, ...], int] = {}  # номер -> закон, уже выбранный в этом тексте
        seen_ids: Set[int] = set()
        local = _Trie()                                # определения «(далее — …)»
        i = 0
        while i < len(toks):
            m = self._best_match(toks, i, low, local)
            if m is None:
                i += 1
                continue
            law_id = self._choose(m, seen_number, seen_ids)
            found.append(LawMention(toks[m.i].start, toks[m.j - 1].end, law_id))
            seen_ids.add(law_id)
            if m.number:
                seen_number.setdefault(m.number, law_id)
            if m.define:
                self._learn_definition(low, toks, m.j, law_id, local)
            i = m.j
        return found

    def _best_match(self, toks, i, low, local) -> Optional[_Match]:
        cands: List[_Match] = []
        n, ids, bare = self.trie.longest(toks, i)
        if n and (self._bare_ok(toks, i, n, low) if bare else self._abbr_ok(toks, i, n, low)):
            m = _Match(i, i + n, ids)
            cands.append(self._extend(toks, m, low) if len(ids) > 1 else m)
        h = self._header(toks, i, low)
        if h is not None:
            cands.append(h)
        n, ids, _ = local.longest(toks, i)
        if n:
            cands.append(_Match(i, i + n, ids, define=False))
        if not cands:
            return None
        # самое длинное; при равенстве — то, где меньше кандидатов
        return max(cands, key=lambda c: (c.j - c.i, -len(c.ids)))

    def _bare_ok(self, toks, i, n, low) -> bool:
        """Название без вида акта («О связи») принимаем, только если оно в кавычках,
        после вида акта или достаточно длинное, чтобы не совпасть случайно."""
        if i > 0 and toks[i - 1].norm in _ACT_WORDS:
            return True
        before = low[max(0, toks[i].start - 3):toks[i].start].strip()
        if before and before[-1] in _QUOTES and (n >= 3 or toks[i].norm in ("о", "об")):
            return True
        return n >= 4

    def _abbr_ok(self, toks, i, n, low) -> bool:
        """«ЖК «Речной»», «ГК «Орион»» — организация, а не кодекс."""
        if n > 2 or len(toks[i].norm) > 5:
            return True
        after = low[toks[i + n - 1].end:toks[i + n - 1].end + 3].lstrip()
        return not after or after[0] not in _QUOTES

    def _choose(self, m: _Match, seen_number, seen_ids) -> int:
        if len(m.ids) == 1:
            return next(iter(m.ids))
        if m.number in seen_number and seen_number[m.number] in m.ids:
            return seen_number[m.number]
        pool = (m.ids & seen_ids) or m.ids
        return min(pool, key=lambda k: self.prior.get(k, (2, 0, k)))

    # ------------------------------------------------------------ «шапка» акта

    def _header(self, toks: List[Token], i: int, low: str) -> Optional[_Match]:
        types = None
        j = i
        for phrase, ts in _TYPE_PHRASES.items():
            k = len(phrase)
            if tuple(t.norm for t in toks[i:i + k]) == phrase and (types is None or k > j - i):
                types, j = ts, i + k
        if types is not None and toks[i].norm == "фз" and i > 0 and toks[i - 1].norm.isdigit() \
                and low[toks[i - 1].end:toks[i].start].strip() in ("-", "–", "—"):
            return None  # «127-ФЗ»: это суффикс номера, а не вид акта
        number_start = False
        if types is None:
            # номер с суффиксом сам задаёт вид: «127-ФЗ», «34-рп»
            num = self._read_number(toks, i, low)
            if num is None or len(num[0]) < 2 or num[0][1] not in ("фз", "рп"):
                return None
            # «Заказ №127-ФЗ», «Билет №34-рп»: знак номера без вида акта — чужой документ
            if low[max(0, toks[i].start - 3):toks[i].start].strip().endswith(("№", "n")):
                return None
            types = frozenset({FZ}) if num[0][1] == "фз" else frozenset({RASP})
            number_start = True
        cand = {k for k, t in self.law_type.items() if t in types}
        number = date_ids = title_ids = None
        last = j if not number_start else i
        steps = 0
        while j < len(toks) and steps < 8:
            steps += 1
            t = toks[j]
            if t.norm == "рф":
                if types == frozenset({FZ, ZRF}):
                    cand = {k for k in cand if self.law_type[k] == ZRF} or cand
                j += 1
                continue
            if t.norm == "от" and j + 1 < len(toks) and toks[j + 1].norm.startswith("@"):
                j += 1
                continue
            if t.norm.startswith("@") and date_ids is None:
                date_ids = self.by_date.get(t.norm, set())
                j += 1
                last = j
                continue
            num = self._read_number(toks, j, low) if number is None else None
            if num is not None:
                number, j = num
                last = j
                continue
            if title_ids is None:
                n, ids, _ = self.title_trie.longest(toks, j)
                if n:
                    title_ids, j = set(ids), j + n
                    last = j
                    continue
                if t.norm in ("о", "об") and number is None:
                    hit = self._title_by_words(toks, j, low)
                    if hit is not None:
                        title_ids, j = hit
                        last = j
                        continue
                # название с опечаткой: сравниваем текст в кавычках с названиями кандидатов
                quoted = self._quoted(toks, j, low)
                if quoted is not None:
                    pool = cand & self._number_ids(number) if number is not None else cand
                    best = self._closest_title(quoted[0], pool)
                    if best is not None:
                        title_ids, j = {best}, quoted[1]
                        last = j
                        continue
            break
        if number is None and date_ids is None and title_ids is None:
            return None
        if number is not None:
            num_ids = self._number_ids(number)
            if not num_ids & cand:
                return None  # номера нет в базе: «ФЗ №20-456» — не наш закон
            cand &= num_ids
        for extra in (date_ids, title_ids):
            if extra is not None:
                cand &= extra
                if not cand:
                    # дата/название противоречат номеру: «от 26.01.1996 № 15-ФЗ», а в базе
                    # 15-ФЗ другого года — значит, закона нет в базе
                    return None
        if not cand:
            return None
        return _Match(i, last, frozenset(cand), number=number)

    def _number_ids(self, number: Tuple[str, ...]) -> Set[int]:
        return self.by_number.get(number, set())

    def _quoted(self, toks, j, low) -> Optional[Tuple[Set[str], int]]:
        """Слова в кавычках, начиная с токена j: -> (стемы, индекс токена после кавычек)."""
        prev_end = toks[j - 1].end if j > 0 else 0
        if not any(ch in _QUOTES for ch in low[prev_end:toks[j].start]):
            return None
        words: Set[str] = set()
        k = j
        while k < len(toks) and k - j < 40:
            if k > j and any(ch in "»\"”" for ch in low[toks[k - 1].end:toks[k].start]):
                break
            words.add(toks[k].norm)
            k += 1
        return words - _STOP, k

    def _closest_title(self, words: Set[str], pool: Set[int]) -> Optional[int]:
        """Закон с самым похожим названием (Жаккар по стемам), если сходство ≥ 0.6."""
        if not words:
            return None
        best, best_score, second = None, 0.0, 0.0
        for law_id in pool:
            title = set(self.title_stems.get(law_id, ())) - _STOP
            if not title:
                continue
            score = len(words & title) / len(words | title)
            if score > best_score:
                best, best_score, second = law_id, score, best_score
            elif score > second:
                second = score
        return best if best_score >= 0.6 and best_score - second >= 0.1 else None

    def _read_number(self, toks, j, low) -> Optional[Tuple[Tuple[str, ...], int]]:
        t = toks[j]
        if not t.norm.isdigit():
            return None
        # не номер, если перед ним стоит маркер статьи/пункта: «ст. 5», «п. 3»
        if j > 0 and toks[j - 1].norm in ("ст", "стат", "п", "пп", "ч", "част", "пункт", "подпункт"):
            return None
        if j + 1 < len(toks):
            nxt = toks[j + 1]
            gap = low[t.end:nxt.start]
            if gap.strip() in ("-", "–", "—", "\u2011") and len(gap) <= 3:
                return (t.norm, nxt.norm), j + 2  # «127-ФЗ», «2300-1», «20-456»
        return (t.norm,), j + 1

    def _title_by_words(self, toks, j, low) -> Optional[Tuple[Set[int], int]]:
        """«Закон о банкротстве» -> «О несостоятельности (банкротстве)»: слова после
        «о/об» должны идти в названии в том же порядке и покрывать его хотя бы наполовину."""
        words: List[str] = []
        k = j + 1
        while k < len(toks) and len(words) < 6:
            gap = low[toks[k - 1].end:toks[k].start]
            if any(ch not in " \t\n()«»\"-" for ch in gap) or toks[k].norm.isdigit() or toks[k].norm.startswith("@"):
                break
            words.append(toks[k].norm)
            k += 1
        content = [w for w in words if w not in _STOP]
        while content:
            pool = None
            for w in content:
                s = self.title_word.get(w, set())
                pool = s if pool is None else pool & s
            good = set()
            for law_id in pool or ():
                title = [w for w in self.title_stems[law_id] if w not in _STOP]
                if _is_subseq(content, title) and 2 * len(content) >= len(title):
                    good.add(law_id)
            if good:
                end = j + 1 + max(idx for idx, w in enumerate(words) if w == content[-1]) + 1
                return good, end
            content = content[:-1]
        return None

    def _extend(self, toks, m: _Match, low) -> _Match:
        """После неоднозначного алиаса («ФЗ №127-ФЗ») смотрим на дату/название справа."""
        j = m.j
        ids = set(m.ids)
        for _ in range(3):
            if j < len(toks) and toks[j].norm == "от":
                j += 1
            if j >= len(toks):
                break
            t = toks[j]
            if t.norm.startswith("@") and ids & self.by_date.get(t.norm, set()):
                ids &= self.by_date[t.norm]
                j += 1
                m = _Match(m.i, j, frozenset(ids))
                continue
            n, tids, _ = self.title_trie.longest(toks, j)
            if n and ids & tids:
                ids &= tids
                j += n
                m = _Match(m.i, j, frozenset(ids))
                continue
            break
        return m

    # ------------------------------------------------------------ «(далее — …)»

    _DEFINE = re.compile(r"\s*[,(]\s*(?:далее\s*(?:по\s+тексту\s*)?(?:[-–—:]\s*)?|далее\s+-\s*)"
                         r"[«\"]?([^()«»\"\n]{2,60}?)[»\"]?\s*\)")

    def _learn_definition(self, low, toks, j, law_id, local: _Trie):
        end = toks[j - 1].end
        m = self._DEFINE.match(low, end)
        if not m:
            return
        seq = [t.norm for t in tokenize(m.group(1), self.fuzzy)]
        if seq and seq[0] not in _STOP and len(seq) <= 6:
            local.add(seq, law_id)


def _is_subseq(needle: Sequence[str], hay: Sequence[str]) -> bool:
    it = iter(hay)
    return all(any(w == h for h in it) for w in needle)
