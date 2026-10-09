"""РОЛЬ 3 — распознавание закона (law_id).

Сейчас НАИВНАЯ заглушка: точное совпадение алиаса без учёта регистра
с проверкой границ слова. Не умеет склонения («Налогового кодекса»),
опечатки, неоднозначности. Заменить своей реализацией, сохранив сигнатуру.
"""
import json
from typing import Dict, List

from app.schemas import LawMention

_WORD = str.isalnum


class LawIndex:
    def __init__(self, aliases: Dict[str, List[str]]):
        # alias(lower) -> law_id; при конфликте берём первый (TODO роль 3: неоднозначности)
        self.alias2id: Dict[str, int] = {}
        for law_id, names in aliases.items():
            for name in names:
                self.alias2id.setdefault(name.lower().strip(), int(law_id))
        # длинные алиасы первыми, чтобы «АПК РФ» побеждал «АПК»
        self.sorted_aliases = sorted(self.alias2id, key=len, reverse=True)

    @classmethod
    def from_file(cls, path: str) -> "LawIndex":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def find_laws(self, text: str) -> List[LawMention]:
        low = text.lower()
        taken = [False] * len(low)
        found: List[LawMention] = []
        for alias in self.sorted_aliases:
            start = low.find(alias)
            while start != -1:
                end = start + len(alias)
                left_ok = start == 0 or not _WORD(low[start - 1])
                right_ok = end == len(low) or not _WORD(low[end])
                if left_ok and right_ok and not any(taken[start:end]):
                    found.append(LawMention(start, end, self.alias2id[alias]))
                    for i in range(start, end):
                        taken[i] = True
                start = low.find(alias, start + 1)
        return sorted(found, key=lambda m: m.start)
