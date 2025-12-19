# BradBot Documentation

Welcome to BradBot’s documentation hub. Use these pages to get set up quickly, understand the available commands, and keep production deployments healthy.

## Quick Links

- [Local development](local-development.md)
- [Deployment & operations](deployment.md)
- [Command reference](commands.md)
- [Feature reference](#feature-reference)

## Feature Reference

### Admin & Ops
- `/admin menu` / `/admin panel` — interactive guild configuration, with a persistent panel option.
- `/admin sync` — force Discord to refresh slash commands (global or guild scope).
- `/admin tools …` — utilities for autoroles, channel restrictions, message mirroring, and booster-role management.
- Text command `:resync` — same as `/admin sync`, handy when slash commands fail to register.

### Community Tools
- `/issues panel` — GitHub issue/discussion modal that can open traditional issues or Discussions (Q&A/general) directly in `GITHUB_REPO`; discussion categories are auto-resolved via the GitHub API.
- `/poll …` — create, refresh, reopen, and analyze rich polls (word clouds, stats, toggle response visibility).
- `/settings …` — let members control notifications and ping preferences via an ephemeral panel.
- `/convert …` — temperature/length/weight/timezone utilities plus testosterone calculators and a robust shoe-size converter (men/women, multi-region, half-size rounding).

### Voice & Fun
- `/voice tts` — Polly-backed TTS with queues, language/voice defaults, and optional sender call-outs.
- `/voice filter_voices`, `/voice join/leave`, `/voice show_tts_options` — voice-session management.
- `/echo` (slash) and `:echo` (text) — have BradBot repeat a message with optional mention safety.
- `/utility remind` & `/utility timer` — personal reminders and timers.

### Automation & Background Tasks
- Booster role restore/checks, conditional roles, reminders/timers, and poll refresh tasks live in `core/tasks.py`.
- Task logs are queryable via `/admin tasklogs`.

## Secrets & Configuration

- BradBot loads `.env`, then automatically fetches AWS Secrets Manager secret `BradBot/creds` (override via `SECRETS_MANAGER_ID` or `AWS_SECRET_ID`) to hydrate sensitive values like `DISCORD_TOKEN` and `GITHUB_TOKEN`.
- Production deployments (systemd service) should set `SECRETS_MANAGER_ID` and ensure the EC2 role has `secretsmanager:GetSecretValue` on that secret.

For deeper instructions, continue to the development and deployment guides.
