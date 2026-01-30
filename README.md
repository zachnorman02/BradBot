# BradBot

BradBot is a feature-rich Discord bot that powers moderation tools, boosters, polls, TTS utilities, and GitHub integrations across multiple communities.

## Highlights

- **Admin automation**: interactive settings panels, conditional roles, booster-role management, and `/admin sync` to refresh slash commands instantly.
- **Community engagement**: GitHub issue forms, advanced polls (stats, word clouds, persistent panels), reminder/timer utilities, and an `/echo` helper.
- **Counting channel**: configurable counting channel with math expressions, anti-double-posting, penalty role (24h), auto-reset on mistakes, and admin controls for next number/reset/disable.
- **Link control**: `/link edit` and `/link delete` let users fix or remove the bot’s link-replacement posts without staff intervention.
- **Starboards**: Multi-board hall-of-fame powered by reactions (`/starboard set/list/delete/lock/block/top`) with per-emoji thresholds and NSFW filters.
- **Voice & TTS**: Polly-backed `/voice tts` queue with default voice/language selection plus `/voice filter_voices`, `/voice join/leave`, and `/voice show_tts_options`.
- **Conversion suite**: `/convert` commands for testosterone calculations, temperature/length/weight/liquids/timezones, and an international shoe-size converter that supports men/women with half-size rounding.
- **Secrets-aware deployment**: Automatically hydrates sensitive values from AWS Secrets Manager (`BradBot/creds`) so tokens never live in plain text on the box.

## Documentation

- [Feature reference](docs/README.md)
- [Command reference](docs/commands.md)
- [Local development guide](docs/local-development.md)
- [Deployment & operations](docs/deployment.md)

## Quick Start (Local Development)

```bash
git clone https://github.com/zachnorman02/BradBot.git
cd BradBot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your DISCORD_TOKEN
docker-compose up -d  # Start PostgreSQL
python scripts/migrate.py migrate
python main.py
```

Use `/admin sync` or the owner-only `:resync` text command whenever you change slash command definitions to ensure Discord picks them up immediately.

## Deployment Notes

- Production instances run via `systemd` (`bradbot.service`) on AWS Lightsail with Aurora DSQL (PostgreSQL-compatible serverless database).
- Environment configuration is managed via `.env` file (not tracked in git) containing `DISCORD_TOKEN`, database credentials, AWS credentials, and other sensitive values.
- Optional: Store frequently-changing secrets in AWS Secrets Manager (`SECRETS_MANAGER_ID=BradBot/creds`) - the bot will automatically fetch and merge them at startup.
- Database uses IAM authentication for enhanced security. Lightsail requires IAM user credentials (access keys) since it doesn't support IAM roles.
- Polls, reminders, boosters, and conditional roles rely on background tasks in `core/tasks.py`. Restarting the bot will respawn tasks automatically.

See the docs directory for full instructions, troubleshooting tips, and command-by-command breakdowns.
