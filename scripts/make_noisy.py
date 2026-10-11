"""Делает «упоротые» версии размеченных файлов, имитируя бенчи 3–4 препода.
Разметка не меняется: сервис должен выдать те же ссылки, что и для чистого текста.

    python -m scripts.make_noisy data/level1.jsonl data/level2.jsonl --out data/noisy --seed 0
    python -m scripts.evaluate data/noisy/*.jsonl

Виды шума (каждый текст получает случайный набор):
  - латиница-двойник вместо кириллицы (с/c, р/p, о/o …);
  - ВЕРХНИЙ или нижний регистр всего текста;
  - лишние / пропавшие пробелы вокруг «ст.», «п.», «№»;
  - переносы строк внутри ссылки;
  - опечатки в словах-маркерах: «статья» -> «стаья», «пункт» -> «пунт».
"""
import argparse
import json
import os
import random
import re

_HOMO = {"а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y", "к": "k",
         "А": "A", "С": "C", "Е": "E", "О": "O", "Р": "P", "Х": "X", "Т": "T", "Н": "H",
         "М": "M", "К": "K", "В": "B"}
_TYPOS = [("стать", "стаь"), ("стать", "сатть"), ("пункт", "пунт"), ("пункт", "пнукт"),
          ("подпункт", "подпукт"), ("част", "чсат"), ("кодекс", "кодкес"), ("закон", "заокн")]


def homoglyphs(t, rng, p):
    return "".join(_HOMO[ch] if ch in _HOMO and rng.random() < p else ch for ch in t)


def spaces(t, rng):
    t = re.sub(r"(ст|п|пп|ч|№)\.?\s+(?=\d)",
               lambda m: m.group(0).rstrip() if rng.random() < .5 else m.group(0) + "  ", t)
    return re.sub(r",\s", lambda m: "," if rng.random() < .3 else m.group(0), t)


def newlines(t, rng):
    return re.sub(r"(\d)\s+(?=[А-ЯA-Zа-я])", lambda m: m.group(1) + ("\n" if rng.random() < .3 else " "), t)


def typos(t, rng):
    for good, bad in rng.sample(_TYPOS, 2):
        t = re.sub(good, bad, t, count=1, flags=re.IGNORECASE) if rng.random() < .5 else t
    return t


def noisify(t, rng):
    ops = rng.sample(["homo", "case", "spaces", "newlines", "typos"], k=rng.randint(1, 3))
    if "homo" in ops:
        t = homoglyphs(t, rng, rng.choice([.1, .3, .6]))
    if "spaces" in ops:
        t = spaces(t, rng)
    if "newlines" in ops:
        t = newlines(t, rng)
    if "typos" in ops:
        t = typos(t, rng)
    if "case" in ops:
        t = t.upper() if rng.random() < .5 else t.lower()
    return t, ops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="data/noisy")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    os.makedirs(args.out, exist_ok=True)
    for path in args.files:
        dst = os.path.join(args.out, os.path.basename(path))
        with open(path, encoding="utf-8") as src, open(dst, "w", encoding="utf-8") as out:
            for line in src:
                if not line.strip():
                    continue
                row = json.loads(line)
                row["text"], row["noise"] = noisify(row["text"], rng)
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("->", dst)


if __name__ == "__main__":
    main()
