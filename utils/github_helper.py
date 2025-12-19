"""
Helpers for interacting with GitHub's REST API.
"""
import os
from typing import List, Optional, Dict

import aiohttp


def _get_github_config() -> tuple[str, str, int]:
    repo = os.getenv("GITHUB_REPO") or os.getenv("GITHUB_ISSUE_REPO")
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_TOKEN")
    timeout = int(os.getenv("GITHUB_TIMEOUT", "15"))
    return repo, token, timeout


class GitHubIssueError(Exception):
    """Raised when a GitHub issue request fails."""


class GitHubDiscussionError(Exception):
    """Raised when a GitHub discussion request fails."""


_DISCUSSION_CATEGORY_CACHE: Dict[str, Dict[str, str]] = {}

_CATEGORY_ALIAS_MAP = {
    "qa": ["q-a", "qa", "qna", "questions", "question-answer"],
    "general": ["general", "general-discussion"],
}


def _parse_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError("GITHUB_REPO must be in the format owner/repo.")
    owner, name = repo.split("/", 1)
    return owner, name


async def _fetch_discussion_categories(
    session: aiohttp.ClientSession, repo: str, token: str
) -> Dict[str, str]:
    cache_key = repo.lower()
    if cache_key in _DISCUSSION_CATEGORY_CACHE:
        return _DISCUSSION_CATEGORY_CACHE[cache_key]

    owner, name = _parse_repo(repo)
    query = """
    query($owner:String!, $name:String!) {
        repository(owner:$owner, name:$name) {
            discussionCategories(first:50) {
                nodes { id slug name }
            }
        }
    }
    """
    payload = {"query": query, "variables": {"owner": owner, "name": name}}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "BradBot-Issue-Reporter",
    }
    async with session.post(
        "https://api.github.com/graphql", json=payload, headers=headers
    ) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise GitHubDiscussionError(
                f"Failed to fetch discussion categories ({resp.status}): {text[:200]}"
            )
        data = await resp.json()
        nodes = (
            data.get("data", {})
            .get("repository", {})
            .get("discussionCategories", {})
            .get("nodes", [])
        )
        mapping: Dict[str, str] = {}
        for node in nodes:
            slug = str(node.get("slug", "")).casefold()
            cat_id = node.get("id")
            if slug and cat_id:
                mapping[slug] = cat_id
        _DISCUSSION_CATEGORY_CACHE[cache_key] = mapping
        return mapping


async def _resolve_discussion_category_id(category: str) -> str | None:
    override = os.getenv(f"GITHUB_DISCUSSION_CATEGORY_{category.upper()}")
    if override:
        return override

    repo, token, timeout_seconds = _get_github_config()
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        mapping = await _fetch_discussion_categories(session, repo, token)

    aliases = _CATEGORY_ALIAS_MAP.get(category, [category])
    for alias in aliases:
        slug = alias.casefold()
        if slug in mapping:
            return mapping[slug]
    return None


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


async def create_discussion(title: str, body: str, category: str) -> dict:
    """
    Create a GitHub discussion in the configured repository.

    Args:
        title: Discussion title.
        body: Discussion body/description.
        category: Category slug ('qa' or 'general' by default).
    """
    repo, token, timeout_seconds = _get_github_config()
    if not repo or not token:
        raise ValueError("GITHUB_REPO and GITHUB_TOKEN environment variables must be set.")
    category_id = await _resolve_discussion_category_id(category)
    if not category_id:
        raise ValueError(f"GitHub discussion category '{category}' could not be resolved.")

    url = f"https://api.github.com/repos/{repo}/discussions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "BradBot-Issue-Reporter",
    }
    payload = {"title": title, "body": body, "category_id": category_id}

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status >= 400:
                error_text = await resp.text()
                raise GitHubDiscussionError(
                    f"GitHub discussion creation failed ({resp.status}): {error_text[:200]}"
                )
            return await resp.json()
