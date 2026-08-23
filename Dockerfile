# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr,
# so logs show up immediately in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install OS packages needed to build/run psycopg (PostgreSQL driver).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first so this layer is cached unless
# requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# Secrets must be provided at runtime (env vars / mounted files), never
# baked into the image. See .env.example for the variables this app needs.
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
