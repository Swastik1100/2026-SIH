# Stage 1: Build the React app
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Set the backend API URL for the production build
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

# Copy the built app
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config to handle React Router (client-side routing)
RUN printf 'server {\n\
    listen 80;\n\
    server_name localhost;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
\n\
    # React Router: serve index.html for all routes\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
\n\
    # API proxy to backend (when running in Docker compose)\n\
    location /api/ {\n\
        proxy_pass http://backend:8000/;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
    }\n\
\n\
    gzip on;\n\
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
