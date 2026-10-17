FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --system --uid 1001 auditlab && mkdir -p /data/datasets && chown auditlab /data/datasets
USER auditlab

EXPOSE 8000
# Les migrations sont appliquées à chaque démarrage (idempotent).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
