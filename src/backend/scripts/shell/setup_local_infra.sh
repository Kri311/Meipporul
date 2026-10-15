#!/bin/bash
cd "$(dirname "$0")/../../../.."

set -e
echo " Veritas Lens: Local Infrastructure Setup (No Docker)     "

echo "[1/4] Installing dependencies..."
sudo apt-get update
sudo apt-get install -y curl ca-certificates gnupg lsb-release

echo "[2/4] Adding PostgreSQL repository for PG 16..."
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list

echo "[3/4] Installing PostgreSQL 16, pgvector, and Redis..."
sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-16-pgvector redis-server

echo "[4/4] Configuring the veritas_lens database..."
# Run postgres commands as the postgres user
sudo -u postgres psql -c "CREATE USER veritas_admin WITH PASSWORD 'veritas_secret_password';" || echo "User might already exist."
sudo -u postgres psql -c "CREATE DATABASE veritas_lens OWNER veritas_admin;" || echo "Database might already exist."
sudo -u postgres psql -d veritas_lens -c "CREATE EXTENSION IF NOT EXISTS vector;"
sudo -u postgres psql -d veritas_lens -c "GRANT ALL PRIVILEGES ON DATABASE veritas_lens TO veritas_admin;"
sudo -u postgres psql -d veritas_lens -c "ALTER SCHEMA public OWNER TO veritas_admin;"

echo " Setup Complete! "
echo " - Redis is running on localhost:6379"
echo " - PostgreSQL is running on localhost:5432 (DB: veritas_lens)"
echo " "
echo " Next steps: "
echo " 1. Use your pyenv virtual environment (or create one: python3 -m venv venv && source venv/bin/activate)"
echo " 2. Install reqs: pip install -r requirements.txt"
echo " 3. Run the system: python main.py"
