# Optional self-hosted API. Build from the repository root:  docker compose up
FROM python:3.12-slim
WORKDIR /app
COPY pipeline/requirements.txt req/pipeline.txt
COPY server/requirements.txt req/server.txt
RUN pip install --no-cache-dir -r req/pipeline.txt -r req/server.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
