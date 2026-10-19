FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Client Docker : le worker lance le bac à sable des scripts (DAT-27).
COPY --from=docker:27.3.1-cli /usr/local/bin/docker /usr/local/bin/docker

COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --system --uid 1001 auditlab && mkdir -p /data/datasets && chown auditlab /data/datasets
USER auditlab

EXPOSE 8000
# Les migrations sont appliquées à chaque démarrage (idempotent).
# NF-09 : plusieurs processus (WEB_CONCURRENCY, 4 par défaut ; (pool + débordement) × processus
# reste sous max_connections de PostgreSQL) ; keep-alive plus long que celui de nginx.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers ${WEB_CONCURRENCY:-4} --timeout-keep-alive 75"]
