# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS builder

WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

ENV PORT=8080 \
    API_UPSTREAM=http://api:8080

COPY docker/frontend.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /src/frontend/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget --spider -q "http://127.0.0.1:${PORT}/healthz"
