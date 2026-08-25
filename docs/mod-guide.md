# BradBot – Mod Guide

Formatted to paste into Discord — each `##` section is sized to fit as its own message if you're posting this in chunks.

---

## 🔒 Channel Permissions

**`/permissions channel access`** — allow or deny one user from a specific channel.
- `channel`, `user`, `allow` (True = clear the deny, False = deny view/send/react/voice/threads)

**`/permissions channel restriction_set`** — a standing rule based on a role, auto-enforced going forward.
- `channel`, `blocking_role`, `mode`:
  - **Block** = members *with* the role can't see the channel
  - **Require** = members *without* the role can't see it
- `/permissions channel restriction_remove` — remove a rule
- `/permissions channel restriction_list` — see all configured rules
- `/permissions channel restriction_apply` — re-apply rules to everyone right now (use after adding/editing one)

**`/permissions channel visibility`** (or right-click a user → **Apps → Check Channel Access**) — see exactly which channels a user or role can/can't see. Give it a `user` for an exact answer, or a `role` for a best-effort estimate.

---

## ✅ Rule Agreement

**`/verify setup`** — opens a form to paste the message link(s) for your rules post(s). Reacting to these is how members "agree."

**`/verify set_verified_role`** — tell the bot which role means "verified," so it knows who to clean up after.

**`/verify check`** — pick a user, see which rules messages they've reacted to (and whether they've agreed to all of them).

**`/verify status`** — see current setup: tracked messages, verified role, and whether auto-cleanup is on.

**`/verify remove_on_verify`** / **`/verify remove_on_leave`** — toggle automatically clearing someone's rules reactions once they're verified, or once they leave.

**`/verify cleanup`** — manually run that cleanup now (`dry_run: True` to preview first).

**`/verify clear`** — wipe the tracked-messages config entirely.

---

## 🧑‍⚖️ Roles

**`/permissions role set`** — add or remove one role from one member.

**`/permissions role temp`** — give a role for a limited time (e.g. `2h`, `1d`); it's removed automatically.

**`/permissions role schedule`** — queue a role add/remove for a specific future time. `/permissions role schedule_list` to see what's queued, `schedule_delete` to cancel one.

**`/permissions deny add`** — block a specific user from *ever* receiving a specific role (even if someone tries to add it). `deny remove` undoes it, `deny check`/`deny list` to review, `deny log_set` to get a channel ping whenever someone tries to give the denied role anyway.

**`/permissions mute`** — create/configure a server-wide mute role that blocks sending/reacting/speaking in every channel.

---

## ⭐ Starboard & Reactions

**`/starboard set`** — configure a channel + emoji + reaction threshold as a starboard.

Right-click any message → **Apps**:
- **Force to Starboard** — post it immediately, ignoring the threshold
- **Block from Starboard** — make sure it never gets starred
- **Unblock from Starboard** — clear a previous force/block
- **Check Reactions** — see who reacted (optionally filtered to one user or one emoji)

`/starboard list` / `/starboard top` to review configured boards and the most-starred messages.
