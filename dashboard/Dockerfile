# Build do dashboard e entrega por nginx.
FROM node:22-alpine AS build
WORKDIR /app

# package*.json primeiro: a camada de dependencias so refaz quando elas mudam.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
