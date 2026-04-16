FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY package.json package-lock.json vite.config.js vitest.setup.js ./
COPY index.html ./
COPY src ./src
RUN npm ci && npm run build

FROM python:3.11-slim

# Install Chromium and its dependencies for headless PDF generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
COPY --from=frontend-build /frontend/dist ./dist

# Ensure the data directory exists (will be overridden by volume mount in prod)
RUN mkdir -p /app/data

ARG APP_VERSION=1.10.1
ENV APP_VERSION=$APP_VERSION

EXPOSE 8080
CMD ["python", "server.py"]
