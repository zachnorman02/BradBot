"""
Cookie handling utilities for BradBot
"""
import os
import json
import tempfile


async def fetch_youtube_cookies():
    """
    Fetch YouTube cookies by logging in automatically if credentials are provided.
    Uses YOUTUBE_USERNAME and YOUTUBE_PASSWORD environment variables.
    Returns path to cookie file, or None if failed.

    NOTE: Browser-based cookie fetching has been disabled.
    """
    print("[COOKIES] Browser-based cookie fetching is disabled")
    return None


def validate_cookies_file(cookie_file_path):
    """Check if cookie file exists and is readable."""
    if not cookie_file_path or not os.path.exists(cookie_file_path):
        return False

    try:
        with open(cookie_file_path, 'r') as f:
            content = f.read()
            return len(content.strip()) > 0
    except:
        return False