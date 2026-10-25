FROM node:22-alpine

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY index.html vite.config.ts tsconfig.json ./
COPY src ./src
COPY .figma ./.figma

ENV PORT=8443
EXPOSE 8443
CMD ["pnpm", "dev"]
