"""
Allows fixing links from various websites.
"""
import re
from typing import Optional

__all__ = ('WebsiteLink', 'websites', 'fix_link', 'get_site_name')

class WebsiteLink:
    """
    Base class for all websites.
    """

    name: str
    id: str

    def __init__(self, url: str) -> None:
        """
        Initialize the website.

        :param url: The URL to fix
        """
        self.url: str = url

    @classmethod
    def if_valid(cls, url: str) -> Optional['WebsiteLink']:
        """
        Return a website if the URL is valid.

        :param url: The URL to check
        :return: The website if the URL is valid, None otherwise
        """
        self = cls(url)
        return self if self.is_valid() else None

    def is_valid(self) -> bool:
        """
        Indicates if the link is valid.

        :return: True if the link is valid, False otherwise
        """
        raise NotImplementedError

    async def render(self) -> Optional[str]:
        """
        Render the fixed link

        :return: The rendered fixed link
        """
        raise NotImplementedError


class SimpleWebsiteLink(WebsiteLink):
    """
    Simple website link with basic domain replacement.
    """

    name: str
    patterns: list[str]
    replacement: str

    def __init__(self, url: str) -> None:
        super().__init__(url)

    def is_valid(self) -> bool:
        """Check if URL matches any of our patterns."""
        for pattern in self.patterns:
            if re.search(pattern, self.url, re.IGNORECASE):
                return True
        return False

    def _clean_tracking_params(self, url: str) -> str:
        """Remove all query parameters from URL."""
        # Split URL at the first '?' to remove all query parameters
        if '?' in url:
            return url.split('?', 1)[0]
        return url

    async def render(self) -> Optional[str]:
        """Return the fixed URL with tracking parameters removed."""
        if not self.is_valid():
            return None
        
        # Simple replacement - change domain
        for pattern in self.patterns:
            if re.search(pattern, self.url, re.IGNORECASE):
                fixed_url = re.sub(
                    r'https?://[^/]+', 
                    f'https://{self.replacement}', 
                    self.url, 
                    flags=re.IGNORECASE
                )
                # Clean tracking parameters
                clean_url = self._clean_tracking_params(fixed_url)
                return clean_url
        return None


class TwitterLink(SimpleWebsiteLink):
    """Twitter/X link handler."""
    name = "Twitter"
    patterns = [r'twitter\.com', r'x\.com', r'fxtwitter\.com']
    replacement = "fxtwitter.com"


class InstagramLink(SimpleWebsiteLink):
    """Instagram link handler."""
    name = "Instagram"
    patterns = [r'instagram\.com', r'ddinstagram\.com']
    replacement = "ddinstagram.com"


class TikTokLink(SimpleWebsiteLink):
    """TikTok link handler."""
    name = "TikTok"
    patterns = [r'tiktok\.com', r'tnktok\.com']
    replacement = "tnktok.com"


class RedditLink(SimpleWebsiteLink):
    """Reddit link handler."""
    name = "Reddit"
    patterns = [r'reddit\.com', r'vxreddit\.com']
    replacement = "vxreddit.com"


class YouTubeLink(SimpleWebsiteLink):
    """YouTube link handler."""
    name = "YouTube"
    patterns = [r'youtube\.com', r'youtu\.be', r'koutube\.com']
    replacement = "koutube.com"
    
    def _clean_tracking_params(self, url: str) -> str:
        # Only keep 'v' and 't' query parameters, remove others
        if '?' not in url:
            return url
        base, query = url.split('?', 1)
        params = query.split('&')
        keep = []
        for param in params:
            if param.startswith('v=') or param.startswith('t='):
                keep.append(param)
        if keep:
            return base + '?' + '&'.join(keep)
        else:
            return base


class ThreadsLink(SimpleWebsiteLink):
    """Threads link handler."""
    name = "Threads"
    patterns = [r'threads\.net', r'fixthreads\.net']
    replacement = "fixthreads.net"


class BlueskyLink(SimpleWebsiteLink):
    """Bluesky link handler."""
    name = "Bluesky"
    patterns = [r'bsky\.app', r'bskx\.app']
    replacement = "bskx.app"


class SnapchatLink(SimpleWebsiteLink):
    """Snapchat link handler."""
    name = "Snapchat"
    patterns = [r'snapchat\.com']
    replacement = "snapchat.com"  # No alternative available yet


class FacebookLink(SimpleWebsiteLink):
    """Facebook link handler."""
    name = "Facebook"
    patterns = [r'facebook\.com', r'facebed\.com']
    replacement = "facebed.com"


class PixivLink(SimpleWebsiteLink):
    """Pixiv link handler."""
    name = "Pixiv"
    patterns = [r'pixiv\.net', r'phixiv\.net']
    replacement = "phixiv.net"


