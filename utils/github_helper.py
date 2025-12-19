"""
Helpers for interacting with GitHub's REST API.
"""
import os
from typing import List, Optional, Dict, Any

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


_DISCUSSION_CATEGORY_CACHE: Dict[str, Dict[str, Any]] = {}

_CATEGORY_ALIAS_MAP = {
    "qa": ["q-a", "qa", "qna", "questions", "question-answer"],
    "general": ["general", "general-discussion"],
}


def _parse_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError("GITHUB_REPO must be in the format owner/repo.")
    owner, name = repo.split("/", 1)
    return owner, name


def _graphql_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "BradBot-Issue-Reporter",
    }


async def _ensure_discussion_cache(
    session: aiohttp.ClientSession, repo: str, token: str
) -> Dict[str, Any]:
    cache_key = repo.lower()
    cached = _DISCUSSION_CATEGORY_CACHE.get(cache_key)
    if cached:
        return cached

    owner, name = _parse_repo(repo)
    query = """
    query($owner:String!, $name:String!) {
        repository(owner:$owner, name:$name) {
            id
            discussionCategories(first:50) {
                nodes { id slug name }
            }
        }
    }
    """
    payload = {"query": query, "variables": {"owner": owner, "name": name}}
    async with session.post(
        "https://api.github.com/graphql", json=payload, headers=_graphql_headers(token)
    ) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise GitHubDiscussionError(
                f"Failed to fetch discussion categories ({resp.status}): {text[:200]}"
            )
        data = await resp.json()
        repo_data = data.get("data", {}).get("repository")
        if not repo_data:
            raise GitHubDiscussionError("Repository not found in GitHub response.")
        repo_id = repo_data.get("id")
        nodes = repo_data.get("discussionCategories", {}).get("nodes", [])
        mapping: Dict[str, str] = {}
        for node in nodes:
            slug = str(node.get("slug", "")).casefold()
            cat_id = node.get("id")
            if slug and cat_id:
                mapping[slug] = cat_id
        cache_entry = {"categories": mapping, "repo_id": repo_id}
        _DISCUSSION_CATEGORY_CACHE[cache_key] = cache_entry
        return cache_entry


async def _resolve_discussion_context(category: str) -> tuple[str | None, str | None]:
    repo, token, timeout_seconds = _get_github_config()
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        cache_entry = await _ensure_discussion_cache(session, repo, token)
        repo_id = cache_entry.get("repo_id")
        mapping = cache_entry.get("categories", {})

    category_override = os.getenv(f"GITHUB_DISCUSSION_CATEGORY_{category.upper()}")
    if category_override:
        return repo_id, category_override

    aliases = _CATEGORY_ALIAS_MAP.get(category, [category])
    for alias in aliases:
        slug = alias.casefold()
        if slug in mapping:
            return repo_id, mapping[slug]
    return repo_id, None


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

    repo_id, category_id = await _resolve_discussion_context(category)
    if not repo_id or not category_id:
        raise ValueError(f"GitHub discussion category '{category}' could not be resolved.")

    mutation = """
    mutation($repositoryId:ID!, $categoryId:ID!, $title:String!, $body:String!) {
        createDiscussion(input:{
            repositoryId:$repositoryId,
            categoryId:$categoryId,
            title:$title,
            body:$body
        }) {
            discussion { title url id }
        }
    }
    """
    variables = {
        "repositoryId": repo_id,
        "categoryId": category_id,
        "title": title,
        "body": body,
    }

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://api.github.com/graphql",
            json={"query": mutation, "variables": variables},
            headers=_graphql_headers(token),
        ) as resp:
            data = await resp.json()
            if resp.status >= 400 or "errors" in data:
                error_text = data.get("errors") or await resp.text()
                raise GitHubDiscussionError(
                    f"GitHub discussion creation failed ({resp.status}): {str(error_text)[:200]}"
                )
            discussion = (
                data.get("data", {})
                .get("createDiscussion", {})
                .get("discussion", {})
            )
            return {
                "title": discussion.get("title"),
                "html_url": discussion.get("url"),
            }
