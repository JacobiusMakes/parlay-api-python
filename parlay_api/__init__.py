"""ParlayAPI Python SDK.

A drop-in replacement for the ``the-odds-api`` Python clients with
extensions for player props, prediction markets, and WebSocket
streaming.

Quickstart
==========

.. code-block:: python

    from parlay_api import ParlayAPI

    client = ParlayAPI(api_key="YOUR_KEY")

    # TOA-compatible endpoints (identical paths and response shapes)
    sports = client.sports()
    odds = client.odds(
        "baseball_mlb",
        regions="us",
        markets="h2h,spreads,totals",
        odds_format="american",
    )
    events = client.events("baseball_mlb")
    scores = client.scores("baseball_mlb", days_from=1)

    # ParlayAPI-specific extensions
    props = client.props(
        "baseball_mlb",
        markets=["player_strikeouts", "player_total_bases"],
        bookmakers=["draftkings", "pinnacle", "fanduel"],
    )

    # Devig helpers
    fair_over, fair_under = client.devig(over_price=-110, under_price=-110)

Migrating from the-odds-api
===========================

Step 1: ``pip install parlay-api``
Step 2: Change one import:

.. code-block:: python

    # before
    from the_odds_api import OddsAPI
    client = OddsAPI(api_key=KEY)

    # after
    from parlay_api import ParlayAPI as OddsAPI  # alias keeps the rest unchanged
    client = OddsAPI(api_key=KEY)

The same paths (``/v4/sports``, ``/v4/sports/{sport}/odds``, etc.) and
response shapes work without further changes.
"""
from __future__ import annotations

__version__ = "0.1.0"

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

DEFAULT_BASE_URL = "https://parlay-api.com"
DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = f"parlay-api-python/{__version__}"


class ParlayAPIError(Exception):
    """Base exception for all SDK errors."""


class InvalidAPIKeyError(ParlayAPIError):
    """Raised when the API key is missing, malformed, or revoked."""


class CreditLimitExceededError(ParlayAPIError):
    """Raised when the account hits its monthly credit cap."""


class RateLimitedError(ParlayAPIError):
    """Raised when the per-second rate limit fires."""


class TierGatedError(ParlayAPIError):
    """Raised when the requested feature requires a higher tier."""


@dataclass
class Quota:
    """Snapshot of API key usage state, returned on every successful call."""
    requests_used: int | None
    requests_remaining: int | None
    requests_last: int | None


