FROM node:24.18.1-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
COPY scripts ./scripts
RUN npm ci
COPY . .
COPY --from=sandbox scripts/sanitize_frontend.mjs /tmp/sanitize_frontend.mjs
RUN node /tmp/sanitize_frontend.mjs /app
RUN rm -f .env .env.local .env.production .env.production.local .env.development .env.development.local
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_SYNTHETIC_SANDBOX=1
RUN npm run build
FROM node:24.18.1-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
COPY --from=build /app/config ./config
USER node
CMD ["node", "server.js"]
