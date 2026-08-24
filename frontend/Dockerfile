# The frontend is a static bundle. Vite inlines VITE_* variables at BUILD time,
# so the API URL is baked into the JavaScript and must be supplied here rather
# than at container start.

FROM node:20-alpine AS builder

WORKDIR /build

# Copy manifests first so the dependency layer is cached independently of
# source changes -- npm ci re-runs only when the lockfile moves.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build


FROM nginx:1.27-alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
