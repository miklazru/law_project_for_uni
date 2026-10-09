FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY law_aliases.json .
COPY app ./app

EXPOSE 8978

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8978"]
