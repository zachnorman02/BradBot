# Deployment & Operations

BradBot is typically deployed on an EC2 instance managed by `systemd`. This guide covers configuration, secrets, and common operational tasks.

## 1. Environment & Secrets

1. Install system dependencies (Python 3.10, ffmpeg, git, Postgres client).
2. Clone the repo to `/home/ubuntu/bradbot` (or your preferred path) and create a virtualenv.
3. Copy `.env.example` to `.env` for non-sensitive defaults (DB host, region, etc.).
4. **Secrets Manager**: Store sensitive values in AWS Secrets Manager secret `BradBot/creds` as JSON, e.g.
   ```json
   {
     "DISCORD_TOKEN": "abc",
     "GITHUB_TOKEN": "ghp_xyz",
     "OTHER_SECRET": "value"
   }
   ```
5. Ensure the instance role has `secretsmanager:GetSecretValue` on that secret. BradBot will load it automatically on startup (see `utils/secrets_manager.py`).

## 2. systemd Service

`bradbot.service` example:
```
[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/bradbot
Environment=PATH=/home/ubuntu/bradbot/venv/bin:/home/ubuntu/.deno/bin
Environment=SECRETS_MANAGER_ID=BradBot/creds
Environment=AWS_REGION=us-east-1
Environment=GITHUB_REPO=zachnorman02/BradBot
ExecStart=/home/ubuntu/bradbot/venv/bin/python main.py
Restart=always
```

Reload and enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bradbot
journalctl -u bradbot -f
```

## 3. Command Syncing

After code changes that modify slash commands:
- Run `/admin sync` (global or guild scope) or the text command `:resync [global|guild]`.
- Watch logs for `Failed to upload commands` errors; they usually indicate a validation/syntax issue.

## 4. Updating Secrets

1. Update the JSON secret in Secrets Manager.
2. Restart the service (`sudo systemctl restart bradbot`) so the new values load.
3. (Optional) Run `/admin sync` if the change impacts slash commands.

## 5. Troubleshooting

| Issue | Action |
| --- | --- |
| Service won’t start | `journalctl -u bradbot -n 200` for stack traces; confirm Secrets Manager access. |
| Unknown interaction errors | Ensure commands respond or defer within 3 seconds; look for blockers in logs. |
| Slash commands missing | Run `:resync` or `/admin sync`, reboot if Discord caches old signatures. |
| Database connection errors | Check IAM auth vs. password mode, verify env vars (DB host/user). |

## 6. Background Tasks

Located in `core/tasks.py`. If tasks stop running:
- Restart the bot to re-create loops.
- Check `/admin tasklogs` for failures.

## 7. Manual Utilities

- `/admin sql` and `/admin tasklogs` are bot-owner only.
- `scripts/migrate_role_rules.py` connects to Discord using the same secrets loader—ensure the environment variables/instance role are available when running manually.
