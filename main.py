import asyncio

from fastapi import FastAPI

from api.routes import router as api_router
from api.routes import llm_service


app = FastAPI(
    title="OpenGrit AI Backend",
    description=(
        "AI backend for text processing, embeddings, graph building, and RAG queries."
    ),
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")
app.include_router(api_router)


@app.on_event("startup")
async def warmup_llm() -> None:
    asyncio.create_task(llm_service.warmup())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
