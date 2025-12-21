# Deployment & Operations

BradBot typically runs on an EC2 instance under `systemd`. This page captures the key steps.

## 1. Environment Setup

1. Install system packages: Python 3.10, ffmpeg, git, Postgres client, build tools.
2. Clone the repo to `/home/ubuntu/bradbot` (or similar) and create a virtualenv.
3. Copy `.env.example` to `.env` for non-sensitive defaults (DB host, region, etc.).
4. **Secrets Manager:** store sensitive values—`DISCORD_TOKEN`, `GITHUB_TOKEN`, etc.—in AWS Secrets Manager secret `BradBot/creds` as JSON. BradBot automatically loads `.env` first, then overlays secrets from this secret (override via `SECRETS_MANAGER_ID`).
5. Attach or update the EC2 IAM role to grant `secretsmanager:GetSecretValue` on `BradBot/creds`.

## 2. systemd Service

`/etc/systemd/system/bradbot.service` example:

```
[Unit]
Description=BradBot Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/bradbot
Environment=PATH=/home/ubuntu/bradbot/venv/bin:/usr/bin
Environment=SECRETS_MANAGER_ID=BradBot/creds
Environment=AWS_REGION=us-east-1
Environment=GITHUB_REPO=zachnorman02/BradBot
ExecStart=/home/ubuntu/bradbot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Reload + enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bradbot
journalctl -u bradbot -f
```

## 3. Syncing Commands

When you change slash commands, run `/admin sync` (global or guild scope) or the text command `:resync [global|guild]`. Always watch logs for `Failed to upload commands` errors.

## 4. Updating Secrets

1. Edit the JSON secret in Secrets Manager.
2. Restart the service: `sudo systemctl restart bradbot`.
3. (Optional) `/admin sync` if command signatures changed.

## 5. Troubleshooting

| Problem | Action |
| --- | --- |
| Service won’t start | `journalctl -u bradbot -n 200` for stack traces; verify IAM permissions for Secrets Manager. |
| Slash commands missing | `/admin sync` or `:resync`. Remember Discord caches global commands for up to an hour. |
| “Unknown interaction” errors | Ensure interactions are deferred/responded to within 3 seconds; look for blockers in logs. |
| Database auth failures | Confirm `DB_HOST`, `DB_USER`, and IAM auth vs password (`USE_IAM_AUTH`). |
| Voice/TTS issues | Ensure `ffmpeg` is installed and the `BRADBOT_TTS_PROVIDER`/voice defaults are set. |

## 6. Background Tasks

- Poll auto-refresh/close, reminders, timers, conditional roles, booster checks are in `core/tasks.py`.
- Use `/admin tasklogs` (bot owner only) to inspect the last N runs.

## 7. Useful Commands

```bash
# Detect running service
systemctl status bradbot

# Tail logs
journalctl -u bradbot -f

# Manual sync fallback
:resync guild
```

Need to update docs? Edit the wiki or `/docs` in the repo and link them here.
