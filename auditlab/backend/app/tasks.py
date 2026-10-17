"""File de tâches (Celery + Redis) : imports et analyses longues tournent en arrière-plan.

En mode « eager » (développement, tests), la tâche s'exécute immédiatement dans le processus.
Lancer un worker : `celery -A app.tasks worker --loglevel=INFO`.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()
celery = Celery("auditlab", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_always_eager=settings.tasks_eager,
    task_eager_propagates=False,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
)
celery.autodiscover_tasks(["app.analytics"], related_name="jobs")
