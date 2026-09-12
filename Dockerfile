FROM node:22-alpine AS frontend

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.14-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app/backend

COPY backend/pyproject.toml ./
RUN uv sync --no-dev

COPY backend/app ./app
COPY --from=frontend /app/frontend/out ./app/static
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
