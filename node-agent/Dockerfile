# Remnawave Node Agent — лёгкий образ для деплоя на нодах

# ── Сборка nDPId ──────────────────────────────────────────────────
# Демон глубокого разбора трафика едет внутри образа, а не ставится на
# ноду руками: оператору достаточно тумблера в панели, а сборка из
# исходников на каждой ноде — это gcc, cmake и десять минут ожидания там,
# где никто этого не ждёт.
#
# Слушать интерфейс он может прямо отсюда: контейнер агента и так живёт в
# сети хоста (network_mode: host) с privileged.
FROM debian:bookworm-slim AS ndpi-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates \
        autoconf automake libtool pkg-config \
        wget unzip \
        libpcap-dev zlib1g-dev libjson-c-dev \
    && rm -rf /var/lib/apt/lists/*

# Пин на релиз, а не на main: демон читает наш сокет, и молча уехавший
# формат событий сломал бы детект в самый неподходящий момент.
# Теги у проекта без префикса «v».
ARG NDPID_REF=1.7
RUN git clone --depth 1 --branch "${NDPID_REF}" https://github.com/utoni/nDPId.git /src/nDPId \
    && cd /src/nDPId && mkdir build && cd build \
    && cmake .. -DBUILD_NDPI=ON -DCMAKE_BUILD_TYPE=Release \
    && make -j"$(nproc)"

# Отдельным шагом и без «|| true» на всей цепочке: иначе провал сборки
# проходит незамеченным, а образ уезжает без демона — ровно это и
# случилось на первом заходе.
RUN strip /src/nDPId/build/nDPId /src/nDPId/build/nDPIsrvd || true; \
    test -x /src/nDPId/build/nDPId && test -x /src/nDPId/build/nDPIsrvd

# ── Образ агента ──────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# procps — pgrep для healthcheck
# util-linux — nsenter для host mode (выполнение команд на хосте)
# libpcap0.8, libjson-c5 — рантайм nDPId
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps util-linux libpcap0.8 libjson-c5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ndpi-builder /src/nDPId/build/nDPId /usr/local/bin/nDPId
COPY --from=ndpi-builder /src/nDPId/build/nDPIsrvd /usr/local/bin/nDPIsrvd

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# SIGTERM для graceful shutdown
STOPSIGNAL SIGTERM

# Запуск из корня проекта: python -m src.main
CMD ["python", "-m", "src.main"]
