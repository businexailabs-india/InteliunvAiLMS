from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery("businex", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name="businex.embed_chunk")
def embed_chunk(text: str) -> list[float]:
    """Deterministic mock embedding used when no paid embedding provider is configured."""
    values = [((ord(char) % 13) / 13) for char in text[:32]]
    return values + [0.0] * max(0, 8 - len(values))
