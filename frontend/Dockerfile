# ---- Étape 1 : build de l'application React/Vite ----
# IMPORTANT : node:20-bookworm-slim (Debian/glibc), PAS node:20-alpine (musl).
# Rollup (utilisé par Vite) installe un binaire natif différent selon la libc
# (@rollup/rollup-linux-x64-gnu vs ...-musl). Le fichier package-lock.json de ce
# projet a été généré sur un environnement glibc ; sur Alpine, npm peut échouer
# à résoudre le binaire musl correspondant à cause d'un bug connu de l'écosystème
# npm/Rollup, ce qui fait planter `vite build` avec une erreur trompeuse
# ("Could not resolve entry module index.html") qui n'a rien à voir avec le
# vrai problème. Rester sur une base glibc pour le build évite ce piège.
FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# VITE_API_BASE est figé au moment du build (Vite remplace import.meta.env au build).
# Pour changer l'URL de l'API sans rebuild, surcharger via un .env avant `docker compose build`.
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE
ARG VITE_MAPBOX_TOKEN=
ENV VITE_MAPBOX_TOKEN=$VITE_MAPBOX_TOKEN
RUN npm run build

# ---- Étape 2 : service statique ----
# (l'étape de service n'exécute aucun npm/node, Alpine reste pertinent ici :
# image finale légère, aucun risque de conflit musl/gnu côté Nginx)
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
