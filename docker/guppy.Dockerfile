FROM node:24.18.1-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run prepare

FROM node:24.18.1-bookworm-slim
WORKDIR /app
# Public source tests/mock fixtures and Git history stay in the build stage.
COPY --from=build /app/dist/server ./dist/server
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
ENV GUPPY_PORT=80
USER node
CMD ["node", "dist/server/server.js"]
