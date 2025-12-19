# Command Reference

This document catalogs BradBot’s major slash command groups, their parameters, and tips for usage. Optional parameters are marked accordingly.

## Admin (`/admin …`)

| Command | Parameters | Description |
| --- | --- | --- |
| `/admin menu` | — | Opens an ephemeral interactive settings view for the current guild. Requires administrator permissions. |
| `/admin panel` | — | Posts a persistent settings panel in the channel. Saves panel metadata so it restores after restarts. |
| `/admin sync` | `scope` (`global` or `guild`, default `global`) | Forces Discord to sync slash commands. Guild scope must be run inside a server. |
| `/admin tools loadboosterroles` | — | Scans boosters, finds their custom roles and saves them to the DB. Runs in-channel with an ephemeral summary. |
| `/admin tools saveboosterrole` | `role` (required), `user` (optional), `user_id` (optional) | Manually save a booster role to the DB. Use `user_id` if the owner left the server. |
| `/admin tools autorole` | `action` (`add`, `remove`, `list`, `check-all`), `rule_name`, `trigger_role`, `roles_to_add`, `roles_to_remove` | Create/update/delete/list automated role rules that run when a trigger role is added. Role lists are comma-delimited. |
| `/admin tools channelrestriction` | `action`, `channel`, `role`, `threshold`, `scope` | Configure channel access restrictions (full parameter set documented inline in `admin_commands.py`). |
| `/admin tools messagemirror` | `action`, `source_channel`, `target_channel`, `limit`, `sync_edits`, `sync_deletes` | Mirrors all messages between channels and keeps them synced. |
| `/admin tools conditionalrole` | `action`, `role`, `blocking_roles`, `deferral_roles` | Manage conditional roles with lists of blocking/deferral roles. |
| `/admin maintenance assignlvl0` | — | Assign “lvl 0” to every verified user without another level role. |
| `/admin maintenance kickunverified` | `dry_run` (bool) | Removes unverified members with no ticket after 30 days. Use `dry_run=true` to preview. |
| `/admin sql` | `query` | Bot-owner only: run arbitrary SQL and return results (truncated). |
| `/admin tasklogs` | `task_name`, `limit` | Bot-owner only: view recent background task executions. |
| `/admin auditlog` | `query` | Bot-owner only SQL-esque query against the guild audit log. |

### Legacy text commands
- `:resync [global|guild]` — Same as `/admin sync`, available to admins.
- `:sync`, `:clearcmds` — Owner-only conveniences retained for testing.

## Issues (`/issues panel`)

Creates a persistent panel with one “Submit” button. Modal fields:
- Title (required)
- Description (optional)
- Dropdown with four options:
  - Bug (issue, “bug” label)
  - Enhancement (issue, “enhancement” label)
  - Question (discussion, Q&A category)
  - General Discussion (discussion, General category)

Discussions categories are auto-detected via GitHub’s API each time someone submits (cached per repo). You can override via `GITHUB_DISCUSSION_CATEGORY_*` env vars if necessary.

## Polls (`/poll …`)

| Command | Parameters | Notes |
| --- | --- | --- |
| `/poll create` | Question, options (comma-separated), expiry (optional), anonymous toggle, channel override | Creates a text-response poll with buttons. Stores responses in DB. |
| `/poll results` | `poll_id` | Shows current results with optional anonymized view depending on poll settings. |
| `/poll toggle_show_responses` | `poll_id`, `show_responses` (bool) | Controls whether the poll embed includes latest responses inline. |
| `/poll close` / `/poll reopen` | `poll_id` | Closes or reopens voting. Closing updates the embed to show final stats. |
| `/poll refresh` | `poll_id` | Re-renders the poll embed/buttons if they stall. |
| `/poll list` | — | Shows active polls in the guild. |
| `/poll wordcloud` | `poll_id` | Generates an image word cloud from responses. |
| `/poll stats` | `poll_id` | Produces summary stats/charts and top responses. |

Background tasks (`core/tasks.py`) auto-refresh and auto-close polls on intervals.

## Conversion (`/convert …`)

