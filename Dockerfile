FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-workspaces
COPY config.json ./
COPY src ./src
ENV PORT=8099
EXPOSE 8099
CMD ["node", "src/server.mjs"]
