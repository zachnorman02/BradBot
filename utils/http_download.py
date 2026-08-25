"""Shared HTTP byte-download helper for image/icon uploads."""
import aiohttp


async def download_bytes(url: str, *, max_bytes: int = 8_000_000) -> bytes:
    """Download a URL's body as bytes.

    Raises ValueError on a non-200 response or if the body exceeds
    max_bytes. Owns its own short-lived aiohttp session.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise ValueError(f"Could not download the file (HTTP {resp.status}).")
            content_length = resp.content_length
            if content_length is not None and content_length > max_bytes:
                raise ValueError("File is too large to download.")
            data = await resp.read()
            if len(data) > max_bytes:
                raise ValueError("File is too large to download.")
            return data
