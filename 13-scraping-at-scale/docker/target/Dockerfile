FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.32"

COPY app.py /app.py

ENV CATALOG_PATH=/data/catalog.json
ENV TARGET_SPEC_PATH=/data/target-spec.json

CMD ["uvicorn", "app:app", "--app-dir", "/", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
