# Local Development Setup

This guide explains how to run BradBot locally for development and testing.

## Prerequisites

- Python 3.10+
- Discord Bot Token
- PostgreSQL (local or Docker)

## Option 1: Docker PostgreSQL (Recommended)

### 1. Install Docker
- **macOS:** [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Linux:** `sudo apt install docker.io docker-compose`

### 2. Start PostgreSQL
```bash
docker-compose up -d
```

This creates a PostgreSQL database with:
- Database: `bradbot`
- User: `bradbot`
- Password: `bradbot_dev`
- Port: `5432`

### 3. Configure Environment
Copy `.env.example` to `.env` and use these settings:
```env
DISCORD_TOKEN=your_discord_bot_token

DB_HOST=localhost
DB_PORT=5432
DB_NAME=bradbot
DB_USER=bradbot
DB_PASSWORD=bradbot_dev
USE_IAM_AUTH=false
```

### 4. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run Migrations
```bash
python scripts/migrate.py
```

### 6. Start the Bot
```bash
python main.py
```

### 7. Stop PostgreSQL (when done)
```bash
docker-compose down
```

---

## Option 2: Local PostgreSQL

### 1. Install PostgreSQL
- **macOS:** `brew install postgresql@16 && brew services start postgresql@16`
- **Ubuntu/Debian:** `sudo apt install postgresql postgresql-contrib`
- **Windows:** [Download installer](https://www.postgresql.org/download/windows/)

### 2. Create Database
```bash
# macOS/Linux
createdb bradbot

# Or using psql
psql postgres
CREATE DATABASE bradbot;
\q
```

### 3. Configure Environment
Copy `.env.example` to `.env`:
```env
DISCORD_TOKEN=your_discord_bot_token

DB_HOST=localhost
DB_PORT=5432
DB_NAME=bradbot
DB_USER=your_postgres_username
DB_PASSWORD=your_postgres_password
USE_IAM_AUTH=false
```

### 4. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run Migrations
```bash
python scripts/migrate.py
```

### 6. Start the Bot
```bash
python main.py
```

---

## Troubleshooting

### Connection Refused
- **Docker:** Ensure container is running: `docker-compose ps`
- **Local:** Ensure PostgreSQL is running: `brew services list` (macOS) or `sudo systemctl status postgresql` (Linux)

### Migration Errors
- Drop and recreate database: `dropdb bradbot && createdb bradbot`
- Run migrations again: `python scripts/migrate.py`

### Import Errors
- Install dependencies: `pip install -r requirements.txt`
- Check Python version: `python --version` (should be 3.10+)

### Permission Denied
- Local PostgreSQL: Ensure your user has database creation privileges
- Docker: Ensure Docker daemon is running

---

## Database Schema

After running migrations, you'll have these tables:
- `schema_migrations` - Migration tracking
- `user_settings` - User preferences and reply notifications
- `guild_settings` - Server-wide settings
- `booster_roles` - Custom booster role configurations
- `polls` - Text-based poll data
- `poll_responses` - User poll responses
- `reminders` - User reminder scheduling
- `timers` - User timer tracking
- `task_logs` - Automated task execution logs

---

## Development Tips

### View Database Contents
```bash
# Docker
docker-compose exec postgres psql -U bradbot -d bradbot

# Local
psql bradbot

# Useful queries
\dt main.*          -- List tables
SELECT * FROM main.guild_settings;
SELECT * FROM main.task_logs ORDER BY started_at DESC LIMIT 10;
```

### Reset Database
```bash
# Docker
docker-compose down -v
docker-compose up -d
python scripts/migrate.py

# Local
dropdb bradbot
createdb bradbot
python scripts/migrate.py
```

### Run Tests
```bash
pytest tests/
```
