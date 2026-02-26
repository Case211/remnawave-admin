# Remnawave Node Agent — лёгкий образ для деплоя на нодах
FROM python:3.12-slim

WORKDIR /app

# procps — pgrep для healthcheck
# util-linux — nsenter для host mode (выполнение команд на хосте)
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# SIGTERM для graceful shutdown
STOPSIGNAL SIGTERM

# Запуск из корня проекта: python -m src.main
CMD ["python", "-m", "src.main"]
