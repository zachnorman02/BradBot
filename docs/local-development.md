# Local Development

BradBot targets Python 3.10+ and PostgreSQL. You can run Postgres in Docker (recommended) or locally.

## 1. Prerequisites

- Python 3.10 or newer
- Discord bot token (dev bot)
- PostgreSQL 13+ (Docker or local install)
- `ffmpeg` (for voice/TTS)

## 2. Clone & Install

```bash
git clone https://github.com/<owner>/BradBot.git
cd BradBot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure Environment

Copy `.env.example` to `.env` and edit:

```env
DISCORD_TOKEN=your_dev_bot_token

DB_HOST=localhost
DB_PORT=5432
DB_NAME=bradbot
DB_USER=bradbot
DB_PASSWORD=bradbot_dev
USE_IAM_AUTH=false
```

> Tip: production loads AWS Secrets Manager (`SECRETS_MANAGER_ID=BradBot/creds`) automatically, but for local dev you usually keep everything in `.env`.

## 4. Start PostgreSQL

### Docker
```bash
docker-compose up -d
```

### Local install
- macOS: `brew install postgresql@16 && brew services start postgresql@16`
- Ubuntu: `sudo apt install postgresql postgresql-contrib`

Create the database/user if necessary.

## 5. Run Migrations

```bash
python scripts/migrate.py
```

## 6. Run BradBot

```bash
python main.py
```

Invite your dev bot to a test guild and run `/admin sync` (or `:resync`) after you change slash commands.

## 7. Troubleshooting

| Issue | Fix |
| --- | --- |
| `psycopg2.OperationalError` | Ensure Postgres is running; verify host/port/user/password in `.env`. |
| Slash command changes not showing | Run `/admin sync` or `:resync` in your dev guild. |
| Missing env vars | Double-check `.env` lives next to `main.py` and is loaded before `load_secret_env()`. |
| Voice/TTS errors | Confirm `ffmpeg` is installed and on your `PATH`. |

## 8. Useful Commands

```bash
# Inspect DB tables (Docker example)
docker-compose exec postgres psql -U bradbot -d bradbot
\dt main.*

# Drop & recreate DB
docker-compose down -v && docker-compose up -d
python scripts/migrate.py
```
