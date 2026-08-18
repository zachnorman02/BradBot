# Command Reference

This page summarizes BradBot's slash commands and right-click "Apps" context menus. For quick end-user/mod walkthroughs see `docs/user-guide.md` and `docs/mod-guide.md`.

## Admin (`/admin …`)

Five subgroups, mostly admin/owner-only:

- **panels** — `settings_menu` / `settings_panel` (ephemeral vs. persistent server settings UI), `commands_menu` / `commands_panel` (ephemeral vs. persistent command-toggle UI).
- **config** — `counting_config` (set/reset counting channel, optional 24h penalty role, starting number, or disable), `counting_set_number` (adjust the next expected number), `level_settings` (level-role naming, verified/unverified roles).
- **tools** — `loadboosterroles` / `saveboosterrole` (manage saved booster-role data), `shiftrole` (nudge a role up/down one position), `kick_inactive_level` (kick members with a level role who've gone quiet), `mirror_add` / `mirror_remove` / `mirror_list` / `mirror_copy_existing` (message mirroring between channels), `assignlvl0`, `kickunverified`, `delete_role`.
- **booster** (requires Manage Roles) — `exclude` / `include` / `list` — stop a specific role from ever being auto-detected as someone's booster role (useful when a role like Admin happens to have only one holder and would otherwise match the "one member" heuristic). `exclude` also purges any saved DB record already tracking that role as someone's booster role, so it can't later get recreated from stale data. `exclude_user` / `include_user` / `list_users` — stop the bot from auto-creating/restoring a role for a specific user when they boost (they can still get one via `/booster customize` or `/booster restore` if run manually).
- **ops** — `sync` (force slash-command sync; text fallback `:resync`), `command_ban` / `command_unban` / `command_disable` / `command_enable` (per-user or per-server command gating), `sql` (bot owner only), `auditlog`, `tasklogs` (bot owner only).

**Apps (right-click a message/user):**

- **Mirror This Message** — manually mirror one message.
- **Ban Author From Command** — ban the author of a message from a specific command.
- **Restore Booster Role** / **Edit Booster Role** — admin equivalents of `/booster restore` and `/booster customize` for another member.
- **Test Booster Role** — diagnostic for role hierarchy/positioning (bot owner only).

## Permissions (`/permissions …`)

Four subgroups plus a top-level `mute`:

- **channel** — `access` (allow/deny one user), `restriction_set` / `restriction_remove` / `restriction_list` / `restriction_apply` (standing role-based rules), `visibility` (see what a user or role can/can't see).
- **role** — `set` (add/remove one role), `temp` (timed role grant, auto-removed), `schedule` / `schedule_list` / `schedule_delete` (queue a future role change).
- **conditional** — `configure` / `remove_config` / `list` / `list_eligible` / `set_eligibility` / `check` / `set_override` / `list_overrides` / `assign` / `bulk_check` — role grants gated on eligibility, with blocking/deferral overrides.
- **automation** — `configure` / `remove` / `list` / `check_all` — trigger-role automation rules.
- **deny** — `add` / `remove` / `check` / `list` / `log_set` / `log_test` / `log_clear` — permanently block a user from ever receiving a specific role.
- **mute** — create/configure a server-wide mute role.

**Apps:** **Check Channel Access** (right-click a user) — same as `/permissions channel visibility` for that user.

## Booster (`/booster …`)

- **role** subgroup: `restore` (recreate your role if it's missing/broken and reapply saved icon/colors), `customize` (opens a Modal for name, a merged Colors field, an Off/On Holographic dropdown, icon upload, and an Off/On Clear Icon dropdown — see `docs/user-guide.md` for details).
- Bot owner can use both even without an active boost, to test behavior.

## Emoji (`/emoji …`)

- Top-level: `save`/`load`/`list`/`saveserver`/`delete` under **db** (saved emoji/sticker catalog), plus `upload` (from an image URL), `rename`, `remove`.

**Apps:**

- **Copy Emoji From Message** — grab an emoji used in a message.
- **Copy Emoji From Reaction** — grab an emoji someone reacted with.
- **Create Emoji From Attachment** — turn an attached image into a server emoji.
- **Save Emojis To Database** — save all emoji in a message to the catalog.

## Poll (`/poll …`)

- `create` (requires *Create Polls* permission), `results`, `stats`, `wordcloud` — build and analyze text-response polls.
- `toggle_show_responses`, `close`, `reopen`, `refresh`, `list` — manage presentation and lifecycle.

## Alarm (`/alarm …`)

- `set` (opens a form for time/message/repeat/TTS), `list`, `cancel`.

## Birthday (`/birthday …`)

- **channel**: `set` / `clear` — where announcements post.
- Top-level: `set` (your own birthday), `clear`, `set_for` (set for another user), `month` (list birthdays in a month), `age` (list users by age), `list` (all birthdays).

## Convert (`/convert …`)

- `testosterone`, `temperature`, `length`, `weight`, `liquid`, `currency` (live exchange rates), `timezone`, `shoe` (handles men's/women's and multiple regions).

## Verify (`/verify …`)

Rules-agreement tracking:

- `setup` (paste rules-message link(s) to track), `set_verified_role`, `check` (a user's agreement status), `status`, `remove_on_verify` / `remove_on_leave` (auto-cleanup toggles), `cleanup` (`dry_run` to preview), `clear` (wipe config).

## Settings (`/settings menu`)

- Opens a user-level settings UI. (No other top-level settings commands remain — booster/notification toggles live elsewhere or were retired.)

## Starboard (`/starboard …`)

- `set` (channel + emoji + threshold, incl. NSFW toggle), `list`, `delete`, `top` (most-starred messages for a board).

**Apps:**

- **Force to Starboard** — post immediately, ignoring the threshold.
- **Block from Starboard** / **Unblock from Starboard** — permanently exclude/re-allow a message.

## Utility (`/utility …`)

- `remind` (natural-language reminder, DMs you), `timer` (visible countdown), `refresh_cookies` (YouTube cookies for media downloads).

## Voice (`/voice …`)

- `join` / `leave` — manage the VC connection.
- `tts` — queue Polly TTS with optional `voice`, `engine`, `language`, `announce_author`, `post_text`.
- `show_tts_options` / `filter_voices` / `debug_tts` (admin) — browse voices or debug audio.

## Issues (`/issues panel`)

Posts a button that opens a modal with title, description, and a submission-type dropdown:

- Bug → GitHub issue (`bug` label)
- Enhancement → GitHub issue (`enhancement` label)
- Question → GitHub Discussion (Q&A)
- General Discussion → GitHub Discussion (General)

Discussion category IDs are auto-resolved (override via `GITHUB_DISCUSSION_CATEGORY_*`).

## Link Handling (Apps only, no slash commands)

When BradBot replaces a posted link (Twitter/X, TikTok, Instagram, Reddit, etc.), use right-click on the bot's message:

- **Edit Bot Message** — edit the replacement text in a Modal (re-run through link replacement; `-# …` embed helper lines preserved).
- **Delete Bot Message** — delete it (only works if you're the original sender).

## Reactions (Apps only)

- **Check Reactions** (right-click a message) — see who reacted, optionally filtered to one user or emoji.

## Standalone Slash Commands

- **/echo** — repeat a message (optional `allow_mentions`; when off, sent silently with mentions suppressed).
- **/timestamp** — generate Discord timestamps from date/time input.

Need more specifics? Read the relevant `commands/<domain>/` package in the repo, or update this page with new features.
