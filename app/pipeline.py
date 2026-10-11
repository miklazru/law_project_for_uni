"""Склейка модулей (роль 1). Единая точка входа: detect(text)."""
import json
import os
import re
from functools import lru_cache
from typing import FrozenSet, List

from app import linker, refs
from app.laws import LawIndex, normalize_chars
from app.schemas import LawLink

ALIASES_PATH = os.environ.get(
    "LAW_ALIASES", os.path.join(os.path.dirname(__file__), "..", "law_aliases.json"))


@lru_cache(maxsize=1)
def get_index() -> LawIndex:
    return LawIndex.from_file(ALIASES_PATH)


@lru_cache(maxsize=1)
def get_codex_ids() -> FrozenSet[int]:
    """law_id кодексов — нужны линкеру для анафор «настоящего Кодекса»."""
    with open(ALIASES_PATH, encoding="utf-8") as f:
        aliases = json.load(f)
    # кодекс — если в каком-то алиасе «кодекс» стоит вне кавычек
    # («Трудовой кодекс РФ» — да, «О введении в действие … кодекса» — нет)
    def unquoted(name: str) -> str:
        return re.sub(r"[«\"].*?[»\"]", " ", name).lower()
    return frozenset(int(k) for k, names in aliases.items()
                     if any("кодекс" in unquoted(n) for n in names))


def detect(text: str) -> List[LawLink]:
    laws = get_index().find_laws(text)
    # парсеру отдаём нормализованный текст (латиница-двойник -> кириллица, нижний регистр);
    # длина строки та же, поэтому позиции ссылок совпадают с оригиналом
    ref_mentions = refs.find_refs(normalize_chars(text))
    return linker.link(ref_mentions, laws, text=text, codex_ids=get_codex_ids())
