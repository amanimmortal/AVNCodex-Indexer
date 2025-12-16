import feedparser
import requests
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class RSSClient:
    BASE_RSS_URL = "https://f95zone.to/sam/latest_alpha/latest_data.php"

    def __init__(self):
        # We use a session but no login required for public RSS usually,
        # though protections might exist.
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )

    def get_games(
        self, limit: int = 60, search: str = None, tags: List[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches games from RSS.
        """
        params = {"cmd": "rss", "cat": "games", "rows": limit}
        if search:
            params["search"] = search

        # Legacy code detail: tags were passed as tags[]=1&tags[]=2
        # requests handles list of tuples well for this.
        query_params = list(params.items())
        if tags:
            for t in tags:
                query_params.append(("tags[]", str(t)))

        try:
            resp = self.session.get(self.BASE_RSS_URL, params=query_params)
            resp.raise_for_status()

            feed = feedparser.parse(resp.content)
            games = []

            for entry in feed.entries:
                game = self._parse_entry(entry)
                if game:
                    games.append(game)

            return games
        except Exception as e:
            logger.error(f"RSS fetch failed: {e}")
            return []

    def _parse_entry(self, entry) -> Optional[Dict[str, Any]]:
        try:
            title_raw = entry.get("title", "")
            # Regex from legacy: ^\[(UPDATE|NEW)\]\s(.*?)\s\[([^\]]+)\]$
            # Simplified for robustness
            name = title_raw
            version = "Unknown"

            match = re.match(
                r"^\[(?:UPDATE|NEW|GAME)\]\s(.*?)(?:\s\[([^\]]+)\])?$",
                title_raw.strip(),
            )
            if match:
                name = match.group(1).strip()
                version = match.group(2).strip() if match.group(2) else "Unknown"

            # Author cleaning
            author_raw = entry.get("author", "")
            author = re.sub(
                r"\s*<rss@f95>\s*", "", author_raw, flags=re.IGNORECASE
            ).strip()

            # Thread ID extraction
            link = entry.get("link", "")
            thread_id = self._extract_thread_id(link)
            if not thread_id:
                return None

            return {
                "id": thread_id,
                "name": name,
                "version": version,
                "author": author,
                "url": link,
                "pub_date": entry.get("published"),
                "tags": [t.get("term") for t in entry.get("tags", [])],
            }
        except Exception as e:
            logger.warning(f"Failed to parse RSS entry: {e}")
            return None

    def _extract_thread_id(self, url: str) -> Optional[int]:
        # Matches /threads/slug.12345/ or /threads/12345/
        match = re.search(r"\.(\d+)/?$", url)
        if match:
            return int(match.group(1))

        match = re.search(r"threads/(\d+)(?:/|$)", url)
        if match:
            return int(match.group(1))

        return None
