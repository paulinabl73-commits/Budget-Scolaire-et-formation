"""File de tâches (Celery + Redis) : imports et analyses longues tournent en arrière-plan.

En mode « eager » (développement, tests), la tâche s'exécute immédiatement dans le processus.
Lancer un worker : `celery -A app.tasks worker --loglevel=INFO`.
"""

from celery import Celery
from celery.schedules import crontab

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


@celery.task(name="auditlab.daily_followup")
def daily_followup() -> int:
    """Relances des plans d'action (CON-06) puis envoi des e-mails en file."""
    from app.db import SessionLocal
    from app.followup import send_reminders
    from app.notify import send_pending

    with SessionLocal() as db:
        count = send_reminders(db)
        send_pending(db)
    return count


# Planification (celery beat) : chaque jour à 6 h UTC.
celery.conf.beat_schedule = {
    "relances-plans-d-action": {
        "task": "auditlab.daily_followup",
        "schedule": crontab(hour=6, minute=0),
    },
}
