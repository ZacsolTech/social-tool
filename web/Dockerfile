# Klypsy website (Next.js) - built by Railway from the /web folder.
FROM node:24-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Read at build time: the /api proxy target and the public site URL (sitemap, canonical links).
ARG API_ORIGIN
ARG NEXT_PUBLIC_SITE_URL
ENV API_ORIGIN=$API_ORIGIN NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
RUN npm run build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app ./
EXPOSE 3000
CMD ["sh", "-c", "exec node node_modules/next/dist/bin/next start -p ${PORT:-3000} -H 0.0.0.0"]
