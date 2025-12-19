"""
Issue command group for GitHub issue submission panels
"""
import discord
from discord import app_commands
from discord import ui
import datetime as dt
from typing import Optional

from database import db
from utils.github_helper import (
    create_issue,
    GitHubIssueError,
    create_discussion,
    GitHubDiscussionError,
)


class IssueReportModal(discord.ui.Modal, title="Submit to GitHub"):
    """Modal for collecting GitHub issue details."""

    def __init__(self):
        super().__init__(timeout=300)
        self.issue_title = discord.ui.TextInput(
            label="Issue Title",
            placeholder="Summarize the problem or idea",
            max_length=100,
            required=True,
        )
        self.add_item(self.issue_title)

        self.issue_description = discord.ui.TextInput(
            label="Description (optional)",
            style=discord.TextStyle.paragraph,
            placeholder="Steps to reproduce, screenshots, context, etc.",
            required=False,
            max_length=2000,
        )
        self.add_item(self.issue_description)

        options = [
            discord.SelectOption(
                label="Bug",
                value="issue:bug",
                description="Something is broken",
                emoji="🐞",
                default=True,
            ),
            discord.SelectOption(
                label="Enhancement",
                value="issue:enhancement",
                description="New idea or improvement",
                emoji="✨",
            ),
            discord.SelectOption(
                label="Question (Q&A Discussion)",
                value="discussion:qa",
                description="Post to the Discussions Q&A section",
                emoji="❓",
            ),
            discord.SelectOption(
                label="General Discussion",
                value="discussion:general",
                description="Start a general topic in Discussions",
                emoji="💬",
            ),
        ]
        self.submission_type_select = discord.ui.Select(
            placeholder="Choose what to create",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="issue_type_select",
        )
        self.add_item(
            discord.ui.Label(
                text="Select submission type:",
                description="Choose what kind of GitHub submission to create",
                component=self.submission_type_select
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        selection = self.submission_type_select.values[0] if self.submission_type_select.values else "issue:bug"
        description = (self.issue_description.value or "").strip()
        if not description:
            description = "_No description provided._"

        submitter_line = f"Submitted by {interaction.user} (ID: {interaction.user.id})"
        guild_line = (
            f"Server: {interaction.guild.name} ({interaction.guild.id})" if interaction.guild else "Server: Direct Message"
        )
        body = f"{description}\n\n---\n{submitter_line}\n{guild_line}"

        kind, value = selection.split(":", 1)
        try:
            if kind == "issue":
                result = await create_issue(
                    title=self.issue_title.value.strip(),
                    body=body,
                    labels=[value],
                )
                await interaction.response.send_message(
                    f"✅ Issue created: [{result.get('title', 'View on GitHub')}]({result.get('html_url')})",
                    ephemeral=True,
                )
            else:
                discussion = await create_discussion(
                    title=self.issue_title.value.strip(),
                    body=body,
                    category=value,
                )
                await interaction.response.send_message(
                    f"✅ Discussion created: [{discussion.get('title', 'View on GitHub')}]({discussion.get('html_url')})",
                    ephemeral=True,
                )
        except ValueError as config_error:
            await interaction.response.send_message(
                "❌ GitHub issue/discussion reporting is not fully configured. Please set GITHUB_REPO, "
                "GITHUB_TOKEN, and discussion category IDs if using discussions.",
                ephemeral=True,
            )
            print(f"[ISSUES] Issue/discussion panel misconfigured: {config_error}")
        except GitHubIssueError as issue_error:
            await interaction.response.send_message(
                f"❌ Failed to create GitHub issue: {issue_error}",
                ephemeral=True,
            )
        except GitHubDiscussionError as discussion_error:
            await interaction.response.send_message(
                f"❌ Failed to create GitHub discussion: {discussion_error}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ An unexpected error occurred while submitting your request.",
                ephemeral=True,
            )
            print(f"[ISSUES] Unexpected GitHub submission error: {e}")


class IssuePanelView(ui.View):
    """View containing a single button to open the issue submission modal."""

    def __init__(self, guild_id: int, custom_id_prefix: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.custom_id_prefix = custom_id_prefix or f"issue_panel:{guild_id}"
        self.report_issue_button.custom_id = f"{self.custom_id_prefix}:report"

    @ui.button(label="Submit an Issue", style=discord.ButtonStyle.blurple, emoji="📝")
    async def report_issue_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = IssueReportModal()
        await interaction.response.send_modal(modal)


class IssuesGroup(app_commands.Group):
    """Slash command group for issue reporting utilities."""

    def __init__(self):
        super().__init__(name="issues", description="GitHub issue reporting commands")

    @app_commands.command(name="panel", description="Create a persistent GitHub issue submission panel")
    @app_commands.default_permissions(administrator=True)
    async def issues_panel(self, interaction: discord.Interaction):
        """Create a panel that lets users submit GitHub issues via a modal."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        try:
            if not db.connection_pool:
                db.init_pool()

            db.init_persistent_panels_table()
            prefix = f"issue_panel:{interaction.guild.id}:{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
            view = IssuePanelView(interaction.guild.id, custom_id_prefix=prefix)

            embed = discord.Embed(
                title="🐞 Report an Issue or Discussion",
                description=(
                    "Found a bug or have an idea? Click below to submit directly to GitHub.\n\n"
                    "The modal lets you choose between Bug, Enhancement, Q&A discussion, or General discussion."
                ),
                color=discord.Color.orange(),
            )
            embed.set_footer(text="Issues are created on GitHub with your Discord username.")

            message = await interaction.channel.send(embed=embed, view=view)
            interaction.client.add_view(view, message_id=message.id)

            db.save_persistent_panel(
                message_id=message.id,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                panel_type='issue_panel',
                metadata={'custom_id_prefix': prefix},
            )

            await interaction.response.send_message(
                "✅ Issue submission panel created! Anyone can now open the modal from this message.",
                ephemeral=True,
            )
        except Exception as e:
            print(f"[ISSUES] Error creating issues panel: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the issues panel.",
                ephemeral=True,
            )
