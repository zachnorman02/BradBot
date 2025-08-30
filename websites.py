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
    routes: list[str]
    replacement: str

    def __init__(self, url: str) -> None:
        super().__init__(url)

    def is_valid(self) -> bool:
        """Check if URL matches any of our routes."""
        for route in self.routes:
            if re.match(route, self.url, re.IGNORECASE):
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
        for route in self.routes:
            if re.match(route, self.url, re.IGNORECASE):
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
    routes = [
        r"https?://(?:www\.|m\.|g\.|t\.|d\.)?(twitter\.com|x\.com|nitter\.net|xcancel\.com|nitter\.poast\.org|nitter\.privacyredirect\.com|lightbrd\.com|nitter\.space|nitter\.tiekoetter\.com)/([\w]+)/status/(\d+)",
        r"https?://(?:www\.|m\.|g\.|t\.|d\.)?(twitter\.com|x\.com|nitter\.net|xcancel\.com|nitter\.poast\.org|nitter\.privacyredirect\.com|lightbrd\.com|nitter\.space|nitter\.tiekoetter\.com)/([\w]+)/status/(\d+)/(photo|video)/(\d+)"
    ]
    replacement = "fxtwitter.com"



# Handles Instagram profile URLs, strips tracking params but does not replace domain
class InstagramProfileLink(SimpleWebsiteLink):
    name = "Instagram"
    routes = [
        r"https?://(?:www\.)?instagram\.com/[\w.-]+/?(?:\?.*)?$"
    ]
    replacement = "instagram.com"

class InstagramLink(SimpleWebsiteLink):
    """Instagram link handler."""
    name = "Instagram"
    routes = [
        r"https?://(?:www\.)?(instagram\.com|ddinstagram\.com)/(p|reels?|tv|share)/([\w-]+)",
        r"https?://(?:www\.)?(instagram\.com|ddinstagram\.com)/([\w-]+)/(p|reels?|tv|share)/([\w-]+)"
    ]
    replacement = "ddinstagram.com"


class TikTokLink(SimpleWebsiteLink):
    """TikTok link handler."""
    name = "TikTok"
    routes = [
        r"https?://(?:www\.|a\.|d\.|vm\.)?(tiktok\.com)/@([\w-]+)/(video|photo)/([\w-]+)",
        r"https?://(?:www\.|a\.|d\.|vm\.)?(tiktok\.com)/(t|embed)/([\w-]+)",
        r"https?://(?:www\.|a\.|d\.|vm\.)?(tiktok\.com)/([\w-]+)"
    ]
    replacement = "a.tnktok.com"


class RedditLink(SimpleWebsiteLink):
    """Reddit link handler."""
    name = "Reddit"
    routes = [
        r"https?://(?:www\.)?(reddit\.com|redditmedia\.com)/(u|r|user)/([\w-]+)/(comments|s)/([\w-]+)(?:/([\w-]+))?",
        r"https?://(?:www\.)?(reddit\.com|redditmedia\.com)/([\w-]+)"
    ]
    replacement = "vxreddit.com"


class YouTubeLink(SimpleWebsiteLink):
    """YouTube link handler."""
    name = "YouTube"
    routes = [
        r"https?://(?:www\.)?(youtube\.com|youtu\.be)/watch\?v=([\w-]+)",
        r"https?://(?:www\.)?(youtube\.com|youtu\.be)/playlist\?list=([\w-]+)",
        r"https?://(?:www\.)?(youtube\.com|youtu\.be)/shorts/([\w-]+)",
        r"https?://(?:www\.)?(youtube\.com|youtu\.be)/([\w-]+)"
    ]
    replacement = "koutube.com"
    
    def _clean_tracking_params(self, url: str) -> str:
        # Only keep 'v' and 't' query parameters, remove others
        if '?' not in url:
            return url
        base, query = url.split('?', 1)
        params = query.split('&')
        keep = []
        for param in params:
            if (
                param.startswith('v=') 
                or param.startswith('t=')
                or param.startswith('list=')
            ):
                keep.append(param)
        if keep:
            return base + '?' + '&'.join(keep)
        else:
            return base


class ThreadsLink(SimpleWebsiteLink):
    """Threads link handler."""
    name = "Threads"
    routes = [
        r"https?://(?:www\.)?(threads\.net|threads\.com)/@([\w-]+)/post/([\w-]+)"
    ]
    replacement = "fixthreads.net"


class BlueskyLink(SimpleWebsiteLink):
    """Bluesky link handler."""
    name = "Bluesky"
    routes = [
        r"https?://(?:www\.|r\.|g\.)?(bsky\.app)/profile/did:([\w-]+)/post/([\w-]+)",
        r"https?://(?:www\.|r\.|g\.)?(bsky\.app)/profile/([\w-]+)/post/([\w-]+)"
    ]
    replacement = "bskx.app"


class SnapchatLink(SimpleWebsiteLink):
    """Snapchat link handler."""
    name = "Snapchat"
    routes = [
        r"https?://(?:www\.)?(snapchat\.com)/p/([\w-]+)/([\w-]+)(?:/([\w-]+))?",
        r"https?://(?:www\.)?(snapchat\.com)/spotlight/([\w-]+)"
    ]
    replacement = "snapchat.com"


