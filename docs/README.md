# BradBot Wiki

Welcome! This wiki mirrors the most important information about running and extending BradBot so teammates can self-serve without digging through the repository.

## 📚 Quick Links

- [Local Development](Local-Development) – set up Python, Postgres, and the `.env`.
- [Deployment & Operations](Deployment) – systemd service, Secrets Manager, syncing commands.
- [Command Reference](Commands) – every slash command group with parameters + tips.

## ✨ Highlights

- **Admin automation:** interactive `/admin menu`, persistent panels, autoroles/conditional roles, `/admin sync`, and text `:resync`.
- **Community engagement:** `/issues panel` (issues or discussions), feature-rich `/poll` suite, reminders/timers, `/echo`, `/link edit|delete`.
- **Counting channel:** `/admin tools counting_config` + `/counting_set_number` to run a counting game with math expressions, anti-double-posting, penalty role (24h), and reset/disable controls.
- **Voice & TTS:** `/voice tts` with queues, default voices, `/voice filter_voices`, `/voice join/leave`, `/voice show_tts_options`.
- **Conversion tools:** `/convert testosterone/temperature/length/weight/timezone/shoe`.
- **Secrets-aware deployment:** loads `.env` then automatically hydrates secrets from AWS Secrets Manager (`BradBot/creds` by default).

## 🚀 Quick Start

```bash
git clone https://github.com/<owner>/BradBot.git
cd BradBot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit with tokens + DB config
python scripts/migrate.py
python main.py
```

After you change slash commands, run `/admin sync` or `:resync` so Discord sees the updates.

## 🛟 Getting Help

- Review the [Command Reference](Commands) for parameters and behaviors.
- Check [Local Development](Local-Development) and [Deployment](Deployment) for environment setup, secrets, and troubleshooting tips.
- If you add or change commands, update the wiki/docs and remind admins to run `/admin sync`.

Happy hacking!
