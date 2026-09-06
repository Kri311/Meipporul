FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for psycopg2 and building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create a non-root user for security best practices
RUN useradd -m celeryuser
USER celeryuser
