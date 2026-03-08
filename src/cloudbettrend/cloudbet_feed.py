from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


class CloudbetAPIError(RuntimeError):
    pass


EMBEDDED_DEFAULT_API_KEY = (
    "eyJhbGciOiJSUzI1NiIsImtpZCI6IkhKcDkyNnF3ZXBjNnF3LU9rMk4zV05pXzBrRFd6cEdw"
    "TzAxNlRJUjdRWDAiLCJ0eXAiOiJKV1QifQ.eyJhY2Nlc3NfdGllciI6InRyYWRpbmciLCJleHAi"
    "OjE5OTYyMzk5ODIsImlhdCI6MTY4MDg3OTk4MiwianRpIjoiNDM2Yzc1NjgtMTM0Ny00MDJhLTg4"
    "ZDMtZDlhZmU3OGQ1MDdiIiwic3ViIjoiNDM4MzY1YTUtMzQ0Yi00NTRmLWE5NmQtM2YyMWUzMDc1"
    "YmYwIiwidGVuYW50IjoiY2xvdWRiZXQiLCJ1dWlkIjoiNDM4MzY1YTUtMzQ0Yi00NTRmLWE5NmQt"
    "M2YyMWUzMDc1YmYwIn0.4eI0AK7z17EyutBgx_0FLUc9r5nWR_oUuiurGPyNlcGSz3853wkipm1u"
    "l_-oIlijPbaIha1UoD_2v3u-X48cJsmQglLNyst-2UPie9qQ3t8bzQUlhnHjcye7Kc-msGHNi-ML"
    "5twdRI-42sESiAECTccsB6NVebHgCqZfAh9-PVT-Hmao4c9AJiyJ2NA5QOTcBz7BJR06MTC0ZMW5"
    "Yklm001eEaDYxpBAorDmvRg5GDldlCBuQfVcvip8Zkp0uPHuAu2TJTJrw7tMYXSn7CUWWlQ_oQ7A"
    "lb-AchSOLkk7y-eUfUtu7plYJnj50wBLs-NLBzjnV3ifUhDk0etB9HNebA"
)


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
        allow_embedded_default: bool = True,
    ) -> "CloudbetFeedClient":
        api_key = os.getenv(env_var, "").strip()
        if not api_key and allow_embedded_default:
            api_key = EMBEDDED_DEFAULT_API_KEY
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

