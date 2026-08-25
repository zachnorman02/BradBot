"""Modal collecting the optional user/emoji filters for the "Check
Reactions" message context menu."""
import discord

from utils.role_parsing import resolve_member_reference
from commands.reaction.helpers import check_message_reactions


class ReactionCheckModal(discord.ui.Modal, title="Check Reactions"):
    user = discord.ui.Label(
        text="User",
        description="Mention, ID, or username. Leave blank to list everyone who reacted.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=100),
    )
    emoji = discord.ui.Label(
        text="Emoji",
        description="Leave blank to check all emoji.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=100),
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        user_raw = self.user.component.value.strip()
        emoji_filter = self.emoji.component.value.strip() or None

        target_user = None
        if user_raw:
            target_user = resolve_member_reference(interaction.guild, user_raw)
            if not target_user:
                await interaction.response.send_message(f"❌ Could not find a member matching `{user_raw}`.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)
        matches, error = await check_message_reactions(self.message, target_user, emoji_filter)
        if error:
            await interaction.followup.send(f"❌ Error scanning reactions: {error}", ephemeral=True)
            return

        if target_user:
            if matches:
                emoji_text = matches[0][1]
                await interaction.followup.send(f"✅ {target_user.mention} reacted" + (f" with {emoji_text}" if emoji_text else "") + ".", ephemeral=True)
            else:
                filt = f" for emoji {emoji_filter}" if emoji_filter else ""
                await interaction.followup.send(f"❌ No reaction from {target_user.mention} found{filt}.", ephemeral=True)
            return

        if not matches:
            filt = f" for emoji {emoji_filter}" if emoji_filter else ""
            await interaction.followup.send(f"❌ No reactions found{filt}.", ephemeral=True)
            return

        seen = {}
        for reactor, emoji_text in matches:
            seen.setdefault(reactor.mention, []).append(emoji_text or "")
        lines = [f"{mention}: {' '.join(e for e in emojis if e)}" for mention, emojis in list(seen.items())[:25]]
        header = f"✅ {len(seen)} user(s) reacted:\n"
        response = header + "\n".join(lines)
        if len(seen) > 25:
            response += f"\n... and {len(seen) - 25} more"
        await interaction.followup.send(response[:2000], ephemeral=True)
