# Browser-backed marketplace sessions use headed Chromium under Xvfb in Docker.
# Xvfb is started by entrypoint.sh before the server.
FROM python:3.13-slim

# Keep in sync with astral-sh/setup-uv in .github/workflows/ci.yml.
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-browsers \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app
# README.md comes along because pyproject declares it as the package readme —
# without it `uv sync` fails while reading project metadata.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project \
    && uv run playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends xvfb fluxbox \
    && rm -rf /var/lib/apt/lists/*

COPY src ./src
COPY entrypoint.sh ./entrypoint.sh
RUN uv sync --frozen --no-dev && chmod +x entrypoint.sh

# /data holds the marketplace browser profiles, shared order store, and Ozon price history;
# mount it as a persistent volume so sessions and synchronized data survive.
VOLUME ["/data"]

# Used by the shared HTTP transport; also serves /metrics.
EXPOSE 8084

ENTRYPOINT ["./entrypoint.sh"]
