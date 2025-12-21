# Command Reference

This page summarizes BradBot’s slash commands. For full details see `docs/commands.md`.

## Admin (`/admin …`)

- **menu / panel** – interactive settings (panel posts a persistent message).
- **sync** – force slash-command sync (`scope: global|guild`). Text fallback: `:resync`.
- **tools loadboosterroles / saveboosterrole** – manage saved booster roles.
- **tools autorole** – configure trigger-role automations.
- **tools channelrestriction / messagemirror / conditionalrole** – channel gates, message mirroring, conditional roles.
- **maintenance assignlvl0 / kickunverified** – clean up level roles and unverified members.
- **sql / tasklogs / auditlog** – bot-owner diagnostics.

## Issues (`/issues panel`)

Posts a button that opens a modal with:
- Title, description
- Submission type dropdown:
  - Bug → GitHub issue (`bug` label)
  - Enhancement → GitHub issue (`enhancement` label)
  - Question → GitHub Discussion (Q&A)
  - General Discussion → GitHub Discussion (General)

Discussion category IDs are auto-resolved (override via `GITHUB_DISCUSSION_CATEGORY_*`).

## Polls (`/poll …`)

- **create** – build a text-response poll (requires *Create Polls* permission).
- **results / stats / wordcloud** – view responses, statistics, and word clouds.
- **toggle_show_responses / close / reopen / refresh / list** – manage presentation and lifecycle.

## Link Tools (`/link …`)

- **edit** – supply the bot message link, edit the full text inside a modal. The update is reprocessed through link replacement; `-# …` embed helper lines are preserved.
- **delete** – delete your own replaced message (bot checks the mention matches you).

## Voice (`/voice …`)

- **join / leave** – manage the VC connection.
- **tts** – queue Polly TTS with optional `voice`, `engine`, `language`, `announce_author`, `post_text`.
- **show_tts_options / filter_voices / debug_tts** – browse voices or debug audio.

## Conversion (`/convert …`)

- **testosterone, temperature, length, weight, timezone, shoe** – utility conversions; shoe conversion handles men/women and multiple regions.

## Utility (`/utility …`)

- **remind** – natural-language reminders (DMs you).
- **timer** – visible countdown timer.
- **refresh_cookies** – refresh YouTube cookies used for media downloads.

## Alarm (`/alarm …`)

- **set** – fully-configurable alarm (text/TTS/tone, repeat, interval, timezone).
- **list / cancel** – manage alarms created by the guild.

## Emoji (`/emoji …`)

- **copy / from_attachment / reaction / upload** – ingest emoji/stickers from messages, attachments, or URLs.
- **db save / load / list / saveServer / delete** – manage the saved emoji catalog.
- **rename / remove** – edit or delete server emoji/stickers.

## Starboard (`/starboard …`)

- **set/list/delete** – manage hall-of-fame boards per channel/emoji/threshold (with NSFW toggles).
- **lock** – force a specific message into a board immediately.
- **block/unblock** – exclude or re-allow individual messages even if they hit the threshold.
- **top** – show the most-starred posts for a board.

## Booster (`/booster role …`)

- **color** – set solid/gradient/holographic colors with multiple hex inputs.
- **label** – rename your booster role.
- **icon** – set a role icon from URL (download/validation handled).

## Settings (`/settings …`)

- **menu** – user-level settings UI.
- **sendpings / notify** – toggle whether your replies ping others or send you notifications.

## Standalone Slash Commands

- **/echo** – repeat a message (optional `allow_mentions`; when off, the output is sent silently and mentions are suppressed).
- **/timestamp** – generate Discord timestamps from date/time input.

Need more specifics? Check `docs/commands.md` in the repo or update this page with new features.
