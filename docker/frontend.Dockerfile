# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

ENV PORT=8080 \
    API_UPSTREAM=http://api:8080 \
    NGINX_ENTRYPOINT_QUIET_LOGS=1

COPY docker/frontend.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --spider -q "http://127.0.0.1:${PORT}/healthz"

CMD ["nginx", "-g", "daemon off;"]
