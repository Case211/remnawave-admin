# Remnawave Admin Web Panel - Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (postgresql-client for pg_dump/psql used by backup service)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY web/backend/requirements.txt /app/web/backend/requirements.txt
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN pip install --no-cache-dir -r /app/web/backend/requirements.txt

# Copy application code
COPY shared/ /app/shared/
COPY web/backend/ /app/web/backend/

# Copy Alembic migrations (auto-run on startup)
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8081

# Run the application (--no-access-log to avoid duplicate logging, format configured in main.py)
CMD ["python", "-m", "uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8081", "--no-access-log", "--log-level", "warning", "--ws", "websockets", "--ws-per-message-deflate", "true"]