class TwitchLink(SimpleWebsiteLink):
    """Twitch link handler."""
    name = "Twitch"
    patterns = [r'twitch\.tv', r'fxtwitch\.seria\.moe']
    replacement = "fxtwitch.seria.moe"


class SpotifyLink(SimpleWebsiteLink):
    """Spotify link handler."""
    name = "Spotify"
    patterns = [r'spotify\.com', r'fxspotify\.com']
    replacement = "fxspotify.com"


class DeviantArtLink(SimpleWebsiteLink):
    """DeviantArt link handler."""
    name = "DeviantArt"
    patterns = [r'deviantart\.com', r'fixdeviantart\.com']
    replacement = "fixdeviantart.com"


class MastodonLink(SimpleWebsiteLink):
    """Mastodon link handler."""
    name = "Mastodon"
    patterns = [r'mastodon\.social', r'mstdn\.jp', r'mastodon\.cloud', r'mstdn\.social', 
               r'mastodon\.world', r'mastodon\.online', r'mas\.to', r'techhub\.social', 
               r'mastodon\.uno', r'infosec\.exchange', r'fx\.zillanlabs\.tech']
    replacement = "fx.zillanlabs.tech"


class TumblrLink(SimpleWebsiteLink):
    """Tumblr link handler."""
    name = "Tumblr"
    patterns = [r'tumblr\.com', r'tpmblr\.com']
    replacement = "tpmblr.com"


class BiliBiliLink(SimpleWebsiteLink):
    """BiliBili link handler."""
    name = "BiliBili"
    patterns = [r'bilibili\.com', r'b23\.tv', r'b22\.top', r'vxbilibili\.com']
    replacement = "vxbilibili.com"


class IFunnyLink(SimpleWebsiteLink):
    """IFunny link handler."""
    name = "IFunny"
    patterns = [r'ifunny\.co']
    replacement = "ifunny.co"  # No alternative available yet


class FurAffinityLink(SimpleWebsiteLink):
    """FurAffinity link handler."""
    name = "FurAffinity"
    patterns = [r'furaffinity\.net', r'xfuraffinity\.net']
    replacement = "xfuraffinity.net"


class ImgurLink(SimpleWebsiteLink):
    """Imgur link handler."""
    name = "Imgur"
    patterns = [r'imgur\.com']
    replacement = "imgur.com"  # No alternative available yet


class WeiboLink(SimpleWebsiteLink):
    """Weibo link handler."""
    name = "Weibo"
    patterns = [r'weibo\.com', r'weibo\.cn']
    replacement = "weibo.com"  # No alternative available yet
    
class Rule34Link(SimpleWebsiteLink):
    """Rule34 link handler."""
    name="Rule34"
    patterns = [r'rule34\.xxx', r'rule34\.paheal\.net']
    replacement = "rule34.xxx" # No alternative available
    
    def _clean_tracking_params(self, url: str) -> str:
        return url

websites = [
    TwitterLink,
    InstagramLink,
    TikTokLink,
    RedditLink,
    YouTubeLink,
    ThreadsLink,
    BlueskyLink,
    SnapchatLink,
    FacebookLink,
    PixivLink,
    TwitchLink,
    SpotifyLink,
    DeviantArtLink,
    MastodonLink,
    TumblrLink,
    BiliBiliLink,
    IFunnyLink,
    FurAffinityLink,
    ImgurLink,
    WeiboLink,
    Rule34Link
]


def fix_link(url: str) -> Optional[str]:
    """
    Try to fix a URL using available website handlers.
    
    :param url: The URL to fix
    :return: Fixed URL if a handler is found, None otherwise
    """
    for website_class in websites:
        website = website_class.if_valid(url)
        if website:
            # Since render is async, we need to handle it properly
            import asyncio
            try:
                # If we're already in an async context, use the existing loop
                loop = asyncio.get_running_loop()
                # Create a task to run the async render method
                task = loop.create_task(website.render())
                return None  # We'll need to handle this differently for async
            except RuntimeError:
                # No running loop, create a new one
                return asyncio.run(website.render())
    return None


async def fix_link_async(url: str) -> Optional[str]:
    """
    Async version of fix_link.
    
    :param url: The URL to fix
    :return: Fixed URL if a handler is found, None otherwise
    """
    for website_class in websites:
        website = website_class.if_valid(url)
        if website:
            return await website.render()
    return None


def get_site_name(url: str) -> str:
    """
    Get the name of the website from a URL.
    
    :param url: The URL to check
    :return: Name of the website or the URL itself
    """
    for website_class in websites:
        website = website_class.if_valid(url)
        if website:
            return website.name
    return url
