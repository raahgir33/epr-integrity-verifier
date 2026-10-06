from fastapi import FastAPI

from app.config import settings

app = FastAPI(title="epr-api")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.gemini_model,
        "region": settings.vertex_location,
    }
