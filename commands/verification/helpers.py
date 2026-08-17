"""Rules-agreement tracking business logic: bulk reaction cleanup for
verified/departed users, shared by the `cleanup` command."""
import discord

from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error


async def run_rules_reaction_cleanup(
    interaction: discord.Interaction,
    dry_run: bool,
    include_verified: bool,
    include_departed: bool,
) -> None:
    """Remove (or, if dry_run, just count) tracked rules-message reactions
    from verified and/or departed users."""
    if not include_verified and not include_departed:
        await send_error(interaction, "Nothing to clean. Enable at least one target (verified or departed users).")
        return

    rules_messages = db.get_rules_agreement_messages(interaction.guild.id)
    if not rules_messages:
        await send_error(interaction, "Rules agreement tracking is not set up. Use `/verify setup` first.")
        return

    verified_member_ids = set()
    verified_role_name = db.get_guild_setting(interaction.guild.id, "verified_role_name", "verified")
    verified_role = discord.utils.get(interaction.guild.roles, name=verified_role_name)

    if include_verified:
        if not verified_role:
            await send_error(interaction, f"Could not find the verified role named '{verified_role_name}'.")
            return
        verified_member_ids = {m.id for m in verified_role.members if not m.bot}

    await interaction.response.defer(ephemeral=True)

    processed_messages = 0
    removed_reactions = 0
    skipped_messages = 0
    errors = 0
    departed_matches = 0
    verified_matches = 0

    for msg_data in rules_messages:
        try:
            channel = interaction.guild.get_channel(msg_data['channel_id'])
            if not channel:
                skipped_messages += 1
                continue

            message = await channel.fetch_message(msg_data['message_id'])
            processed_messages += 1

            for reaction in message.reactions:
                users = [u async for u in reaction.users()]
                for user in users:
                    should_remove = False
                    is_verified_target = include_verified and user.id in verified_member_ids
                    is_departed_target = include_departed and interaction.guild.get_member(user.id) is None

                    if is_verified_target:
                        verified_matches += 1
                        should_remove = True
                    if is_departed_target:
                        departed_matches += 1
                        should_remove = True

                    if not should_remove:
                        continue

                    if dry_run:
                        removed_reactions += 1
                        continue
                    try:
                        await reaction.remove(user)
                        removed_reactions += 1
                    except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                        errors += 1

        except (discord.NotFound, discord.Forbidden):
            skipped_messages += 1
        except Exception as e:
            errors += 1
            logger.error(f"Error during rules cleanup on message {msg_data.get('message_id')}: {e}")

    mode = "Dry Run" if dry_run else "Cleanup Complete"
    embed = discord.Embed(title=f"🧹 Rules Reaction {mode}", color=discord.Color.orange() if dry_run else discord.Color.green())
    embed.add_field(name="Messages Processed", value=str(processed_messages), inline=True)
    embed.add_field(name="Messages Skipped", value=str(skipped_messages), inline=True)
    embed.add_field(name="Reactions Matched" if dry_run else "Reactions Removed", value=str(removed_reactions), inline=True)
    embed.add_field(name="Matched Verified", value=str(verified_matches), inline=True)
    embed.add_field(name="Matched Departed", value=str(departed_matches), inline=True)
    embed.add_field(name="Errors", value=str(errors), inline=True)
    if include_verified:
        embed.add_field(name="Verified Members", value=str(len(verified_member_ids)), inline=True)
    embed.add_field(
        name="Targets",
        value=f"Verified: {'Yes' if include_verified else 'No'}\nDeparted: {'Yes' if include_departed else 'No'}",
        inline=True,
    )
    if dry_run:
        embed.set_footer(text="Dry run only. Run again with dry_run: false to apply removals.")

    await interaction.followup.send(embed=embed, ephemeral=True)
