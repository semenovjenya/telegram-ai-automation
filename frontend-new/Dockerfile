# Node 24.18.0 LTS (multi-arch manifest pinned for reproducible builds).
FROM node:26.13.0-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216 AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

# Copy package files first for better caching
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code (node_modules excluded via .dockerignore)
COPY . .

# Build the Next.js application
RUN NODE_ENV=production npm run build

# Production stage uses the identical runtime image.
FROM node:26.13.0-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216 AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# The standalone server needs only the Node runtime. Remove package managers
# (and their transitive networking clients) from the final attack surface.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
    && addgroup -S -g 1001 nodejs \
    && adduser -S -D -H -u 1001 -G nodejs nextjs

# Copy necessary files from builder
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 7777

ENV PORT=7777
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
