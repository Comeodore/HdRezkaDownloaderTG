FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /fe/dist ./static
ENV FRONTEND_DIR=/app/static
EXPOSE 9970
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9970", "--no-access-log"]
