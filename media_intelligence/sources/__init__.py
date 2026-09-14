"""
Media source plugin loaders.
"""
from .youtube import YouTubeSource
from .social_media import SocialMediaSource
from .direct_media import DirectMediaSource
from .web_page import WebPageSource

__all__ = [
    "YouTubeSource",
    "SocialMediaSource",
    "DirectMediaSource",
    "WebPageSource"
]
