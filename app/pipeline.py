"""Склейка модулей (роль 1). Единая точка входа: detect(text)."""
import os
from functools import lru_cache
from typing import List

from app import linker, refs
from app.laws import LawIndex
from app.schemas import LawLink

ALIASES_PATH = os.environ.get(
    "LAW_ALIASES", os.path.join(os.path.dirname(__file__), "..", "law_aliases.json"))


@lru_cache(maxsize=1)
def get_index() -> LawIndex:
    return LawIndex.from_file(ALIASES_PATH)


def detect(text: str) -> List[LawLink]:
    laws = get_index().find_laws(text)
    ref_mentions = refs.find_refs(text)
    return linker.link(ref_mentions, laws)
