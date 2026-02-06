# Remnawave Admin Web Panel - Frontend Dockerfile

# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install ALL dependencies (ensure devDependencies are included for build)
# NODE_ENV=development ensures devDependencies are installed
ENV NODE_ENV=development
RUN npm ci

# Copy source code
COPY . .

# Build arguments for environment variables
ARG VITE_API_URL
ARG VITE_WS_URL
ARG VITE_TELEGRAM_BOT_USERNAME

# Set environment variables for build
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL
ENV VITE_TELEGRAM_BOT_USERNAME=$VITE_TELEGRAM_BOT_USERNAME

# Build the application (uses local node_modules/.bin/tsc)
ENV NODE_ENV=production
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
