# Local Development

BradBot targets Python 3.10+ and PostgreSQL. You can run the database via Docker (recommended) or a local instance.

## Prerequisites
- Python 3.10+
- Discord bot token
- PostgreSQL 13+ (Docker or local install)

## 1. Clone & Install
```bash
git clone https://github.com/your-org/BradBot.git
cd BradBot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure Environment
Copy `.env.example` to `.env` and edit the values. For local work you typically want:
```env
DISCORD_TOKEN=your_local_dev_token

DB_HOST=localhost
DB_PORT=5432
DB_NAME=bradbot
DB_USER=bradbot
DB_PASSWORD=bradbot_dev
USE_IAM_AUTH=false
```

> **Secrets Manager?** In production BradBot automatically loads AWS Secrets Manager secret `BradBot/creds`. Locally you can skip it (leave `SECRETS_MANAGER_ID` empty) or point to a dev secret if you have one.

## 3. Start PostgreSQL
### Option A: Docker
```bash
docker-compose up -d
```

### Option B: Local Postgres
Install Postgres, create a database/user, and ensure the credentials match your `.env`.

## 4. Run Migrations
```bash
python scripts/migrate.py
```

## 5. Launch the Bot
```bash
python main.py
```

Use Discord’s `/sync` or the local `:sync`/`:resync` commands if you add new slash commands during development.

## Common Issues

| Problem | Fix |
| --- | --- |
| `psycopg2.OperationalError` | Verify Postgres is running; check host/port/user/password. |
| Slash command changes not showing | Run `:resync` in your dev guild or restart the bot. |
| Missing env vars | Ensure `.env` exists and matches `.env.example`. |

## Useful Commands
```bash
# Inspect tables (Docker example)
docker-compose exec postgres psql -U bradbot -d bradbot
\dt main.*

# Drop & recreate database
docker-compose down -v && docker-compose up -d
python scripts/migrate.py
```
