FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

WORKDIR /app

# Prevent interactive prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11, pip, and system dependencies required for psycopg2
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default python
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Upgrade pip
RUN python3.11 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Install PyTorch with CUDA 12.4 support (must be done before requirements.txt)
RUN python3.11 -m pip install --no-cache-dir --default-timeout=100 \
    torch==2.2.1 --index-url https://download.pytorch.org/whl/cu124

# Copy the requirements and install remaining dependencies
COPY requirements.txt .
RUN python3.11 -m pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create a non-root user for security best practices
RUN useradd -m celeryuser
RUN chown -R celeryuser:celeryuser /app
USER celeryuser
