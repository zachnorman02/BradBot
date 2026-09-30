"""Reaction shortcuts on the bot's replaced-link messages: the same
delete/remove-embed actions as the "Delete Bot Message"/"Remove Embed" Apps
context menus (commands/link/context_menus.py), reachable by clicking a
reaction instead of opening the right-click menu. Locked to the original
poster the same way those context menus are (parse_replaced_message_owner)
-- reacting as anyone else just gets the reaction bounced back off.

No pencil/edit reaction: Discord only lets a bot open a modal in response
to a slash/context-menu interaction, and a raw reaction add has no
interaction to respond with, so there's no way for a reaction to drive the
actual edit flow -- editing stays a context-menu-only action.
"""
import discord

from commands.link.helpers import parse_replaced_message_owner

DELETE_EMOJI = "🗑️"
REMOVE_EMBED_EMOJI = "🙈"
LINK_MESSAGE_EMOJIS = (DELETE_EMOJI, REMOVE_EMBED_EMOJI)


async def add_link_message_reactions(message: discord.Message) -> None:
    """Add the delete/remove-embed shortcut reactions to a freshly-sent
    replaced-link message. Best-effort -- e.g. missing Add Reactions
    permission shouldn't block the message itself."""
    for emoji in LINK_MESSAGE_EMOJIS:
        try:
            await message.add_reaction(emoji)
        except discord.DiscordException:
            pass


async def _bounce_reaction(message: discord.Message, emoji: str, reactor) -> None:
    try:
        await message.remove_reaction(emoji, reactor)
    except discord.DiscordException:
        pass


async def handle_link_message_reaction(bot: discord.Client, payload: discord.RawReactionActionEvent) -> None:
    """React to a click on one of the delete/remove-embed shortcuts."""
    if payload.user_id == bot.user.id:
        return

    emoji = str(payload.emoji)
    if emoji not in LINK_MESSAGE_EMOJIS:
        return

    channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.DiscordException:
        return

    owner_id = parse_replaced_message_owner(message, bot.user.id)
    if owner_id is None:
        return  # not one of our replaced-link messages

    reactor = payload.member or bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)

    if payload.user_id != owner_id:
        # Locked to the original poster, same as the Apps context menus.
        await _bounce_reaction(message, emoji, reactor)
        return

    if emoji == DELETE_EMOJI:
        try:
            await message.delete()
        except discord.DiscordException:
            pass

    elif emoji == REMOVE_EMBED_EMOJI:
        try:
            await message.edit(suppress=True)
        except discord.DiscordException:
            pass
        await _bounce_reaction(message, emoji, reactor)
