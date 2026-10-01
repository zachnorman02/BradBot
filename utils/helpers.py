"""
Helper utility functions for message processing
"""
import re
from typing import Optional
from urllib.parse import quote


def is_url_suppressed(content: str, url: str) -> bool:
    """
    Check if a URL should be ignored (wrapped in backticks `, ```, or angle brackets <>).
    
    Args:
        content: The message content
        url: The URL to check
        
    Returns:
        True if the URL should be ignored, False otherwise
    """
    url_start = content.find(url)
    if url_start == -1:
        return False
    
    url_end = url_start + len(url)
    
    # Check for triple backtick code blocks ```URL```
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
        if start < url_start < end:
            return True
    
    # Check for angle brackets <URL>
    # Look backwards for '<'
    has_opening_angle = False
    for i in range(url_start - 1, -1, -1):
        if content[i] == '<':
            has_opening_angle = True
            break
        elif content[i] in (' ', '\n', '\t'):
            continue
        else:
            break
    
    # Look forwards for '>'
    has_closing_angle = False
    for i in range(url_end, len(content)):
        if content[i] == '>':
            has_closing_angle = True
            break
        elif content[i] in (' ', '\n', '\t'):
            continue
        else:
            break
    
    if has_opening_angle and has_closing_angle:
        return True
    
    # Check for single backticks `...URL...` -- the URL doesn't need to be
    # adjacent to the backtick, just inside the same inline-code span (e.g.
    # `curl https://example.com`). Mask out the triple-backtick blocks
    # already handled above so their backticks don't throw off pairing the
    # remaining single ones, then pair consecutive backticks up and check
    # whether the URL falls inside any complete pair. A trailing unpaired
    # backtick (odd count) is correctly left unpaired by range()'s step.
    masked = content
    for start, end in triple_blocks:
        masked = masked[:start] + ('\x00' * (end - start)) + masked[end:]
    backtick_positions = [i for i, ch in enumerate(masked) if ch == '`']
    for j in range(0, len(backtick_positions) - 1, 2):
        start, end = backtick_positions[j], backtick_positions[j + 1]
        if start < url_start < end:
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
        encoded_url = quote(url, safe='')
        return f'https://embedez.io/embed?url={encoded_url}'
    except Exception:
        return None
