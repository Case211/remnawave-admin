# Remnawave Admin Web Panel - Frontend Dockerfile

# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Increase Node.js memory limit to prevent npm OOM crashes
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies (npm install is more stable than npm ci under low memory)
RUN npm install --no-audit --no-fund

# Copy source code and configs
COPY src ./src
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json postcss.config.js tailwind.config.js ./

# Build arguments for environment variables
ARG VITE_API_URL
ARG VITE_WS_URL
ARG VITE_TELEGRAM_BOT_USERNAME

ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL
ENV VITE_TELEGRAM_BOT_USERNAME=$VITE_TELEGRAM_BOT_USERNAME

# Build
RUN npm run build

# Production stage - minimal nginx image
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
