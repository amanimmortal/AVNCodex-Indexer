import httpx
import logging
from typing import Optional, List, Dict, Any
from app.settings import settings
import asyncio

logger = logging.getLogger(__name__)


class F95ZoneClient:
    BASE_URL = "https://f95zone.to"
    LATEST_DATA_URL = f"{BASE_URL}/sam/latest_alpha/latest_data.php"
    LOGIN_URL = f"{BASE_URL}/login/login"

    def __init__(self):
        # Persistent client to hold cookies
        self.client = httpx.AsyncClient(
            verify=False,  # F95 often has weird certs or cloudflare
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
            follow_redirects=True,
        )
        self.username = settings.F95_USERNAME
        self.password = settings.F95_PASSWORD
        self._logged_in = False

    async def close(self):
        await self.client.aclose()

    async def login(self) -> bool:
        """
        Logs in to F95Zone to get session cookies.
        """
        try:
            # 1. Get CSRF Token
            resp = await self.client.get(self.LOGIN_URL)
            resp.raise_for_status()

            # Beautiful Soup is CPU bound, run in thread
            from bs4 import BeautifulSoup

            def parse_csrf(html):
                soup = BeautifulSoup(html, "html.parser")
                token_input = soup.select_one('input[name="_xfToken"]')
                return token_input.get("value") if token_input else None

            xf_token = await asyncio.to_thread(parse_csrf, resp.text)

            if not xf_token:
                logger.error("Could not find login CSRF token.")
                return False

            # 2. Post Creds
            payload = {
                "login": self.username,
                "password": self.password,
                "_xfToken": xf_token,
                "remember": "1",
                "_xfRedirect": self.BASE_URL + "/",
            }

            login_resp = await self.client.post(self.LOGIN_URL, data=payload)
            login_resp.raise_for_status()

            # Check success (usually redirect or cookie presence)
            # httpx cookie jar access
            cookies = self.client.cookies
            if "xf_user" in cookies:
                self._logged_in = True
                logger.info(f"Logged in as {self.username}")
                return True
            else:
                logger.warning(
                    "Login failed (no xf_user cookie). Check credentials or 2FA."
                )
                return False

        except Exception as e:
            logger.error(f"Login exception: {e}")
            return False

    async def get_latest_updates(
        self, page: int = 1, rows: int = 60, sort: str = "date"
    ) -> List[Dict[str, Any]]:
        """
        Fetches the latest updates from the API.
        """
        if not self._logged_in:
            if not await self.login():
                logger.warning("Proceeding without login (results might be limited).")

        params = {
            "cmd": "list",
            "cat": "games",
            "page": page,
            "rows": rows,
            "sort": sort,
        }

        logger.info(
            "Calling F95Zone Latest Updates",
            extra={"url": self.LATEST_DATA_URL, "page": page, "rows": rows},
        )

        try:
            resp = await self.client.get(self.LATEST_DATA_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "ok":
                results = data.get("msg", {}).get("data", [])
                logger.info(
                    "F95Zone Updates Success",
                    extra={
                        "status_code": resp.status_code,
                        "result_count": len(results),
                    },
                )
                return results
            else:
                logger.error("API returned error status", extra={"response": data})
                return None
        except Exception as e:
            logger.error(
                "Failed to fetch updates", exc_info=True, extra={"error": str(e)}
            )
            return None

    async def search_games(
        self, query: str, author: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches for a specific game.
        """
        if not self._logged_in:
            await self.login()

        params = {
            "cmd": "list",
            "cat": "games",
            "search": query,
            "rows": 60,
            "sort": "date",
        }

        logger.info(
            "Calling F95Zone Search",
            extra={"url": self.LATEST_DATA_URL, "query": query},
        )

        try:
            resp = await self.client.get(self.LATEST_DATA_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("msg", {}).get("data", [])
            logger.info(
                "F95Zone Search Success",
                extra={
                    "status_code": resp.status_code,
                    "query": query,
                    "result_count": len(results),
                },
            )
            return results
        except Exception as e:
            logger.error(
                "Search failed", exc_info=True, extra={"query": query, "error": str(e)}
            )
            return []
