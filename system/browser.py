"""
system/browser.py — Browser and URL control for Emi OS v5.
Full command support: open site, search, open URL, social media shortcuts.
"""
from __future__ import annotations

import logging
import urllib.parse
import webbrowser

logger = logging.getLogger(__name__)


class BrowserController:
    """Opens URLs, performs web searches, and navigates to known sites."""

    _SITE_MAP: dict[str, str] = {
        # Search / productivity
        "youtube":       "https://youtube.com",
        "google":        "https://google.com",
        "chatgpt":       "https://chat.openai.com",
        "chat gpt":      "https://chat.openai.com",
        "gmail":         "https://mail.google.com",
        "google mail":   "https://mail.google.com",
        "google drive":  "https://drive.google.com",
        "google docs":   "https://docs.google.com",
        "google sheets": "https://sheets.google.com",
        "google maps":   "https://maps.google.com",
        "maps":          "https://maps.google.com",
        "wikipedia":     "https://wikipedia.org",
        "wiki":          "https://wikipedia.org",
        # Social media
        "twitter":       "https://twitter.com",
        "x":             "https://x.com",
        "reddit":        "https://reddit.com",
        "instagram":     "https://instagram.com",
        "facebook":      "https://facebook.com",
        "tiktok":        "https://tiktok.com",
        "snapchat":      "https://snapchat.com",
        "linkedin":      "https://linkedin.com",
        "pinterest":     "https://pinterest.com",
        "tumblr":        "https://tumblr.com",
        # Dev / tech
        "github":        "https://github.com",
        "stackoverflow": "https://stackoverflow.com",
        "stack overflow":"https://stackoverflow.com",
        "npm":           "https://npmjs.com",
        "pypi":          "https://pypi.org",
        # Entertainment
        "netflix":       "https://netflix.com",
        "twitch":        "https://twitch.tv",
        "disney":        "https://disneyplus.com",
        "disney plus":   "https://disneyplus.com",
        "hulu":          "https://hulu.com",
        "prime":         "https://primevideo.com",
        "amazon prime":  "https://primevideo.com",
        # Shopping
        "amazon":        "https://amazon.com",
        "ebay":          "https://ebay.com",
        # Music
        "spotify":       "https://open.spotify.com",
        "soundcloud":    "https://soundcloud.com",
        # Messaging
        "discord":       "https://discord.com/app",
        "telegram":      "https://web.telegram.org",
        "whatsapp":      "https://web.whatsapp.com",
        # News
        "bbc":           "https://bbc.com",
        "cnn":           "https://cnn.com",
    }

    def open_url(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        logger.info("Opening URL: %s", url)
        webbrowser.open(url)

    def open_site(self, site_name: str) -> tuple[bool, str]:
        """Open a named site. Returns (success, url)."""
        key = site_name.lower().strip()
        url = self._SITE_MAP.get(key)
        if not url:
            # Try partial match
            for k, v in self._SITE_MAP.items():
                if key in k or k in key:
                    url = v
                    break
        if not url:
            return False, ""
        self.open_url(url)
        return True, url

    def search_google(self, query: str) -> None:
        encoded = urllib.parse.quote_plus(query)
        self.open_url(f"https://www.google.com/search?q={encoded}")
        logger.info("Google search: %r", query)

    def search_youtube(self, query: str) -> None:
        encoded = urllib.parse.quote_plus(query)
        self.open_url(f"https://www.youtube.com/results?search_query={encoded}")
        logger.info("YouTube search: %r", query)

    def search_bing(self, query: str) -> None:
        encoded = urllib.parse.quote_plus(query)
        self.open_url(f"https://www.bing.com/search?q={encoded}")

    def is_known_site(self, name: str) -> bool:
        return name.lower().strip() in self._SITE_MAP
