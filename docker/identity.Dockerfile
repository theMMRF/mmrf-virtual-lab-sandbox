FROM node:24.18.1-bookworm-slim
WORKDIR /app
COPY identity ./identity
COPY generated ./generated
USER node
ENV SYNTHETIC_SANDBOX=1 PORT=8080
CMD ["node", "identity/server.mjs"]
