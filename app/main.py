from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.pipeline import detect, get_codex_ids, get_index
from app.schemas import LinksResponse, TextRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_codex_ids()
    get_index()  # прогреваем индекс законов при старте, а не на первом запросе
    yield


app = FastAPI(
    title="Law Links Service",
    description="Сервис для выделения юридических ссылок из текста",
    version="0.1.0",
    lifespan=lifespan,
)


# sync-def намеренно: FastAPI выполнит CPU-работу в threadpool и не заблокирует event loop
@app.post("/detect")
def get_law_links(data: TextRequest) -> LinksResponse:
    return LinksResponse(links=detect(data.text))


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8978)
