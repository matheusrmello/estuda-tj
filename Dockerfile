FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ESTUDATJ_BIND=0.0.0.0 \
    ESTUDATJ_DATA=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' --uid 10001 estudatj \
    && mkdir -p /app /data \
    && chown estudatj:estudatj /data

WORKDIR /app
COPY --chown=estudatj:estudatj backend/ /app/backend/
COPY --chown=estudatj:estudatj frontend/ /app/frontend/

USER estudatj
EXPOSE 8000
CMD ["python3", "backend/server.py"]
