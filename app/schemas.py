"""Общие структуры данных. Это КОНТРАКТ между модулями — менять только по договорённости."""
from dataclasses import dataclass, field
from typing import List, Optional

from pydantic import BaseModel


# ---------- API (формат задан преподом, не трогать) ----------
class LawLink(BaseModel):
    law_id: Optional[int] = None
    article: Optional[str] = None
    point_article: Optional[str] = None
    subpoint_article: Optional[str] = None


class LinksResponse(BaseModel):
    links: List[LawLink]


class TextRequest(BaseModel):
    text: str


# ---------- Внутренние структуры ----------
@dataclass
class LawMention:
    """Упоминание закона в тексте (выход laws.find_laws, роль 3)."""
    start: int
    end: int
    law_id: int


@dataclass
class RefMention:
    """Структурная часть ссылки без закона (выход refs.find_refs, роль 4).

    Списки уже раскрыты: «пп. а, б п. 3» -> subpoints=["а", "б"], points=["3"].
    Пустой список = поле отсутствует (в ответе будет None).
    """
    start: int
    end: int
    articles: List[str] = field(default_factory=list)
    points: List[str] = field(default_factory=list)
    subpoints: List[str] = field(default_factory=list)
