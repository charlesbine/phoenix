FROM python:3.13-slim AS base

# Install pixlet
ARG PIXLET_VERSION=0.34.0
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates bash git tzdata libportaudio2 && \
    ARCH=$(case ${TARGETARCH} in arm64) echo "arm64" ;; amd64) echo "amd64" ;; *) echo "amd64" ;; esac) && \
    curl -fsSL "https://github.com/tidbyt/pixlet/releases/download/v${PIXLET_VERSION}/pixlet_${PIXLET_VERSION}_linux_${ARCH}.tar.gz" \
    | tar -xz -C /usr/local/bin pixlet && \
    chmod +x /usr/local/bin/pixlet && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /usr/local/bin/uv
COPY --from=oven/bun:1 /usr/local/bin/bun /usr/local/bin/bun

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-group dev --no-install-project --extra audio

# Build frontend first (cache layer)
COPY frontend/package.json frontend/bun.lock ./frontend/
RUN cd frontend && bun install --frozen-lockfile

# Copy frontend source and build dashboard assets
COPY frontend/ frontend/
RUN cd frontend && bun run build

# Copy project
COPY phoenix/ phoenix/

# Install the project itself
RUN uv sync --frozen --no-dev --no-group dev --extra audio

# Create non-root runtime user and prepare writable paths before declaring volumes
RUN groupadd --gid 1000 phoenix && \
    useradd --uid 1000 --gid 1000 --groups dialout,audio --create-home --shell /bin/bash phoenix && \
    mkdir -p /app/phoenix/data /app/phoenix/outputs /app/phoenix/logs /app/phoenix/apps && \
    chown -R phoenix:phoenix /app

# Data directories (mount as volumes for persistence)
VOLUME ["/app/phoenix/data", "/app/phoenix/outputs"]

ENV UV_NO_GROUP=dev \
    UV_NO_SYNC=1

EXPOSE 7002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7002/healthz', timeout=3)" || exit 1

# Run all three services via the entrypoint shell script.
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER phoenix

ENTRYPOINT ["/docker-entrypoint.sh"]
