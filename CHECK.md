# Проверка решения перед сдачей

Цель: каждый из нас на своём компьютере убеждается, что сервис из `main` собирается, проходит тесты, держит качество и укладывается во время. Займёт 15–20 минут.

**Сдаём 14.10 до 23:59. Пересдача сжигает бонус, поэтому после проверки в `main` ничего не пушим без согласования с тимлидом.**

---

## Что должно получиться

| Шаг | Ожидаемый результат |
|---|---|
| Тесты | `79 passed` (число может быть чуть больше, если добавили тесты), **0 failed** |
| Качество (ACC) | level1 ≈ 0.99, level2 ≈ 0.97, level3 ≈ 0.99, level4 ≈ 0.84, traps = **1.000** |
| Качество на шуме | каждый уровень не ниже ~0.80, traps = **1.000** |
| Docker | образ собирается, `/detect` отвечает JSON-ом со ссылками |
| Нагрузка | 2000 запросов быстрее **60 с** (лимит препода — 300 с) |

Если что-то не совпадает — не чините сами в `main`, а напишите в чат (см. «Что прислать» в конце).

---

## Linux

```bash
# 1. Свежая копия
git clone https://github.com/miklazru/law_project_for_uni.git
cd law_project_for_uni
# (если репозиторий уже есть: git checkout main && git pull)

# 2. Окружение
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Тесты
python -m pytest -q

# 4. Качество
python -m scripts.evaluate data/level*.jsonl data/traps.jsonl --errors 0

# 5. Качество на «упоротых» данных
python -m scripts.make_noisy data/level*.jsonl data/traps.jsonl --out data/noisy
python -m scripts.evaluate data/noisy/*.jsonl --errors 0

# 6. Docker (если docker без sudo не работает — добавьте sudo к каждой docker-команде)
docker rm -f law-links-container 2>/dev/null
docker build -t law-links-service .
docker run -d -p 8978:8978 --name law-links-container law-links-service
sleep 3

# 7. Запрос к сервису
python -c "import httpx; print(httpx.post('http://localhost:8978/detect', json={'text': 'Согласно пп. 1 п. 1 ст. 374 НК РФ и ст. 151 настоящего Кодекса'}).json())"

# 8. Нагрузка
python -m scripts.loadtest --n 2000 --data data/level3.jsonl

# 9. Уборка
docker rm -f law-links-container
deactivate
```

---

## macOS

Нужны: Python 3.10+ (`brew install python`, если нет) и **запущенный Docker Desktop** (иконка кита в строке меню). На Apple Silicon (M1–M4) всё работает так же.

```bash
# 1. Свежая копия
git clone https://github.com/miklazru/law_project_for_uni.git
cd law_project_for_uni

# 2. Окружение
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Тесты
python -m pytest -q

# 4. Качество
python -m scripts.evaluate data/level*.jsonl data/traps.jsonl --errors 0

# 5. Качество на «упоротых» данных
python -m scripts.make_noisy data/level*.jsonl data/traps.jsonl --out data/noisy
python -m scripts.evaluate data/noisy/*.jsonl --errors 0

# 6. Docker (sudo не нужен)
docker rm -f law-links-container 2>/dev/null
docker build -t law-links-service .
docker run -d -p 8978:8978 --name law-links-container law-links-service
sleep 3

# 7. Запрос к сервису
python -c "import httpx; print(httpx.post('http://localhost:8978/detect', json={'text': 'Согласно пп. 1 п. 1 ст. 374 НК РФ и ст. 151 настоящего Кодекса'}).json())"

# 8. Нагрузка
python -m scripts.loadtest --n 2000 --data data/level3.jsonl

# 9. Уборка
docker rm -f law-links-container
deactivate
```

Если порт 8978 занят (`port is already allocated`): `docker ps`, остановите то, что его держит, и повторите шаг 6.

---

## Windows (PowerShell)

Нужны: Python 3.10+ (python.org, при установке отметить **Add to PATH**), Git и **запущенный Docker Desktop**.

Есть два отличия от Linux и macOS:
- PowerShell сам не раскрывает `data/level*.jsonl`, поэтому файлы перечислены явно;
- консоль Windows по умолчанию не в UTF-8, поэтому сначала включаем UTF-8, иначе вывод с кириллицей может упасть с `UnicodeEncodeError`.

```powershell
# 0. UTF-8 для этой сессии
chcp 65001
$env:PYTHONUTF8 = "1"

# 1. Свежая копия
git clone https://github.com/miklazru/law_project_for_uni.git
cd law_project_for_uni

# 2. Окружение
py -m venv .venv
# если ругается на политику выполнения скриптов:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# 3. Тесты
python -m pytest -q

# 4. Качество
python -m scripts.evaluate data/level1.jsonl data/level2.jsonl data/level3.jsonl data/level4.jsonl data/traps.jsonl --errors 0

# 5. Качество на «упоротых» данных
python -m scripts.make_noisy data/level1.jsonl data/level2.jsonl data/level3.jsonl data/level4.jsonl data/traps.jsonl --out data/noisy
python -m scripts.evaluate data/noisy/level1.jsonl data/noisy/level2.jsonl data/noisy/level3.jsonl data/noisy/level4.jsonl data/noisy/traps.jsonl --errors 0

# 6. Docker
docker rm -f law-links-container 2>$null
docker build -t law-links-service .
docker run -d -p 8978:8978 --name law-links-container law-links-service
Start-Sleep -Seconds 3

# 7. Запрос к сервису (через Python, чтобы не воевать с кавычками и кодировкой в PowerShell)
python -c "import httpx; print(httpx.post('http://localhost:8978/detect', json={'text': 'Согласно пп. 1 п. 1 ст. 374 НК РФ и ст. 151 настоящего Кодекса'}).json())"

# 8. Нагрузка
python -m scripts.loadtest --n 2000 --data data/level3.jsonl

# 9. Уборка
docker rm -f law-links-container
deactivate
```

Если `docker build` падает с ошибкой про WSL 2: откройте Docker Desktop → Settings → General → включите «Use the WSL 2 based engine» и перезапустите Docker Desktop.

---

## Ожидаемый ответ на шаге 7

Порядок ссылок может отличаться, но их должно быть две:

```
{'links': [{'law_id': 15, 'article': '374', 'point_article': '1', 'subpoint_article': '1'},
           {'law_id': 15, 'article': '151', 'point_article': None, 'subpoint_article': None}]}
```

«ст. 151 настоящего Кодекса» должна привязаться к НК (`law_id: 15`) — это проверка, что линкер в сборке.

---

## Что прислать в чат

Одним сообщением:
1. ОС и процессор (например, «macOS, M2» или «Windows 11, Intel»).
2. Строку с итогом тестов (`79 passed …`).
3. Строки с `ACC=` из шагов 4 и 5.
4. Ответ из шага 7.
5. Строку с итогом нагрузки (`2000 запросов за …s`).

Если что-то упало — пришлите полный текст ошибки и номер шага.
