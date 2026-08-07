# OceanPilot EvidenceOS — one-command server image (synthetic prototype).
#
#   docker build -t oceanpilot-evidenceos .
#   docker run --rm -p 8000:8000 oceanpilot-evidenceos
#   # then: curl http://127.0.0.1:8000/health
#
# Serves the core API on 0.0.0.0:8000 with synthetic data only. Feishu / live
# model stay off unless their env vars are supplied (see .env.example).
FROM python:3.12-slim

WORKDIR /app

# Install runtime deps first (better layer caching), then the package.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir -p /app/work

ENV OCEANPILOT_DB_PATH=/app/work/oceanpilot.db
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "oceanpilot.main:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000"]
