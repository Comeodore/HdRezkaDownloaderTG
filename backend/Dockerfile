FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIR=/app/static
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /fe/dist ./static
EXPOSE 9970
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9970/api/health', timeout=4)"
# graceful-shutdown timeout: open SSE streams would otherwise block the lifespan
# shutdown that persists the download queue
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9970", "--no-access-log", "--timeout-graceful-shutdown", "5"]
