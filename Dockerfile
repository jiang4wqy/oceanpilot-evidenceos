# OceanPilot EvidenceOS — one-command server image (synthetic prototype).
#
#   docker build -t oceanpilot-evidenceos .
#   docker run --rm -p 8000:8000 oceanpilot-evidenceos
#   # then: curl http://127.0.0.1:8000/health
#
# Serves the core API on 0.0.0.0:8000 with synthetic data only. Feishu / live
# model stay off unless their env vars are supplied (see config.env.example).
FROM python:3.12-slim

WORKDIR /app

# Install runtime deps first (better layer caching), then the package.
COPY pyproject.toml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install . && mkdir -p /app/work

ENV OCEANPILOT_DB_PATH=/app/work/oceanpilot.db
EXPOSE 8000

CMD ["python", "-m", "oceanpilot.bootstrap"]
