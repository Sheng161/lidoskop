import asyncio

from celery import Celery

from app.config import get_settings
from app.db import SessionFactory
from app.orchestrator import plan_search, run_research

settings = get_settings()
celery_app = Celery("lidoskop", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=1800,
    broker_connection_retry_on_startup=True,
)


async def _plan(job_id: str) -> None:
    async with SessionFactory() as session:
        await plan_search(session, job_id)


async def _research(job_id: str) -> None:
    async with SessionFactory() as session:
        await run_research(session, job_id)


@celery_app.task(
    name="lidoskop.plan_search", autoretry_for=(Exception,), retry_backoff=True, max_retries=2
)
def plan_search_task(job_id: str) -> None:
    asyncio.run(_plan(job_id))


@celery_app.task(
    name="lidoskop.run_research", autoretry_for=(Exception,), retry_backoff=True, max_retries=2
)
def run_research_task(job_id: str) -> None:
    asyncio.run(_research(job_id))
