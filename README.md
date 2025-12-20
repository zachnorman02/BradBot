# BradBot

BradBot is a feature-rich Discord bot that powers moderation tools, boosters, polls, TTS utilities, and GitHub integrations across multiple communities.

## Highlights

- **Admin automation**: interactive settings panels, conditional roles, booster-role management, and `/admin sync` to refresh slash commands instantly.
- **Community engagement**: GitHub issue forms, advanced polls (stats, word clouds, persistent panels), reminder/timer utilities, and an `/echo` helper.
- **Link control**: `/link edit` and `/link delete` let users fix or remove the bot’s link-replacement posts without staff intervention.
- **Voice & TTS**: Polly-backed `/voice tts` queue with default voice/language selection plus `/voice filter_voices`, `/voice join/leave`, and `/voice show_tts_options`.
- **Conversion suite**: `/convert` commands for testosterone calculations, temperature/length/weight/timezones, and an international shoe-size converter that supports men/women with half-size rounding.
- **Secrets-aware deployment**: Automatically hydrates sensitive values from AWS Secrets Manager (`BradBot/creds`) so tokens never live in plain text on the box.

## Documentation

- [Feature reference](docs/README.md)
- [Command reference](docs/commands.md)
- [Local development guide](docs/local-development.md)
- [Deployment & operations](docs/deployment.md)

## Quick Start

```bash
git clone https://github.com/your-org/BradBot.git
cd BradBot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit with your tokens + DB config
python scripts/migrate.py
python main.py
```

Use `/admin sync` or the owner-only `:resync` text command whenever you change slash command definitions to ensure Discord picks them up immediately.

## Deployment Notes

- Production instances should run via `systemd` (`bradbot.service`) and set `SECRETS_MANAGER_ID=BradBot/creds`.
- Grant the EC2 IAM role `secretsmanager:GetSecretValue` on that secret; BradBot will fetch `DISCORD_TOKEN`, `GITHUB_TOKEN`, and other sensitive values automatically at startup.
- Polls, reminders, boosters, and conditional roles rely on the background tasks in `core/tasks.py`. Restarting the bot will respawn the tasks if needed.

See the docs directory for full instructions, troubleshooting tips, and command-by-command breakdowns.
