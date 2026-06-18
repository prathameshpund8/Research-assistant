# ===== Autonomous Research Assistant — frontend image =====

# --- Stage 1: build the Angular app ---
FROM node:22-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- Stage 2: serve with nginx ---
FROM nginx:1.27-alpine

# SPA + API/SSE reverse-proxy config.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Angular's application builder emits to dist/<project>/browser.
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
