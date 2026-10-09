"""Проверка лимита времени через HTTP: имитирует 4 бенча по 500 текстов.

    python -m scripts.loadtest --url http://localhost:8978/detect --n 2000 --data data/seed.jsonl

Лимит препода — 300 с на все 4 бенча. Целимся в ≤ 100 с (запас на их железо).
Запросы шлются последовательно — как, скорее всего, делает их скрипт.
"""
import argparse
import json
import statistics
import time

import httpx

LIMIT_S = 300


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8978/detect")
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--data", default="data/seed.jsonl")
    args = ap.parse_args()

    texts = [json.loads(l)["text"] for l in open(args.data, encoding="utf-8") if l.strip()]
    lat = []
    with httpx.Client(timeout=30) as client:
        t0 = time.perf_counter()
        for i in range(args.n):
            s = time.perf_counter()
            r = client.post(args.url, json={"text": texts[i % len(texts)]})
            r.raise_for_status()
            lat.append(time.perf_counter() - s)
        total = time.perf_counter() - t0

    lat_ms = sorted(x * 1000 for x in lat)
    print(f"{args.n} запросов за {total:.1f}s  "
          f"(p50={statistics.median(lat_ms):.1f}ms, p99={lat_ms[int(0.99 * len(lat_ms)) - 1]:.1f}ms, "
          f"max={lat_ms[-1]:.1f}ms)")
    print("OK: укладываемся с запасом" if total < LIMIT_S / 3 else
          "ВНИМАНИЕ: запас меньше 3x" if total < LIMIT_S else "ПРОВАЛ: дольше лимита")


if __name__ == "__main__":
    main()
