FROM python:3.9-slim

WORKDIR /app

# Install system packages
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    postgresql-server-dev-all \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Start script
COPY start.sh .
RUN chmod +x /app/start.sh  # Use full path
RUN ls -la /app/start.sh    # For permission verification

# Copy project files - prevent nested directory structure
COPY adoorback /app/adoorback
COPY docker-compose.* .
COPY .env* .
COPY .dockerignore .
COPY .gitignore .

# Install Python packages
WORKDIR /app/adoorback
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install uwsgi

# Maintain working directory
WORKDIR /app/adoorback

# Port settings
EXPOSE 8000

# Environment variable settings
ENV PYTHONUNBUFFERED=1

# Environment variables for superuser creation (needs modification for actual deployment)
ENV DJANGO_SUPERUSER_USERNAME=admin
ENV DJANGO_SUPERUSER_EMAIL=admin@example.com
ENV DJANGO_SUPERUSER_PASSWORD=adminpassword

CMD ["/app/start.sh"]