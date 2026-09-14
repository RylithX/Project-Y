"""
Social Media Integrations for Yuna AI
Supports X (Twitter), Instagram, Photon Spectrum (photon.codes), and Media Burst Queuing.
"""

from .config import XConfig, InstagramConfig, PhotonConfig, MediaQueueConfig, load_social_config, load_instagram_config, save_instagram_config
from .x_client import XClient
from .insta_client import InstagramClient
from .photon_client import PhotonClient
from .media_queue import SocialMediaQueue, QueuedVideoItem, UserMediaBatch, global_media_queue
from .vision_analyzer import SocialContentAnalyzer
from .manager import SocialManager

__all__ = [
    "XConfig",
    "InstagramConfig",
    "PhotonConfig",
    "MediaQueueConfig",
    "load_social_config",
    "load_instagram_config",
    "save_instagram_config",
    "XClient",
    "InstagramClient",
    "PhotonClient",
    "SocialMediaQueue",
    "QueuedVideoItem",
    "UserMediaBatch",
    "global_media_queue",
    "SocialContentAnalyzer",
    "SocialManager"
]
