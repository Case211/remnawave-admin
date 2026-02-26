FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        python3-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefer-binary --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY src ./src
COPY locales ./locales
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts

# Write version at build time (pass via --build-arg or auto-detect from git tag)
ARG APP_VERSION=unknown
RUN echo "${APP_VERSION}" > /app/VERSION

RUN mkdir -p /app/logs /app/geoip

CMD ["python", "-m", "src.main"]
