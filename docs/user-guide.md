# BradBot – User Guide

Formatted to paste straight into a Discord channel or pinned message.

---

## ✏️ Editing or deleting your link message

When you post a link from Twitter/X, TikTok, Instagram, Reddit, etc., BradBot may replace it with a cleaned-up version and tag you as the sender.

**To edit it:**
1. Right-click (long-press on mobile) the bot's message
2. **Apps → Edit Bot Message**
3. Change the text in the popup and submit

**To delete it:**
1. Right-click the bot's message
2. **Apps → Delete Bot Message**

You can only edit/delete messages that were created from *your* link.

---

## 💎 Customizing your booster role

Available if you're currently boosting the server.

**`/booster customize`** opens a form pre-filled with your role's current name and colors, so you can see what's there and just edit the part you want to change:
- **Role Name** – optional, leave blank to keep your current name
- **Colors** – one field for both. `#FF0000` = solid, `#FF0000,#00FF00` = gradient
  - Leave blank → keeps whatever colors you currently have
  - Type `clear` → resets to a random solid color
  - Just one hex, no comma → sets that as a solid color (drops any existing gradient)
  - Two comma-separated → sets both sides of a gradient. Leave one side blank in the pair (e.g. `,#00FF00`) to keep that side as-is, or type `clear` on one side to reset just that one
- **Holographic** – dropdown, Off/On, preselected to match your role's current look. Discord's shimmer effect only comes in one fixed color combo (not something you pick), so switching this On overrides whatever you put in Colors.
- **Icon** – optional image upload. Blank = keep your current icon, upload = replace it.
- **Clear Icon** – dropdown, Off/On. Turn On to remove your icon entirely; ignored if you also upload a new one above.

You don't have to refill everything just to change one thing — blank fields are left untouched, so you can update just the name, or just one color, etc.

**`/booster restore`** – if your role ever goes missing or looks broken, this recreates it from your last saved settings.

**Note:** if you stop boosting, your custom role is removed (but your settings are saved). Boost again and it comes back automatically with the same look — no need to redo `/booster customize`.
