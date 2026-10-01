# TrendVN worker: queue, rules, Gemini calls, ffmpeg rendering and the dashboard. Standard library only (no pip step).
# Build context is this folder:  docker compose build worker   (or: ./trendvn build)
FROM python:3.12-slim

ARG VERSION=dev
LABEL org.opencontainers.image.title="trendvn-worker" \
      org.opencontainers.image.description="TrendVN worker: queue, rules, Gemini, ffmpeg, dashboard" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TRENDVN_DATA=/data

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/ /app/

# Runs as the host user's uid/gid (compose sets `user:`) so files in ./data/worker stay yours; 1000 is the fallback.
USER 1000:1000
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"
CMD ["python", "-m", "trendvn_worker"]
