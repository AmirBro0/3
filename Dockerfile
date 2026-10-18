FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OKO_DATA_DIR=/data

# libglib — для OpenCV, DejaVu — кириллические подписи на кадрах-доказательствах
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/oko
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://localhost:8000/healthz || exit 1

# Один процесс uvicorn: очередь задач живёт в памяти процесса.
# Параллельность — через OKO_WORKERS (потоки анализа), а не через --workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
