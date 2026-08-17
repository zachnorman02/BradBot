"""Modal for submitting a GitHub issue or discussion."""
import discord

from utils.github_helper import create_issue, GitHubIssueError, create_discussion, GitHubDiscussionError
from utils.logger import logger


class IssueReportModal(discord.ui.Modal, title="Submit to GitHub"):
    """Modal for collecting GitHub issue details."""

    def __init__(self):
        super().__init__(timeout=300)
        self.issue_title = discord.ui.TextInput(label="Issue Title", placeholder="Summarize the problem or idea", max_length=100, required=True)
        self.add_item(self.issue_title)

        self.issue_description = discord.ui.TextInput(
            label="Description (optional)", style=discord.TextStyle.paragraph,
            placeholder="Steps to reproduce, screenshots, context, etc.", required=False, max_length=2000,
        )
        self.add_item(self.issue_description)

        options = [
            discord.SelectOption(label="Bug", value="issue:bug", description="Something is broken", emoji="🐞", default=True),
            discord.SelectOption(label="Enhancement", value="issue:enhancement", description="New idea or improvement", emoji="✨"),
            discord.SelectOption(label="Question (Q&A Discussion)", value="discussion:qa", description="Post to the Discussions Q&A section", emoji="❓"),
            discord.SelectOption(label="General Discussion", value="discussion:general", description="Start a general topic in Discussions", emoji="💬"),
        ]
        self.submission_type_select = discord.ui.Select(placeholder="Choose what to create", min_values=1, max_values=1, options=options, custom_id="issue_type_select")
        self.add_item(discord.ui.Label(text="Select submission type:", description="Choose what kind of GitHub submission to create", component=self.submission_type_select))

    async def on_submit(self, interaction: discord.Interaction):
        selection = self.submission_type_select.values[0] if self.submission_type_select.values else "issue:bug"
        description = (self.issue_description.value or "").strip() or "_No description provided._"

        submitter_line = f"Submitted by {interaction.user} (ID: {interaction.user.id})"
        guild_line = f"Server: {interaction.guild.name} ({interaction.guild.id})" if interaction.guild else "Server: Direct Message"
        body = f"{description}\n\n---\n{submitter_line}\n{guild_line}"

        kind, value = selection.split(":", 1)
        try:
            if kind == "issue":
                result = await create_issue(title=self.issue_title.value.strip(), body=body, labels=[value])
                await interaction.response.send_message(f"✅ Issue created: [{result.get('title', 'View on GitHub')}]({result.get('html_url')})", ephemeral=True)
            else:
                discussion = await create_discussion(title=self.issue_title.value.strip(), body=body, category=value)
                await interaction.response.send_message(f"✅ Discussion created: [{discussion.get('title', 'View on GitHub')}]({discussion.get('html_url')})", ephemeral=True)
        except ValueError as config_error:
            await interaction.response.send_message(
                "❌ GitHub issue/discussion reporting is not fully configured. Please set GITHUB_REPO, "
                "GITHUB_TOKEN, and discussion category IDs if using discussions.",
                ephemeral=True,
            )
            logger.warning(f"Issue/discussion panel misconfigured: {config_error}")
        except GitHubIssueError as issue_error:
            await interaction.response.send_message(f"❌ Failed to create GitHub issue: {issue_error}", ephemeral=True)
        except GitHubDiscussionError as discussion_error:
            await interaction.response.send_message(f"❌ Failed to create GitHub discussion: {discussion_error}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ An unexpected error occurred while submitting your request.", ephemeral=True)
            logger.error(f"Unexpected GitHub submission error: {e}")
