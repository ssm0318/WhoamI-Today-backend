FROM python:3.9

WORKDIR /app

# Install system packages
# Note: `ant` is required to build JPype1 from source (transitive dep of konlpy)
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    postgresql-server-dev-all \
    libpq-dev \
    libev-dev \
    libevent-dev \
    default-jdk \
    ant \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    ffmpeg \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip "setuptools<70.0.0" wheel

# Install Python packages FIRST (cached unless requirements change)
COPY adoorback/requirements.txt adoorback/requirements.lock* /app/adoorback/
WORKDIR /app/adoorback
RUN if [ -f requirements.lock ]; then \
      pip install --no-cache-dir -r requirements.lock; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi
RUN pip install uwsgi

# Copy project files
WORKDIR /app
COPY start.sh .
RUN chmod +x /app/start.sh
COPY adoorback /app/adoorback
COPY docker-compose.* ./
COPY .env* ./
COPY .dockerignore ./
COPY .gitignore ./

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
