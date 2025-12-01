"""
Helper utility functions for message processing
"""
import re
from typing import Optional


def is_url_in_code_block(content: str, url: str) -> bool:
    """
    Check if a URL is inside a code block (single or triple backticks).
    
    Args:
        content: The message content
        url: The URL to check
        
    Returns:
        True if the URL is in a code block, False otherwise
    """
    url_start = content.find(url)
    if url_start == -1:
        return False
    
    # Check for triple backtick code blocks first
    triple_blocks = []
    i = 0
    while i < len(content):
        start = content.find('```', i)
        if start == -1:
            break
        end = content.find('```', start + 3)
        if end == -1:
            break
        triple_blocks.append((start, end + 3))
        i = end + 3
    
    # Check if URL is in any triple backtick block
    for start, end in triple_blocks:
        if start <= url_start < end:
            return True
    
    # Check for single backtick code blocks (inline code)
    # Remove triple backtick blocks temporarily to avoid conflicts
    temp_content = content
    for start, end in reversed(triple_blocks):
        temp_content = temp_content[:start] + ' ' * (end - start) + temp_content[end:]
    
    # Adjust URL position for the temporary content
    temp_url_start = temp_content.find(url)
    if temp_url_start == -1:
        return False
    
    # Find all single backtick pairs
    backticks = []
    for i, char in enumerate(temp_content):
        if char == '`':
            backticks.append(i)
    
    # Check if URL is between any pair of backticks
    for i in range(0, len(backticks) - 1, 2):
        if i + 1 < len(backticks):
            start, end = backticks[i], backticks[i + 1]
            if start <= temp_url_start < end:
                return True
    
    return False


async def fix_amp_links(content: str) -> str:
    """
    Fix Google AMP links by extracting the original URL.
    
    Args:
        content: Message content containing URLs
        
    Returns:
        Content with AMP links fixed
    """
    # Pattern to match Google AMP URLs
    amp_pattern = re.compile(
        r'https?://(?:www\.)?google\.[a-z]+/amp/s/([^\s<>()]+)',
        re.IGNORECASE
    )
    
    def replace_amp(match):
        # Extract the original URL from the AMP wrapper
        original_url = match.group(1)
        return f'https://{original_url}'
    
    return amp_pattern.sub(replace_amp, content)


async def get_embedez_link(url: str) -> Optional[str]:
    """
    Generate an EmbedEZ link for supported websites.
    EmbedEZ is a service that helps embed content from various sites.
    
    Args:
        url: The original URL
        
    Returns:
        EmbedEZ link or None if not applicable
    """
    # EmbedEZ format: https://embedez.io/embed?url=<encoded_url>
    try:
        from urllib.parse import quote
        encoded_url = quote(url, safe='')
        return f'https://embedez.io/embed?url={encoded_url}'
    except Exception:
        return None
