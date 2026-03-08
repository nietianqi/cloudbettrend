from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


class CloudbetAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudbetFeedClient:
    api_key: str
    base_url: str = "https://sports-api.cloudbet.com"
    timeout_sec: int = 20

    @classmethod
    def from_env(
        cls,
        env_var: str = "CLOUDBET_API_KEY",
        base_url: str = "https://sports-api.cloudbet.com",
    ) -> "CloudbetFeedClient":
        api_key = os.getenv(env_var, "").strip()
        if not api_key:
            raise CloudbetAPIError(
                f"Missing API key. Set environment variable {env_var}."
            )
        return cls(api_key=api_key, base_url=base_url)

    def _get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        query = query or {}
        encoded = parse.urlencode(query, doseq=True)
        url = f"{self.base_url}{path}"
        if encoded:
            url = f"{url}?{encoded}"

        req = request.Request(
            url=url,
            method="GET",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "x-api-key": self.api_key,
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_sec) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload)
        except Exception as exc:  # pragma: no cover - urllib wraps exceptions by type
            raise CloudbetAPIError(f"Cloudbet request failed: {url}; {exc}") from exc

    def list_sports(self) -> dict[str, Any]:
        return self._get("/pub/v2/odds/sports")

    def get_sport_competitions(self, sport_key: str) -> dict[str, Any]:
        return self._get(f"/pub/v2/odds/sports/{sport_key}")

    def get_competition_odds(
        self,
        competition_key: str,
        markets: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        return self._get(
            f"/pub/v2/odds/competitions/{competition_key}",
            query={"markets": list(markets)},
        )