class FacebookLink(SimpleWebsiteLink):
    """Facebook link handler."""
    name = "Facebook"
    routes = [
        r"https?://(?:www\.)?(facebook\.com)/([\w-]+)/posts/([\w-]+)",
        r"https?://(?:www\.)?(facebook\.com)/share/(v|r)/([\w-]+)",
        r"https?://(?:www\.)?(facebook\.com)/reel/([\w-]+)",
        r"https?://(?:www\.)?(facebook\.com)/photo\?fbid=([\w-]+)",
        r"https?://(?:www\.)?(facebook\.com)/watch\?v=([\w-]+)",
        r"https?://(?:www\.)?(facebook\.com)/permalink.php\?story_fbid=([\w-]+)&id=([\w-]+)",
        r"https?://(?:www\.)?(facebook\.com)/groups/([\w-]+)/(posts|permalink)/([\w-]+)"
    ]
    replacement = "facebed.com"


class PixivLink(SimpleWebsiteLink):
    """Pixiv link handler."""
    name = "Pixiv"
    routes = [
        r"https?://(?:www\.)?(pixiv\.net)/member_illust.php\?illust_id=([\w-]+)",
        r"https?://(?:www\.)?(pixiv\.net)/([\w-]+)/artworks/([\w-]+)(?:/([\w-]+))?"
    ]
    replacement = "phixiv.net"


class TwitchLink(SimpleWebsiteLink):
    """Twitch link handler."""
    name = "Twitch"
    routes = [
        r"https?://(?:www\.)?(twitch\.tv)/([\w-]+)/clip/([\w-]+)"
    ]
    replacement = "fxtwitch.seria.moe"


class SpotifyLink(SimpleWebsiteLink):
    """Spotify link handler."""
    name = "Spotify"
    routes = [
        r"https?://(?:www\.)?(spotify\.com)/([\w-]+)/track/([\w-]+)"
    ]
    replacement = "fxspotify.com"


class DeviantArtLink(SimpleWebsiteLink):
    """DeviantArt link handler."""
    name = "DeviantArt"
    routes = [
        r"https?://(?:www\.)?(deviantart\.com)/([\w-]+)/(art|journal)/([\w-]+)"
    ]
    replacement = "fixdeviantart.com"


class MastodonLink(SimpleWebsiteLink):
    """Mastodon link handler."""
    name = "Mastodon"
    routes = [
        r"https?://(?:www\.)?(mastodon\.social|mstdn\.jp|mastodon\.cloud|mstdn\.social|mastodon\.world|mastodon\.online|mas\.to|techhub\.social|mastodon\.uno|infosec\.exchange)/@([\w-]+)/([\w-]+)"
    ]
    replacement = "fx.zillanlabs.tech"


class TumblrLink(SimpleWebsiteLink):
    """Tumblr link handler."""
    name = "Tumblr"
    routes = [
        r"https?://(?:www\.)?(tumblr\.com)/post/([\w-]+)(?:/([\w-]+))?",
        r"https?://(?:www\.)?(tumblr\.com)/([\w-]+)/([\w-]+)(?:/([\w-]+))?"
    ]
    replacement = "tpmblr.com"


class BiliBiliLink(SimpleWebsiteLink):
    """BiliBili link handler."""
    name = "BiliBili"
    routes = [
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/video/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/bangumi/play/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/bangumi/media/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/bangumi/v2/media-index\?media_id=([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/opus/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/dynamic/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/space/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/detail/([\w-]+)",
        r"https?://(?:www\.)?(bilibili\.com|b23\.tv|b22\.top)/m/detail/([\w-]+)"
    ]
    replacement = "vxbilibili.com"


class IFunnyLink(SimpleWebsiteLink):
    """IFunny link handler."""
    name = "IFunny"
    routes = [r'https?://(?:www\.)?ifunny\.co/[\w/-]+']
    replacement = "ifunny.co"  # No alternative available yet


class FurAffinityLink(SimpleWebsiteLink):
    """FurAffinity link handler."""
    name = "FurAffinity"
    routes = [r'https?://(?:www\.)?(furaffinity\.net|xfuraffinity\.net)/[\w/-]+']
    replacement = "xfuraffinity.net"


class ImgurLink(SimpleWebsiteLink):
    """Imgur link handler."""
    name = "Imgur"
    routes = [r'https?://(?:www\.)?imgur\.com/[\w/-]+']
    replacement = "imgur.com"  # No alternative available yet


class WeiboLink(SimpleWebsiteLink):
    """Weibo link handler."""
    name = "Weibo"
    routes = [r'https?://(?:www\.)?(weibo\.com|weibo\.cn)/[\w/-]+']
    replacement = "weibo.com"  # No alternative available yet
    
class Rule34Link(SimpleWebsiteLink):
    """Rule34 link handler."""
    name = "Rule34"
    routes = [r'https?://(?:www\.)?(rule34\.xxx|rule34\.paheal\.net)/[\w/-]+']
    replacement = "rule34.xxx" # No alternative available
    
    def _clean_tracking_params(self, url: str) -> str:
        return url

websites = [
    TwitterLink,
    InstagramProfileLink,
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
