"""Instagram Private API transport (instagrapi) — replaces ADB for posting and engagement."""

from .client import FridayInstagramClient, get_instagram_client

__all__ = ["FridayInstagramClient", "get_instagram_client"]
