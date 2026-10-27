from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import academics, ai, auth, billing, engagement, lms, training
from app.ai.providers import get_provider
from app.config import get_settings

settings = get_settings()
app = FastAPI(title="IntelUniVen AI Edu Lab API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "Idempotency-Key"],
)
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(lms.router)
app.include_router(ai.router)
app.include_router(engagement.router)
app.include_router(training.router)
app.include_router(academics.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "auth_mode": settings.auth_mode, "ai_provider": get_provider(settings).name}


@app.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}
