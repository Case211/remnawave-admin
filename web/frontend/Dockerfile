# Remnawave Admin Web Panel - Frontend Dockerfile

# Build stage - use slim (Debian) instead of alpine for stable npm behavior
FROM node:20-slim AS build

WORKDIR /app

# Increase Node.js memory limit to prevent npm OOM crashes
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies and verify vite binary exists
RUN npm ci --no-audit --no-fund && \
    test -f node_modules/.bin/vite && echo "vite OK" || \
    (echo "ERROR: vite not found after npm ci" && ls node_modules/.bin/ && exit 1)

# Copy source code, public assets, and configs
COPY src ./src
COPY public ./public
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json postcss.config.js tailwind.config.js ./

# Build (no VITE_* args needed — config is injected at runtime via config.js)
RUN npm run build

# Production stage - minimal nginx image
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-secret.conf.template /etc/nginx/nginx-secret.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# NOTE: nginx requires root to bind port 80. To run as non-root, switch to port
# 8080 and add "USER nginx" here. Skipped for now to avoid breaking the deployment.
EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
