"""Офлайн-оценка качества и скорости (без HTTP).

    python -m scripts.evaluate data/seed.jsonl [data/other.jsonl ...] [--errors 10]

Основная метрика — ACCURACY (ответ препода: «обычное акьюраси»).
Считаем её по текстам: текст засчитан, только если множество предсказанных
ссылок в точности совпало с эталоном (одна лишняя или пропущенная ссылка
обнуляет весь текст). Это самая строгая трактовка, поэтому целимся в неё.
Дополнительно печатаем micro P/R/F1 по кортежам
(law_id, article, point_article, subpoint_article) для диагностики.
"""
import argparse
import json
import time
from collections import Counter

from app.pipeline import detect, get_index

KEYS = ("law_id", "article", "point_article", "subpoint_article")


def as_tuple(link) -> tuple:
    d = link if isinstance(link, dict) else link.model_dump()
    return tuple(None if d.get(k) is None else str(d.get(k)).strip() for k in KEYS)


def evaluate(path: str, show_errors: int):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    tp = fp = fn = 0
    exact = 0
    errors = []
    t0 = time.perf_counter()
    for row in rows:
        pred = Counter(as_tuple(x) for x in detect(row["text"]))
        gold = Counter(as_tuple(x) for x in row["links"])
        hit = sum((pred & gold).values())
        tp += hit
        fp += sum(pred.values()) - hit
        fn += sum(gold.values()) - hit
        exact += pred == gold
        if pred != gold:
            errors.append((row["text"], sorted(gold - pred, key=str), sorted(pred - gold, key=str)))
    dt = time.perf_counter() - t0
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    acc = exact / max(len(rows), 1)
    print(f"{path}: n={len(rows)}  ACC={acc:.3f}  |  P={p:.3f}  R={r:.3f}  F1={f1:.3f}  "
          f"time={dt:.2f}s ({1000 * dt / max(len(rows), 1):.1f} ms/text)")
    for text, missed, extra in errors[:show_errors]:
        print(f"  ✗ {text[:120]!r}")
        for t in missed:
            print(f"      пропущено: {t}")
        for t in extra:
            print(f"      лишнее:    {t}")
    return acc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--errors", type=int, default=10, help="сколько ошибок показать")
    args = ap.parse_args()
    t = time.perf_counter()
    get_index()
    print(f"index loaded in {time.perf_counter() - t:.2f}s")
    for f in args.files:
        evaluate(f, args.errors)
