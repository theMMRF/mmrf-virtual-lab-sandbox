FROM node:24.18.1-bookworm-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run prepare
ENV GUPPY_PORT=80
CMD ["node", "dist/server/server.js"]
