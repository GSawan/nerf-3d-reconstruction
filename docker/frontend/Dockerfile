# ─────────────────────────────────────────────────────────────────────────────
# Neo3D — Frontend Dockerfile
# Service: Next.js UI (upload page + Three.js viewer)
#
# Why multi-stage build?
#   Stage 1 (builder): Full Node.js environment to compile TypeScript & Next.js
#   Stage 2 (runner):  Minimal Node.js — only the compiled output + runtime
#
#   Result: ~80MB image vs ~1.2GB if we copied node_modules
#
# Why node:20-alpine?
#   - Alpine Linux = 5MB base (vs 900MB Ubuntu)
#   - node:20-alpine = ~170MB — perfect for production
# ─────────────────────────────────────────────────────────────────────────────

# ─── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first — Docker caches this layer
# Only re-installs when package.json or lockfile changes
COPY frontend/package*.json ./

# ci (not install) = faster, reproducible, uses lockfile exactly
RUN npm ci

# Copy source code
COPY frontend/ .

# Set backend URL for the build — Next.js rewrites use this at runtime not build time
# But NEXT_PUBLIC_* vars are baked in at build, so we pass a placeholder
ENV NEXT_PUBLIC_API_URL=""

# Build the Next.js standalone output
# 'standalone' mode is configured in next.config.ts
RUN npm run build

# ─── Stage 2: Production Runner ───────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Create non-root user
RUN addgroup -g 1001 -S neo3d && \
    adduser -S neo3d -u 1001 -G neo3d

# Copy the standalone output — this is ALL that's needed to run
COPY --from=builder --chown=neo3d:neo3d /app/.next/standalone ./
COPY --from=builder --chown=neo3d:neo3d /app/.next/static ./.next/static
COPY --from=builder --chown=neo3d:neo3d /app/public ./public

USER neo3d

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Standalone mode generates server.js — the production entrypoint
CMD ["node", "server.js"]