| Command | Parameters | Description |
| --- | --- | --- |
| `/convert testosterone` | `starting_type` (`Gel`/`Cypionate`), `dose` (float), `frequency` (int days) | Converts between TRT dosing regimens using legacy calculator. |
| `/convert temperature` | `value`, `from_unit` (`C`, `F`, `K`), `to_unit` | Basic temperature conversion. |
| `/convert length` | `value`, `from_unit`, `to_unit` (m, km, cm, mm, mi, ft, in, yd) | Distance converter. |
| `/convert weight` | `value`, `from_unit`, `to_unit` (kg, g, mg, lb, oz, stone) | Weight converter. |
| `/convert timezone` | `datetime_str`, `from_timezone`, `to_timezone` | Parses natural datetime strings, converts via `zoneinfo`. |
| `/convert shoe` | `value`, `from_system`, `to_system`, `from_gender`, `to_gender` | Converts shoe sizes for US/UK/AU/EU/JP/China/Mexico/KR/Mondopoint/cm/in via linear modeling, rounding half sizes where appropriate. |

## Voice (`/voice …`)

| Command | Parameters | Description |
| --- | --- | --- |
| `/voice join` | `channel` (optional) | Joins your current VC or a specified channel. |
| `/voice leave` | — | Leaves the VC and clears queued audio. |
| `/voice tts` | `text`, optional `language`, `voice`, `engine`, `announce_sender` (bool), `echo_to_channel` (bool) | Adds a message to the Polly-backed TTS queue. Queue processing handles sequential playback. |
| `/voice show_tts_options` | — | Lists available voices, engines, default language. |
| `/voice filter_voices` | `language`, `engine`, `gender` | Filters cached voices (supports gender filtering). |
| `/voice debug_tts` | `text` (default “Debug TTS test”) | Admin-only: synthesizes speech and uploads the file for troubleshooting. |

Helpers in `commands/voice_commands.py` manage connection, queue, and playback loops.

## Utility (`/utility …`)

| Command | Parameters | Description |
| --- | --- | --- |
| `/utility remind` | `time`, `message`, `timezone_offset` (optional) | Sets a reminder; accepts natural language like “in 2h”. Reminders DM the user. |
| `/utility timer` | `duration`, `label`, `notify_channel` (optional) | Creates a countdown visible in-channel with final notification. |
| `/utility refresh_cookies` | — | Admin helper to refresh YouTube cookies for audio downloads. |

## Alarm (`/alarm …`)

| Command | Parameters | Description |
| --- | --- | --- |
| `/alarm set` | `time`, `message`, `channel`, `tts`, `tone`, `alternate`, `repeat`, `interval`, `tz` | Highly configurable scheduled alarm that can speak via TTS or tone. |
| `/alarm list` | — | Lists scheduled alarms and their IDs. |
| `/alarm cancel` | `id` | Cancels a specific alarm by ID. |

## Emoji (`/emoji …`)

- `/emoji copy`, `/emoji upload`, `/emoji from_attachment`, `/emoji reaction` — ingest emoji/stickers from messages, attachments, or reactions.
- `/emoji db save`, `/emoji db load`, `/emoji db list`, `/emoji db saveServer`, `/emoji db delete` — manage stored emoji library.
- `/emoji rename`, `/emoji remove` — rename or delete server emoji.

See `commands/emoji_commands.py` for exact parameter lists—each subcommand includes descriptive parameter names (URL, message link, item type).

## Booster (`/booster role …`)

| Command | Description |
| --- | --- |
| `/booster role color` | Set booster role colors (solid, gradient, holographic). Parameters adapt based on style. |
| `/booster role label` | Rename your booster role. |
| `/booster role icon` | Upload an icon URL (with fetch/validation). |

## Settings (`/settings …`)

- `/settings menu` — Opens an ephemeral UI to toggle reply notifications and scope.
- `/settings sendpings` — `enabled` (bool), `all_servers` (bool) to control reply pinging.
- `/settings notify` — Controls fixed-link reply notifications.

## Standalone Slash Commands

- `/echo` — `message`, `allow_mentions` (default `false`); repeats text in channel.
- `/timestamp` — `date`, `time`, `style`, `timezone_offset`; generates Discord timestamp codes.

## GitHub Issues/Discussions (`/issues panel`)
- See “Issues” section above. Requires `GITHUB_REPO` and `GITHUB_TOKEN`; discussion category IDs auto-resolve via GraphQL, falling back to `GITHUB_DISCUSSION_CATEGORY_*` env overrides.
