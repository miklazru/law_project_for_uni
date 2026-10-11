"""Оценка только распознавания законов (роль 3), без парсера ссылок и линкера.

    python -m scripts.eval_laws data/*.jsonl --errors 20

Для каждого текста сравниваем множество law_id из разметки с множеством law_id,
которые нашёл find_laws. Лишние законы сами по себе не ошибка (закон может
упоминаться без статьи), поэтому главное здесь — recall; лишние показываем
для разбора.
"""
import argparse
import json
import time

from app.pipeline import get_index


def evaluate(path: str, show_errors: int) -> None:
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    index = get_index()
    gold_total = hit = extra_total = texts_ok = n = 0
    errors = []
    t0 = time.perf_counter()
    for row in rows:
        gold = {x["law_id"] for x in row["links"] if x.get("law_id") is not None}
        pred = {m.law_id for m in index.find_laws(row["text"])}
        if not gold:
            continue
        n += 1
        gold_total += len(gold)
        hit += len(gold & pred)
        extra_total += len(pred - gold)
        texts_ok += gold <= pred
        if not gold <= pred or pred - gold:
            errors.append((row["text"], sorted(gold - pred), sorted(pred - gold)))
    dt = time.perf_counter() - t0
    recall = hit / gold_total if gold_total else 0.0
    print(f"{path}: texts={n}  law recall={recall:.3f}  texts with all laws={texts_ok / max(n, 1):.3f}  "
          f"extra laws={extra_total}  ({1000 * dt / max(len(rows), 1):.2f} ms/text)")
    errors.sort(key=lambda e: not e[1])  # сначала пропуски, потом лишние
    for text, missed, extra in errors[:show_errors]:
        print(f"  ✗ {text[:160]!r}")
        if missed:
            print(f"      пропущено: {missed}")
        if extra:
            print(f"      лишнее:    {extra}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--errors", type=int, default=10)
    args = ap.parse_args()
    for f in args.files:
        evaluate(f, args.errors)
