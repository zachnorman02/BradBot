"""
Helpers for interacting with GitHub's REST API.
"""
import os
from typing import List, Optional

import aiohttp


def _get_github_config() -> tuple[str, str, int]:
    repo = os.getenv("GITHUB_REPO") or os.getenv("GITHUB_ISSUE_REPO")
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_TOKEN")
    timeout = int(os.getenv("GITHUB_TIMEOUT", "15"))
    return repo, token, timeout


class GitHubIssueError(Exception):
    """Raised when a GitHub issue request fails."""


async def create_issue(title: str, body: str, labels: Optional[List[str]] = None) -> dict:
    """
    Create a GitHub issue using the REST API.

    Args:
        title: Issue title.
        body: Issue body/description.
        labels: Optional list of labels to apply.

    Returns:
        Parsed JSON response from GitHub.

    Raises:
        ValueError: If credentials/env vars missing.
        GitHubIssueError: If GitHub returns an error.
    """
    repo, token, timeout_seconds = _get_github_config()
    if not repo or not token:
        raise ValueError("GITHUB_REPO and GITHUB_TOKEN environment variables must be set.")

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "BradBot-Issue-Reporter",
    }
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status >= 400:
                error_text = await resp.text()
                raise GitHubIssueError(
                    f"GitHub issue creation failed ({resp.status}): {error_text[:200]}"
                )
            return await resp.json()