class ParlayAPI:
    """Synchronous ParlayAPI client.

    Args:
        api_key: Your ParlayAPI key. Sign up at parlay-api.com.
        base_url: Override for testing or self-hosted instances.
        timeout: Request timeout in seconds.
        user_agent: Custom User-Agent header.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if not api_key:
            raise InvalidAPIKeyError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self._last_quota: Quota | None = None

    # ------------------------------------------------------------------
    # Core HTTP plumbing
    # ------------------------------------------------------------------

    def _build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        params = dict(params or {})
        params["apiKey"] = self.api_key
        # Drop None values so we don't send "regions=None"
        clean = {k: v for k, v in params.items() if v is not None}
        # Coerce list-valued params to comma-separated, matching TOA semantics
        for k, v in list(clean.items()):
            if isinstance(v, (list, tuple, set)):
                clean[k] = ",".join(str(x) for x in v)
            elif isinstance(v, bool):
                clean[k] = "true" if v else "false"
        qs = urllib.parse.urlencode(clean, doseq=False)
        return f"{self.base_url}{path}?{qs}"

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self._build_url(path, params)
        req = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._last_quota = Quota(
                    requests_used=_h_int(resp, "x-requests-used"),
                    requests_remaining=_h_int(resp, "x-requests-remaining"),
                    requests_last=_h_int(resp, "x-requests-last"),
                )
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body)
            except json.JSONDecodeError:
                detail = {"message": body}
            self._handle_error(e.code, detail)
        except urllib.error.URLError as e:
            raise ParlayAPIError(f"network error: {e}")

    def _handle_error(self, status: int, detail: Any) -> None:
        msg = ""
        if isinstance(detail, dict):
            msg = detail.get("message") or detail.get("detail") or str(detail)
        else:
            msg = str(detail)
        if status == 401:
            raise InvalidAPIKeyError(msg or "Unauthorized")
        if status == 403:
            if "credit" in msg.lower() or "limit" in msg.lower():
                raise CreditLimitExceededError(msg)
            raise TierGatedError(msg or "Forbidden")
        if status == 429:
            raise RateLimitedError(msg or "Rate limited")
        raise ParlayAPIError(f"HTTP {status}: {msg}")

    @property
    def last_quota(self) -> Quota | None:
        """The most recent ``x-requests-*`` headers parsed from a response."""
        return self._last_quota

    # ------------------------------------------------------------------
    # the-odds-api compatible endpoints
    # ------------------------------------------------------------------

    def sports(self, all_sports: bool = False) -> list[dict]:
        """List available sports.

        Compatible with TOA ``/v4/sports``. Returns a list of dicts with
        ``key``, ``group``, ``title``, ``description``, ``active``, and
        ``has_outrights``.
        """
        return self._request("/v4/sports", {"all": all_sports} if all_sports else None)

    def odds(
        self,
        sport_key: str,
        regions: str = "us",
        markets: str | Iterable[str] = "h2h",
        bookmakers: str | Iterable[str] | None = None,
        odds_format: str = "american",
        date_format: str = "iso",
        event_ids: Iterable[str] | None = None,
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
    ) -> list[dict]:
        """Game and player-prop odds for a sport.

        ``markets`` accepts TOA core markets (``h2h``, ``spreads``,
        ``totals``, ``outrights``) plus any ParlayAPI player-prop key
        (``player_points``, ``player_strikeouts``, etc.). Pass a single
        string with comma-separated keys or an iterable.

        ``bookmakers`` filters the response to a subset of books.

        Returns a list of events. Each event has ``id``, ``sport_key``,
        ``sport_title``, ``commence_time``, ``home_team``, ``away_team``,
        and ``bookmakers`` with nested markets and outcomes.
        """
        params = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }
        if bookmakers is not None:
            params["bookmakers"] = bookmakers
        if event_ids is not None:
            params["eventIds"] = event_ids
        if commence_time_from:
            params["commenceTimeFrom"] = commence_time_from
        if commence_time_to:
            params["commenceTimeTo"] = commence_time_to
        return self._request(f"/v4/sports/{sport_key}/odds", params)

    def events(
        self,
        sport_key: str,
        date_format: str = "iso",
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
    ) -> list[dict]:
        """Upcoming events for a sport without odds.

        Compatible with TOA ``/v4/sports/{sport}/events``.
        """
        params: dict[str, Any] = {"dateFormat": date_format}
        if commence_time_from:
            params["commenceTimeFrom"] = commence_time_from
        if commence_time_to:
            params["commenceTimeTo"] = commence_time_to
        return self._request(f"/v4/sports/{sport_key}/events", params)

    def scores(
        self,
        sport_key: str,
        days_from: int | None = None,
        date_format: str = "iso",
    ) -> list[dict]:
        """Final and live scores.

        Compatible with TOA ``/v4/sports/{sport}/scores``.
        """
        params: dict[str, Any] = {"dateFormat": date_format}
        if days_from is not None:
            params["daysFrom"] = days_from
        return self._request(f"/v4/sports/{sport_key}/scores", params)

    def historical_odds(
        self,
        sport_key: str,
        date: str,
        regions: str = "us",
        markets: str | Iterable[str] = "h2h",
        odds_format: str = "american",
    ) -> list[dict]:
        """Historical odds snapshot.

        ``date`` is an ISO-8601 timestamp. Compatible with
        ``/v4/historical/sports/{sport}/odds``.
        """
        params = {
            "date": date,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
        }
        return self._request(f"/v4/historical/sports/{sport_key}/odds", params)

    # ------------------------------------------------------------------
    # ParlayAPI-specific extensions
    # ------------------------------------------------------------------

    def props(
        self,
        sport_key: str,
        markets: Iterable[str] | None = None,
        bookmakers: Iterable[str] | None = None,
        player: str | None = None,
        event_id: str | None = None,
        odds_format: str = "american",
        dfs_odds: str = "midpoint",
        limit: int = 5000,
    ) -> list[dict]:
        """Player prop snapshots across all sources.

        Returns a flat list of rows where each row carries one
        ``(book, player, market, line)`` combination with ``over_price``
        and ``under_price`` when paired. DFS pick'em props (PrizePicks,
        Sleeper, Underdog, Betr, Pick6) ship with ``line`` set even
        when prices are null.

        ``dfs_odds`` accepts ``"midpoint"`` (default, +100/-100 zero-vig)
        or ``"effective"`` (per-book implied payout odds).
        """
        params: dict[str, Any] = {
            "oddsFormat": odds_format,
            "dfsOdds": dfs_odds,
            "limit": limit,
        }
        if markets is not None:
            params["markets"] = markets
        if bookmakers is not None:
            params["bookmakers"] = bookmakers
        if player:
            params["player"] = player
        if event_id:
            params["eventId"] = event_id
        return self._request(f"/v1/sports/{sport_key}/props", params)

    def prop_markets(self, sport_key: str) -> list[dict]:
        """Available prop market keys for a sport.

        Returns one row per ``market_key`` with a ``bookmakers`` array
        listing which sources offer that market and a
        ``total_snapshots`` count for the last 60 minutes.
        """
        return self._request(f"/v1/sports/{sport_key}/props/markets")

    def futures(self, sport_key: str) -> dict:
        """Futures and outright markets grouped by competition.

        Pulls Pinnacle's outrights (championship winners, division
        winners, MVP races) plus Polymarket prediction-market futures
        when active.
        """
        return self._request(f"/v1/sports/{sport_key}/futures")

    def usage(self) -> dict:
        """Current API key usage state.

        Returns ``{ "tier": ..., "credits_used": N, "credits_remaining":
        N, "credits_total": N }``.
        """
        return self._request("/v1/usage")

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    def websocket_url(self, sport_key: str) -> str:
        """Build the WebSocket URL for a sport.

        Connect with any standard WS client. On connect, the server
        sends ``{"type":"odds_update", ...}`` with the full current
        snapshot, then push frames as prices change. Optional
        subscribe filter:

        .. code-block:: python

            import asyncio, json, websockets
            async def run():
                url = client.websocket_url("baseball_mlb")
                async with websockets.connect(url) as ws:
                    while True:
                        msg = json.loads(await ws.recv())
                        print(msg.get("type"), len(msg.get("data") or []))
            asyncio.run(run())

        WebSocket access requires Business tier or above.
        """
        scheme = "wss" if self.base_url.startswith("https") else "ws"
        host = self.base_url.split("://", 1)[1]
        return f"{scheme}://{host}/ws/odds/{sport_key}?apiKey={self.api_key}"

    # ------------------------------------------------------------------
    # Devigging math helpers (no network)
    # ------------------------------------------------------------------

    @staticmethod
    def american_to_implied(american: int | float) -> float:
        """Convert American odds to implied probability."""
        american = float(american)
        if american > 0:
            return 100.0 / (american + 100.0)
        return -american / (-american + 100.0)

    @staticmethod
    def american_to_decimal(american: int | float) -> float:
        """Convert American odds to decimal odds."""
        american = float(american)
        if american > 0:
            return american / 100.0 + 1.0
        return 100.0 / -american + 1.0

    @staticmethod
    def decimal_to_american(decimal: float) -> int:
        """Convert decimal odds to American odds (rounded to int)."""
        if decimal >= 2.0:
            return int(round((decimal - 1.0) * 100))
        return int(round(-100.0 / (decimal - 1.0)))

    @staticmethod
    def implied_to_american(prob: float) -> int:
        """Convert implied probability to American odds (rounded)."""
        if prob <= 0 or prob >= 1:
            raise ValueError(f"prob must be in (0, 1), got {prob}")
        if prob < 0.5:
            return int(round((1.0 / prob - 1.0) * 100))
        return int(round(-100.0 * prob / (1.0 - prob)))

    @classmethod
    def devig(
        cls,
        over_price: int | float,
        under_price: int | float,
        method: str = "multiplicative",
    ) -> tuple[float, float]:
        """Remove the vig from a paired Over/Under market.

        Returns ``(fair_over_prob, fair_under_prob)`` summing to 1.0.

        Methods:
          - ``"multiplicative"`` (default): each leg's probability is
            divided by the sum of probabilities. Standard for sports
            books.
          - ``"additive"``: distributes the vig equally across both
            legs. Less accurate at the extremes.
          - ``"power"``: logarithmic redistribution. Preferred for
            heavily skewed markets (e.g., -1500/+700).
        """
        p_over = cls.american_to_implied(over_price)
        p_under = cls.american_to_implied(under_price)
        total = p_over + p_under
        if total <= 0:
            raise ValueError(f"invalid market: {over_price}/{under_price}")

        if method == "multiplicative":
            return (p_over / total, p_under / total)
        if method == "additive":
            half_vig = (total - 1.0) / 2.0
            return (p_over - half_vig, p_under - half_vig)
        if method == "power":
            # Solve k such that p_over^k + p_under^k = 1
            # Bisection works; we need ~5 iterations for 6 decimals
            lo, hi = 0.5, 2.0
            for _ in range(40):
                mid = (lo + hi) / 2.0
                s = p_over ** mid + p_under ** mid
                if s > 1.0:
                    lo = mid
                else:
                    hi = mid
            k = (lo + hi) / 2.0
            return (p_over ** k, p_under ** k)
        raise ValueError(f"unknown devig method: {method!r}")

    @classmethod
    def edge(
        cls,
        book_price: int | float,
        fair_prob: float,
    ) -> float:
        """Return the percentage-point edge of a book price vs a fair
        probability. Positive means the bet is +EV.
        """
        return fair_prob - cls.american_to_implied(book_price)


def _h_int(resp, name: str) -> int | None:
    val = resp.headers.get(name) or resp.headers.get(name.title())
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


__all__ = [
    "ParlayAPI",
    "ParlayAPIError",
    "InvalidAPIKeyError",
    "CreditLimitExceededError",
    "RateLimitedError",
    "TierGatedError",
    "Quota",
    "__version__",
]
