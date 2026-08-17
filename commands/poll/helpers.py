"""Business logic for the poll domain: embed refresh and the results-
visibility check shared by `results`, `wordcloud`, and `stats` (previously
copy-pasted ~30 lines apiece)."""
import discord

from database import db
from utils.logger import logger
from utils.interaction_helpers import is_bot_owner


async def update_poll_embed(poll_id: int, channel, message_id: int):
    """Refresh a poll message's footer/response-count and, if enabled, its
    inline response preview field."""
    try:
        poll_info = db.get_poll(poll_id)
        if not poll_info:
            return

        message = await channel.fetch_message(message_id)
        if not message.embeds:
            return

        embed = message.embeds[0]
        response_count = db.get_poll_response_count(poll_id)

        footer_text = embed.footer.text if embed.footer else ""
        if " • " in footer_text:
            parts = footer_text.split(" • ")
            base_footer = f"{parts[0]} • {parts[1]}" if len(parts) >= 2 else (parts[0] if parts else f"Poll ID: {poll_id}")
        else:
            base_footer = footer_text if footer_text else f"Poll ID: {poll_id}"

        embed.set_footer(text=f"{base_footer} • {response_count} response{'s' if response_count != 1 else ''}")

        if poll_info['show_responses']:
            responses = db.get_poll_responses(poll_id)

            for i, field in enumerate(embed.fields):
                if field.name.startswith("📝 Responses"):
                    embed.remove_field(i)
                    break

            if response_count > 0:
                response_preview = []
                for resp in responses[:5]:
                    preview_text = resp['response_text'][:100]
                    if len(resp['response_text']) > 100:
                        preview_text += "..."
                    response_preview.append(f"**{resp['username']}**: {preview_text}")

                more_text = f"\n*...and {response_count - 5} more*" if response_count > 5 else ""
                embed.add_field(name=f"📝 Responses ({response_count})", value="\n\n".join(response_preview) + more_text, inline=False)
            else:
                embed.add_field(name="📝 Responses (0)", value="*No responses yet*", inline=False)

        await message.edit(embed=embed)
    except Exception as e:
        logger.error(f"Error updating poll embed: {e}")


async def can_view_poll_results(interaction: discord.Interaction, poll_info: dict) -> str | None:
    """Return an error message if interaction.user can't view this poll's
    results, else None. Shared by `results`, `wordcloud`, and `stats`."""
    if await is_bot_owner(interaction):
        return None

    is_creator = poll_info['creator_id'] == interaction.user.id
    has_manage_perms = interaction.user.guild_permissions.manage_messages

    if not is_creator:
        try:
            poll_channel = interaction.guild.get_channel(poll_info['channel_id'])
            if not poll_channel:
                return "Poll channel not found."
            if not poll_channel.permissions_for(interaction.user).view_channel:
                return "You don't have access to the channel where this poll was created."
        except Exception as e:
            logger.error(f"Error checking channel permissions: {e}")
            return "Could not verify channel access."

    if not poll_info['public_results'] and not is_creator and not has_manage_perms:
        return "This poll's results are only visible to the creator and admins."

    return None
