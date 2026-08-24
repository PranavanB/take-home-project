FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/app /app/app
COPY seed /app/seed

RUN pip install --no-cache-dir .

RUN mkdir -p /tmp/job-matcher-sessions && chown -R app:app /app /tmp/job-matcher-sessions

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

