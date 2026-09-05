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

__version__ = "0.3.3"

import json
import os
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
        api_key: Your ParlayAPI key, or omit it. Optional since 0.3.1: the
            keyless endpoints (sports, status, live board) work without one, so
            you can explore before signing up. Falls back to $PARLAYAPI_KEY.
        base_url: Override for testing or self-hosted instances.
        timeout: Request timeout in seconds.
        user_agent: Custom User-Agent header.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        """`api_key` is optional so the first thing a developer types works.

        Previously `ParlayAPI()` raised, which meant `pip install parlay-api`
        followed by the obvious next line failed before you could see any data,
        even though endpoints like /v1/sports, /v1/status and the live board
        need no key at all. The MCP server has always been keyless-first; this
        brings the SDK in line, so someone can explore and *then* sign up.

        Falls back to the PARLAYAPI_KEY environment variable when no key is
        passed. Keyed calls still raise InvalidAPIKeyError when no key is
        available, so authenticated endpoints fail with the same clear error as
        before, just at call time instead of construction time. Passing a key
        positionally keeps working exactly as it did.
        """
        api_key = api_key or os.environ.get("PARLAYAPI_KEY") or ""
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

    def _request(self, path: str, params: dict[str, Any] | None = None,
                 method: str = "GET", json_body: Any | None = None) -> Any:
        url = self._build_url(path, params)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
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

    # ------------------------------------------------------------------
    # Value hunting (ParlayAPI extensions beyond the TOA-compatible core)
    # ------------------------------------------------------------------

    def arbitrage(
        self,
        sport_key: str,
        min_profit: float = 0.0,
        exclude_exchanges: bool = False,
        markets: str | Iterable[str] | None = None,
    ) -> list[dict]:
        """Guaranteed-profit arbitrage opportunities across books.

        Returns bets where the combined implied probability across books is
        under 100%. Soccer and other 3-way (home/draw/away) markets are
        supported, including arbs anchored on the draw. ``min_profit`` is a
        percent (e.g. ``1.5`` for 1.5%).
        """
        params: dict[str, Any] = {"minProfit": min_profit}
        if exclude_exchanges:
            params["exclude_exchanges"] = exclude_exchanges
        if markets is not None:
            params["markets"] = markets
        return self._request(f"/v1/sports/{sport_key}/arbitrage", params)

    def ev(
        self,
        sport_key: str,
        sharp_book: str = "pinnacle",
        min_edge: float = 2.0,
        markets: str | Iterable[str] | None = None,
    ) -> list[dict]:
        """Positive-EV bets vs a sharp book's no-vig fair line.

        Compares each soft book against the no-vig fair probability from a
        sharp book (default Pinnacle). Three-way soccer markets use a
        dedicated no-vig pass over home/draw/away, so +EV on the draw
        surfaces too. ``min_edge`` is a percent (e.g. ``3`` for 3%).
        """
        params: dict[str, Any] = {"sharpBook": sharp_book, "minEdge": min_edge}
        if markets is not None:
            params["markets"] = markets
        return self._request(f"/v1/sports/{sport_key}/ev", params)

    def consensus(
        self,
        sport_key: str,
        markets: str | Iterable[str] | None = None,
    ) -> list[dict]:
        """Consensus (average / best / worst) odds across all books.

        A sharp baseline per (event, market, player, line). Soccer and
        other 3-way markets return separate home, draw, and away rows.
        """
        params: dict[str, Any] = {}
        if markets is not None:
            params["markets"] = markets
        return self._request(f"/v1/sports/{sport_key}/consensus", params)

    def middles(
        self,
        sport_key: str,
        min_gap: float = 1.0,
        markets: str | Iterable[str] | None = None,
        include_props: bool = True,
    ) -> dict:
        """Cross-book middle opportunities.

        Take the Over at a low line on one book and the Under at a higher
        line on another so a window of whole numbers cashes both bets.
        Scans game totals, spreads, AND player-total props. Each result
        carries the window, the numbers that hit, and per-$100 economics
        (``profit_if_hit`` / ``net_if_above_window`` / ``net_if_below_window``).
        ``min_gap`` is the minimum window width in points/runs/goals.
        """
        params: dict[str, Any] = {"min_gap": min_gap, "include_props": include_props}
        if markets is not None:
            params["markets"] = markets
        return self._request(f"/v1/sports/{sport_key}/middles", params)

    # ------------------------------------------------------------------
    # Decision layer ("should I bet this?")
    # ------------------------------------------------------------------

    def verdict(
        self,
        sport: str,
        side: str,
        market: str = "h2h",
        home: str | None = None,
        away: str | None = None,
        event: str | None = None,
        team: str | None = None,
        player: str | None = None,
        line: float | None = None,
        book: str | None = None,
        price: str | int | None = None,
        region: str | None = None,
        books: str | Iterable[str] | None = None,
        bankroll: float | None = None,
        kelly: float = 0.5,
        sharp_book: str = "pinnacle",
    ) -> dict:
        """Grade one bet in a single call. 5 credits.

        Returns the no-vig fair price, the best book YOU can bet at, your-price
        EV (pass ``book`` or ``price``), optional Kelly stake (pass ``bankroll``),
        line movement, and a plain-English BET / LEAN / FAIR / PASS call. Scope
        the best-price shop to books you can use with ``region`` (us/eu/uk/au/ca)
        or an exact ``books`` list, or save them once via ``set_bettable_books``.

        Identify the game with ``home``+``away``, ``event`` ("Away @ Home"), or a
        single ``team``. Player-prop markets need ``player`` (and usually ``line``).
        """
        params: dict[str, Any] = {
            "sport": sport, "side": side, "market": market, "home": home,
            "away": away, "event": event, "team": team, "player": player,
            "line": line, "book": book, "price": price, "region": region,
            "books": books, "bankroll": bankroll, "kelly": kelly,
            "sharpBook": sharp_book,
        }
        return self._request("/v1/verdict", params)

    def parlay_verdict(
        self,
        legs: Iterable[dict],
        region: str | None = None,
        books: str | Iterable[str] | None = None,
        book: str | None = None,
        stake: float | None = None,
        bankroll: float | None = None,
        kelly: float | None = None,
        sharp_book: str | None = None,
    ) -> dict:
        """Grade a 2-12 leg parlay in one call. 10 credits.

        ``legs`` is a list of dicts, each shaped like a ``verdict`` call:
        ``{"sport", "market", "side", "home"/"away" or "team", "player", "line"}``.
        Returns each leg's fair-vs-best, the combined no-vig fair price, the single
        BEST BOOK to place the whole slip at, the parlay EV, the weakest leg,
        same-game correlation warnings, and (with ``stake``) the payout.
        """
        body: dict[str, Any] = {"legs": list(legs)}
        for key, val in (
            ("region", region), ("books", books), ("book", book),
            ("stake", stake), ("bankroll", bankroll), ("kelly", kelly),
            ("sharpBook", sharp_book),
        ):
            if val is not None:
                body[key] = list(val) if key == "books" and isinstance(
                    val, (list, tuple, set)) else val
        return self._request("/v1/parlay/verdict", method="POST", json_body=body)

    def best_bets(
        self,
        sport_key: str,
        region: str | None = None,
        books: str | Iterable[str] | None = None,
        limit: int = 20,
        min_edge: float = 2.0,
        min_books: int = 4,
        markets: str | Iterable[str] | None = None,
    ) -> dict:
        """The +EV bets worth making right now, ranked. 10 credits.

        The discovery half of ``verdict``: scans the sport's board, grades every
        candidate with the same no-vig engine, keeps only bets that are +EV at a
        book YOU can bet at, and ranks by edge. Also returns ``edge_alerts``
        (books showing a price far off the market). Region/books/prefs aware.
        """
        params: dict[str, Any] = {
            "region": region, "books": books, "limit": limit,
            "min_edge": min_edge, "min_books": min_books, "markets": markets,
        }
        return self._request(f"/v1/sports/{sport_key}/best-bets", params)

    def set_bettable_books(
        self,
        region: str | None = None,
        books: str | Iterable[str] | None = None,
    ) -> dict:
        """Remember which books/region you can bet at, so ``verdict`` and
        ``best_bets`` scope recommendations to them without repeating it every
        call. Pass ``region`` (us/eu/uk/au/ca) OR an exact ``books`` list. No credits.
        """
        params: dict[str, Any] = {"region": region, "books": books}
        return self._request("/v1/verdict/prefs", params, method="POST")

    def bettable_books(self) -> dict:
        """Return your saved book/region preference. No credits."""
        return self._request("/v1/verdict/prefs")

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
