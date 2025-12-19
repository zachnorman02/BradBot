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
| `/admin tools autorole` | `action` (choice), `rule_name`, `trigger_role`, `roles_to_add`, `roles_to_remove` | Creates automations that run when a member gains `trigger_role`. <br>• `action=add` — define/update a rule. Provide `roles_to_add` / `roles_to_remove` as comma-separated mentions or IDs. <br>• `remove` — delete by `rule_name`. <br>• `list` — show all rules. <br>• `check-all` — re-run every rule against the guild (deferred). |
| `/admin tools channelrestriction` | `action`, `channel`, `role`, `threshold`, `scope` | Defines gated channels (e.g., “only lvl 5 can talk”). <br>• `action=add` — set `channel`, gating `role`, optional `threshold` (minutes before access) and `scope` (e.g., `messages`, `joins`). <br>• `remove/list` — manage existing rules. Enforcement happens via background tasks. |
| `/admin tools messagemirror` | `action`, `source_channel`, `target_channel`, `limit`, `sync_edits`, `sync_deletes` | Copies existing history (up to `limit`) then mirrors future messages. `sync_edits/deletes` keep mirrored content up to date. |
| `/admin tools conditionalrole` | `action`, `role`, `blocking_roles`, `deferral_roles` | Prevents `role` from being added if members already have any `blocking_roles`. `deferral_roles` postpone auto-assignments routed through other automations. Use comma-separated IDs or mentions. |
| `/admin maintenance assignlvl0` | — | Assign “lvl 0” to every verified user without another level role. |
| `/admin maintenance kickunverified` | `dry_run` (bool) | Removes unverified members with no ticket after 30 days. Use `dry_run=true` to preview. |
| `/admin sql` | `query` | Bot-owner only: run arbitrary SQL and return results (truncated). |
| `/admin tasklogs` | `task_name`, `limit` | Bot-owner only: view recent background task executions. |
| `/admin auditlog` | `query` | Bot-owner only SQL-esque query against the guild audit log. |

### Legacy text commands
- `:resync [global|guild]` — Same as `/admin sync`, available to admins.
- `:sync`, `:clearcmds` — Owner-only conveniences retained for testing.

## Issues (`/issues panel`)

Posts a persistent embed with a single “Submit an Issue” button. When clicked, the modal prompts for:
- **Title** (required)
- **Description** (optional)
- **Submission type** dropdown inside the modal with four options:
  - Bug (GitHub Issue, `bug` label)
  - Enhancement (GitHub Issue, `enhancement` label)
  - Question (GitHub Discussion, Q&A category)
  - General Discussion (GitHub Discussion, General category)

Discussion categories are auto-resolved via GitHub’s API (cached per repo), with optional overrides via `GITHUB_DISCUSSION_CATEGORY_*`.

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

| Command | Parameters | Description |
| --- | --- | --- |
| `/emoji copy` | `message_link`, `which` (`emoji`, `sticker`, `auto`), `create_sticker`, `replace_existing` | Pulls emoji/stickers from a specific message (by link). Downloads the asset and uploads it to the current server, optionally converting to a sticker. |
| `/emoji from_attachment` | `message_link`, `name`, `which`, `create_sticker` | Same as copy but lets you select which attachment to use and assign a name. |
| `/emoji reaction` | `message_link`, `which`, `create_sticker` | Copies reactions off a message. |
| `/emoji upload` | `name`, `url`, `create_sticker`, `replace_existing` | Uploads directly from a URL. |
| `/emoji rename` | `current_name`, `new_name`, `is_sticker` | Renames an existing emoji or sticker. |
| `/emoji remove` | `name`, `is_sticker` | Deletes the asset from the guild. |
| `/emoji db save` | `item` (`emoji`/`sticker`), `is_sticker`, `name`, `notes`, `message_link` | Saves an asset into the bot’s database (optionally grabbing from a message). |
| `/emoji db load` | `search`, `force_type`, `replace_existing` | Loads a saved emoji/sticker into the current server. |
| `/emoji db list` | `search`, `filter_type` | Lists stored assets with metadata. |
| `/emoji db saveServer` | `scope` (`all`, `emoji`, `stickers`), `emoji_name`, `custom_name`, `notes` | Bulk-saves server emoji/stickers into the DB. |
| `/emoji db delete` | `emoji_id` | Removes a saved entry from the DB (bot owner only). |

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
